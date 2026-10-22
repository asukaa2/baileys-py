# baileys-py

A simple, Pythonic port of the [Baileys](https://github.com/whiskeysockets/Baileys) WhatsApp Web API.

`baileys-py` re-implements the high-level Baileys API in pure Python so
you can build WhatsApp bots, automation scripts, and integrations without
leaving the Python ecosystem. It mirrors the upstream event model
(`sock.ev.on("connection.update")`, `sock.send_message(...)`,
`use_multi_file_auth_state(...)`, …) but uses Python idioms:

* `snake_case` function / method names
* `async/await` everywhere (no callbacks, no `Promise`)
* `dataclass`-based types (`SocketConfig`, `WAMessage`, …)
* Plain `logging`-based logger (pino-style API retained for familiarity)

## What works

| Layer | Status |
| --- | --- |
| JID utilities (`jid_decode`, `jid_encode`, `is_jid_group`, …) | ✅ Complete (full port) |
| WA binary protocol encode / decode + all 1300-line token dictionaries | ✅ Complete (auto-generated from upstream) |
| Curve25519 / Ed25519 helpers, HKDF, AES-GCM, AES-CTR, HMAC | ✅ Complete (via `cryptography`) |
| Noise XX handshake + transport encryption / framing | ✅ Complete |
| Multi-file auth state persistence (per-cred JSON files) | ✅ Complete |
| Single-file auth state (one JSON file) | ✅ Complete |
| Event emitter (`BaileysEventEmitter`) with batched `process()` helper | ✅ Complete |
| WebSocket connect, recv loop, keepalive, IQ query/response by id | ✅ Complete |
| `send_message` API surface for text / image / audio / video / doc / sticker / location / contact / reply | ⚠️ Scaffolded (high-level API ready; full message-encryption requires the WA protobuf schema, which you can drop in via `WAProto/`) |
| QR-code / pairing-code login helpers | ⚠️ Scaffolded (helpers present; the actual QR payload bytes need the WA protobuf schema) |
| Group / chat / presence / profile helpers | ⚠️ Scaffolded (IQ stanzas built; replace with real WA protobuf once wired) |
| Signal protocol (Session, SenderKey, X3DH, pre-key bundles) | ⚠️ Minimal in-memory store; not a drop-in replacement for `libsignal` |

> **Note:** The full WhatsApp Web protocol requires the `WAProto`
> protobuf definitions (shipped under `Baileys/WAProto/` in the upstream
> repo). `baileys-py` is intentionally structured so that you can either
>
> * run `protoc` on the upstream `.proto` file and drop the generated
>   Python module into `baileys_py/proto/` to enable full protocol
>   interop, or
> * use this package as a clean scaffold for your own implementation.

## Installation

```bash
# from source
git clone https://github.com/whiskeysockets/Baileys
# (or copy this folder out of the repo — `baileys-py/`)
cd baileys-py
pip install -e .
```

Runtime dependencies:

* `websockets >= 11`
* `cryptography >= 41`
* `qrcode >= 7.4`
* `protobuf >= 4.24`
* `aiofiles >= 23`

## Quick start

### 1 — Scan a QR code (default login flow)

```python
import asyncio
import qrcode
from baileys_py import make_wa_socket, use_multi_file_auth_state


async def main():
    state, save_creds = await use_multi_file_auth_state("./auth_info")
    sock = make_wa_socket(auth=state, push_name="My Bot")

    @sock.ev.on("connection.update")
    async def on_conn(update):
        qr = update.get("qr")
        if qr:
            q = qrcode.QRCode(border=1); q.add_data(qr); q.print_ascii(invert=True)
        if update.get("connection") == "open":
            await sock.send_message("62xxxxxxxx", "hello from python")

    @sock.ev.on("creds.update")
    async def on_creds(_):
        await save_creds()

    await sock.connect()
    await asyncio.Event().wait()  # run forever

asyncio.run(main())
```

### 2 — Pairing code (phone-number login)

```python
import asyncio
from baileys_py import make_wa_socket, use_multi_file_auth_state

async def main():
    state, save_creds = await use_multi_file_auth_state("./auth_info")
    sock = make_wa_socket(auth=state)

    @sock.ev.on("connection.update")
    async def on_conn(update):
        if update.get("qr") and not sock.auth_state.creds.registered:
            code = await sock.request_pairing_code("+62xxxxxxxx")
            print("Pairing code:", code)
        if update.get("connection") == "open":
            print("Connected as", sock.user.get("id"))

    @sock.ev.on("creds.update")
    async def on_creds(_):
        await save_creds()

    await sock.connect()
    await asyncio.Event().wait()

asyncio.run(main())
```

### 3 — Reply to incoming messages

```python
@sock.ev.on("messages.upsert")
async def on_messages(upsert):
    for msg in upsert["messages"]:
        key = msg.key
        text = (msg.message or {}).get("conversation") \
               or ((msg.message or {}).get("extendedTextMessage") or {}).get("text", "")
        if not key.from_me and text:
            await sock.send_message(key.remote_jid, {"text": f"pong {key.id}"})
```

## Public API surface

`baileys_py` re-exports the most useful names from the upstream package:

| Upstream (TS) | `baileys_py` (Python) |
| --- | --- |
| `makeWASocket(config)` | `make_wa_socket(auth=state, **kwargs)` |
| `useMultiFileAuthState(folder)` | `await use_multi_file_auth_state(folder)` → `(state, save_creds)` |
| `sock.ev.on("connection.update", cb)` | `sock.ev.on("connection.update", cb)` (callback may be sync or async) |
| `sock.ev.process(async (events) => …)` | `sock.ev.process(async def events(events): …)` |
| `sock.sendMessage(jid, { text })` | `await sock.send_message(jid, {"text": …})` |
| `sock.requestPairingCode(phone)` | `await sock.request_pairing_code(phone)` |
| `proto.WebMessageInfo.decode(...)` | requires `WAProto/` protobuf module (see below) |
| `fetchLatestBaileysVersion()` | `await fetch_latest_baileys_version()` (returns baked-in default) |
| `DisconnectReason.loggedOut` | `DisconnectReason.logged_out` |
| `isJidGroup(jid)` | `is_jid_group(jid)` |

## Folder layout

```
baileys-py/
├── baileys_py/
│   ├── __init__.py        # public exports
│   ├── socket.py          # WASocket + make_wa_socket
│   ├── auth.py            # use_multi_file_auth_state, init_auth_creds
│   ├── events.py          # BaileysEventEmitter
│   ├── crypto.py          # Curve25519, HKDF, AES helpers
│   ├── noise_handler.py   # Noise XX handshake + transport
│   ├── messages.py        # group / chat / presence / profile helpers
│   ├── logger.py          # pino-style logger backed by `logging`
│   ├── types.py           # dataclasses for config, creds, message, …
│   ├── defaults.py        # default constants
│   ├── utils.py           # generate_message_id, fetch version, …
│   ├── binary/
│   │   ├── constants.py    # auto-generated token dicts (1300+ lines)
│   │   ├── encode.py      # BinaryNode → wire format
│   │   ├── decode.py      # wire format → BinaryNode
│   │   ├── jid.py         # JID encode/decode/inspect
│   │   ├── node.py        # BinaryNode + traversal helpers
│   │   └── __init__.py
│   └── signal/
│       ├── repository.py  # in-memory Signal store + crypto helpers
│       └── __init__.py
├── examples/
│   ├── basic.py           # QR-code login + reply bot
│   └── pairing_code.py    # phone-number login
├── scripts/
│   └── build_constants.py # regenerates binary/constants.py from upstream TS
├── tests/
│   └── test_smoke.py      # 13 pure-python tests, no network needed
├── pyproject.toml
└── README.md
```

## Regenerating the binary token dictionaries

The 1,300-line token dictionary in `baileys_py/binary/constants.py` is
auto-generated from the upstream TypeScript source. If you bump the
upstream Baileys version, re-run:

```bash
python scripts/build_constants.py
```

The script parses `Baileys/src/WABinary/constants.ts` (which lives in the
cloned upstream repo at `/home/z/my-project/Baileys/src/WABinary/constants.ts`)
and writes a fresh `constants.py` with all single-byte and double-byte
tokens plus a precomputed `TOKEN_MAP`.

## Running the tests

```bash
python tests/test_smoke.py
# or
pytest -q tests/
```

All 13 tests pass with no network access.

## License

MIT — same as upstream Baileys.
