"""Fixture HTTP and isolated PostgreSQL regressions for the simplified Canvas cache."""

import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

from app import jobs, worker
from app.config import Settings
from app.models import (
    CanvasQuiz,
    CanvasRoster,
    ExternalIdentity,
    ScopeRevision,
    Training,
    TrainingType,
    User,
    utcnow,
)
from app.services import canvas
from app.services.canvas import (
    CanvasClient,
    CanvasError,
    TrainingSpec,
    apply_snapshot,
    attach_cached_canvas,
)
from app.worker import BackgroundFailure, run_canvas_sync


@pytest.fixture
def settings():
    return Settings(_env_file=None, canvas_api_token="fixture-token", canvas_course_id="101")


@pytest.fixture
def db(settings, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for isolated PostgreSQL tests")
    schema, job_schema = f"canvas_test_{uuid4().hex}", f"jobs_test_{uuid4().hex}"
    control = create_engine(url)
    with control.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    db = create_engine(url, connect_args={"options": f"-c search_path={schema} -c timezone=UTC"})
    SQLModel.metadata.create_all(db)
    with Session(db) as session:
        session.add_all([ScopeRevision(scope=s) for s in ["public", "staff"]])
        session.commit()
    monkeypatch.setattr(canvas, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "engine", db)
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(jobs, "engine", db)
    monkeypatch.setattr(jobs, "JOBS_SCHEMA", job_schema)
    conninfo = url.replace("postgresql+psycopg://", "postgresql://", 1)
    monkeypatch.setattr(jobs, "app", jobs.create_app(conninfo, schema=job_schema))
    jobs.init_jobs(db)
    try:
        yield db
    finally:
        db.dispose()
        with control.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            c.execute(text(f'DROP SCHEMA "{job_schema}" CASCADE'))
        control.dispose()


def add_training(db, **changes):
    with Session(db) as session:
        session.add(CanvasQuiz(id="202", title="Orientation quiz"))
        session.flush()
        training = TrainingType(
            name="Orientation",
            canvas_assignment_id="202",
            canvas_minimum_score=7,
            **changes,
        )
        session.add(training)
        session.commit()
        return training.id


def specs(db, settings):
    with Session(db) as session:
        return [
            TrainingSpec.from_model(t, settings) for t in session.exec(select(TrainingType)).all()
        ]


def adapter(
    settings,
    *,
    fail=False,
    score=8,
    grade="8",
    submitted_at="2026-10-20T15:30:00Z",
    invalid=False,
    hook=None,
    attempt=1,
    email="Alice@UNCC.edu",
    duplicate_email=False,
):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer fixture-token"
        if hook:
            hook(request)
        if request.url.path.endswith("/users"):
            if request.url.params.get("page") == "2":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 12,
                            "name": "Unregistered visitor",
                            "email": email if duplicate_email else "other@example.org",
                        }
                    ],
                )
            return httpx.Response(
                200,
                json=[{"id": True if invalid else 11, "name": "Alice source", "email": email}],
                headers={
                    "Link": '<https://instructure.charlotte.edu/api/v1/courses/101/users?page=2>; rel="next"'
                },
            )
        if request.url.path.endswith("/submissions"):
            if fail:
                return httpx.Response(503, json={"private": "not retained in errors"})
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 303,
                        "assignment_id": 202,
                        "user_id": 11,
                        "workflow_state": "graded",
                        "score": score,
                        "grade": grade,
                        "submitted_at": submitted_at,
                        "graded_at": "2026-10-21T12:00:00Z",
                        "attempt": attempt,
                    }
                ],
            )
        raise AssertionError(f"Unexpected fixture path {request.url.path}")

    return CanvasClient(settings, httpx.Client(transport=httpx.MockTransport(handler))), requests


def test_paginated_bulk_cache_precedes_registration_and_attach_needs_no_network(db, settings):
    add_training(db)
    client, requests = adapter(settings)
    with Session(db) as session:
        counts = apply_snapshot(
            session, client.fetch_snapshot(specs(db, settings)), settings=settings
        )
        session.commit()
        assert counts["roster"] == 2 and counts["linked"] == 0
        assert len(session.exec(select(Training)).all()) == 1
        user = User(first_name="Alice", email="alice@charlotte.edu")
        session.add(user)
        session.flush()
        count = len(requests)
        assert attach_cached_canvas(session, user)["trainings_added"] == 1
        assert len(requests) == count
        session.commit()
    assert len(requests) == 3
    assert all("/quizzes/" not in str(r.url) for r in requests)


