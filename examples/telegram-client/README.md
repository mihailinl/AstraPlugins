# Telegram Bot

Talk to Astra from Telegram. What you send goes into an Astra conversation as
if you had typed it in the app, and the reply appears in Telegram as it is
written.

**Every chat has its own conversation.** Your private chat with the bot, a group
you added it to, and each topic of a forum group are separate conversations in
Astra's sidebar, each with its own memory — and each answered at the same time
as the others, so a long reply in one chat does not keep another waiting.

**And a new conversation can have a new place to live.** Telegram's own **New
chat** button opens one and takes you straight to it; `/new` opens one by
command; `/clear` starts over where you already are. **However it was opened,
the first message written in it becomes its name** — the same name the
conversation gets in Astra.

## What it does

- **Any message** you send the bot goes to Astra, and the answer streams back
  as it is written — through `sendMessageDraft`, the method Telegram added for
  exactly this, so the text animates in the way its own AI assistant does
  rather than jumping once a second. Telegram's "Thinking…" covers the wait
  before the first word, including the wait while Astra finishes a turn it was
  already running in that conversation. Drafts are a **private-chat** method; in
  a group the bot falls back to posting one message and rewriting it about once
  a second, which is what every Telegram client has always supported.

  A draft is a preview, not a message — Telegram calls it a thirty-second
  preview and expires it on its own. What stays in the chat is the finished
  answer, sent normally once the stream is done.
- **`/new`** opens a new conversation **in a chat of its own**. That is what "a
  new chat" means in an app showing one chat at a time: not only a conversation
  with no memory, but a place to hold it, so two of them sit side by side in
  Telegram the way they do in Astra's sidebar. The chat the command was typed in
  is left exactly as it was.

  **Where that is possible is Telegram's answer, not a guess.** `createForumTopic`
  is no longer only a group method: a bot with **topic mode** on has topics in its
  *private* chats too, and each is a chat of its own in the Telegram client. So
  `/new` asks, and uses what comes back — a topic in your private chat with the
  bot, a topic in a forum group, or a plain refusal. Reading `chat.is_forum`
  first would have been wrong in exactly the case this is for: `getChat` on a
  private chat with topic mode answers **no** `is_forum` at all.

  The new topic is born named "New chat", because Telegram wants a name before
  there is a message to take one from, and **the first message written in it
  renames it** — by the same rule Astra titles a conversation by, so the topic
  list and the sidebar read alike.

  A refusal is answered by what can be done about it: in a **private chat** topic
  mode is a setting of the bot itself, so nothing here can help and `/new` starts
  this chat over instead and says so; in a **group** either Topics are off or the
  bot is not an administrator with *Manage topics*, both of which the group's
  owner can change, so that is reported rather than quietly turned into a
  `/clear`.

  **`/new` cannot take you to the chat it opened, and nothing can.** The Bot API
  has no method that moves a client's view, and there is no `t.me` link form for a
  topic of a private chat — Telegram's deep-link reference has one for a group's
  topics and none for a bot's. So the reply says where the new chat is (with a
  link, where a link exists) and you open it. Telegram's own **New chat** button
  is the one path that opens a chat *and* takes you there, which is why it is not
  a worse way to do this: a chat opened that way gets its name from its first
  message exactly as `/new`'s does, because Telegram marks the name it gave as a
  placeholder and the bridge reads that mark.
