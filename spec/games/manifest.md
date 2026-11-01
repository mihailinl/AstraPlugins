<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# The game-integration manifest: `[integration.*]`, schema 1

This is the normative spec for the keys the games marketplace adds to
`astra-gi.toml`. It does not replace
[`astra-bepinex`'s `GAME-INTEGRATION-MANIFEST.md`](https://github.com/mihailinl/astra-bepinex/blob/main/docs/GAME-INTEGRATION-MANIFEST.md),
which stays authoritative for `schema = 1`'s existing sections
(`[integration]`, `[target]`, `[[files]]`, `[[game_files]]`, `[launch]`,
`[[config_writes]]`) and for BepInEx-specific guidance. This document covers
only what `dev/game-integrations-plan-merged.md` §2.2 adds under
`[integration.*]`, normative for any engine and any language — Unity, Unreal,
Godot, Source 2, Lua, Java, whatever a foundation's author writes.

Authority order, where this document and the launcher's parser disagree: the
launcher wins today (it is what actually runs), and a disagreement is a bug in
one of the two, reported like any other — see `CLAUDE.md`, "Test the thing,
not the description of it." `src/manifest.rs` in `astra-game-launcher` is the
code this document describes; `spec/games/schemas/manifest.schema.json` is
its machine-checkable shape, validated against the goldens in
`testdata/games/manifests/`.

## 1. Why `[integration.*]`, never a new top-level table

`astra-game-launcher` v0.3.1 refuses an unknown key in a section that **acts**
(`[target]`, `[[files]]`, `[[game_files]]`, `[launch]`, `[[config_writes]]`)
but reads `[integration]` as metadata with no key check at all
(`v0.3.1:src/manifest.rs:27-38`). So every key this document adds lives nested
under `[integration]`, where an old client silently ignores it instead of
refusing the whole manifest. `schema` stays `1`: a schema bump is reserved for
a change `[integration.*]` cannot carry, and none of the merged plan's
additions needs one (merged §2.2; R12 in §1 of the merged plan keeps
engine-only foundations on schema 1 with a mandatory `[target].engine`, never
the schema-2 the earlier marketplace plan proposed).

**No new `${var}` placeholder.** A manifest that references one answers
`unknown-placeholder` at Play (`v0.3.1:src/launch.rs:142,210`), so nothing
below introduces one; the AI-facing data (`[integration.link]`) travels over
the Astra Link socket instead, never through `[launch].args`.

## 2. The five new tables

```toml
schema = 1

[integration]
id = "someone.peak-astra"
name = "Astra in PEAK"
version = "1.2.0"
license = "MIT"
repo = "https://github.com/someone/peak-astra"
sdk = "https://github.com/mihailinl/astra-unity-sdk"   # optional; dev-mode only, §2.5

[integration.engine]
# present only on the foundation that OWNS this engine code — §2.1
schema = "astra.engine/1"
engine = { codes = { source2 = "Source 2" } }
# … the rest of the astra.engine/1 object; see spec/games/engine-descriptor-v1.md

[integration.loader]
proxies = ["dinput8.dll"]
keep_if_present = ["s2bridge.ini"]

[integration.capabilities]
companion = ["presentation"]

[integration.foundation]
id = "astra.unity"
version = "0.8.1"
engine = "unity-mono"

[integration.link]
context = true
shares_other_players = false
skill = "astra/SKILL.md"
[[integration.link.tools]]
name = "drop_item"
description = "Drop the item the player holds"
params = "astra/tools/drop_item.json"
[[integration.link.triggers]]
name = "boss_spawned"
label = "A boss appears"
data = "astra/triggers/boss_spawned.json"
[[integration.link.events]]
name = "player_died"
data = "astra/events/player_died.json"

[[integration.content]]
path = "animations/climb.fbx"
kind = "animations"
title = "Climb cycle"
credit = "someone"
licence = "CC-BY-4.0"

[target]
engine = "source2"     # mandatory whenever [integration.engine] names a non-built-in code
exe = "*"
platforms = ["windows-x64", "linux-proton"]
anti_cheat = "none"
```

Every table is optional; a manifest with none of them is an ordinary
game-specific or runner GI exactly as `GAME-INTEGRATION-MANIFEST.md` already
describes.

### 2.1 `[integration.engine]` — owning a code

Present **only** on the foundation that first claims an engine code at
ingest. Its value is one `astra.engine/1` descriptor object, normative in
[`engine-descriptor-v1.md`](engine-descriptor-v1.md); this document does not
repeat that grammar.

- A manifest that carries `[integration.engine]` **must** also set
  `[target].engine` to the same code. A mismatch, or a missing
  `[target].engine`, is `engine-undeclared`.
- `[target].engine` names (built-in or declared) are the only values
  `[target].engine` may take; a bare string that matches no known and no
  self-declared code is `engine-not-recognized` at evaluation, not a parse
  error — a foundation ships before its code is anywhere else yet.
- **Many foundations, one owner.** A second (or third…) foundation for the
  same engine writes `[target].engine = "<code>"` and ships **no**
  `[integration.engine]` table at all. It is offered through
  `foundations_for(code)` once the owning foundation's descriptor matches a
  game; it never carries its own copy of the grammar, and two copies that
  drifted is exactly the bug a single owner avoids (merged §2.1, "Many
  foundations per code").
- A code is refused at ingest when it is in `spec/games/reserved.yaml`
  (`engine-code-reserved`) or already claimed by a different publisher
  (`engine-code-taken`); neither check is a manifest-parse concern, so
  `gi-probe check` does not raise them — only real ingest, which holds the
  catalogue's ownership table, can.

### 2.2 `[integration.loader]` — what this install's own loader does

```toml
[integration.loader]
proxies = ["dinput8.dll"]
keep_if_present = ["s2bridge.ini"]
```

| key | meaning |
|---|---|
| `proxies` | bare DLL names (`is_dll_name`, `manifest.rs`) this foundation hijack-loads beside the exe. A file by one of these names that the launcher did **not** place is a foreign loader, never silently replaced (merged §2.5; B§3 "Foreign loader → keep") |
| `keep_if_present` | file names kept at uninstall when present and not Astra's own placement — a sharing marker (e.g. a co-loaded Doorstop's own ini), never a loader DLL |

The two lists must be **disjoint**: a name in both is `loader-policy-conflict`
at `gi-probe check` time. This table only *labels* the files this install's
own `[[game_files]]`/`[launch]` already places or touches — it grants nothing
by itself. The catalogue's separate `loaders.json` allowlist (merged §2.5,
"Classification") decides what the install **sheet** and the moderator queue
show about a loader the manifest did not declare; a manifest cannot widen what
it is allowed to do by naming something here that `[[game_files]]` never
places.

