use std::fmt;
use std::sync::Arc;

use astra_plugin_sdk::Host;
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;

use crate::state::BotState;

/// The `conversation_id` that asks the daemon to open a **new** conversation.
///
/// `PluginHostService.SendChatMessage` reads the field three ways, and the
/// difference is the whole of how this bridge works:
///
/// * **empty** — this plugin's own durable thread. One per plugin, filed under
///   Astra's automation threads, rotated by the daemon after a while. It is the
///   documented default and it is the fallback below, but it gives a chat
///   bridge no way to start over, no thread the user can point at, and — the
///   reason this plugin cannot use it as its main path — only ONE of them, so
///   every Telegram chat would be talking into the same memory.
/// * **the nil UUID** — `chat_processor::process` reads it as *mint a fresh
///   `Main` conversation*, titled from this first message. That is a normal
///   chat: it appears in Astra's sidebar, the user can open it, and it does not
///   rotate underneath us. It is how each Telegram chat gets a conversation of
///   its own.
/// * **any other UUID** — that conversation, which must exist. The daemon
///   refuses an id that names nothing rather than answering into a void
///   (`chat_processor.rs`, "An explicit id must NAME a conversation"), and says
///   so as NOT_FOUND — see [`crate::bot::conversation_is_gone`].
///
/// So the bridge mints once **per Telegram chat**, remembers the id the reply
/// came back on, and keeps using it until `/new`. The SDK's advice is "leave it
/// empty and never store the id back", and the reason it gives is thread
/// rotation — which is a property of the durable thread, not of a `Main`
/// conversation. The daemon states the rule for a stored id in `plugin.proto`:
/// an id the plugin was *told* may be stored across restarts, and a gone one is
/// refused rather than redirected. Both ways this can be wrong are recoverable
/// and are recovered from in [`crate::bot`]: a daemon that refuses the nil id
/// falls back to the durable thread, and a remembered id whose conversation the
/// user has deleted is dropped and minted again.
pub const NEW_CONVERSATION: &str = "00000000-0000-0000-0000-000000000000";

/// This plugin's own durable thread — see [`NEW_CONVERSATION`].
pub const PLUGIN_THREAD: &str = "";

/// One Telegram conversation, and the unit this bridge keeps one Astra
/// conversation — one queue, one reply at a time, one draft — for.
///
/// **`thread_id` is the raw `message_thread_id`, not only a forum topic.** In a
/// forum that is the topic the message was written in, which is what version
/// 0.1 keyed its `topic_map` on and what a user means by "a chat". Telegram also
/// sets it on a reply thread in an ordinary supergroup, and keying on it there
/// gives each of those its own Astra conversation too — which is the same
/// answer to the same question, and it keeps one notion of "where this went"
/// rather than two: the id this bridge files a conversation under is the id it
/// sends the reply back to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ChatKey {
    pub chat_id: i64,
    pub thread_id: Option<i64>,
}

impl ChatKey {
    pub fn new(chat_id: i64, thread_id: Option<i64>) -> Self {
        Self { chat_id, thread_id }
    }

    /// Where this message came from, which is also where its reply goes.
    pub fn of(msg: &frankenstein::types::Message) -> Self {
        Self::new(msg.chat.id, msg.message_thread_id.map(i64::from))
    }

    /// What `sendMessage` and friends want: `message_thread_id`, which Telegram
    /// declares as a 32-bit integer.
    pub fn thread(&self) -> Option<i32> {
        self.thread_id.map(|t| t as i32)
    }

    /// A link a person can follow to this topic.
    ///
    /// `/new` opens a conversation somewhere other than the chat the command was
    /// typed in, so it has to be able to say where. Telegram addresses a topic of
    /// a private supergroup as `t.me/c/<id>/<topic>`, with the `-100` prefix of
    /// the chat id cut off — and only a supergroup has that form, so a chat with
    /// no thread, or one whose id is not a supergroup's, has no link and says so
    /// rather than composing one that opens nothing.
    pub fn topic_link(&self) -> Option<String> {
        let thread = self.thread_id?;
        let id = self.chat_id.to_string();
        let internal = id.strip_prefix("-100")?;
        Some(format!("https://t.me/c/{internal}/{thread}"))
    }
}

/// How a chat is written into `state.json`, and read back out of it.
///
/// A JSON object's keys are strings, so the map of remembered conversations is
/// keyed on this. `811091354` is a chat with no thread; `-1001234567890:57` is
/// topic 57 of that group.
impl fmt::Display for ChatKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self.thread_id {
            Some(thread) => write!(f, "{}:{thread}", self.chat_id),
            None => write!(f, "{}", self.chat_id),
        }
    }
}

impl std::str::FromStr for ChatKey {
    type Err = ();

    fn from_str(text: &str) -> Result<Self, Self::Err> {
        match text.split_once(':') {
            Some((chat, thread)) => Ok(Self::new(
                chat.parse().map_err(|_| ())?,
                Some(thread.parse().map_err(|_| ())?),
            )),
            None => Ok(Self::new(text.parse().map_err(|_| ())?, None)),
        }
    }
}

/// Plugin config from the daemon.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct BotConfig {
    #[serde(default)]
    pub bot_token: String,
    #[serde(default)]
    pub allowed_usernames: String,
    /// Whether `/screenshot` works. **Off unless switched on**, and the default
    /// is the point: every other thing this bridge does is a conversation with
    /// an AI, and this one is a live picture of the desktop. Anyone who can
    /// reach the bot can run it, which with an empty allowlist is the one person
    /// it bound itself to — so the two settings are read together or neither is
    /// read.
    #[serde(default)]
    pub allow_screenshot: bool,
}

impl BotConfig {
    /// Parse allowed usernames into a set.
    pub fn allowed_set(&self) -> Vec<String> {
        if self.allowed_usernames.is_empty() {
            return vec![];
        }
        self.allowed_usernames
            .split(',')
            .map(|s| s.trim().trim_start_matches('@').to_lowercase())
            .filter(|s| !s.is_empty())
            .collect()
    }
}

/// Astra, as a plugin sees it: `PluginHostService`, and nothing else.
///
/// This used to be `Arc<dyn Daemon>` off `PluginContext::daemon`. That client
/// speaks to `ChatService`, and the daemon registers every plugin as
/// `ClientType::PluginClient`, whose session token its auth interceptor refuses
/// on any path outside `/astra.PluginHostService/` — so every call through it
/// came back `PermissionDenied` and this plugin could not send a single
/// message. `Host::send_chat_message` is on the host service and works.
pub type SharedHost = Arc<dyn Host>;
pub type SharedState = Arc<RwLock<BotState>>;
pub type SharedConfig = Arc<RwLock<BotConfig>>;
pub type SharedI18n = Arc<astra_plugin_sdk::I18n>;
