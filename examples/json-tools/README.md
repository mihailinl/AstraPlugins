# JSON Tools

Format, query and diff JSON — in conversation and in commands.

## What it does

Three things the assistant can do for you in a conversation:

- **`json_format`** — pretty-print a JSON string at a chosen indent, or tell you
  precisely where it is malformed.
- **`json_query`** — pull a value out with a dot-path such as
  `data.users[0].name`.
- **`json_diff`** — compare two JSON documents and list what was added, removed
  and changed, path by path.

And one **"JSON Transform" action** for the command editor, which does *format*,
*minify*, *sort keys* or *extract path* on a value from an earlier step and can
store the result in a variable. Sorting keys is the useful one for commands: two
documents that differ only in key order stop looking different.

There is also an **"Invalid JSON Detected" trigger** whose payload carries the
offending text and a source label. Note the honest bit: this trigger is declared
so a command can subscribe to it, but nothing in this plugin fires it today — a
command wired to it will never run until some future version does. It is here as
a worked example of a declared trigger type, not as a working alarm.

## What it needs

- **Node.js 18 or newer** on the machine running Astra. This is a TypeScript
  plugin; Astra does not ship a Node runtime, so the bundle declares
  `runtimes = ["node"]` and the daemon refuses to start it if `node` is missing
  rather than failing halfway.

No network, no files outside its own directory, no account.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `tools` | Astra's assistant may call the plugin during a conversation | The three `json_*` tools |
| `actions` | The plugin contributes steps to the command editor | "JSON Transform" |
| `triggers` | The plugin can start your commands | "Invalid JSON Detected" (declared; see above) |

Text you pass to a tool is processed inside the plugin process and returned. It
is not written to disk and not sent anywhere.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| Default Indent | `2` | Spaces used by *format* and *sort keys* when no indent is given |

## Build it yourself

```bash
cd examples/json-tools
# This example needs astra-plugin-sdk 0.5.0, which is not on npm yet, so point
# resolution at the SDK in this checkout — exactly what CI does:
#   (cd ../../astra-plugin-sdk-ts && bun install && bun run build && bun pm pack --destination /tmp/tgz)
#   node -e 'const f=require("fs"),p=JSON.parse(f.readFileSync("package.json","utf8"));
#            p.overrides={"astra-plugin-sdk":"file:/tmp/tgz/astra-plugin-sdk-0.5.0.tgz"};
#            f.writeFileSync("package.json",JSON.stringify(p,null,2))'
bun install                   # or npm install
bun run test                  # the reference suite, both levels
bun run build                 # esbuild bundles src/index.ts to dist/index.js
astra-plugin build            # produces json-tools-<version>-noarch.astraplugin
```

The bundle is `noarch`: one file that runs on every platform Astra supports,
because the platform-specific part is the Node install, not the plugin.

## How it is written

The object form, with the SDK's `s` schema builder:

```typescript
json_format: tool({
  description: "Pretty-print JSON with configurable indentation.",
  input: s.object({
    json: s.string({ description: "JSON string to format" }),
    indent: s.integer({ minimum: 0, maximum: 10 }).optional(),
  }),
  run: ({ json, indent }, ctx) =>
    JSON.stringify(parse(json), null, indent ?? defaultIndent(ctx.config)),
});
```

`input` is the JSON Schema the assistant reads **and** the type of `run`'s first
argument. There is no `String(args.json ?? "")` anywhere in this plugin: the SDK
validated the assistant's arguments against that schema before the handler ran,
and a violation came back to the assistant as a `BAD_ARGUMENTS` result it can
read and correct.

## The test suite

`test/plugin.test.mjs` is meant to be copied. It runs at both of the SDK's
levels:

- **Level 1** — `Harness.create(app)`, in process, no socket. Every tool, the
  action, the config handling, `assertSchemaAccepts` / `assertSchemaRejects`,
  a `RecordingHost` with `setVariable` made to fail on purpose (so a step that
  could not publish its variable does not report success), and
  `h.fuzzConfig()`, which pushes eleven shapes of real-world config through
  `onConfigChanged`.
- **Level 2** — `MockDaemon`, a real gRPC handshake with a real session token,
  asserting the capabilities this plugin registers with are the ones
  `plugin.toml` declares and that a tool answers correctly over the wire.

## Files

- `src/plugin.ts` — the plugin, as a value. Read it alongside `../text-utils`
  and `../dice-roller` to see the same three capabilities in three languages.
- `src/index.ts` — the two-line entrypoint.
- `test/plugin.test.mjs` — the reference suite.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
