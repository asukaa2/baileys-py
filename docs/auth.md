# Auth state

The "auth state" is the set of cryptographic credentials a linked-device
session needs to reconnect to WhatsApp without rescanning a QR code.

baileys-py ships two ready-made auth-state backends:

* `use_multi_file_auth_state(folder)` — one JSON file per credential
  (mirrors upstream Baileys' `useMultiFileAuthState`).
* `use_single_file_auth_state(path)` — a single JSON file with
  everything in it (handy for tiny scripts).

Both expose the same interface:

```python
state, save_creds = await use_multi_file_auth_state("./auth_info")
sock = make_wa_socket(auth=state)

@sock.ev.on("creds.update")
async def on_creds(_):
    await save_creds()
```

## What's inside an auth state

An auth state has two parts:

1. **`creds`** — an `AuthenticationCreds` dataclass:

    * `noise_key` — Curve25519 keypair used in the Noise XX handshake
    * `pairing_ephemeral_key_pair` — ephemeral keypair for the initial
      pairing step
    * `signed_identity_key` — Ed25519 identity key
    * `signed_pre_key` — signed X25519 pre-key (rotated periodically)
    * `registration_id` — 14-bit random id
    * `adv_secret_key` — base64 random 32 bytes
    * `me` — once authenticated, the user's `{id, name}`
    * `account` — server-provided signed device identity
    * `registered` — True once the device is paired with a phone
    * `account_settings` — ephemeral-message default, unarchive-chats flag
    * `processed_history_messages` — list of history-sync notification
      headers we've already processed (dedup)

2. **`keys`** — a `SignalKeyStore` with the per-recipient Signal
   protocol state:

    * `pre-key` — ephemeral X25519 keys
    * `session` — per-recipient ratchet state
    * `sender-key` — per-group sender-key state
    * `app-state-sync-key` — app-state versioning
    * `app-state-sync-version` — LTHash state
    * `lid-mapping` — PN↔LID mapping
    * `device-list` — per-user known devices
    * `tctoken` — transactional commit token
    * `identity-key` — per-user identity keys

## Multi-file auth state

One file per credential. Best for production-like usage because you can
shard the directory across many small files, write concurrently, and
audit easily.

```python
from baileys_py import use_multi_file_auth_state

state, save_creds = await use_multi_file_auth_state("./auth_info")
```

The folder ends up looking like:

```
auth_info/
├── creds.json
├── pre-key-1.json
├── pre-key-2.json
├── session-62XXX@s.whatsapp.net-0.json
├── session-62XXX@s.whatsapp.net-1.json
├── sender-key-120363XXX@g.us-62XXX@s.whatsapp.net.json
└── ...
```

## Single-file auth state

Everything in one JSON file. Best for tiny scripts / examples / quick
experiments.

```python
from baileys_py import use_single_file_auth_state

state, save_creds = await use_single_file_auth_state("./auth.json")
```

The file looks like:

```json
{
  "creds": { "noise_key": {...}, "signed_identity_key": {...}, ... },
  "keys":  { "pre-key": {"1": {...}}, "session": {...}, ... }
}
```

## Custom backends

You can implement your own by subclassing `SignalKeyStore` and returning
an `AuthenticationState`:

```python
from baileys_py import (
    AuthenticationState,
    AuthenticationCreds,
    SignalKeyStore,
    init_auth_creds,
)


class PostgresSignalKeyStore(SignalKeyStore):
    def __init__(self, pool, jid: str):
        self.pool = pool
        self.jid = jid

    async def get(self, type_: str, ids: list[str]) -> dict:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, value FROM wa_signal_keys "
                "WHERE jid = $1 AND type = $2 AND id = ANY($3)",
                self.jid, type_, ids,
            )
            return {r["id"]: r["value"] for r in rows}

    async def set(self, data: dict) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for cat, items in data.items():
                    for k, v in items.items():
                        await conn.execute(
                            "INSERT INTO wa_signal_keys (jid, type, id, value) "
                            "VALUES ($1,$2,$3,$4) "
                            "ON CONFLICT (jid,type,id) DO UPDATE SET value = EXCLUDED.value",
                            self.jid, cat, k, v,
                        )


async def use_postgres_auth_state(pool, jid: str):
    # Load creds from your DB; fall back to fresh creds if first run.
    creds = await load_creds_from_db(pool, jid) or init_auth_creds()
    keys = PostgresSignalKeyStore(pool, jid)

    state = AuthenticationState(creds=creds, keys=keys)

    async def save_creds():
        await save_creds_to_db(pool, jid, creds)

    return state, save_creds
```

## Clearing credentials (log out)

Delete the folder / file:

```python
import shutil
shutil.rmtree("./auth_info")
```

Or call `keys.clear()`:

```python
await state.keys.clear()
# also overwrite creds.json with `init_auth_creds()` to start fresh
```

## Backing up credentials

The credentials directory contains **all the keys needed to impersonate
your WhatsApp account**. Treat it like a password:

* Keep it on encrypted storage.
* Don't commit it to git (it's in `.gitignore` already).
* Don't ship it inside Docker images.
* Rotate it if leaked: log out from your phone (Settings → Linked
  Devices → Remove), delete the local folder, then re-scan the QR.

## Multi-account

Each account needs its own auth state folder:

```python
state1, save1 = await use_multi_file_auth_state("./acc1")
state2, save2 = await use_multi_file_auth_state("./acc2")

sock1 = make_wa_socket(auth=state1, push_name="Bot 1")
sock2 = make_wa_socket(auth=state2, push_name="Bot 2")
```

## Concurrency

The multi-file backend uses an `asyncio.Lock` per file, so concurrent
`save_creds()` / `keys.set()` calls are safe. The single-file backend
uses one lock for the whole file.

Both backends are *eventually consistent* — a crash between an in-memory
update and the disk write can lose the latest credentials. For strict
durability, use a real database backend.
