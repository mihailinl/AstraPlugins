# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Level 2 of the §5.6 harness: a real daemon, on a real socket, over real gRPC.

WHY A SECOND LEVEL EXISTS

Level 1 calls the servicer object. That covers the plugin's logic and the SDK's
conversions, and it is what a plugin author should write most of their tests
against. It cannot cover the six things that only exist once bytes move:

  * **Handler registration.** Level 1 calls `servicer.CallTool` by attribute. On
    the wire the method is found by its path, from the generated
    `add_PluginCapabilityServiceServicer_to_server` table — a servicer method
    spelled `Calltool` is invisible there and perfect here.
  * **Descriptor mismatch.** A field the plugin's proto has and the daemon's
    does not is a serialisation failure, not a Python one.
  * **The capability interceptor.** `ASTRA_PLUGIN_CAPABILITY_AUTH=require` is a
    metadata check inside gRPC. Level 1 has no metadata.
  * **Registration.** Whether the plugin sends `protocol_version`, whether it
    handles the daemon's refusal, whether it opens a `DaemonClient` it has no
    permission for.
  * **The session token.** Every host call after `Register` must carry
    `x-session-token`; the mock daemon rejects the ones that do not, exactly as
    the real `auth_interceptor.rs` does.
  * **Back-pressure.** The 500-slot bound on the STT audio channel only means
    anything against a real stream with a real flow-control window.

So this level runs `Plugin._run_async` unchanged — the same function Astra runs
— against a `MockDaemon` that serves `PluginHostService` on loopback.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import threading
import time
from typing import Any, Iterable

import grpc

from astra_plugin_sdk import protocol
from astra_plugin_sdk.plugin import Plugin
from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc
from astra_plugin_sdk.testing.recording_host import (
    ChatMessage,
    FiredTrigger,
    LogLine,
    UiPush,
    Variable,
)

__all__ = ["MockDaemon", "WireHarness", "WireError"]

#: The two headers, from the generated `spec/wire.yaml` reader. Re-bound here
#: because this harness is what `astra-plugin test` runs against a real
#: plugin process: if it checked a spelling of its own, a drift between the
#: SDK and the daemon would pass the conformance run it exists to catch.
from astra_plugin_sdk.wire import PLUGIN_TOKEN_HEADER, SESSION_TOKEN_HEADER


class WireError(AssertionError):
    """The plugin did not come up, or did not answer, over the wire."""


