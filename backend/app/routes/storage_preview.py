"""Re-encoded raster previews through the authenticated app, never raw S3 markup."""

import io
import warnings

from fastapi import APIRouter, HTTPException, Query, Response
from PIL import Image, ImageOps

from ..security import DB, Superadmin
from ..services import storage

router = APIRouter(prefix="/api/admin/storage", tags=["storage"])
MAX_PREVIEW_PIXELS = 20_000_000


def raster_preview(data: bytes, size: int = 1024) -> bytes:
    if len(data) > storage.MAX_STORAGE_BYTES:
        raise HTTPException(413, "Preview images must be no larger than 5 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG"}:
                    raise HTTPException(415, "Preview is available for PNG and JPEG images only")
                if source.width * source.height > MAX_PREVIEW_PIXELS:
                    raise HTTPException(413, "Preview images must be no larger than 20 megapixels")
                if getattr(source, "n_frames", 1) != 1:
                    raise HTTPException(415, "Preview is available for still images only")
                source.load()
                image = ImageOps.exif_transpose(source)
                image.thumbnail((size, size), Image.Resampling.LANCZOS)
                # Re-encoding strips original metadata and guarantees a raster
                # response even when a misleading object extension was supplied.
                image = image.convert(
                    "RGBA"
                    if image.mode in {"RGBA", "LA", "P"} or "transparency" in image.info
                    else "RGB"
                )
                image.info.clear()
                output = io.BytesIO()
                image.save(output, format="PNG")
                return output.getvalue()
    except (
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(415, "This object is not a supported PNG or JPEG image") from None


@router.get(
    "/preview",
    response_class=Response,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
def preview(
    session: DB,
    actor: Superadmin,
    key: str = Query(max_length=1024),
    size: int = Query(1024, ge=64, le=1024),
):
    storage.validate_storage_key(key)
    session.rollback()
    data = storage.read_storage_object(key)
    return Response(
        raster_preview(data, size),
        media_type="image/png",
        headers={
            "Content-Disposition": 'inline; filename="preview.png"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
