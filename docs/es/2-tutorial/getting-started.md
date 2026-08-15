> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/2-tutorial/getting-started.md) es la referencia autorizada.

# Primeros pasos

De cero a un plugin que tira dados, tiene pruebas y está empaquetado para
release. Unos quince minutos, la mayor parte esperando a `cargo`.

Cada bloque de código en esta página se ejecuta mediante
[`docs/tools/doctest.py`](../../tools/doctest.py) en la CI. Si uno está mal,
el build está en rojo antes de que lo leas.

## 1 · Instalar la CLI

Una línea. Tarda unos minutos y termina imprimiendo una versión.

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin 0.2.1
```

Desde un clon, `cargo install --path astra-plugin-cli --locked` hace lo
mismo.

**Necesitas Rust 1.85 o más nuevo y `protoc` en tu PATH.** Sin `protoc` la
compilación se detiene en ``Could not find `protoc` ``. Instálalo con
`apt install protobuf-compiler`, `pacman -S protobuf`, `brew install
protobuf`, o `winget install Google.Protobuf`, y vuelve a ejecutar la línea.

**Toma 0.2.1 o más nuevo.** `0.2.0` escribe un workflow de release que falla
en tu primer push de etiqueta, así que si `--version` imprime `0.2.0`,
vuelve a ejecutar la línea de instalación.

Un apunte, que no te bloquea: la CLI no está en crates.io y no tiene
binarios precompilados, así que compilarla es la única manera de
conseguirla. Los binarios precompilados están planeados. Detalle completo,
incluyendo qué hacer cuando no funciona:
[Instalar la CLI](../install-cli.md).

Comprueba la máquina antes de culpar al código:

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

Responde dieciséis preguntas de una sola vez — qué CLI estás ejecutando, qué
directorio de config resolvió, si Astra es alcanzable, qué toolchains
tienes (`protoc` incluido), y si tu workflow de release está fijado (pinned).
Es lo primero que hay que ejecutar cuando algo resulta confuso.

## 2 · Scaffold

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang rust --template tool
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller --lang rust --template tool" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

Cinco archivos: `plugin.toml`, `Cargo.toml`, `src/main.rs`, `README.md`,
`.gitignore`. `Cargo.toml` tiene **una** dependencia, y `src/main.rs` son
quince líneas más un módulo de pruebas.

`--lang` acepta `rust`, `python` o `typescript`; `--template` elige las
capabilities y el código de ejemplo, y `--capabilities tools,triggers`
sobrescribe lo que implique la plantilla.

### Qué fija (pin) el scaffold

| Lenguaje | El scaffold fija | Publicado |
|---|---|---|
| Rust | `astra-plugin-sdk = "0.6"` | crates.io 0.6.0 |
| Python | `astra-plugin-sdk>=0.5,<0.6` | PyPI 0.5.0 |
| TypeScript | `"astra-plugin-sdk": "^0.5.0"` | npm 0.5.0 |

Eso se resuelve desde los registros, así que `cargo build`, `pip install -r
requirements.txt` y `bun install` funcionan en un proyecto nuevo sin nada
que configurar.

**Los límites inferiores son estructurales.** Rust 0.6 es el primer release
cuyo `HostClient` adjunta `x-session-token`, y Python y TypeScript 0.5.0 son
los suyos; contra cualquier versión más antigua el daemon responde
`unauthenticated` en cada llamada al host. Relajar un límite cambia un error
del resolver por uno en tiempo de ejecución, que es el peor intercambio: el
plugin arranca, sirve hooks, y en silencio no puede responder.

Python: `astra-plugin test` ejecuta tu plugin con el `python` que haya en
`PATH`, así que activa primero el entorno virtual en el que instalaste todo.
Si no, el plugin termina con `ModuleNotFoundError: astra_plugin_sdk` antes
de registrarse.

## 3 · Escribir el plugin

Reemplaza `src/main.rs` con esto. Es el plugin completo — argumentos
tipados, un tool, un trigger, y tres pruebas.

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

/// The arguments the model sends. The doc comments become the JSON Schema it
/// reads, so write them for a reader who has never seen this plugin.
#[astra::args]
struct Roll {
    /// How many dice to roll
    #[serde(default = "one")]
    count: u32,
    /// How many sides each die has
    #[serde(default = "six")]
    sides: u32,
}

fn one() -> u32 { 1 }
fn six() -> u32 { 6 }

#[derive(Default)]
struct DiceRoller;

#[astra::plugin]
impl DiceRoller {
    /// Roll dice and return the total. Use it whenever the user asks for a
    /// random number, a dice roll, or a coin flip.
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
        if a.sides < 2 {
            return Err(ToolError::BadArguments("a die needs at least 2 sides".into()));
        }
        let total: u32 = (0..a.count).map(|_| 1 + rand_below(a.sides)).sum();
        ctx.host()
            .fire_trigger("dice_rolled", &json!({ "total": total }).to_string())
            .await?;
        Ok(total.to_string())
    }
}

/// Not a dependency: `SystemTime` is enough entropy for a dice roll.
fn rand_below(n: u32) -> u32 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos();
    nanos % n
}

astra::main!(DiceRoller::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn it_rolls_and_fires_the_trigger() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();

        let total: u32 = h
            .call_tool("roll_dice", json!({ "count": 3, "sides": 6 }))
            .await
            .expect("the tool answered")
            .parse()
            .unwrap();
        assert!((3..=18).contains(&total), "three d6 cannot total {total}");

        assert_eq!(h.fired_triggers().len(), 1);
        assert_eq!(h.fired_triggers()[0].trigger_type, "dice_rolled");
    }

    #[tokio::test]
    async fn a_one_sided_die_is_rejected() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        let err = h
            .call_tool("roll_dice", json!({ "sides": 1 }))
            .await
            .expect_err("a die needs two sides");
        assert!(err.to_string().contains("2 sides"), "{err}");
    }

    /// What the user sees if they never granted `fire_trigger`.
    #[tokio::test]
    async fn a_denied_permission_surfaces_as_an_error() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        h.host().deny("fire_trigger");
        let err = h.call_tool("roll_dice", json!({})).await.expect_err("denied");
        assert!(err.to_string().contains("fire_trigger"), "{err}");
    }
}
```

