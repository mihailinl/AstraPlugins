mod bot;
mod screen;
mod state;
mod telegram;
mod types;

use std::sync::Arc;

use astra_plugin_sdk::prelude::*;
use tokio::sync::{Mutex, RwLock, watch};
use tracing::info;

use state::BotState;
use telegram::TelegramApi;
use types::{BotConfig, SharedConfig, SharedHost, SharedI18n};

struct TelegramBotPlugin {
    config: SharedConfig,
    state: types::SharedState,
    i18n: SharedI18n,
    telegram: Arc<Mutex<Option<Arc<TelegramApi>>>>,
    shutdown_tx: Arc<Mutex<Option<watch::Sender<bool>>>>,
    polling_handle: Arc<Mutex<Option<tokio::task::JoinHandle<()>>>>,
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
        }
    }
}

impl TelegramBotPlugin {
    async fn start_bot(&self, host: SharedHost) {
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
            bot::run_polling_loop(tg, state, host, config, i18n, rx).await;
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

    /// What this plugin is: a chat front-end. `spec/hooks.yaml` files
    /// `SendChatMessage` under the `client` capability, so the manifest
    /// declares it and so does this.
    ///
    /// It does **not** mean `ctx.daemon()` is used. That client speaks to
    /// `ChatService`, which a plugin's session token cannot reach — see
    /// [`types::SharedHost`].
    fn is_client(&self) -> bool {
        true
    }

    /// Config has already been applied by the time this runs, so the bot token
    /// is there and the bot starts once, in one place.
    async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
        let host = ctx.host().clone();
        *HOST.lock().await = Some(host.clone());
        self.start_bot(host).await;
        Ok(())
    }

    async fn on_language_changed(&self, _ctx: &PluginContext, language: &str) {
        self.i18n.set_language(language);
        info!("Language changed to: {}", language);
    }

    /// Typed: the SDK parsed `BotConfig` and told the user if it did not fit.
    async fn on_config(&self, _ctx: &PluginContext, new_config: BotConfig) {
        let token_changed = self.config.read().await.bot_token != new_config.bot_token;
        *self.config.write().await = new_config;
        if token_changed
            && let Some(host) = HOST.lock().await.clone()
        {
            info!("Bot token changed, restarting bot");
            self.stop_bot().await;
            self.start_bot(host).await;
        }
    }

    async fn on_shutdown(&self, _ctx: &PluginContext) {
        self.stop_bot().await;
        let state = self.state.read().await;
        state.save(&BotState::state_file_path());
    }

    /// **Unconfigured is not unhealthy.** Without a bot token there is no bot
    /// to start, and answering `false` there made Astra show a freshly
    /// installed plugin as failing until the user pasted a token — the health
    /// pane saying "broken" about the one state that is simply "not set up
    /// yet". It also failed `astra-plugin test`, which configures a plugin from
    /// its schema's defaults and then asks.
    async fn health_check(&self) -> (bool, String) {
        if self.telegram.lock().await.is_some() {
            return if self.state.read().await.conversation_id.is_some() {
                (true, "ok - bridged to a conversation".into())
            } else {
                (true, "ok - no conversation opened yet".into())
            };
        }
        if self.config.read().await.bot_token.is_empty() {
            (true, "ok - waiting for a bot token".into())
        } else {
            (false, "bot not running".into())
        }
    }
}

/// `on_config` can fire before `on_start` (it does, at startup) and again long
/// after, so the one thing it needs from the context is parked here rather than
/// threaded through every field. `astra_plugin_sdk::ctx()` is the general
/// answer; this plugin only needs the host handle.
static HOST: Mutex<Option<SharedHost>> = Mutex::const_new(None);

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(TelegramBotPlugin::default()).await
}
