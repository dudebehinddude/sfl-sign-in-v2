"""Real Procrastinate/PostgreSQL integration, private schemas, no production I/O."""

from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlmodel import Session, select
from test_canvas import adapter, add_training
from test_canvas import db as db
from test_canvas import settings as settings

from app import jobs, worker
from app.models import EmailJob, ScopeRevision, Training, TrainingType, User, utcnow
from app.services.canvas import CanvasSyncInProgress, canvas_status


def rows(db):
    with Session(db) as session:
        return (
            session.execute(
                text(
                    f"SELECT id, task_name, status::text, args, attempts, scheduled_at FROM {jobs.JOBS_SCHEMA}.procrastinate_jobs ORDER BY id"
                )
            )
            .mappings()
            .all()
        )


def work():
    jobs.app.periodic_registry.periodic_tasks.clear()  # Test only the explicitly queued operation.
    jobs.app.run_worker(wait=False, listen_notify=False, install_signal_handlers=False)


def test_library_job_defer_commits_and_rolls_back_with_application_transaction(db):
    with Session(db) as session:
        jobs.enqueue_canvas_sync(session)
        session.rollback()
    assert rows(db) == []
    with Session(db) as session:
        id = jobs.enqueue_canvas_sync(session)
        assert id is not None
        assert jobs.enqueue_canvas_sync(session) is None
        session.add(User(first_name="Savepoint survives queue deduplication"))
        session.commit()
    assert len(rows(db)) == 1
    with Session(db) as session:
        assert len(session.exec(select(User)).all()) == 1
        assert jobs.active_canvas_targets(session) == {None}


def test_library_worker_retries_safe_failure_then_applies_full_snapshot(db, settings, monkeypatch):
    add_training(db)
    monkeypatch.setattr(worker, "CanvasClient", lambda _: adapter(settings, fail=True)[0])
    with Session(db) as session:
        jobs.enqueue_canvas_sync(session)
        session.commit()
    work()
    job = rows(db)[0]
    assert job["status"] == "todo" and job["attempts"] == 1
    with Session(db) as session:
        t = session.exec(select(TrainingType)).one()
        assert t.canvas_synced_at is None and "HTTP 503" in t.canvas_sync_error
        with jobs._external_connection(session):
            session.execute(
                text(f"UPDATE {jobs.JOBS_SCHEMA}.procrastinate_jobs SET scheduled_at = now()")
            )
        session.commit()
    monkeypatch.setattr(worker, "CanvasClient", lambda _: adapter(settings)[0])
    work()
    assert rows(db)[0]["status"] == "succeeded"
    with Session(db) as session:
        assert session.exec(select(TrainingType)).one().canvas_synced_at is not None


def test_active_library_job_is_reported_and_manual_duplicate_is_conflict(db):
    training_id = add_training(db)
    with Session(db) as session:
        id = jobs.enqueue_canvas_sync(session, training_id)
        session.commit()
    with Session(db) as session:
        with jobs._external_connection(session):
            session.execute(
                text(
                    f"UPDATE {jobs.JOBS_SCHEMA}.procrastinate_jobs SET status='doing' WHERE id=:id"
                ),
                {"id": id},
            )
        session.commit()
        status = canvas_status(session)
        assert status["trainings"][0]["status"] == "running"
        assert "runs" not in status
        with pytest.raises(CanvasSyncInProgress):
            jobs.enqueue_canvas_sync(session)


def test_unconfigured_mail_does_not_require_library_schema_or_pretend_sent(db, monkeypatch):
    with Session(db) as session:
        user = User(email="fixture@example.org")
        session.add(user)
        session.flush()
        email = EmailJob(user_id=user.id, kind="canvas_invite")
        session.add(email)
        session.flush()
        monkeypatch.setattr(jobs, "JOBS_SCHEMA", "absent_fixture_schema")
        assert jobs.enqueue_email(session, email.id) is None
        assert email.state == "unconfigured" and email.sent_at is None
        session.commit()


