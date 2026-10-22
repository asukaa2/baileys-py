# API reference

A complete list of everything exported from the top-level `baileys_py`
package. Each entry has its call signature.

> All async functions return a coroutine — you must `await` them.

## Socket

### `make_wa_socket(config: SocketConfig | None = None, **kwargs) -> WASocket`

Create a socket. Either pass a `SocketConfig` or individual kwargs:

```python
sock = make_wa_socket(auth=state, push_name="My Bot", wa_websocket_url="wss://...")
```

Required: `auth` (an `AuthenticationState`). Everything else has a
sane default in `DEFAULT_CONNECTION_CONFIG`.

### `class WASocket`

The socket itself. Key methods:

| Method | Returns | Description |
|---|---|---|
| `await sock.connect()` | `None` | Open the WebSocket, start recv + keepalive loops |
| `await sock.disconnect()` | `None` | Cancel loops, close WS |
| `await sock.send_message(jid, content, options=None)` | `WAMessage` | Send any kind of message |
| `await sock.send_raw_frame(node: BinaryNode)` | `None` | Encode a node and write it to the WS |
| `await sock.query(node: BinaryNode, timeout_ms=None)` | `BinaryNode` | Send an IQ and await its response by id |
| `await sock.request_pairing_code(phone: str)` | `str` | Request an 8-char pairing code |
| `sock.ev` | `BaileysEventEmitter` | Event emitter (`.on`, `.off`, `.emit`, `.process`) |
| `sock.user` | `dict \| None` | `{id, name}` once authenticated |
| `sock.auth_state` | `AuthenticationState` | The state you passed in |
| `sock.auth_state.creds` | `AuthenticationCreds` | Mutable credential dataclass |
| `sock.config` | `SocketConfig` | Effective config (defaults + overrides merged) |

## Auth

### `init_auth_creds() -> AuthenticationCreds`

Generate a fresh credential object (new keypairs, new registration id,
new adv secret key). Used internally by `use_multi_file_auth_state`.

### `await use_multi_file_auth_state(folder: str) -> (AuthenticationState, save_creds)`

Returns `(state, save_creds)`. `save_creds` is an async callable that
persists `creds.json` to disk.

### `await use_single_file_auth_state(path: str) -> (AuthenticationState, save_creds)`

Same, but in a single JSON file.

### `creds_to_dict(creds) -> dict` / `creds_from_dict(d) -> AuthenticationCreds`

Serialisation helpers (used by the multi-file backend; useful for
custom backends too).

## Types

| Type | Notes |
|---|---|
| `SocketConfig` | User-facing socket config (dataclass) |
| `AuthenticationCreds` | Persistent credentials (dataclass) |
| `AuthenticationState` | `{creds, keys}` |
| `SignalKeyStore` | Abstract key store interface |
| `CacheStore` | Abstract cache store interface |
| `KeyMaterial` | `{private: bytes, public: bytes}` (32-byte Curve25519 keys) |
| `SignedKeyMaterial` | `{key_pair, signature, key_id, timestamp_s?}` |
| `SignalIdentity` | `{identifier: ProtocolAddress, identifier_key: bytes}` |
| `ProtocolAddress` | `{name: str, device_id: int}` |
| `WAMessage` | `{key, message, message_timestamp, status?, participant?, push_name?}` |
| `WAMessageKey` | `{remote_jid, from_me, id, participant?}` |
| `AnyMessageContent` | `str \| dict` |
| `MiscMessageGenerationOptions` | `{message_id?, quoted?, timestamp?, participant?, use_cached_group_metadata?}` |
| `ConnectionState` | `{connection?, last_disconnect?, qr?, received_pending_notifications?, is_online?, user?}` |
| `DisconnectReason` | Enum of close reasons (`.logged_out`, `.connection_lost`, etc.) |
| `MessageUpsertType` | Enum: `notify`, `append` |
| `MediaConnInfo` | `{hosts, auth, ttl, fetched_at}` |
| `WAVersion` | `Tuple[int, int, int]` |
| `WABrowserDescription` | `Tuple[str, str, str]` |

## Binary protocol

| Name | Signature |
|---|---|
| `encode_binary_node(node: BinaryNode) -> bytes` | Encode → wire format |
| `decode_binary_node(buf: bytes) -> BinaryNode` | Decode (handles compression) |
| `decode_decompressed_binary_node(buf: bytes, index=0) -> BinaryNode` | Decode already-decompressed |
| `decompress_if_required(buf: bytes) -> bytes` | Strip + zlib-decompress if needed |
| `get_binary_node_child(node, tag) -> BinaryNode \| None` | First child by tag |
| `get_binary_node_children(node, tag) -> List[BinaryNode]` | All children by tag |
| `get_all_binary_node_children(node) -> List[BinaryNode]` | All children (any tag) |
| `get_binary_node_child_buffer(node, tag) -> bytes \| None` | Child content as bytes |
| `get_binary_node_child_string(node, tag) -> str \| None` | Child content as string |
| `get_binary_node_child_uint(node, tag, length) -> int \| None` | Child content as uint |
| `assert_node_error_free(node)` | Raise if `<error>` child present |
| `reduce_binary_node_to_dictionary(node, tag) -> dict` | Build `{name: value}` from `<item>` children |
| `binary_node_to_string(node, indent=0) -> str` | Pretty-print |

## JID helpers

