import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, create_engine, select

from app import database
from app.config import get_settings
from app.models import (
    KeyholderShift,
    Role,
    ScopeRevision,
    SpaceLevel,
    Training,
    TrainingType,
    User,
    Visit,
)
from app.schemas import KeyholderInput
from app.security import hash_password, token_hash
from app.services.identity import add_student_identifier, canonical_email
from app.services.kiosk import execute_command
from app.services.metrics import calculate_metrics

pytestmark = pytest.mark.postgres
PASSWORD = "fixture-password-only-2026"


@pytest.fixture
def candidate(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL database")
    schema = "core_test_" + uuid4().hex
    jobs_schema = "core_jobs_" + uuid4().hex
    dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')
    db = create_engine(url, connect_args={"options": f"-csearch_path={schema} -ctimezone=UTC"})
    monkeypatch.setattr(database, "engine", db)
    from app import events, jobs, main
    from app.routes import live

    monkeypatch.setattr(events, "CHANNEL", "core_events_" + uuid4().hex)
    monkeypatch.setattr(jobs, "engine", db)
    monkeypatch.setattr(jobs, "JOBS_SCHEMA", jobs_schema)
    monkeypatch.setattr(jobs, "app", jobs.create_app(dsn, schema=jobs_schema))
    jobs.init_jobs(db)

    monkeypatch.setattr(main, "engine", db)
    monkeypatch.setattr(live, "engine", db)
    database.init_db()
    with Session(db) as session:
        users = {}
        for name, role, access, priority in [
            ("holder", Role.SUPERADMIN, SpaceLevel.STAFF, 2),
            ("operator", Role.OPERATOR, SpaceLevel.VOLUNTEER, 0),
            ("viewer", Role.ADMIN, SpaceLevel.MEMBER, -1),
            ("member", None, SpaceLevel.MEMBER, -1),
            ("higher", None, SpaceLevel.KEYHOLDER, 3),
        ]:
            user = User(
                first_name=name,
                last_name="Fixture",
                email=f"{name}@charlotte.edu",
                role=role,
                space_level=access,
                keyholder_priority=priority,
            )
            session.add(user)
            session.flush()
            add_student_identifier(session, user, name + "-id")
            if role:
                user.password_hash = hash_password(PASSWORD)
                session.add(user)
            users[name] = user.id
        session.add(KeyholderShift(user_id=users["holder"]))
        session.add(Visit(user_id=users["holder"]))
        training = TrainingType(name="Laser Cutter", icon_key="laser-cutter")
        session.add(training)
        session.flush()
        training_id = training.id
        session.commit()
    with TestClient(main.create_app(), base_url=get_settings().app_origin) as client:
        client.headers["Origin"] = get_settings().app_origin
        yield {
            "client": client,
            "engine": db,
            "users": users,
            "jobs_schema": jobs_schema,
            "training_id": training_id,
        }
    db.dispose()
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
        connection.execute(f'DROP SCHEMA "{jobs_schema}" CASCADE')


def login(client, name):
    result = client.post("/api/auth/login", json={"identifier": name + "-id", "password": PASSWORD})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return result.json()


def tap(client, identifier):
    return client.post("/api/kiosk/tap", json={"identifier": identifier})


def test_public_projection_and_local_only_tap(candidate, monkeypatch):
    client = candidate["client"]
    import httpx

    original_get = httpx.Client.get
    monkeypatch.setattr(
        "httpx.Client.get",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("Canvas must not be called during tap")
        ),
    )
    first = tap(client, "member-id")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "signed_in"
    monkeypatch.setattr("httpx.Client.get", original_get)
    data = client.get("/api/public/occupancy").json()
    assert len(data["occupants"]) == 2
    assert all(
        set(person) == {"id", "display_name", "avatar_url", "badges"}
        for person in data["occupants"]
    )
    serialized = str(data)
    assert "example.invalid" not in serialized and "member-id" not in serialized
    assert "password_hash" not in serialized and "canvas_id" not in serialized
    with Session(candidate["engine"]) as session:
        visits = session.exec(
            select(Visit).where(Visit.user_id == candidate["users"]["member"])
        ).all()
        assert len(visits) == 1 and visits[0].exit_time is None
    # A subsequent intentional tap still toggles attendance; there are no receipts.
    assert tap(client, "member-id").json()["status"] == "signed_out"
    with Session(candidate["engine"]) as session:
        visits = session.exec(
            select(Visit).where(Visit.user_id == candidate["users"]["member"])
        ).all()
        assert len(visits) == 1 and visits[0].exit_time is not None


def test_concurrent_takeover_confirms_one_expected_shift(candidate):
    from fastapi import HTTPException

    with Session(candidate["engine"]) as session:
        expected = (
            session.exec(select(KeyholderShift).where(KeyholderShift.ended_at.is_(None))).one().id
        )

    def invoke():
        with Session(candidate["engine"]) as session:
            try:
                execute_command(
                    session,
                    "keyholder",
                    KeyholderInput(
                        identifier="higher-id", action="override", expected_shift_id=expected
                    ),
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: invoke(), range(4)))
    assert sorted(results) == [200, 409, 409, 409]
    with Session(candidate["engine"]) as session:
        active = session.exec(select(KeyholderShift).where(KeyholderShift.ended_at.is_(None))).one()
        assert active.user_id == candidate["users"]["higher"]
        visits = session.exec(
            select(Visit).where(Visit.user_id == candidate["users"]["higher"])
        ).all()
        assert len(visits) == 1 and visits[0].exit_time is None


