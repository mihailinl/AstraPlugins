# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Base Plugin class — subclass this to build an Astra plugin."""

import argparse
import asyncio
import inspect
import json
import logging
import os
import signal
import sys
from collections.abc import AsyncIterator
from concurrent import futures

import grpc

from astra_plugin_sdk import limits, protocol, reserved
from astra_plugin_sdk.auth import CapabilityAuthInterceptor, capability_auth_mode
from astra_plugin_sdk.causality import CauseInterceptor
from astra_plugin_sdk.capability_types import (
    ActionTypeDef,
    AiModelInfo,
    FieldDef,
    ToolDef,
    TriggerTypeDef,
    UiContribution,
    VoiceInfo,
    coerce,
)
from astra_plugin_sdk.errors import NotFound, PluginError
from astra_plugin_sdk.host_client import HostClient, HostClientBootstrap
from astra_plugin_sdk.logging_bridge import install_logging_bridge
from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc
from astra_plugin_sdk.types import (
    AiCompleteRequest,
    AudioChunk,
    SttLoadState,
    SttLoadStatus,
    SttOptions,
    coerce_ai_chunk,
    coerce_audio_chunk,
)

#: Where the SDK itself logs. Routed to the daemon by the bridge (§5.10) like
#: any other logger, so an author sees SDK diagnostics in the same pane as their
#: own without having to know this name.
log = logging.getLogger("astra_plugin_sdk")


#: The environment variable the daemon states the manifest's `[capabilities]`
#: in (§5.4).
#:
#: **Why the environment and not argv, and why this SDK is the reason.** The
#: list was briefly appended as ``--capabilities=<list>``, on the reasoning that
#: a plugin already installed on a user's machine scans argv for the prefixes it
#: knows and ignores the rest. True of the Rust and TypeScript SDKs — and false
#: of *this* one as published: 0.4.0 on PyPI calls
#: ``argparse.ArgumentParser.parse_args()``, which prints
#: ``error: unrecognized arguments: --capabilities=tools`` and calls
#: ``sys.exit(2)`` before the gRPC server binds. Every Python plugin in the
#: field would have stopped starting on daemon upgrade, and no release of this
#: package can rescue a build that is already installed. A variable a process
#: does not read cannot break it, so that is the channel.
CAPABILITIES_ENV = "ASTRA_PLUGIN_CAPABILITIES"


def _capabilities_from_env() -> list[str] | None:
    """What the daemon stated, or ``None`` if it stated nothing.

    ``[]`` and ``None`` are different answers. The daemon always sets the
    variable, empty included: empty means "this manifest declares none", and the
    variable being *absent* means the daemon predates §5.4 and the SDK should
    fall back to probing the subclass.
    """
    raw = os.environ.get(CAPABILITIES_ENV)
    if raw is None:
        return None
    return [c.strip() for c in raw.split(",") if c.strip()]


def _accepts(func, name: str) -> bool:
    """Whether `func` would accept `name` as a keyword argument."""
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):  # builtins, C callables
        return False
    if name in params:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def _overrides(plugin: "Plugin", name: str) -> bool:
    """Whether the subclass replaced `Plugin.<name>`.

    Used to choose between two hooks that answer the same rpc (streaming vs
    buffered STT) and to decide what a plugin can actually do. Comparing the
    underlying functions, not the bound methods, because bound methods compare
    unequal even when they wrap the same function.
    """
    own = getattr(type(plugin), name, None)
    base = getattr(Plugin, name, None)
    return own is not None and own is not base


