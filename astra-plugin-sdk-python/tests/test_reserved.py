"""The startup assertion that a retired proto field name has not come back."""

import pytest

from astra_plugin_sdk import reserved
from astra_plugin_sdk.reserved import (
    REGISTRY,
    ReservedNameError,
    assert_no_reserved_names,
    parse_reserved_names,
    vendored_proto_text,
)


def test_the_loaded_proto_passes():
    """The shipped pair is consistent; this is the assertion `run()` makes."""
    assert_no_reserved_names() is None


def test_registry_matches_the_vendored_proto():
    """`REGISTRY` is transcribed by hand; this is what stops it rotting.

    Without this, deleting a line from `REGISTRY` would silently shrink the
    startup check to a check of nothing, and every test above would still pass.
    """
    parsed = parse_reserved_names(vendored_proto_text())
    assert parsed == dict(REGISTRY)


def test_the_parser_is_not_matching_nothing():
    """An anchor test for the parser itself.

    A regex that stops matching returns `{}`, and `{} == {}` would be a green
    test asserting the proto has no reserved names at all. Naming the count is
    the difference between a check and a formality.
    """
    parsed = parse_reserved_names(vendored_proto_text())
    assert len(parsed) == 4
    assert sum(len(v) for v in parsed.values()) == 8


def test_a_revived_reserved_name_is_refused():
    """The failure this whole module exists for.

    Simulated by injecting a field-name lookup that reports `use_thinking` as
    live — which is exactly what a stale 0.4-era `plugin_pb2` earlier on
    `sys.path` would produce.
    """
    def stale_lookup(message_name: str) -> frozenset[str]:
        if message_name == "AiSettings":
            return frozenset({"provider", "use_thinking"})
        return frozenset({"a_field_with_a_name_nobody_retired"})

    with pytest.raises(ReservedNameError) as excinfo:
        assert_no_reserved_names(live_fields=stale_lookup)
    message = str(excinfo.value)
    assert "AiSettings" in message
    assert "use_thinking" in message
    # It has to name the likely cause, or the reader has nothing to act on.
    assert "sys.path" in message


def test_a_renamed_message_fails_rather_than_scanning_nothing():
    """A registry entry the proto no longer has must not read as "all clear"."""
    with pytest.raises(ReservedNameError, match="HotkeySettings"):
        assert_no_reserved_names(
            live_fields=lambda name: None if name == "HotkeySettings" else frozenset()
        )


def test_the_real_lookup_finds_the_real_messages():
    """Guards the other direction: `_live_fields` must actually resolve them."""
    for message_name in REGISTRY:
        fields = reserved._live_fields(message_name)
        assert fields, f"{message_name} resolved to no fields at all"
