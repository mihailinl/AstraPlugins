<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.characters.withdrawn/1`

**Normative.** Source: design note §4 (acts and cascades), §5 (the
`astra.<kind>.withdrawn/1` row, sticky `security`, `lift`). The document's
shape, the acts, the pairing rules, the client's reading of unknown values and
the cascade table are [`common-v1.md`](common-v1.md) §6; the client's 2-hour
freshness bound and the sticky `security` rule are
[`trust-kind-keys-v1.md`](trust-kind-keys-v1.md) §7. Keys: kind `characters`.
Schema: [`schemas/characters-withdrawn-v1.schema.json`](schemas/characters-withdrawn-v1.schema.json).

A separate small document, never rows inside `astra.characters.index/1`: an index
over its cap is refused whole, and a takedown must still reach a client whose
index just failed its size check. Always credential-free, never served stale
(INV-30, TRUST-46).

## 1. What rows this kind carries

Rows of its own (`security`, `rights` with an optional `part` of kind
`character`, `art` or `audio`, `retired`), and the cascade of a required
model or animset (§11a.10, common-v1.md §6.4):

| the required item gets | this character gets |
|---|---|
| `security` | `security`, `member-withdrawn`, `cause` naming it |
| `rights` | `retired`, `member-withdrawn` |
| `retired` | `retired`, `member-retired` |

Goldens: `valid`, `aiko-cascade` (the cascade for a security-withdrawn
model), `no-cascade` (the same served state without it — scenario
`cascade-character-missing` refuses it as `cascade-missing`).

## 2. Goldens

`testdata/content/withdrawn/characters/`; `testdata/content/vectors.json`
`withdrawn` records each verdict.
