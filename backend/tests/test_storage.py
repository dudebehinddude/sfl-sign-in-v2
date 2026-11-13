"""S3 adapter boundaries without accessing credentials, a real bucket or user images."""

import io
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from minio.error import S3Error
from sqlmodel import Session, select
from test_core import candidate as candidate
from test_core import login

from app.models import AuditEvent, User
from app.services import storage


class ObjectResponse(io.BytesIO):
    released = False

    def release_conn(self):
        self.released = True


class Bucket:
    def __init__(self):
        self.objects = {}
        self.responses = []

    def put_object(self, bucket, name, stream, size, content_type):
        assert bucket == "fixture-avatars" and content_type == "image/jpeg"
        self.objects[name] = stream.read(size)

    def get_object(self, bucket, name):
        if name not in self.objects:
            raise S3Error(
                response=None,
                code="NoSuchKey",
                message="Missing",
                resource=name,
                request_id="fixture",
                host_id="fixture",
            )
        response = ObjectResponse(self.objects[name])
        self.responses.append(response)
        return response


@pytest.fixture
def bucket(monkeypatch):
    store = Bucket()
    monkeypatch.setattr(storage, "storage_client", lambda: store)
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: SimpleNamespace(s3_bucket="fixture-avatars", avatar_max_bytes=32),
    )
    return store


def test_avatar_roundtrip_releases_http_connection(bucket):
    key = "a" * 32 + ".jpg"
    storage.put_avatar(key, b"fixture-jpeg")
    assert storage.get_avatar(key) == b"fixture-jpeg"
    assert bucket.responses[-1].closed and bucket.responses[-1].released


def test_missing_avatar_and_invalid_key_do_not_expose_storage_details(bucket):
    with pytest.raises(HTTPException) as missing:
        storage.get_avatar("b" * 32 + ".jpg")
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as invalid:
        storage.put_avatar("../../private", b"wrong")
    assert invalid.value.status_code == 404 and not bucket.objects


def test_unexpected_large_object_is_bounded_and_connection_released(bucket):
    key = "c" * 32 + ".jpg"
    bucket.objects[f"avatars/{key}"] = b"x" * 100
    with pytest.raises(HTTPException) as error:
        storage.get_avatar(key)
    assert error.value.status_code == 503
    assert bucket.responses[-1].closed and bucket.responses[-1].released


# The same fake bucket supports management operations while the API tests use
# real isolated PostgreSQL auth, CSRF, photo references, events and audit rows.
def _missing(name):
    return S3Error(
        response=None,
        code="NoSuchKey",
        message="Missing",
        resource=name,
        request_id="fixture",
        host_id="fixture",
    )


class ManagementBucket(Bucket):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.list_yields = 0
        self.iterator_closed = False
        self.declared_size = None

    def put_object(self, bucket, name, stream, size, content_type):
        self.calls.append(("put", name))
        assert bucket == "fixture-avatars"
        assert content_type in {"image/jpeg", "application/octet-stream"}
        self.objects[name] = stream.read(size)

    def stat_object(self, bucket, name):
        self.calls.append(("stat", name))
        if name not in self.objects:
            raise _missing(name)
        size = self.declared_size if self.declared_size is not None else len(self.objects[name])
        return SimpleNamespace(size=size)

    def get_object(self, bucket, name):
        self.calls.append(("get", name))
        return super().get_object(bucket, name)

    def remove_object(self, bucket, name):
        self.calls.append(("remove", name))
        del self.objects[name]

    def list_objects(self, bucket, *, prefix, recursive, start_after):
        self.calls.append(("list", prefix, start_after))
        assert recursive is True
        try:
            for name in sorted(self.objects):
                if not name.startswith(prefix) or (start_after and name <= start_after):
                    continue
                self.list_yields += 1
                yield SimpleNamespace(
                    object_name=name,
                    size=len(self.objects[name]),
                    last_modified=datetime(2026, 11, 9, tzinfo=UTC),
                    etag="fixture-etag",
                )
        finally:
            self.iterator_closed = True


@pytest.fixture
def management_bucket(monkeypatch):
    store = ManagementBucket()
    monkeypatch.setattr(storage, "storage_client", lambda: store)
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: SimpleNamespace(s3_bucket="fixture-avatars", avatar_max_bytes=32),
    )
    return store


@pytest.mark.parametrize(
    "key", ["", "/root", "a/../b", "a/./b", "a//b", "a\\b", "a\r\nb", "a\u2028b", "é" * 513]
)
def test_management_rejects_unsafe_keys_before_sdk(key, management_bucket):
    with pytest.raises(HTTPException) as error:
        storage.read_storage_object(key)
    assert error.value.status_code == 422
    assert not management_bucket.calls


def test_cursor_pagination_is_bounded_and_scoped(management_bucket):
    management_bucket.objects = {f"uploads/{i:04}": b"x" for i in range(2000)}
    rows, cursor = storage.list_storage_objects("uploads/", limit=2)
    assert [r["key"] for r in rows] == ["uploads/0000", "uploads/0001"]
    assert cursor == "uploads/0001"
    assert management_bucket.list_yields == 3 and management_bucket.iterator_closed
    rows, _ = storage.list_storage_objects("uploads/", cursor, 2)
    assert [r["key"] for r in rows] == ["uploads/0002", "uploads/0003"]
    before = len(management_bucket.calls)
    with pytest.raises(HTTPException) as invalid:
        storage.list_storage_objects("avatars/", cursor, 2)
    assert invalid.value.status_code == 422 and len(management_bucket.calls) == before


