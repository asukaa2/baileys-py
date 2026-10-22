# Internals

A walk through the package layout, the design choices behind it, and
the few places where you need to extend baileys-py to get full WhatsApp
interop.

## Module map

```
baileys_py/
├── __init__.py          # Public re-exports (~110 names)
├── types.py             # Dataclasses for SocketConfig, AuthenticationCreds, WAMessage, …
├── defaults.py          # Defaults + WA constants (NOISE_MODE, etc.)
├── logger.py            # pino-style Logger backed by `logging`
├── events.py            # BaileysEventEmitter (sync + async listeners, batched process())
├── crypto.py            # Curve25519 / Ed25519 / HKDF / AES-GCM/CTR/CBC / HMAC
├── noise_handler.py     # Noise XX handshake + transport encryption
├── socket.py            # WASocket + make_wa_socket (WebSocket connect / recv / keepalive / IQ)
├── auth.py              # use_multi_file_auth_state / use_single_file_auth_state / init_auth_creds
├── messages.py          # High-level group/chat/presence/profile helpers
├── utils.py             # generate_message_id_v2, fetch_latest_baileys_version, etc.
├── binary/
│   ├── __init__.py      # Re-exports
│   ├── constants.py     # Auto-generated token dictionaries (1300+ lines)
│   ├── node.py          # BinaryNode dataclass + traversal helpers
│   ├── encode.py        # BinaryNode → wire bytes
│   ├── decode.py        # wire bytes → BinaryNode
│   └── jid.py           # jid_encode / jid_decode / is_jid_*
└── signal/
    ├── __init__.py
    └── repository.py    # Minimal in-memory Signal store + crypto helpers
```

## Why is the binary protocol a separate sub-package?

The binary protocol is the lowest layer — it knows nothing about
WhatsApp specifics (just how to encode / decode tagged binary trees).
Keeping it isolated means you can reuse it for other WhatsApp-like
protocols, and it makes it easy to swap in a faster Rust extension later
without touching the rest of the codebase.

## Why are credentials split into `creds` and `keys`?

Upstream Baileys does the same split, and it survives for a good
reason:

* **`creds`** — singleton per account (one identity key, one noise
  key, one signed pre-key). Written rarely (on credential updates).
  Fits in a single small file.
* **`keys`** — high-volume per-recipient state (sessions, sender-keys,
  pre-keys). Written often and concurrently. Worth its own store with
  per-key files (or a DB backend).

The split also means you can back `keys` with a database while keeping
`creds` as a JSON file in a config folder — useful when the keys
outgrow a single file (tens of thousands of contacts).

## How events flow

```
WebSocket frame
      ↓
NoiseHandler.decode_frame()  →  bytes
      ↓
decode_binary_node()         →  BinaryNode
      ↓
WASocket._handle_frame()     →  _dispatch_node()
      ↓
BaileysEventEmitter.emit("messages.upsert", payload)
      ↓
Your listener (sync or async)
```

Listeners run on the event loop. If a listener raises, the emitter
logs a traceback but never crashes the recv loop.

## How sending works

```
sock.send_message(jid, {"text": "hi"})
      ↓
WASocket._build_message_payload(content, jid, user_jid)
      ↓ (returns a dict; with WAProto wired in, returns a proto.Message)
WASocket.send_raw_frame(<message> node)
      ↓
encode_binary_node(node)              →  bytes
      ↓
NoiseHandler.encode_frame(bytes)     →  framed bytes (intro header on first)
      ↓
WebSocket.send(framed bytes)
```

## Why does the public API support sync **and** async listeners?

WhatsApp bots often have a mix of listeners:

* **Sync**: pure logging, simple state updates
* **Async**: database writes, HTTP requests, sending replies

