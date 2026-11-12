<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.animsets.index/1`

**Normative.** Source: design note §5 (the `astra.animsets.index/1` row),
§11a.10. Common parts: [`common-v1.md`](common-v1.md). Keys: kind `animsets`.
Schema: [`schemas/animsets-index-v1.schema.json`](schemas/animsets-index-v1.schema.json).
Withdrawals: [`animsets-withdrawn-v1.md`](animsets-withdrawn-v1.md).

## 1. Body

`{schema: "astra.animsets.index/1", serial, issued_at, expires_at, entries}`.

## 2. Entry

An animset is a `.astrapack` with its controller, clips and states. The base
fields (common-v1.md §3), with `artefact.media_type` =
`application/vnd.astra.animpack+zip` (≤ 64 MiB), plus:

| field | note |
|---|---|
| `format` | `astra.animpack` |
| `dimension` | `3d` \| `2d` |
| `parts` | **exactly one**: `animations` for `3d`, `art` for `2d` — a pixel pack IS the look (rule `dimension-part`) |
| `clips` | the number of clip files in the part, 1–4096 (§2.1) |
| `states` | the pack's state names, `^[a-z][a-z0-9_]{0,31}$`, ≤ 64, sorted and unique; may be `[]` (§2.1) |
| `content_confirmed` | common-v1.md §3 |
| `licence` | its one part's facts (common-v1.md §3.1.2): the pack's declared licence, `source: declared` |
| `credits` | `[]` in v1 (common-v1.md §3.2) |
| `thumbnail` | absent in v1 (common-v1.md §3.3): an animset's bundle is exactly its one part |
| `min_astra` | derived, §4 |

### 2.1 `clips` and `states`, from the bytes

Both are read from the files of the animset's one part — the whole
`.astrapack`, paths relative to the zip root (part-digest-v1.md §2) — and from
nothing an author types into a form.

**A clip file** is a file of the part whose path begins `clips/` (at any
depth below it) and whose extension, compared ASCII-case-insensitively, is:

| the part is | a clip file ends in |
|---|---|
| `animations` (`dimension: 3d`) | `.fbx`, `.glb`, `.gltf`, `.vrma` |
| `art` (`dimension: 2d`) | the same four, and `.png`, `.webp` — a 2D pack's sheet IS its animation |

Everything else under `clips/` is not a clip: a `.bin` buffer or a texture
beside a `.gltf`, a `.png` in a 3D pack, a nested `animpack.toml`. A file
outside `clips/` is never one. This is the directory astra-companion's packs
keep every animation file in (`docs/animation-packs.md`: `clips/…`).

**`clips`** is the number of clip files. An archive holds at most 4,096
entries (ingest-v1.md §3 step 2), so the count cannot pass 4,096. **A part
with no clip file is refused at ingest, `E_CONTENT_FORMAT`** (ingest-v1.md §3
step 10): its entry's `clips` could never be at least 1, so it would be
accepted, confirmed and reviewed and then never listed (golden
`archives/hostile/animset-no-clips.astrapack`). The rule is the animset's
alone; a pack inside a character's `.astrachar` is not judged by it.

**`states`**, in this order:

1. **If the pack's root `animpack.toml` declares state rows** — a `[states]`
   table holding at least one sub-table, `[states.<name>]` — the names are
   those sub-tables' names, as written. A plain key of `[states]` (its
   `default`) is not a row.
2. **Otherwise** the names are the file stems of the clip files — the last
   path segment without its final extension — ASCII-lower-cased.

Then, either way: keep only the names that match `^[a-z][a-z0-9_]{0,31}$`,
remove duplicates, sort by code point, and keep the first 64. A name that
does not fit is left out, never rewritten, and never a refusal; `[]` is a
valid result. `states` is a listing for the card. It is not the controller:
the client plays what `animpack.toml` says, whatever this member lists.

`archives/valid/animset-wave.astrapack` holds `clips/a.fbx` and `clips/b.fbx`
and an `animpack.toml` with no state rows: `clips: 2`, `states: ["a", "b"]`.
`animset-states-declared` declares `idle`, `wave` and `Climb-2` over the same
two files: `states: ["idle", "wave"]`. `animset-pixel-sheet` is a 2D pack
whose one clip is `clips/walk.png`.

## 3. Goldens

`testdata/content/index/animsets/` — `no-thumbnail` (the entry a v1 publisher
emits for the wave pack, every derived member re-derived by the checker) and
`valid` (its one part is the ASCII
part-digest golden, `5cbec44c…f255` — paths relative to the pack root, so the
same pack inside a `.astrachar` has the same digest — and its artefact is
`archives/valid/animset-wave.astrapack`), `dimension-2d-animations-part`,
`clips-zero`.

## 4. `min_astra`

The publisher derives the entry's `min_astra` from this table and from nothing
else (common-v1.md §3.4):

| format | format version | lowest Astra release |
|---|---|---|
| `astra.animpack` | 1 | `0.2.8` |

The format and its version are `astrachar.json`'s `format` and
`format_version` (ingest-v1.md §3 step 8).
