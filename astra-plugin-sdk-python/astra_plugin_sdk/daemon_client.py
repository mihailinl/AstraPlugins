"""DaemonClient — full daemon API access for client-capable plugins.

Only available to plugins that override ``is_client()`` to return ``True``.
The daemon issues a session token during registration, and this client
injects it as ``x-session-token`` metadata on every gRPC request.

Example::

    class MyBot(Plugin):
        def is_client(self) -> bool:
            return True

        async def on_daemon_client_ready(self, client: DaemonClient):
            state = await client.get_state()
            print(f"Daemon state: {state.state}")
"""

import grpc

from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc


class DaemonClient:
    """Client for accessing daemon APIs (Chat, Voice, Commands, etc.).

    Only available to plugins with the ``client`` capability.
    The session token is injected as gRPC metadata on every call.
    """

    def __init__(self, daemon_addr: str, session_token: str):
        self._daemon_addr = daemon_addr
        self._token = session_token
        self._metadata = (("x-session-token", session_token),)
        self._channel: grpc.aio.Channel | None = None
        # Service stubs
        self._core: plugin_pb2_grpc.CoreServiceStub | None = None
        self._chat: plugin_pb2_grpc.ChatServiceStub | None = None
        self._voice: plugin_pb2_grpc.VoiceServiceStub | None = None
        self._command: plugin_pb2_grpc.CommandServiceStub | None = None
        self._config: plugin_pb2_grpc.ConfigServiceStub | None = None
        self._media: plugin_pb2_grpc.MediaServiceStub | None = None
        self._monitor: plugin_pb2_grpc.MonitorServiceStub | None = None

    async def connect(self):
        """Connect to the daemon and create service stubs."""
        self._channel = grpc.aio.insecure_channel(self._daemon_addr)
        self._core = plugin_pb2_grpc.CoreServiceStub(self._channel)
        self._chat = plugin_pb2_grpc.ChatServiceStub(self._channel)
        self._voice = plugin_pb2_grpc.VoiceServiceStub(self._channel)
        self._command = plugin_pb2_grpc.CommandServiceStub(self._channel)
        self._config = plugin_pb2_grpc.ConfigServiceStub(self._channel)
        self._media = plugin_pb2_grpc.MediaServiceStub(self._channel)
        self._monitor = plugin_pb2_grpc.MonitorServiceStub(self._channel)

    async def close(self):
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()

    # ===== Core Service =====

    async def get_state(self) -> plugin_pb2.CoreStateResponse:
        """Get the current state of the daemon."""
        return await self._core.GetState(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    async def subscribe_events(self):
        """Subscribe to real-time daemon events. Returns an async iterator."""
        return self._core.SubscribeEvents(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    # ===== Chat Service (event-sourcing API) =====

    async def submit_user_message(
        self,
        text: str,
        *,
        conversation_id: str = "",
        voice_enabled: bool = False,
        source_id: str = "",
    ) -> plugin_pb2.SubmitUserMessageResponse:
        """Submit a user message. Daemon auto-creates a conversation if
        ``conversation_id`` is empty, drives the AI turn asynchronously, and
        emits events through ``subscribe_chat_events``."""
        return await self._chat.SubmitUserMessage(
            plugin_pb2.SubmitUserMessageRequest(
                text=text,
                conversation_id=conversation_id,
                voice_enabled=voice_enabled,
                source_id=source_id,
            ),
            metadata=self._metadata,
        )

    def subscribe_chat_events(self, cursors: dict[str, int] | None = None):
        """Subscribe to the chat firehose — events from every conversation.
        ``cursors`` maps conversation id → last seen seq; backlog is replayed
        only for listed conversations, live events arrive for all.
        Returns an async iterator of FirehoseEventMsg."""
        return self._chat.SubscribeEvents(
            plugin_pb2.SubscribeEventsRequest(cursors=cursors or {}),
            metadata=self._metadata,
        )

    async def stop_generation(self, conversation_id: str = ""):
        """Stop AI generation. Empty ``conversation_id`` cancels every active turn."""
        await self._chat.StopGeneration(
            plugin_pb2.StopGenerationRequest(conversation_id=conversation_id),
            metadata=self._metadata,
        )

    async def respond_to_confirmation(
        self, request_id: str, allowed: bool, allow_like_this: bool = False
    ):
        """Respond to a pending tool confirmation request."""
        await self._chat.RespondToConfirmation(
            plugin_pb2.ConfirmationResponse(
                request_id=request_id,
                allowed=allowed,
                allow_like_this=allow_like_this,
            ),
            metadata=self._metadata,
        )

    async def list_conversations(self) -> plugin_pb2.ListConversationsResponse:
        return await self._chat.ListConversations(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    async def create_conversation(self, title: str) -> plugin_pb2.Conversation:
        return await self._chat.CreateConversation(
            plugin_pb2.CreateConversationRequest(title=title),
            metadata=self._metadata,
        )

    async def delete_conversation(self, conversation_id: str):
        await self._chat.DeleteConversation(
            plugin_pb2.DeleteConversationRequest(id=conversation_id),
            metadata=self._metadata,
        )

    async def clear_conversation(self, conversation_id: str):
        await self._chat.ClearConversation(
            plugin_pb2.ClearConversationRequest(conversation_id=conversation_id),
            metadata=self._metadata,
        )

    # ===== Voice Service =====

    async def speak(self, text: str, voice_id: str = "", interrupt: bool = False):
        """Speak text using TTS."""
        await self._voice.Speak(
            plugin_pb2.SpeakRequest(
                text=text, voice_id=voice_id, interrupt=interrupt
            ),
            metadata=self._metadata,
        )

    async def stop_speaking(self):
        """Stop current speech."""
        await self._voice.StopSpeaking(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    async def start_listening(self):
        """Start listening for speech."""
        await self._voice.StartListening(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    async def stop_listening(self):
        """Stop listening for speech."""
        await self._voice.StopListening(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    # ===== Command Service =====

    async def list_commands(
        self, include_disabled: bool = False
    ) -> plugin_pb2.CommandListResponse:
        """List all commands."""
        return await self._command.List(
            plugin_pb2.ListCommandsRequest(include_disabled=include_disabled),
            metadata=self._metadata,
        )

    async def execute_command(
        self,
        command_id: str,
        variables: dict[str, str] | None = None,
    ) -> plugin_pb2.ExecuteCommandResponse:
        """Execute a command by ID."""
        return await self._command.Execute(
            plugin_pb2.ExecuteCommandRequest(
                id=command_id,
                variables=variables or {},
            ),
            metadata=self._metadata,
        )

    # ===== Config Service =====

    async def get_settings(self) -> plugin_pb2.SettingsResponse:
        """Get all settings."""
        return await self._config.GetSettings(
            plugin_pb2.Empty(), metadata=self._metadata
        )

    # ===== Media Service =====

    async def get_media_state(
        self, session_id: str = ""
    ) -> plugin_pb2.MediaState:
        """Get current media playback state."""
        return await self._media.GetMediaState(
            plugin_pb2.GetMediaStateRequest(session_id=session_id),
            metadata=self._metadata,
        )

    async def control_media(self, action: int, session_id: str = ""):
        """Control media playback. action: 0=play_pause, 1=next, 2=prev, 3=stop."""
        await self._media.ControlMedia(
            plugin_pb2.ControlMediaRequest(
                action=action, session_id=session_id
            ),
            metadata=self._metadata,
        )

    async def get_media_sessions(self) -> list:
        """Get all active media sessions."""
        resp = await self._media.GetMediaSessions(
            plugin_pb2.GetMediaSessionsRequest(), metadata=self._metadata
        )
        return list(resp.sessions)

    # ===== Monitor Service =====

    async def get_system_stats(self) -> plugin_pb2.SystemStats:
        """Get current system stats (CPU, RAM, GPU, etc.)."""
        return await self._monitor.GetSystemStats(
            plugin_pb2.GetSystemStatsRequest(interval_ms=0),
            metadata=self._metadata,
        )