Forcing everyone through `async def` makes sync-style code harder
(it's awkward to write `async def on_msg(_): print("hi")`); forcing
sync only means async users have to wrap their code in
`asyncio.ensure_future`. baileys-py supports both — the emitter calls
`asyncio.ensure_future` automatically when it sees an awaitable return
value.

## Why is `pino` not a dependency?

Upstream Baileys logs via `pino`. The PyPI package called `pino`
exists but is unrelated (a Python JSON logger inspired by pino.js)
and was incorrectly listed as a dependency in early versions of
baileys-py. We ship our own [`baileys_py.logger`](../baileys_py/logger.py)
that exposes a pino-style API (`log.info({"k": "v"}, "msg")`) on top of
Python's stdlib `logging`. No third-party logger required.

## Extending baileys-py (enabling full WA interop)

To enable real WhatsApp messaging, you need the WA protobuf schema
(the `.proto` file upstream ships at `Baileys/WAProto/WAProto.proto`).
Once you have it:

```bash
# 1) Compile the .proto to Python
protoc --python_out=baileys_py/proto/ WAProto.proto
```

```python
# 2) Override the two hooks in WASocket:

from baileys_py import WASocket, BinaryNode
from baileys_py.proto import wa_pb2   # the module you just generated


class FullWASocket(WASocket):
    async def _build_message_payload(self, content: dict, jid: str, user_jid: str):
        msg = wa_pb2.Message()
        if "text" in content:
            msg.conversation = content["text"]
        # ... fill in the rest of the message types ...
        return msg.SerializeToString()

    async def _handle_frame(self, frame: bytes):
        node = decode_binary_node(frame)
        if node.tag == "message":
            # decrypt the <enc> payload using the Signal session,
            # parse with wa_pb2.WebMessageInfo, then emit
            decoded = self._decrypt_message(node)
            self.ev.emit("messages.upsert", {"messages": [decoded], "type": "notify"})
        else:
            await super()._handle_frame(frame)
```

That's it — the rest of the package (noise, crypto, binary protocol,
auth state, events, socket loop) already handles the lower layers.

## Why is certificate verification optional?

The WA Noise handshake includes a server certificate chain. Upstream
Baileys hard-codes the WA long-term public key and verifies the chain
in `processHandshake`. We expose `verify_certificate=callback` so you
can wire in your own check (using the WA protobuf definitions to parse
the cert). If you omit the callback, we skip verification —
**suitable for testing, NOT for production**.

## Why no pre-built binary wheels?

baileys-py is 100% pure Python. The only "C" dependency is
`cryptography`, which ships wheels for every supported platform. No
compilation needed at install time.

## Reproducibility

`pyproject.toml` pins nothing strictly — only minimum versions. If
you need a reproducible install, pin everything in your own
`requirements.txt`:

```text
websockets==11.0.3
cryptography==41.0.7
qrcode==7.4.2
protobuf==4.24.4
aiofiles==23.2.1
```

## Test coverage

The 13 tests in `tests/test_smoke.py` cover:

* JID encode / decode round-trip
* BinaryNode encode / decode round-trip (with bytes content too)
* Curve25519 keypair + ECDH
* HKDF-64
* AES-GCM round-trip
* AES-CTR round-trip
* Noise handler first-frame (intro header included)
* Multi-file auth state round-trip (save → reload → assert)
* `make_wa_socket` raises without `auth`
* `make_wa_socket` builds with `auth`, event emitter works
* Logger emit (no exception)

All tests are pure-Python and require no network access.

## Adding new high-level helpers

If you need an operation not covered by `baileys_py.messages`, follow
the pattern there:

1. Build a `BinaryNode` representing the IQ query.
2. Call `await sock.query(node)`.
3. Parse the response with `get_binary_node_child` etc.

Example (fetching the list of blocked users):

```python
from baileys_py import BinaryNode, get_binary_node_child


async def get_blocklist(sock):
    node = BinaryNode(
        tag="iq",
        attrs={"to": "@s.whatsapp.net", "type": "get", "xmlns": "block"},
        content=[BinaryNode(tag="list")],
    )
    resp = await sock.query(node)
    list_node = get_binary_node_child(resp, "list")
    if not list_node or not isinstance(list_node.content, list):
        return []
    return [item.attrs.get("jid") for item in list_node.content]
```

Drop your helper in `baileys_py/messages.py` and re-export from
`baileys_py/__init__.py`.

## Regenerating the binary constants

If you bump the upstream Baileys version and the token dictionaries
changed:

```bash
python scripts/build_constants.py
```

The script expects the upstream Baileys repo to be cloned at
`/home/z/my-project/Baileys/`. Edit the `SRC` path at the top of the
script to point elsewhere.
