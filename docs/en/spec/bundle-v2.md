# `.astraplugin` bundle format, version 2 — normative specification

**Status:** normative. This document defines the bytes. It is written so that a
third party who has never seen this repository can implement a verifier from it
alone and get the same verdict as we do on every file in
[`testdata/bundles/`](../../../testdata/bundles/README.md).

**Schema string:** `astra.bundle/2`
**File extension:** `.astraplugin`
**Media type:** none registered; served as `application/octet-stream`.

Requirement words — **MUST**, **MUST NOT**, **SHOULD**, **MAY** — are RFC 2119.
"Reject" means: refuse the bundle whole, do not extract, do not fall back to any
earlier format. There is no partial acceptance in this format.

---

## 0. What this format is and is not

A v2 bundle is a ZIP archive whose **first entry is a manifest that names and
digests every other entry**. That is the whole of the idea. It buys one thing a
v1 bundle (a ZIP with a `plugin.toml` in it) could not buy: a reader learns what
the archive is *allowed* to contain before it has trusted any of the archive's
own structure, and every file that lands on disk is checked against that list.

Three things this format deliberately does **not** do, stated here so no reader
infers them from the presence of digests:

* **It carries no authenticity of its own.** Nothing inside a v2 bundle proves
  who produced it. Authenticity comes from outside the file: a GitHub build
  attestation over `sha256(whole file)`, and a signed registry index that pins
  the same number ([`registry-index.md`](registry-index.md)). The legacy in-ZIP
  `SIGNATURE`/`PUBKEY` pair (§11) is *not* an exception — it is retiring and is
  never a trust signal.
* **It says nothing about what the plugin may do at runtime.** That is
  [`permissions.md`](permissions.md).
* **It is not a sandbox boundary.** An installed plugin is a native process
  running with the user's full privileges. Verifying a bundle tells you the
  bytes are the bytes the author published; it does not constrain what those
  bytes do once they run.

## 1. Conformance, and which implementation is normative

Three programs read this format:

| | implementation | role |
|---|---|---|
| **CLI** | `astra-plugin-cli/src/bundle.rs` (`BundleBuilder`, `Bundle::open`) | writes bundles; `astra-plugin verify` reads them back |
| **daemon** | `Astra/astra-rs/astra-daemon/src/plugins/bundle.rs` (`inspect`, `BundleManifest::check_structure`) + `ops/install_plugin.rs` (`extract_archive`) | decides whether a stranger's bytes get extracted onto a user's disk |
| **registry** | `astra-registry/bot/lib/bundle.mjs` (`inspectBundle`) | decides whether a listing is published |

**This document is normative; no implementation is.** Where an implementation
disagrees with this text, the implementation has a bug. Where two
implementations disagree with each other, the disagreement is recorded as a
named divergence in `testdata/bundles/vectors.json` and reproduced in §14 — the
`verdict` field there is the right answer and the `expect` field is what each
program does today.

Consequence for a fourth implementation: **implement §13, not any one of the
three programs.** A verifier that reproduces the daemon exactly would inherit
divergence F2; one that reproduces the registry would inherit F3.

## 2. The container

* A bundle **MUST** be a ZIP archive readable by a conventional reader: local
  file headers from offset 0, a central directory, an end-of-central-directory
  record.
* **ZIP64 MUST NOT be used for entry zero.** A `MANIFEST.json` whose local
  header declares the ZIP64 size sentinel `0xFFFFFFFF` is rejected (§4). No
  other entry has a stated ZIP64 restriction; a manifest that large is not a
  manifest.
* Entries are **files only**. A directory entry is rejected (§6.5): directories
  are implied by the paths and cannot carry a digest.
* **Entry zero MUST be `MANIFEST.json`, stored (compression method 0).** Every
  other entry **MAY** use method 0 (stored) or method 8 (deflate). The CLI packs
  everything but the manifest with deflate at level 6; the vectors in
  `testdata/bundles/` are stored throughout. Both are conformant.
* Order: `MANIFEST.json` first; the legacy `SIGNATURE`/`PUBKEY` pair, if present,
  last and in that order (§11); everything else in between. Producers **SHOULD**
  write the middle in byte-lexicographic order of path — the CLI does, because
  its entries live in a `BTreeMap` — but a verifier **MUST NOT** require it. The
  *manifest's* `files` array is sorted and that requirement is enforced (§7.4);
  the archive's own order is not.
* Timestamps carry no meaning. The CLI stamps every entry `1980-01-01T00:00:00`
  (the earliest a DOS timestamp can express) so that two builds of the same
  inputs produce the same bytes. A verifier **MUST NOT** read a timestamp.

## 3. The two digests

