# TypeScript SDK

TypeScript SDK — це **API на основі класів**: успадкуйте базовий клас `Plugin` і перевизначте async-методи відповідно до можливостей, які ви реалізуєте. SDK інтроспектує, які методи ви перевизначили (тобто повертають непорожні значення), щоб автоматично оголосити можливості під час реєстрації.

Пакет: `@astra/plugin-sdk` у `AstraPlugins/astra-plugin-sdk-ts`.
Джерело істини: `astra-plugin-sdk-ts/src/plugin.ts` і `astra-plugin-sdk-ts/src/types.ts`.

## Рантайм

**Node.js 20+** — підтримуваний рантайм. Демон запускає плагіни з `command = "node"` і `args = ["dist/index.js"]`. Bun може працювати для розробки, але не тестується — збирання за замовчуванням використовує `tsc` і `esbuild`.

## Встановлення

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

## Мінімальний плагін

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

`.run()` парсить аргументи CLI (`--daemon-addr`, `--plugin-id`, `--auth-token`), піднімає gRPC-сервер на `127.0.0.1:0`, реєструється в демоні, автоматично виявляє можливості та диспатчить вхідні RPC.

## Автоматичне виявлення можливостей

Під час запуску SDK перевіряє, які методи ви перевизначили, викликаючи кожен метод можливості та дивлячись, чи повертає він змістовні дані (`plugin.ts:290-302`):

- `listTools()` повертає непорожній масив → `tools`
- `ttsListVoices()` повертає непорожній масив → `tts`
- `sttGetLanguages()` повертає непорожній масив → `stt`
- `aiGetModels()` повертає моделі → `ai_provider`
- `getActionTypes()` повертає типи → `actions`
- `getTriggerTypes()` повертає типи → `triggers`
- `getUiContributions()` повертає внески → `ui_contributions`
- `isClient()` повертає `true` → `client`

Ви все одно маєте оголосити ті самі можливості у `[capabilities]` всередині `plugin.toml` — демон використовує це для розподілу ресурсів і перевірок під час виконання.

## Методи для перевизначення

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

### Дії та тригери

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

### Життєвий цикл

```typescript
async onDaemonClientReady(client: DaemonClient): Promise<void>;
async onConfigChanged(config: Record<string, unknown>): Promise<void>;
async onLanguageChanged(language: string): Promise<void>;
async onActiveTriggers(activeTypes: string[]): Promise<void>;
async onShutdown(): Promise<void>;
async healthCheck(): Promise<{ healthy: boolean; status: string }>;
```

### Події

```typescript
subscribedEvents(): string[];
sourceId(): string;

async onChatSync(event: ChatSyncEvent): Promise<void>;
async onStateChanged(event: StateChangedEvent): Promise<void>;
async onCommandTriggered(event: CommandTriggeredEvent): Promise<void>;
async onCommandCompleted(event: CommandCompletedEvent): Promise<void>;

async onEvent(eventType: string, payload: unknown): Promise<void>;
```

### Клієнтський режим

```typescript
isClient(): boolean;  // override to return true
```

Коли повертає `true`, SDK створює `DaemonClient` і передає його в `onDaemonClientReady`. `DaemonClient` надає `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService` та `MonitorService`.

## Конструктори `Field`

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

## Конструктори `UiContrib`

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

## Активація тригерів

```typescript
async onTick() {
  if (this.activeTriggers.has("on_alarm")) {
    await this.host!.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
  }
}
```

`activeTriggers` підтримується в актуальному стані SDK, коли демон викликає `OnActiveTriggers`.

## Збирання

```bash
npm run build
```

Для продакшн-бандлів використовуйте `esbuild`:

```bash
npx esbuild src/index.ts \
  --bundle \
  --platform=node \
  --target=node20 \
  --outfile=dist/index.js
```

`astra-plugin build` автоматично запустить це, коли виявить TypeScript.

## Робочий приклад — json-tools

Див. `AstraPlugins/examples/json-tools`. Основні моменти:

- Інструменти: `format_json`, `query_json`, `diff_json`.
- Дії з `Field.textareaWithVariables` для шаблонних входів.
- Тригер: `on_parse_error`, що активується з фонового валідатора.

Маніфест:

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

## Куди далі

- [Capabilities](capabilities.md) — повна поведінка кожної можливості.
- [Manifest](manifest.md) — кожне поле `plugin.toml`.
- [Publishing](publishing.md) — збирання, підпис, розповсюдження.