def test_password_reset_smtp_handoff_erases_link_and_job_kwargs_contain_only_id(db, settings):
    settings.smtp_host, settings.smtp_from = "smtp.fixture", "sender@example.org"
    with Session(db) as session:
        user = User(email="recipient@example.org")
        session.add(user)
        session.flush()
        email = EmailJob(
            user_id=user.id,
            kind="password_reset",
            payload={"reset_url": f"{settings.app_origin}/reset-password?token=fixture"},
        )
        session.add(email)
        session.flush()
        id = email.id
        jobs.enqueue_email(session, id)
        session.commit()
    assert rows(db)[0]["args"] == {"email_job_id": str(id)}
    sent = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            pass

        def send_message(self, message):
            sent.append(message)

    worker.run_email(str(id), db, settings, smtp_factory=SMTP)
    assert len(sent) == 1
    with Session(db) as session:
        email = session.get(EmailJob, id)
        assert email.state == "sent" and email.sent_at and email.payload == {}


def test_recovery_email_cancellation_is_transactional_and_does_not_store_token_in_library(
    db, settings
):
    settings.smtp_host, settings.smtp_from = "smtp.fixture", "sender@example.org"
    with Session(db) as session:
        user = User(email="recipient@example.org")
        session.add(user)
        session.flush()
        email = EmailJob(
            user_id=user.id,
            kind="password_reset",
            payload={"reset_url": f"{settings.app_origin}/reset-password?token=fixture"},
        )
        session.add(email)
        session.flush()
        id = email.id
        jobs.enqueue_email(session, id)
        session.commit()
    with Session(db) as session:
        jobs.cancel_email_jobs(session, [id])
        session.rollback()
    assert rows(db)[0]["status"] == "todo"
    with Session(db) as session:
        jobs.cancel_email_jobs(session, [id])
        email = session.get(EmailJob, id)
        email.state, email.payload = "cancelled", {}
        session.add(email)
        session.commit()
    assert rows(db)[0]["status"] == "cancelled"


def test_expiry_uses_library_future_schedule_and_timezone_equivalent_expected_time(db):
    training_id = add_training(db)
    with Session(db) as session:
        user = User()
        session.add(user)
        session.flush()
        expiry = utcnow() + timedelta(hours=1)
        cert = Training(
            user_id=user.id, training_type_id=training_id, expires_at=expiry, awarded_at=utcnow()
        )
        session.add(cert)
        session.flush()
        id = cert.id
        jobs.enqueue_training_expiry(session, id, expiry)
        assert jobs.enqueue_training_expiry(session, id, expiry) is None
        session.commit()
    assert rows(db)[0]["scheduled_at"] == expiry
    work()
    assert rows(db)[0]["status"] == "todo"
    with Session(db) as session:
        cert = session.get(Training, id)
        cert.expires_at = utcnow() - timedelta(seconds=1)
        expected = cert.expires_at.isoformat()
        session.add(cert)
        session.commit()
    worker.expire_training(str(id), expected, db)
    with Session(db) as session:
        assert session.get(ScopeRevision, "public").revision == 1


def test_periodic_dispatch_ticks_every_thirty_seconds_outside_half_hour_boundaries():
    from datetime import UTC, datetime

    app = jobs.create_app("postgresql://unused-fixture")
    periodic = next(iter(app.periodic_registry.periodic_tasks.values()))
    base = datetime(2026, 11, 9, 11, 11, 1, tzinfo=UTC).timestamp()
    first = periodic.croniter.get_next(start_time=base)
    second = periodic.croniter.get_next()
    assert datetime.fromtimestamp(first, UTC) == datetime(2026, 11, 9, 11, 11, 30, tzinfo=UTC)
    assert second - first == 30


def test_canvas_terminal_job_commit_publishes_a_final_status_invalidation(
    db, settings, monkeypatch
):
    import json

    import psycopg

    from app.events import CHANNEL

    add_training(db)
    monkeypatch.setattr(worker, "CanvasClient", lambda _: adapter(settings)[0])
    with Session(db) as session:
        jobs.enqueue_canvas_sync(session)
        session.commit()
    dsn = db.url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(dsn, autocommit=True) as listener:
        listener.execute(f"LISTEN {CHANNEL}")
        work()
        notices = [json.loads(n.payload) for n in listener.notifies(timeout=0.2)]
    assert rows(db)[0]["status"] == "succeeded"
    # Domain evidence is published before Procrastinate ends the job. A final
    # staff-only invalidation must follow that commit so the button can re-enable.
    assert notices[-1]["topics"] == ["canvas"]
    assert set(notices[-1]["revisions"]) == {"staff"}
    with Session(db) as session:
        assert canvas_status(session)["trainings"][0]["status"] == "idle"
        assert session.exec(select(TrainingType)).one().canvas_synced_at is not None
