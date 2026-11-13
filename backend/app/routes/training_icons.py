"""Validated training images, stored as public-intended PNG objects in private S3."""

import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from ..events import audit, publish
from ..models import Permission, Role
from ..security import DB, Actor, require
from ..services import storage

router = APIRouter(tags=["training icons"])
Writer = Annotated[Actor, Depends(require(Permission.TRAININGS_WRITE))]


class UploadedTrainingIcon(BaseModel):
    icon_key: str
    icon_url: str


def _encode_icon(data: bytes) -> bytes:
    if len(data) > storage.MAX_TRAINING_ICON_BYTES:
        raise HTTPException(413, "Training icon must be no larger than 2 MB")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(422, "Upload a JPEG, PNG or WebP training icon")
            if source.width * source.height > 20_000_000:
                raise HTTPException(422, "Training icon must be no larger than 20 megapixels")
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            image.info.clear()
            output = io.BytesIO()
            image.save(output, format="PNG")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Upload a valid JPEG, PNG or WebP training icon") from exc
    return output.getvalue()


@router.post(
    "/api/admin/training-icons",
    status_code=201,
    response_model=UploadedTrainingIcon,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {"file": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
)
async def upload(request: Request, session: DB, actor: Writer):
    if actor.role not in {Role.ADMIN, Role.SUPERADMIN}:
        raise HTTPException(403, "Only administrators may upload training icons")
    actor_id = actor.user.id
    session.rollback()
    request_limit = storage.MAX_TRAINING_ICON_BYTES + 64 * 1024
    received = 0

    async def limited_stream():
        nonlocal received
        async for chunk in request.stream():
            received += len(chunk)
            if received > request_limit:
                raise MultiPartException("Training icon exceeds the 2 MB limit")
            yield chunk

    parser = MultiPartParser(
        request.headers,
        limited_stream(),
        max_files=1,
        max_fields=0,
        max_part_size=storage.MAX_TRAINING_ICON_BYTES,
    )
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        if received > request_limit:
            raise HTTPException(413, "Training icon must be no larger than 2 MB") from None
        raise HTTPException(422, "Choose one JPEG, PNG or WebP training icon") from exc
    try:
        file = form.get("file")
        if (
            not isinstance(file, UploadFile)
            or len(form) != 1
            or file.content_type not in {"image/jpeg", "image/png", "image/webp"}
        ):
            raise HTTPException(422, "Choose one JPEG, PNG or WebP training icon")
        encoded = await run_in_threadpool(
            _encode_icon, await file.read(storage.MAX_TRAINING_ICON_BYTES + 1)
        )
        key = await run_in_threadpool(storage.put_training_icon, encoded)
    finally:
        await form.close()
    audit(session, "training_icon.uploaded", "training_icons", key, actor_id, size=len(encoded))
    publish(session, "storage")
    session.commit()
    return UploadedTrainingIcon(icon_key=key, icon_url=f"/media/{key}")


@router.get(
    "/media/training-icons/{filename}",
    response_class=Response,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
def image(filename: str):
    data = storage.get_training_icon(f"training-icons/{filename}")
    return Response(
        data,
        media_type="image/png",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=86400, immutable",
        },
    )
