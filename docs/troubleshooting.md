# Troubleshooting

Common errors and how to fix them.

---

## Install errors

### `does not appear to be a Python project, as neither pyproject.toml nor setup.py are present in the directory`

This is `uv`'s error when the cloned repo has neither file at the root.
On baileys-py, check:

1. **Right URL.** Use `git+https://github.com/asukaa2/baileys-py.git`
   (the upstream `whiskeysockets/Baileys` is a TypeScript repo with no
   `pyproject.toml`).
2. **Stale uv cache.** Clear it:

   ```bash
   uv cache clean
   uv pip install "git+https://github.com/asukaa2/baileys-py.git"
   ```

3. **Specifying a `--subdirectory` when there isn't one.** The
   `pyproject.toml` is at the **root** of the repo. Don't pass
   `subdirectory=`.

4. **Installing from a ref that doesn't have `pyproject.toml`.** The
   first commit (`c2bc71d`, Oct 2026) added `pyproject.toml`. Anything
   before that fails.

If it still fails, file an issue with the exact command and `uv --version`.

### `ModuleNotFoundError: No module named 'pino'`

Older `baileys-py` versions had `pino` listed as a dependency. The PyPI
package `pino` is unrelated (a JSON logger inspired by pino.js).
baileys-py now ships its own `logger.py`. Upgrade:

```bash
pip install --force-reinstall --no-deps "git+https://github.com/asukaa2/baileys-py.git"
```

### `websockets` install fails on Termux (Android)

```bash
pkg install python-dev libssl-dev
pip install --upgrade pip
pip install websockets
```

### `cryptography` install fails with "needs rust"

`cryptography>=41` ships manylinux wheels — usually `pip install` just
works. If you're on an exotic platform and need to build from source:

```bash
# Debian / Ubuntu
sudo apt install rustc cargo libssl-dev libffi-dev python3-dev
# Termux
pkg install rust libssl-dev python-dev
```

### `protobuf` install hangs

It shouldn't — `protobuf` ships wheels for every supported platform.
If your network is the issue, try a mirror:

```bash
pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple protobuf
```

---

## Runtime errors

### `RuntimeError: socket is not connected`

You called `sock.send_message` / `sock.send_raw_frame` before the
socket finished connecting. Wait for the `connection.update` event with
`connection == "open"` first:

```python
ready = asyncio.Event()

@sock.ev.on("connection.update")
async def on_conn(update):
    if update.get("connection") == "open":
        ready.set()

await sock.connect()
await ready.wait()
await sock.send_message(jid, "hi")
```

### `TimeoutError: query ... timed out`

You sent an IQ query (`sock.query(node)`) and the server didn't respond
in time. Either:

* The IQ id mismatched (rare — `sock.query` auto-assigns ids).
* The server is unreachable / rate-limiting.
* The query was malformed and the server sent an error response that
  wasn't picked up as the matching reply.

Increase the timeout:

```python
resp = await sock.query(node, timeout_ms=120_000)
```

### `EOFError: end of stream` during `decode_binary_node`

A frame from the server was truncated or malformed. Most often this
happens when the noise transport got out of sync (e.g. you reconnected
with a stale session). Fix by logging out and rescanning.

### `Boom`-style errors (`RuntimeError("...", code)`)

