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

import json
from collections.abc import Iterable, Mapping
from typing import Any

import grpc

from astra_plugin_sdk import protocol
from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc
from astra_plugin_sdk.causality import current_cause
from astra_plugin_sdk.wire import SESSION_TOKEN_HEADER, X_ASTRA_CAUSE


#: What :meth:`HostClient.request_settings_change` takes: ``{path: value}``, or
#: ``(path, value)`` pairs in the order they should appear on the card.
SettingChanges = Mapping[str, Any] | Iterable[tuple[str, Any]]


def settings_change_request(
    changes: SettingChanges, reason: str
) -> plugin_pb2.PluginSettingsChangeRequest:
    """The ``PluginSettingsChangeRequest`` :meth:`HostClient.request_settings_change` sends.

    Each value is serialised to JSON for ``value_json`` — any JSON value:
    ``"gpt-4.1"``, ``True``, ``1.2``, ``None``, a list, a dict — compactly and
    with its characters kept. A value JSON cannot represent (``NaN``, infinity,
    an object ``json`` cannot encode) raises ``ValueError`` / ``TypeError``
    here instead of reaching the daemon as something else. Nothing else is
    checked: the count, a path given twice and the reason's length are the
    daemon's to judge (``REFUSED``), so the SDK can never disagree with the
    Astra it talks to.
    """
    if isinstance(changes, (str, bytes)):
        raise TypeError(
            "changes is a mapping {path: value} or (path, value) pairs, not a string"
        )
    pairs = changes.items() if isinstance(changes, Mapping) else changes
    return plugin_pb2.PluginSettingsChangeRequest(
        changes=[
            plugin_pb2.PluginSettingChange(
                path=path,
                value_json=json.dumps(
                    value, allow_nan=False, ensure_ascii=False, separators=(",", ":")
                ),
            )
            for path, value in pairs
        ],
        reason=reason,
    )


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

    async def get_ai_settings(self) -> plugin_pb2.PluginAiSettings:
        """The user's chat provider, model and endpoint — never a key.

        Needs the ``read_ai_settings`` permission. For a plugin that calls the
        user's model itself: ask Astra, never read Astra's files for it.
        ``provider`` is ``openai_compatible`` for an endpoint the user saved,
        ``astra`` (with an empty ``api_base_url``) for Astra's own service;
        ``is_loopback`` says the endpoint is on this machine. An Astra older
        than this RPC answers ``UNIMPLEMENTED``.
        """
        return await self._stub.GetAiSettings(
            plugin_pb2.GetAiSettingsRequest(), metadata=self._metadata
        )

    async def speak(self, text: str) -> plugin_pb2.PluginSpeakResponse:
        """Say ``text`` aloud in Astra's voice, and wait until it has been said.

        Needs the ``speak`` permission — **high-risk**, its own consent
        checkbox, because the words are heard as Astra's — and, besides the
        grant, an account that opens Astra and the person's reply voice on.

        The call lasts as long as the speech and answers with what became of
        it, in ``response.outcome``:

        * ``plugin_pb2.PLUGIN_SPEECH_OUTCOME_SPOKEN`` — it was heard.
        * ``plugin_pb2.PLUGIN_SPEECH_OUTCOME_STOPPED`` — silence was asked for
          before it finished (the wake word, reply voice turned off, Stop, your
          own :meth:`stop_speaking`). **Not an error**; do not say it again
          unasked.
        * ``plugin_pb2.PLUGIN_SPEECH_OUTCOME_NOT_SPOKEN`` — it was not said, and
          ``response.error`` (a ``PluginError``, the message a chat chunk's
          ``error_detail`` carries) says why: ``PLUGIN_ERROR_BAD_ARGUMENTS`` for
          an empty text or one longer than
          :data:`astra_plugin_sdk.limits.SPEAK_TEXT_MAX_CHARS` characters
          (refused, never cut); ``PLUGIN_ERROR_RATE_LIMITED`` with
          ``retry_after_ms`` once this plugin's speaking time is used up (450
          characters at once, then 3 a second, each call costing at least 20);
          ``PLUGIN_ERROR_UNAVAILABLE`` while voice is off, Astra is locked,
          there is no voice, or the speech queue could not take it. Nothing
          refused is queued.

        ::

            said = await self.host.speak("The kettle has boiled.")
            if said.outcome == plugin_pb2.PLUGIN_SPEECH_OUTCOME_NOT_SPOKEN:
                if said.error.code == plugin_pb2.PLUGIN_ERROR_RATE_LIMITED:
                    await asyncio.sleep(said.error.retry_after_ms / 1000)

        The daemon is the authority on the limits; this client checks neither.
        Your words queue behind your own earlier ones, so they never cut
        Astra's replies. A refusal by the gates — no grant, an account that
        does not open Astra, an Astra older than this RPC (``UNIMPLEMENTED``) —
        raises ``grpc.aio.AioRpcError`` like every host call.
        """
        return await self._stub.Speak(
            plugin_pb2.PluginSpeakRequest(text=text), metadata=self._metadata
        )

    async def stop_speaking(self) -> None:
        """Stop everything this plugin asked to be said, sounding and queued.

        Needs ``speak`` — stopping your own speech is part of speaking. Never
        touches anything else Astra is saying, and is allowed whether or not
        anybody is signed in. Each :meth:`speak` it cuts answers
        ``PLUGIN_SPEECH_OUTCOME_STOPPED``.
        """
        await self._stub.StopSpeaking(plugin_pb2.Empty(), metadata=self._metadata)

    async def get_user_identity(self) -> plugin_pb2.PluginUserIdentity:
        """Who is using Astra, as THIS plugin may know it.

        Needs the ``read_user_identity`` permission (not high-risk). Both ids
        are pseudonyms made for this plugin alone — another plugin reads
        different ones for the same person and machine (against plugins that
        use this API honestly: native plugin code can read Astra's files, and
        neither id is a secret) — and never the account's own id, a name, an
        email or a hardware serial:

        * ``install_id`` — this installation of Astra, stable across restarts
          and updates; empty while Astra has no installation key yet.
        * ``signed_in`` — a person is signed in; ``authorized`` — and their
          account opens Astra.
        * ``account_id`` — the signed-in account, the same on every device the
          person signs in on; empty unless ``authorized``. The same value
          arrives as ``account_id`` on this plugin's ``auth_changed`` events.

        An Astra older than this RPC answers ``UNIMPLEMENTED``.
        """
        return await self._stub.GetUserIdentity(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    async def request_settings_change(
        self, changes: SettingChanges, reason: str
    ) -> plugin_pb2.PluginSettingsChangeResponse:
        """**Ask the person** to change some of Astra's settings, on a card they answer.

        Needs the ``request_settings_change`` permission (not high-risk:
        nothing changes without the person's Allow) and an account that opens
        Astra. ``changes`` is ``{path: value}`` or ``(path, value)`` pairs —
        dotted settings paths the assistant itself may change (``ai.model``,
        ``voice.tts_speed``; never the permission mode, a key or Tool Search),
        each value any JSON value; ``reason`` is shown on the card in the
        plugin's own words. All of them change, or none, and what changes is
        exactly what the card showed.

        The call **lasts until the person answers or the card expires** —
        Astra's confirmation timeout, at least 30 s, 120 s unless the person
        changed it — so never await it on a path that must answer quickly. The
        SDK puts no deadline of its own on it. It answers ``response.outcome``:

        * ``plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_APPLIED`` — the person
          allowed it; the settings now hold what was asked for.
        * ``plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_UNCHANGED`` — they
          already held it. Nobody was asked.
        * ``plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_DECLINED`` — the person
          said no, now or to this plugin changing one of these settings before
          (Astra asks again about a setting only after it has changed some
          other way, or after a restart). **Do not ask again unasked.**
        * ``plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_TIMED_OUT`` — nobody
          answered before the card expired (no window open counts).
        * ``plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_REFUSED`` — not asked, or
          not applied: ``response.code`` says why, ``response.refused_path``
          names the setting when it is about one, and ``response.error`` is a
          ``PluginError`` — a sentence, and ``retry_after_ms`` for
          ``rate_limited``. The words: ``not_compiled`` (this Astra was built
          without the ``plugin-requests`` feature), ``locked``, ``invalid`` (no
          changes, a path twice, a value that is not JSON, or more than a card
          can show whole), ``too_many`` (more than
          :data:`astra_plugin_sdk.limits.SETTINGS_CHANGE_MAX_CHANGES`),
          ``reason_too_long`` (more than
          :data:`astra_plugin_sdk.limits.SETTINGS_CHANGE_REASON_MAX_CHARS`
          characters — refused, never cut), ``busy`` (one of this plugin's
          requests is already waiting), ``rate_limited`` (two at once, then
          one every two minutes), ``not_assistant_editable``,
          ``invalid_value``, ``unknown_choice``, ``needs_api_key``,
          ``needs_stt_provider``, ``provider_unreachable``, ``stale`` (the
          settings changed while the card was up), ``stopped`` (this plugin's
          authority ended first), ``write_refused``.

        ::

            asked = await self.host.request_settings_change(
                {"ai.model": "gpt-4.1"}, "PrimeAI's tools are tuned for this model"
            )
            if asked.outcome == plugin_pb2.PLUGIN_SETTINGS_CHANGE_OUTCOME_REFUSED:
                if asked.code == "rate_limited":
                    retry_in = asked.error.retry_after_ms / 1000

        The current values are never returned. The daemon is the authority on
        every limit; this client checks none (see :func:`settings_change_request`
        for the one thing it does: a value JSON cannot hold raises). A refusal
        by the gates — no grant, an account that does not open Astra, an Astra
        older than this RPC (``UNIMPLEMENTED``) — raises
        ``grpc.aio.AioRpcError`` like every host call.
        """
        return await self._stub.RequestSettingsChange(
            settings_change_request(changes, reason), metadata=self._metadata
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

        **Where it lands.** An empty ``conversation_id`` posts to this plugin's
        own durable thread, the right default for anything that is not an answer
        to a specific call. Pass one only when you were TOLD it: the chunks of a
        reply you are streaming carry it, and so does
        :func:`astra_plugin_sdk.current_invocation` inside a tool call or an
        action. An id from an invocation may be stored, across restarts, and
        sent back later.

        **Never await this inside the call that told you the id.** It is a
        deadlock, not a slow path. The conversation that invoked your tool is
        still running the turn waiting for your answer; a message declares an
        intent for the *next* turn, so it queues behind the one that cannot
        finish until you return. Hand it to a task::

            inv = current_invocation()
            if inv and inv.conversation_id:
                asyncio.create_task(self._answer_later(inv.conversation_id))
            return "started"          # the turn can now finish

        **Your text is text.** A message beginning ``/`` reaches the model as
        those literal characters — a plugin cannot invoke a slash command by
        writing one, nor supersede a person's turn. And the stream always ends:
        a line that reached the conversation but that no turn will answer ends
        it with an error chunk (``INTERNAL``, *"this message reached the
        conversation, but no turn will answer it"*) whose hint says not to
        resend.

        **When the conversation is gone** the send is refused, never redirected.
        ``StatusCode.NOT_FOUND`` with a message beginning ``conversation_gone:``
        means it was deleted — forget the id and fall back to your own thread.
        ``INVALID_ARGUMENT`` means the id is not a UUID, or names a chat an
        Astra surface owns. A message accepted and then outlived by its chat
        ends the stream with an error chunk whose ``error_detail.code`` is
        ``PLUGIN_ERROR_NOT_FOUND``. A daemon older than this contract reports
        the same situation as ``INTERNAL``, *"chat processing failed:
        conversation … does not exist"*.

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
