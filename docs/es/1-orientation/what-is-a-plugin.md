> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/1-orientation/what-is-a-plugin.md) es la referencia autorizada.

# Qué es un plugin

Un plugin es un **programa independiente** que el daemon de Astra inicia y que
se comunica con el daemon por gRPC en localhost. No es una biblioteca, no se
carga en el espacio de direcciones de Astra, y no es un script que Astra
interprete. Astra lo lanza como lo haría una shell, con argumentos en la
línea de comandos, y lo detiene pidiéndole que se apague y, si no lo hace,
matando el grupo de procesos.

Ese único hecho determina casi todo lo demás:

- **Puedes escribirlo en cualquier cosa** que hable gRPC. Aquí se ofrecen tres
  SDK — Rust, Python, TypeScript — y están en
  [paridad total](../reference/parity.md): los 35 hooks en los tres.
- **Tiene tus mismos privilegios, no menos.** Consulta [el modelo de seguridad](security.md).
- **Sobrevive mal a sus propios errores, y nada al de Astra.** Un panic en un
  handler se captura y se devuelve como error en lugar de matar el proceso
  (`astra-plugin-sdk/src/panics.rs`); un fallo de todo el proceso lo detecta
  el chequeo de salud del daemon en menos de 15 s.

## Las dos direcciones

Todo lo que hace un plugin es una de dos cosas, y son sistemas separados con
nombres separados en `plugin.toml`.

| | Dirección | Sección del manifiesto | Responde |
|---|---|---|---|
| **Capabilities** | daemon → plugin | `[capabilities]` | Qué implementa el plugin y a qué puede *llamar hacia dentro* Astra |
| **Permissions** | plugin → daemon | `[permissions]` | A qué RPC del host puede *llamar hacia fuera* el plugin |

Antes eran una sola palabra para ambas cosas, y así fue como `dom_access` — lo
más peligroso del sistema — llegó a ser algo que un plugin se concedía a sí
mismo con solo declararlo. Ahora son dos palabras. Declarar
`[capabilities] event_handlers = true` no te permite suscribirte a eventos;
`[permissions] subscribe_events` sí, y solo después de que el usuario dé su
consentimiento.

`[permissions]` es **de denegación por defecto** (default-deny): sin ninguna
sección, un plugin puede llamar a `Register`, `PluginLog`,
`GetPluginSelfConfig` y `GetDaemonInfo`, y nada más
([`spec/permissions.md` §2](../spec/permissions.md)).

## Las diez capabilities

Cada clave es un booleano, `false` por defecto, y te obliga a servir ciertos
hooks. La columna de la derecha muestra los *obligatorios*; los opcionales
están en [la tabla de paridad](../reference/parity.md).

| Clave de `[capabilities]` | Tu plugin se convierte en | Hooks que debes servir |
|---|---|---|
| `tools` | un conjunto de funciones que el modelo puede llamar | `ListTools`, `CallTool` |
| `tts` | un proveedor de texto a voz en los ajustes de Voice | `TtsSynthesize`, `TtsListVoices` |
| `stt` | un proveedor de voz a texto | `SttProcess`, `SttGetLanguages` |
| `ai_provider` | un backend de modelo | `AiComplete` |
| `actions` | pasos en el editor de comandos | `ExecuteAction`, `GetPluginActionTypes` |
| `triggers` | tipos de disparador que los comandos pueden escuchar | `GetPluginTriggerTypes`, `FireTrigger` |
| `ui_contributions` | paneles, páginas y overlays en la ventana de Astra | `GetUiContributions` |
| `event_handlers` | un suscriptor de eventos del daemon | `SubscribeEvents` |
| `client` | su propio frontend de chat | `SendChatMessage` |
| `dom_access` | código que se ejecuta dentro de la ventana de Astra | ninguno — es una decisión de renderizado, no un hook |

Fuente: [`reference/manifest.md`](../reference/manifest.md), generado a partir
del crate con el que el daemon analiza tu manifiesto. `ui_panels` no es una
capability y nunca lo fue — tres ejemplos incluidos en el repositorio la
declaraban, serde descartaba la clave desconocida en silencio, y el único
síntoma era que `astra-plugin check` reportaba cero capabilities. Por eso
exactamente `[capabilities]` rechaza claves desconocidas.

## Cómo se ve un manifiesto

El más pequeño que resulta útil — un plugin con tools, sin permissions, nada
más:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat."
author = "You"
license = "MIT"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
```

Uno que dispara un trigger tiene que pedir el permiso, y `reason` es lo que
lee el usuario cuando Astra le pide que dé su consentimiento:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice, and fire a trigger when one comes up."
author = "You"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

Cada sección y cada clave: [`reference/manifest.md`](../reference/manifest.md).

## Lo que un plugin no puede hacer

- **No puede concederse un permiso a sí mismo — una vez instalado.** El
  bloque `[permissions]` es una solicitud. Para un plugin instalado desde el
  registro o importado como archivo, el conjunto concedido lo resuelve el
  daemon a partir de la procedencia del plugin y se guarda donde el plugin no
  puede escribirlo — el manifiesto vive en el propio directorio del plugin,
  que el plugin sí puede editar. **Un plugin cargado por sideload es la
  excepción**: en ese nivel el manifiesto *es* el registro de consentimiento
  y no hay techo, así que puede ampliar sus propios permisos editando su
  propio archivo. Consulta
  [el modelo de seguridad](security.md#la-procedencia-de-un-plugin-determina-su-techo).
- **No puede llegar directamente al `ChatService` de Astra.** El token de
  sesión que un plugin recibe al registrarse está limitado a
  `PluginHostService`. Impulsar un turno de IA pasa por `SendChatMessage`,
  que está condicionado al permiso `send_chat_message` y se considera de
  alto riesgo.
- **No puede depender de un hook no enrutado.** Un hook puede existir en el
  proto y en los tres SDK y no tener ningún punto de llamada en el daemon:
  `TtsSynthesizeStream` es uno de esos casos hoy. Implementarlo es gratis;
  confiar en que se llame no está soportado hasta que
  [la tabla de paridad](../reference/parity.md) diga `live`.
- **No puede instalarse en una plataforma para la que no tiene bundle.**
  Consulta [plataformas](platforms.md).

## Siguiente

[Arquitectura](architecture.md) si quieres saber cómo se inicia y autentica
el proceso, o ve directo a
[Primeros pasos](../2-tutorial/getting-started.md).
</content>
