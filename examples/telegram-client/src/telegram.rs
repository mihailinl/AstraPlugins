use std::sync::atomic::{AtomicI32, Ordering};
use std::time::Duration;

use frankenstein::AsyncTelegramApi;
use frankenstein::client_reqwest::Bot;
use frankenstein::input_file::{FileUpload, InputFile};
use frankenstein::methods::{
    CreateForumTopicParams, EditForumTopicParams, EditMessageTextParams, SendMessageDraftParams,
    SendMessageParams, SendPhotoParams,
};
use frankenstein::types::{ChatId, Message};
use tracing::warn;

use crate::types::ChatKey;

/// The longest text Telegram accepts in one message. Replies are split on this,
/// not truncated at it — an answer that ran long used to lose its ending.
pub const MAX_MESSAGE_LENGTH: usize = 4096;

/// How long to wait when Telegram says "too fast" and does not say for how long.
const DEFAULT_RETRY_AFTER: Duration = Duration::from_secs(1);

/// One update, as far as this bridge is concerned.
///
/// Deliberately not `frankenstein::updates::Update`. See
/// [`TelegramApi::poll_updates`] for why the bridge reads the envelope itself.
pub enum Incoming {
    Said(Box<Message>),
    /// The stop button was pressed on a streaming draft.
    Stopped { chat: ChatKey, draft_id: i32 },
}

/// Why Telegram refused a call — at the three granularities this bridge reacts
/// differently to, and no finer.
///
/// **This distinction is the difference between streaming and not streaming.**
/// Every refusal used to read the same, so the first failed draft frame of a
/// process turned streaming off for the whole reply — and a timeout on one HTTP
/// request is not evidence that a chat cannot have drafts. A reply that streamed
/// yesterday and arrived in one piece today, with no Stop button on it, is that
/// bug from the outside.
#[derive(Debug)]
pub enum Refusal {
    /// Telegram read the request and will answer the same way every time: the
    /// method is not available in this chat, the bot was blocked, the draft id
    /// is not acceptable. Retrying is pointless; the caller should stop asking.
    Settled { code: u64, description: String },

    /// A 429: the request was fine and arrived too soon after the last one.
    /// `retry_after` is what Telegram said to wait, or one second when it said
    /// nothing.
    TooFast { retry_after: Duration },

    /// The call did not reach Telegram, or Telegram had a bad moment (5xx, a
    /// dropped connection, a body that did not parse). Nothing about the
    /// request is wrong and the next identical one may well work.
    Hiccup(String),
}

impl Refusal {
    /// Read one frankenstein failure as one of the three.
    ///
    /// `error_code` is Telegram's own HTTP-shaped number: 429 is the rate limit,
    /// 5xx is Telegram's side, and every other 4xx is a settled answer about the
    /// request. A code outside those is treated as a hiccup — the kinder
    /// assumption, because the cost of retrying something harmless is one extra
    /// call and the cost of settling on a misread code is a feature switched off
    /// for the life of the process.
    pub fn of(error: &frankenstein::Error) -> Self {
        match error {
            frankenstein::Error::Api(api) => match api.error_code {
                429 => Self::TooFast {
                    retry_after: api
                        .parameters
                        .as_ref()
                        .and_then(|p| p.retry_after)
                        .map_or(DEFAULT_RETRY_AFTER, |s| Duration::from_secs(u64::from(s))),
                },
                code @ 400..=499 => Self::Settled {
                    code,
                    description: api.description.clone(),
                },
                code => Self::Hiccup(format!("Telegram answered {code}: {}", api.description)),
            },
            other => Self::Hiccup(other.to_string()),
        }
    }

