# Python-SDK

Das Python-SDK verwendet eine **deklarative, decorator-basierte** API. Leiten Sie von `Plugin` ab, dekorieren Sie Methoden mit `@tool`, `@action` oder `@trigger` — das SDK erzeugt die Metadaten der Fähigkeiten automatisch aus Ihren Type-Hints.

Paket: `astra-plugin-sdk` unter `AstraPlugins/astra-plugin-sdk-python`.
Maßgebliche Quelle: `astra_plugin_sdk/plugin.py` und `astra_plugin_sdk/decorators.py`.

## Installation

Erfordert Python 3.10+. Fügen Sie Folgendes zu Ihrer `pyproject.toml` hinzu:

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

Der Daemon nutzt [`uv`](https://docs.astral.sh/uv/), um die Abhängigkeiten Ihres Plugins in einer isolierten virtuellen Umgebung zu installieren, sobald er das Bundle lädt. Sie müssen keine venvs von Hand verwalten.

## Minimales Plugin

```python
from astra_plugin_sdk import Plugin, tool

class MyPlugin(Plugin):
    @tool("Say hello")
    async def greet(self, name: str) -> dict:
        return {"greeting": f"Hello, {name}!"}

if __name__ == "__main__":
    MyPlugin().run()
```

`Plugin.run()` übernimmt das Parsen der CLI-Argumente (`--daemon-addr`, `--plugin-id`, `--auth-token`), startet einen gRPC-Server auf einem zufälligen lokalen Port, registriert sich beim Daemon, verteilt eingehende Aufrufe und behandelt Shutdown-Signale.

## Dekoratoren

### `@tool(description)`

Registriert eine Methode als KI-Tool. Type-Hints werden automatisch in JSON-Schema konvertiert (`decorators.py:28-92`).

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

Unterstützte Type-Hints:

| Hint | JSON-Schema |
| --- | --- |
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` | `{"type": "array", "items": ...}` |
| `dict` | `{"type": "object"}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `Optional[T]` | Schema für `T`, Feld als nicht erforderlich markiert |

Parameter ohne Defaultwert werden als `required` markiert. Der Rückgabewert wird automatisch in `{"success": True, "result": ...}` verpackt.

### `@action(label, *, icon_svg="", fields=[], ai_available=False, ai_description="", ai_primary_field="")`

Registriert einen Aktionstyp für den Command Graph. Die Methode wird aufgerufen, wenn ein Befehl diese Aktion ausführt.

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

Registriert einen Triggertyp. Die dekorierte Methode enthält nur Metadaten — den Trigger lösen Sie aus Ihrer eigenen Hintergrundarbeit über `self.fire_trigger` aus.

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

## `Field`-Builder

Alle Builder sind statische Methoden von `Field` (`decorators.py:189-319`):

```python
Field.text(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea_with_variables(id, label, ...)
Field.dropdown(id, label, *, options, default="", description="", conditions=[])
Field.number(id, label, *, min=None, max=None, step=None, default="", ...)
Field.toggle(id, label, *, default=False, description="", conditions=[])
```

`dropdown.options` akzeptiert Tupel, Dicts oder einfache Strings:

```python
Field.dropdown("mode", "Mode", options=[("fast", "Fast"), ("slow", "Slow")])
Field.dropdown("mode", "Mode", options=[{"value": "fast", "label": "Fast"}])
Field.dropdown("mode", "Mode", options=["fast", "slow"])
```

Sichtbarkeitsbedingungen:

```python
Field.text("custom_value", "Custom value", conditions=[
    Field.condition("mode", "equals", "custom")
])
```

## Lifecycle-Hooks

Überschreiben Sie eine dieser Methoden in Ihrer Unterklasse:

| Hook | Zweck |
| --- | --- |
| `async def on_daemon_client_ready(self, client: DaemonClient)` | Wird nach der Registrierung für Client-Plugins aufgerufen — halten Sie `client` für den Zugriff auf die Daemon-API fest. |
| `async def on_config_changed(self, config: dict)` | Konfiguration wurde aktualisiert (durch die UI oder `ConfigService.SetConfig`). |
| `async def on_language_changed(self, language: str)` | Die UI-Sprache des Daemons hat sich geändert — rufen Sie `self.i18n.set_language(language)` auf. |
| `async def on_active_triggers(self, active_types: list[str])` | Aktualisiert `self.active_triggers` — nutzen Sie es, um das Auslösen von Triggern ohne Zuhörer zu überspringen. |
| `async def on_shutdown(self)` | Der Daemon hat das Herunterfahren angefordert — geben Sie hier Ressourcen frei. |
| `async def health_check(self) -> (bool, str)` | Gibt `(healthy, status_message)` zurück. |

## Ereignisse

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

## Client-Plugins

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

`DaemonClient` stellt `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService` und `MonitorService` bereit. Alle Methoden finden Sie in `daemon_client.py`.

## Protokollierung

```python
await self.log_info("Processing request")
await self.log_warn("Rate limit near")
await self.log_error("Connection failed")

# Or call HostClient directly:
await self.host.log("info", "Plugin started")
```

Log-Nachrichten landen im Log-Puffer des Daemons und erscheinen in der Plugins-UI.

## Trigger auslösen

```python
await self.fire_trigger("on_roll_total", {"total": 42})
```

`fire_trigger` sendet das Ereignis an den Daemon, der es gegen die registrierten Befehle abgleicht. Der Aufruf ist auch ohne Zuhörer sicher, prüfen Sie jedoch vorher `self.active_triggers`, um unnötige RPCs zu vermeiden.

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

Sprachdateien liegen unter `locales/en.json`, `locales/ru.json` usw. Unbekannte Schlüssel fallen auf die englische Datei und schließlich auf den Schlüssel selbst zurück.

## UI-Beiträge

```python
def __init__(self):
    super().__init__()
    self.ui_page("stats", "Stats", "http://localhost:8123/stats.html")
    self.ui_effect("http://localhost:8123/snow.html")
    self.ui_overlay("clock", "http://localhost:8123/clock.html",
                    width=200, height=80)
```

## Ausgearbeitetes Beispiel — text-utils

Siehe `AstraPlugins/examples/text-utils`. Highlights:

- Tools: `word_count`, `case_convert`, `regex_match`.
- Aktion: `transform_text` mit `Field.dropdown`.
- Trigger: `on_time` mit einer Hintergrund-asyncio-Schleife.
- Konfiguration: `max_text_length` über `[config].schema` in `plugin.toml`.
- `on_config_changed` aktualisiert die Laufzeitgrenzen.

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

## Wie geht es weiter

- [Fähigkeiten](capabilities.md) — vollständiges Verhalten pro Fähigkeit.
- [Manifest](manifest.md) — jedes `plugin.toml`-Feld.
- [Veröffentlichung](publishing.md) — bauen, signieren, verteilen.
