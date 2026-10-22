# Examples

Curated examples covering common use cases. All examples assume you've
already installed baileys-py (see [Installation](install.md)).

## Minimal QR-login bot

See [`examples/basic.py`](../examples/basic.py). Prints a QR, then
replies `pong <id>` to any incoming message.

```bash
python examples/basic.py
```

## Pairing-code login

See [`examples/pairing_code.py`](../examples/pairing_code.py).

```bash
python examples/pairing_code.py +62XXXXXXXXXXX
```

## Echo bot

```python
import asyncio
from baileys_py import make_wa_socket, use_multi_file_auth_state


async def main():
    state, save_creds = await use_multi_file_auth_state("./auth_info")
    sock = make_wa_socket(auth=state, push_name="Echo Bot")

    @sock.ev.on("connection.update")
    async def on_conn(update):
        if update.get("qr"):
            import qrcode
            q = qrcode.QRCode(border=1)
            q.add_data(update["qr"])
            q.print_ascii(invert=True)
        if update.get("connection") == "open":
            print("Connected as", sock.user.get("id"))

    @sock.ev.on("creds.update")
    async def on_creds(_):
        await save_creds()

    @sock.ev.on("messages.upsert")
    async def on_msg(upsert):
        for msg in upsert["messages"]:
            if msg.key.from_me:
                continue
            text = (msg.message or {}).get("conversation", "")
            if text:
                await sock.send_message(msg.key.remote_jid, {"text": text})

    await sock.connect()
    await asyncio.Event().wait()


asyncio.run(main())
```

## Send a one-off message (no event loop forever)

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

## Run multiple accounts in parallel

```python
import asyncio
from baileys_py import make_wa_socket, use_multi_file_auth_state


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


asyncio.run(main())
```

## Send an image with caption

```python
await sock.send_message(jid, {
    "image": {"url": "https://example.com/cat.jpg"},
    "caption": "look at this cat",
    "mimetype": "image/jpeg",
})
```

## Send a voice note (audio PTT)

```python
await sock.send_message(jid, {
    "audio": {"url": "https://example.com/clip.mp3"},
    "mimetype": "audio/mpeg",
    "ptt": True,
})
```

## Send a location

```python
await sock.send_message(jid, {
    "location": {
        "lat": -6.2088,
        "lng": 106.8456,
        "name": "Monas",
    },
})
```

## Reply to a message

```python
@sock.ev.on("messages.upsert")
async def on_msg(upsert):
    for msg in upsert["messages"]:
        if msg.key.from_me:
            continue
        await sock.send_message(msg.key.remote_jid, {"text": "noted", "reply": msg})
```

## Auto-reconnect on disconnect

```python
@sock.ev.on("connection.update")
async def on_conn(update):
    if update.get("connection") == "close":
        last = update.get("lastDisconnect") or {}
        if last.get("status") == 401:
            print("logged out — clear auth folder and re-scan")
            return
        await asyncio.sleep(2)
        await sock.connect()
```

## Create a group and invite people

```python
from baileys_py.messages import group_create, group_invite_code

result = await group_create(sock, "Project Team", participants=[
    "62XXX@s.whatsapp.net",
    "62YYY@s.whatsapp.net",
])
# Group JID is usually in `result['raw'].attrs['id']`
group_jid = "120363XXX@g.us"
code = await group_invite_code(sock, group_jid)
print(f"Invite link: https://chat.whatsapp.com/{code}")
```

## React to a message

```python
@sock.ev.on("messages.upsert")
async def on_msg(upsert):
    for msg in upsert["messages"]:
        if msg.key.from_me:
            continue
        await sock.send_message(msg.key.remote_jid, {
            "react": {"text": "👍", "key": msg.key},
        })
```

## Save received media to disk

> Scaffolded — needs the WA protobuf schema to decrypt media. The
> skeleton below shows where the hook goes.

```python
import os

@sock.ev.on("messages.media-update")
async def on_media(updates):
    for u in updates:
        if u.get("error"):
            print("media decrypt failed:", u["error"])
            continue
        key = u["key"]
        ciphertext, iv = u["media"]["ciphertext"], u["media"]["iv"]
        # Decrypt with the message's media key (HKDF-derived from the
        # Signal session shared secret). Save to ./media/
        # TODO: implement decryption once WAProto is wired in.
        print("would save media for", key.id)
```

## Block / unblock a user

```python
from baileys_py import BinaryNode


async def block(sock, jid: str):
    node = BinaryNode(
        tag="iq",
        attrs={"to": "@s.whatsapp.net", "type": "set", "xmlns": "block"},
        content=[BinaryNode(tag="item", attrs={"jid": jid, "action": "block"})],
    )
    return await sock.query(node)


async def unblock(sock, jid: str):
    node = BinaryNode(
        tag="iq",
        attrs={"to": "@s.whatsapp.net", "type": "set", "xmlns": "block"},
        content=[BinaryNode(tag="item", attrs={"jid": jid, "action": "unblock"})],
    )
    return await sock.query(node)
```

## Send to a specific device

WhatsApp's multi-device protocol lets you send to a specific
`device:0` (phone) or `device:7` (linked). The default sends to all
known devices. To target a specific one, set the participant field:

```python
from baileys_py import MiscMessageGenerationOptions

opts = MiscMessageGenerationOptions(participant="62XXX:7@s.whatsapp.net")
await sock.send_message("62XXX@s.whatsapp.net", {"text": "hi device 7"}, options=opts)
```

## Docker container

A minimal `Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir "git+https://github.com/asukaa2/baileys-py.git" qrcode
COPY bot.py .
CMD ["python", "bot.py"]
```

Build + run:

```bash
docker build -t baileys-bot .
docker run -it --rm \
    -v "$PWD/auth_info:/app/auth_info" \
    baileys-bot
```

## systemd service

`/etc/systemd/system/baileys-bot.service`:

```ini
[Unit]
Description=Baileys-Py WhatsApp Bot
After=network.target

[Service]
Type=simple
User=bot
WorkingDirectory=/opt/baileys-bot
ExecStart=/opt/baileys-bot/.venv/bin/python /opt/baileys-bot/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable + start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now baileys-bot
```
