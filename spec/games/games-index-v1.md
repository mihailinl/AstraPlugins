<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.games.index/1`

**Normative.** Source: `game-integrations-marketplace-plan.md` §5.3 (the base
shape) as amended by `dev/game-integrations-plan-merged.md` §2.2 (the deltas)
and §1 rows R9, R10, R13, R19, R23, R33, R43. Signed and served exactly like
every other trust-envelope document (`astra-core/src/trust_envelope.rs`), tag
`astra.games.index/1`. Withdrawals are **not** in this document — see
[`games-withdrawn-v1.md`](games-withdrawn-v1.md) — because an over-cap index
is refused whole and the previous verified copy kept
(`plugins/registry_client.rs::read_capped`, verified by the earlier plan),
and a takedown must still reach a client whose index just failed its size
check (R23).

## 1. Envelope and freshness

One JCS document, detached Ed25519 signatures, in the plugin envelope.

| field | meaning |
|---|---|
| `serial` | `= issued_at`, Unix seconds |
| `issued_at` | Unix seconds |
| `expires_at` | Unix seconds. `expires_at − issued_at ≤ 8 days`, 7-day target |
| `key_id` | the signing key's **role**, `"games-current"` or `"games-next"` — never a real key id (§3) |

- A client refuses a document whose `issued_at` is more than 1 day ahead of
  its own clock.
- Re-signed daily and on every change; a client refreshes hourly.
- **New installs and version updates need an unexpired copy.** Detection,
  display, Play and repair of an already-installed version run on the last
  verified copy regardless of its age (merged plan R24) — only *new* code
  needs a fresh signature.

## 2. Body

```jsonc
{
  "schema": "astra.games.index/1",
  "serial": 1798675200,
  "issued_at": 1798675200,
  "expires_at": 1799280000,
  "key_id": "games-current",
  "entries": [ /* Entry, §2.1 */ ],
  "games": [ /* GameRow, §2.2 */ ],
  "anticheat": [ /* AnticheatMarker, §2.3 */ ],
  "loaders": [ /* LoaderAllow, §2.4 */ ],
  "engine_codes": { "source2": { "account": "someone", "repo_id": 123456789 } }
}
```

`engine_codes` is new in the merged plan (§2.1): it is how a client and
`gi-probe` both answer "who owns this code" without scanning every entry —
ingest refuses a second publisher's claim to an owned code with
`engine-code-taken`, and a moderator act may reassign the row here.

### 2.1 Entry

```jsonc
{
  "id": "someone/peak-astra",
  "kind": "integration",                    // "foundation" | "integration"
  "publisher": { "account": "someone", "repo_id": 987654321, "repo_owner_id": 111 },
  "source": {
    "host": "github.com", "repo": "someone/peak-astra",
    "repo_id": 987654321, "repo_owner_id": 111,
    "release_tag": "v1.2.0", "asset": "astra-gi.zip",
    "sha256": "…", "size": 2048576,
    "commit": "…", "workflow_path": ".github/workflows/gi-release.yml",
    "event": "push"
  },
  "version": "1.2.0", "schema": 1, "min_astra": "0.2.8",
  "target": { "store": "steam", "id": 3527290, "exe": "PEAK.exe" },
  "descriptor": null, "descriptor_sha256": null,
  "sdk": null,
  "foundation": { "id": "astra.unity", "version": "0.8.1", "engine": "unity-mono" },
  "built_on": { "entry": "mihailinl/astra-unity", "version": "0.8.1", "verified": true },
  "engine_versions": null,
  "link": { "context": true, "shares_other_players": false, "skill_digest": "…", "digest": "…" },
  "schema_digests": { "tools/drop_item.json": "…" },
  "capabilities": ["companion.presentation"],
  "shares_other_players": false,
  "changes": {
    "profile_files": true,
    "game_files": [ { "path": "winhttp.dll", "sha256": "…", "loader": "allowlisted" } ],
    "launch": true, "config_writes": true
  },
  "code_changed": false,
  "licence": "MIT",
  "review": "unchecked",
  "supersedes": [],
  "flags": [],
  "notes": { "en": "First release.", "ru": "Первый релиз." },
  "content": [
    { "path": "animations/climb.fbx", "kind": "animations", "title": "Climb cycle",
      "credit": "someone", "licence": "CC-BY-4.0", "licence_source": "declared", "sha256": "…" }
  ],
  "content_confirmed": { "market.rights.animations": 1 }
}
```

| field | note |
|---|---|
| `publisher` | the **bound** identity (`{account, repo_id, repo_owner_id}`), set at the first ingest and unchanged by later releases; compared against `source` on every update to detect `changed_hands` (R20, A§4.1) |
| `source` | **this release's** provenance, re-verified every ingest; identical shape to `publisher`'s two ids so the comparison is a plain equality check |
| `target` | present for a game-specific entry (`store`, `id`, `exe`) or a foundation/runner (`exe = "*"`, no `store`/`id`); a **non-owning** foundation sharing an already-claimed engine code sets `target.engine = "<code>"` here, mirroring its manifest's `[target].engine` (manifest.md §2.1, "Many foundations, one owner") |
| `descriptor` / `descriptor_sha256` | present **only** on the entry that owns an engine code: the inline `astra.engine/1` JCS object and its digest (engine-descriptor-v1.md §1) |
| `foundation` | the mirrored `[integration.foundation]` claim (manifest.md §2.4); `offers.rs` also reads `foundation.engine` to match an exe-less game-specific GI to its engine, generalising the pre-Workshop `pins.rs:571-578` check |
| `built_on` | computed by ingest from digests, never trusted from the manifest's claim alone; `verified` is true only on a full file-set match |
| `engine_versions` | a **foundation's own** declared support range (e.g. `"<6000.3"`), replacing the earlier plan's `versions` on the descriptor itself (R8) — detection and support are different owners |
| `capabilities` | replaces the earlier `uses_avatar` boolean; `v1`'s only value is `"companion.presentation"` |
| `review` | `"unchecked"` \| `"source_reviewed"`. The client derives the UI tier and Provenance badge from this plus first-party-list membership; this document states only the fact, never the wording (R19) |
| `notes` | per-locale release notes, replacing free-text "what's new"; a locale a client does not have falls back to `en` |
| `content` | this release's `[[integration.content]]` parts (manifest.md §2.7), each carrying the sha256 ingest hashed, `licence_source` (`"vrm"` when a readable VRM licence decided it, `"declared"` when the manifest's own `licence` string is the whole licence — manifest.md §2.7.3) and, for a `.vrm` part (or a readable `.astrachar`'s body) with readable meta, the `vrm_licence` the HARD VRM gate read, including the VRM usage flags (legal `DRAFT-v3.md` Part 6 G5). Absent or `[]` for a GI with no non-built-in assets. At most 1024 (contract 6.13.0 §4.6; the manifest's own `maxItems` bounds it first, manifest.md §2.7) |
| `content_confirmed` | `{text_id: version}` — which confirmation text version each declared part was last confirmed under (manifest.md §2.7.4). A `text_id` is dot-separated lowercase segments, each `[a-z][a-z0-9_-]*` (`market.rights.animations`); the version is an integer ≥ 1. **Never an account**: who confirmed, and when, is the plugins service's own record, not this document's |
| `link` | `null` when the manifest has no `[integration.link]`; else `context`, `shares_other_players`, `skill_digest` (SHA-256 of the skill file, or `null`) and `digest`, the link table's consent digest exactly as manifest.md §2.6.1 defines it (JCS of the table as parsed, no defaults added). The bytes of each named schema are in `schema_digests` |

**Dropped from the earlier plan's shape:** the flat `engine?`/`engine_ref?`
convenience fields (superseded by `target.engine` and `foundation.engine`
above) and `publisher_confirmed_at` (R20 — "publisher confirms a release"
is removed as an auto-update path entirely).

### 2.2 `games[]` — moderator rows

```jsonc
{ "store": "steam", "id": 3527290, "engine": "unity-mono",
  "prefer": ["mihailinl/astra-unity"], "deny": [], "refuse": null,
  "allow_foundations": false, "note": "" }
