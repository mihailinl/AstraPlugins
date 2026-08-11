# astra-plugin-cli

The `astra-plugin` command: scaffold, run, test, build, release and list a
plugin for Astra.

Repository: <https://github.com/mihailinl/AstraPlugins>

## Installing today

**Not on crates.io.** `index.crates.io` has no entry for `astra-plugin-cli`, so
`cargo install astra-plugin-cli` fails. Build it from this repository:

```bash
git clone -b feat/plugin-production https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli
astra-plugin --version          # must print 0.2.0
```

> **The branch matters.** A bare `git clone` checks out the default branch,
> where this crate is **0.1.3** and its whole command set is `create`, `dev`,
> `build`, `validate`, `keygen` — none of the commands in the table below exist
> there. Verified with `git show master:astra-plugin-cli/src/main.rs`.
> `feat/plugin-production` is not pushed yet (`git ls-remote origin`), so for
> now this means a local checkout of that branch. Delete this note once it is
> the default.

Verified against this checkout. The crate is `astra-plugin-cli`; the binary it
installs is **`astra-plugin`**. `edition = "2024"`, so Rust 1.85 or newer, and
`protoc` must be on PATH — the crate depends on `astra-plugin-sdk`, whose
`build.rs` compiles `proto/plugin.proto` with tonic-build and calls an external
`protoc`.

