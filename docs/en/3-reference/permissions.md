# Permissions

What each `[permissions]` id grants, what it costs the user, and how to write a
`reason` worth reading.

This is the author-facing page. The normative rules — grants, ceilings,
`permissions_hash`, the exact refusal semantics — are in
[`spec/permissions.md`](../spec/permissions.md). The generated table of which
RPC each id gates is in [`reference/manifest.md`](../reference/manifest.md) and
[`reference/parity.md`](../reference/parity.md), both derived from
`spec/hooks.yaml` and checked against the daemon's own table by parity rule R6.

## The shape of it

`[capabilities]` says what the daemon may call **into** your plugin.
`[permissions]` says which host RPCs your plugin may call **out** to. Two
questions, two sections; a capability never implies a permission.

Three properties, all of which surprise someone eventually:

1. **Default-deny.** No `[permissions]` section means no host RPCs beyond the
   bootstrap four.
2. **Declaring is asking, not receiving.** Your manifest is a request. The
   granted set is resolved by the daemon from where the plugin came from and,
   for an installed or imported plugin, stored where the plugin cannot write
   it — the manifest lives in your plugin's own directory, which your plugin can
   edit. **Sideloading inverts this**: for a source directory in Developer Mode
   the manifest *is* the grant, re-read on every load, with no ceiling. That is
   what makes the authoring loop work, and it is also why sideloading is a
   developer tool rather than an install path.
