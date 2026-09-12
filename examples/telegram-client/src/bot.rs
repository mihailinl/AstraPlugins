use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use astra_plugin_sdk::proto::plugin_chat_chunk::Content;
use astra_plugin_sdk::{ChatStream, ToolError};
use frankenstein::types::{ChatType, Message};
use tokio::sync::{mpsc, watch};
use tokio_stream::StreamExt;
use tracing::{debug, info, warn};

use crate::telegram::{Incoming, MAX_MESSAGE_LENGTH, Refusal, TelegramApi};
use crate::types::{
    ChatKey, NEW_CONVERSATION, PLUGIN_THREAD, SharedConfig, SharedHost, SharedI18n, SharedState,
};

/// How often the message carrying a streaming reply is rewritten, where
/// rewriting is what the bridge is reduced to.
///
/// Telegram rate-limits edits per chat, and the old code called the API once
/// per token — which on a paragraph is a few hundred calls, most of them
/// throttled and dropped. A second between rewrites reads as live typing and
/// stays inside the limit whatever the model's token rate turns out to be.
const EDIT_INTERVAL: Duration = Duration::from_millis(1000);

/// How often a streaming draft is pushed.
///
/// Faster than [`EDIT_INTERVAL`] on purpose: that second is the per-chat
/// ceiling on *sending and editing messages*, and a draft is neither — it is
/// the method Telegram added for exactly this, so streaming at a readable rate
/// is what it is for rather than something to be careful about. The number
/// still does not have to be exactly right: if Telegram says too fast, the
/// answer is a pause ([`Drafts::note`]) rather than a feature switched off, and
/// the reply is delivered by `sendMessage` regardless.
const DRAFT_INTERVAL: Duration = Duration::from_millis(250);

/// How long the bridge waits in silence before pushing the draft again.
///
/// A draft expires on its own in about thirty seconds, and the longest silences
/// in a turn are the ones where something is definitely happening: Astra is
/// running a tool, and no text arrives until it comes back. Without this the
/// indicator would vanish from the chat precisely during the turns worth
/// waiting for. Re-sending the same text under the same `draft_id` starts the
/// clock again; twenty seconds leaves ten to spare.
const DRAFT_KEEPALIVE: Duration = Duration::from_secs(20);

/// A stop request naming nothing in particular — `/stop`, typed rather than
/// pressed. The button names the draft it belongs to; the command cannot, so it
/// means whichever reply is running in that chat.
const STOP_ANY: i32 = i32::MIN;

/// How many messages may wait in ONE chat while a reply is being rendered.
///
/// Small on purpose. Telegram holds what it has not been asked for, so a full
/// queue costs nothing but a pause in reading, and a bridge that buffered
/// hundreds of messages would answer them long after the person gave up. It is
/// per chat now, so one chat's backlog is never another chat's wait.
const QUEUE_DEPTH: usize = 16;

/// How many Telegram chats this bridge will serve at once.
///
/// A ceiling rather than a policy: each chat costs a parked task and a queue,
/// and only a person the allowlist admits can open one, so reaching this means
/// something has gone wrong rather than that somebody has a lot of topics. It is
/// logged, never silent.
const MAX_CHATS: usize = 256;

/// One Telegram chat being served: a queue of its messages, and a way to stop
/// the reply being written into it.
///
/// A task per chat, and that is the whole of how several chats work: a reply can
/// take a minute, and nothing about it may keep another chat — or the reader —
/// waiting. What a chat learns along the way (whether drafts work in it, what is
/// on screen) is the serving task's own state, not shared.
struct Session {
    queue: mpsc::Sender<Box<Message>>,
    stop: watch::Sender<i32>,
    task: tokio::task::JoinHandle<()>,
}

/// Dropping the registry ends the tasks in it.
///
/// `stop_bot` sends the shutdown signal and then ABORTS the polling task, so any
/// cleanup written after the loop below may simply never run: the future is
/// dropped at its next await. Every session therefore has two independent ways
/// to end — the shutdown channel it watches itself, and this — so a token change
/// cannot leave a task behind holding the old token.
impl Drop for Session {
    fn drop(&mut self) {
        self.task.abort();
    }
}

/// Whether a chat can show a reply as it is written, and why not.
///
/// **The reason this is per chat and has three states.** Version 0.2 kept one
/// flag for the whole bot and turned it off on the first refused draft, telling
/// a refusal apart from a hiccup only by whether any draft had ever worked. So a
/// single timeout on the first frame of a reply — the empty "Thinking…" one —
/// dropped that whole reply back to rewriting a message, with no Stop button on
/// it, for reasons that had nothing to do with the chat. From the outside that
/// is "sometimes the answer arrives in one piece and there is nothing to press",
/// intermittently, which is exactly how it was reported.
///
/// Now the kind of refusal decides ([`Refusal`]): a settled answer about the
/// chat switches drafts off, a rate limit pauses them, and anything else costs
/// one frame of an animation.
#[derive(Debug, Default)]
struct Drafts {
    /// What kind of chat this is, from the last message Telegram sent about it.
    /// `sendMessageDraft` takes "the target private chat"; a group, supergroup
    /// or channel is refused, so the bridge asks rather than finds out.
    private: bool,
    /// Telegram has settled it: this chat will not take drafts. Stop asking.
    refused: bool,
    /// Pushing drafts again before this moment would only be refused again.
    quiet_until: Option<Instant>,
}

impl Drafts {
    /// Record what kind of chat this is. Called from every message, not just the
    /// first: it is one field read off a message the bridge already has.
    fn saw(&mut self, kind: ChatType) {
        self.private = matches!(kind, ChatType::Private);
    }

    /// Whether drafts are the way this chat is streamed to at all. The pacing
    /// and the fallback both read this; [`Drafts::ready`] is the narrower
    /// question of whether to push one *now*.
    fn usable(&self) -> bool {
        self.private && !self.refused
    }

    /// Whether to push a draft at this moment.
    fn ready(&self) -> bool {
        self.usable() && self.quiet_until.is_none_or(|until| Instant::now() >= until)
    }

    /// What a refused draft means for the ones after it.
    fn note(&mut self, chat: ChatKey, refusal: &Refusal) {
        match refusal {
            Refusal::Settled { .. } => {
                warn!(
                    "{chat} will not take streaming drafts ({refusal}) — falling back to \
                     rewriting a posted message, which every Telegram client supports"
                );
                self.refused = true;
            }
            Refusal::TooFast { retry_after } => {
                debug!("{chat}: drafts are going too fast; pausing {retry_after:?}");
                self.quiet_until = Some(Instant::now() + *retry_after);
            }
            Refusal::Hiccup(why) => {
                debug!("{chat}: one draft frame was lost ({why}); the next is along shortly");
            }
        }
    }
}

