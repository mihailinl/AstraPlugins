<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# Content documents — what every kind shares (v1)

**Normative.** Source: minice `docs/architecture/2026-11-01-content-catalogue.md`
(the design note; "§n" below is that note) §5, §11a.4, §11a.7, §11a.9, §11a.10.
The per-kind specs (`<kind>-index-v1.md`, `<kind>-withdrawn-v1.md`) add only
what differs. Where the note is ambiguous, the reading chosen here is recorded
in [`OPEN.md`](OPEN.md) with its line, and it is always the refusing one.

The kinds are `commands`, `characters`, `models`, `animsets` and `packs` (the
document kinds, plural). An item's own kind word is singular (`command`,
`character`, `model`, `animset`, `pack`) wherever an entry names another item.

## 1. Envelope and signing

Every document is the plugin envelope, unchanged
([`docs/en/spec/registry-index.md`](../../docs/en/spec/registry-index.md) §1–§2):

```jsonc
{ "$comment": "free text, never read as a fact",
  "signed": { "schema": "astra.commands.index/1", "serial": 1798675200, … },
  "signatures": [ { "key_id": "astra-commands-2026a", "sig": "<base64 of 64 bytes>" } ] }
```

- `digest = SHA-256(domain ‖ 0x00 ‖ JCS(signed))`, `sig = Ed25519(key, digest)`.
- **`domain` is the verifier's own constant** — `astra.<kind>.index/1` or
  `astra.<kind>.withdrawn/1` — and never the document's `schema` string. A
  commands signature therefore cannot be replayed as a models document, a plugin
  index, or a `withdrawn` document of its own kind
  (`testdata/content/index/commands/signed-under-models-domain.json`).
- Verification is `verify_strict` and uses **only the two keys of that kind**
  from `trust.json`'s `kind_keys` ([`trust-kind-keys-v1.md`](trust-kind-keys-v1.md)).
  `key_id` is a hint; the verifier tries each usable key and reports the one that
  verified.
- Every number in a content document is an **integer**; JCS of a float is never
  needed and a document carrying one is malformed.
- **A duplicate member name anywhere in a document refuses it, before any
  signature is checked.** A last-wins verifier and a first-wins reader of the
  same bytes see two different documents behind one valid signature:
  `index/commands/duplicate-member-name.json` verifies under a last-wins parse
  (`danger: critical`) while a first-wins reader of it sees `danger: low`. The
  same rule holds for a command artefact (`E_COMMAND_FORMAT`), `astrachar.json`
  (`E_BUNDLE_MANIFEST`) and a glTF JSON chunk (`E_CONTENT_FORMAT`)
  (OPEN.md O-21).

## 2. Freshness

| field | rule |
|---|---|
| `serial` | `= issued_at` (rule `serial-is-issued-at`); ≥ 1 |
| `issued_at` | Unix seconds. A client refuses a document whose `issued_at` is more than **1 day** ahead of its clock (`issued-in-future`) |
| `expires_at` | Unix seconds; `0 < expires_at − issued_at ≤ 8 days` (rule `expiry-span`); 7-day target |

- Re-signed daily and on every change. A client refreshes hourly.
- **Serial floor, per (kind, document).** A client keeps, for each of the ten
  documents, the highest `serial` it verified and the JCS bytes of that
  `signed`. It refuses (`serial-rollback`) a document whose `serial` is below
  the floor, and one whose `serial` equals the floor with different bytes. The
  floor is per document, **not** per key: switching from `current` to `next`
  does not reset it (trust-kind-keys-v1.md §6).
- An **expired** index (`expired`) stops new installs and updates of that kind;
  what is installed keeps working. The withdrawn document has its own, much
  shorter bound (§6.5).
- **Withdrawals never ride inside an index.** An index has no `withdrawn` key
  (the games rule, `spec/games/games-withdrawn-v1.md` §1, for the same reason: an
  index over its size cap is refused whole and a takedown inside it would be
  lost with it).