```

`deny`, `refuse{reason}` and `prefer` apply to **any** game. `engine` applies
**only** where Pass A gave `unknown` with no evidence, or Pass B gave
`engine-ambiguous` — never to override a game Pass A already placed
confidently (merged §2.1; this is the same narrow-only rule
`engine-descriptor-v1.md` §0 states for descriptors themselves, applied to
moderator data instead of code). `allow_foundations` lifts only the
online-game rule (§2.2 below); it can never lift an anti-cheat or VAC
refusal (§2.3).

### 2.3 `anticheat[]` — additive markers only

```jsonc
{ "name": "Easy Anti-Cheat (extended)", "kind": "folder-marker", "value": "EasyAntiCheat" }
```

Composes with, and never removes, the base-walk markers compiled into the
launcher and the other automatic signals (§2.5 below). A row here can only
make detection **stricter**.

### 2.4 `loaders[]` — the off-by-default allowlist

```jsonc
{ "name": "doorstop-winhttp", "sha256": "…", "default_enabled": false }
```

A digest allowlist of known loader builds that ship off by default and are
turned on only by Astra's own launch arguments (the `astra-peak` Doorstop
pattern: `winhttp.dll` with `doorstop_config.ini enabled=false` plus
`--doorstop-enabled true`). This labels; it never grants — a manifest's own
`[integration.loader]` table (manifest.md §2.2) is what the launcher
actually plans from.

### 2.5 Anti-cheat signals (the full list, for the client and the UI)

No foundation is offered when **any** of these fires:

1. Pass A's base-walk markers (compiled into the launcher);
2. the extended folder signatures (EA Javelin, ACE, GameGuard, XIGNCODE,
   Equ8, Denuvo Anti-Cheat);
3. this document's `anticheat[]`;
4. a system-installed kernel anti-cheat service;
5. Steam's own disclosure in `appinfo.vdf`;
6. VAC;
7. for a Pass B claim specifically, `anti-cheat-unknown` when the walk hit
   its cap or the folder ships a `*.sys` file.

This check runs **before** the no-integration decision (today `Unknown`
stops at `not-supported` first — merged §2.4 fixes the order). There is no
per-appid "no anti-cheat" override record; the only lever is adding a row to
`anticheat[]` above (merged §2.4, "No per-game record" — dropping the
earlier plan's per-appid moderator exemption, which was itself a moderator
gate on every unchecked foundation and so worked against auto-publish).

Online PvP, PvP and MMO games get no engine-wide foundation offer unless
`games[].allow_foundations` is set (§2.2); a game-specific entry for such a
game is still allowed, just never "Recommended".

## 3. Keys

**Not a compiled client key any more.** Games documents are authorised only
by the two entries of kind `"games"` in the root-signed `trust.json`'s
`kind_keys` member (minice `docs/architecture/2026-11-01-content-catalogue.md`
§5; the astra-games-catalogue's `lib/trust.mjs`, agreed with minice-01 on
2026-11-01). Each entry:

```jsonc
{ "kind": "games", "role": "current" | "next", "key_id": "astra-games-2026a",
  "alg": "ed25519", "public_key": "<base64, 32 bytes>", "not_before": "<RFC 3339>" }
