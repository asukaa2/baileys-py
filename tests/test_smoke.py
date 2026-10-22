"""Smoke tests for the baileys_py package — pure-python, no network.

Run with::

    pytest -q tests/test_smoke.py

Or directly::

    python tests/test_smoke.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# Allow running from source tree.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import baileys_py as bp


# ---------------------------------------------------------------------------
# JID utilities
# ---------------------------------------------------------------------------

def test_jid_encode_decode_round_trip():
    jid = bp.jid_encode("628123456789", "s.whatsapp.net", device=0)
    assert jid == "628123456789@s.whatsapp.net", jid

    decoded = bp.jid_decode(jid)
    assert decoded is not None
    assert decoded.user == "628123456789"
    assert decoded.server == "s.whatsapp.net"

    assert bp.is_pn_user(jid)
    assert not bp.is_jid_group(jid)
    assert bp.is_jid_group("123@g.us")


# ---------------------------------------------------------------------------
# Binary protocol round-trip
# ---------------------------------------------------------------------------

def test_binary_node_round_trip():
    node = bp.BinaryNode(
        tag="iq",
        attrs={"type": "get", "id": "abc123"},
        content=[
            bp.BinaryNode(tag="query", attrs={"xmlns": "jabber:iq:roster"}),
            bp.BinaryNode(tag="query", attrs={"xmlns": "jabber:iq:last"}),
        ],
    )
    encoded = bp.encode_binary_node(node)
    assert isinstance(encoded, bytes) and encoded[0] == 0  # leading compression flag

    # Decode (prepend the 0-byte if not already there)
    decoded = bp.decode_binary_node(encoded)
    assert decoded.tag == "iq"
    assert decoded.attrs["type"] == "get"
    assert decoded.attrs["id"] == "abc123"
    assert isinstance(decoded.content, list)
    assert len(decoded.content) == 2
    assert decoded.content[0].tag == "query"


def test_binary_with_jid_payload():
    node = bp.BinaryNode(
        tag="message",
        attrs={"to": "628123456789@s.whatsapp.net", "id": "MSG1"},
        content=b"hello",
    )
    encoded = bp.encode_binary_node(node)
    decoded = bp.decode_binary_node(encoded)
    assert decoded.tag == "message"
    assert decoded.attrs["to"] == "628123456789@s.whatsapp.net"
    assert isinstance(decoded.content, (bytes, bytearray))
    assert bytes(decoded.content) == b"hello"


# ---------------------------------------------------------------------------
# Crypto helpers
# ---------------------------------------------------------------------------

def test_curve25519_keypair_generation():
    kp = bp.generate_key_pair()
    assert len(kp.private) == 32
    assert len(kp.public) == 32


def test_curve25519_shared_key():
    a = bp.generate_key_pair()
    b = bp.generate_key_pair()
    s1 = bp.curve_shared_key(a.private, b.public)
    s2 = bp.curve_shared_key(b.private, a.public)
    assert s1 == s2
    assert len(s1) == 32


def test_hkdf_64():
    out = bp.hkdf(b"secret", 64, salt=b"salt", info=b"info")
    assert len(out) == 64


def test_aes_gcm_round_trip():
    key = bp.random_bytes(32)
    iv = bp.random_bytes(12)
    aad = b"some aad"
    pt = b"hello whatsapp"
    ct = bp.aes_encrypt_gcm(pt, key, iv, aad)
    assert ct != pt
    assert bp.aes_decrypt_gcm(ct, key, iv, aad) == pt


def test_aes_ctr_round_trip():
    key = bp.random_bytes(32)
    iv = bp.random_bytes(16)
    pt = b"hello whatsapp " * 4
    ct = bp.aes_encrypt_ctr(pt, key, iv)
    assert bp.aes_decrypt_ctr(ct, key, iv) == pt


# ---------------------------------------------------------------------------
# Noise handler
# ---------------------------------------------------------------------------

def test_noise_handshake_partial():
    client_kp = bp.generate_key_pair()
    noise_kp = bp.generate_key_pair()
    handler = bp.NoiseHandler(client_kp)
    # The very first encode should include the intro header
    frame = handler.encode_frame(b"hello")
    assert frame.startswith(b"WA")
    # Subsequent frames do not have the intro
    next_frame = handler.encode_frame(b"again")
    assert not next_frame.startswith(b"WA")


# ---------------------------------------------------------------------------
# Auth state persistence
# ---------------------------------------------------------------------------

def test_multi_file_auth_state_round_trip(tmp_path=None):
    folder = tmp_path or tempfile.mkdtemp(prefix="baileys-py-test-")

    async def run():
        state, save_creds = await bp.use_multi_file_auth_state(folder)
        assert state.creds.noise_key.private is not None
        assert state.creds.signed_identity_key.private is not None
        # Modify and save
        state.creds.adv_secret_key = "test_secret"
        await save_creds()
        # Reload
        state2, _ = await bp.use_multi_file_auth_state(folder)
        assert state2.creds.adv_secret_key == "test_secret"

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Socket construction
# ---------------------------------------------------------------------------

def test_make_socket_requires_auth():
    try:
        bp.make_wa_socket()
    except ValueError as exc:
        assert "auth" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing auth")


def test_make_socket_with_auth():
    async def run():
        folder = tempfile.mkdtemp(prefix="baileys-py-test-")
        state, _ = await bp.use_multi_file_auth_state(folder)
        sock = bp.make_wa_socket(auth=state)
        assert sock.ev is not None
        assert sock.config is not None
        assert sock.config.auth is not None
        # Quick event round-trip
        received = []
        sock.ev.on("connection.update", lambda d: received.append(d))
        sock.ev.emit("connection.update", {"connection": "open"})
        assert received == [{"connection": "open"}]

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Auto-reconnect + error handling (the "no close frame received or sent" fix)
# ---------------------------------------------------------------------------

def test_default_config_has_auto_reconnect():
    """Auto-reconnect is ON by default with sensible backoff."""
    from baileys_py import DEFAULT_CONNECTION_CONFIG
    assert DEFAULT_CONNECTION_CONFIG.auto_reconnect is True
    assert DEFAULT_CONNECTION_CONFIG.max_reconnect_attempts >= 1
    assert DEFAULT_CONNECTION_CONFIG.reconnect_delay_ms > 0
    assert DEFAULT_CONNECTION_CONFIG.reconnect_max_delay_ms >= DEFAULT_CONNECTION_CONFIG.reconnect_delay_ms
    assert DEFAULT_CONNECTION_CONFIG.reconnect_backoff_multiplier > 1.0


def test_classify_close_no_close_frame():
    """ConnectionClosedError (the 'no close frame received or sent' case)
    maps to connection_lost; ConnectionClosedOK maps to restart_required."""
    from baileys_py import DisconnectReason
    from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

    folder = tempfile.mkdtemp(prefix="baileys-py-test-")
    async def run():
        state, _ = await bp.use_multi_file_auth_state(folder)
        sock = bp.make_wa_socket(auth=state)
        # Abrupt close — the rcvd=None, sent=None case represents
        # "no close frame received or sent" (the exact error the user
        # reported).
        exc = ConnectionClosedError(rcvd=None, sent=None)
        status = sock._classify_close(exc)
        assert status == DisconnectReason.connection_lost.value, \
            f"expected connection_lost, got {status}"
        # Clean close — both frames present → restart_required.
        ok_exc = ConnectionClosedOK(rcvd=None, sent=None)
        assert sock._classify_close(ok_exc) == DisconnectReason.restart_required.value

    asyncio.run(run())


def test_maybe_schedule_reconnect_respects_intentional_disconnect():
    """If the user called disconnect(), auto-reconnect does NOT fire."""
    folder = tempfile.mkdtemp(prefix="baileys-py-test-")
    async def run():
        state, _ = await bp.use_multi_file_auth_state(folder)
        sock = bp.make_wa_socket(auth=state)
        await sock.disconnect()
        # _maybe_schedule_reconnect should be a no-op now
        sock._maybe_schedule_reconnect()
        assert sock._reconnect_task is None, "scheduled a reconnect despite disconnect()"

    asyncio.run(run())


def test_maybe_schedule_reconnect_disabled_via_config():
    folder = tempfile.mkdtemp(prefix="baileys-py-test-")
    async def run():
        state, _ = await bp.use_multi_file_auth_state(folder)
        sock = bp.make_wa_socket(auth=state, auto_reconnect=False)
        sock._maybe_schedule_reconnect()
        assert sock._reconnect_task is None, "scheduled a reconnect despite auto_reconnect=False"

    asyncio.run(run())


def test_maybe_schedule_reconnect_caps_attempts():
    folder = tempfile.mkdtemp(prefix="baileys-py-test-")
    async def run():
        state, _ = await bp.use_multi_file_auth_state(folder)
        sock = bp.make_wa_socket(auth=state, max_reconnect_attempts=2)
        sock._reconnect_attempts = 5  # already past the cap
        sock._maybe_schedule_reconnect()
        assert sock._reconnect_task is None, "scheduled a reconnect past the cap"

    asyncio.run(run())


def test_recv_loop_handles_connection_closed_error_gracefully():
    """The recv loop must NOT log "recv loop crashed" for a
    ConnectionClosedError — it should emit a clean close event and
    schedule a reconnect (unless auto_reconnect=False).
    """
    from websockets.exceptions import ConnectionClosedError

    folder = tempfile.mkdtemp(prefix="baileys-py-test-")
    async def run():
        state, _ = await bp.use_multi_file_auth_state(folder)
        sock = bp.make_wa_socket(auth=state, auto_reconnect=False)
        # Simulate a closed WS by setting _ws to a fake that raises
        # ConnectionClosedError on iteration.
        class _FakeWS:
            closed = True
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise ConnectionClosedError(rcvd=None, sent=None)

        sock._ws = _FakeWS()
        sock._noise = bp.NoiseHandler(bp.generate_key_pair())

        events = []
        sock.ev.on("connection.update", lambda d: events.append(d))

        await sock._recv_loop()

        # Expect a close event with last_disconnect metadata
        close_events = [e for e in events if e.get("connection") == "close"]
        assert close_events, f"expected a close event, got {events}"
        last = close_events[-1]
        assert "last_disconnect" in last, f"missing last_disconnect: {last}"
        assert "error" in last["last_disconnect"]
        assert "status" in last["last_disconnect"]
        # No reconnect scheduled (auto_reconnect=False)
        assert sock._reconnect_task is None

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def test_logger_emit():
    log = bp.Logger("test_logger", level="debug")
    log.info({"x": 1}, "hello")  # should not raise


# ---------------------------------------------------------------------------
# Allow running as a plain script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"\n{failed} failure(s)" if failed else "\nAll tests passed")
    sys.exit(1 if failed else 0)
