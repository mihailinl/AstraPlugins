<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.engine/1`: the engine descriptor

**Normative** for every client that evaluates a descriptor: `astra-game-launcher`
(`src/engines/{descriptor,eval}.rs`, `src/detect.rs`), `gi-probe validate-descriptor`,
and the catalogue's own ingest lint. Where this document and the shipped
launcher disagree, canaries K1-K3 and K17 are how that is caught — see
`dev/game-integrations-plan-merged.md` §3.3 — and the launcher wins until one
of the two is fixed. Source: `dev/game-integrations-launcher-client-plan.md`
§1 ("Descriptor schema `astra.engine/1`") and §3 ("Safety"), as narrowed by
`dev/game-integrations-plan-merged.md` §2.1 and §1 row R1-R9.

## 0. Five rules that hold everywhere below

1. **Narrow-only.** A descriptor can only fill in a game no built-in rule
   recognised (§3). It can never take, hide or ambiguate a game Pass A
   (Unity, Unreal, Godot) already decided, and never widen what a moderated
   descriptor already matched (§3, "Conflicts").
2. **A literal anchor is mandatory.** Every rule has exactly one anchor — a
   top-level `require` lookup with no wildcard in its resolved name (§2.4).
   No anchor, no rule.
3. **Bounds are counted, never timed.** Every limit in §4 is a count — of
   lookups, rules, bytes, probes — never a duration. A budget exhausted
   evaluates identically on a laptop from 2015 and a workstation from 2026;
   a wall-clock timeout would not.
4. **Every lookup names its listing.** `listed` and `child` are answered from
   exactly one of two directory listings, `walk` or `folder` (§2.3) —
   whichever the evaluation context says — and a descriptor cannot choose
   the other one. `stat` never consults either; it is a direct filesystem
   call.
5. **An unknown `schema` or field skips only that descriptor.** A descriptor
   this client does not understand yields no match and raises one banner;
   it never stops evaluation of the other descriptors in the same document,
   and it is never a reason to refuse the whole catalogue (merged plan §1,
   row R4).

## 1. Identity and digest

- **Where it lives.** Inline in the signed `astra.games.index/1` entry, as
  JCS JSON (`games-index-v1.md` §2, field `descriptor`). Inside a foundation's
  own zip, the same object sits under `[integration.engine]`
  (`manifest.md` §2.1); `astra-game-launcher` v0.3.1 drops it unread (no
  `deny_unknown_fields` inside `[integration]`), and the install ledger keeps
  the manifest verbatim regardless.
- **Digest.** `sha256(JCS(parsed))`. Floats and datetimes inside the
  descriptor are refused outright — JCS has no canonical float
  representation, so a descriptor that needed one could not have a stable
  digest. The catalogue's `descriptor_sha256` field (`games-index-v1.md`)
  must equal this digest; a zip whose `[integration.engine]` digest disagrees
  with the catalogue's copy is `descriptor-mismatch`.
- **Built-ins.** The three first-party engines (Unity, Unreal, Godot) are
  compiled TOML under `src/engines/builtin/*.toml` in the launcher
  (`include_str!`), not fetched from any catalogue — see
  `testdata/games/descriptors/builtin/` for the exact goldens this document
  pins, copied verbatim from `dev/game-integrations-launcher-client-plan.md`
  §1.
- **`deny_unknown_fields` everywhere.** At every nesting level. An unknown
  top-level `schema` value (not the literal string `"astra.engine/1"`) skips
  the whole descriptor (rule 5 above).

## 2. Grammar

### 2.1 Codes and display names

- **Pattern:** `^[a-z][a-z0-9-]{1,31}$`, after folding `_` to `-` and a
  Unicode confusables fold. At most 4 codes per descriptor
  (`[engine].codes` is a map of code → display name; see the Unity example,
  which declares two).
- **Reserved codes:** the built-in four plus the sentinel `unknown` —
  `spec/games/reserved.yaml`, `engine_codes`. A descriptor that declares a
  reserved code is refused at ingest with `engine-code-reserved`; this is an
  ingest-time refusal, not a client-side evaluation rule, because a client
  that already has the descriptor installed must still be able to evaluate
  it against the folder it is bound to.
- **Display names:** at most 48 printable characters; no `Bidi_Control`, no
  `Default_Ignorable`, no `·` or `|`; never a built-in engine's display name
  and never a tier phrase ("Reviewed", "Moderated", …) — those are catalogue
  metadata, not something a descriptor author gets to claim for themselves.

### 2.2 `programs`: which files are candidates

One of:
- `{ ext = [...], at?, also_if?, skip_dirs?, first?, skip_wrappers? }` —
  candidates are files under `at` (relative to the game root; `""` means the
  top level) whose extension is in `ext`. `first` caps how many candidates
  Pass B inspects (mandatory, ≤8); `also_if = { dir = "..." }` additionally
  requires a sibling directory to exist before a file is even considered a
  candidate; `skip_dirs` excludes named subdirectories from the walk (e.g.
  `["Engine"]`, so Unreal's own `Engine/Binaries` tree is never itself
  mistaken for the game); `skip_wrappers` (default `true` in Pass B) skips
  launcher/updater-shaped wrapper executables.
- `{ suffix = "...", at?, ... }` — same, matched by filename suffix (Unreal's
  `-win64-shipping.exe`) instead of extension.
- `"none"` — the rule needs no candidate program at all (used only by
  `also_if`-style structural checks that never run in Pass B, which always
  needs a program to anchor its evidence to).

**Pass B** (community descriptors) additionally requires every candidate to
be `exe`/`x86_64`/`x86` or extension-less, confirmed by a PE or ELF magic
number read from the file itself — never trusted from the name alone — and
every wrapper-shaped candidate is skipped regardless of `skip_wrappers`:
`skip_wrappers = false` is a first-party-only knob (§2.6), because turning it
off is exactly the kind of "match anything that merely runs" rule the lint
(§4) exists to catch in a community submission.

### 2.3 Lookups and listings

| lookup | reads | case |
|---|---|---|
| `listed` | exact match, then falls back to an ASCII-case-insensitive match | effectively insensitive |
| `child` | `read_dir`, case-insensitive | insensitive |
| `stat` | `symlink_metadata` on an exact path | exact |

`listed` and `child` never consult the filesystem directly — they read from
one of two listings the evaluator already holds for this pass:

- **`walk`** — breadth-first, sorted, capped at 5,000 entries and depth 4.
  This is the listing a rule's `programs` candidate search runs against.
- **`folder`** — one fresh, uncapped `read_dir`, truncated *before* sorting.
  This is the listing a **hint** (the exe Steam itself suggests), a
  `bootstrap` lookup, or `engine_of_exe_with` consults — contexts that
  already know which single folder they care about and do not need the
  walk's breadth.

A rule never gets to pick which of the two serves a given `listed`/`child` —
the evaluation context decides, by rule 4 above. `stat` is always a direct
call, outside both listings, and `listed` never resolves a candidate named
like a wrapper (§2.2).

`kind` (`file` or `dir`) is mandatory on every `listed`/`child`/`stat` entry.

### 2.4 Requirements: `any` / `all` / `none`, and the anchor

```toml
require = [
  { listed = "engine2.dll", kind = "file" },              # the literal anchor
  { child  = "{project}/core", kind = "dir", as = "core" },
]
```

- `require` is a flat list of lookups (optionally wrapped in `any`/`all`/
  `none`, nestable to depth 3) that must **all** hold for the rule to match.
- `as = "..."` captures a matched path into a placeholder usable by later
  entries and by `evidence`/`version`.
- **The anchor.** Exactly one top-level entry (never one nested inside `any`/
  `all`/`none`) is this rule's anchor: a `listed` lookup whose name, after
  substituting `{stem}`/`{program}`/`{project}`/`{project.leaf}`/
  `{project.parent}`, carries **no** `*` wildcard — one literal name, such as
  `engine2.dll` above or `{stem}_Data` in the Unity rule below (the
  substitution is per-candidate; the *pattern* itself is literal). It must
  not itself be a program file, and it must not be a ubiquitous runtime name
  every exe's folder carries — `steam_api*.dll`, `steam_api64.dll`,
  `vcruntime*.dll`, `d3dcompiler_*.dll`, `msvcp*.dll`. The lint (§4) refuses
  a descriptor whose anchor is one of these outright. The anchor is both the
  O(1) prefilter key (a folder is even considered a candidate for a rule only
  once its listing contains something matching the anchor) and the index key
  descriptors are grouped by.
- **Placeholders:** `{dir} {name} {stem} {program} {project} {project.leaf}
  {project.parent} {pak}`.

### 2.5 Content probes: `head` and `tail`

- **`head`:** at most 4 KiB read from at most 3 named files, matched against
  a version template of the shape `N{1,4}.N{1,2}.N{1,3}[abfpx]N{1,3}`
  (1-4 digits, dot, 1-2 digits, dot, 1-3 digits, an optional single
  flavour letter, 1-3 digits) that never starts immediately after another
  digit. Read only when the rule's own code is not `unknown`.
- **`tail`:** at most 16 bytes from the end of one named file, with a
  `min_len` floor and an `equals` literal (Godot's weak rule reads the last
  4 bytes of the candidate program itself and checks for `GDPC`).

### 2.6 Outputs and tiers

Every rule produces: `code`, `confidence` (`high`/`low`), `binary`
(`"windows"`, `"linux"`, `"by-ext"`, or `{ from_name, map }` — Unreal's weak
120 derives the platform from a `.pak` file's own name suffix), `evidence`
(one captured path, never the bare game root), `passes` (whether a
fallback/weak rule is still allowed to run after a stronger one already
matched), `named_alike` (whether the display name should echo the matched
project/stem), and, only on the rule that owns version extraction, `version`
(the `head`/`tail` extractor plus an optional `versions` range such as
`"<6000.3"`).

**Tiers**, tried in order: `strong` → `strong-fallback` → `weak`. First-party
descriptors only may additionally use `weak_order` (an explicit tie-break
among weak rules), `walk.list_at_limit` (naming specific subdirectories
whose listing is always fetched even past the walk's entry cap — Unreal's
`Binaries/Win64`), `scope = "anywhere"` (search the whole walk rather than a
program-relative subtree), and exemption from both the anchor rule (§2.4)
and the sizing bound (§4) — a first-party weak rule such as Unreal's 110/120
is allowed to be broad precisely because it ships compiled, reviewed, and
held to C1/C1b on every launcher release; a community descriptor gets none
of these four.

### 2.7 Scoped additions

- **`wrappers`** — rules of this kind affect only this descriptor's own
  candidate filtering; they can never exempt another descriptor's candidates
  from being treated as a wrapper.
- **`anti_cheat`** — markers a descriptor may add are scoped to its own
  claims only; they compose additively with every other signal
  (`games-index-v1.md` §5) and can never remove one.

## 3. Evaluation

1. **Pass A** runs the four built-in engines, in today's order, against the
   `walk` listing.
2. **Pass B** runs only when Pass A's answer for a program is `unknown` **with
   no evidence and no hint used**. This specifically excludes the case where
   Pass A found a Unity player whose data folder names neither Mono nor
   IL2CPP (that is still `unknown`, but with `evidence` and `passes: true`)
   and specifically admits the case where no engine's one-program fallback
   found anything at all (`evidence: None`). This is rule 1 (narrow-only)
   made precise: Pass B never gets a second opinion on a game Pass A already
   placed, even tentatively.
3. **Admission into Pass B:** at most 64 descriptors total, at most 4 per
   publisher. Descriptors are tried moderated, then unchecked, then local.
   A hint (Steam's own launch suggestion) uses the `folder` listing and
   skips the walk's prefilter.
4. **Conflicts**, broken in this order: moderation tier (a moderated
   descriptor beats an unchecked one) → hint match → rule tier
   (`strong` > `strong-fallback` > `weak`) → `best()`'s existing tie-break.
   An unchecked descriptor's match **never** replaces or ambiguates a
   moderated one. Otherwise, a genuine tie between two descriptors of the
   same tier yields `engine-ambiguous{codes}` with nothing preselected — the
   user picks.
5. **`anti_cheat`** is the union of Pass A's base-walk markers, every
   descriptor's own scoped `anti_cheat` additions, and the signed catalogue
   marker table (`games-index-v1.md` §5) — see that document for the full
   signal list, which also includes a system kernel anti-cheat service and
   Steam's own disclosure.

## 4. Budgets (safety bound, B§3 "Slow detection")

| scope | bound |
|---|---|
| per descriptor | ≤16 KiB serialized size, ≤16 rules, ≤8 checks, ≤64 lookups, ≤8 content probes |
| per game (whole scan) | ≤1,024 lookups, ≤64 KiB read, ≤4 Pass-B version extractions |

Exceeding **any** bound makes that descriptor yield nothing for that game —
never a partial result, never a hang, and never a reason to stop evaluating
the other descriptors. There is no "partial scan" state (the earlier
marketplace plan's A§6 proposed one; the merged plan drops it — row R7).
`read_dir` results are memoised per folder across every descriptor in the
same scan, and the launcher's cache key is `(folder mtime, Steam buildid,
catalogue serial, descriptor digest)` — an implementation detail, not
normative, kept here only so a client author knows what re-evaluates a
descriptor and what does not.

## 5. Lint (`gi-probe validate-descriptor`)

A descriptor that parses may still be refused before it ever reaches a
moderator:

- **No anchor, or an anchor that is a program file or a ubiquitous runtime
  name** (§2.4) → `descriptor-anchor-invalid`.
- **`E_DESCRIPTOR_TOO_BROAD`** — the descriptor matches any negative fixture
  (an empty folder, an exe-only folder, a folder of bare system DLLs,
  `steam_api64.dll` plus a bare exe) or matches corpus folders labelled with
  two or more different engines. This is a mechanical check against the
  fixture corpus (`testdata/games/descriptors/hostile/`), never a moderator
  judgement call.
- **A reserved or already-owned code** → `engine-code-reserved` /
  `engine-code-taken` (ingest-time; §2.1).

## 6. Schema

[`schemas/engine-descriptor-v1.schema.json`](schemas/engine-descriptor-v1.schema.json)
validates the structural shape above (`deny_unknown_fields` at every level,
via `additionalProperties: false`). It cannot express the anchor rule, the
budget bounds, or `E_DESCRIPTOR_TOO_BROAD` — those are evaluation-time facts
about a specific folder tree, not shapes a schema validator sees — so
`tools/check-games-goldens.py` (§6 of `manifest.md`'s sibling tooling note;
see this repo's CI) checks the schema and the hostile-fixture goldens as two
separate passes over `testdata/games/descriptors/`.
