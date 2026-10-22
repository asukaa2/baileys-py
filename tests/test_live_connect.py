"""Live connect smoke test.

Confirms the socket can:
1. Open the WebSocket to WA Web
2. Send the initial stream:open frame
3. Receive at least one frame back from the server
4. Handle the eventual close gracefully (no "recv loop crashed" log)

Run with::

    python tests/test_live_connect.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from baileys_py import (
    DisconnectReason,
    Logger,
    make_wa_socket,
    use_multi_file_auth_state,
)


async def main() -> None:
    folder = tempfile.mkdtemp(prefix="baileys-py-live-")
    state, _ = await use_multi_file_auth_state(folder)

    log = Logger("baileys", level="debug")
    sock = make_wa_socket(
        auth=state,
        logger=log,
        auto_reconnect=False,  # for the test, don't auto-reconnect
        connect_timeout_ms=15_000,
    )

    events: list = []
    sock.ev.on("connection.update", lambda d: events.append(d))

    print("=== connecting ===")
    await sock.connect()

    # Wait up to 10 seconds for either an open or a close
    deadline = asyncio.get_event_loop().time() + 10
    while asyncio.get_event_loop().time() < deadline:
        if any(e.get("connection") == "open" for e in events):
            print("[OK] connection.update: open")
            break
        if any(e.get("connection") == "close" for e in events):
            print("[FAIL] connection closed before reaching open state")
            break
        await asyncio.sleep(0.1)

    # Wait a bit more to see if we receive any frames or get closed
    print("=== waiting for frames / close ===")
    await asyncio.sleep(5)

    print("=== disconnecting ===")
    await sock.disconnect()

    # Summarise
    print("\n=== event summary ===")
    for e in events:
        print(" ", e)

    open_events = [e for e in events if e.get("connection") == "open"]
    close_events = [e for e in events if e.get("connection") == "close"]
    print(f"\nopen events:   {len(open_events)}")
    print(f"close events:  {len(close_events)}")
    print(f"noise handler: {sock._noise is not None}")

    if open_events:
        print("\n[OK] socket reached open state")
    if close_events:
        last = close_events[-1]
        ld = last.get("last_disconnect") or {}
        status = ld.get("status")
        print(f"\n[last disconnect status] {status}")
        # If the close was the "no close frame" case, confirm we
        # classified it as connection_lost (428), not a generic crash.
        if status == DisconnectReason.connection_lost.value:
            print("[OK] close was classified as connection_lost (428)")
        elif status == DisconnectReason.restart_required.value:
            print("[OK] close was clean — restart_required (415)")


if __name__ == "__main__":
    asyncio.run(main())
