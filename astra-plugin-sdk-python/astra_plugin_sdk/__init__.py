"""Astra Plugin SDK — build plugins for Astra in Python."""

from astra_plugin_sdk.plugin import Plugin
from astra_plugin_sdk.host_client import HostClient, HostClientBootstrap
from astra_plugin_sdk.daemon_client import DaemonClient
from astra_plugin_sdk.decorators import tool, action, trigger, Field
from astra_plugin_sdk.errors import (
    ActionError,
    BadArguments,
    ErrorCode,
    InternalError,
    NotConfigured,
    NotFound,
    PluginError,
    RateLimited,
    Timeout,
    ToolError,
    Unauthorized,
    Unavailable,
)
from astra_plugin_sdk.i18n import I18n
from astra_plugin_sdk import limits
from astra_plugin_sdk.protocol import (
    EXIT_PROTOCOL_INCOMPATIBLE,
    MIN_SUPPORTED_DAEMON_PROTOCOL,
    PROTOCOL_VERSION,
)
from astra_plugin_sdk.types import (
    AiChunk,
    AiCompleteRequest,
    AiMessage,
    AiToolCall,
    AudioChunk,
    SttLoadState,
    SttLoadStatus,
    SttOptions,
    ThemeContribution,
)

__all__ = [
    "Plugin",
    "HostClient",
    "HostClientBootstrap",
    "DaemonClient",
    "tool",
    "action",
    "trigger",
    "Field",
    "I18n",
    "PROTOCOL_VERSION",
    "MIN_SUPPORTED_DAEMON_PROTOCOL",
    "EXIT_PROTOCOL_INCOMPATIBLE",
    # ── error taxonomy (§5.2) ──
    "ErrorCode",
    "PluginError",
    "ToolError",
    "ActionError",
    "BadArguments",
    "NotFound",
    "NotConfigured",
    "Unauthorized",
    "RateLimited",
    "Unavailable",
    "Timeout",
    "InternalError",
    # ── hook payloads (§5.4) ──
    "AiChunk",
    "AiCompleteRequest",
    "AiMessage",
    "AiToolCall",
    "AudioChunk",
    "SttLoadState",
    "SttLoadStatus",
    "SttOptions",
    "ThemeContribution",
]
# Keep in lockstep with `version` in pyproject.toml.
#
# Still 0.5.0: this package has never been published at 0.5.0 (PyPI is at
# 0.4.0), so the breaking changes below land inside the unreleased 0.5.0 rather
# than spending a minor nobody can install. Bumping it would also strand the
# CLI's Python scaffold, which pins `astra-plugin-sdk>=0.5,<0.6`.
__version__ = "0.5.0"
