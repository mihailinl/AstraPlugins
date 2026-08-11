"""The seven capability types: conversion, dict compatibility, and the warning."""

import warnings

import pytest

from astra_plugin_sdk import (
    ActionTypeDef,
    AiModelInfo,
    DropdownOption,
    Field,
    FieldCondition,
    FieldDef,
    Plugin,
    ToolDef,
    TriggerTypeDef,
    UiContribution,
    VoiceInfo,
    action,
    tool,
    trigger,
)
from astra_plugin_sdk.capability_types import coerce, coerce_all
from astra_plugin_sdk.proto import plugin_pb2
from astra_plugin_sdk.testing import Harness

SEVEN = [ToolDef, VoiceInfo, AiModelInfo, FieldDef, ActionTypeDef, TriggerTypeDef, UiContribution]


@pytest.mark.parametrize("cls", SEVEN, ids=lambda c: c.__name__)
def test_every_capability_type_round_trips_through_its_message(cls):
    """`from_proto(to_proto(x)) == x` for a default-constructed value.

    The cheap version of the property that matters: every field the dataclass
    declares must exist on the message and survive the trip. A field added to
    the dataclass and forgotten in `to_proto` fails here.
    """
    original = cls()
    assert cls.from_proto(original.to_proto()) == original


@pytest.mark.parametrize("cls", SEVEN, ids=lambda c: c.__name__)
def test_dataclass_fields_match_the_proto_message(cls):
    """No dataclass field that the generated message does not have.

    This is the check that catches a dataclass drifting from a regenerated
    proto slice — the reason these types exist at all.
    """
    proto_fields = {f.name for f in cls._PROTO.DESCRIPTOR.fields}
    declared = set(cls.__dataclass_fields__)
    assert declared <= proto_fields, f"{cls.__name__} declares fields the proto lacks: {declared - proto_fields}"


def test_populated_values_survive_the_round_trip():
    field = FieldDef(
        id="mode",
        label="Mode",
        field_type="dropdown",
        options=[DropdownOption("a", "A"), DropdownOption("b", "B")],
        conditions=[FieldCondition("other", "not_empty")],
        has_min=True,
        min=1.0,
    )
    definition = ActionTypeDef(type="do", label="Do", fields=[field], ai_available=True)
    assert ActionTypeDef.from_proto(definition.to_proto()) == definition


def test_dict_is_accepted_and_warns_once_naming_the_hook():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = coerce({"name": "hello", "description": "hi"}, ToolDef, "list_tools")
    assert result == ToolDef(name="hello", description="hi")
    assert len(caught) == 1
    assert issubclass(caught[0].category, DeprecationWarning)
    assert "list_tools" in str(caught[0].message)
    assert "ToolDef" in str(caught[0].message)


def test_a_typo_in_a_legacy_dict_names_the_key_and_the_alternatives():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(TypeError) as excinfo:
            coerce({"preview_ur": "x"}, VoiceInfo, "tts_list_voices")
    assert "preview_ur" in str(excinfo.value)
    assert "preview_url" in str(excinfo.value)


def test_nested_legacy_dicts_are_converted_not_dropped():
    """`Msg(**d)` never built sub-messages; that was the bespoke-converter bug."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        field = coerce(
            {
                "id": "mode",
                "label": "Mode",
                "field_type": "dropdown",
                "options": [{"value": "a", "label": "A"}],
                "conditions": [{"field_id": "x", "operator": "not_empty"}],
            },
            FieldDef,
            "stt_config_fields",
        )
    message = field.to_proto()
    assert [o.value for o in message.options] == ["a"]
    assert [c.field_id for c in message.conditions] == ["x"]


def test_a_raw_generated_message_is_accepted_too():
    message = plugin_pb2.PluginToolDef(name="raw")
    assert coerce(message, ToolDef, "list_tools").name == "raw"


def test_something_that_is_neither_is_a_clear_TypeError():
    with pytest.raises(TypeError, match="list_tools"):
        coerce(42, ToolDef, "list_tools")


def test_coerce_all_tolerates_none():
    assert coerce_all(None, ToolDef, "list_tools") == []


# ── the SDK's own helpers must not trip its own deprecation ─────────────────


class _Decorated(Plugin):
    @tool("Say hello")
    async def hello(self, name: str): ...

    @action("Do it", fields=[Field.dropdown("mode", "Mode", options=["a", "b"])])
    async def do_it(self, mode: str = "a"): ...

    @trigger("Tick", fields=[Field.number("every", "Every", min=1, max=60)])
    def tick(self): ...


def test_the_sdk_helpers_produce_dataclasses_and_never_warn():
    """`@tool` + `Field` returning dicts would make the SDK warn about itself.

    A deprecation the author cannot act on is noise that teaches them to ignore
    deprecations, so the SDK's own builders had to move first.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        with Harness(_Decorated()) as h:
            assert h.tool_names() == ["hello"]
            assert [a.type for a in h.actions()] == ["do_it"]
            assert [t.type for t in h.triggers()] == ["tick"]
            options = h.actions()[0].fields[0].options
            assert [o.value for o in options] == ["a", "b"]
            number = h.triggers()[0].fields[0]
            assert (number.has_min, number.min, number.has_max, number.max) == (
                True,
                1.0,
                True,
                60.0,
            )


def test_field_number_without_bounds_says_so():
    """`min=0` and "no minimum" are the same bytes without `has_min`."""
    plain = Field.number("n", "N")
    assert (plain.has_min, plain.has_max, plain.has_step) == (False, False, False)


class _LegacyDicts(Plugin):
    """A plugin written against 0.5, returning dicts from every hook."""

    async def list_tools(self):
        return [{"name": "legacy", "description": "d", "parameters_json": "{}"}]

    async def tts_list_voices(self):
        return [{"id": "v", "name": "V", "language": "en"}]

    async def get_ui_contributions(self):
        return [{"id": "p", "slot": "page.custom", "label": "P", "url": "u"}]


def test_a_05_era_plugin_still_works_and_says_what_to_change():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with Harness(_LegacyDicts()) as h:
            assert h.tool_names() == ["legacy"]
            assert h.voices()[0].id == "v"
            assert h.ui_contributions()[0].label == "P"
    messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("list_tools" in m for m in messages)
    assert any("tts_list_voices" in m for m in messages)
    assert any("get_ui_contributions" in m for m in messages)
