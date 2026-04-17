# TypeScript-SDK

Das TypeScript-SDK ist eine **klassenbasierte** API: Erweitern Sie die Basisklasse `Plugin` und überschreiben Sie die asynchronen Methoden, die zu den von Ihnen implementierten Fähigkeiten passen. Das SDK prüft, welche Methoden Sie überschrieben haben (d. h. nicht-leere Werte zurückgeben), und meldet die Fähigkeiten während der Registrierung automatisch an.

Paket: `@astra/plugin-sdk` unter `AstraPlugins/astra-plugin-sdk-ts`.
Maßgebliche Quelle: `astra-plugin-sdk-ts/src/plugin.ts` und `astra-plugin-sdk-ts/src/types.ts`.

## Laufzeitumgebung

**Node.js 20+** ist die unterstützte Laufzeit. Der Daemon startet Plugins mit `command = "node"` und `args = ["dist/index.js"]`. Bun funktioniert möglicherweise in der Entwicklung, ist aber nicht getestet — Builds verwenden standardmäßig `tsc` und `esbuild`.

## Installation

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

## Minimales Plugin

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

`.run()` parst die CLI-Argumente (`--daemon-addr`, `--plugin-id`, `--auth-token`), bindet einen gRPC-Server an `127.0.0.1:0`, registriert sich beim Daemon, erkennt Fähigkeiten automatisch und verteilt eingehende RPCs.

## Automatische Fähigkeitserkennung

Beim Start prüft das SDK, welche Methoden Sie überschrieben haben, indem es jede Fähigkeitsmethode aufruft und prüft, ob sie sinnvolle Daten liefert (`plugin.ts:290-302`):

- `listTools()` liefert ein nicht-leeres Array → `tools`
- `ttsListVoices()` liefert ein nicht-leeres Array → `tts`
- `sttGetLanguages()` liefert ein nicht-leeres Array → `stt`
- `aiGetModels()` liefert Modelle → `ai_provider`
- `getActionTypes()` liefert Typen → `actions`
- `getTriggerTypes()` liefert Typen → `triggers`
- `getUiContributions()` liefert Beiträge → `ui_contributions`
- `isClient()` gibt `true` zurück → `client`

Sie sollten dieselben Fähigkeiten dennoch unter `[capabilities]` in `plugin.toml` angeben — der Daemon verwendet das zur Ressourcenzuweisung und für Laufzeitprüfungen.

## Überschreibbare Methoden

### Tools

```typescript
async listTools(): Promise<ToolDef[]>;
async callTool(name: string, argumentsJson: string): Promise<ToolResult>;
```

### TTS / STT / AI

```typescript
async ttsListVoices(): Promise<VoiceInfo[]>;
async ttsSynthesize(text: string, voiceId: string,
                    speed: number, pitch: number): Promise<AudioData>;

async sttGetLanguages(): Promise<string[]>;

async aiGetModels(): Promise<{ models: AiModelInfo[]; default: string }>;
```

### Aktionen und Trigger

```typescript
async getActionTypes(): Promise<ActionTypeDef[]>;
async executeAction(actionType: string, paramsJson: string): Promise<ActionResult>;
async getTriggerTypes(): Promise<TriggerTypeDef[]>;
```

### UI-Beiträge

```typescript
async getUiContributions(): Promise<UiContribution[]>;
async handleUiCall(method: string, paramsJson: string): Promise<UiCallResult>;
```

### Lebenszyklus

```typescript
async onDaemonClientReady(client: DaemonClient): Promise<void>;
async onConfigChanged(config: Record<string, unknown>): Promise<void>;
async onLanguageChanged(language: string): Promise<void>;
async onActiveTriggers(activeTypes: string[]): Promise<void>;
async onShutdown(): Promise<void>;
async healthCheck(): Promise<{ healthy: boolean; status: string }>;
```

### Ereignisse

```typescript
subscribedEvents(): string[];
sourceId(): string;

async onChatSync(event: ChatSyncEvent): Promise<void>;
async onStateChanged(event: StateChangedEvent): Promise<void>;
async onCommandTriggered(event: CommandTriggeredEvent): Promise<void>;
async onCommandCompleted(event: CommandCompletedEvent): Promise<void>;

async onEvent(eventType: string, payload: unknown): Promise<void>;
```

### Client-Modus

```typescript
isClient(): boolean;  // override to return true
```

Bei `true` erzeugt das SDK einen `DaemonClient` und übergibt ihn an `onDaemonClientReady`. Der `DaemonClient` stellt `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService` und `MonitorService` bereit.

## `Field`-Builder

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

## `UiContrib`-Builder

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

## Trigger auslösen

```typescript
async onTick() {
  if (this.activeTriggers.has("on_alarm")) {
    await this.host!.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
  }
}
```

`activeTriggers` wird vom SDK aktuell gehalten, wenn der Daemon `OnActiveTriggers` aufruft.

## Build

```bash
npm run build
```

Für Produktionsbundles verwenden Sie `esbuild`:

```bash
npx esbuild src/index.ts \
  --bundle \
  --platform=node \
  --target=node20 \
  --outfile=dist/index.js
```

`astra-plugin build` ruft dies automatisch auf, sobald TypeScript erkannt wird.

## Ausgearbeitetes Beispiel — json-tools

Siehe `AstraPlugins/examples/json-tools`. Highlights:

- Tools: `format_json`, `query_json`, `diff_json`.
- Aktionen mit `Field.textareaWithVariables` für Template-Eingaben.
- Trigger: `on_parse_error`, ausgelöst von einem Hintergrundvalidator.

Manifest:

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

## Wie geht es weiter

- [Fähigkeiten](capabilities.md) — vollständiges Verhalten pro Fähigkeit.
- [Manifest](manifest.md) — jedes `plugin.toml`-Feld.
- [Veröffentlichung](publishing.md) — bauen, signieren, verteilen.
