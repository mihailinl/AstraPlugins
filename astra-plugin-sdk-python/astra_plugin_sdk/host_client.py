# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""HostClient — plugin-side gRPC client for calling the Astra daemon.

The daemon exempts exactly one ``PluginHostService`` RPC from authentication:
``Register`` (`astra-daemon/src/server/auth_interceptor.rs`, ``EXEMPT_PATHS``).
It is the bootstrap path — the plugin proves itself with the spawn-time
``auth_token`` in the request body and hands back a per-plugin session token.
Every other host RPC must present that token as ``x-session-token`` metadata
or the daemon answers ``unauthenticated``.

SECURITY: the split below enforces that in the object graph rather than with a
runtime check. :class:`HostClientBootstrap` exposes ``register`` and nothing
else, and :class:`HostClient` cannot be constructed without a session token —
so there is no reachable object on which an unauthenticated ``log()`` /
``fire_trigger()`` / ``set_variable()`` exists.
"""

import grpc

from astra_plugin_sdk import protocol
from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc
from astra_plugin_sdk.causality import current_cause
from astra_plugin_sdk.wire import SESSION_TOKEN_HEADER, X_ASTRA_CAUSE


class HostClientBootstrap:
    """Pre-registration client. ``Register`` is the only RPC it can make.

    Use it once at startup::

        boot = HostClientBootstrap(daemon_addr, plugin_id)
        await boot.connect()
        response, host = await boot.register(port, capabilities, auth_token)

    On success ``host`` is an authenticated :class:`HostClient` that owns the
    channel; this object is inert afterwards.
    """

    def __init__(self, daemon_addr: str, plugin_id: str):
        self.daemon_addr = daemon_addr
        self.plugin_id = plugin_id
        self._channel: grpc.aio.Channel | None = None
        self._stub: plugin_pb2_grpc.PluginHostServiceStub | None = None

    async def connect(self):
        """Connect to the daemon's PluginHostService."""
        self._channel = grpc.aio.insecure_channel(self.daemon_addr)
        self._stub = plugin_pb2_grpc.PluginHostServiceStub(self._channel)

    async def register(
        self, port: int, capabilities: list[str], auth_token: str = ""
    ) -> tuple[plugin_pb2.PluginRegisterResponse, "HostClient | None"]:
        """Register this plugin with the daemon.

        Returns ``(response, client)``. ``client`` is an authenticated
        :class:`HostClient` when the daemon accepted the registration and
        issued a session token, and ``None`` otherwise — a refused plugin has
        no token, and therefore no way to make any further host call.
        """
        if self._stub is None:
            raise RuntimeError("connect() must be awaited before register()")

        response = await self._stub.Register(
            plugin_pb2.PluginRegisterRequest(
                plugin_id=self.plugin_id,
                port=port,
                capabilities=capabilities,
                auth_token=auth_token,
                # The handshake (production plan 1.3). Without this on the wire
                # the daemon cannot tell an old plugin from a new one, and its
                # protocol floor stops meaning anything.
                protocol_version=protocol.PROTOCOL_VERSION,
                sdk_name=protocol.SDK_NAME,
                sdk_version=protocol.sdk_version(),
            )
        )

        client = None
        if response.success and response.client_session_token:
            # Hand the live channel to the authenticated client so the plugin
            # keeps a single connection to the daemon.
            client = HostClient(
                self.daemon_addr,
                self.plugin_id,
                response.client_session_token,
                _channel=self._channel,
            )
            self._channel = None
            self._stub = None
        return response, client

    async def close(self):
        """Close the gRPC channel, unless it was handed to a HostClient."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None


class HostClient:
    """Authenticated client for calling daemon services from a plugin.

    Obtained from :meth:`HostClientBootstrap.register`. The session token is
    injected as ``x-session-token`` metadata on every request.
    """

    def __init__(
        self,
        daemon_addr: str,
        plugin_id: str,
        session_token: str,
        *,
        _channel: grpc.aio.Channel | None = None,
    ):
        if not session_token:
            raise ValueError(
                "HostClient requires the session token returned by Register; "
                "use HostClientBootstrap to obtain one"
            )
        self.daemon_addr = daemon_addr
        self.plugin_id = plugin_id
        self._metadata = ((SESSION_TOKEN_HEADER, session_token),)
        self._channel = _channel or grpc.aio.insecure_channel(daemon_addr)
        self._stub = plugin_pb2_grpc.PluginHostServiceStub(self._channel)

    async def fire_trigger(self, trigger_type: str, payload_json: str = "{}"):
        """Fire a trigger, carrying the lease for the daemon call it came out of.

        **This is the transport, and the read belongs here rather than one level
        up.** Both other ways to fire — ``PluginContext.fire_trigger`` and the
        ``Plugin.fire_trigger`` wrapper an author is most likely to write —
        forward to this method, and the wrapper routes to the process-global
        host. A read in the context wrapper would leave that path unstamped,
        which is the one the docs teach.

        The lease travels as call metadata rather than in the request body,
        because ``payload_json``'s keys are injected verbatim as workflow
        variables daemon-side: a reserved key would appear as
        ``{__astra_cause}`` in the user's own variable picker.

        No ambient lease means no header. Never an empty one, never an invented
        one, and never a failed fire: the daemon files an unattributed trigger
        as a root event, which is where every plugin built before leases existed
        lands.
        """
        cause = current_cause()
        metadata = self._metadata if cause is None else (*self._metadata, (X_ASTRA_CAUSE, cause))
        await self._stub.FireTrigger(
            plugin_pb2.PluginFireTriggerRequest(
                trigger_type=trigger_type,
                payload_json=payload_json,
            ),
            metadata=metadata,
        )

    async def log(self, level: str, message: str):
        """Log a message to the daemon's log buffer."""
        await self._stub.PluginLog(
            plugin_pb2.PluginLogRequest(
                plugin_id=self.plugin_id,
                level=level,
                message=message,
            ),
            metadata=self._metadata,
        )

    async def get_config(self) -> str:
        """Get this plugin's current config from the daemon."""
        response = await self._stub.GetPluginSelfConfig(
            plugin_pb2.PluginSelfIdRequest(plugin_id=self.plugin_id),
            metadata=self._metadata,
        )
        return response.config_json

    async def get_daemon_info(self) -> plugin_pb2.PluginDaemonInfoResponse:
        """Get daemon info (version, state, port)."""
        return await self._stub.GetDaemonInfo(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    async def subscribe_events(self, event_types: list[str] | None = None, exclude_source_id: str = ""):
        """Subscribe to daemon events. Returns an async iterator.

        Args:
            event_types: Event types to subscribe to. Empty = all.
            exclude_source_id: Skip ChatMessageSync events from this source (server-side filtering).
        """
        return self._stub.SubscribeEvents(
            plugin_pb2.PluginEventFilter(
                plugin_id=self.plugin_id,
                event_types=event_types or [],
                exclude_source_id=exclude_source_id,
            ),
            metadata=self._metadata,
        )

    async def push_to_ui(self, event: str, payload_json: str = "{}"):
        """Push an event into this plugin's own iframes.

        The return path for ``CallFromUi``: the iframe calls in, the backend
        answers later. Requires the ``push_to_ui`` permission — without it the
        daemon answers ``permission_denied``, and the fix is a
        ``[permissions] push_to_ui`` entry in ``plugin.toml`` plus the user's
        consent, not a retry.
        """
        await self._stub.PushToUi(
            plugin_pb2.PluginUiPushRequest(
                plugin_id=self.plugin_id,
                event=event,
                payload_json=payload_json,
            ),
            metadata=self._metadata,
        )

    def send_chat_message(
        self,
        text: str,
        *,
        conversation_id: str = "",
        voice_enabled: bool = False,
    ):
        """Send a chat message as this plugin; stream the assistant's reply.

        Returns an async iterator of ``PluginChatChunk``. Each chunk carries
        exactly one of ``text`` / ``done`` / ``error`` — check with
        ``chunk.WhichOneof("content")``::

            async for chunk in host.send_chat_message("hello"):
                if chunk.WhichOneof("content") == "text":
                    print(chunk.text, end="")

        This is the ONLY working path for a client plugin to talk to the
        conversation. The session token is scoped to ``PluginHostService``, so
        the ``DaemonClient``/``ChatService`` route is ``permission_denied`` by
        construction. Requires the ``send_chat_message`` permission.

        **conversation_id** — Where the message lands. Pass the EMPTY STRING and it goes to this plugin's
        own durable thread: one thread per plugin, kept across calls, so a series of
        messages reads as one conversation. That is the right choice for almost every
        plugin, and it is what you get by default.

        Pass an id ONLY to answer inside a conversation you were told about in this
        same exchange — `PluginChatChunk.conversation_id`, on the chunks of a reply you
        are streaming right now. Do NOT store one and send it back later. Threads
        rotate and are pruned, so a stored id eventually names a conversation that is
        gone, and what happens then depends on the age of the daemon the user is
        running: older builds accept it silently and write the exchange where nobody
        can see it, newer ones refuse it. Neither is something a plugin can recover
        from. Leave it empty and let the daemon place the message.

        There is deliberately no way to ask which conversation the user is looking at.

        Not a coroutine: it returns the stream directly, so ``async for`` works
        without an ``await`` first — the same shape as :meth:`subscribe_events`.
        """
        return self._stub.SendChatMessage(
            plugin_pb2.PluginChatRequest(
                text=text,
                source_id=self.plugin_id,
                conversation_id=conversation_id,
                voice_enabled=voice_enabled,
            ),
            metadata=self._metadata,
        )

    async def set_theme_contribution(self, theme) -> None:
        """Contribute colours, wallpaper and shader to the active Astra theme.

        ``theme`` is a :class:`~astra_plugin_sdk.types.ThemeContribution` (or a
        ready-made ``PluginThemeContribution``). Requires the
        ``set_theme_contribution`` permission, which Phase 4 classes high-risk:
        this repaints the user's whole application, so the daemon refuses it
        below Tier 1 regardless of what the manifest asks for.
        """
        message = theme
        if hasattr(theme, "to_proto"):
            message = theme.to_proto(self.plugin_id)
        elif not message.plugin_id:
            message.plugin_id = self.plugin_id
        await self._stub.SetThemeContribution(message, metadata=self._metadata)

    async def set_variable(self, name: str, value: str, scope: str = "session"):
        """Set a variable in the daemon's variable context.

        Args:
            name: Variable name.
            value: Variable value.
            scope: "session" (default, cleared on restart) or "persistent" (saved to disk).
        """
        await self._stub.SetVariable(
            plugin_pb2.PluginSetVariableRequest(
                plugin_id=self.plugin_id,
                name=name,
                value=value,
                scope=scope,
            ),
            metadata=self._metadata,
        )

    async def close(self):
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
