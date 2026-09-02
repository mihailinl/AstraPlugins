use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use astra_plugin_sdk::proto::plugin_chat_chunk::Content;
use astra_plugin_sdk::{ChatStream, ToolError};
use tokio_stream::StreamExt;
use tracing::{info, warn};

use crate::telegram::{Incoming, MAX_MESSAGE_LENGTH, TelegramApi};
use crate::types::{
    NEW_CONVERSATION, PLUGIN_THREAD, SharedConfig, SharedHost, SharedI18n, SharedState,
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
/// still does not have to be exactly right: if Telegram disagrees, the refusal
/// costs one frame, and the answer is delivered by `sendMessage` regardless.
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
/// means whichever reply is running.
const STOP_ANY: i32 = i32::MIN;

/// How many messages may wait while a reply is being rendered.
///
/// Small on purpose. Telegram holds what it has not been asked for, so a full
/// queue costs nothing but a pause in reading, and a bridge that buffered
/// hundreds of messages would answer them long after the person gave up.
const QUEUE_DEPTH: usize = 32;

/// Run the Telegram long-polling loop until shutdown.
///
/// Two tasks, and the split is what makes the stop button work. Reading updates
/// used to happen in the same loop that rendered a reply, so for the whole of a
/// turn — exactly when a stop is worth pressing — nothing was reading. Now one
/// task only reads, and hands work to the other:
///
/// * a stop, by button or by `/stop`, goes **straight** to the reply in flight
///   over a `watch` channel, ahead of anything queued;
/// * everything else is queued and answered one at a time, which is unchanged
///   and deliberate — see [`answer_queue`].
pub async fn run_polling_loop(
    telegram: Arc<TelegramApi>,
    state: SharedState,
    host: SharedHost,
    config: SharedConfig,
    i18n: SharedI18n,
    shutdown_rx: tokio::sync::watch::Receiver<bool>,
) {
    info!("Starting Telegram polling loop");

    let (stop_tx, stop_rx) = tokio::sync::watch::channel(0i32);
    let (queue_tx, queue_rx) = tokio::sync::mpsc::channel(QUEUE_DEPTH);

    let reader = tokio::spawn(read_updates(
        telegram.clone(),
        config.clone(),
        queue_tx,
        stop_tx,
        shutdown_rx.clone(),
    ));

    answer_queue(
        telegram, state, host, config, i18n, queue_rx, stop_rx, shutdown_rx,
    )
    .await;

    reader.abort();
    info!("Polling loop shutdown");
}

/// Read updates forever, and sort them into *stop now* and *answer in turn*.
///
/// Nothing here waits on Astra, which is the point: this task keeps draining
/// `getUpdates` for the whole of a reply.
async fn read_updates(
    telegram: Arc<TelegramApi>,
    config: SharedConfig,
    queue: tokio::sync::mpsc::Sender<Box<frankenstein::types::Message>>,
    stop: tokio::sync::watch::Sender<i32>,
    mut shutdown_rx: tokio::sync::watch::Receiver<bool>,
) {
    let mut offset: i64 = 0;

    loop {
        let (next_offset, updates) = tokio::select! {
            result = telegram.poll_updates(offset, 30) => {
                match result {
                    Ok(polled) => polled,
                    Err(e) => {
                        warn!("Poll error: {e}");
                        tokio::time::sleep(Duration::from_secs(5)).await;
                        continue;
                    }
                }
            }
            _ = shutdown_rx.changed() => return,
        };
        // Before acting on any of them: what has been read is read, and asking
        // again for a batch already in hand is how a bridge answers the same
        // message twice.
        offset = next_offset;

        for update in updates {
            match update {
                // The stop button on a streaming draft. It names the draft it
                // was shown on, so a press that arrives late — after the reply
                // it belonged to already finished — cannot stop the next one.
                Incoming::Stopped { chat_id, draft_id } => {
                    if chat_id != telegram.chat_id() {
                        continue;
                    }
                    info!("Stop requested for draft {draft_id}");
                    let _ = stop.send(draft_id);
                }
                Incoming::Said(msg) => {
                    // `/stop` typed out: the same thing for a chat that has no
                    // button, which is any group — drafts are private-chat only.
                    if command_of(msg.text.as_deref().unwrap_or("")) == Some("stop") {
                        if msg.chat.id == telegram.chat_id() && permitted(&config, &msg).await {
                            info!("Stop requested by /stop");
                            let _ = stop.send(STOP_ANY);
                        }
                        continue;
                    }
                    if queue.send(msg).await.is_err() {
                        return; // the answering half is gone; so is the reason to read
                    }
                }
            }
        }
    }
}

/// Answer queued messages, one at a time.
///
/// One at a time is the documented right shape: *wait for `done` before sending
/// again* (`docs/en/3-reference/permissions.md`). The daemon parks a message
/// that arrives mid-turn and that queue holds eight, so a bridge that fired
/// everything at once would spend the budget on itself and start losing the
/// oldest lines.
#[allow(clippy::too_many_arguments)]
async fn answer_queue(
    telegram: Arc<TelegramApi>,
    state: SharedState,
    host: SharedHost,
    config: SharedConfig,
    i18n: SharedI18n,
    mut queue: tokio::sync::mpsc::Receiver<Box<frankenstein::types::Message>>,
    stop_rx: tokio::sync::watch::Receiver<i32>,
    mut shutdown_rx: tokio::sync::watch::Receiver<bool>,
) {
    loop {
        let msg = tokio::select! {
            msg = queue.recv() => match msg {
                Some(msg) => msg,
                None => return,
            },
            _ = shutdown_rx.changed() => return,
        };

        handle_message(&telegram, &state, &host, &config, &i18n, &stop_rx, &msg).await;
    }
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

/// The username allowlist. Empty means everyone, which the settings page warns
/// about in the words the user reads before typing a token in.
async fn permitted(config: &SharedConfig, msg: &frankenstein::types::Message) -> bool {
    let username = msg
        .from
        .as_ref()
        .and_then(|u| u.username.as_deref())
        .unwrap_or("");
    let cfg = config.read().await;
    let allowed = cfg.allowed_set();
    allowed.is_empty() || allowed.contains(&username.to_lowercase())
}

#[allow(clippy::too_many_arguments)]
async fn handle_message(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    host: &SharedHost,
    config: &SharedConfig,
    i18n: &SharedI18n,
    stop_rx: &tokio::sync::watch::Receiver<i32>,
    msg: &frankenstein::types::Message,
) {
    let chat_id = msg.chat.id;
    let thread_id = msg.message_thread_id.map(|t| t as i64);
    let text = msg.text.as_deref().unwrap_or("").trim();

    // The bot answers in exactly one chat: whichever one talks to it first.
    let bound = telegram.chat_id();
    if bound != 0 && chat_id != bound {
        return;
    }
    if bound == 0 {
        info!("Bound to chat {chat_id}");
        telegram.set_chat_id(chat_id);
        state.write().await.set_chat_id(chat_id);
    }
    // Says whether replies can stream as drafts. Set from every message, not
    // just the one that binds: after a restart the bridge has only the sign of
    // a stored `chat_id` to guess from, and this is the message that settles it.
    telegram.set_kind(msg.chat.type_field);

    if !permitted(config, msg).await {
        return;
    }

    if let Some(command) = command_of(text) {
        match command {
            "start" | "help" => {
                if let Err(e) = telegram.send(thread_id, &i18n.t("bot.start")).await {
                    warn!("/start error: {e}");
                }
            }
            "screenshot" => {
                if !config.read().await.allow_screenshot {
                    if let Err(e) = telegram.send(thread_id, &i18n.t("bot.screenshot_off")).await {
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
                        .send(thread_id, &i18n.t("bot.screenshot_unsupported"))
                        .await;
                    if let Err(e) = said {
                        warn!("/screenshot error: {e}");
                    }
                    return;
                }
                screenshot(telegram, i18n, thread_id).await;
            }
            "new" => {
                // Forgetting the id is the whole of it: the next message finds
                // none and asks the daemon to open a conversation, which starts
                // the model with no memory of this one. The old chat is left
                // alone in Astra rather than deleted — a plugin cannot delete
                // one, and quietly destroying the user's history would be the
                // wrong reading of "new chat" anyway.
                state.write().await.set_conversation(None);
                info!("Conversation forgotten; the next message opens a new one");
                if let Err(e) = telegram.send(thread_id, &i18n.t("bot.new")).await {
                    warn!("/new error: {e}");
                }
            }
            _ => {}
        }
        return;
    }

    // A sticker, a photo, somebody joining the group: nothing to say to Astra,
    // and the daemon refuses an empty message outright.
    if text.is_empty() {
        return;
    }

    forward(telegram, state, host, i18n, stop_rx, text, thread_id).await;
}

/// Take a picture of the screen and put it in the chat.
///
/// The capture blocks — a framebuffer read and a PNG encode — so it goes to a
/// blocking thread rather than stalling the polling loop, which would let
/// Telegram's long poll time out underneath it.
///
/// The file is temporary in both senses: written to the system temp directory
/// and removed once Telegram has it, whether or not the upload worked. Nothing
/// keeps a picture of the user's desktop lying around because a send failed.
async fn screenshot(telegram: &Arc<TelegramApi>, i18n: &SharedI18n, thread_id: Option<i64>) {
    let taken = tokio::task::spawn_blocking(|| crate::screen::capture(&std::env::temp_dir())).await;

    let (path, monitor) = match taken {
        Ok(Ok(captured)) => captured,
        Ok(Err(e)) => {
            warn!("Screen capture failed: {e:#}");
            let _ = telegram.send(thread_id, &i18n.t("bot.screenshot_failed")).await;
            return;
        }
        Err(e) => {
            warn!("Screen capture panicked: {e}");
            let _ = telegram.send(thread_id, &i18n.t("bot.screenshot_failed")).await;
            return;
        }
    };

    if let Err(e) = telegram.send_photo(thread_id, &path, &monitor).await {
        warn!("Screenshot upload failed: {e:#}");
        let _ = telegram.send(thread_id, &i18n.t("bot.screenshot_failed")).await;
    }
    if let Err(e) = std::fs::remove_file(&path) {
        warn!("Could not delete {}: {e}", path.display());
    }
}

/// Send one Telegram message to Astra and stream the answer back into the chat.
#[allow(clippy::too_many_arguments)]
async fn forward(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    host: &SharedHost,
    i18n: &SharedI18n,
    stop_rx: &tokio::sync::watch::Receiver<i32>,
    text: &str,
    thread_id: Option<i64>,
) {
    let stream = match open_reply(host, state, text).await {
        Ok(stream) => stream,
        Err(e) => {
            warn!("SendChatMessage failed: {e:#}");
            // Told apart because the answers are opposite: a missing permission
            // is fixed once, in Astra's settings, and nothing the user types in
            // Telegram will get past it.
            let key = if matches!(e.downcast_ref::<ToolError>(), Some(ToolError::Unauthorized(_))) {
                "bot.not_permitted"
            } else {
                "bot.send_failed"
            };
            let _ = telegram.send(thread_id, &i18n.t(key)).await;
            return;
        }
    };

    if let Err(e) = render(telegram, state, i18n, stop_rx, stream, thread_id).await {
        warn!("Reply stream failed: {e:#}");
        let _ = telegram.send(thread_id, &i18n.t("bot.send_failed")).await;
    }
}

/// Open the reply stream, having decided which conversation the message belongs
/// to — and recover from the two ways that decision can turn out to be wrong.
///
/// See [`NEW_CONVERSATION`] for what the three shapes of `conversation_id`
/// mean. Neither fallback here is speculative: both are answers this daemon can
/// actually give, and a bridge that treated either as fatal would stop working
/// the first time a user deleted a chat.
async fn open_reply(host: &SharedHost, state: &SharedState, text: &str) -> Result<ChatStream> {
    let remembered = state.read().await.conversation_id.clone();

    if let Some(id) = remembered {
        match host.send_chat_message(text, &id, false).await {
            Ok(stream) => return Ok(stream),
            Err(e) if conversation_is_gone(&e) => {
                warn!("Astra no longer has conversation {id} — opening a new one");
                state.write().await.set_conversation(None);
            }
            Err(e) => return Err(e),
        }
    }

    match host.send_chat_message(text, NEW_CONVERSATION, false).await {
        Ok(stream) => Ok(stream),
        Err(e) if refuses_to_open_one(&e) => {
            warn!(
                "This Astra will not open a conversation for a plugin ({e:#}) — \
                 falling back to this plugin's own durable thread"
            );
            host.send_chat_message(text, PLUGIN_THREAD, false).await
        }
        Err(e) => Err(e),
    }
}

/// The conversation we remembered is not there any more — the user deleted it.
///
/// The daemon refuses an explicit id that names nothing rather than answering
/// into a conversation no client can open, and it says so from inside
/// `chat_processor::process`, so it arrives as `internal` with the reason in
/// the message. The code alone cannot tell this from any other internal fault;
/// the sentence is the only handle the wire gives.
fn conversation_is_gone(error: &anyhow::Error) -> bool {
    matches!(
        error.downcast_ref::<ToolError>(),
        Some(ToolError::Internal(message)) if message.contains("does not exist")
    )
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
/// draft **expires** — it is a preview, not a message, and an answer left in
/// one would vanish from the chat about thirty seconds later.
async fn render(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    i18n: &SharedI18n,
    stop_rx: &tokio::sync::watch::Receiver<i32>,
    mut stream: ChatStream,
    thread_id: Option<i64>,
) -> Result<()> {
    let mut answer = String::new();
    // The message being rewritten, and what it currently says — so an edit that
    // would change nothing is never sent. `posted` stays `None` for a draft:
    // nothing was posted, and the delivery below reads it exactly that way.
    let mut posted: Option<i32> = None;
    let mut shown = String::new();
    let mut next_frame = Instant::now();

    let draft_id = telegram.next_draft_id();
    // Telegram's own "Thinking…", shown by sending a draft with no text. The
    // point is the gap before it: Astra can spend seconds on tools before the
    // first token, and the chat used to sit silent through all of it.
    if telegram.drafts_enabled() {
        let _ = telegram.send_draft(thread_id, draft_id, "").await;
    }

    // This turn's stop requests, and only this turn's: a press that arrived
    // while the last reply was finishing is marked seen here rather than
    // cutting this one off before it starts.
    let mut stop_rx = stop_rx.clone();
    stop_rx.borrow_and_update();
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
                if telegram.drafts_enabled() {
                    let _ = telegram.send_draft(thread_id, draft_id, &shown).await;
                }
                continue;
            }
        };

        // Which conversation the daemon put this in. It is on every chunk, and
        // the first one is how a freshly opened conversation gets its id here.
        // Read first: this runs once per token, and only the first of them has
        // anything to say.
        if !chunk.conversation_id.is_empty()
            && state.read().await.conversation_id.as_deref() != Some(&chunk.conversation_id)
        {
            state
                .write()
                .await
                .set_conversation(Some(chunk.conversation_id.clone()));
        }

        match chunk.content {
            Some(Content::Text(delta)) => {
                answer.push_str(&delta);
                if Instant::now() >= next_frame {
                    show(telegram, thread_id, draft_id, &mut posted, &mut shown, &answer).await;
                    // Read after `show`, because `show` is where drafts can
                    // turn out to be unavailable and the pace drops with them.
                    next_frame = Instant::now()
                        + if telegram.drafts_enabled() {
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
        info!("Reply stopped by the user after {} bytes", answer.len());
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

    // The whole answer, in as many messages as it takes.
    for (index, part) in split_message(&answer).into_iter().enumerate() {
        if index == 0 {
            match posted {
                Some(id) if shown != part => telegram.edit(id, &part).await?,
                Some(_) => {}
                None => {
                    telegram.send(thread_id, &part).await?;
                }
            }
        } else {
            telegram.send(thread_id, &part).await?;
        }
    }
    Ok(())
}

/// Put `text`'s first message-worth on screen: push a draft, or failing that
/// edit the message already there, or post one if this is the first thing to
/// show.
///
/// A failed frame is dropped rather than reported: the next is along shortly
/// and the finished answer is delivered by `render` whatever happened here.
async fn show(
    telegram: &Arc<TelegramApi>,
    thread_id: Option<i64>,
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
    if telegram.drafts_enabled() {
        if telegram.send_draft(thread_id, draft_id, &head).await.is_ok() {
            *shown = head;
            return;
        }
        // Still on: a lost frame, and the next is along shortly. Turned off by
        // that refusal: fall through now rather than wait, so the first words
        // reach the chat through the path that does work.
        if telegram.drafts_enabled() {
            return;
        }
    }

    match *posted {
        Some(id) => {
            if telegram.edit(id, &head).await.is_ok() {
                *shown = head;
            }
        }
        None => {
            if let Ok(message) = telegram.send(thread_id, &head).await {
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
}
