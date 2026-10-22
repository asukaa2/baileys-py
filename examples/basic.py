"""Basic Baileys-Py example: scan a QR code and reply to incoming messages.

Run with::

    python examples/basic.py
"""
from __future__ import annotations

import asyncio
import os
import sys

# Make sure the package is importable when running from source.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import qrcode

from baileys_py import (
    DisconnectReason,
    make_wa_socket,
    use_multi_file_auth_state,
)


async def main() -> None:
    auth_folder = "./baileys_auth_info"
    state, save_creds = await use_multi_file_auth_state(auth_folder)

    sock = make_wa_socket(auth=state, push_name="Baileys-Py Bot")

    # ----- connection lifecycle ----------------------------------------
    async def start_sock() -> None:
        await sock.connect()

    @sock.ev.on("connection.update")
    async def on_connection(update: dict) -> None:
        connection = update.get("connection")
        qr = update.get("qr")
        last_disconnect = update.get("lastDisconnect")

        if qr:
            print("\n[QR] Scan this QR with your WhatsApp phone app:")
            print_qr(qr)

        if connection == "open":
            print("[OK] Connected to WhatsApp Web")
            if sock.user:
                print(f"[OK] Logged in as {sock.user.get('id')} ({sock.user.get('name')})")

        if connection == "close":
            status = (last_disconnect or {}).get("status")
            if status == DisconnectReason.logged_out.value:
                print("[FATAL] Logged out — clear auth folder and re-scan.")
            else:
                print("[RECONNECT] Restarting socket...")
                await start_sock()

    @sock.ev.on("creds.update")
    async def on_creds(_) -> None:
        await save_creds()

    # ----- message handlers --------------------------------------------
    @sock.ev.on("messages.upsert")
    async def on_messages(upsert: dict) -> None:
        for msg in upsert.get("messages", []):
            # `msg` here is a WAMessage dataclass OR a raw BinaryNode (when
            # it was not yet decrypted by the protocol layer).
            key = getattr(msg, "key", None) or (msg.attrs if hasattr(msg, "attrs") else {})
            jid = getattr(key, "remote_jid", None) or key.get("remoteJid") or key.get("from")
            from_me = getattr(key, "from_me", None) or key.get("fromMe", False)
            msg_id = getattr(key, "id", None) or key.get("id")
            if from_me:
                continue
            text = _extract_text(msg)
            print(f"[MSG] from {jid} ({msg_id}): {text!r}")
            if text:
                await sock.send_message(jid, {"text": f"pong {msg_id}"})

    await start_sock()

    # Keep the script alive
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await sock.disconnect()


def print_qr(payload: str) -> None:
    """Render a QR payload to ASCII art in the terminal."""
    qr = qrcode.QRCode(border=1)
    qr.add_data(payload)
    qr.print_ascii(invert=True)


def _extract_text(msg) -> str:
    if hasattr(msg, "message") and msg.message:
        m = msg.message
        return m.get("conversation") or \
               (m.get("extendedTextMessage") or {}).get("text") or ""
    # Raw BinaryNode fallback — search for <body> text content
    if hasattr(msg, "attrs"):
        return msg.attrs.get("body", "")
    return ""


if __name__ == "__main__":
    asyncio.run(main())
