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
| Max text length | `10000` | every tool refuses text longer than this, so a pasted log file cannot stall the plugin |

That label is not written in `plugin.toml`. The schema carries
`"$config.max_text_length.title"` and the daemon looks it up in `locales/` per
request — see **Languages** below.

A value that is not a number is logged and ignored rather than fatal: a config
hook has nowhere to report a failure, and refusing to start over one bad field
would take the whole plugin down.

## Languages

Ships **English, Russian and Ukrainian**, and is the worked example of `locales/`
from Python. Two things are translated, by two different mechanisms, and which
one a string belongs to is decided by *who renders it*:

| | Rendered by | Written as |
|---|---|---|
| The settings form's field label and help text | the **daemon**, per request, from the `locales/` copy it took at install | `"$config.max_text_length.title"` in `[config] schema` |
| The health line — `ok — 3 operations processed` | **this process**, at the moment it produces the sentence | `self.i18n.tn("health.ok", n, n=str(n))` |
| The store card | the **registry**, out of the bundle | the reserved `listing.name` / `listing.description` keys |

The health line is the reason `tn` and not `t`: it carries a count, which the
daemon cannot know, and Russian and Ukrainian need **four** forms of the counted
noun where English needs two. `astra-plugin locale add ru` writes exactly the
rows a language needs — `health.ok.one/few/many/other` for these two — and
`locales.lock.json` records which English each translation was made against, so
rewriting the English makes the translations report themselves stale instead of
quietly describing a sentence that no longer exists.

The action label, its field labels and its dropdown options are **deliberately
literal English**. Astra's current release resolves `$keys` inside
`[config] schema` and nowhere else, so a key there would reach the command
editor as the text `$action.transform.label`; `src/plugin.py` says so where the
labels are written, and one test in the suite holds the line.

The other seven languages are not translated and do not need to be: lookup falls
back per key to English, so a `de` user reads the English label and everything
works.

```bash
astra-plugin locale ls                 # what is shipped, and what is not
astra-plugin locale render --lang uk   # the settings form, without a daemon
astra-plugin locale check              # the locale rules alone
```

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
- `locales/en.json`, `locales/ru.json`, `locales/uk.json` — the translations:
  the two reserved `listing.*` keys the store card is drawn from, the config
  field's label and help text, and the `health.ok` plural family. Flat
  `string → string`, one file per language, beside `plugin.toml` — the daemon
  deserialises them into a string map and drops the whole file on a nested
  object. Written with `astra-plugin locale add`, never by hand.
- `locales.lock.json` — at the root and **not** inside `locales/`, because
  everything in `locales/` that ends in `.json` is a language. It records, per
  translated key, a digest of the English that translation was made against;
  `astra-plugin locale sync` derives it and `astra-plugin locale check` reads it
  back. See [the localisation page](../../docs/en/3-reference/localisation.md).
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
