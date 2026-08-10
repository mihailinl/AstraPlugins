# Telegram Bot

Talk to Astra from Telegram. Each conversation becomes a topic in a Telegram
forum group, and both sides stay in sync.

## What it does

Bridges a Telegram bot to Astra as a full chat client:

- **`/new [title]`** creates a forum topic and a matching Astra conversation.
- **`/list`** shows Astra conversations that are not linked to a topic yet and
  links the one you pick.
- Any message you send in a linked topic goes to Astra as if you had typed it in
  the app, and the reply streams back into the topic as it is generated.
- Sync runs both ways: a conversation you continue in the Astra window appears in
  its Telegram topic, and vice versa.

The interface is translated — English and Russian ship with it, following
Astra's language setting.

## What it needs

1. **A Telegram bot token.** Talk to [@BotFather](https://t.me/BotFather),
   create a bot, copy the token into the plugin's settings.
2. **A Telegram group with Topics enabled**, with your bot added as an
   administrator. Topics are how conversations are kept apart; a plain group
   will not work.
3. **Outbound network access** to `api.telegram.org`.

Optionally set **Allowed Usernames** to a comma-separated list of Telegram
usernames (no `@`). Leave it empty and *anyone who can reach the bot can talk to
your Astra* — including anyone who is added to the group later. Setting it is
the difference between a personal bridge and an open door.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `client` | The plugin acts as a full chat client: it may read your conversations, create new ones, submit messages as you, and subscribe to the live event stream | That *is* the feature — a bridge that could not read and write your conversations would not be a bridge |

`client` is a high-risk capability and Astra will say so before installing. Be
concrete about what installing this means: **your Astra conversations are
relayed to Telegram**, therefore to Telegram's servers, therefore to anyone with
access to that group. That is the intended behaviour and it is not reversible
for messages already sent.

The bot token is stored in the plugin's configuration, and the topic-to-
conversation mapping is written to a `state.json` beside the plugin binary in
Astra's plugin directory.

## Configuration

| Setting | Required | Meaning |
|---|---|---|
| Bot Token | yes | The token from @BotFather |
| Allowed Usernames | no, but read the warning above | Comma-separated Telegram usernames permitted to use the bot. Empty means everyone |

## Build it yourself

```bash
cd examples/telegram-client
cargo build --release
astra-plugin build
```

## Files

- `src/main.rs` — lifecycle, config, and starting/stopping the poll loop.
- `src/telegram.rs` — the Bot API client.
- `src/bot.rs`, `src/commands.rs` — update handling and the two commands.
- `src/sync.rs` — the firehose: Astra events to Telegram, streamed.
- `src/state.rs` — the topic mapping, persisted.
- `locales/` — English and Russian.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
