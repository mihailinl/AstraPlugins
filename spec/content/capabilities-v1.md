<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# Command capabilities — the closed extractor (v1)

**Normative.** Source: design note §3.3 "command capabilities" / "command
requires", §8 option (b), §11a.3, §11a.9 "Trigger capability words", review F5.
The extractor is the CLIENT's (`Astra/astra-daemon/src/command/capabilities.rs`
`extract_capabilities`, `scan_action`, `scan_action_type`), moved into one
shared module `command::capabilities::catalogue_facts` and copied into plugins
with its tree sha256 pinned in both repositories (design §10 "One extractor").
This page is what that module must compute; `tools/check-content-goldens.py`
`derive_command` is a stdlib reading of it, run over `testdata/content/commands/`.
**The tables were read at Astra `origin/main` `5d5ae5e83`** (2026-11-01):
`astra-daemon/src/command/capabilities.rs` (`scan_action`, `scan_action_type`,
`action_danger`, `action_type_danger`, `command_effective_danger`),
`astra-core/src/command/{action.rs,trigger.rs,workflow.rs}` (`Action`,
`Trigger`, `NodeType`, `GraphNode::action_type`, `match_trigger_node_event`) and
`astra-daemon/src/command/type_registry.rs`. A change to any of them moves the
extractor's pinned tree sha256 and needs this page and its goldens moved too.

## 1. Input

The artefact is the client's `CommandDefinition` JSON
(`astra-core/src/command/definition.rs`), parsed strictly with that Rust type
(`E_COMMAND_FORMAT` when it does not parse, and when any object in it names a
member twice — `{"type": "speak", "type": "execute"}` is speak to one reader and
execute to another; golden `duplicate-type-key`). The extractor reads three members:
`triggers[]` (serde tag `type`), `actions[]` (serde tag `type`) and
`workflow.nodes{}` (`node_type`, `data`).

**One key of a node's `data` is bounded: `retry_count`.** The Commands editor
lets a step be tried again at most 10 times (its retry field's `max`; Astra
`astra-daemon/src/command/catalogue_steps.rs` `MAX_RETRIES`). An artefact with a
node whose `data.retry_count` is a JSON integer above 10 is `E_COMMAND_FORMAT`
(golden `retry-count-over-max`). This holds on the client at parse and on the
server at ingest, so such a command never reaches Browse only to be refused at
every install. The value is read the way the client's executor reads it, as an
unsigned 64-bit integer: a string, a negative number, a fraction or a number
past that range is not a retry count at all, means no retries, and passes.

## 2. The allowlists are CLOSED

**Any action type, node type or trigger type that is not on the pinned
extractor's allowlist refuses the upload** — it is never skipped (F5: the
extractor that skipped unknown types was the hole). A new client capability
can reach the catalogue only with a new pinned extractor, and is then held,
because it is not on `commands.auto_publish_capabilities` (§8).

- unknown action type, unknown node type, or an action node naming its type two
  different ways (`data.action_type` ≠ `data.action.type` — the executor and the
  scanner could each believe a different one) → `E_COMMAND_UNKNOWN_ACTION`;
- unknown trigger type, or an `event` trigger with an unknown `event_name` →
  `E_COMMAND_UNKNOWN_TRIGGER` (the client's own refusal for it is
  `command-unknown-trigger`);
- a plugin action or trigger whose handler id is not `plugin__<id>__<name>`
  with `<id>` a valid plugin id, including the bare `dynamic` tag that names no
  plugin at all → `E_COMMAND_PLUGIN_UNNAMED`.

### 2.1 Node types

`start`, `end`, `action`, `condition`, `loop`, `parallel`, `merge`,
`error_handler`, `trigger`, `sticky_note`, `switch`, `delay`
(`astra-core/src/command/workflow.rs` `NodeType`). Only `action` and `trigger`
nodes contribute capabilities. **`sub_workflow` is refused in v1**
(`E_COMMAND_UNKNOWN_ACTION`): it invokes another workflow that the extractor
does not resolve and derives no capability for — the same laundering shape
that makes `run_command` critical (OPEN.md O-12).

### 2.2 Action types and the words they yield

A **linear** action (`actions[]`, recursively inside `condition` / `loop`) may
carry only an `Action` serde tag: `speak`, `execute`, `open_url`,
`open_application`, `type_text`, `press_keys`, `mouse_click`, `set_variable`,
`wait`, `condition`, `loop`, `send_to_ai`, `kill_process`, `system`,
`clipboard`, `notify`, `play_sound`, `control_music`, `noop`, `code`,
`ai_request`, `stream_to_chat`, `set_volume`, `screenshot`, `ui_click`,
`ui_type`, `youtube_play`, `run_command`, `companion_animation`,
`set_companion_enabled`, `work_task`, `macro`, `dynamic`. Any other linear tag —
`open_file` and `plugin__…` included, which exist only as graph-node action
types — is `E_COMMAND_UNKNOWN_ACTION` (the client's own parse refuses it as an
unknown variant). A **graph-node** action type is any row of the table below.

| action type | capability words | danger |
|---|---|---|
| `code` | `runs_code` | critical |
| `execute` | `executes_shell` | critical |
| `execute` with `shell: "open"` (`EXECUTE_OPEN_MODE`) — LINEAR only; a node's `execute` is always the row above | `file_access`, `launches_apps` | high |
| `run_command` | `runs_command` | critical |
| `macro` | `controls_input` | critical |
| `system`, `kill_process` | `system_control` | high |
| `type_text`, `press_keys`, `mouse_click` | `controls_input` | high |
| `ui_click`, `ui_type` | `ui_automation` | high |
| `screenshot` | `takes_screenshots`, `uses_ai` | high |
| `open_url` | `opens_urls` | high |
| `open_application` | `file_access`, `launches_apps` | high |
| `open_file` | `file_access`, `launches_apps` | high |
| `plugin__<id>__<action>` (node) / `dynamic` with that `handler_id` (linear) | `uses_plugin:<id>` | high |
| `clipboard` | `accesses_clipboard` | low |
| `send_to_ai`, `ai_request`, `stream_to_chat`, `work_task` | `uses_ai` | low |
| `play_sound`, `control_music`, `speak`, `youtube_play` | `plays_audio` | low |
| `set_volume` | `system_control` | low |
| `notify` | `sends_notifications` | low |

