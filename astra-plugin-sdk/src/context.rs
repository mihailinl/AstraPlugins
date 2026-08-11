//! [`PluginContext`] — everything a handler needs, in one cheap-to-clone value.
//!
//! # What this replaces
//!
//! Before 0.6 the SDK handed the plugin an `Arc<Mutex<HostClient>>` through
//! `set_host()`, *after* registration, and it was the plugin's problem to store
//! it. Every example did the same thing and dice-roller did it in the shape that
//! shows why it was wrong:
//!
//! ```ignore
//! host: Mutex<Option<Arc<Mutex<HostClient>>>>,
//! // …and then, from a synchronous helper:
//! let host = self.host.try_lock().ok().and_then(|g| g.clone());
//! ```
//!
//! Two locks, one of them tried and abandoned. A tool call that rolled dice
//! while another was firing triggers lost the race and silently fired nothing —
//! `try_lock` returning `Err` was logged as "host client not available yet".
//!
//! [`PluginContext`] is passed *into* the handler, so there is nothing to store
//! and no `Option`; [`Host`] is a trait taking `&self`, so there is nothing to
//! lock. The whole pattern disappears:
//!
//! ```ignore
//! let host = ctx.host().clone();       // Arc clone, infallible
//! tokio::spawn(async move { host.fire_trigger("on_roll_value", &payload).await });
//! ```
//!
//! # Why `Host` is a trait
//!
//! Because a handler must be testable with no daemon, no socket and no Astra
//! installed. `Arc<dyn Host>` is what lets `astra-plugin-sdk`'s test harness
//! (task 5.6) hand a plugin a `RecordingHost` that remembers every fired trigger
//! and can be told to fail on demand. A concrete `HostClient` cannot do that at
//! any price.

use std::sync::Arc;

use anyhow::Result;
use arc_swap::{ArcSwap, ArcSwapOption};

use crate::proto;

/// A stream of chat chunks from [`Host::send_chat_message`].
pub type ChatStream =
    std::pin::Pin<Box<dyn tokio_stream::Stream<Item = Result<proto::PluginChatChunk>> + Send>>;

/// A stream of daemon events from [`Daemon::subscribe_events`].
pub type EventStream =
    std::pin::Pin<Box<dyn tokio_stream::Stream<Item = Result<proto::AstraEvent>> + Send>>;

/// A stream of chat firehose events from [`Daemon::subscribe_chat_events`].
pub type FirehoseStream =
    std::pin::Pin<Box<dyn tokio_stream::Stream<Item = Result<proto::FirehoseEventMsg>> + Send>>;

/// The daemon, as seen from inside a plugin: `PluginHostService`.
///
/// Every method takes `&self`. The real implementation ([`crate::HostClient`])
/// clones its tonic client per call — which is what tonic clients are for — so
/// there is no lock anywhere on this path and concurrent handlers do not
/// serialise behind each other.
///
/// Each method is gated daemon-side by a `[permissions]` grant; the doc comment
/// names which. A denial arrives as `PERMISSION_DENIED`.
#[async_trait::async_trait]
pub trait Host: Send + Sync + 'static {
    /// This plugin's id, as the daemon knows it.
    fn plugin_id(&self) -> &str;

    /// Fire one of this plugin's trigger types. Permission: `fire_trigger`.
    ///
    /// Check [`PluginContext::active_triggers`] first when the payload is
    /// expensive to build — if nothing is listening, the daemon drops it.
    async fn fire_trigger(&self, trigger_type: &str, payload_json: &str) -> Result<()>;

    /// Write a line into the daemon's log buffer — the plugin's log pane.
    /// Permission: none. `level` is `debug` / `info` / `warn` / `error`.
    async fn log(&self, level: &str, message: &str) -> Result<()>;

    /// This plugin's own persisted settings, as JSON. Permission: none.
    ///
    /// Prefer the typed [`crate::PluginCapability::on_config`] hook; this is for
    /// re-reading config from a background task.
    async fn get_config(&self) -> Result<String>;

    /// Daemon version, state and gRPC port. Permission: none.
    async fn get_daemon_info(&self) -> Result<proto::PluginDaemonInfoResponse>;

    /// Publish a variable commands and other plugins can read.
    /// Permission: `set_variable`. `scope` is `session` or `persistent`.
    async fn set_variable(&self, name: &str, value: &str, scope: &str) -> Result<()>;

    /// Push an event into this plugin's own UI iframes — the return path for
    /// `handle_ui_call`. Permission: `push_to_ui`.
    async fn push_to_ui(&self, event: &str, payload_json: &str) -> Result<()>;

    /// Send a chat message as this plugin and stream the assistant's reply.
    /// Permission: `send_chat_message`.
    ///
    /// This is the *only* working path for a client plugin to talk to chat: the
    /// plugin session token is scoped to `PluginHostService`, so the
    /// `ChatService` route through [`Daemon`] answers `PERMISSION_DENIED` unless
    /// the daemon also granted a client session.
    async fn send_chat_message(
        &self,
        text: &str,
        conversation_id: &str,
        voice_enabled: bool,
    ) -> Result<ChatStream>;

    /// Contribute colours, wallpaper and shader to the active Astra theme.
    /// Permission: `set_theme_contribution` (Tier 1 consent — the daemon
    /// refuses it below that).
    async fn set_theme_contribution(&self, theme: proto::PluginThemeContribution) -> Result<()>;

    // ── convenience ──

    /// `log("debug", …)`.
    async fn log_debug(&self, message: &str) -> Result<()> {
        self.log("debug", message).await
    }
    /// `log("info", …)`.
    async fn log_info(&self, message: &str) -> Result<()> {
        self.log("info", message).await
    }
    /// `log("warn", …)`.
    async fn log_warn(&self, message: &str) -> Result<()> {
        self.log("warn", message).await
    }
    /// `log("error", …)`.
    async fn log_error(&self, message: &str) -> Result<()> {
        self.log("error", message).await
    }
}

