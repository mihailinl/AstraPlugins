# astra-plugin-sdk (Python)

Write a plugin for Astra in Python.

Repository: <https://github.com/mihailinl/AstraPlugins>

## Installing

```bash
pip install "astra-plugin-sdk>=0.5,<0.6"
pip install "astra-plugin-sdk[test]"   # adds pytest, for the harness
```

That range is also what `astra-plugin new` writes into `requirements.txt`.

**Take 0.5 or newer, and mean it.** The daemon rejects every host RPC but
`Register` without an `x-session-token`, and 0.5.0 is the first release that
sends one: a 0.4.0 plugin starts, answers inbound hooks, and gets
`unauthenticated` on every `log`, `fire_trigger` and `set_variable` it attempts.

Python 3.10 or newer. Brings `grpcio`, `grpcio-tools` and `protobuf`.

`astra-plugin test` runs your plugin with whatever `python` is on `PATH`, so
activate the virtualenv you installed into before running it.

To install from this repository instead — to try an unreleased change:

```bash
pip install ./AstraPlugins/astra-plugin-sdk-python
```

Astra ships no Python runtime. A Python plugin's `plugin.toml` declares
`runtimes = ["python"]` so the daemon fails with a clear message on a machine
with no interpreter, instead of dying at startup.

## The smallest working plugin

```python
from astra_plugin_sdk import Plugin, tool


class MyPlugin(Plugin):
    @tool("Greet someone by name.")
    async def hello(self, name: str, excited: bool = False):
        return f"Hello, {name}{'!' if excited else '.'}"


if __name__ == "__main__":
    MyPlugin().run()
```

`astra-plugin new my-plugin --lang python` writes this, a `plugin.toml`, a
`pyproject.toml` and a passing `pytest` suite.

**The signature is the schema.** `@tool` reads the method's type hints and
builds the JSON Schema the model is shown: `name` is required because it has no
default, `excited` is optional because it has one. There is no second place to
edit, so the schema and the handler cannot drift. Returning a plain value is
enough — the SDK wraps it as a successful tool result.

Returning `dict`s where a capability type is expected is deprecated and removed
in 0.7. Use the dataclasses: `ToolDef`, `VoiceInfo`, `AiModelInfo`, `FieldDef`,
`DropdownOption`, `FieldCondition`, `ActionTypeDef`, `TriggerTypeDef`,
`UiContribution`.

## Actions, triggers, UI

```python
from astra_plugin_sdk import Field, Plugin, action, tool


class DiceRoller(Plugin):
    @action("Roll Dice", fields=[Field.text("notation", "Dice notation")])
    async def roll_dice(self, params: dict):
        return params.get("notation", "d20")
```

Also exported: `trigger`, and the six UI decorators `ui_call`, `ui_page`,
`ui_slot`, `ui_effect`, `ui_overlay`, `ui_inject`.

## Talking back to Astra

```python
class DiceRoller(Plugin):
    @tool("Roll dice. Use for any request that involves dice or random numbers.")
    async def roll(self, count: int, sides: int = 6):
        await self.log_info(f"rolling {count}d{sides}")
        await self.fire_trigger("on_roll_value", {"value": count * sides})
        return f"{count} d{sides}"
```

`self.log_info` / `log_warn` / `log_error`, `self.fire_trigger`,
`self.push_to_ui` are the convenience wrappers; the full outbound surface is
`self.host` (`HostClient`): `fire_trigger`, `log`, `get_config`,
`get_daemon_info`, `subscribe_events`, `push_to_ui`, `send_chat_message`,
`set_theme_contribution`, `set_variable`.

**Every one of those is default-deny.** A manifest with no `[permissions]`
section may call `Register`, `PluginLog`, `GetPluginSelfConfig` and
`GetDaemonInfo`, and nothing else. `fire_trigger` needs

