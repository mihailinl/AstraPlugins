# Troubleshooting

Keyed to the strings the CLI and the daemon actually print. If you have an error
in front of you, search this page for a fragment of it.

## Start here

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

Fifteen checks, each phrased as the question it answers. It knows which CLI you
are running, which config directory it resolved, whether the daemon is
reachable, which toolchains you have, whether your manifest parses, whether the
entry point exists, whether your permissions cover your capabilities, whether
your `[platform]` block is right, and whether your release workflow is pinned.
Every failure carries a `fix:` line. In a project you have not built yet it
exits non-zero on one of them — `Will the daemon find something to start? …
does not exist` — which is correct: nothing has produced the binary yet.

## The project does not resolve its SDK

**`error: failed to select a version for the requirement astra-plugin-sdk = "^0.6"`**
**`ERROR: No matching distribution found for astra-plugin-sdk<0.6,>=0.5`**
**`error: No version matching "^0.5.0" found for specifier "astra-plugin-sdk" (but package exists)`**

Three languages, one cause: `astra-plugin new` pins the SDK version this
documentation describes, and the registries still carry the previous one —
crates.io 0.5.0, PyPI 0.4.0, npm 0.4.0. Nothing is misconfigured on your
machine, and neither `doctor` nor `check` will mention it, because both read the
manifest and the pin lives in the language's build file. Point the project at
this repository's copy of the SDK; the three fragments are in
[Getting started §2](../2-tutorial/getting-started.md). Do not relax the bound
instead: 0.6 is the first Rust release whose `HostClient` attaches
`x-session-token`, so an older SDK trades this error for `unauthenticated` on
every host call — the section below.

## The plugin will not start

**`Could not read /…/astra/daemon.token. Astra does not look like it is running — start the app first.`**
Exactly what it says. `dev`, `logs` and installing need a running Astra; `new`,
`build`, `check`, `test`, `sign` and `publish` do not. If Astra *is* running,
it resolved a different config directory than the CLI did — compare the path
`doctor` prints with the one Astra shows in its settings.

