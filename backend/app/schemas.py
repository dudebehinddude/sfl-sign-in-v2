import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import Role, SpaceLevel


def university_email(value: str) -> str:
    from .services.identity import canonical_email

    normalized = canonical_email(str(value))
    if not normalized or normalized.rsplit("@", 1)[-1] != "charlotte.edu":
        raise ValueError("Use a charlotte.edu or uncc.edu email")
    return normalized


UniversityEmail = Annotated[EmailStr, AfterValidator(university_email)]
LEGACY_TRAINING_ICONS = {
    "orientation",
    "policies",
    "3d-printer",
    "laser-cutter",
    "resin-printer",
    "waterjet",
}


def training_icon(value: str) -> str:
    if value == "":
        return "orientation"
    if value in LEGACY_TRAINING_ICONS or re.fullmatch(r"training-icons/[a-f0-9]{32}\.png", value):
        return value
    raise ValueError("Choose an original icon or upload a training icon")


TrainingIcon = Annotated[str, Field(max_length=64), AfterValidator(training_icon)]


def validated_identifier(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"(?:[0-9]{9}|[A-Za-z][A-Za-z0-9:_-]{2,63})", value):
        raise ValueError("Enter a nine-digit student ID or issued lab identifier")
    return value


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(Input):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChange(Input):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class TapInput(Input):
    identifier: str = Field(min_length=3, max_length=64)

    @field_validator("identifier")
    @classmethod
    def identifier_format(cls, value):
        return validated_identifier(value)


class RegisterInput(TapInput):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: UniversityEmail

    @field_validator("first_name", "last_name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class KeyholderInput(TapInput):
    action: Literal["open", "handoff", "override", "close", "continue"]
    target_identifier: str | None = Field(default=None, max_length=64)
    expected_shift_id: UUID | None
    sign_out_current_keyholder: bool = False


class UserCreate(Input):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: UniversityEmail | None = None
    identifier: str = Field(min_length=3, max_length=64)
    space_level: SpaceLevel = SpaceLevel.MEMBER
    keyholder_priority: int = Field(default=-1, ge=-1)

    @field_validator("identifier")
    @classmethod
    def identifier_format(cls, value):
        return validated_identifier(value)


class UserPatch(Input):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: UniversityEmail | None = None
    space_level: SpaceLevel | None = None
    keyholder_priority: int | None = Field(default=None, ge=-1)
    active: bool | None = None


class ProfilePatch(Input):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: UniversityEmail | None = None


class TrainingTypeInput(Input):
    name: str = Field(min_length=1, max_length=100)
    icon_key: TrainingIcon = "orientation"
    display_order: int = Field(default=100, ge=0)
    active: bool = True
    canvas_assignment_id: str | None = Field(default=None, max_length=64)
    canvas_minimum_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class TrainingTypePatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon_key: TrainingIcon | None = None
    display_order: int | None = Field(default=None, ge=0)
    active: bool | None = None
    canvas_assignment_id: str | None = Field(default=None, max_length=64)
    canvas_minimum_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class TrainingInput(Input):
    user_id: UUID
    training_type_id: UUID
    awarded_at: datetime | None = None
    expires_at: datetime | None = None


class RevokeInput(Input):
    reason: str = Field(min_length=3, max_length=500)


class CloseVisitInput(Input):
    forgot_to_sign_out: bool = True


class RoleInput(Input):
    role: Role | None


class SetPassword(Input):
    password: str = Field(min_length=12, max_length=1024)


class PasswordResetRequest(Input):
    email: UniversityEmail


class PasswordResetInput(Input):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=1024)
