# TypeScript SDK

The TypeScript SDK is a **class-based** API: extend the `Plugin` base class and override the async methods matching the capabilities you implement. The SDK introspects which methods you've overridden (i.e. return non-empty values) to auto-declare capabilities during registration.

Package: `@astra/plugin-sdk` at `AstraPlugins/astra-plugin-sdk-ts`.
Source of truth: `astra-plugin-sdk-ts/src/plugin.ts` and `astra-plugin-sdk-ts/src/types.ts`.

## Runtime

**Node.js 20+** is the supported runtime. The daemon launches plugins with `command = "node"` and `args = ["dist/index.js"]`. Bun may work for development but is not tested — builds default to `tsc` and `esbuild`.

## Install

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

## Minimal plugin

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

`.run()` parses CLI args (`--daemon-addr`, `--plugin-id`, `--auth-token`), binds a gRPC server on `127.0.0.1:0`, registers with the daemon, auto-discovers capabilities, and dispatches incoming RPCs.

## Capability auto-discovery

On startup the SDK probes which methods you've overridden by calling each capability method and checking whether it returns meaningful data (`plugin.ts:290-302`):

- `listTools()` returns a non-empty array → `tools`
- `ttsListVoices()` returns a non-empty array → `tts`
- `sttGetLanguages()` returns a non-empty array → `stt`
- `aiGetModels()` returns models → `ai_provider`
- `getActionTypes()` returns types → `actions`
- `getTriggerTypes()` returns types → `triggers`
- `getUiContributions()` returns contributions → `ui_contributions`
- `isClient()` returns `true` → `client`

You should still declare the same capabilities in `[capabilities]` inside `plugin.toml` — the daemon uses that to allocate resources and run time checks.

## Overridable methods

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

### Actions and triggers

```typescript
async getActionTypes(): Promise<ActionTypeDef[]>;
async executeAction(actionType: string, paramsJson: string): Promise<ActionResult>;
async getTriggerTypes(): Promise<TriggerTypeDef[]>;
```

### UI contributions

```typescript
async getUiContributions(): Promise<UiContribution[]>;
async handleUiCall(method: string, paramsJson: string): Promise<UiCallResult>;
```

### Lifecycle

```typescript
async onDaemonClientReady(client: DaemonClient): Promise<void>;
async onConfigChanged(config: Record<string, unknown>): Promise<void>;
async onLanguageChanged(language: string): Promise<void>;
async onActiveTriggers(activeTypes: string[]): Promise<void>;
async onShutdown(): Promise<void>;
async healthCheck(): Promise<{ healthy: boolean; status: string }>;
```

### Events

```typescript
subscribedEvents(): string[];
sourceId(): string;

async onChatSync(event: ChatSyncEvent): Promise<void>;
async onStateChanged(event: StateChangedEvent): Promise<void>;
async onCommandTriggered(event: CommandTriggeredEvent): Promise<void>;
async onCommandCompleted(event: CommandCompletedEvent): Promise<void>;

async onEvent(eventType: string, payload: unknown): Promise<void>;
```

### Client mode

```typescript
isClient(): boolean;  // override to return true
```

When true the SDK constructs a `DaemonClient` and passes it to `onDaemonClientReady`. `DaemonClient` exposes `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService`, and `MonitorService`.

## `Field` builders

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

## `UiContrib` builders

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

## Firing triggers

```typescript
async onTick() {
  if (this.activeTriggers.has("on_alarm")) {
    await this.host!.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
  }
}
```

`activeTriggers` is kept up-to-date by the SDK when the daemon calls `OnActiveTriggers`.

## Building

```bash
npm run build
```

For production bundles use `esbuild`:

```bash
npx esbuild src/index.ts \
  --bundle \
  --platform=node \
  --target=node20 \
  --outfile=dist/index.js
```

`astra-plugin build` will call this automatically when it detects TypeScript.

## Worked example — json-tools

See `AstraPlugins/examples/json-tools`. Highlights:

- Tools: `format_json`, `query_json`, `diff_json`.
- Actions with `Field.textareaWithVariables` for template inputs.
- Trigger: `on_parse_error` fired from a background validator.

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

## Where to go next

- [Capabilities](capabilities.md) — full behaviour per capability.
- [Manifest](manifest.md) — every `plugin.toml` field.
- [Publishing](publishing.md) — build, sign, distribute.
