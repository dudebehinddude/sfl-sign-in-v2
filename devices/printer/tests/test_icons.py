"""Public media boundaries; no network server, storage credentials or USB output."""

import io
import json
from uuid import uuid4

import pytest
from PIL import Image
from sfl_printer.client import handle_message
from sfl_printer.icons import IconCache, IconFetchError, NoRedirect
from sfl_printer.labels import MAX_ICON_BYTES, _uploaded_icon, decode_uploaded_icon, render_label

KEY = "training-icons/" + "a" * 32 + ".png"


def png(size=(32, 32), color=(255, 0, 0, 128), format="PNG"):
    data = io.BytesIO()
    image = Image.new("RGBA" if format == "PNG" else "RGB", size, color)
    image.save(data, format=format)
    return data.getvalue()


def payload(key=KEY):
    return {
        "display_name": "Sample Visitor",
        "badges": [
            {"training_type_id": str(uuid4()), "name": "Uploaded training", "icon_key": key},
        ],
    }


class Response(io.BytesIO):
    def __init__(self, data, url, length=None):
        super().__init__(data)
        self.url = url
        self.headers = {} if length is None else {"Content-Length": str(length)}
        self.bytes_read = 0

    def geturl(self):
        return self.url

    def read1(self, size=-1):
        data = super().read(size)
        self.bytes_read += len(data)
        return data


class Opener:
    def __init__(self, data=None, *, length=None, redirected=None):
        self.data = png() if data is None else data
        self.length = length
        self.redirected = redirected
        self.calls = []
        self.responses = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        response = Response(self.data, self.redirected or request.full_url, self.length)
        self.responses.append(response)
        return response


@pytest.mark.parametrize(
    "key",
    [
        "https://attacker.invalid/icon.png",
        "//attacker.invalid/icon.png",
        "../training-icons/" + "a" * 32 + ".png",
        "training-icons/../private",
        "training-icons/" + "a" * 32 + ".png?token=x",
        "training-icons/" + "a" * 32 + ".png#fragment",
        "training-icons/" + "A" * 32 + ".png",
        "training-icons/%2e%2e/icon.png",
        "training-icons/" + "a" * 32 + ".jpg",
        "training-icons\\" + "a" * 32 + ".png",
    ],
)
def test_untrusted_keys_never_become_requests_or_paths(key):
    opener = Opener()
    cache = IconCache("http://lab.local:8099", opener=opener)
    with pytest.raises(IconFetchError):
        cache.get(key)
    with pytest.raises(ValueError):
        render_label(payload(key), {key: png()})
    assert opener.calls == []


def test_fetch_is_same_origin_public_bounded_and_cached():
    opener = Opener()
    cache = IconCache("ws://lab.local:8099", opener=opener)
    assert cache.load((KEY, KEY)) == {KEY: opener.data}
    assert cache.get(KEY) == opener.data
    assert len(opener.calls) == 1
    request, timeout = opener.calls[0]
    assert request.full_url == "http://lab.local:8099/media/" + KEY
    assert request.get_method() == "GET" and request.get_header("Authorization") is None
    assert timeout <= cache.SOCKET_TIMEOUT
    assert opener.responses[0].closed


def test_redirects_are_rejected_instead_of_fetching_an_arbitrary_url():
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "http://attacker.invalid") is None
    opener = Opener(redirected="http://attacker.invalid/icon.png")
    cache = IconCache("http://lab.local", opener=opener)
    with pytest.raises(IconFetchError, match="redirect"):
        cache.get(KEY)
    assert len(opener.calls) == 1 and opener.responses[0].closed
    assert not cache.cache


@pytest.mark.parametrize("length", [MAX_ICON_BYTES + 1, "-1", "not-a-number"])
def test_declared_oversize_or_invalid_length_is_rejected_before_body(length):
    opener = Opener(length=length)
    with pytest.raises(IconFetchError):
        IconCache("http://lab.local", opener=opener).get(KEY)
    assert opener.responses[0].bytes_read == 0 and opener.responses[0].closed


def test_stream_without_length_is_bounded_even_if_the_object_is_oversized():
    opener = Opener(data=b"x" * (MAX_ICON_BYTES + 100))
    cache = IconCache("http://lab.local", opener=opener)
    with pytest.raises(IconFetchError, match="size"):
        cache.get(KEY)
    assert opener.responses[0].bytes_read == MAX_ICON_BYTES + 1
    assert opener.responses[0].closed and not cache.cache


def test_timeout_failure_is_not_cached_or_retried():
    class Timeout:
        def __init__(self):
            self.calls = 0

        def open(self, *args, **kwargs):
            self.calls += 1
            raise TimeoutError("private-server-detail-fixture")

    opener = Timeout()
    cache = IconCache("http://lab.local", opener=opener)
    with pytest.raises(IconFetchError, match="unavailable") as error:
        cache.get(KEY)
    assert "private-server" not in str(error.value)
    assert opener.calls == 1 and not cache.cache


def test_total_deadline_applies_to_all_icons_for_one_label():
    now = [0]

    class SlowOpener(Opener):
        def open(self, request, timeout):
            response = super().open(request, timeout)
            now[0] += 6
            return response

    opener = SlowOpener()
    cache = IconCache("http://lab.local", opener=opener, clock=lambda: now[0])
    second = "training-icons/" + "b" * 32 + ".png"
    with pytest.raises(IconFetchError, match="timed out"):
        cache.load((KEY, second))
    assert len(opener.calls) == 2
    assert opener.responses[-1].closed
    assert opener.calls[-1][1] <= 4


