"""Core data types for the baileys-py package.

These mirror the TypeScript types exported from ``src/Types/`` in the
upstream Baileys project, but rewritten as plain ``dataclasses`` and
``typing`` aliases so they feel natural to Python users.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Crypto / key types
# ---------------------------------------------------------------------------

KeyPair = bytes  # 32-byte private key

#: A pair of (private, public) curve25519 keys, both 32 bytes.
@dataclass
class KeyMaterial:
    private: bytes
    public: bytes


@dataclass
class SignedKeyMaterial:
    key_pair: KeyMaterial
    signature: bytes
    key_id: int
    timestamp_s: Optional[int] = None


@dataclass
class ProtocolAddress:
    name: str  # jid
    device_id: int


@dataclass
class SignalIdentity:
    identifier: ProtocolAddress
    identifier_key: bytes


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@dataclass
class AccountSettings:
    unarchive_chats: bool = False
    default_disappearing_mode: Optional[Dict[str, Any]] = None


@dataclass
class AuthenticationCreds:
    """Persistent WhatsApp Web credentials.

    All keys are stored as raw bytes / base64 strings. They are
    serialized to JSON via :func:`baileys_py.auth.use_multi_file_auth_state`.
    """
    noise_key: KeyMaterial
    pairing_ephemeral_key_pair: KeyMaterial
    signed_identity_key: KeyMaterial
    signed_pre_key: SignedKeyMaterial
    registration_id: int
    adv_secret_key: str
    me: Optional[Dict[str, Any]] = None
    account: Optional[bytes] = None
    signal_identities: Optional[List[SignalIdentity]] = None
    my_app_state_key_id: Optional[str] = None
    first_unuploaded_pre_key_id: int = 1
    next_pre_key_id: int = 1
    last_account_sync_timestamp: Optional[int] = None
    platform: Optional[str] = None
    processed_history_messages: List[Any] = field(default_factory=list)
    account_sync_counter: int = 0
    account_settings: AccountSettings = field(default_factory=AccountSettings)
    registered: bool = False
    pairing_code: Optional[str] = None
    last_prop_hash: Optional[str] = None
    routing_info: Optional[bytes] = None
    additional_data: Optional[Any] = None


@dataclass
class AuthenticationState:
    creds: AuthenticationCreds
    keys: "SignalKeyStore"


# Signal key store interface -------------------------------------------------

SignalDataTypeMap = Dict[str, Any]


class SignalKeyStore:
    """Interface for a persistent signal-key store.

    Implementations should make ``get`` and ``set`` async-safe.
    """

    async def get(self, type_: str, ids: List[str]) -> Dict[str, Any]:
        raise NotImplementedError

    async def set(self, data: Dict[str, Dict[str, Any]]) -> None:
        raise NotImplementedError

    async def clear(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Connection / socket config
# ---------------------------------------------------------------------------

WAVersion = Tuple[int, int, int]
WABrowserDescription = Tuple[str, str, str]

#: A simple cache store interface (mirrors ``CacheStore`` from upstream).
class CacheStore:
    async def get(self, key: str) -> Any: ...
    async def set(self, key: str, value: Any) -> None: ...
    async def del_(self, key: str) -> None: ...
    async def flush_all(self) -> None: ...


@dataclass
class SocketConfig:
    """User-facing socket configuration.

    Only a handful of options are exposed to keep the API simple.
    Anything not set here falls back to :data:`DEFAULT_CONNECTION_CONFIG`.
    """
    wa_websocket_url: Optional[str] = None
    connect_timeout_ms: int = 20_000
    keep_alive_interval_ms: int = 30_000
    default_query_timeout_ms: Optional[int] = 60_000
    version: Optional[WAVersion] = None
    browser: Optional[WABrowserDescription] = None
    push_name: Optional[str] = None
    mark_online_on_connect: bool = True
    sync_full_history: bool = False
    fire_init_queries: bool = True
    emit_own_events: bool = True
    generate_high_quality_link_preview: bool = False
    retry_request_delay_ms: int = 250
    max_msg_retry_count: int = 5
    qr_timeout_ms: Optional[int] = 60_000
    country_code: str = "US"
    agent: Any = None
    fetch_agent: Any = None
    auth: Optional[AuthenticationState] = None
    logger: Any = None
    media_cache: Optional[CacheStore] = None
    msg_retry_counter_cache: Optional[CacheStore] = None
    user_devices_cache: Optional[CacheStore] = None
    get_message: Optional[Callable[["WAMessageKey"], Awaitable[Any]]] = None
    cached_group_metadata: Optional[Callable[[str], Awaitable[Any]]] = None
    should_ignore_jid: Optional[Callable[[str], bool]] = None
    patch_message_before_sending: Optional[Callable[[Any, Any], Any]] = None


# ---------------------------------------------------------------------------
# Message / JID / chat types
# ---------------------------------------------------------------------------

@dataclass
class WAMessageKey:
    remote_jid: Optional[str] = None
    from_me: Optional[bool] = None
    id: Optional[str] = None
    participant: Optional[str] = None


@dataclass
class WAMessage:
    key: WAMessageKey
    message: Optional[Dict[str, Any]] = None
    message_timestamp: Optional[int] = None
    status: Optional[int] = None
    participant: Optional[str] = None
    push_name: Optional[str] = None


#: Anything that can be passed to ``send_message`` as content.
AnyMessageContent = Union[str, Dict[str, Any]]


@dataclass
class MiscMessageGenerationOptions:
    message_id: Optional[str] = None
    quoted: Optional[WAMessage] = None
    timestamp: Optional[int] = None
    participant: Optional[str] = None
    use_cached_group_metadata: bool = False


@dataclass
class ConnectionState:
    connection: Optional[str] = None  # "open" | "connecting" | "close"
    last_disconnect: Optional[Dict[str, Any]] = None
    qr: Optional[str] = None
    received_pending_notifications: Optional[bool] = None
    is_online: Optional[bool] = None
    user: Optional[Dict[str, Any]] = None


class DisconnectReason(Enum):
    """Reasons for a connection close, mirroring upstream's enum."""
    connection_closed = 410
    connection_lost = 428
    connection_replaced = 440
    timed_out = 408
    restart_required = 415
    multidevice_mismatch = 401
    logged_out = 401
    forbidden = 403


# ---------------------------------------------------------------------------
# Convenience enums
# ---------------------------------------------------------------------------

class MessageUpsertType(str, Enum):
    notify = "notify"
    append = "append"


class MediaConnInfo:
    def __init__(self, hosts: Optional[List[Any]] = None, auth: Optional[str] = None,
                 ttl: Optional[int] = None, fetched_at: Optional[int] = None):
        self.hosts = hosts or []
        self.auth = auth
        self.ttl = ttl
        self.fetched_at = fetched_at


__all__ = [
    "KeyMaterial",
    "SignedKeyMaterial",
    "ProtocolAddress",
    "SignalIdentity",
    "AccountSettings",
    "AuthenticationCreds",
    "AuthenticationState",
    "SignalKeyStore",
    "SocketConfig",
    "WAVersion",
    "WABrowserDescription",
    "CacheStore",
    "WAMessageKey",
    "WAMessage",
    "AnyMessageContent",
    "MiscMessageGenerationOptions",
    "ConnectionState",
    "DisconnectReason",
    "MessageUpsertType",
    "MediaConnInfo",
]
