<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# AGENTS.md — read this before you run anything

**AstraPlugins is the authoring side of Astra's plugin system:** three SDKs
(Rust, Python, TypeScript), the `astra-plugin` CLI, the protocol they speak, the
specs that keep them in step. Nothing here runs Astra — the daemon that loads
plugins is a different repository.

**`astra-plugin` is the tool for everything** — scaffolding, checking, running,
testing, packaging, releasing. Use it; do not do its job by hand.
Full docs: [`docs/en/README.md`](docs/en/README.md).

## 1 · Install the CLI

`astra-plugin-cli` is **not on crates.io and has no prebuilt binaries.** Building
from source with Rust is the only way to get it — binaries are a known task, not
something you can use today. If you cannot install Rust, say so and stop; do not
invent another way to obtain the tool. You need **Rust 1.85+** (every crate is
`edition = "2024"`) and **`protoc` on `PATH`** — `pacman -S protobuf`,
`apt install protobuf-compiler`, `brew install protobuf`.

```bash
cargo install --path astra-plugin-cli                                   # from a clone
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
```

Either takes about a minute and ends with `Installed package … (executable
astra-plugin)`. The binary is **`astra-plugin`**, not `astra-plugin-cli`. Confirm
with `astra-plugin --version`: it must say **0.2.1 or newer**. `0.2.0` is the
build whose `init-ci` pinned a SHA no workflow can use, which broke every first
release — if you see it, rebuild.

There is **no workspace `Cargo.toml`** at the root, so `cargo build -p …` fails
with `could not find Cargo.toml`. Every cargo command here needs
`--manifest-path <crate>/Cargo.toml`, and a locally built CLI lands in
`astra-plugin-cli/target/release/`. More:
[`docs/en/install-cli.md`](docs/en/install-cli.md).

## 2 · Create a plugin

```bash
astra-plugin new my-plugin --lang rust --template tool
```

`--lang` is `rust` (default), `python` or `typescript`. `--template` — one of
`tool tts stt stt-streaming ai-provider ui action-trigger client blank` — picks
the capabilities and the example code; `--capabilities` overrides that set.

**Do not hand-write `plugin.toml`, and do not copy one out of `examples/`.** The
scaffold writes a correct manifest with commented, ready-to-uncomment permission
lines. `[capabilities]` is what Astra may call **into** your plugin (ten keys);
`[permissions]` is what your plugin may call **out** to Astra (eight ids,
default-deny, each needing a `reason` the user reads before consenting). They are
independent — declaring `tools` does not grant `fire_trigger` — and both are
**closed sets**, where an unknown key is a hard parse error, not a warning:

```console
$ astra-plugin check .
  ERROR: [capabilities] Capability 'ui_panels' does not exist — Astra calls it 'ui_contributions'.
Error: Check failed with 1 error(s)
```

Reference: [`docs/en/reference/manifest.md`](docs/en/reference/manifest.md),
[`docs/en/3-reference/permissions.md`](docs/en/3-reference/permissions.md).

## 3 · The loop

Each takes a path, defaults to `.`, and accepts `--json` — one document, no
progress lines, which is what you want when parsing. Exit codes: `0` fine ·
`1` the plugin is wrong · `2` the CLI could not run. Prefix each with
`astra-plugin`.

- `check .` — manifest, config schema, release workflow. `--fix` applies what it
  can prove; `--strict` makes warnings fatal.
- `dev .` — builds, then asks the **running Astra** to sideload it, with
  hot-reload. Without Astra: `Could not read …/astra/daemon.token` — start it.
- `test .` — the real feedback loop, and it needs no daemon: runs your plugin
  against a mock one, calling every hook your capabilities imply.
- `build .` — packs a `.astraplugin` bundle and prints its digests;
  `--all-targets` builds every platform bundle a listing needs.

