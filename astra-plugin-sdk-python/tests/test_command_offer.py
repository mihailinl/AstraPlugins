"""`commands_from_astra_file`, held to `testdata/astra-file/vectors.json` — the
same file the other two SDKs read.

The helper splits a `.astra` file (what Astra's Commands page exports) into the
portable commands a plugin offers with ``host.propose_command``, one at a time.
A per-SDK test would pin each implementation to itself; this one reads the
shared vectors, so the question it answers is "do the three agree".

The floors come first: a vectors file that failed to load, or that somebody
emptied, must fail as that and not pass as a clean run.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from astra_plugin_sdk import commands_from_astra_file
from astra_plugin_sdk.host_client import _ASTRA_FILE_LOCAL_FIELDS

#: `testdata/` sits at the repository root, two levels up from this file. It is
#: not shipped inside the wheel — the vectors are shared with the Rust and
#: TypeScript SDKs — so a run from a checkout is the only run that can execute
#: them.
VECTORS = pathlib.Path(__file__).resolve().parents[2] / "testdata" / "astra-file" / "vectors.json"

DOC = json.loads(VECTORS.read_text(encoding="utf-8"))
ACCEPTED = DOC["accepted"]
REFUSED = DOC["refused"]
UNSAFE_INTEGERS = DOC["unsafe_integers"]


def test_the_vectors_carry_enough_cases():
    assert len(ACCEPTED) >= 3
    assert len(REFUSED) >= 10
    assert len(UNSAFE_INTEGERS) >= 2


def test_the_drop_list_is_the_vectors_own():
    """Not a subset, not a superset: the members this helper drops are exactly
    the ones the shared vectors name."""
    assert list(_ASTRA_FILE_LOCAL_FIELDS) == DOC["local_fields"]


@pytest.mark.parametrize("case", ACCEPTED, ids=[c["name"] for c in ACCEPTED])
def test_every_accepted_vector_gives_exactly_its_commands(case):
    assert commands_from_astra_file(case["text"]) == case["commands"]


@pytest.mark.parametrize("case", REFUSED, ids=[c["name"] for c in REFUSED])
def test_every_refused_vector_is_an_error_that_says_why(case):
    with pytest.raises(ValueError) as refused:
        commands_from_astra_file(case["text"])
    message = str(refused.value)
    assert message.startswith("not a .astra"), message
    assert case["mentions"] in message, message


@pytest.mark.parametrize("case", UNSAFE_INTEGERS, ids=[c["name"] for c in UNSAFE_INTEGERS])
def test_numbers_a_javascript_number_cannot_hold_are_read_exactly(case):
    """Python reads them exactly (the TypeScript helper refuses them rather
    than round); the value offered is the value written."""
    assert commands_from_astra_file(case["text"]) == case["commands"]


def test_two_to_the_53_plus_one_stays_itself():
    text = '{"format":"astra-commands","version":1,"commands":[{"priority":9007199254740993}]}'
    [command] = commands_from_astra_file(text)
    assert command["priority"] == 9007199254740993
    assert isinstance(command["priority"], int)


def test_a_file_nested_too_deep_is_the_documented_value_error():
    deep = "[" * 100_000 + "]" * 100_000
    text = '{"format":"astra-commands","version":1,"commands":[{"x":' + deep + "}]}"
    with pytest.raises(ValueError, match="^not a .astra file: it is not JSON"):
        commands_from_astra_file(text)


def test_every_local_member_is_removed_and_only_at_the_top_level():
    local = DOC["local_fields"]
    command = {name: "x" for name in local}
    command["name"] = "kept"
    command["actions"] = [{"id": "an action's own id", "type": "noop"}]
    text = json.dumps({"format": "astra-commands", "version": 1, "commands": [command]})
    assert commands_from_astra_file(text) == [
        {"name": "kept", "actions": [{"id": "an action's own id", "type": "noop"}]}
    ]

