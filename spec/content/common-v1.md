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
| `version` | semver | no build metadata. An index carries an item's newest listed version, plus any older version a listed pack pins or a listed character requires (§3.5) — so `(id, version)` is unique (rule `unique-id-version`), `id` alone is not |
| `author` | string ≤ 64 | the PUBLIC name the author chose (RU: the name the 152-FZ consent covers). Never an account id |
| `listing` | `{locale: {title ≤ 64, description ≤ 4000}}` | 1–16 locales; a client without the reader's locale falls back to `en`, then to the first key |
| `thumbnail` | `{sha256, size ≤ 1 MiB}`, **optional** | PNG or WebP, content-addressed like the artefact. Absent — never `null` — when the item has no picture with a byte source (§3.3) |
| `artefact` | `{sha256, size, media_type}` | the bytes the client downloads (§4) |
| `review` | `unchecked` \| `reviewed` | a client treats any other word as `unchecked`; held items are never in an index (§11a.9) |
| `min_astra` | semver | a client older than this does not offer the item. Derived from the artefact's format, never authored (§3.4) |
| `published_at` | Unix seconds | |
| `parts` | `[{part_kind, digest, size}]` | [`part-digest-v1.md`](part-digest-v1.md); which part kinds a kind allows is in its spec |
| `content_confirmed` | `{text_id: version}` | `text_id` follows the games pattern `^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)*$` (≤ 128), so the SHARED ids such as `market.rights.animations` fit (golden `content-confirmed-dotted-id`; `market..rights` is refused); `version` ≥ 1. Which rights-confirmation text version the parts were last confirmed under — **never an account**; the confirmations themselves are the plugins service's record (§2). Non-empty whenever `parts` is (rule `parts-confirmed`) |
| `licence` | §3.1 | the ITEM's own licence; whose facts those are, per kind, is §3.1.2 |
| `credits` | §3.2 | `[]` is valid, and is what most entries carry |

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
  `source: declared` is what the publisher declared — for a part with no meta,
  or for the item itself (§3.1.2).
  `source` and `spec` agree: `vrm` ⇔ `spec ∈ {vrm0, vrm1}` (rule
  `licence-source-spec`).
- **A `source: vrm` object has `spdx: null`** (rule `licence-vrm-spdx`): a VRM
  meta names no SPDX id, and the server does not guess one from a licence URL
  or a 0.x `licenseName`. Its `license_url` is the meta's own licence URL —
  VRM 1.0 `licenseUrl`, VRM 0.x `otherLicenseUrl`, read from the meta `spec`
  names — when that value is an `https://` URL the schema accepts, and `null`
  otherwise (absent, empty, `http://`, any other scheme). The URL is shown,
  never fetched.
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

#### 3.1.1 The declared licence (G5/W1)

For a part with no VRM meta at all ([`ingest-v1.md`](ingest-v1.md) §4.3), the
publisher declares ONE string instead, `BeginRequest.parts[].licence` /
`DeclaredPart.licence`. **Absent, or `null`, means no declaration** — the
part is `E_CONTENT_LICENCE_UNDECLARED` unless a readable VRM meta covers it.
A PRESENT value is exactly one of:

- the closed SPDX id list: `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`,
  `CC-BY-NC-4.0`, `CC-BY-NC-SA-4.0`, `CC-BY-ND-4.0`, `CC-BY-NC-ND-4.0`,
  `MIT`, `Apache-2.0` — exact spelling, case included (`cc-by-4.0` is not
  `CC-BY-4.0`);
- `custom:<URL>`, where `<URL>`:
  - is **printable ASCII only, U+0021–U+007E** (so no control character, no
    DEL, no space or other whitespace, and no character outside ASCII —
    U+202E, U+200B and a raw non-ASCII IDN host are all refused this way,
    never specially);
  - begins `https://`, case-sensitive;
  - has an AUTHORITY — the bytes from just after `https://` up to the
    first `/`, `?` or `#` (whichever comes first), or to the end of the
    string if none does — that is NON-EMPTY and contains no `@` (so
    `https://user@host/x` is refused, while `https://host/?q=a@b` is fine:
    the `@` is in the query, past the authority's own end);
  - carries no `#` anywhere (no fragment, even past a valid authority and
    path).
- An EMPTY string, or one that is whitespace only, is a declaration that
  IS present and IS malformed — not the same as absent — and is refused the
  same way.

The whole string, `custom:` prefix included, is **at most 512 BYTES**
(UTF-8), not 512 characters — moot for a conforming string, since every
character the rule admits is already one byte, but the limit is a byte
limit on principle, the way every other size cap in this contract is.

Anything that fails any rule above — an unrecognised id, a non-`https://`
scheme, an empty or `@`-bearing authority, a fragment, a control character
or non-ASCII byte anywhere in the string, over 512 bytes, or `custom:` with
no URL at all — is `E_CONTENT_LICENCE_DECLARATION_INVALID` at `begin`
([`ingest-v1.md`](ingest-v1.md) §1), before any byte of the bundle is
uploaded. One malformed entry refuses every declared part in that `begin`,
not only its own. **Two declared parts with the SAME part digest must carry
the SAME declaration** — a `begin` naming one digest twice with two
different declared licences is refused the same way; the same digest with
the same declaration twice is fine.

**The server maps the string to this `licence` object, from this table.**
Every row shares the same fixed fields: `source: "declared"`, `spec: "none"`,
`commercial_detail: null`, `avatar_permission: "unknown"`, every `usage`
flag `"unknown"`. `spdx` is the id as declared, or `null` for a `custom:`
licence; `license_url` is the licence's own canonical URL (the CC deed for
each Creative Commons id, `https://spdx.org/licenses/MIT.html` for `MIT`,
`https://www.apache.org/licenses/LICENSE-2.0` for `Apache-2.0`) or the
declared `custom:` URL.

