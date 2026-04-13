"""Base Plugin class — subclass this to build an Astra plugin."""

import argparse
import asyncio
import json
import signal
import sys
from concurrent import futures

import grpc

from astra_plugin_sdk.host_client import HostClient

# Proto stubs will be generated at install time or pre-shipped.
# For now, define the gRPC servicer interface manually.
# Users run: python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/plugin.proto
# Or the SDK ships pre-generated stubs.

try:
    from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc
except ImportError:
    plugin_pb2 = None
    plugin_pb2_grpc = None


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
        if plugin_pb2_grpc is None:
            print(
                "ERROR: Proto stubs not generated. Run:\n"
                "  python -m grpc_tools.protoc -I proto "
                "--python_out=astra_plugin_sdk/proto "
                "--grpc_python_out=astra_plugin_sdk/proto "
                "proto/plugin.proto",
                file=sys.stderr,
            )
            sys.exit(1)

        # Start gRPC server on random port
        self._server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=4))
        servicer = _CapabilityServicer(self)
        plugin_pb2_grpc.add_PluginCapabilityServiceServicer_to_server(servicer, self._server)

        port = self._server.add_insecure_port("127.0.0.1:0")
        await self._server.start()
        print(f"Plugin gRPC server listening on port {port}")

        # Connect to daemon and register
        self.host = HostClient(daemon_addr, plugin_id)
        await self.host.connect()

        capabilities = await self._discover_capabilities()
        print(f"Registering with capabilities: {capabilities}")

        response = await self.host.register(port, capabilities, auth_token)
        if not response.success:
            print(f"Registration failed: {response.error}", file=sys.stderr)
            sys.exit(1)

        print(f"Registered successfully. Daemon version: {response.daemon_version}")

        # If plugin has client capability and received a session token, create DaemonClient
        if response.client_session_token:
            from astra_plugin_sdk.daemon_client import DaemonClient
            self.daemon = DaemonClient(daemon_addr, response.client_session_token)
            await self.daemon.connect()
            await self.on_daemon_client_ready(self.daemon)
            print("DaemonClient connected (plugin has client capability)")

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
            print(f"Subscribing to events: {event_types}")
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

        The base class automatically updates ``self.active_triggers``.
        Override to add custom logic, but call ``super()`` to keep tracking.

        Args:
            active_types: Un-namespaced trigger types that have at least one
                command listening. If a type is NOT in this list, skip firing it.
        """
        self.active_triggers = set(active_types)

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
        """Return event types to subscribe to. Empty = no subscription.

        Available event types: "chat_message_sync", "speech_recognized",
        "command_triggered", "command_completed", "settings_changed",
        "state_changed", "tts_started", "tts_completed", etc.
        """
        return []

    async def on_event(self, event_type: str, payload: dict):
        """Called when a subscribed event arrives from the daemon (raw fallback).

        Prefer typed handlers like :meth:`on_chat_sync` for common event types.

        Args:
            event_type: Event tag (e.g. "chat_message_sync").
            payload: Parsed event payload dict.
        """
        pass

    async def on_chat_sync(self, event: dict):
        """Called when a chat message sync event arrives.

        The daemon automatically filters by source_id if :meth:`source_id` is set.
        ``event`` dict has: id, conversation_id, role, content, source_id,
        is_streaming, is_complete.
        """
        pass

    async def on_state_changed(self, event: dict):
        """Called when daemon state changes. ``event`` has: previous, current."""
        pass

    async def on_command_triggered(self, event: dict):
        """Called when a command is triggered. ``event`` has: command_id, command_name, variables."""
        pass

    async def on_command_completed(self, event: dict):
        """Called when a command completes. ``event`` has: command_id, command_name, success."""
        pass

    async def _dispatch_event(self, event_type: str, payload: dict):
        """Internal: route events to typed handlers, then always call on_event for backward compat."""
        if event_type == "chat_message_sync":
            await self.on_chat_sync(payload)
        elif event_type == "state_changed":
            await self.on_state_changed(payload)
        elif event_type == "command_triggered":
            await self.on_command_triggered(payload)
        elif event_type == "command_completed":
            await self.on_command_completed(payload)
        # Always call raw handler for backward compatibility
        await self.on_event(event_type, payload)

    async def _event_loop(self, event_types: list[str]):
        """Internal: subscribe to daemon events and dispatch to typed handlers."""
        exclude = self.source_id()
        while True:
            try:
                stream = await self.host.subscribe_events(event_types, exclude_source_id=exclude)
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

    async def OnConfigChanged(self, request, context):
        config = json.loads(request.config_json) if request.config_json else {}
        self.plugin.config = config
        await self.plugin.on_config_changed(config)
        return plugin_pb2.Empty()

    async def OnActiveTriggers(self, request, context):
        await self.plugin.on_active_triggers(list(request.trigger_types))
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
