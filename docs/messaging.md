# Sending messages

`sock.send_message(jid, content, options=None)` is the only method
you need to send any kind of message. The `content` argument is either:

* a plain `str` (treated as text), or
* a `dict` with one of the content keys below.

It returns a `WAMessage` with the generated `key` (you can use that
key later to reply, react, edit, or delete).

## Text

```python
await sock.send_message("62XXXXXXXXXXX@s.whatsapp.net", "hello world")
# or
await sock.send_message("62XXXXXXXXXXX@s.whatsapp.net", {"text": "hello world"})
```

## Reply / quote

Pass a `WAMessage` (or its `key`) in the `reply` field:

```python
@sock.ev.on("messages.upsert")
async def on_messages(upsert):
    for msg in upsert["messages"]:
        if msg.key.from_me:
            continue
        await sock.send_message(
            msg.key.remote_jid,
            {"text": "thanks!", "reply": msg},
        )
```

## Image / audio / video / document / sticker

```python
# Image with optional caption
await sock.send_message(jid, {
    "image": {"url": "https://example.com/cat.jpg"},
    "caption": "look at this cat",
    "mimetype": "image/jpeg",
})

# Audio (mp3)
await sock.send_message(jid, {
    "audio": {"url": "https://example.com/clip.mp3"},
    "mimetype": "audio/mpeg",
    # "ptt": True,  # uncomment to send as a voice note (push-to-talk)
})

# Video with caption
await sock.send_message(jid, {
    "video": {"url": "https://example.com/clip.mp4"},
    "caption": "watch this",
    "mimetype": "video/mp4",
    # "gifPlayback": True,  # send as a GIF
})

# Document
await sock.send_message(jid, {
    "document": {"url": "https://example.com/report.pdf"},
    "filename": "report.pdf",
    "mimetype": "application/pdf",
})

# Sticker (webp)
await sock.send_message(jid, {
    "sticker": {"url": "https://example.com/sticker.webp"},
})
```

> baileys-py currently accepts URLs and file paths. For local files,
> pass a path string and override
> `WASocket._build_message_payload` to upload via WhatsApp's media
> upload endpoint (see [Internals](internals.md)).

## Location

```python
await sock.send_message(jid, {
    "location": {
        "lat": -6.2088,
        "lng": 106.8456,
        "name": "Monas",
    },
})
```

## Contact (vCard)

```python
await sock.send_message(jid, {
    "contact": {
        "name": "Budi",
        "vcard": "BEGIN:VCARD\nVERSION:3.0\nFN:Budi\nTEL:+62...\nEND:VCARD",
    },
})
```

## Poll (group only)

> Poll support requires the WA protobuf message type — scaffolded.

```python
await sock.send_message(group_jid, {
    "poll": {
        "name": "Lunch?",
        "values": ["Pizza", "Sushi", "Salad"],
        "selectable_count": 1,
        "multiSelect": False,
    },
})
```

## Forward a message

```python
forwarded = await sock.send_message(jid, {"text": "FYI", "forward": original_msg})
```

## Edit / delete a message you sent

```python
await sock.send_message(jid, {"edit": original_msg.key, "text": "edited text"})
await sock.send_message(jid, {"delete": original_msg.key})
```

## Pin a message

```python
await sock.send_message(jid, {"pin": original_msg.key, "type": "pin"})
```

## Use a custom message id

By default baileys-py generates a 20-char id. Override it with
`MiscMessageGenerationOptions.message_id`:

```python
from baileys_py import MiscMessageGenerationOptions

opts = MiscMessageGenerationOptions(message_id="MY-CUSTOM-ID-001")
await sock.send_message(jid, {"text": "hi"}, options=opts)
```

## Send to a group

Group JIDs end in `@g.us`. Otherwise the API is identical:

```python
group_jid = "120363XXX@g.us"
await sock.send_message(group_jid, "hello team")
```

## Send a status update (story)

Status JID is `status@broadcast`. See [Examples](examples.md) for a
recipe.

## When does send_message actually hit the wire?

In the current scaffold, `send_message`:

1. Builds the high-level message dict.
2. Emits a `messages.upsert` event of type `append` (so your own
   listeners see the sent message) if `emit_own_events=True`.
3. Returns a `WAMessage`.

The actual wire send requires the WA protobuf encoder. To enable it,
override `WASocket._build_message_payload` to encode via
`proto.Message` and `WASocket.send_raw_frame` to wrap in the right
`<message>` stanza. See [Internals](internals.md) for a sketch.

## Message status & receipts

After a successful send, you'll see these events in order:

1. `messages.upsert` (type `append`) — your message is in your store
2. `message-receipt.update` — server got it (`status = 1` server, `2` device, `3` read)

The receipt `status` codes are:

| Status | Meaning |
|---|---|
| 0 | pending |
| 1 | sent to server |
| 2 | sent to recipient device |
| 3 | read |
| 4 | played (audio/video) |
| 5 | paused (audio/video) |
| 6 | reacted |

## Reactions

```python
# React to a message (emoji)
await sock.send_message(jid, {"react": {"text": "👍", "key": original_msg.key}})

# Remove a reaction
await sock.send_message(jid, {"react": {"text": "", "key": original_msg.key}})
```
