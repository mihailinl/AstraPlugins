> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/4-sdk/python.md) maßgeblich.

# Das Python-SDK

`astra-plugin-sdk` 0.5.0 auf PyPI. `Plugin` ableiten, Methoden dekorieren,
starten.

<!-- doctest: illustrative reason="a requirements.txt fragment; the scaffold that contains it is what the python-plugin blocks below are executed against" -->
```
astra-plugin-sdk>=0.5,<0.6
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
```

Ein Python-Plugin wird als **`noarch`** verpackt: ein Bundle für jede
Plattform. Sein `[entry]` ist `command = "python"`,
`args = ["-m", "src.plugin"]`, `runtimes = ["python"]`.

## Die Form eines Plugins

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
| `@tool("description")` | Eine Funktion, die das Modell aufrufen darf. Parameter werden zum Schema |
| `@action("label")` | Ein Schritt im Befehlseditor |
| `@trigger(...)` | Ein Trigger-Typ |
| `@ui_call` | Eine Methode, die das eigene UI-iframe des Plugins aufrufen darf |
| `@ui_page` · `@ui_slot` · `@ui_effect` · `@ui_overlay` · `@ui_inject` | **Klassen**-Decorators. Registrieren eine UI-Contribution, ausgeliefert aus dem `ui/`-Verzeichnis des Bundles oder von einer URL, die das Plugin bedient |
| `Field(...)` | Verfeinert das Schema eines Parameters — Beschreibung, Bereich, Enum |

Alles andere ist ein Override auf `Plugin`: `tts_synthesize`,
`tts_list_voices`, `tts_config_fields`, `stt_transcribe`,
`stt_transcribe_stream`, `stt_get_languages`,
`stt_load` / `stt_unload` / `stt_load_state`, `ai_complete`,
`get_action_types`, `execute_action`, `get_trigger_types`,
`get_ui_contributions`, `handle_ui_call`, `on_config_changed`,
`on_language_changed`, `on_active_triggers`, `on_shutdown`, `health_check`.

## Astra ansprechen

Komfortmethoden auf `Plugin` — `self.log_info`, `self.log_warn`,
`self.log_error`, `self.fire_trigger(type, payload_dict)`,
`self.push_to_ui(event, payload_dict)` — und alles andere auf `self.host`:

