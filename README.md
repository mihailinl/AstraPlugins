# AstraPlugins

Everything needed to write, test, build and publish a plugin for Astra: three
SDKs, one CLI, the protocol they all speak, and eleven worked examples.

Canonical repository: **<https://github.com/mihailinl/AstraPlugins>**. Every
`repository`, `homepage` and `documentation` field in this tree points there. If
you found this project under any other name, that name is stale — two others
were in circulation and neither resolves.

---

## What a plugin is

A plugin is a **separate process** that Astra's daemon starts and talks to over
gRPC on loopback. Two services run in opposite directions:

- `PluginCapabilityService` — **daemon → plugin**. Your plugin serves it; Astra
  calls in to list your tools, synthesize speech, transcribe audio, hand you an
  event.
- `PluginHostService` — **plugin → daemon**. Astra serves it; your plugin calls
  out to log, fire a trigger, set a variable, push to the UI.

35 hooks across the two, protocol version 1, one source of truth in
[`spec/hooks.yaml`](spec/hooks.yaml). All three SDKs implement all 35 — see
the generated hook-parity page under [`docs/en/`](docs/en/README.md), which
`tools/parity` renders from that file and CI drift-checks.

### What a plugin can do

Ten capabilities. A plugin declares the ones it implements in `[capabilities]`
in its `plugin.toml`; the list is closed, and an unknown key is a hard parse
error rather than a silently-dropped line
(`astra-plugin-cli/vendor/astra-plugin-manifest/src/capabilities.rs`).

| Capability | What your plugin gets to do |
|---|---|
| `tools` | Add tools the assistant can call mid-conversation |
| `actions` | Add steps to the command editor |
| `triggers` | Define trigger types a user's command can start from |
| `tts` | Be a text-to-speech provider |
| `stt` | Be a speech-to-text provider, one-shot or streaming |
| `ai_provider` | Be a completion backend |
| `client` | Be a chat front-end of your own, with its own session |
| `ui_contributions` | Add pages, panels and overlays to the Astra window |
| `event_handlers` | Subscribe to daemon events |
| `dom_access` | Run your own JavaScript **inside** the Astra window |

### What a plugin may do

Capabilities are the inbound direction only. The outbound direction —
which host RPCs your plugin is allowed to call — is `[permissions]`, and it is
**default-deny**. Of the ten host RPCs, four are always allowed (`Register`,
`GetPluginSelfConfig`, `PluginLog`, `GetDaemonInfo`) and six are gated on a
consented permission; two more permissions (`dom_access`, `client`) gate a
surface rather than a call. The table lives in the daemon at
`astra-daemon/src/plugins/host_service.rs` (`HOST_RPC_PERMISSIONS`) and a test
there fails if a new host RPC ships ungated.

Eight permission ids, each with a `reason` you write and the user reads on the
install consent sheet: `fire_trigger`, `subscribe_events`, `set_variable`,
`send_chat_message`, `push_to_ui`, `set_theme_contribution`, `dom_access`,
`client`.

### What a plugin is **not**

**There is no sandbox.** A plugin is a native process running with your full
user privileges: your files, your network, your session. Signatures answer *who
built this*; permissions answer *what the daemon will do on its behalf*. Neither
answers *what the process can do to the machine*. Isolation is planned work
(Phase 7 of [`PRODUCTION_PLAN.md`](PRODUCTION_PLAN.md)) and none of it exists
today. Install plugins the way you install any other native program — from
someone you are willing to run code from.

---

## Where to start

### 1. Get the CLI

`astra-plugin-cli` is **not on crates.io** and there are **no prebuilt
binaries** — verified today: `https://index.crates.io/as/tr/astra-plugin-cli`
answers `404` where `astra-plugin-sdk` answers `200`, and
`gh release list --repo mihailinl/AstraPlugins` prints nothing. So installing it
means building it, which means a Rust toolchain. Prebuilt `linux-x64` and
`windows-x64` binaries are a known, separate, pending task.

One line, no clone:

```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version          # astra-plugin 0.2.1
```

`--git` builds whatever `master` currently carries, and installs it as
`astra-plugin-cli v0.2.1 (https://github.com/mihailinl/AstraPlugins#<sha>)`.

