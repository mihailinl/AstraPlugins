use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use tracing::warn;

use crate::telegram::TelegramApi;

const EDIT_INTERVAL: Duration = Duration::from_secs(2);
const MAX_MESSAGE_LENGTH: usize = 4000;

/// Manages a single Telegram message that gets progressively edited
/// as the AI streams its response.
pub struct StreamingMessage {
    telegram: Arc<TelegramApi>,
    thread_id: i64,
    message_id: Option<i32>,
    accumulated_text: String,
    last_edit_text: String,
    last_edit_time: Instant,
}

impl StreamingMessage {
    pub fn new(telegram: Arc<TelegramApi>, thread_id: i64) -> Self {
        Self {
            telegram,
            thread_id,
            message_id: None,
            accumulated_text: String::new(),
            last_edit_text: String::new(),
            last_edit_time: Instant::now(),
        }
    }

    /// Send the initial placeholder message.
    pub async fn start(&mut self) -> Result<()> {
        let msg = self
            .telegram
            .send_to_topic(self.thread_id, "\u{23f3}")
            .await?;
        self.message_id = Some(msg.message_id);
        self.last_edit_time = Instant::now();
        self.last_edit_text = "\u{23f3}".to_string();
        Ok(())
    }

    /// Append new text from a stream chunk. Flushes to Telegram if enough time has passed.
    pub async fn append(&mut self, text: &str) -> Result<()> {
        self.accumulated_text.push_str(text);
        self.maybe_flush().await
    }

    /// Force-flush the final message text to Telegram.
    pub async fn finalize(&mut self) -> Result<()> {
        if self.accumulated_text.is_empty() {
            self.accumulated_text = "(empty response)".to_string();
        }
        self.force_edit(&self.accumulated_text.clone()).await
    }

    /// Replace the message with an error.
    pub async fn error(&mut self, error_text: &str) -> Result<()> {
        let text = format!("\u{274c} Error: {error_text}");
        self.force_edit(&text).await
    }

    /// Check if a periodic edit is due and flush if so.
    async fn maybe_flush(&mut self) -> Result<()> {
        let elapsed = self.last_edit_time.elapsed();
        if elapsed >= EDIT_INTERVAL && self.accumulated_text != self.last_edit_text {
            let text = self.truncated_text();
            self.force_edit(&text).await?;
        }
        Ok(())
    }

    async fn force_edit(&mut self, text: &str) -> Result<()> {
        let Some(msg_id) = self.message_id else {
            return Ok(());
        };
        if text == self.last_edit_text {
            return Ok(());
        }
        match self.telegram.edit_message(msg_id, text).await {
            Ok(()) => {
                self.last_edit_text = text.to_string();
                self.last_edit_time = Instant::now();
            }
            Err(e) => {
                let err_str = e.to_string();
                // Handle rate limiting (429)
                if err_str.contains("429") || err_str.contains("Too Many Requests") {
                    warn!("Rate limited, backing off");
                    tokio::time::sleep(Duration::from_secs(3)).await;
                    // Retry once
                    if let Err(e2) = self.telegram.edit_message(msg_id, text).await {
                        warn!("Retry edit failed: {e2}");
                    } else {
                        self.last_edit_text = text.to_string();
                        self.last_edit_time = Instant::now();
                    }
                } else if err_str.contains("message is not modified") {
                    // Telegram says nothing changed — not an error
                    self.last_edit_text = text.to_string();
                } else {
                    warn!("Edit message failed: {e}");
                }
            }
        }
        Ok(())
    }

    fn truncated_text(&self) -> String {
        if self.accumulated_text.len() > MAX_MESSAGE_LENGTH {
            format!("{}...", &self.accumulated_text[..MAX_MESSAGE_LENGTH])
        } else {
            self.accumulated_text.clone()
        }
    }
}
