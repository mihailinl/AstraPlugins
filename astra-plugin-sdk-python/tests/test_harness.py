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
from astra_plugin_sdk.proto import plugin_pb2
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


def test_recording_host_answers_get_daemon_info_with_its_port():
    """`PluginDaemonInfoResponse` names the port `grpc_port`; `port=` raised."""
    import asyncio

    host = RecordingHost(daemon_version="9.9", daemon_port=4242)
    info = asyncio.run(host.get_daemon_info())
    assert (info.version, info.grpc_port) == ("9.9", 4242)


# ── speech and identity ─────────────────────────────────────────────────────


class _Announcer(Plugin):
    @tool("Say something aloud, then report what Astra answered and who it is")
    async def announce(self, text: str):
        said = await self.host.speak(text)
        who = await self.host.get_user_identity()
        return {
            "outcome": plugin_pb2.PluginSpeechOutcome.Name(said.outcome),
            "code": (
                plugin_pb2.PluginErrorCode.Name(said.error.code)
                if said.HasField("error")
                else ""
            ),
            "retry_after_ms": said.error.retry_after_ms,
            "install_id": who.install_id,
            "authorized": who.authorized,
            "account_id": who.account_id,
        }

    @tool("Stop saying it")
    async def hush(self):
        await self.host.stop_speaking()
        return "hushed"


def test_speech_is_recorded_and_heard_by_default():
    with Harness(_Announcer()) as h:
        out = h.call_tool("announce", text="The kettle has boiled.").json
        assert out["outcome"] == "PLUGIN_SPEECH_OUTCOME_SPOKEN"
        assert out["code"] == ""
        assert h.host.spoken() == ["The kettle has boiled."]
        assert h.call_tool("hush").json == "hushed"
        assert h.host.stop_count() == 1


def test_a_not_spoken_answer_surfaces_its_error_to_the_plugin():
    """`NOT_SPOKEN` is an answer, not an exception: the plugin reads the code
    and the wait off `error`, and the text is still on the record."""
    with Harness(_Announcer()) as h:
        h.host.speak_response = {
            "outcome": plugin_pb2.PLUGIN_SPEECH_OUTCOME_NOT_SPOKEN,
            "error": plugin_pb2.PluginError(
                code=plugin_pb2.PLUGIN_ERROR_RATE_LIMITED,
                message="this plugin has used its speaking time",
                retry_after_ms=1500,
            ),
        }
        out = h.call_tool("announce", text="Again.").json
        assert out["outcome"] == "PLUGIN_SPEECH_OUTCOME_NOT_SPOKEN"
        assert out["code"] == "PLUGIN_ERROR_RATE_LIMITED"
        assert out["retry_after_ms"] == 1500
        assert h.host.spoken() == ["Again."]


def test_the_user_identity_round_trips_through_the_recording_host():
    with Harness(_Announcer()) as h:
        h.host.user_identity = {
            "install_id": "install-x",
            "signed_in": True,
            "authorized": False,
            "account_id": "",
        }
        out = h.call_tool("announce", text="hi").json
        assert (out["install_id"], out["authorized"], out["account_id"]) == (
            "install-x",
            False,
            "",
        )


def test_a_denied_speak_grant_reaches_the_plugin_as_a_failure():
    with Harness(_Announcer()) as h:
        h.host.fail_always("speak", Unavailable("permission denied: speak"))
        result = h.call_tool("announce", text="x")
        assert not result.success
        assert h.host.spoken() == []


def test_constructing_a_daemon_client_warns_that_it_is_deprecated():
    """Dead since 0.5.0; deprecated, not removed. The author who builds one
    is told so — the SDK's own construction (a `client` plugin's
    `self.daemon`) is silenced, and only that one."""
    from astra_plugin_sdk import DaemonClient

    with pytest.warns(DeprecationWarning, match="self.host"):
        DaemonClient("127.0.0.1:9", "token")


# ── a settings request ──────────────────────────────────────────────────────


class _Tuner(Plugin):
    @tool("Ask for a model, then report what Astra answered")
    async def tune(self, model: str):
        asked = await self.host.request_settings_change(
            {"ai.model": model}, "tuned for this model"
        )
        return {
            "outcome": plugin_pb2.PluginSettingsChangeOutcome.Name(asked.outcome),
            "code": asked.code,
            "refused_path": asked.refused_path,
            "retry_after_ms": asked.error.retry_after_ms,
        }


def test_a_settings_request_is_recorded_and_applied_by_default():
    with Harness(_Tuner()) as h:
        out = h.call_tool("tune", model="gpt-4.1").json
        assert out == {
            "outcome": "PLUGIN_SETTINGS_CHANGE_OUTCOME_APPLIED",
            "code": "",
            "refused_path": "",
            "retry_after_ms": 0,
        }
        [asked] = h.host.settings_change_requests()
        assert [(c.path, c.value_json) for c in asked.changes] == [
            ("ai.model", '"gpt-4.1"')
        ]
        assert asked.reason == "tuned for this model"