| Name | Description |
|---|---|
| `jid_encode(user, server, device=None, agent=None) -> str` | Build a JID |
| `jid_decode(jid) -> FullJid \| None` | Parse a JID |
| `jid_normalized_user(jid) -> str` | Strip `:device`, rewrite `c.us` → `s.whatsapp.net` |
| `are_jids_same_user(a, b) -> bool` | Same `user` part? |
| `is_jid_group(jid)` / `is_jid_broadcast` / `is_jid_newsletter` / `is_jid_status_broadcast` | Type predicates |
| `is_pn_user(jid)` / `is_lid_user` / `is_hosted_pn_user` / `is_hosted_lid_user` | Type predicates |
| `is_jid_meta_ai(jid)` / `is_jid_bot(jid)` | Meta AI / bot detection |
| `transfer_device(from_jid, to_jid) -> str` | Move the `:device` suffix onto another JID |

## Crypto

| Name | Returns |
|---|---|
| `generate_key_pair() -> KeyMaterial` | Fresh Curve25519 keypair |
| `curve_shared_key(private, public) -> bytes` | ECDH shared secret |
| `curve_sign(private, data) -> bytes` | Ed25519 signature |
| `curve_verify(public, data, signature) -> bool` | Ed25519 verify |
| `generate_signal_pub_key(pub) -> bytes` | Prepend `0x05` version byte |
| `signed_key_pair(identity_priv, key_id) -> SignedKeyMaterial` | Build a signed pre-key |
| `generate_registration_id() -> int` | 14-bit random id |
| `hkdf(secret, length, salt=b"", info=b"") -> bytes` | HKDF-SHA256 |
| `aes_encrypt_gcm(pt, key, iv, aad=b"")` / `aes_decrypt_gcm` | AES-256-GCM (tag suffixed) |
| `aes_encrypt_ctr(pt, key, iv)` / `aes_decrypt_ctr` | AES-256-CTR |
| `aes_encrypt(pt, key)` / `aes_decrypt` | AES-256-CBC (IV prefixed) |
| `hmac_sign(key, data)` / `hmac_verify(key, data, sig)` | HMAC-SHA256 |
| `sha256(data)` / `md5(data)` | Hashing |
| `random_bytes(n) -> bytes` | CSPRNG |

## Noise

| Name | Returns |
|---|---|
| `NoiseHandler(key_pair, noise_header=NOISE_WA_HEADER, routing_info=None, verify_certificate=None)` | New handler |
| `handler.encode_frame(data: bytes) -> bytes` | Frame `data` (with intro header on first call) |
| `handler.decode_frame(new_data: bytes) -> List[bytes]` | Decode incoming bytes into frames |
| `handler.process_handshake(...)` -> bytes | Process server hello |
| `handler.finish_init()` | Transition to transport mode |
| `handler.encrypt(pt)` / `handler.decrypt(ct)` | Pre-transport encrypt / decrypt |

## Defaults

| Name | Description |
|---|---|
| `DEFAULT_CONNECTION_CONFIG` | `SocketConfig` with all defaults filled in |
| `DEFAULT_VERSION` | `(2, 3000, 1043857760)` |
| `WA_WEBSOCKET_URL` | `"wss://web.whatsapp.com/ws/chat"` |
| `DEFAULT_ORIGIN` | `"https://web.whatsapp.com"` |
| `WA_DEFAULT_EPHEMERAL` | `7 * 24 * 60 * 60` (seconds in 7 days) |
| `NOISE_MODE` | `b"Noise_XX_25519_AESGCM_SHA256\x00\x00\x00\x00"` |
| `NOISE_WA_HEADER` | `b"WA\x06\x03"` |
| `KEY_BUNDLE_TYPE` | `bytes([5])` |
| `TimeMs` | Class with `Minute`, `Hour`, `Day`, `Week` |
| `default_browser()` | `("Chrome", "10.15.7", "0")` |

## Events / logger

| Name | Description |
|---|---|
| `BaileysEventEmitter` | The event emitter class |
| `Logger` | pino-style logger (backed by `logging`) |
| `get_logger(name="baileys", level="info") -> Logger` | Quick constructor |

## Messages helpers (`from baileys_py.messages import ...`)

| Name | Signature |
|---|---|
| `chat_send_message(sock, jid, content)` | Alias for `sock.send_message` |
| `chat_archive(sock, jid, archive=True)` | Archive / unarchive |
| `chat_pin(sock, jid, pin=True)` | Pin / unpin |
| `chat_mark_read(sock, jid, message_keys)` | Mark read |
| `group_create(sock, subject, participants=None)` | Create a group |
| `group_invite_code(sock, group_jid)` | Get invite code |
| `group_join(sock, code)` | Join by invite code |
| `group_leave(sock, group_jid)` | Leave a group |
| `group_participants_update(sock, group_jid, participants, action)` | Add/remove/promote/demote |
| `send_presence_update(sock, jid, presence)` | Set presence |
| `get_profile_picture_url(sock, jid, high_res=True)` | Get profile pic URL |
| `update_profile_name(sock, name)` | Update your name |
| `update_profile_status(sock, status)` | Update your about |

## Utils

| Name | Returns |
|---|---|
| `generate_message_id_v2(user_id=None) -> str` | 20-char hex id |
| `generate_message_tag() -> str` | Short unique tag |
| `unix_timestamp_seconds() -> int` | Current unix time |
| `await fetch_latest_baileys_version() -> dict` | `{"version", "is_latest"}` |
| `get_aggregate_votes_in_poll_message(message, poll_updates=None) -> list` | Poll aggregation |
| `await promise_timeout(coro, timeout_ms=None)` | Await with timeout |
| `delay_ms(ms)` | `asyncio.sleep(ms/1000)` |
| `get_call_link(id_) -> str` | WhatsApp call link |
| `is_jid_broadcast_(jid)` / `is_jid_group_(jid)` / `is_jid_newsletter_(jid)` | Aliases |
