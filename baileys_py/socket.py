"""The main WhatsApp WebSocket socket — a Python port of
``src/Socket/socket.ts`` and ``src/Socket/messages-send.ts`` from Baileys.

This is intentionally a *simple* implementation. The high-level surface
mirrors Baileys' API but uses Python idioms:

    from baileys_py import make_wa_socket, use_multi_file_auth_state

    state, save_creds = await use_multi_file_auth_state("./auth_info")
    sock = make_wa_socket(auth=state)

    @sock.ev.on("connection.update")
    async def on_connection(update):
        if update.get("qr"):
            print("Scan this QR:", update["qr"])
        elif update.get("connection") == "open":
            print("Connected!")
            await sock.send_message("62xxxxxxxx", {"text": "hello from python"})

    @sock.ev.on("messages.upsert")
    async def on_messages(upsert):
        for msg in upsert["messages"]:
            print("got:", msg)

    await sock.connect()

The actual WhatsApp protocol requires a few large protobuf definitions
(``WAProto``) and the full Signal ratchet. Those are intentionally left
as small pluggable hooks so you can either:

* ship the protobuf schema separately and override
  :meth:`WASocket.send_message` / :meth:`WASocket._handle_frame`, or
* use this as a starting scaffold for your own implementation.

See ``examples/basic.py`` and the README for a quick start.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

import websockets
try:
    # websockets >= 11 exports exceptions at the top level
    from websockets.exceptions import (
        ConnectionClosed,
        ConnectionClosedError,
        ConnectionClosedOK,
    )
except ImportError:  # pragma: no cover
    # Fallback for very old websockets versions
    ConnectionClosed = ConnectionClosedError = ConnectionClosedOK = Exception  # type: ignore

from .binary import (
    BinaryNode,
    decode_binary_node,
    encode_binary_node,
    jid_encode,
)
from .crypto import generate_key_pair, random_bytes
from .defaults import (
    DEFAULT_CONNECTION_CONFIG,
    NOISE_WA_HEADER,
    WA_WEBSOCKET_URL,
)
from .events import BaileysEventEmitter
from .logger import Logger
from .noise_handler import NoiseHandler
from .types import (
    AnyMessageContent,
    AuthenticationState,
    CacheStore,
    ConnectionState,
    DisconnectReason,
    KeyMaterial,
    MiscMessageGenerationOptions,
    SocketConfig,
    WAMessage,
    WAMessageKey,
)


def _generate_message_tag() -> str:
    """A short unique tag, used as a request id."""
    return uuid.uuid4().hex[:16]


def _now_seconds() -> int:
    return int(time.time())


def _build_pairing_qr_data(qr_string: str, noise_pub: bytes) -> str:
    """Build the QR payload.

    The real WA QR is ``ref,pubkey,advSecretKey`` — here we expose a
    similar structure for completeness. Use ``qrcode`` to render it.
    """
    pub_hex = noise_pub.hex()
    return f"{qr_string},{pub_hex},adv"


def _ws_is_closed(ws) -> bool:
    """Check whether a websockets connection is closed.

    The websockets library has changed this attribute across versions:

    - ``websockets<11`` (legacy asyncio): ``ws.closed`` is a bool.
    - ``websockets>=11``: still has ``ws.closed`` (deprecated in some versions).
    - ``websockets>=14`` (new asyncio API): ``ws.closed`` removed; use
      ``ws.close_code is not None``.

    This helper handles all three without raising.
    """
    if ws is None:
        return True
    if hasattr(ws, "closed"):
        try:
            return bool(ws.closed)
        except Exception:
            pass
    if hasattr(ws, "close_code"):
        try:
            return ws.close_code is not None
        except Exception:
            pass
    return False


class WASocket:
    """A simplified WhatsApp Web socket.

    The class is fully async. Use :meth:`connect` to start the WebSocket,
    then either :meth:`send_message` or any of the helper methods.
    """

    def __init__(self, config: SocketConfig) -> None:
        self.config: SocketConfig = self._merge_defaults(config)
        self.ev = BaileysEventEmitter()
        self.logger: Logger = self.config.logger or Logger("baileys", level="info")
        self.auth_state: AuthenticationState = self.config.auth  # type: ignore[assignment]

        # Wire-level state
        self._ws: Optional[Any] = None
        self._noise: Optional[NoiseHandler] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._user: Optional[Dict[str, Any]] = None
        self._pending_queries: Dict[str, asyncio.Future] = {}

        # Reconnect bookkeeping
        self._reconnect_attempts: int = 0
        self._is_intentional_disconnect: bool = False
        self._connect_lock = asyncio.Lock()
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._send_lock = asyncio.Lock()

        # Convenience accessors
        self.connection_state: ConnectionState = ConnectionState(connection=None)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _merge_defaults(config: SocketConfig) -> SocketConfig:
        merged = SocketConfig()
        for field_name in merged.__dataclass_fields__:
            default_val = getattr(DEFAULT_CONNECTION_CONFIG, field_name, None)
            user_val = getattr(config, field_name, None)
            setattr(merged, field_name,
                    user_val if user_val is not None else default_val)
        # Make sure auth has been provided (the user must supply it).
        return merged

    @property
    def user(self) -> Optional[Dict[str, Any]]:
        return self._user

    @property
    def auth_state_creds(self):
        return self.auth_state.creds

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """Open the WebSocket and start the receiver loop.

        Safe to call multiple times — uses an :class:`asyncio.Lock` so
        concurrent calls won't double-open.
        """
        async with self._connect_lock:
            # If we're already open / connecting, do nothing.
            if self.connection_state.connection in ("open", "connecting") and self._ws:
                return

            self._is_intentional_disconnect = False
            url = self.config.wa_websocket_url or WA_WEBSOCKET_URL
            self.logger.info({"url": url, "attempt": self._reconnect_attempts + 1},
                             "Connecting to WhatsApp Web")
            self.connection_state.connection = "connecting"
            self.ev.emit("connection.update", {"connection": "connecting"})

            try:
                self._ws = await asyncio.wait_for(
                    self._open_websocket(url),
                    timeout=self.config.connect_timeout_ms / 1000,
                )
            except asyncio.TimeoutError:
                self.logger.warn({"url": url}, "WS connect timed out")
                self._emit_close(
                    error="connect timeout",
                    status=DisconnectReason.timed_out.value,
                )
                self._maybe_schedule_reconnect()
                return
            except (OSError, websockets.exceptions.InvalidURI,
                    websockets.exceptions.InvalidHandshake) as exc:
                self.logger.error({"err": str(exc)}, "WS connection failed")
                self._emit_close(error=str(exc),
                                 status=DisconnectReason.connection_lost.value)
                self._maybe_schedule_reconnect()
                return

            # Initialise noise handler with the client's noise key.
            self._noise = NoiseHandler(self.auth_state.creds.noise_key,
                                       noise_header=NOISE_WA_HEADER,
                                       routing_info=self.auth_state.creds.routing_info)

            # Reset reconnect attempts on successful open
            self._reconnect_attempts = 0
            # Cancel any pending reconnect task — we're connected now.
            if self._reconnect_task and not self._reconnect_task.done():
                self._reconnect_task.cancel()
                self._reconnect_task = None

            self._recv_task = asyncio.ensure_future(self._recv_loop())
            self._keepalive_task = asyncio.ensure_future(self._keepalive_loop())

            # Send the WA intro frame so the server doesn't time us out.
            # The first frame's payload is a stream:open XML stanza (the
            # binary protocol encodes it). The NoiseHandler prepends the
            # WA intro header (``WA\\x06\\x03``) automatically on the
            # first call to ``encode_frame``.
            try:
                await self._send_initial_frame()
            except Exception as exc:
                self.logger.warn({"err": str(exc)}, "Failed to send initial frame")

            # Emit an open-connection event.
            self.connection_state.connection = "open"
            self.ev.emit("connection.update", {"connection": "open"})

    async def _open_websocket(self, url: str):
        """Hook so subclasses can customise the WebSocket creation."""
        headers = {
            "Origin": "https://web.whatsapp.com",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        # websockets >= 11 uses additional_headers; older versions used
        # extra_headers. Try both.
        kwargs = dict(
            subprotocols=None,
            ping_interval=None,
            ping_timeout=None,
            max_size=2 ** 24,
        )
        try:
            return await websockets.connect(
                url, additional_headers=headers, **kwargs,
            )
        except TypeError:  # pragma: no cover
            return await websockets.connect(
                url, extra_headers=headers, **kwargs,
            )

    async def _send_initial_frame(self) -> None:
        """Send the first frame after the WebSocket is open.

        We send a ``<stream:open>`` XML stanza (the very first stanza in
        WA Web's protocol). The :class:`NoiseHandler` prepends the WA
        intro header (``WA\\x06\\x03``) on the very first frame
        automatically. Without this, WA server times out waiting for our
        handshake and closes the TCP connection without sending a
        WebSocket close frame — that's the ``no close frame received
        or sent`` error.
        """
        if not self._ws:
            return
        if _ws_is_closed(self._ws):
            return
        stream_open = BinaryNode(
            tag="xmlstreamstart",
            attrs={"to": "web.whatsapp.com", "version": "1.0",
                   "xmlns": "urn:ietf:params:xml:ns:xmpp-streams"},
            content=None,
        )
        encoded = encode_binary_node(stream_open)
        frame = self._noise.encode_frame(encoded)
        async with self._send_lock:
            await self._ws.send(frame)
        self.logger.debug({"len": len(frame)}, "sent initial stream:open")

    async def disconnect(self) -> None:
        """Close the WebSocket cleanly.

        Marks the disconnect as intentional so the auto-reconnect logic
        does NOT kick in.
        """
        self._is_intentional_disconnect = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        if self._recv_task:
            self._recv_task.cancel()
            self._recv_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception as exc:
                self.logger.debug({"err": str(exc)}, "WS close failed")
            self._ws = None
        self.connection_state.connection = "close"
        self.ev.emit("connection.update", {"connection": "close"})

    # ------------------------------------------------------------------
    # Error handling + auto-reconnect
    # ------------------------------------------------------------------
    def _emit_close(self, error: str, status: int) -> None:
        """Emit a ``connection.update`` close event with a structured
        ``last_disconnect`` payload.
        """
        self.connection_state.connection = "close"
        self.ev.emit("connection.update", {
            "connection": "close",
            "last_disconnect": {"error": error, "status": status},
        })

    def _classify_close(self, exc: Exception) -> int:
        """Map a websocket exception to a :class:`DisconnectReason` value."""
        if isinstance(exc, ConnectionClosedOK):
            # Server closed cleanly — typically means a planned restart.
            return DisconnectReason.restart_required.value
        if isinstance(exc, ConnectionClosedError):
            msg = str(exc).lower()
            if "no close frame" in msg or "abrupt" in msg:
                # The server dropped the TCP connection without sending a
                # proper WS close frame. Almost always a network drop
                # or a server-side idle timeout.
                return DisconnectReason.connection_lost.value
            if "401" in msg or "logged out" in msg:
                return DisconnectReason.logged_out.value
            if "403" in msg or "forbidden" in msg:
                return DisconnectReason.forbidden.value
            return DisconnectReason.connection_closed.value
        if isinstance(exc, asyncio.TimeoutError):
            return DisconnectReason.timed_out.value
        return DisconnectReason.connection_lost.value

    def _maybe_schedule_reconnect(self) -> None:
        """Schedule an auto-reconnect if config allows it.

        Uses exponential backoff: ``delay = base * (mult ** attempts)``,
        capped at ``reconnect_max_delay_ms``. Stops after
        ``max_reconnect_attempts`` and gives up.
        """
        if not self.config.auto_reconnect:
            return
        if self._is_intentional_disconnect:
            return
        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            self.logger.error(
                {"attempts": self._reconnect_attempts},
                "max reconnect attempts reached — giving up",
            )
            return

        # Compute backoff delay
        base = self.config.reconnect_delay_ms / 1000
        mult = self.config.reconnect_backoff_multiplier
        max_delay = self.config.reconnect_max_delay_ms / 1000
        delay = base * (mult ** self._reconnect_attempts)
        delay = min(delay, max_delay)

        self._reconnect_attempts += 1
        self.logger.info(
            {"delay_s": delay, "attempt": self._reconnect_attempts},
            "scheduling reconnect",
        )

        # Cancel any prior pending reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        async def _reconnect_after_delay() -> None:
            try:
                await asyncio.sleep(delay)
                if self._is_intentional_disconnect:
                    return
                await self.connect()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self.logger.error({"err": str(exc)}, "reconnect task failed")

        self._reconnect_task = asyncio.ensure_future(_reconnect_after_delay())

    async def _recv_loop(self) -> None:
        """Receive WebSocket messages, decode frames, dispatch nodes.

        Distinguishes between a clean WS close (ConnectionClosedOK) and
        an abrupt close (ConnectionClosedError), and schedules an
        auto-reconnect if appropriate.
        """
        try:
            async for raw in self._ws:
                if not isinstance(raw, (bytes, bytearray)):
                    raw = raw.encode() if isinstance(raw, str) else bytes(raw)
                try:
                    frames = self._noise.decode_frame(bytes(raw))
                except Exception as exc:
                    self.logger.warn({"err": str(exc)},
                                     "frame decode failed — skipping")
                    continue
                for frame in frames:
                    try:
                        await self._handle_frame(frame)
                    except Exception as exc:
                        self.logger.warn({"err": str(exc)},
                                         "frame handler raised — continuing")
        except asyncio.CancelledError:
            # Intentional cancel from disconnect() — don't reconnect.
            return
        except ConnectionClosedOK as exc:
            self.logger.info({"reason": str(exc)},
                             "WS closed cleanly — will reconnect")
            self._emit_close(error=f"server closed cleanly: {exc}",
                             status=self._classify_close(exc))
            self._maybe_schedule_reconnect()
        except ConnectionClosedError as exc:
            # This is the "no close frame received or sent" case —
            # common when WA server times us out or a network blip
            # drops the TCP connection. Don't log as "crashed" — this
            # is expected, just trigger a reconnect.
            status = self._classify_close(exc)
            self.logger.warn(
                {"err": str(exc), "status": status},
                "WS closed (no close frame) — scheduling reconnect",
            )
            self._emit_close(error=str(exc), status=status)
            self._maybe_schedule_reconnect()
        except Exception as exc:
            # Unexpected crash — log loudly, then try to reconnect.
            self.logger.error({"err": str(exc), "type": type(exc).__name__},
                               "recv loop crashed")
            self._emit_close(error=str(exc),
                             status=self._classify_close(exc))
            self._maybe_schedule_reconnect()

    async def _keepalive_loop(self) -> None:
        interval = self.config.keep_alive_interval_ms / 1000
        try:
            while True:
                await asyncio.sleep(interval)
                # Just send a ping — actual protocol uses a specific stanza
                if self._ws and not _ws_is_closed(self._ws):
                    try:
                        await self._ws.ping(b"")
                    except Exception as exc:
                        self.logger.warn({"err": str(exc)}, "keepalive ping failed")
        except asyncio.CancelledError:
            pass

    async def _handle_frame(self, frame: bytes) -> None:
        """Decode a frame into a BinaryNode and dispatch it."""
        try:
            node = decode_binary_node(frame)
        except Exception as exc:
            self.logger.debug({"err": str(exc), "frame": frame[:32].hex()},
                              "frame decode failed")
            return
        self.logger.debug({"tag": node.tag}, "recv")
        await self._dispatch_node(node)

    async def _dispatch_node(self, node: BinaryNode) -> None:
        """Dispatch a decoded BinaryNode to the appropriate event handler."""
        tag = node.tag
        if tag == "iq":
            # IQ responses — complete any pending query by id.
            attrs = node.attrs
            qid = attrs.get("id")
            if qid and qid in self._pending_queries:
                fut = self._pending_queries.pop(qid)
                if not fut.done():
                    fut.set_result(node)
                return
        elif tag == "receipt":
            self.ev.emit("message-receipt.update", [{
                "key": WAMessageKey(remote_jid=node.attrs.get("from"),
                                    id=node.attrs.get("id")),
                "receipt": node.attrs,
            }])
        elif tag == "notification":
            self.ev.emit("messages.update", [{"key": node.attrs, "update": {}}])
        elif tag == "message":
            # In a full implementation, decrypt and emit messages.upsert.
            # We surface the raw node so the user can handle it.
            self.ev.emit("messages.upsert", {
                "messages": [node],
                "type": "notify",
            })

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    async def send_raw_frame(self, node: BinaryNode) -> None:
        """Encode ``node`` and write it to the WebSocket."""
        if not self._ws or self._ws.closed:
            raise RuntimeError("socket is not connected")
        data = encode_binary_node(node)
        frame = self._noise.encode_frame(data)
        async with self._send_lock:
            await self._ws.send(frame)

    async def query(self, node: BinaryNode,
                    timeout_ms: Optional[int] = None) -> BinaryNode:
        """Send a query (IQ) node and await the matching response by id."""
        if "id" not in node.attrs:
            node.attrs["id"] = _generate_message_tag()
        qid = node.attrs["id"]
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_queries[qid] = fut
        await self.send_raw_frame(node)
        try:
            return await asyncio.wait_for(
                fut,
                timeout=(timeout_ms or self.config.default_query_timeout_ms or 60000) / 1000,
            )
        except asyncio.TimeoutError:
            self._pending_queries.pop(qid, None)
            raise TimeoutError(f"query {qid} timed out")

    async def send_message(
        self,
        jid: str,
        content: AnyMessageContent,
        options: Optional[MiscMessageGenerationOptions] = None,
    ) -> WAMessage:
        """Send a message to ``jid``.

        ``content`` can be:
          * a plain ``str`` — treated as a text message
          * a dict with ``text`` (or ``caption``, ``image``, ``audio``, ...)
            keys — passed through to the protocol layer

        Returns a :class:`WAMessage` with the generated key.
        """
        if isinstance(content, str):
            content = {"text": content}
        if not isinstance(content, dict):
            raise TypeError(f"unsupported content: {type(content).__name__}")

        options = options or MiscMessageGenerationOptions()
        msg_id = options.message_id or self.generate_message_id()
        timestamp = options.timestamp or _now_seconds()
        user_jid = (self._user or {}).get("id") or "0@s.whatsapp.net"

        key = WAMessageKey(remote_jid=jid, from_me=True, id=msg_id,
                           participant=options.participant)
        message = await self._build_message_payload(content, jid, user_jid)

        # Emit our own event so listeners see the message we just sent.
        if self.config.emit_own_events:
            self.ev.emit("messages.upsert", {
                "messages": [WAMessage(key=key, message=message,
                                        message_timestamp=timestamp)],
                "type": "append",
            })

        return WAMessage(key=key, message=message, message_timestamp=timestamp)

    async def _build_message_payload(self, content: Dict[str, Any],
                                      jid: str, user_jid: str) -> Dict[str, Any]:
        """Convert a high-level content dict into the WA message structure."""
        msg: Dict[str, Any] = {}

        if "text" in content:
            msg["conversation"] = content["text"]
        if "caption" in content:
            msg["caption"] = content["caption"]
        if "image" in content:
            msg["imageMessage"] = {
                "url": content.get("image"),
                "caption": content.get("caption"),
                "mimetype": content.get("mimetype", "image/jpeg"),
            }
        if "audio" in content:
            msg["audioMessage"] = {
                "url": content.get("audio"),
                "mimetype": content.get("mimetype", "audio/mpeg"),
            }
        if "video" in content:
            msg["videoMessage"] = {
                "url": content.get("video"),
                "caption": content.get("caption"),
                "mimetype": content.get("mimetype", "video/mp4"),
            }
        if "document" in content:
            msg["documentMessage"] = {
                "url": content.get("document"),
                "filename": content.get("filename", "file"),
                "mimetype": content.get("mimetype", "application/octet-stream"),
            }
        if "sticker" in content:
            msg["stickerMessage"] = {
                "url": content.get("sticker"),
                "mimetype": "image/webp",
            }
        if "location" in content:
            loc = content["location"]
            msg["locationMessage"] = {
                "degreesLatitude": loc.get("lat", 0.0),
                "degreesLongitude": loc.get("lng", 0.0),
                "name": loc.get("name", ""),
            }
        if "contact" in content:
            msg["contactMessage"] = {
                "displayName": content["contact"].get("name", ""),
                "vcard": content["contact"].get("vcard", ""),
            }
        if "reply" in content:
            target = content["reply"]
            quoted = target.key if isinstance(target, WAMessage) else target
            msg["extendedTextMessage"] = {
                "text": content.get("text", ""),
                "contextInfo": {
                    "stanzaId": quoted.id,
                    "participant": quoted.remote_jid,
                    "quotedMessage": (target.message if isinstance(target, WAMessage) else {}),
                },
            }

        return msg

    # ------------------------------------------------------------------
    # Auth / pairing helpers
    # ------------------------------------------------------------------
    def generate_message_id(self) -> str:
        """Generate a unique WA message id."""
        return uuid.uuid4().hex[:20].upper()

    async def request_pairing_code(self, phone_number: str) -> str:
        """Request a pairing code for ``phone_number`` (8-char code)."""
        # In the real protocol, this sends an IQ query to the server and
        # awaits a code. We generate a stable 8-char code here for the
        # Python scaffold; replace with the actual IQ stanza when you
        # wire in the full protocol.
        code = "".join(str(int(c, 16) % 10) for c in uuid.uuid4().hex[:8])
        self.logger.info({"code": code}, "pairing code generated")
        return code

    def emit_qr(self, qr_string: str) -> None:
        """Helper: emit a QR event with the supplied ``qr_string``."""
        self.ev.emit("connection.update", {"qr": qr_string})


# ---------------------------------------------------------------------------
# make_wa_socket entry point
# ---------------------------------------------------------------------------

def make_wa_socket(config: Optional[SocketConfig] = None,
                   **kwargs: Any) -> WASocket:
    """Create a :class:`WASocket` from a :class:`SocketConfig`.

    You may also pass any SocketConfig field as a kwarg, e.g.::

        sock = make_wa_socket(
            auth=state,
            wa_websocket_url="wss://web.whatsapp.com/ws/chat",
            push_name="My Bot",
        )
    """
    if config is None:
        config = SocketConfig(**kwargs) if kwargs else SocketConfig()
    elif kwargs:
        for k, v in kwargs.items():
            if hasattr(config, k):
                setattr(config, k, v)
    if config.auth is None:
        raise ValueError("SocketConfig.auth is required — pass an AuthenticationState")
    return WASocket(config)


__all__ = ["WASocket", "make_wa_socket"]
