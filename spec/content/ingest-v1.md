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
| 3 | per directory entry: not encrypted (flag bit 0); method Stored (0) or Deflate (8) only; not a link: **whenever the made-by host is not DOS (0) and the external attributes' high 16 bits are non-zero**, those bits are a unix mode and must be a regular file or a directory — zip 9.2.0's `get_unix_mode` reads them for ANY non-DOS host, so a host-19 or host-10 symlink is a symlink (goldens `symlink-host-19`, `symlink-host-10`); no Unicode Path extra field (`0x7075`) on any entry, **in its central OR its local header** (the crate refuses it in either, `read/mod.rs:446`; golden `upath-local-only`); the local header names the same bytes, the same method, the same encryption bit and **the same bit 3**; **bit 3 on a Stored entry is refused outright**; the local CRC and sizes equal the central ones, or — with bit 3 — are all zero; with bit 3 the data descriptor sits exactly at the data's end (its `PK\x07\x08` signature optional, no zip64 form) and its CRC and sizes equal the central record's, Deflate included; a directory entry carries no data; and **the entries tile the file**: the first local header at offset 0, each entry's data (and descriptor) followed at once by the next local header, the last one ending exactly where the directory starts — no gap (where a cloaked entry hides), no overlap (a second reading of the same bytes), no prepended data (OPEN.md O-21); and **the directory lists the entries in ascending local-offset order** (golden `manifest-first-by-offset`) | `E_ARCHIVE_ENCRYPTED`, `E_ARCHIVE_METHOD`, `E_ARCHIVE_LINK`, `E_ZIP_HEADERS_INCONSISTENT` |
| 4 | every name: valid UTF-8; the part-digest path rules ([`part-digest-v1.md`](part-digest-v1.md) §2); `archive::safe_rel` (no `.` segment, no `:`, no NUL, no Windows device name — `con` `prn` `aux` `nul`, `com` and `lpt` followed by a digit **or a superscript `¹` `²` `³`**, **`conin$`, `conout$`**, case-insensitively, with or without an extension — no surrounding whitespace or trailing dot); ≤ 240 bytes; ≤ 16 segments; unique under lower-case folding; **and no path both a file and the directory of another entry** (`a.png` beside `a.png/b.png`, compared case-folded) (goldens `name-device-superscript`, `name-device-conin`, `file-and-directory`) | `E_ARCHIVE_NAME_UNSAFE` |
| 5 | ≤ 128 MiB uncompressed in total; ≤ 100 : 1 per deflated entry. Decompression is streamed against a byte budget and NEVER trusts a declared size | `E_ARCHIVE_TOO_LARGE`, `E_ARCHIVE_RATIO` |
| 6 | `.vrm .glb .png .jpg .webp .ktx2` are Stored | `E_ARCHIVE_MUST_BE_STORED` |
| 7 | **the raw read** (§11a.8): every Deflated entry, bit 3 or not, is inflated from its raw bytes and the deflate stream must end EXACTLY at the central directory's `compressed_size`, with the inflated length and CRC equal to the declared ones (drain the inflater before judging the end); the bit-3 descriptor rule itself is checked at step 3 | `E_ZIP_HEADERS_INCONSISTENT` |
| 8 | **the manifest**: `astrachar.json` is the last entry — by directory order, which step 3 made the same as position in the file — ≤ 1 MiB, parses with no duplicate member name, `format` ∈ {`astra.character`, `astra.animpack`}, a supported `format_version` (1) and `schema` (5). Every other file is listed in its `files` with an equal `sha256:` digest and size, and every listed file exists. The verified list becomes the `content_file` rows | `E_BUNDLE_MANIFEST`, `E_BUNDLE_FILE_UNLISTED`, `E_BUNDLE_FILE_DIGEST` |
| 9 | **the blocklist**: no FILE has a `file_sha256` in `content_blocked_file`, and the bundle is not an object deleted for `rights` or `security`. An object deleted as `refused` or `unreferenced` blocks nothing | `E_CONTENT_BLOCKED` |
| 10 | **the format**: **a GLB is whole** — its header's total length equals the file's size and its first chunk ends inside it, so a JSON chunk declared past EOF is not read as the bytes that happen to be there (golden `vrm-chunk-past-eof`); **no external reference** — in a GLB every `images[].uri` and `buffers[].uri` is a `data:` URI; in a `.gltf` each is a relative path with no scheme, no `..`, no leading `/`, that resolves inside the same part to a file present in the archive (goldens `glb-remote-uri`, `gltf-uri-escape`; `animset-gltf-relative-uri` is accepted); **a name and its content agree** — an entry that begins with the GLB magic `glTF` is named `.vrm`, `.glb` or `.vrma`, and an entry so named begins with it; **and a text glTF is named `.gltf`**: an entry NOT so named whose bytes are a JSON object with a top-level `asset` member (sniffed: the first non-whitespace byte is `{`, and only the top-level keys are read) is refused, so a glTF cannot escape the verdict as `clips/avatar.json` or `accessories/x/model.json` (S5; goldens `gltf-named-json-in-animset`, `gltf-named-json-accessory`); `body.file` ends in `.vrm` and is glTF binary carrying the `VRM` (0.x) or `VRMC_vrm` (1.0) extension (goldens `body-renamed-bin`, `accessory-glb-renamed`); **no GLB or `.gltf` — the body, an accessory, an animset clip, in any part and of any class — has a duplicate member name in its glTF JSON** (one reader's `allowRedistribution: false` is another's `true`; a JSON that does not parse must never fall through to "plain", which an animset part does not judge — goldens `vrm-duplicate-key`, `accessory-duplicate-key`, `animset-glb-duplicate-key`); images and audio as §2 | `E_CONTENT_FORMAT` |
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
`.gltf` text file** (its whole content is the glTF JSON), not only the body. The rule is this
page's §4.2, aligned with astra-ce's legal G4/G5; the games gate applies the same
rule since AstraPlugins #123 (`516ba38`, `spec/games/manifest.md` §2.7.3 as that
PR amends it), which superseded #120 (`d1da665`).