def test_same_submission_attempt_regrade_updates_one_result_and_preserves_manual_award(
    db, settings
):
    training_id = add_training(db)
    with Session(db) as session:
        user = User(email="alice@charlotte.edu")
        session.add(user)
        session.flush()
        session.add(Training(user_id=user.id, training_type_id=training_id, awarded_at=utcnow()))
        session.commit()
    first, _ = adapter(settings, submitted_at=None)
    run_canvas_sync(db, settings, canvas_client=first)
    second, _ = adapter(settings, score=9, grade="9", submitted_at=None)
    run_canvas_sync(db, settings, canvas_client=second)
    with Session(db) as session:
        result = session.exec(select(Training).where(Training.source == "canvas")).one()
        assert result.score == 9 and result.submission_id == "303" and result.attempt == 1
        assert result.completed_at is None
        certs = session.exec(select(Training)).all()
        assert len(certs) == 2 and any(
            c.source == "manual" and c.awarded_at is not None for c in certs
        )
        assert session.exec(select(TrainingType)).one().canvas_sync_started_at is not None


def test_ambiguous_email_is_not_silently_bound(db, settings):
    add_training(db)
    with Session(db) as session:
        session.add(User(email="alice@charlotte.edu"))
        session.commit()
    client, _ = adapter(settings, duplicate_email=True)
    run_canvas_sync(db, settings, canvas_client=client)
    with Session(db) as session:
        assert all(r.identity_conflict for r in session.exec(select(CanvasRoster)).all())
        assert all(i.user_id is None for i in session.exec(select(ExternalIdentity)).all())
        assert all(t.awarded_at is None for t in session.exec(select(Training)).all())


def test_invalid_source_record_rejects_complete_fetch(settings):
    client, _ = adapter(settings, invalid=True)
    with pytest.raises(CanvasError, match="user ID"):
        client.fetch_snapshot([])


def test_pagination_does_not_send_credentials_to_another_origin(settings):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json=[], headers={"Link": '<https://elsewhere.example/api/v1/leak>; rel="next"'}
        )

    client = CanvasClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(CanvasError, match="outside"):
        client.fetch_snapshot([])
    assert len(calls) == 1


def test_threshold_preserves_score_only_policy_and_has_only_assignment_path(db, settings):
    add_training(db)
    for score, grade, passed in [
        (8, None, True),
        (None, None, False),
        (6, "6", False),
        (7, "7", True),
    ]:
        client, requests = adapter(settings, score=score, grade=grade)
        snapshot = client.fetch_snapshot(specs(db, settings))
        assert snapshot.results[0].passed is passed
        assert requests[-1].url.path == "/api/v1/courses/101/assignments/202/submissions"


def test_failed_fetch_keeps_cache_success_checkpoint_and_private_body_out_of_error(db, settings):
    add_training(db)
    client, _ = adapter(settings)
    run_canvas_sync(db, settings, canvas_client=client)
    with Session(db) as session:
        training = session.exec(select(TrainingType)).one()
        before = training.canvas_sync_started_at, training.canvas_synced_at
        fetched = session.exec(select(Training)).one().fetched_at
    broken, _ = adapter(settings, fail=True)
    with pytest.raises(BackgroundFailure, match="HTTP 503"):
        run_canvas_sync(db, settings, canvas_client=broken)
    with Session(db) as session:
        training = session.exec(select(TrainingType)).one()
        assert (training.canvas_sync_started_at, training.canvas_synced_at) == before
        assert "private" not in training.canvas_sync_error
        assert session.exec(select(Training)).one().fetched_at == fetched
        assert len(session.exec(select(CanvasRoster)).all()) == 2


def test_changed_training_config_during_fetch_rejects_snapshot_and_rechecks_cached_awards(
    db, settings
):
    training_id = add_training(db)
    client, _ = adapter(settings)
    run_canvas_sync(db, settings, canvas_client=client)

    def change(request):
        assert db.pool.checkedout() == 0, (
            "Network I/O must not hold an application database connection"
        )
        if request.url.path.endswith("/submissions"):
            with Session(db) as session:
                t = session.get(TrainingType, training_id)
                t.canvas_minimum_score = 99
                session.add(t)
                session.commit()

    client, _ = adapter(settings, hook=change)
    with pytest.raises(BackgroundFailure, match="configuration changed"):
        run_canvas_sync(db, settings, canvas_client=client)
    with Session(db) as session:
        user = User(email="alice@charlotte.edu")
        session.add(user)
        session.flush()
        assert attach_cached_canvas(session, user)["trainings_added"] == 0
        assert session.exec(select(Training)).one().score == 8