def test_unknown_scans_do_not_create_abandoned_profiles_and_registration_uses_explicit_id(
    candidate,
):
    from app.services.identity import find_user

    client = candidate["client"]
    for identifier in ["900001111", "900002222"]:
        response = tap(client, identifier)
        assert response.status_code == 200 and response.json()["status"] == "registration_required"
        assert response.json()["identifier"] == identifier
    with Session(candidate["engine"]) as session:
        assert find_user(session, "900001111") is None and find_user(session, "900002222") is None
        assert len(session.exec(select(Visit)).all()) == 1
    payload = {
        "identifier": "900002222",
        "first_name": "New",
        "last_name": "Visitor",
        "email": "NEW@UNCC.edu",
    }
    registered = client.post("/api/kiosk/register", json=payload)
    assert registered.status_code == 200 and registered.json()["status"] == "signed_in"
    with Session(candidate["engine"]) as session:
        assert find_user(session, "900001111") is None
        user = find_user(session, "900002222")
        assert user.email == "new@charlotte.edu" and user.space_level == SpaceLevel.MEMBER
        assert user.password_hash is None and user.keyholder_priority == -1
        assert user.role is None
        assert len(session.exec(select(Visit).where(Visit.user_id == user.id)).all()) == 1
    # Stale repeated form submission cannot rebind identity or toggle the visit.
    assert (
        client.post("/api/kiosk/register", json=payload | {"first_name": "Different"}).status_code
        == 409
    )
    assert len(client.get("/api/public/occupancy").json()["occupants"]) == 2


def test_keyholder_handoff_close_and_strict_priority(candidate):
    client = candidate["client"]
    result = tap(client, "higher-id").json()
    assert result["status"] == "keyholder_action_required"
    assert set(result["actions"]) == {"override", "continue"}
    continued = client.post(
        "/api/kiosk/keyholder",
        json={
            "identifier": "higher-id",
            "action": "continue",
            "expected_shift_id": result["expected_shift_id"],
        },
    )
    assert continued.status_code == 200, continued.text
    assert continued.json()["status"] == "signed_in"
    prompt = tap(client, "holder-id").json()
    handoff = client.post(
        "/api/kiosk/keyholder",
        json={
            "identifier": "holder-id",
            "target_identifier": "operator-id",
            "action": "handoff",
            "expected_shift_id": prompt["expected_shift_id"],
            "sign_out_current_keyholder": True,
        },
    )
    assert handoff.status_code == 200, handoff.text
    assert client.get("/api/public/occupancy").json()["lab"]["keyholder"]["id"] == str(
        candidate["users"]["operator"]
    )
    prompt = tap(client, "operator-id").json()
    closed = client.post(
        "/api/kiosk/keyholder",
        json={
            "identifier": "operator-id",
            "action": "close",
            "expected_shift_id": prompt["expected_shift_id"],
        },
    )
    assert closed.status_code == 200, closed.text
    assert client.get("/api/public/occupancy").json()["lab"]["is_open"] is False
    with Session(candidate["engine"]) as session:
        visit = session.exec(
            select(Visit).where(Visit.user_id == candidate["users"]["higher"])
        ).one()
        assert visit.forgot_to_sign_out is True


def test_permissions_csrf_and_no_role_escalation(candidate):
    client = candidate["client"]
    assert client.get("/api/admin/users").status_code == 401
    login(client, "viewer")
    assert client.get("/api/admin/metrics").status_code == 200
    assert client.get("/api/admin/database/tables").status_code == 503
    assert (
        client.put(
            f"/api/admin/users/{candidate['users']['viewer']}/role", json={"role": "superadmin"}
        ).status_code
        == 403
    )
    login(client, "operator")
    user_id = candidate["users"]["member"]
    assert client.patch(f"/api/admin/users/{user_id}", json={"space_level": 3}).status_code == 403
    assert (
        client.patch(f"/api/admin/users/{user_id}", json={"role": "superadmin"}).status_code == 422
    )
    client.headers.pop("X-CSRF-Token")
    assert (
        client.patch(f"/api/admin/users/{user_id}", json={"first_name": "Other"}).status_code == 403
    )


def test_operator_assigns_simple_training_and_cannot_edit_definition(candidate):
    client = candidate["client"]
    login(client, "operator")
    data = {
        "user_id": str(candidate["users"]["member"]),
        "training_type_id": str(candidate["training_id"]),
    }
    assert client.post("/api/admin/trainings", json=data).status_code == 201
    assert (
        client.patch(
            f"/api/admin/training-types/{candidate['training_id']}", json={"name": "Changed"}
        ).status_code
        == 403
    )
    assert client.post("/api/admin/trainings", json={**data, "level": "trainer"}).status_code == 422
    tap(client, "member-id")
    badge = next(
        u
        for u in client.get("/api/public/occupancy").json()["occupants"]
        if u["id"] == str(candidate["users"]["member"])
    )["badges"][0]
    assert badge == {
        "training_type_id": str(candidate["training_id"]),
        "name": "Laser Cutter",
        "icon_key": "laser-cutter",
    }


def test_metrics_clip_dst_and_count_forgotten_presence(candidate):
    with Session(candidate["engine"]) as session:
        session.execute(text("DELETE FROM keyholder_shifts"))
        session.execute(text("DELETE FROM visits"))
        session.add(
            Visit(
                user_id=candidate["users"]["member"],
                enter_time=datetime(2026, 11, 1, 3, 0, tzinfo=UTC),
                exit_time=datetime(2026, 11, 2, 6, 0, tzinfo=UTC),
            )
        )
        session.add(
            Visit(
                user_id=candidate["users"]["viewer"],
                enter_time=datetime(2026, 11, 1, 15, 0, tzinfo=UTC),
                exit_time=datetime(2026, 11, 1, 17, 0, tzinfo=UTC),
                forgot_to_sign_out=True,
            )
        )
        session.commit()
        result = calculate_metrics(
            session, date(2026, 11, 1), date(2026, 11, 2), "America/New_York"
        )
        assert result["summary"]["total_hours"] == 25
        assert result["summary"]["unique_visitors"] == 2
        assert result["summary"]["visits"] == 2
        assert result["summary"]["finalized_visits"] == 1
        assert result["daily"][0]["total_hours"] == 25
        assert result["summary"]["excluded_visits"] == 1


def test_timestamp_trigger_and_keyholder_deactivation_guard(candidate):
    client = candidate["client"]
    login(client, "holder")
    assert (
        client.patch(
            f"/api/admin/users/{candidate['users']['holder']}", json={"active": False}
        ).status_code
        == 409
    )
    with Session(candidate["engine"]) as session:
        user = session.get(User, candidate["users"]["member"])
        before = user.updated_at
        session.execute(text("UPDATE users SET first_name='Changed' WHERE id=:id"), {"id": user.id})
        session.commit()
        session.refresh(user)
        assert user.updated_at > before
    assert canonical_email("Example@UNCC.edu") == "example@charlotte.edu"


