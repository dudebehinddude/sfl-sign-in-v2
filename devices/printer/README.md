# Kiosk USB printer agent

Run this small program on the computer connected to the label printer. It connects to the internal server at `/ws/printer` and prints newly received labels. It has no persistent queue, device token or receipt database. Labels sent while it is offline or busy are not queued, and reconnecting does not replay them.

```sh
python3 -m venv .venv
.venv/bin/pip install '.[usb]'
cp .env.example .env.local
# Set the server origin and USB target in .env.local.
.venv/bin/sfl-printer --env-file .env.local run
```

The current hardware defaults are Brother QL-810W and 62x100 labels. Check the actual printer, USB permissions and label stock before adoption. Invalid label data is rejected before USB output. Driver errors or lost acknowledgments leave the outcome unknown; check physical output before deliberately printing another label. Neither side automatically resends it.

Protocol: server `{type:"label",id,label:{display_name,badges}}`; client `{type:"ack",id,status:"printed"|"failed"|"unknown",error}`. The ID only matches the current WebSocket message to its acknowledgment. It is not a stored job. Ping/pong supports a healthy connection.

The `preview payload.json sample.png` command renders without touching USB. Its success does not verify physical printing. The optional `brother-ql` dependency uses GPL-3.0.

Labels use the binary training payload `{training_type_id, name, icon_key}`. The renderer prints each full training name and the original icon, without training levels. Up to 24 badges are fitted into the fixed 1109×696-dot label. Dense or unusually long training names reduce the available type size; inspect a preview before choosing very long names. The six legacy PNG assets remain packaged as a fallback. Uploaded artwork uses `icon_key: "training-icons/<32 lowercase hex>.png"`; the agent fetches `/media/<icon_key>` from the configured app origin before USB output. It accepts only single-frame PNGs up to 512×512 pixels and 2 MiB, refuses redirects, and uses an in-memory LRU cache capped at 16 icons / 8 MiB. A 10-second artwork deadline covers the label, with socket timeouts capped at 5 seconds (an in-flight socket read can finish after the deadline). Failed artwork fetches are acknowledged as failed without printing or retrying. Badge order is exactly the payload order supplied by the backend. Artwork retains color and alpha until the final monochrome conversion.

Previewing a payload with uploaded icons also requires `PRINTER_SERVER_URL`; it uses the same bounded public artwork fetcher. Direct callers can render offline with `render_label(payload, icon_data={key: png_bytes})`.
