# TypeScript SDK

TypeScript SDK 采用**基于类**的 API：继承 `Plugin` 基类，并重写与你实现的能力相匹配的 async 方法。SDK 会探测你重写了哪些方法（即返回非空值的方法），从而在注册时自动声明能力。

Package：`@astra/plugin-sdk`，位于 `AstraPlugins/astra-plugin-sdk-ts`。
权威源：`astra-plugin-sdk-ts/src/plugin.ts` 和 `astra-plugin-sdk-ts/src/types.ts`。

## 运行时

**Node.js 20+** 为受支持的运行时。守护进程使用 `command = "node"` 和 `args = ["dist/index.js"]` 启动插件。Bun 在开发中或许可用，但未经测试 —— 构建默认使用 `tsc` 与 `esbuild`。

## 安装

```bash
cd my-plugin
npm install @astra/plugin-sdk @grpc/grpc-js @grpc/proto-loader
npm install --save-dev typescript @types/node
```

`package.json`：

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

## 最小插件示例

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

`.run()` 解析 CLI 参数（`--daemon-addr`、`--plugin-id`、`--auth-token`），在 `127.0.0.1:0` 上绑定 gRPC 服务器，向守护进程注册，自动发现能力并分发传入的 RPC。

## 能力自动发现

启动时，SDK 会调用每个能力方法并检查其是否返回有意义的数据，以此探测你重写了哪些方法（`plugin.ts:290-302`）：

- `listTools()` 返回非空数组 → `tools`
- `ttsListVoices()` 返回非空数组 → `tts`
- `sttGetLanguages()` 返回非空数组 → `stt`
- `aiGetModels()` 返回模型 → `ai_provider`
- `getActionTypes()` 返回类型 → `actions`
- `getTriggerTypes()` 返回类型 → `triggers`
- `getUiContributions()` 返回 contributions → `ui_contributions`
- `isClient()` 返回 `true` → `client`

你仍应在 `plugin.toml` 的 `[capabilities]` 中声明相同的能力 —— 守护进程据此分配资源并进行运行时检查。

## 可重写方法

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

### Actions 与 triggers

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

### 生命周期

```typescript
async onDaemonClientReady(client: DaemonClient): Promise<void>;
async onConfigChanged(config: Record<string, unknown>): Promise<void>;
async onLanguageChanged(language: string): Promise<void>;
async onActiveTriggers(activeTypes: string[]): Promise<void>;
async onShutdown(): Promise<void>;
async healthCheck(): Promise<{ healthy: boolean; status: string }>;
```

### 事件

```typescript
subscribedEvents(): string[];
sourceId(): string;

async onChatSync(event: ChatSyncEvent): Promise<void>;
async onStateChanged(event: StateChangedEvent): Promise<void>;
async onCommandTriggered(event: CommandTriggeredEvent): Promise<void>;
async onCommandCompleted(event: CommandCompletedEvent): Promise<void>;

async onEvent(eventType: string, payload: unknown): Promise<void>;
```

### Client 模式

```typescript
isClient(): boolean;  // override to return true
```

当其返回 true 时，SDK 会构造一个 `DaemonClient` 并将其传给 `onDaemonClientReady`。`DaemonClient` 暴露 `CoreService`、`ChatService`、`VoiceService`、`CommandService`、`ConfigService`、`MediaService` 和 `MonitorService`。

## `Field` 构建器

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

## `UiContrib` 构建器

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

## 触发触发器

```typescript
async onTick() {
  if (this.activeTriggers.has("on_alarm")) {
    await this.host!.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
  }
}
```

`activeTriggers` 由 SDK 在守护进程调用 `OnActiveTriggers` 时保持为最新。

## 构建

```bash
npm run build
```

对于生产环境包，使用 `esbuild`：

```bash
npx esbuild src/index.ts \
  --bundle \
  --platform=node \
  --target=node20 \
  --outfile=dist/index.js
```

`astra-plugin build` 在检测到 TypeScript 时会自动调用上述构建。

## 完整示例 —— json-tools

请参阅 `AstraPlugins/examples/json-tools`。要点：

- Tools：`format_json`、`query_json`、`diff_json`。
- 使用 `Field.textareaWithVariables` 作为模板输入的 Actions。
- Trigger：`on_parse_error`，由后台校验器触发。

清单：

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

## 下一步

- [能力](capabilities.md) —— 每种能力的完整行为。
- [清单](manifest.md) —— 每个 `plugin.toml` 字段。
- [发布](publishing.md) —— 构建、签名、分发。
