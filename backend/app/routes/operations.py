from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func
from sqlmodel import select

from ..database import lab_lock
from ..events import audit, publish
from ..models import (
    AuditEvent,
    KeyholderShift,
    Permission,
    ScopeRevision,
    TrainingType,
    User,
    Visit,
)
from ..responses import AuditDetail, MetricsResponse, Page, PrintingStatus, PrintResult, VisitDetail
from ..schemas import CloseVisitInput
from ..security import DB, Actor, CurrentActor, Superadmin, require
from ..services.kiosk import _check_out, label_for_user
from ..services.metrics import calculate_metrics, metrics_csv
from .common import get_or_404, page_result

router = APIRouter(prefix="/api/admin", tags=["operations"])
MetricsReader = Annotated[Actor, Depends(require(Permission.METRICS_READ))]
VisitReader = Annotated[Actor, Depends(require(Permission.VISITS_READ))]
VisitWriter = Annotated[Actor, Depends(require(Permission.VISITS_WRITE))]
CanvasReader = Annotated[Actor, Depends(require(Permission.CANVAS_READ))]
CanvasWriter = Annotated[Actor, Depends(require(Permission.CANVAS_WRITE))]
PrintReader = Annotated[Actor, Depends(require(Permission.PRINT_READ))]
PrintWriter = Annotated[Actor, Depends(require(Permission.PRINT_WRITE))]
AuditReader = Annotated[Actor, Depends(require(Permission.AUDIT_READ))]


@router.get("/overview")
def overview(request: Request, session: DB, actor: CurrentActor):
    if not actor.permissions:
        raise HTTPException(403, "Staff permissions are required")
    from ..services.canvas import canvas_status

    counts = {
        "users": session.exec(select(func.count()).select_from(User)).one(),
        "present": session.exec(
            select(func.count()).select_from(Visit).where(Visit.exit_time.is_(None))
        ).one(),
        "training_types": session.exec(select(func.count()).select_from(TrainingType)).one(),
    }
    return {
        "counts": counts,
        "canvas": canvas_status(session),
        "printing": request.app.state.printer.status(),
        "revision": session.get(ScopeRevision, "staff").revision,
    }


@router.get("/metrics", response_model=MetricsResponse)
def metrics(
    session: DB,
    actor: MetricsReader,
    start: date | None = None,
    end: date | None = None,
    timezone: str | None = None,
):
    return calculate_metrics(session, start, end, timezone)


@router.get("/metrics.csv")
def export_metrics(
    session: DB,
    actor: MetricsReader,
    start: date | None = None,
    end: date | None = None,
    timezone: str | None = None,
):
    data = calculate_metrics(session, start, end, timezone)
    return Response(
        metrics_csv(data),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="sfl-metrics-{data["start"]}-{data["end"]}.csv"'
        },
    )


@router.get("/visits", response_model=Page[VisitDetail])
def visits(
    session: DB,
    actor: VisitReader,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    user_id: UUID | None = None,
    active: bool | None = None,
):
    stmt = select(Visit, User).join(User).order_by(Visit.enter_time.desc())
    if user_id:
        stmt = stmt.where(Visit.user_id == user_id)
    if active is not None:
        stmt = stmt.where(Visit.exit_time.is_(None) if active else Visit.exit_time.is_not(None))

    def render(row):
        v, user = row
        return {
            **v.model_dump(mode="json"),
            "display_name": user.display_name,
            "user_href": f"/admin/users/{user.id}",
            "duration_seconds": v.exit_time.timestamp() - v.enter_time.timestamp()
            if v.exit_time
            else None,
        }

    return page_result(session, stmt, page, page_size, render)


@router.post("/visits/{visit_id}/close")
def close_visit(visit_id: UUID, data: CloseVisitInput, session: DB, actor: VisitWriter):
    lab_lock(session)
    visit = get_or_404(session, Visit, visit_id)
    if session.exec(
        select(KeyholderShift).where(
            KeyholderShift.user_id == visit.user_id, KeyholderShift.ended_at.is_(None)
        )
    ).first():
        raise HTTPException(
            409, "Hand off or close the lab before closing the current keyholder's visit"
        )
    if visit.exit_time:
        return visit
    _check_out(session, visit, data.forgot_to_sign_out)
    audit(
        session,
        "visit.closed",
        "visits",
        visit.id,
        actor.user.id,
        forgot_to_sign_out=data.forgot_to_sign_out,
    )
    publish(session, "visits", "occupancy")
    session.commit()
    session.refresh(visit)
    return visit


@router.get("/keyholder-shifts")
def shifts(
    session: DB,
    actor: VisitReader,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
):
    return page_result(
        session,
        select(KeyholderShift, User).join(User).order_by(KeyholderShift.started_at.desc()),
        page,
        page_size,
        lambda row: {
            **row[0].model_dump(mode="json"),
            "display_name": row[1].display_name,
            "user_href": f"/admin/users/{row[1].id}",
        },
    )


@router.get("/printing/status", response_model=PrintingStatus)
def printing_status(request: Request, actor: PrintReader):
    return request.app.state.printer.status()


@router.post("/users/{user_id}/print", response_model=PrintResult)
async def reprint_user(user_id: UUID, request: Request, session: DB, actor: PrintWriter):
    user = get_or_404(session, User, user_id)
    label = label_for_user(session, user)
    audit(session, "print.requested", "users", user.id, actor.user.id)
    session.commit()
    return await request.app.state.printer.send_label(label)


@router.get("/storage/access", status_code=204)
def storage_access(actor: Superadmin):
    return Response(status_code=204)


@router.get("/audit-events", response_model=Page[AuditDetail])
def audit_events(
    session: DB,
    actor: AuditReader,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
):
    from ..services.audit import readable_audits

    total = session.exec(select(func.count()).select_from(AuditEvent)).one()
    rows = session.exec(
        select(AuditEvent)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": readable_audits(session, rows),
        "total": total,
        "page": page,
        "page_size": page_size,
    }
