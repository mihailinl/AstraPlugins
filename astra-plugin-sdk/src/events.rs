//! Typed event structs for common daemon events.
//!
//! These are automatically deserialized by the SDK runner and dispatched
//! to typed handlers on [`PluginCapability`]. Plugin developers use these
//! instead of manually parsing JSON from `on_event`.

use serde::Deserialize;

/// Chat message sync event — sent when any client sends or receives a message.
///
/// The daemon broadcasts these for every message in every conversation.
/// If your plugin sets [`PluginCapability::source_id()`], events from that
/// source are automatically filtered out (you never see your own messages).
#[derive(Debug, Clone, Deserialize)]
pub struct ChatSyncEvent {
    /// Unique message ID.
    pub id: String,
    /// Conversation this message belongs to.
    pub conversation_id: String,
    /// "user" or "assistant".
    pub role: String,
    /// Full accumulated message content (not a delta).
    pub content: String,
    /// Which client sent the original message.
    pub source_id: String,
    /// True while the AI is still generating.
    #[serde(default)]
    pub is_streaming: bool,
    /// True when the message is finalized.
    #[serde(default)]
    pub is_complete: bool,
}

/// State change event — daemon transitioned between states.
#[derive(Debug, Clone, Deserialize)]
pub struct StateChangedEvent {
    pub previous: String,
    pub current: String,
}

/// Command triggered event.
#[derive(Debug, Clone, Deserialize)]
pub struct CommandTriggeredEvent {
    pub command_id: String,
    pub command_name: String,
    #[serde(default)]
    pub variables: std::collections::HashMap<String, String>,
}

/// Command completed event.
#[derive(Debug, Clone, Deserialize)]
pub struct CommandCompletedEvent {
    pub command_id: String,
    pub command_name: String,
    pub success: bool,
}
