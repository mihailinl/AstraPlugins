# Astra Plugin SDK (TypeScript)

Build plugins for [Astra](https://github.com/mihailinl/Astra) in TypeScript.

## Installation

The package name is unscoped. (`@astra/plugin-sdk` appeared in older docs and
scaffolds; that scope was never registered, so it 404s.)

```bash
npm install astra-plugin-sdk
```

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

## License

MIT.