/// The daemon's full API, for plugins with the `client` capability.
///
/// Present on [`PluginContext::daemon`] only when the daemon issued a client
/// session token at registration. Everything here is a *daemon* service
/// (ChatService, VoiceService, …), not `PluginHostService` — a different
/// authorisation surface, which is why it is a separate trait and an `Option`
/// rather than more methods on [`Host`].
#[async_trait::async_trait]
pub trait Daemon: Send + Sync + 'static {
    // ── core ──

    /// The daemon's current state.
    async fn get_state(&self) -> Result<proto::CoreStateResponse>;

    /// The real-time daemon event stream.
    async fn subscribe_events(&self) -> Result<EventStream>;

    // ── chat ──

    /// Append a user message; the daemon drives the AI turn asynchronously and
    /// every client sees the events through [`Self::subscribe_chat_events`].
    async fn submit_user_message(
        &self,
        text: &str,
        conversation_id: &str,
        voice_enabled: bool,
        source_id: &str,
    ) -> Result<proto::SubmitUserMessageResponse>;

    /// The chat firehose — one stream for every conversation. `cursors` maps
    /// conversation id → last seen seq, so only what you missed is replayed.
    async fn subscribe_chat_events(
        &self,
        cursors: std::collections::HashMap<String, u64>,
    ) -> Result<FirehoseStream>;

    /// Stop AI generation. An empty `conversation_id` cancels every active turn.
    async fn stop_generation(&self, conversation_id: &str) -> Result<()>;

    /// Answer a pending dangerous-tool confirmation.
    async fn respond_to_confirmation(
        &self,
        request_id: &str,
        allowed: bool,
        allow_like_this: bool,
    ) -> Result<()>;

    /// Every conversation the daemon knows about.
    async fn list_conversations(&self) -> Result<proto::ListConversationsResponse>;

    /// Create a conversation.
    async fn create_conversation(&self, title: &str) -> Result<proto::Conversation>;

    /// Delete a conversation.
    async fn delete_conversation(&self, conversation_id: &str) -> Result<()>;

    /// Clear a conversation's messages, keeping the conversation.
    async fn clear_conversation(&self, conversation_id: &str) -> Result<()>;

    // ── voice ──

    /// Speak text through the configured TTS provider.
    async fn speak(&self, text: &str, voice_id: &str, interrupt: bool) -> Result<()>;
    /// Stop the current utterance.
    async fn stop_speaking(&self) -> Result<()>;
    /// Start microphone capture.
    async fn start_listening(&self) -> Result<()>;
    /// Stop microphone capture.
    async fn stop_listening(&self) -> Result<()>;

    // ── commands ──

    /// List commands.
    async fn list_commands(&self, include_disabled: bool) -> Result<proto::CommandListResponse>;

    /// Run a command by id.
    async fn execute_command(
        &self,
        id: &str,
        variables: std::collections::HashMap<String, String>,
    ) -> Result<proto::ExecuteCommandResponse>;

    // ── settings, media, monitor ──

    /// All daemon settings.
    async fn get_settings(&self) -> Result<proto::SettingsResponse>;
    /// Current media playback state for one session.
    async fn get_media_state(&self, session_id: &str) -> Result<proto::MediaState>;
    /// Control media playback.
    async fn control_media(&self, action: i32, session_id: &str) -> Result<()>;
    /// Every active media session.
    async fn get_media_sessions(&self) -> Result<Vec<proto::MediaSessionInfo>>;
    /// CPU / RAM / GPU stats.
    async fn get_system_stats(&self) -> Result<proto::SystemStats>;
}

