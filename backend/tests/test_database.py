"""Actual PostgreSQL role isolation and reviewable, session-bound transactions."""

import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select

from app import database, security
from app.config import Settings
from app.models import ROLE_PERMISSIONS, AuditEvent, AuthSession, Role, ScopeRevision, User
from app.routes.database import router
from app.services import sqlconsole, sqlpreviews


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT 1; SELECT 2",
        "COMMIT",
        "SET ROLE postgres",
        "SELECT set_config('role','postgres',true)",
        "SELECT pg_catalog.set_config('transaction_read_only','off',true)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_terminate_backend(1)",
        "SELECT custom_schema.security_definer()",
        "COPY users TO PROGRAM 'anything'",
        "WITH x AS (DELETE FROM users RETURNING *) SELECT * FROM x",
        "SELECT * INTO other FROM users",
        "SELECT * FROM users FOR UPDATE",
        "SELECT * FROM auth_sessions",
        "SELECT payload FROM email_jobs",
        "DROP TABLE users",
        "EXPLAIN ANALYZE SELECT 1",
    ],
)
def test_read_policy_rejects_escapes_and_hidden_secrets(statement):
    with pytest.raises(ValueError):
        sqlconsole.validate_query(statement, "read")


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE users SET role='SUPERADMIN'",
        "UPDATE users SET password_hash='x'",
        "UPDATE users SET active=false",
        "UPDATE users SET email='outside@example.org'",
        "DELETE FROM users",
        "DELETE FROM audit_events",
        "INSERT INTO users VALUES (1)",
    ],
)
def test_write_policy_keeps_account_security_in_admin_controls(statement):
    with pytest.raises(ValueError):
        sqlconsole.validate_query(statement, "write", True)


@pytest.fixture(scope="module")
def pg_workbench():
    admin_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not admin_url:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    name = "sfl_sqlconsole_" + uuid4().hex[:12]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    owner = make_url(admin_url).set(database=name)
    engine = create_engine(owner)
    read_role, write_role, _ = sqlconsole.role_names(name)
    settings = Settings(
        _env_file=None,
        database_url=owner.render_as_string(hide_password=False),
        sql_read_database_url=owner.set(
            username=read_role, password="synthetic_read_%_quote_'_fixture"
        ).render_as_string(hide_password=False),
        sql_write_database_url=owner.set(
            username=write_role, password="synthetic_write_fixture"
        ).render_as_string(hide_password=False),
        sql_max_rows=3,
        sql_statement_timeout_ms=200,
    )
    original_engine, original_settings, preview_settings = (
        database.engine,
        sqlconsole.get_settings,
        sqlpreviews.get_settings,
    )
    database.engine = engine
    sqlconsole.get_settings = sqlpreviews.get_settings = lambda: settings
    try:
        database.init_db()
        with Session(engine) as session:
            sqlconsole.bootstrap_console_roles(session)
            user = User(
                first_name="Database",
                last_name="Fixture",
                role=Role.SUPERADMIN,
                password_hash="not-a-real-password",
                email="fixture@charlotte.edu",
            )
            session.add(user)
            session.commit()
            actor_id = user.id
        yield SimpleNamespace(engine=engine, settings=settings, actor_id=actor_id)
    finally:
        for value in [settings.sql_read_database_url, settings.sql_write_database_url]:
            sqlconsole._console_engine(value).dispose()
        sqlconsole.clear_console_pools()
        database.engine, sqlconsole.get_settings, sqlpreviews.get_settings = (
            original_engine,
            original_settings,
            preview_settings,
        )
        engine.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
            for role in [read_role, write_role]:
                conn.exec_driver_sql(f'DROP ROLE IF EXISTS "{role}"')
        admin.dispose()