def test_live_occupancy_resnapshot_and_private_role_revocation(candidate):

    from app.events import publish

    client = candidate["client"]
    with client.websocket_connect(
        "/ws/public", headers={"Origin": get_settings().app_origin}
    ) as socket:
        first = socket.receive_json()
        assert first["type"] == "snapshot"
        assert len(first["data"]["occupants"]) == 1
        assert tap(client, "member-id").status_code == 200
        changed = socket.receive_json()
        assert changed["type"] == "snapshot"
        assert len(changed["data"]["occupants"]) == 2
        assert changed["revision"] > first["revision"]
    with client.websocket_connect(
        "/ws/public", headers={"Origin": get_settings().app_origin}
    ) as socket:
        assert len(socket.receive_json()["data"]["occupants"]) == 2
    login(client, "viewer")
    with client.websocket_connect(
        get_settings().app_origin.replace("http", "ws", 1) + "/ws/admin",
        headers={"Origin": get_settings().app_origin},
    ) as socket:
        assert socket.receive_json()["type"] == "invalidate"
        with Session(candidate["engine"]) as session:
            user = session.get(User, candidate["users"]["viewer"])
            user.role = None
            session.add(user)
            publish(session, "permissions")
            session.commit()
        # A user with no staff capability is disconnected before another private update.
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


@pytest.mark.asyncio
async def test_simultaneous_notification_never_discards_inbound_command():
    import asyncio
    from types import SimpleNamespace

    from app.routes.live import cleanup_events, next_event

    incoming = asyncio.Queue()
    changes = asyncio.Queue()

    class Socket:
        state = SimpleNamespace()

        async def receive_json(self):
            return await incoming.get()

    socket = Socket()
    command = {"type": "command", "command": "tap", "id": "not-lost"}
    await incoming.put(command)
    await changes.put({"topics": ["occupancy"]})
    first = await next_event(socket, changes)
    second = await next_event(socket, changes)
    assert {first[0], second[0]} == {"message", "change"}
    assert next(value for kind, value in [first, second] if kind == "message") == command
    # Notification arrives while the next receive remains pending, then ack arrives.
    await changes.put({"topics": ["printing"]})
    assert (await next_event(socket, changes))[0] == "change"
    ack = {"type": "ack", "job_id": "not-lost-either"}
    await incoming.put(ack)
    assert await next_event(socket, changes) == ("message", ack)
    await cleanup_events(socket)


def test_raw_sql_timestamp_defaults_and_revision_counter_timestamps(candidate):
    with Session(candidate["engine"]) as session:
        user_id = uuid4()
        inserted = session.execute(
            text("""INSERT INTO users
            (id,first_name,last_name,space_level,keyholder_priority,active)
            VALUES (:id,'Raw','Insert',0,-1,true)
            RETURNING created_at,updated_at"""),
            {"id": user_id},
        ).one()
        assert inserted.created_at is not None
        assert inserted.updated_at is not None
        assert inserted.created_at.tzinfo is not None
        session.commit()
        updated = session.execute(
            text(
                "UPDATE users SET first_name='Updated' WHERE id=:id RETURNING created_at,updated_at"
            ),
            {"id": user_id},
        ).one()
        assert updated.created_at == inserted.created_at
        assert updated.updated_at > inserted.updated_at
        counter = session.execute(
            text(
                "INSERT INTO scope_revisions (scope,revision) VALUES ('timestamp-fixture',0) RETURNING created_at,updated_at"
            )
        ).one()
        session.commit()
        touched = session.execute(
            text(
                "UPDATE scope_revisions SET revision=revision+1 WHERE scope='timestamp-fixture' RETURNING created_at,updated_at"
            )
        ).one()
        assert touched.created_at == counter.created_at
        assert touched.updated_at > counter.updated_at
        assert session.get(ScopeRevision, "public").created_at is not None
        session.commit()


def test_admin_identifier_validation_matches_kiosk(candidate):
    client = candidate["client"]
    login(client, "holder")
    data = {
        "first_name": "Guest",
        "last_name": "Fixture",
        "email": "guest@charlotte.edu",
        "identifier": "not scannable!",
    }
    assert client.post("/api/admin/users", json=data).status_code == 422
    data["identifier"] = "123"
    assert client.post("/api/admin/users", json=data).status_code == 422
    data["identifier"] = "guest-lab-42"
    valid = client.post("/api/admin/users", json=data)
    assert valid.status_code == 201, valid.text
    assert tap(client, "guest-lab-42").json()["status"] == "signed_in"


def test_typed_kiosk_and_staff_responses_match_the_running_contract(candidate):
    client = candidate["client"]
    state = client.get("/api/kiosk/state")
    assert state.status_code == 200, state.text
    payload = state.json()
    assert "device" not in payload
    assert set(payload["stats"]) == {"present", "unique_visitors_today", "weekly_hours"}
    assert "recent_activity" in payload
    assert tap(client, "member-id").status_code == 200
    login(client, "holder")
    for route in [
        "/api/me/profile",
        "/api/admin/users",
        "/api/admin/visits",
        "/api/admin/printing/status",
    ]:
        result = client.get(route)
        assert result.status_code == 200, (route, result.text)


def test_training_definition_selects_one_cached_canvas_quiz(candidate):
    from app.models import CanvasQuiz

    client = candidate["client"]
    login(client, "holder")
    with Session(candidate["engine"]) as session:
        session.add(CanvasQuiz(id="42", title="Laser quiz", points_possible=10))
        session.commit()
    quizzes = client.get("/api/admin/canvas/quizzes")
    assert quizzes.status_code == 200
    assert quizzes.json()["items"] == [{"id": "42", "title": "Laser quiz", "points_possible": 10}]
    response = client.patch(
        f"/api/admin/training-types/{candidate['training_id']}",
        json={"canvas_assignment_id": "42", "canvas_minimum_score": 7},
    )
    assert response.status_code == 200, response.text
    assert response.json()["canvas_assignment_id"] == "42"
    assert response.json()["canvas_minimum_score"] == 7
    assert "canvas_level" not in response.json()
    assert (
        client.patch(
            f"/api/admin/training-types/{candidate['training_id']}",
            json={"canvas_assignment_id": "missing"},
        ).status_code
        == 404
    )


