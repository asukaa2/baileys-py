"""JID (Jabber ID) helpers — a Python port of ``src/WABinary/jid-utils.ts``."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

S_WHATSAPP_NET = "@s.whatsapp.net"
OFFICIAL_BIZ_JID = "16505361212@c.us"
SERVER_JID = "server@c.us"
PSA_WID = "0@c.us"
STORIES_JID = "status@broadcast"
META_AI_JID = "13135550002@c.us"


class WAJIDDomains(Enum):
    WHATSAPP = 0
    LID = 1
    HOSTED = 128
    HOSTED_LID = 129


@dataclass
class FullJid:
    user: str
    server: str
    device: Optional[int] = None
    domain_type: int = 0


def get_server_from_domain_type(initial_server: str,
                                domain_type: Optional[WAJIDDomains]) -> str:
    if domain_type == WAJIDDomains.LID:
        return "lid"
    if domain_type == WAJIDDomains.HOSTED:
        return "hosted"
    if domain_type == WAJIDDomains.HOSTED_LID:
        return "hosted.lid"
    return initial_server


def jid_encode(user, server: str, device: Optional[int] = None,
               agent: Optional[int] = None) -> str:
    """Encode a JID from its parts. Mirrors ``jidEncode``."""
    s = str(user or "")
    if agent:
        s += f"_{agent}"
    if device:
        s += f":{device}"
    return f"{s}@{server}"


def jid_decode(jid: Optional[str]) -> Optional[FullJid]:
    if not jid or "@" not in jid:
        return None
    sep_idx = jid.index("@")
    server = jid[sep_idx + 1:]
    user_combined = jid[:sep_idx]

    if ":" in user_combined:
        user_agent, device = user_combined.split(":", 1)
    else:
        user_agent, device = user_combined, None

    if "_" in user_agent:
        user, agent = user_agent.split("_", 1)
    else:
        user, agent = user_agent, None

    domain_type = WAJIDDomains.WHATSAPP.value
    if server == "lid":
        domain_type = WAJIDDomains.LID.value
    elif server == "hosted":
        domain_type = WAJIDDomains.HOSTED.value
    elif server == "hosted.lid":
        domain_type = WAJIDDomains.HOSTED_LID.value
    elif agent:
        try:
            domain_type = int(agent)
        except ValueError:
            pass

    return FullJid(
        user=user,
        server=server,
        device=int(device) if device is not None else None,
        domain_type=domain_type,
    )


def are_jids_same_user(jid1: Optional[str], jid2: Optional[str]) -> bool:
    a = jid_decode(jid1)
    b = jid_decode(jid2)
    return bool(a and b and a.user == b.user)


def is_jid_meta_ai(jid: Optional[str]) -> bool:
    return bool(jid and jid.endswith("@bot"))


def is_pn_user(jid: Optional[str]) -> bool:
    return bool(jid and jid.endswith("@s.whatsapp.net"))


def is_lid_user(jid: Optional[str]) -> bool:
    return bool(jid and jid.endswith("@lid"))


def is_jid_broadcast(jid: Optional[str]) -> bool:
    return bool(jid and jid.endswith("@broadcast"))


def is_jid_group(jid: Optional[str]) -> bool:
    return bool(jid and jid.endswith("@g.us"))


def is_jid_status_broadcast(jid: str) -> bool:
    return jid == STORIES_JID


def is_jid_newsletter(jid: Optional[str]) -> bool:
    return bool(jid and jid.endswith("@newsletter"))


def is_hosted_pn_user(jid: Optional[str]) -> bool:
    return bool(jid and jid.endswith("@hosted"))


def is_hosted_lid_user(jid: Optional[str]) -> bool:
    return bool(jid and jid.endswith("@hosted.lid"))


def is_jid_bot(jid: Optional[str]) -> bool:
    import re
    if not jid or not jid.endswith("@c.us"):
        return False
    bot_re = re.compile(r"^1313555\d{4}$|^131655500\d{2}$")
    return bool(bot_re.match(jid.split("@")[0]))


def jid_normalized_user(jid: Optional[str]) -> str:
    result = jid_decode(jid)
    if not result:
        return ""
    server = "s.whatsapp.net" if result.server == "c.us" else result.server
    return jid_encode(result.user, server)


def transfer_device(from_jid: str, to_jid: str) -> str:
    from_dec = jid_decode(from_jid)
    to_dec = jid_decode(to_jid)
    if not from_dec or not to_dec:
        return to_jid
    return jid_encode(to_dec.user, to_dec.server, from_dec.device or 0)


__all__ = [
    "S_WHATSAPP_NET", "OFFICIAL_BIZ_JID", "SERVER_JID", "PSA_WID",
    "STORIES_JID", "META_AI_JID",
    "WAJIDDomains", "FullJid",
    "get_server_from_domain_type", "jid_encode", "jid_decode",
    "are_jids_same_user", "is_jid_meta_ai", "is_pn_user", "is_lid_user",
    "is_jid_broadcast", "is_jid_group", "is_jid_status_broadcast",
    "is_jid_newsletter", "is_hosted_pn_user", "is_hosted_lid_user",
    "is_jid_bot", "jid_normalized_user", "transfer_device",
]
