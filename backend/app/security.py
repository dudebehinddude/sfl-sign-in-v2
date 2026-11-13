"""Opaque sessions and explicit authorization; a scanned ID is never a login credential."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from .config import get_settings
from .database import get_session
from .models import (
    ROLE_PERMISSIONS,
    AuthSession,
    Permission,
    Role,
    User,
    utcnow,
)

DB = Annotated[Session, Depends(get_session)]


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password(value: str) -> str:
    if not 12 <= len(value) <= 1024:
        raise ValueError("Password must contain 12 to 1024 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(value.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(value: str, encoded: str) -> bool:
    if len(value) > 1024:
        return False
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def check_origin(origin: str | None, *, required: bool = False) -> None:
    if (required and not origin) or (
        origin and origin.rstrip("/") != get_settings().app_origin.rstrip("/")
    ):
        raise HTTPException(403, "Request origin is not allowed")


@dataclass
class Actor:
    user: User
    role: Role | None
    permissions: set[Permission]
    session: AuthSession

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


def actor_for_token(session: Session, token: str | None) -> Actor:
    if not token:
        raise HTTPException(401, "Sign in to continue")
    auth = session.exec(
        select(AuthSession).where(AuthSession.token_hash == token_hash(token))
    ).first()
    if not auth or auth.revoked_at or auth.expires_at <= utcnow():
        raise HTTPException(401, "Your session has expired")
    user = session.get(User, auth.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account is unavailable")
    permissions = set(ROLE_PERMISSIONS[user.role]) if user.role else set()
    return Actor(user, user.role, permissions, auth)


def current_actor(request: Request, session: DB) -> Actor:
    actor = actor_for_token(session, request.cookies.get(get_settings().session_cookie))
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request.headers.get("origin"))
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(token_hash(csrf), actor.session.csrf_hash):
            raise HTTPException(403, "CSRF token is missing or invalid")
    return actor


CurrentActor = Annotated[Actor, Depends(current_actor)]


def require(permission: Permission):
    def dependency(actor: CurrentActor) -> Actor:
        if not actor.can(permission):
            raise HTTPException(403, "You do not have permission for this action")
        return actor

    return dependency


def require_superadmin(actor: CurrentActor) -> Actor:
    if actor.role != Role.SUPERADMIN:
        raise HTTPException(403, "Only superadmins can use this feature")
    return actor


Superadmin = Annotated[Actor, Depends(require_superadmin)]


def session_payload(actor: Actor) -> dict:
    return {
        "user": {
            "id": str(actor.user.id),
            "display_name": actor.user.display_name,
            "email": actor.user.email,
            "role": actor.role,
            "permissions": sorted(actor.permissions),
        },
        "csrf_token": actor.session.csrf_token,
    }


def create_auth_session(session: Session, user: User) -> tuple[AuthSession, str]:
    token, csrf = new_token(), new_token()
    auth = AuthSession(
        user_id=user.id,
        token_hash=token_hash(token),
        csrf_hash=token_hash(csrf),
        csrf_token=csrf,
        expires_at=utcnow() + timedelta(hours=get_settings().session_hours),
    )
    session.add(auth)
    return auth, token