Exactly two digest constructions exist in this format. Both are SHA-256, both
are rendered as **64 lowercase hex characters**, and neither is ever compared
case-insensitively.

### 3.1 Artifact digest

```
artifact_digest = SHA256(the entire .astraplugin file, byte for byte)
```

No canonicalisation, no entry walk, no exclusions. This is the number that
appears in exactly three places, and it is the same number in all three:

1. the subject of the GitHub build attestation,
2. `artifacts.<platform>.sha256` in the signed registry index,
3. what the daemon streams and hashes before it opens the archive at all.

It is written bare (no `sha256:` prefix), because every place it appears is
already typed.

### 3.2 Manifest digest — and why it is domain-separated

```
manifest_digest = SHA256( "astra.bundle/2" ‖ 0x00 ‖ MANIFEST.json bytes )
```

The prefix is the 14 ASCII bytes `astra.bundle/2` followed by one `0x00` byte —
15 bytes in total — immediately followed by the *stored* bytes of entry zero,
exactly as they sit in the archive, with no re-serialisation, no whitespace
normalisation and no trailing-newline adjustment.

**Why the prefix exists.** Without it the construction is `SHA256(some bytes)` —
which is precisely the shape of every `files[].sha256` in the same document. The
two would be indistinguishable 64-hex strings travelling through the same
records, and a value lifted from one context would verify in the other. The
prefix makes the manifest digest a different function of the same bytes.

**Worked example** (vector `ok-minimal`, reproducible with
`testdata/bundles/handcheck.sh ok-minimal`, which uses only `dd`, `od`,
`printf`, `cat` and `sha256sum`):

```
sha256(manifest bytes)                    2e16024e4557332a2a404a89a94b124807e0b4741046e29fc3f6b94ea1b69682
sha256("astra.bundle/2\0" ‖ manifest)     8e88f82cc6dbb9c253e3a4409a03f763668ca1a46439f994e2a45a6da23ccaf4
sha256(whole file)                        ac3d49a2fc2b7408d5b3c805ec91541510c272547a16e3bc7a30f269ba801aed
```

An implementation that produces the first value where the second is expected has
forgotten the prefix. `vectors.json` records both numbers (`manifest_sha256` and
`manifest_digest`) for every vector so this is a one-line check, and the two are
**never** equal on any real manifest.

### 3.3 The retired construction, and the collision that retired it

Before v2, a bundle was authenticated by an in-ZIP `SIGNATURE` over

```
legacy_digest = SHA256( name₀ ‖ content₀ ‖ name₁ ‖ content₁ ‖ … )
```

in ZIP index order, skipping `SIGNATURE` and `PUBKEY` themselves. No delimiters,
no length prefixes, no entry count, no domain separator. That construction is
**ambiguous**, and the ambiguity is in this repository as two frozen files:

| vector | archive holds | contributes |
|---|---|---|
| `collision-a-bc` | entry `a`, content `bc` | `a` ‖ `bc` = `abc` |
| `collision-ab-c` | entry `ab`, content `c` | `ab` ‖ `c` = `abc` |

The two archives carry **byte-for-byte identical `MANIFEST.json`** and therefore
identical `manifest_digest`; their artifact digests differ; and their legacy
digests are one number:

```
legacy_concat_sha256   0c0e28712aad8b042598cfb95b52d201b955b4c4942e87680404aa446f96e817   (both)
```

One `SIGNATURE` authenticates both archives, and a verifier using that scheme
cannot tell which one it is holding.

Under v2 they are separated, and it takes **both directions** of the
exhaustiveness check to do it (§7.1): in `collision-ab-c`, `ab` is an archive
entry no manifest line covers, *and* `a` is a manifest line no archive entry
satisfies. A verifier that checked only "listed ⇒ present" would accept it.

`legacy_concat_sha256` is recorded in `vectors.json` for this one purpose.
Nothing in this project should ever compute it for any other.

## 4. Entry zero, byte by byte

A conforming reader **MUST** be able to obtain `MANIFEST.json` from a prefix of
the file, without inflating anything and without reading the central directory.
This is the property that lets a reader learn the archive's allowed contents
before it has trusted attacker-controlled structure. All three implementations
do exactly this (`manifest_from_local_header` in the CLI and the daemon,
`manifestBytesFromLocalHeader` in the registry).

Read the local file header at offset 0. All multi-byte fields are little-endian.