class MockDaemon(plugin_pb2_grpc.PluginHostServiceServicer):
    """`PluginHostService` on loopback, with the real authentication rules.

    Records what the plugin asked for, the same way `RecordingHost` does, so a
    test can move between the two levels without relearning the assertions.
    """

    def __init__(
        self,
        *,
        config: dict | None = None,
        language: str = "en",
        auth_token: str | None = None,
        session_token: str | None = None,
        daemon_version: str = "test-daemon",
        accept_registration: bool = True,
        registration_error: str = "",
        denied_permissions: Iterable[str] = (),
    ):
        self.config = dict(config or {})
        self.language = language
        #: The spawn token. The plugin echoes it in `Register`; the daemon
        #: verifies it there and attaches it to daemon→plugin calls.
        self.auth_token = auth_token if auth_token is not None else secrets.token_hex(16)
        self.session_token = (
            session_token if session_token is not None else secrets.token_hex(16)
        )
        self.daemon_version = daemon_version
        self.accept_registration = accept_registration
        self.registration_error = registration_error
        #: Host RPCs answered `permission_denied`, as the §4 gate would. Named
        #: by rpc method (`"FireTrigger"`), which is how `HOST_RPC_PERMISSIONS`
        #: is keyed.
        self.denied = set(denied_permissions)

        self.registrations: list[plugin_pb2.PluginRegisterRequest] = []
        self._logs: list[LogLine] = []
        self._triggers: list[FiredTrigger] = []
        self._variables: list[Variable] = []
        self._ui_pushes: list[UiPush] = []
        self._chat: list[ChatMessage] = []
        self._themes: list[Any] = []
        self.unauthenticated_calls: list[str] = []

        self._server: grpc.aio.Server | None = None
        self.port: int = 0

    # ── authentication, the same rules as the daemon ──

    def _authenticate(self, context, rpc: str) -> bool:
        metadata = dict(context.invocation_metadata() or ())
        if metadata.get(SESSION_TOKEN_HEADER) != self.session_token:
            self.unauthenticated_calls.append(rpc)
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details(f"{rpc}: missing or wrong {SESSION_TOKEN_HEADER}")
            return False
        if rpc in self.denied:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(
                f"{rpc}: this plugin's manifest does not declare the permission it needs"
            )
            return False
        return True

    # ── the service ──

    async def Register(self, request, context):
        # The one exempt path (`EXEMPT_PATHS` in auth_interceptor.rs): the
        # plugin proves itself with the spawn token in the body instead.
        self.registrations.append(request)
        if self.auth_token and request.auth_token != self.auth_token:
            return plugin_pb2.PluginRegisterResponse(
                success=False, error="auth token mismatch"
            )
        if not self.accept_registration:
            return plugin_pb2.PluginRegisterResponse(
                success=False, error=self.registration_error or "refused by the daemon"
            )
        return plugin_pb2.PluginRegisterResponse(
            success=True,
            config_json=json.dumps(self.config),
            daemon_version=self.daemon_version,
            client_session_token=self.session_token,
            language=self.language,
            protocol_version=protocol.PROTOCOL_VERSION,
            min_supported_protocol=protocol.PROTOCOL_VERSION,
        )

    async def PluginLog(self, request, context):
        if not self._authenticate(context, "PluginLog"):
            return plugin_pb2.Empty()
        self._logs.append(LogLine(request.level, request.message))
        return plugin_pb2.Empty()

    async def GetPluginSelfConfig(self, request, context):
        if not self._authenticate(context, "GetPluginSelfConfig"):
            return plugin_pb2.PluginSelfConfigResponse()
        return plugin_pb2.PluginSelfConfigResponse(config_json=json.dumps(self.config))

    async def GetDaemonInfo(self, request, context):
        if not self._authenticate(context, "GetDaemonInfo"):
            return plugin_pb2.PluginDaemonInfoResponse()
        return plugin_pb2.PluginDaemonInfoResponse(version=self.daemon_version)

    async def FireTrigger(self, request, context):
        if not self._authenticate(context, "FireTrigger"):
            return plugin_pb2.Empty()
        self._triggers.append(FiredTrigger(request.trigger_type, request.payload_json))
        return plugin_pb2.Empty()

    async def SetVariable(self, request, context):
        if not self._authenticate(context, "SetVariable"):
            return plugin_pb2.Empty()
        self._variables.append(Variable(request.name, request.value, request.scope))
        return plugin_pb2.Empty()

    async def PushToUi(self, request, context):
        if not self._authenticate(context, "PushToUi"):
            return plugin_pb2.Empty()
        self._ui_pushes.append(UiPush(request.event, request.payload_json))
        return plugin_pb2.Empty()

    async def SetThemeContribution(self, request, context):
        if not self._authenticate(context, "SetThemeContribution"):
            return plugin_pb2.Empty()
        self._themes.append(request)
        return plugin_pb2.Empty()

    async def SubscribeEvents(self, request, context):
        if not self._authenticate(context, "SubscribeEvents"):
            return
        # An empty, immediately-closed stream. A test that needs events pushes
        # them by replacing this method.
        return
        yield  # pragma: no cover — makes this an async generator

    async def SendChatMessage(self, request, context):
        if not self._authenticate(context, "SendChatMessage"):
            return
        self._chat.append(
            ChatMessage(request.text, request.conversation_id, request.voice_enabled)
        )
        yield plugin_pb2.PluginChatChunk(done=True)

    # ── the same assertions as RecordingHost ──

    def logs(self, level: str | None = None) -> list[LogLine]:
        return [l for l in self._logs if level is None or l.level == level]

    def fired_triggers(self, trigger_type: str | None = None) -> list[FiredTrigger]:
        return [t for t in self._triggers if trigger_type is None or t.trigger_type == trigger_type]

    def variables(self) -> dict[str, str]:
        return {v.name: v.value for v in self._variables}

    def ui_pushes(self, event: str | None = None) -> list[UiPush]:
        return [p for p in self._ui_pushes if event is None or p.event == event]

    def chat_messages(self) -> list[ChatMessage]:
        return list(self._chat)

    def theme_contributions(self) -> list[Any]:
        return list(self._themes)

    # ── lifecycle ──

    async def start(self) -> int:
        self._server = grpc.aio.server()
        plugin_pb2_grpc.add_PluginHostServiceServicer_to_server(self, self._server)
        self.port = self._server.add_insecure_port("127.0.0.1:0")
        await self._server.start()
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.stop(grace=0)
            self._server = None

    @property
    def address(self) -> str:
        return f"127.0.0.1:{self.port}"


