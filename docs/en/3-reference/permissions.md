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
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client
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

## The eight ids

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

`dom_access` and `client` gate no RPC and that is the point: they are
**surfaces**. `dom_access` decides whether a UI contribution is rendered as a
script in the Astra window or a sandboxed iframe; `client` is a ceiling on what
a plugin may be. They are refused where the surface is handed out, not at a call
gate.

`dom_access` additionally gets a second consent screen. If you are reaching for
it, read [the security model](../1-orientation/security.md) first and be sure
`push_to_ui` into your own panel will not do.

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

Pass an id **only** to answer inside a conversation you were told about in the
same exchange — `conversation_id` arrives on the chunks of a reply you are
streaming right now. **Do not store one and send it back later.** Threads rotate
and are pruned, so a stored id eventually names a conversation that is gone, and
what happens then depends on how old the daemon in front of you is. Leaving the
field empty is correct on every version.

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

Permissions are grouped by risk. The five high-risk ones each get their own
checkbox and Install stays disabled until every one is ticked; `dom_access` gets
a second screen. There is deliberately **no type-to-confirm**: that is the
pattern for irreversible destruction, and habituating users to type through it
destroys the signal the checkbox carries.

On an update: permissions unchanged or narrowed applies silently; permissions
**widened** stages the update without installing it and keeps the old version
running until the user reviews the delta. Declining costs nothing.
