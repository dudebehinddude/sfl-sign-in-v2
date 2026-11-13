"""Procrastinate owns durable jobs, locks, retries and periodic scheduling.

Only safe record IDs enter library task kwargs. Private mail content stays in
EmailJob and is erased after SMTP handoff or reset cancellation.
https://procrastinate.readthedocs.io/en/stable/howto/production/external_connection.html
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

import procrastinate
from psycopg import sql as pgsql
from sqlalchemy import func, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from .config import get_settings
from .database import engine
from .models import CanvasRoster, EmailJob, Training, TrainingType, utcnow

JOBS_SCHEMA = "jobs"
CANVAS_TASK = "canvas.sync"
QUIZ_TASK = "canvas.refresh_quizzes"
EMAIL_TASK = "email.deliver"
EXPIRY_TASK = "training.expire"


def create_app(conninfo: str, *, schema: str = JOBS_SCHEMA) -> procrastinate.App:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise ValueError("Invalid jobs schema")
    instance = procrastinate.App(
        connector=procrastinate.PsycopgConnector(
            conninfo=conninfo,
            kwargs={"options": f"-c search_path={schema},public"},
            min_size=1,
            max_size=5,
        )
    )
    retry = procrastinate.RetryStrategy(max_attempts=5, wait=30, linear_wait=30)

    @instance.task(name=CANVAS_TASK, lock="canvas", queueing_lock="canvas", retry=retry)
    def canvas_sync(training_type_id: str | None = None):
        from .worker import run_canvas_sync

        run_canvas_sync(training_type_id=training_type_id)

    @instance.task(
        name=QUIZ_TASK, lock="canvas-catalog", queueing_lock="canvas-catalog", retry=retry
    )
    def refresh_quizzes():
        from .worker import refresh_quiz_cache

        refresh_quiz_cache()

    @instance.task(name=EMAIL_TASK, retry=retry)
    def deliver_email(email_job_id: str):
        from .worker import run_email

        run_email(email_job_id)

    @instance.task(name=EXPIRY_TASK, retry=retry)
    def expire(training_id: str, expected_expiry: str):
        from .worker import expire_training

        expire_training(training_id, expected_expiry)

    # croniter uses the sixth field for seconds.
    @instance.periodic(cron="* * * * * */30")
    @instance.task(
        name="maintenance.dispatch", lock="maintenance", queueing_lock="maintenance", retry=retry
    )
    def dispatch(timestamp: int):
        ensure_schedules(timestamp=timestamp)

    return instance


app = create_app(get_settings().psycopg_url)


def init_jobs(db: Engine | None = None, *, schema: str | None = None) -> None:
    """Initialize a fresh candidate's library schema; existing versions need library migrations."""
    schema = schema or JOBS_SCHEMA
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise ValueError("Invalid jobs schema")
    with (db or engine).begin() as connection:
        application_schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        exists = connection.execute(
            text("SELECT to_regclass(:table)"), {"table": f"{schema}.procrastinate_jobs"}
        ).scalar_one()
        if exists is None:
            connection.execute(
                text("SELECT set_config('search_path', :path, true)"), {"path": f"{schema},public"}
            )
            # Use the SQL shipped by the installed library, without rewriting its
            # schema or copying a second application-level workflow model.
            connection.connection.driver_connection.execute(app.schema_manager.get_schema())
        # The task body commits its domain changes before the library commits its
        # terminal state. Bridge those status commits to the staff live stream.
        # No payload, custom job state or queue implementation is added here.
        from .events import CHANNEL

        connection.connection.driver_connection.execute(
            pgsql.SQL("""
CREATE OR REPLACE FUNCTION {jobs}.sfl_canvas_status_changed() RETURNS trigger
LANGUAGE plpgsql AS $sfl$
DECLARE version bigint;
BEGIN
    UPDATE {app}.scope_revisions SET revision=revision+1
        WHERE scope='staff' RETURNING revision INTO version;
    PERFORM pg_notify({channel},json_build_object(
        'revision',version,'revisions',json_build_object('staff',version),
        'topics',json_build_array('canvas'))::text);
    RETURN NEW;
END
$sfl$;
DROP TRIGGER IF EXISTS sfl_canvas_status_changed ON {jobs}.procrastinate_jobs;
CREATE TRIGGER sfl_canvas_status_changed AFTER UPDATE OF status
ON {jobs}.procrastinate_jobs FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status AND
      NEW.task_name IN ('canvas.sync','canvas.refresh_quizzes'))
EXECUTE FUNCTION {jobs}.sfl_canvas_status_changed();
""").format(
                jobs=pgsql.Identifier(schema),
                app=pgsql.Identifier(application_schema),
                channel=pgsql.Literal(CHANNEL),
            )
        )


def _ready(session: Session) -> bool:
    return (
        session.execute(
            text("SELECT to_regclass(:table)"), {"table": f"{JOBS_SCHEMA}.procrastinate_jobs"}
        ).scalar_one()
        is not None
    )


@contextmanager
def _external_connection(session: Session):
    # A savepoint isolates AlreadyEnqueued, whose unique violation otherwise
    # aborts the caller's user/registration transaction. SET LOCAL rolls back too.
    original = session.execute(text("SHOW search_path")).scalar_one()
    with session.begin_nested():
        session.execute(
            text("SELECT set_config('search_path', :path, true)"),
            {"path": f"{JOBS_SCHEMA},{original}"},
        )
        yield session.connection().connection.driver_connection
        session.execute(text("SELECT set_config('search_path', :path, true)"), {"path": original})


