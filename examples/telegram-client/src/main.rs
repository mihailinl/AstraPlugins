mod bot;
mod commands;
mod state;
mod sync;
mod telegram;
mod types;

use std::sync::Arc;

use astra_plugin_sdk::prelude::*;
use tokio::sync::{watch, Mutex, RwLock};
use tracing::info;

use state::BotState;
use telegram::TelegramApi;
use types::{BotConfig, SharedConfig, SharedDaemon, SharedI18n};

struct TelegramBotPlugin {
    config: SharedConfig,
    state: types::SharedState,
    i18n: SharedI18n,
    telegram: Arc<Mutex<Option<Arc<TelegramApi>>>>,
    shutdown_tx: Arc<Mutex<Option<watch::Sender<bool>>>>,
    polling_handle: Arc<Mutex<Option<tokio::task::JoinHandle<()>>>>,
    /// Firehose-side accumulator: in-flight assistant text per conversation.
    firehose: sync::SharedFirehoseState,
}

impl Default for TelegramBotPlugin {
    fn default() -> Self {
        Self {
            config: Arc::new(RwLock::new(BotConfig::default())),
            state: Arc::new(RwLock::new(BotState::load(&BotState::state_file_path()))),
            // `discover()`: $ASTRA_PLUGIN_DIR/locales when the daemon sets it,
            // else ./locales. The bare path worked only because the daemon
            // happens to spawn a plugin with its install directory as the cwd.
            i18n: Arc::new(I18n::discover()),
            telegram: Arc::new(Mutex::new(None)),
            shutdown_tx: Arc::new(Mutex::new(None)),
            polling_handle: Arc::new(Mutex::new(None)),
            firehose: sync::new_shared(),
        }
    }
}

impl TelegramBotPlugin {
    /// `daemon` comes straight off the context now. There is no longer a
    /// "daemon client not ready" state to check for: `on_start` cannot run
    /// before registration, and `PluginContext::daemon` is `Some` for the whole
    /// life of a plugin that has the `client` capability.
    async fn start_bot(&self, daemon: SharedDaemon) {
        let cfg = self.config.read().await.clone();
        if cfg.bot_token.is_empty() {
            info!("Bot token not configured, not starting");
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
        let config = self.config.clone();
        let i18n = self.i18n.clone();

        let handle = tokio::spawn(async move {
            bot::run_polling_loop(tg, state, daemon, config, i18n, rx).await;
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

#[async_trait]
impl PluginCapability for TelegramBotPlugin {
    type Config = BotConfig;

    fn is_client(&self) -> bool {
        true
    }

    /// Config has already been applied by the time this runs, so the bot token
    /// is there and the bot starts once, in one place, instead of racing
    /// `set_daemon_client` against `on_config_changed`.
    async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
        let daemon = ctx
            .daemon()
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("telegram-client needs the `client` capability"))?;
        *DAEMON.lock().await = Some(daemon.clone());
        self.start_bot(daemon).await;
        Ok(())
    }

    async fn on_conversation_event(
        &self,
        _ctx: &PluginContext,
        conv_id: &str,
        event: &astra_plugin_sdk::proto::ConversationEventMsg,
    ) {
        let tg = self.telegram.lock().await.clone();
        if let Some(telegram) = tg {
            if let Err(e) = sync::handle_firehose_event(
                &telegram,
                &self.state,
                &self.firehose,
                conv_id,
                event,
            )
            .await
            {
                tracing::warn!("Firehose event error: {e}");
            }
        }
    }

    async fn on_language_changed(&self, _ctx: &PluginContext, language: &str) {
        self.i18n.set_language(language);
        info!("Language changed to: {}", language);
    }

    /// Typed: the SDK parsed `BotConfig` and told the user if it did not fit.
    async fn on_config(&self, _ctx: &PluginContext, new_config: BotConfig) {
        let token_changed = self.config.read().await.bot_token != new_config.bot_token;
        *self.config.write().await = new_config;
        if token_changed && let Some(daemon) = DAEMON.lock().await.clone() {
            info!("Bot token changed, restarting bot");
            self.stop_bot().await;
            self.start_bot(daemon).await;
        }
    }

    async fn on_shutdown(&self, _ctx: &PluginContext) {
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

/// `on_config` can fire before `on_start` (it does, at startup) and again long
/// after, so the one thing it needs from the context is parked here rather than
/// threaded through every field. `astra_plugin_sdk::ctx()` is the general
/// answer; this plugin only needs the daemon handle.
static DAEMON: Mutex<Option<SharedDaemon>> = Mutex::const_new(None);

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(TelegramBotPlugin::default()).await
}
