from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, text
from sqlmodel import Session, select

from ..models import (
    ExternalIdentity,
    KeyholderShift,
    ScopeRevision,
    Training,
    TrainingType,
    User,
    Visit,
    training_type_order,
    utcnow,
)


def avatar_url(user: User) -> str | None:
    return f"/media/avatars/{user.avatar_key}" if user.avatar_key else None


def training_owner():
    return func.coalesce(Training.user_id, ExternalIdentity.user_id)


def badges_for_users(session: Session, ids: list[UUID]) -> dict:
    if not ids:
        return {}
    owner = training_owner()
    rows = session.exec(
        select(owner, TrainingType)
        .select_from(Training)
        .outerjoin(ExternalIdentity, Training.external_identity_id == ExternalIdentity.id)
        .join(TrainingType, Training.training_type_id == TrainingType.id)
        .where(
            owner.in_(ids),
            Training.awarded_at.is_not(None),
            Training.revoked_at.is_(None),
            (Training.expires_at.is_(None) | (Training.expires_at > utcnow())),
            TrainingType.active.is_(True),
        )
        .order_by(*training_type_order())
    ).all()
    grouped = defaultdict(dict)
    for user_id, definition in rows:
        grouped[user_id][definition.id] = {
            "training_type_id": str(definition.id),
            "name": definition.name,
            "icon_key": definition.icon_key,
        }
    return {user_id: list(items.values()) for user_id, items in grouped.items()}


def public_person(user: User) -> dict:
    return {"id": str(user.id), "display_name": user.display_name, "avatar_url": avatar_url(user)}


def occupancy(session: Session) -> dict:
    users = session.exec(
        select(User)
        .join(Visit)
        .where(Visit.exit_time.is_(None), User.active.is_(True))
        .order_by(User.first_name, User.last_name)
    ).all()
    badges = badges_for_users(session, [u.id for u in users])
    shift = session.exec(select(KeyholderShift).where(KeyholderShift.ended_at.is_(None))).first()
    holder = session.get(User, shift.user_id) if shift else None
    counter = session.get(ScopeRevision, "public")
    return {
        "revision": counter.revision if counter else 0,
        "lab": {
            "is_open": holder is not None,
            "keyholder": public_person(holder) if holder else None,
        },
        "occupants": [{**public_person(u), "badges": badges.get(u.id, [])} for u in users],
    }


def public_snapshot(engine) -> dict:
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        return occupancy(session)


def users_dto(session: Session, users: list[User]) -> list[dict]:
    ids = [user.id for user in users]
    identities = defaultdict(list)
    if ids:
        for identity in session.exec(
            select(ExternalIdentity).where(ExternalIdentity.user_id.in_(ids))
        ).all():
            identities[identity.user_id].append(
                {"provider": identity.provider, "value": identity.value}
            )
    badges = badges_for_users(session, ids)
    return [
        {
            **public_person(user),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "space_level": user.space_level,
            "keyholder_priority": user.keyholder_priority,
            "active": user.active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "identifiers": identities[user.id],
            "role": user.role,
            "badges": badges.get(user.id, []),
        }
        for user in users
    ]


def user_dto(session: Session, user: User) -> dict:
    return users_dto(session, [user])[0]