    /// Whether Telegram certainly did **not** do the thing — so asking again
    /// cannot do it twice.
    ///
    /// Only a `429`. It is the one refusal with that guarantee: Telegram read
    /// the request, refused it for arriving too soon, and says when to come
    /// back. A [`Hiccup`](Self::Hiccup) is deliberately excluded even though
    /// retrying it would often work — a request that failed *after* Telegram
    /// took it would put the same answer in the chat twice, and a caller that
    /// cannot tell the two apart must not guess with the user's chat.
    pub fn certainly_refused(&self) -> bool {
        matches!(self, Self::TooFast { .. })
    }

    /// How long Telegram asked the caller to wait.
    pub fn retry_after(&self) -> Duration {
        match self {
            Self::TooFast { retry_after } => *retry_after,
            _ => DEFAULT_RETRY_AFTER,
        }
    }
}

impl std::fmt::Display for Refusal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Settled { code, description } => write!(f, "Telegram refused ({code}): {description}"),
            Self::TooFast { retry_after } => {
                write!(f, "Telegram says too fast; retry after {}s", retry_after.as_secs())
            }
            Self::Hiccup(why) => write!(f, "{why}"),
        }
    }
}

impl std::error::Error for Refusal {}

/// Thin wrapper over frankenstein's async Bot providing convenience methods.
///
/// It holds **no chat**: every method is told which chat and which thread to
/// write to, because one bot serves as many chats as talk to it and a single
/// bound chat was what version 0.2 had instead of that. What a chat remembers —
/// whether drafts work in it, which draft is on screen — belongs to the task
/// serving that chat (`bot::Drafts`), not here.
pub struct TelegramApi {
    bot: Bot,
    /// `getUpdates` is read through this rather than through `bot`. Everything
    /// else — sending, editing, drafts, photos — goes through frankenstein.
    http: reqwest::Client,
    token: String,
    /// Shared by every chat, so two chats never show a draft under the same id.
    /// Telegram scopes a draft id to a chat, so it need not be global — but a
    /// number that is unique everywhere cannot be confused with another chat's
    /// when a stop arrives naming it.
    draft_seq: AtomicI32,
}