| offset | size | field | requirement |
|---|---|---|---|
| 0 | 4 | signature | **MUST** be `0x04034B50`, else reject: not a ZIP |
| 6 | 2 | general purpose flags | bit 0 (encryption) **MUST** be 0; bit 3 (data descriptor) **MUST** be 0 |
| 8 | 2 | compression method | **MUST** be 0 (stored) |
| 18 | 4 | compressed size | **MUST NOT** be `0xFFFFFFFF` (ZIP64 sentinel); **MUST** be ≤ 4 MiB |
| 26 | 2 | file name length `n` | — |
| 28 | 2 | extra field length `e` | — |
| 30 | `n` | file name | **MUST** be exactly the 13 bytes `MANIFEST.json` |
| 30+`n`+`e` | size | the manifest bytes | — |

**Order the complaints the way the implementations do:** check the *name* before
anything else. An archive whose entry zero is some other file will trip whichever
of the header checks that file happens to fail, and reporting *that* sends the
reader hunting for a problem with a manifest they do not have.

Rejections this produces, with their vectors:

* entry zero is not `MANIFEST.json` → `manifest-not-first`.
* entry zero is compressed → `manifest-compressed`.
* the size runs past the end of the file → truncated bundle.

**A bundle that contains a `MANIFEST.json` anywhere MUST NOT be read as a
pre-v2 bundle.** If the manifest is present but not entry zero, the answer is a
rejection, never a fall-back to the weaker rules. Otherwise moving one entry
would be enough to switch off per-file hashing, which is the only thing v2 adds.
(`manifest-not-first` exists to hold every implementation to this.)

### 4.1 The central directory must agree

Entry zero exists twice: once in the local header at offset 0, and once as the
central-directory record the ZIP reader will use. Nothing in the ZIP format
forces them to describe the same bytes — the central directory is appended last.

A verifier **MUST** read the manifest through *both* paths and compare:

* the CLI and the registry compare the two byte strings / their digests;
* the daemon reads entry 0 via its ZIP reader and compares the bytes to the ones
  it lifted from offset 0.

Vector: `header-disagree`. This is the most v2-specific attack there is. Left
unchecked, the registry hashes, displays and countersigns a manifest no daemon
will ever enforce.

**Which bytes are digested when they agree:** the bytes at offset 0. When they
disagree the bundle is rejected, so the question does not arise.

## 5. `MANIFEST.json`

UTF-8 JSON, one object. The CLI writes it pretty-printed with a trailing
newline; the digest is over whatever bytes are actually written, so formatting
is a producer's choice and a verifier **MUST NOT** re-serialise before hashing.

Complete example — vector `ok-minimal`, the exact bytes that hash to
`2e16024e…`:

```json
{
  "schema": "astra.bundle/2",
  "plugin_id": "vector-plugin",
  "version": "1.0.0",
  "platform": {
    "os": "linux",
    "arch": "x86_64"
  },
  "protocol": 1,
  "min_astra_version": "",
  "capabilities": [
    "tools"
  ],
  "permissions": {},
  "permissions_hash": "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
  "entry": {
    "command": "./bin/fixture",
    "args": []
  },
  "files": [
    {
      "path": "bin/fixture",
      "sha256": "0f7ceb62618162c2ac6765ac683e65dc81ad19add148ada1e7186d186847caba",
      "size": 33,
      "mode": "0755"
    },
    {
      "path": "plugin.toml",
      "sha256": "da1141bb5c5390f1c8a646a0e0b0be1f26cdc0862ccb850dd86e0cd0238f3117",
      "size": 218,
      "mode": "0644"
    }
  ]
}
```

### 5.1 Fields

| field | type | producer | verifier |
|---|---|---|---|
| `schema` | string | **MUST** be `"astra.bundle/2"` | **MUST** compare exactly; any other value → reject, never guess |
| `plugin_id` | string | the plugin id, matching `plugin.toml` | §9 |
| `version` | string | semver | compared against the listing by the registry and the daemon |
| `platform` | `{os, arch}` | see §5.2 | host-compatibility check is the installer's, not the format's |
| `protocol` | integer ≥ 0 | the wire protocol the plugin speaks | range check is the host's |
| `min_astra_version` | string | semver, or `""` for no requirement | — |
| `capabilities` | array of string | the daemon's capability vocabulary | — |
| `permissions` | object | the `[permissions]` section of `plugin.toml`, verbatim | §10 |
| `permissions_hash` | string | `"sha256:" ‖ hex` over §10's canonical bytes | §10 |
| `entry` | `{command, args}` | §8 | §8 |
| `files` | array | §7 | §7 |

**Producers MUST emit every field above.** Verifiers **MUST** reject a manifest
missing `schema`, `plugin_id`, `version`, `platform`, `entry` or `files`.

*Divergence, stated rather than hidden:* the daemon defaults `protocol`,
`min_astra_version`, `capabilities`, `permissions` and `permissions_hash` when
absent (`#[serde(default)]`); the CLI's reader requires them. A bundle omitting
one is therefore installable and unverifiable-by-`astra-plugin verify`. Do not
produce one.

