# `docs/tools` — the three checks that keep the docs honest

`doctest.py` proves the **samples** are true. `linkcheck.py` proves the
**navigation** is. `mirror.py` proves the six translations still carry
English's pages, English's samples and English's table names. All three run in the `docs (samples execute)` job in
`.github/workflows/ci.yml`.

`locales.py` is not a check. It is the one place the set of translated
languages is written down — `doctest.py`, `mirror.py` and the `couplings` job
all import it, and C14 in that job holds it against `spec/locales.yaml` and
against the directories that are actually under `docs/`. All three used to keep
their own copy, and all three said `zh-CN`.

<!-- doctest: cli -->
```bash
python3 docs/tools/doctest.py                 # run every sample
python3 docs/tools/doctest.py --list          # what is there, and how each is checked
python3 docs/tools/doctest.py --strict        # a skipped check is a failure (CI)
python3 docs/tools/doctest.py --only rust-plugin,ts-plugin
python3 docs/tools/doctest.py docs/en/2-tutorial
python3 docs/tools/linkcheck.py               # every relative link resolves
python3 docs/tools/linkcheck.py docs/ru       # one subtree
python3 docs/tools/mirror.py                  # every locale carries en's pages, samples and table names
astra-plugin --version
```

## Why

`docs/en` landed in one commit and was never touched again while nine commits
reshaped the CLI, the manifest, the proto and three SDKs. The largest class of
the ~28 false claims the audit found was a **code sample**: a `plugin.toml`
with a section the parser rejects, a `main.rs` written against a trait that had
changed shape, a CLI line with a flag that does not exist.

Prose drifts and a reader forgives it. A sample that does not compile costs an
evening. So every fenced block in a written page carries a marker saying how it
is checked, and a block with **no** marker is an error — the failure this
replaces is a sample nobody thought about.

## The marker

An HTML comment on the line before the fence:

<!-- doctest: illustrative reason="a sample of the marker syntax itself; running it would be a doc-test recursing into its own documentation" -->
````markdown
<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;
…
```
````

### Runners that execute the sample

| Runner | What it does |
|---|---|
| `rust-plugin` | The block is a complete `src/main.rs`. Built with `cargo build` in a scaffolded project whose SDK is patched to this tree. `test=1` also runs `cargo test` |
| `toml-manifest` | The block is a complete `plugin.toml`. Run through `astra-plugin check --strict`. `locales=1` also writes a `locales/en.json` covering every `$key` the manifest references |
| `cli` | Every `astra-plugin …` line is re-parsed by the real binary. Other lines must use an allowlisted shell command |
| `python-plugin` | A complete module. Byte-compiled, executed top-level, and every `def test_*` it defines is called |
| `ts-plugin` | A complete module. Type-checked with `tsc --noEmit` against this tree's SDK |
| `json` | Parsed with `json.loads` |

### Runners that do not, and must say why

| Runner | Required attribute |
|---|---|
| `output` | `from="<the command that produced it>"` — and it must be a *command*, not a description of one |
| `illustrative` | `reason="<why it cannot run>"`, at least twelve characters |

`output` is only half a non-runner. When `from=` is an `astra-plugin` line
carrying `--help`, `-h`, `--version` or `-V` — `<subcommand> --help` included —
the command **is** run and the block is diffed against what it prints, with
`<lower-case-placeholders>` matching anything. `<COMMAND>` and the other clap
metavariables are upper-case and stay literal.

The subcommand case is new, and the way it was missing is worth keeping: this
paragraph and the harness's own docstring both claimed `<subcommand> --help` was
executed, while the predicate refused any word that was not a flag. Every
subcommand help transcript in these docs was therefore un-run, in all seven
languages, and counted as *accounted for* — a claim in prose standing where a
check was believed to be. It is one predicate now, `self_answering`, called by
the runner and by the summary counter, because it used to be the same expression
written twice.

When `from=` names something this harness will not run — it needs a project, a
daemon, the network, a particular machine — the block must also carry
`unrun="<why, and what a reader should re-run by hand>"`. Nothing checks such a
transcript, and the marker is where that is admitted rather than assumed. The
summary counts the two apart, so `0 failed` never has to be read as a claim
about a block nothing ran.

This is not decoration. `run_output` used to check only that `from=` was a
non-empty string, and a fabricated transcript rode that all the way to review:
a block marked `from="cargo install … --root <scratch> …"` whose body said cargo
had installed into `~/.cargo/bin`, which that command cannot print. Six
translations carried the same block, and the gate was green for all seven.

## How `cli` blocks are checked without side effects

`--help` is appended to each command. `clap` parses the subcommand and every
flag, then short-circuits before the subcommand does anything: a valid line
exits 0, an unknown flag or subcommand exits 2. So `astra-plugin build --target
linux-x64 --reproducible` is verified against the real definitions, and
nothing is built.

## How `rust-plugin` blocks find the SDK

The scaffold this harness builds in pins the **published** SDK, and the tree
runs ahead of crates.io between releases. So the runner rewrites the
`astra-plugin-sdk = …` line to a path dependency on `astra-plugin-sdk/` in this
repository, and refuses to run at all if that line is not there to rewrite.

It used to append `[patch.crates-io]` instead, on the strength of a comment —
also in `ci.yml`, where it still stands — saying that a patch overrides a
dependency *regardless of the declared range*. It does not. Cargo drops a patch
whose version does not satisfy the requirement, prints `patch … was not used in
the crate graph` as a **warning**, and resolves from the registry. Today the
pin and the tree agree and C11 holds them there, so nothing is broken; the
window where they do not is between an SDK version bump and the repin after its
publish, and in that window every Rust sample is checked against the last
released SDK in a run that stays green.

The scratch project is **re-scaffolded when the CLI binary changes**, which is a
separate trap with the same shape. `$TMPDIR/astra-doctest` is reused so a second
run is cheap, and that meant a project scaffolded by an older binary outlived
the scaffold itself: a cached `Cargo.toml` here still pinned SDK `"0.6"` five
commits after the template moved to `"0.7"`. On CI the workdir is always fresh,
so this one is invisible in the only place it is watched.

## What it needs

| | For | Without it |
|---|---|---|
| `cargo` | `rust-plugin` | skipped, and a failure under `--strict` |
| the `astra-plugin` binary | `cli`, `toml-manifest` | built from this tree, unless `--no-build` |
| a Python with `grpcio` | `python-plugin` | the sample is byte-compiled only, and reported as skipped |
| `astra-plugin-sdk-ts/node_modules` and `dist` | `ts-plugin` | skipped |

`ASTRA_DOCTEST_PYTHON=/path/to/venv/bin/python` points the Python runner at an
interpreter that has `grpcio`; `ASTRA_PLUGIN_BIN` points at a prebuilt CLI.
Scratch projects live under `$TMPDIR/astra-doctest` and are reused between
runs, so a second run costs an incremental `cargo build`.

## Adding a sample

1. Write the block.
2. Put a marker above it.
3. Run `python3 docs/tools/doctest.py <the file>`.
4. Fix what it tells you. It will tell you something — the two Rust samples and
   both TypeScript samples in these docs were wrong on first draft, in ways
   review would not have caught: a struct variant used as a tuple variant, an
   error whose `Display` lacked the substring the test asserted, a constructor
   taking an options object rather than a string, a property read as a method.

Identical blocks are executed once: the translated pages carry the same samples
as the English ones, and that they are byte-identical is the point.
`mirror.py` enforces it — see below.

## `linkcheck.py`

Every markdown file under `docs/`, plus every `README.md` in the repository
that is not vendored or a build artefact. A relative target must exist; a
`#fragment` must match a heading in the file it points at, under GitHub's slug
rules, or an explicit `<a id=…>`.

It exists because the rewrite moved almost every page: eight files were deleted
and the tree was renumbered, so a link that was right in April is a 404 now,
and no other check reads a link. It found one on its first run —
`docs/en/spec/bundle-v2.md` pointed at `../manifest.md`, which the rewrite had
turned into `../reference/manifest.md`.

