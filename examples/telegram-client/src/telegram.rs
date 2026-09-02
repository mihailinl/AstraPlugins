use std::sync::atomic::{AtomicBool, AtomicI32, AtomicI64, Ordering};

use anyhow::Result;
use frankenstein::AsyncTelegramApi;
use frankenstein::client_reqwest::Bot;
use frankenstein::input_file::{FileUpload, InputFile};
use frankenstein::methods::{
    EditMessageTextParams, SendMessageDraftParams, SendMessageParams, SendPhotoParams,
};
use frankenstein::types::{ChatId, ChatType, Message};
use tracing::warn;

/// The longest text Telegram accepts in one message. Replies are split on this,
/// not truncated at it — an answer that ran long used to lose its ending.
pub const MAX_MESSAGE_LENGTH: usize = 4096;

/// One update, as far as this bridge is concerned.
///
/// Deliberately not `frankenstein::updates::Update`. See
/// [`TelegramApi::poll_updates`] for why the bridge reads the envelope itself.
pub enum Incoming {
    Said(Box<Message>),
    /// The stop button was pressed on a streaming draft.
    Stopped { chat_id: i64, draft_id: i32 },
}

/// Thin wrapper over frankenstein's async Bot providing convenience methods.
pub struct TelegramApi {
    bot: Bot,
    /// `getUpdates` is read through this rather than through `bot`. Everything
    /// else — sending, editing, drafts, photos — goes through frankenstein.
    http: reqwest::Client,
    token: String,
    chat_id: AtomicI64,
    /// Whether `sendMessageDraft` is worth trying in the bound chat. See
    /// [`TelegramApi::send_draft`] for both ways this turns off.
    drafts: AtomicBool,
    /// Set the first time a draft is accepted. Until then a refusal is read as
    /// *this chat cannot do drafts*; after it, as one lost frame.
    drafts_proven: AtomicBool,
    draft_seq: AtomicI32,
}

impl TelegramApi {
    pub fn new(token: &str, chat_id: i64) -> Self {
        Self {
            bot: Bot::new(token),
            http: reqwest::Client::new(),
            token: token.to_string(),
            chat_id: AtomicI64::new(chat_id),
            // A guess, and only until the first message arrives: a private
            // chat's id is positive and a group's is negative, which is all
            // there is to go on for a `chat_id` restored from disk. `set_kind`
            // replaces it with the type Telegram states.
            drafts: AtomicBool::new(chat_id > 0),
            drafts_proven: AtomicBool::new(false),
            draft_seq: AtomicI32::new(0),
        }
    }

    pub fn chat_id(&self) -> i64 {
        self.chat_id.load(Ordering::Relaxed)
    }

    pub fn set_chat_id(&self, id: i64) {
        self.chat_id.store(id, Ordering::Relaxed);
    }

    /// Record what kind of chat the bot is bound to.
    ///
    /// `sendMessageDraft` takes the numeric id of a **private** chat; a group,
    /// supergroup or channel is refused. Telegram states the type on every
    /// message, so the bridge asks rather than infers.
    pub fn set_kind(&self, kind: ChatType) {
        self.drafts
            .store(matches!(kind, ChatType::Private), Ordering::Relaxed);
    }

    pub fn drafts_enabled(&self) -> bool {
        self.drafts.load(Ordering::Relaxed)
    }

    /// A fresh id per reply. Telegram animates updates that share a `draft_id`
    /// and replaces without animation when it changes, so reusing one across
    /// replies would animate the new answer out of the old one's text. Zero is
    /// not a valid id, which is what the wrapping skips.
    pub fn next_draft_id(&self) -> i32 {
        match self.draft_seq.fetch_add(1, Ordering::Relaxed).wrapping_add(1) {
            0 => 1,
            id => id,
        }
    }

    /// Send a plain-text message, optionally inside a forum topic.
    ///
    /// `thread_id` is where the message that prompted this arrived, so a reply
    /// lands under the message it answers rather than at the bottom of the
    /// group. A bot in a plain chat never sees one.
    pub async fn send(&self, thread_id: Option<i64>, text: &str) -> Result<Message> {
        let mut params = SendMessageParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .text(text)
            .build();
        params.message_thread_id = thread_id.map(|t| t as i32);
        let resp = self
            .bot
            .send_message(&params)
            .await
            .map_err(|e| anyhow::anyhow!("send_message: {e}"))?;
        Ok(resp.result)
    }

