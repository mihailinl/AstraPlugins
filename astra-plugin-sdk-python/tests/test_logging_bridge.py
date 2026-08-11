"""`logging` → `PluginLog`: the bridge, its bound, and its re-entrancy guard."""

import asyncio
import logging
import threading

from astra_plugin_sdk.logging_bridge import (
    DEFAULT_EXCLUDED_LOGGERS,
    PluginLogHandler,
    install_logging_bridge,
    level_name,
)
from astra_plugin_sdk.testing import RecordingHost


class _Plugin:
    """The only thing the handler needs: something with a `.host`."""

    def __init__(self, host=None):
        self.host = host


def _drain(handler: PluginLogHandler, host: RecordingHost, *, expect: int, timeout=2.0):
    """Run the handler's drain task until `expect` lines have reached the host."""

    async def run():
        handler.start()
        deadline = asyncio.get_running_loop().time() + timeout
        while len(host.logs()) < expect and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.005)
        handler.close()

    asyncio.run(run())


def test_levels_map_onto_the_four_the_daemon_knows():
    assert level_name(logging.DEBUG) == "debug"
    assert level_name(logging.INFO) == "info"
    assert level_name(logging.WARNING) == "warn"
    assert level_name(logging.ERROR) == "error"
    # There is no fifth bucket; CRITICAL is an error, not an unknown level.
    assert level_name(logging.CRITICAL) == "error"


def test_a_log_line_reaches_the_daemon():
    host = RecordingHost()
    handler = PluginLogHandler(_Plugin(host))
    logger = logging.getLogger("test.bridge.basic")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.warning("disk is full")
        _drain(handler, host, expect=1)
    finally:
        logger.removeHandler(handler)

    assert host.logs() and host.logs()[0].level == "warn"
    assert "disk is full" in host.logs()[0].message


def test_lines_logged_before_registration_are_not_lost():
    """The lines that matter most are the ones from before the host exists."""
    plugin = _Plugin(None)
    host = RecordingHost()
    handler = PluginLogHandler(plugin)
    logger = logging.getLogger("test.bridge.early")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("connecting to the daemon")

        async def run():
            handler.start()
            await asyncio.sleep(0.05)
            assert host.logs() == [], "sent a log line before the host existed"
            plugin.host = host  # registration completes
            for _ in range(200):
                if host.logs():
                    break
                await asyncio.sleep(0.01)
            handler.close()

        asyncio.run(run())
    finally:
        logger.removeHandler(handler)

    assert "connecting to the daemon" in host.logs()[0].message


def test_the_queue_is_bounded_and_says_how_much_it_dropped():
    """An unbounded queue in front of a stalled daemon is an OOM kill."""
    host = RecordingHost()
    handler = PluginLogHandler(_Plugin(host), capacity=4)
    logger = logging.getLogger("test.bridge.bound")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        for i in range(50):
            logger.info("line %d", i)
        assert len(handler._queue) == 4, "the queue grew past its capacity"
        _drain(handler, host, expect=4)
    finally:
        logger.removeHandler(handler)

    delivered = host.logs()
    assert len(delivered) >= 4
    assert any("dropped" in line.message for line in delivered), (
        "dropped lines vanished silently, which is the bug this bound creates"
    )
    # The tail survives, not the head: the most recent lines are the useful ones.
    assert "line 49" in delivered[-1].message or "line 49" in delivered[-2].message


def test_transport_loggers_are_never_forwarded():
    """Forwarding a grpc record over grpc is how the bridge eats itself."""
    host = RecordingHost()
    handler = PluginLogHandler(_Plugin(host))
    for name in DEFAULT_EXCLUDED_LOGGERS:
        record = logging.LogRecord(name, logging.ERROR, __file__, 1, "boom", (), None)
        handler.emit(record)
    assert len(handler._queue) == 0


def test_a_failing_host_does_not_break_logging():
    host = RecordingHost().fail_always("log", RuntimeError("daemon went away"))
    handler = PluginLogHandler(_Plugin(host))
    logger = logging.getLogger("test.bridge.failure")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("something")

        async def run():
            handler.start()
            await asyncio.sleep(0.1)
            handler.close()

        asyncio.run(run())  # must not raise
    finally:
        logger.removeHandler(handler)


def test_emit_works_from_a_thread_with_no_event_loop():
    """A plugin's worker thread logs like anything else, or the bridge is a lie."""
    host = RecordingHost()
    handler = PluginLogHandler(_Plugin(host))
    logger = logging.getLogger("test.bridge.thread")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        thread = threading.Thread(target=lambda: logger.error("from a worker"))
        thread.start()
        thread.join()
        _drain(handler, host, expect=1)
    finally:
        logger.removeHandler(handler)

    assert host.logs()[0].level == "error"
    assert "from a worker" in host.logs()[0].message


def test_install_is_idempotent():
    logger = logging.getLogger("test.bridge.install")
    first = install_logging_bridge(_Plugin(RecordingHost()), logger=logger)
    second = install_logging_bridge(_Plugin(RecordingHost()), logger=logger)
    bridges = [h for h in logger.handlers if isinstance(h, PluginLogHandler)]
    assert bridges == [second] and first is not second
    logger.handlers.clear()
