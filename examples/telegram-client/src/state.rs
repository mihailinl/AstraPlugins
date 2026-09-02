use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tracing::{info, warn};

/// Persistent state — which Telegram chat this bot belongs to, and which Astra
/// conversation it is talking into.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct BotState {
    /// The chat this bot answers in, learned from the first message it sees.
    #[serde(default)]
    pub chat_id: i64,

    /// The Astra conversation this bridge is writing into, as the daemon
    /// resolved it — learned from the reply stream, not chosen here. `None`
    /// means the next message opens a fresh one (a first run, or `/new`).
    ///
    /// Version 0.1 kept a `topic_map` here instead: one Astra conversation per
    /// Telegram forum topic. That model needed `ChatService.CreateConversation`
    /// and `ListConversations`, which a plugin's session token cannot reach, so
    /// it never worked. An old `state.json` still parses — serde ignores the
    /// field it no longer knows — and comes back with no conversation, which is
    /// the right answer: the ids in it were never real.
    #[serde(default)]
    pub conversation_id: Option<String>,
}

impl BotState {
    /// Path to the state file (next to the executable).
    pub fn state_file_path() -> PathBuf {
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .unwrap_or_else(|| PathBuf::from("."));
        exe_dir.join("state.json")
    }

    /// Load state from disk, or return default.
    pub fn load(path: &std::path::Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(data) => match serde_json::from_str::<BotState>(&data) {
                Ok(state) => {
                    info!(
                        "Loaded state: chat_id={}, conversation={}",
                        state.chat_id,
                        state.conversation_id.as_deref().unwrap_or("none yet"),
                    );
                    state
                }
                Err(e) => {
                    warn!("Failed to parse state file: {e}");
                    BotState::default()
                }
            },
            Err(_) => {
                info!("No state file found, starting fresh");
                BotState::default()
            }
        }
    }

    /// Save state to disk.
    pub fn save(&self, path: &std::path::Path) {
        let data = serde_json::to_string_pretty(self).unwrap_or_default();
        if let Err(e) = std::fs::write(path, data) {
            warn!("Failed to save state: {e}");
        }
    }

    /// Remember (or forget) the conversation this bridge writes into, and
    /// persist it. A no-op when nothing changed, so the common case — every
    /// reply chunk carrying the id we already hold — costs no disk write.
    pub fn set_conversation(&mut self, conversation_id: Option<String>) {
        if self.conversation_id == conversation_id {
            return;
        }
        self.conversation_id = conversation_id;
        self.save(&Self::state_file_path());
    }

    /// Remember the chat this bot answers in, and persist it.
    pub fn set_chat_id(&mut self, chat_id: i64) {
        if self.chat_id == chat_id {
            return;
        }
        self.chat_id = chat_id;
        self.save(&Self::state_file_path());
    }
}
