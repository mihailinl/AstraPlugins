"""Astra Plugin SDK — build plugins for Astra in Python."""

from astra_plugin_sdk.plugin import Plugin
from astra_plugin_sdk.host_client import HostClient
from astra_plugin_sdk.daemon_client import DaemonClient
from astra_plugin_sdk.decorators import tool, action, trigger, Field
from astra_plugin_sdk.i18n import I18n

__all__ = ["Plugin", "HostClient", "DaemonClient", "tool", "action", "trigger", "Field", "I18n"]
__version__ = "0.1.5"
