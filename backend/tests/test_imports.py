"""Bulk preregistration must not impersonate physical attendance."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func
from sqlalchemy.engine import make_url
from sqlmodel import Session, select

from app import database, security
from app.models import (
    AuditEvent,
    AuthSession,
    EmailJob,
    ExternalIdentity,
    KeyholderShift,
    Permission,
    Role,
    SpaceLevel,
    User,
    Visit,
)
from app.routes.imports import router
from app.services.identity import add_student_identifier
from app.services.imports import _parse, apply_users, preview_users

HEADER = "student_id,first_name,last_name,email\n"


@pytest.mark.parametrize(
    "content",
    [
        "first_name,last_name\nNo,Identifier\n",
        "identifier,student_id,first_name,last_name\n801000001,801000002,No,Ambiguity\n",
        "identifier,first_name,last_name,roles\n801000001,No,Escalation,superadmin\n",
        'identifier,first_name,last_name\n801000001,"unterminated,Name\n',
        "identifier,first_name,last_name,\n801000001,Blank,Header,\n",
    ],
)
def test_bad_csv_structure_is_rejected(content):
    with pytest.raises(HTTPException) as invalid:
        _parse(content)
    assert invalid.value.status_code == 422


def test_explicit_header_aliases_and_unicode_names():
    rows, ignored = _parse(
        "\ufeffNiner ID,First Name,Last Name,Email Address,Timestamp\n801000001, Zoë ,O'Connor,USER@UNCC.EDU,ignored\n"
    )
    assert rows[0].identifier == "801000001"
    assert rows[0].first_name == "Zoë"
    assert rows[0].email == "user@charlotte.edu"
    assert ignored == ["Timestamp"]


@pytest.fixture(scope="module")
def pg_import():
    admin_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not admin_url:
        pytest.skip("Set TEST_DATABASE_URL or DATABASE_URL to a disposable PostgreSQL instance")
    name = "sfl_imports_" + uuid4().hex[:12]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql('CREATE DATABASE "' + name + '"')
    engine = create_engine(make_url(admin_url).set(database=name))
    original_engine = database.engine
    database.engine = engine
    try:
        database.init_db()
        with Session(engine) as session:
            actor = User(first_name="CSV", last_name="Operator")
            session.add(actor)
            session.commit()
            actor_id = actor.id
        yield SimpleNamespace(engine=engine, actor_id=actor_id)
    finally:
        database.engine = original_engine
        engine.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql('DROP DATABASE "' + name + '" WITH (FORCE)')
        admin.dispose()


def snapshot_counts(session):
    return {
        model.__tablename__: session.exec(select(func.count()).select_from(model)).one()
        for model in (
            User,
            ExternalIdentity,
            Visit,
            EmailJob,
            KeyholderShift,
        )
    }


def import_csv(pg, content):
    with Session(pg.engine) as session:
        preview = preview_users(session, content)
        return apply_users(session, pg.actor_id, content, preview["fingerprint"], True)


@pytest.mark.postgres
def test_preview_is_read_only_and_apply_has_no_attendance_or_access_side_effects(pg_import):
    content = (
        HEADER
        + "801000101,First,Visitor,FIRST@UNCC.EDU\n801000102,Second,Visitor,second@charlotte.edu\n"
    )
    with Session(pg_import.engine) as session:
        before = snapshot_counts(session)
        preview = preview_users(session, content)
        assert preview["summary"] == {
            "total": 2,
            "new": 2,
            "existing": 0,
            "conflict": 0,
            "invalid": 0,
        }
        assert snapshot_counts(session) == before
        applied = apply_users(session, pg_import.actor_id, content, preview["fingerprint"], True)
        assert applied["created"] == 2
        after = snapshot_counts(session)
        assert after["users"] == before["users"] + 2
        assert after["external_identities"] == before["external_identities"] + 2
        assert {
            key: value
            for key, value in after.items()
            if key not in {"users", "external_identities"}
        } == {
            key: value
            for key, value in before.items()
            if key not in {"users", "external_identities"}
        }
        for user_id in applied["created_user_ids"]:
            user = session.get(User, user_id)
            assert user.space_level == SpaceLevel.MEMBER
            assert user.password_hash is None
            assert user.keyholder_priority == -1
        assert session.exec(select(AuditEvent).where(AuditEvent.action == "users.imported")).first()


@pytest.mark.postgres
def test_existing_profiles_are_skipped_and_never_modified(pg_import):
    content = HEADER + "801000201,Existing,Profile,EXISTING@UNCC.EDU\n"
    with Session(pg_import.engine) as session:
        user = User(
            first_name="Existing",
            last_name="Profile",
            email="existing@charlotte.edu",
            space_level=SpaceLevel.STAFF,
            keyholder_priority=9,
            active=False,
        )
        session.add(user)
        session.flush()
        add_student_identifier(session, user, "801000201")
        session.commit()
        user_id, updated_at = user.id, user.updated_at
        preview = preview_users(session, content)
        assert preview["rows"][0]["status"] == "existing"
        assert "inactive" in preview["rows"][0]["message"]
        result = apply_users(session, pg_import.actor_id, content, preview["fingerprint"], True)
        assert result["created"] == 0 and result["skipped_existing"] == 1
        session.expire_all()
        user = session.get(User, user_id)
        assert (
            user.space_level,
            user.keyholder_priority,
            user.active,
            user.updated_at,
        ) == (SpaceLevel.STAFF, 9, False, updated_at)


@pytest.mark.postgres
@pytest.mark.parametrize(
    "rows",
    [
        "801000301,Duplicate,One,a@charlotte.edu\n801000301,Duplicate,Two,b@charlotte.edu\n",
        "801000302,Shared,One,SHARED@UNCC.EDU\n801000303,Shared,Two,shared@charlotte.edu\n",
        "801000304,Valid,One,valid@charlotte.edu\n801000305,,Invalid,bad-email\n",
    ],
)
def test_conflicting_or_invalid_batch_is_atomic(pg_import, rows):
    content = HEADER + rows
    with Session(pg_import.engine) as session:
        before = snapshot_counts(session)
        preview = preview_users(session, content)
        assert preview["can_apply"] is False
        with pytest.raises(HTTPException) as rejected:
            apply_users(session, pg_import.actor_id, content, preview["fingerprint"], True)
        assert rejected.value.status_code == 409
        assert snapshot_counts(session) == before


@pytest.mark.postgres
def test_existing_identity_and_email_conflicts_are_not_silently_merged(pg_import):
    with Session(pg_import.engine) as session:
        existing = User(
            first_name="Original",
            last_name="Identity",
            email="original@charlotte.edu",
        )
        session.add(existing)
        session.flush()
        add_student_identifier(session, existing, "801000401")
        session.add(
            ExternalIdentity(
                provider="student_id",
                issuer="charlotte",
                value="801000403",
            )
        )
        session.commit()
        content = (
            HEADER
            + "801000401,Different,Person,original@charlotte.edu\n801000402,Another,Identifier,original@charlotte.edu\n801000403,Unbound,Identity,unbound@charlotte.edu\n"
        )
        preview = preview_users(session, content)
        assert preview["summary"]["conflict"] == 3
        with pytest.raises(HTTPException):
            apply_users(session, pg_import.actor_id, content, preview["fingerprint"], True)
        assert session.get(User, existing.id).first_name == "Original"


@pytest.mark.postgres
def test_confirmed_preview_binds_both_input_and_database_state(pg_import):
    content = HEADER + "801000501,Pending,Import,pending@charlotte.edu\n"
    with Session(pg_import.engine) as session:
        original = preview_users(session, content)
        with pytest.raises(HTTPException) as unconfirmed:
            apply_users(session, pg_import.actor_id, content, original["fingerprint"], False)
        assert unconfirmed.value.status_code == 400
        with pytest.raises(HTTPException) as changed:
            apply_users(
                session,
                pg_import.actor_id,
                content.replace("Pending", "Changed"),
                original["fingerprint"],
                True,
            )
        assert changed.value.status_code == 409
        # A matching identifier created after preview changes the plan to existing.
        existing = User(
            first_name="Pending",
            last_name="Import",
            email="pending@charlotte.edu",
        )
        session.add(existing)
        session.flush()
        add_student_identifier(session, existing, "801000501")
        session.commit()
        with pytest.raises(HTTPException) as stale:
            apply_users(session, pg_import.actor_id, content, original["fingerprint"], True)
        assert stale.value.status_code == 409
        refreshed = preview_users(session, content)
        assert (
            apply_users(session, pg_import.actor_id, content, refreshed["fingerprint"], True)[
                "skipped_existing"
            ]
            == 1
        )


@pytest.mark.postgres
def test_simultaneous_apply_creates_one_profile(pg_import):
    content = HEADER + "801000601,Concurrent,Import,concurrent@charlotte.edu\n"
    with Session(pg_import.engine) as session:
        fingerprint = preview_users(session, content)["fingerprint"]

    def apply_once():
        with Session(pg_import.engine) as session:
            try:
                return apply_users(session, pg_import.actor_id, content, fingerprint, True)[
                    "created"
                ]
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = list(executor.map(lambda _: apply_once(), range(2)))
    assert sorted(result) == [1, 409]
    with Session(pg_import.engine) as session:
        assert (
            session.exec(
                select(func.count())
                .select_from(ExternalIdentity)
                .where(
                    ExternalIdentity.provider == "student_id",
                    ExternalIdentity.value == "801000601",
                )
            ).one()
            == 1
        )


@pytest.mark.postgres
def test_user_write_permission_and_http_contract(pg_import):
    app = FastAPI()
    app.include_router(router)
    with Session(pg_import.engine) as session:
        actor_user = session.get(User, pg_import.actor_id)
        actor = security.Actor(
            actor_user,
            None,
            set(),
            AuthSession(
                user_id=actor_user.id,
                token_hash="fixture",
                csrf_hash="fixture",
                csrf_token="fixture",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            ),
        )
        app.dependency_overrides[security.current_actor] = lambda: actor
        app.dependency_overrides[database.get_session] = lambda: session
        content = HEADER + "801000701,HTTP,Import,http@charlotte.edu\n"
        with TestClient(app) as client:
            assert (
                client.post(
                    "/api/admin/imports/users/preview", json={"csv_text": content}
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/admin/imports/users/apply",
                    json={"csv_text": content, "fingerprint": "0" * 64, "confirm": True},
                ).status_code
                == 403
            )
            actor.role = Role.OPERATOR
            actor.permissions = {Permission.USERS_WRITE}
            assert (
                client.post(
                    "/api/admin/imports/users/preview", json={"csv_text": content}
                ).status_code
                == 403
            )
            actor.role = Role.ADMIN
            preview = client.post("/api/admin/imports/users/preview", json={"csv_text": content})
            assert preview.status_code == 200
            assert preview.json()["can_apply"] is True
            applied = client.post(
                "/api/admin/imports/users/apply",
                json={
                    "csv_text": content,
                    "fingerprint": preview.json()["fingerprint"],
                    "confirm": True,
                },
            )
            assert applied.status_code == 200
            assert applied.json()["created"] == 1
            assert "PreviewResponse" in client.get("/openapi.json").json()["components"]["schemas"]


def test_csv_size_and_row_bounds():
    with pytest.raises(HTTPException) as oversized:
        _parse("x" * 1_000_001)
    assert oversized.value.status_code == 422
    content = HEADER + "".join(
        f"{801100000 + number},Bounded,Visitor,user{number}@charlotte.edu\n"
        for number in range(2001)
    )
    with pytest.raises(HTTPException) as too_many:
        _parse(content)
    assert too_many.value.status_code == 422
    assert "2000" in too_many.value.detail
