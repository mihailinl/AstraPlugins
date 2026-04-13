use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use tracing::warn;

use crate::telegram::TelegramApi;

const MAX_MESSAGE_LENGTH: usize = 4000;
/// Minimum interval between draft updates to respect Telegram rate limits.
const DRAFT_INTERVAL: Duration = Duration::from_millis(500);

/// Manages streaming a message to Telegram using sendMessageDraft.
/// Updates with the same draft_id animate smoothly. On finalize, the draft is
/// committed as a real message via sendMessage (which auto-clears the draft).
pub struct StreamingMessage {
    telegram: Arc<TelegramApi>,
    thread_id: i64,
    accumulated_text: String,
    last_sent_text: String,
    tools_text: String,
    last_send_time: Option<Instant>,
}

impl StreamingMessage {
    pub fn new(telegram: Arc<TelegramApi>, thread_id: i64) -> Self {
        Self {
            telegram,
            thread_id,
            accumulated_text: String::new(),
            last_sent_text: String::new(),
            tools_text: String::new(),
            last_send_time: None,
        }
    }

    /// Append new text from a stream chunk.
    pub async fn append(&mut self, text: &str) -> Result<()> {
        self.accumulated_text.push_str(text);
        self.flush().await
    }

    /// Append tool status text.
    pub async fn append_tool(&mut self, text: &str) -> Result<()> {
        self.tools_text.push_str(text);
        self.flush().await
    }

    /// Commit as a real message via sendMessage (auto-clears draft).
    pub async fn finalize(&mut self) -> Result<()> {
        let text = self.display_text();
        if text.is_empty() {
            let _ = self
                .telegram
                .send_to_topic(self.thread_id, "(empty response)")
                .await;
            return Ok(());
        }
        let text = truncate(&text, MAX_MESSAGE_LENGTH);
        match self.telegram.send_to_topic(self.thread_id, &text).await {
            Ok(_) => {}
            Err(e) => warn!("Finalize send failed: {e}"),
        }
        Ok(())
    }

    /// Send an error message.
    pub async fn error(&mut self, error_text: &str) -> Result<()> {
        let text = format!("\u{274c} Error: {error_text}");
        let _ = self.telegram.send_to_topic(self.thread_id, &text).await;
        Ok(())
    }

    /// Send current accumulated text as a draft update (throttled).
    async fn flush(&mut self) -> Result<()> {
        // Throttle: skip if we sent too recently
        if let Some(last) = self.last_send_time {
            if last.elapsed() < DRAFT_INTERVAL {
                return Ok(());
            }
        }

        let text = self.display_text();
        if text.is_empty() || text == self.last_sent_text {
            return Ok(());
        }
        let text = truncate(&text, MAX_MESSAGE_LENGTH);
        let chat_id = self.telegram.chat_id();
        let thread_id = if self.thread_id != 0 {
            Some(self.thread_id)
        } else {
            None
        };
        match self
            .telegram
            .send_draft(chat_id, thread_id, 1, &text)
            .await
        {
            Ok(()) => {
                self.last_sent_text = text;
                self.last_send_time = Some(Instant::now());
            }
            Err(e) => {
                self.last_send_time = Some(Instant::now());
                warn!("Draft update failed: {e}");
            }
        }
        Ok(())
    }

    fn display_text(&self) -> String {
        if self.tools_text.is_empty() {
            self.accumulated_text.clone()
        } else if self.accumulated_text.is_empty() {
            self.tools_text.clone()
        } else {
            format!("{}{}", self.tools_text, self.accumulated_text)
        }
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.len() <= max {
        return s.to_string();
    }
    let end = s.floor_char_boundary(max.saturating_sub(3));
    format!("{}...", &s[..end])
}
