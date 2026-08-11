# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""`logging` → `PluginLog`, so a plugin's own logs reach the daemon (§5.10).

WHY

A Python plugin logs the way Python logs: `logging.getLogger(__name__).info(...)`.
None of that reached Astra. The only way to put a line in the daemon's log pane
was `await self.log_info(...)` — a coroutine, so unusable from a sync helper, a
thread, or a library the plugin depends on. In practice authors used `print()`,
which lands in the daemon's captured stdout with no level, no logger name and no
timestamp, and is therefore useless the moment two things are happening at once.

This module attaches one `logging.Handler` that forwards records to the host's
`PluginLog` RPC. After `install_logging_bridge()` the ordinary Python idiom is
the right one, from anywhere in the process, including background threads.

THREE THINGS THAT MAKE THIS HARDER THAN IT LOOKS

1. **`logging` is synchronous; `PluginLog` is a coroutine on the event loop.**
   `emit()` may run on any thread, including one with no loop. So `emit()` only
   appends to a bounded deque and pokes the loop; a drain task on the loop does
   the awaiting. Logging never blocks on the network.

2. **The queue must be bounded, and dropping must be visible.** An unbounded
   queue in front of a daemon that has stopped reading is a memory leak that
   ends as an OOM kill — reported to the user as "the plugin crashed". The
   deque has a `maxlen`; overflow drops the OLDEST record and counts it, and the
   count is emitted with the next line that does get through. A silent drop is
   how you spend an afternoon looking for a log line that was never sent.

3. **Forwarding must not recurse.** `grpc` logs. If a `grpc` record is forwarded
   over a `grpc` call which logs again, the process spins. Two guards: a
   thread-local re-entrancy flag around the forward, and a default deny-list of
   logger names belonging to the transport itself.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import sys
import threading
from typing import Any, Iterable

__all__ = [
    "PluginLogHandler",
    "install_logging_bridge",
    "DEFAULT_EXCLUDED_LOGGERS",
    "level_name",
]

#: Loggers never forwarded, because forwarding them is how the bridge eats
#: itself: they belong to the transport the forward travels over.
DEFAULT_EXCLUDED_LOGGERS: tuple[str, ...] = ("grpc", "asyncio", "h2", "hpack", "urllib3")

#: How many records may wait for the loop before the oldest are dropped.
#: A daemon that has stopped reading must cost this plugin a bounded amount of
#: memory and nothing more.
DEFAULT_CAPACITY = 512

_LEVEL_NAMES = (
    (logging.ERROR, "error"),
    (logging.WARNING, "warn"),
    (logging.INFO, "info"),
)

_local = threading.local()


def level_name(levelno: int) -> str:
    """A Python level number as the daemon's level string.

    The daemon knows four: `debug`, `info`, `warn`, `error`. `CRITICAL` maps to
    `error` — there is no fifth bucket, and inventing one would show up in the
    UI as an unstyled unknown level.
    """
    for threshold, name in _LEVEL_NAMES:
        if levelno >= threshold:
            return name
    return "debug"


