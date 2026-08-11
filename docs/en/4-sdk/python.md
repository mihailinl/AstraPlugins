# The Python SDK

`astra-plugin-sdk` 0.5.0 on PyPI. Subclass `Plugin`, decorate methods, run it.

<!-- doctest: illustrative reason="a requirements.txt fragment; the scaffold that contains it is what the python-plugin blocks below are executed against" -->
```
astra-plugin-sdk>=0.5,<0.6
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
```

A Python plugin packages as **`noarch`**: one bundle for every platform. Its
`[entry]` is `command = "python"`, `args = ["-m", "src.plugin"]`,
`runtimes = ["python"]`.

## The shape of a plugin

<!-- doctest: python-plugin -->
```python
"""Timer — an Astra plugin."""

from astra_plugin_sdk import BadArguments, Plugin, TriggerTypeDef, tool


class Timer(Plugin):
    """Start countdowns from chat."""

    @tool("Start a countdown. Use it when the user asks to be reminded in N minutes.")
    async def start_timer(self, minutes: int, label: str = "") -> str:
        # The signature IS the schema. `minutes` is required because it has no
        # default; `label` is optional because it has one; the type hints become
        # the JSON types the model is shown.
        if minutes <= 0:
            raise BadArguments("give me at least a minute")
        await self.log_info(f"timer for {minutes}m")
        await self.fire_trigger("timer_started", {"minutes": minutes, "label": label})
        return f"timer set for {minutes} minutes"

    async def get_trigger_types(self) -> list[TriggerTypeDef]:
        return [TriggerTypeDef(type="timer_started", label="Timer started")]


if __name__ == "__main__":
    Timer().run()


# ── tests ─────────────────────────────────────────────────────────────────────
# Plain `def test_*` functions: the harness is synchronous on purpose, so a
# plugin's test suite needs no pytest-asyncio, no event-loop fixture and no
# "coroutine was never awaited" to decode.

def test_it_starts_a_timer():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        result = h.call_tool("start_timer", minutes=5)
        assert result.unwrap() == "timer set for 5 minutes"

        fired = h.host.fired_triggers("timer_started")
        assert len(fired) == 1
        assert fired[0].payload["minutes"] == 5


def test_zero_minutes_is_a_bad_argument():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        result = h.call_tool("start_timer", minutes=0)
        assert not result.success
        assert result.code == "BAD_ARGUMENTS", result.code


def test_the_tool_is_registered_under_the_name_the_daemon_uses():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        assert h.tool_names() == ["start_timer"]
        h.assert_schema_accepts("start_timer", "minutes", "label")
```

## Decorators

| | |
|---|---|
| `@tool("description")` | A function the model may call. Parameters become the schema |
| `@action("label")` | A step in the command editor |
| `@trigger(...)` | A trigger type |
| `@ui_call` | A method the plugin's own UI iframe may call |
| `@ui_page` · `@ui_slot` · `@ui_effect` · `@ui_overlay` · `@ui_inject` | **Class** decorators. Register a UI contribution served from the bundle's `ui/` directory or from a URL the plugin serves |
| `Field(...)` | Refine one parameter's schema — description, range, enum |

Everything else is an override on `Plugin`: `tts_synthesize`, `tts_list_voices`,
`tts_config_fields`, `stt_transcribe`, `stt_transcribe_stream`,
`stt_get_languages`, `stt_load` / `stt_unload` / `stt_load_state`,
`ai_complete`, `get_action_types`, `execute_action`, `get_trigger_types`,
`get_ui_contributions`, `handle_ui_call`, `on_config_changed`,
`on_language_changed`, `on_active_triggers`, `on_shutdown`, `health_check`.

## Calling out to Astra

Convenience methods on `Plugin` — `self.log_info`, `self.log_warn`,
`self.log_error`, `self.fire_trigger(type, payload_dict)`,
`self.push_to_ui(event, payload_dict)` — and everything else on `self.host`:

