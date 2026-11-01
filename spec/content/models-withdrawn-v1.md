<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.models.withdrawn/1`

**Normative.** Source: design note §4 (acts and cascades), §5 (the
`astra.<kind>.withdrawn/1` row, sticky `security`, `lift`). The document's
shape, the acts, the pairing rules, the client's reading of unknown values and
the cascade table are [`common-v1.md`](common-v1.md) §6; the client's 2-hour
freshness bound and the sticky `security` rule are
[`trust-kind-keys-v1.md`](trust-kind-keys-v1.md) §7. Keys: kind `models`.
Schema: [`schemas/models-withdrawn-v1.schema.json`](schemas/models-withdrawn-v1.schema.json).

A separate small document, never rows inside `astra.models.index/1`: an index
over its cap is refused whole, and a takedown must still reach a client whose
index just failed its size check. Always credential-free, never served stale
(INV-30, TRUST-46).

## 1. What rows this kind carries

Rows of its own only — a model requires nothing, so it has no cascade
reason. A `rights` row may name the body part (`part_kind: character`). A
model withdrawn for `security` or `rights` cascades into every character
that requires it and every pack that contains it.

Goldens: `valid`, `aiko-security` (the served state the pack and character
scenarios are judged against), `expiry-span-too-long`.

## 2. Goldens

`testdata/content/withdrawn/models/`; `testdata/content/vectors.json`
`withdrawn` records each verdict.