@pytest.mark.parametrize("path", ["/ws/public", "/ws/admin", "/ws/kiosk"])
def test_live_disconnect_cleans_pending_receive_tasks(candidate, monkeypatch, path):
    from app.routes import live

    client = candidate["client"]
    if path == "/ws/admin":
        login(client, "holder")
    original = live.cleanup_events
    observed = []

    async def checked_cleanup(socket):
        pending = list(getattr(socket.state, "pending_events", {}).values())
        await original(socket)
        observed.append((socket.url.path, all(task.done() for task in pending)))

    monkeypatch.setattr(live, "cleanup_events", checked_cleanup)
    ws_url = get_settings().app_origin.replace("http", "ws", 1) + path
    with client.websocket_connect(ws_url, headers={"Origin": get_settings().app_origin}) as socket:
        socket.receive_json()
        socket.send_json({"type": "ping"})
        while socket.receive_json().get("type") != "pong":
            pass
    assert observed == [(path, True)]


def test_account_recovery_email_is_owner_or_superadmin_only(candidate):
    from datetime import timedelta

    from app import jobs
    from app.models import EmailJob, PasswordReset, utcnow

    db = candidate["engine"]
    client = candidate["client"]
    pending = {}
    with Session(db) as session:
        holder = session.get(User, candidate["users"]["holder"])
        holder.email = "holder@charlotte.edu"
        session.add(holder)
        session.get(User, candidate["users"]["viewer"]).role = Role.ADMIN
        for name in ["holder", "operator"]:
            token = "recovery-fixture-" + uuid4().hex
            reset = PasswordReset(
                user_id=candidate["users"][name],
                token_hash=token_hash(token),
                expires_at=utcnow() + timedelta(minutes=30),
            )
            mail = EmailJob(
                user_id=candidate["users"][name],
                kind="password_reset",
                payload={"reset_url": get_settings().app_origin + "/reset-password?token=" + token},
            )
            session.add(reset)
            session.add(mail)
            session.flush()
            scheduled_id = jobs._defer(
                session,
                jobs.EMAIL_TASK,
                {"email_job_id": str(mail.id)},
                lock=f"email:{mail.id}",
                queueing_lock=f"email:{mail.id}",
            )
            pending[name] = (reset.id, mail.id, scheduled_id, token)
        session.commit()

    target = candidate["users"]["holder"]
    login(client, "operator")
    assert (
        client.patch(
            f"/api/admin/users/{target}", json={"email": "attacker@charlotte.edu"}
        ).status_code
        == 403
    )
    # Ordinary administrators have users.write but cannot take over another account.
    login(client, "viewer")
    assert (
        client.patch(
            f"/api/admin/users/{target}", json={"email": "attacker@charlotte.edu"}
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/api/admin/users/{target}", json={"first_name": "Still Holder"}).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/admin/users/{target}", json={"email": "HOLDER@charlotte.edu"}
        ).status_code
        == 200
    )
    with Session(db) as session:
        assert session.get(User, target).email == "holder@charlotte.edu"
        assert session.get(PasswordReset, pending["holder"][0]).used_at is None

    # A normal visitor without login credentials can still have contact information corrected.
    login(client, "operator")
    member = candidate["users"]["member"]
    assert (
        client.patch(
            f"/api/admin/users/{member}", json={"email": "visitor-corrected@charlotte.edu"}
        ).status_code
        == 200
    )

    # Authenticated owner can change their recovery email through self-profile.
    login(client, "holder")
    assert (
        client.patch("/api/me/profile", json={"email": "holder-new@charlotte.edu"}).status_code
        == 200
    )
    reset_id, mail_id, scheduled_id, token = pending["holder"]
    with Session(db) as session:
        assert session.get(PasswordReset, reset_id).used_at is not None
        assert session.get(EmailJob, mail_id).state == "cancelled"
        assert session.get(EmailJob, mail_id).payload == {}
        assert (
            session.execute(
                text(
                    f"SELECT status::text FROM {candidate['jobs_schema']}.procrastinate_jobs WHERE id=:id"
                ),
                {"id": scheduled_id},
            ).scalar_one()
            == "cancelled"
        )
    assert (
        client.post(
            "/api/auth/password-reset/complete",
            json={"token": token, "password": "replacement-fixture-password"},
        ).status_code
        == 400
    )

    # Superadmin may perform the same change for another credentialed account.
    operator = candidate["users"]["operator"]
    assert (
        client.patch(
            f"/api/admin/users/{operator}", json={"email": "operator-new@charlotte.edu"}
        ).status_code
        == 200
    )
    with Session(db) as session:
        assert session.get(User, operator).email == "operator-new@charlotte.edu"
        assert session.get(PasswordReset, pending["operator"][0]).used_at is not None
        assert session.get(EmailJob, pending["operator"][1]).payload == {}
    # Owner path through general user administration is also allowed where authorized.
    login(client, "operator")
    assert (
        client.patch(
            f"/api/admin/users/{operator}", json={"email": "operator-own@charlotte.edu"}
        ).status_code
        == 200
    )