    /// Upload a picture from disk, with a caption under it.
    ///
    /// Telegram takes the bytes as `multipart/form-data`, and frankenstein's
    /// `InputFile` is a path rather than a buffer, so the caller writes the file
    /// first and deletes it after. The photo is re-encoded and downscaled by
    /// Telegram; a screenshot that must stay pixel-exact would have to go as a
    /// document instead.
    pub async fn send_photo(
        &self,
        thread_id: Option<i64>,
        path: &std::path::Path,
        caption: &str,
    ) -> Result<Message> {
        let mut params = SendPhotoParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .photo(FileUpload::InputFile(InputFile {
                path: path.to_path_buf(),
            }))
            .build();
        params.caption = Some(caption.to_string());
        params.message_thread_id = thread_id.map(|t| t as i32);

        let resp = self
            .bot
            .send_photo(&params)
            .await
            .map_err(|e| anyhow::anyhow!("send_photo: {e}"))?;
        Ok(resp.result)
    }

    /// Stream a partial answer as a draft — Telegram's own method for this.
    ///
    /// `sendMessageDraft` (Bot API 9.3, unrestricted since 9.5) exists because
    /// editing a message once a second is a poor way to show text being
    /// written: every edit is a visible jump, and the per-chat edit ceiling is
    /// what sets that second. A draft animates instead, and empty `text` shows
    /// Telegram's own "Thinking…" — so the user sees the turn start rather than
    /// silence until the first token.
    ///
    /// **A draft is not the message.** It is a preview that expires on its own
    /// in about thirty seconds, and nothing persists it. What makes the answer
    /// stay in the chat is the ordinary [`send`](Self::send) once the stream is
    /// done — which is why nothing here needs undoing on failure.
    ///
    /// Two things turn drafts off, and they are told apart by whether one has
    /// ever worked: the first refusal means this chat cannot have them (a
    /// group, or a Bot API older than 9.3) and drops the bridge back to editing
    /// for good; a later one is a single lost frame of an animation and the
    /// next is 250ms away.
    pub async fn send_draft(&self, thread_id: Option<i64>, draft_id: i32, text: &str) -> Result<()> {
        let mut params = SendMessageDraftParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .text(text)
            .build();
        params.draft_id = Some(draft_id);
        params.message_thread_id = thread_id.map(|t| t as i32);
        // The stop button, and the reason the bridge asks for
        // `StoppedMessageGeneration` updates at all. `keep_on_stop` is left
        // unset — the partial answer is delivered as a real message the moment
        // the stream ends, so a draft kept alongside it would be the same text
        // twice, one copy of which quietly expires.
        params.can_stop = Some(true);

        match self.bot.send_message_draft(&params).await {
            Ok(_) => {
                self.drafts_proven.store(true, Ordering::Relaxed);
                Ok(())
            }
            Err(e) => {
                if !self.drafts_proven.load(Ordering::Relaxed) {
                    warn!(
                        "This chat will not take streaming drafts ({e}) — falling back to \
                         rewriting a posted message, which every Telegram client supports"
                    );
                    self.drafts.store(false, Ordering::Relaxed);
                }
                Err(anyhow::anyhow!("send_message_draft: {e}"))
            }
        }
    }

    /// Replace the text of a message this bot sent.
    ///
    /// The fallback for streaming where [`send_draft`](Self::send_draft) is not
    /// available: post one message as soon as the first words arrive and
    /// rewrite it as more do. `editMessageText` and `sendMessage` are the two
    /// oldest methods in the Bot API, so this works wherever the newer one does
    /// not.
    pub async fn edit(&self, message_id: i32, text: &str) -> Result<()> {
        let params = EditMessageTextParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .message_id(message_id)
            .text(text)
            .build();
        self.bot
            .edit_message_text(&params)
            .await
            .map_err(|e| anyhow::anyhow!("edit_message: {e}"))?;
        Ok(())
    }

