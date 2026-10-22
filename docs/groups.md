# Groups, chats, presence, profile

baileys-py exposes a set of helper functions in `baileys_py.messages`
that wrap common `<iq>` queries. All are async and operate on a
`WASocket` instance.

```python
from baileys_py.messages import (
    group_create, group_invite_code, group_join, group_leave,
    group_participants_update,
    chat_archive, chat_pin, chat_mark_read, chat_send_message,
    send_presence_update,
    get_profile_picture_url, update_profile_name, update_profile_status,
)
```

## Groups

### Create a group

```python
group = await group_create(sock, "My new group", participants=[
    "62XXX@s.whatsapp.net",
    "62YYY@s.whatsapp.net",
])
# Returns a dict with the raw server response.
```

### Get the invite code

```python
code = await group_invite_code(sock, "120363XXX@g.us")
# -> "abc123XYZ"  (or None if the group has no invite)
```

### Join a group by invite code

```python
await group_join(sock, "abc123XYZ")
```

### Leave a group

```python
await group_leave(sock, "120363XXX@g.us")
```

### Update participants

```python
# Add
await group_participants_update(sock, group_jid, ["62XXX@s.whatsapp.net"], "add")

# Remove
await group_participants_update(sock, group_jid, ["62XXX@s.whatsapp.net"], "remove")

# Promote to admin
await group_participants_update(sock, group_jid, ["62XXX@s.whatsapp.net"], "promote")

# Demote from admin
await group_participants_update(sock, group_jid, ["62XXX@s.whatsapp.net"], "demote")
```

## Chats

### Send a message

Alias for `sock.send_message`:

```python
await chat_send_message(sock, "62XXX@s.whatsapp.net", {"text": "hi"})
```

### Archive / unarchive

```python
await chat_archive(sock, "62XXX@s.whatsapp.net", archive=True)
await chat_archive(sock, "62XXX@s.whatsapp.net", archive=False)
```

### Pin / unpin

```python
await chat_pin(sock, "62XXX@s.whatsapp.net", pin=True)
await chat_pin(sock, "62XXX@s.whatsapp.net", pin=False)
```

### Mark messages as read

```python
from baileys_py import WAMessageKey

keys = [
    WAMessageKey(remote_jid="62XXX@s.whatsapp.net", id="MSG1"),
    WAMessageKey(remote_jid="62XXX@s.whatsapp.net", id="MSG2"),
]
await chat_mark_read(sock, "62XXX@s.whatsapp.net", keys)
```

## Presence

```python
# Show "available" (online)
await send_presence_update(sock, "62XXX@s.whatsapp.net", presence="available")

# Show "composing" (typing indicator)
await send_presence_update(sock, "62XXX@s.whatsapp.net", presence="composing")

# Show "paused" (stop typing)
await send_presence_update(sock, "62XXX@s.whatsapp.net", presence="paused")

# Show "unavailable" (offline)
await send_presence_update(sock, "62XXX@s.whatsapp.net", presence="unavailable")

# Show "recording" (audio recording)
await send_presence_update(sock, "62XXX@s.whatsapp.net", presence="recording")
```

To subscribe to other users' presence changes, listen for the
`presence.update` event:

```python
@sock.ev.on("presence.update")
async def on_presence(update):
    jid = update["id"]
    presences = update["presences"]
    for participant, data in presences.items():
        print(f"{participant}: {data}")
```

## Profile

### Get profile picture

```python
# High-res (default)
url = await get_profile_picture_url(sock, "62XXX@s.whatsapp.net", high_res=True)

# Thumbnail
url = await get_profile_picture_url(sock, "62XXX@s.whatsapp.net", high_res=False)
```

### Update your profile name / status

```python
await update_profile_name(sock, "My New Name")
await update_profile_status(sock, "Available for questions")
```

## Block / unblock

> Not yet exposed as a high-level helper. Use `sock.query` directly:

```python
from baileys_py import BinaryNode

async def block(sock, jid: str):
    node = BinaryNode(
        tag="iq",
        attrs={"to": "@s.whatsapp.net", "type": "set", "xmlns": "block"},
        content=[BinaryNode(tag="item", attrs={"jid": jid, "action": "block"})],
    )
    return await sock.query(node)

async def unblock(sock, jid: str):
    node = BinaryNode(
        tag="iq",
        attrs={"to": "@s.whatsapp.net", "type": "set", "xmlns": "block"},
        content=[BinaryNode(tag="item", attrs={"jid": jid, "action": "unblock"})],
    )
    return await sock.query(node)
```

## Newsletter (channels)

> Scaffolded — same IQ pattern as groups, but with `xmlns="newsletter"`.

## Calls

> Scaffolded — listen for the `call` event and respond via IQ.

```python
@sock.ev.on("call")
async def on_call(events):
    for call in events:
        if call["status"] == "offer":
            # Decide whether to accept / reject
            pass
```
