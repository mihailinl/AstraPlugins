<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# Content ingest — what the server refuses, and in which order (v1)

**Normative.** Source: design note §3.3 (validation), §11a.8 (zip cloaking),
§11a.10 (models and animsets), §10 "Hostile goldens". Every refusal is HTTP 422
with the token named here, never 401 or 403 (§3.1); the full list is
[`reason-codes.yaml`](reason-codes.yaml). The door shapes (`begin`, chunks,
`finalize`) are §3.1–§3.2 of the note and frozen there; their own tokens
(`chunk_out_of_range`, `chunk_conflict`, the eligibility refusals) belong to the
door table, not to this page.

`tools/check-content-goldens.py` `ingest_bundle` / `ingest_command` is a stdlib
reading of this page over `testdata/content/archives/` and
`testdata/content/commands/`. The real ingest is Rust (lane L1, `plugins-ingest`);
it MUST give the same first code for every golden.

## 1. Before any byte

At `begin`, against the DECLARED values: the size caps (§2), the author's
quota (`E_CONTENT_QUOTA`), the per-author caps of design §3.1, and the declared
bundle sha256 against the blocklist (`E_CONTENT_BLOCKED`). At `finalize`: the
assembled file's sha256 and size equal what `begin` declared
(`E_CONTENT_DIGEST_MISMATCH`).

## 2. Size caps (knobs; compiled to these values, every kind compiled CLOSED)

| | cap | code |
|---|---|---|
| a character / model / animset bundle | 64 MiB (`bundle_max_bytes`) | `E_CONTENT_TOO_LARGE` |
| the VRM body entry | 50 MiB (`vrm_max_bytes`) | `E_CONTENT_TOO_LARGE` |
| a command artefact | 1 MiB (`command_max_bytes`) | `E_CONTENT_TOO_LARGE` |
| one author's live objects plus every upload session whose staging bytes still exist, at its declared size | 1 GiB | `E_CONTENT_QUOTA` |
| an image | ≤ 8192 px per side and ≤ 64 Mpx | `E_CONTENT_IMAGE_DIMENSIONS` |
| an audio file | a type on the audio allowlist | `E_CONTENT_MEDIA_TYPE` |

## 3. A bundle: the order of the checks

A character, model or animset bundle is a zip whose **last** entry is
`astrachar.json` (astra-companion `docs/character-files.md` §1–2,
`src/config/bundle/manifest.rs` `BundleManifest`). The archive rules are the
companion importer's, copied under `plugins/COPIED.md`. **The first step that
fails decides the code.** A server may report more, but the first is the answer
and the one every golden pins.

