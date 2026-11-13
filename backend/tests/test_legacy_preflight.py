"""Synthetic migration anomalies from the read-only November 10 Zund inventory."""

import copy
import json
import os
import stat
from uuid import uuid4

import pytest

from app import legacy_preflight as legacy

MAPPINGS = {"Policies and Procedures": "2839627", "Orientation": "2633706"}


def snapshot():
    user = {
        "niner_id": 800000001,
        "canvas_id": 101,
        "first_name": "Synthetic",
        "last_name": "Visitor",
        "email": "synthetic@charlotte.edu",
        "is_active": True,
        "is_staff": True,
        "is_superuser": True,
        "user_picture": "",
        "keyholder_priority": -10,
        "space_level": 100,
        "credential_format": "pbkdf2_sha256",
    }
    return {
        "format": legacy.FORMAT,
        "captured_at": "2026-11-10T12:00:00-05:00",
        "tables": {
            "users_spaceuser": [user],
            "tools_and_trainings_trainingcategory": [
                {"id": 1, "name": "Policies and Procedures", "canvas_id": 556178, "user_url": None},
                {"id": 2, "name": "Zund", "canvas_id": None, "user_url": None},
                {"id": 3, "name": "Shopbot", "canvas_id": None, "user_url": None},
            ],
            "tools_and_trainings_training": [
                {
                    "id": 1,
                    "training_level": 100,
                    "completed_on": "2026-11-01T10:00:00-05:00",
                    "user_id": user["niner_id"],
                    "category_id": 2,
                    "certifier_id": user["niner_id"],
                }
            ],
            "visit_tracking_visit": [
                {
                    "id": 1,
                    "enter_time": "2026-11-01T01:30:00-04:00",
                    "exit_time": "2026-11-01T01:30:00-05:00",
                    "still_in_the_space": False,
                    "user_id": user["niner_id"],
                    "forgot_to_signout": None,
                }
            ],
            "users_keyholderhistory": [
                {
                    "id": 1,
                    "start_time": "2026-11-01T01:30:00-04:00",
                    "exit_time": "2026-11-01T01:30:00-05:00",
                    "keyholder_id": user["niner_id"],
                }
            ],
        },
    }


def issues(report):
    return {f["code"]: f for f in report["findings"]}


def test_preflight_is_nonmutating_and_preserves_null_flag_metrics_across_dst():
    data = snapshot()
    original = copy.deepcopy(data)
    report = legacy.inspect_export(data, MAPPINGS)
    assert data == original
    assert report["structural_checks_passed"]
    assert not report["ready_for_import"] and not report["apply_supported"]
    assert report["source_metrics"] == {
        "closed_nonforgotten_visits": 1,
        "closed_nonforgotten_person_seconds": "3600.0",
    }
    assert report["normalizations"]["negative_priorities_to_minus_one"] == 1
    assert report["normalizations"]["null_forgot_flags_to_false"] == 1
    assert report["counts"]["training_types"] == 3  # Includes both non-Canvas categories.
    assert report["legacy_training_levels"] == {100: 1}
    assert report["legacy_space_levels"] == {100: 1}
    assert report["verified_assignment_proposals"] == [
        {"name": "Policies and Procedures", "canvas_assignment_id": "2839627"},
    ]
    assert issues(report)["legacy_canvas_id_differs_from_verified_assignment"]["count"] == 1
    assert "training_provenance_requires_approval" in issues(report)
    assert "application_role_mapping_requires_approval" in issues(report)
    assert "credential_migration_requires_approval" in issues(report)
    encoded = json.dumps(report)
    for private in ["Synthetic", "Visitor", "synthetic@charlotte.edu", "800000001"]:
        assert private not in encoded


def test_duplicate_canvas_id_blocks_without_selecting_or_merging_an_owner():
    data = snapshot()
    other = dict(data["tables"]["users_spaceuser"][0], niner_id=800000002)
    data["tables"]["users_spaceuser"].append(other)
    report = legacy.inspect_export(data, MAPPINGS)
    assert report["counts"]["users"] == 2
    assert issues(report)["ambiguous_canvas_ownership"] == {
        "severity": "blocker",
        "code": "ambiguous_canvas_ownership",
        "count": 1,
    }
    assert not report["structural_checks_passed"]
    assert other["canvas_id"] == 101