Not checked, deliberately: `http(s)://` and `mailto:` (this must pass with no
network), anything inside a fenced block (a sample that prints a path is a
sample — `doctest.py` owns it), and `PRODUCTION_PLAN.md`, which *quotes* the
translation banner including the relative link that is correct only where the
banner is installed. Those exclusions are listed with their reasons in the
module docstring; add to that list only with a reason of the same kind.

## `mirror.py`

Three assertions, all against `docs/en`, for each of the six translations. Each
one exists because the one before it was not enough, and that is the pattern
worth carrying away: every time, what was not compared was the part a machine
had written and a human had copied.

**The page set.** Same relative paths, in both directions, so a translated page
whose English original was deleted fails the build instead of quietly outliving
it — nothing will ever correct it again and a reader has no way to tell.

**The samples.** The sequence of `<!-- doctest: … -->` runners on a page must
match English, every `output` block's body must be byte-identical to its English
original, and the `from=`, `unrun=` and `reason=` attributes must match too. A
transcript is a machine's words, so translating one is always a mistake; the
attributes are notes to the next editor, written in English throughout the tree.

Bodies of `rust-plugin`, `python-plugin`, `ts-plugin` and `toml-manifest` blocks
are **not** compared — they are code, `doctest.py` executes each of them in every
language, and a comment inside one is fair to translate. Their positions are
still compared, and so is `toml-manifest`'s `locales=` attribute: that one is not
a note to an editor but an instruction to the runner, and a translation that drops
it turns that page's manifest sample red in one language only.

**The table rows.** A row whose *first* cell is one inline-code span with no
whitespace in it — an rpc name, a manifest key, a flag — is a row a machine
wrote. It is keyed on that name, it must appear the same number of times in the
translation as in English, and every other whitespace-free code cell in it must
be byte-identical. A code span *with* whitespace is a phrase, not a name, and is
left alone: `spec/registry-index.md` has `issued_at + 30 days` in a cell, and
`issued_at + 30 Tage` is the correct German for it. So are plain cells —
`yes`/`ja` and `**none**`/`**keine**` are translations, not drift.

Rows are keyed by name rather than compared by position on purpose, and the
consequence needs stating carefully, because the short version of it was wrong
here until it was measured. A whole section that exists in English and in no
translation is **not** a failure — **unless it contains a table whose rows lead
with a name**, and then it is six failures. Appending an English-only section of
prose leaves this green; appending one with a single row
`| ``--brand-new`` | does a thing |` gives six TABLE findings and exit 1.

A name-keyed row is derived data and exists in every language or in none; prose
is not and does not. Three sections of `3-reference/permissions.md` and one
table of `reference/cli.md` are absent from six translations today and are not
failures **because their rows are absent on both sides** — there is nothing to
compare. Add a row to the English copy of one of them and this script asks for
it in six files.

Whether an English edit should be blocked until somebody translates it is still
the maintainer's decision, as in the last paragraph. This paragraph is only
about what the script does today, which is what a contributor needs before
writing the section rather than after CI tells them.

The second assertion exists because the first was not enough. A correction to an
English transcript shipped with all six translations still carrying the retracted
claim, and this tool reported "0 mismatches" — it only ever read filenames.

The third exists because the second was not enough either. `docs/en/parity.md`
is generated from `spec/hooks.yaml`; its six translations are hand-maintained
snapshots by declared policy, as are the six of `docs/en/reference/parity.md`.
Twelve copies of a generated table that nothing regenerated and nothing read.
All twelve named `manager.rs:3624` in the `Daemon call site` column where English
named `3924` — 33 rows each, 396 cells, both doc tiers — and this tool printed
"0 mismatches" again, because a table body is neither a filename nor a doctest
block. The same commit stopped printing the daemon *line* in that column at all,
in every language; it lives in `spec/hooks.yaml`, where parity rule R5 checks it
against a live call site and nothing on a page ever did.

It does **not** implement the rest of §7.4's gate ("CI fails when `docs/en/**`
changes without a matching translation touch"): that needs a base ref, and it
blocks an English-only typo fix until somebody touches six other files, which is
a policy decision rather than a script's. The docstring says so at the point
where a contributor would otherwise assume it is covered.
