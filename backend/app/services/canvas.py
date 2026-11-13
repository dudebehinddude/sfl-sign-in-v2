"""Canvas source adapter and local cache binding. No network I/O occurs during taps.

Canvas pagination/submission contracts:
https://developerdocs.instructure.com/services/canvas/basics/file.pagination
https://developerdocs.instructure.com/services/canvas/resources/submissions
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import or_, text
from sqlmodel import Session, select

from ..config import Settings, get_settings
from ..models import (
    AuditEvent,
    CanvasRoster,
    ExternalIdentity,
    Training,
    TrainingType,
    User,
    training_type_order,
    utcnow,
)
from .identity import canonical_email

QUEUE_LOCK = 73190518
IDENTITY_LOCK = 73190519


class CanvasError(Exception):
    """Sanitized integration failure; never contains response bodies or API tokens."""


class CanvasSyncInProgress(CanvasError):
    """A manual request cannot start a second fetch while one is active."""


def canvas_issuer(settings: Settings | None = None) -> str:
    parsed = urlsplit((settings or get_settings()).canvas_base_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise CanvasError("Canvas base URL must be an HTTP(S) origin without credentials or a path")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _opaque_id(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise CanvasError(f"Canvas record has an invalid {field}")
    result = str(value).strip()
    if not result or len(result) > 128 or any(c.isspace() for c in result):
        raise CanvasError(f"Canvas record has an invalid {field}")
    return result


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CanvasError("Canvas result has an invalid completion timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CanvasError("Canvas result has an invalid completion timestamp") from exc
    if result.tzinfo is None:
        raise CanvasError("Canvas completion timestamp must include a timezone")
    return result.astimezone(UTC)


def _score(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int, str)):
        raise CanvasError("Canvas result has an invalid score")
    try:
        result = float(value)
    except ValueError as exc:
        raise CanvasError("Canvas result has an invalid score") from exc
    if not math.isfinite(result):
        raise CanvasError("Canvas result has an invalid score")
    return result


@dataclass(frozen=True)
class TrainingSpec:
    training_type_id: UUID
    assignment_id: str
    minimum_score: float | None
    active: bool
    issuer: str
    course_id: str

    @classmethod
    def from_model(cls, training: TrainingType, settings: Settings | None = None) -> TrainingSpec:
        settings = settings or get_settings()
        return cls(
            training.id,
            training.canvas_assignment_id or "",
            training.canvas_minimum_score,
            training.active,
            canvas_issuer(settings),
            settings.canvas_course_id,
        )

    def validate(self) -> None:
        _opaque_id(self.course_id, "course ID")
        _opaque_id(self.assignment_id, "assignment ID")
        if self.minimum_score is not None:
            _score(self.minimum_score)

    @property
    def fingerprint(self) -> str:
        values = [
            str(self.training_type_id),
            self.assignment_id,
            self.minimum_score,
            self.active,
            self.issuer,
            self.course_id,
        ]
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class RosterRecord:
    canvas_id: str
    email: str | None
    display_name: str


@dataclass(frozen=True)
class ResultRecord:
    canvas_id: str
    training: TrainingSpec
    submission_id: str
    attempt: int
    workflow_status: str
    score: float | None
    grade: str | None
    passed: bool
    completed_at: datetime | None


@dataclass(frozen=True)
class CanvasSnapshot:
    issuer: str
    trainings: tuple[TrainingSpec, ...]
    roster: tuple[RosterRecord, ...]
    results: tuple[ResultRecord, ...]
    skipped_results: int = 0


@dataclass(frozen=True)
class QuizRecord:
    id: str  # Assignment API ID, including when the assignment represents a quiz.
    title: str
    points_possible: float | None


class CanvasClient:
    """Bounded authenticated GETs, following only same-origin Canvas pagination.

    Pass an httpx.Client with MockTransport in tests. Source errors fail the whole
    fetch so existing cache/grants are not cleared by a partial or invalid page.
    """

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None):
        self.settings = settings
        self.issuer = canvas_issuer(settings)
        self._owned_client = http_client is None
        self.client = http_client or httpx.Client(timeout=20, follow_redirects=False)

    def close(self) -> None:
        if self._owned_client:
            self.client.close()

    def _pages(self, path: str, progress, *, collection: str | None = None) -> list[dict]:
        url = f"{self.issuer}/api/v1/{path}"
        seen: set[str] = set()
        records: list[dict] = []
        for _ in range(1000):
            parsed = urlsplit(url)
            if (
                f"{parsed.scheme}://{parsed.netloc}" != self.issuer
                or not parsed.path.startswith("/api/v1/")
                or parsed.username
                or parsed.password
            ):
                raise CanvasError("Canvas pagination points outside the configured API origin")
            if url in seen:
                raise CanvasError("Canvas pagination repeated a page")
            seen.add(url)
            progress()
            try:
                response = self.client.get(
                    url, headers={"Authorization": f"Bearer {self.settings.canvas_api_token}"}
                )
            except httpx.HTTPError as exc:
                raise CanvasError("Canvas HTTP connection failed") from exc
            if response.status_code != 200:
                raise CanvasError(
                    f"Canvas returned HTTP {response.status_code}; cached records were retained"
                )
            try:
                body = response.json()
            except ValueError as exc:
                raise CanvasError("Canvas returned invalid JSON") from exc
            if collection:
                body = body.get(collection) if isinstance(body, dict) else None
            if not isinstance(body, list) or any(not isinstance(item, dict) for item in body):
                raise CanvasError("Canvas returned an unexpected collection shape")
            records.extend(body)
            progress()
            next_url = response.links.get("next", {}).get("url")
            if not next_url:
                return records
            url = str(response.url.join(next_url))
        raise CanvasError("Canvas pagination exceeded the configured safety bound")

    def fetch_quizzes(self) -> tuple[QuizRecord, ...]:
        """One assignment catalog serves both classic and LTI quiz dropdowns.

        https://developerdocs.instructure.com/services/canvas/resources/assignments
        No separate quiz submission adapter or ambiguous native quiz IDs.
        """
        if not self.settings.canvas_configured:
            raise CanvasError("Canvas is not configured")
        course = quote(_opaque_id(self.settings.canvas_course_id, "course ID"), safe="")
        records = {}
        for raw in self._pages(f"courses/{course}/assignments?per_page=100", lambda: None):
            kinds = raw.get("submission_types", [])
            if not isinstance(kinds, list):
                raise CanvasError("Canvas assignment has invalid submission types")
            if not (
                "online_quiz" in kinds
                or "external_tool" in kinds
                or raw.get("is_quiz_assignment") is True
                or raw.get("quiz_id") is not None
            ):
                continue
            id = _opaque_id(raw.get("id"), "assignment ID")
            title = raw.get("name")
            if not isinstance(title, str) or not title.strip():
                raise CanvasError("Canvas quiz assignment has an invalid title")
            records[id] = QuizRecord(id, title[:300], _score(raw.get("points_possible")))
        return tuple(records.values())

    def fetch_snapshot(
        self, trainings: list[TrainingSpec], progress=lambda: None
    ) -> CanvasSnapshot:
        if not self.settings.canvas_configured:
            raise CanvasError("Canvas is not configured")
        for training in trainings:
            training.validate()
        course = quote(_opaque_id(self.settings.canvas_course_id, "course ID"), safe="")
        roster = {}
        # Course users default to active/invited, whereas submissions may include
        # historical enrollment states. Request every state this endpoint supports.
        # https://developerdocs.instructure.com/services/canvas/resources/courses#method.courses.users
        states = "".join(
            f"&enrollment_state[]={state}"
            for state in ["active", "invited", "rejected", "completed", "inactive"]
        )
        for raw in self._pages(
            f"courses/{course}/users?per_page=100&include[]=email{states}", progress
        ):
            id = _opaque_id(raw.get("id"), "user ID")
            email = raw.get("email")
            if email is None and isinstance(raw.get("login_id"), str) and "@" in raw["login_id"]:
                email = raw["login_id"]
            if email is not None:
                if not isinstance(email, str) or len(email) > 254:
                    raise CanvasError("Canvas roster has an invalid email field")
                try:
                    validate_email(email, check_deliverability=False)
                except EmailNotValidError as exc:
                    raise CanvasError("Canvas roster has an invalid email field") from exc
            name = raw.get("name", "")
            if not isinstance(name, str):
                raise CanvasError("Canvas roster has an invalid display name")
            fact = RosterRecord(id, canonical_email(email), name[:300])
            if id in roster and roster[id] != fact:
                raise CanvasError("Canvas returned conflicting user identity records")
            roster[id] = fact
        results = {}
        skipped_results = 0
        for training in trainings:
            assignment = quote(training.assignment_id, safe="")
            path = f"courses/{course}/assignments/{assignment}/submissions?per_page=100"
            # The recovered deployment uses this one bulk path for every training.
            # This API has no incremental timestamp filter. Always follow all pages.
            for raw in self._pages(path, progress):
                id = _opaque_id(raw.get("user_id"), "submission user ID")
                if id not in roster:
                    # Deleted/test-view/unresolvable people are not an identity
                    # authority. Ignore their evidence without blocking all valid
                    # people or inventing ownership from a submission alone.
                    skipped_results += 1
                    continue
                submission_id = _opaque_id(raw.get("id"), "submission ID")
                if (
                    raw.get("assignment_id") is not None
                    and str(raw["assignment_id"]) != training.assignment_id
                ):
                    raise CanvasError("Canvas returned a submission for a different assignment")
                attempt = raw.get("attempt")
                if attempt is None:
                    attempt = 0  # Canvas unsubmitted placeholder, never passing.
                if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
                    raise CanvasError("Canvas result has an invalid attempt")
                workflow = raw.get("workflow_state", "unknown")
                grade = raw.get("grade")
                if not isinstance(workflow, str) or (
                    grade is not None and not isinstance(grade, str)
                ):
                    raise CanvasError("Canvas result has an invalid grade or workflow state")
                score = _score(raw.get("score"))
                # Preserve the recovered deployment's two data-driven checks.
                # A score threshold does not also require a posted grade; the
                # effective Canvas score can be valid before a grade is posted.
                passed = (
                    score is not None and score >= training.minimum_score
                    if training.minimum_score is not None
                    else workflow != "ungraded" and grade is not None
                )
                fact = ResultRecord(
                    id,
                    training,
                    submission_id,
                    attempt,
                    workflow,
                    score,
                    grade,
                    bool(passed),
                    _timestamp(raw.get("submitted_at")),
                )
                key = (id, training.training_type_id)
                if key not in results or fact.attempt >= results[key].attempt:
                    results[key] = fact
        return CanvasSnapshot(
            self.issuer,
            tuple(trainings),
            tuple(roster.values()),
            tuple(results.values()),
            skipped_results,
        )


def _award_cached_result(
    session: Session,
    roster: CanvasRoster,
    user: User,
    result: Training,
    *,
    settings: Settings | None = None,
) -> bool:
    if (
        result.awarded_at is not None
        or result.revoked_at is not None
        or not result.passed
        or not user.active
    ):
        return False
    training = session.get(TrainingType, result.training_type_id)
    if not training or not training.active or not training.canvas_assignment_id:
        return False
    spec = TrainingSpec.from_model(training, settings)
    if spec.fingerprint != result.config_fingerprint:
        return False
    result.awarded_at = utcnow()
    session.add(result)
    return True


def _attach_roster(
    session: Session, roster: CanvasRoster, identity: ExternalIdentity
) -> tuple[User | None, str | None]:
    if identity.user_id:
        user = session.get(User, identity.user_id)
        if user is None:
            return None, "Canvas identity references an unavailable local user"
        if roster.email and user.email and roster.email != canonical_email(user.email):
            return (
                None,
                "Bound Canvas identity email differs from the local user; staff review required",
            )
        other = session.exec(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == "canvas_id",
                ExternalIdentity.issuer == identity.issuer,
                ExternalIdentity.user_id == user.id,
                ExternalIdentity.id != identity.id,
            )
        ).first()
        if other:
            return (
                None,
                "Multiple Canvas identities are bound to this local user; staff review required",
            )
        return user, None
    if not roster.email:
        return None, None
    candidates = session.exec(select(User).where(User.email == roster.email)).all()
    if len(candidates) > 1:
        return None, "Multiple local users have the same email; no automatic binding was made"
    if not candidates:
        return None, None
    user = candidates[0]
    other = session.exec(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == "canvas_id",
            ExternalIdentity.issuer == identity.issuer,
            ExternalIdentity.user_id == user.id,
            ExternalIdentity.id != identity.id,
        )
    ).first()
    matching_rosters = session.exec(
        select(CanvasRoster)
        .join(ExternalIdentity)
        .where(
            CanvasRoster.email == roster.email,
            ExternalIdentity.provider == "canvas_id",
            ExternalIdentity.issuer == identity.issuer,
        )
    ).all()
    if other or len(matching_rosters) > 1:
        return None, "Multiple Canvas identities match this local user; staff review required"
    identity.user_id = user.id
    identity.verified_at = utcnow()
    session.add(identity)
    return user, None


def attach_cached_canvas(session: Session, user: User) -> dict:
    """Attach pre-fetched Canvas data using local records only; caller commits."""
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IDENTITY_LOCK})
    issuer = canvas_issuer()
    email = canonical_email(user.email)
    bound = session.exec(
        select(CanvasRoster, ExternalIdentity)
        .join(ExternalIdentity)
        .where(
            ExternalIdentity.provider == "canvas_id",
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.user_id == user.id,
        )
    ).all()
    rows = bound
    if not rows and email:
        rows = session.exec(
            select(CanvasRoster, ExternalIdentity)
            .join(ExternalIdentity)
            .where(
                ExternalIdentity.provider == "canvas_id",
                ExternalIdentity.issuer == issuer,
                CanvasRoster.email == email,
            )
        ).all()
    conflicts: list[str] = []
    if len(rows) > 1:
        message = "Multiple Canvas identities match this user; staff review required"
        for roster, _identity in rows:
            roster.identity_conflict = message
            session.add(roster)
        return {"matched": False, "conflicts": [message], "trainings_added": 0}
    awards = 0
    matched = False
    for roster, identity in rows:
        if identity.user_id and identity.user_id != user.id:
            conflict = "Matching Canvas identity is already bound to a different user"
            target = None
        else:
            target, conflict = _attach_roster(session, roster, identity)
        roster.identity_conflict = conflict
        session.add(roster)
        if conflict:
            conflicts.append(conflict)
        if target and target.id == user.id:
            matched = True
            for result in session.exec(
                select(Training).where(Training.external_identity_id == identity.id)
            ).all():
                awards += int(_award_cached_result(session, roster, user, result))
            if roster.identity_conflict and roster.identity_conflict not in conflicts:
                conflicts.append(roster.identity_conflict)
    session.flush()
    return {"matched": matched, "conflicts": conflicts, "trainings_added": awards}


def apply_snapshot(
    session: Session, snapshot: CanvasSnapshot, *, settings: Settings | None = None
) -> dict[str, int]:
    """Apply complete pages with batch lookups; caller atomically commits its success checkpoint."""
    settings = settings or get_settings()
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IDENTITY_LOCK})
    # Training edits share the identity lock. Lock rows too so direct SQL edits
    # cannot change eligibility while an award is being attached.
    trainings = {t.id: t for t in session.exec(select(TrainingType).with_for_update()).all()}
    for spec in snapshot.trainings:
        training = trainings.get(spec.training_type_id)
        if training is None or TrainingSpec.from_model(training, settings) != spec:
            raise CanvasError(
                "Canvas training configuration changed during synchronization; retry with current settings"
            )
    now = utcnow()
    identities = session.exec(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == "canvas_id", ExternalIdentity.issuer == snapshot.issuer
        )
    ).all()
    by_value = {identity.value: identity for identity in identities}
    for fact in snapshot.roster:
        if fact.canvas_id not in by_value:
            identity = ExternalIdentity(
                provider="canvas_id", issuer=snapshot.issuer, value=fact.canvas_id
            )
            by_value[fact.canvas_id] = identity
            identities.append(identity)
            session.add(identity)
    session.flush()
    roster_rows = session.exec(
        select(CanvasRoster).where(
            CanvasRoster.external_identity_id.in_([i.id for i in identities])
        )
    ).all()
    by_identity = {roster.external_identity_id: roster for roster in roster_rows}
    rosters = {}
    for fact in snapshot.roster:
        identity = by_value[fact.canvas_id]
        roster = by_identity.get(identity.id)
        if roster is None:
            roster = CanvasRoster(external_identity_id=identity.id)
            by_identity[identity.id] = roster
        roster.email, roster.display_name = fact.email, fact.display_name
        roster.last_seen_at = roster.last_synced_at = now
        rosters[fact.canvas_id] = roster
        session.add(roster)
    session.flush()
    returned = {(by_value[f.canvas_id].id, f.training.training_type_id) for f in snapshot.results}
    fetched_training_ids = [spec.training_type_id for spec in snapshot.trainings]
    cached = session.exec(
        select(Training).where(
            Training.source == "canvas",
            or_(
                Training.training_type_id.in_(fetched_training_ids),
                Training.external_identity_id.in_([i.id for i in identities]),
            ),
        )
    ).all()
    result_by_key = {(r.external_identity_id, r.training_type_id): r for r in cached}
    for previous in cached:
        key = (previous.external_identity_id, previous.training_type_id)
        if previous.training_type_id in fetched_training_ids and key not in returned:
            # Earned training remains. Missing current evidence cannot grant
            # training to a new visitor after a complete source fetch.
            previous.passed, previous.workflow_status, previous.fetched_at = (
                False,
                "not_returned",
                now,
            )
            session.add(previous)
    for fact in snapshot.results:
        roster = rosters[fact.canvas_id]
        key = (by_value[fact.canvas_id].id, fact.training.training_type_id)
        result = result_by_key.get(key)
        if result is None:
            result = Training(
                source="canvas",
                external_identity_id=key[0],
                training_type_id=fact.training.training_type_id,
            )
            result_by_key[key] = result
        result.submission_id, result.attempt = fact.submission_id, fact.attempt
        result.workflow_status, result.score, result.grade = (
            fact.workflow_status,
            fact.score,
            fact.grade,
        )
        result.passed, result.completed_at = fact.passed, fact.completed_at
        result.config_fingerprint, result.fetched_at = fact.training.fingerprint, now
        session.add(result)
    session.flush()

    # Resolve identity conflicts using the whole fetched roster, including
    # people who have never registered locally. No per-student SQL or HTTP.
    user_rows = session.exec(
        select(User).where(
            or_(
                User.id.in_([i.user_id for i in identities if i.user_id]),
                User.email.in_([r.email for r in rosters.values() if r.email]),
            )
        )
    ).all()
    users_by_id = {u.id: u for u in user_rows}
    users_by_email = {}
    for user in user_rows:
        if user.email:
            users_by_email.setdefault(user.email, []).append(user)
    bound_by_user = {}
    for identity in identities:
        if identity.user_id:
            bound_by_user.setdefault(identity.user_id, []).append(identity)
    roster_email_counts = {}
    for roster in by_identity.values():
        if roster.email:
            roster_email_counts[roster.email] = roster_email_counts.get(roster.email, 0) + 1
    linked_users = {}
    for id, roster in rosters.items():
        identity = by_value[id]
        user, conflict = None, None
        if identity.user_id:
            user = users_by_id.get(identity.user_id)
            if user is None:
                conflict = "Canvas identity references an unavailable local user"
            elif roster.email and user.email and roster.email != canonical_email(user.email):
                conflict = (
                    "Bound Canvas identity email differs from the local user; staff review required"
                )
            elif len(bound_by_user.get(user.id, [])) > 1:
                conflict = (
                    "Multiple Canvas identities are bound to this local user; staff review required"
                )
        elif roster.email:
            candidates = users_by_email.get(roster.email, [])
            if len(candidates) > 1:
                conflict = "Multiple local users have the same email; no automatic binding was made"
            elif candidates:
                user = candidates[0]
                if bound_by_user.get(user.id) or roster_email_counts.get(roster.email, 0) > 1:
                    conflict = (
                        "Multiple Canvas identities match this local user; staff review required"
                    )
                else:
                    identity.user_id, identity.verified_at = user.id, now
                    bound_by_user.setdefault(user.id, []).append(identity)
                    session.add(identity)
        roster.identity_conflict = conflict
        session.add(roster)
        if user is not None and conflict is None:
            linked_users[roster.id] = user

    linked_by_identity = {
        r.external_identity_id: linked_users[r.id] for r in rosters.values() if r.id in linked_users
    }
    grants = 0
    for result in result_by_key.values():
        user = linked_by_identity.get(result.external_identity_id)
        training = trainings.get(result.training_type_id)
        if (
            not user
            or not user.active
            or not result.passed
            or result.awarded_at is not None
            or result.revoked_at is not None
            or not training
            or not training.active
            or not training.canvas_assignment_id
        ):
            continue
        spec = TrainingSpec.from_model(training, settings)
        if spec.fingerprint != result.config_fingerprint:
            continue
        result.awarded_at = now
        session.add(result)
        grants += 1
    return {
        "roster": len(rosters),
        "results": len(snapshot.results),
        "skipped_results": snapshot.skipped_results,
        "linked": len(linked_users),
        "trainings_added": grants,
        "conflicts": sum(r.identity_conflict is not None for r in rosters.values()),
    }


def canvas_status(session: Session, *, settings: Settings | None = None) -> dict:
    from ..jobs import active_canvas_jobs

    settings = settings or get_settings()
    active_jobs = active_canvas_jobs(session) if settings.canvas_configured else []
    active = {job["training_type_id"] for job in active_jobs}
    # Historical worker events with this entity type and no target were whole
    # syncs. Explicit per-training scope must never become an overall success.
    scope = AuditEvent.details["scope"].astext
    issuer = AuditEvent.details["issuer"].astext
    course = AuditEvent.details["course_id"].astext
    outcomes = (
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "training_types",
            AuditEvent.action.in_(["canvas.sync_completed", "canvas.sync_failed"]),
            or_(scope == "whole", (scope.is_(None) & AuditEvent.entity_id.is_(None))),
            or_(issuer.is_(None), issuer == canvas_issuer(settings)),
            or_(course.is_(None), course == settings.canvas_course_id),
        )
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
    )
    latest = session.exec(outcomes.limit(1)).first()
    last_success = session.exec(
        outcomes.where(AuditEvent.action == "canvas.sync_completed").limit(1)
    ).first()
    active_whole = [job for job in active_jobs if job["training_type_id"] is None]
    started_at = max((job["started_at"] for job in active_whole if job["started_at"]), default=None)
    if not active_whole and latest:
        value = latest.details.get("started_at")
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                started_at = parsed if parsed.tzinfo else None
            except ValueError:
                pass
    last_error = (
        latest.details.get("error") if latest and latest.action == "canvas.sync_failed" else None
    )
    overview = {
        "status": "unconfigured"
        if not settings.canvas_configured
        else "running"
        if active_jobs
        else "error"
        if last_error
        else "idle",
        "started_at": started_at,
        "last_success_at": last_success.occurred_at if last_success else None,
        "last_error": last_error,
    }
    trainings = session.exec(select(TrainingType).order_by(*training_type_order())).all()
    rosters = session.exec(
        select(CanvasRoster, ExternalIdentity)
        .join(ExternalIdentity)
        .where(
            ExternalIdentity.provider == "canvas_id",
            ExternalIdentity.issuer == canvas_issuer(settings),
        )
    ).all()

    def item(roster, identity):
        return {
            "id": str(roster.id),
            "display_name": roster.display_name,
            "email": roster.email,
            "canvas_id": identity.value,
            "user_id": str(identity.user_id) if identity.user_id else None,
            "conflict": roster.identity_conflict,
        }

    def state(training):
        if not settings.canvas_configured or not training.canvas_assignment_id:
            return "unconfigured"
        if None in active or str(training.id) in active:
            return "running"
        return "error" if training.canvas_sync_error else "idle"

    return {
        "configured": settings.canvas_configured,
        "overview": overview,
        "setup_message": None
        if settings.canvas_configured
        else "Configure CANVAS_API_TOKEN and CANVAS_COURSE_ID to enable synchronization",
        "trainings": [
            {
                "training_type_id": str(t.id),
                "name": t.name,
                "canvas_assignment_id": t.canvas_assignment_id,
                "started_at": t.canvas_sync_started_at,
                "last_success_at": t.canvas_synced_at,
                "last_error": t.canvas_sync_error,
                "status": state(t),
            }
            for t in trainings
        ],
        "unmatched": [item(r, i) for r, i in rosters if i.user_id is None][:100],
        "conflicts": [item(r, i) for r, i in rosters if r.identity_conflict][:100],
    }


def enqueue_canvas_sync(session: Session, **kwargs):
    from ..jobs import enqueue_canvas_sync as enqueue

    return enqueue(session, **kwargs)