@pytest.mark.parametrize(
    "mutate,code",
    [
        (
            lambda d: d["tables"]["visit_tracking_visit"][0].update(still_in_the_space=True),
            "visit_occupancy_flag_conflicts_with_timestamp",
        ),
        (
            lambda d: d["tables"]["visit_tracking_visit"][0].update(
                exit_time="2026-10-31T00:00:00+00:00"
            ),
            "negative_visit_duration",
        ),
        (
            lambda d: d["tables"]["visit_tracking_visit"][0].update(
                enter_time="2026-11-01T01:00:00"
            ),
            "invalid_or_naive_visit_timestamp",
        ),
        (
            lambda d: d["tables"]["visit_tracking_visit"][0].update(user_id=800000099),
            "visit_missing_user",
        ),
        (lambda d: d["tables"]["users_spaceuser"][0].update(space_level=15), "unknown_space_level"),
        (
            lambda d: d["tables"]["tools_and_trainings_training"][0].update(category_id=99),
            "training_missing_category",
        ),
        (
            lambda d: d["tables"]["tools_and_trainings_training"][0].update(certifier_id=800000099),
            "training_missing_certifier",
        ),
        (
            lambda d: d["tables"]["tools_and_trainings_training"][0].update(training_level=15),
            "unknown_legacy_training_level",
        ),
        (
            lambda d: d["tables"]["users_keyholderhistory"][0].update(exit_time=None),
            "active_keyholder_has_no_open_visit",
        ),
    ],
)
def test_conflicts_are_reported_without_guessing_repairs(mutate, code):
    data = snapshot()
    mutate(data)
    before = copy.deepcopy(data)
    report = legacy.inspect_export(data, MAPPINGS)
    assert code in issues(report)
    assert not report["structural_checks_passed"]
    assert data == before


def test_overlapping_and_multiple_open_visits_and_shifts_are_blocked():
    data = snapshot()
    table = data["tables"]["visit_tracking_visit"]
    table.extend(
        [
            dict(table[0], id=2, exit_time=None, still_in_the_space=True),
            dict(table[0], id=3, exit_time=None, still_in_the_space=True),
        ]
    )
    shifts = data["tables"]["users_keyholderhistory"]
    shifts[0]["exit_time"] = None
    shifts.append(dict(shifts[0], id=2))
    report = legacy.inspect_export(data, MAPPINGS)
    assert {
        "multiple_open_visits",
        "overlapping_visit_intervals",
        "multiple_open_keyholder_shifts",
    } <= issues(report).keys()


def test_adjacent_visits_and_historical_duplicate_awards_are_not_deduplicated():
    data = snapshot()
    visits = data["tables"]["visit_tracking_visit"]
    visits.append(
        dict(
            visits[0],
            id=2,
            enter_time=visits[0]["exit_time"],
            exit_time="2026-11-01T02:30:00-05:00",
            forgot_to_signout=True,
        )
    )
    visits.append(
        dict(
            visits[0],
            id=3,
            enter_time="2026-11-01T01:45:00-04:00",
            exit_time="2026-11-01T01:45:00-04:00",
            forgot_to_signout=True,
        )
    )
    awards = data["tables"]["tools_and_trainings_training"]
    awards.append(dict(awards[0], id=2, training_level=0))
    report = legacy.inspect_export(data, MAPPINGS)
    assert report["structural_checks_passed"]
    assert report["counts"]["trainings"] == 2
    assert issues(report)["multiple_historical_awards_must_be_preserved"]["count"] == 1
    assert report["source_metrics"]["closed_nonforgotten_visits"] == 1


def test_no_assignment_id_is_guessed_from_legacy_quiz_id():
    report = legacy.inspect_export(snapshot())
    assert not report["structural_checks_passed"]
    assert "unverified_canvas_assignment_mapping" in issues(report)
    assert report["verified_assignment_proposals"] == []


