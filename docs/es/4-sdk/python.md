> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/4-sdk/python.md) es la referencia autorizada.

# El SDK de Python

`astra-plugin-sdk` 0.5.0 en PyPI. Hereda de `Plugin`, decora métodos,
ejecútalo.

<!-- doctest: illustrative reason="a requirements.txt fragment; the scaffold that contains it is what the python-plugin blocks below are executed against" -->
```
astra-plugin-sdk>=0.5,<0.6
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
```

Un plugin de Python se empaqueta como **`noarch`**: un paquete para cada
plataforma. Su `[entry]` es `command = "python"`,
`args = ["-m", "src.plugin"]`, `runtimes = ["python"]`.

## La forma de un plugin

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

## Decoradores

| | |
|---|---|
| `@tool("description")` | Una función que el modelo puede llamar. Los parámetros se convierten en el schema |
| `@action("label")` | Un paso en el editor de comandos |
| `@trigger(...)` | Un tipo de trigger |
| `@ui_call` | Un método que el propio iframe de UI del plugin puede llamar |
| `@ui_page` · `@ui_slot` · `@ui_effect` · `@ui_overlay` · `@ui_inject` | Decoradores de **clase**. Registran una contribución de UI servida desde el directorio `ui/` del paquete o desde una URL que sirve el plugin |
| `Field(...)` | Refina el schema de un parámetro — descripción, rango, enum |

Todo lo demás es un override sobre `Plugin`: `tts_synthesize`,
`tts_list_voices`, `tts_config_fields`, `stt_transcribe`,
`stt_transcribe_stream`, `stt_get_languages`,
`stt_load` / `stt_unload` / `stt_load_state`, `ai_complete`,
`get_action_types`, `execute_action`, `get_trigger_types`,
`get_ui_contributions`, `handle_ui_call`, `on_config_changed`,
`on_language_changed`, `on_active_triggers`, `on_shutdown`, `health_check`.

## Llamar a Astra

Métodos de conveniencia en `Plugin` — `self.log_info`, `self.log_warn`,
`self.log_error`, `self.fire_trigger(type, payload_dict)`,
`self.push_to_ui(event, payload_dict)` — y todo lo demás en `self.host`:

| `self.host.…` | Permiso |
|---|---|
| `log(level, message)` · `get_config()` · `get_daemon_info()` | ninguno |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope="session")` | `set_variable` |
| `subscribe_events(types, exclude_source_id="")` | `subscribe_events` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(text, …)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

> **`DaemonClient` no funciona hoy, para ningún plugin.** El daemon
> registra cada plugin como `ClientType::PluginClient`, y su interceptor de
> autenticación rechaza esa identidad en cualquier ruta fuera de
> `/astra.PluginHostService/` con
> `permission_denied("plugin session tokens are scoped to PluginHostService")`
> — `client = true` no cambia nada de esto. Así que `submit_user_message`,
> `subscribe_chat_events`, `speak` y `get_settings` fallan todos en tiempo
> de ejecución. La mitad del lado del daemon no está construida, no está
> rota.
>
> **`host.send_chat_message` es la única forma que funciona de impulsar un
> turno de IA.**

Para cuando llegue el lado del daemon: es **`submit_user_message`**, no
`send_message`, en el `DaemonClient`. El cliente completo se entrega a
`on_daemon_client_ready(client)`, y solo a los plugins que declaran
`client = true` y devuelven `True` desde `is_client()`.

## Errores

Lánzalos; el SDK los mapea a los mismos códigos de cable que los otros dos
SDK.

`BadArguments` · `NotFound` · `NotConfigured` · `Unauthorized` ·
`RateLimited` · `Unavailable` · `Timeout` · `InternalError`, todas
subclases de `PluginError`, con `ErrorCode` como el enum. Consulta
[`reference/errors.md`](../reference/errors.md).

## Los tipos de capability son dataclasses

`ToolDef`, `VoiceInfo`, `AiModelInfo`, `FieldDef`, `DropdownOption`,
`FieldCondition`, `ActionTypeDef`, `TriggerTypeDef`, `UiContribution`.

Devolver un `dict` sin procesar donde se espera una dataclass sigue
funcionando y emite un `DeprecationWarning`: obsoleto desde 0.5.0,
eliminable a partir de 0.7.0. Bloquéalo en CI con
`python -W error::DeprecationWarning`.

## Pruebas

| | |
|---|---|
| `testing.Harness` | El plugin en este proceso, a través del servicer de capabilities real |
| `testing.WireHarness` | El plugin como proceso, sobre gRPC |
| `testing.RecordingHost` | Lo que tu plugin le dijo a Astra: `fired_triggers()`, `logs()`, `variables()`, `ui_pushes()`, `chat_messages()`, más `fail_next` / `fail_always` |
| Fixtures de pytest | `astra_harness` y `astra_wire`, si usas pytest |

`h.call_tool("name", **args)` toma el nombre del tool de forma
**posicional** — la `/` en la firma es estructural, porque un tool cuyo
propio parámetro se llame `name` sería, si no, imposible de llamar.

El harness llama al servicer real, así que cubre lo que llamar al método
directamente no cubre: que el tool está registrado bajo el nombre que
usará el daemon, que su schema se analiza correctamente, que los
argumentos sobreviven `json.dumps` → `json.loads`, que el valor de
retorno se serializa, y que un error lanzado se convierte en el código
sobre el que actúa el daemon.

## Lo que este SDK todavía no puede hacer

- **`DaemonClient` no es funcional.** El daemon limita el token de sesión
  de cada plugin a `PluginHostService`, así que cada servicio del lado del
  daemon responde `permission_denied` — incluidos los plugins con
  `client = true`. Usa `host.send_chat_message`.
- **Sin `stdout` propio.** El SDK reconfigura stdout a buffering por línea
  porque el supervisor del daemon lo lee para saber que el plugin está
  vivo; el buffering por bloques hacía que el supervisor recogiera el
  proceso al llegar al tiempo de espera de arranque. Usa el puente de
  logging (`install_logging_bridge`) en lugar de `print`.
- **El arranque es más lento que en los otros dos** — intérprete más
  importación de `grpcio`. El presupuesto del daemon es de 20 s hasta la
  primera línea de salida, lo cual es generoso, pero un plugin que importa
  una pila de ML grande en el ámbito del módulo puede no llegar a tiempo.
  Importa de forma perezosa, en el hook que lo necesite.
- **`ai_get_models` está obsoleto** (0.5.0, eliminable en 0.7.0 para la
  forma dict; el hook en sí se retira en 0.8) y nada lo llama.
- **`tts_synthesize_stream` está vinculado pero no enrutado** — sin punto
  de llamada en el daemon.
- **El SDK de Python está publicado en la 0.5.0**, así que un scaffold
  nuevo resuelve desde PyPI (verificado contra
  `https://pypi.org/pypi/astra-plugin-sdk/json`). Toma 0.5.0 o más nuevo:
  es el primer release que adjunta el `x-session-token` que el daemon
  exige en cada RPC del host salvo `Register`, y cualquier versión más
  antigua responde `unauthenticated` en cada línea de log y cada llamada
  al host.

## Ver también

[Tabla de hooks para Python](../hooks/python.md) ·
[paridad](../reference/parity.md) · [errores](../reference/errors.md) ·
[versionado](../versioning.md)
</content>
