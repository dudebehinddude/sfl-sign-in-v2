"""Whole-sync truth and global training search over isolated synthetic records."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlmodel import Session, select
from test_canvas import adapter, add_training
from test_canvas import db as db
from test_canvas import settings as settings
from test_core import candidate as candidate
from test_core import login

from app import jobs
from app.models import (
    AuditEvent,
    CanvasRoster,
    ExternalIdentity,
    Training,
    TrainingType,
    User,
    utcnow,
)
from app.services.canvas import canvas_status
from app.worker import BackgroundFailure, run_canvas_sync

pytestmark = pytest.mark.postgres


def test_overall_success_never_uses_individual_training_checkpoint(db, settings):
    training_id = add_training(db)
    with Session(db) as session:
        definition = session.get(TrainingType, training_id)
        definition.canvas_synced_at = utcnow()
        session.add(definition)
        session.commit()
        assert canvas_status(session)["overview"]["last_success_at"] is None
    single, _ = adapter(settings)
    run_canvas_sync(db, settings, str(training_id), canvas_client=single)
    with Session(db) as session:
        overview = canvas_status(session)["overview"]
        assert overview["status"] == "idle" and overview["last_success_at"] is None
    whole, _ = adapter(settings)
    run_canvas_sync(db, settings, canvas_client=whole)
    with Session(db) as session:
        overview = canvas_status(session)["overview"]
        success = overview["last_success_at"]
        assert success and overview["started_at"] and overview["started_at"] <= success
        event = session.exec(
            select(AuditEvent).where(
                AuditEvent.action == "canvas.sync_completed", AuditEvent.entity_id.is_(None)
            )
        ).one()
        assert event.details["scope"] == "whole" and event.details["course_id"] == "101"
    partial_failure, _ = adapter(settings, fail=True)
    with pytest.raises(BackgroundFailure):
        run_canvas_sync(db, settings, str(training_id), canvas_client=partial_failure)
    with Session(db) as session:
        overview = canvas_status(session)["overview"]
        assert (
            overview["status"] == "idle"
            and overview["last_error"] is None
            and overview["last_success_at"] == success
        )
    whole_failure, _ = adapter(settings, fail=True)
    with pytest.raises(BackgroundFailure):
        run_canvas_sync(db, settings, canvas_client=whole_failure)
    with Session(db) as session:
        overview = canvas_status(session)["overview"]
        assert overview["status"] == "error" and "HTTP 503" in overview["last_error"]
        assert overview["last_success_at"] == success and overview["started_at"] > success


def test_overall_running_reads_real_library_started_event_and_legacy_whole_metadata(db, settings):
    add_training(db)
    previous = utcnow() - timedelta(days=1)
    with Session(db) as session:
        session.add(
            AuditEvent(
                action="canvas.sync_completed",
                entity_type="training_types",
                occurred_at=previous,
                details={"counts": {"roster": 1}},
            )
        )
        session.add_all(
            [
                AuditEvent(
                    action="canvas.sync_completed",
                    entity_type="training_types",
                    entity_id=str(uuid4()),
                    details={},
                ),
                AuditEvent(
                    action="canvas.sync_completed",
                    entity_type="training_types",
                    details={"scope": "training"},
                ),
                AuditEvent(
                    action="canvas.sync_completed",
                    entity_type="training_types",
                    details={"scope": "whole", "course_id": "other-course"},
                ),
                AuditEvent(action="canvas.sync_completed", entity_type="canvas", details={}),
            ]
        )
        session.commit()
        overview = canvas_status(session)["overview"]
        assert overview["last_success_at"] == previous and overview["started_at"] is None
        job_id = jobs.enqueue_canvas_sync(session)
        session.commit()
        overview = canvas_status(session)["overview"]
        assert overview["status"] == "running" and overview["started_at"] is None
        with jobs._external_connection(session):
            session.execute(
                text(
                    f"UPDATE {jobs.JOBS_SCHEMA}.procrastinate_jobs SET status='doing' WHERE id=:id"
                ),
                {"id": job_id},
            )
        session.commit()
        overview = canvas_status(session)["overview"]
        assert overview["status"] == "running" and overview["started_at"] is not None
        started = session.execute(
            text(
                f"SELECT MAX(at) FROM {jobs.JOBS_SCHEMA}.procrastinate_events WHERE job_id=:id AND type='started'"
            ),
            {"id": job_id},
        ).scalar_one()
        assert overview["started_at"] == started
        assert overview["last_success_at"] == previous


def test_training_search_is_global_and_counts_before_paging_with_user_filter(candidate):
    db, client = candidate["engine"], candidate["client"]
    with Session(db) as session:
        needle = User(first_name="Quinn", last_name="Needle")
        other = User(first_name="Quinn", last_name="Other")
        session.add_all([needle, other])
        filler_type = TrainingType(name="General Workshop", icon_key="orientation")
        laser = TrainingType(name="Precision Laser", icon_key="laser-cutter")
        session.add_all([filler_type, laser])
        session.flush()
        older = utcnow() - timedelta(days=1)
        for _ in range(120):
            session.add(
                Training(
                    user_id=candidate["users"]["member"],
                    training_type_id=filler_type.id,
                    awarded_at=utcnow(),
                    revoked_at=utcnow(),
                )
            )
        session.add_all(
            [
                Training(
                    user_id=needle.id, training_type_id=laser.id, awarded_at=older, created_at=older
                ),
                Training(
                    user_id=needle.id,
                    training_type_id=filler_type.id,
                    awarded_at=older,
                    created_at=older,
                ),
                Training(
                    user_id=other.id, training_type_id=laser.id, awarded_at=older, created_at=older
                ),
            ]
        )
        identity = ExternalIdentity(provider="canvas_id", issuer="fixture", value="99991")
        session.add(identity)
        session.flush()
        session.add(CanvasRoster(external_identity_id=identity.id, display_name="Remote Needle"))
        session.add(
            Training(
                source="canvas",
                external_identity_id=identity.id,
                training_type_id=laser.id,
                created_at=older,
                score=8,
            )
        )
        session.commit()
        needle_id = str(needle.id)
    login(client, "operator")
    first = client.get("/api/admin/trainings").json()
    assert first["total"] == 124 and len(first["items"]) == 100
    assert all(item["user_name"] == "member Fixture" for item in first["items"])
    name = client.get(
        "/api/admin/trainings", params={"search": "quinn needle", "page_size": 1}
    ).json()
    assert name["total"] == 2 and len(name["items"]) == 1
    page2 = client.get(
        "/api/admin/trainings", params={"search": "quinn needle", "page_size": 1, "page": 2}
    ).json()
    assert (
        page2["total"] == 2
        and len(page2["items"]) == 1
        and page2["items"][0]["id"] != name["items"][0]["id"]
    )
    assert (
        client.get("/api/admin/trainings", params={"search": "precision laser"}).json()["total"]
        == 3
    )
    remote = client.get("/api/admin/trainings", params={"search": "remote needle"}).json()
    assert remote["total"] == 1 and remote["items"][0]["user_id"] is None
    combined = client.get(
        "/api/admin/trainings", params={"search": "laser", "user_id": needle_id}
    ).json()
    assert combined["total"] == 1 and combined["items"][0]["user_id"] == needle_id
    assert client.get("/api/admin/trainings", params={"search": "x" * 101}).status_code == 422
