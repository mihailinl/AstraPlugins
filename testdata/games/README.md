<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `testdata/games` — the goldens every other lane pins

`vectors.json` is the index: one record per golden, its verdict
(`accept`/`refuse`), and how `tools/check-games-goldens.py` decides that
verdict — `schema` (the JSON Schema in `spec/games/schemas/` alone),
`semantic` (a small named rule the checker runs in addition, because a
JSON Schema cannot express it — an anchor, a disjointness check, a reserved
list membership), or `pinned` (this repository can only assert the golden
*parses*; the real refusal needs a live folder tree, a real zip, or the
signed catalogue's ownership table, which is lane L's or lane C's test to
run against — `vectors.json` names which).

| directory | what | consumed by |
|---|---|---|
| `manifests/{valid,invalid}/` | `astra-gi.toml` goldens | `astra-game-launcher`'s `tests/`, `gi-probe check` |
| `descriptors/builtin/` | the three first-party engines, as `astra.engine/1` | launcher `tests/detect.rs` (K1, K17) |
| `descriptors/hostile/` | one fixture per `dev/game-integrations-launcher-client-plan.md` §3 row that is a descriptor-grammar attack | launcher `tests/corpus/` (K3), `gi-probe validate-descriptor` |
| `index/`, `withdrawn/` | `astra.games.index/1` / `astra.games.withdrawn/1` goldens | the catalogue's ingest/sign validator and the daemon's client verifier (K12) |
| `link/` | a Link v1 transcript plus restricted data-schema goldens | the daemon's Link serde (K10), `astra-link-mock` (0.2.8.x) |

## Using it

`tools/check-games-goldens.py` is the canonical reader; it is what runs in
this repository's CI (`games-spec` job, `.github/workflows/ci.yml`) and
what `astra-game-launcher`/`astra-games-catalogue` are meant to point their
own suites at by this repository's pinned SHA (K17's other half — see that
canary's row in astra-plugins-ops's `dev/couplings.md`).

Every golden's name says what it proves: an `invalid/` manifest is named
for the one rule it breaks, a `hostile/` descriptor is named for the
safety-table row it attacks, and a change to any of them without a
matching change to `vectors.json`'s recorded verdict is exactly the kind of
drift `tools/test_check_games_goldens.py` exists to catch — it mutates a
copy of each golden and asserts the checker's verdict flips.
