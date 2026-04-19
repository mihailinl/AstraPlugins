use std::sync::Arc;

use anyhow::Result;
use frankenstein::updates::UpdateContent;
use tracing::{info, warn};

use crate::commands;
use crate::telegram::TelegramApi;
use crate::types::{SharedConfig, SharedDaemon, SharedI18n, SharedState, SOURCE_ID};

/// Run the Telegram long-polling loop until shutdown.
pub async fn run_polling_loop(
    telegram: Arc<TelegramApi>,
    state: SharedState,
    daemon: SharedDaemon,
    config: SharedConfig,
    i18n: SharedI18n,
    mut shutdown_rx: tokio::sync::watch::Receiver<bool>,
) {
    info!("Starting Telegram polling loop");
    let mut offset: i64 = 0;

    loop {
        let updates = tokio::select! {
            result = telegram.poll_updates(offset, 30) => {
                match result {
                    Ok(updates) => updates,
                    Err(e) => {
                        warn!("Poll error: {e}");
                        tokio::time::sleep(std::time::Duration::from_secs(5)).await;
                        continue;
                    }
                }
            }
            _ = shutdown_rx.changed() => {
                info!("Polling loop shutdown");
                return;
            }
        };

        for update in updates {
            offset = update.update_id as i64 + 1;

            match update.content {
                UpdateContent::Message(msg) => {
                    handle_message(
                        &telegram,
                        &state,
                        &daemon,
                        &config,
                        &i18n,
                        &msg,
                    )
                    .await;
                }
                UpdateContent::CallbackQuery(cq) => {
                    handle_callback(&telegram, &state, &daemon, &i18n, &cq).await;
                }
                _ => {}
            }
        }
    }
}

async fn handle_message(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    daemon: &SharedDaemon,
    config: &SharedConfig,
    i18n: &SharedI18n,
    msg: &frankenstein::types::Message,
) {
    let chat_id = msg.chat.id;
    let thread_id = msg.message_thread_id.map(|t| t as i64);
    let text = msg.text.as_deref().unwrap_or("");
    let username = msg
        .from
        .as_ref()
        .and_then(|u| u.username.as_deref())
        .unwrap_or("");

    info!("Message from @{username} in chat={chat_id} thread={thread_id:?}: {text}");

    // Auto-detect chat_id from first private chat message
    let stored_chat_id = telegram.chat_id();
    if stored_chat_id != 0 && chat_id != stored_chat_id {
        return; // Ignore messages from other chats
    }
    if stored_chat_id == 0 {
        info!("Auto-detected chat_id={chat_id}");
        telegram.set_chat_id(chat_id);
        let mut state_w = state.write().await;
        state_w.chat_id = chat_id;
        state_w.save(&crate::state::BotState::state_file_path());
        drop(state_w);
    }

    // Username authorization
    {
        let cfg = config.read().await;
        let allowed = cfg.allowed_set();
        if !allowed.is_empty() && !allowed.contains(&username.to_lowercase()) {
            return;
        }
    }

    // Handle commands
    if text.starts_with('/') {
        let (cmd, args) = match text.split_once(' ') {
            Some((c, a)) => (c, a.trim()),
            None => (text, ""),
        };
        // Strip @botname suffix from command
        let cmd = cmd.split('@').next().unwrap_or(cmd);

        match cmd {
            "/new" => {
                if let Err(e) = commands::handle_new(telegram, state, daemon, i18n, args).await {
                    warn!("/new error: {e}");
                }
            }
            "/list" => {
                if let Err(e) = commands::handle_list(telegram, state, daemon, i18n, thread_id).await {
                    warn!("/list error: {e}");
                }
            }
            "/start" => {
                if let Err(e) = telegram
                    .send_message(chat_id, &i18n.t("bot.start"))
                    .await
                {
                    warn!("/start error: {e}");
                }
            }
            _ => {} // Ignore unknown commands
        }
        return;
    }

    // Regular message — forward to Astra
    let Some(thread_id) = thread_id else {
        // Not a topic message — ignore
        return;
    };

    forward_to_astra(telegram, state, daemon, text, thread_id).await;
}

/// Forward a Telegram message to the Astra daemon and stream the response back.
async fn forward_to_astra(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    daemon: &SharedDaemon,
    text: &str,
    thread_id: i64,
) {
    // Look up conversation_id from mapping
    let conv_id: String = {
        let state_r = state.read().await;
        state_r
            .reverse_map
            .get(&thread_id)
            .cloned()
            .unwrap_or_default()
    };

    // Mark as actively streaming (for sync dedup)
    let active_key = if conv_id.is_empty() {
        format!("__pending_{thread_id}")
    } else {
        conv_id.to_string()
    };
    {
        let mut state_w = state.write().await;
        state_w.active_streams.insert(active_key.clone());
    }

    // Submit the user message to the daemon. Daemon drives the AI turn and
    // emits every event back through the chat firehose — see sync.rs for the
    // handler that renders them into this Telegram topic.
    let resp = {
        let mut d = daemon.lock().await;
        let Some(d) = d.as_mut() else {
            warn!("Daemon not connected, can't forward message");
            let mut state_w = state.write().await;
            state_w.active_streams.remove(&active_key);
            return;
        };
        match d.submit_user_message(text, &conv_id, false, SOURCE_ID).await {
            Ok(r) => r,
            Err(e) => {
                warn!("submit_user_message error: {e}");
                let _ = telegram
                    .send_to_topic(thread_id, &format!("\u{274c} Error: {e}"))
                    .await;
                let mut state_w = state.write().await;
                state_w.active_streams.remove(&active_key);
                return;
            }
        }
    };

    // If the daemon auto-created a new conversation, persist the topic mapping
    // and release the active_streams marker so the firehose can render.
    let mut state_w = state.write().await;
    if conv_id.is_empty() && !resp.conversation_id.is_empty() {
        state_w.insert_mapping(resp.conversation_id.clone(), thread_id);
        state_w.active_streams.remove(&active_key);
    } else {
        state_w.active_streams.remove(&active_key);
    }
}


async fn handle_callback(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    daemon: &SharedDaemon,
    i18n: &SharedI18n,
    cq: &frankenstein::types::CallbackQuery,
) {
    let Some(data) = cq.data.as_deref() else {
        return;
    };

    if let Some(conv_id) = data.strip_prefix("link:") {
        if let Err(e) =
            commands::handle_list_callback(telegram, state, daemon, i18n, &cq.id, conv_id).await
        {
            warn!("Callback error: {e}");
            let _ = telegram.answer_callback(&cq.id, &i18n.t("bot.callback_error")).await;
        }
    }
}