**Unknown members MUST be accepted and ignored.** A later v2 addition (a
`changelog_url`, say) must not make every bundle carrying it uninstallable on an
older host. What cannot change without a schema bump is the *meaning* of the
fields above — and `schema` is compared exactly, which is what bounds this.

### 5.2 `platform`

```json
{"os": "linux",   "arch": "x86_64"}     → registry platform key  linux-x64
{"os": "windows", "arch": "x86_64"}     → registry platform key  windows-x64
{"os": "any",     "arch": "any"}        → registry platform key  noarch
```

`any` on an axis means "no requirement": a bundle is compatible with a host when
`(os == "any" || os == host_os) && (arch == "any" || arch == host_arch)`.
`noarch` is how every TypeScript and Python plugin ships — source or bytecode,
run by a runtime the host already has — and the registry writes the same URL and
digest under every supported platform key for one, so no client needs to learn
the word. Vector: `ok-noarch-runtime`.

No other `{os, arch}` pair names a target today. `linux-arm64`, `windows-arm64`,
`macos-x64` and `macos-arm64` are reserved platform keys in the registry schema;
Astra ships no daemon for them.

## 6. Entry names

Every archive entry name is checked. The rules exist because an entry name
becomes a path on somebody else's filesystem, and the extractor is not the only
thing that reads it.

An entry name is **rejected** if any of these holds:

1. **empty**.
2. contains a **backslash** `\`. ZIP paths use `/` only; a backslash is a path
   separator on Windows and a literal filename character elsewhere.
3. **absolute** — starts with `/`.
4. contains **`:`**. On NTFS `bin/fixture:stream` writes *into* `bin/fixture` as
   an alternate data stream, invisibly. Vector: `path-ads`.
5. contains a **control character** (U+0000–U+001F, U+007F).
6. has an **empty component** (`a//b`), or a component equal to **`.`** or
   **`..`**. Vector: `path-traversal` (`../escape`).
7. has a component ending in a **dot or a space**. Win32 strips both silently, so
   `bin/fixture.` and `bin/fixture` are two entries and one file. Vector:
   `path-trailing-dot`.
8. has a component whose **stem** (the text before the first `.`, compared
   case-insensitively) is a reserved MS-DOS device name: `con`, `prn`, `aux`,
   `nul`, `com1`–`com9`, `lpt1`–`lpt9`. `CON.txt` is the console too.

Additionally:

9. **Duplicate names are rejected**, both exactly and **case-insensitively**:
   `plugin.toml` and `Plugin.TOML` are two entries to a ZIP reader and one file
   on NTFS and APFS, where the second overwrites the first *after* the first was
   hashed. Vectors: `duplicate-entry`, `duplicate-entry-case` (see divergence F1).
10. **Directory entries are rejected** (§2). An entry is a directory if its name
    ends in `/`, or if its external attributes give a Unix mode with
    `mode & 0o170000 == 0o040000`. Check both: the first is what a ZIP writer
    conventionally emits, the second is what a hostile one can emit instead.
11. **Symlink entries are rejected**: an entry whose external attributes give a
    Unix mode with `mode & 0o170000 == 0o120000`. The escape here is in the link
    *target*, which is the entry's *content* — every path rule above inspects the
    name and none of them can see it. Vector: `symlink-entry`.

These rules apply to **every** entry, including `MANIFEST.json`, `SIGNATURE` and
`PUBKEY`.

## 7. `files` — the list the archive is checked against

`files` is an array of objects:

| member | type | rule |
|---|---|---|
| `path` | string | an archive entry name; obeys §6 |
| `sha256` | string | **exactly 64 lowercase hex characters**, no prefix |
| `size` | integer ≥ 0 | uncompressed byte length |
| `mode` | string | four octal digits, e.g. `"0755"` — a *string*, because JSON has no octal literal and `755` decimal is a different mode |

* `sha256` containing any uppercase hex digit is **rejected**, not folded.
  Digests here are compared as strings, so an uppercase one would never match
  anything and would present as a corrupt file rather than a malformed manifest.
  Vector: `uppercase-digest`.
* `mode` **MUST** parse as octal. A leading `0o` is accepted by the daemon's
  parser; producers **MUST NOT** emit it. `"0788"` is rejected — 8 is not an
  octal digit.
* The same `path` **MUST NOT** appear twice.
* A reserved name (`MANIFEST.json`, `SIGNATURE`, `PUBKEY`) **MUST NOT** appear:
  the manifest cannot list its own digest, and the legacy pair is computed *over*
  the listed files.

