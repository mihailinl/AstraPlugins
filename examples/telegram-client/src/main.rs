mod bot;
mod commands;
mod state;
mod streaming;
mod sync;
mod telegram;
mod types;

use std::sync::Arc;

use astra_plugin_sdk::prelude::*;
use tokio::sync::{watch, Mutex, RwLock};
use tracing::info;

use state::BotState;
use telegram::TelegramApi;
use types::{BotConfig, SharedConfig, SharedDaemon};

struct TelegramBotPlugin {
    daemon: SharedDaemon,
    config: SharedConfig,
    state: types::SharedState,
    telegram: Arc<Mutex<Option<Arc<TelegramApi>>>>,
    shutdown_tx: Arc<Mutex<Option<watch::Sender<bool>>>>,
    polling_handle: Arc<Mutex<Option<tokio::task::JoinHandle<()>>>>,
}

impl TelegramBotPlugin {
    fn new() -> Self {
        let state = BotState::load(&BotState::state_file_path());
        Self {
            daemon: Arc::new(Mutex::new(None)),
            config: Arc::new(RwLock::new(BotConfig::default())),
            state: Arc::new(RwLock::new(state)),
            telegram: Arc::new(Mutex::new(None)),
            shutdown_tx: Arc::new(Mutex::new(None)),
            polling_handle: Arc::new(Mutex::new(None)),
        }
    }

    async fn start_bot(&self) {
        // Check prerequisites
        let cfg = self.config.read().await.clone();
        if cfg.bot_token.is_empty() {
            info!("Bot token not configured, not starting");
            return;
        }
        if self.daemon.lock().await.is_none() {
            info!("Daemon client not ready, not starting");
            return;
        }

        // Stop previous instance if running
        self.stop_bot().await;

        let chat_id = self.state.read().await.chat_id;
        let tg = Arc::new(TelegramApi::new(&cfg.bot_token, chat_id));
        *self.telegram.lock().await = Some(tg.clone());

        let (tx, rx) = watch::channel(false);
        *self.shutdown_tx.lock().await = Some(tx);

        let state = self.state.clone();
        let daemon = self.daemon.clone();
        let config = self.config.clone();

        let handle = tokio::spawn(async move {
            bot::run_polling_loop(tg, state, daemon, config, rx).await;
        });
        *self.polling_handle.lock().await = Some(handle);

        info!("Telegram bot started (chat_id={chat_id})");
    }

    async fn stop_bot(&self) {
        if let Some(tx) = self.shutdown_tx.lock().await.take() {
            let _ = tx.send(true);
        }
        if let Some(handle) = self.polling_handle.lock().await.take() {
            handle.abort();
            let _ = handle.await;
        }
        *self.telegram.lock().await = None;
        info!("Telegram bot stopped");
    }
}

#[async_trait::async_trait]
impl PluginCapability for TelegramBotPlugin {
    fn is_client(&self) -> bool {
        true
    }

    async fn set_daemon_client(
        &self,
        client: std::sync::Arc<tokio::sync::Mutex<DaemonClient>>,
    ) {
        // Extract the DaemonClient from the SDK wrapper
        let dc = client.lock().await.clone();
        *self.daemon.lock().await = Some(dc);
        info!("DaemonClient connected");
        self.start_bot().await;
    }

    fn subscribed_events(&self) -> Vec<String> {
        vec!["chat_message_sync".to_string()]
    }

    async fn on_event(&self, event_type: &str, payload_json: &str) {
        if event_type == "chat_message_sync" {
            info!("Sync event received ({}B payload)", payload_json.len());
            let tg = self.telegram.lock().await.clone();
            if let Some(telegram) = tg {
                if let Err(e) =
                    sync::handle_sync_event(&telegram, &self.state, payload_json).await
                {
                    tracing::warn!("Sync event error: {e}");
                }
            } else {
                tracing::warn!("Sync event arrived but Telegram not initialized");
            }
        }
    }

    async fn on_config_changed(&self, config_json: &str) {
        if let Ok(new_config) = serde_json::from_str::<BotConfig>(config_json) {
            let token_changed = {
                let old = self.config.read().await;
                old.bot_token != new_config.bot_token
            };
            *self.config.write().await = new_config;
            if token_changed {
                info!("Config changed, restarting bot");
                self.stop_bot().await;
                self.start_bot().await;
            }
        }
    }

    async fn on_shutdown(&self) {
        self.stop_bot().await;
        let state = self.state.read().await;
        state.save(&BotState::state_file_path());
    }

    async fn health_check(&self) -> (bool, String) {
        let has_telegram = self.telegram.lock().await.is_some();
        let state = self.state.read().await;
        let topics = state.topic_map.len();
        if has_telegram {
            (true, format!("ok - {} linked topics", topics))
        } else {
            (false, "bot not running".into())
        }
    }
}

#[tokio::main]
async fn main() {
    astra_plugin_sdk::run(TelegramBotPlugin::new())
        .await
        .unwrap();
}
