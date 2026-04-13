use std::sync::Arc;

use anyhow::Result;
use frankenstein::updates::UpdateContent;
use tracing::{info, warn};

use crate::commands;
use crate::streaming::StreamingMessage;
use crate::telegram::TelegramApi;
use crate::types::{SharedConfig, SharedDaemon, SharedState, SOURCE_ID};

/// Run the Telegram long-polling loop until shutdown.
pub async fn run_polling_loop(
    telegram: Arc<TelegramApi>,
    state: SharedState,
    daemon: SharedDaemon,
    config: SharedConfig,
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
                        &msg,
                    )
                    .await;
                }
                UpdateContent::CallbackQuery(cq) => {
                    handle_callback(&telegram, &state, &daemon, &cq).await;
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
                if let Err(e) = commands::handle_new(telegram, state, daemon, args).await {
                    warn!("/new error: {e}");
                }
            }
            "/list" => {
                if let Err(e) = commands::handle_list(telegram, state, daemon, thread_id).await {
                    warn!("/list error: {e}");
                }
            }
            "/start" => {
                if let Err(e) = telegram
                    .send_message(
                        chat_id,
                        "Astra Telegram Bot is active.\n\n\
                         /new [title] — Create a new conversation topic\n\
                         /list — Link an existing Astra conversation\n\n\
                         Send any message in a topic to chat with Astra.",
                    )
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

    // Get streaming response from daemon
    let stream = {
        let mut d = daemon.lock().await;
        let Some(d) = d.as_mut() else {
            warn!("Daemon not connected, can't forward message");
            let mut state_w = state.write().await;
            state_w.active_streams.remove(&active_key);
            return;
        };
        match d
            .send_message_full(text, false, SOURCE_ID, &conv_id)
            .await
        {
            Ok(s) => s,
            Err(e) => {
                warn!("SendMessage error: {e}");
                let _ = telegram
                    .send_to_topic(thread_id, &format!("\u{274c} Error: {e}"))
                    .await;
                let mut state_w = state.write().await;
                state_w.active_streams.remove(&active_key);
                return;
            }
        }
    };

    // Spawn streaming task
    let telegram = telegram.clone();
    let state = state.clone();
    let daemon_arc = daemon.clone();
    let text_owned = text.to_string();
    let _ = daemon_arc; // not needed in spawned task

    tokio::spawn(async move {
        let result = stream_response(
            &telegram,
            &state,
            stream,
            thread_id,
            conv_id.to_string(),
            active_key.clone(),
        )
        .await;

        if let Err(e) = result {
            warn!("Stream response error: {e}");
            let _ = telegram
                .send_to_topic(thread_id, &format!("\u{274c} Stream error: {e}"))
                .await;
        }

        // Clean up active_streams
        let mut state_w = state.write().await;
        state_w.active_streams.remove(&active_key);
        let _ = text_owned;
    });
}

/// Consume the ChatStreamChunk stream and progressively edit the Telegram message.
async fn stream_response(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    mut stream: tonic::Streaming<astra_plugin_sdk::proto::ChatStreamChunk>,
    thread_id: i64,
    initial_conv_id: String,
    active_key: String,
) -> Result<()> {
    use tokio_stream::StreamExt;

    let mut streaming_msg = StreamingMessage::new(telegram.clone(), thread_id);

    let mut mapped = !initial_conv_id.is_empty();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk?;

        // If this is a new conversation, grab the conversation_id from the first chunk
        if !mapped && !chunk.conversation_id.is_empty() {
            let cid = chunk.conversation_id.clone();
            let mut state_w = state.write().await;
            state_w.insert_mapping(cid.clone(), thread_id);
            // Update active_streams: remove pending key, add real conversation_id
            state_w.active_streams.remove(&active_key);
            state_w.active_streams.insert(cid);
            mapped = true;
        }

        // Process chunk content
        if let Some(content) = chunk.chunk {
            use astra_plugin_sdk::proto::chat_stream_chunk::Chunk;
            match content {
                Chunk::Text(text) => {
                    streaming_msg.append(&text).await?;
                }
                Chunk::Thinking(_) => {
                    // Skip thinking content in Telegram
                }
                Chunk::Tool(tool_exec) => {
                    let tool_text = if tool_exec.completed {
                        format!("[Tool: {} \u{2714}]\n", tool_exec.name)
                    } else {
                        format!("[Using: {}...]\n", tool_exec.name)
                    };
                    streaming_msg.append_tool(&tool_text).await?;
                }
                Chunk::Error(err) => {
                    streaming_msg.error(&err).await?;
                    return Ok(());
                }
                Chunk::Done(_) => {
                    streaming_msg.finalize().await?;
                    return Ok(());
                }
                Chunk::Voice(_) => {
                    // Skip voice-specific content
                }
            }
        }
    }

    // Stream ended without Done marker
    streaming_msg.finalize().await?;
    Ok(())
}

async fn handle_callback(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    daemon: &SharedDaemon,
    cq: &frankenstein::types::CallbackQuery,
) {
    let Some(data) = cq.data.as_deref() else {
        return;
    };

    if let Some(conv_id) = data.strip_prefix("link:") {
        if let Err(e) =
            commands::handle_list_callback(telegram, state, daemon, &cq.id, conv_id).await
        {
            warn!("Callback error: {e}");
            let _ = telegram.answer_callback(&cq.id, "Error linking conversation").await;
        }
    }
}