### 7.1 Exhaustiveness, in both directions

Let `Listed` be the set of `files[].path` and `Present` the set of archive entry
names minus the three reserved names above. A verifier **MUST** enforce:

```
Present ⊆ Listed     (no archive entry that the manifest does not list)
Listed ⊆ Present     (no listed file that the archive does not contain)
```

Both, always. One alone is a hole:

* checking only `Listed ⊆ Present` lets an attacker **add** an entry that the
  extractor writes and nothing hashes — vector `extra-file` (`bin/backdoor`);
* checking only `Present ⊆ Listed` lets them **drop** one and call the bundle
  intact — vector `missing-file`.

And it is the conjunction that separates the collision pair (§3.3).

### 7.2 Content digests

For every entry in `Present`: the SHA-256 of the entry's **uncompressed
content** **MUST** equal the `sha256` of its `files` line. Vector:
`content-digest-mismatch` — the right file set, the right lengths, the wrong
bytes. This is the check a swapped binary trips.

*When* it is performed is an implementation choice with one hard constraint: the
bytes that are hashed **MUST** be the bytes that land on disk. The daemon
therefore hashes during extraction rather than in its pre-extraction pass — see
divergence F2, which is by design and is not a hole.

### 7.3 Sizes

The `size` of every entry **MUST** equal the manifest's. Two independent checks
are appropriate and the daemon makes both: the central directory's declared size
before any work is done (it is attacker-controlled, so this is a cheap lie
detector, not the real check), and a byte count during streaming. The declared
size is what bounds streaming extraction. Vector: `size-mismatch`.

### 7.4 Modes

Where an archive entry carries a Unix mode, `mode & 0o777` **MUST** equal the
manifest's `mode & 0o777`. Where it carries none — an archive written on
Windows — the comparison is skipped; a missing mode is not a defect, a
mismatching one is. The manifest's mode is what an extractor applies. Vector:
`mode-mismatch` (see divergence F3).

Producers normalise: the CLI writes `0755` for anything executable (the resolved
entry binary, the on-disk exec bit, or a path listed in `[bundle] executables`)
and `0644` for everything else. It deliberately does not copy arbitrary on-disk
modes: a checkout under a different umask would otherwise change the bundle's
bytes without changing its content.

### 7.5 Sorted

`files` **MUST** be sorted strictly ascending by `path`, compared as **raw
bytes** (not by Unicode collation, not case-insensitively). The daemon enforces
strict ascent (`w[0].path >= w[1].path` → reject), which also catches the
duplicate case. A verifier is allowed to binary-search this array; an unsorted
one would make that quietly wrong. Vector: `unsorted-files`.

## 8. `entry.command`

`entry.command` is the one field in the manifest that becomes an `execve`. It
**MUST** be either:

* **a host runtime**, matched exactly against the closed list
  `python`, `python3`, `node`, `bun`, `deno`; or