def test_health_requires_initialized_schema_and_revision_rows(candidate, monkeypatch):
    from app import main

    client = candidate["client"]
    assert client.get("/api/health").status_code == 200
    schema = "uninitialized_" + uuid4().hex
    db = candidate["engine"]
    with db.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    empty_db = create_engine(db.url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        monkeypatch.setattr(main, "engine", empty_db)
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json()["status"] == "uninitialized"
    finally:
        monkeypatch.setattr(main, "engine", db)
        empty_db.dispose()
        with db.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    with Session(db) as session:
        session.delete(session.get(ScopeRevision, "public"))
        session.commit()
    assert client.get("/api/health").status_code == 503


def test_manual_canvas_sync_reports_active_job_without_queueing_another(candidate, monkeypatch):
    from app import jobs
    from app.config import Settings
    from app.routes import canvas

    settings = Settings(_env_file=None, canvas_api_token="fixture-only", canvas_course_id="101")
    monkeypatch.setattr(canvas, "get_settings", lambda: settings)
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    client = candidate["client"]
    login(client, "holder")
    first = client.post("/api/admin/canvas/sync")
    assert first.status_code == 202 and first.json()["status"] == "queued", first.text
    with Session(candidate["engine"]) as session:
        job_id = session.execute(
            text(
                f"SELECT id FROM {candidate['jobs_schema']}.procrastinate_jobs WHERE task_name='canvas.sync'"
            )
        ).scalar_one()
        with jobs._external_connection(session):
            session.execute(
                text(
                    f"UPDATE {candidate['jobs_schema']}.procrastinate_jobs SET status='doing' WHERE id=:id"
                ),
                {"id": job_id},
            )
        session.commit()
    second = client.post("/api/admin/canvas/sync")
    assert second.status_code == 409
    assert "already running" in second.json()["detail"]
    with Session(candidate["engine"]) as session:
        assert (
            session.execute(
                text(f"SELECT COUNT(*) FROM {candidate['jobs_schema']}.procrastinate_jobs")
            ).scalar_one()
            == 1
        )


@pytest.mark.parametrize(
    "changes",
    [{"canvas_minimum_score": 9}, {"canvas_assignment_id": "303"}],
)
def test_canvas_training_edits_invalidate_cached_award_evidence(candidate, changes):
    from app.models import CanvasQuiz, CanvasRoster, ExternalIdentity, utcnow
    from app.services.canvas import TrainingSpec, attach_cached_canvas

    client = candidate["client"]
    login(client, "holder")
    with Session(candidate["engine"]) as session:
        session.add_all(
            [
                CanvasQuiz(id="202", title="Original quiz"),
                CanvasQuiz(id="303", title="Replacement quiz"),
            ]
        )
        session.commit()
    initial = {
        "canvas_assignment_id": "202",
        "canvas_minimum_score": 7,
    }
    created = client.patch(f"/api/admin/training-types/{candidate['training_id']}", json=initial)
    assert created.status_code == 200, created.text
    with Session(candidate["engine"]) as session:
        identity = ExternalIdentity(
            provider="canvas_id", issuer="https://instructure.charlotte.edu", value="cached-person"
        )
        session.add(identity)
        session.flush()
        roster = CanvasRoster(external_identity_id=identity.id, email="cached@charlotte.edu")
        session.add(roster)
        session.flush()
        training = session.get(TrainingType, candidate["training_id"])
        cached = Training(
            source="canvas",
            external_identity_id=identity.id,
            training_type_id=training.id,
            config_fingerprint=TrainingSpec.from_model(training).fingerprint,
            score=8,
            passed=True,
            workflow_status="graded",
            fetched_at=utcnow(),
        )
        session.add(cached)
        cached_id = cached.id
        session.commit()
    response = client.patch(f"/api/admin/training-types/{candidate['training_id']}", json=changes)
    assert response.status_code == 200, response.text
    with Session(candidate["engine"]) as session:
        cached = session.get(Training, cached_id)
        assert not cached.passed and cached.workflow_status == "configuration_changed"
        user = User(first_name="Cached", email="cached@charlotte.edu")
        session.add(user)
        session.flush()
        assert attach_cached_canvas(session, user)["trainings_added"] == 0
        # A stale passed flag and new fetch timestamp cannot bypass the configuration fingerprint.
        cached.passed, cached.fetched_at = True, utcnow()
        session.add(cached)
        session.flush()
        assert attach_cached_canvas(session, user)["trainings_added"] == 0
        training = session.get(TrainingType, candidate["training_id"])
        cached.config_fingerprint = TrainingSpec.from_model(training).fingerprint
        cached.score = max(8, (training.canvas_minimum_score or 0) + 1)
        cached.workflow_status = "graded"
        session.add(cached)
        session.flush()
        assert attach_cached_canvas(session, user)["trainings_added"] == 1


@pytest.mark.parametrize("path", ["/api/admin/metrics", "/api/admin/metrics.csv"])
def test_metrics_report_uses_one_snapshot_during_concurrent_checkout(candidate, path):
    import csv
    import io

    from sqlalchemy import event

    db = candidate["engine"]
    with Session(db) as session:
        session.execute(text("DELETE FROM keyholder_shifts"))
        session.execute(text("DELETE FROM visits"))
        visit = Visit(
            user_id=candidate["users"]["member"], enter_time=datetime(2026, 11, 1, 12, tzinfo=UTC)
        )
        session.add(visit)
        session.commit()
        visit_id = visit.id
    changed = []

    def checkout_after_summary(conn, cursor, statement, parameters, context, executemany):
        if "average_visit_minutes" in statement and not changed:
            changed.append(True)
            with db.begin() as writer:
                writer.execute(
                    text("UPDATE visits SET exit_time=:end, forgot_to_sign_out=false WHERE id=:id"),
                    {"end": datetime(2026, 11, 1, 13, tzinfo=UTC), "id": visit_id},
                )

    client = candidate["client"]
    login(client, "holder")
    event.listen(db, "after_cursor_execute", checkout_after_summary)
    try:
        response = client.get(
            path, params={"start": "2026-11-01", "end": "2026-11-02", "timezone": "UTC"}
        )
        assert response.status_code == 200, response.text
    finally:
        event.remove(db, "after_cursor_execute", checkout_after_summary)
    assert changed
    if path.endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(response.text)))
        hours = [float(row["value"]) for row in rows if row["metric"] == "total_hours"]
        assert hours == [0, 0]
    else:
        report = response.json()
        assert report["summary"]["total_hours"] == 0
        assert report["summary"]["open_visits"] == 1
        assert sum(day["total_hours"] for day in report["daily"]) == 0
    with Session(db) as session:
        assert session.get(Visit, visit_id).exit_time is not None


