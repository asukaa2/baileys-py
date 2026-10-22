"""Crypto helpers used throughout the package.

Implements the subset of Baileys' crypto utilities that we need:
- Curve25519 key generation, ECDH, signing/verifying
- HKDF (RFC 5869) using SHA-256
- AES-256 GCM / CTR with the same convention Baileys uses
  (auth tag suffixed to ciphertext for GCM)
- HMAC-SHA256 and SHA-256 helpers

All functions operate on ``bytes`` / ``bytearray``.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import os
import struct
from typing import Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .defaults import KEY_BUNDLE_TYPE
from .types import KeyMaterial, SignedKeyMaterial


# ---------------------------------------------------------------------------
# Curve25519 helpers
# ---------------------------------------------------------------------------

def generate_key_pair() -> KeyMaterial:
    """Generate a Curve25519 key pair and strip the leading version byte
    from the public key (Baileys stores 32-byte raw pub keys).
    """
    priv = x25519.X25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return KeyMaterial(private=priv_bytes, public=pub_bytes)


def curve_shared_key(private_key: bytes, public_key: bytes) -> bytes:
    """ECDH shared secret on Curve25519."""
    priv = x25519.X25519PrivateKey.from_private_bytes(private_key)
    pub = x25519.X25519PublicKey.from_public_bytes(public_key)
    return priv.exchange(pub)


def generate_signal_pub_key(pub_key: bytes) -> bytes:
    """Prepend the KEY_BUNDLE_TYPE byte (0x05) when missing — WhatsApp
    requires the 33-byte form for some curve operations.
    """
    if len(pub_key) == 33:
        return bytes(pub_key)
    return KEY_BUNDLE_TYPE + bytes(pub_key)


def curve_sign(private_key: bytes, data: bytes) -> bytes:
    """Sign using Ed25519 with the given private key.

    WhatsApp's identity keys are Ed25519; this is a faithful Python
    counterpart of Baileys' ``Curve.sign`` (which uses libsignal).
    """
    sk = Ed25519PrivateKey.from_private_bytes(private_key)
    return sk.sign(data)


def curve_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an Ed25519 signature. Returns ``False`` if invalid."""
    try:
        pk = Ed25519PublicKey.from_public_bytes(public_key)
        pk.verify(signature, message)
        return True
    except Exception:
        return False


def signed_key_pair(identity_private_key: bytes, key_id: int) -> SignedKeyMaterial:
    """Build a signed pre-key from the identity key pair."""
    pre = generate_key_pair()
    pub_with_prefix = generate_signal_pub_key(pre.public)
    sig = curve_sign(identity_private_key, pub_with_prefix)
    return SignedKeyMaterial(key_pair=pre, signature=sig, key_id=key_id)


def generate_registration_id() -> int:
    """Random 14-bit registration id (matching libsignal's behaviour)."""
    return int.from_bytes(os.urandom(2), "big") & 0x3FFF


# ---------------------------------------------------------------------------
# HKDF
# ---------------------------------------------------------------------------

def hkdf(secret: bytes, length: int, salt: bytes = b"", info: bytes = b"") -> bytes:
    """HKDF-SHA256.

    Mirrors ``whatsapp-rust-bridge::hkdf``.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt if salt else None,
        info=info,
    )
    return hkdf.derive(secret)


# ---------------------------------------------------------------------------
# AES helpers — same conventions as Baileys (GCM tag suffixed to ciphertext)
# ---------------------------------------------------------------------------

_GCM_TAG_LENGTH = 16  # 128 bits


def aes_encrypt_gcm(plaintext: bytes, key: bytes, iv: bytes,
                    additional_data: bytes = b"") -> bytes:
    """AES-256-GCM. The auth tag is suffixed to the ciphertext."""
    aead = AESGCM(key)
    ct_and_tag = aead.encrypt(iv, plaintext, additional_data)
    return ct_and_tag  # AESGCM already appends the tag


def aes_decrypt_gcm(ciphertext: bytes, key: bytes, iv: bytes,
                    additional_data: bytes = b"") -> bytes:
    """AES-256-GCM with the auth tag suffixed to the ciphertext."""
    aead = AESGCM(key)
    return aead.decrypt(iv, ciphertext, additional_data)


def aes_encrypt_ctr(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
    enc = cipher.encryptor()
    return enc.update(plaintext) + enc.finalize()


def aes_decrypt_ctr(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
    dec = cipher.decryptor()
    return dec.update(ciphertext) + dec.finalize()


def aes_encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-CBC with a random 16-byte IV prefixed to the ciphertext."""
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len]) * pad_len
    enc = cipher.encryptor()
    return iv + enc.update(padded) + enc.finalize()


def aes_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    """AES-256-CBC. Expects the 16-byte IV prefixed to the ciphertext."""
    iv, ct = ciphertext[:16], ciphertext[16:]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    padded = dec.update(ct) + dec.finalize()
    pad_len = padded[-1]
    return padded[:-pad_len]


# ---------------------------------------------------------------------------
# HMAC / hashing
# ---------------------------------------------------------------------------

def hmac_sign(key: bytes, data: bytes) -> bytes:
    return _hmac.new(key, data, hashlib.sha256).digest()


def hmac_verify(key: bytes, data: bytes, signature: bytes) -> bool:
    expected = hmac_sign(key, data)
    return hmac.compare_digest(expected, signature)


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def md5(data: bytes) -> bytes:
    return hashlib.md5(data).digest()


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def random_bytes(n: int) -> bytes:
    return os.urandom(n)


def encode_big_endian(n: int, length: int) -> bytes:
    return n.to_bytes(length, "big")


def decode_big_endian(data: bytes) -> int:
    return int.from_bytes(data, "big")


__all__ = [
    "generate_key_pair",
    "curve_shared_key",
    "generate_signal_pub_key",
    "curve_sign",
    "curve_verify",
    "signed_key_pair",
    "generate_registration_id",
    "hkdf",
    "aes_encrypt_gcm",
    "aes_decrypt_gcm",
    "aes_encrypt_ctr",
    "aes_decrypt_ctr",
    "aes_encrypt",
    "aes_decrypt",
    "hmac_sign",
    "hmac_verify",
    "sha256",
    "md5",
    "random_bytes",
    "encode_big_endian",
    "decode_big_endian",
]