3. **An unknown id is kept and inert.** New ids ship with new Astras, so an
   older daemon keeps a key it does not recognise instead of refusing your
   manifest. It grants nothing. `astra-plugin check` warns — a typo is
   indistinguishable from a forward-compatible id at parse time, so it is a
   warning rather than an error, and `--strict` turns it into a failed exit:

   <!-- doctest: output from="astra-plugin check --strict ." unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client, read_ai_settings, speak, read_user_identity, receive_attachments, request_settings_change
     FAILED: 1 warning(s), and --strict treats warnings as errors
   ```

   Astra's install consent sheet shows the same id under its
   `permission.unrecognised` label, so it is never silently dropped on the way
   in either.

## The four calls that need nothing

| RPC | Why it is free |
|---|---|
| `Register` | The handshake. There is no plugin yet to have permissions |
| `PluginLog` | Writing to your own log |
| `GetPluginSelfConfig` | Reading your own settings |
| `GetDaemonInfo` | `version`, `state`, `grpc_port`, `language` — all of which the register response already handed you |

`GetDaemonInfo` being free is a decision, not an oversight: a checkbox that
protects nothing is how users learn to tick boxes.

## The thirteen ids

| Id | Gates | Own checkbox | Refused to a local import | What it lets you do |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | no | no | Run the user's saved automations |
| `subscribe_events` | `SubscribeEvents` | no | no | Receive daemon events — **takes a `types` allowlist** |
| `set_variable` | `SetVariable` | no | no | Write into the daemon's variable context, namespaced to you |
| `send_chat_message` | `SendChatMessage` | **yes** | **yes** | Drive an AI turn as if the user had spoken |
| `push_to_ui` | `PushToUi` | **yes** | no | Push an event into your own panels |
| `set_theme_contribution` | `SetThemeContribution` | **yes** | **yes** | Restyle the whole app |
| `dom_access` | — (a surface) | **yes** | **yes** | Run your code inside the Astra window, with access to conversations and every other plugin's interface |
| `client` | — (a surface) | **yes** | **yes** | Be a chat front-end with its own session |
| `read_ai_settings` | `GetAiSettings` | no | no | Read the user's chat provider, model and endpoint — never a key |
| `speak` | `Speak`, `StopSpeaking` | **yes** | no | Say your own words aloud in Astra's voice, and stop them |
| `read_user_identity` | `GetUserIdentity` | no | no | Read pseudonyms for this installation and the signed-in account, made for your plugin alone |
| `receive_attachments` | — (a delivery) | **yes** | no | Be handed the pictures the person attached, in a tool that asks for them |
| `request_settings_change` | `RequestSettingsChange` | no | no | Ask the person to change a setting the assistant may change, on a card they answer |

`dom_access` and `client` gate no RPC and that is the point: they are
**surfaces**. `dom_access` decides whether a UI contribution is rendered as a
script in the Astra window or a sandboxed iframe; `client` is a ceiling on what
a plugin may be. They are refused where the surface is handed out, not at a call
gate. `receive_attachments` gates no RPC either, from the other side: there is
nothing for you to call. It decides what Astra *sends* one of your tools —
[below](#receiving-the-pictures-the-person-attached).

`dom_access` additionally gets a second consent screen. If you are reaching for
it, read [the security model](../1-orientation/security.md) first and be sure
`push_to_ui` into your own panel will not do.

## Reading the user's AI settings

A plugin that calls the user's model itself — an assistant of its own, a
summariser — needs to know which provider, model and endpoint the user chose.
**Ask Astra for them; never read Astra's files.** Declare `read_ai_settings` and
call `GetAiSettings` (`get_ai_settings()` in Rust and Python, `getAiSettings()`
in TypeScript):

| Field | What it is |
|---|---|
| `provider` | The chat's provider id. An endpoint the user saved is `openai_compatible`; Astra's own service is `astra` |
| `model` | The chat's model id |
| `api_base_url` | The endpoint. Userinfo, query and fragment are removed; the path is sent as the person configured it (a relay that puts a token in the path gives it to you). Empty for `astra`, whose endpoint is not yours to call |
| `is_loopback` | The endpoint is on this machine (`127.0.0.0/8`, `::1`, `localhost`) — a local model |

It never carries an API key, the user's other saved endpoints, the system prompt
or any role but the chat's. A plugin that needs a key asks the user for one in
its own `[config]` (mark it secret). It is neither high-risk nor refused to a
local import: it is the honest way to this information, and pricing it above
reading `settings.json` would push plugins the wrong way. Reading Astra's own
files is something human review at publication looks for. An Astra older than this call
answers `UNIMPLEMENTED`.

## Speaking in Astra's voice

A plugin that has something to announce — a timer, a build that finished, a
message that arrived — can have Astra say it. Declare `speak` and call `Speak`
(`speak(text)` in Rust and Python, `ctx.speak(text)` in TypeScript).

`speak` is **high-risk**: your words are heard in Astra's voice, as if Astra
said them, so it gets its own consent checkbox. It is not refused to a local
import — an announcement is an ordinary thing for a plugin to want, and the
checkbox is the decision. Besides the grant, `Speak` needs **an account that
opens Astra** and **the person's reply voice on**; it is refused while Astra is
locked.

The call lasts as long as the speech and answers with what became of it:

| Outcome | What it means | What to do |
|---|---|---|
| `SPOKEN` | It was heard | Nothing |
| `STOPPED` | Silence was asked for before it finished: the wake word, reply voice turned off, Stop, your own `StopSpeaking` | Nothing — **it is not an error**. Do not say it again unasked |
| `NOT_SPOKEN` | It was not said; `error` (the same `PluginError` a chat chunk carries) says why | Read the code below. Nothing refused is queued |

| `error.code` | When |
|---|---|
| `PLUGIN_ERROR_BAD_ARGUMENTS` | The text is empty once invisible characters are removed, or longer than **300 characters** (`speak_text_max_chars` in `spec/limits.yaml`). A longer text is refused, never cut |
| `PLUGIN_ERROR_RATE_LIMITED` | Your speaking time is used up. It is budgeted in characters — **450 at once, then 3 a second**, each call costing at least 20 — and `retry_after_ms` says when there is room again |
| `PLUGIN_ERROR_UNAVAILABLE` | The person turned Astra's voice off, Astra is locked, there is no voice, or the speech queue could not take it. Show the text instead; do not ask the person to change it |

Your words queue behind your own earlier ones, on a lane of their own, so they
never cut one of Astra's replies. `StopSpeaking` stops everything you asked to be
said, sounding and queued, and nothing else; it shares the `speak` permission,
and works whether or not anybody is signed in. The limits are the daemon's: the
SDKs export `SPEAK_TEXT_MAX_CHARS` so you can show a counter, and check nothing
themselves. An Astra older than this call answers `UNIMPLEMENTED`.

## Knowing who is using Astra

A plugin that limits use per person or per machine — a trial, a quota, a
licence — needs a stable id for each. **Ask Astra; never read a hardware serial
or Astra's files.** Declare `read_user_identity` and call `GetUserIdentity`
(`get_user_identity()` in Rust and Python, `ctx.getUserIdentity()` in
TypeScript):

| Field | What it is |
|---|---|
| `install_id` | This installation of Astra: the same across restarts and updates of Astra and of your plugin, different on another installation. Empty while Astra has no installation key yet |
| `signed_in` | A person is signed in to Astra |
| `authorized` | …and their account opens Astra |
| `account_id` | The signed-in account: the same on every device the person signs in on. Empty unless `authorized` |

Both ids are **pseudonyms made for your plugin alone**: another plugin reads
different ids for the same person and the same machine, so two plugins cannot
join their records on them. That holds against plugins that use this API
honestly: native plugin code can read Astra's files. Neither is a secret, and neither is ever the
account's own id, the person's name or email, or a hardware serial. It is not
high-risk and not refused to a local import: it is the honest alternative to a
machine serial, and pricing it high would push a plugin back to one. An Astra
older than this call answers `UNIMPLEMENTED`.

**`auth_changed` is narrowed to match** (Astra, 2026-11-12). A plugin granted
the `auth_changed` event used to receive the account's own id, the person's
display name and their plan. It now receives `authenticated`, `authorized`,
`timestamp` and `account_id` — the same pseudonym `GetUserIdentity` answers, and
`""` unless you hold `read_user_identity` and the account opens Astra.
`user_id` and `user_name` still arrive, as `null`, and `subscription_tier` as
`""`, so a parser written for the old shape keeps parsing; none of them carries a
value any more.

## Receiving the pictures the person attached

A tool that works on a picture — reading a receipt, naming a plant, describing a
photo — can ask for the pictures the person attached to the message Astra is
answering. **No Astra release does this yet:** the daemon sends them only when
it is built with the `plugin-provider-slots` build feature. Any other Astra
ignores the request and your tool receives no pictures.

Two things are needed. Declare `receive_attachments` in `[permissions]`, and mark
each tool that wants pictures; then read them in its handler:

| SDK | Mark the tool | Read the pictures |
|---|---|---|
| Rust | `#[tool(wants_attachments)]`, or `ToolDef::new(…).with_attachments(true)` | `ctx.attachments()` |
| Python | `@tool("…", wants_attachments=True)`, or `ToolDef(…, wants_attachments=True)` | `current_attachments()` |
| TypeScript | `wantsAttachments: true` in `tool({…})` or on a `ToolDef` | `ctx.attachments`, or `currentAttachments()` |

