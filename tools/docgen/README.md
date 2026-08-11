# `tools/docgen` — the generated half of `docs/en`

```
python3 tools/docgen/gen.py            # write docs/en/reference/
python3 tools/docgen/gen.py --check    # what CI runs; fails with a diff
python3 tools/docgen/gen.py --only cli # one page, while iterating
```

Needs Python 3.11+ and nothing else, plus a built `astra-plugin` for `cli.md`:

```
cargo build --release --manifest-path astra-plugin-cli/Cargo.toml
```

`$ASTRA_PLUGIN_BIN` overrides which binary is read; otherwise `target/release`,
then `target/debug`, then `$PATH`. The generator never builds it for you — a
docs check that silently starts a five-minute compile is a docs check people
stop running.

## Why this exists

The documentation audit that produced Phase 6 found roughly 28 factually false
claims in `docs/en`. They were not sloppy writing. Every one of them was the
same failure: the docs landed in a single commit, nine commits then reshaped the
CLI, the manifest crate, the proto and the SDKs, and nothing compared the two.
`cli.md` documented a `ui_panels` capability no daemon has ever had, a scaffold
path the CLI does not write, and a `RUST_LOG` that did nothing.

Prose can be reviewed by a human, because a human can tell whether a paragraph
still makes sense. A table of flags cannot: nobody re-reads thirty rows against
`main.rs`. So everything a machine can derive is derived, and the only
documentation anyone has to keep true by hand is the documentation only a human
could have written.

## The pages

| Page | Generator | Source of truth |
|---|---|---|
| `reference/cli.md` | `cli.py` | the `astra-plugin` binary's own `clap` help, executed; plus `#[command(alias)]` and `#[arg(hide = true)]` scanned from `main.rs`, each verified against the binary |
| `reference/manifest.md` | `manifest.py` | `astra-plugin-cli/vendor/astra-plugin-manifest` — the crate the daemon parses `plugin.toml` with |
| `reference/protocol.md` | `protocol.py` | `proto/plugin.proto` + `proto/PROTO_VERSION`, joined with `spec/hooks.yaml` for permissions and routing |
| `reference/errors.md` | `errors.py` | the proto's `PluginErrorCode` and all three SDKs' error modules, cross-checked against each other |
| `reference/parity.md` | `parity.py` | `spec/hooks.yaml`, rendered by `tools/parity/gen.py` — called, not reimplemented |
| `reference/README.md` | `gen.py` | the five above |

`rustsrc.py` is a deliberately small reader for the Rust shapes these
generators need (serde structs, enums, `const` lists, one-expression `fn`s). It
is not a Rust parser and does not try to be; see its module doc for the safety
property that makes that acceptable.

## The rules a generator here follows

1. **Fail rather than omit.** Every lookup is by name, for an item the generator
   knows exists. When it finds nothing, it raises `DocgenError` and the run
   exits non-zero. An empty table is indistinguishable from a feature that was
   removed, and that is the exact failure mode this directory exists to end.

2. **Two readers of one fact, compared.** `protocol.py` checks the proto's
   streaming kinds against `spec/hooks.yaml`; `errors.py` checks four error
   taxonomies against each other; `manifest.py` checks `CAPABILITY_NAMES`
   against the fields of `Capabilities`. Where a page could be assembled from
   two sources, it is, and a disagreement fails the build.

3. **Say where a fact came from, especially when it came from elsewhere.** The
   permission each host RPC is gated on lives in the Astra daemon, which this
   repository cannot see. The page says so, names `spec/hooks.yaml` as the
   checked-in carrier and parity rule R6 as the thing that pins it to the
   daemon. A generated page that quietly presented that as first-hand knowledge
   would be worse than a hand-written one.

4. **No prose that is not in the source.** Section text on these pages is
   quoted from doc comments, module docs and proto comments. Where a generator
   adds a sentence of its own, it is about the *shape* of the thing (`each key
   is a boolean and defaults to false`), never about behaviour.

## Adding a page

Write `tools/docgen/<name>.py` with a `render() -> str`, add it to `PAGES` in
`gen.py` and add its row to `index()`. `gen.py` refuses to render an index that
names a page nothing produced, so the two cannot drift.

Every page must:

* start with `banner(<module>, [<sources>])` — the DO NOT EDIT header naming
  the generator and everything it read;
* use only relative links that resolve on disk. `gen.py` checks every one and
  refuses to write a page with a broken target.

## What is deliberately not generated

`docs/en/parity.md` and `docs/en/hooks/*.md` are still written by
`tools/parity/gen.py` at their old flat paths, and the `parity` CI job checks
them there. `reference/parity.md` is the same renderer's output one directory
deeper. When the flat `docs/en` tier is retired, drop `docs/en/parity.md` from
that generator's `artefacts()` and the reference copy is the only one.

The capabilities and events pages named in the documentation plan are not here
yet: capabilities would be a second view of `spec/hooks.yaml`, and events are
generated from Astra's `event.rs`, which is in the other repository.
