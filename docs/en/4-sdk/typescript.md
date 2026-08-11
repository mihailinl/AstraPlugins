# The TypeScript SDK

`astra-plugin-sdk` **0.5.0 — the version this page describes**, and the one npm
serves. `npm install astra-plugin-sdk` (or `bun add`) resolves it; that is also
what `astra-plugin new --lang typescript` pins. Take 0.5.0 or newer: 0.4.0 sends
no session token and the daemon refuses every host call it makes.

The package name has no scope — an earlier scoped name appears in old projects
and was never registered, so `npm i` of it fails outright.

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

A TypeScript plugin packages as **`noarch`**: one bundle for every platform. Its
`[entry]` is `command = "node"`, `args = ["dist/index.js"]`,
`runtimes = ["node"]`, and `astra-plugin build` bundles `src/index.ts` to a
single self-contained CommonJS file — a `.astraplugin` ships no `node_modules`.

## The shape of a plugin

The plugin is a **value**, exported from the module, and it starts only when
this file is the process entry point. That is what lets a test drive it
in-process with no daemon and no socket.

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

One object, one key per thing your plugin does:

| Key | |
|---|---|
| `tools` | `Record<name, tool({...})>` |
| `actions` | `Record<type, action({...})>` — steps in the command editor |
| `triggers` | `Record<type, { label }>` |
| `tts` · `stt` · `ai` | The provider definitions |
| `ui` | Contributions, and the methods your iframe may call back into |
| `events` | Which daemon events you want, and the handlers |
| `client` | `{ onReady(daemon, ctx) }` — only for `client` plugins, and **the `daemon` it hands you does not work yet**: see below |
| `configSchema` | An `s.object({...})` for your settings |
| `onStart` · `onShutdown` · `onConfigChanged` · `onLanguageChanged` · `onActiveTriggers` · `healthCheck` | Lifecycle |

`plugin()` returns `{ run(), instance, definition }`: `run()` is the last line
of your entry point, `instance` is what the test harness drives, and
`definition` is there for tooling that wants to read your schemas.

## Schemas

`s` builds JSON Schema and the TypeScript type at once:

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

## Calling out to Astra

Use the methods on `ctx`. Every one is `async`, so a plugin that is not
registered yet gets a **rejected promise** rather than a synchronous throw out
of a function that returns one — which is the shape
`try { await ctx.fireTrigger(...) } catch {}` does not catch.

| `ctx.…` | Permission |
|---|---|
| `log(level, msg)` · `info(msg)` · `warn(msg)` · `error(msg)` | none |
| `fireTrigger(type, payload?)` | `fire_trigger` |
| `setVariable(name, value, scope?)` | `set_variable` |
| `pushToUi(event, payload?)` | `push_to_ui` |
| `sendChatMessage(text, opts?)` | `send_chat_message` |
| `setThemeContribution(theme)` | `set_theme_contribution` |

The wrappers take a **payload object** and stringify it for you;
`ctx.host` is the raw client underneath, typed `Host | null`, whose
`fireTrigger` / `pushToUi` take a JSON **string**. `ctx.host` is also where
`getConfig()`, `getDaemonInfo()`, `subscribeEvents()` and `getPluginId()` live.

`setVariable`, `pushToUi` and the UI call path all exist and are bound; older
documentation said otherwise because they landed late.

## Errors

`BadArguments`, `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`,
`Unavailable`, `TimeoutError`, `InternalError` — throw one and the SDK maps it
to the same wire code the other two SDKs produce. `HookUnimplemented` is the way
to say "this hook is absent", which is what `UNIMPLEMENTED` means on the wire.

Taxonomy and wire strings: [`reference/errors.md`](../reference/errors.md).

## Testing

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

`Harness` drives the real capability service in process:
`listTools`, `callTool`, `schema`, `assertSchemaAccepts`, `assertSchemaRejects`,
`executeAction`, `callFromUi`, `synthesize`, `sttStream`, `aiComplete`,
`event`, `conversationEvent`, `configChanged`, `healthCheck`, `fuzzConfig`.
`RecordingHost` records what your plugin told Astra. `MockDaemon` and
`WirePlugin` are the level-2 pair: a real process over gRPC.

## What this SDK cannot do yet

- **The `daemon` handed to `client.onReady` is non-functional.** The daemon
  registers every plugin as `ClientType::PluginClient` and its auth interceptor
  rejects that identity on any path outside `/astra.PluginHostService/` with
  `permission_denied("plugin session tokens are scoped to PluginHostService")`.
  `client: true` does not change it. `host.sendChatMessage` is the only working
  way to drive an AI turn. The daemon-side half is unbuilt, not broken.
- **`UiPanel` is a deprecated alias** for `UiContribution` — deprecated in
  0.5.0, removable from 0.7.0.
- **`aiGetModels` is deprecated** and called by nobody; there is no replacement.
- **`ttsSynthesizeStream` is bound and unrouted** — no daemon call site exists.
- **The proto is not hand-maintained here.** Two proto strings once lived inline
  in this SDK, were written to a temp directory and loaded from there, and one
  of them described a service that had been migrated away — so every TypeScript
  client plugin threw during registration. There is now one `.proto`, vendored
  and checked; do not reintroduce a copy.

## See also

[Hook table for TypeScript](../hooks/typescript.md) ·
[parity](../reference/parity.md) · [errors](../reference/errors.md) ·
[versioning](../versioning.md)
