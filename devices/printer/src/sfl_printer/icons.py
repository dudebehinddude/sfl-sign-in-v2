"""Bounded public artwork retrieval from this printer's configured app origin."""

from __future__ import annotations

import time
from collections import OrderedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .labels import MAX_ICON_BYTES, UPLOADED_ICON_KEY, decode_uploaded_icon


class IconFetchError(ValueError):
    """An artwork failure happens before USB output and is safe to acknowledge."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def app_origin(server: str) -> str:
    parts = urlsplit(server)
    if (
        parts.scheme not in {"http", "https", "ws", "wss"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ValueError(
            "PRINTER_SERVER_URL must be an http(s)/ws(s) origin without credentials, path or query"
        )
    return urlunsplit(
        ("https" if parts.scheme in {"https", "wss"} else "http", parts.netloc, "", "", "")
    )


class IconCache:
    MAX_ENTRIES = 16
    MAX_BYTES = 8 * 1024 * 1024
    SOCKET_TIMEOUT = 5
    TOTAL_TIMEOUT = 10

    def __init__(self, origin: str, *, opener=None, clock=time.monotonic):
        self.origin = app_origin(origin)
        self.opener = opener or build_opener(NoRedirect())
        self.clock = clock
        self.cache: OrderedDict[str, bytes] = OrderedDict()
        self.cache_bytes = 0

    def load(self, keys: tuple[str, ...]) -> dict[str, bytes]:
        """One deadline covers all artwork for a label, including cache misses."""
        if len(keys) > 24 or any(
            not isinstance(key, str) or not UPLOADED_ICON_KEY.fullmatch(key) for key in keys
        ):
            raise IconFetchError("Invalid uploaded training icon keys")
        deadline = self.clock() + self.TOTAL_TIMEOUT
        return {key: self.get(key, deadline=deadline) for key in dict.fromkeys(keys)}

    def get(self, key: str, *, deadline: float | None = None) -> bytes:
        if not isinstance(key, str) or not UPLOADED_ICON_KEY.fullmatch(key):
            raise IconFetchError("Invalid uploaded training icon key")
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        url = self.origin + "/media/" + key
        try:
            request = Request(url, headers={"Accept": "image/png"})
            deadline = (
                min(deadline, self.clock() + self.TOTAL_TIMEOUT)
                if deadline is not None
                else self.clock() + self.TOTAL_TIMEOUT
            )
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise IconFetchError("Training icon request timed out")
            with self.opener.open(request, timeout=min(self.SOCKET_TIMEOUT, remaining)) as response:
                # Defense in depth for injected/custom openers too. Never follow
                # an artwork redirect to a different host or path.
                if response.geturl() != url:
                    raise IconFetchError("Training icon redirects are not permitted")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdecimal() or int(length) > MAX_ICON_BYTES):
                    raise IconFetchError("Training icon exceeds its size limit")
                data = bytearray()
                while True:
                    if self.clock() > deadline:
                        raise IconFetchError("Training icon request timed out")
                    # read1 performs at most one underlying socket read, allowing
                    # the total deadline to be checked even for slow responses.
                    chunk = response.read1(min(64 * 1024, MAX_ICON_BYTES + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_ICON_BYTES:
                        raise IconFetchError("Training icon exceeds its size limit")
                if self.clock() > deadline:
                    raise IconFetchError("Training icon request timed out")
            value = bytes(data)
            decode_uploaded_icon(value)
        except IconFetchError:
            raise
        except (HTTPError, URLError, OSError, ValueError) as error:
            # No payload URL, token or server response is included in the ACK/log.
            raise IconFetchError("Training artwork is unavailable") from error
        while self.cache and (
            len(self.cache) >= self.MAX_ENTRIES or self.cache_bytes + len(value) > self.MAX_BYTES
        ):
            _, removed = self.cache.popitem(last=False)
            self.cache_bytes -= len(removed)
        self.cache[key] = value
        self.cache_bytes += len(value)
        return value
