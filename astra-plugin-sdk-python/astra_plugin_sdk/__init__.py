"""Astra Plugin SDK — build plugins for Astra in Python."""

from astra_plugin_sdk.plugin import Plugin
from astra_plugin_sdk.host_client import HostClient
from astra_plugin_sdk.decorators import tool, action, trigger, Field

__all__ = ["Plugin", "HostClient", "tool", "action", "trigger", "Field"]
__version__ = "0.1.0"
