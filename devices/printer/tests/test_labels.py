"""Actual raster/asset regressions. No USB driver is imported or called."""

from importlib.resources import files
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont
from sfl_printer.labels import HEIGHT, ICON_KEYS, WIDTH, badge_layout, render_label, wrapped_lines

NAMES = {
    "orientation": "Super Fab Lab Orientation",
    "policies": "Lab Policies",
    "3d-printer": "3D Printer",
    "laser-cutter": "Laser Cutter",
    "resin-printer": "Resin Printer",
    "waterjet": "Waterjet",
}


def badge(index=0, **changes):
    key = list(NAMES)[index % len(NAMES)]
    return {"training_type_id": str(uuid4()), "name": NAMES[key], "icon_key": key} | changes


def test_packaged_icons_are_verbatim_legacy_assets():
    original = Path(__file__).resolve().parents[3] / "frontend/public/training-icons"
    for key in ICON_KEYS:
        packaged = files("sfl_printer").joinpath("assets", f"{key}-icon.png").read_bytes()
        assert packaged == (original / f"{key}-icon.png").read_bytes()


@pytest.mark.parametrize("count", range(25))
def test_zero_to_twenty_four_badges_fit_fixed_monochrome_stock(count):
    payload = {"display_name": "Sample Visitor", "badges": [badge(i) for i in range(count)]}
    image = render_label(payload)
    assert image.size == (1109, 696) and image.mode == "RGB"
    colors = image.getcolors(maxcolors=3)
    assert colors is not None
    assert {color for _count, color in colors} == {(0, 0, 0), (255, 255, 255)}
    bounds = ImageChops.difference(image, Image.new("RGB", image.size, "white")).getbbox()
    assert bounds and 0 < bounds[0] < bounds[2] < WIDTH and 0 < bounds[1] < bounds[3] < HEIGHT
    if count:
        draw = ImageDraw.Draw(image)
        layout = badge_layout(draw, payload["badges"])
        side, _, columns, cell_width, cell_height, font, lines = layout
        assert side >= 12
        for parts in lines:
            bounds = draw.multiline_textbbox((0, 0), "\n".join(parts), font=font, spacing=2)
            assert bounds[2] - bounds[0] <= cell_width - side - 12
            assert bounds[3] - bounds[1] <= cell_height - 4


def test_original_icons_and_full_training_names_print_without_default_or_supplied_tiers(
    monkeypatch,
):
    seen = []
    original_text = ImageDraw.ImageDraw.text

    def record(draw, xy, text, *args, **kwargs):
        seen.append(text)
        return original_text(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    entries = [badge(i) for i in range(6)]
    image = render_label({"display_name": "Sample Visitor", "badges": entries})
    for name in NAMES.values():
        assert name in seen
    assert not any(
        tier in text.casefold()
        for text in seen
        for tier in ["apprentice", "operator", "trainer", "certifier"]
    )
    supplied = render_label(
        {
            "display_name": "Sample Visitor",
            "badges": [item | {"level": "certifier"} for item in entries],
        }
    )
    assert image.tobytes() == supplied.tobytes()
    # Known artwork must actually occupy each icon position, not just ship unused.
    layout = badge_layout(ImageDraw.Draw(image), entries)
    side, _, columns, cell_width, cell_height, _font, _lines = layout
    from sfl_printer.labels import BADGE_TOP, GUTTER, MARGIN

    for index in range(6):
        x = MARGIN + (index % columns) * (cell_width + GUTTER)
        y = BADGE_TOP + (index // columns) * cell_height + (cell_height - side) // 2
        assert image.crop((x, y, x + side, y + side)).convert("L").getextrema() == (0, 255)


def test_long_names_are_wrapped_in_full_instead_of_clipped():
    draw = ImageDraw.Draw(Image.new("RGB", (WIDTH, HEIGHT)))
    font = ImageFont.load_default(size=20)
    text = "Very long training name " * 4
    lines = wrapped_lines(draw, text.strip(), font, 160)
    assert " ".join(lines) == text.strip()
    assert all(draw.textlength(line, font=font) <= 160 for line in lines)
    long_word = "W" * 100
    assert "".join(wrapped_lines(draw, long_word, font, 160)) == long_word
    image = render_label(
        {"display_name": "W" * 200, "badges": [badge(i, name="W" * 100) for i in range(24)]}
    )
    assert image.size == (WIDTH, HEIGHT)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"display_name": "Bad\nName"},
        {"display_name": "X" * 201},
        {"display_name": "Sample", "badges": [badge()] * 25},
        {"display_name": "Sample", "badges": [None]},
        {"display_name": "Sample", "badges": [badge(name="X" * 101)]},
        {"display_name": "Sample", "badges": [badge(training_type_id="not-a-uuid")]},
        {"display_name": "Sample", "badges": [badge(icon_key="../../private")]},
        {"display_name": "Sample", "badges": [badge(name=True)]},
    ],
)
def test_invalid_payload_is_rejected_before_rendering(payload):
    with pytest.raises(ValueError):
        render_label(payload)


def test_unknown_safe_icon_does_not_fetch_resources_or_replace_the_training_name(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unknown icons must not become file or network lookups")

    monkeypatch.setattr("sfl_printer.labels.files", forbidden)
    image = render_label({"display_name": "Sample", "badges": [badge(icon_key="custom-training")]})
    assert image.size == (WIDTH, HEIGHT)


@pytest.mark.parametrize(
    "uri", ["https://printer.local", "tcp://printer.local:9100", "file:///tmp/output"]
)
def test_non_usb_output_is_rejected_before_loading_hardware_driver(uri):
    from sfl_printer.labels import usb_print

    with pytest.raises(ValueError, match="USB"):
        usb_print(
            Image.new("RGB", (WIDTH, HEIGHT), "white"),
            printer_uri=uri,
            model="QL-810W",
            label="62x100",
        )


@pytest.mark.parametrize("uploaded", [False, True])
def test_orange_fdm_artwork_remains_visible_on_monochrome_stock(uploaded):
    import io
    from importlib.resources import files

    from sfl_printer.labels import BADGE_TOP, BOTTOM, HEIGHT, MARGIN, render_label

    key = "training-icons/" + "a" * 32 + ".png" if uploaded else "3d-printer"
    payload = {
        "display_name": "FDM contrast",
        "badges": [
            {
                "training_type_id": "00000000-0000-0000-0000-000000000001",
                "name": "FDM Printing",
                "icon_key": key,
            }
        ],
    }
    data = {}
    if uploaded:
        with files("sfl_printer").joinpath("assets", "3d-printer-icon.png").open("rb") as stream:
            with Image.open(stream) as source:
                png = io.BytesIO()
                source.convert("RGBA").save(png, format="PNG")
                data[key] = png.getvalue()
    image = render_label(payload, icon_data=data)
    side = 72
    top = BADGE_TOP + (HEIGHT - BADGE_TOP - BOTTOM - side) // 2
    icon = image.crop((MARGIN, top, MARGIN + side, top + side)).convert("L")
    assert sum(pixel == 0 for pixel in icon.tobytes()) > 200
