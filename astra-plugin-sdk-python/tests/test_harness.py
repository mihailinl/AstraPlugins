"""The level-1 harness, tested against a plugin built to exercise it."""

import inspect
import json

import pytest

from astra_plugin_sdk import (
    HostClient,
    Plugin,
    Unavailable,
    action,
    tool,
    trigger,
    Field,
)
from astra_plugin_sdk.testing import (
    Harness,
    HarnessError,
    RecordingHost,
    backpressure_burst,
    chunk_index,
    golden_pcm_f32,
    wake_seed_burst,
)
from astra_plugin_sdk import limits
from astra_plugin_sdk.types import SttOptions


class _Sample(Plugin):
    def __init__(self):
        super().__init__()
        self.seen_config: list[dict] = []
        self.seen_language: list[str] = []

    @tool("Count words")
    async def word_count(self, text: str):
        return {"words": len(text.split())}

    @tool("Echo the config")
    async def show_config(self):
        return {"config": self.config}

    @tool("Ask the daemon for the config")
    async def ask_daemon(self):
        return {"config": json.loads(await self.host.get_config())}

    @tool("Fire the trigger")
    async def ring(self):
        await self.fire_trigger("bell", {"loud": True})
        await self.host.set_variable("last_ring", "now")
        await self.push_to_ui("rang", {"n": 1})
        await self.log_info("rang the bell")
        return "ok"

    @action("Shout", fields=[Field.text("what", "What")])
    async def shout(self, what: str = "", **_):
        return what.upper()

    @trigger("Bell", fields=[Field.text("tone", "Tone")])
    def bell(self):
        pass

    async def on_config_changed(self, config):
        self.seen_config.append(config)

    async def on_language_changed(self, language):
        self.seen_language.append(language)


@pytest.fixture
def h():
    with Harness(_Sample()).with_config({"a": 1}).with_language("uk") as harness:
        yield harness


# ── what the plugin declares ────────────────────────────────────────────────


def test_tools_come_back_through_the_real_servicer(h):
    assert h.tool_names() == ["ask_daemon", "ring", "show_config", "word_count"]


def test_schema_is_parsed_and_checked(h):
    assert h.schema("word_count")["properties"]["text"] == {"type": "string"}
    h.assert_schema_accepts("word_count", "text")


def test_asking_for_a_tool_that_is_not_there_names_the_ones_that_are(h):
    with pytest.raises(HarnessError, match="ask_daemon"):
        h.schema("nope")


def test_assert_schema_accepts_fails_on_a_parameter_that_is_not_declared(h):
    with pytest.raises(HarnessError, match="nonexistent"):
        h.assert_schema_accepts("word_count", "nonexistent")


def test_a_broken_schema_is_caught_rather_than_handed_to_the_model():
    class _BadSchema(Plugin):
        async def list_tools(self):
            from astra_plugin_sdk import ToolDef

            return [ToolDef(name="bad", description="", parameters_json="not json")]

    with Harness(_BadSchema()) as h:
        with pytest.raises(HarnessError, match="not JSON"):
            h.schema("bad")


def test_a_schema_whose_root_is_not_an_object_is_caught():
    class _ArrayRoot(Plugin):
        async def list_tools(self):
            from astra_plugin_sdk import ToolDef

            return [ToolDef(name="arr", parameters_json='{"type": "array"}')]

    with Harness(_ArrayRoot()) as h:
        with pytest.raises(HarnessError, match="not an object"):
            h.schema("arr")


def test_actions_and_triggers_convert(h):
    assert [a.type for a in h.actions()] == ["shout"]
    assert [t.type for t in h.triggers()] == ["bell"]
    assert h.actions()[0].fields[0].id == "what"


# ── lifecycle ───────────────────────────────────────────────────────────────


def test_start_applies_config_and_language_before_the_first_call(h):
    """The daemon's order: config, then language, then serve.

    A plugin that starts a background task from `on_config_changed` must see the
    config the test set — not a default it is then corrected out of, which is
    what a harness that configured after starting would give it.
    """
    assert h.plugin.seen_config == [{"a": 1}]
    assert h.plugin.seen_language == ["uk"]


def test_config_changes_reach_the_plugin_and_the_host(h):
    h.set_config({"a": 2})
    assert h.plugin.config == {"a": 2}
    assert h.call_tool("show_config").json == {"config": {"a": 2}}
    # `get_config()` on the host answers the same thing, so a plugin that
    # re-reads it mid-call does not see a stale value.
    assert h.call_tool("ask_daemon").json == {"config": {"a": 2}}


def test_active_triggers_are_delivered(h):
    h.set_active_triggers(["bell"])
    assert h.plugin.active_triggers == {"bell"}


def test_language_changes_reach_the_plugin(h):
    h.set_language("de")
    assert h.plugin.language == "de"
    assert h.plugin.seen_language[-1] == "de"


# ── the recording host ──────────────────────────────────────────────────────


def test_everything_the_plugin_asked_the_daemon_for_is_recorded(h):
    assert h.call_tool("ring").success
    assert h.host.fired_triggers("bell")[0].payload == {"loud": True}
    assert h.host.variables() == {"last_ring": "now"}
    assert h.host.ui_pushes("rang")[0].payload == {"n": 1}
    assert h.host.logs("info")[0].message == "rang the bell"


