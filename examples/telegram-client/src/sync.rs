use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use serde::Deserialize;
use tracing::warn;

use crate::state::SyncStreamState;
use crate::telegram::TelegramApi;
use crate::types::{SharedState, SOURCE_ID};

const SYNC_EDIT_INTERVAL: Duration = Duration::from_secs(2);
const MAX_MESSAGE_LENGTH: usize = 4000;

/// Deserialized ChatMessageSyncEvent from the daemon event bus.
#[derive(Debug, Deserialize)]
pub struct ChatMessageSyncEvent {
    pub id: String,
    pub conversation_id: String,
    pub role: String,
    pub content: String,
    pub source_id: String,
    #[serde(default)]
    pub is_streaming: bool,
    #[serde(default)]
    pub is_complete: bool,
}

/// Handle a chat_message_sync event — forward messages from Astra UI to Telegram.
pub async fn handle_sync_event(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    payload_json: &str,
) -> Result<()> {
    let event: ChatMessageSyncEvent = serde_json::from_str(payload_json)?;

    tracing::debug!(
        "Sync: role={} source={} conv={} streaming={} complete={} content_len={}",
        event.role, event.source_id, &event.conversation_id[..8.min(event.conversation_id.len())],
        event.is_streaming, event.is_complete, event.content.len()
    );

    // Filter 1: Skip our own messages
    if event.source_id == SOURCE_ID {
        tracing::debug!("Sync: skipped (own source_id)");
        return Ok(());
    }

    // Filter 2: Skip if conversation not linked to a topic
    let thread_id = {
        let state_r = state.read().await;
        match state_r.topic_map.get(&event.conversation_id) {
            Some(&tid) => tid,
            None => {
                tracing::debug!("Sync: skipped (conversation not linked)");
                return Ok(());
            }
        }
    };

    // Filter 3: Skip if we're actively streaming from Telegram for this conversation
    {
        let state_r = state.read().await;
        if state_r.active_streams.contains(&event.conversation_id) {
            tracing::debug!("Sync: skipped (active stream)");
            return Ok(());
        }
    }

    if event.role == "user" && event.is_complete {
        // User message from another client — send as blockquote
        tracing::info!("Sync: forwarding user message to topic {thread_id}");
        let html = format!(
            "<blockquote>{}</blockquote>",
            html_escape(&truncate(&event.content, MAX_MESSAGE_LENGTH))
        );
        telegram.send_html_to_topic(thread_id, &html).await?;
    } else if event.role == "assistant" {
        handle_assistant_sync(telegram, state, &event, thread_id).await?;
    }

    Ok(())
}

/// Handle streaming/complete assistant messages from sync events.
async fn handle_assistant_sync(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    event: &ChatMessageSyncEvent,
    thread_id: i64,
) -> Result<()> {
    if event.is_streaming && !event.is_complete {
        // Streaming in progress
        let mut state_w = state.write().await;
        if let Some(ss) = state_w.sync_streaming.get_mut(&event.conversation_id) {
            // Existing stream — throttled edit
            if ss.last_edit.elapsed() >= SYNC_EDIT_INTERVAL && event.content != ss.last_content {
                let text = truncate(&event.content, MAX_MESSAGE_LENGTH);
                match telegram.edit_message(ss.telegram_message_id, &text).await {
                    Ok(()) => {
                        ss.last_content = event.content.clone();
                        ss.last_edit = Instant::now();
                    }
                    Err(e) => {
                        let err = e.to_string();
                        if !err.contains("message is not modified") {
                            warn!("Sync edit failed: {e}");
                        }
                    }
                }
            }
        } else {
            // New streaming message — send initial
            drop(state_w); // Release write lock before API call
            match telegram
                .send_to_topic(thread_id, &truncate(&event.content, MAX_MESSAGE_LENGTH))
                .await
            {
                Ok(msg) => {
                    let mut state_w = state.write().await;
                    state_w.sync_streaming.insert(
                        event.conversation_id.clone(),
                        SyncStreamState {
                            telegram_message_id: msg.message_id,
                            last_content: event.content.clone(),
                            last_edit: Instant::now(),
                        },
                    );
                }
                Err(e) => warn!("Sync send failed: {e}"),
            }
        }
    } else if event.is_complete {
        // Final message — do a final edit or send new
        let mut state_w = state.write().await;
        if let Some(ss) = state_w.sync_streaming.remove(&event.conversation_id) {
            drop(state_w);
            let text = truncate(&event.content, MAX_MESSAGE_LENGTH);
            if let Err(e) = telegram.edit_message(ss.telegram_message_id, &text).await {
                let err = e.to_string();
                if !err.contains("message is not modified") {
                    warn!("Sync final edit failed: {e}");
                }
            }
        } else {
            drop(state_w);
            // No streaming state — send as new message
            let text = truncate(&event.content, MAX_MESSAGE_LENGTH);
            if !text.is_empty() {
                telegram.send_to_topic(thread_id, &text).await?;
            }
        }
    }

    Ok(())
}

fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn truncate(s: &str, max: usize) -> String {
    if s.len() > max {
        format!("{}...", &s[..max.saturating_sub(3)])
    } else {
        s.to_string()
    }
}