Each picture carries `mime_type` (`mimeType` in TypeScript), `data` — the bytes —
and `filename`, the bare name it was attached under, never a folder. A tool that
did not ask reads an empty list, and so does any call that carries no pictures.

Astra hands pictures to a call only when all of these hold:

- the tool declared `wants_attachments` in its `ListTools` answer;
- your plugin holds `receive_attachments`;
- the call was made while answering a message the person sent in a conversation
  — the call's invocation names that conversation. Never in a report wake, a
  command's AI step or a sub-agent's turn, and never while Astra holds the turn
  for a Workshop command the person has not approved.

What arrives is only what was attached to **that one message**: never a picture
from earlier in the conversation, never one a tool produced and never one the
model named. At most **4** (`image_input_max_images` in `spec/limits.yaml`) and
20 MiB in all, the newest kept, in the order they were attached; a picture that
cannot be read is never sent. When some were not sent — more than fit, or your
plugin lacks the grant — the **model** is told so after your result; your tool
simply receives fewer, or none.

Today Astra's chat composer scales every attached picture to at most 768 pixels
and re-encodes it as JPEG, keeping the original file name, so that is what your
tool receives. Go by `mime_type`, not by the extension in `filename`.

A call can carry up to 20 MiB of pictures, more than gRPC's default 4 MiB
receive limit. The three SDKs' capability servers receive up to 64 MiB
(`plugin_max_message_bytes`); a plugin that serves the protocol without an SDK
must raise its own server's receive limit above 4 MiB.

