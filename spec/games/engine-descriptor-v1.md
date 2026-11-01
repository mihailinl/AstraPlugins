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
   row R4). The one narrower case is inside the optional `mods` table: an
   error there drops only `mods`, never the descriptor's detection (§7.1).

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
  the whole descriptor (rule 5 above). Inside `mods` an unknown field voids
  only `mods` (§7.9); `mods` itself is part of the canonical form, so of the
  digest and the 16 KiB bound (§4).

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
6. **`mods`** takes no part in any step above (§7.1).

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

`mods` has budgets of its own (§7.8). A mods evaluation draws nothing from
the bounds above, and detection draws nothing from those.

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
- **Anything wrong inside `mods`** → `mods-invalid` with `field` and
  `reason` (§7.9).

## 6. Schema

[`schemas/engine-descriptor-v1.schema.json`](schemas/engine-descriptor-v1.schema.json)
validates the structural shape above (`deny_unknown_fields` at every level,
via `additionalProperties: false`). It cannot express the anchor rule, the
budget bounds, or `E_DESCRIPTOR_TOO_BROAD` — those are evaluation-time facts
about a specific folder tree, not shapes a schema validator sees — so
`tools/check-games-goldens.py` (§6 of `manifest.md`'s sibling tooling note;
see this repo's CI) checks the schema and the hostile-fixture goldens as two
separate passes over `testdata/games/descriptors/`. The optional `mods`
member is `$defs/mods`; its goldens and the checks the schema cannot make
are §7.11.

## 7. `mods`: the player's own mod loaders (optional)

`mods` is an optional top-level member. It says how to recognise a mod
loader the player installed themselves, where that loader keeps their
mods, which of them are enabled, and how Astra can run beside it. It exists
so that Astra can start a game "with your mods" on an engine nobody knew
when the launcher was released: what a loader looks like is data, and the
launcher implements only the closed vocabularies below. A descriptor holds
no code.

### 7.1 What `mods` never does, and who reads it

- **It is not detection.** `mods` takes no part in §3: not Pass A, not
  Pass B's admission or its prefilter, not conflicts, not the anti-cheat
  union, and not which foundation is offered. A descriptor with `mods` and
  the same descriptor without it place every folder identically. The only
  things `mods` changes are the digest (§1), because it is part of the
  canonical form, and the room left under the 16 KiB bound (§4).
- **Only a mods-aware install evaluates it**: an install, or a Play, that
  the player asked to be "with your mods". Ingest and lint validate it
  (§7.9); nothing else reads it.
- **Narrow-only holds for it too.** A descriptor's `mods` is consulted only
  for a game that same descriptor placed. For a game Pass A placed, only
  the built-in descriptor's `mods` (the launcher's compiled data) is
  consulted. A community descriptor therefore can never add a loader to a
  Unity, Unreal or Godot game, nor to another descriptor's games (§7.4,
  `codes`).
- **It never names a mod manager** (§7.7) **and never writes** (§7.10).

**Compatibility with readers that ignore it.** Launcher 0.5.0 accepts
`mods` and reads nothing in it (astra-game-launcher
`docs/ENGINE-DESCRIPTOR.md`, "Reserved for launcher 0.5.1: `mods`";
`gi-probe validate-descriptor` reports the notice `mods-not-evaluated`).
For such a reader to stay correct, `mods` keeps the shape that 0.5.0
checks:

- it is a table, never an array of tables (`[[mods]]`);
- it sits only at the top level: inline in the catalogue's JSON, as
  `[mods]` in a file, or as `[integration.engine.mods]` in a foundation's
  manifest (§1);
- it holds no float, no datetime, no `null`, and no integer past
  2^53 − 1.

A `mods` that is not a table is `descriptor-invalid` (field `mods`) and
skips the whole descriptor, as it does in 0.5.0. So do the §1 JCS
refusals anywhere inside it. Anything else wrong **inside** the table
voids only `mods` (§7.9): the descriptor still detects, offers and plans
exactly as it would without it. This is the one exception to §0 rule 5
and to §1's `deny_unknown_fields`. It lets a later version add a format or
a strategy without making older readers drop the descriptor's detection.
`testdata/games/descriptors/mods/compat/` holds both cases (§7.11).

