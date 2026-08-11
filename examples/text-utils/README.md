# Text Utils

Word counts, case conversion, regex matching and a scheduled trigger.

## What it does

Three tools the assistant can use mid-conversation:

- **`word_count`** — words, characters and lines in a piece of text.
- **`case_convert`** — `upper`, `lower`, `title`, `snake` or `camel`.
- **`regex_match`** — run a regular expression over text and return every match
  with a count.

One **"Transform Text" action** for the command editor: uppercase, lowercase,
title case, reverse, Base64 encode and Base64 decode, on text from an earlier
step, with the result optionally stored in a variable.

One **"Scheduled Time" trigger**. Give it a time in `HH:MM` and any command
subscribed to it runs when the machine's local clock reaches that minute. The
check runs every 30 seconds and fires at most once per minute, so a command
never runs twice for the same tick. It only runs while Astra is running — this
is not a cron replacement, and a machine that is asleep at 09:00 misses 09:00.

## What it needs

- **Python 3.10 or newer** on the machine running Astra. Astra ships no Python
  runtime; the bundle declares `runtimes = ["python"]` so the daemon fails
  clearly if there is no interpreter instead of dying at startup.
- The dependencies in `requirements.txt` (`astra-plugin-sdk`, `grpcio`,
  `protobuf`).

No network, no account.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `tools` | Astra's assistant may call the plugin during a conversation | The three text tools |
| `actions` | The plugin contributes steps to the command editor | "Transform Text" |
| `triggers` | The plugin can start your commands | "Scheduled Time" |

The regex tool runs a pattern you supply against text you supply, in the plugin
process. A pathological pattern can make that process spin — it will not take
Astra down with it, but the plugin will stop answering until you restart it.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| Max Text Length | `10000` | every tool refuses text longer than this, so a pasted log file cannot stall the plugin |

A value that is not a number is logged and ignored rather than fatal: a config
hook has nowhere to report a failure, and refusing to start over one bad field
would take the whole plugin down.

## Testing it — the reference suite

`tests/test_text_utils.py` is the worked example for testing a Python Astra
plugin, and is worth reading before writing tests for your own:

```bash
pip install -e '.[dev]'      # astra-plugin-sdk[test] — pytest and the harness
pytest
```

It uses both levels of `astra_plugin_sdk.testing`:

- **Level 1**, `astra_harness`, drives the plugin through its own gRPC servicer
  in-process. That is not the same as calling the method: it goes through tool
  registration, the JSON round-trip, the schema, and the error taxonomy — which
  is where plugins actually break. `RecordingHost` records everything the plugin
  asked Astra for, and `fail_next` makes the "Astra said no" branch reachable at
  all. Without it, the path a plugin takes when `fire_trigger` is denied for a
  missing `[permissions]` entry is untested by construction.
- **Level 2**, `astra_wire`, runs the plugin's real `run()` against a mock
  daemon over loopback gRPC — registration, the protobuf descriptor, the
  capability interceptor, the `x-session-token` on every host call. One test, at
  the end, because it catches a class of bug level 1 structurally cannot see.

The last test in the file breaks the plugin on purpose — one tool loses its
`@tool` decorator — and shows the suite catching it. A test suite nobody has
watched fail is a test suite nobody should trust.

## Build it yourself

```bash
cd examples/text-utils
pip install -r requirements.txt
astra-plugin build            # produces text-utils-<version>-noarch.astraplugin
```

The bundle is `noarch`: the plugin is pure Python, and the platform-specific
part is the interpreter, which comes from the user's machine.

## Files

- `src/plugin.py` — the whole plugin. The `@tool` / `@action` / `@trigger`
  decorators register everything; there is no manual wiring to read.
- `tests/test_text_utils.py` — the reference suite, above.
- `conftest.py` — three lines, so `src.plugin` imports from `tests/` the same
  way the daemon imports it.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
