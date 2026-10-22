"""BinaryNode type and helpers — a Python port of ``src/WABinary``."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

BinaryNodeContent = Union[List["BinaryNode"], str, bytes, None]


@dataclass
class BinaryNode:
    """A node in WhatsApp's binary protocol.

    ``content`` is either a list of child nodes, a string (e.g. text), a
    raw ``bytes`` payload, or ``None``.
    """
    tag: str
    attrs: Dict[str, str] = field(default_factory=dict)
    content: BinaryNodeContent = None


# ---------------------------------------------------------------------------
# Generic traversal helpers (mirror src/WABinary/generic-utils.ts)
# ---------------------------------------------------------------------------

def get_binary_node_children(node: Optional[BinaryNode], child_tag: str) -> List[BinaryNode]:
    if not node or not isinstance(node.content, list):
        return []
    return [c for c in node.content if isinstance(c, BinaryNode) and c.tag == child_tag]


def get_binary_node_child(node: Optional[BinaryNode], child_tag: str) -> Optional[BinaryNode]:
    children = get_binary_node_children(node, child_tag)
    return children[0] if children else None


def get_all_binary_node_children(node: BinaryNode) -> List[BinaryNode]:
    if isinstance(node.content, list):
        return [c for c in node.content if isinstance(c, BinaryNode)]
    return []


def get_binary_node_child_buffer(node: Optional[BinaryNode], child_tag: str) -> Optional[bytes]:
    child = get_binary_node_child(node, child_tag)
    if child and isinstance(child.content, (bytes, bytearray)):
        return bytes(child.content)
    return None


def get_binary_node_child_string(node: Optional[BinaryNode], child_tag: str) -> Optional[str]:
    child = get_binary_node_child(node, child_tag)
    if not child:
        return None
    if isinstance(child.content, (bytes, bytearray)):
        return bytes(child.content).decode("utf-8", errors="replace")
    if isinstance(child.content, str):
        return child.content
    return None


def get_binary_node_child_uint(node: BinaryNode, child_tag: str, length: int) -> Optional[int]:
    buff = get_binary_node_child_buffer(node, child_tag)
    if not buff:
        return None
    n = 0
    for i in range(min(length, len(buff))):
        n = 256 * n + buff[i]
    return n


def assert_node_error_free(node: BinaryNode) -> None:
    err = get_binary_node_child(node, "error")
    if err:
        raise RuntimeError(
            err.attrs.get("text", "Unknown error"),
            int(err.attrs.get("code", 0)),
        )


def reduce_binary_node_to_dictionary(node: BinaryNode, tag: str) -> Dict[str, str]:
    nodes = get_binary_node_children(node, tag)
    out: Dict[str, str] = {}
    for n in nodes:
        name = n.attrs.get("name")
        value = n.attrs.get("value") or n.attrs.get("config_value")
        if name is not None:
            out[name] = value or ""
        else:
            code = n.attrs.get("config_code", "")
            out[code] = value or ""
    return out


def binary_node_to_string(node, indent: int = 0) -> str:
    tabs = "\t" * indent
    if node is None:
        return "None"
    if isinstance(node, str):
        return tabs + node
    if isinstance(node, (bytes, bytearray)):
        return tabs + bytes(node).hex()
    if isinstance(node, list):
        return "\n".join("\t" * (indent + 1) + binary_node_to_string(x, indent + 1) for x in node)
    children = binary_node_to_string(node.content, indent + 1) if isinstance(node, BinaryNode) else ""
    attrs = " ".join(
        f"{k}='{v}'" for k, v in (node.attrs or {}).items() if v is not None
    )
    head = f"<{node.tag} {attrs}".rstrip()
    if children:
        return f"{head}>\n{children}\n{tabs}</{node.tag}>"
    return f"{head}/>"


__all__ = [
    "BinaryNode", "BinaryNodeContent",
    "get_binary_node_children", "get_binary_node_child",
    "get_all_binary_node_children", "get_binary_node_child_buffer",
    "get_binary_node_child_string", "get_binary_node_child_uint",
    "assert_node_error_free", "reduce_binary_node_to_dictionary",
    "binary_node_to_string",
]
