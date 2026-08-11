# Performance and limits

Every number on this page is declared once, in a file, and generated into the
places that need it. None of them is a guess.

## The shared limits

[`spec/limits.yaml`](../../../spec/limits.yaml) is the one place a number that
must be identical in the daemon and in the SDKs is written down. `node
tools/gen-limits.mjs` regenerates the constants in all three SDKs, and a
`const _: () = assert!(…)` next to the daemon's copy fails to build until the
daemon moves too. The motivating bug: the streaming-STT audio channel was 500 in
the daemon and 32 in the Rust SDK, and the mismatch silently truncated every
utterance to its first fraction.

| Limit | Value | What it bounds |
|---|---|---|
| `plugin_start_timeout_secs` | **20** | From spawn to the plugin's first line of output. Miss it and the daemon calls the start a failure and reaps the process |
| `plugin_stop_grace_secs` | **5** | From `Shutdown` to the process group being killed. Your own drain budget must be under this, or the daemon kills you before your tidy path runs |
| `stt_audio_channel_capacity` | **500** | Chunks buffered between the daemon's voice pipeline and your `stt` hook, at both ends. ~10 s of audio: the worst-case wake-word seed burst plus live audio arriving while a slow provider is still inferring |
| `max_extract_bytes` | **524 288 000** (500 MiB) | Total uncompressed size the daemon will extract from one archive |
| `max_archive_entries` | **10 000** | Entries in one archive |

The last two are zip-bomb mitigation, and they are also a packaging constraint:
a bundle over either makes an uninstallable plugin, so the CLI refuses at build
time rather than letting you discover it on a user's machine.

## `call_timeout_secs` — the one you set

`plugin.call_timeout_secs` in the manifest is how long the daemon waits for
`CallTool` and `ExecuteAction` before giving up. Unset, it uses the daemon's own
`PLUGIN_CALL_TIMEOUT`, which is deliberately lower than "forever".

**A plugin that fronts a long-running agent must declare it.** Otherwise the
daemon throws away your result while your subprocess keeps running — the user
sees a failure and the machine keeps doing the work.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "coding-agent"
name = "Coding Agent"
version = "0.1.0"
license = "MIT"
author = "You"
# This plugin runs an agent that can legitimately take minutes.
call_timeout_secs = 180

[entry]
command = "bin/coding_agent"

[capabilities]
tools = true
```

It is per-plugin, the same way an MCP server's timeout is per-server. Set it to
what your slowest legitimate call needs, not to the largest number you can
think of: the timeout is also what stops a wedged plugin from hanging a
conversation.

## Startup budget, by language

The 20 s is generous, and two of the three languages still manage to spend it.

| | Typical cold start | The thing that eats it |
|---|---|---|
| Rust | milliseconds | nothing |
| TypeScript | Node cold start | the bundle is a single file, so no module resolution over a tree |
| Python | interpreter + `grpcio` import | a large dependency imported at module scope |

The fix is the same in both interpreted cases: **import lazily, inside the hook
that needs it.** A model you load in `on_start` is a model the user waits for
before the plugin is alive; a model you load on the first call is one they wait
for once.

`astra-plugin test` measures the real number on your machine and prints it
against the budget:

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.5ms after Shutdown
         (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
```

## Shutting down inside the grace period

`Shutdown` is answered, and then you exit. Five seconds later the process group
is killed. Anything you must flush — a file, an upstream session — flushes
inside that window or not at all.

A daemon-wide shutdown passes a **much shorter** grace, bounded by the whole
teardown deadline. Do not treat 5 s as a budget you can spend; treat it as a
ceiling you should be well under.

## Health checks

`HealthCheck` runs every 15 s. It is not routed through the daemon's
optional-hook helper, so **any** error — `UNIMPLEMENTED` included — marks the
plugin dead. If you override it, make it cheap and make it total: a health check
that calls an upstream service turns that service's outage into your plugin
being marked dead.

## Bundle size

Nothing enforces a maximum beyond the extraction limits, but two things are
worth knowing:

- A Rust bundle is a stripped release binary and is typically a few megabytes.
- A TypeScript bundle ships **no** `node_modules` — `astra-plugin build`
  produces one self-contained CommonJS file, and CI asserts that nothing is left
  reaching for a module at runtime.

Reproducible packing (`--reproducible`) fixes entry order, mtime and
compression level so two builds of the same inputs are byte-identical. The
release workflow runs a canary on every release, which is what makes a third
party's rebuild meaningful.

## Where these numbers live

| Number | Declared in |
|---|---|
| The five above | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| `call_timeout_secs` | your `plugin.toml` — [reference](../reference/manifest.md) |
| Health-check interval, per-call timeout default | the daemon |