**Opening a file with its default application is launching an application** (since 2026-11-07, Astra
`65775237c`). Whatever the spelling (a linear `execute` with `shell: "open"`, an `open_file` node, or
`open_application` on a file), the operating system runs whatever is registered for that file, and that can be
a `.desktop` entry, an `.exe` or a script. So all three derive `file_access` and `launches_apps` at **high**.
Until that commit the client rated the linear `execute` "open" as `file_access` / low, "matching the old
OpenFile action it replaced", while it rated the same act as high when it arrived by another spelling, so a
locally made command and the same bytes from the catalogue could disagree (astra-50, C7).
| `companion_animation`, `set_companion_enabled` | `drives_companion` | low |
| `condition`, `loop` | — (their `if_true` / `if_false` / `body` are scanned) | low |
| `set_variable`, `wait`, `noop` | — | low |

`danger` is the maximum over every action (both spellings of an action node,
SECURITY B2 — over-report is the only direction a gate may be wrong in); a
command with none is `low`.

### 2.3 Trigger capability words

There are **five** (§11a.9, answered in the client plan §15 Q7):

| trigger | word |
|---|---|
| `text` (linear) / trigger node `trigger_type: text` | `on_phrase` |
| `hotkey` / `trigger_type: hotkey` | `binds_hotkey` |
| `event` with `event_name: startup` (a linear `Trigger::Event` carries `event_name` flat; a trigger NODE carries it at `data.config.event_name`, which is where the client's matcher reads it — an event node without it never fires and is refused, `E_COMMAND_UNKNOWN_TRIGGER`) | **`on_startup`** — never `on_event:startup` |
| `event` with `event_name` ∈ {`shutdown`, `login`, `logout`, `wake_word`, `timer`, `reminder_fired`, `calendar_event_due`} | `on_event:<event_name>` |
| `trigger_type: schedule` | **`on_schedule`** — never `on_event:schedule` |
| `dynamic` with `handler_id: plugin__<id>__<t>` / `trigger_type: plugin__<id>__<t>` | `uses_plugin:<id>` (and `<id>` is a requirement, §3) |

`on_schedule` and `on_startup` are words of their own because both run
**unattended**, a different risk class from a user-fired event. Every trigger
word is outside the §8 auto-publish allowlist, so a triggered command is held.
The built-in node trigger types `reminder` and `calendar_event` are NOT mapped
in v1 and are refused (OPEN.md O-5).

## 3. `requires`

The plugin ids a command needs are exactly the `<id>` of every
`uses_plugin:<id>` the extractor emitted, from actions AND from triggers. The
set must equal the declared `requires` (`E_COMMAND_REQUIRES_MISMATCH`), and the
index entry's `requires` must equal its own `uses_plugin:` words (rule
`requires-match-capabilities`). Each `version_req` must match a listed version
in the SERVED plugin index that no served revocation covers
(`E_COMMAND_REQUIRES_UNLISTED`).

## 4. The comparison

The derived `capabilities` (sorted, unique — rule `capabilities-sorted`),
`danger` and `platforms` must equal the declared ones; otherwise
`E_COMMAND_CAPS_MISMATCH`. The index carries the derived values only.
`platforms` comes from `extract_platform_requirements` (per-action platform
support in `astra-core/src/command/platform.rs`), which the stdlib checker does
not mirror: that comparison is L1's and L8's test against the pinned module.

## 5. `F_COMMAND_EXEC_AND_NETWORK`

Raised when one command's derived capabilities contain both a **code
execution** word (`executes_shell`, `runs_code`, `runs_command` — the last
dispatches a saved command that is not contained in the item) and a
**network** word (`opens_urls`, `uses_ai`) (§11a.3; the word sets are OPEN.md
O-11). It is a flag, not a refusal: such a command
is held under §8 (b) anyway, and the flag puts it FIRST in the moderator queue
with the checklist question "does it download and run code or instructions not
contained in the item?". Network calls alone are allowed. Guard: the
`build-and-ask` golden carries the flag; drop the rule and
`tools/test_check_content_goldens.py` fails.

## 6. What the client shows

**The client displays the capabilities it derives from the artefact itself,
never the ones in the index** (design L0, review F5). It derives with the same
pinned function and compares with the entry's `capabilities` and `danger`; a
difference is `claim-mismatch` and the install is refused. The checker runs
that comparison over every entry of `testdata/content/index/commands/valid.json`.

## 7. Goldens

`testdata/content/commands/valid/` — a prompt-only command, a hotkey + shell +
AI command (the flag), a scheduled plugin command, a startup command, a
plugin-trigger command, a nested condition. `…/hostile/` — one per refusal
above: `caps-mismatch`, `unknown-action`, `unknown-node`, `unknown-trigger`,
`unknown-trigger-node`, `unknown-event-name`, `undeclared-trigger-cap`,
`undeclared-uses-plugin`, `bare-dynamic`, `two-spellings`,
`danger-understated`, `unparsed-handler`, `requires-unlisted` (and
`requires-revoked`, which runs `roll-dice` against a served index whose only
listed dice-roller version is revoked).