    /// Long-poll for updates. Returns the offset to ask from next, and the
    /// updates this bridge understood.
    ///
    /// **`allowed_updates` is named, not left out.** Telegram's default set is
    /// not everything, and `stopped_message_generation` — the press of the stop
    /// button on a streaming draft — is not in it. A bridge that omitted this
    /// would offer a button that silently did nothing. Naming the two kinds
    /// this plugin acts on also stops Telegram sending the dozen it ignores.
    ///
    /// **Why this reads the envelope itself instead of calling frankenstein's
    /// `get_updates`.** That returns `Vec<Update>`, so one update the crate
    /// cannot deserialise fails the whole batch — and the batch failing means
    /// no `update_id` is confirmed, so Telegram sends the same batch again, and
    /// the bot never reads anything else for as long as it runs. A single
    /// unparseable update is a permanent outage.
    ///
    /// That is not hypothetical. frankenstein 0.52.0 declares
    /// `MessageGenerationStopped::draft_id` as `i64`, and Telegram sends it as
    /// a **string** (`"draft_id":"1"`), so pressing Stop wedged the bridge:
    /// *invalid type: string "1", expected i64*. The crate is wrong and should
    /// be fixed upstream; what is fixed here is the shape that let one bad
    /// field stop everything.
    ///
    /// So: the offset advances from the raw `update_id` whatever happens to the
    /// rest of the update, and each one is parsed on its own.
    pub async fn poll_updates(&self, offset: i64, timeout: u32) -> Result<(i64, Vec<Incoming>)> {
        let response = self
            .http
            .post(format!(
                "https://api.telegram.org/bot{}/getUpdates",
                self.token
            ))
            .json(&serde_json::json!({
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": ["message", "stopped_message_generation"],
            }))
            // Long polling holds the request open for `timeout` seconds by
            // design; the margin is for the round trip, not the wait.
            .timeout(std::time::Duration::from_secs(u64::from(timeout) + 15))
            .send()
            .await
            .map_err(|e| anyhow::anyhow!("get_updates: {e}"))?;

        let envelope: GetUpdates = response
            .json()
            .await
            .map_err(|e| anyhow::anyhow!("get_updates: reading the envelope: {e}"))?;

        if !envelope.ok {
            let described = envelope.description.unwrap_or_else(|| "no reason".into());
            return Err(anyhow::anyhow!("get_updates: Telegram refused: {described}"));
        }

        let (next_offset, updates) = digest_updates(envelope.result);
        Ok((next_offset.unwrap_or(offset), updates))
    }
}

/// The `getUpdates` envelope, kept deliberately loose: the updates stay as raw
/// JSON so that one of them being unreadable is one update lost, not a batch.
#[derive(serde::Deserialize)]
struct GetUpdates {
    ok: bool,
    #[serde(default)]
    result: Vec<serde_json::Value>,
    description: Option<String>,
}

/// Turn a batch of raw updates into the offset to ask from next and the ones
/// this bridge acts on.
///
/// The offset comes from `update_id` alone. Nothing else in an update can stop
/// it advancing — that is the whole point, and the reason this is a function
/// with tests rather than a loop inside the poller.
fn digest_updates(values: Vec<serde_json::Value>) -> (Option<i64>, Vec<Incoming>) {
    let mut next_offset = None;
    let mut updates = Vec::new();

    for value in values {
        if let Some(id) = value.get("update_id").and_then(serde_json::Value::as_i64) {
            next_offset = Some(next_offset.map_or(id + 1, |seen: i64| seen.max(id + 1)));
        } else {
            // No id at all: it cannot be acknowledged, and acting on it would
            // mean acting on it again on every poll from here on.
            warn!("Skipping an update with no update_id");
            continue;
        }

        if let Some(stopped) = value.get("stopped_message_generation") {
            match (
                stopped.get("chat").and_then(|c| c.get("id")).and_then(loose_i64),
                stopped.get("draft_id").and_then(loose_i64),
            ) {
                (Some(chat_id), Some(draft_id)) => updates.push(Incoming::Stopped {
                    chat_id,
                    draft_id: draft_id as i32,
                }),
                _ => warn!("A stop arrived without a chat or a draft id: {stopped}"),
            }
            continue;
        }

        if let Some(message) = value.get("message") {
            match serde_json::from_value::<Message>(message.clone()) {
                Ok(message) => updates.push(Incoming::Said(Box::new(message))),
                // Lost, not fatal: the id above is already acknowledged, so the
                // bridge reads on instead of asking for this batch forever.
                Err(e) => warn!("Skipping a message this build cannot read: {e}"),
            }
        }
    }

    (next_offset, updates)
}

