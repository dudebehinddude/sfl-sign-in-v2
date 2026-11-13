"""Canonical tool order and the legacy lab-local today's-visits contract."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from test_canvas import db as db
from test_canvas import settings as settings
from test_core import PASSWORD, login
from test_core import candidate as candidate

from app.models import (
    CanvasRoster,
    ExternalIdentity,
    Training,
    TrainingType,
    User,
    Visit,
    training_type_order,
    utcnow,
)
from app.services.kiosk import label_for_user

pytestmark = pytest.mark.postgres

KNOWN_TYPES = [
    ("Policies and Procedures", "policies"),
    ("Orientation", "orientation"),
    ("FDM Printing", "3d-printer"),
    ("Laser Cutter", "laser-cutter"),
    ("Resin Printing", "resin-printer"),
    ("Waterjet", "waterjet"),
]


@pytest.fixture
def empty_db(db):
    return db


def test_definition_order_propagates_to_all_badges_types_and_label_with_dedup(candidate):
    client, db = candidate["client"], candidate["engine"]
    member = candidate["users"]["member"]
    with Session(db) as session:
        laser = session.get(TrainingType, candidate["training_id"])
        laser.display_order = 3
        session.add(laser)
        types = [
            TrainingType(id=UUID(int=3), name="Alpha", icon_key="orientation", display_order=0),
            TrainingType(id=UUID(int=4), name="Alpha", icon_key="policies", display_order=0),
            TrainingType(id=UUID(int=2), name="Bravo", icon_key="waterjet", display_order=0),
            laser,
        ]
        session.add_all(types[:3])
        session.flush()
        for definition in types:
            session.add(
                Training(user_id=member, training_type_id=definition.id, awarded_at=utcnow())
            )
        identity = ExternalIdentity(
            provider="canvas_id",
            issuer="https://instructure.charlotte.edu",
            value="4999",
            user_id=member,
        )
        session.add(identity)
        session.flush()
        session.add(
            Training(
                source="canvas",
                external_identity_id=identity.id,
                training_type_id=types[0].id,
                awarded_at=utcnow(),
                passed=True,
            )
        )
        session.add(Visit(user_id=member))
        session.commit()
        expected = [str(definition.id) for definition in types]

    login(client, "holder")

    def assert_order(order):
        occupants = client.get("/api/public/occupancy").json()["occupants"]
        person = next(person for person in occupants if person["id"] == str(member))
        assert [badge["training_type_id"] for badge in person["badges"]] == order
        user = client.get(f"/api/admin/users/{member}").json()
        assert [badge["training_type_id"] for badge in user["badges"]] == order
        definitions = client.get("/api/admin/training-types").json()["items"]
        assert [definition["id"] for definition in definitions] == order
        assert all("display_order" in definition for definition in definitions)
        public = client.get("/api/public/training-types").json()["items"]
        assert [definition["id"] for definition in public] == order
        assert all("display_order" in definition for definition in public)
        status = client.get("/api/admin/canvas/status").json()
        assert [definition["training_type_id"] for definition in status["trainings"]] == order
        with Session(db) as session:
            label = label_for_user(session, session.get(User, member))
            assert [badge["training_type_id"] for badge in label["badges"]] == order

    assert_order(expected)
    response = client.patch(f"/api/admin/training-types/{expected[0]}", json={"display_order": 10})
    assert response.status_code == 200 and response.json()["display_order"] == 10
    assert_order(expected[1:] + expected[:1])
    with Session(db) as session:
        awards = session.exec(
            select(Training).where(Training.training_type_id == UUID(expected[0]))
        ).all()
        assert len(awards) == 2 and all(award.awarded_at is not None for award in awards)
        assert next(award for award in awards if award.source == "canvas").passed


def test_order_default_and_nonnegative_api_and_database_constraint(candidate):
    client = candidate["client"]
    login(client, "holder")
    created = client.post("/api/admin/training-types", json={"name": "Appended tool"})
    assert created.status_code == 201 and created.json()["display_order"] == 100
    assert (
        client.post(
            "/api/admin/training-types", json={"name": "Invalid", "display_order": -1}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/admin/training-types/{created.json()['id']}", json={"display_order": -1}
        ).status_code
        == 422
    )
    with Session(candidate["engine"]) as session:
        raw = session.execute(
            text(
                "INSERT INTO training_types(id,name,icon_key,active) VALUES(:id,'Raw default','orientation',true) RETURNING display_order"
            ),
            {"id": uuid4()},
        ).scalar_one()
        assert raw == 100
        session.commit()
        with pytest.raises(IntegrityError) as failure:
            session.execute(
                text("UPDATE training_types SET display_order=-1 WHERE id=:id"),
                {"id": created.json()["id"]},
            )
        assert failure.value.orig.sqlstate == "23514"
        session.rollback()


def test_demo_seed_matches_original_printed_order(empty_db, monkeypatch):
    from app import cli

    monkeypatch.setattr(cli, "engine", empty_db)
    cli.seed_demo(PASSWORD)
    with Session(empty_db) as session:
        types = session.exec(select(TrainingType).order_by(*training_type_order())).all()
        assert [(definition.name, definition.icon_key) for definition in types] == KNOWN_TYPES
        assert [definition.display_order for definition in types] == list(range(6))


def test_additive_preview_migration_preserves_cache_and_later_custom_order(empty_db):
    with Session(empty_db) as session:
        definitions = [TrainingType(name=name, icon_key=icon) for name, icon in KNOWN_TYPES]
        # Ordering backfill also works if an original icon was already uploaded.
        definitions[1].icon_key = "training-icons/" + "a" * 32 + ".png"
        custom = TrainingType(name="Custom icon reuse", icon_key="orientation")
        session.add_all(definitions + [custom])
        user = User(first_name="Synthetic", email="synthetic@charlotte.edu")
        identity = ExternalIdentity(provider="canvas_id", issuer="fixture", value="1234")
        session.add_all([user, identity])
        session.flush()
        session.add(CanvasRoster(external_identity_id=identity.id, email="cached@charlotte.edu"))
        session.add_all(
            [
                Training(user_id=user.id, training_type_id=definitions[0].id, awarded_at=utcnow()),
                Training(
                    source="canvas",
                    external_identity_id=identity.id,
                    training_type_id=definitions[1].id,
                    score=8,
                    passed=True,
                    submission_id="4321",
                    fetched_at=utcnow(),
                ),
            ]
        )
        session.commit()
        training_before = {row.id: row.model_dump() for row in session.exec(select(Training)).all()}
        counts_before = {
            model.__tablename__: len(session.exec(select(model)).all())
            for model in [User, ExternalIdentity, CanvasRoster, TrainingType]
        }
    with empty_db.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE training_types DROP COLUMN display_order")
    migration = (
        Path(__file__).parents[1] / "migrations/add_training_display_order.sql"
    ).read_text()
    with empty_db.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(migration)
    with Session(empty_db) as session:
        rows = session.exec(select(TrainingType).order_by(*training_type_order())).all()
        assert [(row.name, row.display_order) for row in rows] == [
            (name, i) for i, (name, _) in enumerate(KNOWN_TYPES)
        ] + [("Custom icon reuse", 100)]
        assert {
            row.id: row.model_dump() for row in session.exec(select(Training)).all()
        } == training_before
        assert {
            model.__tablename__: len(session.exec(select(model)).all())
            for model in [User, ExternalIdentity, CanvasRoster, TrainingType]
        } == counts_before
        policy = rows[0]
        policy.display_order = 42
        session.add(policy)
        session.commit()
        policy_id = policy.id
    with empty_db.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(migration)
    with Session(empty_db) as session:
        assert session.get(TrainingType, policy_id).display_order == 42
        assert (
            session.execute(
                text(
                    "SELECT COUNT(*) FROM pg_constraint WHERE conrelid='training_types'::regclass AND conname='training_type_display_order_nonnegative'"
                )
            ).scalar_one()
            == 1
        )


def test_today_activity_filters_entry_in_lab_day_and_preserves_both_dst_times(
    candidate, monkeypatch
):
    from app.routes import kiosk

    fixed_now = datetime(2026, 11, 2, 4, 59, 59, 500000, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now.astimezone(tz) if tz else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(kiosk, "datetime", Clock)
    member = candidate["users"]["member"]
    starts = [
        datetime(2026, 11, 1, 4, tzinfo=UTC),
        datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
        datetime(2026, 11, 2, 4, 59, 59, tzinfo=UTC),
    ]
    ends = [
        datetime(2026, 11, 1, 4, 10, tzinfo=UTC),
        datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
        None,
    ]
    with Session(candidate["engine"]) as session:
        session.add_all(
            [
                Visit(user_id=member, enter_time=start, exit_time=end)
                for start, end in zip(starts, ends, strict=True)
            ]
        )
        session.add_all(
            [
                Visit(
                    user_id=member,
                    enter_time=datetime(2026, 11, 1, 3, 59, 59, tzinfo=UTC),
                    exit_time=datetime(2026, 11, 1, 5, tzinfo=UTC),
                ),
                Visit(
                    user_id=member,
                    enter_time=datetime(2026, 11, 2, 5, tzinfo=UTC),
                    exit_time=datetime(2026, 11, 2, 5, 1, tzinfo=UTC),
                ),
            ]
        )
        session.commit()
    response = candidate["client"].get("/api/kiosk/state")
    assert response.status_code == 200, response.text
    recent = response.json()["recent_activity"]
    assert len(recent) == 3
    assert [datetime.fromisoformat(row["enter_time"]) for row in recent] == list(reversed(starts))
    assert [
        datetime.fromisoformat(row["exit_time"]) if row["exit_time"] else None for row in recent
    ] == list(reversed(ends))
    assert (
        recent[0]["action"] == "signed_in" and recent[0]["occurred_at"] == recent[0]["enter_time"]
    )
    assert (
        recent[1]["action"] == "signed_out" and recent[1]["occurred_at"] == recent[1]["exit_time"]
    )
    # More than ten visits: preserve legacy latest COALESCE(exit,entry) order,
    # including an early entry that was signed out much later in the day.
    with Session(candidate["engine"]) as session:
        base = datetime(2026, 11, 1, 8, tzinfo=UTC)
        late_exit = fixed_now - timedelta(microseconds=100000)
        for i in range(12):
            entered = base + timedelta(minutes=i * 5)
            session.add(
                Visit(
                    user_id=member,
                    enter_time=entered,
                    exit_time=late_exit if i == 0 else entered + timedelta(minutes=1),
                )
            )
        session.commit()
    recent = candidate["client"].get("/api/kiosk/state").json()["recent_activity"]
    assert len(recent) == 10
    assert datetime.fromisoformat(recent[0]["enter_time"]) == base
    assert datetime.fromisoformat(recent[0]["exit_time"]) == late_exit
    times = [datetime.fromisoformat(row["occurred_at"]) for row in recent]
    assert times == sorted(times, reverse=True)
