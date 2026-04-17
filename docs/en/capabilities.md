# Capabilities reference

Astra plugins implement one or more of the nine capabilities below. For each, this page shows the purpose, the API surface in every SDK, the proto RPCs involved, and the minimum manifest entry.

## `tools`

Expose AI-callable tools. The chat model sees the tool name, description, and JSON Schema for arguments, and can invoke them during a turn.

Manifest:

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

Proto RPCs (plugin side): `ListTools`, `CallTool`.

## `tts`

Text-to-speech voice provider. Registered voices appear in the daemon's TTS voice picker.

Manifest:

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

Proto RPCs: `TtsListVoices`, `TtsSynthesize`, `TtsSynthesizeStream` (optional, for streaming).

## `stt`

Speech-to-text language provider. The daemon streams audio into the plugin and expects a stream of transcript events.

Manifest:

```toml
[capabilities]
stt = true
```

### Rust / Python / TypeScript

Override `stt_languages` / `sttGetLanguages` to publish supported language codes. Implement streaming STT by handling `SttProcess` at the proto level — examples live in `AstraPlugins/examples/`.

Proto RPCs: `SttGetLanguages`, `SttProcess` (bidirectional streaming).

## `ai_provider`

Register an alternative AI completion backend. Users can pick the plugin in the AI settings and the daemon will route chat completions to it.

Manifest:

```toml
[capabilities]
ai_provider = true
```

### Rust

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);
```

Streaming `AiComplete` is implemented at the proto level.

### Python / TypeScript

```python
async def ai_get_models(self) -> tuple[list[dict], str]:
    return ([{"id": "m1", "name": "Model 1"}], "m1")
```

Proto RPCs: `AiGetModels`, `AiComplete` (server streaming).

## `actions`

Provide custom action types for the Command Graph editor. Users drag your actions into workflows and configure them through field forms you declare.

Manifest:

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

When `aiAvailable` is set, the action also becomes a callable tool for the AI — a single definition powers both the Command Graph UI and the AI.

Proto RPCs: `GetPluginActionTypes`, `ExecuteAction`.

## `triggers`

Provide custom trigger types. Users attach commands to triggers in the Command Graph; the plugin fires events through `HostClient::fire_trigger` and the daemon routes them to matching commands.

Manifest:

```toml
[capabilities]
triggers = true
```

### Rust

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;

// Fire from your own code:
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

Use `active_triggers` / `activeTriggers` to skip firing when no command is listening.

Proto RPCs: `GetPluginTriggerTypes` (plugin side), `FireTrigger` (daemon side via HostClient).

## `client`

Give the plugin full daemon API access. The daemon issues a session token during registration; the SDK hands you a `DaemonClient` that can call any daemon service on behalf of the user.

Manifest:

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
    // store `client` for later use
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

Available daemon services:

- `CoreService` — state, start/stop, subscribe events.
- `ChatService` — send messages, stream responses, manage conversations.
- `VoiceService` — speak, listen, list voices.
- `CommandService` — execute, cancel, list commands.
- `ConfigService` — read/write settings.
- `MediaService` — playback control.
- `MonitorService` — CPU/RAM/GPU stats, plugin list, plugin logs.

## `ui_contributions`

Inject custom UI — full-page tabs, floating overlays, background effects, or DOM injections.

Manifest:

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

Your plugin runs a local HTTP server (any port) and returns URLs pointing at its pages. The Astra UI renders them inside sandboxed iframes. Communicate back to the plugin via the `handle_ui_call` hook.

Proto RPCs: `GetUiContributions`, `CallFromUi`, `PushToUi` (server→UI push).

## `event_handlers`

Subscribe to the daemon's event stream — chat messages, command lifecycle, state changes, and more.

Manifest:

```toml
[capabilities]
event_handlers = true
```

### Rust

```rust
fn subscribed_events(&self) -> Vec<String> {
    vec!["chat_message_sync".into(), "command_completed".into()]
}

async fn on_chat_sync(&self, event: ChatSyncEvent) { /* typed */ }
async fn on_event(&self, event_type: &str, payload_json: &str) { /* raw fallback */ }
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

Typed handlers live next to the raw `on_event` fallback — the SDK deserialises well-known events for you. Use `source_id()` to tell the daemon not to echo back events your own plugin produced.

Proto RPCs: `SubscribeEvents` (server streaming) via HostClient.

## Choosing which capabilities to declare

1. **Only declare what you implement** — the daemon allocates resources per capability.
2. **Start small** — ship a plugin with just `tools = true`, add more as you need.
3. **`client = true` is expensive** — it grants the plugin access to the entire user session. Use it only when the plugin genuinely replaces a first-party feature (like a chat interface on another platform).
