"""Canvas administration. Network requests run in the background, never in these routes."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlmodel import select

from ..config import get_settings
from ..events import audit, publish
from ..jobs import enqueue_canvas_sync, enqueue_quiz_refresh
from ..models import CanvasQuiz, CanvasRoster, ExternalIdentity, Permission, TrainingType, User
from ..responses import Page
from ..security import DB, Actor, require
from ..services.canvas import (
    CanvasError,
    CanvasSyncInProgress,
    attach_cached_canvas,
    canvas_issuer,
    canvas_status,
)
from .common import get_or_404

router = APIRouter(prefix="/api/admin", tags=["canvas"])
CanvasReader = Annotated[Actor, Depends(require(Permission.CANVAS_READ))]
CanvasWriter = Annotated[Actor, Depends(require(Permission.CANVAS_WRITE))]


class SyncInput(BaseModel):
    training_type_id: UUID | None = None


class QueuedResponse(BaseModel):
    status: str = "queued"
    message: str


class QuizItem(BaseModel):
    id: str
    title: str
    points_possible: float | None


class CanvasPerson(BaseModel):
    id: UUID
    display_name: str
    email: str | None
    canvas_id: str
    user_id: UUID | None
    conflict: str | None


class CanvasOverview(BaseModel):
    status: Literal["unconfigured", "running", "error", "idle"]
    started_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None


class TrainingSyncStatus(BaseModel):
    training_type_id: UUID
    name: str
    canvas_assignment_id: str | None
    started_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    status: Literal["unconfigured", "running", "error", "idle"]


class CanvasStatus(BaseModel):
    configured: bool
    setup_message: str | None
    overview: CanvasOverview
    trainings: list[TrainingSyncStatus]
    unmatched: list[CanvasPerson]
    conflicts: list[CanvasPerson]


@router.get("/canvas/status", response_model=CanvasStatus)
def status(session: DB, actor: CanvasReader):
    return canvas_status(session)


@router.get("/canvas/people", response_model=Page[CanvasPerson])
def people(
    session: DB,
    actor: CanvasReader,
    search: str = Query("", max_length=100),
    binding: Literal["unmatched", "conflicts", "all"] = "unmatched",
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
):
    statement = (
        select(CanvasRoster, ExternalIdentity)
        .join(ExternalIdentity)
        .where(ExternalIdentity.provider == "canvas_id", ExternalIdentity.issuer == canvas_issuer())
    )
    if binding == "unmatched":
        statement = statement.where(ExternalIdentity.user_id.is_(None))
    elif binding == "conflicts":
        statement = statement.where(CanvasRoster.identity_conflict.is_not(None))
    if search.strip():
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(CanvasRoster.display_name.ilike(pattern), CanvasRoster.email.ilike(pattern))
        )
    total = session.exec(select(func.count()).select_from(statement.subquery())).one()
    rows = session.exec(
        statement.order_by(func.lower(CanvasRoster.display_name), CanvasRoster.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": roster.id,
                "display_name": roster.display_name,
                "email": roster.email,
                "canvas_id": identity.value,
                "user_id": identity.user_id,
                "conflict": roster.identity_conflict,
            }
            for roster, identity in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/canvas/quizzes")
def quizzes(session: DB, actor: CanvasReader):
    rows = session.exec(select(CanvasQuiz).order_by(CanvasQuiz.title)).all()
    return {
        "items": [QuizItem.model_validate(row, from_attributes=True) for row in rows],
        "refreshed_at": session.exec(select(func.max(CanvasQuiz.fetched_at))).one(),
    }


@router.post("/canvas/quizzes/refresh", status_code=202, response_model=QueuedResponse)
def refresh_quizzes(session: DB, actor: CanvasWriter):
    if not get_settings().canvas_configured:
        raise HTTPException(
            503, "Configure Canvas credentials and course before refreshing quizzes"
        )
    try:
        id = enqueue_quiz_refresh(session)
    except CanvasError as exc:
        raise HTTPException(503, str(exc)) from exc
    audit(session, "canvas.quiz_refresh_requested", "canvas_quizzes", actor_id=actor.user.id)
    publish(session, "canvas")
    session.commit()
    return QueuedResponse(
        message="Quiz catalog refresh queued" if id else "Quiz catalog refresh is already queued"
    )


@router.post("/canvas/sync", status_code=202, response_model=QueuedResponse)
def sync(session: DB, actor: CanvasWriter, data: SyncInput | None = None):
    training_id = data.training_type_id if data else None
    if training_id:
        training = get_or_404(session, TrainingType, training_id)
        if not training.active or not training.canvas_assignment_id:
            raise HTTPException(
                409, "Select a Canvas quiz for this active training before synchronizing"
            )
    try:
        id = enqueue_canvas_sync(session, training_id)
    except CanvasSyncInProgress as exc:
        raise HTTPException(409, str(exc)) from exc
    except CanvasError as exc:
        raise HTTPException(503, str(exc)) from exc
    audit(session, "canvas.sync_requested", "training_types", training_id, actor.user.id)
    publish(session, "canvas")
    session.commit()
    return QueuedResponse(
        message="Canvas synchronization queued"
        if id
        else "Canvas synchronization is already queued"
    )


@router.post("/users/{user_id}/canvas-sync", status_code=202)
def match_user(user_id: UUID, session: DB, actor: CanvasWriter):
    result = attach_cached_canvas(session, get_or_404(session, User, user_id))
    audit(session, "canvas.user_matched", "users", user_id, actor.user.id)
    publish(session, "canvas", "trainings")
    session.commit()
    return result
