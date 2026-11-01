<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `trust.json` `kind_keys` — one key pair per content kind (v1)

**Normative.** Source: design note §5 "Keys", §11a.9 "Keys", §10 guards
"Domain and scope" and "0.2.7 compatibility". Schema:
[`schemas/trust-kind-keys-v1.schema.json`](schemas/trust-kind-keys-v1.schema.json)
(the member, as the root ceremony must publish it). Goldens:
`testdata/content/trust/`.

## 1. The member

`trust.json` (`astra.registry.trust/1`, signed by the compiled roots,
[`docs/en/spec/registry-index.md`](../../docs/en/spec/registry-index.md) §4.2)
gains one member:

```jsonc
"kind_keys": [
  { "kind": "commands", "role": "current", "key_id": "astra-commands-2026a",
    "alg": "ed25519", "public_key": "<base64, 32 bytes>", "not_before": "2026-10-01T00:00:00Z" },
  { "kind": "commands", "role": "next",    "key_id": "astra-commands-2026b",
    "alg": "ed25519", "public_key": "<base64, 32 bytes>", "not_before": "2026-12-01T00:00:00Z" },
  …
]
```

| field | rule |
|---|---|
| `kind` | `commands` \| `characters` \| `models` \| `animsets` \| `packs` \| `games` |
| `role` | `current` \| `next`. **Exactly one of each per kind**; both are pre-authorised |
| `key_id` | `astra-<kind>-<yyyy><letter>`, naming its own kind (the index key's naming) |
| `alg` | `ed25519` |
| `public_key` | base64 of exactly 32 bytes |
| `not_before` | RFC 3339, UTC, `Z`. **`next.not_before` is strictly later than `current.not_before`** |

There is **no `not_after`**: the key AUTHORISATION is long-lived and the short
life belongs to the signatures (§6; design §5, astra-plugins-ops-42's objection,
accepted 2026-11-01). Every `trust.json` re-sign is a root ceremony with the
owner's one passphrase, so a per-key lifetime would make a recurring owner
chore of something nothing gains from.

`games` moves here too (design §5, agreed by astra-plugins-ops-42 on
2026-11-01): its documents are verified with the `games` pair under the domains
`astra.games.index/1` and `astra.games.withdrawn/1`. `spec/games/games-index-v1.md`
§3 still describes compiled `games-current`/`games-next` ids; reconciling it
is lane C's (OPEN.md O-1).

## 2. Scope: a kind key verifies its kind and nothing else

- **A kind key never goes in `index_keys`.** A client that predates `kind_keys`
  reads only `index_keys` (registry-index.md §4.2: "unknown members are kept and
  ignored"), so it can never accept a kind key for the plugin index. The 0.2.7
  guard: the shipped client's `trust.json` parser, run over
  `testdata/content/trust/trust.json`, returns the same `index_keys` it returns
  without the member (design §10; lane L8 runs it).
- A new client verifies `astra.<kind>.*` **only** with the two keys of that
  `kind`. An index key, or another kind's key, never verifies a content document
  (`index/commands/signed-by-index-key.json`, `…/signed-by-models-key.json`), and
  a kind key never verifies `index.json` or `revocations.json`.
- The domain is part of the digest (common-v1.md §1), so the RIGHT key over the
  WRONG domain fails too (`…/signed-under-models-domain.json`).

## 3. Validity

**`not_before` gates validity**, as `index_keys_valid_at` does: a key is usable
at `window_now ≥ not_before`, with `window_now = max(local, server Date)`
(registry-index.md §4.3 — the network may pull "now" forward, never back). The
signer never signs with a key before its `not_before`
(`index/commands/next-before-not-before.json`: refused at 2026-11-15, the same
bytes accepted at 2026-12-31).

## 4. The client's reading: every defect costs the KIND its keys

A client computes, per kind, the set of usable keys. **Any** of the following
gives that kind **no keys at all** — fail closed for the kind, never "skip the
bad row" (which is the `index_keys` rule, and is right there only because two
overlapping index keys can cover for each other; a kind has no third key):

| defect | golden (`trust/kind-keys/`) |
|---|---|
| not exactly one `current` and one `next` row (a duplicate role, or a missing one) | `duplicate-role`, `missing-next` |
| a `role` other than `current` / `next` | `bad-role` |
| an `alg` other than `ed25519` | `bad-alg` |
| a `public_key` that is not 32 bytes of base64 | `bad-public-key` |
| an unparseable `not_before` | `unparseable-not-before` |
| `next.not_before` not strictly later than `current.not_before` | `next-not-later`, `next-earlier` |
| `current` and `next` are the same key | — |
| one of its public keys appears under another kind, or in `index_keys` | `shared-key-across-kinds` (costs BOTH kinds), `kind-key-in-index-keys` |

A row whose `kind` this client does not know is ignored
(`unknown-kind-row` — a later kind must not cost an older client its keys),
except that sharing a public key with it still costs the known kind its keys.

A kind with no keys cannot verify any of its documents: the client keeps the
last verified copies, installs and updates of that kind stop
(`kind-keys-unusable`), and the withdrawn-freshness rule (§7.1) refuses them
anyway once the last verified withdrawn document is 2 h old.

## 5. Signing input and strictness

`digest = SHA-256(astra.<kind>.<doc>/1 ‖ 0x00 ‖ JCS(signed))`, Ed25519
`verify_strict`: `S < L`, canonical point encodings, a small-order public key
or `R` refused. `tools/contentlite.py` is a stdlib reference of exactly this,
checked against RFC 8032 test vector 1; every envelope under `testdata/content/`
is really signed with published TEST keys (`contentlite.test_seed`) — never
trust one outside `testdata/`.

## 6. Signatures are short-lived; rotation needs no ceremony

- **Signature life:** each document carries `expires_at − issued_at ≤ 8 days`
  and a per-(kind, document) serial floor (common-v1.md §2). A stolen signature
  or an old document stops verifying within days, and a still-trusted key
  cannot replay an older document.
- **Routine rotation:** the signer switches from `current` to `next`; clients
  already accept both.
- **The switch is one-way.** The signer never signs with `current` alone once a
  `next`-signed document is served. **A client that has verified a document of
  kind K under K's `next` key retires K's `current` key id on that machine**.
  The verifier tries **every** offered signature against **every** usable key
  and collects every key id that verifies — never stopping at the first — so a
  document dual-signed by `current` and `next` retires `current` whatever order
  its signatures are in (`index/commands/dual-signed-current-first.json`,
  `…-next-first.json`; scenarios `one-way-switch-dual-*`). A document verifies
  when at least one NON-retired key verified it. The client refuses a later document of kind K that only `current` signed (`key-retired`;
  scenario `one-way-switch`). The retirement is by key id, so the ceremony that
  promotes `next` to `current` (same key id) and adds a fresh `next` does not
  un-retire anything.
- **A ceremony happens only** on a compromise, when both keys of a kind are
  spent, or to add a kind. It re-signs `trust.json` without the compromised key
  and with a fresh `next`.
- **Where the keys live:** each private key is generated in
  `/mnt/Storage/Minice/Keys/` and is the secret `ASTRA_<KIND>_SIGNING_KEY` of its
  OWN GitHub environment (`publish-commands`, …), read by its own job, which
  holds no other key (design §5, lane L4).

## 7. The client rules that make a withheld or leaked document harmless

### 7.1 Withdrawn freshness: 2 hours

**A client refuses a new install or an update of kind K when its last
verified fetch of `astra.<K>.withdrawn/1` is older than 2 h**
(`WITHDRAWN_MAX_AGE = 7200` seconds, a client constant, measured from the
moment the fetch verified) — `withdrawn-stale` — **or when its latest fetch of
that document did not verify** — `withdrawn-unverified` — however recent the
previous good one is, **or when the verified document's own `issued_at` is
more than 26 h old** (`WITHDRAWN_MAX_DOC_AGE = 93600`: the daily re-sign plus
the same 2 h) — `withdrawn-stale`. The last clause closes a replay: a
still-unexpired document up to 8 days old, re-served by a stale cache or a
path the attacker controls, verifies on a FRESH fetch, so a fetch clock alone
would read fresh while a takedown signed an hour ago stays hidden (OPEN.md
O-20). An offline user keeps everything installed and is told "cannot check
withdrawals". A cached or blocked index therefore cannot keep installing a
withdrawn item (scenario `withdrawn-freshness`: 0 s and 7200 s allow; 7201 s,
any unverified latest fetch, and a document 26 h + 1 s old refuse).

### 7.2 A `security` row is sticky until a `lift`

Once a client has seen a `security` row covering an installed copy, the copy
**stays disarmed even if a later document omits the row**. The only thing that
re-arms it is a `lift` row `{id, versions, lifts_at}` whose `id` and `versions`
equal the row's and whose `lifts_at` equals the row's `at` — exactly. A lift
with any other `at` re-arms nothing (scenario `sticky-security`: disarmed,
disarmed after the row is dropped, disarmed after a lift with the wrong `at`,
armed only after the exact lift).

- A client remembers sticky rows durably, beside its serial floors.
- A row with an act this client does not know whose `floor_effect` is `disarm`
  is sticky the same way.
- A lift stays in the document for at least 365 days after it was first served,
  so a client that was offline for less than that sees it; one offline for
  longer stays disarmed, which is the safe failure.
- The publisher alarms on any served `lift` that no `M_UNREVOKE` decision made
  (design §5, §10 "Alarms"), so a leaked kind key cannot re-arm copies quietly.
- A document that lifts a `security` row it also carries is a publisher defect
  (rule `lift-not-contradicted`).
