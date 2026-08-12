"""**A trigger fired while handling a daemon call names the call that caused it.**

The bug: a plugin action runs inside a command run a user started by typing in a
chat. The plugin fires a trigger, which starts a *second* command run — and that
run has no idea what caused it, so its output is filed into a freshly
auto-created conversation the user never sees. Two chats driving one plugin at
once are indistinguishable on the wire.

The daemon carries a per-invocation lease as ``x-astra-cause`` call metadata; the
SDK echoes it on ``FireTrigger``. In Python the read lives in
``HostClient.fire_trigger`` — the transport all three fire paths converge on —
with a :class:`contextvars.ContextVar` bound by a server interceptor around every
capability call.

These run at level 2 wherever the wire matters: ``MockDaemon`` reports
``caused_by`` as it arrived on the socket, so what is asserted is what the daemon
would actually see, not what the SDK intended to send. Every link is invisible
when it breaks — a lease that never reaches the wire produces a working plugin
whose output goes to the wrong place, with no error anywhere.
"""

import asyncio
import contextvars
import time

import pytest

from astra_plugin_sdk import Plugin, tool
from astra_plugin_sdk.causality import current_cause
from astra_plugin_sdk.testing import WireHarness


class _Roller(Plugin):
    """Fires through the wrapper on the plugin object — the idiomatic path, and
    the one that routes to the process-global host rather than to any per-call
    context. If the lease read lived in a context wrapper this would lose it."""

    @tool("Roll dice")
    async def roll_dice(self):
        await self.fire_trigger("on_roll_value", {"value": "2"})
        return "1d5: [2] = 2"

    @tool("Roll after yielding to the loop")
    async def roll_slowly(self, name: str = "a", ms: int = 20):
        await asyncio.sleep(ms / 1000)
        await self.fire_trigger("on_roll_value", {"value": name})
        return name

    @tool("Roll from a task the handler spawned")
    async def roll_detached(self):
        task = asyncio.create_task(self.fire_trigger("on_roll_value", {"via": "task"}))
        await task
        return "ok"

    @tool("Roll from a thread-pool worker")
    async def roll_in_executor(self):
        loop = asyncio.get_running_loop()
        # No `contextvars.copy_context()`: this is the documented gap, asserted
        # rather than papered over.
        seen = await loop.run_in_executor(None, current_cause)
        await self.fire_trigger("on_roll_value", {"executor_saw": str(seen)})
        return str(seen)


def _settle(harness, n, timeout=2.0):
    """Wait for `n` fires to land; some of them are deliberately deferred."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(harness.daemon.fired_triggers()) >= n:
            return
        time.sleep(0.01)
    pytest.fail(f"expected {n} fired trigger(s), saw {len(harness.daemon.fired_triggers())}")


def test_a_lease_on_a_call_comes_back_on_the_trigger_it_caused():
    with WireHarness(_Roller()) as w:
        with w.lease("lease-abc"):
            w.call_tool("roll_dice")
        _settle(w, 1)

        fired = w.daemon.fired_triggers()
        assert fired[0].trigger_type == "on_roll_value"
        assert fired[0].caused_by == "lease-abc", (
            "the lease did not survive the trip; the daemon would file this fire as a root "
            "event and its output would land in a conversation nobody is looking at"
        )


def test_a_plugin_that_was_never_leased_fires_a_root_event():
    # The state every daemon in the field is in, and the one this must never
    # make worse. An empty header would be worse than none: the daemon has to
    # tell "sent no lease" from "sent a lease I cannot resolve", and only the
    # second is a bug.
    with WireHarness(_Roller()) as w:
        w.call_tool("roll_dice")
        _settle(w, 1)
        assert w.daemon.fired_triggers()[0].caused_by is None


def test_the_cause_survives_an_await_inside_the_handler():
    with WireHarness(_Roller()) as w:
        with w.lease("lease-slow"):
            w.call_tool("roll_slowly", name="a", ms=20)
        _settle(w, 1)
        assert w.daemon.fired_triggers()[0].caused_by == "lease-slow"


def test_the_cause_survives_a_task_the_handler_spawned():
    # `asyncio.create_task` copies the context at creation, which is what makes
    # a ContextVar the right tool in Python and the wrong one in Rust — a
    # `tokio::task_local!` does not cross `tokio::spawn`.
    with WireHarness(_Roller()) as w:
        with w.lease("lease-task"):
            w.call_tool("roll_detached")
        _settle(w, 1)
        assert w.daemon.fired_triggers()[0].caused_by == "lease-task"


def test_a_thread_pool_worker_sees_no_cause_and_says_so():
    # `loop.run_in_executor` does NOT copy the context. Documented in
    # `causality.py` and asserted here, because a silent gap is how a guarantee
    # becomes a rumour. Losing the cause is safe — a root event; guessing would
    # not be.
    with WireHarness(_Roller()) as w:
        with w.lease("lease-exec"):
            response = w.call_tool("roll_in_executor")
        _settle(w, 1)

        assert response.result == "None", "the executor thread must not inherit the lease"
        # The fire itself is back on the coroutine, so it IS attributed. The gap
        # is the worker thread, not the handler that owns it.
        assert w.daemon.fired_triggers()[0].caused_by == "lease-exec"


def test_a_context_copied_across_the_executor_carries_the_cause():
    """The documented workaround has to actually work, or the doc is a lie."""

    class _Careful(Plugin):
        @tool("Roll, carrying the context across by hand")
        async def roll(self):
            loop = asyncio.get_running_loop()
            ctx = contextvars.copy_context()
            seen = await loop.run_in_executor(None, lambda: ctx.run(current_cause))
            return str(seen)

    with WireHarness(_Careful()) as w:
        with w.lease("lease-copied"):
            assert w.call_tool("roll").result == "lease-copied"


def test_concurrent_plugins_do_not_collect_each_others_cause():
    # Two harnesses rather than two calls on one, because the lease block is one
    # attribute on one harness — and because two chats really are two callers.
    with WireHarness(_Roller()) as a, WireHarness(_Roller()) as b:
        with a.lease("chat-a"):
            a.call_tool("roll_slowly", name="a", ms=40)
        with b.lease("chat-b"):
            b.call_tool("roll_slowly", name="b", ms=5)
        _settle(a, 1)
        _settle(b, 1)

        assert a.daemon.fired_triggers()[0].caused_by == "chat-a"
        assert b.daemon.fired_triggers()[0].caused_by == "chat-b"
