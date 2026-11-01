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
