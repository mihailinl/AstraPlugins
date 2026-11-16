<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# `astra.link/1` — Astra Link

> **STATUS: DRAFT.** This protocol's freeze may slip as late as Astra
> 0.2.8.x (`dev/game-integrations-plan-merged.md` §3.4, "May slip to
> 0.2.8.x" item 1; §0, "Astra Link v1 (A§3); it may slip to 0.2.8.x"). The
> shapes below exist now, ahead of the freeze, so that `[integration.link]`
> (`manifest.md` §2.6) has somewhere normative to point at and an author can
> start writing to it — not because every byte here is final. A freeze
> commit removes this notice and bumps nothing else unless the wire itself
> changes.

Source: `game-integrations-marketplace-plan.md` §3 ("Astra Link v1"), kept
as cited by the merged plan except where §2.2 of the merged plan narrows the
manifest's declaration (`manifest.md` §2.6) and §2.6 moves the proto surface
to D's lane. This document is the protocol a GI's own code speaks; it does
not cover the avatar/companion bridge (`${bridge_token}`,
`[integration.capabilities] companion`), which is a different, older
mechanism documented in `manifest.md` §2.3 and `astra-companion/docs/bridge.md`.

## 1. What a GI may give Astra, and what it never gets

A Link-capable GI may:
- expose tools the AI can call;
- fire triggers automations can bind to;
- add a read-only skill;
- tell the AI, briefly, what is happening in the game;
- open the user's voice input when the player presses its key on the
  companion (`talk`, §5 "Voice key");
- let Astra speak on her own about an event it declared (`speaks`, §5
  "Speaking on her own"), if the user switched that on.

Allowed only as declared in `[integration.link]` and only once the user has
switched it on (§5). **Never available to a game:** chat as the user or as
Astra, slash commands, any variable outside the `game.*` namespace, UI or
theme, the DOM, files, settings, other plugins, choosing the model, or words
spoken for the user (`talk` carries none).

## 2. Discovery: the link file

- On every Play through Astra, the daemon mints a 256-bit link token.
- Launcher ≥0.5 `launch` writes `<profile>/astra-link.json` — a reserved
  profile file name (`reserved.yaml`):
  ```json
  {"schema":1,"url":"ws://127.0.0.1:<port>/link","token":"…",
   "integration":"<id>","appid":…,"issued_unix_ms":…,"expires_unix_ms":…}
  ```
- Written atomically, under the profile lock, beside `play-arm.json` — same
  rule: **a refused Play leaves no fresh link file.**
- Mode `0600` on Unix.
- When Astra spawns the process itself, the path is also exported as
  `ASTRA_LINK_FILE`; under Proton it is given in its `Z:\` form.
- **An old daemon or launcher writes no file at all**, and the GI runs
  presentation-only — it must degrade, not crash, when the file is absent.

## 3. Token lifetime

- **Bound to the launched game's own lifetime.** The daemon's process watch
  ties the token to the game process tree. An unconnected token expires
  after **10 minutes**.
- **First use spends the file token.** The game's first `hello` consumes it
  and the daemon answers with a `resume` token held only in memory. A
  reconnect uses `hello{resume}` and is accepted only while no session for
  that GI is already live. Every `welcome` rotates `resume`. Game exit kills
  both tokens. (This is what covers a Unity load stall longer than 30 s: the
  session ends and resumes rather than failing outright.)
- **Peer process.** The daemon records the connecting socket's peer pid and
  exe; the chat chip shows them. If the peer is not in the launched game's
  own process tree (or its Wine process), the chip turns amber and every
  tool stays held until the user taps Allow. If the lookup itself is
  unavailable on a platform, it shows "unknown" and never blocks on that
  account alone.

## 4. Transport

- **Connection:** a WebSocket on `127.0.0.1` at a random port, subprotocol
  `astra-link.1`. Any `Origin` header is refused; `Host` must equal
  `127.0.0.1:<port>` exactly.
- **Sockets:** at most 4 unauthenticated sockets at once, each closed after
  5 seconds without a `hello`. A **live** session does not count against
  that pool, and at most 1 live session exists per installed GI at a time.
- **Limits:** messages ≤64 KiB; ≤50 messages/second per session; a ping
  every 10 seconds; 30 seconds of silence ends the session (resumable, §3).
- **Framing:** JSON, one object per message, a `t` field naming the kind.
  **Unknown `t` values and unknown fields are ignored in both directions** —
  the same fail-open-on-unknown-but-scoped rule the catalogue documents use
  (`games-index-v1.md` §4), applied to a live socket instead of a signed
  document.

| dir | `t` | fields | limits |
|---|---|---|---|
| game→A | `hello` | `token\|resume`, `integration`, `v`, `client` | first message only, within 5 s of connecting |
| A→game | `welcome` | `granted{tools,triggers,events,context,skill,speaks,talk}`, `limits`, `resume` | — |
| game→A | `event` | `name`, `data` | `name` must be declared; `data` valid against its declared schema; ≤4 KiB; ≤2/s |
| game→A | `context` | `text` | ≤2 KiB; replaces the previous value; ≤1/s |
| game→A | `trigger` | `name`, `data` | `name` must be declared; schema-valid; goes through `trigger_admission` |
| A→game | `call` | `id`, `tool`, `args` | `args` schema-valid |
| game→A | `result` | `id`, `ok`, `data\|error` | ≤16 KiB; 10 s timeout; `error` is a code (§5 "Refusal codes") |
| game→A | `talk` | — | `talk` granted; ≤1 per 2 s; carries no text (§5 "Voice key") |
| game→A | `quiet` | `on` | `true` while the game is in a menu, a cutscene or paused, `false` again when play resumes; ≤2/s (§5 "Speaking on her own") |
| A→game | `grants` | the new granted set | sent on any switch change |
| A→game | `end` | `reason` | one of `withdrawn`, `stopped`, `replaced`, `game_exited`, `catalogue_stale` |
| A→game | `error` | `code` | one of `not_granted`, `rate_limited`, `too_large`, `bad_schema`, `withdrawn` |

See [`schemas/link-v1-message.schema.json`](schemas/link-v1-message.schema.json).

## 5. Enforcement

The granted set a live session actually has is the **intersection** of:

1. the declaration in the signed catalogue entry's `link` summary
   (`games-index-v1.md` §2.1), read from the **daemon's own extracted copy**
   under `<data>/games/link/<entry>/<version>/` — never the profile's own
   copy, which the GI's own code can rewrite;
2. the current consent digest (`games-index-v1.md`-adjacent; the daemon's
   `updates.rs` owns the digest itself);
3. not withdrawn (`games-withdrawn-v1.md`);
4. the user switches, each off until the user turns it on: "AI may act"
   gates tools, triggers and `talk`; "Tell the AI what happens" gates context
   and events; "She may speak on her own" gates `speaks` and has no effect
   while "Tell the AI what happens" is off;
5. catalogue freshness of at most 7 days — past that there is no Link
   session at all, and the game still plays (`end{catalogue_stale}` is sent
   to a session that was already live when the index went stale).

**Tools.** Exposed as `game_<entryhash8>_<name>`, each description prefixed
`"[From <GI name>, a game integration]"` and capped at 200 characters. They
exist only while the session is live, are approved by their declared danger
(below), and a result reaches the model labelled as **untrusted** tool output —
never silently merged into the model's own context as if it had said it.

**Tool danger.** Each tool declares `danger = "low"` or `"high"`
(`manifest.md` §2.6); absent means `"high"`.
- `low` is only for an action that stays inside the game on the user's own
  machine: it moves or turns the companion, marks the map for this session
  only, shows a bubble over her, or reads the game's own state. Anything that
  changes the world other players share, the game's saved data, the player's
  inventory, or anything outside the game is `high`.
- The game declares; the catalogue checks the declaration when it accepts the
  entry and refuses a `low` that is not such an action.
- The daemon honours `low` only for a tool declared in the link table it
  extracted from a **signed** catalogue entry whose `link.digest` matches
  (item 1 above). For any other GI — sideloaded, unsigned, or a table that
  does not match — every tool is `high`.
- A `low` tool runs without an approval card. A `high` one follows the same
  approval policy as any other plugin tool, and the game-text rule below
  applies to it.

**Tools that act on her.** A tool that moves, turns or shows the companion
declares `companion = true`. While the game does not hold her — she is not
being drawn into the game — the daemon refuses such a call before it reaches
the game: the tool's result is `{"status":"refused","code":"NOT_IN_GAME"}`
with a sentence that does not name the game. Every other tool runs whether or
not she is in the game.

**Refusal codes.** A game refuses a call with `result{ok:false, error:<code>}`.
The codes for these cases, which every GI uses for them:
- `not_holding`: she cannot be shown (no compositor, hidden by the player, no
  link to the engine);
- `not_in_world`: the main menu, a loading screen;
- `player_dead`;
- `busy`: a cutscene, a teleport;
- `unknown_target`: the thing the call names is not there;
- `bad_args`: the arguments are valid against the schema but make no sense
  in the game.

A GI may use another code of the same shape (`^[a-z][a-z0-9_]{0,31}$`). The
daemon hands the model the code as the tool's result — never free text from
the game in its place.

**Game text in a turn.** Any turn whose context carries game-sourced content
(context, an event, or a tool result, since the last user message) puts
every tool in the policy's high-risk class onto **per-call approval**,
regardless of the user's own auto-approve setting. This is the prompt-
injection mitigation: a co-op player's chat line, relayed as game text,
cannot talk the AI into a destructive action on the user's own auto-approve
trust.

**Events and context.** Reach the AI only as quoted, labelled data on the
**next user-initiated turn** — never on their own, except a `speaks` event
under the rules below. Only the last 20 events plus the current context value
are kept; nothing here is ever written to chat history or long-term memory.

**Speaking on her own** (`speaks`). *Pending the owner's approval: it changes
what people see, so the shapes are reserved here for the work to go on, and no
client shows the switch until it is approved.* An event declared with
`speaks = true` (`manifest.md` §2.6) may start a short AI turn with no user
message, but only while "She may speak on her own" is on (and "Tell the AI
what happens" with it). That turn:
- starts at most once per 2 minutes and 10 times per hour per GI;
- never starts while the user is speaking, while a user turn runs, or while
  the game last said `quiet{on:true}`;
- is a short turn with no extended reasoning, and its context is that event
  and the current `context` value, quoted and labelled like any game text;
- may call only this GI's own `low` tools, no built-in or other tool;
- writes nothing to long-term memory, and its line in the chat carries a band
  saying it reacts to a game event;
- is spoken like any other reply.

A `speaks` event that cannot start a turn is kept like any other event, for
the next user turn.

**Voice key** (`talk`). A GI that declares `talk = true` may send `talk` when
the player presses its key on the companion. The daemon treats it as a press
of the user's own voice key: it opens voice input the same way, with the same
indicator, and the words are the user's own. `talk` is honoured only while the
session is live and "AI may act" is on, at most once per 2 seconds; otherwise
the game gets `error{not_granted}` or `error{rate_limited}`. The daemon cannot
tell a real press from a forged one, which is why `talk` is declared (and so
in the consent digest), switched and rate-limited.

**Triggers.** `trigger_admission` is keyed by `(Owner::Game(entry), name)` —
a game integration is its own owner, distinct from a plugin's `PluginId`
today. Trigger data must validate against its declared schema. Its fields
reach an automation as `game.<key>` variables, and the workflow binder
refuses `{game.*}` inside shell or raw command text outright — such a value
may only be passed as a quoted argument or an environment variable. A
trigger runs only the automations the user themselves bound to it.

**Skill.** A read-only skills source, at most 16 KiB, labelled as coming
from the GI, visible to the AI only while the session is live.

## 6. The restricted data-schema profile

Every schema file a manifest names (`[integration.link].tools[].params`,
`.triggers[].data`, `.events[].data`) must itself be restricted, so that
validating untrusted game data against it can never become the attack:

- **flat** — a plain object, no nested objects or arrays of objects;
- **at most 8 properties**;
- every property's type is one of: `string` with `maxLength ≤ 64`, an
  `enum`, `integer`, `number`, or `boolean`;
- **local `$ref` only** — no network fetch is ever made to resolve one;
- every `pattern` must be linear-time (no nested quantifiers, no
  catastrophic-backtracking shape) — the daemon validates with remote
  resolution disabled and a linear-time regex engine, so a schema this
  profile would reject could not be evaluated safely even if it slipped
  through.

[`schemas/link-v1-data-schema-profile.schema.json`](schemas/link-v1-data-schema-profile.schema.json)
is a **meta-schema**: it validates that a `params`/`data` JSON Schema file
itself obeys the restriction above, before that file is ever used to
validate a live `event`/`trigger`/`call` payload.

## 7. Kits

- **The spec** is this document plus `schemas/*.json`, GPL-3.0-or-later.
- **`astra-link-mock`** (GPL-3.0, 0.2.8.x) — a single binary for author CI:
  writes a link file, does `hello`/`resume`, calls every declared tool with
  schema-generated arguments, fires deliberately bad data at every event and
  trigger, and prints a conformance report. Not yet built; referenced here
  so `templates/gi-release.yml` has a named, if-present, step for it.
- **SDKs (MPL-2.0, 0.2.8.x):** C# `LinkClient` in
  `astra-bepinex/src/Astra.Bridge.Core`; a dependency-free ~300-line Java
  reference on `java.net.http.WebSocket` in `examples/link-java`.

## 8. Canary K11

`link-v1` framing must match `astra-companion/docs/bridge.md`'s own framing
notes (the `t` field, the ignore-unknown rule) — canary K11
(`dev/game-integrations-plan-merged.md` §3.3), owned jointly by this lane and
E. This document's §4 table is the side of that comparison that lives here;
`tools/check-games-goldens.py`'s self-consistency check (§5 below) is the
spec-side half that runs in **this** repository's CI without needing a
checkout of `astra-companion`.