/// The set of trigger types that currently have at least one command listening.
///
/// The daemon pushes this on `OnActiveTriggers` and the SDK applies it *before*
/// dispatching to the plugin's hook, so `ctx.active_triggers()` is never stale
/// relative to a hook that was told about the same change.
///
/// Reads are wait-free and synchronous, which matters: the check belongs at the
/// top of a hot loop that would otherwise build a payload nobody wants.
#[derive(Clone, Default)]
pub struct ActiveTriggers {
    inner: Arc<ArcSwap<std::collections::HashSet<String>>>,
}

impl ActiveTriggers {
    /// An empty set — nothing is listening.
    pub fn new() -> Self {
        Self::default()
    }

    /// Is anything listening for this trigger type? Un-namespaced, e.g.
    /// `"on_roll_value"`.
    pub fn contains(&self, trigger_type: &str) -> bool {
        self.inner.load().contains(trigger_type)
    }

    /// Nothing is listening for anything.
    pub fn is_empty(&self) -> bool {
        self.inner.load().is_empty()
    }

    /// A snapshot of the whole set.
    pub fn snapshot(&self) -> Vec<String> {
        let mut v: Vec<String> = self.inner.load().iter().cloned().collect();
        v.sort();
        v
    }

    /// Replace the set. Called by the SDK on `OnActiveTriggers`; a test harness
    /// calls it to stage a scenario.
    pub fn set(&self, types: impl IntoIterator<Item = String>) {
        self.inner.store(Arc::new(types.into_iter().collect()));
    }
}

impl std::fmt::Debug for ActiveTriggers {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_tuple("ActiveTriggers").field(&self.snapshot()).finish()
    }
}

/// Everything a handler is given: who this plugin is, what the daemon's UI
/// language is, what is listening, and the two clients.
///
/// Cloning is five atomic increments — clone it into a `tokio::spawn` without
/// thinking about it. The mutable parts (language, active triggers) are shared,
/// so a clone taken at startup sees later updates.
#[derive(Clone)]
pub struct PluginContext {
    inner: Arc<Inner>,
}

struct Inner {
    plugin_id: String,
    language: ArcSwap<String>,
    active_triggers: ActiveTriggers,
    host: Arc<dyn Host>,
    /// Immutable: the client session either existed at registration or it did
    /// not, and nothing later can grant one. An `ArcSwap` here would suggest a
    /// plugin could become client-capable at runtime, which is not true.
    daemon: Option<Arc<dyn Daemon>>,
}

impl PluginContext {
    /// Build a context around a [`Host`].
    ///
    /// The SDK calls this once, after registration. A test builds one around a
    /// fake host and calls handlers directly — that is the whole point of the
    /// trait.
    pub fn new(plugin_id: impl Into<String>, host: Arc<dyn Host>) -> Self {
        Self {
            inner: Arc::new(Inner {
                plugin_id: plugin_id.into(),
                language: ArcSwap::from_pointee("en".to_string()),
                active_triggers: ActiveTriggers::new(),
                host,
                daemon: None,
            }),
        }
    }

    /// Attach the daemon client (client-capable plugins only).
    ///
    /// Builder-only: panics if the context has already been cloned, because the
    /// clones would not see it. The SDK calls this before anyone else holds one.
    pub fn with_daemon(mut self, daemon: Arc<dyn Daemon>) -> Self {
        Arc::get_mut(&mut self.inner)
            .expect("with_daemon must be called before the context is shared")
            .daemon = Some(daemon);
        self
    }

    /// Set the initial UI language.
    pub fn with_language(self, language: impl Into<String>) -> Self {
        self.set_language(language);
        self
    }

    /// This plugin's id, as the daemon knows it.
    pub fn plugin_id(&self) -> &str {
        &self.inner.plugin_id
    }

    /// The daemon's current UI language (`"en"`, `"ru"`, …).
    ///
    /// Kept up to date by the SDK; a background task can read it at any time
    /// without holding anything.
    pub fn language(&self) -> Arc<String> {
        self.inner.language.load_full()
    }

    /// What is listening. See [`ActiveTriggers`].
    pub fn active_triggers(&self) -> &ActiveTriggers {
        &self.inner.active_triggers
    }

