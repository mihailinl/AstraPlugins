<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# Open points in the content contract (v1)

Every place where the design note (minice
`docs/architecture/2026-11-01-content-catalogue.md`, read at the
`arch-boundaries` worktree on 2026-11-01; `L<n>` is its line) is ambiguous,
silent or contradicts itself, the reading this contract chose, and why. **The
rule for choosing was: the reading that refuses, holds or disarms more.** Each
item names who should confirm it. None blocks building against v1: a later
answer that loosens a rule is a new contract version, never an edit.

## Alarms for other lanes (a defect, not a choice)

**O-2, O-2b, O-2c — CLOSED by AstraPlugins #123, commit `516ba38`**
(`spec/games-vrm-conflict-kindkeys`, astra-plugins-ops-42). The games gate read
only the first VRM meta it found (O-2), treated an unrecognised licence token as
allowed (O-2b), and #120's `allowed.vrm` carried the non-UniVRM token
`Redistribution_Allowed` (O-2c). #123 judges both metas, reads unrecognised
tokens as Unknown, re-cuts `allowed.vrm` with `CC_BY`, and adds goldens for each
case. All 19 of its VRM files give the same verdict through this contract's
function as #123 records for them (ingest-v1.md §4.4, run with a checkout of
`516ba38`).

**O-22. An accepted difference in POLICY, not in verdict.** For games, an
`Unknown` verdict is published, flagged `F_CONTENT_VRM_META_UNKNOWN`
(`spec/games/manifest.md` §2.7.3); for content it is HELD for a moderator
(ingest-v1.md §4.1). The verdict function is identical file for file; only what
each product does with `Unknown` differs, deliberately (coordinator,
2026-11-01).

**O-1. Games keys.** L328–330 moves `games` into `kind_keys` (agreed by -42 on
2026-11-01); `spec/games/games-index-v1.md` §3 still compiles `games-current` /
`games-next` and a per-key serial floor. This contract lists `games` in
`kind_keys` and does not edit the games spec. **Lane C** reconciles §3 of that
spec (and its `key_id` body member, which content documents do not carry —
common-v1.md §1: a `key_id` inside `signed` would be a second, unauthenticated
claim of who signed).

## Readings chosen

