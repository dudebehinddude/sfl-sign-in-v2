"""One live LAN printer connection, with no persistent queue or reconnect replay."""

import asyncio
import logging
from uuid import uuid4

from fastapi import WebSocket
from sqlmodel import Session

from ..events import publish
from ..models import utcnow

logger = logging.getLogger(__name__)


class PrinterHub:
    def __init__(self, engine, timeout_seconds=20):
        self.engine = engine
        self.timeout_seconds = timeout_seconds
        self.socket: WebSocket | None = None
        self.inflight: dict | None = None
        self.last_result: dict | None = None
        self.lock = asyncio.Lock()
        self.timeout_task: asyncio.Task | None = None
        self.dispatch_tasks: set[asyncio.Task] = set()

    def dispatch(self, label):
        """Best effort after the committed command reply, without queue/replay."""
        task = asyncio.create_task(self.send_label(label))
        self.dispatch_tasks.add(task)
        task.add_done_callback(self._dispatched)

    def _dispatched(self, task):
        self.dispatch_tasks.discard(task)
        if not task.cancelled() and task.exception():
            error = task.exception()
            logger.error(
                "Live printer send failed", exc_info=(type(error), error, error.__traceback__)
            )

    def status(self):
        return {
            "connected": self.socket is not None,
            "busy": self.inflight is not None,
            "last_result": dict(self.last_result) if self.last_result else None,
        }

    async def _notify(self):
        def changed():
            with Session(self.engine) as session:
                publish(session, "printing")
                session.commit()

        await asyncio.to_thread(changed)

    async def connect(self, socket):
        async with self.lock:
            if self.socket is not None:
                return False
            self.socket = socket
        await self._notify()
        return True

    def _finish(self, status, message=None):
        if self.inflight:
            self.last_result = {
                "status": status,
                "label_id": self.inflight["id"],
                "display_name": self.inflight["label"]["display_name"],
                "at": utcnow().isoformat(),
            }
            if message:
                self.last_result["message"] = str(message)[:300]
            self.inflight = None
        if self.timeout_task and self.timeout_task is not asyncio.current_task():
            self.timeout_task.cancel()
        self.timeout_task = None

    async def disconnect(self, socket):
        async with self.lock:
            if self.socket is not socket:
                return
            self._finish(
                "unknown",
                "Printer disconnected before confirming output; reprint explicitly if needed",
            )
            self.socket = None
        await self._notify()

    async def _deadline(self, socket, label_id):
        await asyncio.sleep(self.timeout_seconds)
        async with self.lock:
            if self.socket is not socket or not self.inflight or self.inflight["id"] != label_id:
                return
            self._finish("unknown", "Printer confirmation timed out; no automatic retry")
            self.socket = None
        await self._notify()
        try:
            await socket.close(code=1011, reason="Printer confirmation timed out")
        except RuntimeError:
            pass

    async def send_label(self, label):
        async with self.lock:
            if self.socket is None:
                return {"status": "offline", "message": "Printer is offline; label was not queued"}
            if self.inflight is not None:
                return {"status": "busy", "message": "Printer is busy; label was not queued"}
            socket = self.socket
            label_id = str(uuid4())
            self.inflight = {"id": label_id, "label": label}
            self.timeout_task = asyncio.create_task(self._deadline(socket, label_id))
        try:
            await asyncio.wait_for(
                socket.send_json({"type": "label", "id": label_id, "label": label}), timeout=1
            )
        except (TimeoutError, RuntimeError, OSError):
            await self.disconnect(socket)
            return {
                "status": "offline",
                "label_id": label_id,
                "message": "Printer connection failed; output is unknown. Reprint explicitly if needed",
            }
        await self._notify()
        return {
            "status": "sent",
            "label_id": label_id,
            "message": "Label sent to the connected printer",
        }

    async def acknowledge(self, socket, message):
        async with self.lock:
            if (
                self.socket is not socket
                or not self.inflight
                or message.get("id") != self.inflight["id"]
            ):
                return False
            status = message.get("status")
            if status not in {"printed", "failed", "unknown"}:
                return False
            self._finish(status, message.get("error"))
        await self._notify()
        return True

    async def stop(self):
        for task in self.dispatch_tasks:
            task.cancel()
        await asyncio.gather(*self.dispatch_tasks, return_exceptions=True)
        async with self.lock:
            socket = self.socket
            self._finish("unknown", "Server stopped before printer confirmation")
            self.socket = None
        if socket:
            try:
                await socket.close(code=1001)
            except RuntimeError:
                pass
