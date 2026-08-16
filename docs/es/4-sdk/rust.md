> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/4-sdk/rust.md) es la referencia autorizada.

# El SDK de Rust

`astra-plugin-sdk` 0.6.0. Una dependencia, y todo a lo que se expanden las
macros pasa por ella.

<!-- doctest: illustrative reason="a Cargo.toml fragment; the scaffold this line comes from is built by every rust-plugin block on this page" -->
```toml
[dependencies]
astra-plugin-sdk = "0.6"
```

0.6 es el primer release cuyo `HostClient` adjunta `x-session-token`.
Contra 0.5 y anteriores el daemon responde `unauthenticated` en cada
llamada al host, así que no relajes ese límite.

## La forma de un plugin

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Timer;

#[astra::plugin]
impl Timer {
    /// Start a countdown. Use it when the user asks to be reminded in N minutes.
    #[tool]
    async fn start_timer(&self, ctx: &PluginContext, a: Minutes) -> Result<String, ToolError> {
        if a.minutes == 0 {
            return Err(ToolError::BadArguments("give me at least a minute".into()));
        }
        ctx.host().log_info(&format!("timer for {}m", a.minutes)).await?;
        Ok(format!("timer set for {} minutes", a.minutes))
    }

    /// Runs from the command editor rather than from the model.
    #[action(label = "Cancel all timers")]
    async fn cancel_all(&self, ctx: &PluginContext) -> Result<String, ActionError> {
        ctx.host().log_info("cancelled").await?;
        Ok("cancelled".into())
    }

    /// A trigger a user can attach a command to.
    #[hook]
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![TriggerTypeDef {
            r#type: "timer_elapsed".into(),
            label: "Timer elapsed".into(),
            ..Default::default()
        }]
    }
}

#[astra::args]
struct Minutes {
    /// How many minutes to wait
    minutes: u32,
}

