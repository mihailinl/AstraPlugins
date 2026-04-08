"""HostClient — plugin-side gRPC client for calling the Astra daemon."""

import grpc

from astra_plugin_sdk.proto import plugin_pb2, plugin_pb2_grpc


class HostClient:
    """Client for calling daemon services from a plugin."""

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
    ) -> plugin_pb2.PluginRegisterResponse:
        """Register this plugin with the daemon."""
        return await self._stub.Register(
            plugin_pb2.PluginRegisterRequest(
                plugin_id=self.plugin_id,
                port=port,
                capabilities=capabilities,
                auth_token=auth_token,
            )
        )

    async def fire_trigger(self, trigger_type: str, payload_json: str = "{}"):
        """Fire a trigger (for trigger plugins)."""
        await self._stub.FireTrigger(
            plugin_pb2.PluginFireTriggerRequest(
                trigger_type=trigger_type,
                payload_json=payload_json,
            )
        )

    async def log(self, level: str, message: str):
        """Log a message to the daemon's log buffer."""
        await self._stub.PluginLog(
            plugin_pb2.PluginLogRequest(
                plugin_id=self.plugin_id,
                level=level,
                message=message,
            )
        )

    async def get_config(self) -> str:
        """Get this plugin's current config from the daemon."""
        response = await self._stub.GetPluginSelfConfig(
            plugin_pb2.PluginSelfIdRequest(plugin_id=self.plugin_id)
        )
        return response.config_json

    async def get_daemon_info(self) -> plugin_pb2.PluginDaemonInfoResponse:
        """Get daemon info (version, state, port)."""
        return await self._stub.GetDaemonInfo(plugin_pb2.Empty())

    async def subscribe_events(self, event_types: list[str] | None = None):
        """Subscribe to daemon events. Returns an async iterator."""
        return self._stub.SubscribeEvents(
            plugin_pb2.PluginEventFilter(
                plugin_id=self.plugin_id,
                event_types=event_types or [],
            )
        )

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
            )
        )

    async def close(self):
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
