> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/migration-0.6.md) es la referencia autorizada.

# Migrar un plugin a los SDK 0.6

Para alguien con un plugin funcional de la era 0.5. Está en el orden en
que te encontrarás los problemas: **lo que falla en tiempo de ejecución
antes de que cambies una línea**, luego lo que falla en tiempo de
compilación, luego lo que compila y se comporta distinto, luego lo que
solo avisa.

El tren de release es `sdk-v0.6.0`: el crate de Rust pasa a 0.6.0, los
paquetes de Python y TypeScript a 0.5.0. Consulta
[versioning.md](versioning.md) para saber por qué difieren los números.

Cada fragmento de abajo es código real de este repositorio — los nueve
ejemplos de Rust se portaron a 0.6 en el commit `134f6d1`, así que ambos
lados de cada diff existen en git y están citados de ahí.

---

## 0. Por qué no puedes quedarte donde estás

Este no es un release de "API nueva y bonita". **Un plugin 0.5 ya está
roto contra el daemon actual**, antes de que cambies nada:

> El `HostClient` de 0.5 no envía `x-session-token`, y el daemon
> responde `unauthenticated` a cada RPC del host salvo `Register`.

Así que `fire_trigger`, `set_variable`, `log`, `push_to_ui` y el resto
fallan en tiempo de ejecución, en una máquina que no es la tuya, con un
mensaje que tu usuario leerá como "el plugin está roto". El registro
sigue teniendo éxito, lo cual es lo que genera la confusión: el plugin
parece arrancar y luego no hace nada.

Esa es toda la razón por la que existe 0.6, y la razón por la que se
permitió que la API de autoría cambiara en el mismo release.

---

## 1. La vía rápida (Rust): una línea, y compila

Si necesitas el plugin funcionando hoy y la migración la semana que
viene, cambia tu import:

<!-- doctest: illustrative reason="a one-line diff of the import, not a compilable file" -->
```diff
-use astra_plugin_sdk::prelude::*;
+use astra_plugin_sdk::compat::*;
```

Ese es el diff completo. `compat` es el trait 0.5, los tipos de
resultado 0.5 y las formas 0.5 de `HostClient`/`DaemonClient`,
reenviadas al trait 0.6 mediante una implementación general (blanket
impl). Verificado en el dice-roller 0.5 real — 255 líneas, sin
modificar salvo esa línea:

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
warning: use of deprecated trait `astra_plugin_sdk::compat::PluginCapability`: implement
`astra_plugin_sdk::PluginCapability` (0.6): handlers take a `&PluginContext`, return
`Result<_, ToolError>`, and declare `type Config`. See docs/en/migration-0.6.md. This
trait is removed in 0.8
  --> src/main.rs:92:6
   |