def actor(pg, role=Role.SUPERADMIN):
    with Session(pg.engine) as session:
        user = session.get(User, pg.actor_id)
    auth = AuthSession(
        user_id=user.id,
        token_hash=uuid4().hex,
        csrf_hash="fixture",
        csrf_token="fixture",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return security.Actor(user, role, set(ROLE_PERMISSIONS[role]) if role else set(), auth)


def read(pg, statement):
    with Session(pg.engine) as session:
        return sqlconsole.execute_query(session, pg.actor_id, statement)


@pytest.fixture
def previews(pg_workbench):
    manager = sqlpreviews.SQLPreviews(pg_workbench.engine)
    yield manager
    manager.rollback_all()


def stage(pg, manager, who, statement):
    with Session(pg.engine) as session:
        return manager.stage(session, who, statement)


def fresh_user(pg, name="Before"):
    with Session(pg.engine) as session:
        user = User(
            first_name=name, last_name="Preview", email=f"fixture{uuid4().hex}@charlotte.edu"
        )
        session.add(user)
        session.commit()
        return user.id


def saved_name(pg, id):
    with Session(pg.engine) as session:
        return session.get(User, id).first_name


def test_read_results_bounds_literals_and_timezone(pg_workbench):
    result = read(pg_workbench, "SELECT generate_series(1,10) AS n")
    assert result["rows"] == [[1], [2], [3]] and result["truncated"]
    assert result["transaction_status"] == "read_only"
    assert read(pg_workbench, "SELECT '100% complete', $$COMMIT; SET ROLE postgres$$")["rows"] == [
        ["100% complete", "COMMIT; SET ROLE postgres"]
    ]
    assert read(pg_workbench, "SELECT 'NaN'::float8")["rows"] == [["nan"]]
    assert read(pg_workbench, "SELECT TIMESTAMPTZ '2026-07-01 16:00:00+00'")["rows"] == [
        ["2026-07-01T12:00:00-04:00"]
    ]
    assert read(pg_workbench, "SELECT TIMESTAMPTZ '2026-01-01 16:00:00+00'")["rows"] == [
        ["2026-01-01T11:00:00-05:00"]
    ]


def test_database_roles_cannot_escalate_or_read_secrets(pg_workbench):
    with sqlconsole._connection("read") as conn:
        with pytest.raises(DBAPIError):
            conn.exec_driver_sql("UPDATE users SET first_name='forbidden'")
        conn.rollback()
        with pytest.raises(DBAPIError):
            conn.exec_driver_sql("SET ROLE postgres")
        conn.rollback()
        with pytest.raises(DBAPIError):
            conn.exec_driver_sql("SELECT password_hash FROM users")
    with sqlconsole._connection("write") as conn:
        with pytest.raises(DBAPIError):
            conn.exec_driver_sql("UPDATE users SET role='SUPERADMIN'")
        conn.rollback()
        with pytest.raises(DBAPIError):
            conn.exec_driver_sql("UPDATE users SET password_hash='forbidden'")
        conn.rollback()
        with pytest.raises(DBAPIError):
            conn.exec_driver_sql("UPDATE users SET email='outside@example.org'")
        conn.rollback()
        with pytest.raises(DBAPIError):
            conn.exec_driver_sql("SELECT payload FROM email_jobs")


def test_reader_transaction_is_database_read_only_and_timeout_bounded(pg_workbench):
    with sqlconsole._connection("read") as conn, conn.begin():
        sqlconsole._configure(conn, "read")
        assert conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
    with pytest.raises(HTTPException) as failure:
        read(pg_workbench, "SELECT pg_sleep(2)")
    assert failure.value.status_code == 400


def test_schema_browser_and_rows_hide_password_but_show_singular_role(pg_workbench):
    tables = sqlconsole.list_tables()["tables"]
    assert not ({"auth_sessions", "email_jobs", "password_resets"} & {t["name"] for t in tables})
    users = next(t for t in tables if t["name"] == "users")
    assert "password_hash" not in {c["name"] for c in users["columns"]}
    assert next(c for c in users["columns"] if c["name"] == "id")["primary_key"]
    assert "role" in {c["name"] for c in users["columns"]}
    assert "password_hash" not in sqlconsole.table_rows("users")["columns"]
    with pytest.raises(HTTPException):
        sqlconsole.table_rows("users; DROP TABLE users")


def test_update_preview_is_invisible_until_same_transaction_commits(pg_workbench, previews):
    who, id = actor(pg_workbench), fresh_user(pg_workbench)
    result = stage(
        pg_workbench, previews, who, f"UPDATE users AS u SET first_name='After' WHERE u.id='{id}'"
    )
    assert result["transaction_status"] == "preview"
    assert result["changes"][0]["before"]["first_name"] == "Before"
    assert result["changes"][0]["after"]["first_name"] == "After"
    assert saved_name(pg_workbench, id) == "Before"
    with Session(pg_workbench.engine) as session:
        revisions = {r.scope: r.revision for r in session.exec(select(ScopeRevision)).all()}
    committed = previews.commit(result["preview_id"], who)
    assert committed == {"transaction_status": "committed", "row_count": 1}
    assert saved_name(pg_workbench, id) == "After"
    with Session(pg_workbench.engine) as session:
        assert session.get(ScopeRevision, "public").revision == revisions["public"] + 1
        assert session.get(ScopeRevision, "staff").revision == revisions["staff"] + 1
        audit = session.exec(
            select(AuditEvent)
            .where(AuditEvent.action == "database.query.succeeded")
            .order_by(AuditEvent.occurred_at.desc())
        ).first()
        assert "query_sha256" in audit.details and "sql" not in audit.details
    with pytest.raises(HTTPException):
        previews.commit(result["preview_id"], who)


def test_rollback_expiry_and_shutdown_never_commit(pg_workbench, previews):
    who, id = actor(pg_workbench), fresh_user(pg_workbench)
    statement = f"UPDATE users SET first_name='Not saved' WHERE id='{id}'"
    result = stage(pg_workbench, previews, who, statement)
    assert previews.rollback(result["preview_id"], who)["transaction_status"] == "rolled_back"
    assert saved_name(pg_workbench, id) == "Before"
    result = stage(pg_workbench, previews, who, statement)
    previews.pending[result["preview_id"]].deadline = 0
    previews.expire()
    assert saved_name(pg_workbench, id) == "Before"
    with pytest.raises(HTTPException) as failure:
        previews.commit(result["preview_id"], who)
    assert failure.value.status_code == 404
    stage(pg_workbench, previews, who, statement)
    previews.rollback_all()
    assert saved_name(pg_workbench, id) == "Before"


def test_preview_bound_to_both_actor_and_auth_session(pg_workbench, previews):
    who, id = actor(pg_workbench), fresh_user(pg_workbench)
    result = stage(
        pg_workbench, previews, who, f"UPDATE users SET first_name='After' WHERE id='{id}'"
    )
    for other in [actor(pg_workbench), actor(pg_workbench)]:
        if other is not who:
            with pytest.raises(HTTPException) as failure:
                previews.commit(result["preview_id"], other)
            assert failure.value.status_code == 403
    with pytest.raises(HTTPException) as failure:
        stage(pg_workbench, previews, who, f"UPDATE users SET last_name='Changed' WHERE id='{id}'")
    assert failure.value.status_code == 409
    previews.rollback(result["preview_id"], who)


def test_insert_and_delete_preview_have_exact_images(pg_workbench, previews):
    who = actor(pg_workbench)
    statement = "INSERT INTO training_types(id,name,icon_key,active) VALUES(gen_random_uuid(),'Temporary','orientation',true)"
    result = stage(pg_workbench, previews, who, statement)
    assert result["changes"][0]["before"] is None
    id = result["changes"][0]["after"]["id"]
    previews.commit(result["preview_id"], who)
    result = stage(pg_workbench, previews, who, f"DELETE FROM training_types WHERE id='{id}'")
    assert result["changes"][0]["before"]["name"] == "Temporary"
    assert result["changes"][0]["after"] is None
    previews.commit(result["preview_id"], who)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE users SET id=gen_random_uuid()",
        "UPDATE users SET first_name='x' FROM visits WHERE users.id=visits.user_id",
        "WITH x AS (SELECT 1) UPDATE users SET first_name='x'",
        "INSERT INTO training_types(id,name,icon_key,active) VALUES(gen_random_uuid(),'x','x',true) ON CONFLICT DO NOTHING",
        "UPDATE users SET role='ADMIN'",
        "UPDATE users SET password_hash='x'",
    ],
)
def test_unsupported_preview_is_rejected_before_any_change(pg_workbench, previews, statement):
    with pytest.raises(HTTPException) as failure:
        stage(pg_workbench, previews, actor(pg_workbench), statement)
    assert failure.value.status_code == 400
    assert not previews.pending


