# `testdata/bundles` — the cross-repo bundle vectors

Twenty-seven `.astraplugin` files, each with a written-down verdict, and the two
digests every implementation of the v2 format has to agree on.

Three programs read this format:

| | implementation | what it is |
|---|---|---|
| **CLI** | `astra-plugin-cli/src/bundle.rs` (`Bundle::open`) | the packer, and the definition of the format |
| **daemon** | `Astra/astra-rs/astra-daemon/src/plugins/bundle.rs` | what decides whether a stranger's bytes get extracted |
| **registry** | `astra-registry/bot/lib/bundle.mjs` | what decides whether a listing is published |

They were written from the same notes, in three languages, in three
repositories that release on three schedules. Nothing structural stops two of
them drifting apart for a release, and the failure is quiet in both directions:
a reader that is too strict makes a legitimate plugin uninstallable, and a
reader that is too lax publishes a bundle the others would have refused. This
directory is the shared fact all three are measured against.

## Using it

The canonical copy lives here. The two consumers hold vendored copies:

```
Astra           astra-rs/astra-daemon/testdata/bundles/
astra-registry  tests/vectors/
```

```sh
tools/vendor-testdata.sh            # refresh both copies, then verify them
tools/vendor-testdata.sh --check    # verify only — this is the CI step
```

A vendored copy carries only the goldens, `vectors.json`, `SHA256SUMS` and this
file. The generator and `handcheck.sh` stay here, because they are how the
goldens are *produced*, and a repo that only reads them has no business
regenerating them.

Each suite also verifies its copy against `SHA256SUMS` **at run time**, before
it reads a single vector, so an edited fixture is a named failure rather than a
mysterious disagreement. Editing a vendored copy is the mistake this guards
against; the canonical directory is the only one worth changing.

CI runs `generate.mjs --check` and `vendor-testdata.sh --check` in AstraPlugins'
`couplings` job. Astra and astra-registry are private / separately checked out,
so that job verifies the canonical directory alone; their copies are verified by
their own suites, on every test run, which is the stronger of the two anyway.

## Files

| | |
|---|---|
| `*.astraplugin` | the goldens. Committed, byte-frozen. |
| `vectors.json` | one record per vector: verdict, layer, both digests, and what each implementation does with it today |
| `SHA256SUMS` | `sha256sum -c`-compatible, covering the goldens and `vectors.json` |
| `generate.mjs` | how the goldens were produced. Not run by any suite — see below |
| `zip.mjs` | a deterministic ZIP writer that can also write malformed archives |
| `handcheck.sh` | the same two digests, computed with coreutils and nothing else |

`generate.mjs --check` regenerates into memory and fails if anything would
change. That is the guard against a generator edit that quietly leaves the
committed goldens describing an older format.

**No suite regenerates its fixtures.** A suite that built its own inputs from
today's code would be asserting that today's code agrees with itself. The
goldens are frozen bytes and the digests are written down beside them.

## The fourth implementation

`vectors.json` records `artifact_sha256` and `manifest_digest` for every
vector. Those numbers are produced by `generate.mjs`, which is a fourth
implementation of the two constructions — but a fourth implementation written by
the same hand as the notes is not much of an independent check, and two of the
three readers under test share a SHA-256 (`sha2`).

So `handcheck.sh` computes both numbers again with `dd`, `od`, `printf`, `cat`
and `sha256sum`:

```
$ ./testdata/bundles/handcheck.sh ok-minimal
  entry 0        : MANIFEST.json (method 0, 760 bytes at offset 43)
  sha256(manifest bytes)                  = 2e16024e4557332a2a404a89a94b124807e0b4741046e29fc3f6b94ea1b69682
  sha256("astra.bundle/2\0" || manifest) = 8e88f82cc6dbb9c253e3a4409a03f763668ca1a46439f994e2a45a6da23ccaf4
ac3d49a2fc2b7408d5b3c805ec91541510c272547a16e3bc7a30f269ba801aed  8e88f82…  ok-minimal.astraplugin
```

Nothing of ours is in that path — not node's crypto, not `sha2`, not this
repo's ZIP code. Run it over the whole directory and compare to `vectors.json`;
27 artifact digests and 25 manifest digests match (the two skips are
`manifest-not-first` and `manifest-compressed`, whose entry zero is by
construction not a stored manifest). A shared bug can make three programs agree
with each other. It cannot make them agree with `sha256sum`.

## The two digests

