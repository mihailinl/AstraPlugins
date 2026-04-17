# `plugin.toml` reference

Every plugin declares itself in a `plugin.toml` manifest at the root of its project. This file tells the daemon how to launch the plugin, which capabilities it implements, and what configuration it accepts.

## Complete example

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"
description = "Word count, case conversion, regex matching"
author = "Astra Team"
license = "MIT"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
tts = false
stt = false
ai_provider = false
client = false
ui_contributions = false
event_handlers = false

[config]
schema = """
{
  "type": "object",
  "properties": {
    "max_text_length": {
      "type": "number",
      "default": 10000,
      "title": "Max Text Length"
    }
  }
}
"""
```

## `[plugin]` — metadata

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | yes | Lowercase alphanumeric with hyphens. Uniquely identifies the plugin. |
| `name` | string | yes | Display name shown in the Plugins UI. |
| `version` | string | yes | Semantic version (`X.Y.Z`). Used for upgrade detection. |
| `description` | string | recommended | Short summary. Shown in the Plugins UI. |
| `author` | string | recommended | Author or organisation name. |
| `license` | string | recommended | SPDX license identifier (`MIT`, `Apache-2.0`, …). |

## `[entry]` — how to launch the plugin

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `command` | string | yes | Executable to invoke. For Rust this is the compiled binary path; for Python `"python"`; for TypeScript `"node"`. |
| `args` | string array | no | Arguments prepended to `--daemon-addr`, `--plugin-id`, `--auth-token`. Typical values: `["-m", "src.plugin"]` for Python or `["dist/index.js"]` for Node. |
| `runtimes` | string array | no | Hint for the daemon. Supported: `"python"`, `"node"`, `"rust"`. Python/Node plugins should always set this so the daemon can prepare the runtime (e.g. create a `uv` venv for Python). |

The daemon appends `--daemon-addr <addr> --plugin-id <id>` to every launch, and optionally `--auth-token <token>` for client plugins.

## `[capabilities]` — what the plugin implements

Each field is a boolean defaulting to `false`. Set to `true` only for capabilities your code actually handles — the daemon uses this to allocate resources and decide whether to surface the plugin in relevant UI (e.g. add its voices to the TTS picker).

| Capability | Purpose |
| --- | --- |
| `tools` | AI tools callable by the chat model. |
| `tts` | Text-to-speech voice provider. |
| `stt` | Speech-to-text language provider. |
| `ai_provider` | Alternative AI completion backend. |
| `actions` | Custom action types in the Command Graph. |
| `triggers` | Custom trigger types in the Command Graph. |
| `client` | Full daemon client (requires session token). |
| `ui_contributions` | UI pages, overlays, effects, slot injections. |
| `event_handlers` | Subscribe to daemon event stream. |

See [Capabilities](capabilities.md) for full behaviour per capability.

## `[config]` — user-facing settings

```toml
[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "Token for the remote service",
      "x-secret": true
    },
    "timeout_ms": {
      "type": "number",
      "default": 5000,
      "minimum": 100,
      "maximum": 60000,
      "title": "Timeout (ms)"
    },
    "mode": {
      "type": "string",
      "enum": ["fast", "accurate"],
      "default": "fast",
      "title": "Mode"
    }
  },
  "required": ["api_key"]
}
"""
```

Rules:

- `schema` is a **JSON Schema string**. The root must have `"type": "object"`.
- The daemon renders the schema as a form in the plugin settings page.
- `title` provides the field label; `description` is shown as help text.
- `default` supplies the initial value.
- `x-secret: true` masks the value in the UI and stores it encrypted.
- `enum` renders as a dropdown.
- `required` array marks mandatory fields.
- When the user updates settings the daemon calls `OnConfigChanged` with the new JSON blob.

## Non-schema TOML fields

Plugins can add arbitrary top-level sections the daemon ignores — useful for tooling. The CLI warns about unknown fields but does not reject them.

## Localising the manifest

You can ship `locales/<lang>.json` files inside the plugin bundle to translate user-facing strings (`name`, `description`, action labels, field labels, etc.). Use the `I18n` helper in each SDK to read them from your code. Only manifest **text** is localised — keys, IDs, and enum values stay constant.

## Validating the manifest

```bash
astra-plugin validate
```

Checks:

- Required fields present (`plugin.id`, `plugin.name`, `plugin.version`, `entry.command`).
- `plugin.id` matches lowercase alphanumeric + hyphens.
- `plugin.version` matches SemVer (`X.Y.Z`).
- At least one capability is enabled.
- `[config].schema` parses as JSON and has `"type": "object"` at root.
- Metadata (description, author) present.

See [CLI reference → validate](cli.md#astra-plugin-validate).
