# Overview

`baileys-py` is a Python re-implementation of the [Baileys](https://github.com/whiskeysockets/Baileys)
WhatsApp Web API. It is **not** a 1-to-1 translation of every TypeScript
file — instead it keeps the same high-level surface (`make_wa_socket`,
`use_multi_file_auth_state`, `sock.ev.on(...)`, `sock.send_message(...)`)
while using Python idioms:

| TypeScript (Baileys) | Python (baileys-py) |
|---|---|
| `makeWASocket(config)` | `make_wa_socket(auth=state, **kwargs)` |
| `sock.ev.on("connection.update", cb)` | same (cb may be sync or async) |
| `sock.sendMessage(jid, { text })` | `await sock.send_message(jid, {"text": ...})` |
| `useMultiFileAuthState(folder)` | `await use_multi_file_auth_state(folder)` |
| `isJidGroup(jid)` | `is_jid_group(jid)` |
| `DisconnectReason.loggedOut` | `DisconnectReason.logged_out` |
| `proto.WebMessageInfo.decode(...)` | requires `WAProto/` protobuf module (see [internals](internals.md)) |

## Design goals

1. **Simple, predictable API.** No surprising inheritance, no fluent
   builders — just plain functions and a single `WASocket` class.
2. **Pythonic.** snake_case, async/await everywhere, `dataclass`-based
   types, plain `logging`-backed logger with a pino-style call signature.
3. **No opaque native binaries.** The upstream Baileys depends on
   `libsignal` (Node bindings) and `whatsapp-rust-bridge`. baileys-py
   uses pure-Python `cryptography` instead.
4. **Easy to extend.** The few places that genuinely need the WhatsApp
   protobuf schema are left as explicit hooks. You can drop in your own
   `WAProto/` module and replace a couple of methods to enable full
   protocol interop.

## Status by layer

| Layer | Status | Notes |
|---|---|---|
| JID utilities | ✅ Complete | Full port of `jid-utils.ts` |
| Binary protocol encode / decode | ✅ Complete | Token dictionaries auto-generated from upstream (1,300+ lines) |
| Crypto primitives (Curve25519, Ed25519, HKDF, AES-GCM/CTR, HMAC) | ✅ Complete | Backed by `cryptography` |
| Noise XX handshake + transport | ✅ Complete | Full framing + counter-based IV |
| Multi-file / single-file auth state | ✅ Complete | Round-trip JSON persistence |
| Event emitter (with batched `process()`) | ✅ Complete | Sync + async listeners |
| WebSocket connect, recv loop, keepalive, IQ query/response | ✅ Complete | `websockets` library |
| `send_message` API surface | ⚠️ Scaffolded | High-level API ready; full message encryption requires WA protobuf |
| QR-code / pairing-code login | ⚠️ Scaffolded | Helpers present; actual QR payload bytes need WA protobuf |
| Group / chat / presence / profile helpers | ⚠️ Scaffolded | IQ stanzas built; replace with real WA protobuf once wired |
| Signal protocol (Session, SenderKey, X3DH) | ⚠️ Minimal | In-memory store; not a drop-in for `libsignal` |

## What "scaffolded" means

A scaffolded layer has the **public API and data structures** in place,
but the actual WhatsApp-specific protobuf encoding / decoding is left
out because that requires shipping the WhatsApp protobuf schema
(`WAProto/`), which is a large generated module.

For each scaffolded layer, the README and the doc page show exactly
which method or hook you need to override to enable full interop.
Typically it's one method (`WASocket._build_message_payload` or
`WASocket._handle_frame`) that you replace with a protobuf-aware
implementation.

See [Internals → Extending baileys-py](internals.md#extending-baileys-py)
for a concrete example.

## Comparison with other WhatsApp libraries for Python

| Library | Backend | Maintenance | Notes |
|---|---|---|---|
| `baileys-py` (this one) | WhatsApp Web (multi-device) | Active | Pure Python, ports Baileys |
| `whatsapp-web.js` (Node) | WhatsApp Web (puppeteer) | Active | Requires Node + headless Chrome |
| `yowsup` (Python) | Old WA protocol | Largely unmaintained | Targets the legacy WA protocol |
| `baileys` (TypeScript) | WhatsApp Web (multi-device) | Active | The upstream we port from |

## License

MIT — same as upstream Baileys. See [LICENSE](../LICENSE).
