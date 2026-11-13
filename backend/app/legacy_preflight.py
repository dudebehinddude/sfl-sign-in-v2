"""Read-only legacy export and offline checks. This module cannot import into v2."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

FORMAT = "sfl-legacy-export-v1"
# Fixed projections deliberately omit hashes, sessions, reset links and job payloads.
COLUMNS = {
    "users_spaceuser": (
        "niner_id",
        "canvas_id",
        "first_name",
        "last_name",
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
        "user_picture",
        "keyholder_priority",
        "space_level",
    ),
    "tools_and_trainings_trainingcategory": ("id", "name", "canvas_id", "user_url"),
    "tools_and_trainings_training": (
        "id",
        "training_level",
        "completed_on",
        "user_id",
        "category_id",
        "certifier_id",
    ),
    "visit_tracking_visit": (
        "id",
        "enter_time",
        "exit_time",
        "still_in_the_space",
        "user_id",
        "forgot_to_signout",
    ),
    "users_keyholderhistory": ("id", "start_time", "exit_time", "keyholder_id"),
}
SPACE_LEVELS = {0: 0, 30: 1, 70: 2, 100: 3}
TRAINING_LEVELS = {0, 30, 70, 100}


class PreflightError(ValueError):
    """Safe error messages never include source records or connection credentials."""


def private_json(path: Path, value: dict) -> None:
    """Create a private new file; never overwrite a source export or follow a symlink."""
    data = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def export_legacy(dsn: str) -> dict:
    """One consistent source snapshot, enforced read-only by PostgreSQL."""
    import psycopg
    from psycopg.rows import dict_row

    tables = {}
    with psycopg.connect(
        dsn,
        autocommit=True,
        row_factory=dict_row,
        connect_timeout=10,
        options="-c default_transaction_read_only=on -c statement_timeout=15000 -c TimeZone=UTC",
    ) as connection:
        connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        try:
            captured_at = connection.execute("SELECT transaction_timestamp() AS at").fetchone()[
                "at"
            ]
            for table, columns in COLUMNS.items():
                projection = ", ".join(f'"{column}"' for column in columns)
                if table == "users_spaceuser":
                    # Only an algorithm label is exported; never a hash or hash fragment.
                    projection += """, CASE
                        WHEN password LIKE '!%' THEN 'unusable'
                        WHEN split_part(password, '$', 1) IN
                             ('pbkdf2_sha256','pbkdf2_sha1','argon2','bcrypt_sha256','scrypt')
                        THEN split_part(password, '$', 1)
                        ELSE 'unknown' END AS credential_format"""
                order = "niner_id" if table == "users_spaceuser" else "id"
                rows = connection.execute(
                    f'SELECT {projection} FROM public."{table}" ORDER BY "{order}"'
                ).fetchall()
                tables[table] = [
                    {
                        key: value.isoformat() if isinstance(value, datetime) else value
                        for key, value in row.items()
                    }
                    for row in rows
                ]
        finally:
            connection.execute("ROLLBACK")
    return {"format": FORMAT, "captured_at": captured_at.isoformat(), "tables": tables}


def _instant(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError
    return parsed.astimezone(UTC)


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_export(data: Any) -> dict[str, list[dict]]:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise PreflightError(
            "Expected an sfl-legacy-export-v1 JSON export, not SQL or a Django fixture"
        )
    try:
        _instant(data.get("captured_at"))
    except ValueError:
        raise PreflightError(
            "Export captured_at must be a timestamp with an explicit offset"
        ) from None
    tables = data.get("tables")
    if not isinstance(tables, dict) or set(tables) != set(COLUMNS):
        raise PreflightError("Export must contain exactly the five documented legacy domain tables")
    for table, columns in COLUMNS.items():
        rows = tables[table]
        if not isinstance(rows, list):
            raise PreflightError(f"{table} must contain a list of rows")
        allowed = set(columns) | ({"credential_format"} if table == "users_spaceuser" else set())
        for row in rows:
            if not isinstance(row, dict) or not set(columns) <= row.keys() or row.keys() - allowed:
                raise PreflightError(
                    f"{table} has missing or unexpected fields; secret fields are forbidden"
                )
            pk = "niner_id" if table == "users_spaceuser" else "id"
            if not _int(row[pk]):
                raise PreflightError(f"{table} primary keys must be integers")
            integer_columns = {
                "canvas_id",
                "keyholder_priority",
                "space_level",
                "training_level",
                "user_id",
                "category_id",
                "certifier_id",
                "keyholder_id",
            }
            for column in set(columns) & integer_columns:
                if row[column] is None and column == "canvas_id":
                    continue
                if not _int(row[column]):
                    raise PreflightError(f"{table} has an invalid integer field")
    return tables


def inspect_export(data: dict, mappings: dict[str, str] | None = None) -> dict:
    tables = validate_export(data)
    users = tables["users_spaceuser"]
    categories = tables["tools_and_trainings_trainingcategory"]
    trainings = tables["tools_and_trainings_training"]
    visits = tables["visit_tracking_visit"]
    shifts = tables["users_keyholderhistory"]
    counts = {
        "users": len(users),
        "training_types": len(categories),
        "trainings": len(trainings),
        "visits": len(visits),
        "keyholder_shifts": len(shifts),
    }
    issues: Counter[tuple[str, str]] = Counter()

    def flag(code: str, severity: str = "blocker", count: int = 1):
        if count:
            issues[severity, code] += count

    # Reports omit personal names, emails, identifiers, media paths and hashes.
    # Training definition names are included only in assignment mapping proposals.
    for table, rows in tables.items():
        pk = "niner_id" if table == "users_spaceuser" else "id"
        flag(
            "duplicate_primary_key:" + table,
            count=sum(n > 1 for n in Counter(r[pk] for r in rows).values()),
        )
    user_ids = {row["niner_id"] for row in users}
    category_ids = {row["id"] for row in categories}
    user_by_id = {row["niner_id"]: row for row in users}
    canvas_ids: Counter[int] = Counter()
    access_levels: Counter[int] = Counter()
    credential_formats: Counter[str] = Counter()
    negative_priorities = null_forgot = 0
    for row in users:
        level, priority = row["space_level"], row["keyholder_priority"]
        if not _int(level) or level not in SPACE_LEVELS:
            flag("unknown_space_level")
        else:
            access_levels[level] += 1
        if not _int(priority):
            flag("invalid_keyholder_priority")
        else:
            negative_priorities += priority < 0
        if not re.fullmatch(r"80[0-9]{7}", str(row["niner_id"])):
            flag("nonstandard_student_id", "warning")
        if not re.fullmatch(r"[0-9]{9}", str(row["niner_id"])):
            flag("student_id_requires_explicit_replacement")
        if row["canvas_id"] is not None:
            if not _int(row["canvas_id"]) or row["canvas_id"] <= 0:
                flag("invalid_canvas_id")
            else:
                canvas_ids[row["canvas_id"]] += 1
        for key in ("first_name", "last_name"):
            if row[key] is not None and (not isinstance(row[key], str) or len(row[key]) > 100):
                flag("name_exceeds_candidate_limits")
        for key in ("is_active", "is_staff", "is_superuser"):
            if not isinstance(row[key], bool):
                flag("invalid_user_boolean")
        email = row["email"]
        if email is not None and (not isinstance(email, str) or len(email) > 254):
            flag("invalid_email_storage")
        elif (
            email
            and email.strip()
            and not re.fullmatch(r"[^@\s]+@(charlotte|uncc)\.edu", email.strip(), re.I)
        ):
            flag("legacy_email_outside_current_registration_policy", "warning")
        if row["user_picture"]:
            flag("avatar_requires_private_media_transfer", "warning")
        credential_format = row.get("credential_format", "not_exported")
        # Keep even malformed/private input out of aggregate labels.
        if not isinstance(credential_format, str) or credential_format not in {
            "unusable",
            "unknown",
            "not_exported",
            "pbkdf2_sha256",
            "pbkdf2_sha1",
            "argon2",
            "bcrypt_sha256",
            "scrypt",
        }:
            credential_format = "unknown"
        credential_formats[credential_format] += 1
    flag("ambiguous_canvas_ownership", count=sum(n > 1 for n in canvas_ids.values()))
    flag(
        "application_role_mapping_requires_approval",
        "decision",
        sum(r["is_staff"] is True or r["is_superuser"] is True for r in users),
    )
    flag(
        "credential_migration_requires_approval",
        "decision",
        sum(n for name, n in credential_formats.items() if name != "unusable"),
    )

    names: Counter[str] = Counter()
    mapping_proposals = []
    for row in categories:
        name = row["name"]
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            flag("invalid_training_type_name")
            continue
        names[name] += 1
        mapped = (mappings or {}).get(name)
        if mapped is not None:
            if str(row["canvas_id"]) != mapped:
                flag("legacy_canvas_id_differs_from_verified_assignment", "warning")
            mapping_proposals.append({"name": name, "canvas_assignment_id": mapped})
        elif row["canvas_id"] is not None:
            flag("unverified_canvas_assignment_mapping")
    flag("duplicate_training_type_name_requires_mapping", count=sum(n > 1 for n in names.values()))

    open_visits: Counter[int] = Counter()
    intervals: dict[int, list[tuple[datetime, datetime | None]]] = defaultdict(list)
    reliable_seconds = Decimal(0)
    reliable_count = 0
    for row in visits:
        if row["user_id"] not in user_ids:
            flag("visit_missing_user")
        if not isinstance(row["still_in_the_space"], bool):
            flag("invalid_visit_boolean")
        if row["forgot_to_signout"] is None:
            null_forgot += 1
        elif not isinstance(row["forgot_to_signout"], bool):
            flag("invalid_forgotten_flag")
        try:
            start = _instant(row["enter_time"])
            end = None if row["exit_time"] is None else _instant(row["exit_time"])
        except ValueError:
            flag("invalid_or_naive_visit_timestamp")
            continue
        if end is not None and end < start:
            flag("negative_visit_duration")
            continue
        if row["still_in_the_space"] is not (end is None):
            flag("visit_occupancy_flag_conflicts_with_timestamp")
        if end is None:
            open_visits[row["user_id"]] += 1
        intervals[row["user_id"]].append((start, end))
        if (
            end is not None
            and row["still_in_the_space"] is False
            and row["forgot_to_signout"] is not True
        ):
            reliable_seconds += Decimal(str((end - start).total_seconds()))
            reliable_count += 1
    flag("multiple_open_visits", count=sum(n > 1 for n in open_visits.values()))
    for spans in intervals.values():
        previous_end = None
        for start, end in sorted(spans, key=lambda pair: pair[0]):
            if end == start:
                continue
            if previous_end is not None and start < previous_end:
                flag("overlapping_visit_intervals")
            previous_end = max(previous_end or start, end or datetime.max.replace(tzinfo=UTC))

    open_shifts = 0
    for row in shifts:
        user = user_by_id.get(row["keyholder_id"])
        if user is None:
            flag("keyholder_shift_missing_user")
        try:
            start = _instant(row["start_time"])
            end = None if row["exit_time"] is None else _instant(row["exit_time"])
        except ValueError:
            flag("invalid_or_naive_shift_timestamp")
            continue
        if end is not None and end < start:
            flag("negative_shift_duration")
        if end is None:
            open_shifts += 1
            if not open_visits[row["keyholder_id"]]:
                flag("active_keyholder_has_no_open_visit")
            if user and (user["is_active"] is not True or user["space_level"] not in {30, 70, 100}):
                flag("active_keyholder_ineligible")
    flag("multiple_open_keyholder_shifts", count=max(0, open_shifts - 1))

    award_pairs: Counter[tuple[int, int]] = Counter()
    training_levels: Counter[int] = Counter()
    for row in trainings:
        if row["user_id"] not in user_ids:
            flag("training_missing_user")
        if row["certifier_id"] not in user_ids:
            flag("training_missing_certifier")
        if row["category_id"] not in category_ids:
            flag("training_missing_category")
        if not _int(row["training_level"]) or row["training_level"] not in TRAINING_LEVELS:
            flag("unknown_legacy_training_level")
        else:
            training_levels[row["training_level"]] += 1
        try:
            _instant(row["completed_on"])
        except ValueError:
            flag("invalid_or_naive_training_timestamp")
        award_pairs[row["user_id"], row["category_id"]] += 1
    flag("training_provenance_requires_approval", "decision", len(trainings))
    flag(
        "multiple_historical_awards_must_be_preserved",
        "warning",
        sum(n > 1 for n in award_pairs.values()),
    )
    findings = [
        {"severity": severity, "code": code, "count": count}
        for (severity, code), count in sorted(issues.items())
    ]
    return {
        "format": "sfl-legacy-preflight-v1",
        "source_captured_at": data["captured_at"],
        "apply_supported": False,
        "ready_for_import": False,
        "structural_checks_passed": not any(f["severity"] == "blocker" for f in findings),
        "counts": counts,
        "findings": findings,
        "normalizations": {
            "negative_priorities_to_minus_one": negative_priorities,
            "null_forgot_flags_to_false": null_forgot,
            "space_level_mapping": SPACE_LEVELS,
        },
        "credential_formats": dict(sorted(credential_formats.items())),
        "legacy_space_levels": dict(sorted(access_levels.items())),
        "legacy_training_levels": dict(sorted(training_levels.items())),
        "verified_assignment_proposals": mapping_proposals,
        "source_metrics": {
            "closed_nonforgotten_visits": reliable_count,
            "closed_nonforgotten_person_seconds": str(reliable_seconds),
        },
        "limitations": [
            "No import or target database connection is implemented",
            "No passwords, sessions, private media or source jobs were exported",
            "created_at/updated_at cannot be reconstructed from absent legacy fields",
            "Training provenance and application roles require an explicit migration policy",
        ],
    }


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise PreflightError(
            "Could not read the JSON file; no source content was printed"
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    exporter = commands.add_parser(
        "export", help="Read-only source export; output contains personal data"
    )
    exporter.add_argument(
        "--source-dsn-env",
        required=True,
        help="Environment variable containing the source PostgreSQL DSN",
    )
    exporter.add_argument(
        "--output", type=Path, required=True, help="New private JSON file, never overwritten"
    )
    inspector = commands.add_parser(
        "inspect", help="Offline aggregate checks; never connects to a database"
    )
    inspector.add_argument("--input", type=Path, required=True)
    inspector.add_argument("--canvas-mappings", type=Path)
    inspector.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            dsn = os.environ.get(args.source_dsn_env)
            if not dsn:
                raise PreflightError("The explicit source DSN environment variable is not set")
            try:
                data = export_legacy(dsn)
            except Exception:
                raise PreflightError(
                    "Read-only source export failed; connection details and source data were not printed"
                ) from None
            private_json(args.output, data)
            print(
                json.dumps({"exported": True, "personal_data_file": True, "source_modified": False})
            )
            return 0
        mappings = load_json(args.canvas_mappings) if args.canvas_mappings else None
        if mappings is not None and (
            not isinstance(mappings, dict)
            or not all(
                isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[0-9]+", v)
                for k, v in mappings.items()
            )
        ):
            raise PreflightError(
                "Canvas mappings must be training names mapped to string assignment IDs"
            )
        report = inspect_export(load_json(args.input), mappings)
        if args.output:
            private_json(args.output, report)
        else:
            print(json.dumps(report, indent=2))
        return 2 if not report["structural_checks_passed"] else 0
    except (PreflightError, OSError) as error:
        # File paths and OS/driver exceptions can embed private account/DSN data.
        print(
            str(error)
            if isinstance(error, PreflightError)
            else "Could not create a new private output file",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
