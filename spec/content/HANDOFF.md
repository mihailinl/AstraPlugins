<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# Maintaining `spec/content` — a handoff

For whoever changes this contract next. [`README.md`](README.md) says what each
spec is; this page says how the machinery around them works and how a change is
made safely. The contract is pinned by three other lanes (the server L1/L2, the
signer L4, the Astra client L8), so a silent change here is a silent change
there.

## The three moving parts

| piece | what it is | never |
|---|---|---|
| `testdata/content/gen.py` | writes **every** golden byte: signed envelopes (published TEST keys, `contentlite.test_seed`), bundles, command artefacts, the part-digest files, `SHA256SUMS`. Deterministic: re-run, commit both | hand-edit a generated file |
| `testdata/content/vectors.json` | the verdicts, **by hand**: each golden's `verdict`, `code`, `flags`, `check`/`rule`. The checker derives the verdict from the bytes and compares, so a generator bug turns the run red instead of agreeing with itself | copy a verdict from the generator's output |
| `tools/check-content-goldens.py` | the stdlib reference reading of the specs. It derives every verdict, then holds the corpus to its pins | treat it as the implementation: L1's Rust is, and must give the same FIRST code for every golden |

`tools/gen-content-schemas.py` writes `spec/content/schemas/*.json` the same
way (eleven files from one source). `tools/contentlite.py` holds the shared
primitives: JCS, the signing digest, the part digest, and Ed25519 (RFC 8032
reference, test use only).

## The pins in `vectors.json`, and why each exists

- **`expected_checks`** is the exact number of checks a run makes, externals
  excluded. Adding or removing a vector, or a check inside one, moves it. That
  is on purpose: a gutted corpus must fail rather than shrink into a green run.
  When you add goldens, run the checker, read the `made N` it reports, and set
  the pin. Never raise it without knowing what N counts.
- **`synth`** is for goldens too large to commit (16 MiB and 33 MiB archives).
  The record names a builder in `gen.py`'s `SYNTH`, and `sha256` pins the bytes
  the builder must produce. The checker builds them in memory.
- **`SHA256SUMS`** records every generated file. Every path in it must be named
  by some vector.
- **`l1_only`** lists each ingest code that has no golden here, with the reason
  only L1 can test it. A code with neither a golden nor a reason fails the run,
  and so does an `l1_only` entry whose code has since gained a golden.
- **`external`** lists goldens other PRs commit, pinned by path and sha256 and
  never copied: AstraPlugins #123 `516ba38` (the VRM gate) and #122 (zip
  cloaking). They run whenever the file is present with that sha256. To run
  them, point `CONTENT_EXTERNAL_ROOT` at a checkout or `git archive` of those
  commits.
- **`reason-codes.yaml`** is held in both directions: every `E_`/`F_` code a spec
  cites is listed there, and every listed code is specified in a spec.

## Running it

```bash
python3 tools/gen-content-schemas.py --check      # schemas current
python3 testdata/content/gen.py --check           # every golden byte, and SHA256SUMS
python3 tools/check-content-goldens.py            # every verdict, from the bytes
python3 tools/test_check_content_goldens.py -v    # mutation suite (~2–3 min)
python3 tools/test_schemalite.py -v               # schemas use only checkable keywords
CONTENT_EXTERNAL_ROOT=/path/to/516ba38-export python3 tools/check-content-goldens.py
```

**The clean-export gate.** Before calling a change done, run all of the above
on a `git archive` of the PUSHED head, not on your working tree:

```bash
git fetch origin spec/content-v1
rm -rf /tmp/clean && mkdir /tmp/clean
git archive origin/spec/content-v1 | tar -x -C /tmp/clean
cd /tmp/clean && python3 tools/check-content-goldens.py && python3 tools/test_check_content_goldens.py
```

This gate exists because a commit once went out without `tools/contentlite.py`:
the working tree was green, the pushed commit was not (`fd1fefd`, fixed in
`a96a0bd`). A pathspec commit also skips untracked files, so `git add` new
goldens explicitly.

## Conventions

- **One commit per rule.** The subject names the rule; the body says what was
  reproduced and what now refuses it.
- **Reproduce first.** Add the golden and watch the checker give the WRONG
  verdict, usually `got accept`. If it does not reproduce, report that with the
  evidence and do not "fix" it. If the golden is refused today only by a
  neighbouring rule, move it into a place where the new rule is the only guard;
  inside a `.astrapack` part a plain glTF is never judged, which makes it a good
  place.
- **A mutation for every rule.** Add a test in
  `tools/test_check_content_goldens.py` that breaks the rule inside the checker
  (`Mutation(...)` patches one module attribute) and requires the run to go red
  on that rule's goldens. If another rule backs a golden up so that no mutation
  can go red, assert the rule directly and say why in the test.
- **The spec moves in the same commit.** A rule lives in `ingest-v1.md` (or
  `common-v1.md`, `part-digest-v1.md`, `trust-kind-keys-v1.md`) and names its
  goldens; a new code goes into `reason-codes.yaml`.
- **Order is contract.** `ingest-v1.md` §3 fixes which code a multi-fault archive
  gets. A new check goes in a stated step, and a two-fault golden pins it when
  the order is not obvious.
- **The refusing reading.** Where a source is ambiguous, take the reading that
  refuses, holds or disarms more, and record it in [`OPEN.md`](OPEN.md) with the
  line it came from.
- **Gate every commit** on the checker and the mutation suite. A gate that goes
  red is a finding: read it before re-running anything.
- **Key retirement is per (kind, document schema), not per kind**, since
  the per-schema change (trust-kind-keys-v1.md §6, design §11a.9); the
  checker's `retirement_scope` is the one place that decides it.
