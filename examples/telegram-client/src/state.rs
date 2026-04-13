use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::time::Instant;

use serde::{Deserialize, Serialize};
use tracing::{info, warn};

/// Persistent state for the Telegram bot — topic↔conversation mappings.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct BotState {
    /// User's private chat ID (auto-detected from first message).
    #[serde(default)]
    pub chat_id: i64,

    /// conversation_id (UUID string) → Telegram message_thread_id
    pub topic_map: HashMap<String, i64>,

    /// Telegram message_thread_id → conversation_id (rebuilt from topic_map on load)
    #[serde(skip)]
    pub reverse_map: HashMap<i64, String>,

    /// Conversations currently being streamed from Telegram→Astra (transient, not persisted)
    #[serde(skip)]
    pub active_streams: HashSet<String>,

    /// Per-conversation state for streaming assistant messages from the Astra UI (transient)
    #[serde(skip)]
    pub sync_streaming: HashMap<String, SyncStreamState>,
}

/// Tracks an in-progress streaming message being forwarded from Astra UI to Telegram.
#[derive(Debug, Clone)]
pub struct SyncStreamState {
    pub telegram_message_id: i32,
    pub last_content: String,
    pub last_edit: Instant,
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
                Ok(mut state) => {
                    state.rebuild_reverse_map();
                    info!("Loaded state: {} topic mappings", state.topic_map.len());
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
        // Only serialize the persistent fields
        #[derive(Serialize)]
        struct Persist<'a> {
            chat_id: i64,
            topic_map: &'a HashMap<String, i64>,
        }
        let data = serde_json::to_string_pretty(&Persist {
            chat_id: self.chat_id,
            topic_map: &self.topic_map,
        })
        .unwrap_or_default();

        if let Err(e) = std::fs::write(path, data) {
            warn!("Failed to save state: {e}");
        }
    }

    /// Insert a conversation↔topic mapping.
    pub fn insert_mapping(&mut self, conversation_id: String, thread_id: i64) {
        self.reverse_map
            .insert(thread_id, conversation_id.clone());
        self.topic_map.insert(conversation_id, thread_id);
        self.save(&Self::state_file_path());
    }

    /// Remove a mapping by conversation_id.
    pub fn remove_mapping(&mut self, conversation_id: &str) {
        if let Some(thread_id) = self.topic_map.remove(conversation_id) {
            self.reverse_map.remove(&thread_id);
        }
        self.save(&Self::state_file_path());
    }

    fn rebuild_reverse_map(&mut self) {
        self.reverse_map = self
            .topic_map
            .iter()
            .map(|(cid, tid)| (*tid, cid.clone()))
            .collect();
    }
}
