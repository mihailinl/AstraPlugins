"""**A tool can ask for the pictures the person attached, and read them.**

Two halves, each at both levels: a tool's ``wants_attachments`` must reach
``ListTools`` (``False`` on every other tool, so nothing changes for a plugin
that never heard of it), and the pictures on
``PluginCallToolRequest.attachments`` must reach ``current_attachments()`` with
their bytes, type and name intact.

Level 2 matters for the second half: the pictures are read off a
protobuf-decoded request, and ``bytes`` that arrive as something else, or a
field read by the wrong name, make a tool that silently never sees one.
"""

import asyncio
import json

from astra_plugin_sdk import AiImage, Plugin, ToolDef, current_attachments, tool
from astra_plugin_sdk.attachments import attachments_from_request
from astra_plugin_sdk.proto import plugin_pb2
from astra_plugin_sdk.testing import Harness, WireHarness

PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 1, 2, 255])
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0, 7, 7, 7])

SENT = [
    AiImage(mime_type="image/png", data=PNG, filename="cat.png"),
    AiImage(mime_type="image/jpeg", data=JPEG, filename="dog.jpg"),
]

EXPECTED = [
    {"mime_type": "image/png", "filename": "cat.png", "data": list(PNG), "is_bytes": True},
    {"mime_type": "image/jpeg", "filename": "dog.jpg", "data": list(JPEG), "is_bytes": True},
]


class _Photos(Plugin):
    @tool("Describe the pictures the person attached", wants_attachments=True)
    async def describe(self):
        return {
            "seen": [
                {
                    "mime_type": a.mime_type,
                    "filename": a.filename,
                    "data": list(a.data),
                    "is_bytes": isinstance(a.data, bytes),
                }
                for a in current_attachments()
            ]
        }

    @tool("Echo a string back")
    async def plain(self, text: str):
        return f"{text}:{len(current_attachments())}"

    @tool("Yields, then names its first picture", wants_attachments=True)
    async def first_slowly(self, ms: int = 20):
        await asyncio.sleep(ms / 1000)
        photos = current_attachments()
        return photos[0].filename if photos else "none"


# ── declaring ────────────────────────────────────────────────────────────────


def test_the_decorator_flag_reaches_list_tools_and_defaults_to_false():
    h = Harness(_Photos())
    flags = {t.name: t.wants_attachments for t in h.tools()}
    assert flags == {"describe": True, "plain": False, "first_slowly": True}


def test_a_hand_written_tooldef_carries_the_flag_and_an_old_one_still_converts():
    asked = ToolDef(name="look", description="Look.", wants_attachments=True)
    assert asked.to_proto().wants_attachments is True
    # Every ToolDef written before the field still builds, and says "no".
    old = ToolDef(name="old", description="Old.", parameters_json="{}")
    assert old.to_proto().wants_attachments is False
    assert ToolDef.from_proto(asked.to_proto()) == asked


# ── receiving, level 1 ───────────────────────────────────────────────────────


def test_attachments_reach_the_handler_with_bytes_type_and_name_intact():
    h = Harness(_Photos())
    r = h.call_tool("describe", "conv-1", SENT)
    assert r.success, r.error
    assert json.loads(r.result)["seen"] == EXPECTED


def test_a_call_that_carries_none_reads_an_empty_list():
    h = Harness(_Photos())
    assert json.loads(h.call_tool("describe").result)["seen"] == []


def test_a_tool_without_the_flag_still_works():
    h = Harness(_Photos())
    r = h.call_tool("plain", text="hi")
    assert r.success and r.result == "hi:0"


def test_concurrent_calls_do_not_read_each_others_pictures():
    # One plugin object serves every call; a field on it would be shared. The
    # contextvar is per task, which is the only scope that can be right.
    h = Harness(_Photos())

    async def both():
        servicer = h._servicer
        a = servicer.CallTool(
            plugin_pb2.PluginCallToolRequest(
                tool_name="first_slowly",
                arguments_json="{}",
                attachments=[SENT[0].to_proto()],
            ),
            None,
        )
        b = servicer.CallTool(
            plugin_pb2.PluginCallToolRequest(
                tool_name="first_slowly",
                arguments_json="{}",
                attachments=[SENT[1].to_proto()],
            ),
            None,
        )
        c = servicer.CallTool(
            plugin_pb2.PluginCallToolRequest(tool_name="first_slowly", arguments_json="{}"),
            None,
        )
        return await asyncio.gather(
            asyncio.ensure_future(a), asyncio.ensure_future(b), asyncio.ensure_future(c)
        )

    ra, rb, rc = h.run(both())
    assert (ra.result, rb.result, rc.result) == ("cat.png", "dog.jpg", "none")


def test_a_request_without_the_field_has_no_attachments():
    class _Old:
        pass

    assert attachments_from_request(_Old()) == []
    assert attachments_from_request(plugin_pb2.PluginCallToolRequest()) == []


# ── level 2 ──────────────────────────────────────────────────────────────────


def test_over_the_wire_the_flag_is_in_list_tools():
    with WireHarness(_Photos()) as w:
        flags = {t.name: t.wants_attachments for t in w.list_tools()}
        assert flags == {"describe": True, "plain": False, "first_slowly": True}


def test_over_the_wire_the_pictures_reach_the_handler_intact():
    with WireHarness(_Photos()) as w:
        reply = w.call_tool("describe", _conversation_id="conv-7", _attachments=SENT)
        assert reply.success, reply.error
        assert json.loads(reply.result)["seen"] == EXPECTED


def test_over_the_wire_a_tool_without_the_flag_still_works():
    with WireHarness(_Photos()) as w:
        reply = w.call_tool("plain", text="yo")
        assert reply.success and reply.result == "yo:0"
