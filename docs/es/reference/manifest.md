> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/reference/manifest.md) es la referencia autorizada. La página en inglés está GENERADA por `tools/docgen/manifest.py` — esta traducción es una instantánea mantenida a mano, no otra copia generada.

# Referencia de `plugin.toml`

Cada sección, cada clave, y todo lo que rechaza alguna. Derivada de
[`astra-plugin-manifest`](../../../astra-plugin-cli/vendor/astra-plugin-manifest/src/manifest.rs)
— el crate con el que el daemon analiza tu manifiesto, vendorizado en
este repositorio y mantenido idéntico byte a byte a la copia de Astra
por `tools/check-manifest-crate.sh`. No hay una segunda definición de
un manifiesto que pueda discrepar de esta página.

Manifiesto de plugin completo, analizado a partir de `plugin.toml`.

Deliberadamente **no** `deny_unknown_fields`: se añaden secciones a lo
largo de los releases — `[permissions]` fue la última — y un daemon más
antiguo debe poder saltarse una sección que no conoce en lugar de
rechazar el plugin. `[capabilities]` es la excepción, y
[`Capabilities`] explica por qué.

## Secciones

| Sección | Obligatoria | Qué declara |
|---|---|---|
| [`[plugin]`](#plugin) | **sí** | Identidad y metadatos del plugin. |
| [`[entry]`](#entry) | **sí** | Cómo arrancar el proceso del plugin. |
| [`[capabilities]`](#capabilities) | no | Qué **implementa** el plugin, daemon→plugin. |
| [`[permissions]`](#permissions) | no | Qué pide **llamar** el plugin, plugin→daemon — y es una *petición*. |
| [`[config]`](#config) | no | JSON Schema para la configuración del plugin (genera automáticamente la UI de ajustes). |
| [`[dependencies]`](#dependencies) | no | Una tabla de strings, sin schema propio. |
| [`[platform]`](#platform) | no | Requisitos de plataforma — `[platform]` en `plugin.toml`. |
| [`[build]`](#build) | no | Metadatos de compilación añadidos por `astra-plugin build`. |
| [`[ui]`](#ui) | no | Definiciones de contribución de UI declaradas en plugin.toml. |

Una sección que este Astra no conoce se **conserva, no se rechaza** —
las secciones se añaden a lo largo de los releases y un daemon más
antiguo tiene que poder saltarse una. `[capabilities]` es la única
excepción, y la razón está abajo.

## `[plugin]`

Identidad y metadatos del plugin.

| Clave | Tipo | Obligatoria | Por defecto | Qué es |
|---|---|---|---|---|
| `id` [†](#lo-que-se-rechaza) | string | **sí** | — | — |
| `name` [†](#lo-que-se-rechaza) | string | **sí** | — | — |
| `version` [†](#lo-que-se-rechaza) | string | **sí** | — | — |
| `description` | string | no | `""` | — |
| `author` | string | no | `""` | — |
| `license` | string | no | `""` | — |
| `homepage` | string | no | `""` | — |
| `min_astra_version` [†](#lo-que-se-rechaza) | string | no | `""` | El Astra más antiguo con el que funciona este plugin, como versión semver (`"0.9.0"`). |
| `call_timeout_secs` | integer | no | ausente | Cuánto espera el daemon a `CallTool` / `ExecuteAction` antes de rendirse, en segundos. |

† tiene una regla que rechaza el manifiesto de plano — consulta
[lo que se rechaza](#lo-que-se-rechaza) para la condición y el mensaje.

**`plugin.min_astra_version`.** El Astra más antiguo con el que
funciona este plugin, como versión semver (`"0.9.0"`). Vacío = sin
requisito.

Su *sintaxis* se valida en todas partes por
[`PluginManifest::validate`]. Su *valor* se compara contra el Astra en
ejecución solo en una compilación que conoce uno — consulta
[`crate::host_astra_version`]. Existió durante todo un release como un
campo que se analizaba y nunca se leía, así que un plugin que
necesitaba una función del daemon que el host no tenía instalada se
instalaba limpiamente y luego fallaba en la única llamada que la
necesitaba, lo cual el usuario lee como "este plugin está roto".

**`plugin.call_timeout_secs`.** Cuánto espera el daemon a `CallTool` /
`ExecuteAction` antes de rendirse, en segundos. `None` → el
`PLUGIN_CALL_TIMEOUT` propio del daemon.

Un plugin que da la cara por un agente de larga ejecución debe declarar
esto: el valor por defecto del daemon es deliberadamente menor que
"para siempre", y a un plugin cuyo propio presupuesto de trabajo lo
supere se le descartaría el resultado mientras su subproceso sigue
corriendo (`coding-agents` distribuye un valor por defecto de 180 s).
Por plugin, del mismo modo que `McpServerConfig::timeout_secs` es por
servidor.

## `[entry]`

Cómo arrancar el proceso del plugin.

| Clave | Tipo | Obligatoria | Por defecto | Qué es |
|---|---|---|---|---|
| `command` [†](#lo-que-se-rechaza) | string | **sí** | — | — |
| `args` | array de strings | no | vacío | — |
| `cwd` | string | no | `.` | — |
| `runtimes` | array de strings | no | vacío | — |

† tiene una regla que rechaza el manifiesto de plano — consulta
[lo que se rechaza](#lo-que-se-rechaza) para la condición y el mensaje.

## `[capabilities]`

Qué **implementa** el plugin, daemon→plugin.

**Una clave desconocida aquí hace fallar todo el manifiesto.**
`Capabilities` es `#[serde(deny_unknown_fields)]`, la única entre las
secciones: son enteramente booleanos de opt-in, así que una errata se
leería, si no, exactamente como `false`, y el plugin se instalaría sin
haber declarado nada. No es hipotético — tres ejemplos incluidos en el
repositorio declaraban `ui_panels`, un nombre que ningún daemon tuvo
jamás, y el único síntoma era que `astra-plugin check` imprimía "No
capabilities enabled".

Cada clave es un booleano y por defecto es `false`. La columna de la
derecha es la unión con
[`spec/hooks.yaml`](../../../spec/hooks.yaml): los hooks que tu plugin
debe servir para que la capability funcione en absoluto. Los hooks
`optional` se omiten aquí; [`parity.md`](./parity.md) los tiene todos.

| Clave | Hooks a cuya implementación obliga |
|---|---|
| `tools` | `ListTools`, `CallTool` |
| `tts` | `TtsSynthesize`, `TtsListVoices` |
| `stt` | `SttProcess`, `SttGetLanguages` |
| `ai_provider` | `AiComplete` |
| `client` | `SendChatMessage` |
| `actions` | `ExecuteAction`, `GetPluginActionTypes` |
| `triggers` | `GetPluginTriggerTypes`, `FireTrigger` |
| `ui_contributions` | `GetUiContributions` |
| `event_handlers` | `SubscribeEvents` |
| `dom_access` | ninguno |

**Nombres que nunca fueron reales:**

- `ui_panels` → `ui_contributions`

## `[permissions]`

Qué pide **llamar** el plugin, plugin→daemon — y es una *petición*.

Ausente significa ningún RPC del host más allá del conjunto de arranque
siempre permitido (§5.6). El conjunto que un plugin realmente tiene lo
resuelve el daemon a partir de su procedencia y nunca se lee de aquí
para un plugin que tiene un registro de confianza: un manifiesto vive
en el propio directorio del plugin, que el plugin puede escribir.

Cada clave es un id de permiso y cada valor es una tabla.

Un id que este Astra no conoce se conserva e inerte: compatibilidad
hacia adelante, y `permissions_hash` se calcula sobre estos bytes por
tres implementaciones, así que un lector que descartara una clave no
reconocida discreparía con las otras dos sobre qué se firmó.

| Id | Bloquea | Casilla propia de consentimiento | Rechazado en importación local | Qué otorga |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | no | no | Ejecuta las automatizaciones guardadas del usuario. |
| `subscribe_events` | `SubscribeEvents` | no | no | Recibe eventos del daemon. |
| `set_variable` | `SetVariable` | no | no | Escribe en el contexto de variables del daemon (con espacio de nombres del plugin que llama). |
| `send_chat_message` | `SendChatMessage` | **sí** | **sí** | Impulsa un turno de IA. |
| `push_to_ui` | `PushToUi` | **sí** | no | Envía un evento a la ventana de Astra. |
| `set_theme_contribution` | `SetThemeContribution` | **sí** | **sí** | Cambia el estilo de toda la app. |
| `dom_access` | — | **sí** | **sí** | Ejecuta el propio código del plugin dentro de la ventana de Astra, con acceso a las conversaciones del usuario y a la interfaz de cualquier otro plugin. |
| `client` | — | **sí** | **sí** | Actúa como frontend cliente (su propia superficie de chat, su propia sesión). |

*Bloquea* es el RPC del host que el daemon rechaza sin el permiso, de
[`spec/hooks.yaml`](../../../spec/hooks.yaml); la regla de paridad R6
comprueba esa columna contra el propio `HOST_RPC_PERMISSIONS` del
daemon, la tabla que lee `require_permission`. Una celda vacía es un
permiso de **superficie** que no bloquea ningún RPC: `dom_access`
decide cómo se renderiza una contribución de UI, y `client` es un
techo de capability.

*Rechazado en importación local* es el techo sobre un archivo
`.astraplugin` que el usuario importó a mano en lugar de instalarlo
desde la tienda: esos ids se descartan de plano, no solo se advierten.
Un directorio fuente cargado con el modo desarrollador activado
deliberadamente no está capado — es el bucle de creación para plugins
de UI.

### El valor de una clave de permiso

| Clave | Tipo | Obligatoria | Por defecto | Qué es |
|---|---|---|---|---|
| `reason` | string | no | `""` | Las propias palabras del autor, renderizadas *subordinadas* a la etiqueta propia de la app (§4.3: entrecomillado, texto plano, ≤140 caracteres, siempre precedido de "The author says:"). |
| `types` | array de strings | no | vacío | `subscribe_events.types` — los tipos de evento solicitados. |
| `scopes` | array de strings | no | vacío | `set_variable.scopes` — `"plugin"` / `"session"` / `"persistent"`. |

**`<permission>.reason`.** Las propias palabras del autor, renderizadas
*subordinadas* a la etiqueta propia de la app (§4.3: entrecomillado,
texto plano, ≤140 caracteres, siempre precedido de "The author says:").
Nunca es la etiqueta misma — las correcciones de redacción se
distribuyen con Astra y no deben poder redactarse desde un listado.

**`<permission>.types`.** `subscribe_events.types` — los tipos de
evento solicitados.

**Una lista blanca, y una vacía no permite nada.** Consulta
[`Permissions::event_types`].

**`<permission>.scopes`.** `set_variable.scopes` — `"plugin"` /
`"session"` / `"persistent"`. Reservado; el daemon da espacio de
nombres hoy a cada escritura de plugin por id de plugin, así que esto
todavía no acota nada y se analiza para que un manifiesto que lo
declare hashee igual en todas partes.

**`fire_trigger`.** `PluginHostService.FireTrigger` — ejecuta las
automatizaciones guardadas del usuario.

**`subscribe_events`.** `PluginHostService.SubscribeEvents` — recibe
eventos del daemon.

Lleva un argumento: [`PermissionRequest::types`] es la **lista blanca**
de tipos de evento, y la aplica el daemon en lugar del filtro que envía
el plugin. Sin eso, cada suscriptor recibía todos los eventos —
incluido `speech_recognized`, que lleva las transcripciones del
usuario.

**`set_variable`.** `PluginHostService.SetVariable` — escribe en el
contexto de variables del daemon (con espacio de nombres del plugin que
llama).

**`send_chat_message`.** `PluginHostService.SendChatMessage` — impulsa
un turno de IA. **Alto riesgo.**

**`push_to_ui`.** `PluginHostService.PushToUi` — envía un evento a la
ventana de Astra. **Alto riesgo.**

**`set_theme_contribution`.** `PluginHostService.SetThemeContribution`
— cambia el estilo de toda la app. **Alto riesgo.**

**`dom_access`.** Ejecuta el propio código del plugin dentro de la
ventana de Astra, con acceso a las conversaciones del usuario y a la
interfaz de cualquier otro plugin. **Alto riesgo, y el único al que el
§4.3 da una segunda pantalla.**

**`client`.** Actúa como frontend cliente (su propia superficie de
chat, su propia sesión). **Alto riesgo.**

## `[config]`

JSON Schema para la configuración del plugin (genera automáticamente la
UI de ajustes).

| Clave | Tipo | Obligatoria | Por defecto | Qué es |
|---|---|---|---|---|
| `schema` | string | **sí** | — | JSON Schema como string. |

## `[dependencies]`

Una tabla libre de `name = "requisito de versión"`. Ambas mitades son
strings y el crate las lee como tales — `HashMap<String, String>`, sin
schema, sin resolución, y nada instala nada a partir de ella.
`astra-plugin check` lista lo declarado y avisa cuando un requisito
está vacío; eso es todo su efecto.

## `[platform]`

| Clave | Tipo | Obligatoria | Por defecto | Qué es |
|---|---|---|---|---|
| `os` | array de strings | no | vacío | — |
| `arch` | array de strings | no | vacío | — |

**`KNOWN_OS_VALUES`** — `linux`, `windows`, `macos`

Los valores de `os` que puede nombrar `[platform] os = [...]`, en el
vocabulario que habla [`current_platform`].

Más amplio que el conjunto para el que Astra distribuye un daemon:
declarar `os = ["macos"]` es una afirmación sobre el plugin, no una
afirmación de que exista un host, y un validador que lo rechazara
estaría rechazando un manifiesto correcto.

**`KNOWN_ARCH_VALUES`** — `x86_64`, `aarch64`

Los valores de `arch` que puede nombrar `[platform] arch = [...]`.

**`RESERVED_PLATFORM_KEYS`** — `linux-x64`, `windows-x64`,
`linux-arm64`, `windows-arm64`, `macos-x64`, `macos-arm64`, `noarch`

Cada clave de artefacto que reserva el schema del registro, en el orden
en que un generador debería emitirlas.

Solo [`platform_key_for`] decide cuáles de estas acepta un *daemon en
ejecución*, y acepta dos. El resto están reservadas para que el
formato del índice nunca tenga que cambiar si Astra más adelante
distribuye esos hosts, y para que un validador del registro pueda
rechazar una errata (`mac-arm64`, `linux-amd64`) en lugar de escribir
una clave que ningún daemon buscará jamás.

**Reservado no es soportado.** El workflow de release de Astra no
compila ni un daemon de macOS ni uno de arm64, así que un paquete
publicado bajo `macos-x64`, `macos-arm64`, `linux-arm64` o
`windows-arm64` no tiene host donde ejecutarse. Un generador que emita
uno está publicando un archivo que nadie puede instalar.

`noarch` es el caso de lenguaje interpretado (TypeScript, Python). Está
reservado aquí para validadores, pero el daemon **no** lo busca: según
la spec del bundle, el índice escribe la misma URL y el mismo digest
bajo cada clave de plataforma *soportada*, así que un paquete `noarch`
se encuentra bajo `linux-x64` / `windows-x64` como cualquier otro.

Nada en la ruta de ejecución del daemon lee esta lista — sus
consumidores son el generador de índice en el repositorio del
registro, el `check` de la CLI, y la prueba de abajo que mantiene
honestas a ambas mitades. Vive junto a la función que decide cuáles de
estas claves son reales, porque ese es el único lugar donde ambos
hechos se pueden leer juntos.

## `[build]`

Metadatos de compilación añadidos por `astra-plugin build`.

| Clave | Tipo | Obligatoria | Por defecto | Qué es |
|---|---|---|---|---|
| `bundled` | boolean | no | `false` | — |
| `language` | string | no | `""` | — |
| `python_version` | string | no | `""` | — |
| `requirements_lock` | string | no | `""` | — |

## `[ui]`

Definiciones de contribución de UI declaradas en plugin.toml.

| Clave | Tipo | Obligatoria | Por defecto | Qué es |
|---|---|---|---|---|
| `contributions` | array de tablas | no | vacío | — |

### `[[ui.contributions]]`

Una definición estática de contribución de UI desde el manifiesto.

| Clave | Tipo | Obligatoria | Por defecto | Qué es |
|---|---|---|---|---|
| `id` | string | **sí** | — | — |
| `slot` | string | no | `""` | — |
| `css_target` | string | no | `""` | — |
| `position` | string | no | `""` | — |
| `url` | string | no | `""` | — |
| `label` | string | no | `""` | — |
| `icon_svg` | string | no | `""` | — |
| `width` | integer | no | `0` | — |
| `height` | integer | no | `0` | — |
| `transparent` | boolean | no | `false` | — |
| `pointer_events` | boolean | no | `true` | — |
| `z_index` | integer | no | `0` | — |
| `props` | tabla de strings | no | vacío | — |

## Lo que se rechaza

Cada rechazo que puede producir `PluginManifest::validate`, con la
condición que lo dispara. Las condiciones son las propias expresiones
de Rust: `plugin.id` se convierte en un componente de ruta —
`<plugins_dir>/<id>/`, creado y luego eliminado con `remove_dir_all` —
así que parafrasear la regla del conjunto de caracteres no es algo que
esta página esté dispuesta a hacer.

| El manifiesto se rechaza cuando | El mensaje |
|---|---|
| `self.plugin.id.is_empty()` | plugin.id is required |
| `self.plugin.name.is_empty()` | plugin.name is required |
| `self.plugin.version.is_empty()` | plugin.version is required |
| `self.entry.command.is_empty()` | entry.command is required |
| `!self.plugin.id.chars().all(\|c\| c.is_ascii_lowercase() \|\| c.is_ascii_digit() \|\| c == '-')` | plugin.id must be lowercase alphanumeric with hyphens: '{}' |
| `self.plugin.id.ends_with('.') \|\| self.plugin.id.ends_with(' ')` | plugin.id must not end with a dot or space: '{}' |
| `is_reserved_device_name(&self.plugin.id)` | plugin.id '{}' is a reserved Windows device name |
| `not (running >= required)` | Plugin '{}' requires Astra {} or newer, but this is Astra {}. Update Astra, or install a build of the plugin that supports {}. |
| ``semver::Version::parse(required)` returns Err` | plugin.min_astra_version '{}' is not a semver version (expected e.g. "0.9.0") |

`min_astra_version` es la única regla con dos mitades. Su **sintaxis**
se comprueba en todas partes, incluido en `astra-plugin check`: un
valor que no es una versión semver es una restricción declarada que no
restringe nada. Su **valor** se compara solo en una compilación que es
en sí misma un Astra — una herramienta que se niega a mirar un plugin
porque apunta a un daemon más nuevo que la propia herramienta sería un
sinsentido.
</content>
