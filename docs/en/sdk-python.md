# Python SDK

The Python SDK uses a **declarative, decorator-based** API. Subclass `Plugin`, decorate methods with `@tool`, `@action`, or `@trigger`, and the SDK auto-builds capability metadata from your type hints.

Package: `astra-plugin-sdk` at `AstraPlugins/astra-plugin-sdk-python`.
Source of truth: `astra_plugin_sdk/plugin.py` and `astra_plugin_sdk/decorators.py`.

## Install

Requires Python 3.10+. Add to your `pyproject.toml`:

```toml
[project]
name = "my_plugin"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "astra-plugin-sdk",
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
]
```

The daemon uses [`uv`](https://docs.astral.sh/uv/) to install your plugin's dependencies into an isolated virtual environment when it loads the bundle. You do not need to manage venvs by hand.

## Minimal plugin

```python
from astra_plugin_sdk import Plugin, tool

class MyPlugin(Plugin):
    @tool("Say hello")
    async def greet(self, name: str) -> dict:
        return {"greeting": f"Hello, {name}!"}

if __name__ == "__main__":
    MyPlugin().run()
```

`Plugin.run()` handles CLI argument parsing (`--daemon-addr`, `--plugin-id`, `--auth-token`), starts a gRPC server on a random local port, registers with the daemon, dispatches incoming calls, and handles shutdown signals.

## Decorators

### `@tool(description)`

Registers a method as an AI tool. Type hints are converted to JSON Schema automatically (`decorators.py:28-92`).

```python
from typing import Literal

@tool("Count words in text")
async def word_count(self, text: str) -> dict:
    return {"words": len(text.split())}

@tool("Convert case")
async def convert_case(
    self,
    text: str,
    mode: Literal["upper", "lower", "title"] = "upper",
) -> dict:
    return {"result": getattr(text, mode)()}
```

Supported type hints:

| Hint | JSON Schema |
| --- | --- |
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` | `{"type": "array", "items": ...}` |
| `dict` | `{"type": "object"}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `Optional[T]` | Schema for `T`, field marked not required |

Parameters without defaults are marked `required`. Return value is automatically wrapped in `{"success": True, "result": ...}`.

### `@action(label, *, icon_svg="", fields=[], ai_available=False, ai_description="", ai_primary_field="")`

Registers a Command Graph action type. The method is invoked when a command executes this action.

```python
from astra_plugin_sdk import action, Field

@action(
    "Transform text",
    icon_svg='<svg>…</svg>',
    fields=[
        Field.text("input", "Input text"),
        Field.dropdown("op", "Operation", options=[
            ("upper", "UPPER"), ("lower", "lower"),
        ]),
    ],
    ai_available=True,
    ai_description="Transform a block of text via upper/lower/title case",
    ai_primary_field="input",
)
async def transform_text(self, input: str, op: str):
    return {"success": True, "result": getattr(input, op)()}
```

### `@trigger(label, *, icon_svg="", fields=[])`

Registers a trigger type. The decorated method holds only metadata — fire the trigger from your own background work via `self.fire_trigger`.

```python
from astra_plugin_sdk import trigger, Field

@trigger("Scheduled time", fields=[
    Field.text("time", "Time", default="09:00", placeholder="HH:MM"),
])
def on_time(self):
    pass

async def tick(self):
    if "on_time" in self.active_triggers:
        await self.fire_trigger("on_time", {"time": "09:00"})
```

## `Field` builders

All builders are static methods of `Field` (`decorators.py:189-319`):

```python
Field.text(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea_with_variables(id, label, ...)
Field.dropdown(id, label, *, options, default="", description="", conditions=[])
Field.number(id, label, *, min=None, max=None, step=None, default="", ...)
Field.toggle(id, label, *, default=False, description="", conditions=[])
```

`dropdown.options` accepts tuples, dicts, or plain strings:

```python
Field.dropdown("mode", "Mode", options=[("fast", "Fast"), ("slow", "Slow")])
Field.dropdown("mode", "Mode", options=[{"value": "fast", "label": "Fast"}])
Field.dropdown("mode", "Mode", options=["fast", "slow"])
```

Visibility conditions:

```python
Field.text("custom_value", "Custom value", conditions=[
    Field.condition("mode", "equals", "custom")
])
```

## Lifecycle hooks

Override any of these on your subclass:

| Hook | Purpose |
| --- | --- |
| `async def on_daemon_client_ready(self, client: DaemonClient)` | Called after registration for client plugins — hold onto `client` for daemon API access. |
| `async def on_config_changed(self, config: dict)` | Config updated (either by UI or `ConfigService.SetConfig`). |
| `async def on_language_changed(self, language: str)` | Daemon UI language changed — call `self.i18n.set_language(language)`. |
| `async def on_active_triggers(self, active_types: list[str])` | Updates `self.active_triggers` — use it to skip firing triggers with no listeners. |
| `async def on_shutdown(self)` | Daemon requested shutdown — release resources here. |
| `async def health_check(self) -> (bool, str)` | Return `(healthy, status_message)`. |

## Events

```python
def subscribed_events(self) -> list[str]:
    return ["chat_message_sync", "command_completed"]

async def on_chat_sync(self, event):
    # event has id, conversation_id, role, content, source_id,
    # is_streaming, is_complete
    ...

async def on_command_triggered(self, event): ...
async def on_command_completed(self, event): ...
async def on_state_changed(self, event): ...

async def on_event(self, event_type: str, payload: dict):
    # Raw fallback for event types not covered by typed handlers
    ...
```

## Client plugins

```python
class MyClientPlugin(Plugin):
    def is_client(self) -> bool:
        return True

    async def on_daemon_client_ready(self, client):
        self.daemon = client
        state = await self.daemon.get_state()
        async for chunk in self.daemon.send_message(conversation_id, "Hello!"):
            print(chunk.text)
```

`DaemonClient` exposes `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService`, and `MonitorService`. See `daemon_client.py` for all methods.

## Logging

```python
await self.log_info("Processing request")
await self.log_warn("Rate limit near")
await self.log_error("Connection failed")

# Or call HostClient directly:
await self.host.log("info", "Plugin started")
```

Log messages land in the daemon's log buffer and appear in the Plugins UI.

## Firing triggers

```python
await self.fire_trigger("on_roll_total", {"total": 42})
```

`fire_trigger` sends the event to the daemon, which matches it against registered commands. Safe to call when no listeners exist, but pre-check `self.active_triggers` to avoid wasted RPCs.

## i18n

```python
from astra_plugin_sdk import I18n

class MyPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.i18n = I18n("locales")  # loads locales/*.json

    async def on_language_changed(self, language: str):
        self.i18n.set_language(language)

    @tool("…")
    async def greet(self, name: str):
        return {"msg": self.i18n.tf("greeting", name)}
```

Locale files live in `locales/en.json`, `locales/ru.json`, etc. Unknown keys fall back to the English file, then to the key itself.

## UI contributions

```python
def __init__(self):
    super().__init__()
    self.ui_page("stats", "Stats", "http://localhost:8123/stats.html")
    self.ui_effect("http://localhost:8123/snow.html")
    self.ui_overlay("clock", "http://localhost:8123/clock.html",
                    width=200, height=80)
```

## Worked example — text-utils

See `AstraPlugins/examples/text-utils`. Highlights:

- Tools: `word_count`, `case_convert`, `regex_match`.
- Action: `transform_text` with `Field.dropdown`.
- Trigger: `on_time` with a background asyncio loop.
- Config: `max_text_length` via `[config].schema` in `plugin.toml`.
- `on_config_changed` updates runtime limits.

Manifest:

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
```

## Where to go next

- [Capabilities](capabilities.md) — full behaviour per capability.
- [Manifest](manifest.md) — every `plugin.toml` field.
- [Publishing](publishing.md) — build, sign, distribute.