def test_preview_limit_rolls_back_large_change(pg_workbench, previews):
    for _ in range(4):
        fresh_user(pg_workbench, "Bounded")
    with pytest.raises(HTTPException) as failure:
        stage(
            pg_workbench,
            previews,
            actor(pg_workbench),
            "UPDATE users SET first_name='Too many' WHERE first_name='Bounded'",
        )
    assert failure.value.status_code == 400
    with Session(pg_workbench.engine) as session:
        assert len(session.exec(select(User).where(User.first_name == "Bounded")).all()) == 4


def test_concurrent_predicate_entry_rolls_back_instead_of_inventing_preimage(
    pg_workbench, previews, monkeypatch
):
    id = fresh_user(pg_workbench, "Concurrent predicate")
    original = sqlconsole._consume
    injected = []

    def consume(result, limit):
        value = original(result, limit)
        if not injected:
            injected.append(fresh_user(pg_workbench, "Concurrent predicate"))
        return value

    monkeypatch.setattr(sqlconsole, "_consume", consume)
    with pytest.raises(HTTPException) as failure:
        stage(
            pg_workbench,
            previews,
            actor(pg_workbench),
            "UPDATE users SET first_name='After' WHERE first_name='Concurrent predicate'",
        )
    assert failure.value.status_code == 409
    assert (
        saved_name(pg_workbench, id)
        == saved_name(pg_workbench, injected[0])
        == "Concurrent predicate"
    )


