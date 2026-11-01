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
| `key_id` | `"games-current"` or `"games-next"` (§3) |

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
  "notes": { "en": "First release.", "ru": "Первый релиз." }
}
```

| field | note |
|---|---|
| `publisher` | the **bound** identity (`{account, repo_id, repo_owner_id}`), set at the first ingest and unchanged by later releases; compared against `source` on every update to detect `changed_hands` (R20, A§4.1) |
| `source` | **this release's** provenance, re-verified every ingest; identical shape to `publisher`'s two ids so the comparison is a plain equality check |
| `target` | present for a game-specific entry (`store`, `id`, `exe`) or a foundation/runner (`exe = "*"`, no `store`/`id`); a **non-owning** foundation sharing an already-claimed engine code sets `target.engine = "<code>"` here, mirroring its manifest's `[target].engine` (manifest.md §2.1, "Many foundations, one owner") |
| `descriptor` / `descriptor_sha256` | present **only** on the entry that owns an engine code: the inline `astra.engine/1` JCS object and its digest (engine-descriptor-v1.md §1) |
| `foundation` | the mirrored `[integration.foundation]` claim (manifest.md §2.4); `offers.rs` also reads `foundation.engine` to match an exe-less game-specific GI to its engine, generalising the pre-marketplace `pins.rs:571-578` check |
| `built_on` | computed by ingest from digests, never trusted from the manifest's claim alone; `verified` is true only on a full file-set match |
| `engine_versions` | a **foundation's own** declared support range (e.g. `"<6000.3"`), replacing the earlier plan's `versions` on the descriptor itself (R8) — detection and support are different owners |
| `capabilities` | replaces the earlier `uses_avatar` boolean; `v1`'s only value is `"companion.presentation"` |
| `review` | `"unchecked"` \| `"source_reviewed"`. The client derives the UI tier and Provenance badge from this plus first-party-list membership; this document states only the fact, never the wording (R19) |
| `notes` | per-locale release notes, replacing free-text "what's new"; a locale a client does not have falls back to `en` |

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

Two compiled Ed25519 key ids, `games-current` and `games-next`, generated
once by an agent into `/mnt/Storage/Minice/Keys/games-{current,next}.ed25519`
(0600, never printed; CLAUDE.md §3) — no owner ceremony. Each key id keeps
its **own** serial floor. The first document a client verifies under
`games-next` retires `games-current` on that client permanently, so a forged
`serial` replayed under the (now-compromised) `current` key cannot hold back
`next`. A later client release compiles a fresh `next` after a ratchet.

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
