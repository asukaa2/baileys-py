"""Decode WhatsApp's binary wire format into :class:`BinaryNode`.

Port of ``src/WABinary/decode.ts``.
"""
from __future__ import annotations

import zlib
from typing import Optional, Union

from . import constants
from .jid import WAJIDDomains, jid_encode
from .node import BinaryNode


class _Decoder:
    def __init__(self, buffer: bytes, index: int = 0) -> None:
        self.buf = buffer
        self.index = index

    def check_eos(self, length: int) -> None:
        if self.index + length > len(self.buf):
            raise EOFError("end of stream")

    def next_byte(self) -> int:
        v = self.buf[self.index]
        self.index += 1
        return v

    def read_byte(self) -> int:
        self.check_eos(1)
        return self.next_byte()

    def read_bytes(self, n: int) -> bytes:
        self.check_eos(n)
        v = self.buf[self.index:self.index + n]
        self.index += n
        return v

    def read_string_from_chars(self, length: int) -> str:
        return self.read_bytes(length).decode("utf-8", errors="replace")

    def read_int(self, n: int, little_endian: bool = False) -> int:
        self.check_eos(n)
        val = 0
        for i in range(n):
            shift = i if little_endian else (n - 1 - i)
            val |= self.next_byte() << (shift * 8)
        return val

    def read_int20(self) -> int:
        self.check_eos(3)
        return ((self.next_byte() & 0x0F) << 16) + \
               (self.next_byte() << 8) + \
                self.next_byte()

    def unpack_hex(self, value: int) -> int:
        if 0 <= value < 16:
            return ord("0") + value if value < 10 else ord("A") + value - 10
        raise ValueError(f"invalid hex: {value}")

    def unpack_nibble(self, value: int) -> int:
        if 0 <= value <= 9:
            return ord("0") + value
        if value == 10:
            return ord("-")
        if value == 11:
            return ord(".")
        if value == 15:
            return 0
        raise ValueError(f"invalid nibble: {value}")

    def unpack_byte(self, tag: int, value: int) -> int:
        if tag == constants.TAGS["NIBBLE_8"]:
            return self.unpack_nibble(value)
        if tag == constants.TAGS["HEX_8"]:
            return self.unpack_hex(value)
        raise ValueError(f"unknown tag: {tag}")

    def read_packed8(self, tag: int) -> str:
        start_byte = self.read_byte()
        value = ""
        for _ in range(start_byte & 127):
            cur_byte = self.read_byte()
            value += chr(self.unpack_byte(tag, (cur_byte & 0xF0) >> 4))
            value += chr(self.unpack_byte(tag, cur_byte & 0x0F))
        if (start_byte >> 7) != 0:
            value = value[:-1]
        return value

    def is_list_tag(self, tag: int) -> bool:
        return tag in (
            constants.TAGS["LIST_EMPTY"],
            constants.TAGS["LIST_8"],
            constants.TAGS["LIST_16"],
        )

    def read_list_size(self, tag: int) -> int:
        if tag == constants.TAGS["LIST_EMPTY"]:
            return 0
        if tag == constants.TAGS["LIST_8"]:
            return self.read_byte()
        if tag == constants.TAGS["LIST_16"]:
            return self.read_int(2)
        raise ValueError(f"invalid tag for list size: {tag}")

    def read_jid_pair(self) -> str:
        i = self.read_string(self.read_byte())
        j = self.read_string(self.read_byte())
        if j:
            return f"{i or ''}@{j}"
        raise ValueError(f"invalid jid pair: {i}, {j}")

    def read_ad_jid(self) -> str:
        domain_type = self.read_byte()
        device = self.read_byte()
        user = self.read_string(self.read_byte())
        if domain_type == WAJIDDomains.LID.value:
            server = "lid"
        elif domain_type == WAJIDDomains.HOSTED.value:
            server = "hosted"
        elif domain_type == WAJIDDomains.HOSTED_LID.value:
            server = "hosted.lid"
        else:
            server = "s.whatsapp.net"
        return jid_encode(user, server, device)

    def read_fb_jid(self) -> str:
        user = self.read_string(self.read_byte())
        device = self.read_int(2)
        server = self.read_string(self.read_byte())
        return f"{user}:{device}@{server}"

    def read_interop_jid(self) -> str:
        user = self.read_string(self.read_byte())
        device = self.read_int(2)
        integrator = self.read_int(2)
        before = self.index
        try:
            server = self.read_string(self.read_byte())
        except EOFError:
            self.index = before
            server = "interop"
        return f"{integrator}-{user}:{device}@{server}"

    def read_string(self, tag: int) -> str:
        if 1 <= tag < len(constants.SINGLE_BYTE_TOKENS):
            return constants.SINGLE_BYTE_TOKENS[tag] or ""
        if tag == constants.TAGS["DICTIONARY_0"] or \
           tag == constants.TAGS["DICTIONARY_1"] or \
           tag == constants.TAGS["DICTIONARY_2"] or \
           tag == constants.TAGS["DICTIONARY_3"]:
            return self.get_token_double(tag - constants.TAGS["DICTIONARY_0"],
                                          self.read_byte())
        if tag == constants.TAGS["LIST_EMPTY"]:
            return ""
        if tag == constants.TAGS["BINARY_8"]:
            return self.read_string_from_chars(self.read_byte())
        if tag == constants.TAGS["BINARY_20"]:
            return self.read_string_from_chars(self.read_int20())
        if tag == constants.TAGS["BINARY_32"]:
            return self.read_string_from_chars(self.read_int(4))
        if tag == constants.TAGS["JID_PAIR"]:
            return self.read_jid_pair()
        if tag == constants.TAGS["FB_JID"]:
            return self.read_fb_jid()
        if tag == constants.TAGS["INTEROP_JID"]:
            return self.read_interop_jid()
        if tag == constants.TAGS["AD_JID"]:
            return self.read_ad_jid()
        if tag in (constants.TAGS["HEX_8"], constants.TAGS["NIBBLE_8"]):
            return self.read_packed8(tag)
        raise ValueError(f"invalid string with tag: {tag}")

    def read_list(self, tag: int) -> list:
        size = self.read_list_size(tag)
        items = []
        for _ in range(size):
            items.append(self.decode_node())
        return items

    def get_token_double(self, i1: int, i2: int) -> str:
        if i1 >= len(constants.DOUBLE_BYTE_TOKENS):
            raise ValueError(f"invalid double token dict ({i1})")
        d = constants.DOUBLE_BYTE_TOKENS[i1]
        if i2 >= len(d):
            raise ValueError(f"invalid double token ({i2})")
        return d[i2]

    def decode_node(self) -> BinaryNode:
        list_size = self.read_list_size(self.read_byte())
        header = self.read_string(self.read_byte())
        if not list_size or not header:
            raise ValueError("invalid node")
        attrs = {}
        attr_count = (list_size - 1) >> 1
        for _ in range(attr_count):
            k = self.read_string(self.read_byte())
            v = self.read_string(self.read_byte())
            attrs[k] = v
        data: Optional[Union[str, bytes, list]] = None
        if list_size % 2 == 0:
            tag = self.read_byte()
            if self.is_list_tag(tag):
                data = self.read_list(tag)
            elif tag == constants.TAGS["BINARY_8"]:
                data = self.read_bytes(self.read_byte())
            elif tag == constants.TAGS["BINARY_20"]:
                data = self.read_bytes(self.read_int20())
            elif tag == constants.TAGS["BINARY_32"]:
                data = self.read_bytes(self.read_int(4))
            else:
                data = self.read_string(tag)
        return BinaryNode(tag=header, attrs=attrs, content=data)


def decompress_if_required(buf: bytes) -> bytes:
    """Strip the leading compression flag and inflate if needed."""
    if not buf:
        return buf
    flag = buf[0]
    if flag & 2:
        return zlib.decompress(buf[1:])
    return buf[1:]


def decode_decompressed_binary_node(buffer: bytes, index: int = 0) -> BinaryNode:
    """Decode an already-decompressed buffer into a BinaryNode."""
    return _Decoder(buffer, index).decode_node()


def decode_binary_node(buf: bytes) -> BinaryNode:
    """Decode a raw WA message buffer (with compression flag) into a BinaryNode."""
    decomp = decompress_if_required(buf)
    return decode_decompressed_binary_node(decomp)


__all__ = [
    "decode_binary_node",
    "decode_decompressed_binary_node",
    "decompress_if_required",
]
