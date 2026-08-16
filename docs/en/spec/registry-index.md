# The signed registry documents — normative specification

**Status:** normative for the document formats and the verification rules.
**Not yet in force:** the signature chain described here is specified,
implemented on both ends, and **not anchored** — see §0.1 before you rely on any
sentence in this file as a security guarantee.

Four documents, three schemas, one signature construction:

| document | schema string | signed by | this repo's copy |
|---|---|---|---|
| `root.json` | `astra.registry.root/1` | **nothing** — it is a transcript of keys compiled into Astra | `astra-registry/registry/v1/root.json` |
| `trust.json` | `astra.registry.trust/1` | a **root** key | published beside the catalogue |
| `index.json` | `astra.registry.index/1` | an **index** key that `trust.json` delegates to | `astra-registry/registry/v1/index.json` |
| `revocations.json` | `astra.registry.revocations/1` | the same index key | `astra-registry/registry/v1/revocations.json` |

Requirement words are RFC 2119.

---

## 0. What this chain answers, and what it does not

It answers: *is this catalogue the one the Astra registry published, is it
current, and has anything in it been withdrawn?* It is the only thing that makes
a cached record safe to install from, because the record pins an artifact digest
and a digest does not expire.

It does **not** answer *who built the plugin*. That is the GitHub build
attestation, checked by the registry bot at ingest (§7), never by the daemon.
What the daemon holds is a registry *assertion* about the author, pinned on
first install (TOFU) and bound to the download URL — see §7.3. UI copy is
required to say "same author as before" and never "verified build".

### 0.1 The chain is not anchored yet — read this first

* `astra-registry/registry/v1/root.json` carries `"status": "provisioned"` and
  two Ed25519 keys. The ceremony in `astra-registry/SECURITY.md` §4
  (`tools/keygen-root.sh`) was run offline on 2026-08-11.
* `astra-daemon`'s `PRODUCTION_ROOT_KEYS` lists the same two. The registry copy
  is public so a third party can read them without disassembling a binary, and
  so a disagreement between the two is visible; the private halves were never on
  a networked machine.
