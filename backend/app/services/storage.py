"""Avatar objects live in one private S3 bucket; users store only the object key."""

import io
import re
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import HTTPException
from minio import Minio
from minio.error import MinioException, S3Error
from urllib3 import PoolManager
from urllib3.exceptions import HTTPError
from urllib3.util import Timeout

from ..config import get_settings

AVATAR_KEY = re.compile(r"[a-f0-9]{32}\.jpg")
TRAINING_ICON_KEY = re.compile(r"training-icons/[a-f0-9]{32}\.png")
MAX_TRAINING_ICON_BYTES = 2 * 1024 * 1024


def _object_name(key: str) -> str:
    if not AVATAR_KEY.fullmatch(key):
        raise HTTPException(404, "Profile image not found")
    return f"avatars/{key}"


@lru_cache
def storage_client() -> Minio:
    settings = get_settings()
    endpoint = urlsplit(settings.s3_endpoint)
    if (
        endpoint.scheme not in {"http", "https"}
        or not endpoint.netloc
        or endpoint.username
        or endpoint.password
        or endpoint.path not in {"", "/"}
        or endpoint.query
        or endpoint.fragment
        or not settings.s3_access_key
        or not settings.s3_secret_key
    ):
        raise HTTPException(503, "Configure the S3 endpoint, bucket and credentials")
    return Minio(
        endpoint.netloc,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        secure=endpoint.scheme == "https",
        region=settings.s3_region,
        http_client=PoolManager(timeout=Timeout(connect=3, read=10), retries=False),
    )


def initialize_bucket() -> None:
    """Explicit provisioning command, rather than a side effect of a read."""
    client = storage_client()
    bucket = get_settings().s3_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def put_avatar(key: str, data: bytes) -> None:
    name = _object_name(key)
    try:
        storage_client().put_object(
            get_settings().s3_bucket,
            name,
            io.BytesIO(data),
            len(data),
            content_type="image/jpeg",
        )
    except (MinioException, HTTPError, OSError) as exc:
        raise HTTPException(503, "Profile image storage is temporarily unavailable") from exc


def get_avatar(key: str) -> bytes:
    name = _object_name(key)
    try:
        response = storage_client().get_object(get_settings().s3_bucket, name)
        try:
            data = response.read(get_settings().avatar_max_bytes + 1)
        finally:
            response.close()
            response.release_conn()
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchBucket"}:
            raise HTTPException(404, "Profile image not found") from exc
        raise HTTPException(503, "Profile image storage is temporarily unavailable") from exc
    except (MinioException, HTTPError, OSError) as exc:
        raise HTTPException(503, "Profile image storage is temporarily unavailable") from exc
    if len(data) > get_settings().avatar_max_bytes:
        raise HTTPException(503, "Stored profile image exceeds the permitted size")
    return data


def _training_icon_failure(exc: Exception) -> None:
    if isinstance(exc, S3Error) and exc.code in {"NoSuchKey", "NoSuchObject"}:
        raise HTTPException(404, "Training icon not found") from None
    raise HTTPException(503, "Training icon storage is temporarily unavailable") from None


def require_training_icon(key: str) -> None:
    if not TRAINING_ICON_KEY.fullmatch(key):
        raise HTTPException(422, "Use the key returned by training icon upload")
    try:
        storage_client().stat_object(get_settings().s3_bucket, key)
    except (MinioException, HTTPError, OSError) as exc:
        _training_icon_failure(exc)


def put_training_icon(data: bytes) -> str:
    from uuid import uuid4

    if len(data) > MAX_TRAINING_ICON_BYTES:
        raise HTTPException(413, "Training icon must be no larger than 2 MB")
    key = f"training-icons/{uuid4().hex}.png"
    try:
        storage_client().put_object(
            get_settings().s3_bucket, key, io.BytesIO(data), len(data), content_type="image/png"
        )
    except (MinioException, HTTPError, OSError) as exc:
        raise HTTPException(503, "Training icon storage is temporarily unavailable") from exc
    return key


def get_training_icon(key: str) -> bytes:
    if not TRAINING_ICON_KEY.fullmatch(key):
        raise HTTPException(404, "Training icon not found")
    try:
        response = storage_client().get_object(get_settings().s3_bucket, key)
        try:
            data = response.read(MAX_TRAINING_ICON_BYTES + 1)
        finally:
            response.close()
            response.release_conn()
    except (MinioException, HTTPError, OSError) as exc:
        _training_icon_failure(exc)
    if len(data) > MAX_TRAINING_ICON_BYTES:
        raise HTTPException(503, "Stored training icon exceeds the permitted size")
    return data


