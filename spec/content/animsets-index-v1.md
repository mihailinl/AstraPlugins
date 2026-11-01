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
| `clips` | the clip count, 1–4096 |
| `states` | the controller's state names, `^[a-z][a-z0-9_]{0,31}$`, ≤ 64 |
| `content_confirmed`, `licence`, `credits` | common-v1.md §3 |

## 3. Goldens

`testdata/content/index/animsets/` — `valid` (its one part is the ASCII
part-digest golden, `5cbec44c…f255` — paths relative to the pack root, so the
same pack inside a `.astrachar` has the same digest — and its artefact is
`archives/valid/animset-wave.astrapack`), `dimension-2d-animations-part`,
`clips-zero`.