| step | rule | code |
|---|---|---|
| 1 | **the end record.** The LAST end-record signature in the file's final 65,557 bytes must end the file exactly (`offset + 22 + comment_length = file length`); one disk; both counts equal; its directory must END where the record begins and START with a directory header, and walking exactly the counted number of directory entries must consume exactly `cd_size` bytes — an entry past the count is seen by a reader that walks the directory and not by one that trusts the count (`E_ZIP_HEADERS_INCONSISTENT`; golden `count-short-of-directory`). **No zip64 in v1, in any spelling**: an entry count of `0xFFFF`, a `cd_size` or directory offset of `0xFFFFFFFF`, any directory entry whose compressed size, uncompressed size or local-header offset is `0xFFFFFFFF`, and any `0x0001` extra field in a central or local header are all `E_ZIP_END_RECORD` (goldens `zip64-*`; OPEN.md O-7). (`config/archive/end_record.rs`: the crate searches backwards and skips a record that fails its checks, so a decoy record once let it index millions of entries behind a count of one) | `E_ZIP_END_RECORD` |
| 2 | **the entry count**, read from that record BEFORE any index is built: ≤ 4,096 | `E_ARCHIVE_TOO_MANY_ENTRIES` |
| 3 | per directory entry: not encrypted (flag bit 0); method Stored (0) or Deflate (8) only; not a link (a Unix mode other than a regular file or a directory); no Unicode Path extra field (`0x7075`) on any entry; the local header names the same bytes, the same method, the same encryption bit and **the same bit 3**; **bit 3 on a Stored entry is refused outright**; the local CRC and sizes equal the central ones, or — with bit 3 — are all zero; with bit 3 the data descriptor sits exactly at the data's end (its `PK\x07\x08` signature optional, no zip64 form) and its CRC and sizes equal the central record's, Deflate included; a directory entry carries no data; and **the entries tile the file**: the first local header at offset 0, each entry's data (and descriptor) followed at once by the next local header, the last one ending exactly where the directory starts — no gap (where a cloaked entry hides), no overlap (a second reading of the same bytes), no prepended data (OPEN.md O-21); and **the directory lists the entries in ascending local-offset order** (golden `manifest-first-by-offset`) | `E_ARCHIVE_ENCRYPTED`, `E_ARCHIVE_METHOD`, `E_ARCHIVE_LINK`, `E_ZIP_HEADERS_INCONSISTENT` |
| 4 | every name: valid UTF-8; the part-digest path rules ([`part-digest-v1.md`](part-digest-v1.md) §2); `archive::safe_rel` (no `.` segment, no `:`, no NUL, no Windows device name, no surrounding whitespace or trailing dot); ≤ 240 bytes; ≤ 16 segments; unique under lower-case folding | `E_ARCHIVE_NAME_UNSAFE` |
| 5 | ≤ 128 MiB uncompressed in total; ≤ 100 : 1 per deflated entry. Decompression is streamed against a byte budget and NEVER trusts a declared size | `E_ARCHIVE_TOO_LARGE`, `E_ARCHIVE_RATIO` |
| 6 | `.vrm .glb .png .jpg .webp .ktx2` are Stored | `E_ARCHIVE_MUST_BE_STORED` |
| 7 | **the raw read** (§11a.8): every Deflated entry, bit 3 or not, is inflated from its raw bytes and the deflate stream must end EXACTLY at the central directory's `compressed_size`, with the inflated length and CRC equal to the declared ones (drain the inflater before judging the end); the bit-3 descriptor rule itself is checked at step 3 | `E_ZIP_HEADERS_INCONSISTENT` |
| 8 | **the manifest**: `astrachar.json` is the last entry — by directory order, which step 3 made the same as position in the file — ≤ 1 MiB, parses with no duplicate member name, `format` ∈ {`astra.character`, `astra.animpack`}, a supported `format_version` (1) and `schema` (5). Every other file is listed in its `files` with an equal `sha256:` digest and size, and every listed file exists. The verified list becomes the `content_file` rows | `E_BUNDLE_MANIFEST`, `E_BUNDLE_FILE_UNLISTED`, `E_BUNDLE_FILE_DIGEST` |
| 9 | **the blocklist**: no FILE has a `file_sha256` in `content_blocked_file`, and the bundle is not an object deleted for `rights` or `security`. An object deleted as `refused` or `unreferenced` blocks nothing | `E_CONTENT_BLOCKED` |
| 10 | **the format**: **a name and its content agree** — an entry that begins with the GLB magic `glTF` is named `.vrm`, `.glb` or `.vrma`, and an entry so named begins with it; `body.file` ends in `.vrm` and is glTF binary carrying the `VRM` (0.x) or `VRMC_vrm` (1.0) extension (goldens `body-renamed-bin`, `accessory-glb-renamed`); no `.vrm`/`.glb` JSON chunk has a duplicate member name (one reader's `allowRedistribution: false` is another's `true`); images and audio as §2 | `E_CONTENT_FORMAT` |
| 11 | **the licence verdict** on every entry that begins with the GLB magic and on every `.gltf` (§4) — chosen by CONTENT, never by extension | `E_CONTENT_LICENCE_CONFLICT`, `E_CONTENT_LICENCE_REFUSED`, `E_CONTENT_LICENCE_UNDECLARED`; flag `F_CONTENT_VRM_META_UNKNOWN` |
| 12 | every listed file is in exactly one part (§5) or is the character's settings; the derived parts equal the declared ones (§6) | `E_CONTENT_FILE_OUTSIDE_PARTS`, `E_CONTENT_PARTS_MISMATCH` |

Rust `zip` ≥ 9.0.5 with `ZipArchive::validate_header_consistency`, plus the two
extra checks of step 7, is the server's implementation (§11a.8); the crate
version is pinned in both repositories as the extractor is. Python's `zipfile`
is fooled by a hidden-entry cloak — the stdlib checker here reads raw headers
for that reason.

### 3.1 The cloaking probes (referenced, not copied)

AstraPlugins PR #122 commits these; each MUST be refused with
`E_ZIP_HEADERS_INCONSISTENT`, and the ingest test pins them by sha256 until the
PR merges:

| file | commit | sha256 |
|---|---|---|
| `testdata/zip-cloaking/slack.zip` | `daa9f05` | `71511e42a17bb35af2db71c72f2a45fe95754ce73ddfcda417968a77a92fe6f3` |
| `testdata/zip-cloaking/upath.zip` | `daa9f05` | `4649643cdf69d4e2f650209d73b49c190ea8d9a7d80888d5c1c174af093fc59f` |
| `testdata/zip-cloaking/stored-dd.zip` | `62e8106` | `3841c473f7ade57d1efca72aa33847d9508773df2147797a8bdb873828f691fb` |

