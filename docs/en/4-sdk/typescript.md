# The TypeScript SDK

`astra-plugin-sdk`, from npm: `npm install astra-plugin-sdk` (or `bun add`)
installs it, and `astra-plugin new --lang typescript` pins the range below.
Take 0.5.0 or newer: 0.4.0 sends no session token and the daemon refuses every
host call it makes.

The package name has no scope — an earlier scoped name appears in old projects
and was never registered, so `npm i` of it fails outright.

<!-- doctest: illustrative reason="a package.json fragment; the scaffold containing it is what the ts-plugin blocks below type-check against" -->
```json
{
  "dependencies": {
    "astra-plugin-sdk": "^0.7.0",
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
| `triggers` | `Record<type, { label, iconSvg?, fields? }>` |
| `tts` · `stt` · `ai` | The provider definitions |
| `ui` | Contributions, and the methods your iframe may call back into |
| `events` | Which daemon events you want, and the handlers |
| `client` | `{ onReady(daemon, ctx) }` — only for `client` plugins, and **the `daemon` it hands you does not work yet**: see below |
| `configSchema` | An `s.object({...})` for your settings |
| `onStart` · `onShutdown` · `onConfigChanged` · `onLanguageChanged` · `onActiveTriggers` · `healthCheck` | Lifecycle |

**The glyph a step wears.** `iconSvg` on an action or a trigger is what the user
sees on the canvas, in the palette and in the step's config header. Pass whole
SVG markup, not a path string: give it a `viewBox` and no `width`/`height`
(Astra sizes it, and those three surfaces are not the same size) and paint with
`currentColor`, so it follows whatever each surface tints its icons. The markup
is sanitised before it renders — scripts, event handlers and external references
are stripped rather than refused — so keep it a plain line drawing. Omit it and
the step still draws, falling back to your plugin's own icon and then to a
generic plugin mark.

**An AI provider's model list** is `ai.models` — an `AiModelList`, or
`(ctx) => list` (sync or async) to fetch it. Astra asks when the plugin starts
and whenever the AI page refreshes, and offers the list in its model picker; the
model the person picks arrives on `req.model` in `ai.complete`, and an empty one
means `defaultModel`. A model's `hints` say how it wants to be driven:
`acceptsImages: true` sends it the conversation's pictures (on
`message.images`, as `AiImage`s), `toolLoading: "all"` puts every tool in the
request instead of Tool Search while they fit a quarter of the window and 32k
tokens, and `contextWindow` sizes the history; `providerHints` covers every
model without hints of its own. **Hints change only Astra's turns on that model,
and only in a daemon built with the `plugin-provider-slots` feature.** A request
to a model that reads pictures carries up to 20 MiB of them, so the SDK's
capability server receives messages up to `limits.PLUGIN_MAX_MESSAGE_BYTES`
(64 MiB) since 0.7.4, where gRPC's default is 4 MiB. A class-based plugin
overrides `aiGetModels()` instead.

**An image provider** (`image_provider`, since 0.7.4) is `image: { generate,
models? }`: `generate` draws one picture per call and answers
`ImageGeneration.drawn(bytes)` or a refusal, `ImageGeneration.refuse(code,
message)` — an answer, never a throw; `models` is optional, and only a model
it marks `acceptsInputImages` is sent the pictures to edit, on
`req.inputImages`. A class-based plugin overrides `imageGenerate()` and
`imageGetModels()`. **No Astra release asks yet** — only a daemon built with
`plugin-provider-slots`. The contract, the refusal codes and a worked plugin:
[Image provider plugins](../image-provider-plugins.md).

**A tool that reads the person's pictures** says `wantsAttachments: true` in
`tool({...})` (or on a class-based plugin's `ToolDef`), and its handler reads
`ctx.attachments` — the pictures attached to the message being answered, as
`AiImage`s; `currentAttachments()` reads the same where no context is to hand.
It needs the high-risk `receive_attachments` permission, and no Astra release
sends pictures yet: [Permissions](../3-reference/permissions.md#receiving-the-pictures-the-person-attached)
has the conditions. A test sends them with `callTool(name, args, {
conversationId, attachments })`, on the harness and on `MockDaemon` alike.

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
| `getAiSettings()` — the chat's provider, model and endpoint, never a key | `read_ai_settings` |
| `speak(text)` — say it aloud in Astra's voice; resolves once it was said, stopped or refused | `speak` (high-risk) |
| `stopSpeaking()` — stop everything this plugin asked to be said | `speak` |
| `getUserIdentity()` — pseudonyms for this installation and the signed-in account | `read_user_identity` |
| `requestSettingsChange(changes, reason)` — ask the person to change some of Astra's settings, on a card they answer | `request_settings_change` |

The wrappers take a **payload object** and stringify it for you;
`ctx.host` is the raw client underneath, typed `Host | null`, whose
`fireTrigger` / `pushToUi` take a JSON **string**. `ctx.host` is also where
`getConfig()`, `getDaemonInfo()`, `subscribeEvents()` and `getPluginId()` live.
For the chat's provider, model and endpoint (never a key; needs
`read_ai_settings`) call `ctx.getAiSettings()`: `Host.getAiSettings` is optional
on the interface, and the wrapper throws a clear error when the host lacks it,
so you never write `ctx.host?.getAiSettings?.()` yourself. `ctx.speak()`,
`ctx.stopSpeaking()`, `ctx.getUserIdentity()` and `ctx.requestSettingsChange()`
work the same way.

`ctx.speak(text)` resolves with a `SpeakResult`: `outcome` is `"SPOKEN"`,
`"STOPPED"` (silence was asked for — **not an error**; do not say it again
unasked) or `"NOT_SPOKEN"`, with `error` — the same `PluginErrorDetail` a chat
chunk carries — saying why (`error.code === "PLUGIN_ERROR_RATE_LIMITED"` comes
with `error.retryAfterMs`). An outcome this SDK does not know reads as
`"UNSPECIFIED"`, never as one it does. `speak` needs an account that opens Astra
and the person's reply voice on, and the daemon refuses a text over
`limits.SPEAK_TEXT_MAX_CHARS` (300) characters rather than cut it.
[Permissions](../3-reference/permissions.md#speaking-in-astras-voice) has the
whole table. In a test, `RecordingHost.speakResult` and `.userIdentity` stage
the answers and `spoken()` lists what your plugin asked to say.

`ctx.requestSettingsChange([{ path: "ai.model", value: "gpt-4.1" }], "why")` —
each `value` any JSON value — asks the person to change settings the assistant
itself may change, on a card that shows each setting as it is and as it would be,
and your reason; all of them change, or none. It resolves with a
`SettingsChangeResult`: `outcome` is `"APPLIED"`, `"UNCHANGED"` (nobody was
asked), `"DECLINED"` (**do not ask again unasked**), `"TIMED_OUT"`, or
`"REFUSED"` with `code` (`rate_limited`, `busy`, `not_assistant_editable`, …),
`refusedPath` and `error.retryAfterMs`; an outcome this SDK does not know reads as
`"UNSPECIFIED"`. **The call lasts until the person answers or the card expires**
— at least 30 s, 120 s by default — and the SDK puts no deadline on it, so never
await it on a path that must answer quickly. A value JSON cannot hold (`NaN`,
`undefined`, a function) throws a `TypeError` before anything is sent; nothing
else is checked client-side — at most `limits.SETTINGS_CHANGE_MAX_CHANGES` (8)
changes and a reason of `limits.SETTINGS_CHANGE_REASON_MAX_CHARS` (140)
characters, and the daemon refuses more. It needs Astra built with the
`plugin-requests` feature (else `"REFUSED"`, `not_compiled`) — no release has it
yet. [Permissions](../3-reference/permissions.md#asking-the-person-to-change-a-setting)
has the whole contract. In a test, `RecordingHost.settingsChangeResult` stages
the answer and `settingsChangeRequests()` lists what was asked for.

`DaemonClient` is `@deprecated` (0.7.4): Astra refuses a plugin's session token
on every service but `PluginHostService`, so it has done nothing since SDK
0.5.0. Everything above is the replacement.

`setVariable`, `pushToUi` and the UI call path all exist and are bound; older
documentation said otherwise because they landed late.

## Where a fired trigger's output goes

A trigger you fire while handling a call from Astra is attributed to that call,
so whatever it causes lands in the conversation that made the call.
**You write nothing for this**, and it holds across `await`, `setTimeout` and
promise chains — including through `ctx.fireTrigger`, `ctx.host.fireTrigger`
and `this.fireTrigger` on a `Plugin` subclass, which all reach the same
transport.

<!-- doctest: illustrative reason="one property of a tool object, not a module: it needs the enclosing `plugin({ tools: { … } })` the ts-plugin blocks above type-check. The behaviour is executed by tools/causality.test.mjs, against a real gRPC handshake." -->
```ts
run: async ({ count }, ctx) => {
  const results = roll(count);
  await ctx.fireTrigger("on_roll_value", { value: results[0] });  // attributed
  return `rolled ${results}`;
},
```

A trigger fired from anywhere else is a **root event**: the daemon files it in
this plugin's own automation thread rather than guessing at a conversation. That
covers a timer started outside a handler, a `child_process`, a
`worker_threads` worker, and a callback scheduled by a native addon. It is the
correct answer, not a degraded one — the wrong conversation is worse than none.

`MockDaemon.firedTriggers()` reports `causedBy` — `undefined` for a root event —
so your own tests can tell the two apart, and `wire.callTool(name, args,
{ causedBy })` issues a call the way the daemon will.

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
`executeAction`, `callFromUi`, `synthesize`, `sttStream`, `aiComplete`, `webSearch`,
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
