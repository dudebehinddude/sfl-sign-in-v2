from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlmodel import select

from ..database import lab_lock
from ..events import audit, publish
from ..models import (
    AuthSession,
    ExternalIdentity,
    KeyholderShift,
    Permission,
    Role,
    SpaceLevel,
    User,
    utcnow,
)
from ..responses import Page, UserDetail
from ..schemas import RoleInput, SetPassword, UserCreate, UserPatch
from ..security import DB, Actor, Superadmin, hash_password, require
from ..services.identity import add_student_identifier, find_user, lock_user, set_recovery_email
from ..services.projections import user_dto, users_dto
from .common import get_or_404

router = APIRouter(prefix="/api/admin", tags=["users"])
Reader = Annotated[Actor, Depends(require(Permission.USERS_READ))]
Writer = Annotated[Actor, Depends(require(Permission.USERS_WRITE))]
RoleWriter = Annotated[Actor, Depends(require(Permission.ROLES_WRITE))]


@router.get("/users", response_model=Page[UserDetail])
def list_users(
    session: DB,
    actor: Reader,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    search: str = Query("", max_length=100),
):
    statement = select(User)
    if search:
        statement = statement.where(
            or_(
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.id.in_(
                    select(ExternalIdentity.user_id).where(
                        ExternalIdentity.value.ilike(f"%{search}%")
                    )
                ),
            )
        )
    total = session.exec(select(func.count()).select_from(statement.subquery())).one()
    rows = session.exec(
        statement.order_by(User.first_name, User.last_name, User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": users_dto(session, rows), "total": total, "page": page, "page_size": page_size}


@router.get("/users/{user_id}", response_model=UserDetail)
def get_user(user_id: UUID, session: DB, actor: Reader):
    return user_dto(session, get_or_404(session, User, user_id))


@router.post("/users", status_code=201, response_model=UserDetail)
def create_user(data: UserCreate, session: DB, actor: Writer):
    if actor.role == Role.OPERATOR:
        raise HTTPException(403, "Only administrators may create user identities")
    lab_lock(session)
    if find_user(session, data.identifier):
        raise HTTPException(409, "Identifier is already registered")
    user = User(**data.model_dump(exclude={"identifier"}))
    session.add(user)
    session.flush()
    add_student_identifier(session, user, data.identifier)
    from ..services.canvas import attach_cached_canvas

    attach_cached_canvas(session, user)
    audit(session, "user.created", "users", user.id, actor.user.id)
    publish(session, "users")
    session.commit()
    return user_dto(session, user)


def preserve_superadmin(session, user):
    if user.role == Role.SUPERADMIN and user.active:
        another = session.exec(
            select(User.id).where(
                User.role == Role.SUPERADMIN,
                User.active.is_(True),
                User.id != user.id,
                User.password_hash.is_not(None),
            )
        ).first()
        if not another:
            raise HTTPException(409, "At least one active superadmin must remain")


@router.patch("/users/{user_id}", response_model=UserDetail)
def update_user(user_id: UUID, data: UserPatch, session: DB, actor: Writer):
    lab_lock(session)
    user = get_or_404(session, User, user_id)
    changes = data.model_dump(exclude_unset=True)
    if (
        actor.role == Role.OPERATOR
        and {"space_level", "keyholder_priority", "active"} & changes.keys()
    ):
        raise HTTPException(403, "Only administrators may change space access or activation")
    if user.role == Role.SUPERADMIN and actor.role != Role.SUPERADMIN and "active" in changes:
        raise HTTPException(403, "Only superadmins may change a superadmin's activation")
    shift = session.exec(
        select(KeyholderShift).where(
            KeyholderShift.user_id == user.id, KeyholderShift.ended_at.is_(None)
        )
    ).first()
    if shift and (
        changes.get("active") is False or changes.get("space_level") == SpaceLevel.MEMBER
    ):
        raise HTTPException(409, "Hand off or close the active keyholder shift first")
    if changes.get("active") is False:
        preserve_superadmin(session, user)
    if "email" in changes:
        set_recovery_email(
            session, user, str(changes["email"]) if changes["email"] else None, actor
        )
        changes["email"] = user.email
    for key, value in changes.items():
        if value is None and key != "email":
            raise HTTPException(422, f"{key} cannot be null")
        setattr(user, key, value)
    session.add(user)
    audit(session, "user.updated", "users", user.id, actor.user.id, fields=sorted(changes))
    publish(session, "users", "permissions")
    session.commit()
    return user_dto(session, user)


@router.get("/roles")
def roles(actor: RoleWriter):
    return {"roles": [{"name": role.value} for role in Role]}


@router.put("/users/{user_id}/role", response_model=UserDetail)
def set_role(user_id: UUID, data: RoleInput, session: DB, actor: RoleWriter):
    lab_lock(session)
    user = lock_user(session, get_or_404(session, User, user_id).id)
    if actor.role != Role.SUPERADMIN and (
        user.role == Role.SUPERADMIN or data.role == Role.SUPERADMIN
    ):
        raise HTTPException(403, "Only superadmins may grant or change superadmin access")
    if user.role == Role.SUPERADMIN and data.role != Role.SUPERADMIN:
        preserve_superadmin(session, user)
    user.role = data.role
    session.add(user)
    audit(session, "user.role_changed", "users", user.id, actor.user.id, role=data.role)
    publish(session, "permissions", "users")
    session.commit()
    return user_dto(session, user)


@router.put("/users/{user_id}/password")
def set_password(user_id: UUID, data: SetPassword, session: DB, actor: Superadmin):
    user = lock_user(session, get_or_404(session, User, user_id).id)
    user.password_hash = hash_password(data.password)
    session.add(user)
    for auth in session.exec(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    ).all():
        auth.revoked_at = utcnow()
        session.add(auth)
    audit(session, "user.password_set", "users", user_id, actor.user.id)
    publish(session, "permissions")
    session.commit()
    return {"ok": True}