def test_failure_injection_makes_the_permission_denied_branch_reachable(h):
    h.host.fail_next("fire_trigger", Unavailable("permission denied: fire_trigger"))
    result = h.call_tool("ring")
    assert not result.success
    assert result.code == "UNAVAILABLE"
    # `fail_next` is once only: the next call goes through.
    assert h.call_tool("ring").success


def test_arming_a_failure_on_a_method_that_does_not_exist_is_refused(h):
    """A typo would silently arm nothing and the test would assert its opposite."""
    with pytest.raises(AttributeError, match="firetrigger"):
        h.host.fail_next("firetrigger", RuntimeError())


def test_the_recording_host_covers_the_whole_real_host_surface():
    """The fake must not drift from `HostClient`, or a test proves nothing.

    Every public coroutine/method on the real client has to exist here with a
    compatible signature; otherwise a plugin that calls a newer host RPC passes
    its tests and fails in Astra.
    """
    real = {
        name
        for name, value in vars(HostClient).items()
        if not name.startswith("_") and callable(value) and name != "close"
    }
    fake = {
        name
        for name, value in vars(RecordingHost).items()
        if not name.startswith("_") and callable(value)
    }
    assert real <= fake, f"RecordingHost is missing {sorted(real - fake)}"
    for name in real:
        # Parameters only: the two modules disagree about whether annotations
        # are strings (`from __future__ import annotations`), and that is not a
        # drift anyone can call from a plugin.
        def params(cls):
            return [
                (p.name, p.kind, p.default)
                for p in inspect.signature(getattr(cls, name)).parameters.values()
            ]

        assert params(RecordingHost) == params(HostClient), (
            f"RecordingHost.{name} has drifted from HostClient.{name}"
        )
        assert inspect.iscoroutinefunction(getattr(RecordingHost, name)) == (
            inspect.iscoroutinefunction(getattr(HostClient, name))
        ), f"RecordingHost.{name} is async and HostClient.{name} is not, or vice versa"


# ── STT ─────────────────────────────────────────────────────────────────────


class _Buffering(Plugin):
    """The non-streaming shape: one call, the whole utterance."""

    def __init__(self):
        super().__init__()
        self.received = b""
        self.options = None

    async def stt_transcribe(self, audio, sample_rate, options=None):
        self.received = audio
        self.options = options
        return {"text": f"{len(audio)} bytes at {sample_rate}", "is_final": True}


class _Streaming(Plugin):
    """The streaming shape, and a slow one: it yields only at the end."""

    def __init__(self):
        super().__init__()
        self.indices: list[int] = []
        self.received = bytearray()

    async def stt_transcribe_stream(self, audio, options=None):
        async for chunk in audio:
            self.indices.append(chunk_index(chunk))
            self.received.extend(chunk.data)
            yield {"text": f"partial {len(self.indices)}", "is_final": False}
        yield {"text": f"{len(self.indices)} chunks", "is_final": True}


def test_a_buffering_plugin_gets_the_whole_utterance_and_the_options():
    pcm = golden_pcm_f32(0.25)
    with Harness(_Buffering()) as h:
        events = h.stt(pcm, options=SttOptions(language="uk", initial_prompt="astra"))
    assert len(events) == 1 and events[0].is_final
    assert h.plugin.received == pcm
    assert h.plugin.options.language == "uk"
    assert h.plugin.options.initial_prompt == "astra"


def test_the_wake_seed_burst_arrives_whole():
    """8 s of already-captured audio, dumped at once when the wake word fires."""
    chunks = wake_seed_burst()
    expected = b"".join(c.data for c in chunks)
    with Harness(_Streaming()) as h:
        events = h.stt(chunks)
    assert bytes(h.plugin.received) == expected
    assert len(h.plugin.indices) == len(chunks)
    assert events[-1].is_final


def test_more_chunks_than_the_queue_holds_are_not_dropped():
    """The 500-slot condition, reproduced (§5.6 fixtures).

    A bounded queue is correct; a bounded queue that drops is not. If the SDK's
    audio queue ever silently discarded on overflow, this is where the tail
    would go missing — which is exactly what a 32-slot queue did against a
    500-slot daemon channel, with no error anywhere.
    """
    chunks = backpressure_burst()
    assert len(chunks) > limits.STT_AUDIO_CHANNEL_CAPACITY
    with Harness(_Streaming(), timeout=30.0) as h:
        events = h.stt(chunks, timeout=30.0)
    assert h.plugin.indices == list(range(len(chunks)))
    assert events[-1].text == f"{len(chunks)} chunks"


def test_a_tool_whose_parameter_is_called_name_is_callable():
    """`name`, `action_type` and `method` are ordinary parameter names.

    The harness spells the RPC's target as a positional-only parameter for this
    reason. Written `def call_tool(self, name, **arguments)` instead, a tool with
    a `name` parameter — which is what the scaffolded `hello` has, and about as
    common as a parameter gets — raises `TypeError: got multiple values for
    argument 'name'`, and there is NO spelling of the call that works. The
    plugin is fine; the test harness is what cannot express the test.
    """

    class _Colliding(Plugin):
        @tool("Greet someone by name")
        async def hello(self, name: str, excited: bool = False):
            return f"Hello, {name}{'!' if excited else '.'}"

        @action("Say hello")
        async def say_hello(self, action_type: str = "x", method: str = "y"):
            return f"{action_type}/{method}"

    with Harness(_Colliding()) as h:
        assert h.call_tool("hello", name="Ada", excited=True).json == "Hello, Ada!"
        assert h.execute_action("say_hello", action_type="a", method="b").json == "a/b"
