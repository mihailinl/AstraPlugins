"""§5.10: a handler that raises returns an error instead of killing the plugin.

Every test here is the same shape — make a handler fail in a way that used to
escape the servicer, then assert the plugin is still answering afterwards. The
second half is the point. A test that only checks the error message would pass
against a servicer that answers once and then leaves the RPC task dead.
"""

import asyncio
import logging
import sys

import pytest

from astra_plugin_sdk import NotConfigured, Plugin, RateLimited, action, tool
from astra_plugin_sdk.testing import Harness


class _Breakable(Plugin):
    def __init__(self):
        super().__init__()
        self.config_calls = 0

    @tool("Fine")
    async def fine(self, text: str = ""):
        return {"echo": text}

    @tool("Raises a plain exception")
    async def boom(self):
        raise RuntimeError("the third-party library did that")

    @tool("Calls sys.exit, as a misbehaving library does")
    async def exits(self):
        sys.exit(2)

    @tool("Raises BaseException directly")
    async def base(self):
        raise BaseException("not an Exception at all")

    @tool("Needs configuration")
    async def needs_key(self):
        raise NotConfigured("api_key", doc_url="https://example.invalid/keys")

    @tool("Is rate limited")
    async def limited(self):
        raise RateLimited("upstream said no", retry_after=2.5)

    @tool("Returns something json cannot encode")
    async def unencodable(self):
        return {"when": object()}

    @action("Explodes")
    async def explode(self, **_):
        raise ValueError("bad params")

    async def on_config_changed(self, config):
        self.config_calls += 1
        if config.get("explode"):
            raise RuntimeError("config handler blew up")

    async def health_check(self):
        if self.config.get("sick"):
            raise RuntimeError("cannot reach the backend")
        return True, "ok"


@pytest.fixture
def h():
    with Harness(_Breakable()) as harness:
        yield harness


def test_a_raising_tool_answers_with_an_error_and_the_plugin_survives(h):
    result = h.call_tool("boom")
    assert not result.success
    assert result.code == "INTERNAL"
    assert "third-party library" in result.error
    assert h.call_tool("fine", text="still here").json == {"echo": "still here"}


def test_sys_exit_inside_a_tool_does_not_take_the_plugin_with_it(h):
    """`SystemExit` is not an `Exception`. `except Exception` never saw it.

    This is the concrete reason §5.10 says `BaseException`: a library that calls
    `sys.exit()` on a bad configuration used to kill the RPC task, and the
    plugin then answered nothing at all while still passing its health check.
    """
    result = h.call_tool("exits")
    assert not result.success
    assert h.call_tool("fine", text="alive").json == {"echo": "alive"}


def test_a_bare_BaseException_is_contained_too(h):
    result = h.call_tool("base")
    assert not result.success
    assert h.health()[0] is True


def test_cancellation_is_NOT_adopted():
    """Swallowing `CancelledError` turns a clean shutdown into a hang."""
    from astra_plugin_sdk.plugin import adopt

    with pytest.raises(asyncio.CancelledError):
        adopt(asyncio.CancelledError(), "somewhere")


def test_the_traceback_is_logged_and_not_sent_to_the_model(h, caplog):
    """The stack goes to the daemon's log; the AI loop gets one sentence."""
    with caplog.at_level(logging.ERROR, logger="astra_plugin_sdk"):
        result = h.call_tool("boom")
    assert "Traceback" in caplog.text
    assert "raise RuntimeError" in caplog.text
    assert "Traceback" not in result.error


def test_a_coded_failure_keeps_its_deep_link(h):
    result = h.call_tool("needs_key")
    assert result.code == "NOT_CONFIGURED"
    assert result.config_field == "api_key"
    assert result.doc_url == "https://example.invalid/keys"
    assert "api_key" in result.hint


def test_a_retry_hint_rounds_up_rather_than_down(h):
    result = h.call_tool("limited")
    assert result.code == "RATE_LIMITED"
    assert result.retry_after_ms == 2500


def test_an_unencodable_return_value_is_an_error_not_a_crash(h):
    result = h.call_tool("unencodable")
    assert not result.success
    assert h.call_tool("fine").success


def test_invalid_json_arguments_are_BAD_ARGUMENTS(h):
    """The model writes this string, and it is not always valid JSON."""
    result = h.call_tool_raw("fine", "{not json")
    assert not result.success
    assert result.code == "BAD_ARGUMENTS"


def test_an_unknown_tool_is_NOT_FOUND(h):
    result = h.call_tool("no_such_tool")
    assert result.code == "NOT_FOUND"


def test_a_raising_action_is_contained(h):
    result = h.execute_action("explode")
    assert not result.success
    assert result.code == "BAD_ARGUMENTS"


def test_a_raising_config_hook_is_reported_and_the_plugin_keeps_serving():
    """`OnConfigChanged` answers `Empty`; there is nowhere to put a failure.

    Before §5.10 the exception escaped as an UNKNOWN transport status and the
    plugin ran on with the config it had — visible nowhere.
    """
    from astra_plugin_sdk.testing import HarnessError

    with Harness(_Breakable()) as h:
        with pytest.raises(HarnessError, match="on_config_changed"):
            h.set_config({"explode": True})
        assert h.call_tool("fine").success
        h.set_config({"explode": False})
        assert h.plugin.config == {"explode": False}


def test_a_raising_health_check_answers_unhealthy_rather_than_dying():
    with Harness(_Breakable()).with_config({"sick": True}) as h:
        healthy, status = h.health()
    assert healthy is False
    assert "cannot reach the backend" in status


def test_a_raising_shutdown_hook_does_not_stop_the_shutdown():
    class _BadExit(Plugin):
        async def on_shutdown(self):
            raise RuntimeError("cleanup failed")

    h = Harness(_BadExit()).start()
    h.stop()  # must not raise: the daemon is on a grace timer