class Plugin:
    """Base class for Astra plugins.

    Subclass this and override the capability methods you need::

        class MyPlugin(Plugin):
            async def list_tools(self):
                return [{"name": "hello", "description": "Say hi", "parameters_json": "{}"}]

            async def call_tool(self, name, arguments_json):
                return {"success": True, "result": "Hello!"}

        if __name__ == "__main__":
            MyPlugin().run()
    """

    def __init__(self):
        self.host: HostClient | None = None
        self.daemon = None  # DaemonClient, set if plugin has "client" capability
        self.config: dict = {}
        self.language: str = "en"
        self.active_triggers: set[str] = set()
        self._server: grpc.aio.Server | None = None
        self._log_handler = None  # PluginLogHandler, installed by `_run_async`
        self.port: int | None = None  # set once the capability server binds
        self._stop_event: asyncio.Event | None = None

        # `stt_transcribe` gained an `options` parameter in 0.6 (§5.4). Asking
        # the signature once, here, is what lets a 0.5-era two-argument override
        # keep working instead of dying with a TypeError on the first utterance.
        self._stt_transcribe_wants_options = _accepts(self.stt_transcribe, "options")

        # Auto-collect @tool / @action / @trigger / @ui_call decorated methods
        self._decorated_tools: dict[str, tuple[ToolDef, object]] = {}
        self._decorated_actions: dict[str, tuple[ActionTypeDef, object]] = {}
        self._decorated_triggers: dict[str, TriggerTypeDef] = {}
        self._ui_calls: dict[str, object] = {}
        for attr_name in dir(self):
            try:
                method = getattr(self, attr_name)
            except Exception:
                continue
            if hasattr(method, "_astra_tool_meta"):
                meta = method._astra_tool_meta
                self._decorated_tools[meta.name] = (meta, method)
            if hasattr(method, "_astra_action_meta"):
                meta = method._astra_action_meta
                self._decorated_actions[meta.type] = (meta, method)
            if hasattr(method, "_astra_trigger_meta"):
                meta = method._astra_trigger_meta
                self._decorated_triggers[meta.type] = meta
            if hasattr(method, "_astra_ui_call_meta"):
                self._ui_calls[method._astra_ui_call_meta["method"]] = method

    #: UI contributions registered by the `@ui_page` / `@ui_slot` / `@ui_effect`
    #: / `@ui_overlay` / `@ui_inject` class decorators. Class-level and replaced
    #: (never mutated) by the decorators, so a subclass cannot append into its
    #: base's list.
    _astra_ui_contributions: list[UiContribution] = []

    def run(self):
        """Parse CLI args, start gRPC server, register with daemon, serve until shutdown."""
        # BEFORE anything else, including argument parsing: if the protobuf
        # module this process loaded revives a field name the protocol retired,
        # every later step is reading the wrong thing. §5.8, `reserved.py`.
        reserved.assert_no_reserved_names()

        parser = argparse.ArgumentParser()
        parser.add_argument("--daemon-addr", required=True, help="Daemon gRPC address")
        parser.add_argument("--plugin-id", required=True, help="Plugin ID")
        parser.add_argument("--auth-token", default="", help="Auth token for registration")
        # A `--capabilities` on argv still wins if some harness passes one, but
        # the daemon does not send it — see `_capabilities_from_env`.
        parser.add_argument("--capabilities", default="", help="Comma-separated capability list")
        # Unknown flags are ignored rather than fatal: the daemon and the SDK
        # ship on different clocks, and a plugin must not die because the daemon
        # it was installed under learned a new argument.
        #
        # THIS LINE IS THE ONE THAT MATTERS. Published 0.4.0 called
        # `parser.parse_args()`, which prints `error: unrecognized arguments`
        # and calls `sys.exit(2)` — so a daemon that appended one new flag would
        # have stopped every Python plugin in the field from starting, before it
        # ever bound its gRPC port. The daemon no longer appends one; this is the
        # belt to that braces, and it is why the next new thing can be added at
        # all.
        args, extra = parser.parse_known_args()
        if extra:
            print(f"Ignoring unrecognized arguments: {' '.join(extra)}", file=sys.stderr, flush=True)

        from_argv = [c for c in args.capabilities.split(",") if c]
        # `None` and `[]` are different answers: `[]` is the daemon saying this
        # manifest declares no capabilities, `None` is nobody having said
        # anything (a daemon older than §5.4).
        capabilities = from_argv if from_argv else _capabilities_from_env()

        asyncio.run(
            self._run_async(
                args.daemon_addr,
                args.plugin_id,
                args.auth_token,
                capabilities,
            )
        )

    async def _run_async(
        self,
        daemon_addr: str,
        plugin_id: str,
        auth_token: str = "",
        declared_capabilities: list[str] | None = None,
    ):
        # The daemon's supervisor reads this process's stdout to decide the
        # plugin came up. Python block-buffers stdout when it is a pipe, so a
        # plugin that only prints would look hung and be killed at the start
        # timeout — force line buffering before the first print.
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except (AttributeError, OSError):
            pass

        # `logging` → `PluginLog`, from here on and from any thread (§5.10).
        # Installed before the port is bound so that a failure during bind or
        # registration is itself logged through the same path — those are the
        # lines an author most needs and the ones a post-registration install
        # would lose.
        self._log_handler = install_logging_bridge(self)
        self._log_handler.start()

        # SECURITY: the capability server is the daemon's way into this plugin's
        # tools, config and shutdown, and loopback separates it from nothing —
        # any process of the same user can dial the port. The guard demands the
        # daemon hand back the spawn-time `--auth-token`, which only it and this
        # process know. Staged; see `astra_plugin_sdk.auth`.
        guard = CapabilityAuthInterceptor(auth_token, capability_auth_mode())
        if not guard.active:
            print(
                "WARNING: capability server is unauthenticated — any local process can "
                "call this plugin. (No --auth-token was passed, or the check is "
                "switched off.)",
                file=sys.stderr,
                flush=True,
            )

        # Start gRPC server on random port
        # Order matters: `guard` first, so an unauthenticated call is refused
        # before anything is bound for it. `CauseInterceptor` is a no-op on every
        # call that carries no invocation lease, which today is all of them.
        self._server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=4),
            interceptors=(guard, CauseInterceptor()),
        )
        servicer = _CapabilityServicer(self)
        plugin_pb2_grpc.add_PluginCapabilityServiceServicer_to_server(servicer, self._server)

        port = self._server.add_insecure_port("127.0.0.1:0")
        #: The loopback port this plugin's capability server bound to. Published
        #: because the OS assigns it and nothing else can find it out — the
        #: level-2 harness (§5.6) dials it, and so does anyone debugging with
        #: `grpcurl`.
        self.port = port
        await self._server.start()
        print(f"Plugin gRPC server listening on port {port}", flush=True)

        # Connect to daemon and register. `Register` is the only host RPC the
        # daemon exempts from `x-session-token`, so it runs on a bootstrap
        # client; the authenticated HostClient only exists once the daemon has
        # handed back a session token.
        bootstrap = HostClientBootstrap(daemon_addr, plugin_id)
        await bootstrap.connect()

        # `is None`, not falsiness: an empty LIST is the daemon stating that this
        # plugin's manifest declares no capabilities, and probing the subclass
        # then would override the file the user consented to. Only `None` — no
        # statement at all, i.e. a daemon older than §5.4 — falls back.
        capabilities = (
            declared_capabilities
            if declared_capabilities is not None
            else await self._discover_capabilities()
        )
        print(f"Registering with capabilities: {capabilities}", flush=True)

        response, host = await bootstrap.register(port, capabilities, auth_token)

        # The protocol verdict comes BEFORE the generic refusal below: "your
        # plugin is too old for this Astra" is a different problem from "the
        # daemon said no", it has a different fix, and it gets its own exit code
        # rather than being flattened into a message the author has to interpret.
        mismatch = protocol.evaluate(response)
        if mismatch:
            print(mismatch, file=sys.stderr, flush=True)
            await bootstrap.close()
            sys.exit(protocol.EXIT_PROTOCOL_INCOMPATIBLE)

        if not response.success:
            print(f"Registration failed: {response.error}", file=sys.stderr, flush=True)
            await bootstrap.close()
            sys.exit(1)
        if host is None:
            print(
                "Registration succeeded but the daemon issued no session token; "
                "every host call would be rejected as unauthenticated",
                file=sys.stderr,
                flush=True,
            )
            await bootstrap.close()
            sys.exit(1)
        self.host = host

        print(f"Registered successfully. Daemon version: {response.daemon_version}", flush=True)
        # …and again through `logging`, which the bridge installed above turns
        # into a `PluginLog`. Two reasons it is not just the print:
        #
        # * it is this plugin's first host call, so the session token the daemon
        #   just issued is exercised on every start rather than only by the
        #   plugins that happen to log something of their own. `astra-plugin
        #   test` asserts that a plugin talked to the daemon at all, precisely
        #   so a host client that stopped authenticating cannot pass
        #   conformance while every inbound hook still answers;
        # * the bridge's stderr handler writes it unbuffered, and the daemon
        #   takes a first line on *either* stream as the readiness signal — so a
        #   plugin whose stdout is block-buffered for any reason still comes up
        #   instead of dying at the 20 s start timeout.
        log.info(
            "Registered with Astra %s (protocol %s) as '%s'",
            response.daemon_version,
            response.protocol_version,
            plugin_id,
        )

        # The daemon issues a session token to EVERY plugin (it gates the host
        # RPCs, not just the daemon API — SECURITY(B1)), so the token alone no
        # longer means "client capability" — gate on `is_client()` instead.
        # Without it a trigger-only plugin opened a DaemonClient it has no
        # permission to use and reconnected the firehose every 2 s forever.
        # Matches runner.rs (`plugin.is_client() && !token.is_empty()`) and
        # plugin.ts (`if (this.isClient())`).
        if self.is_client() and response.client_session_token:
            from astra_plugin_sdk.daemon_client import DaemonClient
            self.daemon = DaemonClient(daemon_addr, response.client_session_token)
            await self.daemon.connect()
            await self.on_daemon_client_ready(self.daemon)
            asyncio.create_task(self._chat_firehose_loop(self.daemon))
            print("DaemonClient connected (plugin has client capability)", flush=True)

        # Pass initial language
        if response.language:
            self.language = response.language
            await self.on_language_changed(response.language)

        # Pass initial config
        if response.config_json:
            self.config = json.loads(response.config_json) if response.config_json != "{}" else {}
            await self.on_config_changed(self.config)

        # Start event subscription if plugin wants events
        event_types = self.subscribed_events()
        if event_types:
            print(f"Subscribing to events: {event_types}", flush=True)
            asyncio.create_task(self._event_loop(event_types))

        # Wait for shutdown
        stop_event = asyncio.Event()
        #: Set it to make `_run_async` return. The level-2 harness (§5.6) owns
        #: the loop the plugin runs on and has no signals to send it.
        self._stop_event = stop_event

        def _signal_handler():
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except (NotImplementedError, ValueError, RuntimeError):
                # NotImplementedError: Windows has no add_signal_handler.
                # ValueError/RuntimeError: this loop is not on the main thread —
                # true of the level-2 harness, and of anyone embedding a plugin
                # in a larger process. Neither is a reason to refuse to start;
                # `_stop_event` is the portable way to stop either way.
                pass

        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            pass

        print("Shutting down...")
        await self.on_shutdown()
        await self._server.stop(grace=2)
        # Detach the log bridge from the root logger: its drain task belongs to
        # the loop that is about to go away, and a handler left behind would be
        # closed at interpreter exit against a dead loop.
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler.close()
            self._log_handler = None

    async def _discover_capabilities(self) -> list[str]:
        """Guess the capability list from what the subclass implements.

        Only reached when the daemon did not pass `--capabilities`; the manifest
        is the real answer and this is the compatibility path. It is also why
        `ai_provider` is decided by `ai_complete` being overridden rather than
        by `ai_get_models` returning something: `AiGetModels` is deprecated and
        defaults to empty, so a provider that implemented the hook that matters
        used to register without the capability that names it.
        """
        caps = []
        tools = await self.list_tools()
        if tools:
            caps.append("tools")
        voices = await self.tts_list_voices()
        if voices:
            caps.append("tts")
        langs = await self.stt_get_languages()
        if langs:
            caps.append("stt")
        models, _ = await self.ai_get_models()
        if models or _overrides(self, "ai_complete"):
            caps.append("ai_provider")
        action_types = await self.get_action_types()
        if action_types:
            caps.append("actions")
        trigger_types = await self.get_trigger_types()
        if trigger_types:
            caps.append("triggers")
        ui_contribs = await self.get_ui_contributions()
        if ui_contribs:
            caps.append("ui_contributions")
        if self.is_client():
            caps.append("client")
        return caps

    # ── Client capability ──

    def is_client(self) -> bool:
        """Override to return True if this plugin acts as a full daemon client.

        Client plugins receive a session token during registration and get
        a :class:`~astra_plugin_sdk.daemon_client.DaemonClient` with access
        to all daemon APIs (chat, voice, commands, media, etc.).
        """
        return False

    async def on_daemon_client_ready(self, client):
        """Called after registration with a DaemonClient (client plugins only).

        Override to store the client reference and start using daemon APIs.

        Args:
            client: A :class:`~astra_plugin_sdk.daemon_client.DaemonClient` instance.
        """
        pass

    # ── Capability methods (override in subclass) ──

    async def list_tools(self) -> list[ToolDef]:
        """Return tool definitions.

        If you use ``@tool`` decorators, this is auto-populated.
        Override to define tools manually (or call ``super()`` to merge both).
        Return :class:`~astra_plugin_sdk.capability_types.ToolDef` values; dicts
        still work for one more minor and warn.
        """
        return [meta for meta, _ in self._decorated_tools.values()]

    async def call_tool(self, name: str, arguments_json: str) -> dict:
        """Execute a tool.

        If you use ``@tool`` decorators, dispatch is automatic.
        Override for manual routing.
        """
        entry = self._decorated_tools.get(name)
        if entry is None:
            raise NotFound(f"Unknown tool: {name}")
        _, handler = entry
        # Exceptions are NOT swallowed here: the servicer turns them into a
        # coded `PluginError` result, so `raise NotConfigured("api_key")` inside
        # a @tool reaches the UI as a link to that field. Flattening them to
        # `str(e)` here is what made every failure look the same.
        args = json.loads(arguments_json) if arguments_json else {}
        result = await handler(**args) if inspect.iscoroutinefunction(handler) else handler(**args)
        if isinstance(result, dict):
            return {"success": True, "result": json.dumps(result)}
        return {"success": True, "result": str(result) if result is not None else ""}

    async def tts_synthesize(
        self, text: str, voice_id: str, speed: float, pitch: float
    ) -> dict:
        """Synthesize TTS. Return {audio_data: bytes, format, sample_rate, duration_ms}."""
        raise NotImplementedError

    async def tts_list_voices(self) -> list[dict]:
        """Return list of voices: [{id, name, language, gender, preview_url}]."""
        return []

    async def stt_get_languages(self) -> list[str]:
        """Return supported STT languages."""
        return []

    async def tts_config_fields(self) -> list[dict]:
        """Declare TTS settings the daemon should render on the Voice page.

        Each entry becomes one input rendered by the daemon's generic
        ``DynamicField`` component — there is no per-plugin frontend code.
        Return ``[]`` (the default) if the TTS provider has no extra settings.

        Field shape mirrors ``FieldDefinitionMsg`` (proto): keys ``id``,
        ``label``, ``field_type`` (``text`` / ``number`` / ``toggle`` /
        ``dropdown`` / ...), and optional ``placeholder``, ``default_value``,
        ``min``, ``max``, ``step``, ``has_min``, ``has_max``, ``has_step``,
        ``options`` ([{value, label}]), ``description``, ``group``.
        """
        return []

    async def stt_config_fields(self) -> list[dict]:
        """Declare STT settings the daemon should render on the Voice page.

        Same contract as :meth:`tts_config_fields` for STT settings.
        """
        return []

    async def stt_transcribe(
        self, audio: bytes, sample_rate: int, options: SttOptions | None = None
    ) -> str | dict:
        """Transcribe a complete utterance to text (non-streaming).

        The SDK accumulates every audio chunk the daemon streams over
        ``SttProcess`` and calls this once the final chunk arrives:
        ``audio`` is the concatenated PCM payload, ``sample_rate`` its
        declared rate, and ``options`` the per-utterance
        :class:`~astra_plugin_sdk.types.SttOptions` the daemon put on the first
        chunk (language hint, wake-word bias) — or ``None`` when it sent none.

        ``options`` is new in 0.6. A 0.5-era override that takes only
        ``(audio, sample_rate)`` keeps working: the servicer inspects the
        signature once at construction and only passes what the override
        accepts.

        Return either the transcript string, or a dict
        ``{text, is_final, confidence, language}`` for full control.
        Override this for an STT plugin.
        """
        raise NotImplementedError

    async def stt_transcribe_stream(
        self, audio: AsyncIterator[AudioChunk], options: SttOptions | None = None
    ):
        """Transcribe live, emitting partial results as the audio arrives.

        This is the streaming half of ``SttProcess`` and it is an **async
        generator**: consume ``audio`` and ``yield`` results as you have them.
        Overriding it takes precedence over :meth:`stt_transcribe`, which the
        SDK otherwise emulates by buffering the whole utterance.

            async def stt_transcribe_stream(self, audio, options=None):
                async for chunk in audio:
                    text = self.decoder.feed(chunk.data)
                    if text:
                        yield {"text": text, "is_final": False}
                yield {"text": self.decoder.finish(), "is_final": True}

        Yield a transcript string, or a dict
        ``{text, is_final, confidence, language}``. Back-pressure is real: the
        SDK buffers at most ``limits.STT_AUDIO_CHANNEL_CAPACITY`` chunks, the
        same bound the daemon's side of the bridge uses, so a slow recognizer
        slows the sender instead of silently losing audio.
        """
        raise NotImplementedError

    # ── STT model lifecycle ──
    #
    # Optional in the strong sense: the daemon routes all three through
    # `optional_hook`, so a plugin that manages its own models simply does not
    # override them and the daemon behaves exactly as it did before the hooks
    # existed. Implementing them is what makes idle-unload actually free VRAM.

    async def stt_load(self, model_path: str, use_gpu: bool) -> None:
        """Load the recognizer model.

        ``model_path`` is resolved by the daemon out of its own model catalog
        and download manager — a plugin that ships or downloads its own models
        ignores it. ``use_gpu`` is false on the daemon's degraded retry after a
        GPU load failed, and a plugin that honours it is the difference between
        "STT is broken" and "STT is slower today".
        """
        raise NotImplementedError

    async def stt_unload(self) -> None:
        """Drop the recognizer model and free its memory."""
        raise NotImplementedError

    async def stt_load_state(self) -> SttLoadStatus | SttLoadState | tuple:
        """Report whether the model is resident, so idle-unload can work.

        Return an :class:`~astra_plugin_sdk.types.SttLoadStatus`, a bare
        :class:`~astra_plugin_sdk.types.SttLoadState`, or ``(state, detail)``.
        Not overriding it means ``NOT_NEEDED``, which is what the daemon
        assumed before the hook existed.
        """
        raise NotImplementedError

    async def tts_synthesize_stream(
        self, text: str, voice_id: str, speed: float, pitch: float
    ):
        """Synthesize as a chunk stream, for first-audio latency.

        An **async generator**: yield :class:`~astra_plugin_sdk.types.AudioChunk`
        or raw ``bytes`` of PCM as fast as the engine produces them. Set
        ``sample_rate`` on the first chunk; the SDK marks the last one for you.

            async def tts_synthesize_stream(self, text, voice_id, speed, pitch):
                yield AudioChunk(data=first, sample_rate=24000)
                async for pcm in self.engine.stream(text):
                    yield pcm

        NOTE: no daemon call site exists for ``TtsSynthesizeStream`` yet — the
        rpc is declared and unrouted (`spec/hooks.yaml`). Implementing it costs
        nothing and is what the three SDKs agreeing looks like, but do not
        expect it to be exercised until the daemon's voice pipeline calls it.
        """
        raise NotImplementedError

    async def tts_activate(self, cek: bytes, voice_id: str) -> None:
        """Activate a licensed voice with a one-time content-encryption key.

        ``cek`` is a raw secret. Seal it under a machine-bound key and store
        that; never write it to disk in the clear and never log it. Most TTS
        plugins have no protected voice and should not override this.

        Unlike the other optional hooks the daemon does NOT treat a failure
        here as "hook absent" — it propagates, and the activation fails. Raise
        only when activation really did not happen.
        """
        raise NotImplementedError

    async def ai_complete(self, request: AiCompleteRequest):
        """Stream a model completion. The whole of the ``ai_provider`` capability.

        An **async generator**: yield
        :class:`~astra_plugin_sdk.types.AiChunk` values, or bare strings for
        plain text deltas. The SDK appends the terminating ``done`` chunk when
        your generator returns, so the last thing you yield can be content.

            async def ai_complete(self, request):
                async for token in self.client.stream(request.messages,
                                                      model=request.model):
                    yield token                      # a text delta
                yield AiChunk.call("1", "get_time", "{}")

        ``request.reasoning_effort`` is the user's thinking-budget choice as a
        string (``""`` means the daemon did not say — distinct from ``"auto"``),
        and ``request.show_reasoning`` says whether anyone will read the
        ``AiChunk.thinking_delta`` chunks you emit.
        """
        raise NotImplementedError

    async def ai_get_models(self) -> tuple[list[dict], str]:
        """Return (models_list, default_model_id).

        DEPRECATED: the daemon has no call site — ``all_ai_providers`` builds
        every plugin provider with ``supports_model_discovery: false``, so the
        model picker never asks. Kept so an existing plugin keeps compiling.
        """
        return [], ""

    async def get_action_types(self) -> list[ActionTypeDef]:
        """Return action type definitions.

        Auto-populated from ``@action`` decorators. Override to define manually.
        """
        return [meta for meta, _ in self._decorated_actions.values()]

    async def execute_action(self, action_type: str, params_json: str) -> dict:
        """Execute an action.

        Auto-dispatched to ``@action`` decorated methods.
        """
        entry = self._decorated_actions.get(action_type)
        if entry is None:
            raise NotFound(f"Unknown action: {action_type}")
        _, handler = entry
        params = json.loads(params_json) if params_json else {}
        result = await handler(**params) if inspect.iscoroutinefunction(handler) else handler(**params)
        if isinstance(result, dict):
            return {"success": True, "result": json.dumps(result)}
        return {"success": True, "result": str(result) if result is not None else ""}

    async def get_trigger_types(self) -> list[TriggerTypeDef]:
        """Return trigger type definitions.

        Auto-populated from ``@trigger`` decorators. Override to define manually.
        """
        return list(self._decorated_triggers.values())

    async def get_ui_contributions(self) -> list[UiContribution]:
        """Return UI contribution definitions (pages, effects, injections).

        Auto-populated from the ``@ui_page`` / ``@ui_slot`` / ``@ui_effect`` /
        ``@ui_overlay`` / ``@ui_inject`` class decorators. Override — and call
        ``super()`` — only when a contribution's URL or size is not known until
        runtime.
        """
        return list(self._astra_ui_contributions)

    # Convenience factories, for the plugin that computes its contributions at
    # runtime. Everything else should use the decorators: a factory's return
    # value has to be plumbed into `get_ui_contributions`, and that is the step
    # the SDK's own documented example forgot for two releases (§5.8).
    @staticmethod
    def ui_page(id: str, label: str, url: str, *, icon_svg: str = "") -> UiContribution:
        return UiContribution(id=id, slot="page.custom", label=label, url=url,
                              icon_svg=icon_svg, pointer_events=True)

    @staticmethod
    def ui_slot(slot: str, url: str, *, id: str = "", label: str = "", width: int = 0, height: int = 0) -> UiContribution:
        return UiContribution(id=id or slot, slot=slot, url=url, label=label,
                              width=width, height=height, pointer_events=True)

    @staticmethod
    def ui_effect(url: str, *, id: str = "effect", audio: bool = False) -> UiContribution:
        return UiContribution(id=id, slot="background.behind", url=url, transparent=True,
                              pointer_events=False, props={"audio": "true"} if audio else {})

    @staticmethod
    def ui_inject(css_target: str, position: str, url: str, *, id: str = "inject", width: int = 0, height: int = 0) -> UiContribution:
        return UiContribution(id=id, css_target=css_target, position=position, url=url,
                              width=width, height=height, pointer_events=True)

    @staticmethod
    def ui_overlay(id: str, url: str, *, width: int = 200, height: int = 200) -> UiContribution:
        return UiContribution(id=id, slot="overlay.floating", url=url, transparent=True,
                              pointer_events=True, width=width, height=height)

    # ── UI calls ──

    async def handle_ui_call(self, method: str, params_json: str) -> dict | str | None:
        """Handle a call from this plugin's UI iframe (``CallFromUi``).

        The default implementation dispatches to the ``@ui_call`` methods, so a
        plugin that uses the decorator never overrides this. Override it for
        manual routing; ``params_json`` is the raw JSON the iframe sent.

        Return either:

        * a dict with ``result_json`` and/or ``error`` keys — used verbatim,
          mirroring ``PluginUiCallResponse``;
        * any other dict or list — auto-serialized into ``result_json``;
        * a string — used as ``result_json`` as-is.
        """
        handler = self._ui_calls.get(method)
        if handler is None:
            raise NotFound(
                f"no UI call handler for `{method}`"
                + (
                    f" (this plugin answers: {', '.join(sorted(self._ui_calls))})"
                    if self._ui_calls
                    else " (this plugin registers none — decorate a method with @ui_call)"
                )
            )
        params = json.loads(params_json) if params_json else {}
        return await _invoke_with_params(handler, params)

    async def on_config_changed(self, config: dict):
        """Called when config changes."""
        pass

    async def on_language_changed(self, language: str):
        """Called when the daemon's UI language changes.

        Override this to update your plugin's locale (e.g., via ``I18n.set_language``).

        Args:
            language: Language code (e.g. "en", "ru", "uk").
        """
        pass

    async def on_active_triggers(self, active_types: list[str]):
        """Called when the set of active trigger types changes.

        ``self.active_triggers`` is already updated by the time this runs — the
        servicer tracks it, exactly as it does for ``config`` and ``language``,
        so an override does not need to call ``super()``.

        Args:
            active_types: Un-namespaced trigger types that have at least one
                command listening. If a type is NOT in this list, skip firing it.
        """
        pass

    async def on_shutdown(self):
        """Called on shutdown."""
        pass

    async def health_check(self) -> tuple[bool, str]:
        """Return (healthy, status_message)."""
        return True, "ok"

    # ── Convenience ──

    async def log_info(self, msg: str):
        """Log an info message to the daemon."""
        if self.host:
            await self.host.log("info", msg)

    async def log_warn(self, msg: str):
        """Log a warning message to the daemon."""
        if self.host:
            await self.host.log("warn", msg)

    async def log_error(self, msg: str):
        """Log an error message to the daemon."""
        if self.host:
            await self.host.log("error", msg)

    async def fire_trigger(self, trigger_type: str, payload: dict | None = None):
        """Fire a trigger with an optional dict payload (auto-serialized)."""
        if self.host:
            payload_json = json.dumps(payload) if payload else "{}"
            await self.host.fire_trigger(trigger_type, payload_json)

    async def push_to_ui(self, event: str, payload: dict | None = None):
        """Push an event into this plugin's own iframes — the return path for
        :meth:`handle_ui_call`. Requires the ``push_to_ui`` permission."""
        if self.host:
            payload_json = json.dumps(payload) if payload else "{}"
            await self.host.push_to_ui(event, payload_json)

    # ── Events ──

    def source_id(self) -> str:
        """Source ID used by this plugin when sending chat messages.

        Events from this source are automatically excluded by the daemon,
        so the plugin never receives its own messages back.
        Return empty string (default) for no exclusion.
        """
        return ""

    def subscribed_events(self) -> list[str]:
        """Return daemon-level event types to subscribe to. Chat events are NOT
        here — override :meth:`on_conversation_event` instead (fed by the
        conversation-log firehose).
        """
        return []

    async def on_event(self, event_type: str, payload: dict):
        """Raw daemon-event fallback. Prefer typed handlers like
        :meth:`on_state_changed` / :meth:`on_command_triggered`.
        """
        pass

    async def on_conversation_event(self, conv_id: str, event):
        """Called for every chat event in every conversation — tool calls,
        text deltas, user messages, errors, etc.

        ``conv_id`` is a UUID string. ``event`` is a ``ConversationEventMsg``
        (protobuf). Use ``event.WhichOneof('event')`` to dispatch.

        Only invoked for plugins with the ``client`` capability.
        """
        pass

    async def on_state_changed(self, event: dict):
        pass

    async def on_command_triggered(self, event: dict):
        pass

    async def on_command_completed(self, event: dict):
        pass

    async def _dispatch_event(self, event_type: str, payload: dict):
        if event_type == "state_changed":
            await self.on_state_changed(payload)
        elif event_type == "command_triggered":
            await self.on_command_triggered(payload)
        elif event_type == "command_completed":
            await self.on_command_completed(payload)
        await self.on_event(event_type, payload)

    async def _event_loop(self, event_types: list[str]):
        """Internal: subscribe to daemon host events and dispatch to typed handlers."""
        while True:
            try:
                stream = await self.host.subscribe_events(event_types)
                print("Event subscription active")
                async for event in stream:
                    try:
                        payload = json.loads(event.payload_json) if event.payload_json else {}
                    except json.JSONDecodeError:
                        payload = {}
                    await self._dispatch_event(event.event_type, payload)
                print("Event subscription stream ended, reconnecting...")
            except Exception as e:
                print(f"Event subscription error: {e}, retrying...")
            await asyncio.sleep(2)

    async def _chat_firehose_loop(self, daemon_client):
        """Internal: subscribe to the chat firehose and dispatch events."""
        while True:
            try:
                stream = daemon_client.subscribe_chat_events({})
                print("Chat firehose active")
                async for fe in stream:
                    if fe.HasField("event"):
                        await self.on_conversation_event(fe.conversation_id, fe.event)
                print("Chat firehose stream ended, reconnecting...")
            except Exception as e:
                print(f"Chat firehose error: {e}, retrying...")
            await asyncio.sleep(2)


