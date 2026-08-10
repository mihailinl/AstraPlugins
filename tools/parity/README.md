# `tools/parity` — the drift detector

Three SDKs implement one protocol. Nothing used to compare them, so they drifted,
and every drift was discovered by a plugin author whose plugin did not work:
`CallFromUi` implemented in Rust and missing in Python, three TypeScript handlers
registered against a proto that no longer had them, hooks the daemon calls that
only one SDK answers.

`spec/hooks.yaml` is the single row-per-hook source of truth. These two scripts
keep it from becoming fiction.

## The two commands

```sh
python3 tools/parity/gen.py            # regenerate the docs from the spec
python3 tools/parity/gen.py --check    # fail if the checked-in docs are stale
python3 tools/parity/check.py          # fail if the spec and the code disagree
python3 tools/parity/check.py --fix-provenance   # re-point daemon_calls lines that moved
```

No third-party dependency: `spec.py` parses the spec's deliberately tiny YAML
subset itself, exactly as `tools/gen-limits.mjs` does for `spec/limits.yaml`.
When PyYAML *is* importable it parses the file a second time and asserts the two
results are equal, so the file cannot quietly become something only this parser
accepts.

## What is generated

| Path | What it is |
|---|---|
| `docs/en/parity.md` | the cross-language dashboard, plus derived findings |
| `docs/en/hooks/rust.md` | per-SDK hook table, author-facing |
| `docs/en/hooks/python.md` | " |
| `docs/en/hooks/typescript.md` | " |
| `spec/generated/conformance.json` | the hook list `astra-plugin test` must cover |

`gen.py` reads **only** the spec — never the SDK sources — so its output is a
pure function of a checked-in file and `--check` is a meaningful gate.
Comparing the spec against reality is `check.py`'s job, and only its job.

## The rules

| Rule | Fails when |
|---|---|
| **R1** | a hook is `stable` in the spec and the SDK has no binding for it (R1b: `n/a` in the spec and bound anyway) |
| **R2** | an SDK binds an rpc that has no row in the spec, or binds it in the wrong direction |
| **R3** | an rpc exists on a plugin-facing service in `proto/plugin.proto` and in no spec row (R3b: a row names an rpc the proto lacks; R3c: `streaming` disagrees with the proto) |
| **R4** | a `planned` row is past its `grace_until` |
| **R5** | `daemon_calls` does not point at the call site it claims |

R5 needs an Astra checkout — `--astra-dir`, else `$ASTRA_RS_DIR`, else
`../Astra/astra-rs`. Without one it is **skipped with a printed warning** that
says the provenance is unverified, rather than passing silently. Line numbers in
`astra-daemon` move constantly; when they do, R5 prints the corrected line, so
the fix is `--fix-provenance`, which moves only line numbers whose call site is
still findable in the same file. When it instead reports that no call site exists
anywhere in the file, that is not a line-number problem: the daemon has stopped
calling the hook, and the row's `routing` is now a lie.

## What counts as a binding

Not "the name appears in the file". Each language has one anchored region and
only names inside it count:

| Language | daemon → plugin | plugin → daemon |
|---|---|---|
| Rust | `async fn` in the `impl … PluginCapabilityService` block of `runner.rs`, cut at `#[cfg(test)]` | `.method(proto::…)` calls in `host_client.rs`, cut at `#[cfg(test)]` |
| Python | `async def` in `_CapabilityServicer` in `plugin.py` | `_stub.Method(` in `host_client.py` |
| TypeScript | keys of the `capabilityHandlers()` map in `plugin.ts` | `REQUIRED_METHODS` and `stub.Method(` in `host-client.ts` |

Cutting Rust at `#[cfg(test)]` matters: `host_client.rs`'s test module contains a
fake daemon that implements the *whole* `PluginHostService` trait, and counting
it would report `SendChatMessage` as shipped when no plugin can call it.

A registered TypeScript handler whose body answers `UNIMPLEMENTED` does **not**
count as a binding. On the wire an `Unimplemented` reply is indistinguishable
from an absent hook, and that equivalence is the protocol's forward-compat
contract — so a stub is `n/a`, not `stable`, and the spec says so.

If an anchor stops matching, `check.py` exits 2 with the anchor that broke. An
empty scan is never reported as a clean bill of health; that failure mode is how
a checker becomes decoration.

## Adding a hook

1. Add the row to `spec/hooks.yaml` — including `daemon_calls`, the `file:line`
   in `astra-daemon` where the daemon really invokes or serves it. A hook with
   no call site is `routing: unrouted`, and that is a finding to report, not a
   row to quietly mark fine.
2. `python3 tools/parity/gen.py`
3. `python3 tools/parity/check.py`
4. Commit the spec and the generated files together.