class WireHarness:
    """Run a plugin's real `run()` path against a `MockDaemon`.

        with WireHarness(TextUtils(), config={"max_text_length": 10}) as w:
            reply = w.call_tool("word_count", text="a b c")
            assert json.loads(reply.result)["words"] == 3

    Synchronous, for the same reason `Harness` is: a plugin author's test should
    not have to own an event loop to find out whether their plugin works.
    """

    def __init__(
        self,
        plugin: Plugin,
        *,
        plugin_id: str = "test-plugin",
        config: dict | None = None,
        language: str = "en",
        capabilities: list[str] | None = None,
        capability_auth: str = "require",
        daemon: MockDaemon | None = None,
        spawn_token: str | None = None,
        timeout: float = 15.0,
    ):
        self.plugin = plugin
        self.plugin_id = plugin_id
        self.timeout = timeout
        self.daemon = daemon or MockDaemon(config=config, language=language)
        self.capabilities = capabilities
        #: The `--auth-token` the plugin is spawned with. Defaults to the one the
        #: daemon expects; set it to something else to rehearse the mismatch,
        #: which is what a plugin started by hand or by an attacker looks like.
        self.spawn_token = (
            spawn_token if spawn_token is not None else self.daemon.auth_token
        )
        self._capability_auth = capability_auth
        self._previous_auth_env: str | None = None
        self._channel: grpc.Channel | None = None
        self._stub = None
        self._run_task: asyncio.Task | None = None

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="astra-wire-harness", daemon=True
        )
        self._thread.start()

    # ── loop plumbing ──

    def run(self, coro, *, timeout: float | None = None):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout if timeout is not None else self.timeout)

    # ── lifecycle ──

    def start(self) -> "WireHarness":
        # `require` by default: the interceptor is a security control (§0.9) and
        # a harness that runs it in the permissive stage tests the stage nobody
        # will ship. A plugin that cannot answer an authenticated call fails
        # here rather than on a user's machine.
        self._previous_auth_env = os.environ.get("ASTRA_PLUGIN_CAPABILITY_AUTH")
        os.environ["ASTRA_PLUGIN_CAPABILITY_AUTH"] = self._capability_auth

        self.run(self.daemon.start())

        async def _guarded():
            # `_run_async` answers a refusal with `sys.exit`, which is right in a
            # process the daemon spawned and wrong inside a task: asyncio
            # re-raises `SystemExit` out of `run_forever`, killing the harness's
            # loop thread before the failure can be reported. Adopting it here
            # keeps the loop alive so the test gets a message instead of a hang.
            try:
                await self.plugin._run_async(
                    self.daemon.address,
                    self.plugin_id,
                    self.spawn_token,
                    self.capabilities,
                )
            except SystemExit as e:
                raise WireError(f"the plugin exited with code {e.code}") from e

        async def _launch():
            return asyncio.get_running_loop().create_task(_guarded())

        self._run_task = self.run(_launch())

        try:
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                if self._run_task.done():
                    failure = self._run_task.exception()
                    raise WireError(
                        f"the plugin died during startup: "
                        f"{type(failure).__name__}: {failure}"
                        if failure is not None
                        else "the plugin returned before it registered"
                    )
                if self.plugin.port and self.plugin.host is not None:
                    break
                time.sleep(0.02)
            else:
                raise WireError(
                    f"the plugin did not register within {self.timeout}s "
                    f"(port={self.plugin.port}, host={self.plugin.host})"
                )
        except BaseException:
            # A harness that leaks its loop and its thread on a failed start is
            # a harness that makes the NEXT test fail for the wrong reason.
            self.stop()
            raise

        self._channel = grpc.insecure_channel(f"127.0.0.1:{self.plugin.port}")
        self._stub = plugin_pb2_grpc.PluginCapabilityServiceStub(self._channel)
        return self

    def stop(self) -> None:
        if self._loop.is_closed():
            return
        try:
            if self._channel is not None:
                self._channel.close()
                self._channel = None
            if self.plugin._stop_event is not None:
                self._loop.call_soon_threadsafe(self.plugin._stop_event.set)
            if self._run_task is not None:
                try:
                    self.run(asyncio.wait_for(_wrap(self._run_task), self.timeout))
                except Exception:
                    self._run_task.cancel()
            self.run(self.daemon.stop())
        finally:
            if self._previous_auth_env is None:
                os.environ.pop("ASTRA_PLUGIN_CAPABILITY_AUTH", None)
            else:
                os.environ["ASTRA_PLUGIN_CAPABILITY_AUTH"] = self._previous_auth_env
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=self.timeout)
            self._loop.close()

    def __enter__(self) -> "WireHarness":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # ── calling the plugin, for real ──

    @property
    def metadata(self) -> list[tuple[str, str]]:
        """What the daemon attaches to every daemon→plugin call."""
        return [(PLUGIN_TOKEN_HEADER, self.daemon.auth_token)]

    def stub(self):
        """The raw `PluginCapabilityServiceStub`, for a call with no wrapper."""
        if self._stub is None:
            raise WireError("start() the harness first")
        return self._stub

    def list_tools(self) -> list[plugin_pb2.PluginToolDef]:
        return list(
            self.stub().ListTools(plugin_pb2.Empty(), metadata=self.metadata).tools
        )

    def call_tool(self, name: str, /, **arguments: Any) -> plugin_pb2.PluginCallToolResponse:
        # Positional-only, for the reason spelled out on `Harness.call_tool`: a
        # tool with a parameter called `name` would otherwise be uncallable.
        return self.stub().CallTool(
            plugin_pb2.PluginCallToolRequest(
                tool_name=name, arguments_json=json.dumps(arguments)
            ),
            metadata=self.metadata,
        )

    def execute_action(self, action_type: str, /, **params: Any):
        return self.stub().ExecuteAction(
            plugin_pb2.PluginExecuteActionRequest(
                action_type=action_type, params_json=json.dumps(params)
            ),
            metadata=self.metadata,
        )

    def ui_call(self, method: str, /, **params: Any) -> plugin_pb2.PluginUiCallResponse:
        return self.stub().CallFromUi(
            plugin_pb2.PluginUiCallRequest(method=method, params_json=json.dumps(params)),
            metadata=self.metadata,
        )

    def ui_contributions(self) -> list[plugin_pb2.PluginUiContribution]:
        return list(
            self.stub()
            .GetUiContributions(plugin_pb2.Empty(), metadata=self.metadata)
            .contributions
        )

    def health(self) -> plugin_pb2.PluginHealthResponse:
        return self.stub().HealthCheck(plugin_pb2.Empty(), metadata=self.metadata)

    def set_config(self, config: dict) -> None:
        self.daemon.config = dict(config)
        self.stub().OnConfigChanged(
            plugin_pb2.PluginConfigChangedMsg(config_json=json.dumps(config)),
            metadata=self.metadata,
        )

    def set_active_triggers(self, trigger_types: Iterable[str]) -> None:
        self.stub().OnActiveTriggers(
            plugin_pb2.PluginActiveTriggersMsg(trigger_types=list(trigger_types)),
            metadata=self.metadata,
        )

    def stt(self, chunks: Iterable[plugin_pb2.PluginAudioChunk], *, timeout: float | None = None):
        """Stream audio over the real bidi `SttProcess` and collect the events.

        This is the call that exercises back-pressure: the chunks go through a
        real HTTP/2 flow-control window into the SDK's bounded queue, so a
        recognizer slower than the sender slows the sender rather than losing
        audio.
        """
        responses = self.stub().SttProcess(
            iter(chunks), metadata=self.metadata, timeout=timeout or self.timeout
        )
        return list(responses)


async def _wrap(task):
    """Await a task without letting its exception escape as a test failure."""
    try:
        await task
    except (asyncio.CancelledError, SystemExit):
        pass