astra::main!(Timer::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn the_manifest_and_the_code_agree() {
        let h = Harness::new(Timer::default()).start().await.unwrap();

        assert_eq!(h.tools().await.len(), 1);
        assert_eq!(h.action_types().await.len(), 1);
        assert_eq!(h.trigger_types().await[0].r#type, "timer_elapsed");

        // The schema is derived from `Minutes`, not hand-written, so it cannot
        // disagree with what the handler parses.
        h.assert_schema_matches::<Minutes>("start_timer").await;
    }
}
```

`#[astra::plugin]` implementa `PluginCapability` a partir de los hooks que
encuentra, y deriva de ellos el conjunto de capabilities declarado — así
que un plugin no puede afirmar una capability que su código no sirve.
`astra-plugin check` compara eso con `plugin.toml`.

## La capa de macros

| | Para qué sirve |
|---|---|
| `#[astra::plugin]` | En el bloque `impl`. Convierte los miembros de abajo en el trait |
| `#[tool]` | Una función que el modelo puede llamar. El comentario de documentación es su descripción |
| `#[action(label = "…")]` | Un paso en el editor de comandos |
| `#[hook]` | Cualquier otro método de `PluginCapability`, por nombre |
| `#[ui_call]` | Un método al que tu contribución de UI puede llamar de vuelta |
| `#[astra::args]` | En la struct de argumentos de un tool |
| `#[astra::config]` | En tu struct de ajustes — `args` más `#[serde(default)]` |
| `astra::main!(Plugin::default())` | El `main` que lo ejecuta |

**Por qué `#[astra::args]` en lugar de `#[derive(Deserialize, JsonSchema)]`:**
el derive de serde se expande a `extern crate serde as _serde`, que se
resuelve en el extern prelude y no se puede alcanzar mediante un re-export.
El derive simple necesitaría por tanto `serde` en tu propio `Cargo.toml` —
justo lo único de lo que trata la promesa de una sola dependencia.
`#[astra::args]` son esos dos derives con `crate = "…"` apuntando a las
copias del SDK. Añadir `serde` tú mismo sigue funcionando; entonces
`use serde::Deserialize;` sombrea el nombre del prelude.

También puedes implementar `PluginCapability` a mano. El trait es público,
cada método tiene un valor por defecto, y las macros producen exactamente
lo que tú escribirías.

## `PluginContext`

Cada handler recibe un `&PluginContext`. Nunca es `None`, es barato de
clonar en una tarea en segundo plano, y significa que nada tiene que vivir
en tu struct detrás de un lock.

| | |
|---|---|
| `ctx.host()` | `&Arc<dyn Host>` — los diez RPC del host. Siempre presente |
| `ctx.daemon()` | `Option<&Arc<dyn Daemon>>` — **`Some` solo para plugins `client`** |
| `ctx.language()` | El idioma de la UI de Astra, actualizado por `OnLanguageChanged` |
| `ctx.active_triggers()` | Cuáles de tus tipos de trigger está escuchando actualmente un comando |
| `ctx.plugin_id()` | Tu id |

Desde un lugar que un parámetro no puede alcanzar — una implementación de
`Drop`, un callback de una biblioteca en C, un `std::thread` lanzado al
arrancar — `astra_plugin_sdk::ctx()` devuelve el contexto del plugin en
ejecución, y `try_ctx()` la versión que puede fallar.

### `Host` — las diez llamadas de salida

| Método | Permiso |
|---|---|
| `log_debug` / `log_info` / `log_warn` / `log_error` / `log` | ninguno |
| `get_config` | ninguno |
| `get_daemon_info` | ninguno |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope)` | `set_variable` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(…)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

`set_variable` toma **tres** argumentos — nombre, valor y scope. La
suscripción a eventos no está en `Host`: declara `subscribed_events()` y el
runner posee el stream (más abajo).

`Host` es un trait, así que una prueba puede sustituir `RecordingHost` y
verificar lo que tu plugin le dijo a Astra.

### `Daemon` — presente en el SDK, rechazado por el daemon

> **`ctx.daemon()` no funciona hoy, para ningún plugin.** La mitad del lado
> del daemon no está en su lugar. Cada plugin — `client = true` o no —
> está registrado como `ClientType::PluginClient`, y el interceptor de
> autenticación del daemon rechaza esa identidad en **cualquier** ruta que
> no empiece por `/astra.PluginHostService/`, con
> `permission_denied("plugin session tokens are scoped to
> PluginHostService")`. `DaemonClient` se conecta con exactamente ese token
> (`astra-plugin-sdk/src/host_client.rs` entrega `client_session_token` a
> `DaemonClient::connect`), así que cada llamada de abajo —
> `submit_user_message`, `subscribe_chat_events`, `speak`,
> `get_settings` — devuelve `permission_denied` en tiempo de ejecución. Un
> canario en `consistency.rs` del daemon mantiene la comprobación de
> alcance en su lugar, así que esto es deliberado y no una regresión: la
> mitad de la autenticación inversa no está construida, no está rota.
>
> **`Host::send_chat_message` es la única forma que funciona de impulsar un
> turno de IA**, y funciona para cualquier plugin al que se le haya
> concedido `send_chat_message`.

La superficie de la API, para cuando llegue el lado del daemon:
`ctx.daemon()` solo es `Some` cuando el plugin declara `client = true` y
`is_client()` devuelve true. Alcanza siete servicios — core, chat, voice,
command, config, media, monitor — con métodos que incluyen
`submit_user_message`, `subscribe_chat_events`, `stop_generation`,
`list_conversations`, `speak`, `start_listening`, `execute_command`,
`get_settings`, `get_system_stats`. Es `submit_user_message`, no
`send_message`.

## Adónde va lo que produce un disparador activado

Un disparador que activas a través de `ctx.host()` mientras atiendes una llamada
de Astra queda atribuido a esa llamada, así que todo lo que provoque aterriza en
la conversación que la persona tiene delante. **No escribes nada para esto**, y
el modismo que ya se distribuye sigue funcionando sin cambios:

<!-- doctest: illustrative reason="a fragment from inside a handler: `ctx` and `payload` are the handler's own bindings, and the rust-plugin blocks on this page are what supply them. The behaviour is executed by tests/causality.rs." -->
```rust
let host = ctx.host().clone();          // the cause rides inside the Arc
tokio::spawn(async move {
    host.fire_trigger("on_roll_value", &payload).await   // still attributed
});
```

Por eso Rust acota el *manejador* en lugar de usar un task-local: un
`tokio::task_local!` no cruza `tokio::spawn`, y el plugin de referencia hace
spawn. Clona `ctx` o `ctx.host()` cuanto quieras: ambos lo llevan.

Un disparador activado desde cualquier otro sitio es un **evento raíz**: el
daemon lo archiva en el hilo de automatización del propio plugin en lugar de
adivinar una conversación. Eso cubre `astra_plugin_sdk::ctx()`, un host que
guardaste en `on_start` y un `std::thread` crudo. Es la respuesta correcta, no
una degradada: la conversación equivocada es peor que ninguna.

`testing::FiredTrigger::caused_by` es `None` para un evento raíz, así que tus
propias pruebas pueden distinguir uno de otro.

## Errores

Los handlers devuelven `Result<_, ToolError>` (`ActionError` es un alias
del mismo tipo). Un fallo por llamada son datos que lee el bucle de IA y
sobre los que actúa, así que viaja en la respuesta en lugar de como un
estado gRPC.

| Variante | Úsala cuando |
|---|---|
| `BadArguments(String)` | El modelo puede arreglarlo llamando de nuevo de otra forma |
| `NotFound(String)` | Id desconocido, 404 |
| `NotConfigured { field, message }` | Falta un ajuste. `field` es un destino de deep-link |
| `Unauthorized(String)` | Credenciales rechazadas, o no se concedió un permiso |
| `RateLimited { retry_after, message }` | Una cuota upstream. `None` significa desconocido, no "inmediatamente" |
| `Unavailable(String)` | Una dependencia está caída; reintentar más tarde sin cambios |
| `Timeout(String)` | Se agotó el tiempo |
| `Internal(String)` | Un bug. Nada sobre lo que el modelo pueda actuar |

`?` funciona con `serde_json::Error`, `std::io::Error`, `tonic::Status` y
`anyhow::Error`. `with_doc_url(…)` envuelve cualquiera de ellos con una
página que documenta *ese* fallo, que la UI renderiza como un enlace.

Taxonomía completa, incluyendo los strings del cable y las formas en
Python/TypeScript: [`reference/errors.md`](../reference/errors.md).

## Eventos

Declara lo que quieres; el runner se suscribe, reconecta y despacha.

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Watcher;

#[astra::plugin]
impl Watcher {
    /// Requires `[permissions] subscribe_events = { types = [...] }` — and the
    /// daemon enforces that allowlist, not this list.
    #[hook]
    fn subscribed_events(&self) -> Vec<String> {
        vec!["command_completed".into(), "state_changed".into()]
    }

    #[hook]
    async fn on_command_completed(
        &self,
        ctx: &PluginContext,
        e: astra_plugin_sdk::events::CommandCompletedEvent,
    ) {
        let _ = ctx
            .host()
            .log_info(&format!("{} finished, success={}", e.command_name, e.success))
            .await;
    }

    /// The catch-all, called for every event as well as the typed handlers.
    #[hook]
    async fn on_event(&self, _ctx: &PluginContext, event_type: &str, _payload_json: &str) {
        let _ = event_type;
    }
}

astra::main!(Watcher::default());
```

Eventos tipados hoy: `StateChangedEvent`, `CommandTriggeredEvent`,
`CommandCompletedEvent`. Los eventos de chat son un stream distinto —
`on_conversation_event`, alimentado por la manguera (firehose) del daemon,
para plugins `client`.

`on_chat_sync` / `ChatSyncEvent` no existen. El evento se retiró y ningún
SDK tiene el método; si estás portando código que lo usaba, usa
`is_client()` más `on_conversation_event`.

## Pruebas

Dos niveles, ambos incluidos con el SDK para que tu `Cargo.toml` se quede
en una línea.

| | Qué impulsa | Qué puede ver |
|---|---|---|
| `testing::Harness` | los hooks, en el proceso, contra un `RecordingHost` | tools, actions, triggers, config, eventos, llamadas de UI, y cada llamada al host que hiciste |
| `testing::WireHarness` | un proceso real, arrancado como lo arranca el daemon | registro, el token de sesión, audio en streaming, las cosas que solo tiene el cable |

`RecordingHost` te da `fired_triggers()`, `logs()`, `variables()`,
`ui_pushes()`, `chat_messages()`, más `deny(rpc)`, `fail(rpc, err)` y
`fail_next(rpc, err)` para simular los fallos con los que se toparán tus
usuarios.

Y un nivel por encima de ambos: `astra-plugin test` arranca tu binario
compilado contra un daemon simulado e impulsa cada hook que impliquen tus
capabilities. Ese no le importa en qué lenguaje se escribió el plugin.

## Lo que este SDK todavía no puede hacer

- **`ctx.daemon()` / `DaemonClient` no es funcional.** El daemon limita el
  token de sesión de cada plugin a `PluginHostService`, así que los siete
  servicios responden `permission_denied` — incluso para plugins con
  `client = true`. Usa `Host::send_chat_message`. Consulta
  [`Daemon`](#daemon--presente-en-el-sdk-rechazado-por-el-daemon) arriba.
- **`TtsSynthesizeStream` está vinculado pero no enrutado.** El SDK lo
  sirve; no existe punto de llamada en el daemon. Impleméntalo si quieres
  — nada lo llamará hasta que
  [la tabla de paridad](../reference/parity.md) diga `live`.
- **`AiGetModels` está obsoleto** (0.6, eliminado en 0.8) y nadie lo llama:
  el selector de modelo tiene codificado
  `supports_model_discovery = false`. No hay reemplazo; `AiComplete` lleva
  el modelo elegido en la petición.
- **La superficie de trait de 0.5 sigue viva como
  `astra_plugin_sdk::compat`**, obsoleta en 0.6 y eliminada en 0.8.
  Consulta [migración a 0.6](../migration-0.6.md).
- **`PluginCapability::source_id()`** está obsoleto: pasa el id a
  `Host::send_chat_message`, ya que el daemon dejó de filtrar por source
  id.
- **La autenticación entrante del servidor de capabilities no necesita
  ningún ajuste.** El daemon presenta `x-plugin-token` en cada llamada y
  fija `ASTRA_PLUGIN_CAPABILITY_AUTH=require`, así que el SDK rechaza una
  llamada sin él. Solo un daemon demasiado antiguo para enviar la
  cabecera te deja en la etapa `warn`; consulta
  [arquitectura](../1-orientation/architecture.md).

## Ver también

[Tabla de hooks para Rust](../hooks/rust.md) · [paridad](../reference/parity.md) ·
[errores](../reference/errors.md) ·
[política de versionado y desuso](../versioning.md)
</content>