async def _invoke_with_params(handler, params):
    """Call a decorated handler with a JSON payload.

    A handler that names its parameters gets them as keyword arguments; one that
    takes `**kwargs` or a single positional gets the whole payload. Both shapes
    are written in the wild and neither is wrong, so the SDK asks the signature
    rather than making the author guess which convention it picked.
    """
    if not isinstance(params, dict):
        result = handler(params)
    else:
        try:
            sig = inspect.signature(handler)
        except (TypeError, ValueError):
            sig = None
        takes_kwargs = sig is not None and any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        named = (
            {n for n, p in sig.parameters.items()
             if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
            if sig is not None
            else set()
        )
        if takes_kwargs or params.keys() <= named:
            result = handler(**params)
        elif len(named) == 1:
            # One positional parameter and a payload that does not match it by
            # name: the author meant "give me the object".
            result = handler(params)
        else:
            result = handler(**params)
    if inspect.isawaitable(result):
        result = await result
    return result


async def _open_stream(maybe_stream):
    """Normalise the three shapes a streaming hook can hand back.

    An `async def` with a `yield` returns an async generator immediately. An
    `async def` without one returns a coroutine — which is what the un-overridden
    base hooks are, and awaiting it is how their `NotImplementedError` reaches
    us. A coroutine that returns an iterable works too, because somebody will
    write that and it costs one line to support.
    """
    if hasattr(maybe_stream, "__aiter__"):
        return maybe_stream
    result = await maybe_stream
    if hasattr(result, "__aiter__"):
        return result
    if result is None:
        raise NotImplementedError
    return _as_async_iter(result)


async def _as_async_iter(values):
    for value in values:
        yield value


async def _with_last_marked(chunks):
    """Yield `AudioChunk`s, flagging the final one `is_last`.

    Held one behind, so the flag lands on the real last chunk instead of on an
    empty trailing one. The daemon's reader stops at `is_last`; an author who
    already set it keeps it.
    """
    pending = None
    async for value in chunks:
        chunk = coerce_audio_chunk(value)
        if pending is not None:
            yield pending
        pending = chunk
    if pending is not None:
        pending.is_last = True
        yield pending


def _stt_event(result) -> plugin_pb2.PluginSttEvent:
    """A transcript string or `{text, is_final, confidence, language}` dict."""
    if isinstance(result, str):
        result = {"text": result}
    return plugin_pb2.PluginSttEvent(
        text=result.get("text", ""),
        is_final=result.get("is_final", True),
        confidence=result.get("confidence", 1.0),
        language=result.get("language", ""),
    )


def _result_response(message_cls, result: dict):
    """Build a Call/Action response from a handler's dict.

    A handler that reports failure as a plain string gets the legacy `error`
    field and no structured detail: the SDK will not invent a code it was not
    given, because a wrong code is worse than an absent one — the daemon acts on
    codes. Raise a `PluginError` to get both halves.
    """
    return message_cls(
        success=bool(result.get("success", False)),
        result=result.get("result", "") or "",
        error=result.get("error", "") or "",
    )


def adopt(exc: BaseException, where: str) -> PluginError:
    """Turn anything a handler raised into a `PluginError`, and log the stack.

    THE POINT OF `BaseException` (production plan §5.10). Every catch site in the
    servicer used to be `except Exception`, which does not include `SystemExit`
    — so a `sys.exit(1)` inside a tool, or a library that calls it on a bad
    config, escaped the handler. In `grpc.aio` that kills the RPC task and the
    plugin answers nothing at all, for that call and for the ones after it: the
    process is alive, the daemon's health check passes, and every tool call
    times out. "The plugin stopped working and there is nothing in the logs" is
    the bug report that produces.

    `asyncio.CancelledError` is the one exception that must NOT be adopted: it
    is not a failure, it is the loop telling this coroutine to stop, and
    swallowing it turns a clean shutdown into a hang.

    The formatted traceback goes to the logger — which the §5.10 bridge routes
    into `PluginLog`, and from there into the daemon's per-plugin log file — and
    NOT into the response. The response's `error` string is read by the AI loop,
    and a Python stack trace in the model's context is noise that costs tokens
    and teaches it nothing.
    """
    if isinstance(exc, asyncio.CancelledError):
        raise exc
    error = PluginError.from_exception(exc)
    if error.detail:
        log.error("%s failed: %s\n%s", where, error.to_error_string(), error.detail)
    else:
        log.error("%s failed: %s", where, error.to_error_string())
    return error


class _CapabilityServicer(plugin_pb2_grpc.PluginCapabilityServiceServicer):
    """gRPC servicer that delegates to the Plugin instance.

    Every method here is a boundary: on this side a Python exception, on the
    other side either an in-band failure the daemon can read or a gRPC status.
    Nothing raised by a plugin handler is allowed past it — see `adopt`.
    """

    def __init__(self, plugin: Plugin):
        self.plugin = plugin

    # ── list hooks ──
    #
    # These seven answer with a repeated field and have no in-band error slot,
    # so a failure travels as a gRPC status. Returning an empty list instead
    # would be worse than an error: "this plugin has no tools" and "asking this
    # plugin for its tools raised" look identical in the UI, and only one of
    # them is a bug the author can fix.

    async def _list(self, hook, hook_name, item_cls, response_cls, field_name, context):
        try:
            values = await hook()
            items = [coerce(v, item_cls, hook_name).to_proto() for v in values or []]
        except BaseException as e:  # noqa: BLE001 — see `adopt`
            adopt(e, hook_name).abort(context)
            return response_cls()
        return response_cls(**{field_name: items})

    async def ListTools(self, request, context):
        return await self._list(
            self.plugin.list_tools, "list_tools", ToolDef,
            plugin_pb2.PluginToolListResponse, "tools", context,
        )

    async def TtsListVoices(self, request, context):
        return await self._list(
            self.plugin.tts_list_voices, "tts_list_voices", VoiceInfo,
            plugin_pb2.PluginTtsVoicesResponse, "voices", context,
        )

    async def TtsGetConfigFields(self, request, context):
        return await self._list(
            self.plugin.tts_config_fields, "tts_config_fields", FieldDef,
            plugin_pb2.PluginConfigFieldsResponse, "config_fields", context,
        )

    async def SttGetConfigFields(self, request, context):
        return await self._list(
            self.plugin.stt_config_fields, "stt_config_fields", FieldDef,
            plugin_pb2.PluginConfigFieldsResponse, "config_fields", context,
        )

    async def GetPluginActionTypes(self, request, context):
        return await self._list(
            self.plugin.get_action_types, "get_action_types", ActionTypeDef,
            plugin_pb2.PluginActionTypesResponse, "types", context,
        )

    async def GetPluginTriggerTypes(self, request, context):
        return await self._list(
            self.plugin.get_trigger_types, "get_trigger_types", TriggerTypeDef,
            plugin_pb2.PluginTriggerTypesResponse, "types", context,
        )

    async def GetUiContributions(self, request, context):
        return await self._list(
            self.plugin.get_ui_contributions, "get_ui_contributions", UiContribution,
            plugin_pb2.PluginUiContributionsResponse, "contributions", context,
        )

    async def SttGetLanguages(self, request, context):
        try:
            langs = await self.plugin.stt_get_languages()
        except BaseException as e:  # noqa: BLE001
            adopt(e, "stt_get_languages").abort(context)
            return plugin_pb2.PluginSttLanguagesResponse()
        return plugin_pb2.PluginSttLanguagesResponse(languages=list(langs or []))

    async def AiGetModels(self, request, context):
        try:
            models, default = await self.plugin.ai_get_models()
            items = [coerce(m, AiModelInfo, "ai_get_models").to_proto() for m in models or []]
        except BaseException as e:  # noqa: BLE001
            adopt(e, "ai_get_models").abort(context)
            return plugin_pb2.PluginAiModelsResponse()
        return plugin_pb2.PluginAiModelsResponse(models=items, default_model=default)

    # ── per-call hooks, in-band failures ──

    async def CallTool(self, request, context):
        # In-band, never a gRPC error: a failed tool call is data the AI loop
        # has to read. "You have no API key configured" is the model's cue to
        # tell the user what to do, and a transport error hides it from the
        # model entirely. See `astra_plugin_sdk.errors`.
        try:
            result = await self.plugin.call_tool(request.tool_name, request.arguments_json)
        except BaseException as e:  # noqa: BLE001 — every failure becomes a coded result
            return adopt(e, f"call_tool({request.tool_name})").to_response(
                plugin_pb2.PluginCallToolResponse, result=""
            )
        return _result_response(plugin_pb2.PluginCallToolResponse, result)

    async def ExecuteAction(self, request, context):
        try:
            result = await self.plugin.execute_action(request.action_type, request.params_json)
        except BaseException as e:  # noqa: BLE001 — every failure becomes a coded result
            return adopt(e, f"execute_action({request.action_type})").to_response(
                plugin_pb2.PluginExecuteActionResponse, result=""
            )
        return _result_response(plugin_pb2.PluginExecuteActionResponse, result)

    async def CallFromUi(self, request, context):
        try:
            result = await self.plugin.handle_ui_call(request.method, request.params_json)
        except BaseException as e:  # noqa: BLE001
            # The daemon relays `error_detail` on to the panel as
            # `CallPluginFromUiResponse.error_detail`, so a plugin's own UI can
            # render the same config-field link a tool failure would.
            return adopt(e, f"handle_ui_call({request.method})").to_response(
                plugin_pb2.PluginUiCallResponse, result_json=""
            )

        if result is None:
            return plugin_pb2.PluginUiCallResponse()
        if isinstance(result, str):
            return plugin_pb2.PluginUiCallResponse(result_json=result)
        if isinstance(result, dict) and ("result_json" in result or "error" in result):
            return plugin_pb2.PluginUiCallResponse(
                result_json=result.get("result_json", ""),
                error=result.get("error", ""),
            )
        # Plain payload — serialize it for the iframe.
        try:
            return plugin_pb2.PluginUiCallResponse(result_json=json.dumps(result))
        except (TypeError, ValueError) as e:
            return plugin_pb2.PluginUiCallResponse(
                error=f"handle_ui_call returned a non-serializable result: {e}"
            )

    # ── TTS ──

    async def TtsSynthesize(self, request, context):
        try:
            result = await self.plugin.tts_synthesize(
                request.text, request.voice_id, request.speed, request.pitch
            )
            return plugin_pb2.PluginTtsSynthesizeResponse(**result)
        except NotImplementedError as e:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details(str(e))
            return plugin_pb2.PluginTtsSynthesizeResponse()
        except BaseException as e:  # noqa: BLE001
            adopt(e, "tts_synthesize").abort(context)
            return plugin_pb2.PluginTtsSynthesizeResponse()

    async def TtsSynthesizeStream(self, request, context):
        """Server-streaming TTS. Unrouted daemon-side today; see the hook doc."""
        try:
            stream = await _open_stream(
                self.plugin.tts_synthesize_stream(
                    request.text, request.voice_id, request.speed, request.pitch
                )
            )
        except NotImplementedError:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details("this plugin does not stream TTS")
            return
        try:
            async for chunk in _with_last_marked(stream):
                yield chunk.to_proto()
        except BaseException as e:  # noqa: BLE001
            # No in-band failure slot on this stream, so the transport carries
            # it — the one place `grpc_status()` is the right answer.
            adopt(e, "tts_synthesize_stream").abort(context)

    async def TtsActivate(self, request, context):
        try:
            await self.plugin.tts_activate(request.cek, request.voice_id)
        except NotImplementedError:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details("this plugin has no protected voice to activate")
        except BaseException as e:  # noqa: BLE001
            # NOT routed through the daemon's `optional_hook`: a failure here
            # fails the activation rather than being read as "no such hook".
            adopt(e, "tts_activate").abort(context)
        return plugin_pb2.PluginTtsActivateResponse()

    # ── STT ──

    async def SttProcess(self, request_iterator, context):
        """Bidi STT. Streams live into `stt_transcribe_stream` when the plugin
        has one; otherwise buffers the utterance for `stt_transcribe`."""
        if _overrides(self.plugin, "stt_transcribe_stream"):
            async for event in self._stt_streaming(request_iterator, context):
                yield event
            return

        # Accumulate the utterance. The daemon currently sends a single
        # f32-LE PCM buffer flagged `is_last`, but a future caller may split
        # it across chunks — drain until `is_last` or end-of-stream either way.
        audio = bytearray()
        sample_rate = 0
        options: SttOptions | None = None
        async for chunk in request_iterator:
            if sample_rate == 0:
                sample_rate = chunk.sample_rate
            if options is None:
                # Per-utterance decoding options ride on the first chunk only.
                parsed = AudioChunk.from_proto(chunk)
                options = parsed.options
            audio.extend(chunk.data)
            if chunk.is_last:
                break

        # Non-streaming transcription: one `stt_transcribe` call, one event.
        try:
            if self.plugin._stt_transcribe_wants_options:
                result = await self.plugin.stt_transcribe(
                    bytes(audio), sample_rate, options
                )
            else:
                result = await self.plugin.stt_transcribe(bytes(audio), sample_rate)
        except NotImplementedError as e:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details(str(e) or "STT not implemented")
            return
        except BaseException as e:  # noqa: BLE001
            adopt(e, "stt_transcribe").abort(context)
            return

        yield _stt_event(result)

    async def _stt_streaming(self, request_iterator, context):
        """Feed `stt_transcribe_stream` while it emits partial results.

        Two coroutines: a pump draining the inbound gRPC stream into a bounded
        queue, and the plugin's generator reading it. The bound is
        `limits.STT_AUDIO_CHANNEL_CAPACITY` — the same number the daemon's half
        of the bridge uses, because the smaller of two channels in series is the
        real capacity and a smaller SDK-side buffer is exactly how streaming STT
        once lost everything past the first fraction of an utterance.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=limits.STT_AUDIO_CHANNEL_CAPACITY)
        options: SttOptions | None = None
        first_seen = asyncio.Event()

        async def pump():
            nonlocal options
            try:
                async for msg in request_iterator:
                    chunk = AudioChunk.from_proto(msg)
                    if not first_seen.is_set():
                        options = chunk.options
                        first_seen.set()
                    await queue.put(chunk)
                    if chunk.is_last:
                        break
            finally:
                first_seen.set()
                await queue.put(None)

        async def audio():
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item

        pump_task = asyncio.create_task(pump())
        try:
            # The hook takes the options up front, so wait for the first chunk
            # (or for the stream to end without one) before calling it.
            await first_seen.wait()
            stream = await _open_stream(
                self.plugin.stt_transcribe_stream(audio(), options)
            )
            async for result in stream:
                yield _stt_event(result)
        except NotImplementedError:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details("STT not implemented")
        except BaseException as e:  # noqa: BLE001
            adopt(e, "stt_transcribe_stream").abort(context)
        finally:
            pump_task.cancel()

    async def SttLoad(self, request, context):
        try:
            await self.plugin.stt_load(request.model_path, request.use_gpu)
        except NotImplementedError:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details("this plugin has no explicit STT model lifecycle")
        except BaseException as e:  # noqa: BLE001
            adopt(e, "stt_load").abort(context)
        return plugin_pb2.Empty()

    async def SttUnload(self, request, context):
        try:
            await self.plugin.stt_unload()
        except NotImplementedError:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details("this plugin has no explicit STT model lifecycle")
        except BaseException as e:  # noqa: BLE001
            adopt(e, "stt_unload").abort(context)
        return plugin_pb2.Empty()

    async def SttGetLoadState(self, request, context):
        try:
            state = await self.plugin.stt_load_state()
        except NotImplementedError:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details("this plugin has no explicit STT model lifecycle")
            return plugin_pb2.SttLoadStateResponse()
        except BaseException as e:  # noqa: BLE001
            adopt(e, "stt_load_state").abort(context)
            return plugin_pb2.SttLoadStateResponse()
        # Accept the three shapes the hook documents: a status, a bare state,
        # or `(state, detail)`.
        try:
            if isinstance(state, SttLoadStatus):
                return state.to_proto()
            if isinstance(state, tuple):
                return SttLoadStatus(SttLoadState(state[0]), str(state[1])).to_proto()
            return SttLoadStatus(SttLoadState(state)).to_proto()
        except BaseException as e:  # noqa: BLE001
            adopt(e, "stt_load_state").abort(context)
            return plugin_pb2.SttLoadStateResponse()

    # ── AI provider ──

    async def AiComplete(self, request, context):
        try:
            req = AiCompleteRequest.from_proto(request)
            stream = await _open_stream(self.plugin.ai_complete(req))
        except NotImplementedError:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details("this plugin is not an AI provider")
            return
        except BaseException as e:  # noqa: BLE001
            yield adopt(e, "ai_complete").to_response(plugin_pb2.PluginAiStreamChunk)
            return

        last: plugin_pb2.PluginAiStreamChunk | None = None
        try:
            async for value in stream:
                last = coerce_ai_chunk(value).to_proto()
                yield last
        except BaseException as e:  # noqa: BLE001
            # `PluginAiStreamChunk` HAS an in-band error slot, so the failure
            # travels as data the daemon's bridge already reads, rather than as
            # a transport fault that would look like the plugin dying. The
            # `error` oneof arm and the structured `error_detail` beside it are
            # both set: the oneof is what tells a receiver the stream ended
            # badly, and an old daemon reads only that.
            yield adopt(e, "ai_complete").to_response(plugin_pb2.PluginAiStreamChunk)
            return

        # Terminate the stream for the author: a completion that never says
        # `done` leaves the daemon's reader waiting on a stream that has already
        # closed, and forgetting it is the easiest mistake to make here.
        if last is None or last.WhichOneof("content") not in ("done", "error"):
            yield plugin_pb2.PluginAiStreamChunk(done=True)

    # ── lifecycle ──
    #
    # These four answer `Empty` and have nowhere to put a failure, which is
    # exactly why they used to be unprotected: a raise in `on_config_changed`
    # escaped as an UNKNOWN status the daemon logged as a transport fault, and
    # the plugin then ran on with stale config and no visible cause. Now the
    # SDK's own state is updated first, the hook is called second, and a raise
    # is reported with the code the author raised.

    async def OnConfigChanged(self, request, context):
        try:
            config = json.loads(request.config_json) if request.config_json else {}
            self.plugin.config = config
            await self.plugin.on_config_changed(config)
        except BaseException as e:  # noqa: BLE001
            adopt(e, "on_config_changed").abort(context)
        return plugin_pb2.Empty()

    async def OnActiveTriggers(self, request, context):
        active_types = list(request.trigger_types)
        self.plugin.active_triggers = set(active_types)
        try:
            await self.plugin.on_active_triggers(active_types)
        except BaseException as e:  # noqa: BLE001
            adopt(e, "on_active_triggers").abort(context)
        return plugin_pb2.Empty()

    async def OnLanguageChanged(self, request, context):
        self.plugin.language = request.language
        try:
            await self.plugin.on_language_changed(request.language)
        except BaseException as e:  # noqa: BLE001
            adopt(e, "on_language_changed").abort(context)
        return plugin_pb2.Empty()

    async def Shutdown(self, request, context):
        # Stopping the SERVER is not stopping the PROCESS. `_run_async` is
        # parked on `_stop_event.wait()`, and until that event is set the
        # interpreter stays alive with nothing left to serve — the daemon's
        # grace timer then expires and SIGKILLs the process group, so the
        # plugin's tidy path never runs on a user's machine. Releasing the
        # event here is what makes `Shutdown` mean "exit".
        #
        # `call_later` rather than `set()`: this handler's response has to
        # reach the daemon before `_run_async` tears the server down under it.
        loop = asyncio.get_running_loop()
        if self.plugin._stop_event is not None:
            # `_run_async` owns the tidy path (on_shutdown, server stop, log
            # bridge). Running `on_shutdown` here as well would run it twice.
            loop.call_later(0.1, self.plugin._stop_event.set)
            return plugin_pb2.Empty()

        # No run loop behind this servicer — a level-1 harness drives it
        # directly, or the plugin is embedded. Nobody else will do the tidying,
        # so do it here.
        #
        # A failing `on_shutdown` must not stop the shutdown: the daemon is
        # waiting on a grace timer and will kill the process group when it
        # expires, so swallowing the error here is the difference between a
        # clean stop and a SIGKILL in the user's log.
        try:
            await self.plugin.on_shutdown()
        except BaseException as e:  # noqa: BLE001
            adopt(e, "on_shutdown")
        if self.plugin._server is not None:
            loop.call_later(0.1, lambda: asyncio.ensure_future(
                self.plugin._server.stop(grace=1)
            ))
        return plugin_pb2.Empty()

    async def HealthCheck(self, request, context):
        try:
            healthy, status = await self.plugin.health_check()
        except BaseException as e:  # noqa: BLE001
            # An unhealthy answer, not a transport error: the daemon's health
            # probe reads `healthy`, and a status code makes it look like the
            # plugin is gone when in fact it answered.
            error = adopt(e, "health_check")
            return plugin_pb2.PluginHealthResponse(
                healthy=False, status=error.to_error_string()
            )
        return plugin_pb2.PluginHealthResponse(healthy=healthy, status=status)
