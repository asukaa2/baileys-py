# Changelog

All notable changes to baileys-py will be documented here. The format
is based on [Keep a Changelog](https://keepachangelog.com/) and the
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned

* Wire in `WAProto/` protobuf schema for full message encryption / decryption
* Implement full Signal ratchet (Session + SenderKey + X3DH)
* Newsletter (channels) helpers
* Business catalog / payments helpers
* Real QR payload generation (currently scaffolded)
* Real pairing-code flow (currently generates a random 8-char code)

## [0.1.0] — 2026-10-22

### Added

* **Initial public release.**
* Binary protocol layer (`baileys_py.binary`):
  * `BinaryNode` dataclass + traversal helpers (`get_binary_node_child`, etc.)
  * `encode_binary_node` / `decode_binary_node` round-trip
  * Auto-generated `constants.py` (1,300+ lines) with single-byte (236)
    and double-byte (4×256) token dictionaries + precomputed `TOKEN_MAP`
  * Full `jid_encode` / `jid_decode` / `is_jid_*` port
* Crypto layer (`baileys_py.crypto`):
  * Curve25519 key generation, ECDH shared secret
  * Ed25519 sign / verify
  * HKDF-SHA256
  * AES-256-GCM (tag suffixed, WA convention)
  * AES-256-CTR
  * AES-256-CBC (IV prefixed, PKCS7)
  * HMAC-SHA256, SHA-256, MD5
  * Signed pre-key generation
* Noise XX handshake + transport (`baileys_py.noise_handler`):
  * Full Noise XX state machine (init, authenticate, mix into key, finish init)
  * Counter-based IV (12 bytes)
  * Transport encryption / decryption with separate enc/dec keys
  * Frame encoding with intro header (`WA\x06\x03`) on first frame
  * Frame decoding with 3-byte length prefix
  * Optional `verify_certificate` callback
* Socket layer (`baileys_py.socket`):
  * `WASocket` class with WebSocket connect / recv / keepalive loops
  * `make_wa_socket(config=None, **kwargs)` factory
  * `send_message(jid, content, options=None)` for text / image / audio / video / document / sticker / location / contact / reply / poll / react / edit / delete
  * `send_raw_frame(node)` for direct binary protocol sends
  * `query(node, timeout_ms=None)` for IQ request/response with future matching by id
  * `request_pairing_code(phone)` helper
  * Auto-reconnect hooks via `connection.update` events
* Auth state (`baileys_py.auth`):
  * `init_auth_creds()` — fresh credential generation
  * `use_multi_file_auth_state(folder)` — one JSON file per credential
  * `use_single_file_auth_state(path)` — single JSON file
  * `creds_to_dict` / `creds_from_dict` for custom backends
  * Async-safe file writes (`asyncio.Lock`)
* Event emitter (`baileys_py.events`):
  * `BaileysEventEmitter` with sync + async listeners
  * `process(processor)` for batched event handling (mirrors upstream `ev.process`)
  * `off`, `remove_all_listeners`, `stop_processing`
* High-level helpers (`baileys_py.messages`):
  * Group: `group_create`, `group_invite_code`, `group_join`, `group_leave`, `group_participants_update`
  * Chat: `chat_send_message`, `chat_archive`, `chat_pin`, `chat_mark_read`
  * Presence: `send_presence_update`
  * Profile: `get_profile_picture_url`, `update_profile_name`, `update_profile_status`
* Logger (`baileys_py.logger`):
  * pino-style API on top of stdlib `logging`
  * `Logger.child({"class": "..."})` for scoped loggers
  * `trace` / `debug` / `info` / `warn` / `error` / `fatal` levels
* Defaults & constants (`baileys_py.defaults`):
  * `DEFAULT_CONNECTION_CONFIG`
  * `DEFAULT_VERSION`, `WA_WEBSOCKET_URL`, `NOISE_MODE`, `NOISE_WA_HEADER`, `KEY_BUNDLE_TYPE`
  * `WA_DEFAULT_EPHEMERAL`, `PROCESSABLE_HISTORY_TYPES`, `TimeMs`
* Signal store stub (`baileys_py.signal.repository`):
  * `SignalRepository` with pre-key / signed-pre-key / identity / session / sender-key stores
  * `encrypt_message` / `decrypt_message` (minimal AES-GCM, not the full ratchet)
* Tests:
  * 13 smoke tests in `tests/test_smoke.py` (all pass, no network needed)
  * JID round-trip, binary protocol round-trip, crypto round-trips, noise handshake, auth state persistence, socket construction, event emitter
* Examples:
  * `examples/basic.py` — QR login + echo bot
  * `examples/pairing_code.py` — pairing-code login
* Scripts:
  * `scripts/build_constants.py` — regenerate binary token dictionaries from upstream Baileys' `constants.ts`
* Packaging:
  * `pyproject.toml` with proper `[build-system]`, `[project]`, `[tool.setuptools.packages.find]`
  * `setup.py` fallback for older pip / uv versions
  * `MANIFEST.in` to include non-Python files in sdist
  * `py.typed` marker (PEP 561)
  * `LICENSE` (MIT)
* Documentation:
  * Comprehensive `docs/` folder with 15 markdown pages
  * README at repo root

### Scaffolded (interfaces ready, full interop pending)

* `WASocket.send_message` — high-level API + event emission work; actual wire send requires WAProto
* QR / pairing-code login — helpers exist; actual QR payload needs WAProto
* Group / chat / presence / profile helpers — IQ stanzas built; replace with real WA protobuf once wired
* Signal protocol — minimal in-memory store; not a drop-in for `libsignal`
* Certificate verification in Noise handshake — optional callback; skip by default

### Notes

* `pino` is **not** a runtime dependency. baileys-py ships its own
  `baileys_py.logger`. (Earlier drafts mistakenly listed `pino`.)
* baileys-py is a community port and is not affiliated with WhatsApp
  or Meta. Using non-official clients may violate WhatsApp's ToS —
  read them yourself and decide.
