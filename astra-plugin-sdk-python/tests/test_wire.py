"""Level 2: the plugin's real `run()` path, over loopback gRPC, against a mock daemon.

Everything here is a thing level 1 structurally cannot see.
"""

import json
import time

import grpc
import pytest

from astra_plugin_sdk import Plugin, tool, ui_call, ui_page
from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc
from astra_plugin_sdk.testing import MockDaemon, WireError, WireHarness
from astra_plugin_sdk.testing.fixtures import backpressure_burst
from astra_plugin_sdk.testing.wire import PLUGIN_TOKEN_HEADER, SESSION_TOKEN_HEADER


@ui_page("panel", "Panel", "http://127.0.0.1:9/panel.html")
class _Wired(Plugin):
    @tool("Count words")
    async def word_count(self, text: str):
        return {"words": len(text.split())}

    @tool("Read the config the daemon sent")
    async def read_config(self):
        return {"config": self.config}

    @tool("Talk to the daemon")
    async def announce(self):
        await self.log_info("hello from the plugin")
        await self.fire_trigger("rang", {"n": 1})
        return "ok"

    @ui_call
    async def ping(self):
        return {"pong": True}


class _Streamer(Plugin):
    def __init__(self):
        super().__init__()
        self.chunks = 0
        self.bytes = 0

    async def stt_transcribe_stream(self, audio, options=None):
        async for chunk in audio:
            self.chunks += 1
            self.bytes += len(chunk.data)
        yield {"text": f"{self.chunks} chunks", "is_final": True}


def test_a_plugin_registers_and_answers_over_a_real_socket():
    with WireHarness(_Wired(), config={"k": "v"}) as w:
        assert w.daemon.registrations, "the plugin never registered"
        registration = w.daemon.registrations[0]
        assert registration.plugin_id == "test-plugin"
        assert registration.port == w.plugin.port
        # §1.3: without these on the wire the daemon cannot tell an old plugin
        # from a new one, and its protocol floor means nothing.
        assert registration.protocol_version >= 1
        assert registration.sdk_name == "astra-plugin-sdk-python"
        assert registration.sdk_version

        reply = w.call_tool("word_count", text="one two three")
        assert reply.success
        assert json.loads(reply.result)["words"] == 3


def test_the_daemons_config_reaches_the_plugin_through_registration():
    with WireHarness(_Wired(), config={"k": "v"}) as w:
        assert json.loads(w.call_tool("read_config").result)["config"] == {"k": "v"}


def test_every_handler_is_reachable_by_its_wire_path():
    """Level 1 calls the servicer by attribute; gRPC finds it by path.

    A servicer method that is registered but misspelled is invisible on the wire
    and perfect in a level-1 test — which is exactly the Phase 0 finding that
    three TypeScript handlers were silently dropped.
    """
    with WireHarness(_Wired()) as w:
        assert [t.name for t in w.list_tools()] == ["announce", "read_config", "word_count"]
        assert [c.id for c in w.ui_contributions()] == ["panel"]
        assert w.health().healthy
        assert json.loads(w.ui_call("ping").result_json) == {"pong": True}


def test_a_host_call_carries_the_session_token():
    """Every host RPC after `Register` must present `x-session-token`.

    The daemon exempts exactly one path. An SDK that forgets the header gets
    `unauthenticated` on `log`, `fire_trigger`, `set_variable` — the Phase 0
    finding that made the whole protocol unusable in all three languages.
    """
    with WireHarness(_Wired()) as w:
        assert w.call_tool("announce").success
        assert w.daemon.unauthenticated_calls == []
        assert "hello from the plugin" in [l.message for l in w.daemon.logs("info")]
        assert w.daemon.fired_triggers("rang")[0].payload == {"n": 1}

    # The SDK logs its own registration through the bridge, so *every* plugin
    # makes at least one authenticated host call on every start — which is what
    # lets `astra-plugin test` assert "this plugin talked to the daemon" over
    # plugins that never log anything of their own.
    assert any("Registered with Astra" in l.message for l in w.daemon.logs("info"))


