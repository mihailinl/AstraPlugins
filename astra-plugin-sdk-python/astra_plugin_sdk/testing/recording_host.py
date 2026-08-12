# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""A `HostClient` that records instead of calling, with failure injection.

Level 1 of the §5.6 harness. The plugin under test cannot tell it from the real
thing — same method names, same signatures, same `async` — so `self.host` works
in a handler without the plugin knowing it is in a test.

FAILURE INJECTION IS THE POINT, NOT AN EXTRA. A plugin whose `fire_trigger`
always succeeds is a plugin whose author has never run the branch that matters:
the daemon refusing a permission the manifest forgot to declare
(`permission_denied`), a restart mid-call, a rate limit. `fail_next` and
`fail_always` make those one line each.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from astra_plugin_sdk.causality import current_cause
from astra_plugin_sdk.proto import plugin_pb2
from astra_plugin_sdk.types import ThemeContribution

__all__ = ["RecordingHost", "LogLine", "FiredTrigger", "Variable", "UiPush", "ChatMessage"]


@dataclass(frozen=True)
class LogLine:
    level: str
    message: str


@dataclass(frozen=True)
class FiredTrigger:
    trigger_type: str
    payload_json: str
    #: The invocation lease this fire arrived under, or ``None`` for a root
    #: event.
    #:
    #: ``None`` is the normal answer almost everywhere: a plugin firing from a
    #: background task it started itself genuinely has no cause. It is set only
    #: when the fire happened inside a daemon call the daemon leased — which is
    #: what decides whether the trigger's output reaches the conversation the
    #: user is looking at. Defaulted so existing positional construction keeps
    #: working.
    caused_by: str | None = None

    @property
    def payload(self) -> Any:
        import json

        return json.loads(self.payload_json) if self.payload_json else {}


@dataclass(frozen=True)
class Variable:
    name: str
    value: str
    scope: str


@dataclass(frozen=True)
class UiPush:
    event: str
    payload_json: str

    @property
    def payload(self) -> Any:
        import json

        return json.loads(self.payload_json) if self.payload_json else {}


@dataclass(frozen=True)
class ChatMessage:
    text: str
    conversation_id: str
    voice_enabled: bool


