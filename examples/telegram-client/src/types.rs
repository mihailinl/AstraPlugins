use std::sync::Arc;

use astra_plugin_sdk::DaemonClient;
use serde::{Deserialize, Serialize};
use tokio::sync::{Mutex, RwLock};

use crate::state::BotState;

/// Source ID used for all messages sent from this plugin to the daemon.
pub const SOURCE_ID: &str = "telegram-bot";

/// Plugin config from the daemon.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct BotConfig {
    #[serde(default)]
    pub bot_token: String,
    #[serde(default)]
    pub allowed_usernames: String,
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

pub type SharedDaemon = Arc<Mutex<Option<DaemonClient>>>;
pub type SharedState = Arc<RwLock<BotState>>;
pub type SharedConfig = Arc<RwLock<BotConfig>>;
