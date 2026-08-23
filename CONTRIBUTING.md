<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# Contributing to AstraPlugins

Two kinds of contribution are wanted here, and they are worth exactly the same:

- **a good bug report** — something you ran, what you expected, what happened;
- **a pull request** — a fix you can demonstrate.

Reporting a broken thing you cannot fix is a complete contribution. The one
outcome that helps nobody is finding a defect and staying quiet about it.

Writing an Astra plugin? You do not need this file — start at
[`docs/en/2-tutorial/getting-started.md`](docs/en/2-tutorial/getting-started.md).
This is about changing **this repository**.

If you are an AI coding agent, read [`AGENTS.md`](AGENTS.md) first. It is short
and it is the one that names the traps; this file is the long form.

---

## Reporting a bug

Open an issue with the **Bug report** template. It asks for five things, and it
asks for them because an issue missing any of them cannot be acted on:

1. the **exact command** you ran, copy-pasted;
2. the **exact output**, complete, including the exit code — `--json` output is
   ideal;
3. `astra-plugin --version`, verbatim;
4. your **OS and architecture**, and the plugin language and its version;
5. what you **expected** instead.

Please do not:

- file "it does not work" with no transcript;
- paste a secret — a token, an API key, a `.env`, a private key. Redact by
  replacing the value, not by hoping nobody scrolls;
- put five unrelated problems in one issue;
- report a page under `docs/en/reference/` or `docs/en/parity.md` as something
  to hand-edit. Those are generated — the bug is in the generator or in its
  source. See "Generated files" below.

### Listing a plugin is a different repository

