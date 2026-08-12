// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

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

    /// [`fire_trigger`](Self::fire_trigger), naming the daemon call that caused
    /// it.
    ///
    /// **Plugin authors never call this.** It is the seam the SDK uses to carry
    /// a per-invocation lease back to the daemon, so that a trigger fired while
    /// handling a call can be attributed to the conversation that call came
    /// from instead of landing in a thread nobody is looking at. The runner
    /// scopes the context it hands a handler ([`PluginContext::for_invocation`])
    /// and `ctx.host()` then fills the cause in on its own.
    ///
    /// Defaulted on purpose: an existing `Host` implementation — a test double,
    /// a fake in someone else's crate — keeps compiling and simply drops the
    /// cause, which is the honest degradation. The daemon treats an absent,
    /// unknown, expired, exhausted or foreign cause identically: the fire
    /// becomes a root event. So a `Host` that ignores this is never *wrong*,
    /// only unattributed. Never synthesise a value to fill it.
    async fn fire_trigger_caused_by(
        &self,
        trigger_type: &str,
        payload_json: &str,
        cause: Option<&str>,
    ) -> Result<()> {
        let _ = cause;
        self.fire_trigger(trigger_type, payload_json).await
    }

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
    /// What [`host`](Self::host) hands out — normally `inner.host` itself, and
    /// a [`CausalHost`] wrapping it while a daemon call is being handled.
    ///
    /// It sits beside `inner` rather than inside it because a per-invocation
    /// context must NOT be a new [`Inner`]: see [`Inner::id`]. Two contexts that
    /// share one `Inner` share one identity, one language cell and one trigger
    /// set, and differ only in which host their handler fires through.
    scoped_host: Arc<dyn Host>,
}

