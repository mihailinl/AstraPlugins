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
///   bridge no way to start over and no thread the user can point at.
/// * **the nil UUID** — `chat_processor::process` reads it as *mint a fresh
///   `Main` conversation*, titled from this first message. That is a normal
///   chat: it appears in Astra's sidebar, the user can open it, and it does not
///   rotate underneath us.
/// * **any other UUID** — that conversation, which must exist. The daemon
///   refuses an id that names nothing rather than answering into a void
///   (`chat_processor.rs`, "An explicit id must NAME a conversation").
///
/// So the bridge mints once, remembers the id the reply came back on, and keeps
/// using it until `/new`. The SDK's advice is "leave it empty and never store
/// the id back", and the reason it gives is thread rotation — which is a
/// property of the durable thread, not of a `Main` conversation. Both ways this
/// can be wrong are recoverable and are recovered from in [`crate::bot`]: a
/// daemon that refuses the nil id falls back to the durable thread, and a
/// remembered id whose conversation the user has deleted is dropped and minted
/// again.
pub const NEW_CONVERSATION: &str = "00000000-0000-0000-0000-000000000000";

/// This plugin's own durable thread — see [`NEW_CONVERSATION`].
pub const PLUGIN_THREAD: &str = "";

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
    /// reach the bot can run it, which with an empty allowlist is anyone who
    /// finds it — so the two settings are read together or neither is read.
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
            .map(|s| s.trim().to_lowercase())
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