class PluginLogHandler(logging.Handler):
    """Forwards `logging` records to the daemon over `PluginLog`.

    Constructed with the `Plugin`, not with a `HostClient`, on purpose: the host
    does not exist until registration succeeds, and records emitted before then
    (import-time, config parsing, a failed connect) are exactly the ones worth
    keeping. They queue, and go out as soon as the host is there.
    """

    def __init__(
        self,
        plugin: Any,
        *,
        capacity: int = DEFAULT_CAPACITY,
        excluded_loggers: Iterable[str] = DEFAULT_EXCLUDED_LOGGERS,
    ):
        super().__init__()
        self._plugin = plugin
        self._excluded = tuple(excluded_loggers)
        self._queue: collections.deque[tuple[str, str]] = collections.deque(maxlen=capacity)
        self._dropped = 0
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wakeup: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    # ── the logging side (any thread, never blocks) ──

    def emit(self, record: logging.LogRecord) -> None:
        if self._excluded and record.name.startswith(self._excluded):
            return
        if getattr(_local, "forwarding", False):
            # A record produced by the forward itself. Dropping it is the only
            # safe answer; the stderr handler still shows it.
            return
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 — a broken formatter must not kill logging
            self.handleError(record)
            return

        with self._lock:
            if len(self._queue) == self._queue.maxlen:
                self._dropped += 1
            self._queue.append((level_name(record.levelno), message))
            loop, wakeup = self._loop, self._wakeup

        if loop is not None and wakeup is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(wakeup.set)
            except RuntimeError:
                pass  # loop shut down between the check and the call

    # ── the plugin side (on the event loop) ──

    def start(self) -> None:
        """Begin draining. Call once, from the plugin's event loop."""
        if self._task is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._wakeup = asyncio.Event()
        if self._queue:
            self._wakeup.set()
        self._task = asyncio.get_running_loop().create_task(self._drain())

    async def _drain(self) -> None:
        assert self._wakeup is not None
        while True:
            await self._wakeup.wait()
            self._wakeup.clear()
            while True:
                with self._lock:
                    if not self._queue:
                        dropped, self._dropped = self._dropped, 0
                        break
                    level, message = self._queue.popleft()
                    dropped, self._dropped = self._dropped, 0
                if dropped:
                    message = f"[{dropped} log line(s) dropped: the daemon was not keeping up] {message}"
                await self._send(level, message)
            if dropped:
                await self._send(
                    "warn", f"[{dropped} log line(s) dropped: the daemon was not keeping up]"
                )

    async def _send(self, level: str, message: str) -> None:
        host = getattr(self._plugin, "host", None)
        if host is None:
            # Not registered yet. Put it back at the front and wait to be poked
            # again — `start()` is called before registration precisely so these
            # survive.
            with self._lock:
                self._queue.appendleft((level, message))
            await asyncio.sleep(0.25)
            if self._wakeup is not None:
                self._wakeup.set()
            return
        _local.forwarding = True
        try:
            await host.log(level, message)
        except Exception as e:  # noqa: BLE001
            # The daemon refusing our logs must never be fatal, and must never
            # be reported *through* the thing that just failed.
            print(f"astra-plugin-sdk: could not forward a log line: {e}", file=sys.stderr)
        finally:
            _local.forwarding = False

    def close(self) -> None:
        # `logging.shutdown()` closes every handler at interpreter exit, from the
        # main thread, long after the plugin's loop is gone. Cancelling straight
        # from here would touch a closed loop from the wrong thread and raise
        # out of an atexit hook, where nothing can catch it.
        task, loop = self._task, self._loop
        self._task = None
        if task is not None and loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass  # the loop closed between the check and the call
        super().close()


def install_logging_bridge(
    plugin: Any,
    *,
    level: int = logging.INFO,
    logger: logging.Logger | None = None,
    also_stderr: bool = True,
    capacity: int = DEFAULT_CAPACITY,
) -> PluginLogHandler:
    """Attach the bridge to `logger` (the root logger by default).

    Returns the handler, so a plugin that wants a different formatter or a
    different level can say so. Idempotent: installing twice replaces the first.

    `also_stderr` adds a plain stderr handler when the target logger has none,
    because the daemon captures the plugin's stderr into its per-plugin log file
    and a plugin whose only log path is the daemon RPC has no diagnostics at all
    on the failure that matters most — the one where registration never
    succeeded.
    """
    target = logger or logging.getLogger()
    for existing in list(target.handlers):
        if isinstance(existing, PluginLogHandler):
            target.removeHandler(existing)
            existing.close()

    handler = PluginLogHandler(plugin, capacity=capacity)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    target.addHandler(handler)

    if also_stderr and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, PluginLogHandler)
        for h in target.handlers
    ):
        stream = logging.StreamHandler(sys.stderr)
        stream.setLevel(level)
        stream.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        target.addHandler(stream)

    if target.level == logging.NOTSET or target.level > level:
        target.setLevel(level)
    return handler