| id | `redistribution` | `modification` | `commercial` | `credit_required` |
|---|---|---|---|---|
| `CC0-1.0` | allowed | allowed | allowed | `false` |
| `CC-BY-4.0`, `CC-BY-SA-4.0` | allowed | allowed | allowed | `true` |
| `CC-BY-NC-4.0`, `CC-BY-NC-SA-4.0` | allowed | allowed | **prohibited** | `true` |
| `CC-BY-ND-4.0` | allowed | **prohibited** | allowed | `true` |
| `CC-BY-NC-ND-4.0` | allowed | **prohibited** | **prohibited** | `true` |
| `MIT`, `Apache-2.0` | allowed | allowed | allowed | `true` |
| `custom:<URL>` | unknown | unknown | unknown | `true` |

`redistribution` is always `allowed` for every row this table can produce —
the whole closed list is a redistribution-permissive one, and `custom:`
reads `unknown` rather than assume a permission nobody declared. Rule
`licence-allowed` (§3.1) therefore never refuses a declared licence on
`redistribution` alone; it is `avatar_permission` and the ingest's own
mandatory hold (`F_CONTENT_LICENCE_DECLARED`, ingest-v1.md §4.3) that keep a
human in the loop.

#### 3.1.2 Whose licence the entry carries

**The entry's `licence` is the item's own**: the terms under which the author
gives THIS item to the people who install it. Where that comes from depends
on the kind, and each kind has exactly one source:

| kind | the entry's `licence` is |
|---|---|
| `model` | its one part's facts: the server-read VRM verdict of the body (`source: vrm`) |
| `animset` | its one part's facts: the declared licence of the pack (`source: declared`, §3.1.1) |
| `command` | **the item declaration**, `BeginRequest.licence` (`source: declared`) |
| `character` | **the item declaration**, `BeginRequest.licence` (`source: declared`) — with no parts, and with several |

**The item declaration.** `BeginRequest.licence` is ONE string of §3.1.1's
grammar — a closed SPDX id or `custom:<URL>` — mapped to the `licence` object
by §3.1.1's table, unchanged.

- It is **required for a `command` and a `character`**: absent or `null` is
  `E_CONTENT_LICENCE_UNDECLARED` at `begin`. Their entry has no other source —
  a command is one JSON artefact with no media, and a character is settings
  plus whatever parts it carries, none of which speaks for the whole.
- A present value that fails §3.1.1's grammar is
  `E_CONTENT_LICENCE_DECLARATION_INVALID` at `begin`, for every kind.
- For a `model` and an `animset` it is not needed; a present one is validated
  and then ignored, exactly as a part declaration that a VRM meta overrides
  ([`ingest-v1.md`](ingest-v1.md) §4.3). For a `pack` it has no meaning (a
  pack has no `licence`, packs-index-v1.md).
- The item declaration says nothing about any PART. A part's rights source
  stays what ingest-v1.md §4.3 says it is — the meta on a character's own
  body or accessory, the part's own `parts[].licence` everywhere else — and
  a part with neither is still `E_CONTENT_LICENCE_UNDECLARED`.

**A character with parts.** Each part keeps its own licence facts, as the
service's record of that part (they key its rights confirmation and its
moderation); the index entry's `parts` rows stay `{part_kind, digest, size}`
and carry no licence. The entry's `licence` is the character's item
declaration, whatever its parts say. **The publisher lists a character only
when every one of its parts would pass rule `licence-allowed` on its own
facts** — an Allowed VRM verdict, or a declared licence — so no entry's
single `licence` object ever stands in front of a part that could not have
been listed alone.

`testdata/content/index/characters/thumb-and-credit.json` is a character
declared `CC0-1.0` whose one `art` part is declared `CC-BY-4.0`: the entry
says `CC0-1.0`.

### 3.2 `credits`

`[{name ≤ 128, role ≤ 64, url: https | null}]`, ≤ 32 rows. They reproduce only
what the author chose to publish; VRM meta contact fields are NOT copied
(§11a.4).

**`[]` is valid, and it is what the publisher emits whenever the artefact
declares no credits in a shape this section names.** In v1 there is one such
shape:

| kind | the publisher emits |
|---|---|
| `character` | when `astrachar.json` carries a `credits` object (astra-companion `docs/character-files.md` §2: `{author, license, url, notes}`) whose `author` is a string of 1–128 characters: **exactly one row**, `{"name": <author>, "role": "author", "url": <url>}`, where `url` is the object's `url` when it is an `https://` URL the schema accepts and `null` otherwise. In every other case — no `credits`, `credits` not an object, no `author`, an empty or over-long one — `[]` |
| `command`, `model`, `animset` | `[]` |

Nothing else is copied: not the manifest's `license` or `notes` (the entry's
licence is §3.1.2's, and free text is not a credit), not a second row, and
never a VRM meta's `author`, `authors`, `contactInformation`, `reference` or
`references`. A name is published as written or not at all — it is never
trimmed to fit. A client accepts any schema-valid `credits`, so a later
version of this contract can give the other kinds a source without changing
the schema (`index/<kind>/valid.json` carries a free-form row on every kind
for that reason).

### 3.3 `thumbnail`

**A thumbnail is listed only when the item has a picture with a byte source,
and is otherwise ABSENT** — the member is left out; it is never `null`
(`index/commands/thumbnail-null.json` is refused by the schema), an empty
object or a placeholder's digest.

| kind | the thumbnail is |
|---|---|
| `pack` | its upload: **required** (packs-index-v1.md; `index/packs/no-thumbnail.json` is refused) |
| `character` | the bundle's ROOT `thumb.png` — the file astra-companion's `docs/character-files.md` marks `role: "thumbnail"` — when it is present, begins with the PNG signature and is 1 byte to 1 MiB. The PATH decides, not the `role` word: no other file becomes a thumbnail by carrying it. Otherwise absent |
| `command`, `model`, `animset` | **absent in v1.** A command is one JSON artefact; a model and an animset have exactly one part, so a loose picture in their bundle is refused; and the image embedded in a bare `.vrm` has no reader here yet. A later version of this contract names a source; the schema already allows the member, so a client written to v1 accepts it when it comes |

- **Every thumbnail a publisher lists MUST have passed the admission hook
  ([`ingest-v1.md`](ingest-v1.md) §1) as the same bytes**: the `sha256` and
  `size` in the entry are those of exactly the bytes the hook read — not of
  a second read of the file, a re-encoding, or a picture rendered later. A
  picture that has not passed, or whose check could not be completed, is not
  listed, and the entry goes out without the member.
- A character's `thumb.png` is still a file of her bundle like any other: a
  standalone image, so an `art` part with its own declared licence and rights
  confirmation ([`ingest-v1.md`](ingest-v1.md) §5). Being the thumbnail
  excuses it from nothing.
- Nothing is resized, converted or taken from inside a VRM. A `thumb.png`
  that is not a PNG, is empty or is over 1 MiB is not a refusal of the
  bundle; the entry simply has no thumbnail.
- **A client draws its own placeholder** for an entry with no thumbnail, and
  never treats the absence as a defect of the entry.

### 3.4 `min_astra`

**`min_astra` is not authored.** No manifest, artefact or upload request
carries it. The publisher derives it from the artefact's FORMAT: each kind
spec has a table "format, format version → the lowest Astra release that
reads it" (`<kind>-index-v1.md`, its `min_astra` section), and the entry's
`min_astra` is that table's value for the artefact it lists. A format version
with no row is not listed at all. Adding a format version adds a row; a row,
once served, never changes.

A client still enforces the member exactly as §5 says: derived or not, an
entry whose `min_astra` it does not meet is skipped.
`tools/check-content-goldens.py` reads each page's table and holds it against
the one it derives from (`MIN_ASTRA`).

### 3.5 Pins: no entry names an unlisted version

A pack's `members[]` and a character's `requires[]` each pin an exact
`(kind, id, version)`. **The publisher never serves an entry that pins a
version its kind's index, of the same publication, does not list.** When it
decides not to list a version — for any reason — it drops every listed pack
and character that pins that version from their indexes too, and repeats
until nothing listed pins anything unlisted. A dropped dependant is not
withdrawn: it gets no row (§6.4 is for a member that was WITHDRAWN), an
installed copy is untouched, and it is listed again when its pins are.

A served set that breaks this is a publisher defect, **`pin-unlisted`**
(scenarios `pins-*`). A `game-integration` member is outside the rule until
`astra.games.index/1` is served ([`ingest-v1.md`](ingest-v1.md) §7), and a
command's `requires` is a range over the plugin index, not a pin.

Clients keep `member-unavailable` and `requires-unavailable` as the defensive
reading: an index fetched a moment before its neighbour can still show a pin
the other does not have yet.

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

Publisher's row policy (v1). The publisher writes a row only for a security decision that has not been reversed and for a confirmed removal under the content rules; `reason_text` is a fixed neutral sentence per `reason_code`. A rights decision writes no row: the listing leaves the index and an installed copy is untouched. An item that merely left the index stays installed. Every reversal of a listed decision is published as a `lift` equal to its row on `id`, `versions` and `at`, so the copy is re-enabled. The `rights` and `retired` acts stay defined for clients; this publisher emits neither.

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
`need-unknown`, `command-unknown-trigger`. The publisher-side invariants are
`cascade-missing` (§6.4) and `pin-unlisted` (§3.5).
