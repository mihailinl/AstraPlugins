# Rust SDK

Rust SDK 是基于 trait 的 API，核心是一个 trait：`PluginCapability`。守护进程暴露的每种能力都对应一个你可以重写的 `async fn`。所有方法都带有空操作（no-op）默认实现，因此你只需实现插件所需的部分。

Crate：`astra-plugin-sdk`，位于 `AstraPlugins/astra-plugin-sdk`。
权威源：`astra-plugin-sdk/src/capability.rs`。

## Cargo 配置

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

## 最小插件示例

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

`astra_plugin_sdk::run(plugin)` 负责解析 CLI 参数（`--daemon-addr`、`--plugin-id`、`--auth-token`），在 `127.0.0.1:0` 上绑定 gRPC 服务器，向守护进程注册，发现你实现了哪些能力，分发传入的调用，并一直阻塞直到守护进程发送 `Shutdown`。

## `PluginCapability` trait

每个方法都有返回空值的默认实现。只需重写你需要的部分。

### Tools

```rust
async fn list_tools(&self) -> Vec<ToolDef>;
async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult;
```

`ToolDef.parameters_json` 是 JSON Schema 字符串。`call_tool` 接收由 AI 选择的工具参数的原始 JSON。返回 `ToolResult::ok(...)` 或 `ToolResult::err(...)`。

### TTS（文本转语音）

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

### STT（语音转文本）

```rust
async fn stt_languages(&self) -> Vec<String>;
```

流式 STT（`SttProcess`）使用双向 gRPC，需要直接重写生成的服务 —— 参考实现见 `examples/`。

### AI provider

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);  // (models, default_model_id)
```

### Actions（命令图）

```rust
async fn action_types(&self) -> Vec<ActionTypeDef>;
async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult;
```

通过 proto 类型和下述 `FieldDef` 构建器来构造 `ActionTypeDef`。

### Triggers（命令图）

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;
```

插件在自己的代码中调用 `host.fire_trigger(...)` 来触发触发器 —— 参见下文 `HostClient`。

### UI contributions

```rust
async fn ui_contributions(&self) -> Vec<UiContribution>;
async fn handle_ui_call(&self, method: &str, params_json: &str) -> UiCallResult;
```

### 事件

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

从 `subscribed_events()` 返回你关心的事件类型 —— 例如 `vec!["chat_message_sync".into(), "command_completed".into()]`。SDK 会代表你打开一个流式订阅，并在匹配到已知事件形态时分发到对应的类型化处理器，否则回退到 `on_event`。

### 生命周期

```rust
async fn set_host(&self, host: Arc<Mutex<HostClient>>) {}
async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {}  // client plugins only
async fn on_config_changed(&self, config_json: &str) {}
async fn on_language_changed(&self, language: &str) {}
async fn on_active_triggers(&self, active_types: Vec<String>) {}
async fn on_shutdown(&self) {}
async fn health_check(&self) -> (bool, String) { (true, "ok".into()) }
```

`set_host` 在注册之后被调用一次 —— 将 `Arc<Mutex<HostClient>>` 存入插件内部（例如放在 `Mutex<Option<...>>` 后面），以便之后回调守护进程。

### Client 插件

```rust
fn is_client(&self) -> bool { true }
```

当此方法返回 `true` 时，守护进程在注册期间下发会话令牌，SDK 会通过 `set_daemon_client` 向你递交一个 `DaemonClient`。这让你可以访问每个守护进程服务：

- `CoreService` —— 守护进程状态、启动/停止、事件订阅。
- `ChatService` —— 发送消息、流式接收响应、管理对话。
- `VoiceService` —— 语音朗读、监听、列出 voices。
- `CommandService` —— 执行或取消命令。
- `ConfigService` —— 读取/写入设置。
- `MediaService` —— 媒体播放控制。
- `MonitorService` —— 系统统计、插件列表、插件日志。

## `FieldDef` 构建器

`FieldDef` 从 proto 类型重新导出。使用 `capability.rs:218-283` 中的静态构造函数来构造实例：

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

可链式调用的 setter：`with_placeholder`、`with_default`、`with_description`、`with_min`、`with_max`、`with_step`、`with_group`、`with_condition`。

可见性条件可使字段仅在其他字段取特定值时出现：

```rust
FieldDef::text("custom_value", "Custom value")
    .with_condition("mode", "equals", "custom")
```

## `UiContribution` 构建器

```rust
let contrib = UiContribution::page("stats", "Stats", "http://localhost:8123/stats.html")
    .with_icon_svg("<svg>…</svg>");

let effect = UiContribution::effect("http://localhost:8123/snow.html")
    .no_pointer_events();

let overlay = UiContribution::overlay("clock", "http://localhost:8123/clock.html")
    .with_size(200, 80)
    .transparent();
```

可用构造函数：`page`、`slot`、`effect`、`inject`、`overlay`。可链式调用的 setter 包括 `with_label`、`with_icon_svg`、`with_size`、`transparent`、`no_pointer_events`、`with_z_index`、`with_prop`、`with_audio`。

## `HostClient`

用于调用守护进程的直通 API。在注册之后通过 `set_host` 提供。

```rust
host.log("info", "Plugin started").await?;
host.fire_trigger("on_alarm", r#"{"time":"09:00"}"#).await?;
host.set_variable("last_roll", "6").await?;
host.push_to_ui("stats", r#"{"counter":42}"#).await?;
let info = host.get_daemon_info().await?;   // version, state, port
let config = host.get_self_config().await?; // current plugin config as JSON
```

## `ActiveTriggers`

在没有任何命令监听时触发触发器是无用功。SDK 维护一个 `ActiveTriggers` 集合，由守护进程通过 `on_active_triggers` 更新：

```rust
if self.active_triggers.contains("on_alarm").await {
    host.fire_trigger("on_alarm", r#"{}"#).await?;
}
```

在你的插件结构体上声明一个 `ActiveTriggers` 字段，并通过重写 `on_active_triggers` 调用 `self.active_triggers.update(types).await`，让 SDK 保持其为最新。

## 完整示例 —— dice-roller

请参阅 `AstraPlugins/examples/dice-roller`，这是一个完整插件，暴露：

- Tools（`roll_dice`、`flip_coin`），带有 JSON Schema 参数。
- Actions（`roll_dice`、`flip_coin`），使用 `FieldDef::number` 和 `FieldDef::dropdown` 输入，并设置 `ai_available = true`。
- Triggers（`on_roll_total`），在每次掷骰后触发。

清单：

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

## 下一步

- [能力](capabilities.md) —— 每种能力的完整行为。
- [清单](manifest.md) —— 每个 `plugin.toml` 字段。
- [发布](publishing.md) —— 构建、签名、分发。
