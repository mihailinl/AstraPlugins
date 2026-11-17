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
- tell the AI what is happening in the game, as facts: a name chosen ahead
  of time, a number, true or false, never text (§5 "Events and context");
- send events that plugins may react to (§5 "Events and plugins");
- open the user's voice input when the player presses its key on the
  companion (`talk`, §5 "Voice key");
- let Astra speak on her own about an event it declared (`speaks`, §5
  "Speaking on her own"), if the user switched that on.

Allowed only as declared in `[integration.link]` and only once the user has
switched it on (§5). **Never available to a game:** chat as the user or as
Astra, slash commands, any variable outside the `game_` namespace, UI or
theme, the DOM, files, settings, other plugins, choosing the model, words
spoken for the user (`talk` carries none), or text of its own in front of the
AI or a plugin.

**Only from the signed catalogue.** Link exists only for a GI installed from
a signed games-catalogue entry (`games-index-v1.md`) whose `link.digest`
matches the table the daemon extracted (§5, item 1). There is no Link without
the catalogue: for a sideloaded or unsigned GI, or one whose table does not
match, the daemon mints no token and writes no link file (§2), so the game
runs presentation-only and never sends an event. In Astra, Link ships in the
same build as the games catalogue (the `games-catalogue` build feature).

**Never over the bridge.** The companion bridge is for presentation only:
events and every other message of this channel never travel over it. A state
the companion shows, such as climbing or swimming, is a bridge parameter and
never a Link event (§5 "Events are edges").

## 2. Discovery: the link file

- On every Play through Astra, the daemon mints a 256-bit link token.
- Launcher ≥0.6.0 `launch_with_link` writes `<profile>/astra-link.json` — a reserved
  profile file name (`reserved.yaml`):
  ```json
  {"schema":1,"url":"ws://127.0.0.1:<port>/link","token":"…",
   "integration":"<id>","game":"<key>","issued_unix_ms":…,"expires_unix_ms":…}
  ```
- `game` is the daemon's key for the game, always a string: a Steam app's id
  in decimal digits (`"892970"`), `local-<16 hex>` for a game the user added
  by hand, `epic-<AppName>` for an Epic game.
- Written atomically, under the profile lock, beside `play-arm.json` — same
  rule: **a refused Play leaves no fresh link file.**
- Mode `0600` on Unix. On Windows the file inherits the ACL of the profile
  folder, since there is no `0600` there. The threat model is the same on
  both: another process of the same user can read the file.
