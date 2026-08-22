> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/4-sdk/typescript.md)。如与英文版有出入，以英文版为准。

# TypeScript SDK

`astra-plugin-sdk` **0.5.0 —— 本页描述的版本**，也是 npm 上提供的版本。
`npm install astra-plugin-sdk`（或 `bun add`）会解析到这个版本；
`astra-plugin new --lang typescript` 固定的也是同一个版本。请使用
0.5.0 或更新版本：0.4.0 不发送会话令牌，守护进程会拒绝它发起的每一次
host 调用。

这个包名没有 scope —— 一个更早的带 scope 的名字残留在一些旧项目里，但
从未真正注册过，所以对它执行 `npm i` 会直接失败。

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

TypeScript 插件打包为 **`noarch`**：每个平台共用一个包。它的 `[entry]`
是 `command = "node"`、`args = ["dist/index.js"]`、
`runtimes = ["node"]`，`astra-plugin build` 会把 `src/index.ts` 打包
成单一的自包含 CommonJS 文件 —— 一个 `.astraplugin` 不携带
`node_modules`。

## 插件的形态

插件是一个**值**，从模块中导出，只有当这个文件本身就是进程入口点时它
才会启动。这正是让测试能够在进程内驱动它、而不需要守护进程也不需要
套接字的原因。

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

一个对象，你的插件所做的每一件事对应一个键：

| 键 | |
|---|---|
| `tools` | `Record<name, tool({...})>` |
| `actions` | `Record<type, action({...})>` —— 命令编辑器中的步骤 |
| `triggers` | `Record<type, { label }>` |
| `tts` · `stt` · `ai` | 提供者的定义 |
| `ui` | 贡献内容，以及你的 iframe 可以回调进来的方法 |
| `events` | 你想要哪些守护进程事件，以及对应的处理函数 |
| `client` | `{ onReady(daemon, ctx) }` —— 仅用于 `client` 类型的插件，而且**它传给你的那个 `daemon` 目前还不能用**：见下文 |
| `configSchema` | 用于你的设置的 `s.object({...})` |
| `onStart` · `onShutdown` · `onConfigChanged` · `onLanguageChanged` · `onActiveTriggers` · `healthCheck` | 生命周期 |

`plugin()` 返回 `{ run(), instance, definition }`：`run()` 是你入口
文件的最后一行，`instance` 是测试工具驱动的对象，`definition` 是留给
想要读取你的 schema 的工具用的。

## Schema

`s` 会同时构建出 JSON Schema 和对应的 TypeScript 类型：

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

## 调用 Astra

使用 `ctx` 上的方法。每一个都是 `async` 的，所以一个尚未注册的插件得到
的是一个**被拒绝的 Promise**，而不是一个从返回 Promise 的函数中同步
抛出的异常 —— 而后者正是 `try { await ctx.fireTrigger(...) } catch {}`
无法捕获的那种形态。

| `ctx.…` | 权限 |
|---|---|
| `log(level, msg)` · `info(msg)` · `warn(msg)` · `error(msg)` | 无 |
| `fireTrigger(type, payload?)` | `fire_trigger` |
| `setVariable(name, value, scope?)` | `set_variable` |
| `pushToUi(event, payload?)` | `push_to_ui` |
| `sendChatMessage(text, opts?)` | `send_chat_message` |
| `setThemeContribution(theme)` | `set_theme_contribution` |

这些包装函数接受一个**负载对象(payload object)**，并替你把它字符串化；
`ctx.host` 是底层的原始客户端，类型是 `Host | null`，它的
`fireTrigger` / `pushToUi` 接受的是一个 JSON **字符串**。
`getConfig()`、`getDaemonInfo()`、`subscribeEvents()` 和
`getPluginId()` 也都在 `ctx.host` 上。

`setVariable`、`pushToUi` 以及 UI 调用路径现在都已经存在并且完成了
绑定；旧文档说的不是这样，是因为它们落地得比较晚。

## 触发器点燃后，产出去了哪里

