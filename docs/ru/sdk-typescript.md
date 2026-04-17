# TypeScript SDK

TypeScript SDK — это **API на основе классов**: унаследуйтесь от базового класса `Plugin` и переопределите асинхронные методы, соответствующие реализуемым вами возможностям. SDK определяет, какие методы вы переопределили (т. е. возвращают непустые значения), чтобы автоматически объявить возможности при регистрации.

Пакет: `@astra/plugin-sdk` в `AstraPlugins/astra-plugin-sdk-ts`.
Источник правды: `astra-plugin-sdk-ts/src/plugin.ts` и `astra-plugin-sdk-ts/src/types.ts`.

## Рантайм

Поддерживаемый рантайм — **Node.js 20+**. Демон запускает плагины с `command = "node"` и `args = ["dist/index.js"]`. Bun может работать для разработки, но не тестируется — по умолчанию сборка использует `tsc` и `esbuild`.

## Установка

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

## Минимальный плагин

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

`.run()` разбирает аргументы командной строки (`--daemon-addr`, `--plugin-id`, `--auth-token`), поднимает gRPC-сервер на `127.0.0.1:0`, регистрируется у демона, автоматически обнаруживает возможности и диспетчеризирует входящие RPC.

## Авто-обнаружение возможностей

При запуске SDK проверяет, какие методы вы переопределили, вызывая каждый метод возможности и проверяя, возвращает ли он осмысленные данные (`plugin.ts:290-302`):

- `listTools()` возвращает непустой массив → `tools`
- `ttsListVoices()` возвращает непустой массив → `tts`
- `sttGetLanguages()` возвращает непустой массив → `stt`
- `aiGetModels()` возвращает модели → `ai_provider`
- `getActionTypes()` возвращает типы → `actions`
- `getTriggerTypes()` возвращает типы → `triggers`
- `getUiContributions()` возвращает контрибуции → `ui_contributions`
- `isClient()` возвращает `true` → `client`

Вам всё равно следует объявить те же возможности в секции `[capabilities]` внутри `plugin.toml` — демон использует её для выделения ресурсов и проверок во время выполнения.

## Переопределяемые методы

### Инструменты

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

### Действия и триггеры

```typescript
async getActionTypes(): Promise<ActionTypeDef[]>;
async executeAction(actionType: string, paramsJson: string): Promise<ActionResult>;
async getTriggerTypes(): Promise<TriggerTypeDef[]>;
```

### UI-контрибуции

```typescript
async getUiContributions(): Promise<UiContribution[]>;
async handleUiCall(method: string, paramsJson: string): Promise<UiCallResult>;
```

### Жизненный цикл

```typescript
async onDaemonClientReady(client: DaemonClient): Promise<void>;
async onConfigChanged(config: Record<string, unknown>): Promise<void>;
async onLanguageChanged(language: string): Promise<void>;
async onActiveTriggers(activeTypes: string[]): Promise<void>;
async onShutdown(): Promise<void>;
async healthCheck(): Promise<{ healthy: boolean; status: string }>;
```

### События

```typescript
subscribedEvents(): string[];
sourceId(): string;

async onChatSync(event: ChatSyncEvent): Promise<void>;
async onStateChanged(event: StateChangedEvent): Promise<void>;
async onCommandTriggered(event: CommandTriggeredEvent): Promise<void>;
async onCommandCompleted(event: CommandCompletedEvent): Promise<void>;

async onEvent(eventType: string, payload: unknown): Promise<void>;
```

### Клиентский режим

```typescript
isClient(): boolean;  // override to return true
```

Когда метод возвращает `true`, SDK создаёт `DaemonClient` и передаёт его в `onDaemonClientReady`. `DaemonClient` предоставляет `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService` и `MonitorService`.

## Билдеры `Field`

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

## Билдеры `UiContrib`

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

## Запуск триггеров

```typescript
async onTick() {
  if (this.activeTriggers.has("on_alarm")) {
    await this.host!.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
  }
}
```

`activeTriggers` поддерживается SDK в актуальном состоянии, когда демон вызывает `OnActiveTriggers`.

## Сборка

```bash
npm run build
```

Для production-бандлов используйте `esbuild`:

```bash
npx esbuild src/index.ts \
  --bundle \
  --platform=node \
  --target=node20 \
  --outfile=dist/index.js
```

`astra-plugin build` вызовет это автоматически, если обнаружит TypeScript.

## Полный пример — json-tools

См. `AstraPlugins/examples/json-tools`. Ключевые моменты:

- Инструменты: `format_json`, `query_json`, `diff_json`.
- Действия с `Field.textareaWithVariables` для шаблонных входных данных.
- Триггер: `on_parse_error`, запускаемый из фонового валидатора.

Манифест:

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

## Куда двигаться дальше

- [Возможности](capabilities.md) — полное поведение каждой возможности.
- [Манифест](manifest.md) — каждое поле `plugin.toml`.
- [Публикация](publishing.md) — сборка, подпись, распространение.