@dataclass
class RecordingHost:
    """Everything a plugin can ask the daemon for, recorded.

    Construct one directly for a unit test, or take the one the `Harness` made::

        h = Harness(MyPlugin()).start()
        h.call_tool("remind", when="09:00")
        assert h.host.fired_triggers()[0].trigger_type == "on_time"
    """

    #: What `get_config()` answers. The `Harness` keeps it in step with the
    #: config it pushed, so a plugin that re-reads its config mid-call sees the
    #: same thing the test set.
    config_json: str = "{}"
    daemon_version: str = "test-daemon"
    daemon_port: int = 0

    _logs: list[LogLine] = field(default_factory=list)
    _triggers: list[FiredTrigger] = field(default_factory=list)
    _variables: list[Variable] = field(default_factory=list)
    _ui_pushes: list[UiPush] = field(default_factory=list)
    _chat: list[ChatMessage] = field(default_factory=list)
    _themes: list[Any] = field(default_factory=list)
    _subscriptions: list[list[str]] = field(default_factory=list)

    _fail_next: dict[str, BaseException] = field(default_factory=dict)
    _fail_always: dict[str, BaseException] = field(default_factory=dict)

    plugin_id: str = "test-plugin"

    # ── failure injection ──

    def fail_next(self, method: str, error: BaseException) -> "RecordingHost":
        """Make the next call to `method` raise `error`, once."""
        self._check_method(method)
        self._fail_next[method] = error
        return self

    def fail_always(self, method: str, error: BaseException) -> "RecordingHost":
        """Make every call to `method` raise `error` until `clear_failures`."""
        self._check_method(method)
        self._fail_always[method] = error
        return self

    def clear_failures(self) -> "RecordingHost":
        self._fail_next.clear()
        self._fail_always.clear()
        return self

    def _check_method(self, method: str) -> None:
        """Refuse to arm a failure on a method that does not exist.

        A typo here is silent otherwise: `fail_next("firetrigger", ...)` arms
        nothing, the call succeeds, and the test passes while asserting the
        opposite of what it says. This is the difference between a harness and a
        harness that can be trusted.
        """
        if method not in _HOST_METHODS:
            raise AttributeError(
                f"RecordingHost has no host call named {method!r}. "
                f"Available: {', '.join(sorted(_HOST_METHODS))}"
            )

    def _maybe_fail(self, method: str) -> None:
        error = self._fail_next.pop(method, None) or self._fail_always.get(method)
        if error is not None:
            raise error

    # ── the HostClient surface ──

    async def fire_trigger(self, trigger_type: str, payload_json: str = "{}") -> None:
        self._maybe_fail("fire_trigger")
        # The same read the real transport does, so a level-1 test sees the same
        # attribution a level-2 one would. Without it, a plugin whose fire lost
        # its cause would look correct here and land in the wrong conversation
        # in production.
        self._triggers.append(FiredTrigger(trigger_type, payload_json, current_cause()))

    async def log(self, level: str, message: str) -> None:
        self._maybe_fail("log")
        self._logs.append(LogLine(level, message))

    async def get_config(self) -> str:
        self._maybe_fail("get_config")
        return self.config_json

    async def get_daemon_info(self):
        self._maybe_fail("get_daemon_info")
        return plugin_pb2.PluginDaemonInfoResponse(
            version=self.daemon_version, port=self.daemon_port
        )

    async def subscribe_events(self, event_types: list[str] | None = None, exclude_source_id: str = ""):
        self._maybe_fail("subscribe_events")
        self._subscriptions.append(list(event_types or []))
        return _EmptyStream()

    async def push_to_ui(self, event: str, payload_json: str = "{}") -> None:
        self._maybe_fail("push_to_ui")
        self._ui_pushes.append(UiPush(event, payload_json))

    def send_chat_message(self, text: str, *, conversation_id: str = "", voice_enabled: bool = False):
        # Not a coroutine, exactly like the real one: it returns the stream.
        self._maybe_fail("send_chat_message")
        self._chat.append(ChatMessage(text, conversation_id, voice_enabled))
        return _EmptyStream()

    async def set_theme_contribution(self, theme) -> None:
        self._maybe_fail("set_theme_contribution")
        if isinstance(theme, ThemeContribution):
            theme = theme.to_proto(self.plugin_id)
        self._themes.append(theme)

    async def set_variable(self, name: str, value: str, scope: str = "session") -> None:
        self._maybe_fail("set_variable")
        self._variables.append(Variable(name, value, scope))

    async def close(self) -> None:
        pass

    # ── assertions ──

    def logs(self, level: str | None = None) -> list[LogLine]:
        return [l for l in self._logs if level is None or l.level == level]

    def fired_triggers(self, trigger_type: str | None = None) -> list[FiredTrigger]:
        return [t for t in self._triggers if trigger_type is None or t.trigger_type == trigger_type]

    def variables(self) -> dict[str, str]:
        """The last value set for each name — what the daemon would hold."""
        return {v.name: v.value for v in self._variables}

    def variable_sets(self) -> list[Variable]:
        """Every `set_variable` call, in order, including overwrites."""
        return list(self._variables)

    def ui_pushes(self, event: str | None = None) -> list[UiPush]:
        return [p for p in self._ui_pushes if event is None or p.event == event]

    def chat_messages(self) -> list[ChatMessage]:
        return list(self._chat)

    def theme_contributions(self) -> list[Any]:
        return list(self._themes)

    def subscriptions(self) -> list[list[str]]:
        return list(self._subscriptions)


class _EmptyStream:
    """A stream that ends immediately. `async for` over it does nothing."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


#: Every host call a plugin can make, used by `_check_method` to reject a typo.
_HOST_METHODS = frozenset(
    {
        "fire_trigger",
        "log",
        "get_config",
        "get_daemon_info",
        "subscribe_events",
        "push_to_ui",
        "send_chat_message",
        "set_theme_contribution",
        "set_variable",
    }
)
