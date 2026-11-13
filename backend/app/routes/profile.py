import io
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlmodel import select

from ..config import get_settings
from ..events import audit, publish
from ..models import User, Visit
from ..responses import ProfileResponse, UserDetail
from ..schemas import ProfilePatch
from ..security import DB, CurrentActor
from ..services.identity import set_recovery_email
from ..services.projections import user_dto
from ..services.storage import get_avatar, put_avatar
from .common import page_result

router = APIRouter(tags=["profile"])


@router.get("/api/me/profile", response_model=ProfileResponse)
def profile(
    session: DB,
    actor: CurrentActor,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
):
    from sqlalchemy import func

    count, total = session.exec(
        select(
            func.count(Visit.id),
            func.coalesce(
                func.sum(func.extract("epoch", Visit.exit_time - Visit.enter_time)) / 3600.0, 0
            ),
        ).where(
            Visit.user_id == actor.user.id,
            Visit.exit_time.is_not(None),
            Visit.forgot_to_sign_out.is_(False),
        )
    ).one()
    history = page_result(
        session,
        select(Visit).where(Visit.user_id == actor.user.id).order_by(Visit.enter_time.desc()),
        page,
        page_size,
    )
    return {
        "user": user_dto(session, actor.user),
        "total_hours": float(total),
        "completed_visits": int(count),
        "visits": history,
    }


@router.patch("/api/me/profile", response_model=UserDetail)
def edit_profile(data: ProfilePatch, session: DB, actor: CurrentActor):
    changes = data.model_dump(exclude_unset=True)
    if "email" in changes:
        if changes["email"] is None:
            raise HTTPException(422, "email cannot be null")
        set_recovery_email(session, actor.user, str(changes["email"]).strip(), actor)
    for key, value in changes.items():
        if value is None:
            raise HTTPException(422, f"{key} cannot be null")
        setattr(actor.user, key, str(value).strip())
    session.add(actor.user)
    audit(session, "profile.updated", "users", actor.user.id, actor.user.id, fields=list(changes))
    publish(session, "users")
    session.commit()
    return user_dto(session, actor.user)


@router.post("/api/me/avatar")
def upload_avatar(file: UploadFile, session: DB, actor: CurrentActor):
    settings = get_settings()
    data = file.file.read(settings.avatar_max_bytes + 1)
    if len(data) > settings.avatar_max_bytes:
        raise HTTPException(413, "Profile image must be no larger than 2 MB")
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in {"JPEG", "PNG"}:
            raise HTTPException(422, "Upload a JPEG or PNG profile image")
        if image.width * image.height > 20_000_000:
            raise HTTPException(422, "Profile image is too large")
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((512, 512))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Upload a valid JPEG or PNG profile image") from exc
    key = uuid4().hex + ".jpg"
    put_avatar(key, output.getvalue())
    actor.user.avatar_key = key
    session.add(actor.user)
    audit(session, "profile.avatar_updated", "users", actor.user.id, actor.user.id)
    publish(session, "users")
    session.commit()
    return {"avatar_url": f"/media/avatars/{key}"}


@router.get("/media/avatars/{key}")
def avatar(key: str, session: DB):
    if not session.exec(select(User.id).where(User.avatar_key == key)).first():
        raise HTTPException(404, "Profile image not found")
    return Response(
        get_avatar(key),
        media_type="image/jpeg",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=300"},
    )