`receive_attachments` is **high-risk**: a person's photos reach code that is not
Astra's, so it gets its own consent checkbox. It is not refused to a local
import — the checkbox is the decision, as for `speak`.

## Asking the person to change a setting

A plugin with a real reason to want one of Astra's settings changed — a model its
tools are tuned for, a voice that suits it — **asks**, and the person decides on a
card. Never write Astra's `settings.json` yourself, and never borrow Astra's own
session to do it: that changes the person's Astra behind their back, and human
review at publication looks for it. Declare `request_settings_change` and call
`RequestSettingsChange` (`request_settings_change(changes, reason)` in Rust and
Python, `ctx.requestSettingsChange(changes, reason)` in TypeScript). **No Astra
release answers it yet:** the daemon takes requests only when it is built with
the `plugin-requests` build feature; any other Astra answers `REFUSED` with the
code `not_compiled`.

Each change is a dotted settings path and the value wanted, as JSON — the SDKs
serialise the value for you. Only the settings the assistant itself may change
can be asked for — the voice, the AI model, the language; never the permission
mode, a key or Tool Search — and each value is checked exactly as the
assistant's own change is. The card names your plugin, shows every setting as it
is and as it would be, and your `reason`, in your words. All of them change, or
none, and what changes is exactly what the card showed.

**The call lasts until the person answers or the card expires** — Astra's
confirmation timeout, at least 30 seconds, 120 unless the person changed it. The
SDKs put no deadline of their own on it. Never await it on a path that must
answer quickly, such as a tool call the model is waiting on.

| Outcome | What it means | What to do |
|---|---|---|
| `APPLIED` | The person allowed it; the settings now hold what you asked for | Nothing |
| `UNCHANGED` | They already held it. Nobody was asked | Nothing |
| `DECLINED` | The person said no — now, or to your plugin changing one of these settings before. Astra asks again about such a setting only after it has changed some other way, or after a restart | Carry on with what the person has. **Do not ask again unasked** |
| `TIMED_OUT` | Nobody answered before the card expired (no window open counts) | Ask later, when the person is there |
| `REFUSED` | Not asked, or not applied: `code` says why, `refused_path` names the setting when it is about one, and `error` is a `PluginError` | Read the code below |

| `code` | When |
|---|---|
| `not_compiled` | This Astra takes no requests: it was built without the `plugin-requests` feature |
| `locked` | Astra is locked by its passcode |
| `invalid` | No changes, a path given twice, a value that is not JSON, or more than a card can show whole |
| `too_many` | More than **8** changes (`settings_change_max_changes` in `spec/limits.yaml`) |
| `reason_too_long` | A reason longer than **140 characters** (`settings_change_reason_max_chars`). It is shown whole, so it is refused, never cut |
| `busy` | One of your requests is already waiting for the person: one card per plugin at a time |
| `rate_limited` | **Two requests at once, then one every two minutes**; `error.retry_after_ms` says when there is room again |
| `not_assistant_editable` | A path the assistant may not change |
| `invalid_value`, `unknown_choice` | A value the setting cannot hold, or a choice it does not offer |
| `needs_api_key`, `needs_stt_provider`, `provider_unreachable` | The change would leave Astra without what it needs: a key for that AI provider, a speech recogniser, a provider that answers |
| `stale` | The settings changed while the card was up, so what the person allowed is not what would be written. Nothing was |
| `stopped` | Your plugin's authority ended first — it was stopped, disabled or withdrawn, or the account stopped opening Astra |
| `write_refused` | The settings could not be written |

