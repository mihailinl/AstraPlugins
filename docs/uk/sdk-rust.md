# Rust SDK

Rust SDK — це API на основі трейтів, зосереджений навколо єдиного трейту `PluginCapability`. Кожна можливість, яку надає демон, відповідає `async fn`, який ви можете перевизначити. Усі методи мають реалізації за замовчуванням, що нічого не роблять, тож ви реалізуєте лише те, що потрібно вашому плагіну.

Крейт: `astra-plugin-sdk` у `AstraPlugins/astra-plugin-sdk`.
Джерело істини: `astra-plugin-sdk/src/capability.rs`.

## Налаштування Cargo

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

## Мінімальний плагін

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

`astra_plugin_sdk::run(plugin)` обробляє розбір аргументів CLI (`--daemon-addr`, `--plugin-id`, `--auth-token`), піднімає gRPC-сервер на `127.0.0.1:0`, реєструється в демоні, визначає реалізовані вами можливості, диспатчить вхідні виклики і блокує до моменту, коли демон надішле `Shutdown`.

## Трейт `PluginCapability`

Кожен метод має реалізацію за замовчуванням, що повертає порожнє значення. Перевизначайте лише те, що потрібно.

### Tools

```rust
async fn list_tools(&self) -> Vec<ToolDef>;
async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult;
```

`ToolDef.parameters_json` — це рядок JSON Schema. `call_tool` отримує сирий JSON з аргументами інструмента, обраними AI. Поверніть `ToolResult::ok(...)` або `ToolResult::err(...)`.

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

Потоковий STT (`SttProcess`) використовує двонаправлений gRPC і вимагає безпосереднього перевизначення згенерованої служби — див. реалізацію-приклад у `examples/`.

### AI provider

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);  // (models, default_model_id)
```

### Actions (Command Graph)

```rust
async fn action_types(&self) -> Vec<ActionTypeDef>;
async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult;
```

Будуйте `ActionTypeDef` з proto-типу та конструкторів `FieldDef` (нижче).

### Triggers (Command Graph)

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;
```

Плагін активує тригери, викликаючи `host.fire_trigger(...)` у власному коді — див. `HostClient` нижче.

### UI contributions

```rust
async fn ui_contributions(&self) -> Vec<UiContribution>;
async fn handle_ui_call(&self, method: &str, params_json: &str) -> UiCallResult;
```

### Події

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

Поверніть типи подій, що вас цікавлять, з `subscribed_events()` — наприклад, `vec!["chat_message_sync".into(), "command_completed".into()]`. SDK відкриває потокову підписку за вас і диспатчить до типізованого обробника, коли відповідає відома форма події, а інакше викликає `on_event`.

### Життєвий цикл

```rust
async fn set_host(&self, host: Arc<Mutex<HostClient>>) {}
async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {}  // client plugins only
async fn on_config_changed(&self, config_json: &str) {}
async fn on_language_changed(&self, language: &str) {}
async fn on_active_triggers(&self, active_types: Vec<String>) {}
async fn on_shutdown(&self) {}
async fn health_check(&self) -> (bool, String) { (true, "ok".into()) }
```

`set_host` викликається один раз після реєстрації — збережіть `Arc<Mutex<HostClient>>` усередині свого плагіна (наприклад, за `Mutex<Option<...>>`), щоб звертатися назад до демона.

### Клієнтські плагіни

```rust
fn is_client(&self) -> bool { true }
```

Коли це повертає `true`, демон видає токен сесії під час реєстрації, і SDK передає вам `DaemonClient` через `set_daemon_client`. Це дає доступ до всіх служб демона:

- `CoreService` — стан демона, запуск/зупинка, підписка на події.
- `ChatService` — надсилання повідомлень, потокові відповіді, керування розмовами.
- `VoiceService` — говорити, слухати, перелік голосів.
- `CommandService` — виконання або скасування команд.
- `ConfigService` — читання/запис налаштувань.
- `MediaService` — керування відтворенням медіа.
- `MonitorService` — системна статистика, список плагінів, логи плагінів.

## Конструктори `FieldDef`

`FieldDef` реекспортується з proto-типу. Будуйте екземпляри статичними конструкторами з `capability.rs:218-283`:

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

Ланцюжкові сетери: `with_placeholder`, `with_default`, `with_description`, `with_min`, `with_max`, `with_step`, `with_group`, `with_condition`.

Умови видимості дозволяють полям з'являтися лише коли інші поля мають певні значення:

```rust
FieldDef::text("custom_value", "Custom value")
    .with_condition("mode", "equals", "custom")
```

## Конструктори `UiContribution`

```rust
let contrib = UiContribution::page("stats", "Stats", "http://localhost:8123/stats.html")
    .with_icon_svg("<svg>…</svg>");

let effect = UiContribution::effect("http://localhost:8123/snow.html")
    .no_pointer_events();

let overlay = UiContribution::overlay("clock", "http://localhost:8123/clock.html")
    .with_size(200, 80)
    .transparent();
```

Доступні конструктори: `page`, `slot`, `effect`, `inject`, `overlay`. Ланцюжкові сетери включають `with_label`, `with_icon_svg`, `with_size`, `transparent`, `no_pointer_events`, `with_z_index`, `with_prop`, `with_audio`.

## `HostClient`

Прозоре API для викликів до демона. Доступне через `set_host` після реєстрації.

```rust
host.log("info", "Plugin started").await?;
host.fire_trigger("on_alarm", r#"{"time":"09:00"}"#).await?;
host.set_variable("last_roll", "6").await?;
host.push_to_ui("stats", r#"{"counter":42}"#).await?;
let info = host.get_daemon_info().await?;   // version, state, port
let config = host.get_self_config().await?; // current plugin config as JSON
```

## `ActiveTriggers`

Активація тригера, коли немає команди-слухача, — марна робота. SDK підтримує набір `ActiveTriggers`, який демон оновлює через `on_active_triggers`:

```rust
if self.active_triggers.contains("on_alarm").await {
    host.fire_trigger("on_alarm", r#"{}"#).await?;
}
```

Оголосіть поле `ActiveTriggers` у структурі свого плагіна і дайте SDK підтримувати його актуальним, перевизначивши `on_active_triggers` для виклику `self.active_triggers.update(types).await`.

## Робочий приклад — dice-roller

Див. `AstraPlugins/examples/dice-roller` — повний плагін, що надає:

- Інструменти (`roll_dice`, `flip_coin`) з параметрами у вигляді JSON Schema.
- Дії (`roll_dice`, `flip_coin`) з полями `FieldDef::number` і `FieldDef::dropdown` та `ai_available = true`.
- Тригери (`on_roll_total`), що активуються після кожного кидка.

Маніфест:

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

## Куди далі

- [Capabilities](capabilities.md) — повна поведінка кожної можливості.
- [Manifest](manifest.md) — кожне поле `plugin.toml`.
- [Publishing](publishing.md) — збирання, підпис, розповсюдження.