**A GLB is classified by its glTF JSON extensions, never by its name**
(coordinator, 2026-11-01). One declaring `VRMC_vrm_animation` (in `extensions`
or `extensionsUsed`) and **no** avatar extension — neither 0.x `VRM` nor 1.0
`VRMC_vrm` — is an ANIMATION: its part needs the `animations` rights
confirmation, not the avatar verdict below, so it is not held for missing
licence meta (golden `animset-vrma`). One carrying an avatar extension anywhere
is an AVATAR and gets the verdict whatever it is called, so a renamed avatar
cannot pass as an animation (golden `vrma-avatar-prohibited`). A PLAIN one — no
avatar extension and no `VRMC_vrm_animation` — gets the verdict **only in a
character or model part** (the body, an accessory); in an animset part, or any
part that is not a character's or model's, it takes that part's rights
confirmation and is never held as Unknown (goldens `animset-plain-glb`, accepted,
and `character-plain-glb-accessory`, held). This is the games gate's rule too
(AstraPlugins #123), so the two agree file for file.

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
- Each meta gives two readings, exactly as astra-companion `src/vrm/meta.rs`
  reads them (`licence_of`, `redistribution_of`, at astra-companion
  `origin/main` `045b0bf`), plus the design's permission rule:

  | | value | reading |
  |---|---|---|
  | 1.0 `allowRedistribution` | `true` | allowed |
  | | `false`, absent, or not a bool (`"true"` is a string) | prohibited |
  | 0.x `licenseName` | `CC0`, or any token beginning `CC_` | allowed |
  | | `Redistribution_Prohibited`, absent, or not a string | prohibited |
  | | `Other`, or **any other token** | **unknown** (the terms are elsewhere) |
  | 1.0 `avatarPermission` / 0.x `allowedUserName` | `everyone` / `Everyone` | allowed |
  | | `onlyAuthor`, `onlySeparatelyLicensedPerson` / `OnlyAuthor`, `ExplicitlyLicensedPerson`, absent (the spec default `onlyAuthor` / `OnlyAuthor`), or not a string | prohibited — named-person licences are refused (open question 8; astra-ce's G5) |
  | | **any other token** | **unknown** |

- The meta's verdict: `Prohibited` if either reading is prohibited; else
  `Unknown` if either is unknown; else `Allowed`. **An unrecognised token is
  never Allowed**: "anything else → Allowed" in the design note covers the
  RECOGNISED permissive values only (coordinator, 2026-11-01). `Unknown` holds
  the version for a moderator (§4.1). Goldens `vrm0-licence-other`,
  `vrm0-user-unrecognised`, `vrm1-avatar-unrecognised` (held),
  `vrm1-redistribution-string` (refused), `model-vrm0-cc-by-nc` (accepted).
- The usage flags go to the index's `licence.usage`.
- **A file carrying BOTH metas is judged on both** (the engine reads 1.0 first
  for display; the verdict here reads both). If their verdicts differ — an
  `Unknown` against an `Allowed` included →
  `E_CONTENT_LICENCE_CONFLICT`. (A reader that stops at the first meta it finds
  would pass `testdata/content/archives/hostile/vrm-metas-disagree.astrachar`,
  whose 0.x meta allows and whose 1.0 meta prohibits; the games gate did, until
#123 — OPEN.md O-2, closed.)

### 4.3 A part with no licence at all

A part with neither readable VRM meta nor a declared licence (`licence_source`
none) → `E_CONTENT_LICENCE_UNDECLARED`. A part whose only VRM file is
`Unknown` is held (§4.1), not refused as undeclared.

### 4.4 The games gate's goldens (AstraPlugins #123)

AstraPlugins #123 (`spec/games-vrm-conflict-kindkeys`, commit `516ba38`) moved
the games gate onto this page's rules and replaced #120's goldens; its
`testdata/games/content/vrm/gen.py` regenerates every file below byte for byte
(checked 2026-11-01). The server's verdict runs these and requires identical
outcomes, pinned by sha256 (design §3.3). `tools/check-content-goldens.py` runs
every one of them, and §3.1's probes, whenever the file is present with the
pinned sha256 (`CONTENT_EXTERNAL_ROOT` points it at another checkout); with a
checkout of `516ba38`, all 22 externals gave the outcome below, and every one
equals #123's own recorded verdict.

| `testdata/games/content/vrm/` | sha256 | verdict |
|---|---|---|
| `allowed-vrm1.vrm` | `c57da68629797f068d4000f9bf23091c000eada6982ef138cbc7e112543abd1a` | Allowed |
| `allowed.vrm` | `73d0f78566d9e4be98c544482c038f88894fab213c04be4ce2286e000d053eea` | Allowed |
| `refused-vrm0-absent-fields.vrm` | `4e77fe322fbc305f8b6aa4687beea0ee4077bccfb024bc06d3d6399994ab310f` | Prohibited |
| `refused-vrm0-named-people.vrm` | `07541a94a5aab6829217da869e37d2ea55a6828e136ce907f54c13265280fd42` | Prohibited |
| `refused-vrm0-only-author.vrm` | `641a9506d0415428d4cdd70ad0ff386b7e049734f737ab15f35fc761bf5100ad` | Prohibited |
| `refused-vrm0-redistribution-prohibited.vrm` | `6b3be446a9f8978cfcf7d78529561f068e4ffb245ea66ca9b849d198c43bb113` | Prohibited |
| `refused-vrm1-absent-fields.vrm` | `c62fb976efa4bd2780612b69788aa884e30997e4d08d31e4b0366d0bb97b6e0a` | Prohibited |
| `refused-vrm1-named-people.vrm` | `2d05c4134c2c35a009687d9a786b7952271ba699c9a4dbb831ef99e941c04e6c` | Prohibited |
| `refused-vrm1-only-author.vrm` | `77f3ea67d6bdf8406986d6f96ffd4d047ef86444aa9d78395859662d3adddb56` | Prohibited |
| `refused-vrm1-redistribution-false.vrm` | `b9a924b811ce5cdc898533144d2dbd37bf50a95d065b8dafc2dc57ae573d9127` | Prohibited |
| `refused-vrm1-redistribution-string.vrm` | `5430e39773e48cfbf03668d38be3ab034f31415738b302b55a2f895b90ea5121` | Prohibited |
| `unknown-no-meta.vrm` | `ad4ad6ba48e49548eb373fda5a6c4d5d369022f3b4a9573869aab95b5f657c81` | Unknown |
| `unknown-vrm0-licence-other.vrm` | `be954a9422ee33471131a3d38353363e8bb8d4ea7e37c7f30e299fc7c0548c5d` | Unknown |
| `unknown-vrm0-licence-unrecognised.vrm` | `e5eaa822262e27f4ae90b6ef7a6e340c9bd6199237038335ae88978c8b1bfe97` | Unknown |
| `unknown-vrm0-user-unrecognised.vrm` | `a488f7305c523de80692b3ee686a275580caad9423d3ae56c7a11ff1877ffb2b` | Unknown |
| `unknown-vrm1-avatar-unrecognised.vrm` | `908ff51c96bb43254bc4d3a37c935f9d5226a6986d80df872d9dde3d4c100dba` | Unknown |
| `vrm-metas-agree.vrm` | `7e3659f5f24a4321f93f99dfcebab31a6c613d12263347eab32dad2213d4d7f5` | Allowed |
| `vrm-metas-disagree.vrm` | `7eec68abf107f779f1ab1a05a18ba20878b7356779441c91a103a5b0900f106e` | Conflict (`E_CONTENT_LICENCE_CONFLICT`) |
| `vrm-metas-unknown-vs-allowed.vrm` | `2f866f53ad2eb0b9e670c4f734599d29bee125e8016dc0bf2550ae1c55280e48` | Conflict (`E_CONTENT_LICENCE_CONFLICT`) |

As a content BODY, `unknown-no-meta.vrm` (a GLB with no VRM extension at all)
fails step 10 before the verdict runs; as an accessory `.glb` it is Unknown and
held, and in an animset it is not judged (§4 above). The verdict function's own
outcome is Unknown either way (OPEN.md O-6).

## 5. Parts

The server derives the parts from the verified file list (part-digest-v1.md
§1), each with its part root (§2: paths relative to it, `""` for a single-file
part): the body named by `astrachar.json` `body.file`; each `animpacks/<id>/` —
or, in a `.astrapack`, the whole zip as ONE pack at the zip root;
each `accessories/<id>/` folder; each standalone image; each audio file. **Every other listed file is refused**
(`E_CONTENT_FILE_OUTSIDE_PARTS`, golden `file-outside-parts`) — a file in no part
would be published without any rights confirmation covering it — except the
character's SETTINGS: **exactly one file, at exactly `<character.dir>/character.toml`**
(astra-companion `docs/character-files.md`: `characters/<id>/character.toml`),
at most 256 KiB, that decodes as UTF-8 and parses as TOML (`E_CONTENT_FORMAT`
otherwise; golden `settings-mp3-bytes`). Any OTHER file named `.toml` is an
ordinary file and needs a part like any other (golden `settings-second-toml`). A
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