- When Astra spawns the process itself, the path is also exported as
  `ASTRA_LINK_FILE`; under Proton it is given in its `Z:\` form.
- **Flatpak Steam** (Linux, from Flathub): the game's sandbox sees only
  `<profile>/BepInEx` of the profile, and a game Steam starts gets no
  environment from Astra, so there is no `ASTRA_LINK_FILE` either. Astra
  grants that sandbox read access to `<profile>/astra-link.json` alone, by a
  Flatpak permission of its own (the daemon's half): the GI reads the file at
  the same path, read-only. The socket works there unchanged, since Flatpak
  Steam shares the host's network, loopback included.
- **An old daemon or launcher writes no file at all**, and the GI runs
  presentation-only — it must degrade, not crash, when the file is absent.

## 3. Token lifetime

- **Bound to the launched game's own lifetime.** The daemon's watcher of
  running games ties the token to the game it recognised. An unconnected
  token expires after **10 minutes**.
- **First use spends the file token.** The game's first `hello` consumes it
  and the daemon answers with a `resume` token held only in memory. A
  reconnect uses `hello{resume}`. A valid resume **replaces** a session of
  that GI that is still live: the old socket gets `end{replaced}` and is
  closed, so a half-open socket never locks the game out for 30 s. Every
  `welcome` rotates `resume`. Game exit kills both tokens. (This is what
  covers a Unity load stall longer than 30 s: the session ends and resumes
  rather than failing outright.)
- **A daemon restart loses `resume`**, which lived only in its memory: Link is
  then off for that game until the next Play writes a new link file.
- **A hello the daemon will not take** — a spent or unknown token, a resume it
  does not know, a GI with no Link now — is answered `error{not_granted}`, and
  the socket closed. The game does not send that token or resume again: it
  reads the link file once more for a new Play's token, and without one stays
  off until the next Play. A hello with no answer at all may be repeated.
- **Peer process.** The daemon records the connecting socket's peer pid and
  exe; the chat chip shows them. The peer is expected to be the process of
  the game the daemon's watcher of running games recognised, or that game's
  Wine process. It is never checked against "the launch's process tree": a
  Steam game is a child of Steam (`-applaunch`), and a Proton game runs under
  Steam's reaper. If the peer is neither, the chip turns amber and every tool
  stays held until the user taps Allow. If the lookup itself is unavailable on
  a platform, it shows "unknown" and never blocks on that account alone.

## 4. Transport

- **Connection:** a WebSocket on `127.0.0.1` at a random port, subprotocol
  `astra-link.1`. Any `Origin` header is refused; `Host` must equal
  `127.0.0.1:<port>` exactly.
- **Sockets:** at most 4 unauthenticated sockets at once, each closed after
  5 seconds without a `hello`. A **live** session does not count against
  that pool, and at most 1 live session exists per installed GI at a time.
- **Limits:** messages ≤64 KiB; ≤50 messages/second per installed GI; a ping
  every 10 seconds; 30 seconds of silence ends the session (resumable, §3).
- **Bursts.** Every rate in the table below is held per installed GI —
  never per session, since a resume replaces a session and must not start the
  counts afresh — on the socket itself, before a message reaches anything else
  in Astra. A message
  over its rate is dropped there, and the game gets `error{rate_limited}`.
  It never reaches the AI, a plugin or an automation, so a chatty mod cannot
  flood the daemon's event bus ahead of the limits on AI turns (§5).
- **Framing:** JSON, one object per message, a `t` field naming the kind.
  **Unknown `t` values and unknown fields are ignored in both directions** —
  the same fail-open-on-unknown-but-scoped rule the catalogue documents use
  (`games-index-v1.md` §4), applied to a live socket instead of a signed
  document.

| dir | `t` | fields | limits |
|---|---|---|---|
| game→A | `hello` | `token\|resume`, `integration`, `v`, `client` | first message only, within 5 s of connecting |
| A→game | `welcome` | `granted{tools,triggers,events,context,skill,speaks,talk}`, `limits{max_message_bytes,max_messages_per_second}`, `resume` | `limits` are integers, at most the protocol's own (65536, 50); a game keeps under them |
| game→A | `event` | `name`, `data` | `name` is a v1 word (§5 "Event words") that this GI declared; `data` valid against its declared schema (the AI profile, §6); ≤4 KiB; ≤2/s, in bursts of at most 5 |
| game→A | `context` | `data` | valid against the declared `context` schema (the AI profile, §6); ≤2 KiB; replaces the previous value; ≤1/s |
| game→A | `trigger` | `name`, `data` | `name` must be declared; schema-valid; goes through `trigger_admission` |
| A→game | `call` | `id`, `tool`, `args` | `args` schema-valid |
| game→A | `result` | `id`, `ok`, `data\|error` | ≤16 KiB; 10 s timeout; `data` valid against the tool's `result` schema (§5 "A tool's result"); `error` is a code (§5 "Refusal codes") |
| game→A | `talk` | — | `talk` granted; ≤1 per 2 s; carries no text (§5 "Voice key") |
| game→A | `quiet` | `on` | `true` while the game is in a menu, a cutscene or paused, `false` again when play resumes; ≤2/s (§5 "Speaking on her own") |
| A→game | `grants` | the new granted set | sent on any switch change |
| A→game | `end` | `reason` | one of `withdrawn`, `stopped`, `replaced`, `game_exited`, `catalogue_stale` |
| A→game | `error` | `code` | one of `not_granted`, `rate_limited`, `too_large`, `bad_schema`, `unknown_event`, `withdrawn` |

See [`schemas/link-v1-message.schema.json`](schemas/link-v1-message.schema.json).

## 5. Enforcement

The granted set a live session actually has is the **intersection** of:

1. the declaration in the signed catalogue entry's `link` summary
   (`games-index-v1.md` §2.1), read from the **daemon's own extracted copy**
   under `<data>/games/link/<entry>/<version>/` — never the profile's own
   copy, which the GI's own code can rewrite. Without such an entry there is
   no session at all (§1, "Only from the signed catalogue");
2. the current consent digest (`manifest.md` §2.6.1; in the daemon,
   `games/service.rs` holds it);
3. not withdrawn (`games-withdrawn-v1.md`);
4. the user switches on the game's row, each off until the user turns it on:
   "AI may act" gates tools, triggers and `talk`; "Tell Astra what happens"
   gates context and events for the AI; "She may speak on her own" gates
   `speaks` and has no effect while "Tell Astra what happens" is off. One more
   switch is global, in Settings, and off by default: "Plugins hear game
   events" gates events for plugins (below), on its own — a user may give an
   event to a plugin without giving it to the AI, and the other way round;
5. catalogue freshness of at most 7 days — past that there is no Link
   session at all, and the game still plays (`end{catalogue_stale}` is sent
   to a session that was already live when the index went stale).

**Tools.** Exposed as `game_<entryhash8>_<name>`, each description prefixed
`"[From <GI name>, a game integration]"` and capped at 200 characters. A
tool's `name` is at most 32 characters of `[a-z0-9_]` (`manifest.md` §2.6),
so the whole name is at most 46 characters, inside the 64 characters of
`[a-zA-Z0-9_-]` that AI providers accept. Tools exist only while the session
is live, are approved by their declared danger (below), and a result reaches
the model labelled as **untrusted** tool output — never silently merged into
the model's own context as if it had said it.

**A tool's result** is facts too. Every tool declares a `result` schema
(`manifest.md` §2.6) under the AI profile (§6), so it is in `schema_digests`
and in the consent like `params`. The daemon validates `result.data` (absent
is `{}`) against it, and the model gets only the fields that schema names:
names from its enums, numbers, booleans. An item's id is a name from a
declared `enum` too; there are no free strings. Data that does not match
never reaches the model: it gets the daemon's own code `bad_result` instead.

**Tool danger.** Each tool declares `danger = "low"` or `"high"`
(`manifest.md` §2.6); absent means `"high"`.
- `low` is only for an action that stays inside the game on the user's own
  machine: it moves or turns the companion, marks the map for this session
  only, shows a bubble over her, or reads the game's own state. Anything that
  changes the world other players share, the game's saved data, the player's
  inventory, or anything outside the game is `high`.
- The game declares; the catalogue checks the declaration when it accepts the
  entry and refuses a `low` that is not such an action.
- The daemon reads `low` only from the link table it extracted from the
  signed entry whose `link.digest` matches (item 1 above). Link exists for no
  other GI (§1), so there is no other source of a `low`.
- A `low` tool runs without an approval card. A `high` one follows the same
  approval policy as any other plugin tool, and the game-data rule below
  applies to it.

**Tools that act on her.** A tool that moves, turns or shows the companion
declares `companion = true`. While the game does not hold her — she is not
being drawn into the game — the daemon refuses such a call before it reaches
the game: the tool's result is `{"status":"refused","code":"not_in_game"}`
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

A GI may use another code of the same shape (`^[a-z][a-z0-9_]{0,31}$`), and
the daemon's own `not_in_game` above has it too. The daemon hands the model
the code as the tool's result — never free text from the game in its place.

**Game data in a turn.** Any turn whose context carries game-sourced content
(context, an event, or a tool result, since the last user message) puts
every tool in the policy's high-risk class onto **per-call approval**,
regardless of the user's own auto-approve setting. This is the prompt-
injection mitigation: whatever a game sends, it cannot talk the AI into a
destructive action on the user's own auto-approve trust.

**Which turns carry game data.** Context, events and tool results from a
game go only into:
- a direct human turn in the main chat;
- a `speaks` turn (below).

Never into a «Code» turn (an external coding agent), a sub-agent's turn or a
background one. The context goes into a turn only when it changed since the
last turn that carried it, not into every turn.

**A cloud model only behind a global switch.** In Settings, off by default:
"Game data may go to a cloud model". While it is off, no game data goes into
any turn whose model is not local. A model is local when its endpoint is a
loopback address (`127.0.0.0/8`, `::1`, `localhost`); every other endpoint,
Astra's own server included, is a cloud model.

**How much game data a turn carries.** At most **4 KiB** of game data per
turn in all: the current `context` value first, then the events, newest
first, while the next one still fits. The rest are left out of that turn.
Game data is ordinary input to the turn, paid from the user's ordinary
credits like any other input.

**Events and context.** What a game tells the AI is only names from an
`enum` the GI declared, numbers and booleans (the AI profile, §6): no game
ever puts text in front of the model. Events and context exist only inside a
live session that passed `hello`/`welcome` (§1, §3). They reach the AI only as
quoted, labelled data on the **next turn that carries game data** (above) —
never on their own, except a `speaks` event under the rules below. Only the last 20 events
plus the current context value are kept, in memory, for the live session.
Neither is ever written to long-term memory, and an event is never written to
the chat history (Astra's spoken reply to a `speaks` event is, below).

**Event words (v1).** An event's name is one word of a closed list. In v1:

| word | sent when |
|---|---|
| `session_started` | the player is in the world and play begins |
| `session_ended` | the player leaves the world: back to the menu, or the game is closing |
| `player_hurt` | the player takes damage |
| `player_fell` | the player falls, a fall that counts in the game (not every step off a ledge) |
| `player_died` | the player dies |
| `player_revived` | the player is back after dying |
| `goal_reached` | the player reaches a goal of the game: a summit, a boss down, a level done |

A manifest that declares any other name is refused by the catalogue. A live
`event` whose name is not on the list, or is on it but not declared by this
GI, is refused with `error{unknown_event}` and goes no further: not to the
AI, not to a plugin, not to an automation. The list grows only by a change to
this document; each event's `data` is the GI's own, under its declared
schema.

**Events are edges, not levels.** An event is sent once, at the moment of the
change: when the player falls, not while they lie on the ground. A state that
lasts (climbing, swimming, low on health) is never an event. The AI may see
it in `context`, and the companion in a bridge parameter.

**Events and plugins.** An event that passed every check above reaches
plugins as one daemon event, whose type is named in
`astra-core/event-vocabulary.json` (the daemon's half). It carries the
event's word and its data, never the game's name or key:
- a plugin learns which game sent it only when its `plugin.toml` names that
  game in `target`, and only for that game;
- it reaches only plugins granted `subscribe_events` for that type, and only
  while the session is live and the global "Plugins hear game events" is on
  (§5, item 4), whatever "Tell Astra what happens" says.

That daemon event is raised by the daemon's `games/link` server alone, so it
exists only in a build with the games catalogue (§1). It replaces the
engine-side `game_event` once planned for PEAK: events never go over the
bridge.

`target` is a `[plugin]` key of `plugin.toml`: an array of at most 16 game
keys, spelled as in §2 (`target = ["3527290"]`). A key for a game the user
added by hand (`local-…`) differs from machine to machine, so a plugin never
names one. The key belongs to `astra-plugin-manifest`, the crate the daemon
parses `plugin.toml` with and from which `docs/en/reference/manifest.md` is
generated. It is named here so that the daemon and the SDKs agree on it
before it lands there.

**AI turns that game events start.** That is a `speaks` turn (below), or a
turn a plugin asks for (`send_chat_message`) in reaction to a game event it
received. The daemon cannot follow a cause through a plugin's own process, so
it counts a plugin's turn as one when the plugin asks for it within 60 seconds
after a game event was delivered to that plugin. Every such turn:
- is off by default: a `speaks` turn needs "She may speak on her own", and a
  plugin's turn needs the plugin's own `send_chat_message` grant, besides
  the "Plugins hear game events" that let the event reach it;
- starts at most once per 2 minutes for each GI (a `speaks` turn) or each
  plugin (a plugin's turn), at most 10 times per hour for each GI, and at most
  10 times per hour for all games together;
- carries game data only as "Which turns carry game data" allows, and so to
  a cloud model only behind its global switch;
- is paid from the user's ordinary credits;
- writes nothing to long-term memory.

**Speaking on her own** (`speaks`). *Pending the owner's approval: it changes
what people see, so the shapes are reserved here for the work to go on, and no
client shows the switch until it is approved.* An event declared with
`speaks = true` (`manifest.md` §2.6) may start a short AI turn with no user
message, but only while "She may speak on her own" is on (and "Tell Astra
what happens" with it). Besides the limits above, that turn:
- never starts while the user is speaking, while a user turn runs, while
  Astra is already speaking, or while the game last said `quiet{on:true}`. It
  never cuts into speech the user is hearing;
- is a short turn with no extended reasoning, and its context is that event
  and the current `context` value, quoted and labelled like any game data;
- may call only this GI's own `low` tools, no built-in or other tool;
- is spoken like any other reply. That reply is kept in the last
  conversation in which a turn carried game data ("Which turns carry game
  data"), or in the main conversation when none has, with a band saying it
  reacts to a game event; the event itself is not written there.

A `speaks` event that cannot start a turn is kept like any other event, for
the next turn that carries game data. That includes a chat whose model is a
cloud model while "Game data may go to a cloud model" is off: the `speaks`
turn does not start at all.

**Voice key** (`talk`). A GI that declares `talk = true` may send `talk` when
the player presses its key on the companion. The daemon treats it as a press
of the user's own voice key: it opens voice input the same way, with the same
indicator, and the words are the user's own. While Astra is speaking, it
silences her, as the voice key does. `talk` is honoured only while the session
is live, "AI may act" is on and the user's voice input is on, at most once per
2 seconds; otherwise the game gets `error{not_granted}`, or
`error{rate_limited}` over the rate. The daemon cannot tell a real press from
a forged one, which is why `talk` is declared (and so in the consent digest),
switched and rate-limited.

**Triggers.** `trigger_admission` is keyed by `(Owner::Game(entry), name)` —
a game integration is its own owner, distinct from a plugin's `PluginId`
today (a daemon change, in the daemon's half). Trigger data must validate
against its declared schema. Its fields reach an automation as variables
named `game_<key>`: the command parser reads a variable only as `{name}` of
letters, digits and `_`, so a dot would end the name (`{game.height}` is no
variable at all). `game_` is these variables' namespace. The workflow binder
refuses `{game_<key>}` outright (and every property of a trigger's data is
such a variable: its schema names properties as ids, §6 "The trigger
profile"):
- inside shell or raw command text — there such a value may only be passed as
  a quoted argument or an environment variable;
- in every text that goes to a model: an AI node's prompt, a task, a chat
  message.

A trigger runs only the automations the user themselves bound to it. Since
the binder keeps trigger data from every model, trigger data is the one place
a game's own string (at most 64 characters, §6) may appear.

**Skill.** A read-only skills source, at most 16 KiB, labelled as coming
from the GI, visible to the AI only while the session is live.

## 6. The restricted data-schema profile

Every schema file a manifest names (`[integration.link].context`,
`.tools[].params`, `.tools[].result`, `.triggers[].data`, `.events[].data`)
must itself be
restricted, so that validating untrusted game data against it can never
become the attack:

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

**The AI profile.** A schema whose data reaches the AI or a plugin — the
`context` schema, every `.events[].data` and every `.tools[].result` — must
also:
- have no `string` property other than an `enum`;
- name its properties, and every `enum` value, as ids: `^[a-z][a-z0-9_]{0,31}$`;
- list at most 64 values in an `enum`.

What a game tells the AI is names it chose ahead of time, numbers and
booleans, never text. A schema's `description` never reaches the model either.
[`schemas/link-v1-ai-data-profile.schema.json`](schemas/link-v1-ai-data-profile.schema.json)
is that stricter meta-schema. A `string` with `maxLength` stays allowed in
`.triggers[].data`, which never reaches the model, and in `.tools[].params`,
which the model writes and the game reads.

**The trigger profile.** Every `.triggers[].data` schema must also name its
properties as ids, `^[a-z][a-z0-9_]{0,31}$`. Each property reaches an
automation as the variable `{game_<key>}` (§5 "Triggers"), and the command
parser reads a variable name only as letters, digits and `_`: a property
named `fall-height` or `BossName` would never be a variable, and would be
lost without a word. A check of the manifest refuses such a schema instead.
[`schemas/link-v1-trigger-data-profile.schema.json`](schemas/link-v1-trigger-data-profile.schema.json)
is that meta-schema: the general profile with property names as ids.

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