## 4. The VRM licence verdict

ONE function, copied from astra-companion `src/vrm/meta.rs` `read_licence`, run
on **every entry whose bytes begin with the GLB magic `glTF`** (whatever it is
called — step 10 then refuses a GLB under a non-GLB name) **and on every
`.gltf` text file** (its whole content is the glTF JSON), not only the body. **The contract is
AstraPlugins PR #120** (`spec/games-vrm-g4` `d1da665`, `spec/games/manifest.md`
§2.7.3 as that PR amends it), aligned with astra-ce's legal G4/G5.

### 4.1 Three outcomes, handled separately

- **`Allowed`** passes.
- **`Unknown`** — no VRM licence meta at all, or meta that cannot be read — is
  **held** for a moderator with `F_CONTENT_VRM_META_UNKNOWN`, whatever §8's
  policy says. Never published without a moderator, never a refusal.
- **`Prohibited`** is refused, `E_CONTENT_LICENCE_REFUSED`.

### 4.2 The rule

- **meta present, a field absent** → the field takes its SPEC DEFAULT
  (astra-companion `src/vrm/meta.rs:80-100`): 1.0 `allowRedistribution → false`,
  `avatarPermission → onlyAuthor`; 0.x `licenseName` absent → prohibited,
  `allowedUserName → OnlyAuthor`. So an absent field REFUSES.
