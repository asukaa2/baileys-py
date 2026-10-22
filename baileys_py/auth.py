"""Persistent authentication state — a Python port of
``src/Utils/use-multi-file-auth-state.ts`` and ``src/Utils/auth-utils.ts``.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .crypto import (
    generate_key_pair,
    generate_registration_id,
    random_bytes,
    signed_key_pair,
)
from .types import (
    AuthenticationCreds,
    AuthenticationState,
    KeyMaterial,
    SignalKeyStore,
    SignedKeyMaterial,
)


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

_BYTES_KEY = "__bytes__"
_KEY_PAIR_KEY = "__kp__"
_SIGNED_KP_KEY = "__skp__"


def _replacer(obj: Any) -> Any:
    """Recursively convert non-JSON-native types to tagged dicts."""
    if isinstance(obj, (bytes, bytearray)):
        return {_BYTES_KEY: base64.b64encode(bytes(obj)).decode("ascii")}
    if isinstance(obj, KeyMaterial):
        return {
            _KEY_PAIR_KEY: True,
            "private": base64.b64encode(obj.private).decode("ascii"),
            "public": base64.b64encode(obj.public).decode("ascii"),
        }
    if isinstance(obj, SignedKeyMaterial):
        return {
            _SIGNED_KP_KEY: True,
            "key_pair": _replacer(obj.key_pair),
            "signature": base64.b64encode(obj.signature).decode("ascii"),
            "key_id": obj.key_id,
            "timestamp_s": obj.timestamp_s,
        }
    if isinstance(obj, dict):
        return {k: _replacer(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replacer(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: _replacer(v) for k, v in asdict(obj).items()} \
            if hasattr(obj, "__dataclass_fields__") \
            else _replacer(obj.__dict__)
    return obj


def _reviver(obj: Any) -> Any:
    """Reverse of :func:`_replacer` — turn tagged dicts back into objects."""
    if isinstance(obj, dict):
        if _BYTES_KEY in obj:
            return base64.b64decode(obj[_BYTES_KEY])
        if obj.get(_KEY_PAIR_KEY):
            return KeyMaterial(
                private=base64.b64decode(obj["private"]),
                public=base64.b64decode(obj["public"]),
            )
        if obj.get(_SIGNED_KP_KEY):
            return SignedKeyMaterial(
                key_pair=_reviver(obj["key_pair"]),
                signature=base64.b64decode(obj["signature"]),
                key_id=obj["key_id"],
                timestamp_s=obj.get("timestamp_s"),
            )
        return {k: _reviver(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_reviver(v) for v in obj]
    return obj


def creds_to_dict(creds: AuthenticationCreds) -> dict:
    """Serialise :class:`AuthenticationCreds` to a JSON-safe dict."""
    d = _replacer(creds.__dict__)
    return d


def creds_from_dict(d: dict) -> AuthenticationCreds:
    """Deserialise a JSON dict back to :class:`AuthenticationCreds`."""
    revived = _reviver(d)
    # Reconstruct the AuthenticationCreds dataclass from the dict.
    if isinstance(revived.get("account_settings"), dict):
        from .types import AccountSettings
        revived["account_settings"] = AccountSettings(**revived["account_settings"])
    # SignalIdentities -> list of SignalIdentity; rebuild from dicts if needed
    if revived.get("signal_identities"):
        from .types import SignalIdentity, ProtocolAddress
        rebuilt = []
        for item in revived["signal_identities"]:
            if isinstance(item, SignalIdentity):
                rebuilt.append(item)
                continue
            rebuilt.append(SignalIdentity(
                identifier=ProtocolAddress(
                    name=item["identifier"]["name"],
                    device_id=item["identifier"]["device_id"],
                ),
                identifier_key=item["identifier_key"],
            ))
        revived["signal_identities"] = rebuilt
    return AuthenticationCreds(**revived)


# ---------------------------------------------------------------------------
# Credential initialisation
# ---------------------------------------------------------------------------

def init_auth_creds() -> AuthenticationCreds:
    """Generate a fresh :class:`AuthenticationCreds`.

    Port of ``initAuthCreds`` from upstream.
    """
    identity = generate_key_pair()
    return AuthenticationCreds(
        noise_key=generate_key_pair(),
        pairing_ephemeral_key_pair=generate_key_pair(),
        signed_identity_key=identity,
        signed_pre_key=signed_key_pair(identity.private, 1),
        registration_id=generate_registration_id(),
        adv_secret_key=base64.b64encode(random_bytes(32)).decode("ascii"),
        processed_history_messages=[],
        next_pre_key_id=1,
        first_unuploaded_pre_key_id=1,
        account_sync_counter=0,
        account_settings=__import__("baileys_py.types", fromlist=["AccountSettings"]).AccountSettings(),
        registered=False,
        pairing_code=None,
        last_prop_hash=None,
        routing_info=None,
        additional_data=None,
    )


# ---------------------------------------------------------------------------
# Multi-file auth state
# ---------------------------------------------------------------------------

def _fix_filename(name: str) -> str:
    return name.replace("/", "__").replace(":", "-")


class _MultiFileSignalKeyStore(SignalKeyStore):
    """A signal key store backed by individual JSON files in a folder."""

    def __init__(self, folder: str) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def get(self, type_: str, ids: List[str]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for _id in ids:
            fp = self.folder / _fix_filename(f"{type_}-{_id}.json")
            if fp.exists():
                try:
                    raw = fp.read_text(encoding="utf-8")
                    result[_id] = _reviver(json.loads(raw))
                except (OSError, json.JSONDecodeError):
                    result[_id] = None
            else:
                result[_id] = None
        return result

    async def set(self, data: Dict[str, Dict[str, Any]]) -> None:
        async with self._lock:
            for category, items in data.items():
                for _id, value in items.items():
                    fp = self.folder / _fix_filename(f"{category}-{_id}.json")
                    if value is None:
                        if fp.exists():
                            fp.unlink()
                    else:
                        fp.write_text(
                            json.dumps(_replacer(value), default=str),
                            encoding="utf-8",
                        )

    async def clear(self) -> None:
        async with self._lock:
            for fp in self.folder.glob("*.json"):
                fp.unlink()


async def use_multi_file_auth_state(folder: str) -> Tuple[AuthenticationState, Callable]:
    """Create or load a multi-file authentication state.

    Returns a tuple ``(state, save_creds)`` where ``save_creds`` is an
    async callable that persists the credentials back to disk.

    Usage::

        state, save_creds = await use_multi_file_auth_state("./auth_info")
        sock = make_wa_socket(auth=state, ...)

        @sock.ev.on("creds.update")
        async def on_creds(_):
            await save_creds()
    """
    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)

    creds_file = path / "creds.json"
    if creds_file.exists():
        raw = creds_file.read_text(encoding="utf-8")
        try:
            creds = creds_from_dict(json.loads(raw))
        except Exception:
            creds = init_auth_creds()
    else:
        creds = init_auth_creds()

    keys = _MultiFileSignalKeyStore(folder)

    async def save_creds() -> None:
        creds_file.write_text(
            json.dumps(creds_to_dict(creds), default=str),
            encoding="utf-8",
        )

    return AuthenticationState(creds=creds, keys=keys), save_creds


# ---------------------------------------------------------------------------
# Single-file auth state (convenience for tiny scripts)
# ---------------------------------------------------------------------------

class _SingleFileSignalKeyStore(SignalKeyStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}
        if path.exists():
            try:
                self._data = _reviver(json.loads(path.read_text("utf-8")))
            except Exception:
                self._data = {}

    async def get(self, type_: str, ids: List[str]) -> Dict[str, Any]:
        cat = self._data.get(type_, {})
        return {i: cat.get(i) for i in ids}

    async def set(self, data: Dict[str, Dict[str, Any]]) -> None:
        async with self._lock:
            for cat, items in data.items():
                self._data.setdefault(cat, {}).update(items)
                # Drop None entries
                self._data[cat] = {k: v for k, v in self._data[cat].items()
                                    if v is not None}
            self.path.write_text(json.dumps(_replacer(self._data), default=str),
                                  encoding="utf-8")

    async def clear(self) -> None:
        async with self._lock:
            self._data = {}
            self.path.write_text("{}", encoding="utf-8")


async def use_single_file_auth_state(file_path: str) -> Tuple[AuthenticationState, Callable]:
    """A simpler auth state that stores everything in a single JSON file."""
    path = Path(file_path)
    if path.exists():
        try:
            raw = json.loads(path.read_text("utf-8"))
            creds = creds_from_dict(raw.get("creds", {}))
        except Exception:
            creds = init_auth_creds()
    else:
        creds = init_auth_creds()
        path.write_text("{}", encoding="utf-8")

    keys = _SingleFileSignalKeyStore(path)

    async def save_creds() -> None:
        path.write_text(
            json.dumps(
                {"creds": creds_to_dict(creds), "keys": _replacer(keys._data)},
                default=str,
            ),
            encoding="utf-8",
        )

    return AuthenticationState(creds=creds, keys=keys), save_creds


__all__ = [
    "init_auth_creds",
    "use_multi_file_auth_state",
    "use_single_file_auth_state",
    "creds_to_dict",
    "creds_from_dict",
]