def test_management_reads_enforce_stat_and_stream_caps_and_release(management_bucket):
    key = "uploads/file"
    management_bucket.objects[key] = b"x" * (storage.MAX_STORAGE_BYTES + 1)
    with pytest.raises(HTTPException) as stat_error:
        storage.read_storage_object(key)
    assert stat_error.value.status_code == 413 and not management_bucket.responses
    # An object can change between stat and get: the actual stream is bounded too.
    management_bucket.declared_size = 1
    with pytest.raises(HTTPException) as stream_error:
        storage.read_storage_object(key)
    assert stream_error.value.status_code == 413
    assert management_bucket.responses[-1].closed and management_bucket.responses[-1].released


def test_management_missing_and_service_errors_are_safe(management_bucket, monkeypatch):
    with pytest.raises(HTTPException) as missing:
        storage.read_storage_object("uploads/missing")
    assert missing.value.status_code == 404

    def fail(*args, **kwargs):
        raise OSError("sensitive-host-and-credential-fixture")

    monkeypatch.setattr(management_bucket, "stat_object", fail)
    with pytest.raises(HTTPException) as unavailable:
        storage.read_storage_object("uploads/file")
    assert unavailable.value.status_code == 503
    assert "sensitive" not in str(unavailable.value.detail)


@pytest.mark.postgres
@pytest.mark.parametrize("name", [None, "operator", "viewer"])
def test_all_storage_routes_require_superadmin(candidate, management_bucket, name):
    client = candidate["client"]
    if name:
        login(client, name)
    requests = [
        client.get("/api/admin/storage/objects"),
        client.get("/api/admin/storage/object", params={"key": "uploads/a"}),
        client.post("/api/admin/storage/objects", files={"file": ("a", b"x")}),
        client.delete("/api/admin/storage/object", params={"key": "uploads/a"}),
    ]
    assert all(response.status_code == (403 if name else 401) for response in requests)
    assert not management_bucket.calls


@pytest.mark.postgres
def test_storage_roundtrip_attachment_and_audit(candidate, management_bucket):
    client = candidate["client"]
    login(client, "holder")
    upload = client.post(
        "/api/admin/storage/objects",
        files={"file": ("../../evil.svg", b"<svg onload='bad()'/>", "image/svg+xml")},
    )
    assert upload.status_code == 201, upload.text
    key = upload.json()["key"]
    assert key.startswith("uploads/") and key.endswith("/evil.svg")
    page = client.get("/api/admin/storage/objects").json()
    assert page["items"][0]["key"] == key and page["items"][0]["users"] == []
    assert set(page) == {"items", "prefix", "next_cursor", "limit", "upload_max_bytes"}
    assert "fixture-avatars" not in str(page)
    result = client.get("/api/admin/storage/object", params={"key": key})
    assert result.status_code == 200 and result.content == management_bucket.objects[key]
    assert result.headers["content-type"] == "application/octet-stream"
    assert result.headers["content-disposition"] == 'attachment; filename="evil.svg"'
    assert result.headers["x-content-type-options"] == "nosniff"
    assert result.headers["cache-control"] == "no-store"
    assert management_bucket.responses[-1].released
    assert client.delete("/api/admin/storage/object", params={"key": key}).status_code == 204
    assert key not in management_bucket.objects
    with Session(candidate["engine"]) as session:
        audits = session.exec(select(AuditEvent).where(AuditEvent.entity_type == "storage")).all()
        assert {row.action for row in audits} == {
            "storage.uploaded",
            "storage.downloaded",
            "storage.deleted",
        }
        assert all(row.actor_user_id == candidate["users"]["holder"] for row in audits)


@pytest.mark.postgres
def test_linked_avatar_is_visible_and_cannot_be_deleted(candidate, management_bucket):
    client = candidate["client"]
    login(client, "holder")
    key = "d" * 32 + ".jpg"
    management_bucket.objects[f"avatars/{key}"] = b"photo"
    with Session(candidate["engine"]) as session:
        user = session.get(User, candidate["users"]["member"])
        user.avatar_key = key
        session.add(user)
        session.commit()
    page = client.get("/api/admin/storage/objects", params={"prefix": "avatars/"})
    refs = page.json()["items"][0]["users"]
    assert refs[0]["id"] == str(candidate["users"]["member"])
    assert refs[0]["href"] == f"/admin/users/{candidate['users']['member']}"
    result = client.delete("/api/admin/storage/object", params={"key": f"avatars/{key}"})
    assert result.status_code == 409 and result.json()["detail"]["users"] == refs
    assert f"avatars/{key}" in management_bucket.objects
    assert not any(call[0] == "remove" for call in management_bucket.calls)


@pytest.mark.postgres
def test_request_caps_validation_and_csrf_precede_storage(candidate, management_bucket):
    client = candidate["client"]
    login(client, "holder")
    for size in [storage.MAX_STORAGE_BYTES + 1, storage.MAX_STORAGE_BYTES + 128 * 1024]:
        result = client.post("/api/admin/storage/objects", files={"file": ("large", b"x" * size)})
        assert result.status_code == 413, result.text
    assert (
        client.post(
            "/api/admin/storage/objects", files={"one": ("x", b"x"), "two": ("y", b"y")}
        ).status_code
        == 422
    )
    assert client.post("/api/admin/storage/objects", json={"file": "no"}).status_code == 422
    assert client.get("/api/admin/storage/objects", params={"limit": 1001}).status_code == 422
    assert client.get("/api/admin/storage/object", params={"key": "../unsafe"}).status_code == 422
    del client.headers["X-CSRF-Token"]
    assert client.post("/api/admin/storage/objects", files={"file": ("x", b"x")}).status_code == 403
    assert not management_bucket.calls
