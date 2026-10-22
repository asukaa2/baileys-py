"""Default constants and the default socket configuration.

Mirrors ``src/Defaults/index.ts`` from upstream Baileys.
"""
from __future__ import annotations

from typing import List, Tuple

from .types import SocketConfig, WAVersion, WABrowserDescription

# WhatsApp Web version. Bumped periodically — see ``fetch_latest_baileys_version``.
DEFAULT_VERSION: WAVersion = (2, 3000, 1043857760)

# WebSocket endpoint used by WhatsApp Web.
WA_WEBSOCKET_URL = "wss://web.whatsapp.com/ws/chat"

DEFAULT_ORIGIN = "https://web.whatsapp.com"

CALL_VIDEO_PREFIX = "https://call.whatsapp.com/video/"
CALL_AUDIO_PREFIX = "https://call.whatsapp.com/voice/"

DEF_CALLBACK_PREFIX = "CB:"
DEF_TAG_PREFIX = "TAG:"
PHONE_CONNECTION_CB = "CB:Pong"

# ADV signature prefixes (bytes).
WA_ADV_ACCOUNT_SIG_PREFIX = bytes([6, 0])
WA_ADV_DEVICE_SIG_PREFIX = bytes([6, 1])
WA_ADV_HOSTED_ACCOUNT_SIG_PREFIX = bytes([6, 5])
WA_ADV_HOSTED_DEVICE_SIG_PREFIX = bytes([6, 6])

# Default ephemeral message lifetime (7 days).
WA_DEFAULT_EPHEMERAL = 7 * 24 * 60 * 60

# Status messages older than 24 hours are considered expired.
STATUS_EXPIRY_SECONDS = 24 * 60 * 60

# Noise XX handshake cipher suite used by WhatsApp.
NOISE_MODE = b"Noise_XX_25519_AESGCM_SHA256\x00\x00\x00\x00"

DICT_VERSION = 3
KEY_BUNDLE_TYPE = bytes([5])
NOISE_WA_HEADER = bytes([87, 65, 6, DICT_VERSION])  # "WA" + 6 + DICT_VERSION

# Default cache TTLs (seconds).
DEFAULT_CACHE_TTLS = {
    "SIGNAL_STORE": 5 * 60,
    "MSG_RETRY": 60 * 60,
    "CALL_OFFER": 5 * 60,
    "USER_DEVICES": 5 * 60,
}

# Pre-key maintenance.
MIN_PREKEY_COUNT = 5
INITIAL_PREKEY_COUNT = 812

UPLOAD_TIMEOUT = 30_000

UNAUTHORIZED_CODES = [401, 403, 419]

PROCESSABLE_HISTORY_TYPES = [
    "INITIAL_BOOTSTRAP",
    "PUSH_NAME",
    "RECENT",
    "FULL",
    "ON_DEMAND",
    "NON_BLOCKING_DATA",
    "INITIAL_STATUS_V3",
]

HISTORY_SYNC_PAUSED_TIMEOUT_MS = 120_000


def default_browser() -> WABrowserDescription:
    """Returns the default browser tuple: macOS Chrome."""
    return ("Chrome", "10.15.7", "0")


# The default connection config used when the user does not specify one.
DEFAULT_CONNECTION_CONFIG = SocketConfig(
    wa_websocket_url=WA_WEBSOCKET_URL,
    connect_timeout_ms=20_000,
    keep_alive_interval_ms=30_000,
    default_query_timeout_ms=60_000,
    version=DEFAULT_VERSION,
    browser=default_browser(),
    mark_online_on_connect=True,
    sync_full_history=False,
    fire_init_queries=True,
    emit_own_events=True,
    generate_high_quality_link_preview=False,
    retry_request_delay_ms=250,
    max_msg_retry_count=5,
    qr_timeout_ms=60_000,
    country_code="US",
)


# Media path mapping (used when uploading media files).
MEDIA_PATH_MAP = {
    "image": "/mms/image",
    "video": "/mms/video",
    "document": "/mms/document",
    "audio": "/mms/audio",
    "sticker": "/mms/image",
    "thumbnail-link": "/mms/image",
    "product-catalog-image": "/product/image",
    "md-app-state": "",
    "md-msg-hist": "/mms/md-app-state",
    "biz-cover-photo": "/pps/biz-cover-photo",
}

MEDIA_KEYS = list(MEDIA_PATH_MAP.keys())

MEDIA_HKDF_KEY_MAPPING = {
    "audio": "Audio",
    "document": "Document",
    "gif": "Video",
    "image": "Image",
    "ppic": "",
    "product": "Image",
    "ptt": "Audio",
    "sticker": "Image",
    "video": "Video",
    "thumbnail-document": "Document Thumbnail",
    "thumbnail-image": "Image Thumbnail",
    "thumbnail-video": "Video Thumbnail",
    "thumbnail-link": "Link Thumbnail",
    "md-msg-hist": "History",
    "md-app-state": "App State",
    "product-catalog-image": "",
    "payment-bg-image": "Payment Background",
    "ptv": "Video",
    "biz-cover-photo": "Image",
}


class TimeMs:
    Minute = 60 * 1000
    Hour = 60 * 60 * 1000
    Day = 24 * 60 * 60 * 1000
    Week = 7 * 24 * 60 * 60 * 1000


__all__ = [
    "DEFAULT_VERSION",
    "WA_WEBSOCKET_URL",
    "DEFAULT_ORIGIN",
    "DEFAULT_CONNECTION_CONFIG",
    "default_browser",
    "NOISE_MODE",
    "NOISE_WA_HEADER",
    "KEY_BUNDLE_TYPE",
    "DICT_VERSION",
    "WA_DEFAULT_EPHEMERAL",
    "WA_ADV_ACCOUNT_SIG_PREFIX",
    "WA_ADV_DEVICE_SIG_PREFIX",
    "WA_ADV_HOSTED_ACCOUNT_SIG_PREFIX",
    "WA_ADV_HOSTED_DEVICE_SIG_PREFIX",
    "DEF_CALLBACK_PREFIX",
    "DEF_TAG_PREFIX",
    "PHONE_CONNECTION_CB",
    "STATUS_EXPIRY_SECONDS",
    "DEFAULT_CACHE_TTLS",
    "MIN_PREKEY_COUNT",
    "INITIAL_PREKEY_COUNT",
    "UPLOAD_TIMEOUT",
    "UNAUTHORIZED_CODES",
    "PROCESSABLE_HISTORY_TYPES",
    "HISTORY_SYNC_PAUSED_TIMEOUT_MS",
    "MEDIA_PATH_MAP",
    "MEDIA_KEYS",
    "MEDIA_HKDF_KEY_MAPPING",
    "TimeMs",
    "CALL_VIDEO_PREFIX",
    "CALL_AUDIO_PREFIX",
]
