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
bun install                   # or npm install
bun run build                 # esbuild bundles src/index.ts to dist/index.js
astra-plugin build            # produces json-tools-<version>-noarch.astraplugin
```

The bundle is `noarch`: one file that runs on every platform Astra supports,
because the platform-specific part is the Node install, not the plugin.

## Files

- `src/index.ts` — the whole plugin. Read it alongside `../text-utils` and
  `../dice-roller` to see the same three capabilities in three languages.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
