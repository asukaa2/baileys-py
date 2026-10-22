"""High-level message helpers that mirror ``src/Socket/messages-recv.ts``,
``src/Socket/groups.ts`` and ``src/Socket/chats.ts`` from Baileys.

These helpers wrap :class:`baileys_py.socket.WASocket` so the public
API stays simple. Each one issues an ``<iq>`` query and returns the
result, parsed into a Python-friendly dict / dataclass.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .binary import (
    BinaryNode,
    get_binary_node_child,
    get_binary_node_children,
    jid_encode,
)
from .socket import WASocket


# ---------------------------------------------------------------------------
# Group helpers
# ---------------------------------------------------------------------------

async def group_create(sock: WASocket, subject: str,
                       participants: Optional[List[str]] = None) -> Dict[str, Any]:
    """Create a new group chat."""
    participants = participants or []
    inner = [BinaryNode(tag="user", attrs={"jid": p}) for p in participants]
    node = BinaryNode(
        tag="iq",
        attrs={"to": "@g.us", "type": "set", "xmlns": "w:g2"},
        content=[BinaryNode(tag="create", attrs={"subject": subject}, content=inner)],
    )
    resp = await sock.query(node)
    return {"raw": resp, "subject": subject, "participants": participants}


async def group_invite_code(sock: WASocket, group_jid: str) -> Optional[str]:
    """Fetch the invite code for an existing group."""
    node = BinaryNode(
        tag="iq",
        attrs={"to": group_jid, "type": "get", "xmlns": "w:g2"},
        content=[BinaryNode(tag="invite")],
    )
    resp = await sock.query(node)
    invite = get_binary_node_child(resp, "invite")
    return invite.attrs.get("code") if invite else None


async def group_join(sock: WASocket, code: str) -> Any:
    """Join a group via invite code."""
    node = BinaryNode(
        tag="iq",
        attrs={"type": "set", "xmlns": "w:g2"},
        content=[BinaryNode(tag="invite", attrs={"code": code})],
    )
    return await sock.query(node)


async def group_leave(sock: WASocket, group_jid: str) -> Any:
    """Leave a group."""
    node = BinaryNode(
        tag="iq",
        attrs={"to": group_jid, "type": "set", "xmlns": "w:g2"},
        content=[BinaryNode(tag="leave")],
    )
    return await sock.query(node)


async def group_participants_update(sock: WASocket, group_jid: str,
                                     participants: List[str], action: str) -> Any:
    """Add/promote/demote/remove participants.

    ``action`` is one of ``add``, ``remove``, ``promote``, ``demote``.
    """
    inner = [BinaryNode(tag="user", attrs={"jid": p}) for p in participants]
    node = BinaryNode(
        tag="iq",
        attrs={"to": group_jid, "type": "set", "xmlns": "w:g2"},
        content=[BinaryNode(tag=action, content=inner)],
    )
    return await sock.query(node)


# ---------------------------------------------------------------------------
# Chat helpers
# ---------------------------------------------------------------------------

async def chat_send_message(sock: WASocket, jid: str,
                            content: Any) -> Any:
    """Alias for :meth:`WASocket.send_message`."""
    return await sock.send_message(jid, content)


async def chat_archive(sock: WASocket, jid: str, archive: bool = True) -> Any:
    """Archive / unarchive a chat."""
    action = "archive" if archive else "unarchive"
    node = BinaryNode(
        tag="iq",
        attrs={"to": jid, "type": "set", "xmlns": "w:chat"},
        content=[BinaryNode(tag=action)],
    )
    return await sock.query(node)


async def chat_pin(sock: WASocket, jid: str, pin: bool = True) -> Any:
    """Pin / unpin a chat."""
    action = "pin" if pin else "unpin"
    node = BinaryNode(
        tag="iq",
        attrs={"to": jid, "type": "set", "xmlns": "w:chat"},
        content=[BinaryNode(tag=action)],
    )
    return await sock.query(node)


async def chat_mark_read(sock: WASocket, jid: str,
                         message_keys: List[Any]) -> Any:
    """Mark messages as read in a chat."""
    receipts = [
        BinaryNode(tag="receipt",
                   attrs={"id": k.id if hasattr(k, "id") else k["id"],
                          "t": "1", "type": "read",
                          "participant": (k.participant if hasattr(k, "participant")
                                           else k.get("participant", ""))})
        for k in message_keys
    ]
    node = BinaryNode(tag="iq", attrs={"to": jid, "type": "set"},
                      content=receipts)
    return await sock.query(node)


# ---------------------------------------------------------------------------
# Presence / typing
# ---------------------------------------------------------------------------

async def send_presence_update(sock: WASocket, jid: str,
                                presence: str = "available") -> Any:
    """Update presence for a chat (``available``, ``composing``, ``paused``...)."""
    node = BinaryNode(
        tag="presence",
        attrs={"to": jid, "type": presence},
    )
    await sock.send_raw_frame(node)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

async def get_profile_picture_url(sock: WASocket, jid: str,
                                  high_res: bool = True) -> Optional[str]:
    """Fetch a profile-picture URL for ``jid``."""
    type_ = "image" if high_res else "preview"
    node = BinaryNode(
        tag="iq",
        attrs={"to": jid, "type": "get", "xmlns": "w:profile:picture"},
        content=[BinaryNode(tag="picture", attrs={"type": type_})],
    )
    resp = await sock.query(node)
    pic = get_binary_node_child(resp, "picture")
    return pic.attrs.get("url") if pic else None


async def update_profile_name(sock: WASocket, name: str) -> Any:
    """Update the connected account's profile name."""
    node = BinaryNode(
        tag="iq",
        attrs={"to": "@s.whatsapp.net", "type": "set", "xmlns": "w:profile"},
        content=[BinaryNode(tag="name", content=name)],
    )
    return await sock.query(node)


async def update_profile_status(sock: WASocket, status: str) -> Any:
    """Update the connected account's about text."""
    node = BinaryNode(
        tag="iq",
        attrs={"to": "@s.whatsapp.net", "type": "set", "xmlns": "w:profile"},
        content=[BinaryNode(tag="status", content=status)],
    )
    return await sock.query(node)


__all__ = [
    "group_create", "group_invite_code", "group_join", "group_leave",
    "group_participants_update",
    "chat_send_message", "chat_archive", "chat_pin", "chat_mark_read",
    "send_presence_update",
    "get_profile_picture_url", "update_profile_name", "update_profile_status",
]