def test_cache_is_lru_and_bounded_by_both_entry_count_and_bytes():
    opener = Opener()
    cache = IconCache("http://lab.local", opener=opener)
    cache.MAX_ENTRIES = 2
    cache.MAX_BYTES = 2 * len(opener.data)
    keys = ["training-icons/" + character * 32 + ".png" for character in "abc"]
    cache.get(keys[0])
    cache.get(keys[1])
    cache.get(keys[0])
    cache.get(keys[2])
    assert list(cache.cache) == [keys[0], keys[2]]
    assert cache.cache_bytes <= cache.MAX_BYTES
    cache.get(keys[1])
    assert len(opener.calls) == 4 and len(cache.cache) == 2
    # A byte limit smaller than three entries also evicts while entries remain available.
    cache.MAX_ENTRIES = 16
    cache.get(keys[0])
    cache.get(keys[2])
    assert len(cache.cache) == 2 and cache.cache_bytes == 2 * len(opener.data)


@pytest.mark.parametrize(
    "data",
    [b"not-png", png((513, 2)), png(format="JPEG", color=(255, 0, 0)), b"x" * (MAX_ICON_BYTES + 1)],
)
def test_uploaded_artwork_must_be_a_bounded_png(data):
    with pytest.raises(ValueError):
        decode_uploaded_icon(data)
    with pytest.raises(ValueError):
        render_label(payload(), {KEY: data})


def test_transparent_png_keeps_color_until_final_label_conversion():
    art = png(color=(255, 0, 0, 128))
    composited = _uploaded_icon(art, 32)
    assert composited.getpixel((16, 16)) == (255, 127, 127)
    transparent = _uploaded_icon(png(color=(0, 0, 0, 0)), 32)
    assert transparent.getpixel((16, 16)) == (255, 255, 255)
    image = render_label(payload(), {KEY: art})
    assert image.mode == "RGB" and image.size == (1109, 696)
    assert {color for _, color in image.getcolors(maxcolors=3)} == {(0, 0, 0), (255, 255, 255)}


def test_bad_artwork_never_reaches_usb_and_failed_ack_does_not_replay():
    class Socket:
        sent = []

        def send(self, message):
            self.sent.append(json.loads(message))

    socket = Socket()
    output = []
    message = json.dumps({"type": "label", "id": str(uuid4()), "label": payload()})
    opener = Opener(data=b"invalid")
    handle_message(
        socket,
        message,
        lambda image: output.append(image) or "printed",
        icons=IconCache("http://lab.local", opener=opener),
    )
    assert not output and len(opener.calls) == 1
    assert socket.sent[-1]["status"] == "failed"
    assert "USB" in socket.sent[-1]["error"]
    # A new connection/cache has nothing queued; only a new message can trigger work.
    assert len(output) == 0


def test_uploaded_artwork_ack_loss_never_repeats_physical_output():
    class Socket:
        def send(self, message):
            raise OSError("ack lost")

    output = []
    message = json.dumps({"type": "label", "id": str(uuid4()), "label": payload()})
    opener = Opener()
    with pytest.raises(OSError):
        handle_message(
            Socket(),
            message,
            lambda image: output.append(image) or "printed",
            icons=IconCache("http://lab.local", opener=opener),
        )
    assert len(output) == 1 and len(opener.calls) == 1


def test_renderer_keeps_incoming_badge_order_instead_of_sorting_or_using_asset_order(monkeypatch):
    from sfl_printer import labels

    original = labels._icon
    seen = []

    def record(key, side):
        seen.append(key)
        return original(key, side)

    monkeypatch.setattr(labels, "_icon", record)
    order = ["waterjet", "policies", "orientation", "3d-printer", "laser-cutter", "resin-printer"]
    data = payload()
    data["badges"] = [
        {"training_type_id": str(uuid4()), "name": key, "icon_key": key} for key in order
    ]
    render_label(data)
    assert seen == order


def test_uploaded_icon_prints_and_acknowledges_once_and_driver_failure_stays_unknown():
    class Socket:
        def __init__(self):
            self.sent = []

        def send(self, message):
            self.sent.append(json.loads(message))

    socket = Socket()
    output = []
    opener = Opener()
    cache = IconCache("http://lab.local", opener=opener)
    message = json.dumps({"type": "label", "id": str(uuid4()), "label": payload()})
    handle_message(socket, message, lambda image: output.append(image) or "printed", icons=cache)
    assert len(output) == 1 and socket.sent[0]["status"] == "printed"

    def fail(image):
        output.append(image)
        raise OSError("driver could have started physical output")

    handle_message(socket, message, fail, icons=cache)
    assert len(output) == 2 and socket.sent[-1]["status"] == "unknown"
    assert len(opener.calls) == 1


def test_complete_payload_is_validated_before_fetching_any_artwork():
    class Socket:
        def __init__(self):
            self.sent = []

        def send(self, message):
            self.sent.append(json.loads(message))

    socket = Socket()
    data = payload()
    data["badges"].append({"training_type_id": "bad-id", "name": "Bad", "icon_key": KEY})
    opener = Opener()
    output = []
    handle_message(
        socket,
        json.dumps({"type": "label", "id": str(uuid4()), "label": data}),
        lambda image: output.append(image),
        icons=IconCache("http://lab.local", opener=opener),
    )
    assert not opener.calls and not output and socket.sent[0]["status"] == "failed"


def test_missing_uploaded_artwork_does_not_silently_print_placeholder():
    with pytest.raises(ValueError, match="unavailable"):
        render_label(payload())
