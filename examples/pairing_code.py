"""Pairing-code example — login with a phone number instead of a QR.

Run with::

    python examples/pairing_code.py +62XXXXXXXXXXX
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from baileys_py import make_wa_socket, use_multi_file_auth_state


async def main(phone_number: str) -> None:
    state, save_creds = await use_multi_file_auth_state("./baileys_auth_info")
    sock = make_wa_socket(auth=state, push_name="Baileys-Py Bot")

    @sock.ev.on("connection.update")
    async def on_connection(update: dict) -> None:
        if update.get("qr") and not sock.auth_state.creds.registered:
            code = await sock.request_pairing_code(phone_number)
            print(f"\n[PAIRING CODE] {code}")
            print("Enter this code on your phone: WhatsApp → Settings → Linked devices → Link with phone number")
        if update.get("connection") == "open":
            print("[OK] Connected!")
            print("Logged in as:", sock.user.get("id") if sock.user else "?")

    @sock.ev.on("creds.update")
    async def on_creds(_):
        await save_creds()

    await sock.connect()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await sock.disconnect()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/pairing_code.py +62XXXXXXXXXXX")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