def test_read_audit_notifies_staff_only(pg_workbench):
    with Session(pg_workbench.engine) as session:
        public = session.get(ScopeRevision, "public").revision
    with psycopg.connect(pg_workbench.settings.psycopg_url, autocommit=True) as listener:
        listener.execute("LISTEN sfl_changes")
        read(pg_workbench, "SELECT 1")
        notices = [json.loads(n.payload) for n in listener.notifies(timeout=1, stop_after=2)]
    assert len(notices) == 2 and all(
        n["topics"] == ["audit"] and set(n["revisions"]) == {"staff"} for n in notices
    )
    with Session(pg_workbench.engine) as session:
        assert session.get(ScopeRevision, "public").revision == public


def test_http_admin_reads_operator_denied_and_only_sa_previews(pg_workbench, previews):
    app = FastAPI()
    app.include_router(router)
    app.state.sql_previews = previews
    who = actor(pg_workbench, Role.ADMIN)
    app.dependency_overrides[security.current_actor] = lambda: who

    def sessions():
        with Session(pg_workbench.engine) as session:
            yield session

    app.dependency_overrides[database.get_session] = sessions
    with TestClient(app) as client:
        assert client.get("/api/admin/database/tables").status_code == 200
        assert client.get("/api/admin/database/rows", params={"table": "users"}).status_code == 200
        response = client.post("/api/admin/database/query", json={"sql": "SELECT 1"})
        assert response.status_code == 200 and response.json()["transaction_status"] == "read_only"
        id = fresh_user(pg_workbench)
        payload = {"sql": f"UPDATE users SET first_name='After' WHERE id='{id}'"}
        assert client.post("/api/admin/database/query", json=payload).status_code == 403
        assert (
            client.post(
                "/api/admin/database/query", json={"sql": "SELECT 1", "mode": "read"}
            ).status_code
            == 422
        )
        who.role, who.permissions = Role.OPERATOR, set(ROLE_PERMISSIONS[Role.OPERATOR])
        assert client.get("/api/admin/database/tables").status_code == 403
        assert client.post("/api/admin/database/query", json={"sql": "SELECT 1"}).status_code == 403
        who.role, who.permissions = Role.SUPERADMIN, set(ROLE_PERMISSIONS[Role.SUPERADMIN])
        result = client.post("/api/admin/database/query", json=payload)
        assert result.status_code == 200, result.text
        preview_id = result.json()["preview_id"]
        who.role, who.permissions = Role.ADMIN, set(ROLE_PERMISSIONS[Role.ADMIN])
        assert client.post(f"/api/admin/database/preview/{preview_id}/commit").status_code == 403
        assert client.post(f"/api/admin/database/preview/{preview_id}/rollback").status_code == 200


