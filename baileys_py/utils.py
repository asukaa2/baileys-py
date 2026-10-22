"""General utility helpers — a Python port of ``src/Utils/generics.ts``
and friends.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from .binary import (
    is_jid_broadcast,
    is_jid_group,
    is_jid_newsletter,
    jid_decode,
    jid_encode,
    jid_normalized_user,
)


# ---------------------------------------------------------------------------
# ID / version helpers
# ---------------------------------------------------------------------------

def generate_message_id_v2(user_id: Optional[str] = None) -> str:
    """Generate a WA-style message id.

    Upstream uses ``3PBI...`` style ids derived from a base32 counter; we
    use a 20-char uppercase hex instead, which is suitable as a unique
    client-generated stanza id.
    """
    suffix = uuid.uuid4().hex[:16].upper()
    return f"3EB0{suffix}"


def generate_message_tag() -> str:
    """Generate a short unique request tag."""
    return uuid.uuid4().hex[:12].upper()


def unix_timestamp_seconds() -> int:
    return int(time.time())


async def fetch_latest_baileys_version() -> Dict[str, Any]:
    """Fetch the latest WA Web version.

    The upstream implementation hits
    ``https://web.whatsapp.com/check-update?version=...&platform=web``.
    For the Python port we default to the baked-in
    :data:`DEFAULT_VERSION` and return it.
    """
    from .defaults import DEFAULT_VERSION
    return {"version": DEFAULT_VERSION, "is_latest": True}


# ---------------------------------------------------------------------------
# Poll / message helpers
# ---------------------------------------------------------------------------

def get_aggregate_votes_in_poll_message(message: Dict[str, Any],
                                         poll_updates: Optional[List[Dict[str, Any]]] = None
                                         ) -> List[Dict[str, Any]]:
    """Aggregate poll votes from ``pollUpdates`` against a poll-creation
    message. Returns a list of ``{"name": str, "voters": int}`` items.
    """
    if not poll_updates:
        return []
    votes: Dict[str, int] = {}
    for update in poll_updates:
        vote = update.get("vote")
        if not vote:
            continue
        for name in vote.get("selectedOptions", []) or []:
            votes[name] = votes.get(name, 0) + 1
    return [{"name": k, "voters": v} for k, v in votes.items()]


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

async def promise_timeout(coro, timeout_ms: Optional[int] = None):
    """Await ``coro`` with a millisecond timeout."""
    if timeout_ms is None:
        return await coro
    return await asyncio.wait_for(coro, timeout=timeout_ms / 1000)


def delay_ms(ms: int):
    """Async sleep for ``ms`` milliseconds."""
    return asyncio.sleep(ms / 1000)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def is_jid_broadcast_(jid: str) -> bool:
    return is_jid_broadcast(jid)


def is_jid_group_(jid: str) -> bool:
    return is_jid_group(jid)


def is_jid_newsletter_(jid: str) -> bool:
    return is_jid_newsletter(jid)


def get_call_link(id_: str) -> str:
    """Construct a WhatsApp call link from a call id."""
    from .defaults import CALL_VIDEO_PREFIX
    return f"{CALL_VIDEO_PREFIX}{id_}"


__all__ = [
    "generate_message_id_v2",
    "generate_message_tag",
    "unix_timestamp_seconds",
    "fetch_latest_baileys_version",
    "get_aggregate_votes_in_poll_message",
    "promise_timeout",
    "delay_ms",
    "is_jid_broadcast_",
    "is_jid_group_",
    "is_jid_newsletter_",
    "get_call_link",
]