A **listing request** — "please put my plugin in the store" — belongs in
[`mihailinl/astra-registry`](https://github.com/mihailinl/astra-registry), and
it must be opened **through that repository's "Plugin listing request"
template**. Its automation only acts on issues carrying the `listing` label,
which only that template applies; a blank issue opened there gets no label, so
no check runs, nothing is posted, and the author hears nothing at all. Nothing
else belongs in that repository's issue tracker.

---

## Opening a pull request

### First, decide whether it should be a PR at all

**Open a PR** when the change is small and provable: a typo, a broken link, a
wrong flag or path in a document, a one-file bug with an obvious correct
behaviour, a failing check you can make pass and demonstrate, a test for
behaviour that already exists.

**Open an issue first** when it is behavioural, cross-repository, or a design
question — anything that changes runtime behaviour, anything that also needs a
change in `Astra` or `astra-registry`, anything editing `spec/hooks.yaml`,
`spec/limits.yaml`, `proto/plugin.proto` or a capability or permission set, and
anything where the correct answer is genuinely arguable. Those are contracts
with two other repositories, and a half-landed protocol change breaks live
plugins.

When in doubt, issue first.

### Then, run the checks

There is **no workspace `Cargo.toml`** at the repository root, so every cargo
command needs `--manifest-path`. Run these from the root:

```bash
bash tools/check-proto.sh                    # one protocol, vendored copies in sync
bash tools/check-manifest-crate.sh           # plugin.toml has exactly one definition
python3 tools/parity/gen.py --check          # the generated parity docs are current
python3 tools/parity/check.py                # the spec and the three SDKs agree
node tools/gen-limits.mjs --check            # the generated limit constants are current
node tools/gen-i18n.mjs --check              # the generated plural tables are current, C17
python3 tools/check-locales.py               # the locale vocabulary, C12 and C14
python3 tools/check-python-stubs.py          # plugin_pb2*.py are what plugin.proto generates
```

Plus the crate you touched:

```bash
cargo test  --manifest-path astra-plugin-sdk/Cargo.toml --all-targets
cargo clippy --manifest-path astra-plugin-sdk/Cargo.toml --all-targets
cargo test  --manifest-path astra-plugin-cli/Cargo.toml --all-targets
python -m pytest tests -v                    # in astra-plugin-sdk-python/
bun run test                                 # in astra-plugin-sdk-ts/ — npm is not required
```

And if you changed anything the reference docs are derived from — a CLI flag,
the manifest crate, the proto, an SDK error type:

```bash
cargo build --release --manifest-path astra-plugin-cli/Cargo.toml
python3 tools/docgen/gen.py --check          # reads that binary; it never builds it for you
```

Five of these behave in ways worth knowing before you read a green tick as
proof:

- `tools/check-manifest-crate.sh` **skips, and exits 0**, when there is no
  `Astra` checkout beside this repository. Point it with
  `ASTRA_REPO=/path/to/Astra` if you want it to actually compare. When there
  *is* one it compares against **`origin/main`**, read out of that repository's
  git database — never against whatever the checkout has open, and it refuses
  rather than guessing if that ref does not resolve (`git -C … fetch origin`).
  A stale checkout used to make this script report drift that did not exist and
  tell you to run `--sync`, which would have deleted a constant the vendored
  copy had and the checkout did not. `ASTRA_REF=worktree` compares the working
  tree on purpose, for editing the crate upstream before pushing it; it says so
  loudly every run, because those bytes exist on no other machine.
- `tools/parity/check.py` skips rule **R7** unless you give it a conformance
  report (`astra-plugin test --report <file>`, then `--report <file>`), and
  prints `CONFORMANCE UNVERIFIED` when it does. Its **R5** line-number drift is
  explicitly *not* a failure; `--fix-provenance` re-points those.
- `node tools/gen-limits.mjs --check` **also checks a file in the `Astra`
  repository** when a checkout is next to this one, and will report drift there
  as a failure of this repo's check. Run
  `ASTRA_RS_DIR=/nonexistent node tools/gen-limits.mjs --check` to check only
  this repository's three generated files, which is what CI does. Never "fix"
  that drift by running the generator without `--check` — it writes into the
  other repository.
- `python3 tools/check-locales.py` runs two rules and only one of them can
  always run. **C14** — the `docs/` locale directories against
  `docs/tools/locales.py` and `spec/locales.yaml` — needs nothing. **C12** —
  `spec/locales.yaml` against the daemon's own `SUPPORTED_LANGUAGES` — needs an
  `Astra` checkout, finds one at `../Astra/astra-rs` or `$ASTRA_RS_DIR`, and
  prints `C12 NOT VERIFIED` and the ten codes it took on trust when there is
  none. It exits 0 either way, and the last line says which of the two you
  got. The third rule of that set, **C13**, is not here at all: it is a
  `#[test]` in `astra-plugin-cli`, so it runs under `cargo test` with no
  checkout and no secret, which is why it is the one the vocabulary actually
  rests on.
- `python3 tools/check-python-stubs.py` needs **the exact grpcio-tools version
  the committed stub records in its own `GRPC_GENERATED_VERSION`**, because
  protoc's output is deterministic for one version and not across versions. A
  different one is reported as `TOOLCHAIN MISMATCH`, in those words, and never
  as protocol drift — the message names the `pip install` line. Exit 2 means
  the check could not run; it never quietly passes when it did not compare.

Paste the output of what you ran into the pull request. The PR template asks
for it.

---

## Generated files

Never hand-edit these. The next generator run silently reverts your change, and
CI fails on the drift. Edit the **source**, re-run the **generator**, and commit
both together.

| Generated | Generator |
|---|---|
| `docs/en/reference/*.md` | `python3 tools/docgen/gen.py` |
| `docs/en/parity.md`, `docs/en/hooks/*.md`, `spec/generated/conformance.json` | `python3 tools/parity/gen.py` |
| `astra-plugin-sdk*/…/limits.{rs,py,ts}` | `node tools/gen-limits.mjs` |
| `astra-plugin-sdk*/…/plural.{rs,py,ts}` | `node tools/gen-i18n.mjs` |
| `astra-plugin-sdk-python/…/proto/plugin_pb2{,_grpc}.py` | `grpc_tools.protoc` + one `sed`, by hand — the recipe is in that directory's `__init__.py`, and `tools/check-python-stubs.py` compares the result |
| `proto/plugin.proto` + its two vendored copies | `tools/sync-proto.sh` (real source is in the `Astra` repository) |
| `astra-plugin-sdk-ts/src/generated/*` | `bun run generate` in `astra-plugin-sdk-ts/` |
| `astra-plugin-cli/vendor/astra-plugin-manifest/src/**` | `tools/check-manifest-crate.sh --sync` (real source is in the `Astra` repository) |
| `astra-plugin-cli/src/conformance.json` | `cp spec/generated/conformance.json astra-plugin-cli/src/conformance.json` |

[`spec/hooks.yaml`](spec/hooks.yaml) and [`spec/limits.yaml`](spec/limits.yaml)
are the source of truth for the cross-language contracts. They are shared with
the daemon; changing one is an *issue first* change.

---

## Changing the CLI

Two things travel with a behaviour change in `astra-plugin-cli`, and neither is
optional:

1. **Bump `version` in `astra-plugin-cli/Cargo.toml` and add a
   [`CHANGELOG.md`](astra-plugin-cli/CHANGELOG.md) entry**, even for a one-line
   fix. The CLI is not published anywhere and has no release tag, so the version
   string is the *only* way anyone can tell a fixed build from a broken one. The
   `init-ci` bug in `5b8ab22` shipped without a bump: `astra-plugin --version`
   said `0.2.0` on both sides of it, and the reporter could not tell whether
   their rebuild had taken.
2. **Regenerate the CLI reference.** `docs/en/reference/cli.md` is generated from
   the binary and embeds its version, so any bump or flag change makes it stale:

   ```bash
   cargo build --release --manifest-path astra-plugin-cli/Cargo.toml
   python3 tools/docgen/gen.py
   ```

---

## House conventions

- **Say what is not true yet, in one sentence, rather than describing a future
  in the present tense.** Every document in this tree does this, and it is the
  reason they are trusted. A claim that is not true today is a bug, in prose
  exactly as in code.
- **Every command in a document must be one somebody ran.** Under `docs/`,
  `docs/tools/doctest.py --strict` actually executes them.
- **Licences are not uniform.** The SDKs, the macro crate and the examples are
  **MPL-2.0**; the CLI, the tooling, the specs and the docs are
  **GPL-3.0-or-later**. Match the file you are editing — see
  [`LICENSE`](LICENSE) for the map and the reasoning.
- **Commits explain why.** The existing log is the style guide.

## Security

Do not open a public issue for a vulnerability in Astra, the daemon, the
registry or the signing chain. Contact the maintainers privately.

Two things about the security model that are true today and that a
well-meaning report often gets backwards: **there is no plugin sandbox** — a
plugin is a native process with the user's full privileges, and isolation is
planned but unbuilt — and a **local signature (`astra-plugin sign` /
`keygen`) is not a trust signal**. Trust comes from CI attestation and the
registry.
