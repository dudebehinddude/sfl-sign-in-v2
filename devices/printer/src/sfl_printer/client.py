"""Receive live labels over a normal WebSocket and send them to one USB printer."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from dotenv import load_dotenv
from websockets.sync.client import connect

from .icons import IconCache, IconFetchError, app_origin
from .labels import render_label, uploaded_icon_keys, usb_print

logger = logging.getLogger("sfl_printer")


def handle_message(socket, message: str | bytes, output, *, icons: IconCache | None = None) -> None:
    payload = json.loads(message)
    if payload.get("type") == "ping":
        socket.send(json.dumps({"type": "pong"}))
        return
    if payload.get("type") != "label":
        return
    label_id = str(UUID(str(payload["id"])))
    detail = None
    try:
        keys = uploaded_icon_keys(payload["label"])
        if keys and icons is None:
            raise IconFetchError("Uploaded training artwork is unavailable")
        artwork = icons.load(keys) if icons else {}
        image = render_label(payload["label"], icon_data=artwork)
    except IconFetchError:
        status, detail = "failed", "Training artwork could not be loaded; label was not sent to USB"
    except (KeyError, TypeError, ValueError) as error:
        status, detail = "failed", f"Invalid label ({type(error).__name__})"
    else:
        try:
            result = output(image)
            status = "printed" if result == "printed" else "unknown"
            if status == "unknown":
                detail = "USB output was not confirmed; check the printer before reprinting"
        except Exception as error:
            # A driver failure may occur after physical output has already begun.
            status, detail = "unknown", f"USB output was not confirmed ({type(error).__name__})"
    socket.send(json.dumps({"type": "ack", "id": label_id, "status": status, "error": detail}))


def websocket_url(server: str) -> tuple[str, str]:
    origin = app_origin(server)
    parts = urlsplit(origin)
    return urlunsplit(
        ("wss" if parts.scheme == "https" else "ws", parts.netloc, "/ws/printer", "", "")
    ), origin


def run() -> None:
    server = os.environ.get("PRINTER_SERVER_URL", "")
    uri = os.environ.get("PRINTER_USB_URI", "")
    if not server or not uri:
        raise ValueError("Set PRINTER_SERVER_URL and PRINTER_USB_URI before running")
    url, origin = websocket_url(server)
    icons = IconCache(origin)
    if not uri.startswith(("usb://", "/dev/usb/")):
        raise ValueError("PRINTER_USB_URI must identify a USB device")
    if importlib.util.find_spec("brother_ql") is None:
        raise ValueError("Install the printer agent USB extra before subscribing to jobs")
    if uri.startswith("/dev/usb/") and not os.access(uri, os.R_OK | os.W_OK):
        raise ValueError("The configured USB printer is unavailable or lacks read/write permission")
    model = os.environ.get("PRINTER_MODEL", "QL-810W")
    label = os.environ.get("PRINTER_LABEL", "62x100")
    delay = 1
    while True:
        try:
            with connect(
                url,
                origin=origin,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
                max_size=1024 * 1024,
            ) as socket:
                logger.info("Printer connected; only new live labels will be received")
                delay = 1
                for message in socket:
                    handle_message(
                        socket,
                        message,
                        lambda image: usb_print(image, printer_uri=uri, model=model, label=label),
                        icons=icons,
                    )
        except KeyboardInterrupt:
            return
        except Exception as error:
            logger.warning("Printer disconnected (%s); reconnecting", type(error).__name__)
            time.sleep(delay)
            delay = min(30, delay * 2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run")
    preview = commands.add_parser(
        "preview", help="Render a supplied label payload without connecting or printing"
    )
    preview.add_argument("payload", type=Path)
    preview.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "preview":
        payload = json.loads(args.payload.read_text())
        keys = uploaded_icon_keys(payload)
        artwork = {}
        if keys:
            server = os.environ.get("PRINTER_SERVER_URL", "")
            if not server:
                raise ValueError("Set PRINTER_SERVER_URL to preview uploaded training icons")
            icons = IconCache(server)
            artwork = icons.load(keys)
        render_label(payload, icon_data=artwork).save(args.output)
    else:
        run()


if __name__ == "__main__":
    main()