Cinco cosas merecen mención:

- **`#[astra::args]`, no `#[derive(Deserialize, JsonSchema)]`.** El derive de
  serde emite `extern crate serde`, que se resuelve a través del extern
  prelude y no se puede alcanzar mediante un re-export — así que el derive
  simple necesitaría `serde` en *tu* `Cargo.toml`, precisamente lo único
  que el scaffold promete que no necesitas. `#[astra::args]` son esos dos
  derives apuntando a las copias del SDK.
- **El comentario de documentación es la descripción que lee el modelo.**
  Tanto en el tool como en cada campo. Di cuándo usar el tool, no cómo
  funciona.
- **Los handlers devuelven `Result<_, ToolError>`.** Un fallo por llamada es
  *datos*: el bucle de IA lo lee y decide qué hacer, así que viaja en la
  respuesta en lugar de como un estado gRPC. `?` funciona con
  `serde_json::Error`, `std::io::Error`, `tonic::Status` y `anyhow::Error`.
- **`ctx.host()` siempre está ahí.** El contexto lleva el cliente del host,
  el idioma de la UI y el conjunto de triggers activos; es barato de clonar
  en una tarea en segundo plano y nunca es `None`. Nada va en tu struct
  detrás de un lock.
- **`h.host().deny("fire_trigger")` simula un rechazo.** Así es como se ve un
  usuario que no dio su consentimiento, y vale la pena una prueba — es el
  fallo que, si no, recibirá tu rastreador de issues.

`cargo test` ejecuta esas tres contra un host que graba: sin daemon, sin
socket, sin Astra instalado.

<!-- doctest: illustrative reason="the block above carries test=1, so the doc-test already ran cargo test on it" -->
```bash
cargo test
```

## 4 · Declarar lo que necesitas

El tool llama a `fire_trigger`, y `[permissions]` es de denegación por
defecto, así que tiene que pedirlo. El `reason` es lo que lee el usuario
cuando Astra le pide consentimiento — escríbelo como una frase sobre *tu
plugin*, no sobre el permiso.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat, and fire a trigger with the result."
author = "Your Name"
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

Luego compruébalo:

<!-- doctest: cli -->
```bash
astra-plugin check --strict
astra-plugin check --fix
```

`check` lee el manifiesto con el propio parser del daemon — el mismo crate,
vendorizado y mantenido idéntico byte a byte — así que no puede discrepar de
lo que ocurrirá en el momento de la instalación. `--fix` aplica las
correcciones que puede demostrar y reporta el resto.

## 5 · Ejecutar la suite de conformidad

<!-- doctest: cli -->
```bash
astra-plugin test
```

Esto es un nivel por encima de `cargo test`: arranca tu plugin tal como lo
arranca el daemon, contra un daemon simulado que sirve `PluginHostService`,
y llama a cada hook entrante que impliquen tus capabilities declaradas.

<!-- doctest: output from="astra-plugin test . --no-build, in the dice-roller project this page builds (the plugin's own tracing lines, which go to stderr, are left out)" -->
```
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] GetPluginTriggerTypes    required  0 trigger type(s)
  [ok  ] CallTool                 required  `roll_dice` answered
  [ok  ] OnActiveTriggers         optional  accepted 0 active trigger(s)
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 40.8ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 775.4µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] Shutdown is honoured within the grace period: the process exited 40.8ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 2 host call(s) reached the daemon: fire_trigger, log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 8 hook(s) exercised, 6 check(s) passed.
```

`GetPluginTriggerTypes` reporta **0** aunque el plugin dispara un trigger.
Disparar uno y *ofrecerlo* son cosas distintas: el editor de comandos lista
lo que el plugin declara, que es un `#[hook] async fn trigger_types(&self)
-> Vec<TriggerTypeDef>`, y el plugin de arriba no tiene ninguno. Generar el
scaffold con `--capabilities tools,triggers` escribe ese hook por ti; el §3
lo omitió para mantener el archivo en una sola pantalla. Disparas sin
declarar y el trigger igual se dispara — pero nadie puede conectarle un
comando.

Un hook `required` no puede responder `UNIMPLEMENTED`; uno `optional` sí
puede, porque en el cable `UNIMPLEMENTED` *significa* "este hook no existe".

## 6 · Ejecutarlo dentro de Astra

Este paso necesita un Astra en ejecución y el **modo desarrollador**, porque
hace sideload de un directorio sin firmar:

<!-- doctest: cli -->
```bash
astra-plugin dev
```

Ejecuta `check --strict`, compila, entrega el directorio al daemon — que
lanza el proceso, acuña su token y posee su ciclo de vida — y luego observa
cambios, recompila, reinicia y sigue los logs.

Lee [sideload](../5-publish/sideload.md) antes de activar el modo
desarrollador. Es una herramienta de desarrollo: ejecuta código local sin
firmar con todos tus privilegios de usuario, y el interruptor baja el
listón para cada plugin de la máquina, no solo este. No es la forma en que
nadie instala un plugin.

Si `dev` no puede alcanzar Astra, `astra-plugin doctor` te dice cuál de las
dos cosas está mal — el daemon no está corriendo, o resolvió un directorio
de config distinto al de la CLI.

## 7 · Empaquetar

<!-- doctest: cli -->
```bash
astra-plugin build
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin build ., in the dice-roller project this page builds (the size and the two digests are properties of your build, not constants)" -->
```
Building plugin 'dice-roller' v0.1.0 (rust) for linux-x64...
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 0.04s
  Added: README.md (0644)
  Added: bin/dice_roller (0755)
  Added: plugin.toml (0644)
  Built: dice-roller-0.1.0-linux-x64.astraplugin (2757.1 KB, 3 files)
  target:          linux-x64
  artifact sha256: 3ae95e05f49156b137afe4b528dc1feb4df4c36c5e8c284b52b7b15e4f3345fa
  manifest digest: 11b1b78dd55232877c881e862e109ec594aa535167d27063a2e3fcbe373d9824
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
  See https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/publishing.md#what-establishes-trust
