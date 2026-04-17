# SDK de TypeScript

El SDK de TypeScript es una API **basada en clases**: extienda la clase base `Plugin` y sobrescriba los métodos asíncronos correspondientes a las capacidades que implemente. El SDK analiza qué métodos ha sobrescrito (es decir, cuáles devuelven valores no vacíos) para autodeclarar las capacidades durante el registro.

Paquete: `@astra/plugin-sdk` en `AstraPlugins/astra-plugin-sdk-ts`.
Fuente de verdad: `astra-plugin-sdk-ts/src/plugin.ts` y `astra-plugin-sdk-ts/src/types.ts`.

## Runtime

**Node.js 20+** es el runtime soportado. El daemon lanza los plugins con `command = "node"` y `args = ["dist/index.js"]`. Bun puede funcionar para desarrollo pero no está probado — los builds utilizan `tsc` y `esbuild` por defecto.

## Instalación

```bash
cd my-plugin
npm install @astra/plugin-sdk @grpc/grpc-js @grpc/proto-loader
npm install --save-dev typescript @types/node
```

`package.json`:

```json
{
  "name": "my-plugin",
  "version": "0.1.0",
  "main": "dist/index.js",
  "scripts": {
    "build": "tsc"
  },
  "dependencies": {
    "@astra/plugin-sdk": "^0.1.5",
    "@grpc/grpc-js": "^1.10.0",
    "@grpc/proto-loader": "^0.7.0"
  }
}
```

## Plugin mínimo

```typescript
import { Plugin, ToolDef, ToolResult } from "@astra/plugin-sdk";

class MyPlugin extends Plugin {
  async listTools(): Promise<ToolDef[]> {
    return [{
      name: "greet",
      description: "Return a greeting",
      parametersJson: JSON.stringify({
        type: "object",
        properties: { name: { type: "string" } },
        required: ["name"],
      }),
    }];
  }

  async callTool(name: string, argumentsJson: string): Promise<ToolResult> {
    const args = JSON.parse(argumentsJson);
    return { success: true, result: `Hello, ${args.name}!` };
  }
}

new MyPlugin().run();
```

`.run()` analiza los argumentos de línea de comandos (`--daemon-addr`, `--plugin-id`, `--auth-token`), vincula un servidor gRPC en `127.0.0.1:0`, se registra con el daemon, descubre automáticamente las capacidades y despacha los RPCs entrantes.

## Descubrimiento automático de capacidades

Al iniciar, el SDK sondea qué métodos ha sobrescrito llamando a cada método de capacidad y comprobando si devuelve datos significativos (`plugin.ts:290-302`):

- `listTools()` devuelve un array no vacío → `tools`
- `ttsListVoices()` devuelve un array no vacío → `tts`
- `sttGetLanguages()` devuelve un array no vacío → `stt`
- `aiGetModels()` devuelve modelos → `ai_provider`
- `getActionTypes()` devuelve tipos → `actions`
- `getTriggerTypes()` devuelve tipos → `triggers`
- `getUiContributions()` devuelve contribuciones → `ui_contributions`
- `isClient()` devuelve `true` → `client`

Aun así, debe declarar las mismas capacidades en `[capabilities]` dentro de `plugin.toml` — el daemon lo utiliza para asignar recursos y realizar verificaciones en tiempo de ejecución.

## Métodos sobrescribibles

### Herramientas

```typescript
async listTools(): Promise<ToolDef[]>;
async callTool(name: string, argumentsJson: string): Promise<ToolResult>;
```

### TTS / STT / IA

```typescript
async ttsListVoices(): Promise<VoiceInfo[]>;
async ttsSynthesize(text: string, voiceId: string,
                    speed: number, pitch: number): Promise<AudioData>;

async sttGetLanguages(): Promise<string[]>;

async aiGetModels(): Promise<{ models: AiModelInfo[]; default: string }>;
```

### Acciones y disparadores

```typescript
async getActionTypes(): Promise<ActionTypeDef[]>;
async executeAction(actionType: string, paramsJson: string): Promise<ActionResult>;
async getTriggerTypes(): Promise<TriggerTypeDef[]>;
```

### Contribuciones de interfaz

