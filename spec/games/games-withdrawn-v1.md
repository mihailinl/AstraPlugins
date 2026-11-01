<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.games.withdrawn/1`

**Normative.** A separate small signed document (merged plan §1, R23 — not
a `withdrawn[]` array inside `astra.games.index/1`, which an over-cap check
would refuse along with the takedown it carries). Same envelope, same key
family and freshness numbers as `games-index-v1.md` §1 and §3, its own
per-key serial floor, and its own client-side size cap — a document this
small has no excuse to ever approach it.

## 1. Why a separate document, precisely

`plugins/registry_client.rs::read_capped` refuses an over-cap document
**whole** and keeps the previous verified copy (verified against the shipped
code by the earlier marketplace plan). The index grows with every new
release; a takedown riding inside it would be unreachable by exactly the
clients most likely to need it — the ones whose index has grown past the
cap. Splitting the documents means a revoke can still reach every client
that can fetch *anything* this small.

## 2. Body

```jsonc
{
  "schema": "astra.games.withdrawn/1",
  "serial": 1798675200,
  "issued_at": 1798675200,
  "expires_at": 1799280000,
  "key_id": "games-current",
  "rows": [ /* Row, §2.1 */ ]
}
```

### 2.1 Row

```jsonc
{
  "repo_id": 987654321,
  "versions": "<=1.1.9",
  "entry_id": "someone/peak-astra",
  "act": "revoke",
  "floor_effect": "no-play",
  "reason_code": "security",
  "reason_text": "A dependency pulled in a credential stealer; see advisory GHSA-….",
  "at": 1798675100
}
```

| field | note |
|---|---|
| `repo_id` | keyed by repository, not by catalogue entry id — this is what still reaches a 0.2.7-era install (via an upgraded client) and an address install, neither of which the catalogue otherwise knows about |
| `versions` | a semver range this act covers |
| `entry_id` | **mandatory when the repository hosts more than one catalogue entry** (R43 — astra-bepinex alone hosts two). Omitted only for a single-entry repo |
| `act` | `yank` \| `delist` \| `deprecate` \| `revoke` — see §3 |
| `floor_effect` | what a client that does not recognise `act` must still do (§4) |
| `reason_code` | `security` \| `broken` \| `author-request` \| `rights-holder` \| `policy` |
| `reason_text` | shown to the user verbatim; never secrets, never a person's real name beyond what the author/reporter already made public |
| `at` | Unix seconds the act was taken |

**`security` is always paired with `act = "revoke"`.** A `security` row with
any other act is a contradiction `gi-probe`/ingest must refuse — a security
finding that only "deprecates" an integration is not what the reason code
says it is.

## 3. Acts

| act | effect |
|---|---|
| `yank` | No longer offered or updated to. Installed copies stay; the client offers Update or Rollback. |
| `delist` | Hidden from Browse and Search. Installed copies stay, unaffected otherwise. |
| `deprecate` | A banner with `reason_text`. Nothing else changes. |
| `revoke` | **Link refuses the token at once; Play with it is refused daemon-side.** A restore runs once the game next exits (Play is blocked meanwhile): it removes or restores only files whose current digest still equals what Astra placed — a file the game itself updated since is left alone, with "Verify game files in Steam" shown. The disabled profile stays; Remove is one click. At most 3 automatic restores per client per 24 hours; beyond that, Link and Play stay refused and the remaining restores wait for one tap ("Restore game files for N games"). |

**Foundation cascade.** Revoking a foundation does **not** automatically
revoke its dependants (entries whose `foundation.id` names it) — the default
is a banner plus a `yank` on each dependant; revoking a dependant is an
explicit, per-entry choice inside the same act. Each dependant counts toward
the catalogue-wide limit of 3 takedowns per 24 hours, counted in **its own**
repository, not the foundation's.

## 4. Client behaviour on an unknown `act` (floor effect)

A client that does not recognise `act` still applies `floor_effect` — the
documented minimum every future act must be expressible as:

| `floor_effect` | minimum behaviour |
|---|---|
| `no-offer` | stop offering this version for new installs |
| `no-update` | stop updating installs to this version |
| `no-play` | refuse Play with this version |

This is how an old client, that has never heard of some future fifth act,
still cannot keep installing or playing something the catalogue has pulled —
the whole reason this document exists is that a takedown must work on a
client older than the act that expresses it.

## 5. Scope, stated honestly

A revoke reaches **online Astra only** and cannot undo a session already
running when it landed. Expiry (`games-index-v1.md` §1) stops new installs
and updates, never Play or repair of what is already installed. Link is
refused whenever the index is more than 7 days stale, independent of any
`withdrawn` row.

## 6. Schema

[`schemas/games-withdrawn-v1.schema.json`](schemas/games-withdrawn-v1.schema.json).
