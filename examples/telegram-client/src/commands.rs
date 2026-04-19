use std::sync::Arc;

use anyhow::Result;
use tracing::info;

use crate::telegram::TelegramApi;
use crate::types::{SharedDaemon, SharedI18n, SharedState};

/// Handle the /new command — create a new forum topic and a matching Astra conversation.
pub async fn handle_new(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    daemon: &SharedDaemon,
    i18n: &SharedI18n,
    args: &str,
) -> Result<()> {
    let title = if args.is_empty() {
        let secs = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        format!("Chat #{secs}")
    } else {
        args.to_string()
    };

    // Truncate title to 128 bytes (Telegram limit)
    let title = if title.len() > 128 {
        title[..title.floor_char_boundary(128)].to_string()
    } else {
        title
    };

    let thread_id = telegram.create_topic(&title).await?;
    info!("Created topic '{title}' with thread_id={thread_id}");

    // Create a matching conversation in the daemon with the same title
    let conv_id = {
        let mut d = daemon.lock().await;
        if let Some(d) = d.as_mut() {
            match d.create_conversation(&title).await {
                Ok(conv) => {
                    info!("Created conversation '{}' (id={})", title, conv.id);
                    Some(conv.id)
                }
                Err(e) => {
                    tracing::warn!("Failed to create conversation: {e}");
                    None
                }
            }
        } else {
            None
        }
    };

    // Map the topic to the conversation
    if let Some(conv_id) = conv_id {
        let mut state_w = state.write().await;
        state_w.insert_mapping(conv_id, thread_id);
    }

    telegram
        .send_to_topic(thread_id, &i18n.t("bot.topic_created"))
        .await?;

    Ok(())
}

/// Handle the /list command — show unlinked daemon conversations.
pub async fn handle_list(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    daemon: &SharedDaemon,
    i18n: &SharedI18n,
    thread_id: Option<i64>,
) -> Result<()> {
    let conversations = {
        let mut d = daemon.lock().await;
        let d = d.as_mut().ok_or_else(|| anyhow::anyhow!("Daemon not connected"))?;
        d.list_conversations().await?
    };

    let state_r = state.read().await;
    let mapped_ids: std::collections::HashSet<&str> = state_r
        .topic_map
        .keys()
        .map(|s| s.as_str())
        .collect();

    let unlinked: Vec<_> = conversations
        .conversations
        .iter()
        .filter(|c| !mapped_ids.contains(c.id.as_str()))
        .collect();

    drop(state_r);

    if unlinked.is_empty() {
        let text = i18n.t("bot.all_linked");
        if let Some(tid) = thread_id {
            telegram.send_to_topic(tid, &text).await?;
        } else {
            telegram.send_message(telegram.chat_id(), &text).await?;
        }
        return Ok(());
    }

    // Build inline keyboard buttons — one per unlinked conversation
    let buttons: Vec<(String, String)> = unlinked
        .iter()
        .take(20) // Telegram button limit
        .map(|c| {
            let label = if c.title.is_empty() {
                format!("Untitled ({})", &c.id[..8.min(c.id.len())])
            } else if c.title.len() > 60 {
                format!("{}...", &c.title[..c.title.floor_char_boundary(57)])
            } else {
                c.title.clone()
            };
            // callback_data format: "link:{conversation_id}"
            (label, format!("link:{}", c.id))
        })
        .collect();

    let select_text = i18n.t("bot.select_conversation");
    if let Some(tid) = thread_id {
        telegram
            .send_inline_keyboard_to_topic(tid, &select_text, buttons)
            .await?;
    } else {
        telegram
            .send_inline_keyboard(telegram.chat_id(), &select_text, buttons)
            .await?;
    }

    Ok(())
}

/// Handle a callback query from the /list inline keyboard.
pub async fn handle_list_callback(
    telegram: &Arc<TelegramApi>,
    state: &SharedState,
    daemon: &SharedDaemon,
    i18n: &SharedI18n,
    callback_query_id: &str,
    conversation_id: &str,
) -> Result<()> {
    // Get conversation title
    let conversations = {
        let mut d = daemon.lock().await;
        let d = d.as_mut().ok_or_else(|| anyhow::anyhow!("Daemon not connected"))?;
        d.list_conversations().await?
    };

    let conv = conversations
        .conversations
        .iter()
        .find(|c| c.id == conversation_id);

    let title = conv.map(|c| c.title.as_str()).unwrap_or("Linked Chat");
    let title = if title.is_empty() { "Linked Chat" } else { title };

    // Truncate title for topic name
    let topic_title = if title.len() > 128 {
        title[..title.floor_char_boundary(128)].to_string()
    } else {
        title.to_string()
    };

    // Create topic
    let thread_id = telegram.create_topic(&topic_title).await?;

    // Save mapping
    {
        let mut state_w = state.write().await;
        state_w.insert_mapping(conversation_id.to_string(), thread_id);
    }

    // Note: history replay for an existing conversation would require a
    // one-shot event-log read that the plugin SDK does not yet expose. For now
    // we just confirm the link — new events from this conversation will
    // render into the topic via the firehose handler.
    telegram
        .send_to_topic(thread_id, &i18n.t("bot.linked"))
        .await?;
    let _ = daemon;

    // Acknowledge callback
    telegram
        .answer_callback(callback_query_id, &i18n.t("bot.linked"))
        .await?;

    info!("Linked conversation {conversation_id} to topic {thread_id}");
    Ok(())
}

