# TypeScript SDK

TypeScript SDK は**クラスベース**の API です。`Plugin` 基底クラスを継承し、実装したい機能に対応する async メソッドをオーバーライドします。SDK は、どのメソッドがオーバーライドされているか（つまり空でない値を返すか）を検査し、登録時に機能を自動宣言します。

パッケージ: `AstraPlugins/astra-plugin-sdk-ts` にある `@astra/plugin-sdk`。
正式な仕様: `astra-plugin-sdk-ts/src/plugin.ts` および `astra-plugin-sdk-ts/src/types.ts`。

## ランタイム

サポートされるランタイムは **Node.js 20 以上** です。デーモンはプラグインを `command = "node"` と `args = ["dist/index.js"]` で起動します。開発時には Bun も動作する可能性がありますがテストされていません。ビルドは既定で `tsc` と `esbuild` を使用します。

## インストール

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

## 最小構成のプラグイン

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

`.run()` は CLI 引数（`--daemon-addr`、`--plugin-id`、`--auth-token`）の解析、`127.0.0.1:0` での gRPC サーバー起動、デーモンへの登録、機能の自動検出、受信 RPC のディスパッチを行います。

## 機能の自動検出

起動時、SDK は各機能メソッドを呼び出してオーバーライドされているかを調べ、戻り値が意味のあるデータかを確認します（`plugin.ts:290-302`）。

- `listTools()` が非空の配列を返す → `tools`
- `ttsListVoices()` が非空の配列を返す → `tts`
- `sttGetLanguages()` が非空の配列を返す → `stt`
- `aiGetModels()` がモデルを返す → `ai_provider`
- `getActionTypes()` が型を返す → `actions`
- `getTriggerTypes()` が型を返す → `triggers`
- `getUiContributions()` がコントリビューションを返す → `ui_contributions`
- `isClient()` が `true` を返す → `client`

それでも `plugin.toml` の `[capabilities]` で同じ機能を宣言してください。デーモンはその宣言を使ってリソースを割り当て、実行時のチェックを行います。

## オーバーライド可能なメソッド

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

### Actions と triggers

```typescript
async getActionTypes(): Promise<ActionTypeDef[]>;
async executeAction(actionType: string, paramsJson: string): Promise<ActionResult>;
async getTriggerTypes(): Promise<TriggerTypeDef[]>;
```

### UI コントリビューション

```typescript
async getUiContributions(): Promise<UiContribution[]>;
async handleUiCall(method: string, paramsJson: string): Promise<UiCallResult>;
```

### ライフサイクル

```typescript
async onDaemonClientReady(client: DaemonClient): Promise<void>;
async onConfigChanged(config: Record<string, unknown>): Promise<void>;
async onLanguageChanged(language: string): Promise<void>;
async onActiveTriggers(activeTypes: string[]): Promise<void>;
async onShutdown(): Promise<void>;
async healthCheck(): Promise<{ healthy: boolean; status: string }>;
```

### イベント

```typescript
subscribedEvents(): string[];
sourceId(): string;

async onChatSync(event: ChatSyncEvent): Promise<void>;
async onStateChanged(event: StateChangedEvent): Promise<void>;
async onCommandTriggered(event: CommandTriggeredEvent): Promise<void>;
async onCommandCompleted(event: CommandCompletedEvent): Promise<void>;

async onEvent(eventType: string, payload: unknown): Promise<void>;
```

### クライアントモード

```typescript
isClient(): boolean;  // override to return true
```

true のとき、SDK は `DaemonClient` を構築して `onDaemonClientReady` に渡します。`DaemonClient` は `CoreService`、`ChatService`、`VoiceService`、`CommandService`、`ConfigService`、`MediaService`、`MonitorService` を公開します。

## `Field` ビルダー

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

## `UiContrib` ビルダー

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

## トリガーの発火

```typescript
async onTick() {
  if (this.activeTriggers.has("on_alarm")) {
    await this.host!.fireTrigger("on_alarm", JSON.stringify({ time: "09:00" }));
  }
}
```

`activeTriggers` は、デーモンが `OnActiveTriggers` を呼び出すたびに SDK が最新の状態に保ちます。

## ビルド

```bash
npm run build
```

本番バンドルには `esbuild` を使用します。

```bash
npx esbuild src/index.ts \
  --bundle \
  --platform=node \
  --target=node20 \
  --outfile=dist/index.js
```

TypeScript が検出されると、`astra-plugin build` がこれを自動的に実行します。

## 実例 — json-tools

`AstraPlugins/examples/json-tools` を参照してください。要点は次のとおりです。

- ツール: `format_json`、`query_json`、`diff_json`。
- テンプレート入力に `Field.textareaWithVariables` を使ったアクション。
- トリガー: バックグラウンドのバリデータから発火する `on_parse_error`。

マニフェスト:

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

## 次に進むには

- [機能](capabilities.md) — 各機能の完全な動作仕様。
- [マニフェスト](manifest.md) — `plugin.toml` の全フィールド。
- [公開](publishing.md) — ビルド、署名、配布。