def test_quiz_dropdown_filters_assignment_metadata_and_preserves_real_assignment_ids(db, settings):
    def handler(request):
        if request.url.params.get("page"):
            return httpx.Response(
                200, json=[{"id": 77, "name": "LTI quiz", "submission_types": ["external_tool"]}]
            )
        return httpx.Response(
            200,
            json=[
                {
                    "id": 202,
                    "name": "Classic quiz",
                    "submission_types": ["online_quiz"],
                    "points_possible": 8,
                },
                {"id": 45, "name": "Essay", "submission_types": ["online_text_entry"]},
            ],
            headers={
                "Link": '<https://instructure.charlotte.edu/api/v1/courses/101/assignments?page=2>; rel="next"'
            },
        )

    client = CanvasClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    assert worker.refresh_quiz_cache(db, settings, canvas_client=client) == 2
    with Session(db) as session:
        assert {q.id for q in session.exec(select(CanvasQuiz)).all()} == {"202", "77"}


def test_later_submission_page_failure_does_not_apply_partial_roster_or_results(db, settings):
    add_training(db)
    base, _ = adapter(settings)
    original = base.client

    def handler(request):
        if request.url.path.endswith("/submissions"):
            if request.url.params.get("page") == "2":
                return httpx.Response(503, json={})
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 303,
                        "user_id": 11,
                        "assignment_id": 202,
                        "attempt": 1,
                        "workflow_state": "graded",
                        "grade": "8",
                        "score": 8,
                    }
                ],
                headers={
                    "Link": '<https://instructure.charlotte.edu/api/v1/courses/101/assignments/202/submissions?page=2>; rel="next"'
                },
            )
        return original.get(request.url, headers=request.headers)

    client = CanvasClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(BackgroundFailure, match="HTTP 503"):
        run_canvas_sync(db, settings, canvas_client=client)
    with Session(db) as session:
        assert session.exec(select(CanvasRoster)).all() == []
        assert session.exec(select(Training)).all() == []
        assert session.exec(select(TrainingType)).one().canvas_sync_started_at is None


def test_existing_identity_email_change_reports_conflict_without_rebinding(db, settings):
    add_training(db)
    with Session(db) as session:
        user = User(email="alice@charlotte.edu")
        session.add(user)
        session.commit()
        id = user.id
    first, _ = adapter(settings)
    run_canvas_sync(db, settings, canvas_client=first)
    changed, _ = adapter(settings, email="different@example.org")
    run_canvas_sync(db, settings, canvas_client=changed)
    with Session(db) as session:
        identity = session.exec(
            select(ExternalIdentity).where(ExternalIdentity.value == "11")
        ).one()
        roster = session.exec(
            select(CanvasRoster).where(CanvasRoster.external_identity_id == identity.id)
        ).one()
        assert identity.user_id == id and roster.identity_conflict


def test_admin_canvas_routes_return_real_queued_contract_and_require_permission(db, settings):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.database import get_session
    from app.models import Permission
    from app.routes.canvas import router
    from app.security import current_actor

    permissions = {Permission.CANVAS_READ, Permission.CANVAS_WRITE}
    app = FastAPI()
    app.include_router(router)

    def session_dependency():
        with Session(db) as session:
            yield session

    actor = SimpleNamespace(user=SimpleNamespace(id=None), can=lambda p: p in permissions)
    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[current_actor] = lambda: actor
    training_id = add_training(db)
    with TestClient(app) as client:
        response = client.post(
            "/api/admin/canvas/sync", json={"training_type_id": str(training_id)}
        )
        assert response.status_code == 202 and response.json()["status"] == "queued"
        status = client.get("/api/admin/canvas/status").json()
        assert status["trainings"][0]["training_type_id"] == str(training_id)
        assert status["trainings"][0]["last_success_at"] is None
        assert status["trainings"][0]["status"] == "running"
        assert client.get("/api/admin/canvas/quizzes").json()["items"][0]["id"] == "202"
        permissions.clear()
        assert client.get("/api/admin/canvas/status").status_code == 403
        assert client.post("/api/admin/canvas/sync").status_code == 403


