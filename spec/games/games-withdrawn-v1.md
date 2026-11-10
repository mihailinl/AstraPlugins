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

**A lift names a row** when its `repo_id`, `versions` and `entry_id` equal
the row's **as written** and its `lifts_at` equals the row's `at`, exactly.
Nothing else is compared, neither the act nor the reason.

- `versions` is compared as a string: `<= 1.1.9` does not lift `<=1.1.9`, and
  `<=1.1.8` does not either. A lift whose `lifts_at` is one second off lifts
  nothing. A lift without `entry_id` does not name a row that has one, nor
  the other way round.
- `entry_id` is the one member a client does not compare byte for byte: it
  trims and lowercases every entry id it reads, a row's and a lift's alike.
  The publisher copies the row's `entry_id` unchanged, so the two readings
  never disagree about a lift the publisher wrote.
- **Rows that share a subject and an `at` are named by one lift, all of
  them.** That is the banner and the `yank` a foundation cascade writes for
  one dependant (§3), and it is also two separate acts taken on one subject
  with the same `versions` within one second, a `revoke` and a `delist` for
  instance. A lift carries no act, so it cannot tell them apart; the publisher
  removes every row it names, and a moderator who wants one of them back takes
  it again.

**What releases a row on a client**, once it verifies a list with a strictly
greater serial:

| the row | released by |
|---|---|
| `revoke` with `reason_code = security` (sticky) | a lift that names it, and nothing else |
| every other row | the list no longer carrying it; a lift is not needed |

**A row in the same list beats a lift for it.** A client applies a list's
lifts to the rows it remembers, then puts every row the list carries in
force. So for the publisher:

- **`lift-not-contradicted`: no lift names a row of the same list.** The
  lifted row leaves `rows` in the issue that first carries its lift. A list
  that carries both is a publisher defect the signer refuses to sign; a client
  that meets one anyway keeps the row in force.
- **A lift stays in the list.** A client that was offline when the lift was
  first served still has the row remembered and needs to read the lift when it
  returns. The list holds **at most 256 lifts**; only past that is the oldest
  one (the smallest `at`) dropped. A client that missed a dropped lift keeps
  the row in force, which is the safe failure. 256 is a count the document's
  size can always afford: a lift as the catalogue writes it is at most about
  half a kibibyte, so a full list is about 128 KiB, an eighth of the 1 MiB
  the service serves a document up to, and lifts can never crowd a takedown
  out.
- **A lift is a moderator act** (`M_LIFT`), taken like every other: one
  console confirmation, an `at`, a `by` and a `reason_text`, recorded in the
  catalogue's public act log. The list carries the act's `at`; who lifted and
  why are in the log, as they are for a row's own act.
- **A lift lifts what it names and nothing else.** The rows a revoke cascaded
  onto its dependants (§3) are rows of their own subjects and are lifted by
  their own acts.
- **A lifted takedown still counts** toward the limit of 3 takedowns per 24
  hours (§3): revoking and lifting must not be a way around the limit.
- A row taken again after its lift is a new act with a new `at`, so the old
  lift does not name it. Should a new row ever share the subject and the `at`
  of a lift the list still holds, that lift leaves the list: the row wins.

**This is the content kinds' `lift`, with three differences**
([`../content/common-v1.md`](../content/common-v1.md) §6 and §6.5,
[`../content/trust-kind-keys-v1.md`](../content/trust-kind-keys-v1.md) §7.2).
The member is `lifts`, the match is the subject as written plus `lifts_at`,
a row beats its lift, and the rule's name is `lift-not-contradicted`, all as
there. What differs follows the client's reader
(`parse_withdrawn` in Astra's `astra-daemon/src/games/catalogue_kind.rs`),
which is authoritative where this section and it disagree:

1. the subject is `{repo_id, entry_id, versions}`, not `{id, versions}`,
   because a games row is keyed by repository (§2.1);
2. only a `revoke` for `security` is sticky. In the content kinds every row
   is, and here that would make a `yank` permanent until someone remembered
   to lift it;
3. a lift is kept by count (256), not for 365 days, and carries its own `at`.

Goldens: `testdata/games/withdrawn/valid-lift-no-row.json`,
`valid-lift-near-miss.json`, `valid-rows-dropped.json`,
`invalid-lift-contradicted.json` and four schema refusals; `vectors.json`'s
`withdrawn.scenarios` (`sticky-security-revoke`,
`lift-contradicted-row-wins`) hold the rows in force after each list of a
sequence, computed by `withdrawn_in_force` in
`tools/check-games-goldens.py`.

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

A revoke reaches **online Astra only** and cannot undo a session already
running when it landed. Expiry (`games-index-v1.md` §1) stops new installs
and updates, never Play or repair of what is already installed. Link is
refused whenever the index is more than 7 days stale, independent of any
`withdrawn` row.

## 6. Schema

[`schemas/games-withdrawn-v1.schema.json`](schemas/games-withdrawn-v1.schema.json).
