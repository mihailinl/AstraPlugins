# astra-plugin-manifest

The `plugin.toml` manifest, defined once.

Three programs read a plugin manifest: the **daemon** (`astra-daemon`, when it
discovers, imports, sideloads or installs a plugin), the **CLI**
(`astra-plugin check` / `build` / `test`), and the **registry bot** (which must
validate a submission with the daemon's own code, or the store admits bundles
the daemon will later refuse). Before this crate they read it with three
different structs.

## The failure this crate exists to end

The CLI's fork grew a `ui_panels` capability. The daemon has never had one — it
calls that `ui_contributions`. Serde drops unknown fields by default, so nothing
anywhere reported an error: `bad-apple`, `companion` and `doom` shipped
declaring `ui_panels`, the daemon parsed their `[capabilities]` into all-`false`,
and the entire visible symptom was `astra-plugin check` printing

    WARN: No capabilities enabled — plugin won't do anything

for three plugins whose whole point is the UI. A drift that produces a warning
about the *author's* plugin, rather than an error about *our* schema, can live
for a very long time.

So `[capabilities]` carries `#[serde(deny_unknown_fields)]`. That section is
nothing but opt-in booleans; there is no benign unknown key in it, and a
misspelled one now fails the manifest and names the correct spelling.

`PluginManifest` itself deliberately does **not** deny unknown fields. Whole
sections are added across releases — `[permissions]` is next — and an older
daemon that refused a manifest carrying a section a newer Astra understands
would make every forward-compatible addition a flag day.

## Vendored, not published — and why

`AstraPlugins` carries a byte-identical copy of `src/` and this README at
`astra-plugin-cli/vendor/astra-plugin-manifest/`.
`AstraPlugins/tools/check-manifest-crate.sh` fails when the two differ and
prints the one command that fixes it.

The alternative was publishing this crate to crates.io and having both repos
depend on the released version. That was considered and rejected, for two
reasons that are about the project rather than the code:

1. **It needs an account that one person has.** Publishing is a credential held
   by the maintainer. A shared type that can only be updated by one person, in a
   separate release step, is a worse coupling than a copied directory that any
   contributor can re-sync and CI can verify.
2. **It couples two release trains.** `astra-plugin` ships on its own cadence
   from `AstraPlugins`; Astra ships from `Astra`. A published dependency means a
   manifest change lands in three steps (publish, bump, bump) with two windows
   in which the repos disagree — which is precisely the state this crate exists
   to make impossible.

Vendoring costs one CI check and buys byte-equality enforced on every push. The
door stays open: if the CLI is ever published to crates.io it will need a
published dependency anyway, and at that point the vendored copy becomes a
`version = "…"` line and `check-manifest-crate.sh` is deleted.

**Direction of the copy is one-way.** `Astra/astra-rs/astra-plugin-manifest` is
the source. Edit it there; run the sync; never the reverse.

## The one intentional difference between the copies

`Cargo.toml`, and only `Cargo.toml`.

The daemon **is** an Astra, so it must refuse a plugin whose
`plugin.min_astra_version` is newer than the running daemon — at parse time, on
every path that parses a manifest. `astra-plugin` is **not** an Astra; a `check`
that refused to look at a plugin targeting a newer daemon than the CLI's own
build would be nonsense.

That single host-dependent rule lives behind the `astra-host` Cargo feature,
which is on by default in Astra's copy (where it pulls `astra_core::VERSION`)
and declared-but-empty in the vendored copy. The whole surface of the
difference is `host_astra_version()`. The *syntax* of `min_astra_version` is
validated in both — an unparseable value is a constraint that constrains
nothing, and the author must hear about it from `astra-plugin check` rather than
from a stranger's daemon.

`src/**` and `README.md` are compared byte-for-byte precisely because that is
where behaviour lives; the two `Cargo.toml` files are compared only on their
dependency *names*, so a dependency added upstream and forgotten downstream is
still a CI failure.

## Layout

| File | Holds |
|---|---|
| `src/manifest.rs` | `PluginManifest` and its sections; `validate()`, the `plugin.id`-as-path-component rules, `min_astra_version` |
| `src/capabilities.rs` | `[capabilities]`, the capability vocabulary, and the rename table behind the error messages |
| `src/platform.rs` | `[platform]`, `current_platform()`, and the single `(os, arch) → registry artifact key` mapping |

## Seams left open on purpose

* **`[permissions]` (plan §5.6, Phase 4)** is a new module plus one field on
  `PluginManifest`. Nothing else moves.
* **The registry bot (plan task 3.3)** links this crate directly and uses
  `is_reserved_device_name`, `CAPABILITY_NAMES` and `RESERVED_PLATFORM_KEYS`
  rather than restating them — all three are `pub` for that reason.
