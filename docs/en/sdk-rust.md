# Rust SDK

The Rust SDK is a trait-based API centred on a single trait, `PluginCapability`. Every capability the daemon exposes corresponds to an `async fn` you can override. All methods have no-op defaults, so you only implement what your plugin needs.

Crate: `astra-plugin-sdk` at `AstraPlugins/astra-plugin-sdk`.
Source of truth: `astra-plugin-sdk/src/capability.rs`.

## Cargo setup

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

## Minimal plugin

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

`astra_plugin_sdk::run(plugin)` handles CLI argument parsing (`--daemon-addr`, `--plugin-id`, `--auth-token`), binds a gRPC server on `127.0.0.1:0`, registers with the daemon, discovers which capabilities you implemented, dispatches incoming calls, and blocks until the daemon sends `Shutdown`.

## The `PluginCapability` trait

Every method has a default that returns an empty value. Override only what you need.

### Tools

```rust
async fn list_tools(&self) -> Vec<ToolDef>;
async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult;
```

`ToolDef.parameters_json` is a JSON Schema string. `call_tool` receives the raw JSON of tool arguments chosen by the AI. Return `ToolResult::ok(...)` or `ToolResult::err(...)`.

### TTS (text-to-speech)

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

### STT (speech-to-text)

```rust
async fn stt_languages(&self) -> Vec<String>;
```

Streaming STT (`SttProcess`) uses bidirectional gRPC and requires overriding the generated service directly — see `examples/` for a reference implementation.

### AI provider

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);  // (models, default_model_id)
```

### Actions (Command Graph)

```rust
async fn action_types(&self) -> Vec<ActionTypeDef>;
async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult;
```

Build `ActionTypeDef` from the proto type and `FieldDef` builders (below).

### Triggers (Command Graph)

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;
```

The plugin fires triggers by calling `host.fire_trigger(...)` in its own code — see `HostClient` below.

### UI contributions

```rust
async fn ui_contributions(&self) -> Vec<UiContribution>;
async fn handle_ui_call(&self, method: &str, params_json: &str) -> UiCallResult;
```

### Events

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

Return the event types you care about from `subscribed_events()` — for example `vec!["chat_message_sync".into(), "command_completed".into()]`. The SDK opens a streaming subscription on your behalf and dispatches to the typed handler when it matches a known event shape, falling back to `on_event`.

### Lifecycle

```rust
async fn set_host(&self, host: Arc<Mutex<HostClient>>) {}
async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {}  // client plugins only
async fn on_config_changed(&self, config_json: &str) {}
async fn on_language_changed(&self, language: &str) {}
async fn on_active_triggers(&self, active_types: Vec<String>) {}
async fn on_shutdown(&self) {}
async fn health_check(&self) -> (bool, String) { (true, "ok".into()) }
```

`set_host` is called once after registration — store the `Arc<Mutex<HostClient>>` inside your plugin (e.g. behind a `Mutex<Option<...>>`) to call back into the daemon.

### Client plugins

```rust
fn is_client(&self) -> bool { true }
```

When this returns `true` the daemon issues a session token during registration and the SDK hands you a `DaemonClient` via `set_daemon_client`. That gives you access to every daemon service:

- `CoreService` — daemon state, start/stop, event subscription.
- `ChatService` — send messages, stream responses, manage conversations.
- `VoiceService` — speak, listen, list voices.
- `CommandService` — execute or cancel commands.
- `ConfigService` — read/write settings.
- `MediaService` — media playback control.
- `MonitorService` — system stats, plugin list, plugin logs.

## `FieldDef` builders

`FieldDef` is re-exported from the proto type. Build instances with the static constructors in `capability.rs:218-283`:

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

Chainable setters: `with_placeholder`, `with_default`, `with_description`, `with_min`, `with_max`, `with_step`, `with_group`, `with_condition`.

Visibility conditions let fields appear only when other fields have specific values:

```rust
FieldDef::text("custom_value", "Custom value")
    .with_condition("mode", "equals", "custom")
```

## `UiContribution` builders

```rust
let contrib = UiContribution::page("stats", "Stats", "http://localhost:8123/stats.html")
    .with_icon_svg("<svg>…</svg>");

let effect = UiContribution::effect("http://localhost:8123/snow.html")
    .no_pointer_events();

let overlay = UiContribution::overlay("clock", "http://localhost:8123/clock.html")
    .with_size(200, 80)
    .transparent();
```

Available constructors: `page`, `slot`, `effect`, `inject`, `overlay`. Chainable setters include `with_label`, `with_icon_svg`, `with_size`, `transparent`, `no_pointer_events`, `with_z_index`, `with_prop`, `with_audio`.

## `HostClient`

Pass-through API for calling the daemon. Available via `set_host` after registration.

```rust
host.log("info", "Plugin started").await?;
host.fire_trigger("on_alarm", r#"{"time":"09:00"}"#).await?;
host.set_variable("last_roll", "6").await?;
host.push_to_ui("stats", r#"{"counter":42}"#).await?;
let info = host.get_daemon_info().await?;   // version, state, port
let config = host.get_self_config().await?; // current plugin config as JSON
```

## `ActiveTriggers`

Firing a trigger when no command is listening is wasted work. The SDK maintains an `ActiveTriggers` set that the daemon updates via `on_active_triggers`:

```rust
if self.active_triggers.contains("on_alarm").await {
    host.fire_trigger("on_alarm", r#"{}"#).await?;
}
```

Declare an `ActiveTriggers` field on your plugin struct and let the SDK keep it fresh by overriding `on_active_triggers` to call `self.active_triggers.update(types).await`.

## Worked example — dice-roller

See `AstraPlugins/examples/dice-roller` for a complete plugin that exposes:

- Tools (`roll_dice`, `flip_coin`) with JSON Schema params.
- Actions (`roll_dice`, `flip_coin`) with `FieldDef::number` and `FieldDef::dropdown` inputs and `ai_available = true`.
- Triggers (`on_roll_total`) that fire after each dice roll.

The manifest:

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

## Where to go next

- [Capabilities](capabilities.md) — full behaviour of every capability.
- [Manifest](manifest.md) — every `plugin.toml` field.
- [Publishing](publishing.md) — building, signing, distributing.