```toml
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

and the `reason` is what the user reads on the install consent sheet.

A plugin whose `is_client()` returns `True` also gets a `DaemonClient` — chat,
voice, commands, settings. Its "type a message as the user" method is
**`submit_user_message`**, not `send_message`.

> **That client does not reach anything yet.** The daemon registers every plugin
> as `ClientType::PluginClient` and its auth interceptor rejects that identity
> on any gRPC path outside `/astra.PluginHostService/`, so every `DaemonClient`
> call answers `permission_denied` — `client = true` included.
> `host.send_chat_message` is the only working way to drive an AI turn. The
> daemon-side half is unbuilt; the SDK surface is here first.

## Errors

```python
from astra_plugin_sdk import NotConfigured

raise NotConfigured("api_key")
```

Eight exceptions with the same eight codes the Rust and TypeScript SDKs use:
`BadArguments`, `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`,
`Unavailable`, `Timeout`, `InternalError`, all deriving from `PluginError`
(aliased `ToolError` / `ActionError`). Raise one from a tool, an action or a UI
call and the SDK fills in both halves of the response: the legacy `error`
string, byte-identical to what the Rust SDK produces, and the structured
`error_detail` carrying `config_field`, `retry_after_ms` and `doc_url`.
`NotConfigured("api_key")` is what turns "the tool failed" into a link to the
exact settings field.

Anything else a handler raises is adopted as `INTERNAL`, except `ValueError` /
`TypeError` (→ `BAD_ARGUMENTS`), `KeyError` (→ `NOT_FOUND`), `TimeoutError` and
`PermissionError`.

Note the 0.5.0 change: `call_tool` and `execute_action` **no longer swallow
exceptions**. An unknown tool raises `NotFound` instead of returning
`{"success": False, ...}`.

## Testing

```python
from astra_plugin_sdk.testing import Harness, fuzz_configs

from src.plugin import DiceRoller


def test_roll():
    with Harness(DiceRoller()) as h:
        assert h.tool_names() == ["roll"]

        result = h.call_tool("roll", count=3, sides=6)
        assert result.success, result.code
        assert result.json == "3 d6"

        assert len(h.host.fired_triggers()) == 1
        assert h.host.logs()


def test_no_config_the_daemon_can_deliver_crashes_this_plugin():
    with Harness(DiceRoller()) as h:
        for payload in fuzz_configs():
            h.set_config(payload)
```

Every block above was executed against this checkout before it was written down.

- **`Harness`** — level 1. In process, no daemon, no socket, but through the
  real gRPC servicer, so a tool that is declared and not routed fails here.
  `h.host` is a `RecordingHost`: `.logs()`, `.fired_triggers()`, `.variables()`,
  `.ui_pushes()`, `.chat_messages()`, and `.fail_next(...)` / `.fail_always(...)`
  to stage the refusal a user's `[permissions]` would produce.
- **`WireHarness`** / **`MockDaemon`** — level 2. A real gRPC server, a real
  `Register` handshake, a real session token, real protobuf encoding.
  `unauthenticated_calls()` lists every host RPC that arrived without a valid
  token.

The fixtures register themselves through a `pytest11` entry point, so
`astra_harness`, `astra_wire`, `golden_pcm`, `wake_seed` and `fuzz_config` are
usable with no `conftest.py` at all.

## What this SDK does not do

- **No isolation.** Your plugin is a native process with the user's full
  privileges. Permissions constrain what the *daemon* will do for you; nothing
  constrains what your process does to the machine.
- `tts_synthesize_stream` is implemented here and **the daemon has no call site
  for `TtsSynthesizeStream`**. `ai_get_models` is deprecated. Both are listed
  under "Findings" in the generated hook-parity page, which `tools/parity`
  renders from [`spec/hooks.yaml`](../spec/hooks.yaml).
- There is no `chat_message_sync` / `on_chat_sync` hook. That event was retired;
  a client plugin uses `is_client()` plus `on_conversation_event`.

Full history, including everything breaking in 0.5.0:
[`CHANGELOG.md`](CHANGELOG.md).

## License

MIT.
