<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `spec/content` — the content catalogue contract (lane L0)

User-published **commands**, **characters**, **models**, **animsets** and
**packs**: the signed documents the minice plugins service serves, the
registry signer signs and the Astra client verifies. This is lane L0 of minice
`docs/architecture/2026-11-01-content-catalogue.md` §10 — the decision record;
nothing here re-decides it. The server (L1/L2), the signer (L4) and the client
(L8) build and test against these files by this repository's SHA.

| file | what |
|---|---|
| [`common-v1.md`](common-v1.md) | what every kind shares: the envelope, freshness, base entry fields, `licence`, `credits`, the withdrawn document, acts, cascades, the client's refusal tokens |
| [`commands-index-v1.md`](commands-index-v1.md) · [`commands-withdrawn-v1.md`](commands-withdrawn-v1.md) | `astra.commands.{index,withdrawn}/1` |
| [`characters-index-v1.md`](characters-index-v1.md) · [`characters-withdrawn-v1.md`](characters-withdrawn-v1.md) | `astra.characters.{index,withdrawn}/1` |
| [`models-index-v1.md`](models-index-v1.md) · [`models-withdrawn-v1.md`](models-withdrawn-v1.md) | `astra.models.{index,withdrawn}/1` |
| [`animsets-index-v1.md`](animsets-index-v1.md) · [`animsets-withdrawn-v1.md`](animsets-withdrawn-v1.md) | `astra.animsets.{index,withdrawn}/1` |
| [`packs-index-v1.md`](packs-index-v1.md) · [`packs-withdrawn-v1.md`](packs-withdrawn-v1.md) | `astra.packs.{index,withdrawn}/1` |
| [`trust-kind-keys-v1.md`](trust-kind-keys-v1.md) | `trust.json`'s `kind_keys`, the signed domain per kind, freshness, the 2 h withdrawn bound, sticky `security` and `lift` |
| [`part-digest-v1.md`](part-digest-v1.md) | the part digest, with both golden vectors |
| [`capabilities-v1.md`](capabilities-v1.md) | the closed command extractor: action, node and trigger types, the five trigger words, `F_COMMAND_EXEC_AND_NETWORK` |
| [`ingest-v1.md`](ingest-v1.md) | what the server refuses, in which order, with which code; the VRM licence verdict |
| [`reason-codes.yaml`](reason-codes.yaml) | every code and client token, hand-parsed |
| [`OPEN.md`](OPEN.md) | where the design note is ambiguous, and the reading chosen — **read it before you build** |
| `schemas/` | **GENERATED** by `tools/gen-content-schemas.py`; never hand-edit |

## Checks

```bash
python3 tools/gen-content-schemas.py --check     # schemas/ is what the generator writes
python3 testdata/content/gen.py --check          # every golden byte, and SHA256SUMS
python3 tools/check-content-goldens.py           # every golden's verdict, from its bytes
python3 tools/test_check_content_goldens.py -v   # the checker's rules are not trivially green
python3 tools/test_schemalite.py -v              # schemas use only the keywords schemalite checks
```

All five run in the `content-spec` CI job and install nothing.