def test_training_mutations_return_the_saved_record_for_the_next_ui_action(candidate):
    client = candidate["client"]
    login(client, "holder")
    created = client.post("/api/admin/training-types", json={"name": "New training"})
    assert created.status_code == 201, created.text
    training_id = created.json()["id"]
    renamed = client.patch(
        f"/api/admin/training-types/{training_id}", json={"name": "Renamed training"}
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Renamed training"
    awarded = client.post(
        "/api/admin/trainings",
        json={
            "user_id": str(candidate["users"]["member"]),
            "training_type_id": training_id,
        },
    )
    assert awarded.status_code == 201, awarded.text
    cert_id = awarded.json()["id"]
    assert awarded.json()["has_training"] is True
    revoked = client.post(
        f"/api/admin/trainings/{cert_id}/revoke", json={"reason": "Correction fixture"}
    )
    assert revoked.status_code == 200 and revoked.json()["revoked_at"]


def test_simplified_core_schema_uses_real_pg_enum_and_numeric_space_level(candidate):
    from sqlalchemy.exc import IntegrityError

    with Session(candidate["engine"]) as session:
        columns = set(
            session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='users'"
                )
            ).scalars()
        )
        assert {"email", "password_hash", "space_level"} <= columns
        assert columns.isdisjoint({"normalized_email", "physical_access_level"})
        assert (
            session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=current_schema() AND table_name='accounts'"
                )
            ).scalar_one()
            == 0
        )
        identity_columns = set(
            session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='external_identities'"
                )
            ).scalars()
        )
        assert "value" in identity_columns and "normalized_value" not in identity_columns
        visit_columns = set(
            session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='visits'"
                )
            ).scalars()
        )
        assert {"enter_time", "exit_time", "forgot_to_sign_out"} <= visit_columns
        assert visit_columns.isdisjoint(
            {"started_at", "ended_at", "purpose", "end_quality", "closure_reason"}
        )
        enum = session.execute(
            text("""SELECT t.typtype, array_agg(e.enumlabel ORDER BY e.enumsortorder) labels
            FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
            JOIN pg_enum e ON e.enumtypid=t.oid
            WHERE a.attrelid='users'::regclass AND a.attname='role' GROUP BY t.typtype""")
        ).one()
        assert enum.typtype == "e" and set(enum.labels) == {role.name for role in Role}
        assert (
            session.execute(
                text("SELECT space_level FROM users WHERE id=:id"),
                {"id": candidate["users"]["holder"]},
            ).scalar_one()
            == 3
        )
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE users SET space_level=4 WHERE id=:id"),
                {"id": candidate["users"]["member"]},
            )
        session.rollback()


def test_merged_password_hash_never_appears_in_normal_user_dtos(candidate):
    client = candidate["client"]
    session_payload = login(client, "holder")
    results = [
        session_payload,
        client.get("/api/me/profile").json(),
        client.get(f"/api/admin/users/{candidate['users']['holder']}").json(),
        client.get("/api/public/occupancy").json(),
    ]
    for payload in results:
        assert "password_hash" not in str(payload)
        assert "scrypt$" not in str(payload)


def test_volunteer_can_open_without_login_and_stale_confirmation_is_rejected(candidate):
    client = candidate["client"]
    # Sole owner leaving closes the lab directly, without a handoff dialog.
    left = tap(client, "holder-id")
    assert left.status_code == 200 and left.json()["status"] == "signed_out"
    assert tap(client, "member-id").json()["status"] == "lab_closed"
    prompt = tap(client, "operator-id").json()
    assert prompt["actions"] == ["open"] and prompt["expected_shift_id"] is None
    opened = client.post(
        "/api/kiosk/keyholder",
        json={"identifier": "operator-id", "action": "open", "expected_shift_id": None},
    )
    assert opened.status_code == 200, opened.text
    assert client.get("/api/public/occupancy").json()["lab"]["keyholder"]["id"] == str(
        candidate["users"]["operator"]
    )
    # The same stale open decision cannot change the new shift.
    assert (
        client.post(
            "/api/kiosk/keyholder",
            json={"identifier": "operator-id", "action": "open", "expected_shift_id": None},
        ).status_code
        == 409
    )


def test_equal_priority_never_prompts_takeover_and_member_priority_cannot_grant_eligibility(
    candidate,
):
    with Session(candidate["engine"]) as session:
        higher = session.get(User, candidate["users"]["higher"])
        higher.keyholder_priority = 2
        member = session.get(User, candidate["users"]["member"])
        member.keyholder_priority = 100
        session.add_all([higher, member])
        session.commit()
    client = candidate["client"]
    assert tap(client, "higher-id").json()["status"] == "signed_in"
    assert tap(client, "member-id").json()["status"] == "signed_in"
    current = client.get("/api/public/occupancy").json()["lab"]["keyholder"]
    assert current["id"] == str(candidate["users"]["holder"])
    prompt = tap(client, "holder-id").json()
    assert (
        client.post(
            "/api/kiosk/keyholder",
            json={
                "identifier": "member-id",
                "action": "override",
                "expected_shift_id": prompt["expected_shift_id"],
            },
        ).status_code
        == 403
    )


def test_handoff_to_present_volunteer_preserves_one_visit_and_optional_owner_presence(candidate):
    client = candidate["client"]
    assert tap(client, "operator-id").json()["status"] == "signed_in"
    prompt = tap(client, "holder-id").json()
    handed = client.post(
        "/api/kiosk/keyholder",
        json={
            "identifier": "holder-id",
            "action": "handoff",
            "target_identifier": "operator-id",
            "sign_out_current_keyholder": False,
            "expected_shift_id": prompt["expected_shift_id"],
        },
    )
    assert handed.status_code == 200, handed.text
    with Session(candidate["engine"]) as session:
        shift = session.exec(select(KeyholderShift).where(KeyholderShift.ended_at.is_(None))).one()
        assert shift.user_id == candidate["users"]["operator"]
        visits = session.exec(
            select(Visit).where(Visit.user_id == candidate["users"]["operator"])
        ).all()
        assert len(visits) == 1 and visits[0].exit_time is None
        assert len(session.exec(select(Visit).where(Visit.exit_time.is_(None))).all()) == 2
    stale_close = client.post(
        "/api/kiosk/keyholder",
        json={
            "identifier": "holder-id",
            "action": "close",
            "expected_shift_id": prompt["expected_shift_id"],
        },
    )
    assert stale_close.status_code == 409


