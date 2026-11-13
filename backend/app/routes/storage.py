"""Same-origin object management for superadmins, never a public S3 proxy."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import select
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from ..events import audit, publish
from ..models import TrainingType, User
from ..security import DB, Superadmin
from ..services import storage

router = APIRouter(prefix="/api/admin/storage", tags=["storage"])


class StorageUser(BaseModel):
    id: str
    display_name: str
    href: str


class StorageObject(BaseModel):
    key: str
    size: int
    last_modified: datetime | None
    etag: str | None
    users: list[StorageUser] = Field(default_factory=list)


class StoragePage(BaseModel):
    items: list[StorageObject]
    prefix: str
    next_cursor: str | None
    limit: int
    upload_max_bytes: int


class UploadedObject(BaseModel):
    key: str
    size: int


def _user_ref(user: User) -> StorageUser:
    return StorageUser(
        id=str(user.id), display_name=user.display_name, href=f"/admin/users/{user.id}"
    )


@router.get("/objects", response_model=StoragePage)
def objects(
    session: DB,
    actor: Superadmin,
    prefix: str = Query("", max_length=1024),
    cursor: str | None = Query(None, max_length=1024),
    limit: int = Query(100, ge=1, le=1000),
):
    # Authentication is complete; release its read transaction during S3 I/O.
    session.rollback()
    rows, next_cursor = storage.list_storage_objects(prefix, cursor, limit)
    avatar_names = [
        row["key"][len("avatars/") :] for row in rows if row["key"].startswith("avatars/")
    ]
    references = {}
    for user in session.exec(select(User).where(User.avatar_key.in_(avatar_names))).all():
        references.setdefault(f"avatars/{user.avatar_key}", []).append(_user_ref(user))
    return StoragePage(
        items=[StorageObject(**row, users=references.get(row["key"], [])) for row in rows],
        prefix=prefix,
        next_cursor=next_cursor,
        limit=limit,
        upload_max_bytes=storage.MAX_STORAGE_BYTES,
    )


@router.get("/object")
def download(key: str, session: DB, actor: Superadmin):
    actor_id = actor.user.id
    storage.validate_storage_key(key)
    session.rollback()
    data = storage.read_storage_object(key)
    audit(session, "storage.downloaded", "storage", key, actor_id, name=key, size=len(data))
    session.commit()
    # Never trust an object's content-type or filename to select browser content.
    return Response(
        data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{storage.safe_storage_filename(key)}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post("/objects", status_code=201, response_model=UploadedObject)
async def upload(request: Request, session: DB, actor: Superadmin):
    actor_id = actor.user.id
    session.rollback()
    # No UploadFile body parameter: authorize before reading any body. Bound the
    # multipart request stream too, not only the already-spooled uploaded file.
    request_limit = storage.MAX_STORAGE_BYTES + 64 * 1024
    received = 0

    async def limited_stream():
        nonlocal received
        async for chunk in request.stream():
            received += len(chunk)
            if received > request_limit:
                raise MultiPartException("Upload exceeds the 5 MB limit")
            yield chunk

    parser = MultiPartParser(
        request.headers,
        limited_stream(),
        max_files=1,
        max_fields=0,
        max_part_size=storage.MAX_STORAGE_BYTES,
    )
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        if received > request_limit:
            raise HTTPException(413, "Upload a file no larger than 5 MB") from None
        raise HTTPException(422, "Choose one file to upload") from exc
    try:
        file = form.get("file")
        if not isinstance(file, UploadFile) or len(form) != 1:
            raise HTTPException(422, "Choose one file to upload")
        data = await file.read(storage.MAX_STORAGE_BYTES + 1)
        result = await run_in_threadpool(
            storage.upload_storage_object, file.filename or "upload", data
        )
    finally:
        await form.close()
    audit(
        session,
        "storage.uploaded",
        "storage",
        result["key"],
        actor_id,
        name=result["key"],
        size=result["size"],
    )
    publish(session, "storage")
    session.commit()
    return UploadedObject(**result)


@router.delete("/object", status_code=204)
def delete(key: str, session: DB, actor: Superadmin):
    actor_id = actor.user.id
    storage.validate_storage_key(key)
    if key.startswith("avatars/"):
        users = session.exec(select(User).where(User.avatar_key == key[len("avatars/") :])).all()
        if users:
            raise HTTPException(
                409,
                detail={
                    "message": "This photo is still used by a person. Change their profile photo before deleting it.",
                    "users": [_user_ref(user).model_dump() for user in users],
                },
            )
    if key.startswith("training-icons/"):
        definitions = session.exec(
            select(TrainingType).where(TrainingType.icon_key == key).order_by(TrainingType.name)
        ).all()
        if definitions:
            names = ", ".join(definition.name for definition in definitions)
            raise HTTPException(
                409,
                detail={
                    "message": f"This icon is still used by {names}. Change the training icon before deleting it.",
                    "users": [],
                },
            )
    session.rollback()
    storage.delete_storage_object(key)
    audit(session, "storage.deleted", "storage", key, actor_id, name=key)
    publish(session, "storage")
    session.commit()
    return Response(status_code=204)
