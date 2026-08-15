> **これは翻訳です。** 正式な情報源は [docs/en](../../en/4-sdk/typescript.md) です。内容に食い違いがある場合は英語版が優先されます。

# TypeScript SDK

`astra-plugin-sdk` **0.5.0 — このページが説明しているバージョン**であり、
npm が配信しているものです。`npm install astra-plugin-sdk`(または
`bun add`）でこれが解決されます; `astra-plugin new --lang typescript`
が固定するのも同じものです。0.5.0 以降を使ってください: 0.4.0 はセッション
トークンを一切送らず、デーモンはそれが行うすべてのホスト呼び出しを拒否
します。

パッケージ名にスコープはありません — 以前のスコープ付き名前が古い
プロジェクトに残っていますが、一度も登録されたことがないため、それを
`npm i` すると完全に失敗します。

<!-- doctest: illustrative reason="a package.json fragment; the scaffold containing it is what the ts-plugin blocks below type-check against" -->
```json
{
  "dependencies": {
    "astra-plugin-sdk": "^0.5.0",
    "@grpc/grpc-js": "^1.10.0",
    "@grpc/proto-loader": "^0.7.0"
  }
}
```

TypeScript プラグインは **`noarch`** としてパッケージ化されます: すべて
のプラットフォームに対して 1 つのバンドルです。その `[entry]` は
`command = "node"`、`args = ["dist/index.js"]`、`runtimes = ["node"]`
であり、`astra-plugin build` は `src/index.ts` を単一の自己完結型
CommonJS ファイルにバンドルします — `.astraplugin` は `node_modules`
を出荷しません。

## プラグインの形

プラグインは**値**であり、モジュールからエクスポートされ、このファイル
がプロセスのエントリポイントである場合にのみ起動します。これによって、
テストはデーモンもソケットもなしにインプロセスでそれを駆動できます。

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool, BadArguments } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    start_timer: tool({
      description:
        "Start a countdown. Use it when the user asks to be reminded in N minutes.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs, so `minutes` really is a number.
      input: s.object({
        minutes: s.number({ description: "How many minutes to wait" }),
        label: s.string({ description: "What the timer is for" }).optional(),
      }),
      run: async ({ minutes, label }, ctx) => {
        // Errors take an options object, not a bare string: the extra fields
        // are what the UI deep-links and retries on.
        if (minutes <= 0) throw new BadArguments({ message: "give me at least a minute" });
        // `ctx.info` / `ctx.fireTrigger` and not `ctx.host.*`: `ctx.host` is
        // `Host | null`, and these wrappers turn "no host" into a rejected
        // promise instead of a synchronous throw your `await` cannot catch.
        await ctx.info(`timer for ${minutes}m`);
        await ctx.fireTrigger("timer_started", { minutes, label });
        return `timer set for ${minutes} minutes`;
      },
    }),
  },

  triggers: {
    timer_started: { label: "Timer started" },
  },

  onConfigChanged: async (config, ctx) => {
    await ctx.info(`config has ${Object.keys(config).length} key(s)`);
  },
});

if (require.main === module) app.run();
```

## `plugin({...})`

1 つのオブジェクト、あなたのプラグインが行うことごとに 1 つのキー:

| キー | |
|---|---|
| `tools` | `Record<name, tool({...})>` |
| `actions` | `Record<type, action({...})>` — コマンドエディタ内のステップ |
| `triggers` | `Record<type, { label }>` |
| `tts` · `stt` · `ai` | プロバイダの定義 |
| `ui` | コントリビューションと、あなたの iframe がコールバックできるメソッド |
| `events` | どのデーモンイベントが欲しいかと、そのハンドラ |
| `client` | `{ onReady(daemon, ctx) }` — `client` プラグインのみ、そして**渡される `daemon` はまだ機能しません**: 下記参照 |
| `configSchema` | あなたの設定用の `s.object({...})` |
| `onStart` · `onShutdown` · `onConfigChanged` · `onLanguageChanged` · `onActiveTriggers` · `healthCheck` | ライフサイクル |

`plugin()` は `{ run(), instance, definition }` を返します:
`run()` はあなたのエントリポイントの最後の行であり、`instance` はテスト
ハーネスが駆動するもの、`definition` はあなたのスキーマを読みたいツール
のためのものです。

## スキーマ

`s` は JSON Schema と TypeScript の型を同時に構築します:

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool } from "astra-plugin-sdk";

const Query = s.object({
  text: s.string({ description: "What to search for" }),
  limit: s.number({ description: "How many results", minimum: 1, maximum: 50 }).optional(),
  fuzzy: s.boolean({ description: "Allow near matches" }).optional(),
  tags: s.array(s.string(), { description: "Restrict to these tags" }).optional(),
  mode: s.enum(["fast", "thorough"], { description: "How hard to look" }).optional(),
});

export const app = plugin({
  tools: {
    search: tool({
      description: "Search the user's notes.",
      input: Query,
      // `args` is typed from `Query`: `args.text` is a string, `args.limit` is
      // `number | undefined`, and a typo in either is a compile error.
      run: (args) => `searching for ${args.text} (limit ${args.limit ?? 10})`,
    }),
  },
});

if (require.main === module) app.run();
```

## Astra への呼び出し

`ctx` 上のメソッドを使ってください。どれも `async` であるため、まだ
登録されていないプラグインは、Promise を返す関数からの同期的な throw
ではなく、**却下された(rejected)Promise** を受け取ります — これが
`try { await ctx.fireTrigger(...) } catch {}` では捕捉できない形です。

