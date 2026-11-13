from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import (
    EmailJob,
    ExternalIdentity,
    PasswordReset,
    Role,
    User,
    utcnow,
)


def canonical_email(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    if normalized.endswith("@uncc.edu"):
        normalized = normalized[:-9] + "@charlotte.edu"
    return normalized


def find_user(session: Session, identifier: str) -> User | None:
    identity = session.exec(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == "student_id",
            ExternalIdentity.issuer == "charlotte",
            ExternalIdentity.value == identifier.strip(),
        )
    ).first()
    return session.get(User, identity.user_id) if identity and identity.user_id else None


def add_student_identifier(session: Session, user: User, value: str):
    identity = ExternalIdentity(
        user_id=user.id,
        provider="student_id",
        issuer="charlotte",
        value=value.strip(),
    )
    session.add(identity)
    return identity


def lock_user(session: Session, user_id):
    """Credential/contact mutations serialize with reset issuance and completion."""
    return session.exec(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def set_recovery_email(session: Session, user: User, email: str | None, actor) -> bool:
    user = lock_user(session, user.id)
    normalized = canonical_email(email)
    changed = normalized != user.email
    if (
        changed
        and user.password_hash
        and actor.user.id != user.id
        and actor.role != Role.SUPERADMIN
    ):
        raise HTTPException(
            403, "Only the account owner or a superadmin may change an account's recovery email"
        )
    if changed:
        now = utcnow()
        for reset in session.exec(
            select(PasswordReset).where(
                PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)
            )
        ).all():
            reset.used_at = now
            session.add(reset)
        mail = session.exec(
            select(EmailJob).where(
                EmailJob.user_id == user.id,
                EmailJob.kind == "password_reset",
                EmailJob.state.not_in(["sent", "cancelled"]),
            )
        ).all()
        from ..jobs import cancel_email_jobs

        cancel_email_jobs(session, [job.id for job in mail])
        for job in mail:
            job.state = "cancelled"
            job.payload = {}
            job.last_error = "Recovery email changed; link invalidated"
            session.add(job)
    user.email = normalized
    session.add(user)
    return changed
