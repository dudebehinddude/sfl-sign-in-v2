import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Request

from .. import database
from ..config import get_settings
from ..responses import KioskResult, KioskState
from ..schemas import KeyholderInput, RegisterInput, TapInput
from ..security import DB, check_origin
from ..services.kiosk import execute_command
from ..services.projections import occupancy

router = APIRouter(prefix="/api/kiosk", tags=["kiosk"])


@router.get("/state", response_model=KioskState)
def state(session: DB):
    from zoneinfo import ZoneInfo

    from sqlalchemy import func
    from sqlmodel import select

    from ..models import User, Visit
    from ..services.metrics import calculate_metrics

    lab_zone = ZoneInfo(get_settings().lab_timezone)
    today = datetime.now(lab_zone).date()
    day_start = datetime.combine(today, datetime.min.time(), tzinfo=lab_zone)
    day_end = day_start + timedelta(days=1)
    today_filter = (Visit.enter_time >= day_start, Visit.enter_time < day_end)
    metrics = calculate_metrics(session, today - timedelta(days=6), today + timedelta(days=1))
    recent = session.exec(
        select(Visit, User)
        .join(User)
        .where(*today_filter)
        .order_by(func.coalesce(Visit.exit_time, Visit.enter_time).desc())
        .limit(10)
    ).all()
    today_visitors = session.exec(
        select(func.count(func.distinct(Visit.user_id))).where(*today_filter)
    ).one()
    current = occupancy(session)
    return {
        **current,
        "stats": {
            "present": len(current["occupants"]),
            "unique_visitors_today": today_visitors,
            "weekly_hours": metrics["summary"]["total_hours"],
        },
        "recent_activity": [
            {
                "user_id": str(u.id),
                "display_name": u.display_name,
                "action": "signed_out" if v.exit_time else "signed_in",
                "occurred_at": (v.exit_time or v.enter_time).isoformat(),
                "enter_time": v.enter_time.isoformat(),
                "exit_time": v.exit_time.isoformat() if v.exit_time else None,
            }
            for v, u in recent
        ],
    }


def _execute(command, data):
    # A cancelled HTTP caller must not close the still-running worker session.
    with database.Session(database.engine) as session:
        return execute_command(session, command, data)


async def perform(request, command, data, background):
    check_origin(request.headers.get("origin"), required=True)
    result = await asyncio.to_thread(_execute, command, data)
    label = result.pop("_label", None)
    if label:
        background.add_task(request.app.state.printer.send_label, label)
    return result


@router.post("/tap", response_model=KioskResult)
async def tap(data: TapInput, request: Request, background: BackgroundTasks):
    return await perform(request, "tap", data, background)


@router.post("/register", response_model=KioskResult)
async def register(data: RegisterInput, request: Request, background: BackgroundTasks):
    return await perform(request, "register", data, background)


@router.post("/keyholder", response_model=KioskResult)
async def keyholder(data: KeyholderInput, request: Request, background: BackgroundTasks):
    return await perform(request, "keyholder", data, background)