- **`/clear`** starts **this** chat's conversation over, where it is: its next
  message begins with no memory of what came before, and **every other chat is
  left exactly where it was**. In a topic, that message renames the topic too —
  the name in the list is the name of the conversation in it, and that is now a
  different conversation. The old conversation stays in Astra's sidebar — the
  plugin never deletes anything.

  One caveat worth stating rather than discovering: Telegram lets a bot rename a
  topic it **created** (so `/new`'s always), and for one a person created itself
  the rule is the chat's own — if it refuses, the conversation still starts over
  and only the name stays as it was, which the plugin log says in as many words.
- **Stopping a reply.** A streaming draft carries Telegram's own **Stop**
  button, and `/stop` does the same for a chat that has no draft to put one on.
  Whatever had arrived by then is delivered as a message, marked stopped. A stop
  reaches the reply in the chat it was pressed in and no other.

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

## A conversation per chat, and where the line is

Each Telegram chat asks Astra to open a conversation the first time it is
written in, remembers the id the reply comes back on, and uses it from then on
until `/new`. The conversation Astra opens is a normal one: it is in the
sidebar, you can open it, read it, and carry on typing in it from the desktop.

What that costs and what it does not:

- **The plugin still cannot list or pick conversations.**
  `PluginHostService.SendChatMessage` is the only way a plugin reaches one. The
  daemon registers every plugin as `ClientType::PluginClient` and its auth
  interceptor refuses that identity on any gRPC path outside
  `/astra.PluginHostService/`, so `ChatService.ListConversations` answers
  `permission_denied` whatever the manifest says. Version 0.1 of this plugin was
  built on those calls and could not send a single message. What makes a
  conversation per chat possible is not a new call: it is that `SendChatMessage`
  reads the nil UUID as *open a fresh conversation* and then names the one it
  opened on every chunk of the reply, so the bridge can mint one per chat and
  remember which is which.
- **What you type in Astra does not appear in Telegram.** A plugin cannot
  subscribe to conversation events either, so the bridge is one-way in that
  sense: Telegram in, replies back.
- **There is no "current conversation".** Astra has no notion of which chat you
  are looking at and no way to ask, which is why each Telegram chat keeps its
  own id rather than following you around the app.
- **Tool calls are invisible here.** `PluginChatChunk`, the only thing
  `SendChatMessage` streams back, carries text, `done` or an error and nothing
  else; the events that name a tool — `ToolCallStartEvt`, `ToolCallResultEvt` —
  are `ConversationEventMsg` variants on `ChatService`'s firehose, and
  `PluginHostService.SubscribeEvents` says so in the proto: *chat-log events
  travel through `ChatService.SubscribeEvents`, NOT through this stream*. So
  while Astra runs a tool the bridge can say that something is happening, and
  cannot say what: the streaming draft is held open through the silence rather
  than left to expire.
- **A chat is named by whoever did not choose its name.** A topic a person
  created and titled keeps that title, in a group or anywhere else: Telegram says
  which names were its own (`is_name_implicit` on the topic-created service
  message) and only those are replaced. The threads Telegram's client opens for a
  bot with topic mode are all of them, which is why the name it gives is worth
  replacing and a human's is not.
- **Astra names each conversation from the first message in it**, and so does
  this bridge name the topic: the daemon keeps the first 40 characters of that
  message (`conversation_cache::derive_conversation_title`) and the plugin
  applies the same rule to the topic name, so one conversation has one name in
  both lists. A plugin still cannot *title* an Astra conversation — there is no
  call for it — which is why the two agree by deriving the same thing rather than
  by one copying the other.
- **If you delete a conversation in Astra**, the chat that was using it opens a
  new one on its next message. The daemon refuses a deleted id rather than
  redirecting the message somewhere nobody asked for, and that refusal is what
  the bridge reads.

The bridge serves up to 256 chats at once, and holds up to 16 messages per chat
while a reply is being written. Both are ceilings rather than policies: reaching
either is logged.

## What it needs

1. **A Telegram bot token.** Talk to [@BotFather](https://t.me/BotFather),
   create a bot, copy the token into the plugin's settings.
2. **Outbound network access** to `api.telegram.org`.
3. **For `/new` to open a chat of its own**, one of two things:
   - **in your private chat with the bot** — *topic mode* on for the bot, which
     is the bot's own setting (@BotFather) and shows up as
     `has_topics_enabled` on `getMe`. Nothing else; the bot creates and names the
     topics it opens.
   - **in a group** — Topics turned on for the group, the bot an administrator
     in it with **Manage topics**, and privacy mode off (`/setprivacy` →
     Disable in @BotFather), because a bot in a group otherwise sees only
     commands and replies.

   Without either, `/new` starts the conversation over where it was typed and
   says that is what it did.

## Who can talk to it

The bot answers in as many chats as it is written in, so *which chat* can no
longer be what keeps strangers out. Exactly one of two gates is in force:

- **Allowed Usernames, when you set it.** A comma-separated list of Telegram
  usernames. Anybody on it can use the bot, in any chat, including a group they
  add it to. This is the setting to use if more than one person should reach
  your Astra, or if you want to be explicit about who does.
- **The person who first talked to the bot, when you leave it empty.** One
  Telegram account, learned from the first message and remembered in
  `state.json`; every other account is ignored wherever it writes. Version 0.2
  bound itself to the first *chat* for the same reason — this keeps that
  protection while letting you have as many chats as you like.

So installing this version cannot widen who can reach your Astra, and updating
from 0.2 does not either: an install that was bound to one chat keeps that chat
as the gate until it has learned whose it is.

A message with no sender — a service message, an anonymous group admin, a
channel post — names no account to compare, and is ignored.

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

The bot token is stored in the plugin's configuration. The account it answers
and the conversation each chat is talking into are written to a `state.json`
beside the plugin binary in Astra's plugin directory.

## Configuration

| Setting | Required | Meaning |
|---|---|---|
| Bot Token | yes | The token from @BotFather |
| Allowed Usernames | no — read *Who can talk to it* above | Comma-separated Telegram usernames permitted to use the bot, in any chat. Empty means the one account that first talked to it |
| Allow `/screenshot` | no, **off by default** | Whether `/screenshot` works at all. Windows only. Read the section below before turning it on |

## Streaming, and when it stops streaming

Two things decide whether a reply animates as it is written, and they are kept
apart on purpose, per chat:

- **What kind of chat it is.** `sendMessageDraft` takes "the target private
  chat", so a group, supergroup or channel is answered by posting a message and
  rewriting it instead. The bridge reads the chat's own type off the message
  rather than finding out by being refused.
- **What Telegram says when it refuses a draft.** A `400` about the chat is a
  settled answer and drafts stop being tried there; a `429` is a pace limit and
  pauses them for as long as Telegram asked; anything else — a dropped
  connection, a `502`, a body that did not parse — costs one frame of an
  animation and nothing more.

That split is what version 0.2 did not have: one flag for the whole bot, turned
off by the first refusal of any kind, which made a single timed-out request drop
a whole reply back to a rewritten message with no Stop button on it. From the
outside that was "sometimes the answer arrives in one piece and there is nothing
to press", intermittently.

Whether a reply animated or not, the finished answer is delivered the same way:
as ordinary messages. That delivery is the one call worth retrying, because what
the model wrote is in hand and nowhere else that lasts — so a refusal that
waiting could change is tried once more, after the delay Telegram asked for.

## `/screenshot`, why it is off, and why it is Windows only

Everything else this bridge does is a conversation with an AI. This is a live
picture of the desktop — whatever is on screen at the moment the command
arrives, sent to Telegram's servers and to everyone who can see that chat.
Anyone who may talk to the bot may run it, so fill in **Allowed Usernames**
first, or know that the one account the bot bound itself to is the whole of the
protection; the two settings are meant to be read together.

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
- `src/telegram.rs` — the Bot API client: send, draft, edit, long-poll, and what
  a refusal from Telegram means.
- `src/bot.rs` — routing each update to the chat it belongs to, a task per chat,
  the commands, naming a topic, and the reply stream.
- `src/screen.rs` — capturing the screen for `/screenshot`, and the platform line.
- `src/state.rs` — the account the bot answers, a conversation per chat, and
  which chats are waiting to be named, persisted.
- `src/types.rs` — config, what a chat is addressed by, and what the three
  shapes of `conversation_id` mean.
- `locales/` — English and Russian, and both planes in one plugin: the
  `$config.*` keys `plugin.toml` references, which the daemon resolves for
  the settings form, and the `bot.*` keys this process resolves itself with
  `I18n`. See [the localisation page](../../docs/en/3-reference/localisation.md).
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
