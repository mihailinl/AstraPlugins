"""The hooks added in production plan §5.4, exercised through the real servicer.

These go through `_CapabilityServicer` rather than calling the `Plugin` methods
directly, because the servicer is where every mistake this task exists to
prevent actually lives: the wire projection, the `oneof` precedence, the
terminating `done` chunk, the `is_last` flag, and the choice between streaming
and buffered STT. Calling `plugin.ai_complete(...)` and asserting on what it
yields would pass with all of that broken.

Run: `python -m unittest discover -s tests` from `astra-plugin-sdk-python/`.
"""

import asyncio
import unittest

import grpc

from astra_plugin_sdk import (
    AiChunk,
    AudioChunk,
    NotConfigured,
    Plugin,
    SttLoadState,
    SttLoadStatus,
)
from astra_plugin_sdk.plugin import _CapabilityServicer
from astra_plugin_sdk.proto import plugin_pb2


class FakeContext:
    """The two methods a servicer uses to fail an RPC."""

    def __init__(self):
        self.code = None
        self.details = ""

    def set_code(self, code):
        self.code = code

    def set_details(self, details):
        self.details = details


async def collect(agen):
    return [item async for item in agen]


async def feed(chunks):
    for chunk in chunks:
        yield chunk


def run(coro):
    return asyncio.run(coro)


# ── the hooks nobody implements ──────────────────────────────────────────────


class AbsentHookTest(unittest.TestCase):
    """A plugin that overrides nothing must answer UNIMPLEMENTED, which the
    daemon's `optional_hook` reads as "this hook is absent" — not as a fault."""

    def setUp(self):
        self.servicer = _CapabilityServicer(Plugin())
        self.ctx = FakeContext()

    def test_stt_lifecycle_hooks_report_absent(self):
        for call in (
            lambda: self.servicer.SttLoad(plugin_pb2.SttLoadRequest(), self.ctx),
            lambda: self.servicer.SttUnload(plugin_pb2.Empty(), self.ctx),
            lambda: self.servicer.SttGetLoadState(plugin_pb2.Empty(), self.ctx),
        ):
            with self.subTest():
                self.ctx = FakeContext()
                run(call())
                self.assertEqual(self.ctx.code, grpc.StatusCode.UNIMPLEMENTED)

    def test_tts_activate_reports_absent(self):
        run(self.servicer.TtsActivate(plugin_pb2.PluginTtsActivateRequest(), self.ctx))
        self.assertEqual(self.ctx.code, grpc.StatusCode.UNIMPLEMENTED)

    def test_ai_complete_reports_absent(self):
        chunks = run(
            collect(
                self.servicer.AiComplete(plugin_pb2.PluginAiCompleteRequest(), self.ctx)
            )
        )
        self.assertEqual(chunks, [])
        self.assertEqual(self.ctx.code, grpc.StatusCode.UNIMPLEMENTED)

    def test_tts_synthesize_stream_reports_absent(self):
        chunks = run(
            collect(
                self.servicer.TtsSynthesizeStream(
                    plugin_pb2.PluginTtsSynthesizeRequest(text="hi"), self.ctx
                )
            )
        )
        self.assertEqual(chunks, [])
        self.assertEqual(self.ctx.code, grpc.StatusCode.UNIMPLEMENTED)


# ── AI provider ──────────────────────────────────────────────────────────────


class AiProvider(Plugin):
    async def ai_complete(self, request):
        self.seen = request
        yield "Hel"
        yield "lo"
        yield AiChunk.thinking_delta("hmm")
        yield AiChunk.call("1", "get_time", "{}")