def test_source_exceptions_warn_but_are_not_rewritten_to_fit_registration():
    data = snapshot()
    user = data["tables"]["users_spaceuser"][0]
    user.update(email="ALUMNI@example.org", user_picture="private/photo.jpg")
    report = legacy.inspect_export(data, MAPPINGS)
    assert "legacy_email_outside_current_registration_policy" in issues(report)
    assert "avatar_requires_private_media_transfer" in issues(report)
    assert user["email"] == "ALUMNI@example.org"
    assert "private/photo.jpg" not in json.dumps(report)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["tables"]["users_spaceuser"][0].update(password="private-hash"),
        lambda d: d["tables"]["users_spaceuser"][0].update(niner_id="private-identifier"),
        lambda d: d["tables"]["tools_and_trainings_training"][0].update(user_id=[800000001]),
        lambda d: d.update(captured_at="2026-11-10T12:00:00"),
        lambda d: d["tables"].pop("visit_tracking_visit"),
    ],
)
def test_wrong_or_secret_bearing_input_is_rejected_without_echo(mutate):
    data = snapshot()
    mutate(data)
    with pytest.raises(legacy.PreflightError) as error:
        legacy.inspect_export(data)
    assert "private-" not in str(error.value)


def test_private_outputs_never_overwrite_or_follow_a_symlink(tmp_path):
    output = tmp_path / "export.json"
    legacy.private_json(output, snapshot())
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        legacy.private_json(output, {})
    link = tmp_path / "link.json"
    link.symlink_to(output)
    with pytest.raises(FileExistsError):
        legacy.private_json(link, {})
    assert output.read_bytes() == before


