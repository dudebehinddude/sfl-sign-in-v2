"""A disconnected printer must never create a deferred label backlog."""

import asyncio

import pytest

from app.services.printing import PrinterHub


class Socket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send_json(self, data):
        self.messages.append(data)

    async def close(self, **kwargs):
        self.closed = True


@pytest.fixture
def hub(monkeypatch):
    value = PrinterHub(None, timeout_seconds=0.02)
    changes = []

    async def notify():
        changes.append(value.status())

    monkeypatch.setattr(value, "_notify", notify)
    return value, changes


@pytest.mark.asyncio
async def test_offline_and_busy_labels_are_dropped_without_replay(hub):
    printer, changes = hub
    label = {"display_name": "Visitor", "badges": []}
    assert (await printer.send_label(label))["status"] == "offline"
    socket = Socket()
    assert await printer.connect(socket)
    assert socket.messages == []
    sent = await printer.send_label(label)
    assert sent["status"] == "sent"
    assert (await printer.send_label({"display_name": "Dropped", "badges": []}))["status"] == "busy"
    assert socket.messages == [{"type": "label", "id": sent["label_id"], "label": label}]
    assert not await printer.acknowledge(socket, {"id": "wrong", "status": "printed"})
    assert await printer.acknowledge(socket, {"id": sent["label_id"], "status": "printed"})
    assert printer.status()["last_result"]["status"] == "printed"
    assert not printer.status()["busy"]
    await printer.disconnect(socket)
    replacement = Socket()
    assert await printer.connect(replacement)
    assert replacement.messages == []
    assert len(changes) >= 4
    await printer.stop()


@pytest.mark.asyncio
async def test_disconnect_and_timeout_are_unknown_and_never_reprinted(hub):
    printer, _ = hub
    socket = Socket()
    assert await printer.connect(socket)
    await printer.send_label({"display_name": "May have printed", "badges": []})
    await printer.disconnect(socket)
    assert printer.status()["last_result"]["status"] == "unknown"
    replacement = Socket()
    assert await printer.connect(replacement)
    assert replacement.messages == []
    await printer.send_label({"display_name": "Stalled", "badges": []})
    await asyncio.sleep(0.04)
    assert printer.status()["last_result"]["status"] == "unknown"
    assert not printer.status()["connected"]
    assert replacement.closed
    assert len(replacement.messages) == 1
    await printer.stop()


@pytest.mark.asyncio
async def test_single_printer_and_ack_correlation(hub):
    printer, _ = hub
    socket, intruder = Socket(), Socket()
    assert await printer.connect(socket)
    assert not await printer.connect(intruder)
    sent = await printer.send_label({"display_name": "Visitor", "badges": []})
    ack = {"id": sent["label_id"], "status": "failed", "error": "Bad image"}
    assert not await printer.acknowledge(intruder, ack)
    assert not await printer.acknowledge(socket, {**ack, "status": "queued"})
    assert await printer.acknowledge(socket, ack)
    assert not await printer.acknowledge(socket, ack)
    assert printer.status()["last_result"]["message"] == "Bad image"
    await printer.stop()


@pytest.mark.asyncio
async def test_command_can_dispatch_without_waiting_for_blocked_printer(hub, monkeypatch):
    printer, _ = hub
    blocker = asyncio.Event()

    async def blocked(_):
        await blocker.wait()

    monkeypatch.setattr(printer, "send_label", blocked)
    printer.dispatch({"display_name": "Visitor", "badges": []})
    await asyncio.sleep(0)
    assert len(printer.dispatch_tasks) == 1
    assert not blocker.is_set()
    await printer.stop()
    assert not printer.dispatch_tasks