def test_internal_kiosk_requires_same_origin_but_no_staff_session_or_pairing(candidate):
    client = candidate["client"]
    assert not client.cookies
    assert client.get("/api/kiosk/state").status_code == 200
    assert (
        client.post(
            "/api/kiosk/tap",
            json={"identifier": "member-id"},
            headers={"Origin": "http://untrusted.example"},
        ).status_code
        == 403
    )
    assert tap(client, "member-id").json()["status"] == "signed_in"
    with client.websocket_connect(
        "/ws/kiosk", headers={"Origin": get_settings().app_origin}
    ) as socket:
        assert socket.receive_json()["type"] == "snapshot"
        socket.send_json(
            {
                "type": "command",
                "id": "followup",
                "command": "tap",
                "data": {"identifier": "member-id"},
            }
        )
        for _ in range(5):
            message = socket.receive_json()
            if message["type"] == "result":
                assert message["id"] == "followup" and message["result"]["status"] == "signed_out"
                break
        else:
            pytest.fail("Kiosk WebSocket command did not return its result")


def test_cancelled_http_tap_keeps_its_worker_session_open(candidate, monkeypatch):
    import asyncio
    from contextlib import suppress
    from threading import Event

    import httpx

    from app.routes import kiosk

    started, release, closed = Event(), Event(), Event()
    command_sessions = []
    original_execute = kiosk.execute_command

    class TrackedSession(Session):
        def close(self):
            if self in command_sessions:
                closed.set()
            super().close()

    def paused_command(session, command, data):
        command_sessions.append(session)
        # Start a transaction before cancelling the HTTP request. Its lifetime
        # must belong to this worker, even after the caller stops awaiting it.
        session.exec(select(User).where(User.id == candidate["users"]["member"])).one()
        started.set()
        assert release.wait(5)
        return original_execute(session, command, data)

    monkeypatch.setattr(database, "Session", TrackedSession)
    monkeypatch.setattr(kiosk, "execute_command", paused_command)

    async def invoke():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=candidate["client"].app),
            base_url=get_settings().app_origin,
        ) as client:
            request = asyncio.create_task(
                client.post(
                    "/api/kiosk/tap",
                    json={"identifier": "member-id"},
                    headers={"Origin": get_settings().app_origin},
                )
            )
            try:
                assert await asyncio.to_thread(started.wait, 5)
                request.cancel()
                with suppress(asyncio.CancelledError):
                    await request
                assert not closed.is_set(), "Request teardown closed a running worker's session"
            finally:
                release.set()
                assert await asyncio.to_thread(closed.wait, 5)

    asyncio.run(invoke())
    with Session(candidate["engine"]) as session:
        visit = session.exec(
            select(Visit).where(Visit.user_id == candidate["users"]["member"])
        ).one()
        assert visit.exit_time is None


def test_single_role_assignment_matrix_and_last_superadmin(candidate):
    client, users = candidate["client"], candidate["users"]
    login(client, "viewer")  # This fixture is an ordinary admin, not a viewer role.
    member, holder, admin = users["member"], users["holder"], users["viewer"]
    response = client.put(f"/api/admin/users/{member}/role", json={"role": "operator"})
    assert response.status_code == 200 and response.json()["role"] == "operator"
    assert "roles" not in response.json()
    assert client.put(f"/api/admin/users/{member}/role", json={"role": "admin"}).status_code == 200
    assert client.put(f"/api/admin/users/{member}/role", json={"role": None}).status_code == 200
    for target, role in [(admin, "superadmin"), (holder, None), (holder, "operator")]:
        assert client.put(f"/api/admin/users/{target}/role", json={"role": role}).status_code == 403
    assert client.patch(f"/api/admin/users/{holder}", json={"active": False}).status_code == 403
    login(client, "operator")
    assert (
        client.put(f"/api/admin/users/{member}/role", json={"role": "operator"}).status_code == 403
    )
    assert (
        client.post(
            "/api/admin/users",
            json={
                "identifier": "800123456",
                "first_name": "New",
                "last_name": "Visitor",
                "email": "new@charlotte.edu",
            },
        ).status_code
        == 403
    )
    login(client, "holder")
    assert client.put(f"/api/admin/users/{holder}/role", json={"role": "admin"}).status_code == 409
    assert (
        client.put(f"/api/admin/users/{admin}/role", json={"role": "superadmin"}).status_code == 200
    )
    assert client.put(f"/api/admin/users/{holder}/role", json={"role": "admin"}).status_code == 200


def test_university_email_validation_on_every_user_input_path(candidate):
    client = candidate["client"]
    login(client, "holder")
    member = candidate["users"]["member"]
    for method, path, data in [
        (
            "post",
            "/api/kiosk/register",
            {
                "identifier": "800999111",
                "first_name": "New",
                "last_name": "Visitor",
                "email": "outside@example.org",
            },
        ),
        (
            "post",
            "/api/admin/users",
            {
                "identifier": "800999112",
                "first_name": "New",
                "last_name": "Visitor",
                "email": "outside@example.org",
            },
        ),
        ("patch", f"/api/admin/users/{member}", {"email": "outside@example.org"}),
        ("patch", "/api/me/profile", {"email": "outside@example.org"}),
        ("post", "/api/auth/password-reset/request", {"email": "outside@example.org"}),
    ]:
        assert getattr(client, method)(path, json=data).status_code == 422, path
    result = client.post(
        "/api/kiosk/register",
        json={
            "identifier": "800999113",
            "first_name": "New",
            "last_name": "Visitor",
            "email": "NEW@UNCC.EDU",
        },
    )
    assert result.status_code == 200, result.text
    with Session(candidate["engine"]) as session:
        assert session.exec(select(User).where(User.email == "new@charlotte.edu")).one()
    imported = client.post(
        "/api/admin/imports/users/preview",
        json={
            "csv_text": "identifier,first_name,last_name,email\n800999114,New,Visitor,outside@example.org\n"
        },
    )
    assert imported.status_code == 200 and imported.json()["summary"]["invalid"] == 1