| `ctx.…` | パーミッション |
|---|---|
| `log(level, msg)` · `info(msg)` · `warn(msg)` · `error(msg)` | なし |
| `fireTrigger(type, payload?)` | `fire_trigger` |
| `setVariable(name, value, scope?)` | `set_variable` |
| `pushToUi(event, payload?)` | `push_to_ui` |
| `sendChatMessage(text, opts?)` | `send_chat_message` |
| `setThemeContribution(theme)` | `set_theme_contribution` |

これらのラッパーは**ペイロードオブジェクト**を受け取り、あなたの代わりに
文字列化します; `ctx.host` はその下にある生のクライアントで、型は
`Host | null` であり、その `fireTrigger` / `pushToUi` は JSON
**文字列**を取ります。`getConfig()`、`getDaemonInfo()`、
`subscribeEvents()`、`getPluginId()` も `ctx.host` にあります。

`setVariable`、`pushToUi`、UI 呼び出し経路はすべて存在し、結びつけられて
います; 古いドキュメントはそうではないと言っていましたが、それらは遅れて
実装されたためです。

## エラー

`BadArguments`、`NotFound`、`NotConfigured`、`Unauthorized`、
`RateLimited`、`Unavailable`、`TimeoutError`、`InternalError` — これらの
いずれかを throw すると、SDK は他の 2 つの SDK が生成するのと同じ wire
コードにマッピングします。`HookUnimplemented` は「このフックは存在しない」
と言う方法であり、それはワイヤー上で `UNIMPLEMENTED` が意味することと
同じです。

分類と wire 上の文字列: [`reference/errors.md`](../reference/errors.md)。

## テスト

<!-- doctest: illustrative reason="a test file, not a plugin: it imports ../dist/plugin.cjs, which only exists after that project's own pretest step bundles it. This is the file `astra-plugin new --lang typescript` writes, and CI runs it there." -->
```javascript
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);

// `pretest` bundles src/index.ts with the SDK left EXTERNAL, so the plugin
// under test and the harness testing it share one copy of the SDK.
const { app } = require("../dist/plugin.cjs");
const { Harness } = require("astra-plugin-sdk/testing");

test("start_timer answers, and its schema matches its handler", async () => {
  const h = await Harness.create(app).start();

  assert.deepEqual(await h.toolNames(), ["start_timer"]);
  await h.assertSchemaAccepts("start_timer", { minutes: 5 });
  await h.assertSchemaRejects("start_timer", { minutes: "five" });

  const result = await h.callTool("start_timer", { minutes: 5 });
  assert.equal(result.success, true);
  assert.equal(result.result, "timer set for 5 minutes");
  assert.equal(h.host.firedTriggers()[0].triggerType, "timer_started");

  // An argument the schema forbids never reaches the handler: it comes back as
  // an in-band BAD_ARGUMENTS the assistant can read and correct.
  const bad = await h.callTool("start_timer", {});
  assert.equal(bad.success, false);
  assert.match(bad.error, /BAD_ARGUMENTS/);
});

test("no config the daemon can deliver crashes this plugin", async () => {
  // The daemon delivers config it did not author: the user's typing, and an
  // older version of this plugin's own schema. None of it may throw.
  const h = await Harness.create(app).start();
  assert.deepEqual(await h.fuzzConfig(), []);
});
```

`Harness` は実際のケーパビリティサービスをインプロセスで駆動します:
`listTools`、`callTool`、`schema`、`assertSchemaAccepts`、
`assertSchemaRejects`、`executeAction`、`callFromUi`、`synthesize`、
`sttStream`、`aiComplete`、`event`、`conversationEvent`、
`configChanged`、`healthCheck`、`fuzzConfig`。`RecordingHost` は
あなたのプラグインが Astra に伝えたことを記録します。`MockDaemon` と
`WirePlugin` はレベル 2 のペアです: gRPC 経由の実際のプロセスです。

## この SDK がまだできないこと

- **`client.onReady` に渡される `daemon` は機能しません。** デーモンは
  すべてのプラグインを `ClientType::PluginClient` として登録し、その
  認証インターセプターは `/astra.PluginHostService/` の外にあるあらゆる
  パスでこのアイデンティティを
  `permission_denied("plugin session tokens are scoped to
  PluginHostService")` で拒否します。`client: true` はこれを変えません。
  `host.sendChatMessage` だけが AI のターンを駆動する動作する方法です。
  デーモン側の半分がまだ構築されていないのであって、壊れているのでは
  ありません。
- **`UiPanel` は非推奨のエイリアスです**。`UiContribution` に対する
  もので、0.5.0 で非推奨、0.7.0 から削除可能です。
- **`aiGetModels` は非推奨であり**、誰にも呼ばれていません; 代替は
  ありません。
- **`ttsSynthesizeStream` は結びつけられていますが unrouted です**
  — デーモン側の呼び出し箇所は存在しません。
- **ここでは proto は手動で管理されていません。** かつてこの SDK には
  2 つの proto 文字列がインラインで存在し、一時ディレクトリに書き出され
  そこから読み込まれていましたが、そのうちの 1 つは、すでに移行済みの
  サービスを説明していました — そのため、すべての TypeScript の
  client プラグインが登録中に例外を投げていました。今では単一の
  `.proto` が vendor され、チェックされています; コピーを再導入しない
  でください。

## 関連ページ

[TypeScript のフック表](../hooks/typescript.md) ·
[パリティ](../reference/parity.md) · [エラー](../reference/errors.md) ·
[バージョニング](../versioning.md)