# Staff object management stays within the configured bucket. These limits are
# independent of the narrower public avatar route and its validated key format.
MAX_STORAGE_BYTES = 5 * 1024 * 1024
MAX_STORAGE_KEY_BYTES = 1024


def validate_storage_key(value: str, *, prefix: bool = False) -> str:
    import unicodedata

    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise HTTPException(422, "Object path contains invalid characters") from None
    if (
        (not value and not prefix)
        or size > MAX_STORAGE_KEY_BYTES
        or value.startswith("/")
        or "\\" in value
        or any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for c in value)
        or any(part in {".", ".."} for part in value.split("/"))
        or "//" in value
    ):
        raise HTTPException(
            422, "Use an object path without control characters or parent-directory segments"
        )
    return value


def safe_storage_filename(value: str) -> str:
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:160].strip(".") or "download"


def _storage_failure(exc: Exception) -> None:
    if isinstance(exc, S3Error) and exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
        raise HTTPException(404, "Object not found") from None
    raise HTTPException(503, "Object storage is temporarily unavailable") from None


def list_storage_objects(
    prefix: str = "", cursor: str | None = None, limit: int = 100
) -> tuple[list[dict], str | None]:
    from itertools import islice

    validate_storage_key(prefix, prefix=True)
    if not 1 <= limit <= 1000:
        raise HTTPException(422, "Choose between 1 and 1000 objects per page")
    if cursor is not None:
        validate_storage_key(cursor)
        if not cursor.startswith(prefix):
            raise HTTPException(422, "The cursor does not belong to this path prefix")
    try:
        iterator = storage_client().list_objects(
            get_settings().s3_bucket,
            prefix=prefix,
            recursive=True,
            start_after=cursor,
        )
        try:
            # The SDK reads at most two 1000-object S3 pages for this bounded
            # lookahead, rather than materializing the entire bucket iterator.
            rows = list(islice(iterator, limit + 1))
        finally:
            close = getattr(iterator, "close", None)
            if close:
                close()
        items = []
        for row in rows[:limit]:
            try:
                key = validate_storage_key(row.object_name)
            except HTTPException:
                raise HTTPException(503, "Storage returned an unsupported object path") from None
            items.append(
                {
                    "key": key,
                    "size": row.size or 0,
                    "last_modified": row.last_modified,
                    "etag": row.etag,
                }
            )
        return items, items[-1]["key"] if len(rows) > limit and items else None
    except (MinioException, HTTPError, OSError) as exc:
        _storage_failure(exc)


def read_storage_object(key: str) -> bytes:
    validate_storage_key(key)
    client, bucket = storage_client(), get_settings().s3_bucket
    try:
        stat = client.stat_object(bucket, key)
        if stat.size is None or stat.size > MAX_STORAGE_BYTES:
            raise HTTPException(413, "This object exceeds the 5 MB download limit")
        response = client.get_object(bucket, key)
        try:
            data = response.read(MAX_STORAGE_BYTES + 1)
        finally:
            response.close()
            response.release_conn()
    except (MinioException, HTTPError, OSError) as exc:
        _storage_failure(exc)
    if len(data) > MAX_STORAGE_BYTES:
        raise HTTPException(413, "This object exceeds the 5 MB download limit")
    return data


def upload_storage_object(filename: str, data: bytes) -> dict:
    from uuid import uuid4

    if len(data) > MAX_STORAGE_BYTES:
        raise HTTPException(413, "Upload a file no larger than 5 MB")
    key = f"uploads/{uuid4().hex}/{safe_storage_filename(filename)}"
    try:
        storage_client().put_object(
            get_settings().s3_bucket,
            key,
            io.BytesIO(data),
            len(data),
            content_type="application/octet-stream",
        )
    except (MinioException, HTTPError, OSError) as exc:
        _storage_failure(exc)
    return {"key": key, "size": len(data)}


def delete_storage_object(key: str) -> None:
    validate_storage_key(key)
    try:
        client, bucket = storage_client(), get_settings().s3_bucket
        client.stat_object(bucket, key)
        client.remove_object(bucket, key)
    except (MinioException, HTTPError, OSError) as exc:
        _storage_failure(exc)
