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
All three must give the two golden vectors below, bit for bit.

## 1. What a part is

A **part** is a unit of rights: the thing an author confirms they may publish,
keyed so that a confirmation is re-asked only when that unit's bytes or names
change (design §1 decision 5).

| a part is | part kind |
|---|---|
| the body: every file under the body's own path (a single `.vrm` is one pair) | `character` |
| one animation pack: every file under `animpacks/<id>/` | `animations` (a 3D set) or `art` (a 2D/pixel set, because a pixel pack IS the look; §11a.10) |
| one 3D accessory: every file under its own folder (`accessory_parts[]`) | `character` |
| a standalone 2D image | `art` |
| an audio file | `audio` |
| a command's artefact: its one file, named `<id>.command.json` | `command` |

Only `in_file` lines count: a `builtin` or `integration` pack, which carries no
bytes in the bundle, is **not** a part and contributes nothing.

**The part digest keys confirmations and nothing else.** It depends on paths,
so a rename changes it. The blocklist and every deletion work on each FILE's
sha256 (`content_file`), which a rename does not change (design §2, review F2).

## 2. Paths

`path` is the zip entry name relative to the BUNDLE root, with `/` separators,
case preserved, in Unicode NFC. The ingest **refuses the bundle**
(`E_ARCHIVE_NAME_UNSAFE`, [`ingest-v1.md`](ingest-v1.md) §3 step 4) on a name
that is:

| rule (as `tools/contentlite.py` `path_refusal` names it) | |
|---|---|
| `empty` | the empty string |
| `not-nfc` | not equal to its own NFC normalisation |
| `backslash` | contains `\` |
| `leading-slash` | starts with `/` |
| `control-character` | contains a C0 or C1 control character or DEL (U+0000–U+001F, U+007F–U+009F) |
| `empty-segment` | contains `//` (an empty segment) |
| `dot-dot` | has a `..` segment |

so a stored name is already canonical. (A personal export only WARNS
`NAME_NOT_NFC`; the daemon refuses to publish such a name, and this refusal is
the backstop. Each rule has a vector in `testdata/content/vectors.json`
`part_digest_refusals`.)

## 3. The function

1. For each file of the part: `file_sha256` = lowercase hex SHA-256 of its
   bytes, 64 characters, no `sha256:` prefix. An **empty file counts**, with the
   SHA-256 of zero bytes. Directory entries do not count; an empty folder
   contributes nothing.
2. Form the pairs `[path, file_sha256]` — 2-element JSON arrays.
3. Sort the pairs by `path` in **UTF-8 byte order** (no locale collation).
4. Serialise the array with RFC 8785 JCS: no whitespace, minimal string
   escaping, non-ASCII emitted as raw UTF-8.
5. `part_digest` = lowercase hex SHA-256 of those UTF-8 bytes.

## 4. Golden vectors

Both are committed as files, so a reader re-computes them from bytes rather
than from this page: `testdata/content/part-digest/ascii/…`,
`testdata/content/part-digest/non-ascii/…`, and the exact JCS bytes in
`part-digest/ascii.jcs` and `part-digest/non-ascii.jcs`.
`tools/check-content-goldens.py` re-computes both on every run.

**ASCII** — an animation pack, part kind `animations`:

| path | bytes |
|---|---|
| `animpacks/wave/animpack.toml` | `name = "wave"\n` |
| `animpacks/wave/clips/a.fbx` | `FBX-A` |
| `animpacks/wave/clips/b.fbx` | `FBX-B` |

```
[["animpacks/wave/animpack.toml","9ee744a91926a20f1e6413aa98e9afb7139448f9a107e8dcbc83e2006991f1d6"],["animpacks/wave/clips/a.fbx","cf26079b909b3f27c5ee34d729283bfae6473018a64ecf5a39530bd6c0016c2d"],["animpacks/wave/clips/b.fbx","95ee5323ae74ee42371d2ebf7b7c4fd21e216d5760ca94e62c1a75dcd19b89ea"]]
```

part digest **`de7753f5f2d78d89e07a1c6dde87c6549e9ada36afb5d1db7406d4d3157e2588`**.
The same three files are the whole of `testdata/content/archives/valid/animset-wave.astrapack`'s
part, and the valid `animsets` index names this digest.

**Non-ASCII** — the path `animpacks/волна/clips/ü.fbx` (NFC); its bytes are the
UTF-8 of `OGG-FBX-ü-body` (`4f 47 47 2d 46 42 58 2d c3 bc 2d 62 6f 64 79`),
file sha256 `906e3479d575970545fd6fd8991c187c04ef336e7bd09b766c1866cc76c42c27`;
part digest **`66c85d350c3c7ea28cc901483ffd3cc461ab0d95d36d2fd27d98942fc1ca39c9`**.

## 5. Where it is used

- `parts[].digest` in every index entry that carries parts (common-v1.md §3).
- `requires[].digest` in a character entry is the required model's or animset's
  own single part's digest — a model and an animset each have exactly one part
  (§11a.10). The client checks it against that signed entry and refuses
  `requires-digest-mismatch`.
- A `rights` withdrawn row's optional `part` reference.
- The server refuses an upload whose derived parts differ from the ones the
  client declared at `begin` (`E_CONTENT_PARTS_MISMATCH`, ingest-v1.md §6).
