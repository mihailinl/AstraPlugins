"""The reference test suite for a Python Astra plugin (production plan §5.6).

Read this before writing tests for your own plugin. It is roughly the shape
every plugin's suite should have:

  1. **Declarations** — the tools exist, under the names the daemon will use,
     with schemas the model can produce arguments for.
  2. **Behaviour** — call each tool the way Astra calls it, through the harness,
     not by calling the Python method.
  3. **Failure** — every way the tool can fail, and the code it fails with.
     This is the half most suites skip and the half users actually meet.
  4. **The daemon side** — what the plugin asked Astra for, and what it does
     when Astra says no.
  5. **Configuration** — including the values nobody designed for.
  6. **Over the wire** — one level-2 test, because level 1 cannot see
     registration, the descriptor, or the interceptor.

Run it with `pytest` from this directory. The `astra_harness` / `astra_wire`
fixtures come from `astra_plugin_sdk.testing`; there is no conftest to write.
"""

import json

import pytest

from astra_plugin_sdk import Unavailable
from astra_plugin_sdk.testing import Harness

from src.plugin import TextUtils


@pytest.fixture
def h(astra_harness):
    """A started plugin with the default config, torn down after each test."""
    return astra_harness(TextUtils(), config={"max_text_length": 10000})


# ── 1. what the plugin declares ─────────────────────────────────────────────


def test_the_three_tools_are_registered_under_the_names_astra_will_use(h):
    assert h.tool_names() == ["case_convert", "regex_match", "word_count"]


def test_every_tool_schema_is_something_a_model_can_answer(h):
    """`h.schema` fails on unparseable JSON or a non-object root."""
    for name in h.tool_names():
        assert h.schema(name)["type"] == "object"
    h.assert_schema_accepts("word_count", "text")
    h.assert_schema_accepts("case_convert", "text", "mode")
    h.assert_schema_accepts("regex_match", "text", "pattern")


def test_required_parameters_are_marked_required(h):
    assert set(h.schema("case_convert")["required"]) == {"text", "mode"}


def test_the_action_carries_the_fields_the_command_editor_renders(h):
    (transform,) = h.actions()
    assert transform.type == "transform_text"
    assert [f.id for f in transform.fields] == ["operation", "input_text", "store_in"]
    operation = transform.fields[0]
    assert [o.value for o in operation.options] == [
        "upper", "lower", "title", "reverse", "base64_encode", "base64_decode",
    ]
    # The conditional field is only shown once an operation is chosen.
    assert transform.fields[2].conditions[0].field_id == "operation"
    assert transform.ai_available and transform.ai_primary_field == "input_text"


def test_the_trigger_is_declared_with_its_time_field(h):
    (tick,) = h.triggers()
    assert tick.type == "on_time"
    assert tick.fields[0].id == "time" and tick.fields[0].default_value == "09:00"


# ── 2. behaviour ────────────────────────────────────────────────────────────


def test_word_count(h):
    assert h.call_tool("word_count", text="one two three").json == {
        "words": 3,
        "characters": 13,
        "lines": 1,
    }


def test_word_count_of_nothing_is_not_one_empty_line(h):
    assert h.call_tool("word_count", text="").json == {
        "words": 0,
        "characters": 0,
        "lines": 0,
    }


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("upper", "HELLO WORLD"),
        ("lower", "hello world"),
        ("title", "Hello World"),
        ("snake", "hello_world"),
        ("camel", "helloWorld"),
    ],
)
def test_case_convert(h, mode, expected):
    assert h.call_tool("case_convert", text="hello world", mode=mode).json == expected


def test_regex_match_returns_every_match_and_a_count(h):
    result = h.call_tool("regex_match", text="a1 b22 c333", pattern=r"\d+").json
    assert result == {"pattern": r"\d+", "matches": ["1", "22", "333"], "count": 3}


@pytest.mark.parametrize(
    "operation,text,expected",
    [
        ("upper", "hi", "HI"),
        ("reverse", "abc", "cba"),
        ("base64_encode", "hi", "aGk="),
        ("base64_decode", "aGk=", "hi"),
    ],
)
def test_the_transform_action(h, operation, text, expected):
    assert h.execute_action("transform_text", operation=operation, input_text=text).result == expected


def test_health_reports_how_much_work_it_has_done(h):
    h.call_tool("word_count", text="one")
    h.call_tool("word_count", text="two")
    healthy, status = h.health()
    assert healthy and "2 operations" in status


# ── 3. failure ──────────────────────────────────────────────────────────────


def test_an_unknown_case_mode_is_BAD_ARGUMENTS_and_lists_the_real_ones(h):
    """The model is the caller. This is the code that tells it to try again."""
    result = h.call_tool("case_convert", text="x", mode="klingon")
    assert not result.success
    assert result.code == "BAD_ARGUMENTS"
    assert "snake" in result.error


def test_an_invalid_regex_is_BAD_ARGUMENTS_not_a_crash(h):
    result = h.call_tool("regex_match", text="x", pattern="(unclosed")
    assert result.code == "BAD_ARGUMENTS"
    assert "not a valid regular expression" in result.error


def test_text_over_the_configured_limit_is_refused_with_both_numbers(astra_harness):
    h = astra_harness(TextUtils(), config={"max_text_length": 5})
    result = h.call_tool("word_count", text="far too long")
    assert result.code == "BAD_ARGUMENTS"
    assert "12 characters" in result.error and "at most 5" in result.error