def test_a_refused_settings_request_surfaces_its_code_path_and_wait():
    """`REFUSED` is an answer, not an exception: the plugin reads the code
    word, the setting and the wait, and the request is still on the record."""
    with Harness(_Tuner()) as h:
        h.host.settings_change_response = {
            "outcome": plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_REFUSED,
            "refused_path": "ai.model",
            "code": "rate_limited",
            "error": {
                "code": plugin_pb2.PLUGIN_ERROR_RATE_LIMITED,
                "message": "this plugin asked too often",
                "retry_after_ms": 90000,
            },
        }
        out = h.call_tool("tune", model="gpt-4.1").json
        assert out == {
            "outcome": "PLUGIN_SETTINGS_CHANGE_OUTCOME_REFUSED",
            "code": "rate_limited",
            "refused_path": "ai.model",
            "retry_after_ms": 90000,
        }
        assert len(h.host.settings_change_requests()) == 1


@pytest.mark.parametrize(
    "outcome",
    [
        plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_UNCHANGED,
        plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_DECLINED,
        plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_TIMED_OUT,
    ],
)
def test_every_other_settings_outcome_reaches_the_plugin_as_itself(outcome):
    with Harness(_Tuner()) as h:
        h.host.settings_change_response = {"outcome": outcome}
        out = h.call_tool("tune", model="m").json
        assert out["outcome"] == plugin_pb2.PluginSettingsChangeOutcome.Name(outcome)
        assert out["code"] == ""


def test_a_denied_settings_request_grant_reaches_the_plugin_as_a_failure():
    with Harness(_Tuner()) as h:
        h.host.fail_always(
            "request_settings_change",
            Unavailable("permission denied: request_settings_change"),
        )
        assert not h.call_tool("tune", model="m").success
        assert h.host.settings_change_requests() == []


def test_setting_values_are_sent_as_compact_json_of_any_kind():
    from astra_plugin_sdk.host_client import settings_change_request

    req = settings_change_request(
        {
            "ai.model": "gpt-4.1",
            "voice.enabled": True,
            "voice.tts_speed": 1.2,
            "ai.max_tool_rounds": 24,
            "x.none": None,
            "x.obj": {"a": [1, "two"]},
            "x.text": 'say "hi"\n',
            "x.cyrillic": "Алиса",
        },
        "why",
    )
    assert [(c.path, c.value_json) for c in req.changes] == [
        ("ai.model", '"gpt-4.1"'),
        ("voice.enabled", "true"),
        ("voice.tts_speed", "1.2"),
        ("ai.max_tool_rounds", "24"),
        ("x.none", "null"),
        ("x.obj", '{"a":[1,"two"]}'),
        ("x.text", '"say \\"hi\\"\\n"'),
        ("x.cyrillic", '"Алиса"'),
    ]
    assert req.reason == "why"
    # Every value round-trips through JSON to what was meant.
    assert [json.loads(c.value_json) for c in req.changes][5:7] == [
        {"a": [1, "two"]},
        'say "hi"\n',
    ]


def test_setting_changes_may_be_pairs_and_keep_their_order_and_repeats():
    """Pairs keep the card's order, and a path given twice is sent twice: the
    daemon refuses it (`invalid`), the SDK does not second-guess it."""
    from astra_plugin_sdk.host_client import settings_change_request

    req = settings_change_request([("b", 1), ("a", 2), ("b", 3)], "")
    assert [(c.path, c.value_json) for c in req.changes] == [
        ("b", "1"),
        ("a", "2"),
        ("b", "3"),
    ]


def test_no_limit_is_checked_client_side():
    """The daemon is the authority: nine changes and a 200-character reason go
    out as they are, and its `REFUSED` (`too_many` / `reason_too_long`) is what
    the plugin reads — the SDK can never disagree with the Astra it talks to."""
    from astra_plugin_sdk.host_client import settings_change_request

    many = {f"p.{i}": i for i in range(limits.SETTINGS_CHANGE_MAX_CHANGES + 1)}
    long_reason = "é" * (limits.SETTINGS_CHANGE_REASON_MAX_CHARS + 60)
    req = settings_change_request(many, long_reason)
    assert len(req.changes) == limits.SETTINGS_CHANGE_MAX_CHANGES + 1
    assert req.reason == long_reason


@pytest.mark.parametrize(
    "value, error",
    [(float("nan"), ValueError), (float("inf"), ValueError), (object(), TypeError)],
)
def test_a_value_json_cannot_hold_raises_before_anything_is_sent(value, error):
    from astra_plugin_sdk.host_client import settings_change_request

    with pytest.raises(error):
        settings_change_request({"voice.tts_speed": value}, "why")


def test_a_string_is_not_a_set_of_changes():
    from astra_plugin_sdk.host_client import settings_change_request

    with pytest.raises(TypeError, match="not a string"):
        settings_change_request("ai.model", "why")


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