**The daemon reaped the process at startup.** The budget is
`plugin_start_timeout_secs` = **20 s** to the first line of output. A Python
plugin that imports a large ML stack at module scope can miss it; import lazily
inside the hook that needs it. `astra-plugin test` measures this and prints the
number:

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
```

**The plugin starts and immediately dies.** Check `astra-plugin logs -f` first;
if there is nothing there at all, the process is failing before the SDK
installs its logging. Run the binary by hand — `astra-plugin dev --standalone`
does that and tells you what it cannot do that way.

**`HealthCheck` errors mark the plugin dead.** It runs every 15 s and is not
routed through the daemon's optional-hook helper: *any* error, including
`UNIMPLEMENTED`, means dead. If you overrode `health_check`, make sure it
cannot throw.

## A host call comes back `permission_denied`

The message names the permission and where the granted set came from. Three
causes, in order of likelihood:

1. **You did not declare it.** `[permissions]` is default-deny. Declaring
   `[capabilities] event_handlers = true` does not buy `SubscribeEvents`;
   `[permissions] subscribe_events` does.
2. **The user did not grant it**, or the install path capped it. A
   [locally imported file](../5-publish/local-install.md) has
   `send_chat_message`, `set_theme_contribution`, `dom_access` and `client`
   refused outright.
3. **You are signed out or the app is locked.** Astra refuses plugin RPCs in
   both states, and the CLI says so: *"Astra refuses plugin RPCs while signed
   out or locked — sign in and unlock the app, then try again."*

`astra-plugin doctor` answers 1 without running anything:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## A host call comes back `unauthenticated`

Every `PluginHostService` call except `Register` must carry the session token in
`x-session-token`. All three SDKs attach it — **from 0.6 in Rust, 0.5 in Python
and TypeScript**. Against an older SDK every host call fails this way, which is
why the scaffold's dependency bound does not go lower.

`astra-plugin test` asserts it end to end:

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`
```

## Sideloading is refused

**`Sideloading is disabled.`** `safety.allow_unsigned_plugins` is off. Read
[what turning it on costs](../5-publish/sideload.md) before you do.

**`Refusing sideload marker in …: this daemon never authorised a sideload of …`**
Somebody hand-planted a `sideload.json`. That has not worked since the daemon
started keeping its own record of what it authorised. Use `astra-plugin dev`.

## An install is refused

Every verification failure on the registry path is a **hard block with no
override**, and each names which of two things happened.

| What you see | What it means |
|---|---|
| The downloaded file does not match what the registry signed | `DIGEST_MISMATCH` — the download was discarded. Report it |
| Astra could not verify the plugin catalogue's signature | `SIGNATURE_INVALID` — the store is disabled rather than falling back to unverified data |
| This update comes from a different repository than the one you installed from | `IDENTITY_CHANGED` — no override, ever. Only an uninstall clears the pin |
| The plugin was withdrawn | `REVOKED` — with the advisory and one-click uninstall. Files are never deleted silently |
| This bundle is for another platform | `PLATFORM_UNSUPPORTED` |
| This plugin needs a newer Astra | `PROTOCOL_UNSUPPORTED` |
| Network, or your clock is wrong | Retryable, and worded as such. These must never look like a verification failure |

**`nothing here vouches for these bytes`** on a local file: install it from the
Plugins page instead, or read [local install](../5-publish/local-install.md) for
what importing it costs.

Today the trust chain is **not anchored** — the root keys exist, but no
root-signed `trust.json` delegates an index-signing key yet, so there is nothing
to check a catalogue signature against. A catalogue therefore classifies as
unsigned and revocation is not enforced. See
[`spec/registry-index.md` §0.1](../spec/registry-index.md).

## A tool call fails in a way the model cannot fix

Use the right code; that is what the model reads.

| Code | Say this when |
|---|---|
| `BAD_ARGUMENTS` | Retrying with different arguments could work |
| `NOT_CONFIGURED` | A setting is missing — **and set `config_field`**, which is what turns the error into a link to that exact input |
| `UNAUTHORIZED` | A value is present and was refused. Different from `NOT_CONFIGURED` |
| `RATE_LIMITED` | With `retry_after_ms` when the upstream said one |
| `UNAVAILABLE` / `TIMEOUT` | Transient. A later identical call may work |
| `INTERNAL` | A bug. Nothing the model can act on |

`UNIMPLEMENTED` is **not** an error: it means "this hook is absent", and the
daemon reads it that way. Returning it because your TTS crashed makes the daemon
believe you have no TTS. Full taxonomy:
[`reference/errors.md`](../reference/errors.md).

## `astra-plugin check` complains

**`config.schema is not valid JSON`** or **`should have "type": "object" at
root`** — the settings form is generated from that schema.

**An unknown key in `[capabilities]` fails the whole manifest.** That section is
the one place unknown keys are refused, because every key is an opt-in boolean
and a typo would otherwise read exactly like `false`. `ui_panels` is the classic:
it is `ui_contributions`, and three shipped examples declared nothing at all for
months because of it.

**An unknown `[permissions]` id is kept and warned about**, not refused — new
ids ship with new Astras, and the permissions block is hashed byte-for-byte by
three implementations, so dropping a key would make them disagree about what
was signed.

`astra-plugin check --fix` applies what it can prove and reports the rest.

## The CLI prints nothing useful

`RUST_LOG` works now — it was documented since 0.1 and inert until a subscriber
was installed:

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

Trace goes to **stderr**, so `--json` on stdout stays a clean single document.

## Exit codes

| | |
|---|---|
| `0` | success |
| `1` | the plugin or the bundle is wrong |
| `2` | the CLI could not run the check — a missing file, a missing toolchain |

The split is load-bearing: a release workflow that treats "the bundle is bad"
and "I could not look" the same ships one of them.

## Still stuck

- [Logs](logs.md) — where they are, per OS
- [Performance](performance.md) — timeouts and the numbers behind them
- [Examples](../7-examples/README.md) — eleven working plugins, several of which
  exercise the path you are debugging