```
artifact digest = sha256(the whole .astraplugin file)
manifest digest = sha256("astra.bundle/2\0" ‖ the stored bytes of MANIFEST.json)
```

The artifact digest is one number in three places: the attestation subject, the
index record, and what the daemon hashes before it extracts a byte. No
canonicalisation questions.

The manifest digest's domain prefix is the whole point of it. Without the
prefix it is `sha256(some bytes)` — the same shape as every `files[].sha256`,
and `files[]` is a list of exactly those. A value lifted from one context would
verify in the other.

## Reading a vector

```json
{
  "name": "collision-ab-c",
  "verdict": "reject",
  "layer": "bundle-structure",
  "why_it_matters": "…",
  "plugin_id": "vector-plugin",
  "version": "1.0.0",
  "platform_key": "linux-x64",
  "artifact_sha256": "…",
  "artifact_size": 1234,
  "manifest_sha256": "…",
  "manifest_digest": "…",
  "legacy_concat_sha256": "…",
  "expect": { "cli": "reject", "daemon": "reject", "registry": "reject" }
}
```

* **`verdict`** — the answer the format's rules give. The right answer.
* **`expect`** — what each implementation does **today**, and what that repo's
  suite asserts.
* **`divergence`** — present only where `expect` disagrees with `verdict`. It is
  a defect record with a test attached: it names the finding, says how bad it
  is, and says how to close it. Closing it turns a suite red until the entry is
  deleted, which is the only way a known gap stays known instead of becoming
  folklore.
* **`layer`** — which gate is expected to catch it, and therefore which one each
  suite asks. `bundle-structure` is the reader in the table above; `plugin-id`
  is `PluginManifest::validate` and the registry's `invalidId`;
  `permissions-hash` is §5.3-D and exists nowhere yet. `expect` means *what that
  repository as a whole does*, not what one function does — a structural reader
  that also policed plugin ids would look like it had a job it does not.
* **`plugin_id` / `version` / `platform_key`** — what a consumer must tell its
  reader the bundle claims to be. The registry bot cross-checks the manifest
  against the *listing*, so without these every vector would be refused for
  saying it is `vector-plugin` when the caller asked about something else, and
  an id-mismatch error would stand in front of the defect each vector is
  actually about.

## The collision

`collision-a-bc` and `collision-ab-c` carry **byte-for-byte identical**
`MANIFEST.json`. One holds an entry named `a` whose content is `bc`; the other
holds an entry named `ab` whose content is `c`.

The retired in-ZIP digest is `SHA256(name₀‖content₀‖name₁‖content₁‖…)` — no
delimiters, no length prefixes, no entry count, no domain separator. Both
archives contribute the bytes `abc`, so:

```
legacy_concat_sha256  0c0e28712aad8b042598cfb95b52d201b955b4c4942e87680404aa446f96e817   collision-a-bc
legacy_concat_sha256  0c0e28712aad8b042598cfb95b52d201b955b4c4942e87680404aa446f96e817   collision-ab-c
```

One number. One legacy `SIGNATURE` authenticates both archives, and a verifier
using that scheme cannot tell which one it is holding. Under v2 the manifest
names each file and pins its digest, so `collision-ab-c` is refused twice over —
`ab` is an entry no manifest line covers, and `a` is a manifest line no entry
satisfies. That is the argument for retiring the old construction, and it is why
the exhaustiveness check has to run in *both* directions.

`legacy_concat_sha256` is recorded for every vector for this one purpose.
Nothing in this project should ever compute it for any other.

## The vectors

### Accepted

| vector | what it is for |
|---|---|
| `ok-minimal` | the control. Every rejection has to be a rejection *of* something |
| `ok-noarch-runtime` | `platform: any/any` and `entry.command: "node"` — how every TypeScript and Python plugin ships |
| `ok-permissions` | a non-empty permission map with a correct `permissions_hash`, so three RFC 8785 implementations are forced to agree on the canonical bytes |
| `ok-legacy-signed` | the retiring `SIGNATURE`/`PUBKEY` pair, last two entries, in order |
| `collision-a-bc` | the honest half of the collision pair |

### Rejected