在处理来自 Astra 的调用时点燃的触发器，会被归属到那次调用。因此它引发的一切都会
落在用户此刻正看着的那段对话里。**为此你不需要写任何代码**，而且它在 `await`、
`setTimeout` 和 promise 链上都成立——包括通过 `ctx.fireTrigger`、
`ctx.host.fireTrigger`，以及 `Plugin` 子类上的 `this.fireTrigger`，它们都到达
同一条传输通道。

<!-- doctest: illustrative reason="one property of a tool object, not a module: it needs the enclosing `plugin({ tools: { … } })` the ts-plugin blocks above type-check. The behaviour is executed by tools/causality.test.mjs, against a real gRPC handshake." -->
```ts
run: async ({ count }, ctx) => {
  const results = roll(count);
  await ctx.fireTrigger("on_roll_value", { value: results[0] });  // attributed
  return `rolled ${results}`;
},
```

从别处点燃的触发器是**根事件**：守护进程会把它归入本插件自己的自动化线程，而不是
去猜是哪段对话。这包括在处理器之外启动的定时器、`child_process`、
`worker_threads` 的 worker，以及由原生扩展安排的回调。这是正确答案，不是降级的
答案——落错对话比不落更糟。

`MockDaemon.firedTriggers()` 会报告 `causedBy`——根事件为 `undefined`——所以你
自己的测试能把两者区分开，而 `wire.callTool(name, args, { causedBy })` 会按
守护进程的方式发出调用。

## 错误

`BadArguments`、`NotFound`、`NotConfigured`、`Unauthorized`、
`RateLimited`、`Unavailable`、`TimeoutError`、`InternalError` ——
抛出其中之一，SDK 会把它映射为和另外两个 SDK 相同的传输层错误码。
`HookUnimplemented` 是用来表达"这个钩子不存在"的方式，这也正是
`UNIMPLEMENTED` 在传输层面上的含义。

分类体系和传输层字符串：见 [`reference/errors.md`](../reference/errors.md)。

## 测试

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

`Harness` 会在进程内驱动真正的能力服务(capability service)：
`listTools`、`callTool`、`schema`、`assertSchemaAccepts`、
`assertSchemaRejects`、`executeAction`、`callFromUi`、`synthesize`、
`sttStream`、`aiComplete`、`event`、`conversationEvent`、
`configChanged`、`healthCheck`、`fuzzConfig`。`RecordingHost` 会记录
你的插件对 Astra 说了什么。`MockDaemon` 和 `WirePlugin` 是第二层级的
搭档：通过 gRPC 驱动一个真实进程。

## 这个 SDK 目前还做不到的事

- **传给 `client.onReady` 的那个 `daemon` 不能正常工作。** 守护进程把
  每一个插件都注册为 `ClientType::PluginClient`，它的认证拦截器会拒绝
  这个身份访问 `/astra.PluginHostService/` 之外的任何路径，返回
  `permission_denied("plugin session tokens are scoped to
  PluginHostService")`。`client: true` 并不能改变这一点。
  `host.sendChatMessage` 是唯一一条能真正驱动 AI 对话轮次的可用路径。
  守护进程那一侧的部分还没有被构建出来，而不是坏掉了。
- **`UiPanel` 是一个被弃用的别名**，指向 `UiContribution` —— 0.5.0
  中弃用，0.7.0 起可移除。
- **`aiGetModels` 已被弃用**，没有任何人调用它；没有替代方案。
- **`ttsSynthesizeStream` 已经绑定，但是 unrouted 的** —— 不存在守护
  进程侧的调用点。
- **这里的 proto 不是手动维护的。** 曾经有两段 proto 字符串以内联
  形式存在于这个 SDK 中，被写入一个临时目录后再从那里加载，其中一个
  描述的是一个早已迁移走的服务 —— 于是每一个 TypeScript client 插件
  都会在注册过程中抛出异常。现在只有一份 `.proto`，作为 vendor 依赖
  并接受检查；请不要重新引入一份拷贝。

## 另请参阅

[TypeScript 钩子表](../hooks/typescript.md) ·
[对照表](../reference/parity.md) · [错误](../reference/errors.md) ·
[版本管理](../versioning.md)