def test_successful_missing_source_result_stops_new_awards_without_revoking_history(db, settings):
    from dataclasses import replace

    add_training(db)
    with Session(db) as session:
        session.add(User(email="alice@charlotte.edu"))
        session.commit()
    client, _ = adapter(settings)
    snapshot = client.fetch_snapshot(specs(db, settings))
    snapshot = replace(
        snapshot,
        results=snapshot.results
        + (replace(snapshot.results[0], canvas_id="12", submission_id="304"),),
    )
    with Session(db) as session:
        apply_snapshot(session, snapshot, settings=settings)
        session.commit()
        assert (
            len(session.exec(select(Training).where(Training.awarded_at.is_not(None))).all()) == 1
        )
        apply_snapshot(session, replace(snapshot, results=()), settings=settings)
        session.commit()
        user = User(email="other@example.org")
        session.add(user)
        session.flush()
        assert attach_cached_canvas(session, user)["trainings_added"] == 0
        assert all(
            r.workflow_status == "not_returned" for r in session.exec(select(Training)).all()
        )
        cert = session.exec(select(Training).where(Training.awarded_at.is_not(None))).one()
        assert cert.source == "canvas" and cert.revoked_at is None


def test_unthresholded_training_preserves_original_non_null_grade_check(db, settings):
    training_id = add_training(db)
    with Session(db) as session:
        training = session.get(TrainingType, training_id)
        training.canvas_minimum_score = None
        session.add(training)
        session.commit()
    for grade, expected in [(None, False), ("", True), ("8", True)]:
        client, _ = adapter(settings, grade=grade)
        assert client.fetch_snapshot(specs(db, settings)).results[0].passed is expected


