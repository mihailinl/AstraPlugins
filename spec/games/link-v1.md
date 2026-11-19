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
  "Speaking on her own"), if the user switched that on;
- act in the game when the user asks: gather, fight, pick up, hand over
  (`danger = "game"` tools, §5 "Actions in the game"), only in a world where
  the player is alone, and only if the user switched that on;
- give the game agent a knowledge base: guides to the game, its author's own
  text, signed with the entry (§5 "The game agent", "Knowledge").

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
  `welcome` rotates `resume`, and after every `welcome` (a resume's too) the
  player counts as not alone until the game's next `world` (§5 "Actions in
  the game"). Game exit kills both tokens. (This is what
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
  One message is never dropped: `world{alone:false}`, which takes the `game`
  tools away (§5 "Actions in the game"), passes whatever the rate.
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
| A→game | `welcome` | `granted{tools,triggers,events,context,skill,speaks,talk,acts}`, `limits{max_message_bytes,max_messages_per_second}`, `resume` | `limits` are integers, at most the protocol's own (65536, 50); a game keeps under them |
| game→A | `event` | `name`, `data` | `name` is a v1 word (§5 "Event words") that this GI declared; `data` valid against its declared schema (the AI profile, §6); ≤4 KiB; ≤2/s, in bursts of at most 5 |
| game→A | `context` | `data` | valid against the declared `context` schema (the AI profile, §6); ≤2 KiB; replaces the previous value; ≤1/s |
| game→A | `trigger` | `name`, `data` | `name` must be declared; schema-valid; goes through `trigger_admission` |
| A→game | `call` | `id`, `tool`, `args` | `args` schema-valid |
| game→A | `result` | `id`, `ok`, `data\|error` | ≤16 KiB; 10 s timeout; `data` valid against the tool's `result` schema (§5 "A tool's result"); `error` is a code (§5 "Refusal codes") |
| game→A | `talk` | — | `talk` granted; ≤1 per 2 s; carries no text (§5 "Voice key") |
| game→A | `quiet` | `on` | `true` while the game is in a menu, a cutscene or paused, `false` again when play resumes; ≤2/s (§5 "Speaking on her own") |
| game→A | `world` | `alone` | `true` while the player is alone in the world (the game is its host and no other player is in it), `false` otherwise; sent when it changes; ≤1/s; until the first one the player counts as not alone (§5 "Actions in the game") |
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
   `speaks` and has no effect while "Tell Astra what happens" is off; "She may
   act in the game" gates the `game` tools (`acts`) and has no effect while
   "AI may act" is off. One more
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

**Tool danger.** Each tool declares `danger = "low"`, `"game"` or `"high"`
(`manifest.md` §2.6); absent means `"high"`.
- `low` is only for an action that stays inside the game on the user's own
  machine and changes nothing in it: it moves or turns the companion, marks
  the map for this session only, shows a bubble over her, reads the game's
  own state, or stops what she is doing for the AI.
- `game` is an action that stays inside the game and may change the player's
  own world, character and inventory there, in a world where the player is
  alone: she gathers, fights, picks up or hands over. Below, "Actions in the
  game".
- Everything else is `high`, and these always are, whatever the world:
  money or a premium currency, a store purchase, a trade with another player
  or a market; deleting or overwriting a save, a character or a world; the
  game's settings; the game's chat, an invite, opening the world to others;
  anything that reaches another player; anything outside the game.
- The game declares; the catalogue checks the declaration when it accepts the
  entry and refuses a `low` or a `game` that is not such an action. A `game`
  tool passes only when its effect is one the player could cause by playing,
  with the means the game gives (her tools and weapons come from the game,
  never from nothing), at the pace of play, in the player's own world, and is
  on none of the `high` list above.
- The daemon reads `low` and `game` only from the link table it extracted
  from the signed entry whose `link.digest` matches (item 1 above). Link
  exists for no other GI (§1), so there is no other source of either.
- A `low` or `game` tool runs without an approval card. A `high` one follows
  the same approval policy as any other plugin tool, and the game-data rule
  below applies to it.

**Actions in the game** (`danger = "game"`). What the player asks her to do
in the game, done for them, and only when they ask. The tools exist only to
serve a request the person made, never her own initiative, and no approval
card stands between the request and the action: a person who asks her to
fetch wood must not be asked to confirm each swing. A `game` tool is offered
to the model only while all of these hold:
- the session is live, and "AI may act" and "She may act in the game" are on
  (§5 item 4; the granted set's `acts`);
- the game's last `world` said `alone: true`;
- the turn is the person's own (below, "The person's own turn": typed
  text, Astra's own voice key, or the wake word only under its flag).
  A turn a `talk` opened is not one (§5 "Voice key").

It is never offered in any other turn: a turn a `talk` opened, a `speaks`
turn, a work-ended turn, a turn a plugin asks for, an automation or a
trigger, a sub-agent's, background or «Code» turn. There it is absent from the tools, and a call to
it all the same (a name kept in the history, a model that calls a tool it
was not offered) is refused by the daemon with `not_granted` before it
reaches the game. The daemon pins both with a canary and a test. That is
what keeps "only when asked" true without a card.

**Checked at every call, not once a turn.** Before each `game` call reaches
the game, the daemon checks again that `acts` is granted and that the game's
last `world` said `alone: true`, and refuses the call itself with
`not_granted` or `not_alone` when either no longer holds.

Besides:
- **No approval card**, whatever the user's approval policy, and the
  game-data rule below does not put a `game` tool onto per-call approval:
  what a game tells the model is names, numbers and booleans (§6), never
  text that could talk it into an action, and the worst a `game` action can
  do stays inside the player's own game.
- **At most 4 `game` calls in one turn.** A fifth gets the daemon's own
  result `{"status":"refused","code":"turn_limit"}` before it reaches the
  game: a guard against a model that loops. The turn is the whole tool loop
  that answers one human message, every round of it; the daemon holds the
  count, and a resume does not reset it. A refused call counts, whoever
  refused it. Calls the model makes together in one round count in the order
  it listed them.
- **Stopping is always possible.** A GI with any `game` tool declares a
  tool with `stops = true` (`manifest.md` §2.6) that ends all of her `game`
  work, her guarding included. It is `low`: it changes nothing, so it stays
  offered whenever tools are, and no limit counts it. The catalogue refuses a
  GI with `game` tools and no such tool (`game-without-stop`), and a `stops`
  tool that is not `low` (`stops-not-low`).
- **Work never outlives its permission.** The game ends all `game` work at
  once, as its `stops` tool would, when any of these happens: a `grants`
  arrives with `acts` false; an `end` arrives, whatever its reason; the
  connection to Astra drops (a resume does not start the work again); the
  player is no longer alone; the player dies or leaves the world.
- **The game holds the line too.** It refuses a `game` call with `not_alone`
  unless the player is alone, and when that stops being true (another player
  joins) it stops any such work at once and sends `world{alone:false}`.
- **Long work answers at once.** A call that starts work lasting longer than
  a call may (10 s, §4) returns as soon as it has started. How the work goes
  is the game's `context` or a later call's result, never a `result` held
  back; that it ended is the game's `work_ended` event, when it declares one
  (§5 "Event words").

**Tools that act on her.** A tool that moves, turns or shows the companion
declares `companion = true`. While the game does not hold her — she is not
being drawn into the game — the daemon refuses such a call before it reaches
the game: the tool's result is `{"status":"refused","code":"not_in_game"}`
with a sentence that does not name the game. Every other tool runs whether or
not she is in the game. **A `stops` tool is never refused this way**, even
with `companion = true`: her work goes on whether or not she is drawn, so
stopping it must never wait for her to be (§5 "Actions in the game").

**Refusal codes.** A game refuses a call with `result{ok:false, error:<code>}`.
The codes for these cases, which every GI uses for them:
- `not_holding`: she cannot be shown (no compositor, hidden by the player, no
  link to the engine);
- `not_in_world`: the main menu, a loading screen;
- `player_dead`;
- `busy`: a cutscene, a teleport;
- `not_alone`: a `game` tool, while the player is not alone in the world
  (§5 "Actions in the game");
- `no_tool`: she has no tool or weapon for the job;
- `tool_too_weak`: the tool she has cannot do it (a pickaxe of too low a tier);
- `bag_full`: her bag has no room;
- `too_far`: the target is beyond where she may go;
- `limit_reached`: a limit the game sets is reached (her map marks, say);
- `failed`, `unknown_tool`, `too_large`: the game's own Link client says
  these for any tool: the game's handler failed, the game has no such tool,
  or the result was too large to send;
- `unknown_target`: the thing the call names is not there;
- `bad_args`: the arguments are valid against the schema but make no sense
  in the game.

**The list is closed.** A game sends only the codes above. The daemon's own
results add `not_in_game` (above), `not_granted`, `not_alone` and
`turn_limit` (§5 "Actions in the game") and `bad_result` ("A tool's result").
The daemon hands the model the code as the tool's result, and only a code
from this list: any other code a game sends reaches the model as
`bad_result`, so an error is never a channel for the game's own words. So
does a `result` message over its 16 KiB (§4), whatever it says; the wire's
own `error{too_large}` (Astra→game) is a different thing, about a message
the game sent. `testdata/games/vectors.json`'s `link.refusal_codes` holds
the list and what the model gets for each case, for every implementation to
test against.

**Game data in a turn.** Any turn whose context carries game-sourced content
(context, an event, or a tool result, since the last user message) runs under
the user's own approval policy, with three rules on top:
- every tool in the policy's **most dangerous class** (in Astra, `Critical`:
  a shell command, deleting files, pressing keys, anything irreversible on
  the computer) goes onto **per-call approval**, regardless of the user's
  own auto-approve setting;
- the turn hands no work to anything that outlives it or runs out of the
  person's sight: no delegated agent, no «Code» agent, no background
  «Work» task (a reminder the person asked for is not one). A call to one is
  refused;
- it writes nothing to long-term memory. When the person asks in so many
  words that something be remembered, Astra answers with one fixed sentence
  instead: she cannot keep memories during a linked game, and they should
  tell her again outside the game.

A `game` tool is in none of these (above, "Actions in the game"), and an
everyday action of the user's own trust (a reminder, music) needs no card.
This is the prompt-injection mitigation, sized to its attacker: a game's
data is names, numbers and booleans (§6), so what it could still steer is
the model's choice of a tool; the card stands in front of every choice
that could do lasting harm on the computer, and a game cannot reach a
person's memory or a task that runs on without them.

**Which turns carry game data.** Context, events and tool results from a
game go only into:
- the person's own turn in the main chat (§5 "The person's own turn"),
  never one a `talk` opened;
- a `speaks` turn (below);
- a work-ended turn (below, "When her work ends").

Never into a «Code» turn (an external coding agent), a sub-agent's turn or a
background one. The context goes into a turn only when it changed since the
last turn that carried it, not into every turn.

**A cloud model only with the person's consent, for each game.** Off by
default for every game. The first time a turn whose model is not local would
carry a game's data, Astra asks once in the chat, for that game: allow its
game data to go to a cloud model, or not now. The answer is kept for that
game key and can be changed in Settings at any time. While a game is not
allowed ("its cloud consent is off"), none of its game data goes into any
turn whose model is not local, and "Not now" runs the turn without it. A
model is local when its endpoint is a loopback address (`127.0.0.0/8`,
`::1`, `localhost`); every other endpoint, Astra's own server included, is a
cloud model.

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
| `work_ended` | her work for the player in the game ended: a job a `game` tool started (§5 "Actions in the game"), whatever ended it |

A manifest that declares any other name is refused by the catalogue. A live
`event` whose name is not on the list, or is on it but not declared by this
GI, is refused with `error{unknown_event}` and goes no further: not to the
AI, not to a plugin, not to an automation. The list grows only by a change to
this document; each event's `data` is the GI's own, under its declared
schema.

**`work_ended`.** It says how a job the person asked for went, so that she can
say so ("I have the wood") without being asked. Only a GI with a `game` tool
declares it, and never with `speaks = true` (semantic rule
`work-ended-misdeclared`). Its `data` schema passes the work-ended profile
(§6), so its data is:
- `reason`, always: one of `done` (she did what was asked), `bag_full`,
  `no_tool`, `tool_too_weak`, `tool_broken`, `nothing_left` (nothing more of
  it within reach), `too_far` (the player went too far from her), `stopped`
  (any of the ends of "Work never outlives its permission" below) and
  `failed` (anything else). A GI declares the ones it sends;
- `progress`, when the GI has a count: how many she gathered, killed or did
  in that job, an integer of at least 0, in the GI's own unit;
- nothing else.

A game sends it once, when the job ends, like every event. A job the
person's own call ended — the `stops` tool, or a `game` tool that starts
another job in its place — is answered by that call's result in their turn,
so the game sends no `work_ended` for it: no second turn says what the first
already did. The daemon reads a `reason` it does not know (a later version's
word) as `failed`. It is game
data like any event, and may start a turn of its own (below, "When her work
ends").

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

**AI turns that game events start.** That is a `speaks` turn (below), a
work-ended turn (below, "When her work ends"), or a turn a plugin asks for
(`send_chat_message`) in reaction to a game event it received. The daemon
cannot follow a cause through a plugin's own process, so it counts a
plugin's turn as one when the plugin asks for it within 60 seconds
after a game event was delivered to that plugin. Every such turn:
- is off by default: a `speaks` turn needs "She may speak on her own", a
  work-ended turn "She may act in the game" (the work exists only under it),
  and a plugin's turn needs the plugin's own `send_chat_message` grant,
  besides the "Plugins hear game events" that let the event reach it;
- starts within its own window, each counted apart from the others:
  - a `speaks` turn at most once per 60 seconds and 30 times per hour for
    each GI, and 30 times per hour for all games together; Settings may
    lower that rate, never raise it;
  - a plugin's turn at most once per 2 minutes for each plugin, and 10 times
    per hour for all plugins' game-caused turns together;
  - a work-ended turn at most 10 times per hour for each GI;
- carries game data only as "Which turns carry game data" allows, and so to
  a cloud model only with that game's cloud consent;
- is paid from the user's ordinary credits;
- writes nothing to long-term memory.

**Speaking on her own** (`speaks`). An event declared with
`speaks = true` (`manifest.md` §2.6) may start a short AI turn with no user
message, but only while "She may speak on her own" is on (and "Tell Astra
what happens" with it). Besides the limits above, that turn:
- never starts while the user is speaking, while a user turn runs, while
  Astra is already speaking, or while the game last said `quiet{on:true}`. It
  never cuts into speech the user is hearing;
- is a short turn with no extended reasoning, and its context is that event
  and the current `context` value, quoted and labelled like any game data;
- may call only this GI's own `low` tools, never a `game` one, no built-in or
  other tool;
- is spoken like any other reply. That reply is kept in the last
  conversation in which a turn carried game data ("Which turns carry game
  data"), or in the main conversation when none has, with a band saying it
  reacts to a game event; the event itself is not written there.

A `speaks` event that cannot start a turn is kept like any other event, for
the next turn that carries game data. That includes a chat whose model is a
cloud model while that game's cloud consent is off: the `speaks`
turn does not start at all.

**When her work ends** (`work_ended`). The daemon itself, never a plugin, may
start a short turn for a `work_ended` event, so that she says how the job the
person asked for went. It needs "Tell Astra what happens" and "She may act in
the game", not "She may speak on her own": it answers a request the person
made. It is not the person's own turn, nor a turn of the game agent run for
the person (§5 "The game agent"): it is a turn of the game's, like a `speaks`
turn, under the same rules:
- it never starts while the user is speaking, while a user turn runs, while
  Astra is already speaking, or while the game last said `quiet{on:true}`;
  until one of those ends the event waits, and a newer `work_ended` replaces
  it;
- it is a short turn with no extended reasoning, and its context is that
  event and the current `context` value, quoted and labelled like any game
  data;
- it may call only this GI's own `low` tools, never a `game` one, no built-in
  or other tool;
- with a cloud model while that game's cloud consent is off it does
  not start at all;
- its reply is spoken and kept like a `speaks` turn's: in the last
  conversation in which a turn carried game data (where the person asked),
  with a band saying it reacts to a game event;
- at most 10 per hour for each GI, its own window (above).

A `work_ended` that cannot start a turn is kept like any other event, for the
next turn that carries game data. Plugins get it as any other game event
(above, "Events and plugins"), and a plugin's turn in reaction to it is a
plugin's turn, under that turn's own rules and limits.

**Voice key** (`talk`). A GI that declares `talk = true` may send `talk` when
the player presses its key on the companion. The daemon treats it as a press
of the user's own voice key: it opens voice input the same way, with the same
indicator, and the words are the user's own. While Astra is speaking, it
silences her, as the voice key does. `talk` is honoured only while the session
is live, "AI may act" is on and the user's voice input is on, at most once per
2 seconds; otherwise the game gets `error{not_granted}`, or
`error{rate_limited}` over the rate. The daemon cannot tell a real press from
a forged one, nor the user's own voice from sound the game plays, which is
why `talk` is declared (and so in the consent digest), switched and
rate-limited, and why **a turn a `talk` opened is not a human turn**: it is a
turn from the game. It is offered no `game` tool, carries no game data,
writes nothing to long-term memory, and no rule that relaxes approval for a
human turn applies to it.

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

**The person's own turn.** While a Link session is live, a turn in the main
chat counts as the person's own (for `game` tools and for the game agent)
only when it was opened by:
- text typed in Astra;
- Astra's own voice key (its hotkey or push-to-talk);
- the wake word, **only** when all of these hold:
  - the capture that heard it ran with echo cancellation against the
    machine's whole output (the system loopback: a PipeWire monitor, WASAPI
    loopback), not only Astra's own voice;
  - the words recognised do not match what was playing from the speakers;
  - the daemon declares this capability with a flag, and turns the flag on
    only after false wake-ups have been measured on real game sound.

  Until the flag is on (it is not today: Astra's echo cancellation removes
  only her own voice), a wake-word turn while a session is live is treated
  like a turn a `talk` opened: no `game` tool, no game data, no game
  agent. A game that plays "Astra, …" must never open the person's turn.
  The person types, or uses Astra's voice key.

Never a turn a `talk` opened (§5 "Voice key"), a `speaks` turn, a turn a
plugin asks for, an automation or a trigger, a sub-agent's, background,
handoff or «Code» turn.

**The game agent.** While a Link session of a GI is live, the person talks
to the game agent: the assistant's "Game" profile, one more of its modes
(as "Fast" and "Work" are), not a second assistant. It answers about the game
and acts in it, and hands anything else to the ordinary assistant. A turn
runs as the game agent when all of these hold:
- it is the person's own turn in the main chat (above);
- the session is live, the player is in the world (not `quiet` in a menu),
  and the game's per-game switch "Answer as the game agent" is on. It is on
  by default: the profile grants nothing by itself, every tool is still
  behind its own switch;
- the conversation is not bound to another mode («Code», «Work»), and the
  person has not picked a mode or a model for it by hand («Fast» included):
  such a conversation keeps what it has, and is never taken over.

The daemon checks these, and the cloud gate below, again before every model
call of the turn. When one no longer holds (a switch turned off, a session
that ended, a model changed in the middle of the turn), **the turn stops
there**: no further model call is made in it, nothing gathered in the Game
profile (game data, a game tool's result, a knowledge passage) is sent to
any other model, and the chat says the turn stopped and why. The person's
next message starts afresh.

**The cloud gate comes first.** The game agent runs on the model of the
"Fast" role. When that model is a cloud model and the game's cloud consent
is off, the profile is not used at all: the turn runs in the
conversation's ordinary mode, with no game data and no game tool, and the
chat says why, once a session. There is no way around the gate through the
profile.

**Game data stays out of the cloud, in history too.** A Game turn's
messages, its tool results, its knowledge passages and its replies are game
data. They are carried into a later turn (the history it replays, a
compaction or a summary, the memory digest) only when that turn's model is
local or that game's cloud consent is on; otherwise the daemon
leaves them out of what that turn sends. They are never written to long-term
memory. A daemon canary pins this for every path that reads a conversation's
history.

**Passages and game results stay in Game turns.** A knowledge passage is the
author's free text, and a game tool's result is the game's. Both are
replayed only into a later Game turn. Any other turn (the ordinary
assistant's, a handoff, a summary) sees a Game turn by its reply alone, so
an ordinary turn with the computer's tools never reads a guide's words on
the user's auto-approve. A turn whose replayed history would hold a passage
or a game result anyway counts as carrying game data (the per-call approval
of "Game data in a turn").

What the game agent is offered, and nothing else:
- this GI's tools, under every rule above (`low`, `game` and `high`, the
  `acts` switch, alone, the turn limit);
- `game_<entryhash8>-knowledge`, when the GI ships a knowledge base (below);
- `ask_astra`, the handoff to the ordinary assistant: "write it in my
  notes", "open the wiki in the browser". It takes **no argument**: the
  daemon hands over the person's own last message, verbatim, and nothing
  the model wrote. The handoff turn starts with that message and no history
  of Game turns, so no game data, game tool result or knowledge passage goes
  with it, and its answer comes back to the conversation without sending
  them anywhere. At most one handoff per turn of the person's.
- **A handoff turn is never the person's turn for approval.** The decision
  to hand off was made by a model that had read the game's data and the
  knowledge base, so the handoff turn is under "Game data in a turn" (its
  per-call approval of the most dangerous class, no hand-off of work, no
  memory), whatever the user's auto-approve setting. A daemon canary pins what the handoff
  carries and this rule.

No built-in tool that reaches the computer is on the game agent's wire. Its
prompt is short and about the game, with the GI's skill. Each of its turns
carries a "Game" badge in the chat, so the person sees who answered. A Game
turn's reply is shown with no remote image loaded and no link followed
without the person's click: a passage or a reply cannot send data out by
being rendered.

**Knowledge** (`knowledge`). A GI may ship a knowledge base for the game
agent: a folder of Markdown files that `[integration.link] knowledge` names
(`manifest.md` §2.6): guides, recipes, bosses, biomes. It is the author's
own text, like the skill, and never the game's live data:
- at most 256 files, each a `.md` file of UTF-8 text, each at most 256 KiB,
  together at most 4 MiB, at most 4 folders deep below the knowledge folder
  (`a/b/c/d/guide.md` in it is as deep as a file may be, `a/b/c/d/e/guide.md`
  is refused), no link of any kind (symbolic or hard) and no `..` in a path.
  Ingest refuses a release that breaks any of these (`vectors.json`
  `link.knowledge_paths`);
- signed with the entry: `link.knowledge_digest` is the folder's part digest
  (`spec/content/part-digest-v1.md`, paths relative to the folder), so a
  changed base asks for consent again. Ingest refuses an entry that declares
  `knowledge` and has no `knowledge_digest`, or the other way round, and so
  does the daemon;
- its licence is declared (`knowledge_licence`, an SPDX id or text, required
  with `knowledge`) and shown on the consent sheet. Text taken from a wiki
  under CC BY-SA keeps its attribution in the files;
- the catalogue's review reads it as text that reaches the model, as it
  reads the skill, and refuses a base that instructs the model rather than
  informs it;
- the daemon indexes only **its own extracted copy** of the base (beside
  the link table, `<data>/games/link/<entry>/<version>/`), never the
  profile's, which the GI's own code can rewrite. It checks the copy against
  `knowledge_digest` before it indexes it, and builds the index again when
  the digest changes;
- the index and the search are local: words (BM25) or an embedding model
  that runs on this machine. A query carries game context, so it never goes
  to a cloud embedding service;
- the daemon offers `game_<entryhash8>-knowledge(query)` to the game agent
  only, one per GI, named like the GI's tools (§5 "Tools"). The `-` is not
  in a tool's `name`, so no GI's own tool can take the name. The daemon
  answers it from its index and the call never reaches the game. A call
  returns at most 4 passages, at most 2 KiB together, and at most 8 KiB of
  passages reach one turn. Each passage reaches the model labelled as
  untrusted text from the GI, as a tool's output does, never as the model's
  own context.

**Wiki on demand.** A game whose GI ships no knowledge base (a game played
through a runner such as "Astra for any Unity game", say) may still have a
public wiki. The game agent may look things up in it, under these rules:
- **Which wiki.** The catalogue's signed `wikis[]` row for the game
  (`games-index-v1.md` §2.6) names it. Without one, the person may give an
  address for that game themselves; the daemon accepts it only over `https`,
  only as a MediaWiki API endpoint (`…/api.php`, its `siteinfo` answering),
  and never one on the person's own machine or network. The daemon never
  guesses a wiki.
- **Asking first.** Looking something up tells that wiki which game is being
  played. The first time a Game turn would look something up for a game, the
  chat asks once, naming the wiki's host: "Look this up on <host>? That site
  will see which game you are playing." (Allow / Not now). The answer is kept
  per game and can be changed in that game's Link settings. "Not now", or no
  answer, means no request is made; the call answers that the wiki is not
  allowed and the agent answers without it.
- **The tool.** It is the GI's own `game_<entryhash8>-knowledge(query)`
  (above): offered to the game agent only, when the GI has no base of its own
  and the game has a wiki. A GI's own base always wins: when there is one, the
  wiki is not searched.
- **What is fetched**, and only on such a call: the wiki's own search (at
  most 3 results), then the plain text of those pages (at most 256 KiB each).
  Nothing else: no image, no link followed, no other host (a redirect off the
  wiki's host is refused).
- **How.** `https` only, no cookies, at most one request in flight and at most
  20 a minute per wiki, the API's `maxlag` honoured; a refusal or an outage
  answers the call as unavailable. The `User-Agent` names Astra and its
  version only: no account, device id or other personal data goes to the
  wiki, and the query goes to no one else (no search engine, no cloud model,
  no cloud embedding service).
- **Kept on this machine.** Page text is cached per game with its revision
  id and indexed like a GI's base (local words or a local embedding model);
  a page is fetched again when the wiki's search reports a newer revision.
  At most 64 MiB per game, the least recently used pages dropped first.
- **Reaching the model.** The same caps and labels as a GI's base (at most 4
  passages, 2 KiB a call, 8 KiB a turn), each passage labelled as untrusted
  text from that wiki, with its attribution: the wiki's name, the page's
  title, the licence, the revision and its address. Anyone can edit a wiki, so
  a passage is game data like any other: it stays in Game turns and behind
  the cloud gate (above).
- **Licence.** Wiki text (usually CC BY-SA) is fetched for this person's own
  session and kept on their machine: it is never redistributed, and no
  catalogue artefact holds it. Its attribution goes with every passage.

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
The names themselves (property names, `enum` values, tool names) are the
author's words, and they do reach the model: the catalogue's review reads
them as such and refuses a name that is an instruction rather than a name.
[`schemas/link-v1-ai-data-profile.schema.json`](schemas/link-v1-ai-data-profile.schema.json)
is that stricter meta-schema. A `string` with `maxLength` stays allowed in
`.triggers[].data`, which never reaches the model, and in `.tools[].params`,
which the model writes and the game reads.

**The work-ended profile.** A `work_ended` event's `data` schema (§5
"`work_ended`") passes the general profile, the AI profile and
[`schemas/link-v1-work-ended-data-profile.schema.json`](schemas/link-v1-work-ended-data-profile.schema.json):
an object with a required `reason`, a string `enum` whose values are drawn from
the closed list of §5, an optional `progress` integer with a `minimum` of at
least 0, and no other property.

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
