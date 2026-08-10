"""Astra Plugin SDK — build plugins for Astra in Python."""

from astra_plugin_sdk.plugin import Plugin
from astra_plugin_sdk.host_client import HostClient, HostClientBootstrap
from astra_plugin_sdk.daemon_client import DaemonClient
from astra_plugin_sdk.decorators import tool, action, trigger, Field
from astra_plugin_sdk.i18n import I18n
from astra_plugin_sdk import limits
from astra_plugin_sdk.protocol import (
    EXIT_PROTOCOL_INCOMPATIBLE,
    MIN_SUPPORTED_DAEMON_PROTOCOL,
    PROTOCOL_VERSION,
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
]
# Keep in lockstep with `version` in pyproject.toml.
__version__ = "0.5.0"