def test_cache_application_batches_selects_instead_of_querying_each_student(db, settings):
    from dataclasses import replace

    from sqlalchemy import event

    from app.services.canvas import RosterRecord

    add_training(db)
    client, _ = adapter(settings)
    snapshot = client.fetch_snapshot(specs(db, settings))
    source = snapshot.results[0]
    roster = tuple(
        RosterRecord(str(1000 + i), f"visitor{i}@example.org", "Fixture visitor") for i in range(40)
    )
    results = tuple(
        replace(source, canvas_id=r.canvas_id, submission_id=str(2000 + i))
        for i, r in enumerate(roster)
    )
    snapshot = replace(snapshot, roster=roster, results=results)
    selects = []

    def count_select(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(db, "before_cursor_execute", count_select)
    try:
        with Session(db) as session:
            counts = apply_snapshot(session, snapshot, settings=settings)
            session.commit()
    finally:
        event.remove(db, "before_cursor_execute", count_select)
    assert counts["roster"] == counts["results"] == 40
    assert len(selects) <= 12, f"Expected batch lookups, observed {len(selects)} SELECT statements"


def test_earned_training_survives_nonpassing_regrade_and_revocation_is_not_resurrected(
    db, settings
):
    from app.models import utcnow
    from app.services.projections import badges_for_users

    add_training(db)
    with Session(db) as session:
        user = User(email="alice@charlotte.edu")
        session.add(user)
        session.commit()
        id = user.id
    client, _ = adapter(settings)
    run_canvas_sync(db, settings, canvas_client=client)
    with Session(db) as session:
        training = session.exec(select(Training)).one()
        first_award = training.awarded_at
        assert first_award and training.user_id is None and training.external_identity_id
        assert len(badges_for_users(session, [id])[id]) == 1
    client, _ = adapter(settings, score=0, grade="0", attempt=2)
    run_canvas_sync(db, settings, canvas_client=client)
    with Session(db) as session:
        training = session.exec(select(Training)).one()
        assert not training.passed and training.attempt == 2 and training.awarded_at == first_award
        assert len(badges_for_users(session, [id])[id]) == 1
        training.revoked_at = utcnow()
        revoked = training.revoked_at
        session.add(training)
        session.commit()
    client, _ = adapter(settings, score=9, grade="9", attempt=3)
    run_canvas_sync(db, settings, canvas_client=client)
    with Session(db) as session:
        training = session.exec(select(Training)).one()
        assert (
            training.passed
            and training.revoked_at == revoked
            and training.awarded_at == first_award
        )
        assert not badges_for_users(session, [id]).get(id)


def test_roster_requests_all_documented_enrollment_states(db, settings):
    add_training(db)
    client, requests = adapter(settings)
    client.fetch_snapshot(specs(db, settings))
    roster_request = next(request for request in requests if request.url.path.endswith("/users"))
    assert set(roster_request.url.params.get_list("enrollment_state[]")) == {
        "active",
        "invited",
        "rejected",
        "completed",
        "inactive",
    }


def test_unresolvable_submission_is_counted_not_granted_and_does_not_block_valid_people(
    db, settings
):
    add_training(db)
    with Session(db) as session:
        user = User(email="alice@charlotte.edu")
        session.add(user)
        session.commit()
        id = user.id
    original, _ = adapter(settings)

    def handler(request):
        response = original.client.get(request.url, headers=request.headers)
        if request.url.path.endswith("/submissions"):
            records = response.json()
            records.append({**records[0], "id": 999, "user_id": 404})
            return httpx.Response(200, json=records)
        return response

    client = CanvasClient(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    counts = run_canvas_sync(db, settings, canvas_client=client)
    assert (
        counts["skipped_results"] == 1 and counts["results"] == 1 and counts["trainings_added"] == 1
    )
    with Session(db) as session:
        assert len(session.exec(select(Training)).all()) == 1
        assert {identity.value for identity in session.exec(select(ExternalIdentity)).all()} == {
            "11",
            "12",
        }
        training = session.exec(select(Training)).one()
        identity = session.get(ExternalIdentity, training.external_identity_id)
        assert identity.user_id == id and training.awarded_at is not None
        assert session.exec(select(TrainingType)).one().canvas_synced_at is not None


def test_canvas_people_pages_search_and_filters_cover_full_cache_with_two_queries(db, settings):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import event

    from app.database import get_session
    from app.models import Permission
    from app.routes.canvas import router
    from app.security import current_actor

    with Session(db) as session:
        bound = User(first_name="Bound", email="bound@charlotte.edu")
        session.add(bound)
        session.flush()
        for index in range(205):
            identity = ExternalIdentity(
                provider="canvas_id",
                issuer=canvas.canvas_issuer(settings),
                value=str(10000 + index),
                user_id=bound.id if index == 3 else None,
            )
            session.add(identity)
            session.flush()
            session.add(
                CanvasRoster(
                    external_identity_id=identity.id,
                    display_name=f"Person {index:03d}",
                    email=f"person{index:03d}@charlotte.edu",
                    identity_conflict="Review required" if index == 204 else None,
                )
            )
        # Other identity providers/issuers must not leak into this Canvas cache.
        other = ExternalIdentity(provider="canvas_id", issuer="https://other.invalid", value="1")
        session.add(other)
        session.flush()
        session.add(
            CanvasRoster(external_identity_id=other.id, display_name="Other course provider")
        )
        session.commit()
    app = FastAPI()
    app.include_router(router)
    permissions = {Permission.CANVAS_READ}
    app.dependency_overrides[current_actor] = lambda: SimpleNamespace(
        can=lambda permission: permission in permissions
    )

    def sessions():
        with Session(db) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        first = client.get("/api/admin/canvas/people").json()
        assert first["total"] == 204 and first["page"] == 1 and first["page_size"] == 100
        assert len(first["items"]) == 100
        third = client.get("/api/admin/canvas/people?page=3").json()
        assert len(third["items"]) == 4 and third["items"][-1]["display_name"] == "Person 204"
        found = client.get("/api/admin/canvas/people", params={"search": "PERSON204"}).json()
        assert found["total"] == 1 and found["items"][0]["display_name"] == "Person 204"
        assert (
            client.get("/api/admin/canvas/people", params={"search": "Person 204"}).json()["total"]
            == 1
        )
        conflicts = client.get("/api/admin/canvas/people?binding=conflicts").json()
        assert conflicts["total"] == 1 and conflicts["items"][0]["conflict"] == "Review required"
        statements = []

        def counted(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db, "before_cursor_execute", counted)
        try:
            all_people = client.get("/api/admin/canvas/people?binding=all&page_size=1000").json()
        finally:
            event.remove(db, "before_cursor_execute", counted)
        assert all_people["total"] == len(all_people["items"]) == 205
        assert len(statements) == 2
        assert any(person["user_id"] for person in all_people["items"])
        assert set(all_people["items"][0]) == {
            "id",
            "display_name",
            "email",
            "canvas_id",
            "user_id",
            "conflict",
        }
        assert client.get("/api/admin/canvas/people?page_size=1001").status_code == 422
        assert client.get("/api/admin/canvas/people?binding=invalid").status_code == 422
        assert client.post("/api/admin/canvas/sync").status_code == 403
        permissions.clear()
        assert client.get("/api/admin/canvas/people").status_code == 403
