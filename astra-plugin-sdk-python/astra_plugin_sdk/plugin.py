"""Base Plugin class — subclass this to build an Astra plugin."""

import argparse
import asyncio
import json
import signal
import sys
from concurrent import futures

import grpc

from astra_plugin_sdk import protocol
from astra_plugin_sdk.auth import CapabilityAuthInterceptor, capability_auth_mode
from astra_plugin_sdk.host_client import HostClient, HostClientBootstrap
from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc


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

        # Auto-collect @tool / @action / @trigger decorated methods
        self._decorated_tools: dict[str, tuple[dict, object]] = {}
        self._decorated_actions: dict[str, tuple[dict, object]] = {}
        self._decorated_triggers: dict[str, dict] = {}
        for attr_name in dir(self):
            try:
                method = getattr(self, attr_name)
            except Exception:
                continue
            if hasattr(method, "_astra_tool_meta"):
                meta = method._astra_tool_meta
                self._decorated_tools[meta["name"]] = (meta, method)
            if hasattr(method, "_astra_action_meta"):
                meta = method._astra_action_meta
                self._decorated_actions[meta["type"]] = (meta, method)
            if hasattr(method, "_astra_trigger_meta"):
                meta = method._astra_trigger_meta
                self._decorated_triggers[meta["type"]] = meta

    def run(self):
        """Parse CLI args, start gRPC server, register with daemon, serve until shutdown."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--daemon-addr", required=True, help="Daemon gRPC address")
        parser.add_argument("--plugin-id", required=True, help="Plugin ID")
        parser.add_argument("--auth-token", default="", help="Auth token for registration")
        args = parser.parse_args()

        asyncio.run(self._run_async(args.daemon_addr, args.plugin_id, args.auth_token))

    async def _run_async(self, daemon_addr: str, plugin_id: str, auth_token: str = ""):
        # The daemon's supervisor reads this process's stdout to decide the
        # plugin came up. Python block-buffers stdout when it is a pipe, so a
        # plugin that only prints would look hung and be killed at the start
        # timeout — force line buffering before the first print.
        try:
            sys.stdout.reconfigure(line_buffering=True)
        except (AttributeError, OSError):
            pass

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
        self._server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=4), interceptors=(guard,)
        )
        servicer = _CapabilityServicer(self)
        plugin_pb2_grpc.add_PluginCapabilityServiceServicer_to_server(servicer, self._server)

        port = self._server.add_insecure_port("127.0.0.1:0")
        await self._server.start()
        print(f"Plugin gRPC server listening on port {port}", flush=True)

        # Connect to daemon and register. `Register` is the only host RPC the
        # daemon exempts from `x-session-token`, so it runs on a bootstrap
        # client; the authenticated HostClient only exists once the daemon has
        # handed back a session token.
        bootstrap = HostClientBootstrap(daemon_addr, plugin_id)
        await bootstrap.connect()

        capabilities = await self._discover_capabilities()
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

        def _signal_handler():
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            pass

        print("Shutting down...")
        await self.on_shutdown()
        await self._server.stop(grace=2)

    async def _discover_capabilities(self) -> list[str]:
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
        if models:
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

    async def list_tools(self) -> list[dict]:
        """Return tool definitions.

        If you use ``@tool`` decorators, this is auto-populated.
        Override to define tools manually (or call ``super()`` to merge both).
        """
        return [meta for meta, _ in self._decorated_tools.values()]

    async def call_tool(self, name: str, arguments_json: str) -> dict:
        """Execute a tool.

        If you use ``@tool`` decorators, dispatch is automatic.
        Override for manual routing.
        """
        entry = self._decorated_tools.get(name)
        if entry is None:
            return {"success": False, "result": "", "error": f"Unknown tool: {name}"}
        _, handler = entry
        try:
            args = json.loads(arguments_json) if arguments_json else {}
            result = await handler(**args) if asyncio.iscoroutinefunction(handler) else handler(**args)
            if isinstance(result, dict):
                return {"success": True, "result": json.dumps(result)}
            return {"success": True, "result": str(result) if result is not None else ""}
        except Exception as e:
            return {"success": False, "result": "", "error": str(e)}

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

    async def stt_transcribe(self, audio: bytes, sample_rate: int) -> str | dict:
        """Transcribe a complete utterance to text (non-streaming).

        The SDK accumulates every audio chunk the daemon streams over
        ``SttProcess`` and calls this once the final chunk arrives:
        ``audio`` is the concatenated PCM payload, ``sample_rate`` its
        declared rate.

        Return either the transcript string, or a dict
        ``{text, is_final, confidence, language}`` for full control.
        Override this for an STT plugin.
        """
        raise NotImplementedError

    async def ai_get_models(self) -> tuple[list[dict], str]:
        """Return (models_list, default_model_id)."""
        return [], ""

    async def get_action_types(self) -> list[dict]:
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
            return {"success": False, "result": "", "error": f"Unknown action: {action_type}"}
        _, handler = entry
        try:
            params = json.loads(params_json) if params_json else {}
            result = await handler(**params) if asyncio.iscoroutinefunction(handler) else handler(**params)
            if isinstance(result, dict):
                return {"success": True, "result": json.dumps(result)}
            return {"success": True, "result": str(result) if result is not None else ""}
        except Exception as e:
            return {"success": False, "result": "", "error": str(e)}

    async def get_trigger_types(self) -> list[dict]:
        """Return trigger type definitions.

        Auto-populated from ``@trigger`` decorators. Override to define manually.
        """
        return list(self._decorated_triggers.values())

    async def get_ui_contributions(self) -> list[dict]:
        """Return UI contribution definitions (pages, effects, settings sections, CSS injections)."""
        return []

    # Convenience factories for UI contributions
    @staticmethod
    def ui_page(id: str, label: str, url: str, *, icon_svg: str = "") -> dict:
        return {"id": id, "slot": "page.custom", "label": label, "url": url, "icon_svg": icon_svg, "pointer_events": True}

    @staticmethod
    def ui_slot(slot: str, url: str, *, id: str = "", label: str = "", width: int = 0, height: int = 0) -> dict:
        return {"id": id or slot, "slot": slot, "url": url, "label": label, "width": width, "height": height, "pointer_events": True}

    @staticmethod
    def ui_effect(url: str, *, id: str = "effect", audio: bool = False) -> dict:
        props = {"audio": "true"} if audio else {}
        return {"id": id, "slot": "background.behind", "url": url, "transparent": True, "pointer_events": False, "props": props}

    @staticmethod
    def ui_inject(css_target: str, position: str, url: str, *, id: str = "inject", width: int = 0, height: int = 0) -> dict:
        return {"id": id, "css_target": css_target, "position": position, "url": url, "width": width, "height": height, "pointer_events": True}

    @staticmethod
    def ui_overlay(id: str, url: str, *, width: int = 200, height: int = 200) -> dict:
        return {"id": id, "slot": "overlay.floating", "url": url, "transparent": True, "pointer_events": True, "width": width, "height": height}

    # ── UI calls ──

    async def handle_ui_call(self, method: str, params_json: str) -> dict | str | None:
        """Handle a call from this plugin's UI iframe (``CallFromUi``).

        Override this to implement UI→backend communication. ``params_json``
        is the raw JSON the iframe sent.

        Return either:

        * a dict with ``result_json`` and/or ``error`` keys — used verbatim,
          mirroring ``PluginUiCallResponse``;
        * any other dict or list — auto-serialized into ``result_json``;
        * a string — used as ``result_json`` as-is.
        """
        return {"error": f"No UI call handler implemented (method: {method})"}

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


def _field_dict_to_proto(d: dict):
    """Convert a config-fields dict to ``FieldDefinitionMsg``.

    Handles nested ``options`` / ``conditions`` arrays — protobuf's
    ``**dict`` unpack does not auto-convert dicts to sub-messages, so the
    nested entries are built explicitly.
    """
    options = [plugin_pb2.DropdownOptionMsg(**o) for o in d.get("options", []) or []]
    conditions = [
        plugin_pb2.FieldVisibilityCondition(**c) for c in d.get("conditions", []) or []
    ]
    flat = {k: v for k, v in d.items() if k not in ("options", "conditions")}
    return plugin_pb2.FieldDefinitionMsg(**flat, options=options, conditions=conditions)


class _CapabilityServicer(plugin_pb2_grpc.PluginCapabilityServiceServicer):
    """gRPC servicer that delegates to the Plugin instance."""

    def __init__(self, plugin: Plugin):
        self.plugin = plugin

    async def ListTools(self, request, context):
        tools = await self.plugin.list_tools()
        return plugin_pb2.PluginToolListResponse(
            tools=[plugin_pb2.PluginToolDef(**t) for t in tools]
        )

    async def CallTool(self, request, context):
        result = await self.plugin.call_tool(request.tool_name, request.arguments_json)
        return plugin_pb2.PluginCallToolResponse(**result)

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

    async def TtsListVoices(self, request, context):
        voices = await self.plugin.tts_list_voices()
        return plugin_pb2.PluginTtsVoicesResponse(
            voices=[plugin_pb2.PluginVoiceInfo(**v) for v in voices]
        )

    async def SttGetLanguages(self, request, context):
        langs = await self.plugin.stt_get_languages()
        return plugin_pb2.PluginSttLanguagesResponse(languages=langs)

    async def TtsGetConfigFields(self, request, context):
        fields = await self.plugin.tts_config_fields()
        return plugin_pb2.PluginConfigFieldsResponse(
            config_fields=[_field_dict_to_proto(f) for f in fields]
        )

    async def SttGetConfigFields(self, request, context):
        fields = await self.plugin.stt_config_fields()
        return plugin_pb2.PluginConfigFieldsResponse(
            config_fields=[_field_dict_to_proto(f) for f in fields]
        )

    async def SttProcess(self, request_iterator, context):
        # Accumulate the utterance. The daemon currently sends a single
        # f32-LE PCM buffer flagged `is_last`, but a future caller may split
        # it across chunks — drain until `is_last` or end-of-stream either way.
        audio = bytearray()
        sample_rate = 0
        async for chunk in request_iterator:
            if sample_rate == 0:
                sample_rate = chunk.sample_rate
            audio.extend(chunk.data)
            if chunk.is_last:
                break

        # Non-streaming transcription: one `stt_transcribe` call, one event.
        try:
            result = await self.plugin.stt_transcribe(bytes(audio), sample_rate)
        except NotImplementedError as e:
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details(str(e) or "STT not implemented")
            return
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return

        if isinstance(result, str):
            result = {"text": result}
        yield plugin_pb2.PluginSttEvent(
            text=result.get("text", ""),
            is_final=result.get("is_final", True),
            confidence=result.get("confidence", 1.0),
            language=result.get("language", ""),
        )

    async def AiGetModels(self, request, context):
        models, default = await self.plugin.ai_get_models()
        return plugin_pb2.PluginAiModelsResponse(
            models=[plugin_pb2.PluginAiModelInfo(**m) for m in models],
            default_model=default,
        )

    async def ExecuteAction(self, request, context):
        result = await self.plugin.execute_action(request.action_type, request.params_json)
        return plugin_pb2.PluginExecuteActionResponse(**result)

    async def GetPluginActionTypes(self, request, context):
        types = await self.plugin.get_action_types()
        return plugin_pb2.PluginActionTypesResponse(
            types=[plugin_pb2.ActionTypeDefinitionMsg(**t) for t in types]
        )

    async def GetPluginTriggerTypes(self, request, context):
        types = await self.plugin.get_trigger_types()
        return plugin_pb2.PluginTriggerTypesResponse(
            types=[plugin_pb2.TriggerTypeDefinitionMsg(**t) for t in types]
        )

    async def GetUiContributions(self, request, context):
        contributions = await self.plugin.get_ui_contributions()
        return plugin_pb2.PluginUiContributionsResponse(
            contributions=[plugin_pb2.PluginUiContribution(**c) for c in contributions]
        )

    async def CallFromUi(self, request, context):
        try:
            result = await self.plugin.handle_ui_call(request.method, request.params_json)
        except Exception as e:
            return plugin_pb2.PluginUiCallResponse(error=str(e))

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

    async def OnConfigChanged(self, request, context):
        config = json.loads(request.config_json) if request.config_json else {}
        self.plugin.config = config
        await self.plugin.on_config_changed(config)
        return plugin_pb2.Empty()

    async def OnActiveTriggers(self, request, context):
        active_types = list(request.trigger_types)
        self.plugin.active_triggers = set(active_types)
        await self.plugin.on_active_triggers(active_types)
        return plugin_pb2.Empty()

    async def OnLanguageChanged(self, request, context):
        self.plugin.language = request.language
        await self.plugin.on_language_changed(request.language)
        return plugin_pb2.Empty()

    async def Shutdown(self, request, context):
        await self.plugin.on_shutdown()
        # Schedule server stop
        asyncio.get_running_loop().call_later(0.1, lambda: asyncio.ensure_future(
            self.plugin._server.stop(grace=1)
        ))
        return plugin_pb2.Empty()

    async def HealthCheck(self, request, context):
        healthy, status = await self.plugin.health_check()
        return plugin_pb2.PluginHealthResponse(healthy=healthy, status=status)