**Take 0.2.1 or newer.** `0.2.0`'s `init-ci` pinned an annotated tag's object
SHA instead of the commit it names, so every first release died with `invalid
value workflow reference` before a job started ([#2]). `0.2.1` fixes exactly
that and changes nothing else — it is a version bump so that a fixed build can
be told from a broken one, which `0.2.0` could not be, having shipped on both
sides of the fix. If `--version` says `0.2.0`, re-run the line above and then
`astra-plugin init-ci`; the pin is not repaired in place.

[#2]: https://github.com/mihailinl/AstraPlugins/issues/2

From a clone instead, if you want to read the CLI as well as run it:

```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
```

A bare `git clone` checks out `master`, and `master` carries the current CLI —
there is no branch you need to know about.

Building needs Rust 1.85+ **and `protoc` on PATH** — the CLI depends on
`astra-plugin-sdk`, whose `build.rs` compiles `proto/plugin.proto` with
tonic-build, which calls an external `protoc`. `apt install protobuf-compiler` /
`pacman -S protobuf` / `brew install protobuf` / `winget install
Google.Protobuf`.

Every crate here is `edition = "2024"`, so the floor is whatever Rust first
supported that edition — 1.85. No crate declares a `rust-version`, and CI builds
on `stable`, so that is the only bound that is actually enforced. The installed
binary is called `astra-plugin`, not `astra-plugin-cli`.

Longer version, including what to do when it does not work:
[`docs/en/install-cli.md`](docs/en/install-cli.md).

### 2. Scaffold

```bash
astra-plugin new my-plugin              # Rust
astra-plugin new my-plugin --lang python
astra-plugin new my-plugin --lang typescript
```

The Rust scaffold is 15 lines and one dependency:

```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct MyPlugin;

#[astra::plugin]
impl MyPlugin {
    /// Say hello. Describe when to use the tool, not how it works.
    #[tool]
    async fn hello(&self) -> Result<String, ToolError> {
        Ok("Hello from the plugin!".into())
    }
}

astra::main!(MyPlugin::default());
```

…plus a `#[tokio::test]` that starts the plugin and calls the tool. `cargo test`
passes on a fresh scaffold.

`--template` picks what you start from: `tool` (default), `tts`, `stt`,
`stt-streaming`, `ai-provider`, `ui`, `action-trigger`, `client`, `blank`.

**Before you `cargo add` / `pip install` / `npm install` anything by hand, read
[Publication state](#publication-state) below.** The versions the scaffolds pin
are on the public registries — Rust 0.6.0, Python 0.5.0, TypeScript 0.5.0,
verified against `index.crates.io`, PyPI and the npm registry — but every
*older* version there fails every host call, which is why those pins have lower
bounds and are not worth relaxing.

### 3. Iterate

```bash
astra-plugin dev .        # check --strict, build, sideload into the running Astra, hot-reload
astra-plugin test .       # conformance suite against a real plugin process
astra-plugin check --fix  # manifest, config schema, release workflow
astra-plugin logs -f      # your plugin's output, from the daemon that spawned it
astra-plugin doctor       # why won't it start: toolchains, daemon, entry point, permissions
```

`dev` talks to the daemon on the port it wrote to `<config>/daemon.port`,
defaulting to `127.0.0.1:32000`.

### 4. Release

**Publishing a plugin means one specific thing: a tagged release that GitHub's
CI builds and attests, plus one listing request, ever.** Pushing your source to
GitHub is not publishing. Sending someone a zip is not publishing. Asking a
maintainer to build your plugin is not publishing. The registry pins your plugin
by the digest of the exact file a user downloads and reads GitHub's build
attestation to learn which workflow, at which commit, in which repository
produced those bytes — and a file you built on your laptop carries neither.

You write no YAML.

```bash
astra-plugin init-ci      # writes .github/workflows/release.yml, pinned by commit SHA
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

The tag starts your `release.yml`, which calls the reusable
[`plugin-release.yml`](.github/workflows/plugin-release.yml) in this repository —
on `master`, released as the tag `plugin-release/v1`, which `init-ci` resolves
and pins by commit SHA. That workflow builds one `.astraplugin` per platform,
creates the GitHub Release and has GitHub **attest** each asset, so anyone can
run

```bash
gh attestation verify <file>.astraplugin --repo <owner>/<repo>
```

and learn which repository, workflow and commit produced that exact file. It
does not prove the code is safe.

### 5. Get listed — once, ever

```bash
astra-plugin publish --dry-run   # every registry check that can run locally
astra-plugin publish             # opens a prefilled listing request
```

`publish` uploads nothing and holds no credential: the submission carries only
`owner/repo` and a tag. The registry reads your GitHub Release, verifies every
asset from scratch, and lists it. After that, a new tag is the whole release —
the registry notices it (`astra-plugin publish --notify` is the manual nudge if
it does not). Astra then installs from **your** GitHub Release, with the digest
pinned by the index.

**Use the URL `publish` gives you.** It targets the registry's issue template,
which applies the `listing` label, and the registry's bot only starts an ingest
for an issue carrying that label. Two real listing requests once arrived
unlabelled and got no answer at all, not even a refusal. Both halves of that are
closed now: the registry has turned blank issues off, so the form is the only
door, and a request that still reaches the bot unlabelled gets a comment naming
the label instead of silence. The template link is the one that starts
verification with nobody having to intervene.

There is no `astra-plugin login`. Nothing in this toolchain asks you for a
credential.

**→ [The whole journey in one page](docs/en/publishing.md)**, from an empty
directory to a listed plugin, with every command and its output.

---

## Publication state

| Package | In this tree | Published | Install |
|---|---|---|---|
| `astra-plugin-sdk` (crates.io) | 0.6.0 | 0.6.0 | `astra-plugin-sdk = "0.6"` |
| `astra-plugin-sdk` (PyPI) | 0.5.0 | 0.5.0 | `pip install "astra-plugin-sdk>=0.5,<0.6"` |
| `astra-plugin-sdk` (npm) | 0.5.0 | 0.5.0 | `npm install astra-plugin-sdk` |
| `astra-plugin-macros` (crates.io) | 0.6.0 | 0.6.0 | arrives with the SDK |
| `astra-plugin-cli` (crates.io) | 0.2.1 | **not published, and no prebuilt binaries** | `cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked` |

**Take those versions or newer.** The daemon requires an `x-session-token` on
every host RPC but `Register`, and the first SDK release that attaches one is
Rust 0.6.0 / Python 0.5.0 / TypeScript 0.5.0. Anything older answers
`unauthenticated` on every log line, every `fire_trigger`, every `set_variable`
— the plugin starts, serves inbound hooks, and cannot say a word back. That is
why the scaffold's pins have lower bounds and why they are not worth relaxing.

Two other things, stated exactly, so that no document here implies more than is
true:

- **`trust.json` is signed; the catalogue is not.** The root ceremony ran on
  2026-08-11: `astra-registry/registry/v1/root.json` publishes two Ed25519 keys
  and `astra-daemon/src/plugins/trust.rs` (`PRODUCTION_ROOT_KEYS`) compiles in
  the same two. `registry/v1/trust.json` is now signed by `astra-root-2026a`,
  delegates to the index key `astra-index-2026a`, and names the one
  reusable-workflow commit the registry accepts in an attestation
  (`e3329df…`, which is what `plugin-release/v1` points at). **But
  `registry/v1/index.json` and `revocations.json` still carry
  `"signatures": []`** — so no catalogue signature verifies, a default build
  still fails closed, and revocation is not enforced.
- **Prebuilt CLI binaries do not exist.** Installing the CLI requires Rust and
  `protoc`. See §1.

`astra-plugin publish` targets
[`mihailinl/astra-registry`](https://github.com/mihailinl/astra-registry),
which is public and answering — the submission path works end to end; what the
missing catalogue signature blocks is Astra *installing* from what it publishes.

---

## Installing plugins, in order of preference

1. **Astra's Store.** The canonical path. Verified index, pinned digest,
   consent sheet.
2. **A local `.astraplugin` file** (`ImportPluginFile`). Advanced, and it has a
   ceiling: unless the file's digest is in a fresh signed index, `dom_access`,
   `client`, `send_chat_message` and `set_theme_contribution` are **refused
   outright, not warned about**
   (`astra-plugin-manifest/src/permissions.rs`, `TIER2_REFUSED_PERMISSIONS`).
3. **Sideloading a source directory** — `astra-plugin dev`. A **developer
   tool**, not an install path. It needs Developer Mode, it runs unsigned code
   with your full privileges, and it is the only path with no capability
   ceiling, because it is the authoring loop for UI plugins.

Hand-planting a `sideload.json` marker does not work: the daemon refuses any
marker it did not record itself.

---

## Repository layout

| Path | What it is |
|---|---|
| [`astra-plugin-sdk/`](astra-plugin-sdk/README.md) | Rust SDK |
| [`astra-plugin-sdk-python/`](astra-plugin-sdk-python/README.md) | Python SDK |
| [`astra-plugin-sdk-ts/`](astra-plugin-sdk-ts/README.md) | TypeScript SDK |
| [`astra-plugin-cli/`](astra-plugin-cli/README.md) | The `astra-plugin` command |
| [`astra-plugin-macros/`](astra-plugin-macros/README.md) | `#[astra::plugin]` and friends — an implementation detail of the Rust SDK |
| [`examples/`](examples/README.md) | Eleven plugins, from 15 lines to a WebAssembly Doom |
| [`proto/plugin.proto`](proto/plugin.proto) | The protocol, single source; each SDK vendors a checked copy |
| [`spec/hooks.yaml`](spec/hooks.yaml) | The hook table every parity check reads |
| [`docs/en/`](docs/en/README.md) | The documentation |
| [`PRODUCTION_PLAN.md`](PRODUCTION_PLAN.md) | Architecture, security model, and what is not built yet |

Platforms: **linux-x64** and **windows-x64** for native plugins; **noarch** for
Python and TypeScript. `astra-plugin build --all-targets` produces every bundle
a plugin needs to be installable everywhere Astra runs.

## License

Not one licence — see [LICENSE](LICENSE) for the map and the reasoning.

The SDKs, the macro crate and the examples are **MPL-2.0**: file-level
copyleft, designed to be combined with code under other terms. Your plugin is
yours, under any licence you choose, including a proprietary one. The CLI, the
tooling, the specs and the docs are **GPL-3.0-or-later**.

Being *allowed* to write a proprietary plugin is not the same as being allowed
to *list* one: the registry accepts open-source licences only today. That is
policy and can change; the licence is not and will not.

Attribution: see [NOTICE](NOTICE).

Copyright (C) 2026 Minice — https://minice.ai
