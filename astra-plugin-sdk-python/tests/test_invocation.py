"""**A tool call is told which conversation made it.**

The id arrives in the request BODY, not in metadata, and that is why this file
sits beside ``test_causality.py`` rather than inside it. The lease says *what
run* is calling; the invocation says *which conversation* that run belongs to.
A call may carry either, both or neither, and neither may stand in for the
other — a run that has a conversation but no lease is a real case upstream (a
nested sub-agent, or a command's "send to AI" step), not a contradiction.

The trap these exist for is specific to protobuf, and it is silent. An unset
singular message field is not ``None``: ``request.invocation`` returns a
default-constructed ``PluginInvocation``, which is truthy-adjacent enough that
``if request.invocation:`` reports EVERY call as coming from a conversation.
Only ``HasField`` answers the question actually being asked.
"""

import asyncio

import pytest

from astra_plugin_sdk import Invocation, Plugin, current_invocation, tool
from astra_plugin_sdk.invocation import invocation_from_request
from astra_plugin_sdk.proto import plugin_pb2
from astra_plugin_sdk.testing import Harness


class _Reporter(Plugin):
    @tool("Reports where it was called from")
    async def look(self):
        inv = current_invocation()
        return inv.conversation_id if inv else "none"

    @tool("Yields to the loop, then reports")
    async def look_slowly(self, ms: int = 20):
        await asyncio.sleep(ms / 1000)
        inv = current_invocation()
        return inv.conversation_id if inv else "none"


@pytest.fixture
def h():
    return Harness(_Reporter())


def test_a_conversation_in_the_body_reaches_the_handler(h):
    assert h.call_tool("look", "conv-7").result == "conv-7"


def test_no_invocation_message_means_no_conversation(h):
    assert h.call_tool("look").result == "none"


def test_an_invocation_naming_nothing_is_the_same_answer(h):
    # `""` is how a daemon spells "not from a conversation" in a message it
    # still sends. Handing a plugin an empty id would give it something that can
    # never resolve, and the two cases must be indistinguishable.
    assert h.call_tool("look", None).result == "none"


def test_an_unset_field_is_not_a_present_one():
    # The protobuf trap, asserted directly rather than only through a handler:
    # `request.invocation` is a real message even when nothing set it.
    request = plugin_pb2.PluginCallToolRequest(tool_name="look", arguments_json="{}")
    assert request.invocation is not None, "protobuf returns a default message, not None"
    assert request.HasField("invocation") is False
    assert invocation_from_request(request) is None


def test_a_request_type_without_the_field_answers_none():
    # An older generated module, or a hand-built stub in somebody's test. Not an
    # error — it is the same answer, and raising here would break a plugin whose
    # own tests predate the field.
    class _NoField:
        pass

    assert invocation_from_request(_NoField()) is None


def test_the_conversation_survives_an_await(h):
    # A ContextVar is chosen over a plain attribute precisely because a handler
    # may suspend. An attribute would be correct until two calls overlapped,
    # which is the scenario this whole design is about.
    assert h.call_tool("look_slowly", "conv-8", ms=20).result == "conv-8"


def test_concurrent_calls_do_not_read_each_others_conversation():
    # Two chats driving one plugin at once. `contextvars` copies into each task,
    # so neither call can see the other's id.
    plugin = _Reporter()
    h_a, h_b = Harness(plugin), Harness(plugin)

    a = h_a.call_tool("look_slowly", "conv-A", ms=30)
    b = h_b.call_tool("look_slowly", "conv-B", ms=5)

    assert (a.result, b.result) == ("conv-A", "conv-B")


def test_an_action_is_told_too():
    class _Actor(Plugin):
        async def execute_action(self, action_type: str, params_json: str) -> dict:
            inv = current_invocation()
            return {"success": True, "result": inv.conversation_id if inv else "none"}

    h = Harness(_Actor())
    assert h.execute_action("anything", "conv-9").result == "conv-9"
    assert h.execute_action("anything").result == "none"


def test_invocation_is_frozen():
    # It describes a call that has already arrived; nothing the plugin does can
    # change where it was called from.
    inv = Invocation(conversation_id="conv-1")
    with pytest.raises(Exception):
        inv.conversation_id = "conv-2"  # type: ignore[misc]
