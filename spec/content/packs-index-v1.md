<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.packs.index/1`

**Normative.** Source: design note §1 decision 11, §3.3 "pack members", §5
(the `astra.packs.index/1` row), §11a.9 ("packs carry NO `min_astra`").
Envelope and freshness: [`common-v1.md`](common-v1.md) §1–§2. Keys: kind
`packs`. Schema: [`schemas/packs-index-v1.schema.json`](schemas/packs-index-v1.schema.json).
Withdrawals: [`packs-withdrawn-v1.md`](packs-withdrawn-v1.md).

## 1. Body

`{schema: "astra.packs.index/1", serial, issued_at, expires_at, entries}`.

## 2. Entry

**A pack is a list of references to items already published.** It carries no
copies, so it cannot be used to get around the review of each kind. Its upload
is only its thumbnail.

| field | note |
|---|---|
| `id`, `version`, `author`, `listing`, `thumbnail`, `review`, `published_at` | common-v1.md §3 |
| `members` | `[{kind, id, version, digest}]`, 1–64 (knob), no `(kind, id)` twice (rule `unique-members`). `kind` ∈ `command`, `character`, `model`, `animset`, `game-integration` — **never `pack`**. `digest` is the member entry's `artefact.sha256` (OPEN.md O-3) |

A pack has **no** `min_astra` (its members gate themselves), **no** `parts`,
`content_confirmed`, `licence` or `credits` (OPEN.md O-8): the card shows each
member's own.

## 3. Client rules

Installing a pack resolves every member against its kind's signed index: the
`(id, version)` listed and not withdrawn (`member-unavailable`), and the
digest equal (`member-digest-mismatch`). A member the client cannot install
(its `min_astra`, an unknown `needs` word) is reported, never silently skipped.

## 4. Goldens

`testdata/content/index/packs/` — `valid` (three members, each pinning a real
artefact), `member-pack`, `min-astra-present`, `licence-present`, `members-65`,
`duplicate-member`; the ingest scenarios `pack-member-*` in
`testdata/content/vectors.json`.