### 7.2 Shape

```toml
[[mods.loader]]
id = "bepinex5"                         # §2.1's code pattern; unique in this descriptor
name = "BepInEx 5"                      # §2.1's display-name rules
codes = ["unity-mono"]                  # optional (§7.4)
source = ["game", "manager", "picked"]  # where its install may be (§7.3); closed
require = [                             # recognition (§7.4): §2.4's lookups
  { stat = "{source}/BepInEx/core/BepInEx.dll", kind = "file" },
  { stat = "{source}/BepInEx/core/BepInEx.Preloader.dll", kind = "file" },
]
root = "{source}/BepInEx/plugins"       # the mods root (§7.5)
enabled = [                             # §7.5; closed
  { format = "dir-per-mod" },
  { format = "file-glob", glob = "*.dll" },
]
coexist = [                             # §7.6; closed
  { strategy = "chain", entry = "{source}/BepInEx/core/BepInEx.Preloader.dll" },
]

[mods.loader.version]                   # optional (§7.4)
pe = "{source}/BepInEx/core/BepInEx.dll"
key = ["ProductVersion", "FileVersion"]
template = "N{1,2}.N{1,2}.N{1,3}"
versions = ">=5.4, <5.5"
```

`mods` has one member, `loader`: 1 to 4 loader tables, tried in order.
Every member above is required except `codes` and `version`. A loader's
`id` is how a foundation names the loader it can run beside (the value of
astra-bepinex's `[integration.mods] loader`: `bepinex5`,
`bepinex6-il2cpp`), how the launcher remembers the player's choice, and
how the player is told which loader was found. So two loaders of one
descriptor never share one (reason `loader-id-duplicate`).

### 7.3 Paths and the jail

Every path in `mods` begins with `{source}`, followed by zero or more
`/`-separated components. `{source}` is the root of the player's mod set,
and it is the jail: nothing outside it is read.