def test_the_mock_daemons_own_session_gate_refuses_an_untokened_caller():
    """The gate that makes the test above mean anything, tested on its own.

    `test_a_host_call_carries_the_session_token` detects a missing token
    *solely* by this daemon rejecting the call: it asserts a trigger arrived and
    that `unauthenticated_calls` is empty. Relax `MockDaemon._authenticate` —
    while debugging a level-2 test that "keeps 401-ing me", or in a refactor
    that drops the early return — and that test keeps its name, keeps passing,
    and stops testing anything. The SDK's only defence against the Phase 0
    regression would be gone with no signal anywhere.

    So the gate is driven from outside, over the wire, the way a plugin drives
    it. Rust and TypeScript have the same test.
    """
    with WireHarness(_Wired()) as w:
        channel = grpc.insecure_channel(w.daemon.address)
        stub = plugin_pb2_grpc.PluginHostServiceStub(channel)
        line = plugin_pb2.PluginLogRequest(
            plugin_id="impostor", level="info", message="let me in"
        )

        with pytest.raises(grpc.RpcError) as excinfo:
            stub.PluginLog(line)  # no metadata at all
        assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED

        with pytest.raises(grpc.RpcError) as excinfo:
            stub.PluginLog(line, metadata=[(SESSION_TOKEN_HEADER, "guessed")])
        assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED

        # The token it actually issued gets through. Without this the gate could
        # be "refuse everything", which would fail the real tests for a reason
        # that has nothing to do with the header.
        stub.PluginLog(line, metadata=[(SESSION_TOKEN_HEADER, w.daemon.session_token)])
        assert "let me in" in [l.message for l in w.daemon.logs("info")]

        # Both refusals are on the record; the accepted call is not.
        assert w.daemon.unauthenticated_calls == ["PluginLog", "PluginLog"]
        channel.close()


def test_a_call_without_the_daemon_token_is_refused():
    """`ASTRA_PLUGIN_CAPABILITY_AUTH=require`: loopback is not a boundary.

    Any local process can dial an OS-assigned loopback port. Without this check
    another installed plugin could call `OnConfigChanged` and repoint this
    plugin's base URL at a host it controls.
    """
    with WireHarness(_Wired(), capability_auth="require") as w:
        channel = grpc.insecure_channel(f"127.0.0.1:{w.plugin.port}")
        stub = plugin_pb2_grpc.PluginCapabilityServiceStub(channel)
        with pytest.raises(grpc.RpcError) as excinfo:
            stub.ListTools(plugin_pb2.Empty())  # no metadata at all
        assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED

        with pytest.raises(grpc.RpcError) as excinfo:
            stub.ListTools(plugin_pb2.Empty(), metadata=[(PLUGIN_TOKEN_HEADER, "guessed")])
        assert excinfo.value.code() == grpc.StatusCode.UNAUTHENTICATED
        channel.close()


def test_a_refused_registration_does_not_leave_a_half_started_plugin():
    daemon = MockDaemon(accept_registration=False, registration_error="not installed")
    with pytest.raises(WireError, match="exited with code 1"):
        WireHarness(_Wired(), daemon=daemon, timeout=5.0).start()


def test_a_wrong_spawn_token_is_refused_by_the_daemon():
    """The token proves the daemon spawned this process; a mismatch is fatal."""
    daemon = MockDaemon(auth_token="the-real-one")
    with pytest.raises(WireError, match="exited with code 1"):
        WireHarness(_Wired(), daemon=daemon, spawn_token="guessed", timeout=5.0).start()
    assert daemon.registrations[0].auth_token == "guessed"


def test_backpressure_over_a_real_stream_loses_nothing():
    """600 chunks through a 500-slot queue and a real HTTP/2 window.

    The condition `spec/limits.yaml` exists for. Only reachable at this level:
    level 1 has no flow-control window at all.
    """
    chunks = backpressure_burst()
    plugin = _Streamer()
    with WireHarness(plugin, timeout=60.0) as w:
        events = w.stt([c.to_proto() for c in chunks], timeout=60.0)
    assert plugin.chunks == len(chunks)
    assert plugin.bytes == sum(len(c.data) for c in chunks)
    assert events[-1].text == f"{len(chunks)} chunks"


def test_shutdown_makes_the_process_exit_and_not_merely_the_server_stop():
    """`Shutdown` must end the RUN, not just the gRPC server.

    `_run_async` parks on `_stop_event.wait()`. A `Shutdown` handler that stops
    the server and leaves that event unset leaves an interpreter alive with
    nothing to serve; the daemon's grace timer then expires and SIGKILLs the
    process group, so `on_shutdown` — the plugin's only chance to flush state —
    never runs on a user's machine. `astra-plugin test` reports this as
    "the process was still running 5s after Shutdown".

    Level 2 on purpose: level 1 never starts `_run_async`, so it cannot see it.
    """
    stopped = []

    class _Tidy(Plugin):
        async def on_shutdown(self):
            stopped.append(True)

    with WireHarness(_Tidy(), timeout=15.0) as w:
        w.stub().Shutdown(plugin_pb2.Empty(), metadata=w.metadata, timeout=5.0)

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not w._run_task.done():
            time.sleep(0.05)

        assert w._run_task.done(), (
            "the plugin is still running after Shutdown — the daemon kills the "
            "process group when the grace period expires"
        )

    # And the tidy path ran exactly once: `Shutdown` hands off to `_run_async`
    # rather than doing the cleanup itself, and doing both would run it twice.
    assert stopped == [True]
