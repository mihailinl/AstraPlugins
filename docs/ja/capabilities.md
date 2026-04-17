# 機能リファレンス

Astra プラグインは、以下の9つの機能のうち1つ以上を実装します。このページでは各機能の目的、各 SDK での API 面、関連する proto RPC、最小のマニフェストエントリを示します。

## `tools`

AI から呼び出せるツールを公開します。チャットモデルはツール名、説明、引数の JSON Schema を参照し、ターン中に呼び出すことができます。

マニフェスト：

```toml
[capabilities]
tools = true
```

### Rust

```rust
async fn list_tools(&self) -> Vec<ToolDef>;
async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult;
```

### Python

```python
@tool("Description")
async def my_tool(self, arg1: str, arg2: int = 5) -> dict:
    return {"value": 42}
```

### TypeScript

```typescript
async listTools(): Promise<ToolDef[]>;
async callTool(name: string, argumentsJson: string): Promise<ToolResult>;
```

Proto RPC（プラグイン側）：`ListTools`、`CallTool`。

## `tts`

テキスト読み上げの音声プロバイダーです。登録された音声はデーモンの TTS 音声ピッカーに表示されます。

マニフェスト：

```toml
[capabilities]
tts = true
```

### Rust

```rust
async fn tts_voices(&self) -> Vec<VoiceInfo>;
async fn tts_synthesize(
    &self, text: &str, voice_id: &str, speed: f32, pitch: f32
) -> anyhow::Result<AudioData>;
```

### Python

```python
async def tts_list_voices(self) -> list[dict]:
    return [{"id": "alice", "name": "Alice", "language": "en", "gender": "female"}]

async def tts_synthesize(self, text, voice_id, speed, pitch):
    return {"audio": audio_bytes, "format": "pcm", "sample_rate": 24000}
```

### TypeScript

```typescript
async ttsListVoices(): Promise<VoiceInfo[]>;
async ttsSynthesize(text, voiceId, speed, pitch): Promise<AudioData>;
```

Proto RPC：`TtsListVoices`、`TtsSynthesize`、`TtsSynthesizeStream`（任意、ストリーミング用）。

## `stt`

音声認識の言語プロバイダーです。デーモンはプラグインに音声をストリーミングし、文字起こしイベントのストリームを期待します。

マニフェスト：

```toml
[capabilities]
stt = true
```

### Rust / Python / TypeScript

`stt_languages` / `sttGetLanguages` をオーバーライドしてサポートする言語コードを公開します。ストリーミング STT は proto レベルで `SttProcess` を扱うことで実装できます。例は `AstraPlugins/examples/` にあります。

Proto RPC：`SttGetLanguages`、`SttProcess`（双方向ストリーミング）。

## `ai_provider`

代替の AI 補完バックエンドを登録します。ユーザーは AI 設定でプラグインを選択でき、デーモンはチャットの補完をそこへルーティングします。

マニフェスト：

```toml
[capabilities]
ai_provider = true
```

### Rust

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);
```

ストリーミングの `AiComplete` は proto レベルで実装します。

### Python / TypeScript

```python
async def ai_get_models(self) -> tuple[list[dict], str]:
    return ([{"id": "m1", "name": "Model 1"}], "m1")
```

Proto RPC：`AiGetModels`、`AiComplete`（サーバーストリーミング）。

## `actions`

Command Graph エディター用のカスタムアクション型を提供します。ユーザーはアクションをワークフローにドラッグし、あなたが宣言したフィールドフォームから設定します。

マニフェスト：

```toml
[capabilities]
actions = true
```

### Rust

```rust
async fn action_types(&self) -> Vec<ActionTypeDef>;
async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult;
```

### Python

```python
@action("Roll dice", fields=[Field.number("sides", "Sides", default="6")])
async def roll_dice(self, sides: int):
    return {"success": True, "result": str(roll(sides))}
```

### TypeScript

```typescript
async getActionTypes(): Promise<ActionTypeDef[]>;
async executeAction(actionType: string, paramsJson: string): Promise<ActionResult>;
```

`aiAvailable` を設定すると、アクションは AI から呼び出し可能なツールにもなります。単一の定義が Command Graph UI と AI の両方を動かします。

Proto RPC：`GetPluginActionTypes`、`ExecuteAction`。

## `triggers`

カスタムトリガー型を提供します。ユーザーは Command Graph でコマンドをトリガーに紐付けます。プラグインは `HostClient::fire_trigger` でイベントを発火し、デーモンはそれらを一致するコマンドへルーティングします。

マニフェスト：

```toml
[capabilities]
triggers = true
```

### Rust

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;

// 自分のコードから発火：
host.fire_trigger("on_alarm", r#"{"time":"09:00"}"#).await?;
```

