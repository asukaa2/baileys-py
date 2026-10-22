"""baileys-py: a simple Pythonic port of the Baileys WhatsApp Web API.

Public API — drop-in for the most common Baileys use cases:

    from baileys_py import (
        make_wa_socket,
        use_multi_file_auth_state,
        DisconnectReason,
    )

Quick start::

    import asyncio
    from baileys_py import make_wa_socket, use_multi_file_auth_state

    async def main():
        state, save_creds = await use_multi_file_auth_state("./auth_info")
        sock = make_wa_socket(auth=state)

        @sock.ev.on("connection.update")
        async def on_conn(update):
            if update.get("qr"):
                print("QR:", update["qr"])
            if update.get("connection") == "open":
                await sock.send_message("62xxxxxxxx", "hello from python")

        @sock.ev.on("messages.upsert")
        async def on_msg(upsert):
            for msg in upsert["messages"]:
                print("received:", msg)

        @sock.ev.on("creds.update")
        async def on_creds(_):
            await save_creds()

        await sock.connect()

    asyncio.run(main())

See ``examples/`` for more usage patterns.
"""
from __future__ import annotations

from .auth import (
    creds_from_dict,
    creds_to_dict,
    init_auth_creds,
    use_multi_file_auth_state,
    use_single_file_auth_state,
)
from .binary import (
    BinaryNode,
    assert_node_error_free,
    binary_node_to_string,
    decode_binary_node,
    decode_decompressed_binary_node,
    decompress_if_required,
    encode_binary_node,
    get_all_binary_node_children,
    get_binary_node_child,
    get_binary_node_child_buffer,
    get_binary_node_child_string,
    get_binary_node_child_uint,
    get_binary_node_children,
    is_jid_broadcast,
    is_jid_bot,
    is_jid_group,
    is_jid_meta_ai,
    is_jid_newsletter,
    is_jid_status_broadcast,
    is_hosted_lid_user,
    is_hosted_pn_user,
    is_lid_user,
    is_pn_user,
    jid_decode,
    jid_encode,
    jid_normalized_user,
    reduce_binary_node_to_dictionary,
    transfer_device,
)
from .crypto import (
    aes_decrypt,
    aes_decrypt_ctr,
    aes_decrypt_gcm,
    aes_encrypt,
    aes_encrypt_ctr,
    aes_encrypt_gcm,
    curve_shared_key,
    curve_sign,
    curve_verify,
    generate_key_pair,
    generate_registration_id,
    generate_signal_pub_key,
    hkdf,
    hmac_sign,
    hmac_verify,
    md5,
    random_bytes,
    sha256,
    signed_key_pair,
)
from .defaults import (
    DEFAULT_CONNECTION_CONFIG,
    DEFAULT_ORIGIN,
    DEFAULT_VERSION,
    KEY_BUNDLE_TYPE,
    NOISE_WA_HEADER,
    NOISE_MODE,
    TimeMs,
    WA_DEFAULT_EPHEMERAL,
    WA_WEBSOCKET_URL,
    default_browser,
)
from .events import BaileysEventEmitter
from .logger import Logger, get_logger
from .messages import (
    chat_archive,
    chat_mark_read,
    chat_pin,
    chat_send_message,
    get_profile_picture_url,
    group_create,
    group_invite_code,
    group_join,
    group_leave,
    group_participants_update,
    send_presence_update,
    update_profile_name,
    update_profile_status,
)
from .noise_handler import NoiseHandler
from .socket import WASocket, make_wa_socket
from .types import (
    AnyMessageContent,
    AuthenticationCreds,
    AuthenticationState,
    CacheStore,
    ConnectionState,
    DisconnectReason,
    KeyMaterial,
    MediaConnInfo,
    MessageUpsertType,
    MiscMessageGenerationOptions,
    ProtocolAddress,
    SignalIdentity,
    SignalKeyStore,
    SocketConfig,
    WAVersion,
    WABrowserDescription,
    WAMessage,
    WAMessageKey,
)
from .utils import (
    delay_ms,
    fetch_latest_baileys_version,
    generate_message_id_v2,
    generate_message_tag,
    get_aggregate_votes_in_poll_message,
    get_call_link,
    is_jid_broadcast_,
    is_jid_group_,
    is_jid_newsletter_,
    promise_timeout,
    unix_timestamp_seconds,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # socket
    "WASocket", "make_wa_socket",
    # auth
    "init_auth_creds", "use_multi_file_auth_state", "use_single_file_auth_state",
    "creds_to_dict", "creds_from_dict",
    # types
    "SocketConfig", "AuthenticationCreds", "AuthenticationState",
    "SignalKeyStore", "CacheStore", "KeyMaterial",
    "SignalIdentity", "ProtocolAddress",
    "WAMessage", "WAMessageKey", "AnyMessageContent",
    "MiscMessageGenerationOptions", "ConnectionState",
    "DisconnectReason", "MessageUpsertType", "MediaConnInfo",
    "WAVersion", "WABrowserDescription",
    # binary
    "BinaryNode",
    "encode_binary_node", "decode_binary_node",
    "decode_decompressed_binary_node", "decompress_if_required",
    "get_binary_node_child", "get_binary_node_children",
    "get_binary_node_child_buffer", "get_binary_node_child_string",
    "get_binary_node_child_uint", "get_all_binary_node_children",
    "reduce_binary_node_to_dictionary", "assert_node_error_free",
    "binary_node_to_string",
    "jid_decode", "jid_encode", "jid_normalized_user",
    "is_jid_group", "is_jid_broadcast", "is_jid_newsletter",
    "is_jid_status_broadcast", "is_jid_bot", "is_jid_meta_ai",
    "is_lid_user", "is_pn_user", "is_hosted_pn_user", "is_hosted_lid_user",
    "transfer_device",
    # crypto
    "generate_key_pair", "curve_shared_key", "curve_sign", "curve_verify",
    "generate_signal_pub_key", "signed_key_pair", "generate_registration_id",
    "hkdf", "hmac_sign", "hmac_verify", "sha256", "md5", "random_bytes",
    "aes_encrypt_gcm", "aes_decrypt_gcm",
    "aes_encrypt_ctr", "aes_decrypt_ctr",
    "aes_encrypt", "aes_decrypt",
    # defaults
    "DEFAULT_CONNECTION_CONFIG", "DEFAULT_ORIGIN", "DEFAULT_VERSION",
    "WA_WEBSOCKET_URL", "WA_DEFAULT_EPHEMERAL",
    "NOISE_MODE", "NOISE_WA_HEADER", "KEY_BUNDLE_TYPE", "TimeMs", "default_browser",
    # events / logger
    "BaileysEventEmitter", "Logger", "get_logger",
    # noise
    "NoiseHandler",
    # messages helpers
    "chat_send_message", "chat_archive", "chat_pin", "chat_mark_read",
    "group_create", "group_invite_code", "group_join", "group_leave",
    "group_participants_update",
    "send_presence_update",
    "get_profile_picture_url", "update_profile_name", "update_profile_status",
    # utils
    "generate_message_id_v2", "generate_message_tag",
    "unix_timestamp_seconds", "fetch_latest_baileys_version",
    "get_aggregate_votes_in_poll_message", "promise_timeout", "delay_ms",
    "get_call_link",
    "is_jid_broadcast_", "is_jid_group_", "is_jid_newsletter_",
]