class AiCompleteTest(unittest.TestCase):
    def test_the_request_carries_reasoning_effort_and_show_reasoning(self):
        """The response half of reasoning always existed; only the request half
        was never wired. `""` must stay distinct from `"auto"`."""
        plugin = AiProvider()
        servicer = _CapabilityServicer(plugin)
        request = plugin_pb2.PluginAiCompleteRequest(
            messages=[plugin_pb2.PluginAiMessage(role="user", content="hi")],
            model="m",
            reasoning_effort="high",
            show_reasoning=True,
        )
        run(collect(servicer.AiComplete(request, FakeContext())))
        self.assertEqual(plugin.seen.reasoning_effort, "high")
        self.assertTrue(plugin.seen.show_reasoning)
        self.assertEqual(plugin.seen.messages[0].content, "hi")

    def test_a_bare_string_is_a_text_delta_and_the_stream_is_terminated(self):
        """An author's generator ends with content; the SDK appends `done`,
        because a stream that never says so leaves the daemon's reader waiting."""
        servicer = _CapabilityServicer(AiProvider())
        chunks = run(
            collect(
                servicer.AiComplete(plugin_pb2.PluginAiCompleteRequest(), FakeContext())
            )
        )
        kinds = [c.WhichOneof("content") for c in chunks]
        self.assertEqual(
            kinds, ["text_delta", "text_delta", "thinking_delta", "tool_call", "done"]
        )
        self.assertEqual(chunks[0].text_delta, "Hel")
        self.assertEqual(chunks[3].tool_call.name, "get_time")

    def test_a_failure_becomes_an_in_band_error_chunk(self):
        """`PluginAiStreamChunk` has an error slot, so a rate limit reaches the
        daemon as data instead of as a transport fault that looks like a crash."""

        class Limited(Plugin):
            async def ai_complete(self, request):
                yield "partial"
                raise NotConfigured("api_key")

        servicer = _CapabilityServicer(Limited())
        ctx = FakeContext()
        chunks = run(
            collect(servicer.AiComplete(plugin_pb2.PluginAiCompleteRequest(), ctx))
        )
        self.assertEqual(chunks[-1].WhichOneof("content"), "error")
        self.assertEqual(
            chunks[-1].error_detail.code, plugin_pb2.PLUGIN_ERROR_NOT_CONFIGURED
        )
        self.assertEqual(chunks[-1].error_detail.config_field, "api_key")
        # NOT a transport error: the daemon must not read this as the plugin
        # having no `AiComplete` hook.
        self.assertIsNone(ctx.code)


# ── TTS ──────────────────────────────────────────────────────────────────────


class StreamingTts(Plugin):
    async def tts_synthesize_stream(self, text, voice_id, speed, pitch):
        yield AudioChunk(data=b"aa", sample_rate=24000)
        yield b"bb"
        yield b"cc"


class TtsStreamTest(unittest.TestCase):
    def test_is_last_lands_on_the_real_last_chunk(self):
        """Not on an empty trailing one: the daemon's reader stops at `is_last`,
        and a flag on an empty chunk costs a round trip of silence."""
        servicer = _CapabilityServicer(StreamingTts())
        chunks = run(
            collect(
                servicer.TtsSynthesizeStream(
                    plugin_pb2.PluginTtsSynthesizeRequest(text="hi"), FakeContext()
                )
            )
        )
        self.assertEqual([c.data for c in chunks], [b"aa", b"bb", b"cc"])
        self.assertEqual([c.is_last for c in chunks], [False, False, True])
        self.assertEqual(chunks[0].sample_rate, 24000)


class TtsActivateTest(unittest.TestCase):
    def test_the_key_and_voice_reach_the_hook(self):
        seen = {}

        class Protected(Plugin):
            async def tts_activate(self, cek, voice_id):
                seen["cek"] = cek
                seen["voice_id"] = voice_id

        servicer = _CapabilityServicer(Protected())
        ctx = FakeContext()
        run(
            servicer.TtsActivate(
                plugin_pb2.PluginTtsActivateRequest(cek=b"\x01" * 32, voice_id="v"), ctx
            )
        )
        self.assertEqual(seen["cek"], b"\x01" * 32)
        self.assertEqual(seen["voice_id"], "v")
        self.assertIsNone(ctx.code)


# ── STT ──────────────────────────────────────────────────────────────────────


class StreamingStt(Plugin):
    async def stt_transcribe_stream(self, audio, options=None):
        self.options = options
        async for chunk in audio:
            yield {"text": chunk.data.decode(), "is_final": chunk.is_last}


class BufferedStt(Plugin):
    async def stt_transcribe(self, audio, sample_rate, options=None):
        self.options = options
        self.sample_rate = sample_rate
        return audio.decode()


class LegacyStt(Plugin):
    """A 0.5-era override that never heard of `options`."""

    async def stt_transcribe(self, audio, sample_rate):
        return audio.decode()