/// Run the Telegram long-polling loop until shutdown.
///
/// This task does nothing but read updates and hand them to the chat they belong
/// to. It is never the task that waits on Astra — that is [`Session`]'s, one per
/// chat — which is what makes a stop arrive while the reply it stops is still
/// being written, and what lets two chats be answered at the same time.
pub async fn run_polling_loop(
    telegram: Arc<TelegramApi>,
    state: SharedState,
    host: SharedHost,
    config: SharedConfig,
    i18n: SharedI18n,
    mut shutdown_rx: watch::Receiver<bool>,
) {
    info!("Starting Telegram polling loop");

    let mut chats: HashMap<ChatKey, Session> = HashMap::new();
    let mut offset: i64 = 0;

    loop {
        let polled = tokio::select! {
            result = telegram.poll_updates(offset, 30) => result,
            _ = shutdown_rx.changed() => break,
        };
        let (next_offset, updates) = match polled {
            Ok(polled) => polled,
            Err(e) => {
                warn!("Poll error: {e}");
                tokio::select! {
                    _ = tokio::time::sleep(Duration::from_secs(5)) => continue,
                    _ = shutdown_rx.changed() => break,
                }
            }
        };
        // Before acting on any of them: what has been read is read, and asking
        // again for a batch already in hand is how a bridge answers the same
        // message twice.
        offset = next_offset;

        for update in updates {
            match update {
                // The stop button on a streaming draft. It names the chat and
                // the draft it was shown on, so a press that arrives late —
                // after the reply it belonged to already finished — cannot stop
                // the next one, and a press in one chat cannot stop another's.
                Incoming::Stopped { chat, draft_id } => {
                    if let Some(session) = chats.get(&chat) {
                        info!("Stop requested for draft {draft_id} in {chat}");
                        let _ = session.stop.send(draft_id);
                    }
                }
                Incoming::Said(msg) => {
                    let chat = ChatKey::of(&msg);
                    // WHO may talk to this bot is decided here, before a chat
                    // can cost anything: a message from anybody else buys no
                    // task, no queue slot and no Astra conversation.
                    if !admit(&state, &config, &msg).await {
                        continue;
                    }

                    // `/stop` typed out: the same thing for a chat that has no
                    // button, which is any group — drafts are private-chat only.
                    // Read here rather than in the chat's own queue, because a
                    // stop that queued behind the reply it means to end would
                    // arrive after it finished.
                    if command_of(msg.text.as_deref().unwrap_or("")) == Some("stop") {
                        if let Some(session) = chats.get(&chat) {
                            info!("Stop requested by /stop in {chat}");
                            let _ = session.stop.send(STOP_ANY);
                        }
                        continue;
                    }

                    let Some(session) = serve(
                        &mut chats,
                        chat,
                        &telegram,
                        &state,
                        &host,
                        &config,
                        &i18n,
                        &shutdown_rx,
                    ) else {
                        continue;
                    };
                    // **`try_send`, never `send`.** Waiting for room in one
                    // chat's queue would stop the bridge reading for every other
                    // chat, which is the shape this loop exists to avoid. A
                    // queue this deep is already a person typing faster than
                    // Astra can answer.
                    if let Err(e) = session.queue.try_send(msg) {
                        warn!("{chat} has {QUEUE_DEPTH} messages waiting; dropping this one: {e}");
                    }
                }
            }
        }
    }

    info!("Polling loop shutdown");
}

/// The session serving `chat`, started if this is the first message from it.
///
/// `None` when the bridge is already serving as many chats as it will.
#[allow(clippy::too_many_arguments)]
fn serve<'a>(
    chats: &'a mut HashMap<ChatKey, Session>,
    chat: ChatKey,
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    host: &SharedHost,
    config: &SharedConfig,
    i18n: &SharedI18n,
    shutdown_rx: &watch::Receiver<bool>,
) -> Option<&'a Session> {
    if !chats.contains_key(&chat) {
        if chats.len() >= MAX_CHATS {
            warn!("Already serving {MAX_CHATS} chats; {chat} is not being answered");
            return None;
        }
        let (queue_tx, queue_rx) = mpsc::channel(QUEUE_DEPTH);
        let (stop_tx, stop_rx) = watch::channel(0i32);
        info!("Serving {chat}");
        let task = tokio::spawn(serve_chat(
            chat,
            telegram.clone(),
            state.clone(),
            host.clone(),
            config.clone(),
            i18n.clone(),
            queue_rx,
            stop_rx,
            shutdown_rx.clone(),
        ));
        chats.insert(
            chat,
            Session {
                queue: queue_tx,
                stop: stop_tx,
                task,
            },
        );
    }
    chats.get(&chat)
}

/// Answer one chat's messages, one at a time.
///
/// One at a time is the documented right shape: *wait for `done` before sending
/// again* (`docs/en/3-reference/permissions.md`). The daemon parks a message
/// that arrives mid-turn — per conversation, so two chats do not park behind
/// each other — and a bridge that fired everything at once would spend that
/// queue on itself and start losing the oldest lines.
#[allow(clippy::too_many_arguments)]
async fn serve_chat(
    chat: ChatKey,
    telegram: Arc<TelegramApi>,
    state: SharedState,
    host: SharedHost,
    config: SharedConfig,
    i18n: SharedI18n,
    mut queue: mpsc::Receiver<Box<Message>>,
    stop_rx: watch::Receiver<i32>,
    mut shutdown_rx: watch::Receiver<bool>,
) {
    let mut drafts = Drafts::default();

    loop {
        let msg = tokio::select! {
            msg = queue.recv() => match msg {
                Some(msg) => msg,
                None => break, // the reader is gone; so is the reason to answer
            },
            _ = shutdown_rx.changed() => break,
        };

        handle_message(
            chat,
            &telegram,
            &state,
            &host,
            &config,
            &i18n,
            &stop_rx,
            &mut drafts,
            &msg,
        )
        .await;
    }

    debug!("{chat} is no longer being served");
}

/// The command in a message, if it is one: `/new`, `/new@some_bot arg` and
/// `  /new  ` all read as `new`.
///
/// Shared by the two places that dispatch commands. The update reader has to
/// recognise `/stop` before anything else, because a stop that queued behind
/// the reply it means to end would arrive after it finished.
fn command_of(text: &str) -> Option<&str> {
    let command = text.trim().strip_prefix('/')?;
    let command = command.split_whitespace().next().unwrap_or(command);
    Some(command.split('@').next().unwrap_or(command))
}

/// Whether this message may reach Astra at all.
///
/// **Two gates, and only one of them is ever in force.** The bot answers in as
/// many chats as it is written in, so "which chat" can no longer be what keeps
/// strangers out, and something has to be:
///
/// * **The username allowlist**, when the user has set one. Then it is the whole
///   answer: anybody on it, in any chat, including a group they add the bot to.
/// * **The person who first talked to the bot**, when the allowlist is empty.
///   One Telegram account, learned once and remembered; every other account is
///   ignored wherever it writes. This is what version 0.2's "the bot binds to
///   the first chat that talks to it" was protecting, kept intact while the
///   number of chats stops being one — and it is why installing this version
///   cannot widen who can reach an Astra.
///
/// An install updating from 0.2 has a bound CHAT and no bound person yet, so
/// until one is learned that chat is what gates: the update does not hand the
/// bot to whoever writes first.
///
/// A message with no `from` — a service message, an anonymous group admin, a
/// channel post — names no account, so there is nothing to compare and it is
/// refused.
async fn admit(state: &SharedState, config: &SharedConfig, msg: &Message) -> bool {
    let allowed = config.read().await.allowed_set();
    if !allowed.is_empty() {
        let username = msg
            .from
            .as_ref()
            .and_then(|u| u.username.as_deref())
            .unwrap_or("")
            .to_lowercase();
        return !username.is_empty() && allowed.contains(&username);
    }

    let Some(user_id) = msg.from.as_ref().map(|u| u.id) else {
        return false;
    };
    let (owner, bound_chat) = {
        let state = state.read().await;
        (state.owner_user_id, state.chat_id)
    };
    match owner {
        Some(owner) => owner == user_id,
        None => {
            if bound_chat != 0 && msg.chat.id != bound_chat {
                debug!(
                    "Ignoring {}: this bot was bound to chat {bound_chat} and has no owner yet",
                    msg.chat.id
                );
                return false;
            }
            info!(
                "Bound to Telegram user {user_id}; with no allowlist set, only they are answered"
            );
            state.write().await.set_owner(user_id);
            true
        }
    }
}

