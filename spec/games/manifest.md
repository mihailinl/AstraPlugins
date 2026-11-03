<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# The game-integration manifest: `[integration.*]`, schema 1

This is the normative spec for the keys the games Workshop adds to
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

#### 2.6.1 The link digest

The consent digest of a GI's AI-facing surface, carried as `link.digest` in
its catalogue entry (games-index-v1.md §2.1). The catalogue's ingest and
`gi-probe check` compute it by this one rule, and each is tested against
`testdata/games/vectors.json`'s `link.digest` vectors:

1. Take the `[integration.link]` table of the astra-gi.toml **as shipped in
   the release**, parsed as **TOML 1.0** (a file that needs TOML 1.1 syntax,
   or begins with a byte-order mark, is refused as an invalid manifest, so no
   reader computes a digest another reader cannot), **exactly as written**:
   - **A newline inside a multi-line string is LF.** TOML lets a parser
     keep or normalise CRLF there, so the rule fixes it: CRLF becomes LF
     before step 3, and a CRLF checkout gives the same digest as an LF one
     (vectors `crlf`, `crlf-as-lf`).
   - **No default is added** for a key the table leaves out. An absent
     optional key (`skill`, `tools`, `triggers`, `events`) is absent, never
     `false`, `[]` or `null`.
   - Writing a default out explicitly therefore changes the digest. That
     asks the player to consent again, which is the conservative reading:
     no two implementations ever have to agree on what a default is.
2. Map it to JSON: a string stays a string, a boolean a boolean, an array an
   array, a table an object. The table's schema admits nothing else, so no
   number, float or datetime ever reaches the digest.
3. Canonicalise with RFC 8785 (JCS), the same function as every other JCS
   in these specs (`tools/contentlite.py`):
   - members are sorted by their names' UTF-16 code units;
   - strings are UTF-8, escaped only as RFC 8785 requires.
4. `digest` = lowercase hex of SHA-256 over those bytes.

A GI with no `[integration.link]` table has `link: null` and no digest. The
digest covers the table's text only. The bytes of the files it names are
covered separately: `link.skill_digest` covers the skill file, and
`schema_digests` covers every `params`/`data` schema. A client asks for
consent again when any of the three changes.

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

