# Rust SDK

Rust SDK — это API на основе трейтов, построенный вокруг единственного трейта `PluginCapability`. Каждая возможность, которую предоставляет демон, соответствует методу `async fn`, который вы можете переопределить. У всех методов есть реализация по умолчанию без побочных эффектов, поэтому вы реализуете только то, что нужно вашему плагину.

Крейт: `astra-plugin-sdk` в `AstraPlugins/astra-plugin-sdk`.
Источник правды: `astra-plugin-sdk/src/capability.rs`.

## Настройка Cargo

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

## Минимальный плагин

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

`astra_plugin_sdk::run(plugin)` выполняет разбор аргументов командной строки (`--daemon-addr`, `--plugin-id`, `--auth-token`), поднимает gRPC-сервер на `127.0.0.1:0`, регистрируется у демона, определяет, какие возможности вы реализовали, диспетчеризирует входящие вызовы и блокируется до тех пор, пока демон не отправит `Shutdown`.

## Трейт `PluginCapability`

У каждого метода есть реализация по умолчанию, возвращающая пустое значение. Переопределяйте только то, что вам нужно.

### Инструменты

```rust
async fn list_tools(&self) -> Vec<ToolDef>;
async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult;
```

`ToolDef.parameters_json` — это строка JSON Schema. `call_tool` получает сырой JSON аргументов инструмента, выбранных ИИ. Верните `ToolResult::ok(...)` или `ToolResult::err(...)`.

### TTS (преобразование текста в речь)

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

### STT (преобразование речи в текст)

```rust
async fn stt_languages(&self) -> Vec<String>;
```

Потоковый STT (`SttProcess`) использует двунаправленный gRPC и требует переопределения сгенерированного сервиса напрямую — см. `examples/` для эталонной реализации.

### ИИ-провайдер

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);  // (models, default_model_id)
```

### Действия (Граф команд)

```rust
async fn action_types(&self) -> Vec<ActionTypeDef>;
async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult;
```

Собирайте `ActionTypeDef` из proto-типа и билдеров `FieldDef` (ниже).

### Триггеры (Граф команд)

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;
```

Плагин запускает триггеры, вызывая `host.fire_trigger(...)` в собственном коде — см. `HostClient` ниже.

### UI-контрибуции

```rust
async fn ui_contributions(&self) -> Vec<UiContribution>;
async fn handle_ui_call(&self, method: &str, params_json: &str) -> UiCallResult;
```

### События

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

Верните из `subscribed_events()` типы событий, которые вас интересуют — например, `vec!["chat_message_sync".into(), "command_completed".into()]`. SDK открывает потоковую подписку от вашего имени и направляет событие в типизированный обработчик, если оно соответствует известной форме, с откатом на `on_event`.

### Жизненный цикл

```rust
async fn set_host(&self, host: Arc<Mutex<HostClient>>) {}
async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {}  // client plugins only
async fn on_config_changed(&self, config_json: &str) {}
async fn on_language_changed(&self, language: &str) {}
async fn on_active_triggers(&self, active_types: Vec<String>) {}
async fn on_shutdown(&self) {}
async fn health_check(&self) -> (bool, String) { (true, "ok".into()) }
```

`set_host` вызывается один раз после регистрации — сохраните `Arc<Mutex<HostClient>>` внутри вашего плагина (например, за `Mutex<Option<...>>`), чтобы обращаться к демону.

### Клиентские плагины

```rust
fn is_client(&self) -> bool { true }
```

Когда этот метод возвращает `true`, демон выдаёт токен сессии во время регистрации, а SDK передаёт вам `DaemonClient` через `set_daemon_client`. Это даёт доступ ко всем сервисам демона:

- `CoreService` — состояние демона, старт/стоп, подписка на события.
- `ChatService` — отправка сообщений, потоковые ответы, управление диалогами.
- `VoiceService` — говорить, слушать, получать список голосов.
- `CommandService` — выполнение или отмена команд.
- `ConfigService` — чтение/запись настроек.
- `MediaService` — управление воспроизведением медиа.
- `MonitorService` — статистика системы, список плагинов, логи плагинов.

## Билдеры `FieldDef`

`FieldDef` реэкспортируется из proto-типа. Создавайте экземпляры через статические конструкторы в `capability.rs:218-283`:

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

Цепочечные сеттеры: `with_placeholder`, `with_default`, `with_description`, `with_min`, `with_max`, `with_step`, `with_group`, `with_condition`.

Условия видимости позволяют полям появляться только когда другие поля имеют определённые значения:

```rust
FieldDef::text("custom_value", "Custom value")
    .with_condition("mode", "equals", "custom")
```

## Билдеры `UiContribution`

```rust
let contrib = UiContribution::page("stats", "Stats", "http://localhost:8123/stats.html")
    .with_icon_svg("<svg>…</svg>");

let effect = UiContribution::effect("http://localhost:8123/snow.html")
    .no_pointer_events();

let overlay = UiContribution::overlay("clock", "http://localhost:8123/clock.html")
    .with_size(200, 80)
    .transparent();
```

Доступные конструкторы: `page`, `slot`, `effect`, `inject`, `overlay`. Цепочечные сеттеры включают `with_label`, `with_icon_svg`, `with_size`, `transparent`, `no_pointer_events`, `with_z_index`, `with_prop`, `with_audio`.

## `HostClient`

Прозрачный API для вызова демона. Доступен через `set_host` после регистрации.

```rust
host.log("info", "Plugin started").await?;
host.fire_trigger("on_alarm", r#"{"time":"09:00"}"#).await?;
host.set_variable("last_roll", "6").await?;
host.push_to_ui("stats", r#"{"counter":42}"#).await?;
let info = host.get_daemon_info().await?;   // version, state, port
let config = host.get_self_config().await?; // current plugin config as JSON
```

## `ActiveTriggers`

Запуск триггера, когда ни одна команда не слушает, — пустая трата работы. SDK поддерживает множество `ActiveTriggers`, которое демон обновляет через `on_active_triggers`:

```rust
if self.active_triggers.contains("on_alarm").await {
    host.fire_trigger("on_alarm", r#"{}"#).await?;
}
```

Объявите поле `ActiveTriggers` в структуре плагина и позвольте SDK держать его актуальным, переопределив `on_active_triggers` так, чтобы он вызывал `self.active_triggers.update(types).await`.

## Полный пример — dice-roller

См. `AstraPlugins/examples/dice-roller` для полного плагина, который предоставляет:

- Инструменты (`roll_dice`, `flip_coin`) с JSON Schema-параметрами.
- Действия (`roll_dice`, `flip_coin`) с полями `FieldDef::number` и `FieldDef::dropdown` и `ai_available = true`.
- Триггеры (`on_roll_total`), запускающиеся после каждого броска кубиков.

Манифест:

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

## Куда двигаться дальше

- [Возможности](capabilities.md) — полное поведение каждой возможности.
- [Манифест](manifest.md) — каждое поле `plugin.toml`.
- [Публикация](publishing.md) — сборка, подпись, распространение.
