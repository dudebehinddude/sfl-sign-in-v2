"""All charts and CSV share half-open, timezone-aware finalized-visit metrics."""

import csv
import io
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session

from ..config import get_settings
from ..models import utcnow


def reporting_window(start: date | None, end: date | None, timezone: str | None):
    zone = timezone or get_settings().lab_timezone
    try:
        tz = ZoneInfo(zone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, "Unknown reporting timezone") from exc
    today = datetime.now(tz).date()
    end = end or today + timedelta(days=1)
    start = start or end - timedelta(days=7)
    if end <= start or (end - start).days > 1830:
        raise HTTPException(
            422, "Choose an end after the start and a range no longer than five years"
        )
    return start, end, zone


def calculate_metrics(session: Session, start=None, end=None, timezone=None):
    # Authentication may already have queried the caller's READ COMMITTED
    # transaction. Use an independent committed, read-only snapshot for every
    # report section and keep the same semantics for JSON and CSV callers.
    bind = session.get_bind().execution_options(isolation_level="REPEATABLE READ")
    with Session(bind) as report:
        report.execute(text("SET TRANSACTION READ ONLY"))
        return _calculate_metrics(report, start, end, timezone)


def _calculate_metrics(session: Session, start=None, end=None, timezone=None):
    start, end, zone = reporting_window(start, end, timezone)
    params = {"start": start, "end": end, "zone": zone, "as_of": utcnow()}
    common = """WITH bounds AS (SELECT CAST(:start AS date)::timestamp AT TIME ZONE :zone AS a,
       CAST(:end AS date)::timestamp AT TIME ZONE :zone AS b),
    presence AS (SELECT v.*, GREATEST(v.enter_time,bounds.a) AS clipped_start,
       LEAST(COALESCE(v.exit_time,:as_of),bounds.b) AS clipped_end,
       (v.exit_time IS NOT NULL AND NOT v.forgot_to_sign_out) AS reliable
       FROM visits v CROSS JOIN bounds
       WHERE v.enter_time < bounds.b AND COALESCE(v.exit_time,:as_of) > bounds.a) """
    summary = (
        session.execute(
            text(
                common
                + """SELECT COUNT(DISTINCT user_id) AS unique_visitors, COUNT(*) AS visits,
       COUNT(*) FILTER(WHERE reliable) finalized_visits,
       COALESCE(SUM(EXTRACT(EPOCH FROM clipped_end-clipped_start)) FILTER(WHERE reliable)/3600.0,0) AS total_hours,
       COALESCE(AVG(EXTRACT(EPOCH FROM clipped_end-clipped_start)) FILTER(WHERE reliable)/60.0,0) AS average_visit_minutes,
       COUNT(*) FILTER(WHERE exit_time IS NOT NULL AND NOT reliable) excluded_visits,
       COUNT(*) FILTER(WHERE exit_time IS NULL) open_visits FROM presence"""
            ),
            params,
        )
        .mappings()
        .one()
    )
    summary = {
        k: float(v) if k in {"total_hours", "average_visit_minutes"} else int(v)
        for k, v in summary.items()
    }
    first = session.execute(
        text("""WITH bounds AS (SELECT CAST(:start AS date)::timestamp AT TIME ZONE :zone a, CAST(:end AS date)::timestamp AT TIME ZONE :zone b),
      first_visits AS (SELECT user_id,MIN(enter_time) first_at FROM visits GROUP BY user_id)
      SELECT COUNT(*) FROM first_visits,bounds WHERE first_at>=a AND first_at<b"""),
        params,
    ).scalar_one()
    summary["new_visitors"] = int(first)
    daily = (
        session.execute(
            text(
                common
                + """, days AS (SELECT day::date date,day::timestamp AT TIME ZONE :zone a,(day+interval '1 day')::timestamp AT TIME ZONE :zone b
       FROM generate_series(CAST(:start AS date), CAST(:end AS date)-1, interval '1 day') day)
       SELECT d.date, COUNT(p.id) visits,COUNT(DISTINCT p.user_id) unique_visitors,
       COALESCE(SUM(EXTRACT(EPOCH FROM LEAST(p.clipped_end,d.b)-GREATEST(p.clipped_start,d.a))) FILTER(WHERE p.reliable)/3600.0,0) total_hours
       FROM days d LEFT JOIN presence p ON p.clipped_start<d.b AND p.clipped_end>d.a GROUP BY d.date ORDER BY d.date"""
            ),
            params,
        )
        .mappings()
        .all()
    )
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": zone,
        "summary": summary,
        "daily": [
            {
                "date": row["date"].isoformat(),
                "visits": int(row["visits"]),
                "unique_visitors": int(row["unique_visitors"]),
                "total_hours": float(row["total_hours"]),
            }
            for row in daily
        ],
        "definitions": {
            "counts": "All visits overlapping the window, including open/forgotten visits; unique visitors are distinct people",
            "durations": "Completed visits not marked forgotten, clipped to requested dates; forgotten and open visits excluded",
            "average_denominator": "finalized_visits",
            "new_visitors": "First-ever visit starts within requested dates",
            "end": "Exclusive lab-local date",
        },
    }


def metrics_csv(data):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["scope", "date", "metric", "value"])
    for key, value in data["summary"].items():
        writer.writerow(["summary", "", key, value])
    for day in data["daily"]:
        for key in ["visits", "unique_visitors", "total_hours"]:
            writer.writerow(["daily", day["date"], key, day[key]])
    return output.getvalue()
