<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.commands.withdrawn/1`

**Normative.** Source: design note §4 (acts and cascades), §5 (the
`astra.<kind>.withdrawn/1` row, sticky `security`, `lift`). The document's
shape, the acts, the pairing rules, the client's reading of unknown values and
the cascade table are [`common-v1.md`](common-v1.md) §6; the client's 2-hour
freshness bound and the sticky `security` rule are
[`trust-kind-keys-v1.md`](trust-kind-keys-v1.md) §7. Keys: kind `commands`.
Schema: [`schemas/commands-withdrawn-v1.schema.json`](schemas/commands-withdrawn-v1.schema.json).

A separate small document, never rows inside `astra.commands.index/1`: an index
over its cap is refused whole, and a takedown must still reach a client whose
index just failed its size check. Always credential-free, never served stale
(INV-30, TRUST-46).

## 1. What rows this kind carries

| reason | when |
|---|---|
| `security` (act `security`, floor `disarm`) | `M_REVOKE`: the command is disabled on every client |
| `rights-holder` (act `rights`, floor `disarm`, optional `part` of kind `command`, `art` or `audio`) | a rights act |
| `policy`, `author-request`, `broken` | `M_YANK` / `M_DELIST` (`rights` or `retired`, the moderator's pick), `M_DEPRECATE`, the author's `A_YANK` (`retired`) |
| `requires-unavailable` (act `retired`, `cause: {kind: plugin, id, version}`) | a required plugin was withdrawn and no other matching listed version remains. The command is not disarmed: the plugin's own revocation already disarms the code. A moderator may escalate with `M_REVOKE` |

Goldens: `valid` (one of each, plus a `lift`), the sticky sequence
`seq-1-security` → `seq-4-lift`, and one per rule: `security-reason-retired-act`,
`security-floor-not-disarm`, `rights-floor-no-offer`, `retired-floor-no-offer`,
`part-without-rights`, `cascade-without-cause`, `lift-contradicts-row`,
`bad-act-enum` (refused for the publisher; scenario `client-floor-unknown-act`
shows a client applying its `floor_effect`), `missing-lifts`.

## 2. Goldens

`testdata/content/withdrawn/commands/`; `testdata/content/vectors.json`
`withdrawn` records each verdict.