def test_unconfigured_console_fails_closed(monkeypatch):
    monkeypatch.setattr(sqlconsole, "get_settings", lambda: Settings(_env_file=None))
    with pytest.raises(HTTPException) as failure:
        sqlconsole._settings_url("read")
    assert failure.value.status_code == 503


@pytest.mark.asyncio
async def test_lifespan_shutdown_rolls_back_pending_transaction(pg_workbench, previews):
    who, id = actor(pg_workbench), fresh_user(pg_workbench)
    await previews.start()
    stage(
        pg_workbench,
        previews,
        who,
        f"UPDATE users SET first_name='Pending shutdown' WHERE id='{id}'",
    )
    await previews.stop()
    assert saved_name(pg_workbench, id) == "Before"
    assert not previews.pending


def test_other_actor_cannot_take_over_same_session_identifier(pg_workbench, previews):
    who, id = actor(pg_workbench), fresh_user(pg_workbench)
    result = stage(
        pg_workbench, previews, who, f"UPDATE users SET first_name='After' WHERE id='{id}'"
    )
    other = actor(pg_workbench)
    other.session.id = who.session.id
    other.user = User(id=fresh_user(pg_workbench))
    with pytest.raises(HTTPException) as failure:
        previews.rollback(result["preview_id"], other)
    assert failure.value.status_code == 403
    assert saved_name(pg_workbench, id) == "Before"
    previews.rollback(result["preview_id"], who)


def test_finalize_failure_rolls_back_domain_and_revisions_but_audits_failure(
    pg_workbench, previews
):
    who, id = actor(pg_workbench), fresh_user(pg_workbench)
    result = stage(
        pg_workbench, previews, who, f"UPDATE users SET first_name='Not committed' WHERE id='{id}'"
    )
    with Session(pg_workbench.engine) as session:
        before = {row.scope: row.revision for row in session.exec(select(ScopeRevision)).all()}
        session.execute(
            text(
                "ALTER TABLE audit_events ADD CONSTRAINT reject_test_success CHECK(action <> 'database.query.succeeded') NOT VALID"
            )
        )
        session.commit()
    try:
        with pytest.raises(HTTPException) as failure:
            previews.commit(result["preview_id"], who)
        assert failure.value.status_code == 409
        assert saved_name(pg_workbench, id) == "Before"
        assert not previews.pending
        with Session(pg_workbench.engine) as session:
            assert session.get(ScopeRevision, "public").revision == before["public"]
            assert session.get(ScopeRevision, "staff").revision == before["staff"] + 1
            assert (
                session.exec(
                    select(AuditEvent)
                    .where(AuditEvent.action == "database.query.failed")
                    .order_by(AuditEvent.occurred_at.desc())
                )
                .first()
                .details["error_kind"]
                == "commit"
            )
    finally:
        with pg_workbench.engine.begin() as conn:
            conn.execute(text("ALTER TABLE audit_events DROP CONSTRAINT reject_test_success"))
