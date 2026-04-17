# Referencia de capacidades

Los plugins de Astra implementan una o más de las nueve capacidades siguientes. Para cada una, esta página muestra el propósito, la superficie de la API en cada SDK, los RPCs de proto involucrados y la entrada mínima del manifiesto.

## `tools`

Expone herramientas invocables por la IA. El modelo de chat ve el nombre de la herramienta, la descripción y el JSON Schema de los argumentos, y puede invocarlas durante un turno.

Manifiesto:

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

RPCs de proto (lado del plugin): `ListTools`, `CallTool`.

## `tts`

Proveedor de voces de texto a voz. Las voces registradas aparecen en el selector de voces TTS del daemon.

Manifiesto:

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

RPCs de proto: `TtsListVoices`, `TtsSynthesize`, `TtsSynthesizeStream` (opcional, para streaming).

## `stt`

Proveedor de idiomas de voz a texto. El daemon transmite audio hacia el plugin y espera un stream de eventos de transcripción.

Manifiesto:

```toml
[capabilities]
stt = true
```

### Rust / Python / TypeScript

Sobrescriba `stt_languages` / `sttGetLanguages` para publicar los códigos de idioma soportados. Implemente STT con streaming manejando `SttProcess` a nivel de proto — los ejemplos están en `AstraPlugins/examples/`.

RPCs de proto: `SttGetLanguages`, `SttProcess` (streaming bidireccional).

## `ai_provider`

Registre un backend alternativo de completions de IA. Los usuarios pueden elegir el plugin en los ajustes de IA, y el daemon enrutará las completions de chat hacia él.

Manifiesto:

```toml
[capabilities]
ai_provider = true
```

### Rust

```rust
async fn ai_models(&self) -> (Vec<AiModelInfo>, String);
```

El `AiComplete` con streaming se implementa a nivel de proto.

### Python / TypeScript

```python
async def ai_get_models(self) -> tuple[list[dict], str]:
    return ([{"id": "m1", "name": "Model 1"}], "m1")
```

RPCs de proto: `AiGetModels`, `AiComplete` (streaming del servidor).

## `actions`

Provee tipos de acción personalizados para el editor del Command Graph. Los usuarios arrastran sus acciones a los workflows y las configuran mediante los formularios de campos que usted declare.

Manifiesto:

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

Cuando `aiAvailable` está activado, la acción también se convierte en una herramienta invocable por la IA — una sola definición alimenta tanto la UI del Command Graph como la IA.

RPCs de proto: `GetPluginActionTypes`, `ExecuteAction`.

## `triggers`

Provee tipos de disparadores personalizados. Los usuarios adjuntan comandos a disparadores en el Command Graph; el plugin dispara eventos a través de `HostClient::fire_trigger` y el daemon los enruta a los comandos correspondientes.

Manifiesto:

```toml
[capabilities]
triggers = true
```

### Rust

```rust
async fn trigger_types(&self) -> Vec<TriggerTypeDef>;

// Disparar desde su propio código:
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

Use `active_triggers` / `activeTriggers` para omitir disparos cuando no hay ningún comando escuchando.

RPCs de proto: `GetPluginTriggerTypes` (lado del plugin), `FireTrigger` (lado del daemon vía HostClient).

## `client`

Otorga al plugin acceso completo a la API del daemon. El daemon emite un token de sesión durante el registro; el SDK le entrega un `DaemonClient` que puede llamar a cualquier servicio del daemon en nombre del usuario.

Manifiesto:

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
    // guardar `client` para uso posterior
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

Servicios del daemon disponibles:

- `CoreService` — estado, iniciar/detener, suscripción a eventos.
- `ChatService` — enviar mensajes, transmitir respuestas, gestionar conversaciones.
- `VoiceService` — hablar, escuchar, listar voces.
- `CommandService` — ejecutar, cancelar, listar comandos.
- `ConfigService` — leer/escribir ajustes.
- `MediaService` — control de reproducción.
- `MonitorService` — estadísticas de CPU/RAM/GPU, lista de plugins, logs de plugins.

## `ui_contributions`

Inyecta UI personalizada — pestañas de página completa, overlays flotantes, efectos de fondo o inyecciones DOM.

Manifiesto:

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

Su plugin ejecuta un servidor HTTP local (cualquier puerto) y devuelve URLs que apuntan a sus páginas. La UI de Astra las renderiza dentro de iframes sandbox. Comuníquese de vuelta al plugin a través del hook `handle_ui_call`.

RPCs de proto: `GetUiContributions`, `CallFromUi`, `PushToUi` (push del servidor a la UI).

## `event_handlers`

Suscríbase al stream de eventos del daemon — mensajes de chat, ciclo de vida de comandos, cambios de estado y más.

Manifiesto:

```toml
[capabilities]
event_handlers = true
```

### Rust

```rust
fn subscribed_events(&self) -> Vec<String> {
    vec!["chat_message_sync".into(), "command_completed".into()]
}

async fn on_chat_sync(&self, event: ChatSyncEvent) { /* tipado */ }
async fn on_event(&self, event_type: &str, payload_json: &str) { /* fallback crudo */ }
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

Los manejadores tipados conviven con el fallback crudo `on_event` — el SDK deserializa los eventos conocidos por usted. Use `source_id()` para indicar al daemon que no le reenvíe eventos producidos por su propio plugin.

RPCs de proto: `SubscribeEvents` (streaming del servidor) vía HostClient.

## Cómo elegir las capacidades a declarar

1. **Declare solo lo que implementa** — el daemon reserva recursos por capacidad.
2. **Empiece pequeño** — publique un plugin solo con `tools = true`, y añada más según las necesite.
3. **`client = true` es caro** — otorga al plugin acceso a toda la sesión del usuario. Úselo solo cuando el plugin realmente reemplace una funcionalidad de primera parte (como una interfaz de chat en otra plataforma).
