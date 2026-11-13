"""Real PostgreSQL references and a fake S3 bucket, with real image codecs."""

import io
import re
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, PngImagePlugin
from sqlmodel import Session, select
from test_core import candidate as candidate
from test_core import login
from test_storage import ManagementBucket

from app.models import TrainingType
from app.services import storage


class IconBucket(ManagementBucket):
    def put_object(self, bucket, name, stream, size, content_type):
        self.calls.append(("put", name))
        assert bucket == "fixture-avatars" and content_type == "image/png"
        self.objects[name] = stream.read(size)


@pytest.fixture
def icon_bucket(monkeypatch):
    store = IconBucket()
    monkeypatch.setattr(storage, "storage_client", lambda: store)
    monkeypatch.setattr(
        storage,
        "get_settings",
        lambda: SimpleNamespace(s3_bucket="fixture-avatars", avatar_max_bytes=32),
    )
    return store


def picture(format="PNG"):
    image = Image.new(
        "RGBA" if format in {"PNG", "WEBP"} else "RGB",
        (900, 700),
        (40, 80, 120, 64) if format in {"PNG", "WEBP"} else (40, 80, 120),
    )
    output = io.BytesIO()
    if format == "PNG":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private-note", "not published")
        image.save(output, format=format, pnginfo=metadata)
    elif format == "WEBP":
        image.save(output, format=format, lossless=True)
    else:
        image.save(output, format=format)
    return output.getvalue()


def upload(client, data=None, mime="image/png"):
    return client.post(
        "/api/admin/training-icons",
        files={"file": ("icon.png", picture() if data is None else data, mime)},
    )


@pytest.mark.postgres
@pytest.mark.parametrize("name", ["holder", "viewer"])
@pytest.mark.parametrize(
    "format,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_admin_upload_reencodes_public_preview_preserving_alpha(
    candidate, icon_bucket, name, format, mime
):
    client = candidate["client"]
    login(client, name)
    result = upload(client, picture(format), mime)
    assert result.status_code == 201, result.text
    payload = result.json()
    assert re.fullmatch(r"training-icons/[a-f0-9]{32}\.png", payload["icon_key"])
    assert payload["icon_url"] == f"/media/{payload['icon_key']}"
    with Session(candidate["engine"]) as session:
        assert not session.exec(
            select(TrainingType).where(TrainingType.icon_key == payload["icon_key"])
        ).first()
    # Public preview is intentionally available before a definition references it.
    client.post("/api/auth/logout")
    response = client.get(payload["icon_url"])
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(response.content)) as decoded:
        assert decoded.format == "PNG" and max(decoded.size) == 512
        assert decoded.mode == "RGBA"
        assert decoded.getpixel((0, 0))[3] == (64 if format in {"PNG", "WEBP"} else 255)
        assert "private-note" not in decoded.info and "exif" not in decoded.info


@pytest.mark.postgres
@pytest.mark.parametrize("name,status", [(None, 401), ("operator", 403)])
def test_icon_upload_auth_precedes_storage(candidate, icon_bucket, name, status):
    client = candidate["client"]
    if name:
        login(client, name)
    assert upload(client).status_code == status
    assert not icon_bucket.calls


@pytest.mark.postgres
def test_icon_validation_size_pixels_mime_and_csrf(candidate, icon_bucket):
    client = candidate["client"]
    login(client, "holder")
    for data, mime in [
        (b"<svg onload='bad()'/>", "image/png"),
        (b"not JPEG", "image/jpeg"),
        (picture(), "text/html"),
    ]:
        assert upload(client, data, mime).status_code == 422
    for size in [storage.MAX_TRAINING_ICON_BYTES + 1, storage.MAX_TRAINING_ICON_BYTES + 128 * 1024]:
        assert upload(client, b"x" * size).status_code == 413
    # A valid PNG header advertising >20 MP must be rejected before image load.
    original = picture()
    header = struct.pack(">IIBBBBB", 5000, 4001, 8, 6, 0, 0, 0)
    oversized = (
        original[:8]
        + struct.pack(">I", 13)
        + b"IHDR"
        + header
        + struct.pack(">I", zlib.crc32(b"IHDR" + header))
        + original[33:]
    )
    too_many_pixels = upload(client, oversized)
    assert too_many_pixels.status_code == 422
    assert "20 megapixels" in too_many_pixels.json()["detail"]
    assert client.post("/api/admin/training-icons", json={"file": "no"}).status_code == 422
    del client.headers["X-CSRF-Token"]
    assert upload(client).status_code == 403
    assert not icon_bucket.calls


