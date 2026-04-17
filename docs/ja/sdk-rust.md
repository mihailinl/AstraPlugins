# Rust SDK

Rust SDK は `PluginCapability` という単一のトレイトを中心としたトレイトベースの API です。デーモンが公開するすべての機能は、オーバーライド可能な `async fn` に対応しています。すべてのメソッドには no-op のデフォルト実装があるため、必要なものだけを実装すれば十分です。

クレート: `AstraPlugins/astra-plugin-sdk` にある `astra-plugin-sdk`。
正式な仕様: `astra-plugin-sdk/src/capability.rs`。

## Cargo のセットアップ

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

## 最小構成のプラグイン

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

`astra_plugin_sdk::run(plugin)` は、CLI 引数（`--daemon-addr`、`--plugin-id`、`--auth-token`）の解析、`127.0.0.1:0` での gRPC サーバーの起動、デーモンへの登録、実装済み機能の検出、受信コールのディスパッチ、そしてデーモンから `Shutdown` を受け取るまでのブロッキングを一括で処理します。

## `PluginCapability` トレイト

各メソッドには空の値を返すデフォルト実装があります。必要なものだけをオーバーライドしてください。

### Tools

```rust
async fn list_tools(&self) -> Vec<ToolDef>;
async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult;
```

`ToolDef.parameters_json` は JSON Schema の文字列です。`call_tool` には AI が選択したツール引数の生 JSON が渡されます。結果は `ToolResult::ok(...)` または `ToolResult::err(...)` で返します。

### TTS（音声合成）

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

### STT（音声認識）

```rust
async fn stt_languages(&self) -> Vec<String>;
```

ストリーミング STT（`SttProcess`）は双方向 gRPC を使用するため、生成されたサービスを直接オーバーライドする必要があります。実装例は `examples/` を参照してください。

### AI プロバイダ

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);  // (models, default_model_id)
```

### Actions（Command Graph）

```rust
async fn action_types(&self) -> Vec<ActionTypeDef>;
async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult;
```

`ActionTypeDef` は proto 型と後述の `FieldDef` ビルダーから構築します。

### Triggers（Command Graph）

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;
```

トリガーはプラグイン側のコードから `host.fire_trigger(...)` を呼び出して発火させます。後述の `HostClient` を参照してください。

### UI コントリビューション

```rust
async fn ui_contributions(&self) -> Vec<UiContribution>;
async fn handle_ui_call(&self, method: &str, params_json: &str) -> UiCallResult;
```

### イベント

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

`subscribed_events()` から、関心のあるイベント種別を返してください（例: `vec!["chat_message_sync".into(), "command_completed".into()]`）。SDK が代わりにストリーミング購読を開始し、既知のイベント形状に一致する場合は型付きハンドラへ、一致しない場合は `on_event` にフォールバックしてディスパッチします。

### ライフサイクル

```rust
async fn set_host(&self, host: Arc<Mutex<HostClient>>) {}
async fn set_daemon_client(&self, client: Arc<Mutex<DaemonClient>>) {}  // client plugins only
async fn on_config_changed(&self, config_json: &str) {}
async fn on_language_changed(&self, language: &str) {}
async fn on_active_triggers(&self, active_types: Vec<String>) {}
async fn on_shutdown(&self) {}
async fn health_check(&self) -> (bool, String) { (true, "ok".into()) }
```

`set_host` は登録直後に一度だけ呼び出されます。受け取った `Arc<Mutex<HostClient>>` は、デーモンへコールバックできるようにプラグイン内（例: `Mutex<Option<...>>` の中）に保持してください。

### クライアントプラグイン

```rust
fn is_client(&self) -> bool { true }
```

これが `true` を返すと、デーモンは登録時にセッショントークンを発行し、SDK は `set_daemon_client` 経由で `DaemonClient` を渡します。これにより、次のすべてのデーモンサービスへアクセスできます。

- `CoreService` — デーモンの状態、開始／停止、イベント購読。
- `ChatService` — メッセージ送信、応答のストリーミング、会話管理。
- `VoiceService` — 音声出力、音声入力、ボイス一覧。
- `CommandService` — コマンドの実行やキャンセル。
- `ConfigService` — 設定の読み書き。
- `MediaService` — メディア再生の制御。
- `MonitorService` — システム統計、プラグイン一覧、プラグインログ。

## `FieldDef` ビルダー

`FieldDef` は proto 型から再エクスポートされています。インスタンスは `capability.rs:218-283` の静的コンストラクタで生成します。

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

チェーン可能なセッター: `with_placeholder`、`with_default`、`with_description`、`with_min`、`with_max`、`with_step`、`with_group`、`with_condition`。

表示条件を使うと、他のフィールドが特定の値を持つ場合にのみフィールドを表示できます。

```rust
FieldDef::text("custom_value", "Custom value")
    .with_condition("mode", "equals", "custom")
```

## `UiContribution` ビルダー

```rust
let contrib = UiContribution::page("stats", "Stats", "http://localhost:8123/stats.html")
    .with_icon_svg("<svg>…</svg>");

let effect = UiContribution::effect("http://localhost:8123/snow.html")
    .no_pointer_events();

let overlay = UiContribution::overlay("clock", "http://localhost:8123/clock.html")
    .with_size(200, 80)
    .transparent();
```

利用可能なコンストラクタ: `page`、`slot`、`effect`、`inject`、`overlay`。チェーン可能なセッター: `with_label`、`with_icon_svg`、`with_size`、`transparent`、`no_pointer_events`、`with_z_index`、`with_prop`、`with_audio`。

## `HostClient`

デーモンを呼び出すためのパススルー API です。登録後、`set_host` を通じて利用できます。

```rust
host.log("info", "Plugin started").await?;
host.fire_trigger("on_alarm", r#"{"time":"09:00"}"#).await?;
host.set_variable("last_roll", "6").await?;
host.push_to_ui("stats", r#"{"counter":42}"#).await?;
let info = host.get_daemon_info().await?;   // version, state, port
let config = host.get_self_config().await?; // current plugin config as JSON
```

## `ActiveTriggers`

待ち受けているコマンドが無いときにトリガーを発火しても無駄になります。SDK は `ActiveTriggers` のセットを保持しており、デーモンは `on_active_triggers` を介してこのセットを更新します。

```rust
if self.active_triggers.contains("on_alarm").await {
    host.fire_trigger("on_alarm", r#"{}"#).await?;
}
```

プラグインの構造体に `ActiveTriggers` フィールドを宣言し、`on_active_triggers` をオーバーライドして `self.active_triggers.update(types).await` を呼び出すことで、SDK がセットを最新に保ちます。

## 実例 — dice-roller

完全なプラグイン例は `AstraPlugins/examples/dice-roller` にあります。以下を公開しています。

- JSON Schema パラメータを持つツール（`roll_dice`、`flip_coin`）。
- `FieldDef::number` と `FieldDef::dropdown` を入力に使い、`ai_available = true` にしたアクション（`roll_dice`、`flip_coin`）。
- 各ダイスロール後に発火するトリガー（`on_roll_total`）。

マニフェスト:

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

## 次に進むには

- [機能](capabilities.md) — 各機能の完全な動作仕様。
- [マニフェスト](manifest.md) — `plugin.toml` の全フィールド。
- [公開](publishing.md) — ビルド、署名、配布。
