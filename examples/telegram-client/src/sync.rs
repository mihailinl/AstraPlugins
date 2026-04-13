use std::sync::Arc;

use anyhow::Result;
use astra_plugin_sdk::prelude::ChatSyncEvent;
use tracing::warn;

use crate::telegram::TelegramApi;
use crate::types::SharedState;

const MAX_MESSAGE_LENGTH: usize = 4000;

/// Handle a chat_message_sync event — forward messages from other clients to Telegram.
/// Source filtering is done server-side via `source_id()` — we never receive our own messages.
pub async fn handle_sync_event(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    event: &ChatSyncEvent,
) -> Result<()> {
    tracing::debug!(
        "Sync: role={} source={} conv={} streaming={} complete={} content_len={}",
        event.role, event.source_id, &event.conversation_id[..8.min(event.conversation_id.len())],
        event.is_streaming, event.is_complete, event.content.len()
    );

    // Filter: Skip if conversation not linked to a topic
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

    // Filter: Skip if we're actively streaming from Telegram for this conversation
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
        handle_assistant_sync(telegram, state, event, thread_id).await?;
    }

    Ok(())
}

/// Handle streaming/complete assistant messages from sync events.
/// Uses sendMessageDraft for native streaming, sendMessage for finalization.
async fn handle_assistant_sync(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    event: &ChatSyncEvent,
    thread_id: i64,
) -> Result<()> {
    if event.is_streaming && !event.is_complete {
        // Streaming in progress — send draft update
        if !event.content.is_empty() {
            let text = truncate(&event.content, MAX_MESSAGE_LENGTH);
            let mut state_w = state.write().await;
            state_w.sync_streaming.insert(event.conversation_id.clone());
            drop(state_w);
            let chat_id = telegram.chat_id();
            if let Err(e) = telegram.send_draft(chat_id, Some(thread_id), 1, &text).await {
                warn!("Sync draft failed: {e}");
            }
        }
    } else if event.is_complete {
        // Final message — commit as real message
        let mut state_w = state.write().await;
        let was_streaming = state_w.sync_streaming.remove(&event.conversation_id);
        drop(state_w);

        let text = truncate(&event.content, MAX_MESSAGE_LENGTH);
        if !text.is_empty() {
            if let Err(e) = telegram.send_to_topic(thread_id, &text).await {
                warn!("Sync finalize failed: {e}");
            }
        } else if was_streaming {
            // Was streaming but final content is empty — shouldn't happen, but handle
            if let Err(e) = telegram.send_to_topic(thread_id, "(empty response)").await {
                warn!("Sync finalize (empty) failed: {e}");
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
    if s.len() <= max {
        return s.to_string();
    }
    let end = s.floor_char_boundary(max.saturating_sub(3));
    format!("{}...", &s[..end])
}
