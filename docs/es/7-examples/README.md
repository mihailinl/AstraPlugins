> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/7-examples/README.md) es la referencia autorizada.

# Ejemplos

Once plugins en [`examples/`](../../../examples/), todos portados a los
SDK actuales y todos compilados en CI. Lee uno que haga lo que quieres
hacer, y luego empieza desde el scaffold en lugar de desde el ejemplo —
no llevan ningún andamiaje que tengas que borrar.

Cada entrada de abajo se lee del propio `plugin.toml` de ese plugin.

## Los que hay que leer primero

| | Lenguaje | Capabilities | Permisos | Por qué este |
|---|---|---|---|---|
| [`dice-roller`](../../../examples/dice-roller/) | Rust | `tools`, `actions`, `triggers` | `fire_trigger` | El plugin de referencia. Tres capabilities, un permiso, y una suite de pruebas que muestra cómo se prueba cada uno |
| [`json-tools`](../../../examples/json-tools/) | TypeScript | `tools`, `actions`, `triggers` | `set_variable` | La misma forma en TypeScript, y el ejemplo cuyas pruebas llegan al nivel del cable |
| [`text-utils`](../../../examples/text-utils/) | Python | `tools`, `actions`, `triggers` | `fire_trigger` | La misma forma en Python |

Esos tres son deliberadamente el mismo plugin de tres maneras. Si estás
eligiendo un lenguaje, lee los tres y elige el ecosistema del que quieres
extraer bibliotecas — cada capability está disponible en cada SDK.

## Proveedores de voz

| | Lenguaje | Capabilities | Por qué este |
|---|---|---|---|
| [`tone-tts`](../../../examples/tone-tts/) | Rust | `tts` | Un proveedor de texto a voz que habla en pitidos. Una prueba de cableado, no una voz |
| [`mock-stt`](../../../examples/mock-stt/) | Rust | `stt` | Devuelve una transcripción determinista que describe el audio que recibió. El stream bidireccional, menos un reconocedor |
| [`echo-stt`](../../../examples/echo-stt/) | Rust | `stt` | No transcribe nada y reproduce tu micrófono de vuelta a través del proceso del plugin. Para oír qué te envía realmente el daemon |

`tone-tts` y `mock-stt` son dos de los cuatro plugins que el job de
conformidad ejecuta en cada corrida de CI, precisamente porque ejercitan
hooks que ningún otro ejercita.

## UI, y `dom_access`

Estos ejecutan código dentro de la ventana de Astra. Son la razón por la
que [el sideload no tiene techo de permisos](../5-publish/sideload.md):
`dom_access` no se puede desarrollar de ninguna otra forma.

| | Lenguaje | Capabilities | Por qué este |
|---|---|---|---|
| [`companion`](../../../examples/companion/) | Rust | `ui_contributions`, `dom_access` | Un gato que vuela por la ventana y dice cosas. La contribución de UI completa más pequeña |
| [`bad-apple`](../../../examples/bad-apple/) | Rust | `ui_contributions`, `dom_access` | La animación de *Bad Apple!!* en cuatro modos de renderizado. Incluye sus propios datos de frames; ver su `SETUP.md` |
| [`doom`](../../../examples/doom/) | Rust | `ui_contributions`, `dom_access` | Una página de Doom ejecutando un motor de WebAssembly. Lo más extremo que puede ser una contribución de UI |

`companion` es el cuarto plugin que ejecuta el job de conformidad, para
`ui_contributions`.

## Clientes

Un plugin `client` es su propio frontend de chat — su propia sesión, su
propia superficie. Es una capability de alto riesgo, y se rechaza de
plano en un
[archivo importado localmente](../5-publish/local-install.md).

> **Ambos van por delante del daemon.** La mitad del lado del daemon de
> la vía de cliente no está construida: cada plugin se registra como
> `ClientType::PluginClient`, y el interceptor de autenticación rechaza
> esa identidad en cualquier ruta gRPC fuera de
> `/astra.PluginHostService/`. Así que el `DaemonClient` contra el que
> están escritos estos dos responde `permission_denied` en cada llamada.
> Léelos por la forma de un plugin cliente — la superficie, el flujo de
> eventos, el I18n — no como algo que puedas ejecutar de extremo a
> extremo hoy. Consulta
> [la sección `Daemon` del SDK de Rust](../4-sdk/rust.md#daemon-presente-en-el-sdk-rechazado-por-el-daemon).

| | Lenguaje | Capabilities | Por qué este |
|---|---|---|---|
| [`telegram-client`](../../../examples/telegram-client/) | Rust | `client` | Cada conversación de Astra se convierte en un tema de Telegram, con respuestas en streaming |
| [`web-chat`](../../../examples/web-chat/) | Rust | `client` | Una ventana de navegador que habla con Astra. Para observar la sincronización multi-cliente en acción |

## Plataformas

Ninguno de los once declara un bloque `[platform]`, lo que significa que
el daemon considera cada uno compatible en todas partes — correcto para
los dos interpretados, y algo que un plugin nativo *publicado* debería
ajustar. Consulta [plataformas](../1-orientation/platforms.md).

| Lenguaje | Qué compila un release |
|---|---|
| Rust (nueve de ellos) | `linux-x64` **y** `windows-x64`, un paquete cada uno |
| TypeScript (`json-tools`) | un paquete `noarch` |
| Python (`text-utils`) | un paquete `noarch` |

`doom` y `bad-apple` además distribuyen datos — un motor de WebAssembly,
unos pocos megabytes de frames — y su `SETUP.md` dice de dónde vienen y
cómo regenerarlos.

## Con qué se prueban

| Nivel | Qué se ejecuta | Qué ejemplos |
|---|---|---|
| Unitario | el harness en proceso del SDK, en las propias pruebas de cada ejemplo | `dice-roller`, `mock-stt`, `text-utils`, `json-tools` |
| Compilación | cada ejemplo se compila en cada corrida de CI | los once |
| Conformidad | `astra-plugin test` arranca el proceso real contra un daemon simulado y ejercita cada hook que impliquen sus capabilities | `dice-roller`, `mock-stt`, `tone-tts`, `companion` |

El conjunto de conformidad se elige por cobertura de la tabla de hooks,
no por variedad — tools/actions/triggers, el stream bidireccional de
STT, TTS, y contribuciones de UI. **`ai_provider` no tiene ejemplo y por
tanto no está cubierto**, lo cual merece decirse en voz alta: una brecha
de cobertura que nadie nombra se convierte en una que todos asumen que
está cerrada.

Los ejemplos de Python y TypeScript todavía no están en el job de
conformidad, porque sus SDK no están publicados y una corrida de
conformidad que instala a medias un SDK termina informando sobre la
instalación en lugar de sobre el plugin. `astra-plugin test` ejercita un
proceso y no le importa en qué lenguaje se escribió, así que se unirán
al job el día en que se publiquen los SDK.

## Ejecutar uno

<!-- doctest: cli -->
```bash
cd examples/dice-roller
astra-plugin check --strict
astra-plugin test
astra-plugin dev
```

`dev` necesita un Astra en ejecución y el modo desarrollador — lee
[qué cuesta eso](../5-publish/sideload.md) primero.
</content>
