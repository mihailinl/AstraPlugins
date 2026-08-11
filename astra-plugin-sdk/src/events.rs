//! Typed event structs for common daemon events.
//!
//! These are automatically deserialized by the SDK runner and dispatched
//! to typed handlers on [`crate::PluginCapability`]. Plugin developers use these
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
    /// The utterance or text that matched the command's trigger.
    ///
    /// This field replaces `variables`, which the daemon never sent:
    /// `AstraEvent::CommandTriggered` carries `command_id`, `command_name` and
    /// `trigger_text` and nothing else (`astra-core/src/event.rs`). `variables`
    /// was `#[serde(default)]`, so it deserialized to an empty map on every
    /// event and a plugin that read it read `{}` forever — a field that cannot
    /// be populated is worse than an absent one, because it looks like an
    /// answer.
    #[serde(default)]
    pub trigger_text: String,
}

/// Command completed event.
#[derive(Debug, Clone, Deserialize)]
pub struct CommandCompletedEvent {
    pub command_id: String,
    pub command_name: String,
    pub success: bool,
}