There is **no `astra-plugin login`**. Nothing here holds a credential or uploads
a file — see [Release](#release) below for why that is a design choice rather
than a missing feature.

## Commands

| Command | What it does |
|---|---|
| `new <NAME>` | Scaffold a project. `--lang rust\|python\|typescript`, `--template tool\|tts\|stt\|stt-streaming\|ai-provider\|ui\|action-trigger\|client\|blank`, `--capabilities`, `--output` |
| `dev [PATH]` | `check --strict`, build, ask the running Astra to sideload the plugin, hot-reload on edit. `--daemon-addr`, `--standalone` |
| `check [PATH]` | Manifest, config schema and release workflow. `--strict`, `--fix`, `--resolve-pin` |
| `test [PATH]` | The conformance suite, against a real plugin process. `--no-build`, `--report` |
| `doctor [PATH]` | Why it will not start: toolchains, daemon, manifest, entry point, permissions, platform block, release workflow. `--daemon-addr` |
| `logs [PLUGIN_ID]` | The plugin's output, from the daemon that spawned it. `-f`, `-n`, `--path`, `--daemon-addr` |
| `build [PATH]` | Pack a `.astraplugin`. `--target linux-x64\|windows-x64\|noarch`, `--all-targets`, `--reproducible`, `-o` |
| `verify <FILE>` | Verify a built bundle and print its digests |
| `version <VERSION> [PATH]` | Set the version in `plugin.toml` and every other manifest at once. `--allow-downgrade` |
| `init-ci` | Write `.github/workflows/release.yml`, pinned to a commit of the reusable workflow. Idempotent — re-run it to upgrade the pin, it keeps your inputs |
| `publish [PATH]` | Preflight a release, or open a prefilled listing request. `--dry-run`, `--notify`, `--repo`, `--print-url` |
| `sign <FILE>` | Append the **retiring** in-ZIP `SIGNATURE`/`PUBKEY` pair. `--key` |
| `keygen` | Generate the **optional** Ed25519 keypair `sign` uses |

Every command takes `--json` and prints one JSON document with progress
suppressed, so the output is safe to pipe.

Exit codes: **0** success · **1** the plugin or bundle is wrong · **2** the CLI
could not run the check. `RUST_LOG` controls trace output, e.g.
`RUST_LOG=astra_plugin=debug`.

## The loop

```bash
astra-plugin new my-plugin
cd my-plugin
astra-plugin dev .
```

`dev` talks to the daemon at the address it wrote to `<config>/daemon.port`,
defaulting to `127.0.0.1:32000`. It runs `check --strict` first, then asks the
daemon to sideload the directory, so the **daemon** owns the process and mints
its session token. `--standalone` spawns the process yourself instead, and the
plugin then cannot register with Astra at all — the command says so.

Hand-writing a `sideload.json` marker does not work: the daemon refuses any
marker it did not record itself, and requires Developer Mode at load time.

```bash
astra-plugin test .
```

runs the conformance suite: it starts the plugin the way the daemon does,
against a mock daemon serving `PluginHostService`, and calls every inbound hook
the manifest's capabilities imply. A hook `spec/hooks.yaml` marks `required` may
not answer `UNIMPLEMENTED`; an `optional` one may, because on the wire
`UNIMPLEMENTED` *is* an absent hook.

## Release

```bash
astra-plugin init-ci
astra-plugin version 0.2.0
git tag v0.2.0 && git push --tags
```

`init-ci` writes about nine lines that call the reusable
`.github/workflows/plugin-release.yml` in `mihailinl/AstraPlugins`. That
workflow owns every real decision — matrix, toolchain, gates, attestation,
upload — so a fix there reaches every plugin at its next pin bump.

The `uses:` line is pinned **by commit SHA**, not by `@v1`, because a movable
tag in someone else's repository selects a job that runs inside *your*
repository with *your* `contents: write` token. The SHA is resolved with
`git ls-remote` when the file is written, not compiled into the binary — a CLI
installed a year ago would otherwise pin a year-old workflow and call it
current.

The caller must grant `contents`, `id-token` and `attestations`; a called
workflow can only reduce what the caller granted, so `check` refuses a caller
that omits one rather than letting the run fail after the build.

## Getting listed

```bash
astra-plugin publish --dry-run   # every registry check that can run locally
astra-plugin publish             # opens a prefilled listing request
astra-plugin publish --notify    # a release ping for a plugin already listed
```

**This command never uploads a bundle and never holds a credential.** The
artifacts are GitHub Release assets your CI attached and attested; the registry
reads them from your repository and verifies every one from scratch. So a
submission carries only `owner/repo` and a tag — which is exactly why it can be
a URL you open in a browser you are already signed in to, rather than a token
this program would have to be trusted with.

**The registry repository does not exist yet.** `publish` targets
`mihailinl/astra-registry`, which returns 404 today. `--dry-run` is fully
useful now; the submission URL is not.

## About `sign` and `keygen`

`sign` is an **optional second factor, not a trust signal.** Astra checks the
in-ZIP `SIGNATURE`/`PUBKEY` pair against a pinned Astra publisher key, so a
bundle signed with your own key is untrusted exactly as an unsigned one is. What
makes Astra install a plugin is the registry record countersigning
`sha256(whole file)`. Both this command and the format entries it writes are
removed in a future release. `build` does not sign and does not claim that a
local key confers trust.

## Where the manifest types come from

`plugin.toml` is parsed by `astra-plugin-manifest` — the daemon's own crate,
**vendored** into `vendor/astra-plugin-manifest/` rather than published, with
`tools/check-manifest-crate.sh` failing when the copy drifts. This CLI used to
keep its own struct; it grew a `ui_panels` capability the daemon never had,
serde dropped the unknown key, and three shipped examples ended up declaring no
capabilities at all. `[capabilities]` is now `deny_unknown_fields`, so a typo is
an error that names the correct key.

`astra-plugin test` reuses `astra_plugin_sdk::testing::MockDaemon` — the same
service, the same session-token gate, the same permission gate the SDK's own
`WireHarness` runs against — rather than a second mock that could drift.

## License

**GPL-3.0-or-later** — see [LICENSE](LICENSE). Nothing links this tool, so it
carries the stronger copyleft: fork it and your changes ship under the same
terms.

The SDKs it scaffolds against are MPL-2.0, so the plugins you build with it are
yours under any licence you like.

Redistribution must preserve the attribution in [NOTICE](NOTICE), an additional
term under GPL-3.0 section 7(b).

Copyright (C) 2026 Minice — https://minice.ai
