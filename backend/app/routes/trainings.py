from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, text, update
from sqlmodel import select

from ..events import audit, publish
from ..models import (
    CanvasQuiz,
    CanvasRoster,
    ExternalIdentity,
    Permission,
    Role,
    Training,
    TrainingType,
    User,
    training_type_order,
    utcnow,
)
from ..responses import Page, TrainingDetail, TrainingTypeDetail
from ..schemas import RevokeInput, TrainingInput, TrainingTypeInput, TrainingTypePatch
from ..security import DB, Actor, require
from ..services.identity import lock_user
from ..services.projections import training_owner
from ..services.storage import require_training_icon
from .common import get_or_404, page_result

router = APIRouter(prefix="/api/admin", tags=["trainings"])
Reader = Annotated[Actor, Depends(require(Permission.TRAININGS_READ))]
Writer = Annotated[Actor, Depends(require(Permission.TRAININGS_WRITE))]


def validate_icon_reference(key: str):
    if key.startswith("training-icons/"):
        try:
            require_training_icon(key)
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(
                    422, "Uploaded training icon was not found; upload it before saving"
                ) from None
            raise


@router.get("/training-types", response_model=Page[TrainingTypeDetail])
def list_types(
    session: DB,
    actor: Reader,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    search: str = "",
):
    statement = select(TrainingType).order_by(*training_type_order())
    if search:
        statement = statement.where(TrainingType.name.ilike(f"%{search[:100]}%"))
    return page_result(session, statement, page, page_size)


@router.post("/training-types", status_code=201, response_model=TrainingTypeDetail)
def create_type(data: TrainingTypeInput, session: DB, actor: Writer):
    if actor.role == Role.OPERATOR:
        raise HTTPException(403, "Only administrators may define trainings")
    validate_icon_reference(data.icon_key)
    if data.canvas_assignment_id:
        get_or_404(session, CanvasQuiz, data.canvas_assignment_id)
    record = TrainingType(**data.model_dump())
    session.add(record)
    session.flush()
    audit(session, "training_type.created", "training_types", record.id, actor.user.id)
    publish(session, "training-types")
    session.commit()
    session.refresh(record)
    return record


@router.patch("/training-types/{training_id}", response_model=TrainingTypeDetail)
def update_type(training_id: UUID, data: TrainingTypePatch, session: DB, actor: Writer):
    if actor.role == Role.OPERATOR:
        raise HTTPException(403, "Only administrators may define trainings")
    if data.icon_key is not None:
        validate_icon_reference(data.icon_key)
    from ..services.canvas import IDENTITY_LOCK

    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IDENTITY_LOCK})
    record = get_or_404(session, TrainingType, training_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("canvas_assignment_id"):
        get_or_404(session, CanvasQuiz, changes["canvas_assignment_id"])
    changed = any(
        key in changes and getattr(record, key) != changes[key]
        for key in ["canvas_assignment_id", "canvas_minimum_score", "active"]
    )
    for key, value in changes.items():
        if value is None and key not in {"canvas_assignment_id", "canvas_minimum_score"}:
            raise HTTPException(422, f"{key} cannot be null")
        setattr(record, key, value)
    if changed:
        # Preserve already-earned awards. Only current cached eligibility is invalidated.
        session.execute(
            update(Training)
            .where(Training.training_type_id == training_id, Training.source == "canvas")
            .values(passed=False, workflow_status="configuration_changed")
        )
        record.canvas_sync_started_at = record.canvas_synced_at = None
        record.canvas_sync_error = None
    session.add(record)
    audit(session, "training_type.updated", "training_types", record.id, actor.user.id)
    publish(session, "training-types", "canvas", "trainings")
    session.commit()
    session.refresh(record)
    return record


def training_query():
    return (
        select(Training, TrainingType, ExternalIdentity, User, CanvasRoster)
        .join(TrainingType, Training.training_type_id == TrainingType.id)
        .outerjoin(ExternalIdentity, Training.external_identity_id == ExternalIdentity.id)
        .outerjoin(User, User.id == training_owner())
        .outerjoin(CanvasRoster, CanvasRoster.external_identity_id == ExternalIdentity.id)
    )


def render_training(row):
    record, definition, identity, user, roster = row
    now = utcnow()
    return {
        **record.model_dump(),
        "user_id": user.id if user else None,
        "user_name": user.display_name
        if user
        else roster.display_name
        if roster
        else "Unregistered visitor",
        "user_href": f"/admin/users/{user.id}" if user else None,
        "training_type_name": definition.name,
        "has_training": bool(
            definition.active
            and record.awarded_at is not None
            and record.revoked_at is None
            and (record.expires_at is None or record.expires_at > now)
        ),
    }


def training_dto(session, record_id):
    return render_training(session.exec(training_query().where(Training.id == record_id)).one())


@router.get("/trainings", response_model=Page[TrainingDetail])
def trainings(
    session: DB,
    actor: Reader,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    user_id: UUID | None = None,
    search: str = Query("", max_length=100),
):
    statement = training_query()
    if user_id:
        statement = statement.where(training_owner() == user_id)
    if search.strip():
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                TrainingType.name.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                func.concat(User.first_name, " ", User.last_name).ilike(pattern),
                CanvasRoster.display_name.ilike(pattern),
            )
        )
    total = session.exec(select(func.count()).select_from(statement.subquery())).one()
    rows = session.exec(
        statement.order_by(Training.created_at.desc(), Training.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [render_training(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/trainings", status_code=201, response_model=TrainingDetail)
def award(data: TrainingInput, session: DB, actor: Writer):
    get_or_404(session, User, data.user_id)
    # Serialize same-person assignments so concurrent submits cannot both pass.
    lock_user(session, data.user_id)
    now = utcnow()
    existing = session.exec(
        select(Training.id).where(
            Training.user_id == data.user_id,
            Training.training_type_id == data.training_type_id,
            Training.source == "manual",
            Training.revoked_at.is_(None),
            Training.awarded_at.is_not(None),
            or_(Training.expires_at.is_(None), Training.expires_at > now),
        )
    ).first()
    if existing:
        raise HTTPException(409, "This person already has an active manual training assignment")
    definition = get_or_404(session, TrainingType, data.training_type_id)
    if not definition.active:
        raise HTTPException(409, "Training is inactive")
    if data.expires_at and (not data.expires_at.tzinfo or data.expires_at <= utcnow()):
        raise HTTPException(422, "Expiration must be a future timezone-aware time")
    if data.awarded_at and not data.awarded_at.tzinfo:
        raise HTTPException(422, "Award time must include timezone")
    record = Training(**data.model_dump(exclude_none=True), awarded_by_user_id=actor.user.id)
    record.awarded_at = data.awarded_at or utcnow()
    session.add(record)
    session.flush()
    if record.expires_at:
        from ..jobs import enqueue_training_expiry

        enqueue_training_expiry(session, record.id, record.expires_at)
    audit(
        session,
        "training.awarded",
        "trainings",
        record.id,
        actor.user.id,
        training_type_id=str(definition.id),
        user_id=str(data.user_id),
    )
    publish(session, "trainings")
    session.commit()
    return training_dto(session, record.id)


@router.post("/trainings/{training_id}/revoke", response_model=TrainingDetail)
def revoke(training_id: UUID, data: RevokeInput, session: DB, actor: Writer):
    record = get_or_404(session, Training, training_id)
    if not record.revoked_at:
        record.revoked_at = utcnow()
        session.add(record)
        audit(
            session, "training.revoked", "trainings", record.id, actor.user.id, reason=data.reason
        )
        publish(session, "trainings")
        session.commit()
    return training_dto(session, record.id)
