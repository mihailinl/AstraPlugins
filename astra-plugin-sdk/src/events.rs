//! Typed event structs for common daemon events.
//!
//! These are automatically deserialized by the SDK runner and dispatched
//! to typed handlers on [`PluginCapability`]. Plugin developers use these
//! instead of manually parsing JSON from `on_event`.

use serde::Deserialize;

// Chat events flow through `DaemonClient::subscribe_chat_events` (firehose),
// not through the host event bus. See `capability::on_conversation_event`.

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