def test_the_limit_applies_to_the_action_as_well(astra_harness):
    h = astra_harness(TextUtils(), config={"max_text_length": 5})
    assert h.execute_action("transform_text", operation="upper", input_text="far too long").code == (
        "BAD_ARGUMENTS"
    )


def test_bad_base64_is_the_callers_problem_not_an_internal_error(h):
    result = h.execute_action("transform_text", operation="base64_decode", input_text="!!!")
    assert result.code == "BAD_ARGUMENTS"


def test_an_unknown_tool_is_NOT_FOUND(h):
    assert h.call_tool("summarise").code == "NOT_FOUND"


def test_arguments_that_are_not_json_are_BAD_ARGUMENTS(h):
    """The model writes this string. Sometimes it writes it wrong."""
    assert h.call_tool_raw("word_count", "{text: 'no quotes'}").code == "BAD_ARGUMENTS"


def test_a_failing_tool_does_not_stop_the_next_one(h):
    h.call_tool("case_convert", text="x", mode="nope")
    assert h.call_tool("word_count", text="still here").success


# ── 4. the daemon side ──────────────────────────────────────────────────────


def test_the_trigger_does_not_fire_when_no_command_is_listening(h):
    """`on_active_triggers` is not advice. Firing anyway wakes commands twice."""
    assert h.run(h.plugin.tick(now="09:00")) is False
    assert h.host.fired_triggers() == []


def test_the_trigger_fires_once_per_minute_and_not_twice(h):
    h.set_active_triggers(["on_time"])
    assert h.run(h.plugin.tick(now="09:00")) is True
    assert h.run(h.plugin.tick(now="09:00")) is False
    assert h.run(h.plugin.tick(now="09:01")) is True

    fired = h.host.fired_triggers("on_time")
    assert [f.payload["time"] for f in fired] == ["09:00", "09:01"]


def test_a_daemon_that_refuses_fire_trigger_does_not_break_the_schedule(h):
    """`[permissions] fire_trigger` missing, or Astra restarting mid-call.

    Without failure injection this branch is unreachable in a test, and an
    unreachable branch is a branch that is wrong.
    """
    h.set_active_triggers(["on_time"])
    h.host.fail_next("fire_trigger", Unavailable("permission denied: FireTrigger"))
    assert h.run(h.plugin.tick(now="09:00")) is False
    # The next minute still gets its chance.
    assert h.run(h.plugin.tick(now="09:01")) is True


# ── 5. configuration ────────────────────────────────────────────────────────


def test_config_changes_take_effect_immediately(h):
    assert h.call_tool("word_count", text="a b c").success
    h.set_config({"max_text_length": 2})
    assert h.call_tool("word_count", text="a b c").code == "BAD_ARGUMENTS"


def test_a_config_the_plugin_never_designed_for_does_not_take_it_down(h, fuzz_config):
    """Parametrized over the SDK's fuzz set — empty, wrong types, huge, None.

    A plugin may reject any of these. What it may not do is raise out of
    `on_config_changed`, which has nowhere to put a failure: the plugin would
    then run on with the config it had and nothing anywhere would say so.
    """
    h.set_config(fuzz_config)
    assert h.health()[0] is True
    assert h.call_tool("word_count", text="ok").success


def test_a_nonsense_length_keeps_the_last_good_value(h):
    h.set_config({"max_text_length": "not a number"})
    assert h.plugin.max_text_length == 10000


# ── 6. over the wire ────────────────────────────────────────────────────────


def test_the_plugin_registers_and_answers_over_real_grpc(astra_wire):
    """Level 2. Catches what level 1 structurally cannot.

    Handler registration by wire path, the protobuf descriptor, the capability
    interceptor in its `require` stage, and the `x-session-token` on every host
    call after `Register`.
    """
    w = astra_wire(TextUtils(), config={"max_text_length": 100})

    registration = w.daemon.registrations[0]
    assert sorted(registration.capabilities) == ["actions", "tools", "triggers"]
    assert registration.sdk_name == "astra-plugin-sdk-python"

    assert [t.name for t in w.list_tools()] == ["case_convert", "regex_match", "word_count"]

    reply = w.call_tool("word_count", text="over the wire")
    assert reply.success
    assert json.loads(reply.result)["words"] == 3

    refused = w.call_tool("case_convert", text="x", mode="klingon")
    assert not refused.success
    assert refused.error.startswith("BAD_ARGUMENTS:")

    # The config the daemon sent at registration reached the plugin.
    assert w.call_tool("word_count", text="x" * 101).error.startswith("BAD_ARGUMENTS:")

    w.set_active_triggers(["on_time"])
    assert w.plugin.active_triggers == {"on_time"}
    assert w.health().healthy


# ── the harness is only as good as the defect it catches ────────────────────


def test_the_suite_catches_a_tool_that_stops_being_registered():
    """A demonstration, not a test of the plugin.

    A harness nobody has seen fail is a harness nobody should trust. Here the
    plugin is broken on purpose — one tool loses its decorator — and the same
    assertions the suite above makes are shown failing.
    """
    class _Broken(TextUtils):
        # No `@tool`: the method still exists and still works when called
        # directly, which is exactly why a unit test would not notice.
        async def regex_match(self, text: str, pattern: str):
            return {"pattern": pattern, "matches": [], "count": 0}

    with Harness(_Broken()) as h:
        assert h.tool_names() == ["case_convert", "word_count"]
        assert h.call_tool("regex_match", text="a1", pattern=r"\d").code == "NOT_FOUND"
