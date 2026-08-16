<!--
Thank you for the fix.

Before you write anything: is this the right shape of contribution? Small and
provable — a typo, a broken link, a wrong flag or path, a one-file bug with an
obvious correct behaviour, a test for behaviour that already exists — is a PR.

Behavioural, cross-repository, or a design question is an ISSUE FIRST. That
means anything changing runtime behaviour, anything that also needs a change in
`Astra` or `astra-registry`, and anything editing `spec/hooks.yaml`,
`spec/limits.yaml`, `proto/plugin.proto` or a capability or permission set —
those are contracts with two other repositories, and a half-landed protocol
change breaks live plugins. CONTRIBUTING.md has the full rule.
-->

## What this changes

<!-- One paragraph. What was wrong, and what it does now. -->

## Why

<!-- The defect, the surprise, or the gap. Link the issue if there is one:
     "Fixes #123". If there is no issue, describe what you hit. -->

## How you know it works

<!-- A transcript, a new test, a before/after. Not "should work". -->

## Checks

Paste the **real output**, not a tick. `bash tools/check-manifest-crate.sh`
exits 0 while *skipping* when there is no `Astra` checkout beside this
repository, and `python3 tools/parity/check.py` skips rule R7 with
`CONFORMANCE UNVERIFIED` unless given a `--report` file — so the output is the
only thing that says which of those actually happened.

```console
$ bash tools/check-proto.sh

$ bash tools/check-manifest-crate.sh

$ python3 tools/parity/gen.py --check

$ python3 tools/parity/check.py

$ node tools/gen-limits.mjs --check

```

<!-- `node tools/gen-limits.mjs --check` also inspects a generated block in the
     Astra repository when a checkout is next to this one, and reports drift
     there as a failure here. To check only this repository's three files, the
     way CI does:  ASTRA_RS_DIR=/nonexistent node tools/gen-limits.mjs --check
     Never resolve that drift by running the generator without --check; it
     writes into the other repository. -->

Per-crate tests for what you touched — **there is no workspace `Cargo.toml`, so
`--manifest-path` is required**:

```console
$ cargo test --manifest-path <crate>/Cargo.toml --all-targets

$ cargo clippy --manifest-path <crate>/Cargo.toml --all-targets

```

<!-- Python SDK:      python -m pytest tests -v      (in astra-plugin-sdk-python/)
     TypeScript SDK:  bun run test                   (in astra-plugin-sdk-ts/)
     Docs:            python3 docs/tools/linkcheck.py
                      ASTRA_PLUGIN_BIN=astra-plugin-cli/target/release/astra-plugin \
                        python3 docs/tools/doctest.py --strict
     Reference docs:  cargo build --release --manifest-path astra-plugin-cli/Cargo.toml
                      python3 tools/docgen/gen.py --check -->

## Before merging

- [ ] I did not hand-edit a generated file. (`docs/en/reference/*`,
      `docs/en/parity.md`, `docs/en/hooks/*`, `proto/plugin.proto` and its
      vendored copies, `limits.{rs,py,ts}`, `spec/generated/conformance.json`,
      `astra-plugin-cli/src/conformance.json`, the vendored manifest crate.) If
      one of those changed, I changed its **source** and re-ran its generator,
      and both are in this PR.
- [ ] Every command I added to a document is one I ran, and its output is what I
      pasted.
- [ ] If I changed how `astra-plugin` behaves: I bumped `version` in
      `astra-plugin-cli/Cargo.toml`, added an
      `astra-plugin-cli/CHANGELOG.md` entry, and re-ran
      `python3 tools/docgen/gen.py` — the CLI ships only as a source build, so
      the version string is the only way to tell one build from another, and the
      generated CLI reference embeds it.
- [ ] Anything that does not work yet is stated in one sentence, in the present
      tense, rather than described as though it already worked.
- [ ] The licence header matches the file's tree — **MPL-2.0** for the SDKs, the
      macro crate and the examples; **GPL-3.0-or-later** for the CLI, the
      tooling, the specs and the docs.
- [ ] No secret, token, key or personal path is in the diff.