| vector | the defect it stands for |
|---|---|
| `collision-ab-c` | the concatenation collision, above |
| `extra-file` | an entry the manifest does not list: a file the extractor writes and nothing hashes |
| `missing-file` | a listed file the archive omits: dropping an entry must not look like an intact bundle |
| `duplicate-entry` | two entries named `plugin.toml` — the second overwrites the first *after* the first was hashed |
| `duplicate-entry-case` | `plugin.toml` + `Plugin.TOML`: two entries here, one file on NTFS and APFS |
| `symlink-entry` | the escape is in the link *target*; every path guard in this project checks the entry name |
| `content-digest-mismatch` | right file set, wrong bytes, same length |
| `size-mismatch` | the declared size is what bounds streaming extraction |
| `mode-mismatch` | the manifest's mode is what gets applied |
| `uppercase-digest` | digests are compared as strings; an uppercase one never matches anything |
| `unsorted-files` | `files` is specified sorted, so a reader may binary-search it |
| `manifest-not-first` | invariant 1. Moving the manifest must never fall back to the pre-v2 rules |
| `manifest-compressed` | reading it must not require inflating unchecked bytes |
| `header-disagree` | the central directory points at a manifest that is not the one at byte zero |
| `path-traversal` | `../escape` — zip-slip |
| `path-ads` | `bin/fixture:stream` writes *into* `bin/fixture` on Windows, invisibly |
| `path-trailing-dot` | Windows strips it, so two entries become one file |
| `entry-command-shell` | `entry.command: "sh"` turns unconstrained `args` into arbitrary code |
| `entry-command-escape` | `../../../bin/sh` — the install directory is the jail |
| `plugin-id-traversal` | `plugin.id` becomes `<plugins_dir>/<id>`, which is created and `remove_dir_all`'d |
| `plugin-id-con` | a Windows device name: installable on Linux, impossible on Windows, invisible to Linux CI |
| `permissions-hash-mismatch` | `permissions` and `permissions_hash` describe different plugins |

### Cases added beyond the plan's list, and why

The plan (§6, task 3.11) names the collision, an extra file, a missing file, a
duplicate name, a symlink, `../evil`, `con`, and a bad permissions hash. These
are the additions:

* **`header-disagree`** — the most v2-specific attack there is. The central
  directory is appended last and nothing in the ZIP format forces it to describe
  the archive it is attached to. The registry bot reads the central directory;
  the daemon reads the local header at offset 0. Left unchecked, the registry
  hashes, displays and countersigns a manifest no daemon will ever enforce.
  Reading both and comparing is the only way to notice.
* **`manifest-not-first` / `manifest-compressed`** — invariant 1 is what lets a
  reader learn what the archive is *allowed* to contain before it has trusted
  any of it. Without vectors, losing it is silent: reordering one entry would be
  enough to switch off per-file hashing, which is the only thing v2 adds.
* **`content-digest-mismatch`** — the plan's cases are all about the file *set*.
  This is the *content* half, and it is the one a swapped binary trips.
* **`size-mismatch` / `mode-mismatch` / `uppercase-digest` / `unsorted-files`** —
  the other fields of a `files[]` line. Each is compared somewhere, so each can
  stop being compared somewhere.
* **`duplicate-entry-case`** — `duplicate-entry` with the collision moved from
  the ZIP into the filesystem. It is the variant an exact-match `seen` set does
  not see, and it found a real divergence (F1).
* **`path-ads` / `path-trailing-dot`** — Windows hazards that a Linux CI cannot
  discover by running anything. They have to be asserted from a fixture or not
  at all.
* **`entry-command-shell` / `entry-command-escape`** — `entry.command` is the
  one field in the manifest that becomes an `execve`.
* **`ok-noarch-runtime`** — the positive counterpart to those two: an
  implementation that hardened `entry.command` into "must be a listed file"
  would take the entire scripted half of the catalogue offline, and only an
  accept-vector catches that.
* **`ok-permissions`** — nothing else pins the canonical encoding of the
  permission map, which is compared across a repository boundary.

## Divergences currently recorded

These are in `vectors.json` under `divergence`, and each is asserted by all
three suites. They are not TODOs in a comment; they are failing behaviour with
a test that will change colour when it is fixed.

| | vector | who is out of step |
|---|---|---|
| **F1** | `duplicate-entry-case` | only the daemon folds case before looking for duplicates |
| **F2** | `content-digest-mismatch` | by design: the daemon hashes content during extraction, not here |
| **F3** | `mode-mismatch` | the registry bot does not compare modes at all |
| **F4** | `plugin-id-*` | the CLI validates neither, in `verify` or in `check` |
| **F5** | `permissions-hash-mismatch` | nobody checks the manifest's permission hash against its own permissions |