- **redistribution prohibited** (0.x `licenseName = Redistribution_Prohibited`,
  1.0 `allowRedistribution ≠ true`) or **a permission limited to the author or
  to named people** (0.x `OnlyAuthor | ExplicitlyLicensedPerson`, 1.0
  `onlyAuthor | onlySeparatelyLicensedPerson`) → `Prohibited`. Named-person
  licences are refused (open question 8; astra-ce's G5).
- anything else → `Allowed`; the usage flags go to the index's `licence.usage`.
- **A file carrying BOTH metas is judged on both.** If they disagree →
  `E_CONTENT_LICENCE_CONFLICT`. (A reader that stops at the first meta it finds
  would pass `testdata/content/archives/hostile/vrm-metas-disagree.astrachar`,
  whose 0.x meta allows and whose 1.0 meta prohibits — OPEN.md O-2.)

### 4.3 A part with no licence at all

A part with neither readable VRM meta nor a declared licence (`licence_source`
none) → `E_CONTENT_LICENCE_UNDECLARED`. A part whose only VRM file is
`Unknown` is held (§4.1), not refused as undeclared.

### 4.4 PR #120's goldens

The server's verdict runs these and requires identical outcomes, pinned by
sha256 (design §3.3):

| `testdata/games/content/vrm/` | sha256 | verdict |
|---|---|---|
| `allowed.vrm` | `db9765f8f7bc1cd8c85b836a9ffdf8a32577b333cddfca81f8975cf1c9d1da01` | Allowed |
| `allowed-vrm1.vrm` | `c57da68629797f068d4000f9bf23091c000eada6982ef138cbc7e112543abd1a` | Allowed |
| `refused-vrm0-only-author.vrm` | `641a9506d0415428d4cdd70ad0ff386b7e049734f737ab15f35fc761bf5100ad` | Prohibited |
| `refused-vrm1-only-author.vrm` | `77f3ea67d6bdf8406986d6f96ffd4d047ef86444aa9d78395859662d3adddb56` | Prohibited |
| `refused-vrm0-named-people.vrm` | `07541a94a5aab6829217da869e37d2ea55a6828e136ce907f54c13265280fd42` | Prohibited |
| `refused-vrm1-named-people.vrm` | `2d05c4134c2c35a009687d9a786b7952271ba699c9a4dbb831ef99e941c04e6c` | Prohibited |
| `refused-vrm0-redistribution-prohibited.vrm` | `6b3be446a9f8978cfcf7d78529561f068e4ffb245ea66ca9b849d198c43bb113` | Prohibited |
| `refused-vrm1-redistribution-false.vrm` | `b9a924b811ce5cdc898533144d2dbd37bf50a95d065b8dafc2dc57ae573d9127` | Prohibited |
| `refused-vrm0-absent-fields.vrm` | `4e77fe322fbc305f8b6aa4687beea0ee4077bccfb024bc06d3d6399994ab310f` | Prohibited (defaulted) |
| `refused-vrm1-absent-fields.vrm` | `c62fb976efa4bd2780612b69788aa884e30997e4d08d31e4b0366d0bb97b6e0a` | Prohibited (defaulted) |
| `unknown-no-meta.vrm` | `ad4ad6ba48e49548eb373fda5a6c4d5d369022f3b4a9573869aab95b5f657c81` | Unknown |

As a content BODY, `unknown-no-meta.vrm` (a GLB with no VRM extension at all)
fails step 10 before the verdict runs; as an accessory `.glb` it is Unknown and
held. The verdict function's own outcome is Unknown either way (OPEN.md O-6).

## 5. Parts

The server derives the parts from the verified file list (part-digest-v1.md
§1): the body named by `astrachar.json` `body.file`; each `animpacks/<id>/`;
each `accessories/<id>/` folder; each standalone image; each audio file. **Every other listed file is refused**
(`E_CONTENT_FILE_OUTSIDE_PARTS`, golden `file-outside-parts`) — a file in no part
would be published without any rights confirmation covering it — except the
character's SETTINGS, a `.toml` directly in `astrachar.json`'s `character.dir`,
which is configuration and carries no content. A
model has exactly one part (`character`), an animset exactly one (`animations`,
or `art` for 2D), and the index says so (models-index-v1.md, animsets-index-v1.md).

## 6. Declared versus derived

The server refuses parts that differ from what the client declared at `begin`
(`E_CONTENT_PARTS_MISMATCH`); a command's capabilities, danger, platforms and
requires per [`capabilities-v1.md`](capabilities-v1.md) (`E_COMMAND_FORMAT`,
`E_COMMAND_UNKNOWN_ACTION`, `E_COMMAND_UNKNOWN_TRIGGER`,
`E_COMMAND_PLUGIN_UNNAMED`, `E_COMMAND_CAPS_MISMATCH`,
`E_COMMAND_REQUIRES_MISMATCH`, `E_COMMAND_REQUIRES_UNLISTED`). The `declared`
values are kept for the mismatch record; the index carries only the derived.

## 7. References to other items, against the SERVED documents

Every check below reads the documents the registry SERVES (verified under
their kind keys, `E_SERVED_UNVERIFIED` when one does not verify), never the
service's own tables, so Almaty cannot vouch for what it cannot get signed
(design §4 F1).

| upload | rule | code |
|---|---|---|
| pack | ≤ 64 members (knob) | `E_PACK_TOO_MANY_MEMBERS` |
| pack | a member is never a pack | `E_PACK_NESTED` |
| pack | a `game-integration` member is refused until `astra.games.index/1` is served | `E_PACK_MEMBER_KIND_UNSERVED` |
| pack | each `{kind, id, version}` is a listed entry of its kind and no served withdrawn row covers it | `E_PACK_MEMBER_UNLISTED` |
| pack | `digest` equals that entry's `artefact.sha256` | `E_PACK_MEMBER_DIGEST` |
| character | each `requires {kind: model\|animset, id, version}` is listed and not withdrawn | `E_CHARACTER_REQUIRES_UNLISTED` |
| character | `digest` equals that entry's single part digest | `E_CHARACTER_REQUIRES_DIGEST` |
| command | each required plugin has a listed, unrevoked version matching `version_req` | `E_COMMAND_REQUIRES_UNLISTED` |
| any | the slug's reserved prefixes, as for plugins | `E_ID_RESERVED_PREFIX` |

The same checks run again on every later withdrawal, as the cascade of
common-v1.md §6.4.

## 8. Goldens

`testdata/content/archives/valid/` — a body-only model, the wave animset (whose
part is the ASCII part-digest golden), a settings-only character.
`testdata/content/archives/hostile/` — one per row of §3 and §4: a decoy end
record, trailing junk, 10,001 entries, `..`, a non-NFC name, a case collision,
a C1 control character, a symlink, an encrypted entry, a gap between entries,
overlapping entries, a directory entry carrying data, a ratio bomb, a deflated
VRM, a manifest with a duplicate key, a glTF JSON with a duplicate key, a local header naming another file, a Unicode Path extra field, the
manifest first, an unlisted file, a wrong digest, a prohibiting `.glb` beside
an allowed body, redistribution prohibited, a field absent, named people, the
two metas disagreeing, no meta (held), not a GLB, no VRM extension, the allowed
body under a new name against a blocklist, and an audio part with no licence.
Chunk-level refusals (a chunk number past the last, a last chunk too long) are
the door's and lane L1's test.
