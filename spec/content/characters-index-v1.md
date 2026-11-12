<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.characters.index/1`

**Normative.** Source: design note §5 (the `astra.characters.index/1` row),
§11a.4, §11a.10 (the split into `character`, `model` and `animset`). Common
parts: [`common-v1.md`](common-v1.md). Keys: kind `characters`. Schema:
[`schemas/characters-index-v1.schema.json`](schemas/characters-index-v1.schema.json).
Withdrawals: [`characters-withdrawn-v1.md`](characters-withdrawn-v1.md).

## 1. Body

`{schema: "astra.characters.index/1", serial, issued_at, expires_at, entries}`.

## 2. Entry

A character is **settings only** after the 2026-11-01 split: its body is a
`model` item and its animations are `animset` items, each reviewed and
withdrawn on its own. The base fields (common-v1.md §3), with
`artefact.media_type` = `application/vnd.astra.character+zip` (≤ 64 MiB), plus:

| field | note |
|---|---|
| `format` | `astra.character` |
| `requires` | `[{kind: "model" \| "animset", id, version, digest}]`, 1–16: **exactly one `model`** and any number of animsets, no `(kind, id)` twice (rule `one-model`). `digest` is the required entry's own single part digest ([`part-digest-v1.md`](part-digest-v1.md) §5) |
| `parts` | only what the character itself carries: `character` (a 3D accessory), `art`, `audio`. Never `animations` or `command`. May be empty |
| `content_confirmed` | non-empty whenever `parts` is |
| `needs` | the bundle's closed `needs` tokens (astra-companion `config/bundle.rs` `Need`: `sprite-sheet`, `sprite-filter` today). A client that does not know a token does not offer the entry (`need-unknown`) |
| `licence` | **the item declaration** (common-v1.md §3.1.2), `BeginRequest.licence`, required at `begin` — for a character with no parts and for one with several. Her parts keep their own facts in the service's record, and she is listed only when every part would pass `licence-allowed` on its own |
| `credits` | at most ONE row, from `astrachar.json`'s own `credits`: `{name: <author>, role: "author", url: <its url if https, else null>}`; otherwise `[]` (common-v1.md §3.2) |
| `thumbnail` | the bundle's root `thumb.png`, when present and a PNG of at most 1 MiB; otherwise the member is absent (common-v1.md §3.3). It is also an `art` part of the bundle, like any other standalone image |
| `min_astra` | derived, §5 |

## 3. Client rules

- **Each required item is resolved against ITS kind's signed index** at
  install: the `(id, version)` must be listed and not withdrawn
  (`requires-unavailable`), and `digest` must equal that entry's single part
  digest (**`requires-digest-mismatch`**), whatever the server checked at
  ingest. Scenario `requires-digest-mismatch` runs
  `index/characters/requires-stale-digest.json`, a schema- and rule-valid
  document, against the valid models index.
- A person may install or publish the whole or any part; a model or set used by
  several characters is stored once (content-addressed).
- An older model or animset version a listed character requires stays listed
  in its own index (common-v1.md §3, `version`).

## 4. Goldens

`testdata/content/index/characters/` — `valid`, `no-thumbnail` (the entry a
v1 publisher emits for `archives/valid/character-aiko.astrachar`: no root
`thumb.png`, no manifest credits), `thumb-and-credit` (for
`archives/valid/character-thumb-credits.astrachar`: her `thumb.png` as the
thumbnail and as an `art` part, one `author` credit, and the item's declared
`CC0-1.0` beside a part declared `CC-BY-4.0`), `requires-stale-digest` (valid;
the client refuses it), `requires-no-model`, `requires-two-models`,
`part-kind-animations`.

## 5. `min_astra`

The publisher derives the entry's `min_astra` from this table and from nothing
else (common-v1.md §3.4):

| format | format version | lowest Astra release |
|---|---|---|
| `astra.character` | 1 | `0.2.8` |

The format and its version are `astrachar.json`'s `format` and
`format_version` (ingest-v1.md §3 step 8).
