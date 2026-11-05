<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# The part digest (v1)

**Normative.** Source: design note §2 "The part digest" (the function shared
with the engine's `InspectCharacterFile` report, astra-companion-5f,
2026-11-01) and §11a.9 "One part digest". Implemented in astra-companion
`src/config/bundle/part_digest.rs` (branch `bundle/part-digests` f5ea16f), in
`tools/contentlite.py` `part_digest` here, and in the server's ingest (lane L1).
All three must give the three golden vectors below, bit for bit.

**Changed 2026-11-01 (agreed with astra-companion-5f): paths are relative to
the PART ROOT, not the bundle root.** A pack inside a `.astrachar` sits at
`animpacks/<id>/…` while a published `.astrapack` holds it at the zip root, and
`<id>` varies per machine (`moves (2)`), so under bundle-root paths the same
bytes got different digests and the catalogue could not see that a character's
referenced set IS the animset item.

## 1. What a part is

A **part** is a unit of rights: the thing an author confirms they may publish,
keyed so that a confirmation is re-asked only when that unit's bytes or names
change (design §1 decision 5).

| a part is | part kind | part root |
|---|---|---|
| the body: a lone `.vrm` (v1's only body shape, `body.file` ends in `.vrm`) | `character` | none — a **single-file** part |
| the body, were it a folder | `character` | that folder |
| one animation pack: `animpacks/<id>/` in a `.astrachar`, the whole zip in a `.astrapack` | `animations` (a 3D set) or `art` (a 2D/pixel set, because a pixel pack IS the look; §11a.10) | its own directory: `animpacks/<id>/` in a `.astrachar`; the zip root of a `.astrapack` |
| one 3D accessory: every file under its own folder (`accessory_parts[]`) | `character` | its own folder |
| a standalone 2D image | `art` | none — single-file |
| an audio file | `audio` | none — single-file |
| a command's artefact | `command` | none — single-file |

Only `in_file` lines count: a `builtin` or `integration` pack, which carries no
bytes in the bundle, is **not** a part and contributes nothing.

**How an animation pack's kind is read** (agreed with the engine,
astra-companion-2c `src/avatar_kind.rs::parse_token`, and the architect,
minice-b9, 2026-11-05): the kind comes from the pack's OWN `animpack.toml` at
its part root — `animpacks/<id>/animpack.toml` in a `.astrachar`, the zip
root of a `.astrapack` — read from `[animpack] kind`. Normalise: trim exactly
Rust `char::is_ascii_whitespace` (space, `\t`, `\n`, `\x0c`, `\r` — **not**
`\x0b`, so a leading vertical tab is not trimmed and the token is left
unrecognised), then ASCII-lowercase. `pixel` or `2d` → `art`; anything else,
including an absent `kind`, → `animations`. An `animpack.toml` that does not
parse as TOML, or a `kind` that is present but not a string, refuses the
bundle (`E_BUNDLE_MANIFEST`) rather than defaulting. If the bundle's own
manifest ALSO names a kind for the same pack — the `.astrachar` character
manifest's `packs[]` entry for that pack's id, or a `.astrapack` manifest's
own top-level `kind` — and it normalises to a different answer, the bundle is
refused the same way: a name agrees with its content, the rule already
applied to the GLB magic (ingest-v1.md §3 step 8).

**The part digest keys confirmations and nothing else.** The blocklist and every
deletion work on each FILE's sha256 (`content_file`), whatever its path
(design §2, review F2).

## 2. Paths

**`path` is the file's path relative to its PART ROOT** (§1's last column),
with `/` separators, case preserved, in Unicode NFC: `clips/a.fbx`, never
`animpacks/wave/clips/a.fbx`. So the same pack has ONE digest whether it sits
at a `.astrapack`'s zip root or inside a `.astrachar` under any `<id>`.

**A single-file part has ONE pair, whose path is the empty string `""`.** Its
digest therefore depends on the file's sha256 alone, and a rename never changes
it.

Paths are DERIVED from zip entry names, and the ingest **refuses the bundle**
(`E_ARCHIVE_NAME_UNSAFE`, [`ingest-v1.md`](ingest-v1.md) §3 step 4) on an ENTRY
NAME that is:

