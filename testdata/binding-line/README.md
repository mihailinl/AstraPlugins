# `testdata/binding-line` — a mirror, and not the original

Thirty-one files a stranger could commit to `.well-known/astra-plugin-owner`,
each with the outcome ID-23 and ID-24 require, so that the three programs which
read that file can be measured against one fact instead of three self-agreements.

    mirrors:  astra-registry@8c94c240e5f176b1fd8c9166df6fd83b09e74c59:tests/binding-line/vectors.json
    sha256:   2fe708abc724db9502f6801e5a0a0a59db996793afae85767468f5662cf34db4  vectors.json

Those two lines are read by `tools/check-registry-mirrors.py` rule **C31**, not
only by you. Editing one without the other is a red build, and that is the
point: a pin and a digest that can drift apart are a pin nobody can act on.

## Direction

`astra-registry:tests/binding-line/vectors.json` is **canonical** (registry plan
B-T2.4, landed in `bc0d195`). This directory is a copy, and the copy is
downstream in every sense — a case added here reserves nothing, a case removed
here only stops this repository from noticing a disagreement it will still have.

**To change the corpus, change it in astra-registry**, by editing
`tests/binding-line/generate.mjs` and running it; then re-copy `vectors.json`
and `SHA256SUMS` here and move both lines of the provenance block above.

That direction is the opposite of `testdata/bundles/`, and the difference is
worth one sentence because the two sit in the same tree. The bundle corpus is
**ours**, and `tools/vendor-testdata.sh` pushes it out to the daemon and to the
registry, sweeping each destination with `rm -f`. This corpus travels the other
way. `vendor-testdata.sh` neither copies nor sweeps it — its source is
`testdata/bundles` alone and its destinations are in the other two repositories —
and that is checked rather than remembered: C31's fourth leg re-reads
`vendor-testdata.sh` and fails if this directory ever becomes one of its
destinations. The registry holds the mirror image of that guard:
`bot/tests/binding.test.mjs` asserts that `tests/vectors/` — which the sweep
*does* own — contains no subdirectory, so the day somebody tidies the corpus
into it, the answer is a red test and not a silent deletion.

## What this directory does not carry, deliberately

The corpus's **meaning** — what each case is for, why the window is counted in
bytes, what `outcome`, `token`, `cli_write` and `proposal` mean, and the five
questions (`Q1`…`Q5`) the contract has not yet answered — is written once, in
`astra-registry:tests/binding-line/README.md`. Read it there.

It is not repeated here because a second copy of an argument is the copy that
rots: `SHA256SUMS` covers `vectors.json` and nothing else, so prose copied into
this file would be prose nothing compares, drifting from the original at the
speed of the first upstream edit. `spec/reserved-ids.yaml` makes the same choice
about astra-registry's `reserved_note`, and for the same reason.

`generate.mjs` is not copied either. It is how the goldens are produced, it
imports nothing from this repository, and a generator in a tree that must not
regenerate is an invitation to regenerate — which would replace a shared fact
with this repository's opinion of it.

## Who reads it here

`astra-plugin-cli/src/binding.rs` (plan task AP-8): one ID-23/ID-24 reader and
one writer, measured against every case, and against the `cli_write` column in
particular — that column is where FLOW-50's `{22,128}` writer disagrees with
ID-23's `{16,128}` reader, and `astra-registry:bot/lib/binding.mjs` carries the
same constant with a comment saying that this corpus is what joins the two
copies.

**That reader does not exist yet.** This directory is its precursor: AP-8's
Repo/files line said it was "tested against `testdata/binding-line/vectors.json`"
while nothing in this repository had ever held that path. When `binding.rs`
lands, its suite must verify `SHA256SUMS` **before it reads a case**, the way
`bot/tests/binding.test.mjs` does — a walk that lost its file finds no
disagreement and passes.

## What keeps this copy honest, and what does not

C31, in `tools/check-registry-mirrors.py`, in four legs:

| leg | needs | what a red means |
|---|---|---|
| **in-repo** | nothing | `vectors.json` does not hash to `SHA256SUMS`, or the block above disagrees with `SHA256SUMS`, or the file no longer parses to a corpus. Somebody edited a copy. |
| **sweep** | nothing | `vendor-testdata.sh` has grown a destination or a source that overlaps this directory, and the next vendor run would delete or overwrite it. |
| **pinned** | an astra-registry checkout | these bytes are not what `astra-registry@<sha>` above really held. The provenance line was typed from memory rather than taken. |
| **head** | an astra-registry checkout | upstream has moved. **Head red with pinned green is the ordinary case** and means this copy is stale; both red means somebody edited this one. |

All four legs run in CI on every push, in two jobs. The first two run in the
`couplings` job, which checks out one repository, so there C31 prints what it
took on trust and ends the run with `NOT VERIFIED` rather than with the word
"pass" — on every green run, in the middle of a passing transcript,
deliberately. A nag that appears when everything is fine is the only honest
report a check can give about a comparison it did not make. C20 in
`tools/check-locales.py` and C27 in the same file as C31 say the same sentence
for the same reason.

The last two run in `proto-upstream`'s last step, against the astra-registry
checkout that job holds at `_registry`. That checkout is one commit deep, so
the step first fetches the commit named on the `mirrors:` line above by its
SHA. It reads that SHA with `--pins`, from this file, through the same reader
C31 uses. Before that step existed, the pinned and head legs had never run in
CI.

To run the two comparing legs locally — the thing worth doing before you move
the pin — name a checkout that holds the pinned commit:

```sh
python3 tools/check-registry-mirrors.py --rules C31 --registry-dir ../astra-registry
```

A checkout that is missing the commit is red and says which fetch to run. A
directory that is not a git checkout of its own is exit 2.

## Licence

`astra-registry` is GPL-3.0-or-later and so is everything under `testdata/` in
this repository (see the README's licence section: the SDKs, the macro crate and
the examples are MPL-2.0; the CLI, the tooling, the specs, the testdata and the
docs are GPL-3.0-or-later). Copyright Minice. The copy changes nothing about
either: same licence, same holder, same terms, moving between two repositories
that both carry `LICENSES/GPL-3.0.txt` verbatim.