class SttProcessTest(unittest.TestCase):
    def chunks(self):
        return [
            plugin_pb2.PluginAudioChunk(
                data=b"one",
                sample_rate=16000,
                options=plugin_pb2.SttTranscribeOptions(
                    language="en", initial_prompt="astra"
                ),
            ),
            plugin_pb2.PluginAudioChunk(data=b"two", is_last=True),
        ]

    def test_the_streaming_hook_wins_and_sees_every_chunk(self):
        plugin = StreamingStt()
        servicer = _CapabilityServicer(plugin)
        events = run(collect(servicer.SttProcess(feed(self.chunks()), FakeContext())))
        self.assertEqual([e.text for e in events], ["one", "two"])
        self.assertEqual([e.is_final for e in events], [False, True])
        # The per-utterance options ride on the first chunk only, and the
        # streaming hook has to be told them before it starts decoding.
        self.assertEqual(plugin.options.language, "en")
        self.assertEqual(plugin.options.initial_prompt, "astra")

    def test_without_a_streaming_hook_the_utterance_is_buffered(self):
        plugin = BufferedStt()
        servicer = _CapabilityServicer(plugin)
        events = run(collect(servicer.SttProcess(feed(self.chunks()), FakeContext())))
        self.assertEqual([e.text for e in events], ["onetwo"])
        self.assertEqual(plugin.sample_rate, 16000)
        self.assertEqual(plugin.options.language, "en")

    def test_a_0_5_era_two_argument_override_still_works(self):
        """`options` is new in 0.6. Breaking every existing Python STT plugin
        over an argument they cannot have known about buys nothing."""
        servicer = _CapabilityServicer(LegacyStt())
        events = run(collect(servicer.SttProcess(feed(self.chunks()), FakeContext())))
        self.assertEqual([e.text for e in events], ["onetwo"])


class SttLoadStateTest(unittest.TestCase):
    def test_all_three_answer_shapes(self):
        answers = [
            (SttLoadStatus(SttLoadState.READY), plugin_pb2.SttLoadStateResponse.READY, ""),
            (SttLoadState.LOADING, plugin_pb2.SttLoadStateResponse.LOADING, ""),
            (
                (SttLoadState.FAILED, "no VRAM"),
                plugin_pb2.SttLoadStateResponse.FAILED,
                "no VRAM",
            ),
        ]
        for answer, state, detail in answers:
            with self.subTest(answer=answer):

                class Recognizer(Plugin):
                    async def stt_load_state(self):
                        return answer

                response = run(
                    _CapabilityServicer(Recognizer()).SttGetLoadState(
                        plugin_pb2.Empty(), FakeContext()
                    )
                )
                self.assertEqual(response.state, state)
                self.assertEqual(response.detail, detail)

    def test_load_gets_the_daemon_resolved_path_and_the_gpu_toggle(self):
        seen = {}

        class Recognizer(Plugin):
            async def stt_load(self, model_path, use_gpu):
                seen["path"] = model_path
                seen["gpu"] = use_gpu

        ctx = FakeContext()
        run(
            _CapabilityServicer(Recognizer()).SttLoad(
                plugin_pb2.SttLoadRequest(model_path="/m/base.bin", use_gpu=False), ctx
            )
        )
        self.assertEqual(seen, {"path": "/m/base.bin", "gpu": False})
        self.assertIsNone(ctx.code)


# ── tools and actions carry the taxonomy ─────────────────────────────────────


class ToolDispatchTest(unittest.TestCase):
    def test_a_raised_taxonomy_error_becomes_a_coded_result(self):
        """In-band, not a transport error: the AI loop has to read this."""

        class Weather(Plugin):
            async def call_tool(self, name, arguments_json):
                raise NotConfigured("api_key")

        ctx = FakeContext()
        response = run(
            _CapabilityServicer(Weather()).CallTool(
                plugin_pb2.PluginCallToolRequest(tool_name="w"), ctx
            )
        )
        self.assertFalse(response.success)
        self.assertEqual(
            response.error_detail.code, plugin_pb2.PLUGIN_ERROR_NOT_CONFIGURED
        )
        self.assertIsNone(ctx.code)

    def test_an_unknown_tool_is_not_found_not_internal(self):
        response = run(
            _CapabilityServicer(Plugin()).CallTool(
                plugin_pb2.PluginCallToolRequest(tool_name="nope"), FakeContext()
            )
        )
        self.assertFalse(response.success)
        self.assertEqual(response.error_detail.code, plugin_pb2.PLUGIN_ERROR_NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