92 | impl PluginCapability for DiceRoller {
   |      ^^^^^^^^^^^^^^^^

warning: `dice_roller` (bin "dice_roller") generated 12 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 16.38s
```

(Una advertencia por cada elemento obsoleto que toques — once aquí, más
un `unused_mut` que ya no necesita el antiguo
`let mut h = host.lock().await`.)

Compila, sus tools responden, y el host que guardaba en `set_host`
sigue alcanzando al daemon. La propia suite de pruebas del SDK lo fija:
siete pruebas escritas *contra el trait 0.5*, ejecutadas a través del
harness 0.6, en `astra-plugin-sdk/src/capability.rs`
(`mod compat::tests`).

Tres cosas que saber antes de depender de esto:

- **`compat::*` reemplaza a `prelude::*`; no es una adición.** Importa
  ambos y tendrás dos traits llamados `PluginCapability` en el ámbito, y
  `impl PluginCapability for MyPlugin` se vuelve ambiguo (E0659) en
  lugar de obsoleto.
- **Desaparece en 0.8** — dos versiones menores, según
  [versioning.md](versioning.md).
- **Los hooks que 0.5 nunca tuvo siguen ausentes.** `ai_complete`,
  `tts_activate`, `stt_load` / `stt_unload` / `stt_load_state` responden
  `UNIMPLEMENTED` a través del shim, que el protocolo lee como *hook
  ausente*. Para implementarlos hay que migrar el trait.

`compat::*` también reexporta los nombres 0.6 — `PluginContext`,
`ToolError`, `Host`, `Daemon`, `Config`, `NoConfig` — así que puedes
mover hooks a las nuevas firmas uno a uno sin que la línea de import
vuelva a cambiar. Cuando el último esté migrado, cambia `compat::*` de
vuelta a `prelude::*` y las advertencias desaparecen.

El resto de este documento es esa migración.

---

## 2. Qué falla en tiempo de compilación (Rust)

Estos son los errores reales al compilar el dice-roller 0.5 sin
modificar contra 0.6 — 15 de ellos, en cinco tipos.

### 2.1 `Config` es un tipo asociado obligatorio

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0046]: not all trait items implemented, missing: `Config`
  --> src/main.rs:92:1
   |
92 | impl PluginCapability for DiceRoller {
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ missing `Config` in implementation
   |
   = help: implement the missing item: `type Config = /* Type */;`
```

Si tu plugin no tiene ajustes, es una línea:

<!-- doctest: illustrative reason="the single line that satisfies the associated type; the whole impl it belongs to is the block above" -->
```rust
type Config = NoConfig;
```

Si los tiene, declara el tipo e implementa `on_config` — el SDK analiza
el JSON del daemon por ti. bad-apple, antes
(`examples/bad-apple/src/main.rs` en `134f6d1^`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn on_config_changed(&self, config_json: &str) {
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(config_json) {
        let mut cfg = self.config.lock().unwrap();
        if let Some(s) = v.get("render_mode").and_then(|s| s.as_str()) {
            cfg.render_mode = s.to_string();
        }
        if let Some(n) = v.get("opacity").and_then(|n| n.as_f64()) {
            cfg.opacity = n;
        }
        // …three more arms, each silently skipping a field of the wrong type
    }
}
```

y después (`examples/bad-apple/src/main.rs`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
#[derive(Serialize, Deserialize)]
#[serde(default)]
struct BadAppleConfig {
    render_mode: String,
    opacity: f64,
    charset: String,
    color: String,
    #[serde(rename = "loop")]
    do_loop: bool,
}

#[async_trait]
impl PluginCapability for BadApple {
    type Config = BadAppleConfig;

    async fn on_config(&self, _ctx: &PluginContext, config: BadAppleConfig) {
        self.config.store(config);
    }
}
```

Veinte líneas a dos, y un campo del tipo incorrecto ahora se reporta en
lugar de saltarse.

> **Usa `#[serde(default)]` (o `#[astra::config]`, que lo añade).** La
> primera carga de config que el daemon envía a un plugin recién
> instalado es `{}`. Un tipo de config con un campo obligatorio la
> rechaza, `on_config` nunca se llama ni una sola vez, y tu plugin sirve
> cada llamada sobre `Config::default()` — una clave de API vacía, un
> nombre de trigger que es el string vacío. El SDK avisa con fuerza
> exactamente de este caso, pero el panel de logs no es donde estás
> mirando.

`Config<T>` es el almacén sin locks donde guardarlo: `self.config.load()`
es una lectura atómica, y una reescritura de config a mitad de una
llamada de tool no puede bloquearla.

### 2.2 Los handlers toman un `&PluginContext`

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0050]: method `call_tool` has 3 parameters but the declaration in trait
              `astra_plugin_sdk::PluginCapability::call_tool` has 4
   --> src/main.rs:117:24
    |
117 |     async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult {
    |                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ expected 4 parameters, found 3
```

Añade `ctx: &PluginContext` (o `_ctx`) después de `&self`. Lleva
`plugin_id`, `language`, `active_triggers`, `host` y `daemon`; es barato
de clonar; nunca es `None`. mock-stt, antes y después:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5 — examples/mock-stt/src/main.rs at 134f6d1^
async fn stt_transcribe(&self, audio: &[u8], sample_rate: u32) -> anyhow::Result<SttEvent> {
```

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.6 — examples/mock-stt/src/main.rs
async fn stt_transcribe(
    &self,
    _ctx: &PluginContext,
    audio: &[u8],
    sample_rate: u32,
    options: &SttOptions,
) -> anyhow::Result<SttEvent> {
```

TTS colapsó al mismo tiempo sus cuatro argumentos en un único
`TtsRequest` — tone-tts pasó de
`(&self, text, voice_id, speed, _pitch)` a
`(&self, _ctx, req: TtsRequest)`, leyendo `req.text`, `req.voice_id`,
`req.speed`.

Desde un lugar que un parámetro no puede alcanzar — una tarea lanzada,
un `Drop`, un callback del crate de otra persona —
`astra_plugin_sdk::ctx()` devuelve el mismo contexto.

### 2.3 `set_host` y `set_daemon_client` desaparecieron

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0407]: method `set_host` is not a member of trait `PluginCapability`
  --> src/main.rs:95:5
   |
95 | /     async fn set_host(&self, host: Arc<Mutex<HostClient>>) {
96 | |         *self.host.lock().await = Some(host);
97 | |         info!("Host client received");
98 | |     }
   | |_____^ not a member of trait `PluginCapability`
```

Borra el hook, borra el campo, usa `ctx.host()`. Vale la pena hacerlo
bien en lugar de a través del shim, porque la forma 0.5 tenía un defecto.
dice-roller, antes (`examples/dice-roller/src/main.rs` en `134f6d1^`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
struct DiceRoller {
    default_sides: AtomicU32,
    total_rolls: AtomicU64,
    host: Mutex<Option<Arc<Mutex<HostClient>>>>,
}

fn fire_roll_triggers_bg(&self, results: Vec<u32>, sides: u32) {
    let host = self.host.try_lock().ok().and_then(|g| g.clone());
    let host = match host {
        Some(h) => h,
        None => {
            info!("Cannot fire triggers: host client not available yet");
            return;
        }
    };
    // …
}
```

Cuando una segunda llamada a un tool retenía ese lock, `try_lock`
devolvía `None`, el plugin registraba "host client not available yet", y
**no disparaba nada**. Después:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
fn fire_roll_values(&self, ctx: &PluginContext, results: &[u32], sides: u32) {
    let host = ctx.host().clone();
    let results = results.to_vec();
    tokio::spawn(async move {
        for v in results {
            let payload = json!({ "value": v.to_string(), "roll": format!("1d{sides}"), "sum": v.to_string() });
            if let Err(e) = host.fire_trigger("on_roll_value", &payload.to_string()).await {
                let _ = host.log_warn(&format!("failed to fire on_roll_value: {e}")).await;
            }
        }
    });
}
```

`Arc<dyn Host>` no tiene ningún lock que perder. Lo mismo se aplica a
los plugins cliente: `ctx.daemon()` es `Some` durante toda la vida de un
plugin con la capability `client`, así que cada rama de "daemon client
not ready" desaparece. telegram-client perdió su campo `SharedDaemon` y
esta comprobación:

> `Some` se refiere al handle, no a lo que puede alcanzar. El daemon
> limita el token de sesión de cada plugin a `PluginHostService`, así
> que las llamadas hechas a través de `ctx.daemon()` responden
> actualmente `permission_denied` — consulta
> [la página del SDK de Rust](4-sdk/rust.md#daemon-presente-en-el-sdk-rechazado-por-el-daemon).
> Esta sección trata sobre la forma de la migración, no sobre una vía
> que funcione de extremo a extremo hoy.

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5
if self.daemon.lock().await.is_none() {
    info!("Daemon client not ready, not starting");
    return;
}
```

### 2.4 `ToolResult` / `ActionResult` / `UiCallResult` se eliminaron

<!-- doctest: output from="cargo build of a 0.5 plugin against the 0.6 SDK" -->
```
error[E0433]: cannot find type `ToolResult` in this scope
```

Los handlers devuelven `Result<String, ToolError>` (`ActionError` es un
alias de `ToolError`). La correspondencia es mecánica:

| 0.5 | 0.6 |
| --- | --- |
| `ToolResult::ok(text)` | `Ok(text)` |
| `ToolResult::err("unknown tool")` | `Err(ToolError::NotFound(…))` |
| `ToolResult::err("bad JSON")` | `Err(ToolError::BadArguments(…))`, o simplemente `?` en el parseo |
| `ToolResult::err("no API key")` | `Err(ToolError::not_configured("api_key"))` |
| `UiCallResult::ok(json)` / `::err(msg)` | `Ok(json)` / `Err(ToolError::…)` |

El tipo no es decoración. Es lo que le dice al bucle de IA si reintentar
puede servir de algo, y `NotConfigured { field }` es lo que convierte
"el tool falló" en un enlace a esa entrada exacta de ajustes.
bad-apple, después:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn handle_ui_call(
    &self,
    _ctx: &PluginContext,
    method: &str,
    _params_json: &str,
) -> Result<String, ToolError> {
    match method {
        "getConfig" => Ok(serde_json::to_string(&*self.config.get())?),
        _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
    }
}
```

Nota el `?` en `serde_json::to_string`: existen implementaciones de
`From` para `serde_json::Error`, `std::io::Error`, `tonic::Status` y
`anyhow::Error`, y cada conversión es una afirmación sobre de qué tipo
es el fallo — `serde_json::from_str(args)?` dentro de `call_tool`
significa `BAD_ARGUMENTS`, el único fallo que el modelo puede arreglar
intentándolo de nuevo.

Si pasas por el shim en su lugar, cada fallo 0.5 se convierte en
`ToolError::Internal` con la misma frase. Esa es la lectura honesta de
un string cuyo autor nunca dijo qué era, y es peor que lo que tú mismo
puedes decir en cinco minutos.

### 2.5 Rupturas menores en tiempo de compilación

| Qué | 0.5 | 0.6 |
| --- | --- | --- |
| `discover_capabilities` | un hook | **eliminado.** El daemon indica el `[capabilities]` del manifiesto en `ASTRA_PLUGIN_CAPABILITIES` |
| `ActiveTriggers::contains` / `update` | `async`, `tokio::RwLock` | síncrono (`ArcSwap`), y `update` ahora se llama `set` |
| `HostClient::new(..)` | construible | solo `connect_bootstrap` → `register` → cliente autenticado |
| `use astra_plugin_sdk::prelude::{Deserialize, Serialize}` | funcionaba | marcadores de posición que fallan con una frase: usa `#[astra::args]`, o añade `serde` a tu propio `Cargo.toml` |
| `on_shutdown()`, `on_event()`, `on_state_changed()` y los demás hooks de evento | sin `ctx` | `ctx` primero, igual que todo lo demás |

---

## 3. Qué falla en tiempo de ejecución (compila, y se comporta distinto)

### 3.1 `[permissions]` es de denegación por defecto

El que muerde primero en la máquina de un usuario, y no es en absoluto
un cambio de SDK — es la Fase 4. Un manifiesto sin sección
`[permissions]` puede llamar a `Register`, `PluginLog` y
`GetPluginSelfConfig`, y **nada más**. `fire_trigger`, `set_variable`,
`push_to_ui`, `send_chat_message`, `subscribe_events` y
`set_theme_contribution` necesitan cada uno un permiso declarado y
concedido, y una denegación llega como `PERMISSION_DENIED` →
`ToolError::Unauthorized`.

Declarar la capability no basta. De
`examples/dice-roller/plugin.toml`:

<!-- doctest: illustrative reason="an excerpt of the [permissions] block from examples/dice-roller/plugin.toml, not a whole manifest" -->
```toml
# `[permissions]` is the other direction: which host RPCs the plugin may call
# out to. Default-deny — a manifest with no `[permissions]` section may call
# nothing beyond Register, PluginLog and GetPluginSelfConfig, so declaring
# `triggers = true` is not what lets `fire_trigger` through. This is.
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

El `reason` se muestra al usuario en el momento de instalar.
Escríbeselo a él.

### 3.2 Orden de arranque, y `on_start`

0.6 arregla el orden: bind → register → build ctx → `on_config` →
`on_language_changed` → `on_start` → serve. `on_start` es nuevo, y
devolver `Err` **aborta el arranque**: el proceso sale con código
distinto de cero en lugar de dejar un plugin que el daemon cree sano y
que falla cada llamada de la misma forma.

Aquí es donde pertenecen el calentamiento y las tareas en segundo
plano. echo-stt movió su hilo de audio ahí, fuera de `main`;
telegram-client movió todo el arranque de su bot fuera de
`set_daemon_client`, lo cual eliminó una carrera contra
`on_config_changed`:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
/// Config has already been applied by the time this runs, so the bot token
/// is there and the bot starts once, in one place, instead of racing
/// `set_daemon_client` against `on_config_changed`.
async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
    let daemon = ctx
        .daemon()
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("telegram-client needs the `client` capability"))?;
```

### 3.3 Comportamiento que cambió en silencio

- **`ActiveTriggers` tiene un escritor.** En 0.5 nada lo escribía nunca,
  así que `contains()` siempre respondía false. Si protegías una carga
  útil costosa detrás de eso, esa protección siempre estaba cerrada y
  ahora está abierta — la carga útil se construirá.
- **El canal de audio de STT tiene capacidad para 500 chunks, no 32.**
  Un reconocedor en streaming que en silencio descartaba audio bajo
  carga ya no lo hace. Si compensabas esos descartes, deja de hacerlo.
- **`source_id()` no afecta a nada.** El daemon dejó de filtrar por
  source id; cada cliente ve cada evento. Obsoleto en 0.6, desaparece en
  0.8. Pasa el id a `Host::send_chat_message` en su lugar.
- **Las capabilities vienen del daemon**, en
  `ASTRA_PLUGIN_CAPABILITIES`, no de examinar cuáles de tus métodos
  devuelven un vector no vacío. Un plugin cuyas capabilities anunciadas
  solían discrepar de su manifiesto ahora anuncia el manifiesto, que es
  a lo que consintió el usuario.

---

## 4. Lo que solo avisa

| Advertencia | Plazo | Hacer en su lugar |
| --- | --- | --- |
| `use of deprecated trait compat::PluginCapability` | 0.8 | el trait 0.6 — §2 |
| `use of deprecated struct compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.8 | `Result<String, ToolError>` — §2.4 |
| `use of deprecated type alias compat::HostClient` / `DaemonClient` | 0.8 | `ctx.host()` / `ctx.daemon()` — §2.3 |
| `use of deprecated method source_id` | 0.8 | eliminar el override |
| Python `DeprecationWarning: … returned a dict` | 0.7 | devolver la dataclass |
| `AiGetModels` / `ai_models()` | 0.8 | nada — el daemon nunca lo pregunta |

Nada de esa tabla es todavía un error, y nada de ella se convertirá en
uno dentro de una sola versión menor: consulta
[versioning.md](versioning.md) para la garantía y cómo se hace cumplir.

---

## 5. Python

El paquete pasa de 0.4.0 → 0.5.0. La clase sigue siendo `Plugin` y los
decoradores siguen siendo `@tool` / `@action` / `@trigger`, así que la
mayoría de los archivos cambian muy poco.

**Los fallos ahora tienen código.** `call_tool` y `execute_action` antes
capturaban cualquier `Exception` y la aplanaban a
`{"success": False, "error": str(e)}` — por lo que cada fallo se veía
idéntico. Lanza en su lugar uno de los ocho errores, y el SDK rellena
tanto el string heredado como el `error_detail` estructurado:

De `examples/text-utils/src/plugin.py`:

<!-- doctest: illustrative reason="one decorated method from examples/text-utils/src/plugin.py, not a whole module" -->
```python
@tool("Convert text case: upper, lower, title, snake, camel.")
async def case_convert(self, text: str, mode: str):
    self._check_length(text)
    if mode not in CASE_MODES:
        # BAD_ARGUMENTS, not INTERNAL: the model is the caller here, and this
        # code is what tells it to try again with a different `mode` rather
        # than to give up and apologise to the user.
        raise BadArguments(f"unknown mode {mode!r}; use one of {', '.join(CASE_MODES)}")
    self.operations_count += 1
    return self._convert_case(text, mode)
```

`raise NotConfigured("api_key")` es el que se convierte en un enlace a
ese campo exacto de ajustes.

Qué más comprobar:

- **`stt_transcribe` toma un tercer parámetro**,
  `options: SttOptions | None`. Un override con dos argumentos sigue
  funcionando — el servicer inspecciona tu firma una vez y solo pasa lo
  que acepta — así que esto es opcional, y añadir `options=None` es
  cómo obtienes la pista de idioma y el sesgo de wake-word del daemon.
- **Devuelve dataclasses, no dicts**, desde los hooks de capability.
  Los dicts siguen funcionando y emiten un `DeprecationWarning` que
  nombra la clase a devolver; desaparecen en 0.7.
- **`HostClient` no se puede construir sin autenticar.**
  `HostClientBootstrap(addr, plugin_id).register(...)` devuelve el
  real.
- **`@ui_call` / `@ui_page` se registran.** Antes eran
  `@staticmethod`s que devolvían un dict que el llamador descartaba.
- Bloquea la CI con las advertencias:
  `python -W error::DeprecationWarning -m pytest`.

## 6. TypeScript

El paquete pasa de 0.4.0 → 0.5.0, y el nombre publicado es
`astra-plugin-sdk` — no `@astra/plugin-sdk`, como decían cuatro sitios
antes.

- **Los fallos tienen código**, los mismos ocho que en todas partes, y
  `code` es un literal de string por clase, así que
  `switch (err.code) { case "NOT_CONFIGURED": … }` estrecha a la
  subclase y alcanza `err.configField` sin necesidad de cast.
- **El constructor de `HostClient` es privado**; `HostClient.register(...)`
  es la única forma de obtener uno, y lanza `RegistrationError` si el
  daemon rechaza.
- **Los clientes cargan el propio descriptor generado del SDK** en
  lugar de dos strings de proto en línea mantenidos a mano, y
  comprueban cada método que van a llamar en el momento de conectar —
  un desajuste es un `ProtoContractError` al arrancar en lugar de un
  `TypeError` en la primera llamada.
- **`UiPanel` está obsoleto**; es un alias de `UiContribution`.
- Si tu `package.json` es anterior a 0.5.0, ten en cuenta el nuevo mapa
  `exports`, `"type": "commonjs"`, `engines: { node: ">=20" }` y la
  salida dual CJS+ESM.

---

## 7. Verificar la migración

No necesitas tener Astra instalado para saber si la migración funcionó.
Los SDK 0.6 incluyen un harness de pruebas que ejecuta tus handlers en
proceso contra un host que graba:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
use astra_plugin_sdk::testing::Harness;

#[tokio::test]
async fn the_0_5_dice_roller_still_rolls_and_still_fires() {
    let h = Harness::new(DiceRoller::new())
        .with_config_json(r#"{"default_sides":20}"#)
        .start()
        .await
        .unwrap();

    let out = h
        .call_tool("roll_dice", serde_json::json!({"count": 3, "sides": 6}))
        .await
        .unwrap();
    assert!(out.starts_with("Rolled 3d6:"), "{out}");

    // The triggers the 0.5 `try_lock` used to drop when it lost the race.
    assert_eq!(h.wait_for_triggers("on_roll_value", 3).await.len(), 3);
}
```

Así es como se aceptó el shim: el `DiceRoller` de ahí es el dice-roller
**0.5**, sin modificar salvo su línea de import, ejecutándose sobre
0.6. Sin daemon, sin socket, sin Astra instalado — `Harness` construye
un `PluginContext` alrededor de un host que graba, así que
`fired_triggers()` es una lista sobre la que puedes hacer aserciones.

Una lista de comprobación breve:

1. Compila sin ningún import de `compat::`.
2. Tu `plugin.toml` tiene una sección `[permissions]` para cada RPC del
   host que llamas, cada una con un `reason` escrito para el usuario.
3. `on_config` ve `{}` sin caerse — eso es una instalación nueva.
4. Todo lo que hacías antes en `set_host` / `set_daemon_client` ocurre
   en `on_start`, y `on_start` devuelve `Err` cuando el plugin
   genuinamente no puede funcionar.
5. Cada `ToolResult::err` se ha convertido en la variante de
   `ToolError` que dice por qué.
</content>
