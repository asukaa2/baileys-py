# baileys-py documentation

A simple, Pythonic port of the [Baileys](https://github.com/whiskeysockets/Baileys)
WhatsApp Web API.

This is the documentation entry point. Start here if you're new to the
project; jump straight to [Installation](install.md) if you just want to
get it running.

## Table of contents

| # | Page | What's inside |
|---|------|---------------|
| 1 | [Overview](overview.md) | What baileys-py is, what works, what's scaffolded, design goals |
| 2 | [Installation](install.md) | uv / pip / from-source, troubleshooting common install errors |
| 3 | [Quick start](quickstart.md) | Minimal QR-login bot, pairing-code login, reply bot |
| 4 | [Events & lifecycle](events.md) | `BaileysEventEmitter`, all event names, batched `process()` |
| 5 | [Sending messages](messaging.md) | `send_message`, all content types, replies, polls |
| 6 | [Auth state](auth.md) | `use_multi_file_auth_state`, `use_single_file_auth_state`, custom stores |
| 7 | [JID utilities](jid.md) | Encode / decode / inspect WhatsApp JIDs |
| 8 | [Binary protocol](binary.md) | `BinaryNode`, encode/decode, token dictionaries |
| 9 | [Crypto layer](crypto.md) | Curve25519, Ed25519, HKDF, AES-GCM/CTR, Noise XX |
| 10 | [Groups / chats / presence](groups.md) | Group operations, chat pin/archive, presence, profile |
| 11 | [API reference](api.md) | Full list of exported names with signatures |
| 12 | [Examples](examples.md) | Curated example scripts and recipes |
| 13 | [Internals](internals.md) | Module map, design notes, how to extend baileys-py |
| 14 | [Troubleshooting](troubleshooting.md) | Common errors and how to fix them |
| 15 | [FAQ](faq.md) | Frequently asked questions |
| 16 | [Changelog](changelog.md) | What's new in each release |

## Quick links

* 📦 **Repo**: <https://github.com/asukaa2/baileys-py>
* 📚 **Upstream Baileys**: <https://github.com/whiskeysockets/Baileys>
* 🚀 **Install**: `pip install git+https://github.com/asukaa2/baileys-py.git`
* 🧪 **Tests**: `python tests/test_smoke.py` (13 tests, no network)