Paths: `<registry host>/registry/v1/<kind>/index.json` and
`…/<kind>/withdrawn.json`, byte-identical on `registry.minice.ai` and
`registry.knice.tech`, each ≤ 1 MiB (SERVE-50). Content documents are
**credential-free**: no catalogue ticket, no account token (§11a.7).

## 3. Base entry fields

Every entry of `commands`, `characters`, `models` and `animsets` carries:

| field | type | note |
|---|---|---|
| `id` | string | the item's slug: `spec/reserved-ids.yaml` `id_pattern`, and never `--` (rule `id-double-hyphen`). Unique within its kind for ever |
| `version` | semver | no build metadata. An index carries an item's newest listed version, plus any older version a listed pack pins or a listed character requires (§5) — so `(id, version)` is unique (rule `unique-id-version`), `id` alone is not |
| `author` | string ≤ 64 | the PUBLIC name the author chose (RU: the name the 152-FZ consent covers). Never an account id |
| `listing` | `{locale: {title ≤ 64, description ≤ 4000}}` | 1–16 locales; a client without the reader's locale falls back to `en`, then to the first key |
| `thumbnail` | `{sha256, size ≤ 1 MiB}` | PNG or WebP, content-addressed like the artefact |
| `artefact` | `{sha256, size, media_type}` | the bytes the client downloads (§4) |
| `review` | `unchecked` \| `reviewed` | a client treats any other word as `unchecked`; held items are never in an index (§11a.9) |
| `min_astra` | semver | a client older than this does not offer the item |
| `published_at` | Unix seconds | |
| `parts` | `[{part_kind, digest, size}]` | [`part-digest-v1.md`](part-digest-v1.md); which part kinds a kind allows is in its spec |
| `content_confirmed` | `{text_id: version}` | which rights-confirmation text version the parts were last confirmed under — **never an account**; the confirmations themselves are the plugins service's record (§2). Non-empty whenever `parts` is (rule `parts-confirmed`) |
| `licence` | §3.1 | |
| `credits` | §3.2 | |

`packs` carry a reduced set (packs-index-v1.md).

### 3.1 `licence`

All members are present; a member that does not apply is `null` or `unknown`,
never absent.

```jsonc
"licence": { "source": "vrm" | "declared",
             "spec": "vrm0" | "vrm1" | "none",
             "commercial_detail": "corporation" | "personalProfit" | "personalNonProfit" | "Allow" | "Disallow" | null,
             "redistribution": "allowed" | "prohibited" | "unknown",
             "avatar_permission": "everyone" | "author_only" | "named_people" | "unknown",
             "modification": "allowed" | "prohibited" | "unknown",
             "commercial": "allowed" | "prohibited" | "unknown",
             "credit_required": true | false,
             "spdx": "<SPDX id>" | null,
             "license_url": "<https URL>" | null,
             "usage": { "violent": …, "sexual": …, "political": …, "antisocial": … } }
```

- `source: vrm` is the SERVER-read VRM meta ([`ingest-v1.md`](ingest-v1.md) §4);
  `source: declared` is what the publisher declared for a part with no meta.
  `source` and `spec` agree: `vrm` ⇔ `spec ∈ {vrm0, vrm1}` (rule
  `licence-source-spec`).