* **A root key does not sign a catalogue.** It signs `trust.json`, which
  delegates to an index-signing key. **That document is now signed.**
  `registry/v1/trust.json` verifies under `astra-root-2026a`, delegates to the
  index-signing key `astra-index-2026a`, and names the single reusable-workflow
  commit the bot will accept in a build attestation
  (`e3329df252a46d747676cb540ae4b986af68a3ad`, which is what the tag
  `plugin-release/v1` points at). The registry's own
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` prints all three
  facts. So `E_TRUST_UNPROVISIONED` no longer fires at ingest.
* Therefore, today: `trust.json` verifies and an index key is delegated, but
  **nothing has signed the catalogue with it**. Every catalogue is still
  classified `UNSIGNED`, and the ceremony changed the reason it carries — from
  `NoTrustAnchor` to **`NoSignatures`**. The daemon's `classify_signature`
  separates the two exactly: `NoTrustAnchor` means no verified `trust.json`
  reached the build, so there is no key to check any signature against, and the
  catalogue may well be signed; `NoSignatures` means the anchor is there and the
  catalogue itself carries none. What moved is which link is missing: the gap is
  now between the delegated key and the index, not between the root and the
  delegation.
* `registry/v1/index.json` and `registry/v1/revocations.json` are committed with
  `"signatures": []` — "unsigned" said out loud, where an absent member could not
  be told from a stripped one.
* Consequences that follow and must not be papered over: an unsigned catalogue
  can never upgrade a record to installable-with-full-trust, and because
  `verify_revocations_document` is strict (§6.4), **an unsigned withdrawal list
  is refused, so revocation enforcement is not live either** —
  `RevocationFreshness::NotEnforced` until a signature-valid list is fetched
  once.

Everything below describes the format and the algorithm, and none of it changes
when the remaining link lands. The root ceremony has already run and the
delegation is signed; what is left is for a signature to appear in the
`signatures` array of a published `index.json`, at which point the chain starts
carrying weight on a user's machine.

## 1. The envelope

Every signed document has the same outer shape:

```json
{
  "$comment": "…free text…",
  "signed":     { "schema": "…", "serial": 1, "…": "…" },
  "signatures": [ { "key_id": "astra-reg-2026a", "sig": "<base64, 88 chars>" } ]
}
```

* **Only `signed` is authenticated.** Nothing outside it may be read as a fact —
  not `$comment`, not the `key_id` strings, not the signature list's own shape.
* `sig` is base64 of the raw **64-byte Ed25519 signature**. The index schema pins
  the spelling: `^[A-Za-z0-9+/]{86}==$`.
* `key_id` is a **hint** for logging and key selection. A verifier **MUST** try
  every trusted key against every offered signature and **MUST** report the
  `key_id` of the key that actually verified, never the one the document claimed.
  A document that lies about who signed it still verifies if a trusted key did,
  and never verifies because it named the right key.
* An empty `signatures` array means unsigned. It is not an error shape; it is the
  pre-ceremony state and the state of a hand-written local catalogue.

## 2. The signing input

```
digest = SHA-256( domain ‖ 0x00 ‖ JCS(signed) )
sig    = Ed25519(private_key, digest)
```

* `domain` is the document's schema string: `astra.registry.trust/1`,
  `astra.registry.index/1`, or `astra.registry.revocations/1`.
* **The verifier supplies `domain` from its own constant, never from the
  `schema` member of the file it is reading.** Otherwise a signature over a
  `trust.json` is replayable as a signature over an `index.json` by editing one
  string — and anyone who could get one catalogue signed could then publish an
  *empty* withdrawal list and switch the mechanism off.
* The `0x00` is what stops a domain that is a prefix of another from colliding
  with it.
* Ed25519 verification **SHOULD** be strict (`ed25519_dalek::verify_strict`, or
  equivalent): reject small-order public keys and the malleable encodings a
  permissive verifier accepts.
* The signature is over the SHA-256 digest, passed to Ed25519 as an ordinary
  message. Do not enable any "pre-hashed" mode; Ed25519 hashes internally and
  this construction feeds it 32 bytes.

Both ends of this exist and agree by test:
`astra-registry/bot/lib/sign.mjs` (`signingDigest`, `signEnvelope`,
`verifyEnvelope`) and `astra-daemon/src/plugins/trust.rs` (`signing_digest`,
`verify_envelope`). `astra-registry/bot/fixtures/index/` holds a document the
JavaScript signer produced which the Rust verifier checks byte for byte, so
neither can drift without a red build.

## 3. Canonicalisation (JCS profile)

`JCS(signed)` is RFC 8785 canonical JSON, with one deliberate narrowing.

* **Object keys are sorted by UTF-16 code unit** (RFC 8785 §3.2.3). This is what
  JavaScript's default `Array.prototype.sort()` does, and the Rust side spells it
  out (`a.encode_utf16().cmp(b.encode_utf16())`) rather than assuming byte order.
  For all-ASCII keys the two orders coincide; above the BMP they do not.
* **No insignificant whitespace.** Compact form.
* **Strings** are escaped as RFC 8785 §3.2.2.2 requires: escape `"`, `\` and the
  C0 controls (short forms where they exist), leave `/` and all non-ASCII as
  literal UTF-8.
* **Numbers MUST be integers in ±(2^53 − 1)** — JavaScript's
  `Number.MAX_SAFE_INTEGER`. Both implementations **refuse** anything else rather
  than implement §3.2.2's floating-point canonicalisation. The registry emits
  only integers (`serial`, `size`, `protocol`), and an implementation that gets
  §3.2.2 *nearly* right produces signatures that verify on one side and not the
  other. `1.0` and `1` are the same JSON number and both serialise as `1`.
* **Duplicate object keys MUST be rejected at parse time**, not resolved (RFC
  8785 §3.1). `{"a":1,"a":2}` means two things, and a signed document must mean
  one. Trailing bytes after the document are rejected for the same reason.