**The other direction is read by bytes, for every file in the release —
declared or not, whatever its name, the manifest alone excepted: that is
`astra-gi.toml` at the release root, and a file of that name in any folder is
judged like every other** (golden `vrm-named-manifest-nested`: a prohibited
VRM saved as `models/astra-gi.toml`) (the content catalogue's
[`ingest-v1.md`](../content/ingest-v1.md) §3 step 10, called as that
contract's own code, `tools/check-content-goldens.py`). A name must never
decide whether a file escapes the gate: three.js and every glTF loader sniff
the magic, so a prohibited avatar shipped as `data/avatar.bin` would load
while the gate never opened it. Each of these is **`E_CONTENT_FORMAT`**:

- a file that begins with the GLB magic `glTF` and is not named `.vrm`,
  `.glb` or `.vrma` (content's `name_matches_magic`; golden `glb-named-bin`).
  Named as one, it is content-typed by the table above, so undeclared it is
  `E_CONTENT_UNDECLARED`, as before;
- a file not named `.gltf` whose bytes are a text glTF by the content
  catalogue's own sniff (`is_gltf_json`: after an optional UTF-8 BOM the
  first non-whitespace byte is `{` and the **top-level** object names an
  `asset` member, read key by key, whether or not the rest parses; golden
  `gltf-named-json`; a nested `asset` key is not one, golden
  `json-nested-asset`);
- a zip that is a content bundle by the content catalogue's own definition —
  its **last** entry is `astrachar.json`, read with content's `walk_zip`, so
  only an archive Astra's importer would open as a bundle counts — and is
  not named `.astrachar` or `.astrapack` (golden `bundle-renamed`). A game's
  own archive (a `.jar`, a mod `.zip`) has no such entry and is not one.
  Named as one, it is judged as §2.7.3 says.

**A game's own archives are opened one level deep.** A zip that is not a
content bundle — a `.jar`, a mod `.zip`, anything that begins with the zip
magic `PK`, whatever it is called — is walked with the content contract's own
`walk_zip`, **every cloaking check included** (ingest-v1.md §3 steps 1–4 and
7: the end record, the headers that must agree, entries that tile the file,
the names, the raw read), under limits made for game archives rather than
content bundles: **65,536 entries and 512 MiB uncompressed**, and no
Stored-only rule, which is a bundle's (golden `jar-5000-entries`, accepted
past content's 4,096). Inside it:

- every GLB, text glTF and bundle is judged **exactly as a top-level file
  is** — the rules above, §2.7.3's format rules, caps and VRM gate, an
  embedded bundle's content verdict — and its glTF JSON counts toward the
  release's 32 MiB (goldens `jar-glb-named-bin`, `jar-vrm-prohibited`);
- each such GLB, `.gltf` or bundle is a **part that must be declared**, with
  the path `<archive path>!<inner path>` — `mods/avatar.jar!assets/avatar.vrm`
  — and is otherwise `E_CONTENT_UNDECLARED` (goldens `jar-vrm-undeclared`,
  `jar-vrm-declared`). The owner's per-part rights checkbox must not be
  bypassable by putting a model in a jar. The manifest schema's `path`
  already admits `!`. Other content-typed files in an archive (a mod's
  textures and sounds) are not parts and need no entry;
- **cloaking is always refused**, with content's own code — an archive that
  shows one reader different entries than another is never published,
  whatever its size (golden `jar-cloaked`). An archive whose reader cannot
  follow it at all is refused `E_CONTENT_FORMAT`. One consequence, stated so
  nobody is surprised: an Android APK signed with scheme v2 or later puts its
  signing block between the last entry and the directory, which is exactly
  the gap a cloaked entry hides in, and is refused;
- **an archive the walk cannot otherwise open is not refused**: past the
  limits, zip64 (which a modpack past 65,535 entries or 4 GiB needs), a
  compression method other than Stored or Deflate, an encrypted or linked
  entry, a name content's rules refuse, a deflate ratio over 100. It
  publishes flagged **`F_CONTENT_ARCHIVE_UNSCANNED`**, shown to moderators
  with the reason, so big modpacks still work (golden `jar-zip64`). A part
  declared inside such an archive cannot be found, and is
  `E_CONTENT_MISSING`;
- **an archive inside an archive is not opened** — one level deep — and is
  flagged `F_CONTENT_ARCHIVE_UNSCANNED` the same (golden `jar-in-jar`:
  Fabric's `META-INF/jars/` and Forge's jar-in-jar nest them).

Three deliberate differences from the content catalogue, because a game
integration ships arbitrary files and a content bundle does not:

- **A text glTF's top-level `asset` is an object.** The content
  catalogue's sniff decides on a top-level `asset` key whatever its value.
  three.js reads `asset.version` and refuses a file without one, so a glTF's
  `asset` is an object; `{"asset": "textures/hero.png", "scale": 2}` is a
  game's data file, and is accepted here (golden `json-asset-string`). The
  C-speed test below looks for the key followed by `{`, so a nested object
  `asset` beside a top-level string one still errs toward refusing.

- **A UTF-16/32 byte-order mark is not refused.** The content catalogue
  refuses one on its text kinds — `.gltf`, `.json` and `.toml` must be UTF-8
  (ingest-v1.md §3 step 10, narrowed by #132; any other entry only when it
  decodes to a glTF) — and a game integration carries UTF-16LE
  localisation `.json` and `.toml` files (golden `localisation-utf16`,
  accepted). Here the mark refuses a `.gltf` alone (§2.7.3). Such a text is instead sniffed **as the
  text it decodes to** — a piece at a time, never the whole file for a test
  of its first character (golden `pak-utf16-bom`: a 32 MiB archive that
  begins `FF FE`, checked within 4 MiB of memory; decoded whole, a 128 MiB
  one cost 658 MB) — so a UTF-16 glTF under another name is still refused
  (golden `gltf-named-json-utf16`). This only ever over-refuses: a browser's
  `fetch().text()` and three.js decode UTF-8 whatever the mark, so such a
  file does not load as a glTF there at all; the margin covers a reader that
  does detect the encoding (Python's `json.loads` on bytes does). The BOM rule applies to glTF candidates
  only: every `.gltf` (§2.7.3).
- **The key-by-key sniff is bounded.** It reads every character in Python
  (about 4 MiB a second on `{"":0,"":0,…}`; twenty such 16 MiB files once
  held the gate for 102 s), so it runs only on a JSON-looking file whose
  bytes name an `asset` key with an object value at all — tested first, at
  C speed; no such key, no glTF (golden `json-many-keys-no-asset`, five such files, accepted within
  5 s) — and it reads at most **64 MiB per release**. Past that budget, a
  JSON-looking file whose bytes name the key is refused unread, as one over
  16 MiB is.
- **Over 16 MiB the key-by-key sniff is not run** — it reads every
  character, and a game's data file may be large. A JSON-looking file (after
  an optional BOM, `{` first) of more than 16 MiB not named `.gltf` is
  refused when its bytes name an `asset` key with an object value at all,
  the key spelt plainly or with `\u` escapes that JSON decodes to the same
  key, and accepted otherwise
  (goldens `json-over-16mib-nested-asset`, refused, and
  `json-over-16mib-plain`, accepted; both built in memory by
  `testdata/games/content/vrm/gen.py`). Nothing that large is a glTF this
  gate would accept anyway (§2.7.3's 16 MiB cap), so the cheap test errs
  only toward refusing.

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
something an author's confirmation can override. **It applies by content,
never by name** (the content catalogue's `ingest-v1.md` §4, so that the two
gates agree on every file): to every declared part whose bytes begin with the
GLB magic `glTF`, whatever it is called, and to every `.gltf` text file, once
the file is classified by the extensions its glTF JSON names in `extensions`
or `extensionsUsed`:

- an **avatar** names `VRM` or `VRMC_vrm` — it gets the verdict below, in any
  part, so a renamed avatar cannot pass as an animation or as art;
- an **animation** names `VRMC_vrm_animation` and no avatar extension — no
  avatar verdict; its part needs the `animations` rights confirmation;
- a **plain** glTF names neither — judged (and so `unknown`, below) only in a
  `character` part, since a character is an avatar whatever its extensions;
  in any other part it is ordinary art.

**Before any of that, every GLB and every `.gltf` — in any part, of any
class — is held to the format rules** (the content catalogue's `ingest-v1.md`
§3 step 10), and a file that breaks one is refused **`E_CONTENT_FORMAT`**:

- **a GLB is whole**: its header's total length equals the file's size, and
  its first chunk is JSON and ends inside the file, so a chunk declared past
  EOF is never read as whatever bytes happen to be there;
- **its glTF JSON parses and names no member twice**: one reader's
  `allowRedistribution: false` is another's `true`, and JSON that does not
  parse must never fall through to "plain", which an animation part does not
  judge. JSON nested so deep that the parser's own stack gives out is JSON
  that does not parse — a refusal, never a crash of the gate (golden
  `gltf-million-deep`, built in memory);
- **the caps, the content catalogue's own** (`gltf_problem`, ingest-v1.md
  §3 steps 5 and 10), each naming the cap it breaks: a GLB JSON chunk or a
  `.gltf` over **16 MiB**, checked from the header or the file's size
  **before** anything is parsed (goldens `glb-json-over-16mib`,
  `gltf-over-16mib`); JSON nested **deeper than 128**, the top-level object
  being depth 1 (goldens `gltf-too-deep`, refused, and `gltf-depth-128`,
  accepted); and more than **32 MiB of glTF JSON in the whole release** —
  every GLB's declared first-chunk length plus every `.gltf`'s size, read
  before any is parsed (golden `gltf-total-over-32mib`: three GLBs of 11 MiB,
  each fine alone). The reason is the server's memory: one release must not
  make it hold a gigabyte of parsed JSON (B1: seven 16 MiB `.gltf` once held
  1.9 GB). These are `E_CONTENT_FORMAT` here; the content catalogue gives
  its archive-wide budget its own `E_ARCHIVE_TOO_LARGE`;
- **a `.gltf` carries no byte-order mark** — UTF-8, UTF-16 or UTF-32: glTF
  2.0 is UTF-8 JSON without one, and a reader that decodes by the mark
  (Python's `json.loads` on bytes) sees a different text from one that does
  not (a browser, three.js) (goldens `gltf-with-bom`,
  `gltf-utf16`). Unlike the content catalogue, which refuses a UTF-16/32
  mark on any entry, this applies to a `.gltf` alone (§2.7.1);
- **no external reference** (the content catalogue's own `uri_refusal`): in
  a GLB every `images[].uri` and `buffers[].uri` is a `data:` URI; in a
  `.gltf` each is a `data:` URI or a plain relative path naming a file the
  release holds, so nothing Astra loads makes it fetch a URL, which would
  tell a third party who is looking at the model. A loader percent-decodes
  the uri (and splits off a query or fragment) **before** it joins it to the
  file's folder, so the uri is judged as the loader reads it: **decoded
  exactly once** — glTF 2.0 encodes a space, and `Base%20Color.bin` names
  `Base Color.bin` (golden `gltf-uri-space-encoded`, accepted) — with no raw
  `?`, `#` or `\`, no malformed escape, nothing still percent-encoded once
  decoded (`%252e%252e/` decodes to `%2e%2e/`, and a second decoding would
  climb out; golden `gltf-uri-double-encoded`), and, decoded, no scheme, no
  `..` and no leading `/`: `..%2f..%2f..%2f..%2fetc%2fpasswd` leaves the
  release once decoded even when a file with that literal name sits beside
  the `.gltf` (golden `gltf-uri-percent`, the content catalogue's `pct`, N2;
  its code is pinned, not content's wording). `images` and `buffers` must be
  arrays of objects: a JavaScript loader indexes an object's `"0"` key as
  `images[0]`. The content catalogue's further rule — the uri resolves
  inside the `.gltf`'s own part — has no equivalent here: a game
  integration's part is one file, and the buffer it names is not a part of
  its own.

**A `.astrachar` or `.astrapack` part is judged whole, by the content
contract's own code** — `ingest_bundle` in `tools/check-content-goldens.py`,
never a second reading of it: `walk_zip` and [`ingest-v1.md`](../content/ingest-v1.md)
§3 steps 1–8 (the end record, the entry count, the headers and the cloaking
probes, the names, the sizes and the 32 MiB budget, Stored-only types, the
raw read, the manifest and its digests), step 10 (every GLB and `.gltf` in
it, by the rules above), step 11 (the licence verdict on **every** GLB and
`.gltf` in it, not only the body) and step 12's rule that every file is in
exactly one part. Two steps have nothing to run on here: step 9 is the
server's blocklist, which this gate does not hold, and step 12's
parts-mismatch half compares declared part digests, which a game
integration does not declare. A refusal **refuses the release with
content's own code** (`E_ZIP_HEADERS_INCONSISTENT`, `E_BUNDLE_MANIFEST`,
`E_CONTENT_LICENCE_REFUSED`, …), its detail content's, prefixed
`<gi path>!` so that a per-file refusal reads `<gi path>!<inner path>`
(goldens `bundle-vrm-redistribution-prohibited`,
`bundle-glb-prohibited-beside-allowed-body`, `bundle-vrm-metas-disagree`,
`bundle-gap-between-entries` — the content catalogue's own hostile bundles,
byte for byte, which `gen.py --check` keeps equal to `testdata/content/`). An
`astrachar.json` that is not an object is content's own `E_BUNDLE_MANIFEST`
(since #131; before it, content's reader raised on one); any bundle shape
that reader still raises on instead of refusing is refused
`E_CONTENT_FORMAT` here, never a crash. **A bundle is unzipped once, and its glTF JSON counts toward
the release's 32 MiB** (§2.7.3's caps): the sum of its GLB chunk lengths and
`.gltf` sizes, from the walk's headers, is charged before anything in it is
parsed, and the bundle that would take the release past 32 MiB is refused
`E_CONTENT_FORMAT` unparsed (golden `bundle-gltf-total-over-32mib`: three
bundles of 11 MiB each; four of 32 MiB once cost 787 MB and 31 s, and were
accepted). The part's declared `licence` stands for every part of the
bundle (content's `declared_licence`); without one, each part needs its own
allowed VRM meta (golden `bundle-audio-licence-undeclared`, refused by
content's step 11; `bundle-model-aiko`, accepted with `licence_source =
"vrm"` from its body; `bundle-animset-wave`, accepted on its declared
licence). This replaces the earlier reading of the body alone, which passed
an unreadable bundle as a gap (`F_CONTENT_ASTRACHAR_UNREADABLE`) and never
opened its accessories: an unreadable bundle is now what the content
catalogue says it is, a refusal.

The gate parses the file's GLB container (the 12-byte header, then the first
chunk if it is typed `JSON`), or a `.gltf` file's whole text, and reads each
VRM meta present. Each meta gives two readings, exactly as astra-companion's
`src/vrm/meta.rs` (`licence_of`, `redistribution_of`, origin/main `045b0bf`)
and the content catalogue's `ingest-v1.md` §4.2 read them:

| | value | reading |
|---|---|---|
| VRM 1.0 `allowRedistribution` | `true` | allowed |
| | `false`, absent, or not a bool (the string `"true"` included) | prohibited |
| VRM 0.x `licenseName` | `CC0`, or any token beginning `CC_` | allowed |
| | `Redistribution_Prohibited`, absent, or not a string | prohibited |
| | `Other`, or **any other token** | **unknown** (the terms are elsewhere) |
| VRM 1.0 `avatarPermission` / VRM 0.x `allowedUserName` | `everyone` / `Everyone` | allowed |
| | `onlyAuthor`, `onlySeparatelyLicensedPerson` / `OnlyAuthor`, `ExplicitlyLicensedPerson` (named people only, D8 widened), absent, or not a string | prohibited |
| | **any other token** | **unknown** |

A meta's verdict is **prohibited** if either reading is, else **unknown** if
either is, else **allowed**. **An unrecognised token is never allowed.** A
prohibited verdict is refused with `E_CONTENT_LICENCE_REFUSED`, naming the
field and its value (the redistribution field first).

**A file carrying BOTH blocks is judged on both, never only the first one
found** (O-2 — the games gate and this document both used to stop at
`extensions.VRM.meta` when present and never look at `extensions.VRMC_vrm.meta`
at all, so a file whose VRM 0.x meta allowed and whose VRM 1.0 meta prohibited
passed outright). The content catalogue's own contract states the same rule
for the same reason (`ingest-v1.md` §4.2 — "A file carrying BOTH metas is
judged on both. If they disagree → `E_CONTENT_LICENCE_CONFLICT`"); here, that
means the rule above runs once per meta (each spec reading its own absent-field
default below, independently), and the file is refused
**`E_CONTENT_LICENCE_CONFLICT`**, naming both verdicts, whenever the two
verdicts differ — an unknown against an allowed included. The usage flags
(G5, below) are display and are never compared, exactly as the content gate
does not compare them.

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

**`unknown`: no readable meta, or a meta whose verdict is unknown.** A file
the gate judges (above) that carries no `extensions.VRM.meta` and no
`extensions.VRMC_vrm.meta` block — not every `.vrm` has one — or whose meta
reads unknown (an unrecognised licence or permission token) is neither
refused nor passed silently: it is flagged `F_CONTENT_VRM_META_UNKNOWN`, its
meta is not used as the part's licence (`vrm_licence` is absent), and it
reaches the release's confirmation step only via §2.7.3's `licence_source`
fallback below (G4: "`unknown` passes only with the character checkbox and
the licence line beside it", which is the publish form's job, not this
gate's).

The verdict is the content catalogue's, file for file; only what follows an
`unknown` differs, and on purpose. The content catalogue holds an `unknown`
for a moderator (`ingest-v1.md` §4.1). This catalogue publishes it flagged,
under the publish-at-once rule every community release follows, because a
GI's part always carries the author's declared licence (`licence_source =
"declared"`, or `E_CONTENT_LICENCE_UNDECLARED`) and the per-part rights
confirmation (`W_CONTENT_UNCONFIRMED` until it is given). **The same holds
inside an embedded bundle**: where `ingest_bundle` returns the content
catalogue's `held` with `F_CONTENT_VRM_META_UNKNOWN`, this gate publishes the
release flagged `F_CONTENT_VRM_META_UNKNOWN` on the bundle's path (golden
`bundle-vrm0-licence-other`), and only with the part's declared licence —
without it, `E_CONTENT_LICENCE_UNDECLARED`.

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

**Reserved: CSAM hash matching — `W_CONTENT_CSAM_PENDING`,
`F_CONTENT_CSAM_UNSCANNED`.** The owner made CSAM hash matching a gate on
content publishing (2026-11-01; the content contract's `ingest-v1.md` §1),
and it applies to a game integration's images too, which would otherwise
bypass it (astra-plugins-ops `dev/game-integrations-lane-c-minice-design.md`
§1.6a). **The plugins service scans every image of a GI release** — a
declared `art` part, a texture inside a GLB or `.gltf` (a bufferView, a
`data:` uri or a relative file) and every image inside an embedded
`.astrachar`/`.astrapack` — with minice's own extractor and scanner, after
the rights gate and before the release is leased for signing. **This
checker never does, and neither does the catalogue's public Actions run**:
neither holds a scanner key, and "every image" is defined once, by that
extractor, not a second time here. The two codes are reserved so that no
other rule takes them:

| code | class | meaning |
|---|---|---|
| `W_CONTENT_CSAM_PENDING` | wait | the release has at least one image and no scanner is configured yet; it clears by itself once one is. A wait, not a refusal, because a release is a tag the author cannot cheaply re-cut. A release with no image publishes as it always did |
| `F_CONTENT_CSAM_UNSCANNED` | held | a scan errored, timed out or met an image it could not decode; nothing is published unscanned |

A match is not a code of this gate: the service quarantines the release
and blocks the publisher, as for content.

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
`E_CONTENT_LICENCE_CONFLICT` (§2.7.3's two-meta disagreement),
`E_CONTENT_FORMAT` (§2.7.3's whole-GLB, duplicate-member and external-reference
rules) and `E_CONTENT_LICENCE_UNDECLARED` (§2.7.3's `licence_source` fallback
with nothing to fall back to), and the flag `F_CONTENT_VRM_META_UNKNOWN` (a
judged glTF with no readable VRM meta, or an unrecognised token — never a
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