- **Only an Allowed verdict is ever signed.** An entry with
  `redistribution = prohibited`, or `avatar_permission ∈ {author_only,
  named_people}`, is refused by the client however it got signed (rule
  `licence-allowed`, defence in depth behind ingest's `E_CONTENT_LICENCE_REFUSED`).
- `commercial` follows §11a.9: 0.x `Allow` → allowed, `Disallow` → prohibited;
  1.0 `corporation` and `personalProfit` → allowed (Astra's user is an
  individual), `personalNonProfit` → prohibited.
- **`commercial_detail` is DISPLAY ONLY and is never compared** with anything —
  a client that refuses an entry because `commercial_detail` disagrees with
  `commercial` is wrong (`testdata/content/index/commands/valid.json`, entry
  `greet`, carries exactly that disagreement and is valid).
- `usage` carries the VRM 1.0 usage flags. 0.x fills `violent` and `sexual`
  only, so for `spec: vrm0` `political` and `antisocial` are `unknown` (rule
  `vrm0-usage`). Anything the meta does not state is `unknown` — for the USAGE
  flags only; `redistribution` and `commercial` of a present meta use the spec
  default (§11a.9).

### 3.2 `credits`

`[{name ≤ 128, role ≤ 64, url: https | null}]`, ≤ 32 rows. They reproduce only
what the author chose to publish; VRM meta contact fields are NOT copied
(§11a.4).

## 4. Artefacts and downloads

- The client builds the download URL from the sha256 and its edition's
  **compiled** base — `https://content.minice.ai/o/sha256/<hex>` or
  `https://content.knice.tech/o/sha256/<hex>` — and **never** takes a URL from
  an entry (§1 decision 2). No entry field is a URL to fetch, by construction.
- Downloads are **anonymous**: no account token, no catalogue ticket (§11a.6).
- The client hashes what it downloaded and refuses a size or sha256 that is not
  the entry's (`artefact-digest-mismatch`). It does not trust the CDN for
  integrity.

## 5. Unknown values in an index (client)

- An entry of a shape this client does not understand, or whose `min_astra` it
  does not meet, is **skipped**; it never costs the document.
- An unknown `needs[]` word (characters) makes that one entry not installable
  (`need-unknown`).
- An unknown capability word is never a reason to install: the client shows the
  capabilities it derived itself ([`capabilities-v1.md`](capabilities-v1.md) §6)
  and refuses an entry whose claim differs from its derivation
  (`claim-mismatch`).

## 6. The withdrawn document

```jsonc
{ "schema": "astra.<kind>.withdrawn/1", "serial": …, "issued_at": …, "expires_at": …,
  "rows":  [ { "id", "versions", "act", "floor_effect", "reason_code",
               "part"?:  {"part_kind", "digest"},
               "cause"?: {"kind", "id", "version"},
               "reason_text", "at" } ],
  "lifts": [ { "id", "versions", "lifts_at" } ] }
```

`rows` and `lifts` are always present (`[]` when empty). `at` is when the act was
taken.

**`versions` (and a command's `version_req`) is comparators only, judged by
SemVer 2.0.0 §11 precedence — it is NOT Cargo's `VersionReq`.** A range is
**canonical**, in exactly one of three shapes, with no spaces: `=V`; a lower
bound `>=V` or `>V`, optionally followed by `,` and an upper bound `<=V` or
`<V`; or an upper bound alone. `V` is a full SemVer version. There is no caret,
tilde, wildcard, `||`, bare version or other order — a client reads any of them
as unparseable (below). Canonical spelling is what lets a `lift` be matched to
its row by plain string equality (§6.5). A pre-release is matched by precedence
alone — unlike Cargo, which excludes pre-releases from a requirement that does
not name one. So `<=1.0.0` covers `1.0.0-rc.1` (a withdrawal of a release
withdraws its release candidates), and `1.0.0-rc.2 < 1.0.0-rc.10 < 1.0.0`
(numeric identifiers compare numerically and below alphanumeric ones). Scenario
`semver-precedence` holds a pre-release case below, equal to and above every
comparator.

`reason_text` (≤ 500) is shown verbatim
and carries no secret and no person's name beyond what is already public.

### 6.1 Acts

| act | installed copy | new install | update |
|---|---|---|---|
| `security` | **disarmed** — the command disabled, the character/model/animset not loaded; removal offered | refused | refused |
| `rights` | hidden; delete offered, of the whole item or only the named `part` | refused | refused |
| `retired` | kept and marked | not offered | none |

The strongest act covering a version wins (`security` > `rights` > `retired`).

### 6.2 Pairing rules (publisher; the checker names each)

| rule | |
|---|---|
| `security-pairs` | `reason_code = security` ⇒ `act = security` |
| `floor-of-act` | `security` ⇒ `floor_effect = disarm`; `rights` ⇒ `disarm`; `retired` ⇒ `no-update` or `disarm` |
| `part-only-rights` | `part` only with `act = rights`; never on a `packs` row (a pack has no parts) |
| `cause-on-cascade` | `cause` present ⇔ `reason_code ∈ {requires-unavailable, member-withdrawn, member-retired}` |
| `lift-not-contradicted` | no lift in a document names a `security` row present in the same document |

`floor_effect` is **cumulative**: `no-offer` (refuse a new install) ⊂
`no-update` (also refuse an update to it) ⊂ `disarm` (also disarm an installed
copy). `rights` floors at `disarm` because an old client cannot hide one part
and "hidden" must not degrade to "keeps loading".

### 6.3 Unknown values in a withdrawn document (client)

**A client never refuses a whole withdrawn document for an `act`,
`reason_code` or `floor_effect` it does not know.** The schemas in
`schemas/*-withdrawn-v1.schema.json` are what the PUBLISHER must emit; a client
parses each row on its own and:

- reads a `versions` range it cannot parse as covering **every** version (a
  takedown must not fail open on syntax; scenario `unparseable-range-covers-all`).
  **Every comparator is parsed before any is evaluated**: `<=1.0.0,^2.0` is
  unparseable, so it covers `2.0.0`, exactly as `^2.0,<=1.0.0` does — never
  "false at the first comparator";
- applies the act when it knows it (§6.1);
- otherwise applies `floor_effect`;
- otherwise (an unknown `floor_effect` as well) applies `disarm`.

This is how a takedown reaches a client older than the act that expresses it
(the games rule, `games-withdrawn-v1.md` §4).

### 6.4 Cascades

On every accepted plugin index or revocations document and on every content
withdrawal, the publisher re-checks dependants against the SERVED documents and
writes a row for each dependant, `cause` naming the member (§4, §11a.10):

| what changed | a command requiring it | a pack containing it | a character requiring it |
|---|---|---|---|
| gets `security` | `retired`, `requires-unavailable` (if no other matching listed version remains) | **`security`**, `member-withdrawn` | **`security`**, `member-withdrawn` |
| gets `rights` | as above | `retired`, `member-withdrawn` | `retired`, `member-withdrawn` |
| gets `retired` | as above | `retired`, `member-retired` | `retired`, `member-retired` |
| is restored | the automatic `retired` is lifted | the automatic act is lifted; a moderator's own act stays | as packs |

A served set in which a listed dependant of a withdrawn member carries no such
row is a publisher defect, `cascade-missing`
(`testdata/content/vectors.json` scenarios `cascade-*`).

### 6.5 The client's withdrawn-freshness rule, sticky rows and `lift`

Both are in [`trust-kind-keys-v1.md`](trust-kind-keys-v1.md) §7, beside the key
rules, because they are what makes a leaked or withheld document harmless.

A `lift` is `{id, versions, lifts_at}`, plus **`cause{kind, id, version}`** when
it undoes a CASCADE row (§6.4) — the same `cause` that row carried. A `lift`
never shares `(id, versions, at)` with a row of the same document, whatever the
row's act (rule `lift-not-contradicted`); if one does anyway, the client lets
the ROW win.

## 7. Client refusal tokens

Lower-case, as `spec/content/reason-codes.yaml` `client:` lists them:
`kind-keys-unusable`, `signature-invalid`, `key-retired`, `serial-rollback`,
`issued-in-future`, `expired`, `withdrawn-stale`, `withdrawn-unverified`,
`artefact-digest-mismatch`, `claim-mismatch`, `requires-digest-mismatch`,
`requires-unavailable`, `member-digest-mismatch`, `member-unavailable`,
`need-unknown`, `command-unknown-trigger`. The publisher-side invariant of §6.4
is `cascade-missing`.