* Members whose value is `undefined` do not exist; there is no such thing in
  JSON. (The registry's serialiser drops them; a JSON parser never produces one.)

The pretty file committed in the repository is produced by the *same*
serialiser (`stableStringify`) with the same key order, so a reviewer reading a
diff is reading the bytes that get signed, modulo whitespace.

## 4. Keys, delegation and rotation

### 4.1 Roots

* Ed25519. Public halves are **compiled into Astra**, base64 of the raw 32 bytes.
* **Two slots**, generated in one offline ceremony: one `Active`, one `Reserve`
  that is never used until a root must be replaced. Both ship from day one, so
  replacing a root is a signature rather than a flag day.
* A root signs **`trust.json` and nothing else**. A root signature never appears
  on `index.json`, on `revocations.json`, or on a bundle.
* `root.json` is a transcript, not an authority: it is unsigned on purpose — a
  self-signed root document proves nothing the compiled-in key does not already
  prove. It exists so the two copies can be compared. Each entry's
  `fingerprint_sha256` is SHA-256 over the raw 32-byte public key, lowercase hex;
  the same value `tools/keygen-root.sh` prints and the daemon logs when a root
  signature verifies.
* Test roots exist (`astra-registry/tools/testkeys/`, private halves committed on
  purpose, `key_id` prefixed `TEST-ONLY-DO-NOT-TRUST-`). The daemon can only
  compile them behind the non-default `insecure-test-trust-roots` feature **in a
  debug profile**; asking for it in a release profile is a `compile_error!`.

### 4.2 `trust.json`

```json
{ "signed": {
    "schema": "astra.registry.trust/1",
    "serial": 3,
    "issued_at": "2026-08-01T00:00:00Z",
    "expires_at": "2026-11-01T00:00:00Z",
    "index_keys": [
      { "key_id": "astra-reg-2026a", "public_key": "<base64 32 bytes>",
        "not_before": "2026-07-01T00:00:00Z", "not_after": "2026-10-01T00:00:00Z",
        "comment": "quarterly" }
    ],
    "reusable_workflow_shas": ["<40-hex commit>"]
  },
  "signatures": [ … ] }
```

Verification rules:

* `serial` **MUST NOT** be 0 — 0 is the "nothing accepted yet" sentinel on the
  verifier's side, so a published document may not claim it.
* `schema` **MUST** equal `astra.registry.trust/1`. Check it before the
  signature purely so a mis-filed document says "wrong schema" rather than "no
  root signed this"; it cannot change the outcome, because the digest domain is
  the verifier's own constant.
* Unknown members are **kept and ignored**. A newer registry adding a field must
  not brick an older daemon, and the raw verified `signed` survives a round trip
  so nothing is silently dropped and re-signed.
* An `index_keys` entry with an unparseable key or an unparseable window is
  **skipped with a warning**, not fatal: one bad row must not cost a catalogue
  that another key could verify. An unparseable `not_before` is treated as *not
  yet valid* and an unparseable `not_after` as *expired* — fail closed on the row,
  open on the document.
* `reusable_workflow_shas` is the allowlist of resolved reusable-workflow commit
  SHAs the **registry bot** enforces (§7). The daemon carries it and does not use
  it. Changing it is a root-key ceremony, which is the entire point of putting it
  here.

**Rotation.** Quarterly, and immediately on suspicion. A planned rotation
publishes a `trust.json` in which the outgoing and incoming keys have
**overlapping windows for 30 days**, so `index_keys_valid_at(now)` returning two
keys is the normal state during a changeover, not an anomaly.

### 4.3 Which clock judges a key window

Two clock readings exist: this machine's, and the HTTP `Date` of the fetch that
produced the document.

* **Freshness** (§5) is judged at `now = server_date ?? local` — believe the
  registry's reading for the duration of one fetch. This costs an attacker
  nothing they did not already have (they could serve a stale document to a
  machine whose clock they do not control) and rescues the far commoner case: a
  laptop with a wrong clock being told its catalogue has expired.
* **Key validity windows** are judged at `window_now = max(local, server)` — the
  network may pull "now" *forward* and **never** push it *back*. `not_after` is
  the only mechanism that retires a compromised index key; judging it at a
  network-supplied instant would let the thief also choose the day, forever, by
  answering with an old `Date`. Taking the later reading makes a stolen retired
  key *more* expired whichever reading the attacker controls.
* Disagreement beyond **2 hours** (`CLOCK_SKEW_TOLERANCE_HOURS`) is itself the
  signal: the verdict becomes `CLOCK_SKEW` rather than a claim about the
  document. Small enough that a dead CMOS battery trips it immediately, large
  enough that ordinary NTP-less drift does not.
* Anything **durable** written from a clock (last-fetch timestamps, floors) is
  clamped to the local clock first. One response carrying
  `Date: Fri, 01 Jan 2100 …` would otherwise move a daemon's notion of the
  present to 2100 permanently — a durable denial of service written by anyone who
  can answer one fetch.

## 5. `index.json`

### 5.1 Shape

`signed` is:

| member | type | rule |
|---|---|---|
| `schema` | const `astra.registry.index/1` | required |
| `serial` | integer ≥ 0 | required, monotonic (§5.4) |
| `issued_at` | `YYYY-MM-DDTHH:MM:SSZ` | stamped **at signing**, absent in the committed tree |
| `expires_at` | same | `issued_at + 30 days` |
| `plugins` | array | one record per listed plugin, sorted by `id` |

Timestamps are RFC 3339 UTC, **seconds precision, no milliseconds, no offset**.
Two spellings of one instant are two different signed documents.

A plugin record carries `id`, `name`, `version`, `description`, `license`,
`capabilities`, `repository_url`, `source`, `icon_url`, `downloads`, `stars`,
`updated_at`, `download_url`, `platform_downloads` and `releases[]`. The full
JSON Schema is `astra-registry/schema/index-v1.json`; it is `additionalProperties:
false` and is the authority on the field list.

Two rules are worth restating because a verifier depends on them:

* **`releases[]` is the authoritative half**, newest first by semver precedence.
  Each release has `version`, `published_at`, `release` (`{kind: "github_release",
  repo, tag}` or `{kind: "direct", base_url}`) and `artifacts` (platform key →
  `{url, filename, sha256, size}`).
* **The flat fields are a projection** of `releases[0]`, computed in the same
  generator pass, so they cannot disagree with it. `version`,
  `platform_downloads` and `download_url` exist because the shipping daemon reads
  exactly those.

Platform keys: `linux-x64`, `windows-x64`, `noarch`, plus the reserved
`linux-arm64`, `windows-arm64`, `macos-x64`, `macos-arm64`. A `noarch` artifact
is written under **every supported platform key**, so no client needs to know the
word (`PLATFORM_KEYS_FOR_NOARCH = ["linux-x64", "windows-x64"]`).

`downloads` and `stars` are always `0`. This registry counts nothing.

**Staging entries** — a listing whose release exists on paper but has no artifact
digest yet — are marked `staging: true`, are **omitted from
`platform_downloads` and `download_url`**, and are uninstallable by construction:
no digest, no install.

### 5.2 The artifact digest, and where URLs may point

`artifacts.<key>.sha256` is `sha256` of the whole `.astraplugin` file — the same
number as the attestation subject and as what the daemon hashes
([`bundle-v2.md` §3.1](bundle-v2.md#31-artifact-digest)). `size` is that file's
length; the schema caps it at 256 MiB.

Every artifact URL **MUST** be `https://` and **MUST** sit under the prefix its
own `release` object implies:

* `github_release` → `https://github.com/<repo>/releases/download/<tag>/`,
* `direct` → the release's `base_url`,

and **MUST** end in the declared `filename`. This is enforced in
`astra-registry/tools/validate.mjs`, not by a schema pattern, because a pattern
that could only describe GitHub made the self-hosted case unstateable. `direct`
exists for self-hosted and staging catalogues; policy keeps it out of the public
catalogue.

### 5.3 Determinism — the property an auditor leans on

`index.json`'s `signed` member is generated from `plugins/**` by
`tools/build-index.mjs` and **reads no clock**: same sources + same serial → same
bytes. Keys sorted by UTF-16 code unit, plugins by id, releases by semver.
`--check` fails if the committed file differs by one byte, and CI runs it.

`issued_at`/`expires_at` are added by `bot/sign-index.mjs` at signing time, not
by the generator, for two reasons: they are properties of the *publication*, and
a generator that read a clock could not be reproduced. This is what makes §8's
audit possible at all — a third party can rebuild the catalogue content from the
git tree and compare it to what was signed.

### 5.4 Serial

* **Monotonic**, derived from `git rev-list --count HEAD -- plugins` on the
  default branch. Never read-and-increment from a file: two merges in the same
  minute both read *N* and both write *N+1*, and the second silently un-bumps the
  first. A commit count is a property of the history, so concurrent merges get
  distinct values by construction. Path-limiting means a docs commit does not
  move the catalogue's version number.
* A verifier keeps a **serial floor** per catalogue URL and refuses anything
  below it. The floor is `max(in-memory, on-disk)` and lives in daemon-owned,
  MAC'd state (`astra.registry.state/1`), **not** in the index cache: the cache
  is a convenience that may be deleted at any moment, and the floor is a security
  decision that must survive exactly the deletion an attacker would perform. It
  is monotonic *in code*, so corrupting the state file resets the file and not the
  running process.

Three documents, three serial rules, and the differences are deliberate:

| document | accepted when | why |
|---|---|---|
| `trust.json` | **strictly greater** than what is held | it changes only on a key rotation, so "same serial, different bytes" is a rollback attempt and nothing else |
| `index.json` | **not below** the floor | ordinary republication |
| `revocations.json` | **greater or equal** on disk; a **strictly greater** serial replaces the set, a lower-or-equal one may only **add** | the list is re-signed on a schedule to stay inside its 7-day window; refusing equal would make every quiet week block installs. "Same serial, fewer entries" is a replay, and adding-only defeats it |

The MAC on the state file is a **tripwire, not a boundary**: the key lives in the
same 0700 directory as the file it authenticates, so an attacker who can read
that directory can forge it. It raises the bar from "edit a file" to "find and
use the key". The real boundary is the directory — a sibling of `plugins/`, never
a child, so the subject of these decisions is not also their author.

### 5.5 Freshness, and the asymmetry that matters most

| document | TTL | what staleness costs |
|---|---|---|
| `index.json` | **30 days** (`CATALOG_TTL_DAYS` / `CATALOG_MAX_AGE_DAYS`) | a **banner**. Browse says the catalogue is old. **Cached, digest-pinned records stay installable.** |
| `revocations.json` | **7 days** (`REVOCATION_TTL_DAYS` / `REVOCATION_MAX_AGE_DAYS`) | a **hard block** on new installs |

This asymmetry is the whole freshness policy, and it follows from what each
document is for. A catalogue record is a *digest*, and a digest does not expire:
an attacker who freezes the registry so you keep a record you already verified
gains nothing. A withdrawal list is the opposite — "carry on" there means "keep
installing something we may already have withdrawn" — so that one is the block:

> `REVOCATIONS_STALE: Astra can't check whether this plugin has been withdrawn.
> The withdrawal list it has is N days old and Astra will not install with one
> older than 7 days. Reconnect to the network and try again. Plugins already
> installed keep running.`

Note the last sentence. Staleness never stops a plugin that is already running.

Verdict codes a conforming client emits, most severe first
(`IndexVerdict::code`):

| code | meaning |
|---|---|
| `SIGNATURE_INVALID` | signatures were offered and none was made by a trusted key. **The only code that means tampering.** No clock is involved in reaching it, so no clock can excuse it. |
| `SIGNATURE_KEY_EXPIRED` | a delegated key signed it, outside its window, judged with a server `Date` in hand (so skew is not an explanation) |
| `CLOCK_SKEW` | this machine's clock and the document's timestamps cannot both be right, and the signature verified — so the clock is the suspect |
| `CATALOG_STALE` | past `expires_at` |
| `FRESHNESS_UNKNOWN` | no `issued_at` and no `expires_at` — a hand-written local catalogue |
| `UNSIGNED` | no signatures, or no trust anchor to check them against |

`SIGNATURE_INVALID` and `SIGNATURE_KEY_EXPIRED` are **rejections**: the document
is not read at all, and there is no cached fallback offered for it. `UNSIGNED` is
not a rejection — it is the pre-ceremony state of the world and of every local
catalogue — but it can never upgrade a record to fully trusted.

Where a document was **fetched from is never an input**. A catalogue is believed
because a delegated key signed it; `plugins.registry_url` is ordinary
configuration and the catalogue is expected to move hosts. The daemon's
verification path contains no hostname check and must not grow one.

## 6. `revocations.json`

### 6.1 Shape

```json
{ "signed": {
    "schema": "astra.registry.revocations/1",
    "serial": 12,
    "issued_at": "…", "expires_at": "…",
    "revocations": [
      { "kind": "digest", "value": "<64 hex>",
        "id": "ASTRA-2026-0001", "severity": "critical", "action": "disable",
        "reason": "Exfiltrated conversation history to an attacker-controlled host.",
        "advisory_url": "https://…" }
    ] },
  "signatures": [ … ] }
```

Generated from one file per advisory under `astra-registry/tools/revocations/`
by `tools/build-revocations.mjs`; one advisory becomes one entry per key it
names, and every entry carries the advisory's id, severity, action, reason and
URL, because a client shows exactly one of them — the first that matches — and
each must stand on its own. Entries are sorted by `(kind, value)`, so the
document is deterministic.

### 6.2 The kind vocabulary

`RevocationKind` in `astra-daemon/src/plugins/trust.rs` is the authority; the
registry's `KINDS` table exists so a registry cannot publish a kind the daemon
would silently ignore — an unknown kind is a withdrawal that does not happen.

| kind | `value` | matches |
|---|---|---|
| `digest` | 64 lowercase hex | `sha256` of a whole `.astraplugin`, compared case-insensitively |
| `binary` | 64 lowercase hex | `sha256` of a **resolved `entry.command` file** |
| `id` | plugin id | every version of that plugin |
| `id_version` | `<id>@<semver>` | that exact release |
| `version_range` | plugin id + `versions` window | see §6.3 |
| `identity` | `github:owner/repo` or `origin:host` | a pinned publisher identity |
| `publisher_key` | a key id | a trust record's `signer_key_id` |

`action` is `block_install`, `disable` or `warn`. `warn` does not block an
install; `disable` also stops and disables a copy already installed. `severity`
(`critical` / `high` / `moderate` / `low`) is advisory only — no behaviour hangs
on it.

`reason` is shown to a user **verbatim** in a notification the daemon marks
persistent, so the generator refuses text containing bidi overrides or
zero-width joiners, and caps it at 300 characters.

### 6.3 Version windows

OSV's shape and OSV's semantics: `introduced` is **inclusive**, `fixed` is
**exclusive**, both optional, and `{}` means every version — which makes
`version_range` a strict generalisation of `id`. `introduced == fixed` covers
nothing and is refused at build time.

Ordering is standard semver precedence, so `1.0.0-rc.1 < 1.0.0`: an advisory that
says "fixed in 1.0.0" must not leave `1.0.0-rc.1` unrevoked. Build metadata is
ignored (semver §10). **A version string neither side can parse is *inside* the
window** — the alternative is that `version = "totally-fine"` slips past every
bound an advisory could express, and the attacker chooses that string.

### 6.4 Verification is strict, unlike the catalogue's

`verify_index_document` returns a graded verdict; `verify_revocations_document`
returns `Err`. No trust anchor, no signature, a signature from a stranger, or a
signature from a key outside its window are all failures. A withdrawal list is
only ever consulted in order to *refuse* something, so a document nobody can
attribute has exactly one safe reading — "this is not a withdrawal list" — and
returning it as an empty set would be the attacker's preferred outcome, reachable
by serving any file at all.

The absence of a usable list is handled one level up, by the 7-day block (§5.5).
That, and not a permissive parser, is what keeps a registry outage from becoming
a silent loss of enforcement.

A cached list is **re-verified on every load**, never trusted because this daemon
once wrote it — which is what lets the cached copy be an install-grade input, and
why a key rotation retires the cached list at the same moment it retires a live
one.

### 6.5 The sideload gap, closed at the source

A digest-only advisory leaves a hole by default: withdraw by digest, and a user
can uninstall (dropping the trust record the digest was read from), copy
`plugin.toml` and the binary into a directory, and sideload the same code. A
directory has no archive, so it has no bundle digest and no signer.

The generator therefore **refuses an advisory whose every entry is keyed on
something a directory cannot have.** At least one entry **MUST** be of kind
`binary`, `id`, `id_version` or `version_range`. `identity` and `publisher_key`
explicitly do not count.

Five enforcement points consume the list: install (§5.3-A.4 of the plan), update
resolution, the import path, the sideload path, and the periodic intersection of
the list with installed plugins by recorded `artifact_sha256`.

## 7. Provenance — what the registry checks that the daemon cannot

### 7.1 At ingest (registry bot, `bot/lib/attestation.mjs`)

1. `gh attestation verify <file> --repo <repo> --signer-workflow <path>
   --format json`. This proves a workflow in that repository built these bytes
   and that Sigstore recorded it.
2. **The attestation's subject digest MUST equal the artifact's `sha256`** —
   the third of that number's three places (`E_ATTESTATION_SUBJECT_MISMATCH`).
3. The certificate's source repository MUST be `https://github.com/<repo>`
   (`E_ATTESTATION_REPO_MISMATCH`).
4. The **resolved reusable-workflow commit SHA** is read back out of the
   certificate and MUST appear in `trust.json`'s `reusable_workflow_shas`
   (`E_WORKFLOW_NOT_ALLOWED`). A missing SHA is a failure, not a default
   (`E_ATTESTATION_INVALID`).

Step 4 is what makes a mutable `@v1` tag unusable as a supply chain: a tag can be
repointed at any commit and the attestation would still name the right repository
and workflow file. Changing that allowlist is a root-key ceremony.

That allowlist now exists: the signed `trust.json` names exactly one commit,
`e3329df252a46d747676cb540ae4b986af68a3ad`. So `E_TRUST_UNPROVISIONED` no longer
stops ingest, and step 4 is live — a build produced by any other workflow is
refused with `E_WORKFLOW_NOT_ALLOWED`. The daemon-side half is still fail-closed
for a different reason: the catalogue itself carries no signature (§0.1).

### 7.2 Not implemented: the per-release countersignature

`PRODUCTION_PLAN` §5.2 specifies a per-release countersignature over

```
SHA256("astra-registry-countersign-v1" ‖ 0x00 ‖ id ‖ 0x00 ‖ version ‖ 0x00 ‖ platform ‖ 0x00 ‖ artifact_sha256)
```

**Nothing computes or checks this today.** The string appears in the plan and
nowhere in any of the three repositories. A record's authenticity currently comes
from the index envelope signature that covers the whole catalogue. Do not
implement a verifier against this section expecting to find such a field.

### 7.3 What the daemon does instead

The daemon performs **no** Sigstore verification: attestations are checked in the
bot's CI, where the network, the GitHub API and `gh` all exist. Locally it does
two things, and their combination is what bounds a registry-key compromise to
"publish new plugins":

* **TOFU pin.** On first install it records the identity the listing declared
  (`{kind: "github", repo}` or `{kind: "origin", host}`). An update whose
  identity differs is a **hard block with no override, ever**.
* **URL-vs-identity binding.** The artifact URL must live under the pinned
  repository's release namespace, compared on host and path prefix after redirect
  resolution. The identity is the repo the record **declares**, never the repo
  the URL implies — deriving it from the URL would make the check tautological on
  a first install.

Residual risk, stated because the UI must not overstate: `identity` is a string
the registry asserts. A compromised index key can publish a record with a
truthful identity and a fabricated provenance block. The URL check forces the
bytes to come from the pinned repo's release namespace; a repo-plus-registry
compromise defeats both.

## 8. The audit procedure

Everything in the published catalogue is verifiable by a third party with no
access to any private key. This is the procedure. Steps marked **tooling** have a
script in `astra-registry`; steps marked **manual** do not yet, and the
`registry/tools/audit-index.sh` named in `PRODUCTION_PLAN` §5.5 **does not exist
today** — it is described here as the procedure it will automate.

**A. Reproduce the catalogue content.** *(tooling)*

```sh
git clone <registry repo> && cd astra-registry
node tools/build-index.mjs --check          # byte-identical regeneration
node tools/build-revocations.mjs --check
node tools/validate.mjs                     # schema + URL pinning + digests
```

Then compare the published `signed` member against the regenerated one, ignoring
only `issued_at` and `expires_at` (§5.3). Any other difference is a catalogue
that does not match its own git history.

*What this prints today* (verified while writing this document): both `--check`
runs report "byte-identical to a fresh generation" at serial 1 with 0
signatures, and `validate.mjs` **fails** — all eleven listings are staging
entries with no artifact digest, which it refuses unless `--allow-staging` is
passed. That is the correct answer for a catalogue whose plugins have not been
released yet, and it is the reason nothing in it is installable.

**B. Check the signature chain.** *(tooling)*

```sh
node bot/sign-index.mjs --verify registry/v1/index.json --trust registry/v1/trust.json
```

and, by hand, that `trust.json` verifies under a key in `registry/v1/root.json`
whose fingerprint matches the one your Astra binary logs. Recompute independently
if you prefer: `SHA-256(domain ‖ 0x00 ‖ JCS(signed))`, Ed25519-verify, per §2–§3.

*What this prints today:* `FAIL … no trusted key was supplied (offered: none;
trusted: none)` — there is no `trust.json` to pass and no root to verify one
with (§0.1). A verifier that reported anything else against the current tree
would be lying.

**C. Check the serial and the window.** *(manual)* `serial` must be ≥ the last
one you saw; `expires_at − issued_at` must be 30 days for the catalogue and 7 for
the withdrawal list; `key_id` must be a key `trust.json` names with a window
containing `issued_at`.

**D. Check every artifact against the public transparency log.** *(manual)* For
each release in the index — `<…>` are placeholders read out of the index record,
so these two commands are a template rather than a copy-paste:

```sh
curl -fL -o a.astraplugin "<artifacts.<key>.url>"
sha256sum a.astraplugin                     # must equal artifacts.<key>.sha256
gh attestation verify a.astraplugin \
   --repo <release.repo> \
   --signer-workflow <AstraPlugins>/.github/workflows/plugin-release.yml \
   --format json
```

`--repo` is the **author's** repository, from the index record's
`release.repo`. `--signer-workflow` is the **shared reusable** workflow that
built it — the one `astra-plugin init-ci` pins the caller to, held by the bot as
`DEFAULT_SIGNER_WORKFLOW` in `astra-registry/bot/ingest.mjs` and asserted against
a file that exists in `AstraPlugins/.github/workflows/`. Take the exact string
from that constant rather than reconstructing it; a transposed path matches no
attestation at all and every honest artifact then looks like it has none.

`gh attestation verify` fetches the Sigstore bundle for that artifact digest and
checks it against Sigstore's trust root, **including the Rekor transparency-log
inclusion proof**. From its JSON output, assert by hand what the bot asserts at
ingest (§7.1): the subject digest equals the file's digest, the source repository
is the repo the index names, and the resolved signer-workflow commit SHA is in
`trust.json`'s `reusable_workflow_shas`.

A record the registry published for an artifact with **no** attestation, or one
whose attestation names a different repository, is exactly the after-the-fact
detection this procedure exists for: nothing stops a compromised registry key
from publishing a *new* plugin, and auditability is the whole of the mitigation.

**E. Check the bundle itself.** *(tooling)* Run
[`bundle-v2.md` §13](bundle-v2.md#13-the-verification-algorithm) over the
downloaded file, and confirm its `MANIFEST.json` `plugin_id`, `version`,
`platform` and `permissions_hash` agree with the index record.

## 9. Summary of what is in force today

| property | status |
|---|---|
| document formats, envelope, signing construction, JCS profile | implemented on both ends, cross-tested by fixture |
| root keys | **provisioned** 2026-08-11 — the same two on both sides |
| `trust.json` | **signed** under `astra-root-2026a`, delegating to `astra-index-2026a` and allowlisting one workflow commit |
| `index.json` / `revocations.json` signatures | empty arrays in the committed tree — **this is now the missing link** |
| catalogue verdicts, serial floors, freshness, clock handling | implemented in the daemon and under test |
| revocation vocabulary, matching, five enforcement points | implemented; **inert until a signature-valid list is fetched once** |
| build attestation check at ingest | implemented and live; the workflow allowlist comes from the signed `trust.json` |
| per-release countersignature | specified in the plan only; **no implementation** |
| `audit-index.sh` | does not exist; §8 is the manual procedure |

---

*Sources checked while writing this document:
`astra-registry/schema/{index-v1,version-v1,plugin-v1}.json`;
`astra-registry/tools/lib/canonical.mjs`; `astra-registry/tools/lib/revocations.mjs`;
`astra-registry/tools/build-index.mjs`; `astra-registry/bot/lib/sign.mjs`;
`astra-registry/bot/sign-index.mjs`; `astra-registry/bot/lib/attestation.mjs`;
`astra-registry/registry/v1/{root,index,revocations}.json`;
`astra-registry/SECURITY.md`;
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/registry_client.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs` (`refresh_revocations`).*
