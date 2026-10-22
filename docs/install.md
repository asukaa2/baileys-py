# Installation

`baileys-py` runs on **Python 3.9+**. It has no native-code dependencies —
everything is pure Python.

## Option A — Install from git (recommended)

```bash
# With pip
pip install "git+https://github.com/asukaa2/baileys-py.git"

# With uv
uv pip install "git+https://github.com/asukaa2/baileys-py.git"

# With pipx (CLI use only — not relevant for a library, included for completeness)
pipx install "git+https://github.com/asukaa2/baileys-py.git"
```

### Install a specific tag / commit / branch

```bash
# A specific branch
pip install "git+https://github.com/asukaa2/baileys-py.git@main"

# A specific commit (full SHA)
pip install "git+https://github.com/asukaa2/baileys-py.git@c2bc71d"
```

## Option B — Install from source

```bash
git clone https://github.com/asukaa2/baileys-py.git
cd baileys-py
pip install -e .           # editable install (changes you make are picked up)
# or
pip install .             # regular install
```

### Optional dev extras

```bash
pip install -e ".[dev]"   # pytest, pytest-asyncio, ruff, build
```

## Option C — Build a wheel and install that

```bash
git clone https://github.com/asukaa2/baileys-py.git
cd baileys-py
pip install build
python -m build              # produces dist/baileys_py-0.1.0-py3-none-any.whl
pip install dist/baileys_py-0.1.0-py3-none-any.whl
```

## Runtime dependencies

These are installed automatically:

| Package | Min version | Used for |
|---|---|---|
| `websockets` | 11.0 | WebSocket connection to WA |
| `cryptography` | 41.0 | Curve25519, Ed25519, AES-GCM/CTR, HKDF |
| `qrcode` | 7.4 | Rendering QR codes for terminal login |
| `protobuf` | 4.24 | (Reserved for WA protobuf; not yet wired in) |
| `aiofiles` | 23.0 | Async file I/O in the multi-file auth state |

## Verifying the install

```bash
python -c "import baileys_py; print(baileys_py.__version__)"
# expected: 0.1.0
```

## Verifying with the test suite

```bash
git clone https://github.com/asukaa2/baileys-py.git
cd baileys-py
python tests/test_smoke.py
# expected: All tests passed
```

## Troubleshooting

### `does not appear to be a Python project, as neither pyproject.toml nor setup.py are present in the directory`

This error comes from `uv` when it clones a repo and finds neither
`pyproject.toml` nor `setup.py` at the root. If you see it on
`asukaa2/baileys-py`, check:

1. **You're using the right URL.** The repo is
   `https://github.com/asukaa2/baileys-py` — **not**
   `https://github.com/whiskeysockets/Baileys` (the upstream is a
   TypeScript project and has no `pyproject.toml`).
2. **Your `uv` cache is stale.** Clear it and retry:

   ```bash
   uv cache clean
   uv pip install "git+https://github.com/asukaa2/baileys-py.git"
   ```

3. **You installed before the first push.** The repo on
   `https://github.com/asukaa2/baileys-py` had no commits at all until
   `c2bc71d` (Oct 2026). Anything cached from before that will be empty.

If the error persists, file an issue with the exact command you ran and
the output of `uv --version` / `pip --version`.

### `ModuleNotFoundError: No module named 'pino'`

Older versions of `baileys-py` had `pino` listed as a dependency by
mistake. The package on PyPI called `pino` is unrelated to Baileys'
`pino` logger. We now ship our own
[`baileys_py.logger`](../baileys_py/logger.py), so `pino` is no longer
required. Upgrade:

```bash
pip install --force-reinstall "git+https://github.com/asukaa2/baileys-py.git"
```

### `websockets` install fails on Termux

```bash
pkg install python-dev libssl-dev
pip install --upgrade pip
pip install websockets
```

### `cryptography` install fails on Linux without rust

`cryptography>=41` ships manylinux wheels — usually `pip install` just
works. If you're on an exotic platform and need to build from source:

```bash
# Debian / Ubuntu
sudo apt install rustc cargo libssl-dev libffi-dev python3-dev
# Termux (Android)
pkg install rust libssl-dev python-dev
```

### `protobuf` install hangs

It shouldn't — `protobuf` ships wheels for every supported platform.
If your network is the issue, try a mirror:

```bash
pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple protobuf
```