Also `astra-plugin doctor` (why won't it start) and `astra-plugin logs <id>`.

## 4 · Publishing

**Publishing is not pushing source.** The registry never builds anything: it
reads *attested* bundles — artifacts GitHub cryptographically ties to the
workflow run that produced them — off your GitHub Release, and verifies each one.
A hand-built bundle is refused however good it is.

1. `astra-plugin init-ci .` — writes `.github/workflows/release.yml`, pinned to a
   commit of Astra's reusable workflow.
2. `astra-plugin version <semver>` — sets the version in every manifest at once.
3. Commit, tag, `git push --tags`. CI builds, attests and uploads the bundles.
4. `astra-plugin publish --dry-run` — runs every registry check that can run
   locally, and names the ones only the registry can.
5. `astra-plugin publish` — opens a prefilled listing request in `astra-registry`;
   it uploads nothing and holds no credential.

Full story: [`docs/en/publishing.md`](docs/en/publishing.md),
[`docs/en/5-publish/`](docs/en/5-publish/release-with-ci.md).

## 5 · House rules

**Never hand-edit a generated file.** The next generator run reverts it and CI
fails on the drift. Change the source, re-run the generator, commit both.

| Generated | Generator |
|---|---|
| `docs/en/reference/*.md` | `python3 tools/docgen/gen.py` (reads the built CLI binary) |
| `docs/en/parity.md`, `docs/en/hooks/*.md`, `spec/generated/conformance.json` | `python3 tools/parity/gen.py` |
| `astra-plugin-sdk*/…/limits.{rs,py,ts}` | `node tools/gen-limits.mjs` |
| `proto/plugin.proto` + its two vendored copies | `tools/sync-proto.sh` (source is in `Astra`) |
| `astra-plugin-sdk-ts/src/generated/*` | `bun run generate` in `astra-plugin-sdk-ts/` |
| `astra-plugin-cli/vendor/astra-plugin-manifest/src/**` | `tools/check-manifest-crate.sh --sync` (source is in `Astra`) |
| `astra-plugin-cli/src/conformance.json` | copied from `spec/generated/conformance.json` |

**[`spec/hooks.yaml`](spec/hooks.yaml) and [`spec/limits.yaml`](spec/limits.yaml)
are the source of truth** — for the 35 hooks, and for the numbers that must be
identical in the daemon and the SDKs. Both are shared with `Astra`, so changing
either is an *issue first* change (§6).

**Run these from the repository root before proposing anything** — all five were
run for this file, all five exit 0:

```bash
bash tools/check-proto.sh                    # one protocol, vendored copies in sync
bash tools/check-manifest-crate.sh           # plugin.toml has exactly one definition
python3 tools/parity/gen.py --check          # the generated parity docs are current
python3 tools/parity/check.py                # the spec and the three SDKs agree
ASTRA_RS_DIR=/nonexistent node tools/gen-limits.mjs --check
```

Three exit 0 while skipping something, so read the output, not just the code —
[`CONTRIBUTING.md`](CONTRIBUTING.md#then-run-the-checks) says which and why, and
why `ASTRA_RS_DIR=/nonexistent` is not decoration. Touched a CLI flag, the
manifest crate, the proto or an SDK error type? Then also `cargo build --release
--manifest-path astra-plugin-cli/Cargo.toml`, then `python3 tools/docgen/gen.py
--check`.

`npm` is not on `PATH`; use `bun`. Licences are not uniform: SDKs, macros and
examples are **MPL-2.0**, the CLI, tooling, specs and docs **GPL-3.0-or-later**.
Never invent a version — `astra-plugin-sdk` is 0.6.0 on crates.io, 0.5.0 on PyPI,
0.5.0 on npm, and the CLI is published nowhere.

## 6 · If you find a bug, say so

**Do not stay quiet, and do not silently work around it.** A defect you routed
around is a defect the next person hits. Reporting one you cannot fix is a
complete contribution.

- **Small and provable** — a typo, a broken link, a wrong flag or path, a one-file
  bug with an obvious correct behaviour, a test for existing behaviour → **fix it
  and open a pull request.**
- **Behavioural, cross-repository, or a design question** — anything changing
  runtime behaviour, anything that also needs a change in `Astra` or
  `astra-registry`, anything editing `spec/hooks.yaml`, `spec/limits.yaml`,
  `proto/plugin.proto`, or a capability or permission set → **open an issue
  first.** In doubt, issue first.

Which repository, and which template:

- A plugin, SDK, CLI, scaffold, example or docs bug → **AstraPlugins**, *Bug
  report*; an idea or a question → *Plugin idea or question*.
- Getting a plugin listed, or anything about the registry or its bot →
  **[`mihailinl/astra-registry`](https://github.com/mihailinl/astra-registry)**,
  *Plugin listing request* — and it must be that template: the registry's
  automation only acts on issues labelled `listing`, which only the template
  applies. `astra-plugin publish` opens it prefilled.

Either way give the exact command, the complete output including the exit code,
`astra-plugin --version`, your OS and architecture, and what you expected — the
templates ask for exactly that. Do not commit, push, tag or change anything on
GitHub unless you were asked to in this session; reading with `gh` is fine. Full
rules: [`CONTRIBUTING.md`](CONTRIBUTING.md).
