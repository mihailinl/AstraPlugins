# astra-plugin-sdk (TypeScript)

Write a plugin for Astra in TypeScript.

Repository: <https://github.com/mihailinl/AstraPlugins>

The package name is unscoped. (`@astra/plugin-sdk` appeared in older docs and
scaffolds; that scope was never registered, so it 404s.)

## Installing today

**`npm install astra-plugin-sdk` gets you 0.4.0.** The daemon rejects every host
RPC but `Register` without an `x-session-token`, and **0.5.0 is the first release
that sends one** — a 0.4.0 plugin starts, answers inbound hooks, and gets
`unauthenticated` on everything it tries to say back. Its `DaemonClient` is
worse: it loaded an inline proto string that predates the chat event-sourcing
migration, so its methods are `undefined` at runtime.

`astra-plugin new --lang typescript` pins `^0.5.0`, which does not resolve yet:

```
error: No version matching "^0.5.0" found for specifier "astra-plugin-sdk" (but package exists)
```

Until 0.5.0 is published, build the package from this checkout and install the
tarball — the same sequence CI runs:

```bash
git clone -b feat/plugin-production https://github.com/mihailinl/AstraPlugins
cd AstraPlugins/astra-plugin-sdk-ts
bun install --frozen-lockfile
bun run build
bun pm pack --destination /tmp/tgz     # -> /tmp/tgz/astra-plugin-sdk-0.5.0.tgz
```

> **The branch matters.** A bare `git clone` checks out the default branch,
> where `package.json` says **0.4.0** — so `bun pm pack` writes
> `astra-plugin-sdk-0.4.0.tgz`, the next command's path does not exist, and you
> would be installing the exact version this section exists to route around.
> Verified with `git show master:astra-plugin-sdk-ts/package.json`.
> `feat/plugin-production` is not pushed yet (`git ls-remote origin`), so for
> now this means a local checkout of that branch; delete this note once it is
> the default.

then in your plugin:

```bash
bun add /tmp/tgz/astra-plugin-sdk-0.5.0.tgz     # or: npm install /tmp/tgz/...tgz
```

Verified: with that dependency in place, a freshly scaffolded plugin's
`bun run test` passes.

Requires Node 20 or newer. Ships both CommonJS and ES modules.

## Quick start

A plugin is a value. Declare each tool's parameters once, as a schema:

```typescript
import { plugin, tool, s } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    hello: tool({
      description: "Greet someone by name.",
      input: s.object({
        name: s.string({ description: "Who to greet" }),
        excited: s.boolean().optional(),
      }),
      run: ({ name, excited }) => `Hello, ${name}${excited ? "!" : "."}`,
    }),
  },
});

if (require.main === module) app.run();
```

`input` is the JSON Schema the model is shown **and** the type of `run`'s first
argument: `name` is a `string`, `excited` is `boolean | undefined`, and the
handler is not reached at all unless the arguments conform — a violation comes
back to the assistant as an in-band `BAD_ARGUMENTS` result it can correct.

The class form is still supported and still the right choice for a plugin with
real state and a lifecycle:

```typescript
import { Plugin } from "astra-plugin-sdk";

class MyPlugin extends Plugin {
  async listTools() {
    return [{ name: "hello", description: "Say hello", parametersJson: "{}" }];
  }
  async callTool(name: string, argumentsJson: string) {
    return { success: true, result: "Hello!" };
  }
}

new MyPlugin().run();
```

## The schema builder

| Builder | JSON Schema | TypeScript |
|---|---|---|
| `s.string({ minLength, maxLength, pattern, format })` | `{"type":"string",…}` | `string` |
| `s.number({ minimum, maximum })` / `s.integer(…)` | `{"type":"number"\|"integer",…}` | `number` |
| `s.boolean()` | `{"type":"boolean"}` | `boolean` |
| `s.enum(["a","b"] as const)` | `{"type":"string","enum":[…]}` | `"a" \| "b"` |
| `s.array(item, { minItems, maxItems })` | `{"type":"array","items":…}` | `T[]` |
| `s.object({ … })` | `{"type":"object","properties":…,"required":…}` | `{ … }` |
| `.optional()` | omitted from `required` | `key?: T` |
| `.nullable()` | `anyOf: [T, {"type":"null"}]` | `T \| null` |
| `.describe(text)` | `description` | — |

Objects emit `additionalProperties: false`, so an argument the model invented is
reported rather than silently obeyed. Use `Infer<typeof schema>` to name the
type elsewhere. `default` is advisory: it is shown to the model and **not**
filled in at parse time, because a runtime that invented values would make
`indent?: number` a type that is never `undefined`.

## Capabilities

Everything is optional; declare what your plugin does.

