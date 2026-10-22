# JID utilities

WhatsApp uses Jabber IDs (JIDs) to identify chats, users, groups,
broadcasts, and other entities. baileys-py ships a complete port of
upstream Baileys' `jid-utils.ts`.

## Anatomy of a JID

```
6281234567890:7@s.whatsapp.net
└──user──┘ └device┘ └─server─┘
```

| Part | Meaning |
|---|---|
| `user` | Phone number (without `+`) for individual chats; random id for groups |
| `device` (optional) | Device id (`:0` = primary phone, `:7` = linked device) |
| `server` | `s.whatsapp.net` (user), `g.us` (group), `broadcast`, `newsletter`, `lid`, `hosted` |

## Encoding / decoding

```python
from baileys_py import jid_encode, jid_decode

# Build a JID
jid = jid_encode("6281234567890", "s.whatsapp.net", device=0)
# -> "6281234567890@s.whatsapp.net"

jid = jid_encode("120363XXX", "g.us")
# -> "120363XXX@g.us"

# Parse a JID
decoded = jid_decode("6281234567890:7@s.whatsapp.net")
# -> FullJid(user="6281234567890", server="s.whatsapp.net", device=7, domain_type=0)
```

## Inspection helpers

```python
from baileys_py import (
    is_jid_group, is_jid_broadcast, is_jid_newsletter,
    is_lid_user, is_pn_user, is_hosted_pn_user, is_hosted_lid_user,
    is_jid_meta_ai, is_jid_bot, is_jid_status_broadcast,
    are_jids_same_user, jid_normalized_user,
)

is_jid_group("120363XXX@g.us")              # True
is_jid_broadcast("status@broadcast")         # True
is_jid_status_broadcast("status@broadcast")  # True
is_jid_newsletter("123@newsletter")          # True
is_pn_user("628XXX@s.whatsapp.net")          # True
is_lid_user("abc@lid")                       # True
is_jid_meta_ai("13135550002@bot")            # True
are_jids_same_user("6281234567890:0@s.whatsapp.net",
                   "6281234567890:7@s.whatsapp.net")  # True
```

## Normalisation

`jid_normalized_user` strips the `:device` suffix and rewrites
`s.whatsapp.net` for legacy `c.us` servers:

```python
jid_normalized_user("6281234567890:7@c.us")
# -> "6281234567890@s.whatsapp.net"
```

Use it whenever you need a stable cache key for a user.

## Transferring the device id

`transfer_device` swaps the device id of one JID onto another:

```python
transfer_device("628XXX:7@s.whatsapp.net", "62YYY@s.whatsapp.net")
# -> "62YYY:7@s.whatsapp.net"
```

## Built-in JIDs

```python
from baileys_py.binary import (
    S_WHATSAPP_NET,        # "@s.whatsapp.net"
    OFFICIAL_BIZ_JID,      # "16505361212@c.us"  — official business
    SERVER_JID,            # "server@c.us"
    PSA_WID,               # "0@c.us"            — system messages
    STORIES_JID,           # "status@broadcast"
    META_AI_JID,           # "13135550002@c.us"  — Meta AI bot
)
```

## WAJIDDomains

WhatsApp has an internal "domain type" byte for some JIDs:

| Constant | Value | Server |
|---|---|---|
| `WAJIDDomains.WHATSAPP` | 0 | `s.whatsapp.net` |
| `WAJIDDomains.LID` | 1 | `lid` |
| `WAJIDDomains.HOSTED` | 128 | `hosted` |
| `WAJIDDomains.HOSTED_LID` | 129 | `hosted.lid` |

You usually don't need this — `jid_decode` populates `domain_type`
automatically.

## Common patterns

### Build a JID from a phone number

```python
def phone_to_jid(phone: str) -> str:
    phone = phone.lstrip("+").replace(" ", "").replace("-", "")
    return jid_encode(phone, "s.whatsapp.net")
```

### Pull the phone number out of a JID

```python
def jid_to_phone(jid: str) -> str:
    decoded = jid_decode(jid)
    return decoded.user if decoded else ""
```

### Distinguish 1:1 from group

```python
if is_jid_group(jid):
    handle_group(jid)
elif is_jid_broadcast(jid):
    handle_broadcast(jid)
elif is_jid_newsletter(jid):
    handle_newsletter(jid)
else:
    handle_dm(jid)
```
