"""Live projections and kiosk commands share the REST service/permission boundary."""

import asyncio

import anyio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlmodel import Session

from ..config import get_settings
from ..database import engine
from ..schemas import KeyholderInput, RegisterInput, TapInput
from ..security import actor_for_token, check_origin
from ..services.kiosk import execute_command
from ..services.projections import public_snapshot

router = APIRouter(tags=["live"])


async def next_event(websocket, queue, timeout=20):
    # Keep a completed receive until it has actually been delivered. A database
    # notification must never cancel or discard a kiosk command / printer ack.
    tasks = getattr(websocket.state, "pending_events", None)
    if tasks is None:
        tasks = {}
        websocket.state.pending_events = tasks
    if "message" not in tasks:
        tasks["message"] = asyncio.create_task(websocket.receive_json())
    if "change" not in tasks:
        tasks["change"] = asyncio.create_task(queue.get())
    done, _ = await asyncio.wait(
        set(tasks.values()), timeout=timeout, return_when=asyncio.FIRST_COMPLETED
    )
    if not done:
        return "heartbeat", None
    preferred = getattr(websocket.state, "prefer_event", "message")
    order = [preferred, "change" if preferred == "message" else "message"]
    for kind in order:
        task = tasks[kind]
        if task in done:
            del tasks[kind]
            websocket.state.prefer_event = "change" if kind == "message" else "message"
            return kind, task.result()
    raise RuntimeError("No completed websocket event")


async def cleanup_events(websocket):
    tasks = getattr(websocket.state, "pending_events", {})
    for task in tasks.values():
        if not task.done():
            task.cancel()
    # ASGI shutdown can cancel the surrounding scope while these child tasks
    # still hold receive/queue waits. Drain them before leaving the socket.
    with anyio.CancelScope(shield=True):
        await asyncio.gather(*tasks.values(), return_exceptions=True)
    tasks.clear()


def _staff(token):
    with Session(engine) as session:
        actor = actor_for_token(session, token)
        if not actor.permissions:
            raise HTTPException(403, "Staff permission required")
        return {"role": actor.role, "permissions": sorted(actor.permissions)}


def _kiosk_command(command, data):
    schema = {"tap": TapInput, "register": RegisterInput, "keyholder": KeyholderInput}.get(command)
    if not schema:
        raise HTTPException(422, "Unknown kiosk command")
    parsed = schema.model_validate(data)
    with Session(engine) as session:
        return execute_command(session, command, parsed)


@router.websocket("/ws/public")
async def public_socket(websocket: WebSocket):
    try:
        check_origin(websocket.headers.get("origin"))
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async with websocket.app.state.events.subscribe() as queue:

            async def snapshot():
                data = await asyncio.to_thread(public_snapshot, engine)
                await websocket.send_json(
                    {
                        "type": "snapshot",
                        "topic": "occupancy",
                        "revision": data["revision"],
                        "data": data,
                    }
                )

            await snapshot()
            while True:
                kind, message = await next_event(websocket, queue)
                if kind == "change" and (
                    "public" in message.get("revisions", {}) or message.get("resnapshot")
                ):
                    await snapshot()
                elif kind == "heartbeat":
                    await websocket.send_json({"type": "ping"})
                elif (
                    kind == "message"
                    and isinstance(message, dict)
                    and message.get("type") == "ping"
                ):
                    await websocket.send_json({"type": "pong"})
    except (TimeoutError, WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await cleanup_events(websocket)


@router.websocket("/ws/admin")
async def admin_socket(websocket: WebSocket):
    token = websocket.cookies.get(get_settings().session_cookie)
    try:
        check_origin(websocket.headers.get("origin"), required=True)
        identity = await asyncio.to_thread(_staff, token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async with websocket.app.state.events.subscribe() as queue:
            await websocket.send_json({"type": "invalidate", "topics": ["all"], "revision": 0})
            while True:
                kind, message = await next_event(websocket, queue)
                # Expiry/revocation/role changes are rechecked before every private update
                # and on heartbeat; privileged payloads are never queued for clients.
                current = await asyncio.to_thread(_staff, token)
                if current != identity:
                    await websocket.send_json({"type": "permissions_changed"})
                    await websocket.close(code=1008)
                    return
                if kind == "change":
                    await websocket.send_json(
                        {
                            "type": "invalidate",
                            "topics": message.get("topics", ["all"]),
                            "revision": message.get("revisions", {}).get("staff", 0),
                        }
                    )
                elif kind == "heartbeat":
                    await websocket.send_json({"type": "ping"})
                elif (
                    kind == "message"
                    and isinstance(message, dict)
                    and message.get("type") == "ping"
                ):
                    await websocket.send_json({"type": "pong"})
    except HTTPException:
        await websocket.close(code=1008)
    except (TimeoutError, WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await cleanup_events(websocket)


@router.websocket("/ws/kiosk")
async def kiosk_socket(websocket: WebSocket):
    try:
        check_origin(websocket.headers.get("origin"), required=True)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async with websocket.app.state.events.subscribe() as queue:
            data = await asyncio.to_thread(public_snapshot, engine)
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "topic": "occupancy",
                    "revision": data["revision"],
                    "data": data,
                }
            )
            while True:
                kind, message = await next_event(websocket, queue)
                if kind == "change":
                    if "public" in message.get("revisions", {}) or message.get("resnapshot"):
                        data = await asyncio.to_thread(public_snapshot, engine)
                        await websocket.send_json(
                            {
                                "type": "snapshot",
                                "topic": "occupancy",
                                "revision": data["revision"],
                                "data": data,
                            }
                        )
                elif kind == "heartbeat":
                    await websocket.send_json({"type": "ping"})
                elif isinstance(message, dict) and message.get("type") == "command":
                    request_id = str(message.get("id", ""))[:128]
                    try:
                        result = await asyncio.to_thread(
                            _kiosk_command, message.get("command"), message.get("data", {})
                        )
                        label = result.pop("_label", None)
                        await websocket.send_json(
                            {"type": "result", "id": request_id, "result": result}
                        )
                        if label:
                            websocket.app.state.printer.dispatch(label)
                    except HTTPException as exc:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "id": request_id,
                                "status": exc.status_code,
                                "detail": exc.detail,
                            }
                        )
                    except ValidationError as exc:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "id": request_id,
                                "status": 422,
                                "detail": jsonable_encoder(exc.errors(include_context=False)),
                            }
                        )
                elif isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
    except HTTPException:
        await websocket.close(code=1008)
    except (TimeoutError, WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await cleanup_events(websocket)


@router.websocket("/ws/printer")
async def printer_socket(websocket: WebSocket):
    try:
        check_origin(websocket.headers.get("origin"))
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    hub = websocket.app.state.printer
    if not await hub.connect(websocket):
        await websocket.close(code=1008, reason="A printer is already connected")
        return
    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=20)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") == "ack":
                await hub.acknowledge(websocket, message)
            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        with anyio.CancelScope(shield=True):
            await hub.disconnect(websocket)
