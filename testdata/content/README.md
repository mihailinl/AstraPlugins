<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `testdata/content` — the goldens the server, the signer and the client pin

**Everything here except this file, `vectors.json` and `gen.py` is GENERATED
by `gen.py`** — deterministic, re-run it and commit both; never hand-edit a
golden. `SHA256SUMS` records every generated file, and `gen.py --check` fails
on any byte that moved.

**The verdicts are not in the generator.** `vectors.json` states by hand what
each golden must be — `accept`, `held`, or refused with which code — and
`tools/check-content-goldens.py` derives the verdict from the bytes and
compares. A generator bug turns the checker red instead of agreeing with
itself.

Every envelope is really signed (Ed25519, `tools/contentlite.py`) with
**published TEST keys** whose seeds are `contentlite.test_seed(<key id>)`. The
TEST root that signs `trust/trust.json` has public key
`IGzxwzZlVZl+I5OBxofWXuaRV7DX7F1AYVomAKKcuio=`. Trusting any of these keys
outside a test is a bug. The goldens' clock is `vectors.json` `now`
(1798675200, 2026-12-31T00:00:00Z) unless a record says otherwise.

| directory | what | consumed by |
|---|---|---|
| `part-digest/` | both part-digest vectors as files, and their exact JCS bytes | the server's ingest, the engine's `part_digest.rs`, the client |
| `trust/` | a TEST `trust.json` with `kind_keys`, and `kind-keys/` variants each costing a named kind its keys | the client's trust parser (L8), the root ceremony's self-check (L4) |
| `index/<kind>/`, `withdrawn/<kind>/` | `valid.json`, one golden per schema or semantic rule, the signature goldens, the served states the scenarios use, the sticky sequence | the publisher (`plugins-server/src/publisher/`), the signer, the client verifier |
| `commands/{valid,hostile}/` | `CommandDefinition` artefacts | the shared extractor's tests on both sides (`catalogue_facts`) |
| `archives/{valid,hostile}/` | `.astrachar` / `.astrapack` bundles: the design note's §10 hostile list | `plugins-ingest` (L1) |

`vectors.json` fields: `verdict` (`accept` \| `held` \| `refuse`); `check`
(`schema`, `semantic` with the one `rule` that refuses it, `signature` with the
client `reason`); `code` and `flags` for an ingest; `claim` for a command (what
the uploader declared); `blocklist` / `declared_licence` for a bundle's ingest
context; `animset` for the `clips` and `states` an animset bundle's entry
must carry; `derive` on an index golden — `{members, item_licence?,
declared_licence?}` — for the entry members the checker re-derives from the
entry's artefact (found among the valid goldens by its sha256) and compares:
`min_astra`, `credits`, `thumbnail` (derived `null` = the member absent),
`licence`, and an animset's `clips`, `states` and `dimension`;
`declared_licence.item[]` for the item's own declaration at `begin`;
`scenarios[]` for several documents judged together (a
`one-way-switch` sequence offers each file to the verifier its directory names,
`index` or `withdrawn`, because key retirement is per schema and its scope is
that verifier's domain constant, never the body's `schema`);
`external[]` for
goldens other PRs commit (#123's VRM files, `516ba38`; #122's cloaking probes), referenced
by path and sha256 and never copied — the checker RUNS each one whose file is
present with that sha256 and says so for each it skips (`CONTENT_EXTERNAL_ROOT`
points it at another checkout).

Two guards keep the corpus from being gutted into a green run: every path in
`SHA256SUMS` must be named by at least one vector, and `expected_checks` pins
the exact number of checks the run makes (externals excluded) — adding or
removing a vector moves it, on purpose. `l1_only` lists each ingest code that
has no golden here, with the reason only lane L1 can test it; a code with
neither is a red run. A command's `claim.requires` carries each plugin's
`version_req`, and `served_plugins` its listed versions and revocation WINDOWS
(ranges).
