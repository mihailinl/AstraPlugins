//! Chat firehose handler — forwards events from Astra → Telegram topics.
//!
//! Consumes per-event `ConversationEventMsg` from `on_conversation_event`.
//! Accumulates streaming text per assistant message and emits either draft
//! updates (for live typing) or final messages (on AssistantComplete).

use std::collections::HashMap;
use std::sync::Arc;

use anyhow::Result;
use astra_plugin_sdk::proto::{
    conversation_event_msg::Event as ProtoEvent, ConversationEventMsg,
};
use tokio::sync::Mutex;
use tracing::warn;

use crate::telegram::TelegramApi;
use crate::types::{SharedState, SOURCE_ID};

const MAX_MESSAGE_LENGTH: usize = 4000;

/// Buffer for an in-flight assistant message within one conversation.
#[derive(Default)]
struct AssistantBuf {
    message_id: String,
    text: String,
    thread_id: i64,
}

/// Per-conversation accumulator shared across firehose events. Wraps one
/// active assistant message at a time; `AssistantComplete` clears it.
#[derive(Default)]
pub struct FirehoseState {
    /// conv_id → in-flight assistant buffer
    inflight: HashMap<String, AssistantBuf>,
}

pub type SharedFirehoseState = Arc<Mutex<FirehoseState>>;

pub fn new_shared() -> SharedFirehoseState {
    Arc::new(Mutex::new(FirehoseState::default()))
}

/// Dispatch a firehose event from `on_conversation_event` into Telegram.
pub async fn handle_firehose_event(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    firehose: &SharedFirehoseState,
    conv_id: &str,
    msg: &ConversationEventMsg,
) -> Result<()> {
    // Skip events this plugin itself originated — we already posted them to Telegram.
    if msg.source_id == SOURCE_ID {
        return Ok(());
    }

    // Skip if we're actively streaming FROM Telegram for this conversation
    // (the user is typing; daemon will echo back what we just sent).
    {
        let state_r = state.read().await;
        if state_r.active_streams.contains(conv_id) {
            tracing::debug!("firehose: skipped (active Telegram stream)");
            return Ok(());
        }
    }

    // Find the topic for this conversation; skip if not linked.
    let thread_id = {
        let state_r = state.read().await;
        match state_r.topic_map.get(conv_id) {
            Some(&tid) => tid,
            None => {
                tracing::debug!("firehose: skipped (conversation not linked to topic)");
                return Ok(());
            }
        }
    };

    let Some(ref event) = msg.event else {
        return Ok(());
    };

    match event {
        ProtoEvent::UserMessage(e) => {
            // User message from another client — forward as a blockquote.
            let html = format!(
                "<blockquote>{}</blockquote>",
                html_escape(&truncate(&e.content, MAX_MESSAGE_LENGTH))
            );
            telegram.send_html_to_topic(thread_id, &html).await?;
        }
        ProtoEvent::AssistantStart(e) => {
            let mut fs = firehose.lock().await;
            fs.inflight.insert(
                conv_id.to_string(),
                AssistantBuf {
                    message_id: e.message_id.clone(),
                    text: String::new(),
                    thread_id,
                },
            );
        }
        ProtoEvent::AssistantTextDelta(e) => {
            let mut fs = firehose.lock().await;
            let buf = fs.inflight.entry(conv_id.to_string()).or_insert_with(|| AssistantBuf {
                message_id: e.message_id.clone(),
                text: String::new(),
                thread_id,
            });
            buf.text.push_str(&e.delta);
            let snapshot = truncate(&buf.text, MAX_MESSAGE_LENGTH);
            let tid = buf.thread_id;
            drop(fs);
            let chat_id = telegram.chat_id();
            if let Err(e) = telegram.send_draft(chat_id, Some(tid), 1, &snapshot).await {
                warn!("Telegram draft update failed: {e}");
            }
        }
        ProtoEvent::AssistantComplete(_) => {
            let mut fs = firehose.lock().await;
            if let Some(buf) = fs.inflight.remove(conv_id) {
                drop(fs);
                let text = truncate(&buf.text, MAX_MESSAGE_LENGTH);
                if !text.is_empty() {
                    if let Err(e) = telegram.send_to_topic(buf.thread_id, &text).await {
                        warn!("Telegram finalize failed: {e}");
                    }
                }
            }
        }
        ProtoEvent::Error(e) => {
            let mut fs = firehose.lock().await;
            let buf = fs.inflight.remove(conv_id);
            drop(fs);
            let tid = buf.map(|b| b.thread_id).unwrap_or(thread_id);
            let body = format!("⚠️ {}", truncate(&e.content, MAX_MESSAGE_LENGTH - 4));
            if let Err(e) = telegram.send_to_topic(tid, &body).await {
                warn!("Telegram error-send failed: {e}");
            }
        }
        ProtoEvent::ToolCallStart(e) => {
            let line = format!("🔧 {}", e.name);
            if let Err(e) = telegram.send_to_topic(thread_id, &line).await {
                warn!("Telegram tool-start send failed: {e}");
            }
        }
        // Tool completions, thinking, voice deltas, confirmations — skipped for
        // now; the chat shows the final assistant text + tool-name markers.
        _ => {}
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