| rule (as `tools/contentlite.py` `path_refusal` names it) | |
|---|---|
| `empty` | the empty string — an entry name; the derived `""` of a single-file part is not an entry name and is never subject to it |
| `not-nfc` | not equal to its own NFC normalisation |
| `backslash` | contains `\` |
| `leading-slash` | starts with `/` |
| `control-character` | contains a C0 or C1 control character or DEL (U+0000–U+001F, U+007F–U+009F) |
| `empty-segment` | contains `//` (an empty segment) |
| `dot-dot` | has a `..` segment |

so a stored name, and every path derived from it, is already canonical. (A
personal export only WARNS `NAME_NOT_NFC`; the daemon refuses to publish such a
name, and this refusal is the backstop. Each rule has a vector in
`testdata/content/vectors.json` `part_digest_refusals`.)

## 3. The function

1. For each file of the part: `file_sha256` = lowercase hex SHA-256 of its
   bytes, 64 characters, no `sha256:` prefix. An **empty file counts**, with the
   SHA-256 of zero bytes. Directory entries do not count; an empty folder
   contributes nothing.
2. Form the pairs `[path, file_sha256]` — 2-element JSON arrays, `path` per §2
   (relative to the part root; `""` for a single-file part).
3. Sort the pairs by `path` in **UTF-8 byte order** (no locale collation).
4. Serialise the array with RFC 8785 JCS: no whitespace, minimal string
   escaping, non-ASCII emitted as raw UTF-8.
5. `part_digest` = lowercase hex SHA-256 of those UTF-8 bytes.

## 4. Golden vectors

All three are committed as files, so a reader re-computes them from bytes
rather than from this page: `testdata/content/part-digest/{ascii,non-ascii,single-file}/…`,
and the exact JCS bytes in `part-digest/{ascii,non-ascii,single-file}.jcs`.
`tools/check-content-goldens.py` re-computes all three on every run.
astra-companion-5f computed them independently on 2026-11-01 and they agree.

**ASCII** — an animation pack, part kind `animations`, paths relative to the
pack root:

| path | bytes |
|---|---|
| `animpack.toml` | `name = "wave"\n` |
| `clips/a.fbx` | `FBX-A` |
| `clips/b.fbx` | `FBX-B` |

```
[["animpack.toml","9ee744a91926a20f1e6413aa98e9afb7139448f9a107e8dcbc83e2006991f1d6"],["clips/a.fbx","cf26079b909b3f27c5ee34d729283bfae6473018a64ecf5a39530bd6c0016c2d"],["clips/b.fbx","95ee5323ae74ee42371d2ebf7b7c4fd21e216d5760ca94e62c1a75dcd19b89ea"]]
```

part digest **`5cbec44ce0e36e9f2f2b8f0a75a6eb5f5b9f9b5131d7bf50612f68a2727ef255`**.
The same three files are the whole of `testdata/content/archives/valid/animset-wave.astrapack`
(at its zip root) AND the pack `animpacks/moves (2)/` inside
`archives/valid/character-with-pack.astrachar`: **one digest for both**, which
the checker asserts.

**Non-ASCII** — the path `clips/ü.fbx` under the pack root (NFC); its bytes are
the UTF-8 of `OGG-FBX-ü-body` (`4f 47 47 2d 46 42 58 2d c3 bc 2d 62 6f 64 79`),
file sha256 `906e3479d575970545fd6fd8991c187c04ef336e7bd09b766c1866cc76c42c27`;
part digest **`395755a2b649b6c820d1c401b07de8ec06d863d313b39518f541744c7bd80c79`**.

**Single file** — a lone `.vrm` body whose bytes are the ASCII text
`glTF-VRM-test`, file sha256
`98bae0cf35361c8c39a366f238c7954f24b1a13d0014f23e89013b1ab25bd9d2`; one pair
`["", "98bae0cf…d9d2"]`; part digest
**`06c7b7f3a998db259f3dee4471e8542687eeb518982d094fec93744161305e1c`** whatever
the file is called.

## 5. Where it is used

- `parts[].digest` in every index entry that carries parts (common-v1.md §3).
- `requires[].digest` in a character entry is the required model's or animset's
  own single part's digest — a model and an animset each have exactly one part
  (§11a.10). The client checks it against that signed entry and refuses
  `requires-digest-mismatch`.
- A `rights` withdrawn row's optional `part` reference.
- The server refuses an upload whose derived parts differ from the ones the
  client declared at `begin` (`E_CONTENT_PARTS_MISMATCH`, ingest-v1.md §6).
