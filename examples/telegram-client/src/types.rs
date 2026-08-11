use std::sync::Arc;

use astra_plugin_sdk::Daemon;
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;

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

/// The daemon, as the plugin context hands it over. It used to be an
/// `Arc<Mutex<Option<DaemonClient>>>`: every call site locked it, matched the
/// `Option`, and had a "daemon not connected" branch that could not happen
/// after `on_start`.
pub type SharedDaemon = Arc<dyn Daemon>;
pub type SharedState = Arc<RwLock<BotState>>;
pub type SharedConfig = Arc<RwLock<BotConfig>>;
pub type SharedI18n = Arc<astra_plugin_sdk::I18n>;
