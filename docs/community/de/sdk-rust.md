> **Community-Übersetzung, zuletzt synchronisiert am 2026-04-17.** Die englische Dokumentation ist maßgeblich und hat sich seitdem geändert. Siehe [docs/en](../../en/README.md).
>
> **Community translation, last synchronised 2026-04-17.** The English documentation is authoritative and has changed since. See [docs/en](../../en/README.md).

---

# Rust-SDK

Das Rust-SDK ist eine trait-basierte API, zentriert auf ein einziges Trait: `PluginCapability`. Jede Fähigkeit, die der Daemon bereitstellt, entspricht einer `async fn`, die Sie überschreiben können. Alle Methoden haben No-op-Defaults, sodass Sie nur implementieren müssen, was Ihr Plugin tatsächlich benötigt.

Crate: `astra-plugin-sdk` unter `AstraPlugins/astra-plugin-sdk`.
Maßgebliche Quelle: `astra-plugin-sdk/src/capability.rs`.

## Cargo-Setup

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

## Minimales Plugin

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

`astra_plugin_sdk::run(plugin)` übernimmt das Parsen der CLI-Argumente (`--daemon-addr`, `--plugin-id`, `--auth-token`), bindet einen gRPC-Server an `127.0.0.1:0`, registriert sich beim Daemon, erkennt, welche Fähigkeiten Sie implementiert haben, verteilt eingehende Aufrufe und blockiert, bis der Daemon `Shutdown` sendet.

## Das Trait `PluginCapability`

Jede Methode hat einen Default, der einen leeren Wert zurückgibt. Überschreiben Sie nur, was Sie benötigen.

### Tools

```rust
async fn list_tools(&self) -> Vec<ToolDef>;
async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult;
```

`ToolDef.parameters_json` ist ein JSON-Schema-String. `call_tool` erhält das rohe JSON der von der KI gewählten Tool-Argumente. Geben Sie `ToolResult::ok(...)` oder `ToolResult::err(...)` zurück.

### TTS (Text-to-Speech)

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

### STT (Speech-to-Text)

```rust
async fn stt_languages(&self) -> Vec<String>;
```

Streaming-STT (`SttProcess`) verwendet bidirektionales gRPC und erfordert, dass Sie den generierten Dienst direkt überschreiben — in `examples/` finden Sie eine Referenzimplementierung.

### AI-Provider

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);  // (models, default_model_id)
```

### Aktionen (Command Graph)

```rust
async fn action_types(&self) -> Vec<ActionTypeDef>;
async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult;
```

Konstruieren Sie `ActionTypeDef` aus dem Proto-Typ und den `FieldDef`-Buildern (siehe unten).

### Trigger (Command Graph)

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;
```

Das Plugin feuert Trigger, indem es in seinem eigenen Code `host.fire_trigger(...)` aufruft — siehe `HostClient` weiter unten.

### UI-Beiträge

```rust
async fn ui_contributions(&self) -> Vec<UiContribution>;
async fn handle_ui_call(&self, method: &str, params_json: &str) -> UiCallResult;
```

### Ereignisse

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

Geben Sie in `subscribed_events()` die Ereignistypen zurück, an denen Sie interessiert sind — zum Beispiel `vec!["chat_message_sync".into(), "command_completed".into()]`. Das SDK öffnet in Ihrem Namen ein Streaming-Abonnement und leitet an den typisierten Handler weiter, wenn das Ereignis eine bekannte Form hat — ansonsten fällt es auf `on_event` zurück.

### Lebenszyklus

```rust
async fn set_host(&self, host: Arc<Mutex<HostClient>>) {}
async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {}  // client plugins only
async fn on_config_changed(&self, config_json: &str) {}
async fn on_language_changed(&self, language: &str) {}
async fn on_active_triggers(&self, active_types: Vec<String>) {}
async fn on_shutdown(&self) {}
async fn health_check(&self) -> (bool, String) { (true, "ok".into()) }
```

`set_host` wird einmal nach der Registrierung aufgerufen — speichern Sie den `Arc<Mutex<HostClient>>` in Ihrem Plugin (z. B. hinter einem `Mutex<Option<...>>`), um den Daemon zurückzurufen.

### Client-Plugins