#[allow(clippy::too_many_arguments)]
async fn handle_message(
    chat: ChatKey,
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    host: &SharedHost,
    config: &SharedConfig,
    i18n: &SharedI18n,
    stop_rx: &watch::Receiver<i32>,
    drafts: &mut Drafts,
    msg: &Message,
) {
    let text = msg.text.as_deref().unwrap_or("").trim();

    // Says whether replies in this chat can stream as drafts. Read from every
    // message, because it is the only thing that states the chat's kind and a
    // restart has nothing else to go on.
    drafts.saw(msg.chat.type_field);

    if let Some(command) = command_of(text) {
        match command {
            "start" | "help" => {
                if let Err(e) = telegram.send(chat, &i18n.t("bot.start")).await {
                    warn!("/start error: {e}");
                }
            }
            "screenshot" => {
                if !config.read().await.allow_screenshot {
                    if let Err(e) = telegram.send(chat, &i18n.t("bot.screenshot_off")).await {
                        warn!("/screenshot error: {e}");
                    }
                    return;
                }
                // Asked before the capture rather than reported after it: on a
                // build with no backend the answer is a property of the build,
                // not a failure, and "it could not be captured, see the log"
                // would send the user looking for a fault that is not there.
                if !crate::screen::SUPPORTED {
                    let said = telegram
                        .send(chat, &i18n.t("bot.screenshot_unsupported"))
                        .await;
                    if let Err(e) = said {
                        warn!("/screenshot error: {e}");
                    }
                    return;
                }
                screenshot(chat, telegram, i18n).await;
            }
            "new" => new_chat(chat, telegram, state, i18n, msg).await,
            "clear" => {
                start_over(chat, state).await;
                if let Err(e) = telegram.send(chat, &i18n.t("bot.clear")).await {
                    warn!("/clear error: {e}");
                }
            }
            _ => {}
        }
        return;
    }

    // Whether this message is the one that names the chat it arrived in.
    if names_the_chat_it_is_in(chat, msg, state).await {
        state.write().await.set_awaiting_title(chat, true);
    }

    // A sticker, a photo, somebody joining the group: nothing to say to Astra,
    // and the daemon refuses an empty message outright.
    if text.is_empty() {
        return;
    }

    forward(chat, telegram, state, host, i18n, stop_rx, drafts, text).await;
}

/// `/new` — a new conversation in a **new Telegram chat of its own**.
///
/// This is what "a new chat" means in an app that shows one chat at a time: not
/// only a conversation with no memory, but a place to hold it, so two sit side
/// by side in Telegram the way they do in Astra's sidebar. The chat the command
/// was typed in is left exactly as it was, conversation and all, because the new
/// one is somewhere else now.
///
/// **Telegram decides whether there is a place to open, and it is asked rather
/// than guessed.** `createForumTopic` is not only a group method any more: a bot
/// with topic mode on (`User::has_topics_enabled`) has topics in its **private**
/// chats too, and that is where this was reported from — a private chat whose
/// `getChat` answers no `is_forum` at all, so a bridge that read that field
/// first would refuse the one case it was asked for. A forum group works the
/// same way through the same call.
///
/// What a refusal means depends on the kind of chat, and the two fixes are in
/// different places:
///
/// * **a private chat** — topic mode is off for this bot, which is a setting of
///   the bot itself, so nothing about this chat can be changed to help. `/new`
///   then means what `/clear` means ([`start_over`]) and says which it did,
///   rather than pretending a chat was opened out of sight.
/// * **a group** — either topics are off for the group or the bot is not an
///   administrator with *Manage topics*. Both are two taps away for whoever runs
///   the group, so the refusal is reported instead of being turned into a silent
///   `/clear`.
/// * **anything else** (a rate limit, a hiccup) — worth trying again, and said
///   so.
///
/// The topic is born under a placeholder name because Telegram wants one before
/// there is a message to take it from; the first message written in it replaces
/// that ([`name_topic`]).
async fn new_chat(
    chat: ChatKey,
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    i18n: &SharedI18n,
    msg: &Message,
) {
    let thread = match telegram
        .create_topic(chat.chat_id, &i18n.t("bot.new_placeholder"))
        .await
    {
        Ok(thread) => thread,
        Err(Refusal::Settled { code, description }) => {
            warn!("No topic can be opened in {}: {code} {description}", chat.chat_id);
            if matches!(msg.chat.type_field, ChatType::Private) {
                // Nothing here to fix, so the command does the next most useful
                // thing and names it.
                start_over(chat, state).await;
                if let Err(e) = telegram.send(chat, &i18n.t("bot.new_here")).await {
                    warn!("/new error: {e}");
                }
            } else if let Err(e) = telegram.send(chat, &i18n.t("bot.new_refused")).await {
                warn!("/new error: {e}");
            }
            return;
        }
        Err(refusal) => {
            warn!("Could not open a topic in {} just now: {refusal}", chat.chat_id);
            if let Err(e) = telegram.send(chat, &i18n.t("bot.new_failed")).await {
                warn!("/new error: {e}");
            }
            return;
        }
    };

    let opened = ChatKey::new(chat.chat_id, Some(i64::from(thread)));
    {
        let mut state = state.write().await;
        // It holds no conversation yet, so its first message opens one — the
        // same path every new chat takes. Marked for its name under the same
        // lock, so nothing can see one half of this done.
        state.set_conversation(opened, None);
        state.set_awaiting_title(opened, true);
    }
    info!("Opened {opened} for a new conversation");

    // Written INTO the new topic, so it is not an empty thread the person has to
    // guess is theirs, and so the topic list has something to show.
    if let Err(e) = telegram.send(opened, &i18n.t("bot.new_opened")).await {
        warn!("Could not write into {opened}: {e}");
    }

    // And said where the command was typed, with the way there. The link is data
    // rather than a sentence, so it is appended instead of interpolated: a
    // translation cannot lose it, and a chat whose id has no link form simply
    // gets the sentence.
    let mut told = i18n.t("bot.new_created");
    if let Some(link) = opened.topic_link() {
        told.push('\n');
        told.push_str(&link);
    }
    if let Err(e) = telegram.send(chat, &told).await {
        warn!("/new error: {e}");
    }
}

/// Start this chat's conversation over: `/clear`, and what `/new` falls back to
/// where Telegram has no second thread to offer.
///
/// Forgetting this chat's id is the whole of it: its next message finds none and
/// asks the daemon to open a conversation, which starts the model with no memory
/// of this one. **Only this chat's** — every other chat carries on where it was,
/// which is the difference a `/clear` in one of several chats has to make. The
/// old conversation is left alone in Astra rather than deleted: a plugin cannot
/// delete one, and quietly destroying the user's history would be the wrong
/// reading of "start over".
///
/// A topic is also marked to be **renamed** by the message that starts the new
/// conversation, for the same reason `/new` marks the one it opens: the name in
/// the topic list is the name of the conversation in it, and that conversation
/// is about to be a different one. A chat with no thread has no name of its own
/// to set — a private chat is titled by the person, a group by its members — so
/// it is not marked.
async fn start_over(chat: ChatKey, state: &SharedState) {
    let mut state = state.write().await;
    state.set_conversation(chat, None);
    state.set_awaiting_title(chat, chat.thread().is_some());
    info!("{chat} forgot its conversation; its next message opens a new one");
}

