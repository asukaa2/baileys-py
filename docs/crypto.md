# Crypto layer

baileys-py uses the [`cryptography`](https://cryptography.io) library
for all cryptographic primitives. There are no native binaries —
everything is pure Python and audited by the cryptography maintainers.

## Modules

| Module | Purpose |
|---|---|
| `baileys_py.crypto` | Curve25519, Ed25519, HKDF, AES-GCM/CTR/CBC, HMAC, SHA-256, MD5 |
| `baileys_py.noise_handler` | Noise XX handshake + transport encryption/framing |
| `baileys_py.signal.repository` | In-memory Signal protocol store (PreKey, SignedPreKey, sessions, sender-keys, identities) |

## Curve25519 / Ed25519

```python
from baileys_py import generate_key_pair, curve_shared_key, curve_sign, curve_verify

# Generate a Curve25519 keypair (used for ECDH on the noise channel)
kp = generate_key_pair()
# kp.private: 32 bytes
# kp.public:  32 bytes (no version-byte prefix — we store raw pub keys)

# ECDH shared secret
other = generate_key_pair()
shared = curve_shared_key(kp.private, other.public)  # 32 bytes

# Sign with Ed25519 (identity keys)
sig = curve_sign(kp.private, b"hello")
ok = curve_verify(kp.public, b"hello", sig)  # True

# Prepend the 0x05 version byte (some WA functions require it)
from baileys_py import generate_signal_pub_key
pub33 = generate_signal_pub_key(kp.public)  # 33 bytes
```

## Signed pre-key

```python
from baileys_py import signed_key_pair

identity_kp = generate_key_pair()
spk = signed_key_pair(identity_kp.private, key_id=1)
# spk.key_pair.public    -> X25519 pub key
# spk.key_pair.private   -> X25519 priv key
# spk.signature          -> Ed25519 signature over the 33-byte pub key
# spk.key_id             -> int
```

## HKDF (RFC 5869, SHA-256)

```python
from baileys_py import hkdf

key = hkdf(secret=b"shared", length=64, salt=b"salt", info=b"info")
# 64 bytes of keying material
```

## AES

| Function | Mode | Notes |
|---|---|---|
| `aes_encrypt_gcm(pt, key, iv, aad=b"")` / `aes_decrypt_gcm` | AES-256-GCM | Auth tag suffixed to ciphertext (WA convention) |
| `aes_encrypt_ctr(pt, key, iv)` / `aes_decrypt_ctr` | AES-256-CTR | Used by noise transport |
| `aes_encrypt(pt, key)` / `aes_decrypt` | AES-256-CBC | Random 16-byte IV prefixed; PKCS7 padding |

```python
from baileys_py import (
    aes_encrypt_gcm, aes_decrypt_gcm,
    aes_encrypt_ctr, aes_decrypt_ctr,
    aes_encrypt, aes_decrypt,
    random_bytes,
)

key = random_bytes(32)
iv  = random_bytes(12)
aad = b"associated-data"
ct  = aes_encrypt_gcm(b"hello", key, iv, aad)
# ct includes the 16-byte GCM auth tag at the end
pt  = aes_decrypt_gcm(ct, key, iv, aad)
assert pt == b"hello"
```

## HMAC / hashing

```python
from baileys_py import hmac_sign, hmac_verify, sha256, md5

mac  = hmac_sign(key=b"k", data=b"data")
ok   = hmac_verify(key=b"k", data=b"data", signature=mac)
h    = sha256(b"abc")
m    = md5(b"abc")
```

## Noise XX handshake

WhatsApp uses the Noise XX pattern (`Noise_XX_25519_AESGCM_SHA256`)
over WebSocket. The handshake is done once per WebSocket connection;
after that, the noise handler produces transport keys and encrypts /
decrypts every frame.

```python
from baileys_py import NoiseHandler, generate_key_pair, NOISE_WA_HEADER

client_kp = generate_key_pair()
noise_kp = generate_key_pair()

handler = NoiseHandler(client_kp, noise_header=NOISE_WA_HEADER)

# First frame includes the WA intro header
first = handler.encode_frame(b"hello")
# first starts with b"WA\x06\x03"

# Subsequent frames do NOT include the intro header
second = handler.encode_frame(b"world")

# Process the server hello (you'd parse this from WA's protobuf
# HandshakeMessage; the API here accepts the raw bytes)
key_enc = handler.process_handshake(
    server_hello_ephemeral=...,
    server_hello_static=...,
    server_hello_payload=...,
    noise_key=noise_kp,
)

# Transition to transport mode
handler.finish_init()

# Now encrypt/decrypt with transport keys
ct = handler.encode_frame(b"some node")
frames = handler.decode_frame(some_incoming_bytes)
```

The `WASocket` class wires this up automatically — you only need
`NoiseHandler` directly if you're building your own socket.

## Counter-based IV

The noise transport uses a 12-byte IV where the first 8 bytes are zero
and the last 4 bytes are a 32-bit big-endian counter. baileys-py
manages this internally — you never see the IV.

## Signal protocol

```python
from baileys_py.signal import SignalRepository, encrypt_message, decrypt_message

repo = SignalRepository(
    store=state.keys,                # your SignalKeyStore
    identity_key=creds.signed_identity_key,
    registration_id=creds.registration_id,
)

# Pre-key generation
repo.generate_pre_keys(count=50, start_id=1)

# Trust on first use
await repo.save_identity("62XXX@s.whatsapp.net", their_pubkey)

# Encrypt / decrypt a message body
shared = curve_shared_key(my_session_key, their_session_key)
ct = encrypt_message(b"hello", shared, aad=b"")
pt = decrypt_message(ct, shared, aad=b"")
```

> **Note**: `encrypt_message` / `decrypt_message` here use a
> single-shot AES-GCM with an HKDF-derived key. They are **not** the
> Signal ratchet — to do real Signal sessions, plug in a proper Signal
> implementation (e.g. `python-axolotl`) and replace these helpers.

## Cert verification

The Noise handshake includes a server certificate chain (the WA
"long-term" cert + an intermediate + a leaf). Upstream Baileys verifies
the signature with `WA_CERT_DETAILS.PUBLIC_KEY` and checks the
`issuerSerial`.

baileys-py leaves this as an optional callback so you can wire in the
WA protobuf definitions:

```python
def verify_cert(cert_bytes: bytes) -> bool:
    # Parse with your WAProto module, verify with WA_CERT_DETAILS.PUBLIC_KEY
    return True

handler = NoiseHandler(client_kp, verify_certificate=verify_cert)
```

If the callback is omitted, certificate verification is skipped
(suitable for testing / experimentation; not recommended for
production).
