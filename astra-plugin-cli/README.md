# astra-plugin-cli

The `astra-plugin` command: scaffold, run, test, build, release and list a
plugin for Astra.

Repository: <https://github.com/mihailinl/AstraPlugins>

## Install

The crate is `astra-plugin-cli`; the binary it installs is **`astra-plugin`**.

**Today, building from source is the only way to get it.** There are no
releases yet — verified: `gh release list --repo mihailinl/AstraPlugins` prints
nothing and no `cli-v*` tag exists — and the crate is not on crates.io either
(`https://index.crates.io/as/tr/astra-plugin-cli` answers `404`). So you need a
Rust toolchain. The release automation that will end that is in this repository
already, at `.github/workflows/release-cli.yml`; **[Prebuilt
binaries](#prebuilt-binaries--from-the-first-cli-v-tag-onward)** below describes
what it will publish, and applies from the first `cli-v` tag onward, not before.

### From source (the only path that works today)

You need Rust **1.85 or newer** (`edition = "2024"`), and `protoc` on PATH — the
crate depends on `astra-plugin-sdk`, whose `build.rs` compiles
`proto/plugin.proto` with tonic-build and shells out to a real `protoc`.

One line, no clone:

```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

Or from a clone, if you want to read the CLI as well as run it:

```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

Both build whatever `master` carries when you run them, so the version they
print is that commit's, not one you picked. `master`'s `Cargo.toml` currently
says `0.2.0` even though this crate's newest changelog entry is `0.2.1` — the
version is bumped on the branch that will release it, so do not treat the number
as a health check. What matters is the fix commit `5b8ab22`: any `master` build
has it. To confirm, run `astra-plugin init-ci` and read the SHA it pins —
`e3329df252a46d747676cb540ae4b986af68a3ad` is the commit and is right,
`dc1a044876926e9cf1170f034e2eab533ec07641` is the `plugin-release/v1` tag object
and is the bug that broke first releases.

**`cargo install astra-plugin-cli` does not work**, and will not until the
manifest crate this one parses `plugin.toml` with is published. `plugin.toml` is
parsed by the daemon's own `astra-plugin-manifest`, vendored into
`vendor/astra-plugin-manifest/` (see [below](#where-the-manifest-types-come-from)
for why), and cargo does not package a path dependency's source — verified with
`cargo package --list`, in which `vendor/` does not appear. So the published
tarball would name a crate that is not on crates.io.

### Prebuilt binaries — from the first `cli-v` tag onward

**None of this applies yet.** It describes what
`.github/workflows/release-cli.yml` publishes once a `cli-v<version>` tag is
pushed; until then <https://github.com/mihailinl/AstraPlugins/releases> is
empty, and every command below would 404. Check the releases page before
following any of it.

Once a release exists it is tagged `cli-v<version>` and carries five files on a
public repository — the three archives, their digests, and the attestation
bundle (a private or internal fork cannot publish to the transparency log, so it
gets four):

| Asset | For |
|---|---|
| `astra-plugin-<version>-linux-x64-musl.tar.gz` | **Any x86-64 Linux.** Statically linked, no libc requirement. Take this one if unsure. |
| `astra-plugin-<version>-linux-x64-gnu.tar.gz` | x86-64 Linux with glibc **2.39 or newer** (Ubuntu 24.04+), built against the same libc as the Astra daemon |
| `astra-plugin-<version>-windows-x64.zip` | Windows x86-64 |
| `SHA256SUMS.txt` | The digest of each of the three |
| `astra-plugin-<version>.sigstore.jsonl` | The build attestation, for verifying offline or from a mirror |

Each archive holds the binary plus `LICENSE`, `NOTICE` and this README, under a
single top-level directory named after the archive.

Linux:

```bash
V=<version>        # the tag is cli-v$V — see the releases page
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v$V/astra-plugin-$V-linux-x64-musl.tar.gz
tar -xzf astra-plugin-$V-linux-x64-musl.tar.gz
sudo install -m 0755 astra-plugin-$V-linux-x64-musl/astra-plugin /usr/local/bin/astra-plugin
astra-plugin --version          # astra-plugin $V
```

Swap `-musl` for `-gnu` if you would rather have the glibc build. The musl one
is static, so it runs on Debian 12, Ubuntu 22.04, RHEL 9 and Amazon Linux 2023,
none of which have the glibc 2.39 the `-gnu` archive needs.

Windows (PowerShell):

```powershell
$V = "<version>"
Invoke-WebRequest -Uri "https://github.com/mihailinl/AstraPlugins/releases/download/cli-v$V/astra-plugin-$V-windows-x64.zip" -OutFile astra-plugin.zip
Expand-Archive astra-plugin.zip -DestinationPath $HOME\astra-plugin
$env:Path += ";$HOME\astra-plugin\astra-plugin-$V-windows-x64"
astra-plugin --version
```

That `$env:Path` line lasts for the session. To keep it, add the same directory
under **Settings → System → About → Advanced system settings → Environment
Variables**.

Checking what you downloaded:

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing
gh attestation verify astra-plugin-<version>-linux-x64-musl.tar.gz --repo mihailinl/AstraPlugins
```

The attestation names the repository, workflow and commit the archive was built
from, over the sha256 of the whole file. It proves where the file came from. It
does not prove the code is safe.

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

`publish` targets `mihailinl/astra-registry`, which is public and open for
submissions. (An earlier note here said that repository returned 404. It does
not — checked with `gh repo view mihailinl/astra-registry`.)

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

## Releasing this CLI (maintainers)

`.github/workflows/release-cli.yml` builds and publishes every binary above. A
tag is the whole process:

```bash
# set version = "0.2.2" in astra-plugin-cli/Cargo.toml
git commit -am "cli 0.2.2"
git tag cli-v0.2.2 && git push origin cli-v0.2.2
```

The `cli-` prefix is not decoration: this repository also releases plugins under
`v*` and SDKs under their own tags, so `v0.2.2` is already taken.

The tag must match `astra-plugin-cli/Cargo.toml`, and the workflow asserts that
before it builds anything — then asserts a third time that the binary it is
about to archive answers `--version` with the same number. 0.2.0 shipped a
broken `init-ci`, the fix shipped, and `astra-plugin --version` said `0.2.0` on
both sides of it; that is the failure those three checks exist to end.

Read the header comment in that file before the first run — it lists the one
secret a maintainer has to create (`CARGO_REGISTRY_TOKEN`, for crates.io only)
and why the crates.io step is inert until the manifest crate is published.

## License

**GPL-3.0-or-later** — see [LICENSE](LICENSE). Nothing links this tool, so it
carries the stronger copyleft: fork it and your changes ship under the same
terms.

The SDKs it scaffolds against are MPL-2.0, so the plugins you build with it are
yours under any licence you like.

Redistribution must preserve the attribution in [NOTICE](NOTICE), an additional
term under GPL-3.0 section 7(b).

Copyright (C) 2026 Minice — https://minice.ai