/// Name the topic after the message that starts its conversation.
///
/// **Astra already does this for the conversation itself**: the daemon titles a
/// new one from the first message it carries
/// (`conversation_cache::derive_conversation_title`). This is the same name on
/// the Telegram side, by the same rule ([`topic_name`]), so the topic list and
/// the sidebar read alike.
///
/// Only a chat a command marked gets here, so nothing renames a topic somebody
/// made and named. A chat with no thread has no name to set, and drops the mark
/// rather than calling anything.
///
/// A refusal is read the way drafts read one: a settled 400 — no **Manage
/// topics** right, a name Telegram will not take — would refuse every later
/// message identically, so the mark is dropped and the log says why; a rate
/// limit or a hiccup leaves it, and the next message in this chat names the
/// topic instead. The conversation is unaffected either way, which is why this
/// runs before it and not instead of it: a name is the one thing here that can
/// fail without costing the person an answer.
async fn name_topic(chat: ChatKey, telegram: &Arc<TelegramApi>, state: &SharedState, text: &str) {
    let Some(thread) = chat.thread() else {
        state.write().await.set_awaiting_title(chat, false);
        return;
    };

    let name = topic_name(text);
    match telegram.rename_topic(chat.chat_id, thread, &name).await {
        Ok(()) => {
            info!("{chat} is now called {name:?}");
            state.write().await.set_awaiting_title(chat, false);
        }
        Err(refusal @ Refusal::Settled { .. }) => {
            warn!("{chat} keeps the name it has: {refusal}");
            state.write().await.set_awaiting_title(chat, false);
        }
        Err(refusal) => debug!("{chat} will be named by its next message: {refusal}"),
    }
}

/// Should the chat this message arrived in be named after it?
///
/// **The chats a person opens with Telegram's own button are the ones this is
/// for.** A client with topic mode on gives each conversation with a bot a thread
/// of its own, names them all "New chat", and says that the name was nobody's
/// choice — `is_name_implicit`. `/new` does the same by command, and it has to,
/// because a bot cannot take anybody to a chat it opened: there is no Bot API
/// method that moves a client's view and no link form for a topic of a private
/// chat. So the button is the path that gets used, and a bridge that only named
/// what `/new` opened would leave every chat that matters called "New chat" —
/// which is how this was reported.
///
/// Two facts say it, and a group's topics are under neither:
///
/// * **Telegram said so** — the `forum_topic_created` service message carries
///   `is_name_implicit`. A topic somebody named does not carry it and is left
///   exactly as they named it, in a group or anywhere else.
/// * **It is a thread of a PRIVATE chat that has never spoken.** Those are the
///   client's own per-conversation threads, all named alike, and this is what
///   covers them where no service message reached the bridge. A group's topics
///   are named by the people in it, which is why this clause stops at private
///   chats; there, `/new` and `/clear` are what mark one.
///
/// An empty message — a sticker, a photo — is allowed to decide this even though
/// it cannot be a name: what it marks is the chat, and the next message with
/// words in it is what gets used.
async fn names_the_chat_it_is_in(chat: ChatKey, msg: &Message, state: &SharedState) -> bool {
    if msg
        .forum_topic_created
        .as_deref()
        .is_some_and(|created| created.is_name_implicit.unwrap_or(false))
    {
        info!("{chat} was opened by Telegram under a placeholder name");
        return true;
    }

    chat.thread_id.is_some()
        && matches!(msg.chat.type_field, ChatType::Private)
        && state.read().await.conversation_of(chat).is_none()
}

/// What to call a topic whose conversation starts with `text`.
///
/// **The daemon's rule, copied on purpose.**
/// `conversation_cache::derive_conversation_title` keeps the first 40 characters
/// and marks a longer message with an ellipsis, so a conversation in Astra's
/// sidebar and the topic feeding it carry one name rather than two versions of
/// it. The one difference is that whitespace is collapsed: a topic name is a
/// single line in a list, and Telegram takes 1 to 128 characters for it.
fn topic_name(text: &str) -> String {
    let line = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let chars: Vec<char> = line.chars().collect();
    if chars.len() > 40 {
        format!("{}...", chars[..37].iter().collect::<String>())
    } else {
        line
    }
}

/// Take a picture of the screen and put it in the chat.
///
/// The capture blocks — a framebuffer read and a PNG encode — so it goes to a
/// blocking thread rather than stalling this chat's task, and the reader is a
/// different task again, so Telegram's long poll cannot time out under it.
///
/// The file is temporary in both senses: written to the system temp directory
/// and removed once Telegram has it, whether or not the upload worked. Nothing
/// keeps a picture of the user's desktop lying around because a send failed.
async fn screenshot(chat: ChatKey, telegram: &Arc<TelegramApi>, i18n: &SharedI18n) {
    let taken = tokio::task::spawn_blocking(|| crate::screen::capture(&std::env::temp_dir())).await;

    let (path, monitor) = match taken {
        Ok(Ok(captured)) => captured,
        Ok(Err(e)) => {
            warn!("Screen capture failed: {e:#}");
            let _ = telegram.send(chat, &i18n.t("bot.screenshot_failed")).await;
            return;
        }
        Err(e) => {
            warn!("Screen capture panicked: {e}");
            let _ = telegram.send(chat, &i18n.t("bot.screenshot_failed")).await;
            return;
        }
    };

    if let Err(e) = telegram.send_photo(chat, &path, &monitor).await {
        warn!("Screenshot upload failed: {e:#}");
        let _ = telegram.send(chat, &i18n.t("bot.screenshot_failed")).await;
    }
    if let Err(e) = std::fs::remove_file(&path) {
        warn!("Could not delete {}: {e}", path.display());
    }
}

/// Send one Telegram message to Astra and stream the answer back into the chat.
#[allow(clippy::too_many_arguments)]
async fn forward(
    chat: ChatKey,
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    host: &SharedHost,
    i18n: &SharedI18n,
    stop_rx: &watch::Receiver<i32>,
    drafts: &mut Drafts,
    text: &str,
) {
    // The id every frame of this reply is drawn under, and the clean slate for
    // stopping it: a press that arrived while the last reply was finishing is
    // marked seen HERE, before the button for this one is shown, so it cannot
    // cut this reply off before it starts — and a press from here on counts.
    let draft_id = telegram.next_draft_id();
    let mut stop_rx = stop_rx.clone();
    stop_rx.borrow_and_update();

    // Telegram's own "Thinking…", shown by sending a draft with no text —
    // **before** Astra is asked anything, which is the point. The daemon parks a
    // message that arrives while another turn is running in the same
    // conversation, so `open_reply` below can take as long as that turn does,
    // and the chat used to sit silent through all of it with nothing to press.
    if drafts.ready()
        && let Err(refusal) = telegram.send_draft(chat, draft_id, "").await
    {
        drafts.note(chat, &refusal);
    }

    // The name of the conversation, where Telegram has one to set. `/new` opened
    // this topic under a placeholder and `/clear` left the name of a
    // conversation that is over; either way the message that starts the new one
    // is what it should be called, and that is known only now.
    if state.read().await.awaits_title(chat) {
        name_topic(chat, telegram, state, text).await;
    }

    let reply = match open_reply(host, state, chat, text).await {
        Ok(reply) => reply,
        Err(e) => {
            warn!("SendChatMessage failed for {chat}: {e:#}");
            // Told apart because the answers are opposite: a missing permission
            // is fixed once, in Astra's settings, and nothing the user types in
            // Telegram will get past it.
            let key = if matches!(e.downcast_ref::<ToolError>(), Some(ToolError::Unauthorized(_))) {
                "bot.not_permitted"
            } else {
                "bot.send_failed"
            };
            let _ = telegram.send(chat, &i18n.t(key)).await;
            return;
        }
    };

    if let Err(e) = render(
        chat, telegram, state, i18n, stop_rx, drafts, reply, draft_id,
    )
    .await
    {
        warn!("Reply stream failed for {chat}: {e:#}");
        let _ = telegram.send(chat, &i18n.t("bot.send_failed")).await;
    }
}