```

`verify` vuelve a leer lo que `build` acaba de escribir y responde a otra
pregunta: que `MANIFEST.json` es la entrada 0 y está almacenado, que la
lista de archivos es exhaustiva en ambas direcciones, y que cada digest,
tamaño y modo listado coincide con el archivo. No dice nada sobre quién lo
escribió — ese es trabajo del registro.

El nombre del archivo no es cosmético: `<id>-<version>-<target>.astraplugin`
es el nombre que debe tener un paquete publicado, y el segmento target es la
clave de plataforma del registro.

**`build` no firma, y no necesitas ninguna clave.** Lo que hace que Astra
instale un plugin es un registro del registry contrafirmando el sha256 del
archivo completo — no ninguna clave que tú tengas. Consulta
[el modelo de seguridad](../1-orientation/security.md).

## 8 · Publicar

Ahora la parte que importa, y son dos comandos:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
astra-plugin version 0.1.1
```

`init-ci` escribe `.github/workflows/release.yml`, fijado (pinned) por SHA
de commit al workflow de release reutilizable de Astra. Después de eso,
**una etiqueta (tag) es todo el proceso de release**: la CI compila cada
target, certifica cada paquete con la procedencia de compilación de GitHub,
y los adjunta a un GitHub Release.

Luego una sola solicitud, una vez para siempre, y cada release posterior no
requiere intervención.

Nota lo que publicar **no es**: subir este repositorio a GitHub no publica
tu plugin, ni tampoco enviarle a alguien el `.astraplugin` que acabas de
compilar. El registro fija el digest de un archivo que produjo la CI y lee
la attestation de compilación adjunta a él, y un archivo compilado en tu
portátil no tiene ninguna de las dos cosas.

**→ [Publicar un plugin](../publishing.md)** — todo el recorrido en una sola
página, desde aquí hasta un plugin listado, con cada comando y su salida
esperada. Las páginas de cada etapa detrás de ella:
[Publicar release con CI](../5-publish/release-with-ci.md) ·
[Conseguir el listado](../5-publish/get-listed.md)

## Lo mismo en Python

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang python --template tool
```

<!-- doctest: python-plugin -->
```python
"""DiceRoller — an Astra plugin."""

from astra_plugin_sdk import Plugin, tool


class DiceRoller(Plugin):
    """Roll dice from chat."""

    @tool("Roll dice and return the total.")
    async def roll_dice(self, count: int = 1, sides: int = 6) -> str:
        # The parameters ARE the schema: a parameter with no default is
        # required, one with a default is optional, and the type hints become
        # the JSON types the model is shown.
        if sides < 2:
            raise ValueError("a die needs at least 2 sides")
        total = sum(1 + (i % sides) for i in range(count))
        await self.host.fire_trigger("dice_rolled", f'{{"total": {total}}}')
        return str(total)


if __name__ == "__main__":
    DiceRoller().run()
```

El punto de entrada es `[entry] command = "python"`,
`args = ["-m", "src.plugin"]`, `runtimes = ["python"]`, y el paquete es
`noarch`.

## Lo mismo en TypeScript

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang typescript --template tool
```

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    roll_dice: tool({
      description: "Roll dice and return the total.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs.
      input: s.object({
        count: s.number({ description: "How many dice to roll" }).optional(),
        sides: s.number({ description: "How many sides each die has" }).optional(),
      }),
      run: ({ count, sides }) => {
        const n = count ?? 1;
        const faces = sides ?? 6;
        if (faces < 2) throw new Error("a die needs at least 2 sides");
        let total = 0;
        for (let i = 0; i < n; i++) total += 1 + Math.floor(Math.random() * faces);
        return String(total);
      },
    }),
  },
});

// `astra-plugin build` bundles this to CommonJS, so `require.main` is the
// honest "am I the entrypoint" test. Importing this module — as a test does —
// does not start a server.
if (require.main === module) app.run();
```

## A dónde ir después

| Si quieres | Lee |
|---|---|
| La API completa de Rust | [SDK de Rust](../4-sdk/rust.md) |
| Cada clave de `plugin.toml` | [referencia del manifiesto](../reference/manifest.md) |
| Cada hook, en cada SDK | [paridad](../reference/parity.md) |
| Publicarlo | [Publicar release con CI](../5-publish/release-with-ci.md) |
| Algo está roto | [Solución de problemas](../6-operate/troubleshooting.md) |
| Un ejemplo desarrollado | [Ejemplos](../7-examples/README.md) — once de ellos |
</content>