The current values are never returned: what your plugin learns is the outcome.
The limits are the daemon's: the SDKs export `SETTINGS_CHANGE_MAX_CHANGES` and
`SETTINGS_CHANGE_REASON_MAX_CHARS` and check neither themselves. Besides the
grant the call needs **an account that opens Astra**; a missing grant, or an
account that does not open Astra, is a failed call like every host call, not an
outcome. It is neither
high-risk nor refused to a local import: each request is a card the person
answers, so the consent is asked every time. An Astra older than this call
answers `UNIMPLEMENTED`.

## Sending a chat message

`send_chat_message` is the only path a plugin has into a conversation, and two
things decide what your call actually does: **where the message lands**, and
**what happens if Astra is already busy**.

### Where it lands

**Leave `conversation_id` empty.** The message goes to your plugin's own durable
thread — one thread per plugin, kept across calls — so a series of messages
reads as one conversation instead of a pile of one-line chats.

Say plainly what this replaces, because a version of this contract you may have
read said the opposite. `conversation_id` was documented, in the protocol and in
two of the three SDKs, as *"empty = the active conversation"*. There has never
been an active conversation to send to: Astra deliberately exposes no way to ask
which conversation the user is looking at, and an empty id was read as *start a
new one*. So every message a plugin sent opened its own chat, titled with that
message, and the model answered each one holding no memory of the one before.
The plugin that surfaced it was a Minecraft bridge: every sentence a player
typed in game chat became its own Astra thread.

Pass an id **only** to answer inside a conversation you were actually told
about. There are two ways to be told, and no third: the chunks of a reply you
are streaming right now carry `conversation_id`, and a tool call or an action
carries the conversation that invoked it — see below. Anything else is a guess,
and there is no API for the guess on purpose.

### Answering in the conversation that called you

When the model calls one of your tools or runs one of your actions from inside a
conversation, the daemon tells you which conversation that was. **You may store
that id, including across restarts, and send it back later.** That is what the
field is for: a plugin asked in one chat to go and do something can come back to
that same chat with the answer, as itself, minutes or hours later.

In Rust that is `ctx.invocation()`, and `.conversation()` on what it returns.
In TypeScript it is `ctx.invocation?.conversationId`, or `currentInvocation()`
where no context is to hand. In Python it is `current_invocation()`, then
`.conversation_id`.

**Absent is the common answer, and it is not a cue to guess.** You get nothing
when the call was not made from a conversation at all — a trigger, a timer, your
own UI — when the call has a cause the daemon holds no lease for, such as a
nested sub-agent or a command's *send to AI* step, and when the daemon in front
of you predates the field. All three arrive identically, and the right response
to all three is the same: leave `conversation_id` empty and post to your own
thread.

**Never await a send into the conversation that is calling you, from inside that
call.** That conversation is still running the turn that invoked you. Your
message declares an intent for the *next* turn, so it queues behind the one
waiting for your answer, and the tool call times out. Hand the send to a
detached task, or do it later — `examples/dice-roller` ships the idiom.

A conversation can be deleted while you hold its id. The send fails with a
distinct, catchable answer rather than silently going somewhere else:

A `NOT_FOUND` whose message begins `conversation_gone:` says it was deleted:
forget the id and fall back to your own thread. An `INVALID_ARGUMENT` says the
id is not a UUID, or names a chat an Astra surface owns. A message that was
accepted and then outlived its chat ends the stream with an error chunk whose
`error_detail.code` is `PLUGIN_ERROR_NOT_FOUND`. A daemon older than this
contract reports that same situation as `INTERNAL`, *"chat processing failed:
conversation … does not exist"*.

Leaving the field empty remains correct on every version, and is still the right
default for anything that is not an answer to a specific call.

### What happens if Astra is busy

An arriving message declares an **intent**; the turn in flight names the
**boundary**. Nothing is injected into a turn that is already running — a
message you send mid-turn begins the *next* one. Your call resolves exactly once,
in one of three shapes, and they are distinguishable without a flag:

| What you see | What it means | What to do |
|---|---|---|
| The stream opens and stays quiet, then answers | Queued behind work in flight. It will be delivered at the turn boundary | Nothing. Carry on as normal |
| The stream opens and ends with an error chunk naming a reason | Parked, then dropped. It will not be delivered | Report it. Do not retry blindly |
| No stream at all — the call fails before one appears | Refused outright | Back off |

The three demand opposite reactions, which is why they are three shapes and not
one status field: *queued* means wait, *dropped* means say so, *refused* means
slow down.

A drop names its reason. **`Evicted`** — the conversation's parked queue was
full and the **oldest** waiting message was discarded, not the newest, because
the newest line is the one the model needs and the one somebody is still waiting
on. **`ConversationDeleted`** and **`NotStarted`** are what they say.

**`Locked`** is the one worth reading twice: a locked Astra answers your message
with a refusal rather than holding it. That looks harsh and is the kinder
choice. A locked daemon starts no turns at all, so "the next boundary" is the
first turn *after* the user comes back and types their code — your line would
surface in the middle of something else, hours later, with nothing on screen
having said it was still pending.

The parked queue holds **8 messages per conversation**, and the small number is
deliberate. A queue is a person who has decided to wait, and a person does not
type nine things while waiting for one answer. Nine is reachable only by a
client in a loop, and the ceiling exists so that a loop cannot turn into
unbounded memory holding somebody's words.

**The stream always ends**, including in the case that used to be silence. A
line that reached the conversation but that no turn will ever answer ends the
stream with an error chunk — `INTERNAL`, *"this message reached the conversation,
but no turn will answer it"* — and its hint says the same thing the shape does:
**do not resend**. The message is not lost and sending it again would post it
twice.

**Your text is text, never a command.** A message beginning `/` — `/help`,
`/reset`, anything — reaches the model as those literal characters. A plugin
cannot invoke a slash command by writing one, and cannot supersede a person's
turn by writing one either. Sending `/stop` stops nothing; it says the word.

**The pattern that is right on every daemon**: wait for `done` before sending
again. On builds older than the queue, a message sent while a turn was running
cut that turn short — a tool call in flight was abandoned and its result never
reached the log. Waiting for `done` was the fix then and costs nothing now.

## Arguments

Two ids take arguments, and both narrow what you get.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "meeting-notes"
name = "Meeting Notes"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/meeting_notes"

[capabilities]
tools = true
event_handlers = true