    /// The daemon, as `PluginHostService`. Always present.
    ///
    /// `ctx.host().fire_trigger(..)` calls straight through;
    /// `ctx.host().clone()` gives an `Arc<dyn Host>` to move into a task.
    pub fn host(&self) -> &Arc<dyn Host> {
        &self.inner.host
    }

    /// The full daemon API — `Some` only for plugins with the `client`
    /// capability, whose registration was granted a client session token.
    pub fn daemon(&self) -> Option<&Arc<dyn Daemon>> {
        self.inner.daemon.as_ref()
    }

    /// Set the UI language. Called by the SDK on `OnLanguageChanged`.
    pub fn set_language(&self, language: impl Into<String>) {
        self.inner.language.store(Arc::new(language.into()));
    }
}

impl std::fmt::Debug for PluginContext {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PluginContext")
            .field("plugin_id", &self.plugin_id())
            .field("language", &self.language())
            .field("active_triggers", self.active_triggers())
            .field("daemon", &self.inner.daemon.is_some())
            .finish_non_exhaustive()
    }
}

// ── the ambient context, for background tasks ────────────────────────────────

static CURRENT: std::sync::LazyLock<ArcSwapOption<PluginContext>> =
    std::sync::LazyLock::new(ArcSwapOption::empty);

/// The running plugin's context.
///
/// Handlers are *given* a `&PluginContext` and should use that. This is for the
/// places a parameter cannot reach: a `Drop` impl, a callback from a C library,
/// a `std::thread` spawned at startup, a `once_cell` initialiser.
///
/// `None` before [`crate::run`] has registered, and in a unit test that has not
/// called [`install_context`].
pub fn try_ctx() -> Option<PluginContext> {
    CURRENT.load_full().map(|c| (*c).clone())
}

/// [`try_ctx`] or panic.
///
/// Panics with one sentence naming the cause, because the alternative — an
/// `unwrap` on a `None` twelve frames down — names nothing.
pub fn ctx() -> PluginContext {
    try_ctx().expect(
        "no PluginContext yet: the plugin has not finished registering. \
         Handlers are passed `ctx` — use that. From a background task started \
         before `on_start`, clone the context in `on_start` instead.",
    )
}

/// Publish `ctx` as the ambient context. The SDK calls this once, right after
/// registration; a test harness calls it to make [`ctx`] work.
pub fn install_context(context: PluginContext) {
    CURRENT.store(Some(Arc::new(context)));
}

#[cfg(test)]
mod tests {
    use super::*;

    struct NullHost;

    #[async_trait::async_trait]
    impl Host for NullHost {
        fn plugin_id(&self) -> &str {
            "test"
        }
        async fn fire_trigger(&self, _: &str, _: &str) -> Result<()> {
            Ok(())
        }
        async fn log(&self, _: &str, _: &str) -> Result<()> {
            Ok(())
        }
        async fn get_config(&self) -> Result<String> {
            Ok("{}".into())
        }
        async fn get_daemon_info(&self) -> Result<proto::PluginDaemonInfoResponse> {
            Ok(Default::default())
        }
        async fn set_variable(&self, _: &str, _: &str, _: &str) -> Result<()> {
            Ok(())
        }
        async fn push_to_ui(&self, _: &str, _: &str) -> Result<()> {
            Ok(())
        }
        async fn send_chat_message(&self, _: &str, _: &str, _: bool) -> Result<ChatStream> {
            Ok(Box::pin(tokio_stream::empty()))
        }
        async fn set_theme_contribution(&self, _: proto::PluginThemeContribution) -> Result<()> {
            Ok(())
        }
    }

    fn ctx_for_test() -> PluginContext {
        PluginContext::new("test", Arc::new(NullHost))
    }

    /// The property the whole redesign rests on: a clone taken anywhere sees
    /// updates made anywhere. dice-roller's `try_lock` existed because the old
    /// shape had no way to say this.
    #[test]
    fn clones_share_the_mutable_parts() {
        let a = ctx_for_test();
        let b = a.clone();
        a.set_language("ru");
        assert_eq!(*b.language(), "ru");
        a.active_triggers().set(["on_roll_value".to_string()]);
        assert!(b.active_triggers().contains("on_roll_value"));
        assert!(!b.active_triggers().contains("on_time"));
    }

    #[test]
    fn a_context_without_a_client_session_has_no_daemon() {
        assert!(ctx_for_test().daemon().is_none());
    }

    #[tokio::test]
    async fn host_is_callable_through_the_arc_with_no_lock() {
        let ctx = ctx_for_test();
        let host = ctx.host().clone();
        tokio::spawn(async move { host.fire_trigger("t", "{}").await })
            .await
            .unwrap()
            .unwrap();
        ctx.host().log_info("still usable").await.unwrap();
    }
}