```

**Validity window, stated explicitly.** A `kind_keys` entry for `"games"`
counts toward verifying a document when `window_now ≥ not_before`, with
`window_now = max(local, server Date)` — the verifier's clock, never the
document's own `issued_at` (`spec/content/trust-kind-keys-v1.md` §3;
`docs/en/spec/registry-index.md` §4.3). A document issued before `next`'s
`not_before` still verifies under `next` once the verifier's clock reaches
it — the same bytes, checked later (the content goldens'
`next-before-not-before` refuses that check now, `next-before-not-before-later`
accepts it once `not_before` has passed) — so games does not add an
`issued_at` bound of its own; one rule for the key window across every
Workshop kind beats a stricter games-only reading that would drift from it.
Independent of the key, the document itself is valid only while
`now < expires_at`,
**exclusive**: at `now = expires_at` it has already expired (§1), never at
the instant after.

`trust.json` carries **exactly two** entries for kind `"games"` — one
`role: "current"`, one `role: "next"` — both already authorised the moment
the root signature that covers `trust.json` itself verifies. Adding a games
key, or replacing one outright, is a root ceremony (the owner's passphrase,
CLAUDE.md §3); *using* the `next` one routinely is not. A kind key never
appears in `trust.json`'s `index_keys` (the plugin registry's own key list)
and a kind key for `"games"` is never shared with any other kind.

**A `trust.json` that breaks either separation, or carries a malformed
`"games"` row, costs only the `"games"` kind its keys — fail closed per
kind, never the whole document** (`spec/content/trust-kind-keys-v1.md` §4:
not exactly one `current` and one `next` row, a bad `role`/`alg`/
`public_key`, an unparseable `not_before`, `next.not_before` not strictly
later than `current.not_before`, `current` equal to `next`, or a `"games"`
public key shared with `index_keys` or another kind — a shared key costs
every kind it appears under). With no keys, `"games"` cannot verify
`astra.games.index/1` or `astra.games.withdrawn/1`: installs and updates of
games content stop and the client keeps the last verified copy of each
(`kind-keys-unusable`), while `index_keys` and every other content kind
keep verifying off the same `trust.json`. One bad `"games"` row must not
take every Workshop kind offline.

**No per-key lifetime.** A `kind_keys` entry is authorised from its
`not_before` onward and stays authorised until a root ceremony says
otherwise — there is no `not_after` on the key itself. What is short-lived is
each *signed document*: `expires_at − issued_at ≤ 8 days` (§1) plus a
**serial floor per document schema** — this index has its own, the withdrawn
list has its own (`games-withdrawn-v1.md`) — that a routine role swap never
resets.

**Routine rotation is the signer moving from `current` to `next`** — no
client release, no ceremony, the same ratchet as before but now a
day-to-day operation rather than something a new client build has to compile.

**The switch is one-way, and it retires `current` per DOCUMENT SCHEMA, not
per kind** (minice `docs/architecture/2026-11-01-content-catalogue.md`
§11a.9, decided 2026-11-02; the same rule as
`spec/content/trust-kind-keys-v1.md` §6):

- **The signer** never signs a document of a schema with `current` alone
  once it has served a `next`-signed document *of that schema*. It may still
  sign `astra.games.withdrawn/1` with `current` after `astra.games.index/1`
  has moved to `next`, and the reverse.
- **The client:** the first `astra.games.index/1` it verifies that **moves
  the rotation** retires `"current"` **for `astra.games.index/1` only**, on
  that client, **permanently**. A document moves the rotation when its body
  `key_id` is `"games-next"` **or** the `next` key is among the keys that
  verified it, whatever its body names (the union below). From then on it
  refuses a later index that only `current` signed, so a forged `serial`
  replayed under a since-retired role cannot hold back the one that took
  over. That index retires nothing for `astra.games.withdrawn/1`: a
  withdrawn list signed by `current` still verifies until a withdrawn list
  that moves the rotation has itself been verified
  (`games-withdrawn-v1.md`).
- **What the client stores:** one high-water "seen `next`" mark **per
  schema** — one for `astra.games.index/1`, one for
  `astra.games.withdrawn/1`, never one for the kind `"games"`. The mark is the
  `kind_keys.key_id` that held the `current` role when that schema's first
  document that moves the rotation arrived, i.e. the key id retired for that
  schema.
  It only moves forward: no later document clears it. Because it records a
  key id rather than a role, the ceremony that promotes `next` to `current`
  (same key id) and adds a fresh `next` un-retires nothing and retires
  nothing new.
- **Why per schema:** the index and the withdrawn list are signed and served
  on separate schedules — separate fetches, separate size caps, separate
  serial floors (`games-withdrawn-v1.md` §1). Under per-kind retirement, a
  still-valid `current`-signed withdrawn list fetched in the middle of a
  rotation would be refused because the index had reached `next` first, and
  withdrawals are the safety path that must never go dark. The cost is
  small: each schema retires `current` on its own first `next` document, and
  each schema's serial floor still stops the replay of an older one.

A later rotation needs a root ceremony to install a fresh `"next"` only once
both roles have been spent for a schema, or on a suspected compromise — not
on every rotation, the way a compiled key id used to force a client release.

**The document body names the key's ROLE, never its real id.** The signed
body's `key_id` (§1, §2) is always the literal string `"games-current"` or
`"games-next"` — a reference to a `kind_keys` **role** for kind `"games"`,
exactly as `games-index-v1.schema.json`'s enum already states it, never a
`kind_keys.key_id` value. The **signature envelope**'s own `key_id` (the
plugin envelope's `signatures[].key_id`, a hint for logging and key
selection — astra-registry `bot/lib/sign.mjs` — never trusted for which key
actually signed) carries the real `kind_keys.key_id` that did the signing
(e.g. `"astra-games-2026a"`). A client verifies a games document only against
the two `kind_keys` public keys of kind `"games"` — never an `index_keys` key
and never another kind's `kind_keys` key, whatever either `key_id` claims —
and never uses the body's role string to pick which public key to try.

**The ratchet moves on the UNION** (minice RG delta re-check, 2026-11-05):
a document retires `current` for its schema when **its body names
`"games-next"`, or the `next` public key is among the keys that verified
it**. Either one is enough. A document signed by BOTH keys whose body says
`"games-current"` therefore retires `current`, just as
`spec/content/trust-kind-keys-v1.md` §6 ("verifies under K's next key")
requires. Under the body role alone it would retire nothing, and a §6
client and a games client would disagree on the same bytes. The union is
the refusing reading: it satisfies this section and §6 at once, and a
later `current`-only document is refused under either. A verifier takes
the next state from the verification itself (the role set it collected),
never from re-reading the body.

**The claimed role must be among the keys that verified.** The verifier
tries both of kind `"games"`'s public keys against every offered signature
and collects every role that verified — never stopping at the first
(`spec/content/trust-kind-keys-v1.md` §6). The body's `key_id` must name
one of the roles in that collected set: a document whose `key_id` is
`"games-current"` but that only the `"games-next"` key verifies — or the
reverse — is refused, never accepted on the strength of a role that turned
out not to have signed it. This is what keeps the ratchet above keyed to
what actually verified, rather than to a string the signer wrote. Read
this way, `games-index-v1.md` §3 and `spec/content/trust-kind-keys-v1.md`
§6 could be heard as two different rules — the content contract's "verifies
under K's next key" naming the key that checked out, this spec's own body
`key_id` naming only a claim. This paragraph settles that reading for
games in favour of the stricter one: a claim the signature itself does not
back is refused, not merely logged.

## 3a. References to a catalogue item (packs, `requires`)

A pack member, or a command's or pack's dependency, names a registry or catalogue item by **kind, id and version**. One rule for every kind, agreed 2026-11-01 by the client (astra-4c, astra-ce) and the registry (astra-plugins-ops):

| kind | `id` | version | the bytes the client installs |
|---|---|---|---|
| `games` | the **index entry id**, `entries[].id` (e.g. `someone/peak-astra`) — never the manifest's `[integration].id`, which stays internal to the package | `entries[].version` (semver) | the entry's zip `sha256`, from this signed document |
| `plugin` | the registry plugin id, `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$` | `releases[].version` (semver) of the signed `registry/v1/index.json` | the per-platform `releases[].artifacts.<platform>.sha256`, from that signed index |

- A **member** pins an exact version: `{kind, id, version}`. A **dependency** carries a range: `{kind, id, version_req}` (semver requirement).
- **The digest is never copied into the pack as the source of truth.** The client takes it from the signed document at install. A pack may carry a `digest` as a belt; a mismatch with the signed document refuses the install.
- **Why the entry id:** it is the key `games-withdrawn-v1` and the client's ledger use, and one repository can publish more than one entry (a runner's Mono and IL2CPP builds), so neither the repository nor the manifest id tells them apart.
- **Availability:** a published version's bytes never change. A version that is withdrawn (`games-withdrawn-v1`), revoked (`registry/v1/revocations.json`) or delisted refuses NEW installs through a reference; a revoked one is also disabled where installed; a yanked or deprecated one is not offered for new installs and stays where installed.

## 4. Client behaviour on an unknown value

- An entry of unknown `kind` is skipped — it affects only that entry.
- A descriptor with an unknown atom never matches (engine-descriptor-v1.md
  §0, rule 5) — it affects only that entry's offer, never the document.
- An unknown `games[]`/`anticheat[]`/`loaders[]` row shape is skipped with
  the same scoping.

## 5. Schema

[`schemas/games-index-v1.schema.json`](schemas/games-index-v1.schema.json).
Signature verification, the freshness checks (§1) and the `engine_codes`
ownership rule are run-time facts a JSON Schema cannot express; they are
covered by `tools/check-games-goldens.py` and, on the client side, by D's own
fixtures (merged plan §3.2, lane D "Tests").
