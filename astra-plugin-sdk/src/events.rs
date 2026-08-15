// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

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
///
/// # The daemon no longer sends the phrase that started the command
///
/// `trigger_text` was the utterance the user typed or spoke — or, for a
/// plugin's own fire, the whole payload it sent — and it went to every plugin
/// declaring `command_triggered`. The daemon removed the field from the event
/// entirely: it is the user's own words, and asking to hear that commands ran
/// is not asking to hear what the user said. There is nowhere for it to ride
/// any more, so a plugin reading it would read `""` forever.
///
/// What replaces it is [`Self::trigger_type`] — WHICH doorbell rang, as a
/// machine identifier — plus [`Self::run_id`], so a fire can be joined to the
/// command it started and to the later `command_completed`.
#[derive(Debug, Clone, Deserialize)]
pub struct CommandTriggeredEvent {
    pub command_id: String,
    /// The command's own name — **only for the plugin whose own
    /// [`fire_trigger`](crate::HostClient) started this command.**
    ///
    /// A command's name is the user's own writing, so every other reader gets
    /// `""`. The KEY is always present, which is why this is not an `Option`:
    /// the shape a plugin deserializes must not depend on who is reading it.
    #[serde(default)]
    pub command_name: String,
    /// Which doorbell rang — the trigger's DECLARED type, resolved off the
    /// entry node, never the phrase that rang it.
    ///
    /// The daemon's built-in vocabulary is `text`, `hotkey`, `reminder`,
    /// `calendar_event` and `schedule`; a plugin's own trigger is
    /// `plugin__<id with '-' replaced by '_'>__<event>`.
    #[serde(default)]
    pub trigger_type: String,
    /// The run this fire started, as a UUID string. Stable for the whole run,
    /// so a plugin can correlate its own fire with what came of it.
    #[serde(default)]
    pub run_id: String,
    /// The plugin whose own fire started this command — `None` for every other
    /// reader, so this never enumerates the plugins installed on the machine.
    ///
    /// `Some(id)` is therefore exactly "this is the answer to MY fire".
    #[serde(default)]
    pub fired_by: Option<String>,
}

/// Command completed event.
#[derive(Debug, Clone, Deserialize)]
pub struct CommandCompletedEvent {
    pub command_id: String,
    /// **Always `""`.** Unlike `command_triggered`, this event carries nothing
    /// that says whose fire it was, so there is no reader the daemon can safely
    /// give the user's own writing to. Correlate by [`Self::command_id`], which
    /// is the same value the matching `command_triggered` carried.
    #[serde(default)]
    pub command_name: String,
    pub success: bool,
}
