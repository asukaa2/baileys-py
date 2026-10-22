"""A small async-friendly event emitter mirroring Baileys' ``BaileysEventEmitter``.

Usage::

    ev = BaileysEventEmitter()
    ev.on('connection.update', lambda update: ...)
    ev.emit('connection.update', {'connection': 'open'})

There is also an :meth:`process` helper that mirrors Baileys' batch
processing style::

    async def handle(events):
        if events.get('connection.update'): ...
        if events.get('messages.upsert'): ...
    ev.process(handle)
"""
from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

Listener = Callable[[Any], Union[None, Awaitable[None]]]


class BaileysEventEmitter:
    def __init__(self) -> None:
        self._listeners: Dict[str, List[Listener]] = defaultdict(list)
        self._buffer: Dict[str, Any] = {}
        self._processor: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

    def on(self, event: str, listener: Listener) -> Listener:
        self._listeners[event].append(listener)
        return listener

    def off(self, event: str, listener: Listener) -> None:
        if listener in self._listeners.get(event, []):
            self._listeners[event].remove(listener)

    def remove_all_listeners(self, event: Optional[str] = None) -> None:
        if event is None:
            self._listeners.clear()
        else:
            self._listeners.pop(event, None)

    def emit(self, event: str, arg: Any) -> bool:
        """Emit ``arg`` to all listeners for ``event``.

        If a buffered processor is registered (via :meth:`process`),
        events are accumulated into the processor's batch and flushed
        in a single ``await`` call instead of being dispatched one-by-one.

        Listeners that return awaitables are scheduled on the event loop
        so ``emit`` itself never blocks.
        """
        if self._processor is not None:
            self._buffer[event] = arg
            return True
        listeners = self._listeners.get(event, [])
        for fn in listeners:
            self._invoke(fn, arg)
        return bool(listeners)

    def process(self, processor: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """Register a single batch processor.

        While a processor is registered, all :meth:`emit` calls accumulate
        into a buffer. The processor is invoked asynchronously when
        :meth:`flush` is called (or after each emit, via a queued task).
        """
        self._processor = processor
        # Spawn a task that drains the buffer whenever events come in.
        if not hasattr(self, "_drain_task"):
            self._drain_task = asyncio.ensure_future(self._drain_loop())

    async def _drain_loop(self) -> None:
        while True:
            await asyncio.sleep(0)
            if self._buffer:
                await self.flush()

    async def flush(self) -> None:
        if not self._buffer or self._processor is None:
            return
        snapshot, self._buffer = self._buffer, {}
        await self._processor(snapshot)

    def stop_processing(self) -> None:
        if getattr(self, "_drain_task", None):
            self._drain_task.cancel()
            self._drain_task = None
        self._processor = None

    @staticmethod
    def _invoke(fn: Listener, arg: Any) -> None:
        try:
            res = fn(arg)
            if inspect.isawaitable(res):
                asyncio.ensure_future(res)
        except Exception:
            # Listeners should never crash the emitter. Surface errors
            # via stderr instead of propagating.
            import traceback
            traceback.print_exc()


__all__ = ["BaileysEventEmitter", "Listener"]