A component is never empty, `.` or `..`. It never holds `\`, `:`, `*`, a
control character, or a `{` that does not open a placeholder, and it never
ends in `.` or a space. So an absolute path, a drive letter, a UNC path or
a `~` home cannot be written, because each would have to begin with
something other than `{source}` (reason `path-outside-jail`). A `..`
component is reason `path-escapes`; the other component rules are reason
`path-invalid`.

`source` lists where `{source}` may resolve. It is a closed set the
launcher implements:

| value | `{source}` is |
|---|---|
| `game` | the game folder that detection ran on |
| `manager` | a mod manager's profile folder for this game, found by a launcher adapter (§7.7) |
| `picked` | the folder the player chose in Astra with "Choose folder…" («Указать папку…»), through the native folder picker, and that the launcher remembers in Astra's profile for this game |

The descriptor names none of these folders. It says only which kinds may
hold this loader. Reads below `{source}` are jailed the way detection's
reads are (B§3 "Read outside the folder"): a path is resolved one component
at a time, a symbolic link, junction or reparse point is refused at every
step, and a probe opens only a regular file.

After `{source}/`, a component may hold the placeholders that the
detection rule which placed the game bound (§2.4: `{project}`,
`{project.leaf}`, `{project.parent}`, `{stem}`, `{name}`, `{dir}`,
`{program}`, and that rule's `as` captures, such as Unity's `{data}`),
with their game-relative values. A placeholder that rule did not bind
makes the loader yield nothing. `{source}` itself appears only first.
`mods` has no placeholder for Astra's own profile and no way to name a
file outside `{source}`: where Astra's files go is the foundation's
manifest's business (`${profile}`), never a descriptor's.

### 7.4 Recognising a loader

`require` is §2.4's requirement grammar with three narrowings:

1. every path is a §7.3 path, so it holds no `*`;
2. `as` is not allowed (a loader binds no placeholder);
3. the lookups are answered in the **mods context**. `listed` and `child`
   read the `folder` listing (§2.3) of the directory their path names
   below `{source}`, one `read_dir` per directory, memoised; `stat` is the
   direct call it always is. As in rule 4, the context decides which
   listing serves a lookup, never the descriptor.

`any`/`all`/`none` nest to depth 3, as in §2.4. A loader is recognised in a
source when its whole `require` holds there.

**The loader anchor.** At least one top-level entry (never one inside
`any`/`all`/`none`) is a `listed`, `child` or `stat` lookup whose last
component holds a literal name that is neither:

- a name mod loaders hijack-load by (merged plan §2.5: `winhttp.dll`,
  `version.dll`, `dwmapi.dll`, `dinput8.dll`, the `xinput*` names and the
  rest of the list the launcher keeps as `src/plan.rs` `HIJACK_NAMES`), nor
- a §2.4 ubiquitous runtime name.

A proxy DLL says only that *some* loader sits in a folder: one name is
shared by BepInEx's Doorstop, UE4SS, the Ultimate ASI Loader and ReShade.
So a proxy may appear in a loader's `require`, but never alone. A loader
with no such entry is reason `loader-anchor-invalid`.

**`codes`** (optional) limits a loader to games this descriptor placed under
one of the listed codes. Every one must be among this descriptor's own
`[engine].codes` (else reason `code-undeclared`). When `codes` is absent,
the loader applies to every code of this descriptor.

**`version`** (optional) reads the loader's own version, so that a version
can be required:

- `pe`: one §7.3 path to a PE file (a `.dll` or `.exe`) of the loader.
- `key`: one or two of `ProductVersion` and `FileVersion` (closed), tried
  in order. The value read for a key is that of the first `String` entry
  with that key in the file's `StringFileInfo`.
- `template`: §2.5's version template, matched against the start of the
  value. The character after the match must not be a digit. `N{a,b}` is a
  run of a to b digits; anything else is a literal character.
- `versions` (optional): one or two comparators joined by `, `. Each is
  one of `=`, `<`, `<=`, `>`, `>=`, followed by an operand written in the
  template's own shape and cut after any digit run. The comparison is
  numeric, digit run by digit run, over the operand's runs only. So
  `>=5.4, <5.5` holds for `5.4.23.3`, and `=6.0.0-be.788` holds for
  `6.0.0-be.788+5bd4ae5` but not for `6.0.0-be.789`.

The read is a bounded probe, not a scan of the file. It reads only the PE
headers, the section table, and the `RT_VERSION` resource reached through
the resource directory: at most 32 KiB of the file in all (§7.8). The
loader's version is unknown when there is no such resource, no entry with
the key, no template match, or an operand that does not read in the
template's shape.

A loader whose `versions` does not hold, unknown included, is
**recognised but unsupported**. The player is told which loader was found
and which version Astra needs, and is offered to play without mods. It is
never a dead end and never a guess. A foundation may require a narrower
version than the descriptor does, in its own manifest (astra-bepinex's
`bepinex_build`), but it can never widen `versions`.

### 7.5 The mods root, and which mods are enabled

`root` is a §7.3 path to the folder that holds the player's mods for this
loader. `enabled` is a list of one to three formats from a closed set the
launcher implements. A mod is enabled when any listed format says so.

| `format` | its members | a mod is | it is enabled when |
|---|---|---|---|
| `dir-per-mod` | none | a folder directly in `root` | it is there |
| `enable-list` | `list`: a §7.3 path to a text file; `line`: `name-colon-flag` (closed); `marker` (optional): one file name | a folder directly in `root` | the first line of the list that names it says `1`, or the folder holds a file named `marker` |
| `file-glob` | `glob` | a file directly in `root` whose name matches `glob` | it is there |

`name-colon-flag` is UE4SS's `mods.txt`: one mod per line, `<name> : 1`
(enabled) or `<name> : 0` (disabled). Spaces around the colon are optional.
A line that is empty, starts with `;`, or does not read this way is
skipped. A name is compared with the folder's name ignoring ASCII case.

`glob` is one file name with one or two `*` (each matches any run of
characters, including none) and no other wildcard: no `/`, no `**`, no
`?`, no `[`. So it matches within the one listing of `root` and never
descends (reason `glob-over-budget`).

The player's mods are read for one purpose: so that the player sees, on
the install sheet, what will load beside Astra. Astra never enables,
disables, reorders, renames or removes a mod (§7.10). A `.old` suffix,
which r2modman and Thunderstore Mod Manager use for "disabled", simply
does not match a `*.dll` glob.

### 7.6 `coexist`: how Astra runs beside the player's loader

`coexist` is a list of zero to three strategies, in order of preference.
Each is a table whose `strategy` is one of a closed set the launcher
implements:

| `strategy` | its members | what happens |
|---|---|---|
| `chain` | `entry` (required): a §7.3 path to a file of the player's loader; `tell` (optional) | Astra's runner starts first and hands control to the player's loader at `entry`, which then loads their mods as it always does. `entry` is loaded in place by the game process; it is never written, copied or replaced. |
| `side-by-side` | `tell` (optional) | The player's loader starts as it would without Astra, and Astra's runner runs beside it. Astra's own files stay in Astra's profile. If the player's loader must load something of Astra's, it is told where through `tell` (an environment variable or an argument), never by a file written into the player's tree. Without `tell`, this strategy serves only a foundation that adds nothing to this loader. |
| `via-manager` | none | The player's mod manager starts the game with its own profile, and Astra rides along through a launcher adapter for that manager (§7.7). It is unavailable when no adapter exists for the manager in use. |

`tell` is closed too. The launcher implements each channel, and the value
it carries is always a folder in Astra's profile that the foundation's
manifest names. Whoever starts the player's loader sets it: Astra's runner
in `chain`, the launcher in `side-by-side`.

| `tell` | channel |
|---|---|
| `ue4ss-mods-paths` | the environment variable `UE4SS_MODS_PATHS`, a `;`-separated list of extra Mods folders UE4SS reads. Astra's folder is appended; an existing value is kept. |

**Which strategy a start uses.** A start takes the first strategy in
`coexist` that the foundation's manifest declares it can do. That
declaration is the foundation's `[integration.mods]`: today astra-bepinex
`docs/GAME-INTEGRATION-MANIFEST.md` §7, chain only, and not yet in
`manifest.md`. "With your mods" is offered only when every loader
recognised in the source has such a strategy. A loader with none, or with
`coexist = []` (recognised, and Astra cannot run beside it), makes the
start "without mods", and the player is told which loader was the reason.
A descriptor never makes a foundation chain, tell or ride along: the
descriptor says what the player's loader allows, and the foundation says
what it can do.

### 7.7 Managers are adapters, never data

r2modman, Thunderstore Mod Manager and Gale today, and Mod Organizer 2 and
Vortex later, are launcher **adapters**: launcher code that knows where a
manager keeps its profiles and its own enable state, and (for
`via-manager`) how that manager starts a game. A descriptor says only
`source = ["manager"]` or `strategy = "via-manager"`.

A member that names a manager, a manager's profile folder, its config or
its executable is reason `manager-as-data`, under any key and in any
value. A new manager is a launcher release, reviewed like any other code.
It is never a catalogue entry.

### 7.8 Budgets

These bounds are counted, never timed (§0 rule 3), and they are separate
from §4's.

| scope | bound |
|---|---|
| per `mods` member | ≤4 loaders. Per loader: ≤8 checks in `require` (§4's per-rule bound), `any`/`all`/`none` depth ≤3, ≤3 `enabled` formats, ≤3 `coexist` strategies. Across all its loaders: ≤64 lookups (`listed`, `child`, `stat`) and ≤8 content probes (`tail`, a `version`, an `enable-list` list). It counts toward the descriptor's 16 KiB (§4). |
| per mods evaluation (one game, one source) | ≤5,000 entries listed in any one directory, the mods root included. ≤128 KiB read in all, of which a `version` probe reads ≤32 KiB and a `list` ≤16 KiB. |

Exceeding a per-member bound is reason `over-budget`. Exceeding a
per-evaluation bound makes that loader yield nothing for that source:
never a partial list of mods. The start is then "without mods", and the
player is told why.

### 7.9 An invalid `mods`

Every refusal inside the table is `mods-invalid`, with `field` (the
member's path, such as `mods.loader[1].root`) and one `reason`:

| `reason` | |
|---|---|
| `unknown` | a member or value this version does not know: every one of `source`, `key`, `format`, `line`, `strategy` and `tell` is a closed set |
| `shape` | a missing member, a wrong type, or a count outside the schema's bounds |
| `path-outside-jail`, `path-escapes`, `path-invalid` | §7.3 |
| `glob-over-budget` | §7.5 |
| `loader-anchor-invalid`, `code-undeclared` | §7.4 |
| `loader-id-duplicate` | §7.2 |
| `over-budget` | §7.8 |
| `manager-as-data` | §7.7 |

A `mods` that is not a table is not `mods-invalid`: it is
`descriptor-invalid` (field `mods`), as §7.1 says.

At ingest, and in `gi-probe validate-descriptor`, `mods-invalid` refuses
the descriptor, so a catalogue never signs one. A client that evaluates
`mods` and finds it invalid treats the descriptor as carrying no `mods`
(§7.1) and says so once. It never stops detecting with that descriptor.

### 7.10 Read-only and private

- **Read-only.** The launcher and every runner open nothing under
  `{source}` for writing. No mod, loader file, enable list, marker or
  config of the player's is created, changed, renamed, moved or deleted:
  not by an install, a Play, an update or an uninstall. Astra's own files
  stay in Astra's profile. `chain` loads the player's `entry` in place,
  and `side-by-side` tells their loader where Astra's folder is through
  `tell`. Choosing "without mods" for one start changes how Astra starts,
  never the player's files. This is the existing rule that other people's
  files are not Astra's to change (B§3 "Overwrite a player's file", "Plant
  code in another loader's folder"), stated for mods.
- **Private.** What a mods evaluation finds stays on the player's PC: which
  loaders, their versions, the mods, which of them are enabled, how many
  there are, the folder paths, and the picked folder. It is shown to the
  player and used for that start. It is not sent to the catalogue, to
  minice.ai, to a publisher, in a rating, in a problem or crash report, or
  in any analytics. The descriptor itself holds nothing about any player:
  it is published data about a loader.

### 7.11 Goldens

`testdata/games/descriptors/mods/`, listed in `vectors.json` under
`descriptors.mods`, and kept out of the `builtin` and `hostile` lists that
launcher 0.5.0's K17 reads:

| golden | what it pins |
|---|---|
| `builtin/unity.mods.toml` | BepInEx 5 (Mono; 5.4.x; chain from the game, a manager or a picked folder) and BepInEx 6 (IL2CPP; exactly `6.0.0-be.788`; chain), as data on `descriptors/builtin/unity.toml` |
| `builtin/unreal.mods.toml` | UE4SS 3.x (chain, told by `ue4ss-mods-paths`), UE4SS 2.x (recognised, `coexist = []`: it cannot chain) and the `~mods` paks (`file-glob`, present means enabled; side by side), as data on `descriptors/builtin/unreal.toml` |
| `compat/source2-with-mods.toml` | condition 1: a descriptor with `mods` that a reader ignoring it still accepts for detection. Without `mods`, it is `manifests/valid/foundation-owns-engine.toml`'s `[integration.engine]`, member for member |
| `compat/source2-with-future-mods.toml` | a `mods` table from a later version: this schema refuses it, while detection and the 0.5.0 reader's view accept the same descriptor |
| `hostile/mods-*.toml` | one per rule: `path-escape`, `absolute-path`, `over-budget-glob`, `unknown-enum`, `manager-as-data`, `anchor-on-a-proxy`, `loader-for-another-engine`, `loader-id-duplicate`, `over-budget-lookups`, `not-a-table` |

`tools/check-games-goldens.py` checks `$defs/mods` and the rules a schema
cannot express: the loader anchor, `codes`, ids, the §7.8 per-member
budget, and `manager-as-data`. It checks each built-in `mods` against the
built-in descriptor it rides on. For every golden that carries `mods`, it
checks that the same descriptor without `mods` is a valid descriptor
whatever `mods` holds, which is the 0.5.0 reader's view of §7.1.
`tools/test_check_games_goldens.py` proves each of those checks by
mutation, and holds that every definition the schema's `mods` reaches is a
`mods*` one with no member named like a detection member, so `mods` can
never carry what detection reads.

**Open** (not in this version):

- UE4SS 3's `mods.json` as an `enable-list` line format;
- `LogicMods` (Blueprint mods that UE4SS's BPModLoaderMod loads);
- mods in subfolders of a `file-glob` root;
- MelonLoader, which is not supported.

Each would arrive as a new closed value, which an older client reads as
"without mods" (§7.9).
