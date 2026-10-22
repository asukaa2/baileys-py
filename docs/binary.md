# Binary protocol

WhatsApp's WebSocket uses a compact binary encoding for all stanzas
(`<message>`, `<iq>`, `<presence>`, `<receipt>`, etc.). The encoding is
a tagged TLV-style format with three key optimisations:

1. **Token dictionaries** — common strings like `iq`, `type`, `from`,
   `participant` are mapped to single bytes (236 in the single-byte
   table) or two bytes (1,024 in the double-byte table).
2. **Packed nibbles / hex** — short numeric strings (phone numbers,
   timestamps) are packed two-per-byte with a 1-byte header.
3. **JID encoding** — JIDs are split into user / device / server and
   stored compactly.

baileys-py ports this in full, including all 1,300+ lines of token
dictionaries auto-generated from upstream Baileys.

## BinaryNode

Every WA stanza is represented as a `BinaryNode`:

```python
from baileys_py import BinaryNode

node = BinaryNode(
    tag="iq",
    attrs={"type": "get", "id": "abc123"},
    content=[
        BinaryNode(tag="query", attrs={"xmlns": "jabber:iq:roster"}),
    ],
)
```

`content` can be:

* `None` — leaf node
* `str` — text content
* `bytes` — raw binary blob (e.g. an encrypted message payload)
* `List[BinaryNode]` — child nodes

## Encoding / decoding

```python
from baileys_py import encode_binary_node, decode_binary_node

wire_bytes = encode_binary_node(node)
# -> bytes(b'\x00\xF8\x06...')

decoded = decode_binary_node(wire_bytes)
# -> BinaryNode(tag='iq', attrs={'type': 'get', 'id': 'abc123'}, content=[...])
```

The encoding always starts with a 1-byte compression flag (`0x00` for
uncompressed, `0x02` for zlib-compressed). baileys-py always emits
`0x00` (no compression); the decoder handles both.

## Pretty-printing

```python
from baileys_py import binary_node_to_string

print(binary_node_to_string(node))
# <iq type='get' id='abc123'>
#     <query xmlns='jabber:iq:roster'/>
# </iq>
```

Useful for debugging — see the actual stanza that's about to be sent.

## Traversal helpers

These mirror upstream Baileys' `generic-utils.ts`:

```python
from baileys_py import (
    get_binary_node_child,
    get_binary_node_children,
    get_all_binary_node_children,
    get_binary_node_child_buffer,
    get_binary_node_child_string,
    get_binary_node_child_uint,
    assert_node_error_free,
    reduce_binary_node_to_dictionary,
)

# Get first child by tag
query = get_binary_node_child(iq_node, "query")

# Get all children by tag
items = get_binary_node_children(node, "item")

# Get a child's content as bytes (for binary payloads)
encrypted = get_binary_node_child_buffer(node, "enc")

# Get a child's content as string
text = get_binary_node_child_string(node, "body")

# Get a child's content as a uint of N bytes
ts = get_binary_node_child_uint(node, "t", 4)

# Throw if the node has an <error> child
assert_node_error_free(iq_result)

# Build a dict from a list of <item name="..." value="..."/> children
config = reduce_binary_node_to_dictionary(node, "item")
```

## Working with raw frames

`WASocket.send_raw_frame(node)` encodes the node, frames it (with the
Noise transport if handshook is done), and writes to the WebSocket. For
query/response patterns, `WASocket.query(node)` sends an `<iq>` and
awaits the matching response by id:

```python
node = BinaryNode(
    tag="iq",
    attrs={"to": "62XXX@s.whatsapp.net", "type": "get", "xmlns": "w:profile:picture"},
    content=[BinaryNode(tag="picture", attrs={"type": "image"})],
)
response = await sock.query(node)
pic = get_binary_node_child(response, "picture")
url = pic.attrs.get("url") if pic else None
```

## Token dictionaries

The 1,300-line `baileys_py/binary/constants.py` is auto-generated from
upstream Baileys' `src/WABinary/constants.ts`:

* `TAGS` — well-known bytes (LIST_EMPTY, BINARY_8, BINARY_20, BINARY_32,
  JID_PAIR, AD_JID, NIBBLE_8, HEX_8, DICTIONARY_0..3)
* `SINGLE_BYTE_TOKENS` — 236 single-byte tokens
* `DOUBLE_BYTE_TOKENS` — 4×256 double-byte tokens
* `TOKEN_MAP` — precomputed lookup `str -> {dict?, index}`

If you bump the upstream Baileys version, re-generate the constants
file:

```bash
python scripts/build_constants.py
```

(The script expects the upstream Baileys repo to be cloned at
`/home/z/my-project/Baileys/`. Edit the `SRC` path at the top of the
script to point elsewhere.)

## Round-trip test

```python
from baileys_py import BinaryNode, encode_binary_node, decode_binary_node

node = BinaryNode(
    tag="iq",
    attrs={"type": "get", "id": "abc123"},
    content=[
        BinaryNode(tag="query", attrs={"xmlns": "jabber:iq:roster"}),
        BinaryNode(tag="query", attrs={"xmlns": "jabber:iq:last"}),
    ],
)

# Encode -> bytes -> decode -> node
assert decode_binary_node(encode_binary_node(node)).tag == "iq"
```

This round-trip is one of the 13 tests in `tests/test_smoke.py`.
