# SDK de Rust

El SDK de Rust es una API basada en traits centrada en un único trait, `PluginCapability`. Cada capacidad que expone el daemon se corresponde con una `async fn` que usted puede sobrescribir. Todos los métodos tienen implementaciones predeterminadas vacías (no-op), así que solo debe implementar lo que su plugin necesite.

Crate: `astra-plugin-sdk` en `AstraPlugins/astra-plugin-sdk`.
Fuente de verdad: `astra-plugin-sdk/src/capability.rs`.

## Configuración de Cargo

```toml
[package]
name = "my-plugin"
version = "0.1.0"
edition = "2021"

[dependencies]
astra-plugin-sdk = { path = "../../astra-plugin-sdk" }
tokio = { version = "1", features = ["full"] }
async-trait = "0.1"
anyhow = "1"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

## Plugin mínimo

```rust
use astra_plugin_sdk::prelude::*;

struct MyPlugin;

#[async_trait]
impl PluginCapability for MyPlugin {
    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef {
            name: "hello".into(),
            description: "Say hello".into(),
            parameters_json: "{}".into(),
        }]
    }

    async fn call_tool(&self, _name: &str, _args: &str) -> ToolResult {
        ToolResult::ok("Hello!")
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(MyPlugin).await
}
```

`astra_plugin_sdk::run(plugin)` se encarga del análisis de argumentos de línea de comandos (`--daemon-addr`, `--plugin-id`, `--auth-token`), vincula un servidor gRPC en `127.0.0.1:0`, se registra con el daemon, descubre qué capacidades ha implementado, despacha las llamadas entrantes y se bloquea hasta que el daemon envía `Shutdown`.

## El trait `PluginCapability`

Cada método tiene una implementación predeterminada que devuelve un valor vacío. Sobrescriba solo lo que necesite.

### Herramientas

```rust
async fn list_tools(&self) -> Vec<ToolDef>;
async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult;
```

`ToolDef.parameters_json` es una cadena con un JSON Schema. `call_tool` recibe el JSON en bruto de los argumentos de la herramienta elegidos por la IA. Devuelva `ToolResult::ok(...)` o `ToolResult::err(...)`.

### TTS (síntesis de voz)

```rust
async fn tts_synthesize(
    &self,
    text: &str,
    voice_id: &str,
    speed: f32,
    pitch: f32,
) -> anyhow::Result<AudioData>;

async fn tts_voices(&self) -> Vec<VoiceInfo>;
```

### STT (reconocimiento de voz)

```rust
async fn stt_languages(&self) -> Vec<String>;
```

El STT por streaming (`SttProcess`) utiliza gRPC bidireccional y requiere sobrescribir el servicio generado directamente — consulte `examples/` para una implementación de referencia.

### Proveedor de IA

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);  // (models, default_model_id)
```

### Acciones (Command Graph)

```rust
async fn action_types(&self) -> Vec<ActionTypeDef>;
async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult;
```

Construya `ActionTypeDef` a partir del tipo proto y los builders de `FieldDef` (véase abajo).

### Disparadores (Command Graph)

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;
```

El plugin dispara los disparadores llamando a `host.fire_trigger(...)` en su propio código — véase `HostClient` más abajo.

### Contribuciones de interfaz

```rust
async fn ui_contributions(&self) -> Vec<UiContribution>;
async fn handle_ui_call(&self, method: &str, params_json: &str) -> UiCallResult;
```

### Eventos

```rust
fn source_id(&self) -> &str { "" }
fn subscribed_events(&self) -> Vec<String> { vec![] }
async fn on_event(&self, event_type: &str, payload_json: &str) {}

// Typed convenience handlers (SDK deserializes for you):
async fn on_chat_sync(&self, event: ChatSyncEvent) {}
async fn on_state_changed(&self, event: StateChangedEvent) {}
async fn on_command_triggered(&self, event: CommandTriggeredEvent) {}
async fn on_command_completed(&self, event: CommandCompletedEvent) {}
```

Devuelva los tipos de eventos que le interesan desde `subscribed_events()` — por ejemplo `vec!["chat_message_sync".into(), "command_completed".into()]`. El SDK abre una suscripción de streaming en su nombre y despacha al manejador tipado cuando el evento coincide con una forma conocida, recurriendo a `on_event` en caso contrario.

### Ciclo de vida

```rust
async fn set_host(&self, host: Arc<Mutex<HostClient>>) {}
async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {}  // client plugins only
async fn on_config_changed(&self, config_json: &str) {}
async fn on_language_changed(&self, language: &str) {}
async fn on_active_triggers(&self, active_types: Vec<String>) {}
async fn on_shutdown(&self) {}
async fn health_check(&self) -> (bool, String) { (true, "ok".into()) }
```

`set_host` se llama una vez tras el registro — guarde el `Arc<Mutex<HostClient>>` dentro de su plugin (por ejemplo, detrás de un `Mutex<Option<...>>`) para realizar llamadas de vuelta al daemon.

### Plugins cliente

```rust
fn is_client(&self) -> bool { true }
```

Cuando esto devuelve `true`, el daemon emite un token de sesión durante el registro y el SDK le entrega un `DaemonClient` a través de `set_daemon_client`. Eso le da acceso a todos los servicios del daemon:

- `CoreService` — estado del daemon, iniciar/detener, suscripción a eventos.
- `ChatService` — enviar mensajes, transmitir respuestas, gestionar conversaciones.
- `VoiceService` — hablar, escuchar, listar voces.
- `CommandService` — ejecutar o cancelar comandos.
- `ConfigService` — leer/escribir ajustes.
- `MediaService` — control de reproducción multimedia.
- `MonitorService` — estadísticas del sistema, lista de plugins, logs de plugins.

## Builders de `FieldDef`

`FieldDef` se reexporta desde el tipo proto. Construya instancias con los constructores estáticos en `capability.rs:218-283`:

```rust
use astra_plugin_sdk::prelude::*;

