"""Explicit response contracts; private fields cannot leak into public projections."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .models import Role, SpaceLevel


class Badge(BaseModel):
    training_type_id: UUID
    name: str
    icon_key: str


class PublicPerson(BaseModel):
    id: UUID
    display_name: str
    avatar_url: str | None = None


class Occupant(PublicPerson):
    badges: list[Badge] = Field(default_factory=list)


class LabState(BaseModel):
    is_open: bool
    keyholder: PublicPerson | None = None


class Occupancy(BaseModel):
    revision: int
    lab: LabState
    occupants: list[Occupant]


class KioskResult(BaseModel):
    status: Literal[
        "signed_in",
        "signed_out",
        "registration_required",
        "keyholder_action_required",
        "lab_closed",
    ]
    message: str
    user: PublicPerson | None = None
    revision: int
    identifier: str | None = None
    expected_shift_id: UUID | None = None
    actions: list[str] | None = None


class SessionUser(BaseModel):
    id: UUID
    display_name: str
    email: str | None = None
    role: Role | None = None
    permissions: list[str]


class AuthResponse(BaseModel):
    user: SessionUser
    csrf_token: str


class Identifier(BaseModel):
    provider: str
    value: str


class UserDetail(PublicPerson):
    first_name: str
    last_name: str
    email: str | None = None
    space_level: SpaceLevel
    keyholder_priority: int
    active: bool
    created_at: datetime
    updated_at: datetime
    identifiers: list[Identifier]
    role: Role | None = None
    badges: list[Badge]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class TrainingDetail(BaseModel):
    id: UUID
    user_id: UUID | None
    user_name: str
    user_href: str | None
    training_type_id: UUID
    training_type_name: str
    source: str
    awarded_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    has_training: bool
    score: float | None
    grade: str | None
    passed: bool
    completed_at: datetime | None
    fetched_at: datetime | None
    submission_id: str | None
    attempt: int
    created_at: datetime
    updated_at: datetime


class TrainingTypeDetail(BaseModel):
    id: UUID
    name: str
    icon_key: str
    display_order: int
    active: bool
    canvas_assignment_id: str | None
    canvas_minimum_score: float | None
    canvas_sync_started_at: datetime | None
    canvas_synced_at: datetime | None
    canvas_sync_error: str | None
    created_at: datetime
    updated_at: datetime


class AuditDetail(BaseModel):
    id: UUID
    occurred_at: datetime
    action: str
    action_label: str
    actor_name: str
    actor_href: str | None
    target_name: str
    target_href: str | None
    details: dict


class MetricsSummary(BaseModel):
    unique_visitors: int
    visits: int
    finalized_visits: int
    total_hours: float
    average_visit_minutes: float
    new_visitors: int
    excluded_visits: int
    open_visits: int


class DailyMetrics(BaseModel):
    date: str
    visits: int
    unique_visitors: int
    total_hours: float


class MetricsResponse(BaseModel):
    start: str
    end: str
    timezone: str
    summary: MetricsSummary
    daily: list[DailyMetrics]
    definitions: dict[str, str]


class VisitDetail(BaseModel):
    id: UUID
    user_id: UUID
    enter_time: datetime
    exit_time: datetime | None = None
    forgot_to_sign_out: bool
    created_at: datetime
    updated_at: datetime
    display_name: str | None = None
    user_href: str | None = None
    duration_seconds: float | None = None


class ProfileResponse(BaseModel):
    user: UserDetail
    total_hours: float
    completed_visits: int
    visits: Page[VisitDetail]


class PrintResult(BaseModel):
    status: Literal["sent", "offline", "busy"]
    label_id: UUID | None = None
    message: str


class PrinterLastResult(BaseModel):
    status: Literal["printed", "failed", "unknown"]
    label_id: UUID
    display_name: str
    at: datetime
    message: str | None = None


class PrintingStatus(BaseModel):
    connected: bool
    busy: bool
    last_result: PrinterLastResult | None = None


class KioskStats(BaseModel):
    present: int
    unique_visitors_today: int
    weekly_hours: float


class RecentActivity(BaseModel):
    user_id: UUID
    display_name: str
    action: Literal["signed_in", "signed_out"]
    occurred_at: datetime
    enter_time: datetime
    exit_time: datetime | None


class KioskState(Occupancy):
    stats: KioskStats
    recent_activity: list[RecentActivity]


class SnapshotMessage(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    topic: Literal["occupancy"] = "occupancy"
    revision: int
    data: Occupancy


class InvalidationMessage(BaseModel):
    type: Literal["invalidate"] = "invalidate"
    topics: list[str]
    revision: int


class KioskCommandEnvelope(BaseModel):
    type: Literal["command"] = "command"
    id: str
    command: Literal["tap", "register", "keyholder"]
    data: dict


class LabelPayload(BaseModel):
    display_name: str
    avatar_url: str | None = None
    badges: list[Badge]


class PrinterJobEnvelope(BaseModel):
    type: Literal["label"] = "label"
    id: UUID
    label: LabelPayload
