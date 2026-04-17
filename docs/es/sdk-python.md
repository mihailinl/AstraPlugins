# SDK de Python

El SDK de Python utiliza una API **declarativa, basada en decoradores**. Cree una subclase de `Plugin`, decore los métodos con `@tool`, `@action` o `@trigger`, y el SDK construye automáticamente los metadatos de las capacidades a partir de sus anotaciones de tipo.

Paquete: `astra-plugin-sdk` en `AstraPlugins/astra-plugin-sdk-python`.
Fuente de verdad: `astra_plugin_sdk/plugin.py` y `astra_plugin_sdk/decorators.py`.

## Instalación

Requiere Python 3.10+. Añada a su `pyproject.toml`:

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

El daemon utiliza [`uv`](https://docs.astral.sh/uv/) para instalar las dependencias de su plugin en un entorno virtual aislado cuando carga el paquete. No necesita gestionar venvs manualmente.

## Plugin mínimo

```python
from astra_plugin_sdk import Plugin, tool

class MyPlugin(Plugin):
    @tool("Say hello")
    async def greet(self, name: str) -> dict:
        return {"greeting": f"Hello, {name}!"}

if __name__ == "__main__":
    MyPlugin().run()
```

`Plugin.run()` se encarga del análisis de argumentos de línea de comandos (`--daemon-addr`, `--plugin-id`, `--auth-token`), inicia un servidor gRPC en un puerto local aleatorio, se registra con el daemon, despacha las llamadas entrantes y gestiona las señales de cierre.

## Decoradores

### `@tool(description)`

Registra un método como herramienta de IA. Las anotaciones de tipo se convierten en JSON Schema automáticamente (`decorators.py:28-92`).

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

Anotaciones de tipo soportadas:

| Anotación | JSON Schema |
| --- | --- |
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` | `{"type": "array", "items": ...}` |
| `dict` | `{"type": "object"}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `Optional[T]` | Esquema para `T`, campo marcado como no obligatorio |

Los parámetros sin valores por defecto se marcan como `required`. El valor de retorno se envuelve automáticamente en `{"success": True, "result": ...}`.

### `@action(label, *, icon_svg="", fields=[], ai_available=False, ai_description="", ai_primary_field="")`

Registra un tipo de acción del Command Graph. El método se invoca cuando un comando ejecuta esta acción.

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

Registra un tipo de disparador. El método decorado contiene solamente metadatos — dispare el disparador desde su propio trabajo en segundo plano mediante `self.fire_trigger`.

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

## Builders `Field`

Todos los builders son métodos estáticos de `Field` (`decorators.py:189-319`):

```python
Field.text(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea_with_variables(id, label, ...)
Field.dropdown(id, label, *, options, default="", description="", conditions=[])
Field.number(id, label, *, min=None, max=None, step=None, default="", ...)
Field.toggle(id, label, *, default=False, description="", conditions=[])
```

`dropdown.options` acepta tuplas, diccionarios o cadenas simples:

```python
Field.dropdown("mode", "Mode", options=[("fast", "Fast"), ("slow", "Slow")])
Field.dropdown("mode", "Mode", options=[{"value": "fast", "label": "Fast"}])
Field.dropdown("mode", "Mode", options=["fast", "slow"])
```

Condiciones de visibilidad:

```python
Field.text("custom_value", "Custom value", conditions=[
    Field.condition("mode", "equals", "custom")
])
```

## Hooks de ciclo de vida

Sobrescriba cualquiera de estos en su subclase:

| Hook | Propósito |
| --- | --- |
| `async def on_daemon_client_ready(self, client: DaemonClient)` | Invocado tras el registro para plugins cliente — conserve `client` para acceder a la API del daemon. |
| `async def on_config_changed(self, config: dict)` | Configuración actualizada (ya sea desde la interfaz o mediante `ConfigService.SetConfig`). |
| `async def on_language_changed(self, language: str)` | Cambió el idioma de la interfaz del daemon — llame a `self.i18n.set_language(language)`. |
| `async def on_active_triggers(self, active_types: list[str])` | Actualiza `self.active_triggers` — úselo para evitar disparar disparadores sin oyentes. |
| `async def on_shutdown(self)` | El daemon solicitó el cierre — libere recursos aquí. |
| `async def health_check(self) -> (bool, str)` | Devuelva `(healthy, status_message)`. |

## Eventos

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

## Plugins cliente

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

`DaemonClient` expone `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService` y `MonitorService`. Consulte `daemon_client.py` para todos los métodos.

## Registro de logs

```python
await self.log_info("Processing request")
await self.log_warn("Rate limit near")
await self.log_error("Connection failed")

# Or call HostClient directly:
await self.host.log("info", "Plugin started")
```

Los mensajes de log llegan al búfer de logs del daemon y aparecen en la interfaz de Plugins.

## Disparar disparadores

```python
await self.fire_trigger("on_roll_total", {"total": 42})
```

`fire_trigger` envía el evento al daemon, que lo compara con los comandos registrados. Es seguro llamarlo cuando no existen oyentes, pero conviene verificar antes `self.active_triggers` para evitar RPCs innecesarios.

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

Los archivos de traducciones residen en `locales/en.json`, `locales/ru.json`, etc. Las claves desconocidas recurren al archivo en inglés y, en último término, a la propia clave.

## Contribuciones de interfaz

```python
def __init__(self):
    super().__init__()
    self.ui_page("stats", "Stats", "http://localhost:8123/stats.html")
    self.ui_effect("http://localhost:8123/snow.html")
    self.ui_overlay("clock", "http://localhost:8123/clock.html",
                    width=200, height=80)
```

## Ejemplo práctico — text-utils

Consulte `AstraPlugins/examples/text-utils`. Aspectos destacados:

- Herramientas: `word_count`, `case_convert`, `regex_match`.
- Acción: `transform_text` con `Field.dropdown`.
- Disparador: `on_time` con un bucle asyncio en segundo plano.
- Configuración: `max_text_length` mediante `[config].schema` en `plugin.toml`.
- `on_config_changed` actualiza los límites en tiempo de ejecución.

Manifiesto:

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

## Dónde continuar

- [Capacidades](capabilities.md) — comportamiento completo por capacidad.
- [Manifiesto](manifest.md) — cada campo de `plugin.toml`.
- [Publicación](publishing.md) — construir, firmar, distribuir.
