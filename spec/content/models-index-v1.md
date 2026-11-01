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
| `body_kind` | `vrm` \| `pixel`. `format: vrm` ⇒ `body_kind: vrm`; a `pixel` body has no VRM meta, so its licence is `source: declared` (rule `model-format`) |
| `parts` | **exactly one**, `part_kind: character` — the body. For `format: vrm` the single pair's path is `<id>.vrm` (OPEN.md O-4) |
| `content_confirmed` | non-empty |
| `licence` | carries the SERVER-read VRM verdict (`source: vrm`) when the body has readable meta ([`ingest-v1.md`](ingest-v1.md) §4); only an Allowed verdict is ever listed (rule `licence-allowed`) |
| `credits` | common-v1.md §3.2 |

The rights part kind of a model is `character` (§11a.10). Moderation is as for
characters: held until the author is established for the kind (§8 (b)).

## 3. Goldens

`testdata/content/index/models/` — `valid` (its part digest is the body of
`archives/valid/model-aiko.astrachar`), `two-parts`, `format-vrm-body-pixel`,
`licence-vrm-spec-none`, `avatar-author-only`, `vrm0-political-known`.