| `self.host.…` | Permission |
|---|---|
| `log(level, message)` · `get_config()` · `get_daemon_info()` | keine |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope="session")` | `set_variable` |
| `subscribe_events(types, exclude_source_id="")` | `subscribe_events` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(text, …)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

> **`DaemonClient` funktioniert heute für kein Plugin.** Der Daemon
> registriert jedes Plugin als `ClientType::PluginClient`, und sein
> Auth-Interceptor lehnt diese Identität auf jedem Pfad außerhalb von
> `/astra.PluginHostService/` mit
> `permission_denied("plugin session tokens are scoped to PluginHostService")`
> ab — `client = true` ändert daran nichts. Also scheitern
> `submit_user_message`, `subscribe_chat_events`, `speak` und
> `get_settings` alle zur Laufzeit. Die Daemon-seitige Hälfte ist ungebaut,
> nicht kaputt.
>
> **`host.send_chat_message` ist der einzige funktionierende Weg, einen
> AI-Turn auszulösen.**

Für wenn die Daemon-Seite ankommt: Es ist **`submit_user_message`**, nicht
`send_message`, auf dem `DaemonClient`. Der vollständige Client wird an
`on_daemon_client_ready(client)` übergeben, und nur an Plugins, die
`client = true` deklarieren und `True` von `is_client()` zurückgeben.

## Fehler

Wirf sie; das SDK bildet sie auf dieselben Wire-Codes ab wie die beiden
anderen SDKs.

`BadArguments` · `NotFound` · `NotConfigured` · `Unauthorized` ·
`RateLimited` · `Unavailable` · `Timeout` · `InternalError`, alle
Unterklassen von `PluginError`, mit `ErrorCode` als Enum. Siehe
[`reference/errors.md`](../reference/errors.md).

## Capability-Typen sind Dataclasses

`ToolDef`, `VoiceInfo`, `AiModelInfo`, `FieldDef`, `DropdownOption`,
`FieldCondition`, `ActionTypeDef`, `TriggerTypeDef`, `UiContribution`.

Ein rohes `dict` zurückzugeben, wo eine Dataclass erwartet wird,
funktioniert weiterhin und gibt eine `DeprecationWarning` aus: als veraltet
markiert in 0.5.0, entfernbar ab 0.7.0. In CI absichern mit
`python -W error::DeprecationWarning`.

## Testen

| | |
|---|---|
| `testing.Harness` | Das Plugin in diesem Prozess, über den echten Capability-Servicer |
| `testing.WireHarness` | Das Plugin als Prozess, über gRPC |
| `testing.RecordingHost` | Was dein Plugin Astra mitgeteilt hat: `fired_triggers()`, `logs()`, `variables()`, `ui_pushes()`, `chat_messages()`, plus `fail_next` / `fail_always` |
| pytest-Fixtures | `astra_harness` und `astra_wire`, falls du pytest benutzt |

`h.call_tool("name", **args)` nimmt den Tool-Namen **positional** — das `/`
in der Signatur ist tragend, weil ein Tool, dessen eigener Parameter
`name` heißt, sonst nicht aufrufbar wäre.

Der Harness ruft den echten Servicer auf, deckt also ab, was der direkte
Aufruf der Methode nicht abdeckt: dass das Tool unter dem Namen registriert
ist, den der Daemon verwenden wird, dass sein Schema parst, dass Argumente
`json.dumps` → `json.loads` überstehen, dass sich der Rückgabewert
serialisieren lässt, und dass ein geworfener Fehler zu dem Code wird, nach
dem der Daemon handelt.

## Was dieses SDK noch nicht kann

- **`DaemonClient` ist funktionsunfähig.** Der Daemon begrenzt das
  Session-Token jedes Plugins auf `PluginHostService`, sodass jeder
  Daemon-seitige Dienst mit `permission_denied` antwortet — `client = true`
  Plugins eingeschlossen. Benutze `host.send_chat_message`.
- **Kein eigenes `stdout`.** Das SDK konfiguriert stdout auf
  zeilenweise Pufferung um, weil der Supervisor des Daemons es liest, um
  zu erfahren, dass das Plugin lebt; Block-Pufferung ließ den Supervisor
  den Prozess beim Start-Timeout abräumen. Benutze die Logging-Bridge
  (`install_logging_bridge`) statt `print`.
- **Der Start ist langsamer als bei den anderen beiden** — Interpreter plus
  `grpcio`-Import. Das Budget des Daemons beträgt 20 s bis zur ersten
  Ausgabezeile, was großzügig ist, aber ein Plugin, das im Modulbereich
  einen großen ML-Stack importiert, kann es verpassen. Importiere träge
  (lazy), im jeweils benötigten Hook.
- **`ai_get_models` ist veraltet** (0.5.0, entfernbar ab 0.7.0 für die
  dict-Form; der Hook selbst wird in 0.8 ausgemustert) und niemand ruft ihn
  auf.
- **`tts_synthesize_stream` ist gebunden und ungeroutet** — keine
  Aufrufstelle im Daemon.
- **Das Python-SDK ist bei 0.5.0 veröffentlicht**, sodass ein frisches
  Scaffold von PyPI auflöst (verifiziert gegen
  `https://pypi.org/pypi/astra-plugin-sdk/json`). Nimm 0.5.0 oder neuer: es
  ist das erste Release, das den `x-session-token` anhängt, den der Daemon
  bei jedem Host-RPC außer `Register` verlangt, und alles Ältere antwortet
  bei jeder Log-Zeile und jedem Host-Aufruf mit `unauthenticated`.

## Siehe auch

[Hook-Tabelle für Python](../hooks/python.md) ·
[Parität](../reference/parity.md) · [Fehler](../reference/errors.md) ·
[Versionierung](../versioning.md)
</content>
