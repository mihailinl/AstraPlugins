"""Astra Plugin SDK — build plugins for Astra in Python."""

from astra_plugin_sdk.plugin import Plugin
from astra_plugin_sdk.host_client import HostClient, HostClientBootstrap
from astra_plugin_sdk.daemon_client import DaemonClient
from astra_plugin_sdk.decorators import tool, action, trigger, Field
from astra_plugin_sdk.i18n import I18n

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
]
# Keep in lockstep with `version` in pyproject.toml.
__version__ = "0.5.0"
