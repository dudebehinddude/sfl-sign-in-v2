"""Render binary training badges using the original artwork, with no training tiers."""

from __future__ import annotations

import io
import math
import re
import unicodedata
import warnings
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from uuid import UUID

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1109, 696  # Brother 62x100 printable dots, landscape before rotation.
MARGIN, GUTTER, BADGE_TOP, BOTTOM = 45, 24, 260, 24
ICON_KEYS = frozenset(
    {"orientation", "policies", "3d-printer", "laser-cutter", "resin-printer", "waterjet"}
)
MAX_ICON_BYTES = 2 * 1024 * 1024
MAX_ICON_SIDE = 512
UPLOADED_ICON_KEY = re.compile(r"training-icons/[a-f0-9]{32}\.png")
ICON_ALIASES = {
    "door-open": "orientation",
    "clipboard-check": "policies",
    "printer": "3d-printer",
    "zap": "laser-cutter",
    "droplets": "resin-printer",
    "waves": "waterjet",
}


def _text(value, limit, field):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(unicodedata.category(char) == "Cc" for char in value)
    ):
        raise ValueError(f"{field} requires 1 to {limit} characters without control characters")
    return " ".join(value.split())


def _validated(payload):
    if not isinstance(payload, dict):
        raise ValueError("Label must be an object")
    name = _text(payload.get("display_name"), 200, "display_name")
    badges = payload.get("badges", [])
    if not isinstance(badges, list) or len(badges) > 24:
        raise ValueError("Label supports at most 24 badge entries")
    result = []
    for badge in badges:
        if not isinstance(badge, dict):
            raise ValueError("Badge must be an object")
        identifier = badge.get("training_type_id")
        if not isinstance(identifier, str) or len(identifier) > 36:
            raise ValueError("Badge training_type_id must be a UUID")
        try:
            UUID(identifier)
        except ValueError as error:
            raise ValueError("Badge training_type_id must be a UUID") from error
        label = _text(badge.get("name"), 100, "Badge name")
        key = badge.get("icon_key")
        if not isinstance(key, str) or not (
            re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key) or UPLOADED_ICON_KEY.fullmatch(key)
        ):
            raise ValueError("Badge icon_key is invalid")
        result.append({"name": label, "icon_key": ICON_ALIASES.get(key, key)})
    return name, result


def uploaded_icon_keys(payload: dict) -> tuple[str, ...]:
    """Validate the complete label before requesting any public artwork."""
    _, badges = _validated(payload)
    return tuple(
        dict.fromkeys(
            badge["icon_key"] for badge in badges if UPLOADED_ICON_KEY.fullmatch(badge["icon_key"])
        )
    )


