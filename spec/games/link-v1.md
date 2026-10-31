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
- tell the AI, briefly, what is happening in the game.

Allowed only as declared in `[integration.link]` and only once the user has
switched it on (§4). **Never available to a game:** chat as the user or as
Astra, slash commands, any variable outside the `game.*` namespace, UI or
theme, the DOM, files, settings, other plugins, or choosing the model.

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
| A→game | `welcome` | `granted{tools,triggers,events,context,skill}`, `limits`, `resume` | — |
| game→A | `event` | `name`, `data` | `name` must be declared; `data` valid against its declared schema; ≤4 KiB; ≤2/s |
| game→A | `context` | `text` | ≤2 KiB; replaces the previous value; ≤1/s |
| game→A | `trigger` | `name`, `data` | `name` must be declared; schema-valid; goes through `trigger_admission` |
| A→game | `call` | `id`, `tool`, `args` | `args` schema-valid |
| game→A | `result` | `id`, `ok`, `data\|error` | ≤16 KiB; 10 s timeout |
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
4. the two user switches: "AI may act" gates tools and triggers; "Tell the
   AI what happens" gates context and events;
5. catalogue freshness of at most 7 days — past that there is no Link
   session at all, and the game still plays (`end{catalogue_stale}` is sent
   to a session that was already live when the index went stale).

**Tools.** Exposed as `game_<entryhash8>_<name>`, each description prefixed
`"[From <GI name>, a game integration]"` and capped at 200 characters. They
exist only while the session is live, follow the same approval policy as any
other plugin tool, and a result reaches the model labelled as **untrusted**
tool output — never silently merged into the model's own context as if it
had said it.

**Game text in a turn.** Any turn whose context carries game-sourced content
(context, an event, or a tool result, since the last user message) puts
every tool in the policy's high-risk class onto **per-call approval**,
regardless of the user's own auto-approve setting. This is the prompt-
injection mitigation: a co-op player's chat line, relayed as game text,
cannot talk the AI into a destructive action on the user's own auto-approve
trust.

**Events and context.** Reach the AI only as quoted, labelled data on the
**next user-initiated turn** — never on their own. Only the last 20 events
plus the current context value are kept; nothing here is ever written to
chat history or long-term memory.

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