/// A reply stream, and whether the conversation id its chunks carry belongs to
/// this chat.
///
/// It usually does, and remembering it is the whole of how a chat keeps one
/// conversation. The exception is the durable-thread fallback below: the id those
/// chunks name is the plugin's own thread at its CURRENT rotation, and
/// `plugin.proto` is explicit that storing one pins the holder to a thread the
/// daemon retires and later prunes. The empty string is how that thread is
/// addressed, and the way back to it is for the chat to hold no id at all.
struct Reply {
    stream: ChatStream,
    remember: bool,
}

/// Open the reply stream for one chat, having decided which conversation the
/// message belongs to — and recover from the two ways that decision can turn out
/// to be wrong.
///
/// See [`NEW_CONVERSATION`] for what the three shapes of `conversation_id` mean.
/// Each Telegram chat holds its own, so this is the function that makes "several
/// chats" mean several conversations in Astra rather than one shared one.
/// Neither fallback here is speculative: both are answers this daemon can
/// actually give, and a bridge that treated either as fatal would stop working
/// the first time a user deleted a chat.
async fn open_reply(
    host: &SharedHost,
    state: &SharedState,
    chat: ChatKey,
    text: &str,
) -> Result<Reply> {
    let remembered = state.read().await.conversation_of(chat);

    if let Some(id) = remembered {
        match host.send_chat_message(text, &id, false).await {
            Ok(stream) => {
                return Ok(Reply {
                    stream,
                    remember: true,
                });
            }
            Err(e) if conversation_is_gone(&e) => {
                warn!("Astra no longer has conversation {id} — opening a new one for {chat}");
                state.write().await.set_conversation(chat, None);
            }
            Err(e) => return Err(e),
        }
    }

    match host.send_chat_message(text, NEW_CONVERSATION, false).await {
        Ok(stream) => Ok(Reply {
            stream,
            remember: true,
        }),
        Err(e) if refuses_to_open_one(&e) => {
            warn!(
                "This Astra will not open a conversation for a plugin ({e:#}) — \
                 falling back to this plugin's own durable thread, which every chat then \
                 shares"
            );
            host.send_chat_message(text, PLUGIN_THREAD, false)
                .await
                .map(|stream| Reply {
                    stream,
                    remember: false,
                })
        }
        Err(e) => Err(e),
    }
}

/// The conversation this chat remembered is not there any more — the user
/// deleted it.
///
/// **Two spellings, because two daemons say it differently**, and a bridge that
/// knew only one stops working the first time somebody deletes a chat:
///
/// * **NOT_FOUND** — what Astra answers today, with its message led by the
///   `conversation_gone` token. The CODE alone is read and the sentence is not,
///   because the only thing `SendChatMessage` addresses is a conversation: there
///   is nothing else for "not found" to be about. `chat_processor::refusal_status`
///   is the one place that maps it, and the daemon's own comment says the token
///   rides in the message only because Astra's shells drop the gRPC code.
/// * **INTERNAL, containing "does not exist"** — what the daemon of version
///   0.2's era answered: the refusal came out of `chat_processor::process` with
///   the reason in the sentence, and the sentence was the only handle the wire
///   gave. Kept so this plugin keeps working against that build. Matching the
///   substring is what version 0.2 did, and matching it ALONE is the bug this
///   function had: today's daemon says NOT_FOUND and "no longer exists", neither
///   of which that test recognised, so a user who deleted the chat got
///   "Astra could not answer" on every message until they typed `/new`.
fn conversation_is_gone(error: &anyhow::Error) -> bool {
    match error.downcast_ref::<ToolError>() {
        Some(ToolError::NotFound(_)) => true,
        Some(ToolError::Internal(message)) => message.contains("does not exist"),
        _ => false,
    }
}

/// This daemon refused the id that means *open a new conversation*.
///
/// `invalid_argument` is what `SendChatMessage` answers an id it will not parse
/// or will not accept, and it is the shape a future Astra that decides a plugin
/// may not open conversations would answer in. The durable thread is always
/// available, so that refusal costs the user a fresh context rather than the
/// whole bridge.
fn refuses_to_open_one(error: &anyhow::Error) -> bool {
    matches!(
        error.downcast_ref::<ToolError>(),
        Some(ToolError::BadArguments(_))
    )
}

/// Render one reply stream into the chat: show it arriving, then deliver it.
///
/// Two ways of showing it, and the difference is only visible to the reader —
/// a draft that animates where Telegram allows one, a message rewritten each
/// second where it does not. Delivery is the same either way and does not
/// depend on which happened: the finished answer is sent as ordinary messages,
/// split into as many as it takes. That matters more than it looks, because a
/// draft **expires** — Telegram calls it a thirty-second preview, not a message,
/// and an answer left in one would vanish from the chat.
#[allow(clippy::too_many_arguments)]
async fn render(
    chat: ChatKey,
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    i18n: &SharedI18n,
    mut stop_rx: watch::Receiver<i32>,
    drafts: &mut Drafts,
    reply: Reply,
    draft_id: i32,
) -> Result<()> {
    let Reply {
        mut stream,
        remember,
    } = reply;
    let mut answer = String::new();
    // The message being rewritten, and what it currently says — so an edit that
    // would change nothing is never sent. `posted` stays `None` for a draft:
    // nothing was posted, and the delivery below reads it exactly that way.
    let mut posted: Option<i32> = None;
    let mut shown = String::new();
    let mut next_frame = Instant::now();
    let mut stopped = false;

    loop {
        let chunk = tokio::select! {
            // Checked first, so a stop that lands in the same breath as a token
            // is still a stop.
            biased;

            _ = stop_rx.changed() => {
                let asked = *stop_rx.borrow();
                if asked == draft_id || asked == STOP_ANY {
                    stopped = true;
                    break;
                }
                continue;
            }

            chunk = stream.next() => match chunk {
                Some(chunk) => chunk?,
                None => break,
            },

            _ = tokio::time::sleep(DRAFT_KEEPALIVE) => {
                // Nothing for twenty seconds. Astra is working — a tool call is
                // the usual reason, and the plugin protocol says nothing about
                // those: `PluginChatChunk` carries text, done or error, and the
                // events that name a tool travel on `ChatService`, which a
                // plugin's token cannot reach. So the bridge cannot say *what*
                // is happening, only keep the sign that something is.
                if drafts.ready()
                    && let Err(refusal) = telegram.send_draft(chat, draft_id, &shown).await
                {
                    drafts.note(chat, &refusal);
                }
                continue;
            }
        };

        // Which conversation the daemon put this in. It is on every chunk, and
        // the first one is how a freshly opened conversation gets its id into
        // this chat's row. Read first: this runs once per token, and only the
        // first of them has anything to say.
        if remember
            && !chunk.conversation_id.is_empty()
            && state.read().await.conversation_of(chat).as_deref() != Some(&chunk.conversation_id)
        {
            state
                .write()
                .await
                .set_conversation(chat, Some(chunk.conversation_id.clone()));
        }

        match chunk.content {
            Some(Content::Text(delta)) => {
                answer.push_str(&delta);
                if Instant::now() >= next_frame {
                    show(
                        chat, telegram, drafts, draft_id, &mut posted, &mut shown, &answer,
                    )
                    .await;
                    // Read after `show`, because `show` is where drafts can
                    // turn out to be unavailable and the pace drops with them.
                    next_frame = Instant::now()
                        + if drafts.usable() {
                            DRAFT_INTERVAL
                        } else {
                            EDIT_INTERVAL
                        };
                }
            }
            Some(Content::Done(_)) => break,
            Some(Content::Error(message)) => {
                // The turn ended badly and the daemon named why: a parked
                // message that was evicted, a deleted conversation, a locked
                // Astra. Whatever arrived before it is still the answer so far,
                // so the reason is appended rather than replacing it, and the
                // delivery below is the same one a finished turn gets.
                //
                // NOT_FOUND here is the one the bridge must act on rather than
                // only report: this chat's conversation was deleted while its
                // message waited behind a turn, so the id is forgotten and the
                // next message opens a new conversation instead of failing.
                if chunk.error_detail.as_ref().is_some_and(|detail| {
                    detail.code
                        == astra_plugin_sdk::proto::PluginErrorCode::PluginErrorNotFound as i32
                }) {
                    warn!("{chat}'s conversation was deleted while its message waited");
                    state.write().await.set_conversation(chat, None);
                }
                if !answer.is_empty() {
                    answer.push_str("\n\n");
                }
                answer.push_str("⚠️ ");
                answer.push_str(&message);
                break;
            }
            None => {}
        }
    }

    // Let go of the stream before anything else. Dropping it is the whole of
    // what a plugin can do to end a turn early: `ChatService.StopGeneration`
    // exists and is refused to a plugin token like the rest of that service, so
    // whether Astra abandons the turn or finishes it unheard is the daemon's
    // decision about a cancelled stream, not this bridge's to make.
    drop(stream);

    if stopped {
        info!("Reply in {chat} stopped by the user after {} bytes", answer.len());
        if !answer.trim().is_empty() {
            answer.push_str("\n\n");
        }
        answer.push_str(&i18n.t("bot.stopped"));
    }

    let answer = if answer.trim().is_empty() {
        i18n.t("bot.no_reply")
    } else {
        answer
    };

    deliver(chat, telegram, posted, &shown, &answer).await
}

