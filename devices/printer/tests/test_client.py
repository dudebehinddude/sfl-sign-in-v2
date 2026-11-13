import json
import unittest
from uuid import uuid4

from sfl_printer.client import handle_message, websocket_url
from sfl_printer.labels import render_label


class Socket:
    def __init__(self):
        self.sent = []

    def send(self, value):
        self.sent.append(json.loads(value))


def label(payload=None):
    return json.dumps(
        {
            "type": "label",
            "id": str(uuid4()),
            "label": payload
            if payload is not None
            else {"display_name": "Sample Visitor", "badges": []},
        }
    )


class ProtocolTests(unittest.TestCase):
    def test_live_label_prints_then_acknowledges(self):
        socket = Socket()
        output = []
        handle_message(socket, label(), lambda image: output.append(image.size) or "printed")
        self.assertEqual(output, [(1109, 696)])
        self.assertEqual(socket.sent[0]["status"], "printed")
        self.assertNotIn("lease_token", socket.sent[0])

    def test_invalid_label_does_not_touch_usb(self):
        socket = Socket()
        output = []
        handle_message(socket, label({}), lambda image: output.append(1))
        self.assertEqual(output, [])
        self.assertEqual(socket.sent[0]["status"], "failed")

    def test_driver_failure_reports_unknown_and_does_not_retry(self):
        socket = Socket()
        output = []

        def fail(image):
            output.append(1)
            raise OSError("fixture output failed after possible physical output")

        handle_message(socket, label(), fail)
        self.assertEqual(output, [1])
        self.assertEqual(socket.sent[0]["status"], "unknown")

    def test_lost_ack_does_not_repeat_output(self):
        socket = Socket()
        output = []

        def lost(value):
            raise OSError("fixture connection dropped")

        socket.send = lost
        with self.assertRaises(OSError):
            handle_message(socket, label(), lambda image: output.append(1) or "printed")
        self.assertEqual(output, [1])

    def test_origin_and_render_dimensions(self):
        self.assertEqual(
            websocket_url("https://sfl.local:8443"),
            ("wss://sfl.local:8443/ws/printer", "https://sfl.local:8443"),
        )
        for invalid in [
            "http://user:password@host",
            "http://host?token=abc",
            "file:///tmp/file",
            "http://host/admin",
        ]:
            with self.assertRaises(ValueError):
                websocket_url(invalid)
        image = render_label(
            {
                "display_name": "Sample",
                "badges": [
                    {
                        "training_type_id": str(uuid4()),
                        "name": "Orientation",
                        "icon_key": "orientation",
                    }
                ],
            }
        )
        self.assertEqual(image.size, (1109, 696))
        self.assertEqual(image.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