```rust
fn is_client(&self) -> bool { true }
```

Gibt dies `true` zurück, stellt der Daemon bei der Registrierung ein Sitzungstoken aus und das SDK übergibt Ihnen einen `DaemonClient` per `set_daemon_client`. Damit erhalten Sie Zugriff auf jeden Dienst des Daemons:

- `CoreService` — Daemon-Status, Start/Stop, Ereignisabonnement.
- `ChatService` — Nachrichten senden, Antworten streamen, Konversationen verwalten.
- `VoiceService` — sprechen, zuhören, Stimmen auflisten.
- `CommandService` — Befehle ausführen oder abbrechen.
- `ConfigService` — Einstellungen lesen/schreiben.
- `MediaService` — Medienwiedergabe steuern.
- `MonitorService` — Systemstatistiken, Plugin-Liste, Plugin-Logs.

## `FieldDef`-Builder

`FieldDef` wird vom Proto-Typ reexportiert. Erzeugen Sie Instanzen mit den statischen Konstruktoren in `capability.rs:218-283`:

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

Verkettbare Setter: `with_placeholder`, `with_default`, `with_description`, `with_min`, `with_max`, `with_step`, `with_group`, `with_condition`.

Sichtbarkeitsbedingungen lassen Felder nur dann erscheinen, wenn andere Felder bestimmte Werte haben:

```rust
FieldDef::text("custom_value", "Custom value")
    .with_condition("mode", "equals", "custom")
```

## `UiContribution`-Builder

```rust
let contrib = UiContribution::page("stats", "Stats", "http://localhost:8123/stats.html")
    .with_icon_svg("<svg>…</svg>");

let effect = UiContribution::effect("http://localhost:8123/snow.html")
    .no_pointer_events();

let overlay = UiContribution::overlay("clock", "http://localhost:8123/clock.html")
    .with_size(200, 80)
    .transparent();
```

Verfügbare Konstruktoren: `page`, `slot`, `effect`, `inject`, `overlay`. Verkettbare Setter sind unter anderem `with_label`, `with_icon_svg`, `with_size`, `transparent`, `no_pointer_events`, `with_z_index`, `with_prop`, `with_audio`.

## `HostClient`

Durchgereichte API für Aufrufe an den Daemon. Nach der Registrierung über `set_host` verfügbar.

```rust
host.log("info", "Plugin started").await?;
host.fire_trigger("on_alarm", r#"{"time":"09:00"}"#).await?;
host.set_variable("last_roll", "6").await?;
host.push_to_ui("stats", r#"{"counter":42}"#).await?;
let info = host.get_daemon_info().await?;   // version, state, port
let config = host.get_self_config().await?; // current plugin config as JSON
```

## `ActiveTriggers`

Einen Trigger auszulösen, wenn kein Befehl zuhört, ist verschwendete Arbeit. Das SDK pflegt eine `ActiveTriggers`-Menge, die der Daemon via `on_active_triggers` aktualisiert:

```rust
if self.active_triggers.contains("on_alarm").await {
    host.fire_trigger("on_alarm", r#"{}"#).await?;
}
```

Deklarieren Sie ein `ActiveTriggers`-Feld in Ihrer Plugin-Struktur und halten Sie es durch das SDK aktuell, indem Sie `on_active_triggers` überschreiben und darin `self.active_triggers.update(types).await` aufrufen.

## Ausgearbeitetes Beispiel — dice-roller

Unter `AstraPlugins/examples/dice-roller` finden Sie ein vollständiges Plugin, das Folgendes bereitstellt:

- Tools (`roll_dice`, `flip_coin`) mit JSON-Schema-Parametern.
- Aktionen (`roll_dice`, `flip_coin`) mit `FieldDef::number`- und `FieldDef::dropdown`-Eingaben und `ai_available = true`.
- Trigger (`on_roll_total`), die nach jedem Würfelwurf auslösen.

Das Manifest:

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

## Wie geht es weiter

- [Fähigkeiten](capabilities.md) — vollständiges Verhalten jeder Fähigkeit.
- [Manifest](manifest.md) — jedes `plugin.toml`-Feld.
- [Veröffentlichung](publishing.md) — bauen, signieren, verteilen.