### Python

```python
@trigger("Scheduled time", fields=[Field.text("time", "Time", default="09:00")])
def on_time(self):
    pass

await self.fire_trigger("on_time", {"time": "09:00"})
```

### TypeScript

```typescript
async getTriggerTypes(): Promise<TriggerTypeDef[]>;
await this.host!.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
```

リッスンしているコマンドがない場合の発火をスキップするには `active_triggers` / `activeTriggers` を使用します。

Proto RPC：`GetPluginTriggerTypes`（プラグイン側）、`FireTrigger`（デーモン側、HostClient 経由）。

## `client`

プラグインにデーモン API へのフルアクセスを付与します。デーモンは登録時にセッショントークンを発行し、SDK はユーザーの代わりに任意のデーモンサービスを呼び出せる `DaemonClient` を渡してくれます。

マニフェスト：

```toml
[capabilities]
client = true
```

### Rust

```rust
fn is_client(&self) -> bool { true }

async fn set_daemon_client(
    &self,
    client: Arc<Mutex<DaemonClient>>,
) {
    // 後で使うために `client` を保存
}
```

### Python

```python
def is_client(self) -> bool:
    return True

async def on_daemon_client_ready(self, client):
    self.daemon = client
    state = await client.get_state()
```

### TypeScript

```typescript
isClient(): boolean { return true; }

async onDaemonClientReady(client: DaemonClient): Promise<void> {
  this.daemon = client;
}
```

利用可能なデーモンサービス：

- `CoreService` ── 状態、起動/停止、イベント購読。
- `ChatService` ── メッセージ送信、応答ストリーミング、会話管理。
- `VoiceService` ── 発話、聴取、音声一覧。
- `CommandService` ── コマンドの実行、キャンセル、一覧。
- `ConfigService` ── 設定の読み書き。
- `MediaService` ── 再生制御。
- `MonitorService` ── CPU/RAM/GPU 統計、プラグイン一覧、プラグインログ。

## `ui_contributions`

カスタム UI を注入します ── フルページタブ、フローティングオーバーレイ、背景エフェクト、DOM 注入など。

マニフェスト：

```toml
[capabilities]
ui_contributions = true
```

### Rust / Python / TypeScript

```rust
UiContribution::page("stats", "Stats", "http://localhost:8123/stats.html");
UiContribution::overlay("clock", "http://localhost:8123/clock.html").with_size(200, 80);
UiContribution::effect("http://localhost:8123/snow.html").no_pointer_events();
UiContribution::inject(".sidebar", "after", "http://localhost:8123/widget.html");
```

プラグインはローカル HTTP サーバー（任意のポート）を実行し、自分のページを指す URL を返します。Astra UI はそれらをサンドボックス化された iframe 内でレンダリングします。プラグインへの逆方向通信は `handle_ui_call` フックで行います。

Proto RPC：`GetUiContributions`、`CallFromUi`、`PushToUi`（サーバー → UI プッシュ）。

## `event_handlers`

デーモンのイベントストリームを購読します ── チャットメッセージ、コマンドのライフサイクル、状態変化など。

マニフェスト：

```toml
[capabilities]
event_handlers = true
```

### Rust

```rust
fn subscribed_events(&self) -> Vec<String> {
    vec!["chat_message_sync".into(), "command_completed".into()]
}

async fn on_chat_sync(&self, event: ChatSyncEvent) { /* 型付き */ }
async fn on_event(&self, event_type: &str, payload_json: &str) { /* 生のフォールバック */ }
```

### Python

```python
def subscribed_events(self) -> list[str]:
    return ["chat_message_sync", "command_completed"]

async def on_chat_sync(self, event):
    ...
```

### TypeScript

```typescript
subscribedEvents(): string[] { return ["chat_message_sync"]; }
async onChatSync(event: ChatSyncEvent): Promise<void> { ... }
```

型付きハンドラは生の `on_event` フォールバックと並んで存在します ── SDK が既知のイベントを代わりにデシリアライズしてくれます。`source_id()` を使うと、自分のプラグインが生成したイベントをデーモンがエコーバックしないように指示できます。

Proto RPC：`SubscribeEvents`（サーバーストリーミング）、HostClient 経由。

## どの機能を宣言するか

1. **実装したものだけを宣言する** ── デーモンは機能ごとにリソースを割り当てます。
2. **小さく始める** ── `tools = true` だけでプラグインを出荷し、必要に応じて機能を追加します。
3. **`client = true` はコストが高い** ── プラグインにユーザーセッション全体へのアクセスを与えます。別プラットフォーム上のチャット UI など、ファーストパーティ機能を実際に置き換える場合にのみ使用してください。