* **a path to a file the manifest lists.** Compare after stripping a leading
  `./` and converting `\` to `/`. The result **MUST** appear in `files[].path`.

Rejected outright:

* empty (after trimming);
* absolute (`/usr/bin/sh`, or a Windows drive-letter prefix such as `C:\…`);
* containing a `..` component — vector `entry-command-escape` (`../../../bin/sh`);
* naming a file the manifest does not list — vector `entry-command-shell` (`sh`).

**On shells.** The registry rejects a shell by name — `sh`, `bash`, `zsh`,
`fish`, `dash`, `csh`, `ksh`, `cmd`, `cmd.exe`, `powershell`, `powershell.exe`,
`pwsh`, `pwsh.exe` — with a distinct error code, because `entry.command: "sh"`
turns unconstrained `args` into arbitrary code. The CLI and the daemon reach the
same verdict through the runtime-or-listed-file rule (a shell is neither). A
conforming verifier only needs the general rule; naming shells separately buys a
better message, not a different outcome.

`entry.args` is an array of strings, defaulting to `[]`. This format places no
constraint on its contents; the host does not interpret it.

**Do not "harden" this into "must be a listed file".** That would take the entire
scripted half of the catalogue offline — every TypeScript and Python plugin runs
through a host runtime. Vector `ok-noarch-runtime` (`entry.command: "node"`,
`platform: any/any`) exists precisely to catch that mistake, and it is an
*accept* vector.

## 9. `plugin.toml` and `plugin.id`

Every bundle **MUST** contain a `plugin.toml` entry, listed in `files` like any
other file. It is the plugin manifest the host parses; its full field reference
is [the manifest reference](../reference/manifest.md).

Two rules belong to *this* document because a bundle can be refused for them:

* `MANIFEST.plugin_id` and `MANIFEST.version` **MUST** agree with what the
  installer was asked for, and with the listing that offers the bundle. Without
  this, a registry entry `foo` could serve an archive whose manifest says `bar`,
  and `bar` would install.
* **`plugin.id` becomes a path component** — `<plugins_dir>/<id>/` — a directory
  the host creates, writes into and recursively deletes. It is therefore
  validated:
  * non-empty, and every character is `[a-z0-9-]` (lowercase ASCII letters,
    digits, hyphen);
  * **MUST NOT** end in a dot or a space (already excluded by the charset; kept
    as a separate rule so relaxing the charset later cannot silently reintroduce
    the hole);
  * **MUST NOT** be a reserved MS-DOS device name under the §6.8 stem rule.

  Vectors: `plugin-id-traversal`, `plugin-id-con` (see divergence F4). `con` is
  installable on Linux, impossible on Windows, and invisible to a Linux CI that
  only runs things.

## 10. `permissions` and `permissions_hash`

`MANIFEST.permissions` is the plugin's `[permissions]` section, copied verbatim:
an object mapping a permission id to a request object
(`{reason?, types?, scopes?}`). Its vocabulary and meaning are
[`permissions.md`](permissions.md); this section defines only the bytes and the
hash.

```
canonical_bytes  = RFC 8785 (JCS) serialisation of the permissions object
permissions_hash = "sha256:" ‖ lowercase_hex( SHA256( canonical_bytes ) )
```

Rules:

* **`null` and `{}` are the same value** — a plugin that asks for nothing — and
  both canonicalise to `{}`. A producer that omits the member and one that
  writes an empty object **MUST** produce the same hash. That hash is
  `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`
  = `sha256("{}")`, and it appears in most of the vectors.
* The `sha256:` prefix is **part of the value**, unlike `files[].sha256`. It
  carries its algorithm because this number is compared across a repository
  boundary — the packer writes it, the registry re-derives it at ingest, the host
  re-derives it before it believes it.
* Empty members are **omitted**, not emitted empty: a request with no reason,
  no types and no scopes is `{}`, never `{"reason":""}`. Two canonical spellings
  of one declaration is exactly the drift this hash exists to prevent.
* JCS in practice: object keys sorted by UTF-16 code unit, no insignificant
  whitespace, strings escaped as RFC 8785 §3.2.2.2 requires. This document's
  values are strings, arrays of strings and objects only — no numbers — so the
  subtle half of JCS (§3.2.2's number canonicalisation) does not arise here.

Worked example (vector `ok-permissions`, the values every implementation is held
to):

```
{"fire_trigger":{"reason":"Fires the on_dice_roll trigger you configure"},"subscribe_events":{"reason":"Watches for command_completed"}}
→ sha256:63dde3632926bc9fb348e0973dbce01d07476a1569cede023edde451b04a6a85
```

and one with arguments, canonicalised:

```
{"set_variable":{"scopes":["plugin"]},"subscribe_events":{"reason":"Watches for command_completed","types":["command_completed","tool_started"]}}
```

A verifier **MUST** recompute the hash from `MANIFEST.permissions` and reject a
manifest that disagrees with its own `permissions_hash`. Vector:
`permissions-hash-mismatch` — the `permissions` block asks for `fire_trigger` and
the `permissions_hash` is the hash of `{}`, i.e. the two describe different
plugins. See divergence F5 for who checks this today.

## 11. The legacy `SIGNATURE` / `PUBKEY` pair

A pre-v2 bundle could carry two extra entries: `SIGNATURE` (base64 of a 64-byte
Ed25519 signature over §3.3's concatenation digest) and `PUBKEY` (base64 of the
raw 32-byte public key). They are **retiring**, and while they exist:

* they are **never** listed in `files` (they are computed over the listed files);
* if either is present, **both MUST be present**, and they **MUST** be the last
  two entries in the archive, `SIGNATURE` then `PUBKEY`. Anything after them
  would be outside what the signature covers. Vector: `ok-legacy-signed` (an
  accept vector — the pair is tolerated, not required).
* **They are not a trust signal.** A key that ships in the archive it
  authenticates proves nothing about who wrote it, and the digest they cover is
  the ambiguous one. A verifier **MUST NOT** treat their presence, validity or
  absence as evidence of anything. The registry emits a warning
  (`W_LEGACY_SIGNATURE_ENTRY`) and continues.

Retirement, named once on each side so the two cannot drift: the CLI's
`LEGACY_PAIR_SUNSET` (`astra-plugin 0.5.0 / Astra 0.4.0`) and the daemon's
`LEGACY_SIGNATURE_SUNSET` (`Astra 0.4.0 (astra-plugin 0.5.0)`). `astra-plugin
build` already does not write them; `astra-plugin sign` is the only thing that
does, and it goes at the sunset together with the daemon's reader.

## 12. Limits

From [`spec/limits.yaml`](../../../spec/limits.yaml), the one place these numbers
are declared:

| limit | value | applies to |
|---|---|---|
| `max_archive_entries` | 10 000 | number of ZIP entries, including `MANIFEST.json` |
| `max_extract_bytes` | 524 288 000 (500 MiB) | total uncompressed bytes |
| manifest ceiling | 4 MiB | `MANIFEST.json` alone |

A bundle exceeding one of these **MUST** be rejected. Apply the entry-count
ceiling **before** allocating one record per entry, and the byte ceiling both to
the manifest's declared sum and to the bytes that actually arrive during
streaming — the declared numbers are the archive's own assertion.

The CLI refuses to *build* past these limits, so an author finds out on their own
machine rather than from a user's failed install.

## 13. The verification algorithm

This is the implementable form. A verifier holds a file and, optionally, an
expectation `(plugin_id, version, platform_key)` from a listing. Every step is a
**reject** on failure.

**A. The file.**
1. `artifact_digest = SHA256(file)`. If an expected digest was supplied and does
   not match, stop here; nothing below is meaningful.

**B. Entry zero, from offset 0.** (§4)
2. Parse the local file header. Name = `MANIFEST.json`; flags bits 0 and 3 clear;
   method 0; size not the ZIP64 sentinel and ≤ 4 MiB; slice out the manifest
   bytes.
3. `manifest_digest = SHA256("astra.bundle/2" ‖ 0x00 ‖ manifest_bytes)`.
4. Parse the manifest as JSON. `schema == "astra.bundle/2"`, exactly.

**C. The central directory.** (§2, §4.1, §12)
5. Open the archive normally. Entry count ≤ 10 000.
6. Entry 0 in the central directory is `MANIFEST.json`, stored, and its bytes
   equal the bytes from step 2.

**D. Structure, before any content.** (§6, §7, §12)
7. Walk the entries in order. For each: apply §6 (name rules, no directory, no
   symlink, no duplicate exact or case-folded).
8. Build `Present` (entry names minus the three reserved names). Check
   `Present ⊆ Listed` and `Listed ⊆ Present`.
9. For each `files` line: 64 lowercase hex `sha256`, parseable four-digit octal
   `mode`, no duplicate `path`, no reserved `path`; the array is strictly
   ascending by `path` as bytes.
10. For each entry in `Present`: declared `size` matches, and — where the archive
    carries a mode — `mode & 0o777` matches.
11. Sum of `files[].size` ≤ 500 MiB.
12. If `SIGNATURE` or `PUBKEY` is present: both are, and they are the last two
    entries in that order.
13. `entry.command` is a listed file or a host runtime (§8).

**E. Content.** (§7.2)
14. For each entry in `Present`, streaming and bounded by the declared size:
    SHA-256 of the uncompressed content equals the manifest's. If the verifier
    also extracts, hash the bytes it writes, not a second read.

**F. Cross-checks the format requires and a structural reader alone cannot make.**
15. `permissions_hash` equals the recomputation from `MANIFEST.permissions`
    (§10).
16. `plugin.toml` parses, and `plugin.id` obeys §9. `plugin_id` / `version` /
    `platform` agree with the listing that offered the bundle, if any.

Steps A–E need only the file. Step F needs the file and the listing.

## 14. Golden vectors

`testdata/bundles/` holds 27 frozen `.astraplugin` files, `vectors.json` (verdict,
layer, both digests, and what each implementation does today) and `SHA256SUMS`.
The two consumers hold vendored copies (`Astra/astra-rs/astra-daemon/testdata/bundles/`,
`astra-registry/tests/vectors/`), refreshed by `tools/vendor-testdata.sh`. Each
suite verifies its copy against `SHA256SUMS` before reading a single vector.

**No suite regenerates its fixtures.** A suite that built its inputs from today's
code would be asserting that today's code agrees with itself.

### Accept (5)

| vector | what it proves |
|---|---|
| `ok-minimal` | the control. Every rejection has to be a rejection *of* something |
| `ok-noarch-runtime` | `platform: any/any` + `entry.command: "node"` — how every TypeScript and Python plugin ships (§5.2, §8) |
| `ok-permissions` | a non-empty permission map with a correct hash — three JCS implementations forced to agree (§10) |
| `ok-legacy-signed` | the retiring pair, last two entries, in order (§11) |
| `collision-a-bc` | the honest half of the collision pair (§3.3) |

### Reject (22)

| vector | rule that rejects it |
|---|---|
| `collision-ab-c` | §7.1, **both** directions |
| `extra-file` | §7.1 `Present ⊆ Listed` |
| `missing-file` | §7.1 `Listed ⊆ Present` |
| `duplicate-entry` | §6.9 exact duplicate |
| `duplicate-entry-case` | §6.9 case-folded duplicate (F1) |
| `symlink-entry` | §6.11 |
| `content-digest-mismatch` | §7.2 (F2) |
| `size-mismatch` | §7.3 |
| `mode-mismatch` | §7.4 (F3) |
| `uppercase-digest` | §7 `sha256` charset |
| `unsorted-files` | §7.5 |
| `manifest-not-first` | §4 |
| `manifest-compressed` | §4 |
| `header-disagree` | §4.1 |
| `path-traversal` | §6.6 (and §7.1: the entry is unlisted) |
| `path-ads` | §6.4 (and §7.1) |
| `path-trailing-dot` | §6.7 (and §7.1) |
| `entry-command-shell` | §8 |
| `entry-command-escape` | §8 |
| `plugin-id-traversal` | §9 (F4) |
| `plugin-id-con` | §9 (F4) |
| `permissions-hash-mismatch` | §10 (F5) |

Note on the three `path-*` vectors: each hides its hostile entry *outside*
`MANIFEST.files`, so a verifier that implements only §7.1 rejects all three. It
should still implement §6 — the day a manifest lists such a path, exhaustiveness
has nothing to say and only the name rules do.

### 14.1 Self-test values

For any implementation, the fastest first check is that both digests of every
vector match `vectors.json`'s `artifact_sha256` and `manifest_digest`. Those
numbers do not come from any of the three programs:
`testdata/bundles/handcheck.sh` derives them again from `dd`, `od`, `printf`,
`cat` and `sha256sum`. 27 artifact digests and 25 manifest digests match — the
two skips are `manifest-not-first` and `manifest-compressed`, whose entry zero is
by construction not a stored manifest. A shared bug can make three programs agree
with each other; it cannot make them agree with coreutils.

## 15. Known divergences

These are in `vectors.json` under `divergence`, and each is asserted by all three
suites — a failing behaviour with a test that changes colour when it is fixed,
rather than a TODO in a comment. **In every row this document's verdict is the
right answer.**

| | vector | who is out of step | why it is where it is |
|---|---|---|---|
| **F1** | `duplicate-entry-case` | only the daemon folds case before looking for duplicates | the CLI and the registry use exact-match sets. Both should fold. |
| **F2** | `content-digest-mismatch` | the daemon's pre-extraction pass accepts it | **by design.** The daemon hashes content *during* extraction, so the bytes hashed are the bytes written. It is not a hole; it is the same check at a different moment. |
| **F3** | `mode-mismatch` | the registry bot does not compare modes at all (warning only) | modes are applied by the installer, not by the registry, so it downgraded the check. §7.4 says compare. |
| **F4** | `plugin-id-*` | the CLI validates neither, in `verify` or in `check` | the daemon's `PluginManifest::validate` and the registry's `invalidId` both refuse. The author's own machine should too. |
| **F5** | `permissions-hash-mismatch` | only the CLI's bundle reader does not recompute the hash | the daemon blocks the install (`PERMISSIONS_HASH_MISMATCH`) and the registry refuses to list (`E_PERMISSIONS_HASH_MISMATCH`). |

If you close one, delete the `divergence` block and set that implementation's
`expect` to the verdict — the suites will tell you the moment you have.

## 16. What a verified bundle does and does not tell you

**Does:** these bytes are exactly the bytes whose manifest lists them, every file
in the archive is accounted for in both directions, nothing extracts outside the
install directory, and the digest you hold is the digest anyone else computing it
over this file will get.

**Does not:** who wrote it (that is the attestation and the signed index —
[`registry-index.md`](registry-index.md)), whether it is currently withdrawn
(that is the revocation list), what it may call at runtime
([`permissions.md`](permissions.md)), or what the process can do to the machine
once it starts. A plugin runs as the user, with the user's privileges. Nothing in
this format changes that, and nothing in Astra's UI may imply it does.

---

*Sources checked while writing this document, all read at the commit this landed
on: `astra-plugin-cli/src/bundle.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/bundle.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs` (`permissions_hash`, `jcs`);
`Astra/astra-rs/astra-plugin-manifest/src/manifest.rs` (`validate`,
`is_reserved_device_name`); `astra-registry/bot/lib/bundle.mjs`;
`astra-registry/tools/lib/canonical.mjs`; `spec/limits.yaml`;
`testdata/bundles/{README.md,vectors.json}` and the vector bytes themselves.*
