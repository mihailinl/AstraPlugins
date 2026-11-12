<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.models.index/1`

**Normative.** Source: design note §5 (the `astra.models.index/1` row),
§11a.10. Common parts: [`common-v1.md`](common-v1.md). Keys: kind `models`.
Schema: [`schemas/models-index-v1.schema.json`](schemas/models-index-v1.schema.json).
Withdrawals: [`models-withdrawn-v1.md`](models-withdrawn-v1.md).

## 1. Body

`{schema: "astra.models.index/1", serial, issued_at, expires_at, entries}`.

## 2. Entry

A model is a VRM body or a body-only `.astrachar`. The base fields
(common-v1.md §3), plus:

| field | note |
|---|---|
| `format` | `vrm` (the artefact IS the `.vrm`, `media_type: model/gltf-binary`, ≤ 50 MiB) \| `astra.character` (a body-only bundle, `application/vnd.astra.character+zip`, ≤ 64 MiB) |
| `body_kind` | `vrm` \| `pixel`. `format: vrm` ⇒ `body_kind: vrm`; a `pixel` body has no VRM meta, so its licence is `source: declared` (rule `model-format`). **`pixel` is unreachable in v1**: ingest accepts a model only when its body is a VRM (ingest-v1.md §3 step 10 — `body.file` ends `.vrm` and carries a VRM extension), so every entry a v1 publisher emits says `vrm`. The word stays in the enum, and the rule stays, so that a later version can admit a pixel body without a new schema; a client that meets it treats it as any entry it cannot show — skipped (common-v1.md §5) |
| `parts` | **exactly one**, `part_kind: character` — the body. A lone `.vrm` body is a single-file part: one pair, path `""` (part-digest-v1.md §2) |
| `content_confirmed` | non-empty |
| `licence` | its one part's facts (common-v1.md §3.1.2): the SERVER-read VRM verdict (`source: vrm`) of the body ([`ingest-v1.md`](ingest-v1.md) §4), so `spdx: null` and `license_url` the meta's own licence URL when it is `https://`, else `null` (rule `licence-vrm-spdx`); only an Allowed verdict is ever listed (rule `licence-allowed`) |
| `credits` | `[]` in v1 (common-v1.md §3.2). A VRM meta's author and contact fields are never copied |
| `thumbnail` | absent in v1 (common-v1.md §3.3): the picture embedded in a `.vrm` has no reader here yet, and a model's bundle may hold nothing but its body |
| `min_astra` | derived, §4 |

The rights part kind of a model is `character` (§11a.10). Moderation is as for
characters: held until the author is established for the kind (§8 (b)).

## 3. Goldens

`testdata/content/index/models/` — `valid` (its part digest is the body of
`archives/valid/model-aiko.astrachar`), `no-thumbnail` (the same entry as a
v1 publisher emits it), `none-listed` (an index with no entry),
`licence-vrm-spdx`, `two-parts`, `format-vrm-body-pixel`,
`licence-vrm-spec-none`, `avatar-author-only`, `vrm0-political-known`.

## 4. `min_astra`

The publisher derives the entry's `min_astra` from this table and from nothing
else (common-v1.md §3.4):

| format | format version | lowest Astra release |
|---|---|---|
| `astra.character` | 1 | `0.2.8` |
| `vrm` | 0.x | `0.2.8` |
| `vrm` | 1.0 | `0.2.8` |

For a body-only bundle the format and version are `astrachar.json`'s; for a
bare `.vrm` (`format: vrm`) the version is the VRM specification the entry's
`licence.spec` names (`vrm0` → 0.x, `vrm1` → 1.0).