impl TelegramApi {
    pub fn new(token: &str) -> Self {
        Self {
            bot: Bot::new(token),
            http: reqwest::Client::new(),
            token: token.to_string(),
            draft_seq: AtomicI32::new(0),
        }
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

    /// Send a plain-text message into `chat`, inside its thread if it has one.
    ///
    /// A thread id is where the message that prompted this arrived, so a reply
    /// lands under the topic it answers rather than at the bottom of the group.
    /// A bot in a private chat never sees one.
    pub async fn send(&self, chat: ChatKey, text: &str) -> Result<Message, Refusal> {
        let mut params = SendMessageParams::builder()
            .chat_id(ChatId::Integer(chat.chat_id))
            .text(text)
            .build();
        params.message_thread_id = chat.thread();
        let resp = self
            .bot
            .send_message(&params)
            .await
            .map_err(|e| Refusal::of(&e))?;
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
        chat: ChatKey,
        path: &std::path::Path,
        caption: &str,
    ) -> Result<Message, Refusal> {
        let mut params = SendPhotoParams::builder()
            .chat_id(ChatId::Integer(chat.chat_id))
            .photo(FileUpload::InputFile(InputFile {
                path: path.to_path_buf(),
            }))
            .build();
        params.caption = Some(caption.to_string());
        params.message_thread_id = chat.thread();

        let resp = self
            .bot
            .send_photo(&params)
            .await
            .map_err(|e| Refusal::of(&e))?;
        Ok(resp.result)
    }

    /// Stream a partial answer as a draft — Telegram's own method for this.
    ///
    /// `sendMessageDraft` (Bot API 9.3; `can_stop` and the stop update came with
    /// 10.3) exists because editing a message once a second is a poor way to
    /// show text being written: every edit is a visible jump, and the per-chat
    /// edit ceiling is what sets that second. A draft animates instead, and an
    /// empty `text` shows Telegram's own "Thinking…" — so the user sees the turn
    /// start rather than silence until the first token.
    ///
    /// **A draft is not the message.** Telegram calls it "a temporary 30-second
    /// preview" and nothing persists it. What makes the answer stay in the chat
    /// is the ordinary [`send`](Self::send) once the stream is done — which is
    /// why nothing here needs undoing on failure.
    ///
    /// **It is a private-chat method.** `chat_id` is documented as "the target
    /// private chat"; a group, supergroup or channel is refused. The caller
    /// decides from the chat's own type rather than finding out the hard way
    /// (`bot::Drafts`), and what comes back here says which kind of refusal it
    /// was rather than leaving that to be guessed.
    pub async fn send_draft(
        &self,
        chat: ChatKey,
        draft_id: i32,
        text: &str,
    ) -> Result<(), Refusal> {
        let mut params = SendMessageDraftParams::builder()
            .chat_id(ChatId::Integer(chat.chat_id))
            .text(text)
            .build();
        params.draft_id = Some(draft_id);
        params.message_thread_id = chat.thread();
        // The stop button, and the reason the bridge asks for
        // `stopped_message_generation` updates at all. `keep_on_stop` is left
        // unset — the partial answer is delivered as a real message the moment
        // the stream ends, so a draft kept alongside it would be the same text
        // twice, one copy of which quietly expires.
        params.can_stop = Some(true);

        self.bot
            .send_message_draft(&params)
            .await
            .map(|_| ())
            .map_err(|e| Refusal::of(&e))
    }

    /// Replace the text of a message this bot sent.
    ///
    /// The fallback for streaming where [`send_draft`](Self::send_draft) is not
    /// available, which is every group: post one message as soon as the first
    /// words arrive and rewrite it as more do. `editMessageText` and
    /// `sendMessage` are the two oldest methods in the Bot API, so this works
    /// wherever the newer one does not.
    pub async fn edit(&self, chat: ChatKey, message_id: i32, text: &str) -> Result<(), Refusal> {
        let params = EditMessageTextParams::builder()
            .chat_id(ChatId::Integer(chat.chat_id))
            .message_id(message_id)
            .text(text)
            .build();
        self.bot
            .edit_message_text(&params)
            .await
            .map(|_| ())
            .map_err(|e| Refusal::of(&e))
    }

    /// Open a new topic in a forum group, and say which thread it is.
    ///
    /// **This is the only way a bot can put a second chat in front of somebody.**
    /// A private chat has one thread and no method to add another, so a new topic
    /// in a forum group is the one place where two conversations can sit side by
    /// side in Telegram the way they do in Astra's sidebar.
    ///
    /// The bot must be an administrator of that group with **Manage topics**.
    /// Without it Telegram answers a settled 400, and the caller says so in the
    /// chat rather than retrying: nothing the person types next gets past a
    /// missing right, and the fix is in the group's settings.
    pub async fn create_topic(&self, chat_id: i64, name: &str) -> Result<i32, Refusal> {
        let params = CreateForumTopicParams::builder()
            .chat_id(ChatId::Integer(chat_id))
            .name(name)
            .build();
        let resp = self
            .bot
            .create_forum_topic(&params)
            .await
            .map_err(|e| Refusal::of(&e))?;
        Ok(resp.result.message_thread_id)
    }

    /// Rename one topic.
    ///
    /// Telegram takes a name of 1 to 128 characters, and the caller derives it
    /// from a message, so keeping it inside that is the caller's job. The same
    /// **Manage topics** right as creating one is needed.
    ///
    /// The General topic of a forum is deliberately out of reach: it is renamed
    /// by a different method (`editGeneralForumTopic`) and it is the group's own
    /// first thread, whose name is not any one conversation's to take.
    pub async fn rename_topic(
        &self,
        chat_id: i64,
        thread_id: i32,
        name: &str,
    ) -> Result<(), Refusal> {
        let params = EditForumTopicParams::builder()
            .chat_id(ChatId::Integer(chat_id))
            .message_thread_id(thread_id)
            .name(name)
            .build();
        self.bot
            .edit_forum_topic(&params)
            .await
            .map(|_| ())
            .map_err(|e| Refusal::of(&e))
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
    pub async fn poll_updates(
        &self,
        offset: i64,
        timeout: u32,
    ) -> anyhow::Result<(i64, Vec<Incoming>)> {
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
            // The thread is read too, so a stop inside a forum topic reaches the
            // reply running in THAT topic rather than the group's other one.
            let thread = stopped.get("message_thread_id").and_then(loose_i64);
            match (
                stopped
                    .get("chat")
                    .and_then(|c| c.get("id"))
                    .and_then(loose_i64),
                stopped.get("draft_id").and_then(loose_i64),
            ) {
                (Some(chat_id), Some(draft_id)) => updates.push(Incoming::Stopped {
                    chat: ChatKey::new(chat_id, thread),
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
    use frankenstein::response::{ErrorResponse, ResponseParameters};

    fn api_error(code: u64, description: &str, retry_after: Option<u16>) -> frankenstein::Error {
        frankenstein::Error::Api(ErrorResponse {
            ok: false,
            description: description.to_string(),
            error_code: code,
            parameters: retry_after.map(|retry_after| ResponseParameters {
                migrate_to_chat_id: None,
                retry_after: Some(retry_after),
            }),
        })
    }

    /// The classification the whole of streaming hangs on. A chat that cannot
    /// take drafts says so with a 400 and means it; a 429 or a dropped
    /// connection says nothing about the chat at all, and reading one as the
    /// other is what turned streaming off for a whole reply.
    #[test]
    fn a_rate_limit_is_not_a_refusal_and_a_refusal_is_not_a_hiccup() {
        let settled = Refusal::of(&api_error(400, "Bad Request: chat not found", None));
        assert!(matches!(settled, Refusal::Settled { code: 400, .. }));
        assert!(!settled.certainly_refused(), "asking again cannot help");

        let fast = Refusal::of(&api_error(429, "Too Many Requests", Some(7)));
        assert!(matches!(fast, Refusal::TooFast { .. }));
        assert!(fast.certainly_refused(), "the one refusal safe to retry");
        assert_eq!(fast.retry_after(), Duration::from_secs(7), "Telegram said 7");

        // 429 with no `parameters` still means wait, not "this cannot work".
        let bare = Refusal::of(&api_error(429, "Too Many Requests", None));
        assert!(bare.certainly_refused());
        assert_eq!(bare.retry_after(), DEFAULT_RETRY_AFTER);

        let theirs = Refusal::of(&api_error(502, "Bad Gateway", None));
        assert!(matches!(theirs, Refusal::Hiccup(_)));
        assert!(
            !theirs.certainly_refused(),
            "it may have gone through; sending it again could post it twice"
        );
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
            Incoming::Stopped { chat: ChatKey { chat_id: 811091354, thread_id: None }, draft_id: 1 }
        ));
        assert!(matches!(&updates[1], Incoming::Said(m) if m.text.as_deref() == Some("что делаешь")));
    }

    /// A stop pressed inside a forum topic names that topic, and the bridge
    /// keeps it — a reply is running per topic now, and the press must reach the
    /// one it was shown on.
    #[test]
    fn a_stop_carries_the_topic_it_was_pressed_in() {
        let batch: Vec<serde_json::Value> = serde_json::from_str(
            r#"[{"update_id":1,"stopped_message_generation":{
                  "chat":{"id":-1002,"type":"supergroup"},
                  "message_thread_id":57,"draft_id":9}}]"#,
        )
        .unwrap();

        let (_, updates) = digest_updates(batch);
        assert!(matches!(
            updates[0],
            Incoming::Stopped {
                chat: ChatKey { chat_id: -1002, thread_id: Some(57) },
                draft_id: 9
            }
        ));
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
        let api = TelegramApi::new("test:token");
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