- **Tools** — `tools: { name: tool({ description, input, run }) }`
- **Actions** — `actions: { type: action({ label, fields, params, run }) }`
- **Triggers** — `triggers: { type: { label, fields } }`, fired with `ctx.fireTrigger`
- **TTS** — `tts: { voices, synthesize, synthesizeStream, configFields, activate }`
- **STT** — `stt: { languages, transcribe, transcribeStream, load, unload, loadState }`
- **AI provider** — `ai: { complete }`, an async generator of chunks
- **UI** — `ui: { contributions, onCall }`
- **Events** — `events: { subscribe, on, onConversation }`
- **Lifecycle** — `onStart`, `onConfigChanged`, `onLanguageChanged`, `onActiveTriggers`, `onShutdown`, `healthCheck`

## Talking to the daemon

Every handler's second argument is a `PluginContext`:

```typescript
run: async ({ text }, ctx) => {
  await ctx.info(`working on ${text.length} characters`);
  await ctx.fireTrigger("did_a_thing", { length: text.length });
  await ctx.setVariable("last_input", text);
  const timeout = ctx.configValue("timeout_ms", 5000);
  return text.toUpperCase();
}
```

`console.log` and friends are routed into the daemon's log pane too, so a
library that logs is visible without changing it. An uncaught exception or
unhandled rejection is logged at `error` level and exits with code 70, rather
than the process silently vanishing.

**Every outbound call is default-deny.** A manifest with no `[permissions]`
section may call `Register`, `PluginLog`, `GetPluginSelfConfig` and
`GetDaemonInfo`, and nothing else. `ctx.setVariable` above needs

```toml
[permissions]
set_variable = { reason = "Publishes the transformed JSON as the variable your command names in 'Store Result In'", scopes = ["session"] }
```

and the `reason` is what the user reads on the install consent sheet. Declaring
the matching **capability** is not what opens the call; this is.

A plugin whose `isClient()` returns `true` also gets a `DaemonClient` — chat,
voice, commands, settings. There is no `chat_message_sync` hook; a client plugin
uses `events.onConversation`.

> **That client does not reach anything yet.** The daemon registers every plugin
> as `ClientType::PluginClient` and its auth interceptor rejects that identity
> on any gRPC path outside `/astra.PluginHostService/`, so every `DaemonClient`
> call answers `permission_denied` — `client: true` included.
> `host.sendChatMessage` is the only working way to drive an AI turn. The
> daemon-side half is unbuilt; the SDK surface is here first.

## Errors

```typescript
import { NotConfigured } from "astra-plugin-sdk";

run: () => { throw new NotConfigured("api_key"); }
```

Eight classes with the same eight codes the Rust and Python SDKs use:
`BadArguments`, `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`,
`Unavailable`, `Timeout`, `InternalError`, all extending `PluginError`. `code`
is a string literal on each class, so `AnyPluginError` is a discriminated union
and `switch (err.code) { case "NOT_CONFIGURED": … }` narrows to the subclass and
reaches `err.configField` with no cast.

A failure stays **in-band** (`success: false`, `error: "NOT_CONFIGURED: …"`,
plus a structured `errorDetail`) rather than becoming a gRPC status, because the
assistant has to read it. Anything else you throw is adopted as `INTERNAL`,
except `SyntaxError` / `TypeError` — what `JSON.parse` throws on the model's
arguments — which become `BAD_ARGUMENTS`.

## Testing

```typescript
import { Harness, MockDaemon } from "astra-plugin-sdk/testing";

const h = await Harness.create(app).withConfig({ indent: 4 }).start();
const result = await h.callTool("hello", { name: "Ada" });
await h.assertSchemaRejects("hello", { name: 42 });
assert.deepEqual(h.host.firedTriggers(), []);
```

`Harness` is level 1: in process, no socket, driving the SDK's real handler map.
`MockDaemon` is level 2: a real gRPC server, a real `Register` handshake, a real
session token and real protobuf encoding — the only place a descriptor mismatch,
the auth interceptor or `keepCase` casing can be checked at all. A suite wants
both. See `examples/json-tools/test/plugin.test.mjs` for a worked one.

Fixtures come with the harness: `utteranceChunks()` is a golden 16 kHz utterance
longer than the STT channel's 500-slot bound, `firehoseEvents()` is a whole
assistant turn, and `h.fuzzConfig()` pushes eleven shapes of real-world config
through `onConfigChanged` and reports which ones threw.

Every TypeScript block in this file was executed against a build of this
checkout before it was written down.

## What this SDK does not do

- **No isolation.** Your plugin is a native Node process with the user's full
  privileges. Permissions constrain what the *daemon* will do for you; nothing
  constrains what your process does to the machine.
- `ttsSynthesizeStream` is implemented here and **the daemon has no call site
  for `TtsSynthesizeStream`**. `aiGetModels` is deprecated and still bound so
  old plugins get `UNIMPLEMENTED` rather than a transport error. Both are listed
  under "Findings" in the generated hook-parity page, which `tools/parity`
  renders from [`spec/hooks.yaml`](../spec/hooks.yaml).

Full history, including everything breaking in 0.5.0:
[`CHANGELOG.md`](CHANGELOG.md).

## License

MIT.