def _defer(
    session: Session,
    name: str,
    kwargs: dict,
    *,
    lock: str,
    queueing_lock: str,
    schedule_at: datetime | None = None,
) -> int | None:
    options = {"lock": lock, "queueing_lock": queueing_lock}
    if schedule_at is not None:
        options["schedule_at"] = schedule_at
    try:
        with _external_connection(session) as connection:
            return app.configure_task(name, connection=connection, **options).defer(**kwargs)
    except procrastinate.exceptions.AlreadyEnqueued:
        return None


def active_canvas_jobs(session: Session) -> list[dict]:
    if not _ready(session):
        return []
    return [
        dict(row)
        for row in session.execute(
            text(f"""SELECT j.args->>'training_type_id' AS training_type_id,
                j.status::text AS status, MAX(e.at) FILTER(WHERE e.type='started') AS started_at
                FROM {JOBS_SCHEMA}.procrastinate_jobs j
                LEFT JOIN {JOBS_SCHEMA}.procrastinate_events e ON e.job_id=j.id
                WHERE j.task_name=:task AND j.status IN ('todo','doing')
                GROUP BY j.id ORDER BY j.id"""),
            {"task": CANVAS_TASK},
        ).mappings()
    ]


def active_canvas_targets(session: Session) -> set[str | None]:
    return {row["training_type_id"] for row in active_canvas_jobs(session)}


def enqueue_canvas_sync(session: Session, training_type_id: UUID | str | None = None) -> int | None:
    from .services.canvas import QUEUE_LOCK, CanvasError, CanvasSyncInProgress

    if not get_settings().canvas_configured:
        raise CanvasError("Canvas is not configured")
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": QUEUE_LOCK})
    if not _ready(session):
        raise CanvasError("Background jobs schema is not initialized")
    running = session.execute(
        text(f"""SELECT 1 FROM {JOBS_SCHEMA}.procrastinate_jobs
        WHERE task_name = :task AND status = 'doing' LIMIT 1"""),
        {"task": CANVAS_TASK},
    ).first()
    if running:
        raise CanvasSyncInProgress("Canvas synchronization is already running")
    return _defer(
        session,
        CANVAS_TASK,
        {"training_type_id": str(training_type_id) if training_type_id else None},
        lock="canvas",
        queueing_lock="canvas",
    )


def enqueue_quiz_refresh(session: Session) -> int | None:
    from .services.canvas import CanvasError

    if not _ready(session):
        raise CanvasError("Background jobs schema is not initialized")
    return _defer(session, QUIZ_TASK, {}, lock="canvas-catalog", queueing_lock="canvas-catalog")


def enqueue_email(session: Session, email_id: UUID | str) -> int | None:
    settings = get_settings()
    email = session.get(EmailJob, UUID(str(email_id)))
    if email is None or email.state in {"sent", "cancelled"}:
        return None
    if (
        not settings.smtp_host
        or not settings.smtp_from
        or (email.kind == "canvas_invite" and not settings.canvas_enrollment_url)
    ):
        email.state = "unconfigured"
        email.last_error = "SMTP sender or Canvas enrollment configuration is incomplete"
        session.add(email)
        return None
    email.state, email.last_error = "pending", None
    session.add(email)
    return _defer(
        session,
        EMAIL_TASK,
        {"email_job_id": str(email_id)},
        lock=f"email:{email_id}",
        queueing_lock=f"email:{email_id}",
    )


def cancel_email_jobs(session: Session, email_ids: list[UUID]) -> None:
    if not email_ids or not _ready(session):
        return
    ids = (
        session.execute(
            text(f"""SELECT id FROM {JOBS_SCHEMA}.procrastinate_jobs
        WHERE task_name = :task AND args->>'email_job_id' = ANY(:ids)
        AND status IN ('todo','doing')"""),
            {"task": EMAIL_TASK, "ids": [str(id) for id in email_ids]},
        )
        .scalars()
        .all()
    )
    for id in ids:
        with _external_connection(session) as connection:
            app.job_manager.cancel_job_by_id(id, abort=True, connection=connection)


def enqueue_training_expiry(
    session: Session, training_id: UUID | str, expires_at: datetime | None
) -> int | None:
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        raise ValueError("Training expiry must have a timezone")
    key = f"expiry:{training_id}:{expires_at.isoformat()}"
    return _defer(
        session,
        EXPIRY_TASK,
        {"training_id": str(training_id), "expected_expiry": expires_at.isoformat()},
        lock=f"expiry:{training_id}",
        queueing_lock=key,
        schedule_at=expires_at,
    )


def ensure_schedules(db: Engine | None = None, *, timestamp: int | None = None) -> None:
    """Library periodic dispatcher applies the configured Canvas interval and repairs missing defers."""
    settings = get_settings()
    now = (
        datetime.fromtimestamp(timestamp, tz=utcnow().tzinfo) if timestamp is not None else utcnow()
    )
    with Session(db or engine) as session:
        if settings.canvas_configured and not active_canvas_targets(session):
            timestamps = session.exec(
                select(TrainingType.canvas_synced_at).where(
                    TrainingType.active, TrainingType.canvas_assignment_id.is_not(None)
                )
            ).all()
            last_roster = session.exec(select(func.max(CanvasRoster.last_synced_at))).one()
            due = any(
                t is None or (now - t).total_seconds() >= settings.canvas_sync_seconds
                for t in timestamps
            )
            if due or (
                not timestamps
                and (
                    last_roster is None
                    or (now - last_roster).total_seconds() >= settings.canvas_sync_seconds
                )
            ):
                enqueue_canvas_sync(session)
        for email in session.exec(
            select(EmailJob).where(EmailJob.state.in_(["pending", "unconfigured"]))
        ).all():
            enqueue_email(session, email.id)
        for cert in session.exec(
            select(Training).where(Training.revoked_at.is_(None), Training.expires_at > now)
        ).all():
            enqueue_training_expiry(session, cert.id, cert.expires_at)
        session.commit()
