use std::sync::atomic::{AtomicI64, Ordering};

use anyhow::Result;
use frankenstein::client_reqwest::Bot;
use frankenstein::methods::{
    AnswerCallbackQueryParams, CreateForumTopicParams, EditMessageTextParams, GetUpdatesParams,
    SendMessageParams,
};
use frankenstein::ParseMode;
use frankenstein::types::{
    ChatId, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyMarkup,
};
use frankenstein::updates::Update;
use frankenstein::AsyncTelegramApi;

/// Thin wrapper over frankenstein's async Bot providing convenience methods.
pub struct TelegramApi {
    bot: Bot,
    token: String,
    http: reqwest::Client,
    chat_id: AtomicI64,
}

impl TelegramApi {
    pub fn new(token: &str, chat_id: i64) -> Self {
        Self {
            bot: Bot::new(token),
            token: token.to_string(),
            http: reqwest::Client::new(),
            chat_id: AtomicI64::new(chat_id),
        }
    }

    pub fn chat_id(&self) -> i64 {
        self.chat_id.load(Ordering::Relaxed)
    }

    pub fn set_chat_id(&self, id: i64) {
        self.chat_id.store(id, Ordering::Relaxed);
    }

    /// Send a plain text message to the chat (no topic).
    pub async fn send_message(&self, chat_id: i64, text: &str) -> Result<Message> {
        let params = SendMessageParams::builder()
            .chat_id(ChatId::Integer(chat_id))
            .text(text)
            .build();
        let resp = self
            .bot
            .send_message(&params)
            .await
            .map_err(|e| anyhow::anyhow!("send_message: {e}"))?;
        Ok(resp.result)
    }

    /// Send a plain text message to a forum topic.
    pub async fn send_to_topic(&self, thread_id: i64, text: &str) -> Result<Message> {
        let params = SendMessageParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .text(text)
            .message_thread_id(thread_id as i32)
            .build();
        let resp = self
            .bot
            .send_message(&params)
            .await
            .map_err(|e| anyhow::anyhow!("send_message: {e}"))?;
        Ok(resp.result)
    }

    /// Send an HTML-formatted message to a forum topic.
    pub async fn send_html_to_topic(&self, thread_id: i64, html: &str) -> Result<Message> {
        let params = SendMessageParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .text(html)
            .parse_mode(ParseMode::Html)
            .message_thread_id(thread_id as i32)
            .build();
        let resp = self
            .bot
            .send_message(&params)
            .await
            .map_err(|e| anyhow::anyhow!("send_html: {e}"))?;
        Ok(resp.result)
    }

    /// Edit an existing message's text (plain text).
    pub async fn edit_message(&self, message_id: i32, text: &str) -> Result<()> {
        let params = EditMessageTextParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .message_id(message_id)
            .text(text)
            .build();
        self.bot
            .edit_message_text(&params)
            .await
            .map_err(|e| anyhow::anyhow!("edit_message: {e}"))?;
        Ok(())
    }

    /// Send a streaming draft (native Telegram AI streaming).
    /// `draft_id` must be non-zero; updates with the same ID animate smoothly.
    /// Uses direct reqwest call for full response visibility.
    pub async fn send_draft(&self, chat_id: i64, thread_id: Option<i64>, draft_id: i32, text: &str) -> Result<()> {
        let url = format!(
            "https://api.telegram.org/bot{}/sendMessageDraft",
            self.token
        );
        let mut body = serde_json::json!({
            "chat_id": chat_id,
            "text": text,
            "draft_id": draft_id,
        });
        if let Some(tid) = thread_id {
            body["message_thread_id"] = serde_json::json!(tid);
        }
        let resp = self.http.post(&url).json(&body).send().await?;
        let status = resp.status();
        if !status.is_success() {
            let resp_body = resp.text().await.unwrap_or_default();
            tracing::warn!("sendMessageDraft failed: {status} — {resp_body}");
            return Err(anyhow::anyhow!("sendMessageDraft: {status}"));
        }
        Ok(())
    }

    /// Create a new forum topic. Returns the message_thread_id.
    pub async fn create_topic(&self, name: &str) -> Result<i64> {
        let params = CreateForumTopicParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .name(name)
            .build();
        let resp = self
            .bot
            .create_forum_topic(&params)
            .await
            .map_err(|e| anyhow::anyhow!("create_topic: {e}"))?;
        Ok(resp.result.message_thread_id as i64)
    }

    /// Send a message with inline keyboard buttons.
    /// `buttons` is a list of (label, callback_data) pairs, displayed as rows.
    pub async fn send_inline_keyboard(
        &self,
        chat_id: i64,
        text: &str,
        buttons: Vec<(String, String)>,
    ) -> Result<Message> {
        let keyboard = Self::build_keyboard(buttons);

        let params = SendMessageParams::builder()
            .chat_id(ChatId::Integer(chat_id))
            .text(text)
            .reply_markup(ReplyMarkup::InlineKeyboardMarkup(InlineKeyboardMarkup {
                inline_keyboard: keyboard,
            }))
            .build();
        let resp = self
            .bot
            .send_message(&params)
            .await
            .map_err(|e| anyhow::anyhow!("send_inline_keyboard: {e}"))?;
        Ok(resp.result)
    }

    /// Send a message with inline keyboard buttons to a forum topic.
    pub async fn send_inline_keyboard_to_topic(
        &self,
        thread_id: i64,
        text: &str,
        buttons: Vec<(String, String)>,
    ) -> Result<Message> {
        let keyboard = Self::build_keyboard(buttons);

        let params = SendMessageParams::builder()
            .chat_id(ChatId::Integer(self.chat_id()))
            .text(text)
            .message_thread_id(thread_id as i32)
            .reply_markup(ReplyMarkup::InlineKeyboardMarkup(InlineKeyboardMarkup {
                inline_keyboard: keyboard,
            }))
            .build();
        let resp = self
            .bot
            .send_message(&params)
            .await
            .map_err(|e| anyhow::anyhow!("send_inline_keyboard_to_topic: {e}"))?;
        Ok(resp.result)
    }

    fn build_keyboard(buttons: Vec<(String, String)>) -> Vec<Vec<InlineKeyboardButton>> {
        buttons
            .into_iter()
            .map(|(label, data)| {
                vec![InlineKeyboardButton::builder()
                    .text(label)
                    .callback_data(data)
                    .build()]
            })
            .collect()
    }

    /// Answer a callback query (acknowledges button press).
    pub async fn answer_callback(&self, callback_query_id: &str, text: &str) -> Result<()> {
        let params = AnswerCallbackQueryParams::builder()
            .callback_query_id(callback_query_id)
            .text(text)
            .build();
        self.bot
            .answer_callback_query(&params)
            .await
            .map_err(|e| anyhow::anyhow!("answer_callback: {e}"))?;
        Ok(())
    }

    /// Poll for updates (long polling).
    pub async fn poll_updates(&self, offset: i64, timeout: u32) -> Result<Vec<Update>> {
        let params = GetUpdatesParams::builder()
            .offset(offset)
            .timeout(timeout)
            .build();
        let resp = self
            .bot
            .get_updates(&params)
            .await
            .map_err(|e| anyhow::anyhow!("get_updates: {e}"))?;
        Ok(resp.result)
    }
}