### 2.3 `[integration.capabilities]` — the avatar bridge

```toml
[integration.capabilities]
companion = ["presentation"]
```

`v1`'s only id is `companion.presentation`: this GI's `${bridge_token}`
config write (see `GAME-INTEGRATION-MANIFEST.md` §4's `[[config_writes]]`
example) may be captured by the desktop companion. `gi-probe check` refuses
`${bridge_token}` anywhere in `[[config_writes]]` when this table is absent or
does not list `presentation` (`capability-undeclared`) — merged §2.2 replaces
the earlier plan's inference from the variable's mere presence with this
explicit declaration. An id this launcher does not recognise is
`needs-newer-astra`, never silently dropped: a capability a newer Astra
grants must not look granted on an older one.

### 2.4 `[integration.foundation]` — building on someone else's engine support

```toml
[integration.foundation]
id = "astra.unity"
version = "0.8.1"
engine = "unity-mono"
```

A claim only — "this GI's `[[files]]` were built against foundation `id`
version `version`, targeting engine `engine`." Ingest computes the truth
(`built_on{entry, version, verified}`) by comparing digests against the named
foundation's **full** file set; `verified` is true only on a full match. A
runner manifest (the three first-party built-ins) carries **no**
`[integration.foundation]` table (merged plan, lane L/K13 "runners carry no
`[integration.engine]`" — the symmetric rule for foundation claims), and
neither does a GI with no engine dependency (astra-in-death-stranding: R14).

### 2.5 `[integration] sdk`

```toml
[integration]
sdk = "https://github.com/mihailinl/astra-unity-sdk"
```

An optional URL, metadata only (so an old client reads and ignores it like
every other `[integration]` key). Shown only in Settings → Developer, never
on the ordinary install sheet — it is a pointer for the next author building
on this foundation, not something an installing user needs.

### 2.6 `[integration.link]`

The full grammar, limits and the wire protocol it drives are normative in
[`link-v1.md`](link-v1.md) (**DRAFT** — may freeze as late as 0.2.8.x; see
that document's status note). This table's shape in the TOML is exactly the
example in §2 above: `context`, `shares_other_players`, an optional `skill`
path, and the three repeatable arrays `tools`, `triggers`, `events`. Limits
enforced by `gi-probe check`, unchanged from the earlier marketplace plan:
at most 16 tools, 16 triggers and 32 events; every named JSON Schema file
(`params`/`data`) may use only a local `$ref` and only linear-time regex
patterns (§6 of `link-v1.md` gives the exact restricted profile and its own
schema).

### 2.7 `[[integration.content]]` — this GI's own animations, models, art and audio

```toml
[[integration.content]]
path = "animations/climb.fbx"
kind = "animations"
title = "Climb cycle"
credit = "someone"
licence = "CC-BY-4.0"
```

A game integration may ship its own non-built-in assets — a climbing
animation, a character model, cover art, a theme track — instead of (or
alongside) referencing something already in Astra. Each one gets its own
author rights-confirmation checkbox at publish time, using exactly the same
confirmation text astra-ce uses for the same kind (owner's rule, merged plan
§5.4). This table is what makes that checkbox possible: one entry per asset,
never a whole folder at once, so each confirmation is about one identifiable
file.

| key | meaning |
|---|---|
| `path` | the part's id: relative to the release zip's root, no `..` segment, no `:` (so a `builtin:` reference can never be mistaken for a declared part, below). **Must be unique** across this table — a path declared twice is `content-duplicate`, §2.7.2 |
| `kind` | `"animations"` \| `"character"` \| `"art"` \| `"audio"`. The shared asset-rights rule astra-ce uses also has a `command` kind (a character macro), and it is deliberately **not** in this enum: a GI is a native process already, running what it likes, and "confirm you have the rights to run this command" is not a sentence that means anything here |
| `title` | shown next to the checkbox |
| `credit` | shown next to the checkbox |
| `licence` | an SPDX id or free text (unlike `[integration] license`, which is the *code's* licence and is SPDX-allowlist-checked, §4 of the ingest order below never allowlist-checks this field — it is shown, not policed) |

#### 2.7.1 Content-typed files, and the ingest order

A **content-typed** file is one whose extension **and** magic bytes both say
so — an extension alone is never enough, because nothing stops an author
naming a loader DLL `climb.fbx`:

| extension | magic |
|---|---|
| `.astrapack`, `.astrachar` | a zip local-file-header signature (`PK\x03\x04`/`PK\x05\x06`/`PK\x07\x08`) — both are zips built on the same core (astra-companion `docs/animation-packs.md` D1/D2) |
| `.vrma`, `.glb`, `.vrm` | the GLB container magic, the literal bytes `glTF` |
| `.gltf` | JSON text (starts with `{`) |
| `.fbx` | the binary FBX magic `Kaydara FBX Binary` or the ASCII header `; FBX` |
| `.png`, `.jpg`/`.jpeg`, `.webp`, `.gif` | the format's own file signature |
| `.ogg`, `.wav`, `.mp3`, `.flac` | the format's own file signature |

Code, DLLs and loader binaries never count, whatever their extension — this
table is closed, and nothing outside it is ever treated as content.

**Ingest runs in this order: provenance → manifest schema → content check →
gi-probe.** The content check — this section — runs on the real release zip,
after the manifest has parsed and validated but *before* gi-probe, because
gi-probe's own report (code changes, loader classification, Link limits) is
about the GI's *code*, and a release with broken content declarations is
refused before that code is even inspected. `gi-probe check` (lane L, once
built) raises the same codes below for an author's own local run; the
catalogue's ingest (astra-games-catalogue, `lib/content.mjs`) is the
authoritative implementation today.

#### 2.7.2 The coverage refusals

Every content-typed file in the release must be covered by **exactly one**
`[[integration.content]]` entry:

- `E_CONTENT_UNDECLARED` — a content-typed file with no entry at its path.
- `E_CONTENT_MISSING` — an entry whose `path` matches no content-typed file.
  A file that merely sits at that path but fails the magic-byte check (a
  renamed loader DLL, a corrupted GLB) does not count as covering the entry:
  the check fails closed, not open.
- `E_CONTENT_DUPLICATE` — a `path` declared by more than one entry.

A `builtin:` reference (astra-companion's own shorthand for "no bytes here,
use the compiled-in one") is never a part — `path`'s pattern refuses the `:`
that would make such a reference parse at all, and even without that, no
real file in the zip would ever match it, which only ever reads as
`E_CONTENT_MISSING`.

#### 2.7.3 The HARD VRM licence gate

**Normative source: marketplace legal `DRAFT-v3.md` Part 6 G4 (Terms 8.1,
D8 — widened by the coordinator's second round, 2026-11-01) and G5 (Part 1
rule 2; Terms 6.4).** D8 was decided for astra-ce's character checkbox
first; G4 makes it the *same* rule for a GI's content parts — one gate,
read the same way, wherever a VRM reaches Astra.

Runs **before any checkbox** — a licence that refuses redistribution is not
something an author's confirmation can override. It applies to every `.vrm`
file this table declares, and to the body inside a `.astrachar` bundle
*when that bundle's format is readable* (its `astrachar.json` parses, its
`body` is a `{"file": ...}` pointing at a `.vrm` inside the same zip —
astra-companion `docs/character-files-and-2d-editor.md` §1.3/§1.4). When it
is not readable, that is noted as a gap (`F_CONTENT_ASTRACHAR_UNREADABLE` in
the catalogue), never a refusal: an unreadable bundle is a different problem
than a bundle that reads cleanly and says no.

The gate parses the file's GLB container (the 12-byte header, then the first
chunk if it is typed `JSON`) and inspects `extensions` in that chunk. It
refuses with `E_CONTENT_LICENCE_REFUSED`, naming the field and its value,
when:

- **VRM 0.x** — `extensions.VRM.meta.allowedUserName == "OnlyAuthor"`, or
  `== "ExplicitlyLicensedPerson"` (named people only, D8 widened), or
  `extensions.VRM.meta.licenseName == "Redistribution_Prohibited"`;
- **VRM 1.0** — `extensions.VRMC_vrm.meta.avatarPermission == "onlyAuthor"`,
  or `== "onlySeparatelyLicensedPerson"` (named people only), or
  `extensions.VRMC_vrm.meta.allowRedistribution == false`.

**A file carrying BOTH blocks is judged on both, never only the first one
found** (O-2 — the games gate and this document both used to stop at
`extensions.VRM.meta` when present and never look at `extensions.VRMC_vrm.meta`
at all, so a file whose VRM 0.x meta allowed and whose VRM 1.0 meta prohibited
passed outright). The content catalogue's own contract states the same rule
for the same reason (`ingest-v1.md` §4.2 — "A file carrying BOTH metas is
judged on both. If they disagree → `E_CONTENT_LICENCE_CONFLICT`"); here, that
means the rule above runs once per meta (each spec reading its own absent-field
default below, independently), and the file is refused
**`E_CONTENT_LICENCE_CONFLICT`**, naming both verdicts, whenever:

- the two verdicts disagree — the redistribution/permission fields above lead
  one spec to allow what the other refuses; or
- the two sides both carry an **overlapping** usage flag (G5, below) and its
  effective allow/disallow differs between them: VRM 0.x `violentUssageName`
  against VRM 1.0 `allowExcessivelyViolentUsage`, and VRM 0.x
  `sexualUssageName` against VRM 1.0 `allowExcessivelySexualUsage`. VRM 0.x's
  `commercialUssageName` and VRM 1.0's `allowPoliticalOrReligiousUsage` /
  `allowAntisocialOrHateUsage` have no counterpart on the other spec and are
  never compared.

A conflict is refused outright, before `licence_source` (below) is even
asked — it is never "whichever meta happened to parse first wins".

**An absent field reads as ITS OWN SPEC'S default, never as "allowed"** —
this replaces this document's earlier text, which said the opposite and was
wrong (G4: "reading each spec's defaults for absent fields"). The defaults
are astra-companion's own (`src/vrm/meta.rs:80-100`, `licence_of` /
`redistribution_of`, the implementation this gate ports):

| spec | field | when absent |
|---|---|---|
| VRM 1.0 | `avatarPermission` | `"onlyAuthor"` — refused |
| VRM 1.0 | `allowRedistribution` | `false` (the meta schema's own default) — refused |
| VRM 0.x | `allowedUserName` | `"OnlyAuthor"` (UniVRM's default) — refused |
| VRM 0.x | `licenseName` | prohibited (UniVRM's default) — refused |

So a VRM 1.0 file whose `extensions.VRMC_vrm.meta` carries neither field at
all is refused exactly as if it had written `avatarPermission: "onlyAuthor"`
itself — absence is never a gap in this gate, only in the one below.

**`unknown`: no VRM meta at all.** A `.vrm` file (or a readable `.astrachar`
body) that is a well-formed GLB but carries no `extensions.VRM.meta` and no
`extensions.VRMC_vrm.meta` block — not every `.vrm` has one — is neither
refused nor passed silently: it is flagged `F_CONTENT_VRM_META_UNKNOWN` and
reaches the release's confirmation step only via §2.7.3's `licence_source`
fallback below (G4: "`unknown` passes only with the character checkbox and
the licence line beside it", which is the publish form's job, not this
gate's).

**The usage flags (G5).** Kept with the part in `vrm_licence.fields`
whichever of these the file actually carries, alongside the
redistribution/permission fields above, so the install sheet and the public
card can show the whole licence line:

- **VRM 1.0** — `allowExcessivelyViolentUsage`, `allowExcessivelySexualUsage`,
  `allowPoliticalOrReligiousUsage`, `allowAntisocialOrHateUsage`;
- **VRM 0.x** — `violentUssageName`, `sexualUssageName`,
  `commercialUssageName` (the spec's own misspelling, kept verbatim).

`vrm_licence.fields` holds the **raw** keys the file carries — an absent
key's spec default is applied only by the refusal logic above, never
fabricated here; a display default (if any) is the install sheet's own
concern, not this gate's. **When both blocks are present and agree** (no
conflict above), `vrm_licence` shows the VRM 1.0 side — the same precedence
astra-companion's own `licence_of` reads them in for display, "a file
carrying both is read as 1.0". A conflict carries no `vrm_licence` at all:
the release is refused before display is ever asked.

**`licence_source`: every covered part needs a licence from somewhere.**
When the gate found readable VRM meta (`vrm_licence` is present, whether the
verdict was allowed or refused), the part's `licence_source` is `"vrm"`.
Otherwise — a non-VRM kind, or a `.vrm`/`.astrachar` body whose meta reads
`unknown` — the part's own `[[integration.content]].licence` string (§2.7)
is its whole licence, and `licence_source` is `"declared"`. A part with
neither — no readable VRM meta **and** an absent or empty `licence` — is
refused with `E_CONTENT_LICENCE_UNDECLARED`, naming the path (G5, Part 1
rule 2a's `licence.source = declared` fallback, applied to a GI's own
free-text `licence` field rather than astra-ce's richer structured
declaration form).

#### 2.7.4 The catalogue entry

An entry carries `content[]`, each `{path, kind, title, credit, licence?,
licence_source, sha256, vrm_licence?}` (games-index-v1.md §2.1), and
`content_confirmed`, a `{text_id: version}` map of which confirmation text
each declared part was last confirmed under. **Never an account** — who
confirmed what, and when, is a confirmation record, and confirmation
records live in the plugins service (minice), not in the signed catalogue
document.

### 2.8 Reserved: `[[integration.uses]]`

Not valid in schema 1 — the schema refuses it outright
(`manifest.schema.json`'s `"uses": false`), and `reserved.yaml`'s
`integration_reserved_keys` names it, so shipping it early cannot collide
with what it ends up meaning.

The future shape, not yet specified: `{kind = "character" | "animset", id,
version_req}`, a *reference* to an in-app catalogue item instead of embedded
bytes — the counterpart to §2.7's `[[integration.content]]` for the case
where the asset already exists in Astra and the GI just wants to ask for it
by id and version range, the way a package manifest names a dependency.
Reserving the key now means a schema that specifies it later does not have
to ask "did anyone already ship something under this name, and what did
they mean by it."

## 3. Reserved names and ids

[`spec/games/reserved.yaml`](reserved.yaml) is the **one list** of:

- reserved engine codes (the four built-ins plus the `unknown` sentinel);
- the `astra.`/`minice.` id prefixes and the `Minice`/`Official` name
  substrings reserved to the first-party publisher;
- the profile file names `[[files]]`/`[[config_writes]]` may not place
  (the launcher's own bookkeeping plus the two Link files).

`astra-game-launcher`'s `src/manifest.rs`/`src/engines/` and `gi-probe` each
hold a copy; canary K13 (`dev/couplings.md` in astra-plugins-ops) fails CI the
moment a copy drifts from this file. Do not duplicate the list anywhere else
— point at `reserved.yaml`.

## 4. `gi-probe check`, in one place

Every rule this document states as a refusal (`engine-undeclared`,
`loader-policy-conflict`, `capability-undeclared`, `engine-code-reserved`,
a reserved id or name, a reserved profile file name, a Link limit) is a
`gi-probe check` finding, not a bare TOML-parse error — `gi-probe` links the
launcher's own `manifest.rs` and `descriptor.rs` so there is exactly one
parser for both the launcher and the catalogue's ingest (merged plan §3.2,
lane L; A§5.2 step 5). `testdata/games/manifests/invalid/` holds one golden
per rule, named for the rule it breaks, and `tools/check-games-goldens.py`
(§6 of this repo's CI, see `.github/workflows/ci.yml`'s `games-spec` job)
asserts each one is refused with exactly that code.

§2.7's content-coverage codes (`E_CONTENT_UNDECLARED`, `E_CONTENT_MISSING`,
`E_CONTENT_DUPLICATE`), the VRM gate's `E_CONTENT_LICENCE_REFUSED`,
`E_CONTENT_LICENCE_CONFLICT` (§2.7.3's two-meta disagreement) and
`E_CONTENT_LICENCE_UNDECLARED` (§2.7.3's `licence_source` fallback with
nothing to fall back to), and the flag `F_CONTENT_VRM_META_UNKNOWN` (a
`.vrm`/`.astrachar` body with no readable VRM meta at all — never a
refusal) are the one exception to "gi-probe check finding": the ingest
order (§2.7.1) runs
the content check **before** gi-probe, over the real release zip's bytes,
not the parsed manifest alone — `path` uniqueness is the only part of §2.7
`gi-probe check` can assert from the manifest by itself (`testdata/games/
manifests/valid/content-parts.toml` and `.../invalid/content-kind-not-
allowed.toml`, `.../content-path-traversal.toml` are schema-only goldens for
exactly that reason). The coverage and licence checks need the files
themselves, which is why `testdata/games/content/releases/` pairs a
manifest with real tiny content files instead of living beside the other
manifest goldens; `check-games-goldens.py`'s own Python implementation and
the catalogue's `lib/content.mjs` are independent implementations of the
same rule, each pinned against these same goldens, in the same spirit as
every other semantic rule in this document.

## 5. The author release template

[`templates/gi-release.yml`](../../templates/gi-release.yml) is the GitHub
Actions workflow a third-party author copies into their own repository (never
`uses:`-referenced — unlike `plugin-release.yml`, it is not a reusable
workflow, because a GI's build is not one shape: BepInEx, ReShade, UE4SS, a
bare Lua script). It triggers on a tag push, pins every action by its commit
SHA, builds `astra-gi.zip` in whatever language the integration is written
in, runs `actions/attest-build-provenance` over the finished zip, and
publishes it as the tag's release asset — the one artifact ingest (merged
plan, lane C) will fetch, hash and verify. See the template's own header
comment for what it deliberately does not do (sign, resolve dependencies, or
run `gi-probe` itself — that happens at ingest, against the built artifact,
not inside the author's own CI, where a hostile build could fake a clean
result).
