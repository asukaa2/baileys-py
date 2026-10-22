"""A tiny structured logger that mirrors Baileys' ``pino`` based logger.

We do not depend on ``pino`` itself — we just expose ``debug/info/warn/
error/trace/fatal`` so any code that uses ``logger.debug(...)`` works.
If you want a real ``pino`` integration you can pass a compatible logger
via :class:`SocketConfig.logger`.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Optional


_LOG_LEVELS = {
    "fatal": logging.CRITICAL,
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "trace": 5,  # below DEBUG
}


class _BaileysLogger:
    """A minimal pino-style logger backed by ``logging``.

    Usage:
        >>> log = Logger.child({"class": "baileys"})
        >>> log.info({"event": "connected"}, "WS connected")
    """

    def __init__(self, name: str = "baileys", bindings: Optional[dict] = None,
                 level: str = "info"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(_LOG_LEVELS.get(level, logging.INFO))
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
            ))
            self._logger.addHandler(handler)
        self.bindings = bindings or {}
        self.level = level

    # ------------------------------------------------------------------
    # pino-style methods
    # ------------------------------------------------------------------
    def child(self, bindings: dict) -> "Logger":
        merged = {**self.bindings, **bindings}
        return Logger(self._logger.name, merged, self.level)

    def _emit(self, lvl: str, payload: Any, msg: str) -> None:
        binding_str = " ".join(f"{k}={v}" for k, v in self.bindings.items())
        prefix = f"[{binding_str}] " if binding_str else ""
        text = f"{prefix}{msg}"
        if payload:
            text += f" {payload!r}"
        self._logger.log(_LOG_LEVELS[lvl], text)

    def trace(self, payload: Any = None, msg: str = "") -> None:
        self._emit("trace", payload, msg)

    def debug(self, payload: Any = None, msg: str = "") -> None:
        self._emit("debug", payload, msg)

    def info(self, payload: Any = None, msg: str = "") -> None:
        self._emit("info", payload, msg)

    def warn(self, payload: Any = None, msg: str = "") -> None:
        self._emit("warn", payload, msg)

    def error(self, payload: Any = None, msg: str = "") -> None:
        self._emit("error", payload, msg)

    def fatal(self, payload: Any = None, msg: str = "") -> None:
        self._emit("fatal", payload, msg)


# Public alias that feels pino-like.
Logger = _BaileysLogger


def get_logger(name: str = "baileys", level: str = "info") -> Logger:
    return Logger(name=name, level=level)


__all__ = ["Logger", "get_logger"]
