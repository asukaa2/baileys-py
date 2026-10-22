# Quick start

This page walks through three minimal examples:

1. [Login with a QR code](#1-login-with-a-qr-code)
2. [Login with a pairing code](#2-login-with-a-pairing-code)
3. [Reply to incoming messages](#3-reply-to-incoming-messages)

> You'll need a working install. See [Installation](install.md) if you
> haven't installed baileys-py yet.

## 1. Login with a QR code

Save as `bot.py` and run with `python bot.py`:

```python
import asyncio
import qrcode
from baileys_py import make_wa_socket, use_multi_file_auth_state


async def main():
    # 1) Load or create auth credentials. The folder persists between
    #    runs so you only scan the QR code once.
    state, save_creds = await use_multi_file_auth_state("./auth_info")
    sock = make_wa_socket(auth=state, push_name="My Python Bot")

    # 2) Handle connection lifecycle
    @sock.ev.on("connection.update")
    async def on_connection(update: dict):
        qr = update.get("qr")
        if qr:
            print("[QR] Scan with your phone:")
            qr_obj = qrcode.QRCode(border=1)
            qr_obj.add_data(qr)
            qr_obj.print_ascii(invert=True)

        if update.get("connection") == "open":
            print("[OK] Connected! Logged in as:", sock.user.get("id"))
            # Send a one-off message
            await sock.send_message("62XXXXXXXXXXX", "hello from python")

        if update.get("connection") == "close":
            status = (update.get("lastDisconnect") or {}).get("status")
            if status == 401:  # logged_out
                print("[FATAL] logged out — clear ./auth_info and re-scan")
            else:
                print("[RECONNECT] restarting socket")
                await sock.connect()

    # 3) Persist credentials whenever they change
    @sock.ev.on("creds.update")
    async def on_creds(_):
        await save_creds()

    # 4) Open the WebSocket
    await sock.connect()

    # 5) Keep the script alive
    await asyncio.Event().wait()


asyncio.run(main())
```

### What to expect

1. First run: a QR code is printed in the terminal.
2. Open WhatsApp on your phone → Settings → Linked Devices → Link a device.
3. Scan the QR. The connection transitions to `open` and the message
   is sent.
4. Subsequent runs: `./auth_info/` already has credentials, so no QR
   is needed.

## 2. Login with a pairing code

Pairing codes are 8-character codes you enter on the phone instead of
scanning a QR. Useful on headless servers where you can't show a QR.

```python
import asyncio
from baileys_py import make_wa_socket, use_multi_file_auth_state


async def main(phone_number: str):
    state, save_creds = await use_multi_file_auth_state("./auth_info")
    sock = make_wa_socket(auth=state, push_name="My Python Bot")

    @sock.ev.on("connection.update")
    async def on_connection(update: dict):
        if update.get("qr") and not sock.auth_state.creds.registered:
            # Server asked us to login; ask for a pairing code instead.
            code = await sock.request_pairing_code(phone_number)
            print(f"\n[PAIRING CODE] {code}")
            print("Enter it on your phone:")
            print("  WhatsApp > Settings > Linked devices > Link with phone number")
        if update.get("connection") == "open":
            print("[OK] Logged in as", sock.user.get("id"))

    @sock.ev.on("creds.update")
    async def on_creds(_):
        await save_creds()

    await sock.connect()
    await asyncio.Event().wait()


asyncio.run(main("+62XXXXXXXXXXX"))  # full international format, with +
```

## 3. Reply to incoming messages

A tiny echo bot:

```python
@sock.ev.on("messages.upsert")
async def on_messages(upsert: dict):
    for msg in upsert["messages"]:
        key = msg.key
        text = _extract_text(msg)

        # Skip messages we sent ourselves
        if key.from_me:
            continue

        print(f"[MSG] {key.remote_jid}: {text}")
        await sock.send_message(
            key.remote_jid,
            {"text": f"pong: {text}"},
        )


def _extract_text(msg) -> str:
    """Pull the text body out of a WAMessage (or raw BinaryNode)."""
    message = getattr(msg, "message", None) or {}
    if not message:
        # raw BinaryNode fallback
        return getattr(msg, "attrs", {}).get("body", "")
    return (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or ""
    )
```

## Recipes

### Send a one-off message without running an event loop forever

```python
import asyncio
from baileys_py import make_wa_socket, use_multi_file_auth_state


async def send_one(to_jid: str, body: str):
    state, _ = await use_multi_file_auth_state("./auth_info")
    sock = make_wa_socket(auth=state)

    ready = asyncio.Event()

    @sock.ev.on("connection.update")
    async def on_conn(update):
        if update.get("connection") == "open":
            ready.set()

    await sock.connect()
    await ready.wait()
    await sock.send_message(to_jid, body)
    await sock.disconnect()


asyncio.run(send_one("62XXXXXXXXXXX@s.whatsapp.net", "ping"))
```

### Auto-reconnect on disconnect

```python
@sock.ev.on("connection.update")
async def on_connection(update):
    if update.get("connection") == "close":
        last = update.get("lastDisconnect") or {}
        if last.get("status") == 401:  # logged out
            print("logged out — refusing to reconnect")
            return
        # Wait a beat then reconnect
        await asyncio.sleep(2)
        await sock.connect()
```

### Run multiple sockets in parallel

Each socket needs its own auth state folder and its own
`BaileysEventEmitter`:

```python
async def run_account(folder: str, push_name: str):
    state, save_creds = await use_multi_file_auth_state(folder)
    sock = make_wa_socket(auth=state, push_name=push_name)
    sock.ev.on("creds.update", lambda _: asyncio.ensure_future(save_creds()))
    await sock.connect()

async def main():
    await asyncio.gather(
        run_account("./acc1", "Bot 1"),
        run_account("./acc2", "Bot 2"),
    )
```

### Print QR to terminal (without `qrcode` library)

You'll need the `qrcode` library (it's a runtime dependency, so it
should already be installed). See the first example for the exact
incantation.

## Next steps

* [Events & lifecycle](events.md) — full list of events the socket emits
* [Sending messages](messaging.md) — every content type
* [Auth state](auth.md) — pick the right persistence backend