let fields = vec![
    FieldDef::text("name", "Name")
        .with_placeholder("Enter your name")
        .with_description("Shown in the greeting"),
    FieldDef::textarea("body", "Message body"),
    FieldDef::textarea_with_variables("template", "Template")
        .with_placeholder("Hello {name}!"),
    FieldDef::dropdown("mode", "Mode", &[("fast", "Fast"), ("slow", "Slow")])
        .with_default("fast"),
    FieldDef::number("count", "Count")
        .with_min(1.0)
        .with_max(100.0)
        .with_step(1.0),
    FieldDef::toggle("verbose", "Verbose output"),
    FieldDef::hotkey("shortcut", "Shortcut"),
    FieldDef::file_picker("path", "File path"),
];
```

Setters encadenables: `with_placeholder`, `with_default`, `with_description`, `with_min`, `with_max`, `with_step`, `with_group`, `with_condition`.

Las condiciones de visibilidad permiten que los campos aparezcan solo cuando otros campos tengan valores específicos:

```rust
FieldDef::text("custom_value", "Custom value")
    .with_condition("mode", "equals", "custom")
```

## Builders de `UiContribution`

```rust
let contrib = UiContribution::page("stats", "Stats", "http://localhost:8123/stats.html")
    .with_icon_svg("<svg>…</svg>");

let effect = UiContribution::effect("http://localhost:8123/snow.html")
    .no_pointer_events();

let overlay = UiContribution::overlay("clock", "http://localhost:8123/clock.html")
    .with_size(200, 80)
    .transparent();
```

Constructores disponibles: `page`, `slot`, `effect`, `inject`, `overlay`. Los setters encadenables incluyen `with_label`, `with_icon_svg`, `with_size`, `transparent`, `no_pointer_events`, `with_z_index`, `with_prop`, `with_audio`.

## `HostClient`

API de paso directo para llamar al daemon. Disponible mediante `set_host` tras el registro.

```rust
host.log("info", "Plugin started").await?;
host.fire_trigger("on_alarm", r#"{"time":"09:00"}"#).await?;
host.set_variable("last_roll", "6").await?;
host.push_to_ui("stats", r#"{"counter":42}"#).await?;
let info = host.get_daemon_info().await?;   // version, state, port
let config = host.get_self_config().await?; // current plugin config as JSON
```

## `ActiveTriggers`

Disparar un disparador cuando ningún comando está escuchando es trabajo desperdiciado. El SDK mantiene un conjunto `ActiveTriggers` que el daemon actualiza mediante `on_active_triggers`:

```rust
if self.active_triggers.contains("on_alarm").await {
    host.fire_trigger("on_alarm", r#"{}"#).await?;
}
```

Declare un campo `ActiveTriggers` en la estructura de su plugin y deje que el SDK lo mantenga actualizado sobrescribiendo `on_active_triggers` para llamar a `self.active_triggers.update(types).await`.

## Ejemplo práctico — dice-roller

Consulte `AstraPlugins/examples/dice-roller` para un plugin completo que expone:

- Herramientas (`roll_dice`, `flip_coin`) con parámetros JSON Schema.
- Acciones (`roll_dice`, `flip_coin`) con entradas `FieldDef::number` y `FieldDef::dropdown` y `ai_available = true`.
- Disparadores (`on_roll_total`) que se disparan después de cada tirada de dados.

El manifiesto:

```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.1"

[entry]
command = "target/release/dice_roller.exe"

[capabilities]
tools = true
actions = true
triggers = true
```

## Dónde continuar

- [Capacidades](capabilities.md) — comportamiento completo de cada capacidad.
- [Manifiesto](manifest.md) — cada campo de `plugin.toml`.
- [Publicación](publishing.md) — construir, firmar, distribuir.
