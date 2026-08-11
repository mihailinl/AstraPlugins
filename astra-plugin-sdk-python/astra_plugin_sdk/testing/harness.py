"""Level 1 of the §5.6 test harness: the plugin, in this process, over the servicer.

WHAT IT TESTS THAT CALLING THE METHOD DIRECTLY DOES NOT

    plugin.word_count(text="hi")        # tests a Python function
    harness.call_tool("word_count", text="hi")   # tests a PLUGIN

Everything between the two is where plugins actually break: whether the tool is
registered under the name the daemon will use, whether its JSON Schema parses,
whether the arguments survive `json.dumps` → `json.loads`, whether the return
value can be serialised, whether the failure the handler raises becomes the code
the daemon acts on, whether the dataclass the hook returned converts to its
protobuf message. The harness calls the real `_CapabilityServicer`, so all of it
is on the path.

SYNCHRONOUS ON PURPOSE
Every method here is blocking, backed by a loop the harness owns on a background
thread. A plugin author's test is then a plain `def test_x():` — no
`pytest-asyncio`, no `@pytest.mark.asyncio`, no event-loop fixture arguments, no
"coroutine was never awaited" warning to decode. `h.run(coro)` is there for the
cases that genuinely need the loop.
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Any, Iterable

import grpc

from astra_plugin_sdk import limits
from astra_plugin_sdk.plugin import Plugin, _CapabilityServicer
from astra_plugin_sdk.proto import plugin_pb2
from astra_plugin_sdk.testing.recording_host import RecordingHost
from astra_plugin_sdk.types import AudioChunk, SttOptions

__all__ = ["Harness", "Result", "SttEvent", "HarnessError", "FakeContext"]

#: How long a blocking harness call waits for the plugin before giving up.
#: A test that hangs tells you nothing; a test that fails after five seconds
#: names the hook that hung.
DEFAULT_TIMEOUT = 5.0


class HarnessError(AssertionError):
    """The plugin failed in a way the harness was asked to treat as fatal."""


@dataclass(frozen=True)
class Result:
    """One `CallTool` / `ExecuteAction` / `CallFromUi` answer, both halves."""

    success: bool
    result: str
    error: str
    #: The structured code (`"NOT_CONFIGURED"`…), or None when the response
    #: carried no structured error — which is what an older daemon sees.
    code: str | None = None
    config_field: str = ""
    retry_after_ms: int = 0
    hint: str = ""
    doc_url: str = ""

    @property
    def json(self) -> Any:
        """`result` parsed as JSON.

        Raises `HarnessError` on a failed call rather than a `JSONDecodeError`
        on an empty string, because "the call failed and here is why" is the
        thing you want to read when a test goes red.
        """
        if not self.success:
            raise HarnessError(f"call failed: {self.error or '(no message)'}")
        if not self.result:
            return None
        try:
            return json.loads(self.result)
        except json.JSONDecodeError:
            return self.result

    def unwrap(self) -> str:
        if not self.success:
            raise HarnessError(f"call failed: {self.error or '(no message)'}")
        return self.result


@dataclass(frozen=True)
class SttEvent:
    text: str
    is_final: bool
    confidence: float
    language: str


class FakeContext:
    """The bits of `grpc.aio.ServicerContext` the SDK's servicer touches.

    Deliberately not a mock that accepts anything: the servicer is only allowed
    to use `set_code` / `set_details` / `invocation_metadata`, and if it starts
    using something else the harness should fail loudly rather than silently
    record nothing.
    """

    def __init__(self, metadata: Iterable[tuple[str, str]] = ()):
        self.code: grpc.StatusCode | None = None
        self.details: str = ""
        self._metadata = tuple(metadata)

    def set_code(self, code) -> None:
        self.code = code

    def set_details(self, details) -> None:
        self.details = details

    def invocation_metadata(self):
        return self._metadata

    @property
    def failed(self) -> bool:
        return self.code not in (None, grpc.StatusCode.OK)


def _result(response, context: FakeContext, result_field: str = "result") -> Result:
    detail = None
    for field in response.DESCRIPTOR.fields:
        if field.message_type is not None and field.name.endswith("error_detail"):
            if response.HasField(field.name):
                detail = getattr(response, field.name)
            break
    code = None
    if detail is not None:
        # The enum variant name minus its generated prefix — the same spelling
        # `ErrorCode` uses, so a test compares against `"NOT_CONFIGURED"`.
        enum_type = detail.DESCRIPTOR.fields_by_name["code"].enum_type
        name = enum_type.values_by_number[detail.code].name
        for known in ("PLUGIN_ERROR_CODE_", "PLUGIN_ERROR_"):
            if name.startswith(known):
                name = name[len(known):]
                break
        code = name
    error = response.error or (context.details if context.failed else "")
    # `PluginUiCallResponse` has no `success` field — a UI call reports failure
    # by filling in `error`, so success is the absence of one. Reading a missing
    # `success` as True is how a NOT_FOUND used to come back as a successful
    # call with an error message nobody looked at.
    success = (
        response.success
        if "success" in {f.name for f in response.DESCRIPTOR.fields}
        else not error and not context.failed
    )
    return Result(
        success=success,
        result=getattr(response, result_field, "") or "",
        error=error,
        code=code,
        config_field=detail.config_field if detail is not None else "",
        retry_after_ms=detail.retry_after_ms if detail is not None else 0,
        hint=detail.hint if detail is not None else "",
        doc_url=detail.doc_url if detail is not None else "",
    )


class Harness:
    """Drive a plugin through its own gRPC servicer, without a daemon.

        h = Harness(TextUtils()).with_config({"max_text_length": 20}).start()
        assert h.tool_names() == ["case_convert", "regex_match", "word_count"]
        assert h.call_tool("word_count", text="one two").json["words"] == 2

    `start()` is separate from `__init__` so that `with_config` /
    `with_language` / `with_capabilities` run BEFORE `on_config_changed` — a
    plugin that starts a background task from its config hook must see the
    config the test set, not a default it then has to be corrected out of.
    """

    def __init__(self, plugin: Plugin, *, timeout: float = DEFAULT_TIMEOUT):
        self.plugin = plugin
        self.host = RecordingHost()
        self.timeout = timeout
        self._config: dict = {}
        self._language = "en"
        self._started = False
        self._servicer = _CapabilityServicer(plugin)

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="astra-harness", daemon=True
        )
        self._thread.start()

    # ── setup ──

    def with_config(self, config: dict) -> "Harness":
        self._config = dict(config)
        return self

    def with_language(self, language: str) -> "Harness":
        self._language = language
        return self

    def with_host(self, host: RecordingHost) -> "Harness":
        self.host = host
        return self

    def start(self) -> "Harness":
        """Run the lifecycle the daemon runs: host → config → language.

        Same order as `Plugin._run_async` and as the Rust runner: a plugin that
        works here and not in Astra because of ordering is a harness bug, and
        this is the line that prevents it.
        """
        if self._started:
            return self
        self.plugin.host = self.host
        self.host.config_json = json.dumps(self._config)
        self.run(self._start_async())
        self._started = True
        return self

    async def _start_async(self) -> None:
        if self._config:
            await self.set_config_async(self._config)
        await self.plugin.on_language_changed(self._language)
        self.plugin.language = self._language

    def stop(self) -> None:
        """Send `Shutdown` and shut the harness loop down. Idempotent.

        Through the servicer, not by calling `on_shutdown` directly: the daemon
        sends an RPC, and a plugin whose cleanup raises must still shut down —
        the daemon is on a grace timer and kills the process group when it
        expires. A harness that let the exception out would make that path
        untestable.
        """
        if self._loop.is_closed():
            return
        try:
            if self._started:
                self.run(self._servicer.Shutdown(plugin_pb2.Empty(), FakeContext()))
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=self.timeout)
            self._loop.close()

    def __enter__(self) -> "Harness":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # ── the loop ──

    def run(self, coro, *, timeout: float | None = None):
        """Run a coroutine on the harness's loop and wait for it."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout if timeout is not None else self.timeout)

    def _drain(self, agen, *, timeout: float | None = None) -> list:
        async def collect():
            return [item async for item in agen]

        return self.run(collect(), timeout=timeout)

    # ── declarations ──

    def tools(self) -> list[plugin_pb2.PluginToolDef]:
        ctx = FakeContext()
        response = self.run(self._servicer.ListTools(plugin_pb2.Empty(), ctx))
        self._raise_if_failed(ctx, "list_tools")
        return list(response.tools)

    def tool_names(self) -> list[str]:
        return sorted(t.name for t in self.tools())

    def schema(self, tool_name: str) -> dict:
        """A tool's parameter JSON Schema, parsed.

        Fails when the tool is missing or its schema does not parse — the two
        ways a `@tool` silently does not work. The daemon hands this schema
        straight to the model, so a schema that does not parse means the tool is
        never called and nothing anywhere says why.
        """
        for tool in self.tools():
            if tool.name == tool_name:
                try:
                    schema = json.loads(tool.parameters_json or "{}")
                except json.JSONDecodeError as e:
                    raise HarnessError(
                        f"tool {tool_name!r} has a parameters_json that is not JSON: {e}"
                    ) from None
                if not isinstance(schema, dict) or schema.get("type") != "object":
                    raise HarnessError(
                        f"tool {tool_name!r} has a schema whose root is not an object; "
                        f"the model cannot produce arguments for it"
                    )
                return schema
        raise HarnessError(
            f"no tool named {tool_name!r}; this plugin declares {self.tool_names()}"
        )

    def assert_schema_accepts(self, tool_name: str, *names: str) -> None:
        """Assert a tool's schema declares each named parameter."""
        properties = self.schema(tool_name).get("properties", {})
        missing = [n for n in names if n not in properties]
        if missing:
            raise HarnessError(
                f"tool {tool_name!r} has no parameter(s) {', '.join(missing)}; "
                f"it declares {sorted(properties)}"
            )

    def actions(self) -> list[plugin_pb2.ActionTypeDefinitionMsg]:
        ctx = FakeContext()
        response = self.run(self._servicer.GetPluginActionTypes(plugin_pb2.Empty(), ctx))
        self._raise_if_failed(ctx, "get_action_types")
        return list(response.types)

    def triggers(self) -> list[plugin_pb2.TriggerTypeDefinitionMsg]:
        ctx = FakeContext()
        response = self.run(self._servicer.GetPluginTriggerTypes(plugin_pb2.Empty(), ctx))
        self._raise_if_failed(ctx, "get_trigger_types")
        return list(response.types)

    def ui_contributions(self) -> list[plugin_pb2.PluginUiContribution]:
        ctx = FakeContext()
        response = self.run(self._servicer.GetUiContributions(plugin_pb2.Empty(), ctx))
        self._raise_if_failed(ctx, "get_ui_contributions")
        return list(response.contributions)

    def voices(self) -> list[plugin_pb2.PluginVoiceInfo]:
        ctx = FakeContext()
        response = self.run(self._servicer.TtsListVoices(plugin_pb2.Empty(), ctx))
        self._raise_if_failed(ctx, "tts_list_voices")
        return list(response.voices)

    def stt_languages(self) -> list[str]:
        ctx = FakeContext()
        response = self.run(self._servicer.SttGetLanguages(plugin_pb2.Empty(), ctx))
        self._raise_if_failed(ctx, "stt_get_languages")
        return list(response.languages)

    def tts_config_fields(self) -> list[plugin_pb2.FieldDefinitionMsg]:
        ctx = FakeContext()
        response = self.run(self._servicer.TtsGetConfigFields(plugin_pb2.Empty(), ctx))
        self._raise_if_failed(ctx, "tts_config_fields")
        return list(response.config_fields)

    def stt_config_fields(self) -> list[plugin_pb2.FieldDefinitionMsg]:
        ctx = FakeContext()
        response = self.run(self._servicer.SttGetConfigFields(plugin_pb2.Empty(), ctx))
        self._raise_if_failed(ctx, "stt_config_fields")
        return list(response.config_fields)

    def _raise_if_failed(self, ctx: FakeContext, hook: str) -> None:
        if ctx.failed:
            raise HarnessError(f"{hook} failed: {ctx.code.name}: {ctx.details}")

    # ── calls ──

    def call_tool(self, name: str, /, **arguments: Any) -> Result:
        """Call a tool the way the daemon does: by name, with JSON arguments.

        The tool name is POSITIONAL-ONLY, and the `/` is load-bearing: without
        it, `h.call_tool("hello", name="Ada")` — a tool whose own parameter is
        called `name`, which is about as common as parameters get — raises
        `TypeError: got multiple values for argument 'name'` and there is no
        spelling of the call that works. Same for `action_type` and `method`
        below.
        """
        ctx = FakeContext()
        response = self.run(
            self._servicer.CallTool(
                plugin_pb2.PluginCallToolRequest(
                    tool_name=name, arguments_json=json.dumps(arguments)
                ),
                ctx,
            )
        )
        return _result(response, ctx)

    def call_tool_raw(self, name: str, arguments_json: str) -> Result:
        """Call a tool with a literal argument string — including invalid JSON.

        The model produces this string, and it is not always valid. A plugin
        that returns `BAD_ARGUMENTS` for `"{oops"` is behaving; one that raises
        past the servicer is not.
        """
        ctx = FakeContext()
        response = self.run(
            self._servicer.CallTool(
                plugin_pb2.PluginCallToolRequest(tool_name=name, arguments_json=arguments_json),
                ctx,
            )
        )
        return _result(response, ctx)

    def execute_action(self, action_type: str, /, **params: Any) -> Result:
        ctx = FakeContext()
        response = self.run(
            self._servicer.ExecuteAction(
                plugin_pb2.PluginExecuteActionRequest(
                    action_type=action_type, params_json=json.dumps(params)
                ),
                ctx,
            )
        )
        return _result(response, ctx)

    def ui_call(self, method: str, /, **params: Any) -> Result:
        """Call the plugin the way its own UI iframe does (`CallFromUi`)."""
        ctx = FakeContext()
        response = self.run(
            self._servicer.CallFromUi(
                plugin_pb2.PluginUiCallRequest(method=method, params_json=json.dumps(params)),
                ctx,
            )
        )
        return _result(response, ctx, result_field="result_json")

    def health(self) -> tuple[bool, str]:
        ctx = FakeContext()
        response = self.run(self._servicer.HealthCheck(plugin_pb2.Empty(), ctx))
        return response.healthy, response.status

    # ── lifecycle ──

    def set_config(self, config: dict) -> None:
        self.run(self.set_config_async(config))

    async def set_config_async(self, config: dict) -> None:
        ctx = FakeContext()
        self._config = dict(config)
        self.host.config_json = json.dumps(config)
        await self._servicer.OnConfigChanged(
            plugin_pb2.PluginConfigChangedMsg(config_json=json.dumps(config)), ctx
        )
        if ctx.failed:
            raise HarnessError(f"on_config_changed failed: {ctx.code.name}: {ctx.details}")

    def set_language(self, language: str) -> None:
        ctx = FakeContext()
        self.run(
            self._servicer.OnLanguageChanged(
                plugin_pb2.LanguageChangedMsg(language=language), ctx
            )
        )
        if ctx.failed:
            raise HarnessError(f"on_language_changed failed: {ctx.code.name}: {ctx.details}")

    def set_active_triggers(self, trigger_types: Iterable[str]) -> None:
        """Tell the plugin which of its triggers have a listening command.

        The plugin is meant to skip firing a trigger nobody listens to, and a
        plugin that never sees this call fires everything — which is only
        visible in a test that can make the call.
        """
        ctx = FakeContext()
        self.run(
            self._servicer.OnActiveTriggers(
                plugin_pb2.PluginActiveTriggersMsg(trigger_types=list(trigger_types)), ctx
            )
        )
        if ctx.failed:
            raise HarnessError(f"on_active_triggers failed: {ctx.code.name}: {ctx.details}")

    # ── voice ──

    def stt(
        self,
        audio: bytes | Iterable[AudioChunk | bytes],
        *,
        sample_rate: int = 16000,
        options: SttOptions | None = None,
        timeout: float | None = None,
    ) -> list[SttEvent]:
        """Transcribe, over the real `SttProcess` bidi stream.

        `audio` may be one buffer — the shape the daemon sends today — or a
        sequence of chunks, which is what a streaming plugin has to survive.
        The final chunk is flagged `is_last` for you.

        Deterministic: the chunks are fed as fast as the plugin takes them, with
        no timing, so a streaming recognizer's partial results come out in a
        fixed order.
        """
        chunks = _as_chunks(audio, sample_rate, options)

        async def collect():
            events = []
            async for event in self._servicer.SttProcess(_aiter(chunks), FakeContext()):
                events.append(
                    SttEvent(event.text, event.is_final, event.confidence, event.language)
                )
            return events

        return self.run(collect(), timeout=timeout)

    def tts(self, text: str, *, voice_id: str = "", speed: float = 1.0, pitch: float = 1.0):
        ctx = FakeContext()
        response = self.run(
            self._servicer.TtsSynthesize(
                plugin_pb2.PluginTtsSynthesizeRequest(
                    text=text, voice_id=voice_id, speed=speed, pitch=pitch
                ),
                ctx,
            )
        )
        self._raise_if_failed(ctx, "tts_synthesize")
        return response

    def tts_stream(
        self, text: str, *, voice_id: str = "", speed: float = 1.0, pitch: float = 1.0
    ) -> list[plugin_pb2.PluginAudioChunk]:
        ctx = FakeContext()
        chunks = self._drain(
            self._servicer.TtsSynthesizeStream(
                plugin_pb2.PluginTtsSynthesizeRequest(
                    text=text, voice_id=voice_id, speed=speed, pitch=pitch
                ),
                ctx,
            )
        )
        self._raise_if_failed(ctx, "tts_synthesize_stream")
        return chunks

    def ai_complete(self, request: plugin_pb2.PluginAiCompleteRequest | None = None, **kwargs):
        """Stream a completion. `kwargs` build the request when you pass none."""
        if request is None:
            messages = kwargs.pop("messages", [])
            request = plugin_pb2.PluginAiCompleteRequest(
                messages=[
                    m if not isinstance(m, dict) else plugin_pb2.PluginAiMessage(**m)
                    for m in messages
                ],
                **kwargs,
            )
        return self._drain(self._servicer.AiComplete(request, FakeContext()))