def test_readable_audit_and_larger_lists_use_batch_names(candidate):
    from sqlalchemy import event

    from app.events import audit
    from app.models import utcnow

    holder, member = candidate["users"]["holder"], candidate["users"]["member"]
    with Session(candidate["engine"]) as session:
        for _ in range(40):
            record = Training(
                user_id=member, training_type_id=candidate["training_id"], awarded_at=utcnow()
            )
            session.add(record)
            session.flush()
            audit(session, "training.awarded", "trainings", record.id, holder)
        session.add_all([User(first_name=f"Batch {i}", last_name="Fixture") for i in range(110)])
        session.commit()
    client = candidate["client"]
    login(client, "operator")
    queries = []

    def counted(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(candidate["engine"], "before_cursor_execute", counted)
    try:
        response = client.get("/api/admin/audit-events")
    finally:
        event.remove(candidate["engine"], "before_cursor_execute", counted)
    assert response.status_code == 200 and response.json()["page_size"] == 100
    items = [item for item in response.json()["items"] if item["action"] == "training.awarded"]
    assert len(items) == 40
    assert all(
        item["actor_name"] == "holder Fixture"
        and item["target_name"] == "Laser Cutter · member Fixture"
        for item in items
    )
    assert all(
        item["actor_href"].endswith(str(holder)) and item["target_href"].endswith(str(member))
        for item in items
    )
    assert len(queries) <= 10, len(queries)
    default = client.get("/api/admin/users").json()
    larger = client.get("/api/admin/users?page_size=1000").json()
    assert default["page_size"] == 100 and len(default["items"]) == 100
    assert len(larger["items"]) == larger["total"]
    assert client.get("/api/admin/users?page_size=1001").status_code == 422


def test_training_schema_has_one_identity_authority_and_no_tiers(candidate):
    from app.models import ExternalIdentity

    with Session(candidate["engine"]) as session:
        tables = set(
            session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()"
                )
            ).scalars()
        )
        assert "trainings" in tables
        assert tables.isdisjoint({"canvas_results", "certifications", "user_roles"})
        columns = set(
            session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='training_types'"
                )
            ).scalars()
        )
        assert columns.isdisjoint({"slug", "description", "canvas_level"})
        definition = session.get(TrainingType, candidate["training_id"])
        identity = ExternalIdentity(
            provider="canvas_id",
            issuer="fixture",
            value="valid-foreign-key",
            user_id=candidate["users"]["member"],
        )
        session.add(identity)
        session.flush()
        invalid = Training(
            user_id=candidate["users"]["member"],
            external_identity_id=identity.id,
            source="canvas",
            training_type_id=definition.id,
        )
        session.add(invalid)
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError) as failure:
            session.flush()
        assert failure.value.orig.sqlstate == "23514"
        session.rollback()


def test_uncredentialed_superadmin_role_cannot_allow_last_login_to_be_removed(candidate):
    client = candidate["client"]
    login(client, "holder")
    member, holder = candidate["users"]["member"], candidate["users"]["holder"]
    assert (
        client.put(f"/api/admin/users/{member}/role", json={"role": "superadmin"}).status_code
        == 200
    )
    assert client.put(f"/api/admin/users/{holder}/role", json={"role": "admin"}).status_code == 409


def test_visit_duration_uses_elapsed_seconds_across_eastern_fall_back(candidate):
    from app.routes.operations import visits

    with Session(candidate["engine"]) as session:
        visit = Visit(
            user_id=candidate["users"]["member"],
            enter_time=datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
            exit_time=datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
        )
        session.add(visit)
        session.commit()
        session.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
        result = visits(
            session, None, page=1, page_size=100, user_id=candidate["users"]["member"], active=False
        )
        assert result["items"][0]["duration_seconds"] == 3600


@pytest.mark.parametrize("staff", ["operator", "viewer", "holder"])
def test_manual_training_assignment_rejects_active_duplicate_and_preserves_history(
    candidate, staff
):
    client = candidate["client"]
    login(client, staff)
    user_id = candidate["users"]["member"]
    data = {"user_id": str(user_id), "training_type_id": str(candidate["training_id"])}
    first = client.post("/api/admin/trainings", json=data)
    assert first.status_code == 201
    duplicate = client.post("/api/admin/trainings", json=data)
    assert duplicate.status_code == 409
    tap(client, "member-id")
    assert (
        client.post(
            f"/api/admin/trainings/{first.json()['id']}/revoke", json={"reason": "Correction"}
        ).status_code
        == 200
    )
    occupant = next(
        row
        for row in client.get("/api/public/occupancy").json()["occupants"]
        if row["id"] == str(user_id)
    )
    assert occupant["badges"] == []
    replacement = client.post("/api/admin/trainings", json=data)
    assert replacement.status_code == 201
    with Session(candidate["engine"]) as session:
        record = session.get(Training, replacement.json()["id"])
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.add(record)
        session.commit()
    assert client.post("/api/admin/trainings", json=data).status_code == 201
    with Session(candidate["engine"]) as session:
        records = session.exec(select(Training).where(Training.user_id == user_id)).all()
        assert len(records) == 3
        assert sum(row.revoked_at is not None for row in records) == 1


def test_concurrent_manual_training_assignments_create_one_active_row(candidate):
    client = candidate["client"]
    login(client, "operator")
    data = {
        "user_id": str(candidate["users"]["member"]),
        "training_type_id": str(candidate["training_id"]),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: client.post("/api/admin/trainings", json=data), range(2))
        )
    assert sorted(response.status_code for response in responses) == [201, 409]
    with Session(candidate["engine"]) as session:
        assert (
            len(session.exec(select(Training).where(Training.user_id == data["user_id"])).all())
            == 1
        )
