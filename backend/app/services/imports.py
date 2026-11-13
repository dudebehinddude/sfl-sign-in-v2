"""Preview and atomically preregister CSV users without recording attendance."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import lab_lock
from app.events import audit, publish
from app.models import ExternalIdentity, SpaceLevel, User
from app.schemas import TapInput, UserCreate
from app.services.identity import add_student_identifier, canonical_email

MAX_CSV_BYTES = 1_000_000
MAX_CSV_ROWS = 2000
HEADER_ALIASES = {
    "identifier": "identifier",
    "student_id": "identifier",
    "niner_id": "identifier",
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "email_address": "email",
}
PRIVILEGED_HEADERS = {
    "roles",
    "role",
    "password",
    "password_hash",
    "is_superuser",
    "is_staff",
    "is_active",
    "active",
    "space_level",
    "keyholder_priority",
    "canvas_id",
    "user_id",
    "permissions",
}


@dataclass(frozen=True)
class ParsedRow:
    row_number: int
    identifier: str
    first_name: str
    last_name: str
    email: str | None
    error: str | None = None


def _header(value: str) -> str:
    return value.lstrip("\ufeff").strip().casefold().replace("-", "_").replace(" ", "_")


def _name_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def _parse(csv_text: str) -> tuple[list[ParsedRow], list[str]]:
    if not csv_text.strip() or len(csv_text.encode("utf-8")) > MAX_CSV_BYTES:
        raise HTTPException(422, "Supply a nonempty CSV file no larger than 1 MB")
    reader = csv.reader(io.StringIO(csv_text, newline=""), strict=True)
    try:
        original_headers = next(reader)
        headers = [_header(item) for item in original_headers]
        if not headers or any(not header for header in headers):
            raise HTTPException(422, "Every CSV column needs a header")
        if len(set(headers)) != len(headers):
            raise HTTPException(422, "CSV headers must be unique")
        if PRIVILEGED_HEADERS.intersection(headers):
            raise HTTPException(
                422,
                "CSV preregistration cannot assign access, credentials, roles, or external Canvas identities",
            )
        mapped = [HEADER_ALIASES.get(header) for header in headers]
        known = [header for header in mapped if header]
        if len(set(known)) != len(known):
            raise HTTPException(422, "Multiple CSV columns map to the same field")
        missing = {"identifier", "first_name", "last_name"} - set(known)
        if missing:
            raise HTTPException(422, "Missing CSV headers: " + ", ".join(sorted(missing)))
        ignored = [
            name.strip() for name, field in zip(original_headers, mapped, strict=True) if not field
        ]
        parsed: list[ParsedRow] = []
        for number, values in enumerate(reader, start=2):
            if not any(value.strip() for value in values):
                continue
            if len(parsed) >= MAX_CSV_ROWS:
                raise HTTPException(422, f"CSV imports are limited to {MAX_CSV_ROWS} users")
            if len(values) != len(headers):
                parsed.append(
                    ParsedRow(
                        number,
                        "",
                        "",
                        "",
                        None,
                        "Row has a different number of fields than its header",
                    )
                )
                continue
            data = {
                field: value.strip() for field, value in zip(mapped, values, strict=True) if field
            }
            identifier = data.get("identifier", "")
            first_name, last_name = data.get("first_name", ""), data.get("last_name", "")
            email = data.get("email") or None
            try:
                if any(
                    unicodedata.category(char) == "Cc"
                    for value in (first_name, last_name)
                    for char in value
                ):
                    raise ValueError("Names cannot contain control characters")
                identifier = TapInput(identifier=identifier).identifier
                item = UserCreate(
                    identifier=identifier, first_name=first_name, last_name=last_name, email=email
                )
                first_name, last_name = item.first_name, item.last_name
                email = canonical_email(str(item.email)) if item.email else None
                error = None
            except ValidationError as invalid:
                fields = sorted({str(issue["loc"][0]) for issue in invalid.errors()})
                error = "Invalid or missing " + ", ".join(fields)
            except ValueError as invalid:
                error = str(invalid)
            parsed.append(ParsedRow(number, identifier, first_name, last_name, email, error))
        if not parsed:
            raise HTTPException(422, "CSV contains no user rows")
        return parsed, ignored
    except (csv.Error, StopIteration, UnicodeError) as error:
        raise HTTPException(
            422, "CSV could not be parsed; check its header and quoted fields"
        ) from error


def _email_aliases(email: str) -> set[str]:
    aliases = {email}
    if email.endswith("@charlotte.edu"):
        aliases.add(email.removesuffix("@charlotte.edu") + "@uncc.edu")
    return aliases


def preview_users(session: Session, csv_text: str) -> dict[str, Any]:
    parsed, ignored = _parse(csv_text)
    valid = [row for row in parsed if not row.error]
    identifier_counts = Counter(row.identifier for row in valid)
    email_counts = Counter(row.email for row in valid if row.email)
    identifiers = set(identifier_counts)
    emails = set(email_counts)
    identities = (
        session.exec(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == "student_id",
                ExternalIdentity.issuer == "charlotte",
                ExternalIdentity.value.in_(identifiers),
            )
        ).all()
        if identifiers
        else []
    )
    by_identifier = {identity.value: identity for identity in identities}
    user_ids = {identity.user_id for identity in identities if identity.user_id}
    aliases = set().union(*(_email_aliases(email) for email in emails)) if emails else set()
    conditions = []
    if user_ids:
        conditions.append(User.id.in_(user_ids))
    if emails:
        conditions.append(User.email.in_(emails))
        conditions.append(func.lower(func.trim(User.email)).in_(aliases))
    users = session.exec(select(User).where(or_(*conditions))).all() if conditions else []
    by_user = {user.id: user for user in users}
    by_email: dict[str, list[User]] = defaultdict(list)
    for user in users:
        normalized = canonical_email(user.email)
        if normalized:
            by_email[normalized].append(user)
    results = []
    fingerprint_rows = []
    summary = {"total": len(parsed), "new": 0, "existing": 0, "conflict": 0, "invalid": 0}
    for row in parsed:
        status, message = "new", "Ready to preregister; attendance will not change"
        identity = by_identifier.get(row.identifier)
        user = by_user.get(identity.user_id) if identity and identity.user_id else None
        if row.error:
            status, message = "invalid", row.error
        elif identifier_counts[row.identifier] > 1:
            status, message = "conflict", "Identifier occurs more than once in this CSV"
        elif row.email and email_counts[row.email] > 1:
            status, message = (
                "conflict",
                "Email occurs more than once in this CSV; review the identities manually",
            )
        elif identity and not user:
            status, message = (
                "conflict",
                "Identifier already exists without an available user binding; review it manually",
            )
        elif user:
            names_match = _name_key(user.first_name) == _name_key(row.first_name) and _name_key(
                user.last_name
            ) == _name_key(row.last_name)
            email_matches = row.email is None or canonical_email(user.email) == row.email
            if names_match and email_matches:
                status = "existing"
                message = "Already registered; no fields or permissions will be changed"
                if not user.active:
                    message = (
                        "Already registered but inactive; import will not reactivate this account"
                    )
            else:
                status, message = (
                    "conflict",
                    "Identifier belongs to a different or incomplete profile; import will not overwrite it",
                )
        elif row.email and by_email.get(row.email):
            status, message = (
                "conflict",
                "Email already belongs to another local profile; import will not merge users",
            )
        summary[status] += 1
        results.append(
            {
                "row_number": row.row_number,
                "identifier": row.identifier,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "email": row.email,
                "status": status,
                "message": message,
                "existing_user_id": str(user.id) if user else None,
            }
        )
        fingerprint_rows.append(
            {
                **results[-1],
                "existing_updated_at": user.updated_at.isoformat() if user else None,
                "identity_id": str(identity.id) if identity else None,
                "email_matches": sorted(
                    (str(match.id), match.updated_at.isoformat())
                    for match in by_email.get(row.email or "", [])
                ),
            }
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "csv_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
                "rows": fingerprint_rows,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "fingerprint": fingerprint,
        "can_apply": not summary["invalid"] and not summary["conflict"],
        "summary": summary,
        "rows": results,
        "ignored_columns": ignored,
    }


def apply_users(
    session: Session, actor_id: UUID, csv_text: str, fingerprint: str, confirm: bool
) -> dict:
    if not confirm:
        raise HTTPException(400, "Confirm the preview before applying preregistration")
    # This is the same lock used by normal user creation and kiosk identity work.
    # No external calls are made while this bounded transaction owns the lock.
    lab_lock(session)
    parsed, _ = _parse(csv_text)
    identity_keys = sorted(
        {
            int.from_bytes(
                hashlib.sha256(("student_id:charlotte:" + row.identifier).encode()).digest()[:8],
                "big",
                signed=True,
            )
            for row in parsed
            if not row.error
        }
    )
    if identity_keys:
        session.execute(
            text(
                "SELECT pg_advisory_xact_lock(identity_key) FROM (SELECT unnest(CAST(:keys AS bigint[])) AS identity_key ORDER BY identity_key) ordered_keys"
            ),
            {"keys": identity_keys},
        )
    preview = preview_users(session, csv_text)
    if not hmac.compare_digest(preview["fingerprint"], fingerprint):
        raise HTTPException(
            409, "The CSV or existing user data changed. Preview again before applying."
        )
    if not preview["can_apply"]:
        raise HTTPException(
            409, "Resolve every invalid or conflicting row before applying. No users were created."
        )
    created: list[tuple[User, str]] = []
    for row in preview["rows"]:
        if row["status"] != "new":
            continue
        user = User(
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=canonical_email(row["email"]),
            space_level=SpaceLevel.MEMBER,
            keyholder_priority=-1,
        )
        session.add(user)
        created.append((user, row["identifier"]))
    try:
        session.flush()
        for user, identifier in created:
            add_student_identifier(session, user, identifier)
            audit(session, "user.preregistered", "users", user.id, actor_id, source="csv_import")
        audit(
            session,
            "users.imported",
            "users",
            actor_id=actor_id,
            created=len(created),
            skipped_existing=preview["summary"]["existing"],
            fingerprint=fingerprint,
        )
        if created:
            publish(session, "users")
        created_user_ids = [str(user.id) for user, _ in created]
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            409, "User data changed during import. Nothing was imported; preview again."
        ) from error
    return {
        "created": len(created),
        "skipped_existing": preview["summary"]["existing"],
        "created_user_ids": created_user_ids,
        "fingerprint": fingerprint,
        "message": "Preregistration complete. No visits, labels, invitations, roles, or passwords were created.",
    }