def test_inspection_cli_cannot_connect_to_any_database_and_has_distinct_exit_codes(
    tmp_path, monkeypatch, capsys
):
    import psycopg

    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda *a, **kw: pytest.fail("Offline inspection connected to PostgreSQL"),
    )
    source, mapping = tmp_path / "source.json", tmp_path / "mapping.json"
    source.write_text(json.dumps(snapshot()))
    mapping.write_text(json.dumps(MAPPINGS))
    assert legacy.main(["inspect", "--input", str(source), "--canvas-mappings", str(mapping)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert not report["ready_for_import"]
    assert legacy.main(["inspect", "--input", str(source)]) == 2
    capsys.readouterr()
    source.write_text('{"private": BROKEN-SECRET}')
    assert legacy.main(["inspect", "--input", str(source)]) == 1
    assert "BROKEN-SECRET" not in capsys.readouterr().err


def test_export_failure_does_not_echo_connection_credentials(tmp_path, monkeypatch, capsys):
    def fail(dsn):
        raise ValueError(dsn)

    monkeypatch.setenv("SYNTHETIC_SOURCE_DSN", "postgresql://test:SECRET@fixture/test")
    monkeypatch.setattr(legacy, "export_legacy", fail)
    assert (
        legacy.main(
            [
                "export",
                "--source-dsn-env",
                "SYNTHETIC_SOURCE_DSN",
                "--output",
                str(tmp_path / "new.json"),
            ]
        )
        == 1
    )
    assert "SECRET" not in capsys.readouterr().err
    assert not (tmp_path / "new.json").exists()


@pytest.fixture
def source_database():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict

    dsn = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.skip("Set TEST_DATABASE_URL to disposable PostgreSQL")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    name = "sfl_legacy_preflight_" + uuid4().hex[:12]
    params = conninfo_to_dict(dsn)
    params["dbname"] = name
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with psycopg.connect(**params) as connection:
            for table, columns in legacy.COLUMNS.items():
                definitions = []
                for column in columns:
                    if column in {
                        "niner_id",
                        "id",
                        "canvas_id",
                        "keyholder_priority",
                        "space_level",
                        "training_level",
                        "user_id",
                        "category_id",
                        "certifier_id",
                        "keyholder_id",
                    }:
                        kind = "bigint"
                    elif column in {"completed_on", "enter_time", "exit_time", "start_time"}:
                        kind = "timestamptz"
                    elif column in {
                        "is_active",
                        "is_staff",
                        "is_superuser",
                        "still_in_the_space",
                        "forgot_to_signout",
                    }:
                        kind = "boolean"
                    else:
                        kind = "text"
                    definitions.append(sql.SQL("{} " + kind).format(sql.Identifier(column)))
                if table == "users_spaceuser":
                    definitions.append(sql.SQL("password text NOT NULL"))
                connection.execute(
                    sql.SQL("CREATE TABLE {} ({})").format(
                        sql.Identifier(table), sql.SQL(",").join(definitions)
                    )
                )
                for original in snapshot()["tables"][table]:
                    row = {
                        key: value for key, value in original.items() if key != "credential_format"
                    }
                    if table == "users_spaceuser":
                        row["password"] = "pbkdf2_sha256$100000$SYNTHETIC_SALT$SECRET_HASH_SENTINEL"
                    connection.execute(
                        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                            sql.Identifier(table),
                            sql.SQL(",").join(map(sql.Identifier, row)),
                            sql.SQL(",").join(sql.Placeholder() for _ in row),
                        ),
                        list(row.values()),
                    )
        yield psycopg.conninfo.make_conninfo(**params)
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.postgres
def test_real_export_is_read_only_consistent_and_excludes_hashes(source_database, monkeypatch):
    import psycopg

    real_connect = psycopg.connect
    observed = {
        "read_only": False,
        "repeatable_read": False,
        "write_rejected": False,
        "concurrent_update": False,
    }
    queries = []

    class Probe:
        def __init__(self, *args, **kwargs):
            self.connection = real_connect(*args, **kwargs)

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, query, *args, **kwargs):
            queries.append(query)
            if query == "SELECT transaction_timestamp() AS at":
                observed["read_only"] = (
                    self.connection.execute("SHOW transaction_read_only").fetchone()[
                        "transaction_read_only"
                    ]
                    == "on"
                )
                observed["repeatable_read"] = (
                    self.connection.execute("SHOW transaction_isolation").fetchone()[
                        "transaction_isolation"
                    ]
                    == "repeatable read"
                )
                self.connection.execute("SAVEPOINT readonly_probe")
                try:
                    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                        self.connection.execute(
                            "UPDATE users_spaceuser SET first_name='SHOULD_NOT_CHANGE'"
                        )
                    observed["write_rejected"] = True
                finally:
                    self.connection.execute("ROLLBACK TO SAVEPOINT readonly_probe")
            if 'FROM public."tools_and_trainings_trainingcategory"' in query:
                with real_connect(source_database, autocommit=True) as writer:
                    writer.execute("UPDATE users_spaceuser SET first_name='CHANGED_AFTER_SNAPSHOT'")
                    writer.execute(
                        "INSERT INTO visit_tracking_visit VALUES (99, '2026-11-10T10:00:00Z', '2026-11-10T11:00:00Z', false, 800000001, false)"
                    )
                observed["concurrent_update"] = True
            return self.connection.execute(query, *args, **kwargs)

    monkeypatch.setattr(psycopg, "connect", Probe)
    exported = legacy.export_legacy(source_database)
    assert all(observed.values())
    assert exported["tables"]["users_spaceuser"][0]["first_name"] == "Synthetic"
    assert len(exported["tables"]["visit_tracking_visit"]) == 1
    encoded = json.dumps(exported)
    assert "SECRET_HASH_SENTINEL" not in encoded and "SYNTHETIC_SALT" not in encoded
    assert '"password"' not in encoded
    assert exported["tables"]["users_spaceuser"][0]["credential_format"] == "pbkdf2_sha256"
    assert all(query.startswith(("SELECT", "BEGIN", "ROLLBACK")) for query in queries)
    assert legacy.inspect_export(exported, MAPPINGS)["structural_checks_passed"]


def test_unknown_credential_label_does_not_disclose_unexpected_private_values():
    data = snapshot()
    data["tables"]["users_spaceuser"][0]["credential_format"] = ["PRIVATE_SENTINEL"]
    report = legacy.inspect_export(data, MAPPINGS)
    assert report["credential_formats"] == {"unknown": 1}
    assert "PRIVATE_SENTINEL" not in json.dumps(report)