struct Inner {
    /// Distinguishes this context from every other one this process makes, for
    /// the process's whole life.
    ///
    /// It exists for the 0.5 compatibility shim, which has to deliver `set_host`
    /// exactly once per (plugin, context) pair and — being a blanket impl — has
    /// no field of its own to remember that in. It used the *address* of the
    /// host `Arc` instead, and an address is only unique while the thing at it
    /// is alive: a test process that builds a harness, drops it, and builds
    /// another gets the allocator's recently-freed blocks back, in the same
    /// order, from the same construction sequence. The second harness then
    /// collided with the first's record, its `set_host` was skipped as "already
    /// delivered", and its plugin answered `host client not available yet`.
    ///
    /// A counter cannot be recycled, so the collision cannot happen. It is not
    /// public: nothing outside the shim has any business identifying a context.
    id: u64,
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
        static NEXT_ID: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);
        Self {
            scoped_host: host.clone(),
            inner: Arc::new(Inner {
                // Relaxed: the only requirement is that no two contexts get the
                // same number, which `fetch_add` gives on its own. Nothing is
                // ordered against this value.
                id: NEXT_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed),
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
    ///
    /// While a handler is running this is the *scoped* host: a trigger fired
    /// through it names the daemon call that caused it, so its output lands in
    /// the conversation the user is actually looking at. That property rides in
    /// the `Arc` and therefore survives `clone()` and `tokio::spawn` — which it
    /// has to, because the shipped reference idiom fires from a detached task
    /// (`examples/dice-roller/src/main.rs`). Everywhere else — [`ctx()`], a host
    /// stashed at `on_start`, a raw `std::thread` — this is the plain host and
    /// the fire is a root event.
    pub fn host(&self) -> &Arc<dyn Host> {
        &self.scoped_host
    }

    /// This context, scoped to one daemon call.
    ///
    /// The runner builds one of these per inbound RPC from the lease in the
    /// call's metadata, and hands it to the handler in place of the shared
    /// context. `cause: None` yields a plain clone, which is what every arm gets
    /// from a daemon that does not issue leases — i.e. every daemon today.
    ///
    /// **It reuses `inner`, deliberately.** A fresh [`PluginContext::new`] would
    /// mint a new [`Inner::id`], and the 0.5 compatibility shim keys "have I
    /// delivered `set_host` for this context" on that number in a process-global
    /// set that is never pruned — so a per-call context would leak one entry per
    /// action call, forever, inside every third-party plugin process.
    pub(crate) fn for_invocation(&self, cause: Option<Arc<str>>) -> Self {
        match cause {
            Some(cause) => Self {
                inner: self.inner.clone(),
                scoped_host: Arc::new(CausalHost {
                    inner: self.inner.host.clone(),
                    cause,
                }),
            },
            None => self.clone(),
        }
    }

    /// This context's process-unique number. See [`Inner::id`].
    ///
    /// Clones share it — they share one `Inner` — which is the point: every hook
    /// the runner forwards gets a clone, and they must all look like the same
    /// context to the 0.5 shim.
    pub(crate) fn instance_id(&self) -> u64 {
        self.inner.id
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

/// The real host, plus the lease for the call currently being handled.
///
/// Everything forwards untouched except [`Host::fire_trigger`], which is the
/// one method whose result the daemon has to file somewhere. There is no
/// `Deref`-style shortcut here: `Host` has ten required methods and forwarding
/// them by hand is the price of the wrapper being the only thing that differs.
/// The four `log_*` conveniences are NOT overridden — their defaults call
/// `self.log`, which forwards, so they reach the same place.
struct CausalHost {
    inner: Arc<dyn Host>,
    cause: Arc<str>,
}

#[async_trait::async_trait]
impl Host for CausalHost {
    fn plugin_id(&self) -> &str {
        self.inner.plugin_id()
    }

    /// The whole point. A plugin author writes `ctx.host().fire_trigger(..)`
    /// and the lease goes with it.
    async fn fire_trigger(&self, trigger_type: &str, payload_json: &str) -> Result<()> {
        self.inner
            .fire_trigger_caused_by(trigger_type, payload_json, Some(&self.cause))
            .await
    }

    /// An explicit cause wins over the scoped one — the caller knows something
    /// this wrapper does not. `None` means "use my scope", not "no cause": a
    /// caller wanting a root event fires through a host that was never scoped.
    async fn fire_trigger_caused_by(
        &self,
        trigger_type: &str,
        payload_json: &str,
        cause: Option<&str>,
    ) -> Result<()> {
        self.inner
            .fire_trigger_caused_by(trigger_type, payload_json, cause.or(Some(&self.cause)))
            .await
    }

    async fn log(&self, level: &str, message: &str) -> Result<()> {
        self.inner.log(level, message).await
    }

    async fn get_config(&self) -> Result<String> {
        self.inner.get_config().await
    }

    async fn get_daemon_info(&self) -> Result<proto::PluginDaemonInfoResponse> {
        self.inner.get_daemon_info().await
    }

    async fn set_variable(&self, name: &str, value: &str, scope: &str) -> Result<()> {
        self.inner.set_variable(name, value, scope).await
    }

    async fn push_to_ui(&self, event: &str, payload_json: &str) -> Result<()> {
        self.inner.push_to_ui(event, payload_json).await
    }

    async fn send_chat_message(
        &self,
        text: &str,
        conversation_id: &str,
        voice_enabled: bool,
    ) -> Result<ChatStream> {
        self.inner
            .send_chat_message(text, conversation_id, voice_enabled)
            .await
    }

    async fn set_theme_contribution(&self, theme: proto::PluginThemeContribution) -> Result<()> {
        self.inner.set_theme_contribution(theme).await
    }
}

/// Records what cause each fire arrived with, so a test can tell "no lease"
/// apart from "a lease that did not survive".
///
/// Crate-visible rather than local to this module's tests, because the runner's
/// over-the-wire tests need the same double and a second copy of a ten-method
/// trait impl is a second thing to keep in step.
#[cfg(test)]
#[derive(Default)]
pub(crate) struct CauseSpy {
    fires: std::sync::Mutex<Vec<(String, Option<String>)>>,
}

#[cfg(test)]
impl CauseSpy {
    pub(crate) fn causes(&self) -> Vec<Option<String>> {
        self.fires.lock().unwrap().iter().map(|(_, c)| c.clone()).collect()
    }
}

#[cfg(test)]
#[async_trait::async_trait]
impl Host for CauseSpy {
    fn plugin_id(&self) -> &str {
        "spy"
    }
    async fn fire_trigger(&self, t: &str, _: &str) -> Result<()> {
        self.fires.lock().unwrap().push((t.into(), None));
        Ok(())
    }
    async fn fire_trigger_caused_by(&self, t: &str, _: &str, cause: Option<&str>) -> Result<()> {
        self.fires
            .lock()
            .unwrap()
            .push((t.into(), cause.map(str::to_owned)));
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

    // ── the invocation lease ─────────────────────────────────────────────────

    fn spied() -> (PluginContext, Arc<CauseSpy>) {
        let spy = Arc::new(CauseSpy::default());
        (PluginContext::new("test", spy.clone()), spy)
    }

    /// The reason `for_invocation` reuses `inner` instead of building a fresh
    /// context: the 0.5 shim keys "have I delivered `set_host`" on this number
    /// in a global set that is never pruned, so a per-call identity would leak
    /// an entry per action call for the life of the process.
    #[test]
    fn a_scoped_context_is_the_same_context() {
        let (ctx, _) = spied();
        let scoped = ctx.for_invocation(Some(Arc::from("lease-1")));
        assert_eq!(scoped.instance_id(), ctx.instance_id());
        assert_eq!(scoped.plugin_id(), ctx.plugin_id());

        // And it is still one shared cell, not a snapshot.
        scoped.set_language("ru");
        assert_eq!(*ctx.language(), "ru");
        ctx.active_triggers().set(["on_roll_value".to_string()]);
        assert!(scoped.active_triggers().contains("on_roll_value"));
    }

    /// The property Rust cannot get from a task-local, and the whole reason the
    /// cause rides in the `Arc` instead: the shipped reference idiom clones the
    /// host, `tokio::spawn`s, and fires from there.
    #[tokio::test]
    async fn the_cause_survives_a_detached_task() {
        let (ctx, spy) = spied();
        let scoped = ctx.for_invocation(Some(Arc::from("lease-1")));

        let host = scoped.host().clone();
        tokio::spawn(async move {
            // An await first, so this cannot pass by running inline.
            tokio::task::yield_now().await;
            host.fire_trigger("on_roll_value", "{}").await
        })
        .await
        .unwrap()
        .unwrap();

        assert_eq!(spy.causes(), vec![Some("lease-1".to_string())]);
    }

    /// Everything that is not a scoped handler is a root event, and says so by
    /// carrying nothing at all rather than by carrying an empty string.
    #[tokio::test]
    async fn an_unscoped_context_fires_with_no_cause() {
        let (ctx, spy) = spied();
        ctx.host().fire_trigger("on_time", "{}").await.unwrap();

        // …including a context scoped with no lease, which is what every arm
        // gets from a daemon that does not issue them — i.e. every daemon in
        // the field today.
        let unleased = ctx.for_invocation(None);
        unleased.host().fire_trigger("on_time", "{}").await.unwrap();

        assert_eq!(spy.causes(), vec![None, None]);
    }

    /// The **ambient** context is never scoped, even while a leased call is in
    /// flight beside it.
    ///
    /// Distinct from the test above, which uses a context nobody scoped: this
    /// one pins [`ctx()`] itself, the process-global that a `Drop` impl, a
    /// callback from a C library or a `std::thread` started at boot reaches
    /// for. Those places have no way to know which call is running, so picking
    /// up whichever lease happened to be live would attribute their output to a
    /// conversation chosen by timing. `install_context` publishes the base
    /// context and `for_invocation` never republishes, so the answer is `None`
    /// — a root event, decided by the source rather than by the clock.
    #[tokio::test]
    async fn the_ambient_context_is_never_scoped() {
        let (base, spy) = spied();
        install_context(base.clone());

        // A leased call is being handled…
        let scoped = base.for_invocation(Some(Arc::from("lease-1")));
        scoped.host().fire_trigger("from_the_handler", "{}").await.unwrap();

        // …and something outside it reaches for the ambient context meanwhile.
        ctx().host().fire_trigger("from_a_drop_impl", "{}").await.unwrap();

        assert_eq!(spy.causes(), vec![Some("lease-1".to_string()), None]);
    }

    /// A caller who names a cause knows something the scope does not.
    #[tokio::test]
    async fn an_explicit_cause_beats_the_scoped_one() {
        let (ctx, spy) = spied();
        let scoped = ctx.for_invocation(Some(Arc::from("lease-1")));
        scoped
            .host()
            .fire_trigger_caused_by("on_roll_value", "{}", Some("lease-2"))
            .await
            .unwrap();
        assert_eq!(spy.causes(), vec![Some("lease-2".to_string())]);
    }

    /// The compatibility promise attached to the defaulted trait method: a
    /// `Host` written before leases existed keeps working, and simply reports a
    /// root event. `NullHost` overrides neither method.
    #[tokio::test]
    async fn a_host_that_never_heard_of_leases_still_fires() {
        let ctx = ctx_for_test().for_invocation(Some(Arc::from("lease-1")));
        ctx.host().fire_trigger("on_roll_value", "{}").await.unwrap();
    }
}