```typescript
async getUiContributions(): Promise<UiContribution[]>;
async handleUiCall(method: string, paramsJson: string): Promise<UiCallResult>;
```

### Ciclo de vida

```typescript
async onDaemonClientReady(client: DaemonClient): Promise<void>;
async onConfigChanged(config: Record<string, unknown>): Promise<void>;
async onLanguageChanged(language: string): Promise<void>;
async onActiveTriggers(activeTypes: string[]): Promise<void>;
async onShutdown(): Promise<void>;
async healthCheck(): Promise<{ healthy: boolean; status: string }>;
```

### Eventos

```typescript
subscribedEvents(): string[];
sourceId(): string;

async onChatSync(event: ChatSyncEvent): Promise<void>;
async onStateChanged(event: StateChangedEvent): Promise<void>;
async onCommandTriggered(event: CommandTriggeredEvent): Promise<void>;
async onCommandCompleted(event: CommandCompletedEvent): Promise<void>;

async onEvent(eventType: string, payload: unknown): Promise<void>;
```

### Modo cliente

```typescript
isClient(): boolean;  // override to return true
```

Cuando es `true`, el SDK construye un `DaemonClient` y lo pasa a `onDaemonClientReady`. `DaemonClient` expone `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService` y `MonitorService`.

## Builders `Field`

```typescript
import { Field } from "@astra/plugin-sdk";

const fields = [
  Field.text("name", "Name", { placeholder: "Ada", description: "Display name" }),
  Field.textarea("body", "Body"),
  Field.textareaWithVariables("template", "Template"),
  Field.dropdown("mode", "Mode", {
    options: [
      { value: "fast", label: "Fast" },
      { value: "slow", label: "Slow" },
    ],
    default: "fast",
  }),
  Field.number("count", "Count", { min: 1, max: 100, step: 1 }),
  Field.toggle("verbose", "Verbose", { default: false }),
  Field.condition("mode", "equals", "custom"),  // visibility rule
];
```

## Builders `UiContrib`

```typescript
import { UiContrib } from "@astra/plugin-sdk";

const contributions = [
  UiContrib.page("stats", "Stats", "http://localhost:8123/stats.html", {
    iconSvg: "<svg>…</svg>",
  }),
  UiContrib.effect("http://localhost:8123/snow.html"),
  UiContrib.overlay("clock", "http://localhost:8123/clock.html", {
    width: 200,
    height: 80,
    transparent: true,
  }),
  UiContrib.inject("#sidebar", "after", "http://localhost:8123/widget.html"),
];
```

## `HostClient`

```typescript
await this.host.log("info", "Starting up");
await this.host.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
await this.host.setVariable("last_value", "42");
await this.host.pushToUi("stats", JSON.stringify({ counter: 42 }));
const info = await this.host.getDaemonInfo();
const config = await this.host.getConfig();
```

## Disparar disparadores

```typescript
async onTick() {
  if (this.activeTriggers.has("on_alarm")) {
    await this.host!.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
  }
}
```

El SDK mantiene `activeTriggers` actualizado cuando el daemon invoca `OnActiveTriggers`.

## Compilación

```bash
npm run build
```

Para builds de producción utilice `esbuild`:

```bash
npx esbuild src/index.ts \
  --bundle \
  --platform=node \
  --target=node20 \
  --outfile=dist/index.js
```

`astra-plugin build` lo llamará automáticamente cuando detecte TypeScript.

## Ejemplo práctico — json-tools

Consulte `AstraPlugins/examples/json-tools`. Aspectos destacados:

- Herramientas: `format_json`, `query_json`, `diff_json`.
- Acciones con `Field.textareaWithVariables` para entradas de plantilla.
- Disparador: `on_parse_error` disparado desde un validador en segundo plano.

Manifiesto:

```toml
[plugin]
id = "json-tools"
name = "JSON Tools"
version = "0.1.1"

[entry]
command = "node"
args = ["dist/index.js"]
runtimes = ["node"]

[capabilities]
tools = true
actions = true
triggers = true
```

## Dónde continuar

- [Capacidades](capabilities.md) — comportamiento completo por capacidad.
- [Manifiesto](manifest.md) — cada campo de `plugin.toml`.
- [Publicación](publishing.md) — construir, firmar, distribuir.
