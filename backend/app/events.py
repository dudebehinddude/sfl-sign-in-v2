"""Transaction-ordered revisions and commit-time PostgreSQL invalidations."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import psycopg
from sqlalchemy import text
from sqlmodel import Session, select

from .config import get_settings
from .models import AuditEvent, ScopeRevision

logger = logging.getLogger(__name__)
CHANNEL = "sfl_changes"


def publish(session: Session, *topics: str) -> int:
    scopes = ["staff"]
    if set(topics) & {
        "occupancy",
        "users",
        "training-types",
        "trainings",
        "visits",
        "keyholders",
        "all",
    }:
        scopes.append("public")
    revisions = {}
    # Lock in a consistent scope order. Counter locks are held through commit,
    # so revisions follow transaction serialization rather than sequence allocation.
    for scope in sorted(set(scopes)):
        counter = session.exec(
            select(ScopeRevision).where(ScopeRevision.scope == scope).with_for_update()
        ).one()
        counter.revision += 1
        session.add(counter)
        revisions[scope] = counter.revision
    session.flush()
    session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {
            "channel": CHANNEL,
            "payload": json.dumps(
                {
                    "revision": revisions.get("staff", 0),
                    "revisions": revisions,
                    "topics": list(dict.fromkeys(topics)),
                }
            ),
        },
    )
    return revisions.get("public", revisions["staff"])


def audit(
    session: Session, action: str, entity_type: str, entity_id=None, actor_id=None, **details
) -> None:
    session.add(
        AuditEvent(
            actor_user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            details=details,
        )
    )


class EventHub:
    """One LISTEN connection per API process, not one per browser.

    NOTIFY carries only topics/revision, never sensitive domain rows. A reconnect
    broadcasts a fresh invalidation to every client. Domain snapshots remain the
    source of truth, so a sequence ID is not mistaken for commit order.
    """

    def __init__(self):
        self.queues: set[asyncio.Queue] = set()
        self.ready = asyncio.Event()
        self.task: asyncio.Task | None = None

    async def start(self):
        self.task = asyncio.create_task(self._listen())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def broadcast(self, message):
        for queue in tuple(self.queues):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                message = {"revision": 0, "topics": ["all"], "resnapshot": True}
            queue.put_nowait(message)

    async def _listen(self):
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    get_settings().psycopg_url, autocommit=True, connect_timeout=5
                ) as conn:
                    await conn.execute(f"LISTEN {CHANNEL}")
                    self.ready.set()
                    self.broadcast({"revision": 0, "topics": ["all"], "resnapshot": True})
                    async for notify in conn.notifies():
                        self.broadcast(json.loads(notify.payload))
            except asyncio.CancelledError:
                raise
            except (psycopg.Error, OSError, ValueError):
                logger.exception(
                    "Database live listener disconnected; clients will resnapshot after recovery"
                )
                self.ready.clear()
                await asyncio.sleep(1)

    @asynccontextmanager
    async def subscribe(self):
        await asyncio.wait_for(self.ready.wait(), timeout=10)
        queue = asyncio.Queue(maxsize=32)
        # Register before snapshot query, so no commit between snapshot and subscribe is lost.
        self.queues.add(queue)
        try:
            yield queue
        finally:
            self.queues.discard(queue)
