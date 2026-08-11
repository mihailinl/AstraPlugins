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

`astra-plugin-cli` is **not on crates.io yet** (verified: `index.crates.io` has
no entry for it). Build it from this repository:

```bash
git clone -b feat/plugin-production https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli
astra-plugin --version          # must print 0.2.0
```

> **Check that version.** Everything on this page is `astra-plugin 0.2.0`. The
> repository's **default branch still carries 0.1.3**, whose entire command set
> is `create`, `dev`, `build`, `validate`, `keygen` — so a bare
> `git clone` (which checks out the default branch) installs a CLI where the
> very next command, `astra-plugin new`, fails with
> `unrecognized subcommand 'new'`, and so does every other command below.
> Verified with `git show master:astra-plugin-cli/Cargo.toml`.
>
> `feat/plugin-production` is the branch that carries this work and it is **not
> pushed yet** — `git ls-remote origin` lists `master` and one unrelated feature
> branch. Until it is, this repository is only usable from a local checkout of
> that branch. Delete this note once it is on the default branch.

Building needs Rust 1.85+ **and `protoc` on PATH** — the SDK's `build.rs`
compiles `proto/plugin.proto` with tonic-build, which calls an external
`protoc`. `apt install protobuf-compiler` / `pacman -S protobuf` /
`brew install protobuf`.

Every crate here is `edition = "2024"`, so the floor is whatever Rust first
supported that edition — 1.85. No crate declares a `rust-version`, and CI builds
on `stable`, so that is the only bound that is actually enforced. The installed
binary is called `astra-plugin`, not `astra-plugin-cli`.

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
are not on the public registries yet, and the versions that *are* there fail
every host call.

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

You write no YAML.

```bash
astra-plugin init-ci      # writes .github/workflows/release.yml, pinned by commit SHA
astra-plugin version 0.2.0
git tag v0.2.0 && git push --tags
```

The tag starts your `release.yml`, which calls the reusable
[`plugin-release.yml`](.github/workflows/plugin-release.yml) in this repository.
That workflow builds one `.astraplugin` per platform, creates the GitHub Release
and has GitHub **attest** each asset, so anyone can run

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
pinned by a signed index.

There is no `astra-plugin login`. Nothing in this toolchain asks you for a
credential.

---

## Publication state

Read this before copying an install command out of any tutorial.

| Package | In this tree | Published | `add`/`install` gets you |
|---|---|---|---|
| `astra-plugin-sdk` (crates.io) | 0.6.0 | **0.5.0** | a version with no `#[astra::plugin]` and no session token |
| `astra-plugin-sdk` (PyPI) | 0.5.0 | **0.4.0** | a version that sends no session token |
| `astra-plugin-sdk` (npm) | 0.5.0 | **0.4.0** | a version that sends no session token |
| `astra-plugin-macros` (crates.io) | 0.6.0 | **not published** | — |
| `astra-plugin-cli` (crates.io) | 0.2.0 | **not published** | — |

The daemon requires an `x-session-token` on every host RPC but `Register`. The
first SDK release that attaches it is **Rust 0.6.0**, **Python 0.5.0**,
**TypeScript 0.5.0**. Anything older answers `unauthenticated` on every log
line, every `fire_trigger`, every `set_variable` — the plugin starts, serves
inbound hooks, and cannot say a word back.

Until the release train runs, build against this checkout. Each SDK README has
the exact commands, and they are the ones CI runs:

- [Rust](astra-plugin-sdk/README.md#installing-today)
- [Python](astra-plugin-sdk-python/README.md#installing-today)
- [TypeScript](astra-plugin-sdk-ts/README.md#installing-today)

Two other things that do not exist yet, so that no document here implies
otherwise:

- **The registry repository is not created.** `astra-plugin publish` targets
  `mihailinl/astra-registry`, which returns 404 today.
- **The trust root keys are not provisioned.** Astra compiles in two root key
  slots and both are empty (`astra-daemon/src/plugins/trust.rs`,
  `PRODUCTION_ROOT_KEYS`). Until the root ceremony runs, no catalogue signature
  verifies and a default build fails closed. Nothing here promises a trust
  guarantee that is not yet anchored.

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

MIT.
