# 能力参考

Astra 插件实现下面九个能力中的一个或多个。本页对每个能力展示其用途、在各 SDK 中的 API 面、涉及的 proto RPC 以及最小化的清单条目。

## `tools`

暴露可被 AI 调用的工具。聊天模型会看到工具的名称、描述以及参数的 JSON Schema，并可以在一次对话轮次中调用它们。

清单：

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

Proto RPC（插件侧）：`ListTools`、`CallTool`。

## `tts`

文本转语音的声音提供者。注册的声音会出现在守护进程的 TTS 声音选择器中。

清单：

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

Proto RPC：`TtsListVoices`、`TtsSynthesize`、`TtsSynthesizeStream`（可选，用于流式）。

## `stt`

语音转文字的语言提供者。守护进程向插件流式发送音频，并期望接收转写事件流。

清单：

```toml
[capabilities]
stt = true
```

### Rust / Python / TypeScript

重写 `stt_languages` / `sttGetLanguages` 来发布支持的语言代码。通过在 proto 层处理 `SttProcess` 来实现流式 STT —— 示例位于 `AstraPlugins/examples/`。

Proto RPC：`SttGetLanguages`、`SttProcess`（双向流式）。

## `ai_provider`

注册一个替代的 AI 补全后端。用户可以在 AI 设置中选择该插件，守护进程会将聊天补全路由到它。

清单：

```toml
[capabilities]
ai_provider = true
```

### Rust

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);
```

流式的 `AiComplete` 在 proto 层实现。

### Python / TypeScript

```python
async def ai_get_models(self) -> tuple[list[dict], str]:
    return ([{"id": "m1", "name": "Model 1"}], "m1")
```

Proto RPC：`AiGetModels`、`AiComplete`（服务端流式）。

## `actions`

为 Command Graph 编辑器提供自定义的操作类型。用户将您的操作拖入工作流，并通过您声明的字段表单来配置它们。

清单：

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

当设置了 `aiAvailable` 时，该操作也会成为 AI 可调用的工具 —— 一个定义同时驱动 Command Graph UI 和 AI。

Proto RPC：`GetPluginActionTypes`、`ExecuteAction`。

## `triggers`

提供自定义的触发器类型。用户在 Command Graph 中把命令挂到触发器上；插件通过 `HostClient::fire_trigger` 触发事件，守护进程会把它们路由到匹配的命令。

清单：

```toml
[capabilities]
triggers = true
```

### Rust

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;

// 从您自己的代码触发：
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

当没有命令监听时，使用 `active_triggers` / `activeTriggers` 来跳过触发。

Proto RPC：`GetPluginTriggerTypes`（插件侧）、`FireTrigger`（守护进程侧，通过 HostClient）。

## `client`

赋予插件对守护进程 API 的完全访问权限。守护进程在注册期间签发一个会话令牌；SDK 会交给您一个 `DaemonClient`，它可以代表用户调用任何守护进程服务。

清单：

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
    // 保存 `client` 以供后续使用
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

可用的守护进程服务：

- `CoreService` —— 状态、启动/停止、事件订阅。
- `ChatService` —— 发送消息、流式获取响应、管理会话。
- `VoiceService` —— 说话、聆听、列出声音。
- `CommandService` —— 执行、取消、列出命令。
- `ConfigService` —— 读写设置。
- `MediaService` —— 播放控制。
- `MonitorService` —— CPU/RAM/GPU 统计、插件列表、插件日志。

## `ui_contributions`

注入自定义 UI —— 整页标签、浮动覆盖层、背景特效或 DOM 注入。

清单：

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

您的插件运行一个本地 HTTP 服务器（任何端口），并返回指向其页面的 URL。Astra UI 将它们渲染在沙箱 iframe 中。通过 `handle_ui_call` 钩子回调到插件。

Proto RPC：`GetUiContributions`、`CallFromUi`、`PushToUi`（服务器 → UI 推送）。

## `event_handlers`

订阅守护进程的事件流 —— 聊天消息、命令生命周期、状态变化等等。

清单：

```toml
[capabilities]
event_handlers = true
```

### Rust

```rust
fn subscribed_events(&self) -> Vec<String> {
    vec!["chat_message_sync".into(), "command_completed".into()]
}

async fn on_chat_sync(&self, event: ChatSyncEvent) { /* 类型化 */ }
async fn on_event(&self, event_type: &str, payload_json: &str) { /* 原始回退 */ }
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

类型化的处理器与原始 `on_event` 回退并存 —— SDK 会为您反序列化已知事件。使用 `source_id()` 告诉守护进程不要把您插件自己产生的事件回发给您。

Proto RPC：`SubscribeEvents`（服务端流式），通过 HostClient。

## 如何选择要声明的能力

1. **只声明您实现的能力** —— 守护进程按能力分配资源。
2. **从小处开始** —— 仅带 `tools = true` 发布插件，按需添加更多能力。
3. **`client = true` 代价很高** —— 它授予插件对整个用户会话的访问权限。仅在插件确实替代一项第一方功能（比如另一平台上的聊天界面）时才使用它。
