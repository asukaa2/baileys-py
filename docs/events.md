# Events & lifecycle

`baileys-py` uses a single `BaileysEventEmitter` per socket. You
register listeners with `sock.ev.on(event_name, callback)` and the
socket emits events as it connects, receives messages, etc.

## Subscribing

```python
def on_update(update: dict):
    print("connection:", update.get("connection"))

sock.ev.on("connection.update", on_update)
```

Listeners can be **sync** or **async**. Async listeners are scheduled on
the event loop and never block the socket.

```python
@sock.ev.on("messages.upsert")
async def on_messages(upsert):
    await asyncio.sleep(1)  # doing something async is fine
    print("got", len(upsert["messages"]), "messages")
```

## Unsubscribing

```python
sock.ev.off("connection.update", on_update)
sock.ev.remove_all_listeners("connection.update")
sock.ev.remove_all_listeners()
```

## Batched processing

The upstream Baileys API has a `sock.ev.process(async (events) => {...})`
helper that batches multiple events into a single dict and dispatches
them once per tick. baileys-py supports the same pattern:

```python
async def handle(events: dict):
    if events.get("connection.update"):
        ...
    if events.get("messages.upsert"):
        ...
    if events.get("creds.update"):
        ...

sock.ev.process(handle)
```

While a processor is registered, `emit()` no longer calls listeners
one-by-one. Instead, events accumulate in a buffer and are flushed in a
single call to your processor at the next event-loop tick.

To stop batched processing:

```python
sock.ev.stop_processing()
```

## Full event list

All event names mirror upstream Baileys' `BaileysEventMap`.

### Connection & credentials

| Event | Payload | When |
|---|---|---|
| `connection.update` | `Partial<ConnectionState>` (dict) | WS opened / closed / QR available / phone connected |
| `creds.update` | `Partial<AuthenticationCreds>` | Saved credentials changed (call `save_creds()`) |

### History sync

| Event | Payload | When |
|---|---|---|
| `messaging-history.set` | `{ chats, contacts, messages, isLatest, progress, syncType }` | Initial / on-demand history sync chunk |
| `messaging-history.status` | `{ syncType, status, explicit }` | Sync phase completed or paused |

### Chats & contacts

| Event | Payload | When |
|---|---|---|
| `chats.upsert` | `List[Chat]` | New chats appear (history sync) |
| `chats.update` | `List[ChatUpdate]` | Existing chats changed |
| `chats.delete` | `List[str]` (jids) | Chats deleted |
| `chats.lock` | `{ id, locked }` | A chat was locked / unlocked |
| `contacts.upsert` | `List[Contact]` | New contacts appear |
| `contacts.update` | `List[Partial[Contact]]` | Existing contacts changed (e.g. profile pic) |
| `presence.update` | `{ id, presences }` | Online/offline/typing status of participants |
| `blocklist.set` | `{ blocklist }` | Initial blocklist received |
| `blocklist.update` | `{ blocklist, type: "add" \| "remove" }` | Blocklist changed |

### Messages

| Event | Payload | When |
|---|---|---|
| `messages.upsert` | `{ messages: List[WAMessage], type: "notify" \| "append", requestId? }` | New message received OR appended (your own sent messages if `emit_own_events=True`) |
| `messages.update` | `List[{ key, update }]` | Status changed (delivered / read), edited, deleted, poll updates |
| `messages.media-update` | `List[{ key, media?, error? }]` | Decrypted media available (or decryption failed) |
| `messages.delete` | `{ keys: List[WAMessageKey] } \| { jid, all: True }` | Messages deleted |
| `messages.reaction` | `List[{ key, reaction }]` | A message was reacted to (or reaction removed) |
| `message-receipt.update` | `List[{ key, receipt }]` | Read / delivery receipts |

### Groups

| Event | Payload | When |
|---|---|---|
| `groups.upsert` | `List[GroupMetadata]` | New group chats appear |
| `groups.update` | `List[Partial[GroupMetadata]]` | Group subject / description changed |
| `group-participants.update` | `{ id, author, participants, action }` | Participants added / removed / promoted / demoted |
| `group.join-request` | `{ id, author, participant, action, method }` | Someone requested to join a group |
| `group.member-tag.update` | `{ groupId, participant, label }` | A participant's group label changed |

### Calls

| Event | Payload | When |
|---|---|---|
| `call` | `List[WACallEvent]` | Incoming / accepted / rejected call |

### Newsletters (channels)

| Event | Payload | When |
|---|---|---|
| `newsletter.reaction` | `{ id, server_id, reaction: { code, count, removed? } }` | Newsletter post reaction |
| `newsletter.view` | `{ id, server_id, count }` | Newsletter view count |
| `newsletter-participants.update` | `{ id, author, user, new_role, action }` | Newsletter participant role changed |
| `newsletter-settings.update` | `{ id, update }` | Newsletter settings changed |

### Labels (business)

| Event | Payload | When |
|---|---|---|
| `labels.edit` | `Label` | A label was created / edited |
| `labels.association` | `{ association, type: "add" \| "remove" }` | Label assigned to / removed from a chat |

### Settings

| Event | Payload | When |
|---|---|---|
| `settings.update` | `{ setting, value }` | A user setting changed (locale, time format, etc.) |
| `message-capping.update` | `NewChatMessageCapInfo` | Server enforced a new message cap |

## Connection state machine

```
                  ┌─────────────┐
                  │  (initial)  │
                  └──────┬──────┘
                         │ connect()
                         ▼
                  ┌─────────────┐
                  │ connecting  │
                  └──────┬──────┘
                         │ WS open
                         ▼
                  ┌─────────────┐
                  │    open     │ ◄────┐
                  └──────┬──────┘      │
                         │ disconnect()│
                         ▼            │
                  ┌─────────────┐      │
                  │    close    │ ─────┘ auto-reconnect
                  └─────────────┘
```

The `connection.update` event fires on every transition. Its payload:

```python
{
    "connection": "open" | "connecting" | "close",
    "qr": "2@...",                      # present when QR is available
    "receivedPendingNotifications": True,
    "isOnline": True,
    "user": { "id": "...", "name": "..." },
    "lastDisconnect": { "error": "...", "status": 401 },
}
```

## Disconnect reasons

`lastDisconnect.status` is one of:

| Status | Constant | Meaning |
|---|---|---|
| 410 | `DisconnectReason.connection_closed` | Server closed the WS |
| 428 | `DisconnectReason.connection_lost` | Network lost |
| 440 | `DisconnectReason.connection_replaced` | Another client took over |
| 408 | `DisconnectReason.timed_out` | Keepalive missed |
| 415 | `DisconnectReason.restart_required` | Server asked us to restart |
| 401 | `DisconnectReason.logged_out` | Logged out — clear auth state and re-scan |
| 403 | `DisconnectReason.forbidden` | Banned / forbidden |
| 401 | `DisconnectReason.multidevice_mismatch` | Linked-device protocol mismatch |

## Why are some events scaffolded?

The full event set requires the WhatsApp protobuf schema (`WAProto/`).
Scaffolded events still fire, but with raw `BinaryNode` payloads
instead of decoded `proto.WebMessageInfo` dicts. To get full payloads,
drop in `WAProto/` and override `WASocket._dispatch_node` (see
[Internals](internals.md)).