def _as_chunks(
    audio: bytes | Iterable[AudioChunk | bytes],
    sample_rate: int,
    options: SttOptions | None,
) -> list[plugin_pb2.PluginAudioChunk]:
    if isinstance(audio, (bytes, bytearray, memoryview)):
        audio = [bytes(audio)]
    out: list[plugin_pb2.PluginAudioChunk] = []
    for item in audio:
        chunk = item if isinstance(item, AudioChunk) else AudioChunk(data=bytes(item))
        if not chunk.sample_rate:
            chunk.sample_rate = sample_rate
        out.append(chunk.to_proto())
    if not out:
        out = [plugin_pb2.PluginAudioChunk(sample_rate=sample_rate)]
    # Per-utterance options ride on the first chunk only — the same place the
    # daemon puts them.
    if options is not None:
        out[0].options.CopyFrom(
            options
            if isinstance(options, plugin_pb2.SttTranscribeOptions)
            else plugin_pb2.SttTranscribeOptions(
                language=options.language, initial_prompt=options.initial_prompt
            )
        )
    out[-1].is_last = True
    return out


async def _aiter(items):
    for item in items:
        yield item


#: Re-exported so a test asserting on back-pressure does not have to import
#: `limits` separately to say what number it is asserting about.
STT_AUDIO_CHANNEL_CAPACITY = limits.STT_AUDIO_CHANNEL_CAPACITY