@pytest.mark.postgres
def test_uploaded_reference_exists_before_save_and_used_icon_cannot_be_deleted(
    candidate, icon_bucket
):
    client = candidate["client"]
    login(client, "holder")
    missing = "training-icons/" + "a" * 32 + ".png"
    assert (
        client.post(
            "/api/admin/training-types", json={"name": "Missing", "icon_key": missing}
        ).status_code
        == 422
    )
    id = candidate["training_id"]
    assert (
        client.patch(f"/api/admin/training-types/{id}", json={"icon_key": missing}).status_code
        == 422
    )
    for invalid in [
        "training-icons/bad.png",
        " training-icons/" + "a" * 32 + ".png",
        "uploads/" + "a" * 32 + ".png",
    ]:
        assert (
            client.patch(f"/api/admin/training-types/{id}", json={"icon_key": invalid}).status_code
            == 422
        )
    payload = upload(client).json()
    updated = client.patch(
        f"/api/admin/training-types/{id}",
        json={"name": "Uploaded Machine", "icon_key": payload["icon_key"]},
    )
    assert updated.status_code == 200 and updated.json()["icon_key"] == payload["icon_key"]
    created = client.post(
        "/api/admin/training-types",
        json={"name": "Another Machine", "icon_key": payload["icon_key"]},
    )
    assert created.status_code == 201
    result = client.delete("/api/admin/storage/object", params={"key": payload["icon_key"]})
    assert result.status_code == 409
    assert result.json()["detail"]["users"] == []
    assert (
        "Uploaded Machine" in result.json()["detail"]["message"]
        and "Another Machine" in result.json()["detail"]["message"]
    )
    assert payload["icon_key"] in icon_bucket.objects
    assert not any(call[0] == "remove" for call in icon_bucket.calls)
    for definition_id in [id, created.json()["id"]]:
        assert (
            client.patch(
                f"/api/admin/training-types/{definition_id}", json={"icon_key": "orientation"}
            ).status_code
            == 200
        )
    assert (
        client.delete("/api/admin/storage/object", params={"key": payload["icon_key"]}).status_code
        == 204
    )


@pytest.mark.postgres
def test_missing_public_icon_and_storage_outage_are_distinct(candidate, icon_bucket, monkeypatch):
    client = candidate["client"]
    assert client.get("/media/training-icons/not-valid.png").status_code == 404
    key = "training-icons/" + "b" * 32 + ".png"
    assert client.get(f"/media/{key}").status_code == 404

    def fail(*args, **kwargs):
        raise OSError("private-storage-host-or-credential")

    monkeypatch.setattr(icon_bucket, "get_object", fail)
    result = client.get(f"/media/{key}")
    assert result.status_code == 503 and "private-storage" not in result.text
    login(client, "holder")
    monkeypatch.setattr(icon_bucket, "stat_object", fail)
    response = client.patch(
        f"/api/admin/training-types/{candidate['training_id']}", json={"icon_key": key}
    )
    assert response.status_code == 503 and "private-storage" not in response.text
    assert (
        client.post(
            "/api/admin/training-types", json={"name": "Unavailable", "icon_key": key}
        ).status_code
        == 503
    )
    with Session(candidate["engine"]) as session:
        assert session.get(TrainingType, candidate["training_id"]).icon_key == "laser-cutter"


def test_public_icon_stream_is_bounded_and_released(icon_bucket):
    key = "training-icons/" + "c" * 32 + ".png"
    icon_bucket.objects[key] = b"x" * (storage.MAX_TRAINING_ICON_BYTES + 1)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as failure:
        storage.get_training_icon(key)
    assert failure.value.status_code == 503
    assert icon_bucket.responses[-1].closed and icon_bucket.responses[-1].released


@pytest.mark.postgres
def test_original_policies_png_filename_contains_webp_and_uploads_as_png(candidate, icon_bucket):
    # Exact bytes copied from frontend/public/training-icons/policies-icon.png.
    original = (Path(__file__).parent / "fixtures/original-policies.webp").read_bytes()
    with Image.open(io.BytesIO(original)) as source:
        assert source.format == "WEBP"
    client = candidate["client"]
    login(client, "holder")
    result = upload(client, original, "image/png")
    assert result.status_code == 201, result.text
    response = client.get(result.json()["icon_url"])
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(response.content)) as normalized:
        assert normalized.format == "PNG" and max(normalized.size) <= 512


def test_missing_and_empty_icon_keep_original_orientation_default():
    from app.schemas import TrainingTypeInput, TrainingTypePatch

    assert TrainingTypeInput(name="Default").icon_key == "orientation"
    assert TrainingTypeInput(name="Empty", icon_key="").icon_key == "orientation"
    assert TrainingTypePatch(icon_key="").icon_key == "orientation"
