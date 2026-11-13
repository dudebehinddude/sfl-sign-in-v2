from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, func, text
from sqlmodel import select

from ..config import get_settings
from ..events import audit, publish
from ..models import AuthSession, EmailJob, LoginAttempt, PasswordReset, User, utcnow
from ..responses import AuthResponse
from ..schemas import LoginInput, PasswordChange, PasswordResetInput, PasswordResetRequest
from ..security import (
    DB,
    CurrentActor,
    actor_for_token,
    check_origin,
    create_auth_session,
    hash_password,
    new_token,
    session_payload,
    token_hash,
    verify_password,
)
from ..services.identity import canonical_email, find_user, lock_user

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/login", response_model=AuthResponse)
def login(data: LoginInput, request: Request, response: Response, session: DB):
    check_origin(request.headers.get("origin"), required=True)
    key = token_hash(
        (request.client.host if request.client else "unknown") + ":" + data.identifier.casefold()
    )
    lock = int(key[:15], 16)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    attempts = session.exec(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.key_hash == key,
            LoginAttempt.occurred_at > utcnow() - timedelta(minutes=15),
        )
    ).one()
    if attempts >= 10:
        raise HTTPException(429, "Too many sign-in attempts; try again in fifteen minutes")
    user = find_user(session, data.identifier)
    if not user and "@" in data.identifier:
        candidates = session.exec(
            select(User).where(User.email == canonical_email(data.identifier))
        ).all()
        user = candidates[0] if len(candidates) == 1 else None
    # Same password work for absent accounts, to reduce obvious account enumeration.
    valid = verify_password(
        data.password,
        user.password_hash
        if user and user.password_hash
        else "scrypt$00000000000000000000000000000000$" + "0" * 128,
    )
    if not user or not user.active or not user.password_hash or not valid:
        session.add(LoginAttempt(key_hash=key))
        audit(session, "auth.login_failed", "users", identifier_hash=token_hash(data.identifier))
        session.commit()
        raise HTTPException(401, "Identifier or password is incorrect")
    session.execute(delete(LoginAttempt).where(LoginAttempt.key_hash == key))
    auth, token = create_auth_session(session, user)
    audit(session, "auth.login", "users", user.id, user.id)
    session.commit()
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    return session_payload(actor_for_token(session, token))


@router.get("/me", response_model=AuthResponse)
def me(actor: CurrentActor):
    return session_payload(actor)


@router.post("/logout")
def logout(response: Response, session: DB, actor: CurrentActor):
    actor.session.revoked_at = utcnow()
    session.add(actor.session)
    audit(session, "auth.logout", "users", actor.user.id, actor.user.id)
    publish(session, "permissions")
    session.commit()
    response.delete_cookie(get_settings().session_cookie, path="/")
    return {"ok": True}


@router.post("/password")
def change_password(data: PasswordChange, session: DB, actor: CurrentActor):
    user = lock_user(session, actor.user.id)
    if not user.password_hash or not verify_password(data.current_password, user.password_hash):
        raise HTTPException(403, "Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    session.add(user)
    from ..models import AuthSession

    for auth in session.exec(
        select(AuthSession).where(
            AuthSession.user_id == actor.user.id,
            AuthSession.id != actor.session.id,
            AuthSession.revoked_at.is_(None),
        )
    ).all():
        auth.revoked_at = utcnow()
        session.add(auth)
    audit(session, "auth.password_changed", "users", actor.user.id, actor.user.id)
    publish(session, "permissions")
    session.commit()
    return {"ok": True}


@router.post("/password-reset/request")
def request_reset(data: PasswordResetRequest, request: Request, session: DB):
    check_origin(request.headers.get("origin"), required=True)
    if not get_settings().smtp_host or not get_settings().smtp_from:
        raise HTTPException(
            503, "Email delivery is not configured; contact a superadmin for account recovery"
        )
    key = token_hash("reset:" + canonical_email(str(data.email)))
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(key[:15], 16)})
    attempts = session.exec(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.key_hash == key, LoginAttempt.occurred_at > utcnow() - timedelta(hours=1)
        )
    ).one()
    if attempts >= 3:
        raise HTTPException(429, "Too many recovery requests; try again in an hour")
    session.add(LoginAttempt(key_hash=key))
    users = session.exec(
        select(User).where(
            User.password_hash.is_not(None),
            User.email == canonical_email(str(data.email)),
            User.active.is_(True),
        )
    ).all()
    if len(users) == 1:
        user = lock_user(session, users[0].id)
        # The candidate may have changed its recovery address before this lock.
        if (
            not user.active
            or not user.password_hash
            or user.email != canonical_email(str(data.email))
        ):
            session.commit()
            return {
                "message": "If that email belongs to an active account, a recovery email has been queued"
            }
        token = new_token()
        session.add(
            PasswordReset(
                user_id=user.id,
                token_hash=token_hash(token),
                expires_at=utcnow() + timedelta(minutes=30),
            )
        )
        mail = EmailJob(
            user_id=user.id,
            kind="password_reset",
            payload={"reset_url": get_settings().app_origin + "/reset-password?token=" + token},
        )
        session.add(mail)
        session.flush()
        from ..jobs import enqueue_email

        enqueue_email(session, mail.id)
    session.commit()
    return {
        "message": "If that email belongs to an active account, a recovery email has been queued"
    }


@router.post("/password-reset/complete")
def complete_reset(data: PasswordResetInput, request: Request, session: DB):
    check_origin(request.headers.get("origin"), required=True)
    reset = session.exec(
        select(PasswordReset).where(PasswordReset.token_hash == token_hash(data.token))
    ).first()
    if not reset or reset.used_at or reset.expires_at <= utcnow():
        raise HTTPException(400, "Recovery link is invalid or expired")
    user = lock_user(session, reset.user_id)
    reset = session.exec(
        select(PasswordReset)
        .where(PasswordReset.id == reset.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if reset.used_at or reset.expires_at <= utcnow():
        raise HTTPException(400, "Recovery link is invalid or expired")
    if not user or not user.active or not user.password_hash:
        raise HTTPException(400, "Recovery link is invalid or expired")
    user.password_hash = hash_password(data.password)
    session.add(user)
    reset.used_at = utcnow()
    session.add(reset)
    for auth in session.exec(
        select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
    ).all():
        auth.revoked_at = utcnow()
        session.add(auth)
    audit(session, "auth.password_reset", "users", user.id, user.id)
    publish(session, "permissions")
    session.commit()
    return {"message": "Password updated; sign in with your new password"}
