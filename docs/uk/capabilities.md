# Довідник можливостей

Плагіни Astra реалізують одну або більше з дев'яти можливостей, описаних нижче. Для кожної з них на цій сторінці показано призначення, поверхню API у кожному SDK, пов'язані RPC proto та мінімальний запис у маніфесті.

## `tools`

Надає інструменти, які може викликати AI. Чат-модель бачить назву інструмента, опис та JSON Schema для аргументів і може викликати їх під час свого ходу.

Маніфест:

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

RPC proto (з боку плагіна): `ListTools`, `CallTool`.

## `tts`

Постачальник голосів для синтезу мовлення. Зареєстровані голоси з'являються у вибиралці голосів TTS демона.

Маніфест:

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

RPC proto: `TtsListVoices`, `TtsSynthesize`, `TtsSynthesizeStream` (опціонально, для стримінгу).

## `stt`

Постачальник мов для розпізнавання мовлення. Демон потоково передає аудіо до плагіна й очікує потоку подій транскрипту.

Маніфест:

```toml
[capabilities]
stt = true
```

### Rust / Python / TypeScript

Перевизначте `stt_languages` / `sttGetLanguages`, щоб публікувати коди підтримуваних мов. Реалізуйте потоковий STT, обробляючи `SttProcess` на рівні proto — приклади є в `AstraPlugins/examples/`.

RPC proto: `SttGetLanguages`, `SttProcess` (двонаправлений стримінг).

## `ai_provider`

Реєструє альтернативний бекенд AI-генерації. Користувачі можуть обрати плагін у налаштуваннях AI, і демон буде маршрутизувати чат-завершення до нього.

Маніфест:

```toml
[capabilities]
ai_provider = true
```

### Rust

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);
```

Потоковий `AiComplete` реалізується на рівні proto.

### Python / TypeScript

```python
async def ai_get_models(self) -> tuple[list[dict], str]:
    return ([{"id": "m1", "name": "Model 1"}], "m1")
```

RPC proto: `AiGetModels`, `AiComplete` (потік з боку сервера).

## `actions`

Надає власні типи дій для редактора Command Graph. Користувачі перетягують ваші дії у робочі процеси та налаштовують їх через форми полів, які ви оголошуєте.

Маніфест:

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

Коли встановлено `aiAvailable`, дія також стає інструментом, який може викликати AI — єдине визначення живить і UI Command Graph, і AI.

RPC proto: `GetPluginActionTypes`, `ExecuteAction`.

## `triggers`

Надає власні типи тригерів. Користувачі прикріплюють команди до тригерів у Command Graph; плагін активує події через `HostClient::fire_trigger`, а демон маршрутизує їх до команд, що збігаються.

Маніфест:

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

Використовуйте `active_triggers` / `activeTriggers`, щоб не активувати тригери, коли немає команди-слухача.

RPC proto: `GetPluginTriggerTypes` (з боку плагіна), `FireTrigger` (з боку демона через HostClient).

## `client`

Надає плагіну повний доступ до API демона. Демон видає токен сесії під час реєстрації; SDK передає вам `DaemonClient`, який може викликати будь-яку службу демона від імені користувача.

Маніфест:

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

Доступні служби демона:

- `CoreService` — стан, запуск/зупинка, підписка на події.
- `ChatService` — надсилання повідомлень, потокові відповіді, керування розмовами.
- `VoiceService` — говорити, слухати, перелік голосів.
- `CommandService` — виконання, скасування, перелік команд.
- `ConfigService` — читання/запис налаштувань.
- `MediaService` — керування відтворенням.
- `MonitorService` — статистика CPU/RAM/GPU, список плагінів, логи плагінів.

## `ui_contributions`

Впроваджує власний UI — повносторінкові вкладки, плаваючі оверлеї, фонові ефекти або DOM-ін'єкції.

Маніфест:

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

Ваш плагін запускає локальний HTTP-сервер (на будь-якому порту) і повертає URL, що вказують на його сторінки. UI Astra рендерить їх у ізольованих iframe. Спілкуйтеся назад з плагіном через хук `handle_ui_call`.

RPC proto: `GetUiContributions`, `CallFromUi`, `PushToUi` (push сервер→UI).

## `event_handlers`

Підписка на потік подій демона — повідомлення чату, життєвий цикл команд, зміни стану тощо.

Маніфест:

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

Типізовані обробники живуть поруч із сирим відкатом `on_event` — SDK десеріалізує відомі події за вас. Використовуйте `source_id()`, щоб сказати демону не повертати назад події, які згенерував ваш власний плагін.

RPC proto: `SubscribeEvents` (потік з боку сервера) через HostClient.

## Як обрати, які можливості оголошувати

1. **Оголошуйте лише те, що реалізуєте** — демон розподіляє ресурси на кожну можливість.
2. **Починайте з малого** — випустіть плагін лише з `tools = true`, додавайте решту за потреби.
3. **`client = true` — дорога** — вона дає плагіну доступ до всієї сесії користувача. Використовуйте її, лише коли плагін справді замінює вбудовану функцію (наприклад, інтерфейс чату на іншій платформі).
