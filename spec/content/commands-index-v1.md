<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.commands.index/1`

**Normative.** Source: design note §5 (the `astra.commands.index/1` row),
§11a.4, §11a.9. Envelope, freshness, the base entry fields, `licence` and
`credits` are [`common-v1.md`](common-v1.md) §1–§3; keys are
[`trust-kind-keys-v1.md`](trust-kind-keys-v1.md) (kind `commands`). Schema:
[`schemas/commands-index-v1.schema.json`](schemas/commands-index-v1.schema.json).
Withdrawals: [`commands-withdrawn-v1.md`](commands-withdrawn-v1.md).

## 1. Body

```jsonc
{ "schema": "astra.commands.index/1", "serial": 1798675200,
  "issued_at": 1798675200, "expires_at": 1799280000, "entries": [ /* §2 */ ] }
```

## 2. Entry

The base fields (common-v1.md §3), with `artefact.media_type` =
`application/vnd.astra.command+json` and `artefact.size` ≤ 1 MiB, plus:

| field | note |
|---|---|
| `capabilities` | the SERVER-derived words ([`capabilities-v1.md`](capabilities-v1.md)), sorted and unique (rule `capabilities-sorted`). The client shows its OWN derivation and refuses a claim that differs (`claim-mismatch`) |
| `danger` | `low` \| `high` \| `critical`, derived |
| `platforms` | `windows` \| `linux` \| `macos`, ≥ 1, derived |
| `requires` | `[{kind: "plugin", id, version_req}]` — exactly the `uses_plugin:<id>` words (rule `requires-match-capabilities`) |
| `parts` | exactly ONE part of kind `command` (rule `one-command-part`: the artefact, a single-file part whose one pair has the path `""`), plus any `art` / `audio` part it carries |
| `content_confirmed` | `{text_id: version}`, non-empty (rule `parts-confirmed`) |
| `licence` | **the item declaration** (common-v1.md §3.1.2): the author declares ONE licence for the command at `begin`, `BeginRequest.licence`, and the entry carries the object common-v1.md §3.1.1 maps it to — always `source: declared`, `spec: none`. A command with no declaration is refused at `begin` (`E_CONTENT_LICENCE_UNDECLARED`). Its `command` part itself takes no part declaration (ingest-v1.md §4.3) |
| `credits` | `[]` in v1 (common-v1.md §3.2): a command artefact has no credits member |
| `thumbnail` | absent in v1 (common-v1.md §3.3): a command is one JSON artefact and carries no picture |
| `min_astra` | derived, §5 |

## 3. Client rules specific to commands

- An installed command from the catalogue is saved **disarmed** (`enabled =
  false`) until the user approves it, whatever the artefact says (the client
  plan, Astra `docs/arcs/CATALOGUE_CORE_PLAN.md` §4.8).
- A required plugin that is not installed is shown per plugin, with
  installed yes/no; the command is not armed without it.

## 4. Goldens

`testdata/content/index/commands/valid.json` (six entries; every entry's claim
equals the stdlib derivation of its artefact under `testdata/content/commands/valid/`),
`no-thumbnail` (the same six as a v1 publisher emits them: no `thumbnail`,
`credits: []`, `min_astra` from §5, `licence` the object a declared
`CC-BY-4.0` maps to — each re-derived by the checker), `thumbnail-null`
(refused: absent is not `null`),
the signature goldens (`signed-by-next`, `next-before-not-before`,
`signed-by-models-key`, `signed-by-index-key`, `signed-under-models-domain`,
`tampered-after-signing`) and one golden per rule; `testdata/content/vectors.json`
`index` records each verdict.

## 5. `min_astra`

The publisher derives the entry's `min_astra` from this table and from nothing
else (common-v1.md §3.4):

| format | format version | lowest Astra release |
|---|---|---|
| `portable-command` | 1 | `0.2.8` |

A command artefact carries no version member of its own: its format version
is the version of the shape authority it was accepted under,
[`schemas/portable-command-v1.schema.json`](schemas/portable-command-v1.schema.json)
(ingest-v1.md §6) — `1`.