/// Put the finished answer in the chat, in as many messages as it takes.
///
/// The one call in a reply whose failure the user would actually notice. What
/// the model wrote is in hand and nowhere else that lasts: a draft is a preview
/// that expires, and the rewritten message holds only the first part of a long
/// answer — so a refusal here is the answer lost, with an error in its place.
/// The likeliest cause is Telegram's own pace limit, about a message a second
/// per chat, and a reply that was streaming by rewriting a message has just used
/// that budget. So that one refusal is waited out and tried again — and only
/// that one, because it is the only one that promises the message did not
/// arrive ([`Refusal::certainly_refused`]).
async fn deliver(
    chat: ChatKey,
    telegram: &Arc<TelegramApi>,
    posted: Option<i32>,
    shown: &str,
    answer: &str,
) -> Result<()> {
    for (index, part) in split_message(answer).into_iter().enumerate() {
        match posted {
            // The message already on screen becomes the first part of the
            // answer — unless it already says exactly that.
            Some(id) if index == 0 => {
                if shown != part {
                    twice(chat, telegram, Put::Edit(id, &part)).await?;
                }
            }
            _ => {
                twice(chat, telegram, Put::Send(&part)).await?;
            }
        }
    }
    Ok(())
}

/// One way of putting text in a chat, so [`twice`] can retry either without
/// taking a closure that borrows half this module.
enum Put<'a> {
    Send(&'a str),
    Edit(i32, &'a str),
}

/// Put it in the chat, once.
async fn put(chat: ChatKey, telegram: &TelegramApi, what: &Put<'_>) -> Result<(), Refusal> {
    match *what {
        Put::Send(text) => telegram.send(chat, text).await.map(|_| ()),
        Put::Edit(id, text) => telegram.edit(chat, id, text).await,
    }
}

/// Do it, and if Telegram refused it for arriving too soon, do it once more.
async fn twice(chat: ChatKey, telegram: &TelegramApi, what: Put<'_>) -> Result<(), Refusal> {
    match put(chat, telegram, &what).await {
        Ok(()) => Ok(()),
        Err(refusal) if refusal.certainly_refused() => {
            let wait = refusal.retry_after();
            warn!("{chat}: {refusal} — delivering the answer again in {wait:?}");
            tokio::time::sleep(wait).await;
            put(chat, telegram, &what).await
        }
        Err(settled) => Err(settled),
    }
}

/// Put `text`'s first message-worth on screen: push a draft, or failing that
/// edit the message already there, or post one if this is the first thing to
/// show.
///
/// A failed frame is dropped rather than reported: the next is along shortly
/// and the finished answer is delivered by [`deliver`] whatever happened here.
#[allow(clippy::too_many_arguments)]
async fn show(
    chat: ChatKey,
    telegram: &Arc<TelegramApi>,
    drafts: &mut Drafts,
    draft_id: i32,
    posted: &mut Option<i32>,
    shown: &mut String,
    text: &str,
) {
    let Some(head) = split_message(text).into_iter().next() else {
        return;
    };
    if head.trim().is_empty() || head == *shown {
        return;
    }

    // Only the first message-worth is streamed. An answer longer than that
    // arrives whole, in parts, when it is finished — a draft cannot hold more
    // than one message either.
    if drafts.usable() {
        if !drafts.ready() {
            return; // Telegram said too fast; this frame is the one to skip
        }
        match telegram.send_draft(chat, draft_id, &head).await {
            Ok(()) => {
                *shown = head;
                return;
            }
            Err(refusal) => {
                drafts.note(chat, &refusal);
                if drafts.usable() {
                    return; // a lost frame, and the next is along shortly
                }
                // Settled: fall through now rather than wait, so the first words
                // reach the chat through the path that does work.
            }
        }
    }

    match *posted {
        Some(id) => {
            if telegram.edit(chat, id, &head).await.is_ok() {
                *shown = head;
            }
        }
        None => {
            if let Ok(message) = telegram.send(chat, &head).await {
                *posted = Some(message.message_id);
                *shown = head;
            }
        }
    }
}

/// Cut `text` into pieces Telegram will accept, preferring a line break near
/// the end of each so a split lands between paragraphs rather than mid-word.
///
/// Always returns at least one piece, so the caller can post the first without
/// a special case. The old code truncated at 4000 characters and appended `...`
/// instead, which threw the end of every long answer away.
fn split_message(text: &str) -> Vec<String> {
    if text.len() <= MAX_MESSAGE_LENGTH {
        return vec![text.to_string()];
    }

    let mut parts = Vec::new();
    let mut rest = text;
    while rest.len() > MAX_MESSAGE_LENGTH {
        // A char boundary first — `rest[..cut]` panics on anything else, and a
        // model's answer is UTF-8, not ASCII.
        let hard = rest.floor_char_boundary(MAX_MESSAGE_LENGTH);
        let cut = rest[..hard]
            .rfind('\n')
            .filter(|breakpoint| *breakpoint > hard / 2)
            .map(|breakpoint| breakpoint + 1)
            .unwrap_or(hard);
        parts.push(rest[..cut].to_string());
        rest = &rest[cut..];
    }
    if !rest.is_empty() {
        parts.push(rest.to_string());
    }
    parts
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::BotState;
    use crate::types::BotConfig;

    #[test]
    fn short_text_is_one_message() {
        assert_eq!(split_message("hello"), vec!["hello".to_string()]);
        assert_eq!(split_message(""), vec![String::new()]);
    }

    #[test]
    fn a_long_answer_is_split_and_nothing_is_lost() {
        let long = "x".repeat(MAX_MESSAGE_LENGTH * 2 + 7);
        let parts = split_message(&long);
        assert_eq!(parts.len(), 3);
        assert!(parts.iter().all(|p| p.len() <= MAX_MESSAGE_LENGTH));
        assert_eq!(parts.concat(), long, "splitting must not drop a byte");
    }

    #[test]
    fn a_split_prefers_a_line_break() {
        let mut long = "a".repeat(MAX_MESSAGE_LENGTH - 10);
        long.push('\n');
        long.push_str(&"b".repeat(100));
        let parts = split_message(&long);
        assert_eq!(parts.len(), 2);
        assert!(parts[0].ends_with('\n'));
        assert_eq!(parts[1], "b".repeat(100));
        assert_eq!(parts.concat(), long);
    }

    /// One reading of a command, wherever it is read. The update reader has to
    /// recognise `/stop` on its own, and a second parser that disagreed with
    /// this one would be a command that works in one place and not the other.
    #[test]
    fn a_command_reads_the_same_everywhere() {
        assert_eq!(command_of("/stop"), Some("stop"));
        assert_eq!(command_of("   /stop  "), Some("stop"));
        assert_eq!(command_of("/stop@astra_bot"), Some("stop"));
        assert_eq!(command_of("/new some argument"), Some("new"));
        assert_eq!(command_of("/clear"), Some("clear"));
        assert_eq!(command_of("/"), Some(""));

        assert_eq!(command_of("hello"), None);
        assert_eq!(command_of(""), None);
        assert_eq!(command_of("please /stop"), None, "a mention is not a command");
    }

    /// Why `floor_char_boundary` is in there. A cut in the middle of a
    /// multi-byte character panics, and a model's answer is full of them.
    #[test]
    fn a_split_never_lands_inside_a_character() {
        let long = "я".repeat(MAX_MESSAGE_LENGTH);
        let parts = split_message(&long);
        assert!(parts.len() > 1);
        assert!(parts.iter().all(|p| p.len() <= MAX_MESSAGE_LENGTH));
        assert_eq!(parts.concat(), long);
    }

    /// The classification that decides whether a reply streams at all.
    ///
    /// A 400 about the chat is the one answer worth believing; version 0.2
    /// believed a timeout just as readily, and that is the intermittent "no
    /// streaming, nothing to press" this splits apart.
    #[test]
    fn only_a_settled_refusal_switches_drafts_off() {
        let chat = ChatKey::new(1, None);
        let mut drafts = Drafts::default();
        drafts.saw(ChatType::Private);
        assert!(drafts.ready(), "a private chat starts able to stream");

        drafts.note(chat, &Refusal::Hiccup("connection reset".into()));
        assert!(drafts.ready(), "a dropped connection costs one frame");

        drafts.note(
            chat,
            &Refusal::TooFast {
                retry_after: Duration::from_secs(30),
            },
        );
        assert!(!drafts.ready(), "too fast means wait");
        assert!(drafts.usable(), "...and NOT that the chat cannot stream");

        drafts.note(
            chat,
            &Refusal::Settled {
                code: 400,
                description: "Bad Request: method is available for private chats only".into(),
            },
        );
        assert!(!drafts.usable(), "that one Telegram means");
        assert!(!drafts.ready());
    }

    /// A group cannot take drafts, and the bridge knows it from the chat's own
    /// kind rather than from a refusal.
    #[test]
    fn only_a_private_chat_takes_drafts() {
        let mut drafts = Drafts::default();
        assert!(!drafts.usable(), "nothing is known about the chat yet");

        drafts.saw(ChatType::Private);
        assert!(drafts.usable());

        for kind in [ChatType::Group, ChatType::Supergroup, ChatType::Channel] {
            drafts.saw(kind);
            assert!(!drafts.usable(), "{kind:?} cannot take a draft");
        }
    }

    /// **One name for one conversation.** The daemon titles a conversation from
    /// its first message, keeping 40 characters and marking a longer one; a topic
    /// fed by that conversation is named by the same rule, so the topic list and
    /// Astra's sidebar are not two different names for the same thing.
    #[test]
    fn a_topic_is_named_the_way_astra_names_a_conversation() {
        assert_eq!(topic_name("как дела"), "как дела");

        // Exactly the daemon's boundary: 40 kept whole, 41 cut to 37 and marked.
        let forty = "я".repeat(40);
        assert_eq!(topic_name(&forty), forty);
        let long = "я".repeat(41);
        assert_eq!(topic_name(&long), format!("{}...", "я".repeat(37)));
        assert_eq!(topic_name(&long).chars().count(), 40);

        // A topic name is one line in a list, so the newline a message may start
        // with cannot travel into it.
        assert_eq!(topic_name("  первая строка\nвторая  "), "первая строка вторая");
    }

    /// One message, as Telegram's JSON, for the cases `said` cannot build.
    fn envelope(json: &str) -> Message {
        serde_json::from_str(json).expect("the fixture parses as a Telegram message")
    }

    /// **The chats the person actually opens.** Telegram's own "New chat" button
    /// is the only way to open one and be taken to it — no Bot API method moves a
    /// client's view — so those threads must be named too, or the complaint this
    /// answers ("every chat is called New chat") survives the feature that was
    /// supposed to fix it.
    #[tokio::test]
    async fn a_chat_telegram_opened_is_named_by_its_first_message() {
        let (state, _config) = given(BotState::bound(Some(7), 0), "");
        let thread = ChatKey::new(811_091_354, Some(316_592));

        // A thread of a private chat that has not spoken yet: the client opened
        // it, and every one of them carries the same placeholder name.
        let first = envelope(
            "{\"message_id\":1,\"date\":1,\"message_thread_id\":316592,\
             \"chat\":{\"id\":811091354,\"type\":\"private\"},\"text\":\"как дела\"}",
        );
        assert!(names_the_chat_it_is_in(thread, &first, &state).await);

        // Once it is talking, its name is its own and a later message is not a
        // second chance to set it.
        state
            .write()
            .await
            .set_conversation(thread, Some("7fd22c5b-0000-0000-0000-000000000001".into()));
        assert!(!names_the_chat_it_is_in(thread, &first, &state).await);
    }

    /// A topic somebody named is theirs. Telegram says which is which, and the
    /// flag is the only thing that lets this reach a group at all.
    #[tokio::test]
    async fn a_topic_a_person_named_is_left_alone() {
        let (state, _config) = given(BotState::bound(Some(7), 0), "");
        let topic = ChatKey::new(-1_001_234_567_890, Some(57));

        let implicit = envelope(
            "{\"message_id\":1,\"date\":1,\"message_thread_id\":57,\
             \"chat\":{\"id\":-1001234567890,\"type\":\"supergroup\",\"is_forum\":true},\
             \"forum_topic_created\":{\"name\":\"New chat\",\"icon_color\":7322096,\
             \"is_name_implicit\":true}}",
        );
        assert!(
            names_the_chat_it_is_in(topic, &implicit, &state).await,
            "Telegram said the name was a placeholder"
        );

        let chosen = envelope(
            "{\"message_id\":1,\"date\":1,\"message_thread_id\":57,\
             \"chat\":{\"id\":-1001234567890,\"type\":\"supergroup\",\"is_forum\":true},\
             \"forum_topic_created\":{\"name\":\"Работа\",\"icon_color\":7322096}}",
        );
        assert!(!names_the_chat_it_is_in(topic, &chosen, &state).await);

        // And an ordinary message in a group's topic never takes its name: only
        // the flag above, or `/new` and `/clear`, mark one.
        let ordinary = envelope(
            "{\"message_id\":2,\"date\":1,\"message_thread_id\":57,\
             \"chat\":{\"id\":-1001234567890,\"type\":\"supergroup\",\"is_forum\":true},\
             \"text\":\"привет\"}",
        );
        assert!(!names_the_chat_it_is_in(topic, &ordinary, &state).await);
    }

    /// `/clear`, and `/new` where there are no topics, mark the chat they ran in
    /// to be renamed — but only where Telegram has a name that belongs to the
    /// conversation. A private chat is titled by the person and a group by its
    /// members; neither is a conversation's to take.
    #[tokio::test]
    async fn only_a_topic_is_marked_to_be_renamed() {
        let (state, _config) = given(BotState::bound(Some(7), 0), "");
        let private = ChatKey::new(811_091_354, None);
        let topic = ChatKey::new(-1_001_234_567_890, Some(57));

        start_over(private, &state).await;
        start_over(topic, &state).await;

        let state = state.read().await;
        assert!(!state.awaits_title(private), "a private chat has no name to set");
        assert!(state.awaits_title(topic));
        assert_eq!(state.conversation_of(topic), None, "and it starts over too");
    }

    /// `/new` answers somewhere other than where it was typed, so it has to be
    /// able to say where. Only a supergroup's topic has a link form.
    #[test]
    fn a_topic_link_points_at_the_topic() {
        assert_eq!(
            ChatKey::new(-1_001_234_567_890, Some(57)).topic_link().as_deref(),
            Some("https://t.me/c/1234567890/57"),
        );
        assert_eq!(ChatKey::new(-1_001_234_567_890, None).topic_link(), None);
        assert_eq!(ChatKey::new(811_091_354, Some(57)).topic_link(), None);
    }

    /// One Telegram message, as Telegram would have sent it.
    fn said(chat_id: i64, user_id: u64, username: Option<&str>, text: &str) -> Message {
        let named = username.map_or(String::new(), |name| format!(",\"username\":\"{name}\""));
        serde_json::from_str(&format!(
            "{{\"message_id\":1,\"date\":1,               \"chat\":{{\"id\":{chat_id},\"type\":\"private\"}},               \"from\":{{\"id\":{user_id},\"is_bot\":false,\"first_name\":\"A\"{named}}},               \"text\":\"{text}\"}}"
        ))
        .expect("the fixture parses as a Telegram message")
    }

    fn given(state: BotState, allowed: &str) -> (SharedState, SharedConfig) {
        (
            Arc::new(tokio::sync::RwLock::new(state)),
            Arc::new(tokio::sync::RwLock::new(BotConfig {
                bot_token: "test:token".into(),
                allowed_usernames: allowed.to_string(),
                allow_screenshot: false,
            })),
        )
    }

    /// **The gate that replaced "the bot answers in one chat".** With no
    /// allowlist the bot belongs to the person who first spoke to it — in every
    /// chat they write in, which is the feature, and in nobody else's, which is
    /// what keeps the feature from being an open door.
    #[tokio::test]
    async fn with_no_allowlist_the_bot_belongs_to_one_person_in_any_chat() {
        let (state, config) = given(BotState::default(), "");

        assert!(admit(&state, &config, &said(10, 7, Some("owner"), "hi")).await);
        assert_eq!(state.read().await.owner_user_id, Some(7), "learned once");

        // The same person, a different chat — a group, a forum topic, anything.
        assert!(admit(&state, &config, &said(-100200, 7, Some("owner"), "hi")).await);

        // Somebody else, in the chat the owner uses and in their own.
        assert!(!admit(&state, &config, &said(10, 8, Some("stranger"), "hi")).await);
        assert!(!admit(&state, &config, &said(11, 8, Some("stranger"), "hi")).await);

        // And a message with no `from` at all names no account to compare.
        let service: Message = serde_json::from_str(
            "{\"message_id\":2,\"date\":1,\"chat\":{\"id\":10,\"type\":\"private\"},\"text\":\"hi\"}",
        )
        .unwrap();
        assert!(!admit(&state, &config, &service).await);
    }

    /// An allowlist is the whole answer when it is set: it admits its names in
    /// any chat, and refuses the person the bot happens to be bound to.
    #[tokio::test]
    async fn an_allowlist_is_the_whole_answer_when_it_is_set() {
        let (state, config) = given(BotState::bound(Some(7), 0), "Friend, @second");

        assert!(admit(&state, &config, &said(10, 8, Some("friend"), "hi")).await);
        assert!(
            admit(&state, &config, &said(10, 9, Some("SECOND"), "hi")).await,
            "the list is read case-insensitively, and a pasted @ is not a typo"
        );
        assert!(!admit(&state, &config, &said(10, 7, Some("owner"), "hi")).await);
        assert!(
            !admit(&state, &config, &said(10, 8, None, "hi")).await,
            "an account with no username cannot be on a list of usernames"
        );
    }

    /// Updating from 0.2 does not widen who can reach an Astra: until the owner
    /// is learned, the chat that install was bound to is what gates.
    #[tokio::test]
    async fn an_update_from_0_2_keeps_the_reach_it_had() {
        let (state, config) = given(BotState::bound(None, 811091354), "");

        assert!(
            !admit(&state, &config, &said(999, 8, Some("stranger"), "hi")).await,
            "the update must not hand the bot to whoever writes first"
        );
        assert_eq!(state.read().await.owner_user_id, None);

        assert!(admit(&state, &config, &said(811091354, 7, Some("owner"), "hi")).await);
        assert_eq!(
            state.read().await.owner_user_id,
            Some(7),
            "the person in the bound chat is the owner"
        );
        assert!(
            admit(&state, &config, &said(999, 7, Some("owner"), "hi")).await,
            "and from then on they have as many chats as they like"
        );
    }

    /// The refusal a deleted conversation arrives as — in both spellings, since
    /// this plugin runs against daemons that use either.
    #[test]
    fn a_deleted_conversation_is_recognised_from_either_daemon() {
        let today = anyhow::Error::new(ToolError::NotFound(
            "conversation_gone: conversation 7fd22c5b-… no longer exists".into(),
        ));
        assert!(conversation_is_gone(&today));

        let older = anyhow::Error::new(ToolError::Internal(
            "conversation 7fd22c5b-… does not exist".into(),
        ));
        assert!(conversation_is_gone(&older));

        // Not every failure is a gone conversation: these must NOT make the
        // bridge forget an id and silently start a second conversation.
        assert!(!conversation_is_gone(&anyhow::Error::new(
            ToolError::Unauthorized("send_chat_message is not granted".into())
        )));
        assert!(!conversation_is_gone(&anyhow::Error::new(
            ToolError::Internal("the daemon is restarting".into())
        )));
        assert!(!conversation_is_gone(&anyhow::Error::new(
            ToolError::Unavailable("Astra is locked".into())
        )));
    }
}
