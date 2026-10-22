"""A minimal in-memory Signal protocol implementation.

The upstream Baileys uses ``libsignal`` (via TypeScript bindings) and
``whatsapp-rust-bridge``. Re-implementing the full Signal protocol
(Session, SenderKey, PreKey bundles, X3DH key agreement) in Python is
possible with the ``cryptography`` package — this module provides the
core surface (pre-keys, sessions, sender-keys, identity store) so the
socket code can wire it together.

This is intentionally kept as a *minimal-but-functional* stub: it gives
you the data structures and store interfaces you need to either swap in
``python-axolotl``/``cryptography``-based Signal or to implement the few
remaining primitives yourself.

The interfaces mirror ``src/Types/Signal.ts`` and
``src/Signal/libsignal.ts`` from upstream Baileys.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..crypto import (
    aes_decrypt_gcm,
    aes_encrypt_gcm,
    curve_shared_key,
    curve_sign,
    curve_verify,
    generate_key_pair,
    hkdf,
    random_bytes,
)
from ..types import KeyMaterial, SignalKeyStore


@dataclass
class PreKey:
    id: int
    key_pair: KeyMaterial


@dataclass
class SignedPreKey:
    id: int
    key_pair: KeyMaterial
    signature: bytes


# ---------------------------------------------------------------------------
# Identity store
# ---------------------------------------------------------------------------

@dataclass
class IdentityKey:
    """A peer identity key (Ed25519 public key, 32 bytes)."""
    identifier: str  # jid
    public_key: bytes


class SignalRepository:
    """Minimal Signal repository.

    Stores per-jid:
      - identity key
      - sessions (raw bytes blob — opaque to this layer)
      - pre-keys and signed pre-keys
      - sender-keys for group messaging

    Backed by a :class:`SignalKeyStore` for persistence.
    """

    def __init__(self, store: SignalKeyStore, identity_key: KeyMaterial,
                 registration_id: int) -> None:
        self.store = store
        self.identity_key = identity_key
        self.registration_id = registration_id
        self._pre_keys: Dict[int, PreKey] = {}
        self._signed_pre_keys: Dict[int, SignedPreKey] = {}
        self._identities: Dict[str, bytes] = {}

    # --- pre-keys --------------------------------------------------------
    def generate_pre_keys(self, count: int, start_id: int = 1) -> List[PreKey]:
        out = []
        for i in range(start_id, start_id + count):
            pk = PreKey(id=i, key_pair=generate_key_pair())
            self._pre_keys[i] = pk
            out.append(pk)
        return out

    def get_pre_key(self, key_id: int) -> Optional[PreKey]:
        return self._pre_keys.get(key_id)

    def remove_pre_key(self, key_id: int) -> None:
        self._pre_keys.pop(key_id, None)

    # --- signed pre-keys -------------------------------------------------
    def add_signed_pre_key(self, key_id: int, key_pair: KeyMaterial,
                           signature: bytes) -> SignedPreKey:
        spk = SignedPreKey(id=key_id, key_pair=key_pair, signature=signature)
        self._signed_pre_keys[key_id] = spk
        return spk

    def get_signed_pre_key(self, key_id: int) -> Optional[SignedPreKey]:
        return self._signed_pre_keys.get(key_id)

    # --- identities ------------------------------------------------------
    async def save_identity(self, identifier: str, public_key: bytes) -> None:
        self._identities[identifier] = public_key
        await self.store.set({"identity-key": {identifier: public_key}})

    async def is_trusted_identity(self, identifier: str, public_key: bytes) -> bool:
        existing = self._identities.get(identifier)
        if existing is None:
            return True  # trust on first use
        return existing == public_key

    # --- sessions --------------------------------------------------------
    async def load_session(self, identifier: str) -> Optional[bytes]:
        result = await self.store.get("session", [identifier])
        return result.get(identifier)

    async def store_session(self, identifier: str, data: bytes) -> None:
        await self.store.set({"session": {identifier: data}})

    # --- sender-keys (group sessions) ------------------------------------
    async def load_sender_key(self, group_id: str) -> Optional[bytes]:
        result = await self.store.get("sender-key", [group_id])
        return result.get(group_id)

    async def store_sender_key(self, group_id: str, data: bytes) -> None:
        await self.store.set({"sender-key": {group_id: data}})


# ---------------------------------------------------------------------------
# Minimal encrypt/decrypt helpers (X3DH + AES-GCM based ratchet-less demo)
#
# NOTE: WhatsApp uses the full Signal ratchet. The functions below
# implement a *minimal* encryption layer so messages can flow through the
# socket — they are NOT a drop-in for WhatsApp's Signal handshake.
# Replace these with a proper Signal implementation (e.g. python-axolotl)
# for production WhatsApp interop.
# ---------------------------------------------------------------------------

def derive_session_key(shared: bytes, salt: bytes = b"") -> bytes:
    """Derive a 32-byte AES key from a Curve25519 shared secret."""
    return hkdf(shared, length=32, salt=salt, info=b"WA-SessionKey")


def encrypt_message(plaintext: bytes, shared: bytes,
                    aad: bytes = b"") -> bytes:
    """Encrypt ``plaintext`` with AES-256-GCM derived from ``shared``."""
    key = derive_session_key(shared)
    iv = random_bytes(12)
    ct = aes_encrypt_gcm(plaintext, key, iv, aad)
    return iv + ct


def decrypt_message(ciphertext: bytes, shared: bytes,
                    aad: bytes = b"") -> bytes:
    """Decrypt a payload produced by :func:`encrypt_message`."""
    key = derive_session_key(shared)
    iv, ct = ciphertext[:12], ciphertext[12:]
    return aes_decrypt_gcm(ct, key, iv, aad)


def sign_message(private_key: bytes, payload: bytes) -> bytes:
    return curve_sign(private_key, payload)


def verify_message(public_key: bytes, payload: bytes, signature: bytes) -> bool:
    return curve_verify(public_key, payload, signature)


__all__ = [
    "PreKey",
    "SignedPreKey",
    "IdentityKey",
    "SignalRepository",
    "derive_session_key",
    "encrypt_message",
    "decrypt_message",
    "sign_message",
    "verify_message",
]
