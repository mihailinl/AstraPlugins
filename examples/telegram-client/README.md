# Telegram Bot

Talk to Astra from Telegram. What you send goes into an Astra conversation as
if you had typed it in the app, and the reply appears in Telegram as it is
written.

## What it does

- **Any message** you send the bot goes to Astra, and the answer streams back
  as it is written — through `sendMessageDraft`, the method Telegram added for
  exactly this, so the text animates in the way its own AI assistant does
  rather than jumping once a second. Telegram's "Thinking…" covers the wait
  before the first word. Drafts are a **private-chat** method; in a group the
  bot falls back to posting one message and rewriting it about once a second,
  which is what every Telegram client has always supported.

  A draft is a preview, not a message — it expires on its own in about thirty
  seconds. What stays in the chat is the finished answer, sent normally once
  the stream is done.
- **`/new`** starts a new conversation: the next message begins with no memory
  of what came before. The old one stays in Astra's sidebar — the plugin never
  deletes anything.
- **Stopping a reply.** A streaming draft carries Telegram's own **Stop**
  button, and `/stop` does the same for a chat that has no draft to put one on.
  Whatever had arrived by then is delivered as a message, marked stopped.

  What stopping means here is worth being exact about: the bridge lets go of the
  reply stream. It cannot tell Astra to abandon the turn — `StopGeneration` is
  on `ChatService`, refused to a plugin like the rest of it — so whether the
  daemon drops the work or finishes it unheard is the daemon's call about a
  cancelled stream.
- **`/screenshot`** sends a picture of this machine's screen into the chat.
  **Windows only**, and **off until you switch it on** — see below for both.
- **`/help`** repeats the short version of this page inside the chat.
- A long answer is **split** across as many messages as it takes, at a line
  break where there is one.

The interface is translated — English and Russian ship with it, following
Astra's language setting.

## One conversation, and why

The bridge holds **one Astra conversation at a time**, not one per Telegram
topic. That is a limit of what a plugin may do, not a simplification:

`PluginHostService.SendChatMessage` is the only way a plugin can reach a
conversation. The daemon registers every plugin as `ClientType::PluginClient`
and its auth interceptor refuses that identity on any gRPC path outside
`/astra.PluginHostService/`, so `ChatService.ListConversations` and
`CreateConversation` — the two calls a topic-per-conversation bridge needs —
answer `permission_denied` whatever the manifest says. Version 0.1 of this
plugin was built on them and could not send a single message.

The conversation Astra opens is a normal one: it is in the sidebar, you can
open it, read it and carry on typing in it from the desktop. What you type
there does not appear in Telegram — a plugin cannot subscribe to conversation
events either — so the bridge is one-way in that sense: Telegram in, replies
back.

**Tool calls are invisible here, for the same reason.** `PluginChatChunk`, the
only thing `SendChatMessage` streams back, carries text, `done` or an error and
nothing else; the events that name a tool — `ToolCallStartEvt`,
`ToolCallResultEvt` — are `ConversationEventMsg` variants on `ChatService`'s
firehose, and `PluginHostService.SubscribeEvents` says so in the proto: *chat-log
events travel through `ChatService.SubscribeEvents`, NOT through this stream*.
So while Astra runs a tool the bridge can say that something is happening, and
cannot say what: the streaming draft is held open through the silence rather
than left to expire.

## What it needs

1. **A Telegram bot token.** Talk to [@BotFather](https://t.me/BotFather),
   create a bot, copy the token into the plugin's settings.
2. **Outbound network access** to `api.telegram.org`.

A private chat with the bot is enough; a group works too, and in a forum group
the bot answers inside the topic you wrote in. The bot binds to the **first
chat that talks to it** and ignores every other one from then on.

Optionally set **Allowed Usernames** to a comma-separated list of Telegram
usernames (no `@`). Leave it empty and *anyone who can reach the bot can talk to
your Astra* — including anyone who is added to the group later. Setting it is
the difference between a personal bridge and an open door.

## What it asks for, and why

| | What it means | Why this plugin asks |
|---|---|---|
| `client` (capability + permission) | The plugin is a chat front-end | `spec/hooks.yaml` files `SendChatMessage` under this capability |
| `send_chat_message` (permission) | Drive an AI turn as if the user had spoken | That *is* the feature |

`send_chat_message` is high-risk and Astra will say so before installing, with
its own checkbox. Be concrete about what installing this means: **what Astra
replies is relayed to Telegram**, therefore to Telegram's servers, therefore to
anyone with access to that chat. That is the intended behaviour and it is not
reversible for messages already sent.

The bot token is stored in the plugin's configuration. The chat it is bound to
and the conversation it is talking into are written to a `state.json` beside the
plugin binary in Astra's plugin directory.

## Configuration

| Setting | Required | Meaning |
|---|---|---|
| Bot Token | yes | The token from @BotFather |
| Allowed Usernames | no, but read the warning above | Comma-separated Telegram usernames permitted to use the bot. Empty means everyone |
| Allow `/screenshot` | no, **off by default** | Whether `/screenshot` works at all. Windows only. Read the section below before turning it on |

## `/screenshot`, why it is off, and why it is Windows only

Everything else this bridge does is a conversation with an AI. This is a live
picture of the desktop — whatever is on screen at the moment the command
arrives, sent to Telegram's servers and to everyone who can see that chat.
Anyone who may talk to the bot may run it, so with **Allowed Usernames** empty
that is anyone who finds the bot. Fill that in first; the two settings are
meant to be read together.

The picture is taken by the plugin itself, not by Astra. Astra can do it —
`MediaService` carries *"Capture a PNG screenshot of the requested monitor"* —
but that is a daemon service, and a plugin's session token is refused outside
`PluginHostService`, the same wall as the chat firehose. What lets the plugin
do it anyway is that a sideloaded plugin is a native process running as you,
with no sandbox; Astra's [security page](../../docs/en/1-orientation/security.md)
says so in as many words, under *what is not defended against*. So the switch
here is the whole of the protection, which is why it defaults to off.

Only the primary monitor is captured. The file is written to the system
temporary directory and deleted once Telegram has it, whether the upload
succeeded or not.

**Windows only, for now.** The capture library needs PipeWire and libxcb on
Linux, both as `-sys` crates, and a binary that links them does not start at
all where those shared objects are missing — so the Linux build would trade a
bridge that needs no display, and no system package, for one that cannot load
on a headless machine, in exchange for a command that ships switched off. On
Linux the command answers that it is unavailable and nothing else about the
bridge changes. Lifting this means capturing through X11 directly rather than
installing the packages, and that is a later version.

## Build it yourself

```bash
cd examples/telegram-client
cargo build --release
astra-plugin build
```

## Files

- `src/main.rs` — lifecycle, config, and starting/stopping the poll loop.
- `src/telegram.rs` — the Bot API client: send, draft, edit, long-poll.
- `src/bot.rs` — update handling, the commands, and the reply stream.
- `src/screen.rs` — capturing the screen for `/screenshot`, and the platform line.
- `src/state.rs` — the bound chat and the current conversation, persisted.
- `src/types.rs` — config, and what the three shapes of `conversation_id` mean.
- `locales/` — English and Russian, and both planes in one plugin: the
  `$config.*` keys `plugin.toml` references, which the daemon resolves for
  the settings form, and the `bot.*` keys this process resolves itself with
  `I18n`. See [the localisation page](../../docs/en/3-reference/localisation.md).
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
