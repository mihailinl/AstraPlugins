<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.games.withdrawn/1`

**Normative.** A separate small signed document (merged plan §1, R23 — not
a `withdrawn[]` array inside `astra.games.index/1`, which an over-cap check
would refuse along with the takedown it carries). Same envelope, same
`kind_keys` key pair and freshness numbers as `games-index-v1.md` §1 and §3,
its own serial floor (tracked separately from the index document's — a
replayed `withdrawn` serial must not hold back a fresh one, and vice versa), and its own client-side size cap — a document this small
has no excuse to ever approach it.

**This list retires the `current` key on its own** (`games-index-v1.md` §3;
minice design §11a.9, 2026-11-02). Key retirement is per document schema, not
per kind: a client that has verified an `astra.games.index/1` that moves the
rotation keeps accepting an `astra.games.withdrawn/1` signed by `current`, and
refuses a `current`-only withdrawn list only after it has verified a withdrawn
list that moves the rotation itself. A document moves the rotation when its
body names `"games-next"` OR the `next` key is among the keys that verified it
(`games-index-v1.md` §3, the union). The client keeps a separate high-water "seen `next`"
mark for this schema — the key id it retired for it — beside the index's
mark, never one mark for the kind. The signer, likewise, never goes back to
`current` for this list once it has served a `next`-signed one, whatever the
index has done. The reason: this list and the index are signed and served on
separate schedules, and a takedown must never be refused because the index
finished its rotation first.

**A ceremony that promotes `next` to `current` is bridged for this list on
its own** (`games-index-v1.md` §3, the bridge). Before the new trust.json is
published, a withdrawn list co-signed by the old `current` and `next` under
`"games-current"` must be the one served. A takedown signed `"games-next"` by
the promoted key would be refused under the new trust.json, and a client
would then drop the last withdrawals it holds.

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
  "rows": [ /* Row, §2.1 */ ],
  "lifts": [ /* Lift, §2.2 */ ]
}
```

`lifts` is optional: a list without the member carries no lift (every list
signed before the member existed is one). The signer writes it in every list
since, `[]` when there is none.

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
| `entry_id` | **mandatory when the repository hosts more than one catalogue entry** (R43 — astra-bepinex alone hosts two). Omitted only for a single-entry repo. Always one a client can read (§2.2, `entry-id-readable`) |
| `act` | `yank` \| `delist` \| `deprecate` \| `revoke` — see §3 |
| `floor_effect` | what a client that does not recognise `act` must still do (§4) |
| `reason_code` | `security` \| `broken` \| `author-request` \| `rights-holder` \| `policy` |
| `reason_text` | shown to the user verbatim; never secrets, never a person's real name beyond what the author/reporter already made public |
| `at` | Unix seconds the act was taken, or the first second after it that no other row or lift of the same subject carries (§2.2, `one-act-per-second`). A takedown that waited over the limit of §3 carries the second it entered the list |

**`security` is always paired with `act = "revoke"`.** A `security` row with
any other act is a contradiction `gi-probe`/ingest must refuse — a security
finding that only "deprecates" an integration is not what the reason code
says it is.

### 2.2 Lift

```jsonc
{
  "repo_id": 987654321,
  "versions": "<=1.1.9",
  "entry_id": "someone/peak-astra",
  "lifts_at": 1798675100,
  "at": 1798761500
}
```

| field | note |
|---|---|
| `repo_id`, `versions`, `entry_id` | the lifted row's own, exactly as that row carried them. `entry_id` is absent when the row had none |
| `lifts_at` | the lifted row's `at` |
| `at` | Unix seconds the lift was taken |

**Why a lift exists.** A `revoke` for `security` is **sticky** on a client:
once a client has verified a list that carries it, the row stays in force
there even when a later list omits it, because after a restart a list that no
longer carries a row is no evidence the row was withdrawn, and a withheld or
replayed list must not re-arm a credential stealer. So omitting the row can
never undo it. A lift is the signed statement that does.

**A lift names a row** when the two have the same **subject** (`repo_id`,
`entry_id`, `versions`) and the lift's `lifts_at` equals the row's `at`,
exactly. Nothing else is compared, neither the act nor the reason.

**How a subject is read.** A client reads a row's subject and a lift's by
these three rules, and the publisher compares subjects by the same three
everywhere it compares them (naming a row, the rules below), never byte for
byte where a client would not:

| member | read as |
|---|---|
| `repo_id` | a non-negative JSON integer. A string or a fraction is no `repo_id`: the row cannot be keyed, the lift is skipped |
| `entry_id` | absent and `null` are the same, **none**, and none equals no id. Otherwise the string is trimmed of leading and trailing white space (Unicode `White_Space`, Rust's `trim`) and lowercased (Unicode lowercase, not ASCII only: `ÜNÏ/Peak` is `ünï/peak`). **Empty once trimmed, or holding a control character, it cannot be read**: the row cannot be keyed, the lift is skipped |
| `versions` | byte for byte, with no trim and no normalisation: `<= 1.1.9` and ` <=1.1.9` are not `<=1.1.9`. An absent member reads as the empty string |

So ` Someone/PEAK-Astra ` names the row of `someone/peak-astra`, a lift whose
`lifts_at` is one second off names nothing, and a lift without `entry_id`
does not name a row that has one, nor the other way round.

A row a client cannot key costs more than that row: **while a list carries
one, the client retracts nothing from it**, and every row in force before it
stays, save a lifted one. Hence the first publisher rule:

- **`entry-id-readable`: every `entry_id` the publisher writes, in a row or
  in a lift, is one a client can read.** An act that would write another is
  refused. Because lowercase is computed from each reader's own Unicode
  tables, which differ between versions for recently added letters, the
  publisher also refuses an act whose `entry_id` holds a non-ASCII character
  that is not already lowercase: an id is written the way every client will
  read it.

**What releases a row on a client**, once it verifies a list with a strictly
greater serial:

| the row | released by |
|---|---|
| `revoke` with `reason_code = security` (sticky) | a lift that names it, and nothing else |
| every other row | the list no longer carrying it; a lift is not needed |

**A row in the same list beats a lift for it.** A client applies a list's
lifts to the rows it remembers, then puts every row the list carries in
force. And a lift carries no act, so it names **every** row of its subject
and second. The publisher therefore holds two more rules, and checks both on
every list before it signs:

- **`lift-not-contradicted`: no lift names a row of the same list.** The
  lifted row leaves `rows` in the issue that first carries its lift. A client
  that meets a list carrying both keeps the row in force.
- **`one-act-per-second`: no two acts' rows of one subject share an `at`**,
  and no row carries the subject and second of a lift the list still holds.
  When an act's row would, the publisher gives it the first free second after
  the act's own; the act is not refused, because a security revoke must not
  wait for a retry. The move ends where an act's own `at` must (below): at
  the signer's clock plus five minutes. With no second free up to there the
  act is refused, never dated later. The only rows of one subject that share
  a second are the two **one** act writes together, the banner and the `yank`
  of a foundation cascade (§3).

**So one lift lifts exactly what one act wrote for that subject at that
second**: one row, or a cascade's banner and its `yank` together. It lifts no
other subject: the rows a revoke cascaded onto its dependants (§3) are rows
of their own subjects and are lifted by their own acts.

**A lift is a moderator act** (`M_LIFT`), taken like every other: one console
confirmation, an `at`, a `by` and a `reason_text`, recorded in the
catalogue's public act log. The list carries the act's `at`; who lifted and
why are in the log, as they are for a row's own act.

**The act says what it lifts.** Beside the subject and `lifts_at` it carries
`kinds`: a non-empty array of distinct values out of `yank`, `delist`,
`deprecate` and `revoke` (a row's `act`, §2.1), the kinds of the rows it is
expected to remove. The publisher refuses the act unless the rows of that
subject and second, in the list or still waiting over the takedown limit,
are of **exactly** those kinds, and says both sets. A row's `at` is not
always its act's `at` (it may have taken the next free second, above), so a
moderator who copies the wrong second would otherwise lift another act's
row, and a client could not tell: `lifts_at` naming a `delist` act's own
second must not release the security `revoke` that sits there. `kinds` is in
the act and so in the public act log. **The list's `lifts` element does not
carry it**: a client matches by subject and `at` alone, and this document
does not change.

The publisher bounds the act:

- **Every act's `at` is Unix seconds, and is not ahead of the signer's
  clock** (beyond five minutes of skew): a withdrawal as much as a lift. A
  row dated in the future is published at once and could then never be
  lifted, because its lift needs `lifts_at` ≤ `at` ≤ the clock. A timestamp
  in milliseconds (10^11 or more) is refused as that.
- **`lifts_at` ≤ `at`.** A lift is dated when it was taken, never before the
  row it lifts.
- **At most 3 lifts of security revokes in any 24 hours**, counted by when
  the signer applies them. The fourth is refused, not queued: a lift is never
  urgent, and one console session must not be able to re-arm everything.
  Lifts of other rows are not counted.
- **A lifted takedown still counts** toward the limit of 3 takedowns per 24
  hours (§3), which is likewise counted by when the signer applies a
  takedown, not by the act's own `at`: revoking and lifting is no way round
  it, and neither is a back-dated act.
- **A takedown still waiting over that limit** has reached no client. A lift
  that names it removes it and writes nothing into `lifts`. When a
  foundation's revoke is lifted, the takedowns it cascaded that are still
  waiting go with it; the ones already in the list keep their rows and need
  their own lifts.

**A lift stays in the list.** A client that was offline when the lift was
first served still has the row remembered and must read the lift when it
returns. The list holds **at most 256 lifts**. When it is full, room is made
in this order, and no other:

1. a lift of a row that was **not** sticky, oldest first. No client needs
   it: the row's absence already released the act;
2. a lift of a security revoke that is **older than 365 days**, oldest first
   (the content kinds' retention). A client offline for longer keeps the row
   in force, which is the safe failure;
3. otherwise nothing leaves, and a new lift of a security revoke is refused:
   "the lift list is full". That takes 256 security lifts in one year.

A lift's age is counted **from when the signer applied it**, not from its
own `at`, which is only bounded from above: a lift honestly dated a year
back is as young as the day it was applied. So no lift of a security revoke
is ever accepted and dropped in the same issue, unpublished; it is kept, or
its act is refused.

256 is a count the document's size can always afford: a lift as the
catalogue writes it is at most about half a kibibyte, so a full list is about
128 KiB, an eighth of the 1 MiB the service serves a document up to, and
lifts can never crowd a takedown out.

**This is the content kinds' `lift`, with three differences**
([`../content/common-v1.md`](../content/common-v1.md) §6 and §6.5,
[`../content/trust-kind-keys-v1.md`](../content/trust-kind-keys-v1.md) §7.2).
The member is `lifts`, the match is the subject plus `lifts_at`, a row beats
its lift, a security lift is kept 365 days and the rule's name is
`lift-not-contradicted`, all as there. What differs follows the client's
reader (`canonical_id` and `parse_withdrawn` in Astra's
`astra-daemon/src/games/catalogue_kind.rs`), which is authoritative where
this section and it disagree:

1. the subject is `{repo_id, entry_id, versions}`, not `{id, versions}`,
   because a games row is keyed by repository (§2.1), and `entry_id` is read
   trimmed and lowercased;
2. only a `revoke` for `security` is sticky. In the content kinds every row
   is, and here that would make a `yank` permanent until someone remembered
   to lift it;
3. a lift carries its own `at`, and the list is bounded by count as well.

Goldens (`testdata/games/withdrawn/`, verdicts in `vectors.json`):
`valid-lift-no-row`, `valid-lift-near-miss` (six lifts one member away from a
row), `valid-rows-dropped`, `valid-lift-entry-id-as-a-client-reads-it`,
`valid-cascade-banner-and-yank`; refused by a rule,
`invalid-lift-contradicted` and its two `entry-id` variants (case and space;
non-ASCII), `invalid-two-acts-one-second`, `invalid-row-entry-id-unreadable`,
`invalid-lift-entry-id-unreadable`; and four schema refusals.
`vectors.json`'s `withdrawn.scenarios` hold the rows in force on a client
after each list of a sequence (`sticky-security-revoke`,
`lift-contradicted-row-wins`, `entry-id-as-a-client-reads-it`,
`unreadable-row-retracts-nothing`, `unreadable-lift-is-skipped`), computed by
`withdrawn_in_force` in `tools/check-games-goldens.py`.

## 3. Acts

| act | effect |
|---|---|
| `yank` | No longer offered or updated to. Installed copies stay; the client offers Update or Rollback. |
| `delist` | Hidden from Browse and Search. Installed copies stay, unaffected otherwise. |
| `deprecate` | A banner with `reason_text`. Nothing else changes. |
| `revoke` | **Link refuses the token at once; Play with it is refused daemon-side.** A restore runs once the game next exits (Play is blocked meanwhile): it removes or restores only files whose current digest still equals what Astra placed — a file the game itself updated since is left alone, with "Verify game files in Steam" shown. The disabled profile stays; Remove is one click. At most 3 automatic restores per client per 24 hours; beyond that, Link and Play stay refused and the remaining restores wait for one tap ("Restore game files for N games"). |

A `revoke` whose `reason_code` is `security` is sticky: only a lift (§2.2)
ends it. Every other act ends when a later list omits its row.

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

A revoke reaches **online Astra only**. A session already running when it
lands is ended only by an engine that holds one bridge token per game profile
(it advertises `supports_bridge_token_sets`): Astra removes the revoked
integration's token from the engine's set and the engine closes that session.
An engine without that support keeps a running session until the game exits;
Link and Play are refused from the next start either way. Expiry (`games-index-v1.md` §1) stops new installs
and updates, never Play or repair of what is already installed. Link is
refused whenever the index is more than 7 days stale, independent of any
`withdrawn` row.

## 6. Schema

[`schemas/games-withdrawn-v1.schema.json`](schemas/games-withdrawn-v1.schema.json).