def decode_uploaded_icon(data: bytes) -> Image.Image:
    """Only bounded, single-frame PNG artwork; alpha is composited onto white."""
    if not isinstance(data, bytes) or not data or len(data) > MAX_ICON_BYTES:
        raise ValueError("Training icon must be a PNG no larger than 2 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if (
                    source.format != "PNG"
                    or getattr(source, "n_frames", 1) != 1
                    or not 1 <= source.width <= MAX_ICON_SIDE
                    or not 1 <= source.height <= MAX_ICON_SIDE
                ):
                    raise ValueError("Training icon must be a single PNG up to 512 by 512 pixels")
                icon = source.convert("RGBA")
                icon.load()
                return icon
    except (
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("Training icon is not a supported PNG") from error


def _uploaded_icon(data: bytes, side: int) -> Image.Image:
    icon = decode_uploaded_icon(data)
    icon.thumbnail((side, side), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (side, side), "white")
    canvas.alpha_composite(icon, ((side - icon.width) // 2, (side - icon.height) // 2))
    return canvas.convert("RGB")


def wrapped_lines(draw, text, font, width):
    """Wrap every character, including long unbroken names, without truncation."""
    lines = []
    remaining = text
    while remaining and draw.textlength(remaining, font=font) > width:
        low, high = 1, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if draw.textlength(remaining[:middle], font=font) <= width:
                low = middle
            else:
                high = middle - 1
        boundary = remaining.rfind(" ", 0, low + 1)
        boundary = boundary if boundary > 0 else low
        lines.append(remaining[:boundary].rstrip())
        remaining = remaining[boundary:].lstrip()
    if remaining:
        lines.append(remaining)
    return lines


def _name_style(draw, name):
    for size in range(84, 13, -2):
        font = ImageFont.load_default(size=size)
        lines = wrapped_lines(draw, name, font, WIDTH - 2 * MARGIN)
        bounds = draw.multiline_textbbox((0, 0), "\n".join(lines), font=font, spacing=5)
        if bounds[3] - bounds[1] <= 140:
            return font, lines
    raise ValueError("Display name does not fit the label")


def badge_layout(draw, badges):
    """Select the largest common text size, then the largest available icons."""
    if not badges:
        return None
    for size in range(28, 8, -1):
        font = ImageFont.load_default(size=size)
        options = []
        for columns in sorted({1, min(2, len(badges)), min(3, len(badges))}):
            rows = math.ceil(len(badges) / columns)
            cell_width = (WIDTH - 2 * MARGIN - (columns - 1) * GUTTER) // columns
            cell_height = (HEIGHT - BADGE_TOP - BOTTOM) // rows
            side = min(72, max(12, cell_height - 8), cell_width // 3)
            width = cell_width - side - 12
            lines = [wrapped_lines(draw, badge["name"], font, width) for badge in badges]
            heights = [
                draw.multiline_textbbox((0, 0), "\n".join(parts), font=font, spacing=2)[3]
                - draw.multiline_textbbox((0, 0), "\n".join(parts), font=font, spacing=2)[1]
                for parts in lines
            ]
            if all(height <= cell_height - 4 for height in heights):
                options.append((side, -columns, columns, cell_width, cell_height, font, lines))
        if options:
            return max(options, key=lambda option: option[:2])
    raise ValueError("Training names do not fit the label")


@lru_cache(maxsize=192)
def _icon(key, side):
    canvas = Image.new("RGBA", (side, side), "white")
    if key in ICON_KEYS:
        # Whitelisted package resources only. Payloads cannot supply paths or URLs.
        with files("sfl_printer").joinpath("assets", f"{key}-icon.png").open("rb") as stream:
            with Image.open(stream) as source:
                icon = source.convert("RGBA")
        icon.thumbnail((side, side), Image.Resampling.LANCZOS)
        canvas.alpha_composite(icon, ((side - icon.width) // 2, (side - icon.height) // 2))
    else:
        # Unknown metadata still prints the full name, without inventing another training.
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((1, 1, side - 2, side - 2), outline="black", width=1)
        draw.text(
            (side / 2, side / 2),
            "?",
            anchor="mm",
            fill="black",
            font=ImageFont.load_default(size=max(9, side // 2)),
        )
    return canvas.convert("RGB")


def render_label(payload: dict, icon_data: Mapping[str, bytes] | None = None) -> Image.Image:
    name, badges = _validated(payload)
    icon_data = {} if icon_data is None else icon_data
    if (
        not isinstance(icon_data, Mapping)
        or len(icon_data) > 24
        or any(
            not isinstance(key, str) or not UPLOADED_ICON_KEY.fullmatch(key) for key in icon_data
        )
    ):
        raise ValueError("Uploaded artwork must use valid training icon keys")
    for key in uploaded_icon_keys(payload):
        if key not in icon_data:
            raise ValueError("Uploaded training artwork is unavailable")
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (MARGIN, 30), "Charlotte Super Fab Lab", fill="black", font=ImageFont.load_default(size=35)
    )
    draw.line((MARGIN, 85, WIDTH - MARGIN, 85), fill="black", width=3)
    font, lines = _name_style(draw, name)
    draw.multiline_text(
        (WIDTH / 2, 174),
        "\n".join(lines),
        fill="black",
        font=font,
        anchor="mm",
        align="center",
        spacing=5,
    )
    layout = badge_layout(draw, badges)
    if layout:
        side, _, columns, cell_width, cell_height, font, lines = layout
        for index, badge in enumerate(badges):
            x = MARGIN + (index % columns) * (cell_width + GUTTER)
            y = BADGE_TOP + (index // columns) * cell_height
            key = badge["icon_key"]
            artwork = (
                _uploaded_icon(icon_data[key], side)
                if UPLOADED_ICON_KEY.fullmatch(key)
                else _icon(key, side)
            )
            image.paste(artwork, (x, y + (cell_height - side) // 2))
            text = "\n".join(lines[index])
            bounds = draw.multiline_textbbox((0, 0), text, font=font, spacing=2)
            draw.multiline_text(
                (x + side + 12, y + (cell_height - (bounds[3] - bounds[1])) / 2 - bounds[1]),
                text,
                fill="black",
                font=font,
                spacing=2,
            )
    # RGB remains the driver contract; only black/white pixels reach monochrome stock.
    return image.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")


def usb_print(image: Image.Image, *, printer_uri: str, model: str, label: str) -> str:
    if not printer_uri.startswith(("usb://", "/dev/usb/")):
        raise ValueError("Use an explicit USB printer URI or /dev/usb device")
    # Optional hardware dependency is loaded only for a deliberately configured USB run.
    from brother_ql.backends.helpers import send
    from brother_ql.conversion import convert
    from brother_ql.raster import BrotherQLRaster

    raster = BrotherQLRaster(model)
    instructions = convert(raster, [image], label=label, rotate=90, cut=True)
    backend = "pyusb" if printer_uri.startswith("usb://") else "linux_kernel"
    outcome = send(
        instructions, printer_identifier=printer_uri, backend_identifier=backend, blocking=True
    )
    return "printed" if outcome.get("did_print") else "uncertain"
