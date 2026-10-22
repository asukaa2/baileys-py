"""Encode :class:`BinaryNode` into WhatsApp's binary wire format.

Port of ``src/WABinary/encode.ts``.
"""
from __future__ import annotations

from typing import List, Union

from . import constants
from .jid import jid_decode
from .node import BinaryNode


def _pack_nibble(c: str) -> int:
    if c == "-":
        return 10
    if c == ".":
        return 11
    if c == "\0":
        return 15
    if "0" <= c <= "9":
        return ord(c) - ord("0")
    raise ValueError(f"invalid byte for nibble: {c!r}")


def _pack_hex(c: str) -> int:
    if "0" <= c <= "9":
        return ord(c) - ord("0")
    if "A" <= c <= "F":
        return 10 + ord(c) - ord("A")
    if "a" <= c <= "f":
        return 10 + ord(c) - ord("a")
    if c == "\0":
        return 15
    raise ValueError(f"invalid hex char: {c!r}")


def _is_nibble(s: str) -> bool:
    if not s or len(s) > constants.TAGS["PACKED_MAX"]:
        return False
    return all(("0" <= c <= "9") or c in "-." for c in s)


def _is_hex(s: str) -> bool:
    if not s or len(s) > constants.TAGS["PACKED_MAX"]:
        return False
    return all(("0" <= c <= "9") or ("A" <= c <= "F") for c in s)


class _Encoder:
    def __init__(self) -> None:
        self.buf: bytearray = bytearray([0])  # first byte is reserved for compression flag

    def push_byte(self, v: int) -> None:
        self.buf.append(v & 0xFF)

    def push_bytes(self, data: Union[bytes, bytearray, List[int]]) -> None:
        self.buf.extend(data)

    def push_int(self, value: int, n: int, little_endian: bool = False) -> None:
        for i in range(n):
            shift = i if little_endian else (n - 1 - i)
            self.buf.append((value >> (shift * 8)) & 0xFF)

    def push_int16(self, value: int) -> None:
        self.push_bytes([(value >> 8) & 0xFF, value & 0xFF])

    def push_int20(self, value: int) -> None:
        self.push_bytes([(value >> 16) & 0x0F, (value >> 8) & 0xFF, value & 0xFF])

    def write_byte_length(self, length: int) -> None:
        if length >= (1 << 32):
            raise ValueError(f"string too large to encode: {length}")
        if length >= (1 << 20):
            self.push_byte(constants.TAGS["BINARY_32"])
            self.push_int(length, 4)
        elif length >= 256:
            self.push_byte(constants.TAGS["BINARY_20"])
            self.push_int20(length)
        else:
            self.push_byte(constants.TAGS["BINARY_8"])
            self.push_byte(length)

    def write_string_raw(self, s: str) -> None:
        b = s.encode("utf-8")
        self.write_byte_length(len(b))
        self.push_bytes(b)

    def write_jid(self, jid) -> None:
        if jid.device is not None:
            self.push_byte(constants.TAGS["AD_JID"])
            self.push_byte(jid.domain_type or 0)
            self.push_byte(jid.device or 0)
            self.write_string(jid.user)
        else:
            self.push_byte(constants.TAGS["JID_PAIR"])
            if jid.user:
                self.write_string(jid.user)
            else:
                self.push_byte(constants.TAGS["LIST_EMPTY"])
            self.write_string(jid.server)

    def write_packed_bytes(self, s: str, type_: str) -> None:
        if len(s) > constants.TAGS["PACKED_MAX"]:
            raise ValueError("too many bytes to pack")
        self.push_byte(constants.TAGS["NIBBLE_8"] if type_ == "nibble"
                       else constants.TAGS["HEX_8"])
        rounded = (len(s) + 1) // 2
        if len(s) % 2 != 0:
            rounded |= 128
        self.push_byte(rounded)
        pack = _pack_nibble if type_ == "nibble" else _pack_hex
        half = len(s) // 2
        for i in range(half):
            self.push_byte((pack(s[2 * i]) << 4) | pack(s[2 * i + 1]))
        if len(s) % 2 != 0:
            self.push_byte((pack(s[-1]) << 4) | pack("\0"))

    def write_string(self, s) -> None:
        if s is None:
            self.push_byte(constants.TAGS["LIST_EMPTY"])
            return
        if not isinstance(s, str):
            raise TypeError(f"expected str, got {type(s).__name__}")
        if s == "":
            self.write_string_raw(s)
            return

        tok = constants.TOKEN_MAP.get(s)
        if tok is not None:
            if "dict" in tok:
                self.push_byte(constants.TAGS["DICTIONARY_0"] + tok["dict"])
            self.push_byte(tok["index"])
        elif _is_nibble(s):
            self.write_packed_bytes(s, "nibble")
        elif _is_hex(s):
            self.write_packed_bytes(s, "hex")
        else:
            decoded = jid_decode(s)
            if decoded is not None:
                self.write_jid(decoded)
            else:
                self.write_string_raw(s)

    def write_list_start(self, size: int) -> None:
        if size == 0:
            self.push_byte(constants.TAGS["LIST_EMPTY"])
        elif size < 256:
            self.push_bytes([constants.TAGS["LIST_8"], size])
        else:
            self.push_byte(constants.TAGS["LIST_16"])
            self.push_int16(size)

    def encode(self, node: BinaryNode) -> None:
        if not node.tag:
            raise ValueError("Invalid node: tag cannot be empty")
        valid_attrs = {k: v for k, v in node.attrs.items()
                       if v is not None and not isinstance(v, (list, dict))}
        content_present = node.content is not None
        # Header is 1 (tag) + 2*attr_count + (1 if content else 0)
        list_size = 2 * len(valid_attrs) + 1 + (1 if content_present else 0)
        self.write_list_start(list_size)
        self.write_string(node.tag)
        for k, v in valid_attrs.items():
            self.write_string(k)
            self.write_string(str(v))
        content = node.content
        if content is None:
            return
        if isinstance(content, str):
            self.write_string(content)
        elif isinstance(content, (bytes, bytearray)):
            self.write_byte_length(len(content))
            self.push_bytes(content)
        elif isinstance(content, list):
            valid = [c for c in content
                     if c is not None and (isinstance(c, BinaryNode) or
                         isinstance(c, (bytes, bytearray, str)))]
            self.write_list_start(len(valid))
            for item in valid:
                if isinstance(item, BinaryNode):
                    self.encode(item)
                elif isinstance(item, (bytes, bytearray)):
                    self.write_byte_length(len(item))
                    self.push_bytes(item)
                elif isinstance(item, str):
                    self.write_string(item)
        else:
            raise TypeError(f"invalid children for header {node.tag!r}: {type(content)}")


def encode_binary_node(node: BinaryNode) -> bytes:
    """Encode a BinaryNode tree into WhatsApp's binary wire format."""
    enc = _Encoder()
    enc.encode(node)
    return bytes(enc.buf)


__all__ = ["encode_binary_node"]
