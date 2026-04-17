# Справочник возможностей

Плагины Astra реализуют одну или несколько из девяти возможностей ниже. Для каждой на этой странице показаны: назначение, API в каждом SDK, задействованные proto RPC и минимальная запись в манифесте.

## `tools`

Предоставлять инструменты, вызываемые ИИ. Модель чата видит имя инструмента, описание и JSON Schema для аргументов и может вызвать его в рамках хода.

Манифест:

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

Proto RPC (со стороны плагина): `ListTools`, `CallTool`.

## `tts`

Провайдер голосов для преобразования текста в речь. Зарегистрированные голоса появляются в выборе голосов TTS демона.

Манифест:

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

Proto RPC: `TtsListVoices`, `TtsSynthesize`, `TtsSynthesizeStream` (опционально, для стриминга).

## `stt`

Провайдер языков для преобразования речи в текст. Демон передаёт аудио в плагин потоком и ожидает поток событий транскрипции.

Манифест:

```toml
[capabilities]
stt = true
```

### Rust / Python / TypeScript

Переопределите `stt_languages` / `sttGetLanguages`, чтобы опубликовать поддерживаемые коды языков. Реализуйте потоковый STT, обрабатывая `SttProcess` на уровне proto — примеры находятся в `AstraPlugins/examples/`.

Proto RPC: `SttGetLanguages`, `SttProcess` (двунаправленный стриминг).

## `ai_provider`

Зарегистрировать альтернативный бэкенд для ИИ-завершений. Пользователи могут выбрать плагин в настройках ИИ, и демон будет маршрутизировать завершения чата к нему.

Манифест:

```toml
[capabilities]
ai_provider = true
```

### Rust

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);
```

Потоковый `AiComplete` реализуется на уровне proto.

### Python / TypeScript

```python
async def ai_get_models(self) -> tuple[list[dict], str]:
    return ([{"id": "m1", "name": "Model 1"}], "m1")
```

Proto RPC: `AiGetModels`, `AiComplete` (серверный стриминг).

## `actions`

Предоставить пользовательские типы действий для редактора Графа команд. Пользователи перетаскивают ваши действия в рабочие процессы и настраивают их через формы полей, которые вы объявляете.

Манифест:

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

Когда установлен `aiAvailable`, действие также становится вызываемым инструментом для ИИ — единое определение обслуживает и UI Графа команд, и ИИ.

Proto RPC: `GetPluginActionTypes`, `ExecuteAction`.

## `triggers`

Предоставить пользовательские типы триггеров. Пользователи привязывают команды к триггерам в Графе команд; плагин запускает события через `HostClient::fire_trigger`, а демон маршрутизирует их к соответствующим командам.

Манифест:

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

Используйте `active_triggers` / `activeTriggers`, чтобы не запускать триггеры, когда ни одна команда их не слушает.

Proto RPC: `GetPluginTriggerTypes` (сторона плагина), `FireTrigger` (сторона демона через HostClient).

## `client`

Дать плагину полный доступ к API демона. Демон выдаёт токен сессии при регистрации; SDK передаёт вам `DaemonClient`, который может вызывать любой сервис демона от имени пользователя.

Манифест:

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

Доступные сервисы демона:

- `CoreService` — состояние, старт/стоп, подписка на события.
- `ChatService` — отправка сообщений, потоковые ответы, управление диалогами.
- `VoiceService` — говорить, слушать, получать список голосов.
- `CommandService` — выполнение, отмена, список команд.
- `ConfigService` — чтение/запись настроек.
- `MediaService` — управление воспроизведением.
- `MonitorService` — статистика CPU/RAM/GPU, список плагинов, логи плагинов.

## `ui_contributions`

Внедрить пользовательский UI — полностраничные вкладки, плавающие оверлеи, фоновые эффекты или внедрение в DOM.

Манифест:

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

Ваш плагин поднимает локальный HTTP-сервер (на любом порту) и возвращает URL, указывающие на его страницы. UI Astra отрисовывает их внутри изолированных iframe. Обратная коммуникация к плагину осуществляется через хук `handle_ui_call`.

Proto RPC: `GetUiContributions`, `CallFromUi`, `PushToUi` (push с сервера в UI).

## `event_handlers`

Подписаться на поток событий демона — сообщения чата, жизненный цикл команд, изменения состояния и многое другое.

Манифест:

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

Типизированные обработчики соседствуют с сырым откатом `on_event` — SDK десериализует для вас хорошо известные события. Используйте `source_id()`, чтобы сообщить демону не отсылать обратно события, которые произвёл ваш собственный плагин.

Proto RPC: `SubscribeEvents` (серверный стриминг) через HostClient.

## Как выбрать, какие возможности объявлять

1. **Объявляйте только то, что вы реализуете** — демон выделяет ресурсы на каждую возможность.
2. **Начинайте с малого** — выпустите плагин только с `tools = true`, добавляйте остальное по мере необходимости.
3. **`client = true` — дорогое удовольствие** — это даёт плагину доступ ко всей пользовательской сессии. Используйте только когда плагин действительно заменяет встроенную функциональность (например, интерфейс чата на другой платформе).
