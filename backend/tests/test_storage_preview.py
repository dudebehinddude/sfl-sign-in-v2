"""Authenticated preview safety with isolated PostgreSQL auth and fake S3 bytes."""

import io
import struct
import zlib

import pytest
from PIL import Image
from test_core import candidate as candidate
from test_core import login
from test_storage import management_bucket as management_bucket

from app.services import storage


def image_bytes(format="PNG", size=(40, 20)):
    image = Image.new("RGBA" if format == "PNG" else "RGB", size, (20, 80, 120))
    output = io.BytesIO()
    options = {}
    if format == "JPEG":
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = "private metadata fixture"
        options["exif"] = exif
    image.save(output, format=format, **options)
    return output.getvalue()


@pytest.mark.postgres
@pytest.mark.parametrize("name", [None, "operator", "viewer"])
def test_preview_requires_superadmin_before_storage(candidate, management_bucket, name):
    client = candidate["client"]
    if name:
        login(client, name)
    result = client.get("/api/admin/storage/preview", params={"key": "avatars/photo.jpg"})
    assert result.status_code == (403 if name else 401)
    assert not management_bucket.calls


@pytest.mark.postgres
@pytest.mark.parametrize("format", ["PNG", "JPEG"])
def test_preview_reencodes_supported_images_strips_metadata_and_limits_size(
    candidate, management_bucket, format
):
    client = candidate["client"]
    login(client, "holder")
    key = "training-icons/photo.png" if format == "PNG" else "avatars/photo.jpg"
    management_bucket.objects[key] = image_bytes(format, (1800, 900))
    result = client.get("/api/admin/storage/preview", params={"key": key})
    assert result.status_code == 200, result.text
    assert result.headers["content-type"] == "image/png"
    assert result.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in result.headers["cache-control"].split(", ")
    assert result.headers["cross-origin-resource-policy"] == "same-origin"
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.format == "PNG" and max(image.size) <= 1024
        assert image.size == ((1024, 512) if format == "PNG" else (512, 1024))
        assert not image.getexif() and "private metadata" not in str(image.info)
    thumb = client.get("/api/admin/storage/preview", params={"key": key, "size": 128})
    with Image.open(io.BytesIO(thumb.content)) as image:
        assert max(image.size) == 128
    assert all(response.closed and response.released for response in management_bucket.responses)


@pytest.mark.postgres
@pytest.mark.parametrize(
    "data", [b"<svg onload='evil()'/>", b"<html>not a raster</html>", b"broken", image_bytes("GIF")]
)
def test_preview_never_serves_markup_or_unsupported_bytes_as_an_image(
    candidate, management_bucket, data
):
    client = candidate["client"]
    login(client, "holder")
    management_bucket.objects["avatars/misleading.jpg"] = data
    result = client.get("/api/admin/storage/preview", params={"key": "avatars/misleading.jpg"})
    assert result.status_code == 415
    assert result.headers["content-type"].startswith("application/json")
    assert data not in result.content
    assert management_bucket.responses[-1].closed and management_bucket.responses[-1].released


@pytest.mark.postgres
def test_preview_byte_pixel_and_query_bounds(candidate, management_bucket):
    client = candidate["client"]
    login(client, "holder")
    key = "avatars/large.png"
    management_bucket.objects[key] = b"x" * (storage.MAX_STORAGE_BYTES + 1)
    assert client.get("/api/admin/storage/preview", params={"key": key}).status_code == 413
    assert not management_bucket.responses
    # Valid IHDR/CRC declares >20MP; the endpoint rejects before decompression.
    data = bytearray(image_bytes())
    data[16:24] = struct.pack(">II", 5001, 4000)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    management_bucket.objects[key] = bytes(data)
    assert client.get("/api/admin/storage/preview", params={"key": key}).status_code == 413
    calls = len(management_bucket.calls)
    for params in [{"key": "../private"}, {"key": key, "size": 1025}, {"key": key, "size": 1}]:
        assert client.get("/api/admin/storage/preview", params=params).status_code == 422
    assert len(management_bucket.calls) == calls


@pytest.mark.postgres
def test_png_alpha_survives_preview_and_missing_object_returns_safe_error(
    candidate, management_bucket
):
    client = candidate["client"]
    login(client, "holder")
    output = io.BytesIO()
    Image.new("RGBA", (8, 8), (255, 0, 0, 100)).save(output, format="PNG")
    management_bucket.objects["training-icons/alpha.png"] = output.getvalue()
    result = client.get("/api/admin/storage/preview", params={"key": "training-icons/alpha.png"})
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.mode == "RGBA" and image.getpixel((0, 0)) == (255, 0, 0, 100)
    missing = client.get("/api/admin/storage/preview", params={"key": "avatars/missing.jpg"})
    assert missing.status_code == 404 and missing.headers["content-type"].startswith(
        "application/json"
    )