baileys-py wraps WA error nodes into `RuntimeError(message, code)`.
The code is the WA error code (e.g. `401`, `403`, `419`). See
[Events → Disconnect reasons](events.md#disconnect-reasons).

### `RuntimeError: noise certificate verification failed`

You passed a `verify_certificate` callback that returned `False`.
Either fix your verifier (the cert is genuinely invalid) or omit the
callback to skip verification (testing only).

---

## Connection issues

### `WebSocket connection failed` immediately

Possible causes:

* **Firewall blocking WSS port 443** — unusual, but check.
* **WA banned your IP** — sometimes happens on cloud providers; use a
  residential proxy.
* **Wrong `wa_websocket_url`** — make sure it's
  `wss://web.whatsapp.com/ws/chat`.

### Connection drops every 30 seconds

That's the keepalive interval. baileys-py sends a WS-level ping every
30 seconds by default. If your proxy strips pings, increase the interval
or move to a direct connection:

```python
sock = make_wa_socket(auth=state, keep_alive_interval_ms=120_000)
```

### Connection says "logged out" (status 401)

Your credentials are no longer valid. Either:

* You removed the linked device from your phone.
* WA rotated something and the session expired.
* You logged in with the same credentials on another phone (and the
  old session was invalidated).

Fix: delete the `auth_info` folder and re-scan the QR.

### Two devices can't be linked simultaneously

WhatsApp's multi-device support is per-account, not per-credential.
You can link multiple devices to one account, but each linked device
gets its own credentials. Don't share one `auth_info` folder across
two processes — use a separate folder per device.

---

## Auth / credentials

### `auth_info/` is full of small JSON files

That's how `use_multi_file_auth_state` works — one file per
credential. See [Auth state](auth.md).

### Lost my `auth_info/` folder — can I recover?

No. The keys are not stored anywhere else. Re-scan the QR to create a
new linked device.

### Can I copy `auth_info/` to another machine?

Yes. The credentials are pure keypairs and don't bind to the host.
Treat the folder like a password (see [Auth state → Backing up](auth.md#backing-up-credentials)).

---

## Messages

### `send_message` doesn't actually deliver

The high-level API builds the message dict and emits the
`messages.upsert` (type `append`) event, but the **actual wire send
requires the WA protobuf schema**. See [Internals → Extending
baileys-py](internals.md#extending-baileys-py-scaffolded-interop) for
how to wire it in.

### Messages from myself are showing up

That's because `emit_own_events=True` (the default). Turn it off if
you only want incoming messages:

```python
sock = make_wa_socket(auth=state, emit_own_events=False)
```

### Receipts aren't firing

Make sure you've subscribed to the right event:

```python
@sock.ev.on("message-receipt.update")
async def on_receipt(updates):
    for u in updates:
        print(u["key"].id, "→", u["receipt"])
```

### Polls don't aggregate

`get_aggregate_votes_in_poll_message` requires the WA protobuf poll
type. Until you wire in WAProto, it returns an empty list.

---

## Build / packaging

### `pip install -e .` doesn't pick up changes

You're probably using an old setuptools. Upgrade:

```bash
pip install --upgrade setuptools pip
pip install -e .
```

### `MANIFEST.in` is being ignored

`MANIFEST.in` only matters for `sdist` (`python -m build --sdist`). If
you're installing from a wheel or directly from the repo, file
inclusion is controlled by `pyproject.toml`'s
`[tool.setuptools.package-data]` and `include-package-data = true`.

### sdist is missing the binary constants

Check `MANIFEST.in`:

```
recursive-include baileys_py *.py
```

Re-build:

```bash
rm -rf dist/ build/ *.egg-info
python -m build
```

### Tests fail with `pytest-asyncio` not installed

Install the dev extras:

```bash
pip install -e ".[dev]"
```

Then:

```bash
pytest -q tests/
```

---

## Performance

### Sending 1000 messages is slow

Two things to check:

1. **Don't `await` each one serially.** Use `asyncio.gather`:

   ```python
   await asyncio.gather(*[
       sock.send_message(jid, {"text": f"msg {i}"})
       for i in range(1000)
   ])
   ```

2. **The send is bottlenecked by the underlying WS send lock.** If
   you've measured that this is the actual bottleneck, consider
   batching multiple `BinaryNode`s into one frame.

### Memory grows unbounded over time

Listeners you forgot to unregister. Check that every `sock.ev.on(...)`
either:

* is a module-level listener (lives for the socket's lifetime), or
* is unregistered with `sock.ev.off(event, listener)` when no longer
  needed.

### `keys` store is getting big

The multi-file backend writes one file per Signal session. For bots
with many contacts this can reach tens of thousands of files.
Switch to the single-file backend (one JSON, slower per-write but
fewer inodes), or implement a DB-backed store (see
[Auth state → Custom backends](auth.md#custom-backends)).
