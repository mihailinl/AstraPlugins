<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.packs.withdrawn/1`

**Normative.** Source: design note §4 (acts and cascades), §5 (the
`astra.<kind>.withdrawn/1` row, sticky `security`, `lift`). The document's
shape, the acts, the pairing rules, the client's reading of unknown values and
the cascade table are [`common-v1.md`](common-v1.md) §6; the client's 2-hour
freshness bound and the sticky `security` rule are
[`trust-kind-keys-v1.md`](trust-kind-keys-v1.md) §7. Keys: kind `packs`.
Schema: [`schemas/packs-withdrawn-v1.schema.json`](schemas/packs-withdrawn-v1.schema.json).

A separate small document, never rows inside `astra.packs.index/1`: an index
over its cap is refused whole, and a takedown must still reach a client whose
index just failed its size check. Always credential-free, never served stale
(INV-30, TRUST-46).

## 1. What rows this kind carries

Rows of its own, and the cascade of a member (common-v1.md §6.4): a
member's `security` makes the pack **`security`**, `member-withdrawn`
(owner, 2026-11-01); a member's `rights` or `retired` makes it `retired`
(`member-withdrawn` / `member-retired`). A pack act a moderator made stays
when the member is restored. **A packs row never carries `part`** — a pack
has no parts (rule `part-only-rights`).

Goldens: `valid` (the security cascade of the withdrawn model),
`no-cascade` (scenario `cascade-pack-missing`), `row-with-part`.

## 2. Goldens

`testdata/content/withdrawn/packs/`; `testdata/content/vectors.json`
`withdrawn` records each verdict.
