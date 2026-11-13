"""Normalized provisional schema. No production import is performed by these models."""

from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class SpaceLevel(IntEnum):
    MEMBER = 0
    VOLUNTEER = 1
    KEYHOLDER = 2
    STAFF = 3


class Role(StrEnum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    OPERATOR = "operator"


class Permission(StrEnum):
    USERS_READ = "users.read"
    USERS_WRITE = "users.write"
    TRAININGS_READ = "trainings.read"
    TRAININGS_WRITE = "trainings.write"
    VISITS_READ = "visits.read"
    VISITS_WRITE = "visits.write"
    METRICS_READ = "metrics.read"
    CANVAS_READ = "canvas.read"
    CANVAS_WRITE = "canvas.write"
    PRINT_READ = "printing.read"
    PRINT_WRITE = "printing.write"
    AUDIT_READ = "audit.read"
    ROLES_WRITE = "roles.write"
    DATABASE_READ = "database.read"
    DATABASE_WRITE = "database.write"


ROLE_PERMISSIONS = {
    Role.SUPERADMIN: set(Permission),
    Role.ADMIN: set(Permission) - {Permission.DATABASE_WRITE},
    Role.OPERATOR: {
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.TRAININGS_READ,
        Permission.TRAININGS_WRITE,
        Permission.VISITS_READ,
        Permission.PRINT_READ,
        Permission.PRINT_WRITE,
        Permission.CANVAS_READ,
        Permission.METRICS_READ,
        Permission.AUDIT_READ,
    },
}


class Timestamped(SQLModel):
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": False, "server_default": text("CURRENT_TIMESTAMP")},
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "nullable": False,
            "onupdate": utcnow,
            "server_default": text("CURRENT_TIMESTAMP"),
        },
    )


class User(Timestamped, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("keyholder_priority >= -1", name="user_priority_minimum"),
        CheckConstraint("space_level BETWEEN 0 AND 3", name="user_space_level_range"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: str | None = Field(default=None, index=True, max_length=254)
    password_hash: str | None = None
    role: Role | None = Field(default=None, index=True)
    avatar_key: str | None = Field(default=None, max_length=64)
    space_level: SpaceLevel = Field(default=SpaceLevel.MEMBER, sa_type=Integer)
    keyholder_priority: int = -1
    active: bool = Field(default=True, sa_column_kwargs={"server_default": text("true")})

    @property
    def display_name(self) -> str:
        return " ".join(part for part in [self.first_name, self.last_name] if part) or "Visitor"


class ExternalIdentity(Timestamped, table=True):
    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "issuer", "value", name="identity_provider_issuer_value_unique"
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    provider: str = Field(max_length=32)
    issuer: str = Field(default="charlotte", max_length=254)
    value: str = Field(max_length=128)
    verified_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class AuthSession(Timestamped, table=True):
    __tablename__ = "auth_sessions"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(unique=True, index=True)
    csrf_hash: str
    csrf_token: str
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class TrainingType(Timestamped, table=True):
    __tablename__ = "training_types"
    __table_args__ = (
        CheckConstraint("display_order >= 0", name="training_type_display_order_nonnegative"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=100)
    icon_key: str = "orientation"
    display_order: int = Field(default=100, ge=0, sa_column_kwargs={"server_default": text("100")})
    active: bool = True
    canvas_assignment_id: str | None = Field(default=None, foreign_key="canvas_quizzes.id")
    canvas_minimum_score: float | None = None
    canvas_sync_started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    canvas_synced_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    canvas_sync_error: str | None = None


def training_type_order():
    return TrainingType.display_order, TrainingType.name, TrainingType.id


class CanvasQuiz(Timestamped, table=True):
    __tablename__ = "canvas_quizzes"
    id: str = Field(primary_key=True, max_length=64)
    title: str
    points_possible: float | None = None
    fetched_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class Training(Timestamped, table=True):
    __tablename__ = "trainings"
    __table_args__ = (
        UniqueConstraint("external_identity_id", "training_type_id", name="canvas_training_unique"),
        CheckConstraint(
            "(source = 'manual' AND user_id IS NOT NULL AND external_identity_id IS NULL) OR "
            "(source = 'canvas' AND user_id IS NULL AND external_identity_id IS NOT NULL)",
            name="training_owner_source",
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    external_identity_id: UUID | None = Field(
        default=None, foreign_key="external_identities.id", index=True
    )
    training_type_id: UUID = Field(foreign_key="training_types.id", index=True)
    awarded_by_user_id: UUID | None = Field(default=None, foreign_key="users.id")
    # Awarded state is independent of the latest source evidence below. Cached
    # pre-signup rows have no award until identity binding checks current config.
    awarded_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    source: str = "manual"
    submission_id: str | None = None
    attempt: int = 0
    config_fingerprint: str = Field(default="", max_length=64)
    workflow_status: str = "unknown"
    score: float | None = None
    grade: str | None = None
    passed: bool = False
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    fetched_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class Visit(Timestamped, table=True):
    __tablename__ = "visits"
    __table_args__ = (
        CheckConstraint("exit_time IS NULL OR exit_time >= enter_time", name="visit_time_order"),
        Index(
            "one_open_visit_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("exit_time IS NULL"),
        ),
        Index("visits_time_range", "enter_time", "exit_time"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    enter_time: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    exit_time: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    forgot_to_sign_out: bool = False


class KeyholderShift(Timestamped, table=True):
    __tablename__ = "keyholder_shifts"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="shift_time_order"),
        Index(
            "one_open_keyholder_shift",
            text("(true)"),
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    started_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    ended_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class CanvasRoster(Timestamped, table=True):
    __tablename__ = "canvas_roster"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    external_identity_id: UUID = Field(
        foreign_key="external_identities.id", unique=True, index=True
    )
    email: str | None = Field(default=None, index=True)
    display_name: str = ""
    last_seen_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    last_synced_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    identity_conflict: str | None = None


class EmailJob(Timestamped, table=True):
    __tablename__ = "email_jobs"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    kind: str = "canvas_invite"
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    state: str = "pending"
    attempts: int = 0
    last_error: str | None = None
    sent_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class AuditEvent(SQLModel, table=True):
    __tablename__ = "audit_events"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor_user_id: UUID | None = Field(default=None, foreign_key="users.id")
    action: str = Field(index=True)
    entity_type: str
    entity_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    occurred_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class ScopeRevision(Timestamped, table=True):
    __tablename__ = "scope_revisions"
    scope: str = Field(primary_key=True)
    revision: int = 0


class LoginAttempt(SQLModel, table=True):
    __tablename__ = "login_attempts"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    key_hash: str = Field(index=True)
    occurred_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class PasswordReset(Timestamped, table=True):
    __tablename__ = "password_resets"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")
    token_hash: str = Field(unique=True, index=True)
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    used_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