/// A number Telegram may have written as a string.
///
/// `draft_id` comes back quoted — `"draft_id":"1"` — which is what broke
/// frankenstein's typed update. Reading both shapes costs nothing and means a
/// field that changes representation cannot stop the bridge again.
fn loose_i64(value: &serde_json::Value) -> Option<i64> {
    value
        .as_i64()
        .or_else(|| value.as_str().and_then(|s| s.parse().ok()))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The bridge asks Telegram what kind of chat it is in, and the answer
    /// decides whether replies can stream as drafts at all.
    #[test]
    fn only_a_private_chat_takes_drafts() {
        let api = TelegramApi::new("test:token", -100123);
        assert!(!api.drafts_enabled(), "a negative id reads as a group");

        api.set_kind(ChatType::Private);
        assert!(api.drafts_enabled());

        for kind in [ChatType::Group, ChatType::Supergroup, ChatType::Channel] {
            api.set_kind(kind);
            assert!(!api.drafts_enabled(), "{kind:?} cannot take a draft");
        }
    }

    /// The batch that used to wedge the bridge, byte for byte from a real log.
    ///
    /// Telegram writes `draft_id` as a **string**, frankenstein 0.52 declares
    /// it `i64`, and its typed `get_updates` therefore failed the whole
    /// response: *invalid type: string "1", expected i64*. No `update_id` was
    /// confirmed, so the same batch came back on every poll and the bot never
    /// read another message for as long as it ran.
    #[test]
    fn the_stop_that_wedged_the_bridge() {
        let batch: Vec<serde_json::Value> = serde_json::from_str(
            r#"[
              {"update_id":556763401,
               "stopped_message_generation":{"chat":{"id":811091354,"type":"private"},"draft_id":"1"}},
              {"update_id":556763402,
               "message":{"message_id":305,"date":1788341203,
                          "chat":{"id":811091354,"type":"private"},"text":"что делаешь"}}
            ]"#,
        )
        .expect("the fixture is the response Telegram actually sent");

        let (next_offset, updates) = digest_updates(batch);

        assert_eq!(next_offset, Some(556763403), "the batch must be acknowledged");
        assert_eq!(updates.len(), 2, "neither update is lost to the other");
        assert!(matches!(
            updates[0],
            Incoming::Stopped { chat_id: 811091354, draft_id: 1 }
        ));
        assert!(matches!(&updates[1], Incoming::Said(m) if m.text.as_deref() == Some("что делаешь")));
    }

    /// The shape of the bug, not just the one instance of it: whatever an
    /// update turns out to contain, the offset moves past it. Anything else is
    /// an outage that lasts until someone restarts the plugin.
    #[test]
    fn an_unreadable_update_is_skipped_not_repeated() {
        let batch: Vec<serde_json::Value> = serde_json::from_str(
            r#"[
              {"update_id":10,"message":{"message_id":"not a number"}},
              {"update_id":11,"edited_message":{"message_id":1}},
              {"update_id":12,
               "message":{"message_id":7,"date":1,"chat":{"id":5,"type":"private"},"text":"hi"}}
            ]"#,
        )
        .unwrap();

        let (next_offset, updates) = digest_updates(batch);

        assert_eq!(next_offset, Some(13), "a bad update is still acknowledged");
        assert_eq!(updates.len(), 1, "only the readable one is acted on");
        assert!(matches!(&updates[0], Incoming::Said(m) if m.text.as_deref() == Some("hi")));
    }

    /// An update with no id cannot be acknowledged, so acting on it would mean
    /// acting on it again on every poll from here on.
    #[test]
    fn an_update_with_no_id_is_ignored() {
        let batch: Vec<serde_json::Value> =
            serde_json::from_str(r#"[{"message":{"message_id":1}}]"#).unwrap();
        assert_eq!(digest_updates(batch).0, None);
    }

    /// Telegram has written this id both ways; the bridge reads both.
    #[test]
    fn a_number_telegram_quoted_is_still_a_number() {
        assert_eq!(loose_i64(&serde_json::json!(7)), Some(7));
        assert_eq!(loose_i64(&serde_json::json!("7")), Some(7));
        assert_eq!(loose_i64(&serde_json::json!("-7")), Some(-7));
        assert_eq!(loose_i64(&serde_json::json!("seven")), None);
        assert_eq!(loose_i64(&serde_json::json!(null)), None);
    }

    /// Zero is not a draft id, and a counter that runs long enough reaches it.
    #[test]
    fn a_draft_id_is_never_zero() {
        let api = TelegramApi::new("test:token", 1);
        assert_eq!(api.next_draft_id(), 1, "the first reply gets a usable id");
        assert_ne!(api.next_draft_id(), 1, "a second reply gets its own");

        // The one counter value whose successor is zero.
        api.draft_seq.store(-1, Ordering::Relaxed);
        assert_eq!(api.next_draft_id(), 1);

        // And the wrap itself, which is merely large rather than invalid.
        api.draft_seq.store(i32::MAX, Ordering::Relaxed);
        assert_eq!(api.next_draft_id(), i32::MIN);
    }
}
