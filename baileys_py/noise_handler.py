"""Noise XX handshake + transport — Python port of
``src/Utils/noise-handler.ts``.

WhatsApp Web uses the Noise XX pattern (``Noise_XX_25519_AESGCM_SHA256``)
over WebSocket. We implement the symmetric-key encryption / decryption
state machine, frame framing (3-byte length prefix + intro header), and
the certificate-verification stub.

The certificate protobuf decoding in upstream uses
``proto.CertChain.decode``. Since we do not ship the WhatsApp protobuf
schema in this package, certificate verification is left as a hook
(:meth:`NoiseHandler.verify_certificate`) which by default skips
verification (suitable for testing / experimentation).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional, Union

from .crypto import (
    aes_decrypt_gcm,
    aes_encrypt_gcm,
    curve_shared_key,
    hkdf,
    sha256,
)
from .defaults import NOISE_WA_HEADER, NOISE_MODE
from .types import KeyMaterial

IV_LENGTH = 12


def _generate_iv(counter: int) -> bytes:
    iv = bytearray(IV_LENGTH)
    struct.pack_into(">I", iv, 8, counter)
    return bytes(iv)


@dataclass
class _TransportState:
    enc_key: bytes
    dec_key: bytes
    read_counter: int = 0
    write_counter: int = 0

    def encrypt(self, plaintext: bytes) -> bytes:
        iv = _generate_iv(self.write_counter)
        self.write_counter += 1
        return aes_encrypt_gcm(plaintext, self.enc_key, iv, b"")

    def decrypt(self, ciphertext: bytes) -> bytes:
        iv = _generate_iv(self.read_counter)
        self.read_counter += 1
        return aes_decrypt_gcm(ciphertext, self.dec_key, iv, b"")


class NoiseHandler:
    """A faithful Python port of Baileys' Noise handler.

    Args:
        key_pair: the client's ephemeral noise key pair
        noise_header: the WA noise header (defaults to ``b"WA\\x05\\x03"``)
        routing_info: optional routing-info prefix for the intro header
        verify_certificate: optional callback ``(cert_bytes) -> bool``.
            When omitted, certificate verification is skipped.
    """

    def __init__(self, key_pair: KeyMaterial,
                 noise_header: bytes = NOISE_WA_HEADER,
                 routing_info: Optional[bytes] = None,
                 verify_certificate: Optional[Callable[[bytes], bool]] = None) -> None:
        self.private_key = key_pair.private
        self.public_key = key_pair.public
        self.noise_header = noise_header
        self.verify_certificate = verify_certificate

        data = bytes(NOISE_MODE)
        self.hash = data if len(data) == 32 else sha256(data)
        self.salt = self.hash
        self.enc_key = self.hash
        self.dec_key = self.hash
        self.counter = 0
        self.sent_intro = False

        self.in_bytes = bytearray()
        self.transport: Optional[_TransportState] = None
        self.is_waiting_for_transport = False

        if routing_info:
            self.intro_header = (
                b"ED" + bytes([0, 1]) +
                (len(routing_info) >> 16).to_bytes(1, "big") +
                (len(routing_info) & 0xFFFF).to_bytes(2, "big") +
                routing_info +
                noise_header
            )
        else:
            self.intro_header = bytes(noise_header)

        # Authenticate the initial header + our pub key (mirrors upstream)
        self.authenticate(self.noise_header)
        self.authenticate(self.public_key)

    # ------------------------------------------------------------------
    # Core ops
    # ------------------------------------------------------------------
    def authenticate(self, data: bytes) -> None:
        if self.transport is None:
            self.hash = sha256(self.hash + data)

    def encrypt(self, plaintext: bytes) -> bytes:
        if self.transport:
            return self.transport.encrypt(plaintext)
        iv = _generate_iv(self.counter)
        out = aes_encrypt_gcm(plaintext, self.enc_key, iv, self.hash)
        self.counter += 1
        self.authenticate(out)
        return out

    def decrypt(self, ciphertext: bytes) -> bytes:
        if self.transport:
            return self.transport.decrypt(ciphertext)
        iv = _generate_iv(self.counter)
        out = aes_decrypt_gcm(ciphertext, self.dec_key, iv, self.hash)
        self.counter += 1
        self.authenticate(ciphertext)
        return out

    def _local_hkdf(self, data: bytes) -> tuple:
        key = hkdf(data, 64, salt=self.salt, info=b"")
        return key[:32], key[32:]

    def mix_into_key(self, data: bytes) -> None:
        write, read = self._local_hkdf(data)
        self.salt = write
        self.enc_key = read
        self.dec_key = read
        self.counter = 0

    def finish_init(self) -> None:
        """Transition to Transport state."""
        self.is_waiting_for_transport = True
        write, read = self._local_hkdf(b"")
        self.transport = _TransportState(enc_key=write, dec_key=read)
        self.is_waiting_for_transport = False

    # ------------------------------------------------------------------
    # Handshake step (server hello processing)
    # ------------------------------------------------------------------
    def process_handshake(self, server_hello_ephemeral: bytes,
                          server_hello_static: bytes,
                          server_hello_payload: bytes,
                          noise_key: KeyMaterial) -> bytes:
        """Process the server-hello portion of the Noise XX handshake.

        Returns the encrypted client public noise key to send back.

        ``server_hello_payload`` is the server's certificate chain; if
        :attr:`verify_certificate` is set, the cert is passed to it for
        verification (the callback should return ``True`` to accept).
        """
        self.authenticate(server_hello_ephemeral)
        self.mix_into_key(curve_shared_key(self.private_key, server_hello_ephemeral))

        dec_static = self.decrypt(server_hello_static)
        self.mix_into_key(curve_shared_key(self.private_key, dec_static))

        cert_decoded = self.decrypt(server_hello_payload)
        if self.verify_certificate is not None:
            if not self.verify_certificate(cert_decoded):
                raise RuntimeError("noise certificate verification failed")

        key_enc = self.encrypt(noise_key.public)
        self.mix_into_key(curve_shared_key(noise_key.private, server_hello_ephemeral))
        return key_enc

    # ------------------------------------------------------------------
    # Frame encoding / decoding
    # ------------------------------------------------------------------
    def encode_frame(self, data: bytes) -> bytes:
        """Frame ``data`` for sending over the WebSocket.

        Prepends the intro header on the first frame, then a 3-byte
        big-endian length prefix.
        """
        if self.transport:
            data = self.transport.encrypt(data)
        intro_size = 0 if self.sent_intro else len(self.intro_header)
        frame = bytearray(intro_size + 3 + len(data))
        if not self.sent_intro:
            frame[:len(self.intro_header)] = self.intro_header
            self.sent_intro = True
        n = len(data)
        frame[intro_size] = (n >> 16) & 0xFF
        frame[intro_size + 1] = (n >> 8) & 0xFF
        frame[intro_size + 2] = n & 0xFF
        frame[intro_size + 3:] = data
        return bytes(frame)

    def decode_frame(self, new_data: bytes) -> List[bytes]:
        """Append ``new_data`` to the internal buffer and return a list
        of fully-received frames (decrypted when in transport mode).
        """
        if self.is_waiting_for_transport:
            self.in_bytes.extend(new_data)
            return []
        self.in_bytes.extend(new_data)

        frames: List[bytes] = []
        while True:
            if len(self.in_bytes) < 3:
                return frames
            size = (self.in_bytes[0] << 16) | (self.in_bytes[1] << 8) | self.in_bytes[2]
            if len(self.in_bytes) < size + 3:
                return frames
            frame = bytes(self.in_bytes[3:3 + size])
            del self.in_bytes[:3 + size]
            if self.transport is not None:
                frame = self.transport.decrypt(frame)
            frames.append(frame)
        return frames


__all__ = ["NoiseHandler"]