[permissions]
subscribe_events = { types = ["command_completed", "state_changed"], reason = "Notices when a recording command finishes so it can write the summary" }
set_variable = { scopes = ["plugin"], reason = "Stores the id of the note it just wrote so your commands can open it" }
fire_trigger = { reason = "Fires meeting_summarised when a summary is ready" }
```

- **`subscribe_events.types` is an allowlist, enforced by the daemon** — not by
  the filter your plugin sends. Without it, every subscriber received every
  event, including `speech_recognized`, which carries the user's transcripts.
  An empty list allows nothing.
- **`set_variable.scopes`** is `"plugin"`, `"session"` or `"persistent"`.

**One event type is accepted and never delivered: `update_state_changed`.** It
is a real member of the event enum, so naming it in `types` is accepted at
every gate — the CLI, the registry and the daemon's own grant all take it — and
then nothing ever arrives. Your plugin waits for ever, with no error anywhere
to say why.

The reason is not an oversight in the delivery path. That event is the doorbell
for the update block of `GetState`, and the pattern is *ring, then re-read the
document*. A plugin cannot re-read it: every plugin session token is scoped to
`PluginHostService`, so `GetState` is refused by construction. Delivering the
doorbell would tell a plugin only the timing of somebody's sign-in and of their
Check / Update / Later presses, with nothing it could act on — so it is
withheld on purpose.

Nothing on this side can warn you, and that is worth saying plainly rather than
implying a check exists. `types` is a list of free-form strings here; the
vocabulary of what each name means, and of which names reach a plugin at all,
lives in the daemon. Until that vocabulary can mark an event non-deliverable,
this paragraph is the only thing between an author and a subscription that
silently never fires.

## Writing a reason

The `reason` is rendered below Astra's own label for the permission, visually
subordinate, quoted, plain text, capped at 140 characters, and always prefixed
*"The author says:"*. The label is Astra's, in the user's language; the reason
is yours. You cannot craft the label, which is deliberate — wording fixes ship
with Astra and must not be writable by a listing.

A good reason:

- **names the feature the user recognises**, not the API — *"Fires the
  on_dice_roll trigger you configure"*, not *"calls FireTrigger"*;
- **says when**, if it is not always — *"only while a recording is in
  progress"*;
- **does not restate the label.** Astra already rendered it;
- **does not push.** No urgency, no threats, no instructions to the user. A
  consent sheet is the last place to make an exception, and text with bidi
  overrides or zero-width joiners is refused where it is displayed verbatim.

| Instead of | Write |
|---|---|
| `"needs fire_trigger"` | `"Fires the trigger you configure when a roll completes"` |
| `"required for the plugin to work"` | `"Reads command-completion events so it can log the run"` |
| `"full access to the UI"` | `"Draws the timer in the panel this plugin adds to the sidebar"` |
| `"REQUIRED! Do not disable!"` | — remove the permission, or say what it is for |

A permission with no plausible reason is a permission to delete from the
manifest. Nothing checks that automatically; a person reading your listing is
the only backstop, and `astra-plugin check` will tell you when you have declared
a permission your capabilities do not need.

## What happens when a permission is missing

The call comes back `permission_denied`, with a message naming the permission
**and** where the granted set came from. In a test you can stage exactly that:

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Notifier;

#[astra::plugin]
impl Notifier {
    /// Announce that something happened.
    #[tool]
    async fn announce(&self, ctx: &PluginContext) -> Result<String, ToolError> {
        // Handle the denial rather than propagating it: a tool that returns an
        // error the model cannot act on is worse than one that says what it did.
        match ctx.host().fire_trigger("announced", "{}").await {
            Ok(()) => Ok("announced".into()),
            // `{e:#}` and not `{e}`: the host call fails with a short outer
            // message and the useful half — the permission id and where the
            // granted set came from — is in the cause chain.
            Err(e) => Ok(format!("could not fire the trigger: {e:#}")),
        }
    }
}

astra::main!(Notifier::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn a_missing_grant_is_reported_not_hidden() {
        let h = Harness::new(Notifier::default()).start().await.unwrap();
        h.host().deny("fire_trigger");

        let answer = h.call_tool("announce", json!({})).await.unwrap();
        assert!(answer.contains("fire_trigger"), "{answer}");
    }
}
```

`astra-plugin doctor` answers the same question about a manifest before you
ever run it:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## Where the granted set comes from

| Install path | Granted |
|---|---|
| From the store, verified | what the manifest asked for, after consent |
| A `.astraplugin` file imported by hand | the manifest, **capped**: `send_chat_message`, `set_theme_contribution`, `dom_access`, `client` are refused outright |
| A sideloaded source directory, Developer Mode on | the manifest, uncapped |
| `Untrusted` / `TamperDetected` / `Revoked` | nothing |
| Installed before trust records existed | the manifest, capped as an imported file |

Full table and the reasoning: [`spec/permissions.md` §4](../spec/permissions.md).

## Consent, from the user's side

Permissions are grouped by risk. The seven high-risk ones each get their own
checkbox and Install stays disabled until every one is ticked; `dom_access` gets
a second screen. There is deliberately **no type-to-confirm**: that is the
pattern for irreversible destruction, and habituating users to type through it
destroys the signal the checkbox carries.

On an update: permissions unchanged or narrowed applies silently; permissions
**widened** stages the update without installing it and keeps the old version
running until the user reviews the delta. Declining costs nothing.
