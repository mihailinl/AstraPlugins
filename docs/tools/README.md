# `docs/tools` — the three checks that keep the docs honest

`doctest.py` proves the **samples** are true. `linkcheck.py` proves the
**navigation** is. `mirror.py` proves `docs/ru` still covers what §7.4 says it
covers. All three run in the `docs (samples execute)` job in
`.github/workflows/ci.yml`.

<!-- doctest: cli -->
```bash
python3 docs/tools/doctest.py                 # run every sample
python3 docs/tools/doctest.py --list          # what is there, and how each is checked
python3 docs/tools/doctest.py --strict        # a skipped check is a failure (CI)
python3 docs/tools/doctest.py --only rust-plugin,ts-plugin
python3 docs/tools/doctest.py docs/en/2-tutorial
python3 docs/tools/linkcheck.py               # every relative link resolves
python3 docs/tools/linkcheck.py docs/ru       # one subtree
python3 docs/tools/mirror.py                  # docs/ru covers the written tier, exactly
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
| `toml-manifest` | The block is a complete `plugin.toml`. Run through `astra-plugin check --strict` |
| `cli` | Every `astra-plugin …` line is re-parsed by the real binary. Other lines must use an allowlisted shell command |
| `python-plugin` | A complete module. Byte-compiled, executed top-level, and every `def test_*` it defines is called |
| `ts-plugin` | A complete module. Type-checked with `tsc --noEmit` against this tree's SDK |
| `json` | Parsed with `json.loads` |

### Runners that do not, and must say why

| Runner | Required attribute |
|---|---|
| `output` | `from="<the command that produced it>"` |
| `illustrative` | `reason="<why it cannot run>"`, at least twelve characters |

## How `cli` blocks are checked without side effects

`--help` is appended to each command. `clap` parses the subcommand and every
flag, then short-circuits before the subcommand does anything: a valid line
exits 0, an unknown flag or subcommand exits 2. So `astra-plugin build --target
linux-x64 --reproducible` is verified against the real definitions, and
nothing is built.

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

Identical blocks are executed once: the Russian pages carry the same samples as
the English ones, and that they are byte-identical is the point.

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

`docs/ru` covers `README.md`, `1-orientation/`, `2-tutorial/`, `5-publish/` and
`6-operate/` — the written tier — and nothing else. This asserts that as a set
equality in both directions, so a Russian page whose English original was
deleted fails the build instead of quietly outliving it.

It does **not** implement the rest of §7.4's gate ("CI fails when `docs/en/**`
changes without a matching `docs/ru/**` touch"): that needs a base ref, and it
blocks an English-only typo fix until somebody touches a Russian file, which is
a policy decision rather than a script's. The docstring says so at the point
where a contributor would otherwise assume it is covered.

The other half of that story needs no policy: `doctest.py` executes each fenced
block once and reports the Russian copies as `identical to` their English
original, so a sample that drifts between languages stops being deduplicated
and shows up as a second execution.
