"""Permission-protected, preview-first CSV preregistration. Never creates visits."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.models import Permission, Role
from app.security import DB, Actor, require
from app.services.imports import MAX_CSV_BYTES, apply_users, preview_users

router = APIRouter(prefix="/api/admin/imports/users", tags=["user preregistration"])
UserWriter = Annotated[Actor, Depends(require(Permission.USERS_WRITE))]


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv_text: str = Field(min_length=1, max_length=MAX_CSV_BYTES)


class ApplyInput(PreviewInput):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm: bool = False


class ImportSummary(BaseModel):
    total: int
    new: int
    existing: int
    conflict: int
    invalid: int


class PreviewRow(BaseModel):
    row_number: int
    identifier: str
    first_name: str
    last_name: str
    email: str | None
    status: Literal["new", "existing", "conflict", "invalid"]
    message: str
    existing_user_id: UUID | None


class PreviewResponse(BaseModel):
    fingerprint: str
    can_apply: bool
    summary: ImportSummary
    rows: list[PreviewRow]
    ignored_columns: list[str]


class ApplyResponse(BaseModel):
    created: int
    skipped_existing: int
    created_user_ids: list[UUID]
    fingerprint: str
    message: str


@router.post("/preview", response_model=PreviewResponse)
def preview(payload: PreviewInput, session: DB, actor: UserWriter):
    if actor.role == Role.OPERATOR:
        raise HTTPException(403, "Only administrators may import user identities")
    return preview_users(session, payload.csv_text)


@router.post("/apply", response_model=ApplyResponse)
def apply(payload: ApplyInput, session: DB, actor: UserWriter):
    if actor.role == Role.OPERATOR:
        raise HTTPException(403, "Only administrators may import user identities")
    return apply_users(
        session, actor.user.id, payload.csv_text, payload.fingerprint, payload.confirm
    )