| `self.host.…` | Permission |
|---|---|
| `log(level, message)` · `get_config()` · `get_daemon_info()` | none |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope="session")` | `set_variable` |
| `subscribe_events(types, exclude_source_id="")` | `subscribe_events` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(text, …)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

> **`DaemonClient` does not work today, for any plugin.** The daemon registers
> every plugin as `ClientType::PluginClient` and its auth interceptor rejects
> that identity on any path outside `/astra.PluginHostService/` with
> `permission_denied("plugin session tokens are scoped to PluginHostService")` —
> `client = true` changes nothing about this. So `submit_user_message`,
> `subscribe_chat_events`, `speak` and `get_settings` all fail at run time. The
> daemon-side half is unbuilt, not broken.
>
> **`host.send_chat_message` is the only working way to drive an AI turn.**

For when the daemon side lands: it is **`submit_user_message`**, not
`send_message`, on the `DaemonClient`. The full client is handed to
`on_daemon_client_ready(client)`, and only for plugins that declare
`client = true` and return `True` from `is_client()`.

## Errors

Raise them; the SDK maps them to the same wire codes as the other two SDKs.

`BadArguments` · `NotFound` · `NotConfigured` · `Unauthorized` · `RateLimited` ·
`Unavailable` · `Timeout` · `InternalError`, all subclasses of `PluginError`,
with `ErrorCode` as the enum. See [`reference/errors.md`](../reference/errors.md).

## Capability types are dataclasses

`ToolDef`, `VoiceInfo`, `AiModelInfo`, `FieldDef`, `DropdownOption`,
`FieldCondition`, `ActionTypeDef`, `TriggerTypeDef`, `UiContribution`.

Returning a raw `dict` where a dataclass is expected still works and emits a
`DeprecationWarning`: deprecated in 0.5.0, removable from 0.7.0. Gate it in CI
with `python -W error::DeprecationWarning`.

## Testing

| | |
|---|---|
| `testing.Harness` | The plugin in this process, through the real capability servicer |
| `testing.WireHarness` | The plugin as a process, over gRPC |
| `testing.RecordingHost` | What your plugin told Astra: `fired_triggers()`, `logs()`, `variables()`, `ui_pushes()`, `chat_messages()`, plus `fail_next` / `fail_always` |
| pytest fixtures | `astra_harness` and `astra_wire`, if you use pytest |

`h.call_tool("name", **args)` takes the tool name **positionally** — the `/` in
the signature is load-bearing, because a tool whose own parameter is called
`name` would otherwise be uncallable.

The harness calls the real servicer, so it covers what calling the method
directly does not: that the tool is registered under the name the daemon will
use, that its schema parses, that arguments survive `json.dumps` →
`json.loads`, that the return value serialises, and that a raised error becomes
the code the daemon acts on.

## What this SDK cannot do yet

- **`DaemonClient` is non-functional.** The daemon scopes every plugin's session
  token to `PluginHostService`, so every daemon-side service answers
  `permission_denied` — `client = true` plugins included. Use
  `host.send_chat_message`.
- **No `stdout` of your own.** The SDK reconfigures stdout to line buffering
  because the daemon's supervisor reads it to learn the plugin is alive; block
  buffering made the supervisor reap the process at the start timeout. Use the
  logging bridge (`install_logging_bridge`) rather than `print`.
- **Startup is slower than the other two** — interpreter plus `grpcio` import.
  The daemon's budget is 20 s to the first line of output, which is generous,
  but a plugin that imports a large ML stack at module scope can miss it. Import
  lazily in the hook that needs it.
- **`ai_get_models` is deprecated** (0.5.0, removable 0.7.0 for the dict form;
  the hook itself is retired in 0.8) and nothing calls it.
- **`tts_synthesize_stream` is bound and unrouted** — no daemon call site.
- **The Python SDK is not published at 0.5.0 yet.** PyPI is at 0.4.0, so a fresh
  scaffold does not resolve until the release train runs. Until then, install
  the SDK from this repository.

## See also

[Hook table for Python](../hooks/python.md) ·
[parity](../reference/parity.md) · [errors](../reference/errors.md) ·
[versioning](../versioning.md)
