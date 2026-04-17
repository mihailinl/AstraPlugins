# Referenz zu den Fähigkeiten

Astra-Plugins implementieren eine oder mehrere der neun unten aufgeführten Fähigkeiten. Diese Seite zeigt für jede Fähigkeit den Zweck, die API-Oberfläche in allen SDKs, die beteiligten Proto-RPCs und den minimalen Manifest-Eintrag.

## `tools`

Stellen Sie KI-aufrufbare Werkzeuge bereit. Das Chat-Modell sieht Name, Beschreibung und JSON-Schema für die Argumente und kann sie während eines Turns aufrufen.

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

Proto-RPCs (Plugin-Seite): `ListTools`, `CallTool`.

## `tts`

Text-zu-Sprache-Stimmenanbieter. Registrierte Stimmen erscheinen in der TTS-Stimmenauswahl des Daemons.

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

Proto-RPCs: `TtsListVoices`, `TtsSynthesize`, `TtsSynthesizeStream` (optional, für Streaming).

## `stt`

Sprach-zu-Text-Sprachanbieter. Der Daemon streamt Audio in das Plugin und erwartet einen Stream von Transkript-Events.

Manifest:

```toml
[capabilities]
stt = true
```

### Rust / Python / TypeScript

Überschreiben Sie `stt_languages` / `sttGetLanguages`, um unterstützte Sprachcodes zu veröffentlichen. Implementieren Sie Streaming-STT, indem Sie `SttProcess` auf Proto-Ebene behandeln — Beispiele befinden sich in `AstraPlugins/examples/`.

Proto-RPCs: `SttGetLanguages`, `SttProcess` (bidirektionales Streaming).

## `ai_provider`

Registrieren Sie ein alternatives KI-Completion-Backend. Nutzer können das Plugin in den KI-Einstellungen auswählen, und der Daemon leitet Chat-Completions dorthin weiter.

Manifest:

```toml
[capabilities]
ai_provider = true
```

### Rust

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);
```

`AiComplete` mit Streaming wird auf Proto-Ebene implementiert.

### Python / TypeScript

```python
async def ai_get_models(self) -> tuple[list[dict], str]:
    return ([{"id": "m1", "name": "Model 1"}], "m1")
```

Proto-RPCs: `AiGetModels`, `AiComplete` (Server-Streaming).

## `actions`

Stellen Sie benutzerdefinierte Aktionstypen für den Command-Graph-Editor bereit. Nutzer ziehen Ihre Aktionen in Workflows und konfigurieren sie über die Feldformulare, die Sie deklarieren.

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

Wenn `aiAvailable` gesetzt ist, wird die Aktion auch zu einem aufrufbaren Werkzeug für die KI — eine einzige Definition treibt sowohl die Command-Graph-UI als auch die KI an.

Proto-RPCs: `GetPluginActionTypes`, `ExecuteAction`.

## `triggers`

Stellen Sie benutzerdefinierte Trigger-Typen bereit. Nutzer hängen Commands an Trigger im Command Graph an; das Plugin feuert Events über `HostClient::fire_trigger`, und der Daemon leitet sie an passende Commands weiter.

Manifest:

```toml
[capabilities]
triggers = true
```

### Rust

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;

// Aus dem eigenen Code feuern:
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

Verwenden Sie `active_triggers` / `activeTriggers`, um das Feuern zu überspringen, wenn kein Command zuhört.

Proto-RPCs: `GetPluginTriggerTypes` (Plugin-Seite), `FireTrigger` (Daemon-Seite über HostClient).

## `client`

Geben Sie dem Plugin vollen Zugriff auf die Daemon-API. Der Daemon stellt während der Registrierung ein Session-Token aus; das SDK übergibt Ihnen einen `DaemonClient`, der jeden Daemon-Dienst im Namen des Nutzers aufrufen kann.

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
    // `client` für spätere Verwendung speichern
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

Verfügbare Daemon-Dienste:

- `CoreService` — Zustand, Start/Stop, Event-Abonnement.
- `ChatService` — Nachrichten senden, Antworten streamen, Unterhaltungen verwalten.
- `VoiceService` — sprechen, zuhören, Stimmen auflisten.
- `CommandService` — Commands ausführen, abbrechen, auflisten.
- `ConfigService` — Einstellungen lesen/schreiben.
- `MediaService` — Wiedergabesteuerung.
- `MonitorService` — CPU/RAM/GPU-Statistiken, Plugin-Liste, Plugin-Logs.

## `ui_contributions`

Injizieren Sie benutzerdefinierte UI — Vollseiten-Tabs, schwebende Overlays, Hintergrundeffekte oder DOM-Injektionen.

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

Ihr Plugin betreibt einen lokalen HTTP-Server (beliebiger Port) und gibt URLs zurück, die auf seine Seiten zeigen. Die Astra-UI rendert sie in Sandbox-iframes. Kommunizieren Sie über den Hook `handle_ui_call` zurück zum Plugin.

Proto-RPCs: `GetUiContributions`, `CallFromUi`, `PushToUi` (Server→UI-Push).

## `event_handlers`

Abonnieren Sie den Event-Stream des Daemons — Chat-Nachrichten, Command-Lebenszyklus, Zustandsänderungen und mehr.

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

async fn on_chat_sync(&self, event: ChatSyncEvent) { /* typisiert */ }
async fn on_event(&self, event_type: &str, payload_json: &str) { /* Roh-Fallback */ }
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

Typisierte Handler leben neben dem Roh-Fallback `on_event` — das SDK deserialisiert bekannte Events für Sie. Verwenden Sie `source_id()`, um dem Daemon mitzuteilen, dass er Events, die Ihr eigenes Plugin produziert hat, nicht zurücksenden soll.

Proto-RPCs: `SubscribeEvents` (Server-Streaming) über HostClient.

## Welche Fähigkeiten deklarieren?

1. **Deklarieren Sie nur, was Sie implementieren** — der Daemon reserviert Ressourcen pro Fähigkeit.
2. **Klein anfangen** — liefern Sie ein Plugin nur mit `tools = true` und erweitern Sie es bei Bedarf.
3. **`client = true` ist teuer** — es gewährt dem Plugin Zugriff auf die gesamte Nutzer-Session. Verwenden Sie es nur, wenn das Plugin tatsächlich eine First-Party-Funktion ersetzt (z. B. eine Chat-Oberfläche auf einer anderen Plattform).