| id | L | the note says | v1 reads it as | confirm |
|---|---|---|---|---|
| O-3 | 204, 300 | a pack member must have "an equal digest"; `members[{…,digest}]` — which digest is not said, while `requires[].digest` (L734) is the part digest | `digest` = the member entry's **`artefact.sha256`**. It binds the exact bytes the client installs, it exists for every kind (a command, a multi-part character, a game integration), and a part digest only keys confirmations (L119) | coordinator |
| O-4 | 296 | a command entry carries "the `command` part" | **superseded 2026-11-01**: a command's part is a single-file part, ONE pair whose path is `""` (part-digest-v1.md §2, paths relative to the part root, agreed with astra-companion-5f), as is a `format: vrm` model's body — so neither depends on a name at all | astra-ce (the client computes it) |
| O-5 | 680–683 | five trigger words; "an unknown trigger type is refused" | the client's registry also has node trigger types `reminder` and `calendar_event` (Astra `type_registry.rs`), which map to none of the five. v1 **refuses them** (`E_COMMAND_UNKNOWN_TRIGGER`) rather than invent a word; `event_name` is a closed list (astra-core `trigger.rs` `events`, minus `startup`), so `on_event:timer` exists although a timer is as unattended as a schedule | astra-ce, with the moderation owner (§8) |
| O-6 | 192 vs 195 | format: "the VRM is glTF binary carrying the `VRM` or `VRMC_vrm` extension"; licence: "no VRM licence meta at all → `Unknown`, held, never a refusal" | a **body** with no VRM extension fails format first (`E_CONTENT_FORMAT`); a body WITH the extension and no meta is `Unknown` → held; an accessory `.glb` with no meta is `Unknown` → held. The verdict function's own outcome for PR #120's `unknown-no-meta.vrm` stays `Unknown`, as L201 requires | coordinator |
| O-7 | 193 | the companion importer's archive rules (its `end_record.rs` accepts zip64) | **zip64 is refused** in v1 (`E_ZIP_END_RECORD`): a bundle ≤ 64 MiB with ≤ 4,096 entries never needs it, and every extra end-record shape is one more parser differential | astra-ce |
| O-8 | 566 vs 300 | §11a.4 "every entry of every kind carries `licence` and `credits`"; §5's packs row has neither | **packs carry neither** (nor `parts`, `content_confirmed`): a pack has no bytes but its thumbnail, and a pack-level licence would be a second, unverifiable claim over its members' own; the card shows each member's | owner (via astra-ce, legal) |
| O-9 | 482 vs 195 | the guard list: "the ingest must refuse … a VRM … missing its licence"; §3.3: no meta → `Unknown`, held, never a refusal | "missing its licence" = **meta present with the licence field absent**, refused by the spec default (`vrm-field-absent`); no meta at all is held (`vrm-no-meta`). Both end not-published | coordinator |
| O-10 | 301 | `floor_effect` values for an old client, with no pairing to acts | `floor_effect` is **cumulative** (`no-offer` ⊂ `no-update` ⊂ `disarm`); `security` ⇒ `disarm`, `rights` ⇒ `disarm` (an old client cannot hide one part, and "hidden" must not degrade to "keeps loading"), `retired` ⇒ `no-update` or `disarm`. An unknown `floor_effect` is `disarm` | astra-4c |
| O-11 | 558–559 | "code execution and network access" | execution = `executes_shell`, `runs_code`, **`runs_command`** (it dispatches a saved command not contained in the item — the moderator checklist's own question); network = `opens_urls`, `uses_ai` (the extractor has no other network word). The flag only orders the queue, so over-including costs ordering, never a publish | moderation owner |
| O-12 | 202 | "any action type or node type that is not on the allowlist" | `sub_workflow` IS a `NodeType` but **is refused in v1**: it invokes a workflow the extractor does not resolve and derives nothing for — `run_command`'s laundering shape — so admitting it would let a command's capabilities be whatever the other workflow does | astra-ce |
| O-13 | 336, 347 | "a per-kind `serial` floor"; games keeps a per-KEY floor | the floor is per **(kind, document)** across both keys (a switch to `next` does not reset it); an equal serial with different bytes is refused (`serial-rollback`) | astra-4c |
| O-14 | 663–664 | "the switch is one-way" — said of the signer only | the CLIENT enforces it too, **per document schema** (trust-kind-keys-v1.md §6): after verifying an `astra.<K>.<D>/1` under `next`, it retires K's `current` key id for (K, D) and refuses a later `current`-only (K, D) document (`key-retired`); K's other schema keeps verifying under `current` until its own `next`-signed document is seen. Per kind was the first reading; it is NOT the refusing one for the withdrawn list, where a refusal means withdrawals go dark mid-rotation, so per schema disarms more | astra-4c; per schema: minice-01 (design §11a.9) |
| O-15 | 290–292 | `lift {id, versions, lifts_at}`, with no retention | a lift stays served ≥ 365 days after it was first served; a client offline longer stays disarmed. A lift must match the row's `id`, `versions` AND `at` exactly | coordinator |
| O-16 | 297, 717 | a character's `parts` are "only what the character itself carries"; it requires "its model, its base set and any add-on sets" | parts ⊂ {`character` (a 3D accessory), `art`, `audio`} — never `animations` (those are animsets) or `command`; requires **exactly one model** and **zero or more** animsets (a character on built-in animations requires no set; a `builtin` pack is not an item) | astra-ce |
| O-17 | 659–666 | the kind_keys refusals: alg, role, duplicates, the `not_before` order | ALSO fail closed for the kind: a missing role, a public key that is not 32 bytes, an unparseable `not_before`, `current` = `next`, and a public key that appears under another kind or in `index_keys` (both kinds lose their keys). A row of an unknown kind is ignored | astra-4c |
| O-18 | — | the note names no code for most archive limits, the unknown trigger, the unnamed plugin, nested packs, character requires | coined, in `reason-codes.yaml`: `E_ZIP_END_RECORD`, `E_ARCHIVE_TOO_MANY_ENTRIES`, `E_ARCHIVE_ENCRYPTED`, `E_ARCHIVE_METHOD`, `E_ARCHIVE_LINK`, `E_ARCHIVE_NAME_UNSAFE`, `E_ARCHIVE_TOO_LARGE`, `E_ARCHIVE_RATIO`, `E_ARCHIVE_MUST_BE_STORED`, `E_BUNDLE_MANIFEST`, `E_BUNDLE_FILE_UNLISTED`, `E_BUNDLE_FILE_DIGEST`, `E_CONTENT_DIGEST_MISMATCH`, `E_CONTENT_TOO_LARGE`, `E_CONTENT_QUOTA`, `E_CONTENT_FORMAT`, `E_CONTENT_IMAGE_DIMENSIONS`, `E_CONTENT_MEDIA_TYPE`, `E_CONTENT_PARTS_MISMATCH`, `E_COMMAND_FORMAT`, `E_COMMAND_UNKNOWN_TRIGGER`, `E_COMMAND_PLUGIN_UNNAMED`, `E_PACK_NESTED`, `E_PACK_TOO_MANY_MEMBERS`, `E_PACK_MEMBER_KIND_UNSERVED`, `E_CHARACTER_REQUIRES_UNLISTED`, `E_CHARACTER_REQUIRES_DIGEST`, `E_SERVED_UNVERIFIED`. Lane L2 adds them to `table.rs` (its `tests/reason_codes.rs` count moves) | lane L2 |
| O-20 | 285–288 | the client refuses installs when "its last verified FETCH of `withdrawn/1` is older than 2 h" | **also when the document's own `issued_at` is older than 26 h.** The note's rule alone is defeated by replay: any still-unexpired document (up to 8 days) re-served by a stale gcore cache (`stale: [error, updating]`, CLAUDE.md "the edge lies to the first reader") or a hostile path verifies on a fresh fetch. Cost: a signer outage of more than a day stops installs and updates of content (never use of what is installed), which the withdrawn-age alarm (§10) already pages on | coordinator, astra-4c |
| O-21 | 193, 275 | the companion importer's archive rules; the plugin envelope | three refusals the note does not list, each closing a parser differential: **a duplicate JSON member name** anywhere (documents, command artefacts, `astrachar.json`, glTF JSON); **zip entries that do not tile the file** (a gap, an overlap, prepended data) and a directory entry that carries data; and on the client, **a withdrawn `versions` range it cannot parse covers every version** | coordinator (the ingest copy, L1, must add the first two) |
| O-19 | 203 | "`version_req` must match a listed version" | v1's `version_req` and `versions` grammar is the comparator set `<`, `<=`, `>`, `>=`, `=`, comma-joined, judged by **SemVer §11 precedence, not Cargo `VersionReq`** (common-v1.md §6) — so a pre-release is covered by precedence alone; a caret or tilde range is a later version of this contract | lane L1, astra-4c (a Rust client must not reach for `semver::VersionReq`) |
