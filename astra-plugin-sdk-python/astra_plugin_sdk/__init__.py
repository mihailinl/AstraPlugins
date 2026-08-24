# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Astra Plugin SDK — build plugins for Astra in Python."""

from astra_plugin_sdk.plugin import Plugin
from astra_plugin_sdk.host_client import HostClient, HostClientBootstrap
from astra_plugin_sdk.daemon_client import DaemonClient
from astra_plugin_sdk.capability_types import (
    ActionTypeDef,
    AiModelInfo,
    DropdownOption,
    FieldCondition,
    FieldDef,
    ToolDef,
    TriggerTypeDef,
    UiContribution,
    VoiceInfo,
)
from astra_plugin_sdk.decorators import (
    Field,
    action,
    tool,
    trigger,
    ui_call,
    ui_effect,
    ui_inject,
    ui_overlay,
    ui_page,
    ui_slot,
)
from astra_plugin_sdk.logging_bridge import PluginLogHandler, install_logging_bridge
from astra_plugin_sdk.reserved import ReservedNameError, assert_no_reserved_names
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
from astra_plugin_sdk.i18n import I18n, key
from astra_plugin_sdk import limits
from astra_plugin_sdk import plural
from astra_plugin_sdk import wire
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
    # ── UI: registering decorators (§5.8) ──
    "ui_call",
    "ui_page",
    "ui_slot",
    "ui_effect",
    "ui_overlay",
    "ui_inject",
    # ── the seven capability types (§5.8) ──
    "ToolDef",
    "VoiceInfo",
    "AiModelInfo",
    "FieldDef",
    "DropdownOption",
    "FieldCondition",
    "ActionTypeDef",
    "TriggerTypeDef",
    "UiContribution",
    # ── logging and the reserved-name assertion (§5.10, §5.8) ──
    "install_logging_bridge",
    "PluginLogHandler",
    "assert_no_reserved_names",
    "ReservedNameError",
    "I18n",
    "key",
    "plural",
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
__version__ = "0.6.1"
