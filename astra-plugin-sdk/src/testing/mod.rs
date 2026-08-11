// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! Two test harnesses, and the reason there are two.
//!
//! # Level 1 — in process
//!
//! [`Harness`] runs the plugin's hooks directly against a [`RecordingHost`].
//! No daemon, no socket, no Astra installed, no runtime the author has to
//! build. It is fast enough to put on every handler, and it is where the
//! *logic* is tested: what a tool answers, which triggers it fires, what it
//! does when the host says no.
//!
//! ```no_run
//! # use astra_plugin_sdk::prelude::*;
//! # use astra_plugin_sdk::testing::Harness;
//! # #[derive(Default)] struct Dice;
//! # #[async_trait] impl PluginCapability for Dice { type Config = NoConfig; }
//! # async fn f() -> anyhow::Result<()> {
//! let h = Harness::new(Dice::default())
//!     .with_config(json!({ "default_sides": 20 }))
//!     .start()
//!     .await?;
//!
//! let out = h.call_tool("roll_dice", json!({ "count": 2 })).await?;
//! assert!(h.fired_triggers().iter().any(|t| t.trigger_type == "on_roll_value"));
//! # Ok(()) }
//! ```
//!
//! # Level 2 — over the wire
//!
//! [`WireHarness`] starts a [`MockDaemon`] on loopback, runs the plugin's real
//! [`run`](crate::run) startup path against it — bind, register, config,
//! language, `on_start`, serve — and drives it with a real
//! `PluginCapabilityServiceClient`.
//!
//! It exists because level 1 **structurally cannot** catch these, and this
//! project shipped every one of them:
//!
//! | defect | why level 1 is blind to it |
//! |---|---|
//! | a hook the gRPC service never routes to the plugin | level 1 calls the hook directly |
//! | a descriptor that disagrees with the daemon's | level 1 never encodes a message |
//! | the session-token interceptor missing | level 1 makes no RPC |
//! | field-name casing on the wire | level 1 passes Rust values |
//! | the 500-slot audio channel sized at 32 | level 1 has no channel in between |
//!
//! ```no_run
//! # use astra_plugin_sdk::prelude::*;
//! # use astra_plugin_sdk::testing::WireHarness;
//! # #[derive(Default)] struct Dice;
//! # #[async_trait] impl PluginCapability for Dice { type Config = NoConfig; }
//! # async fn f() -> anyhow::Result<()> {
//! let w = WireHarness::start(Dice::default()).await?;
//! let tools = w.list_tools().await?;                  // a real ListTools RPC
//! let out = w.call_tool("roll_dice", "{}").await?;    // a real CallTool RPC
//! assert!(!w.daemon().fired_triggers().is_empty());   // what reached the daemon
//! w.shutdown().await?;
//! # Ok(()) }
//! ```
//!
//! # Why this module is always compiled
//!
//! §3.1's bar is **one dependency**. A `testing` feature would mean a second
//! `[dev-dependencies]` entry in every plugin's `Cargo.toml` and a paragraph
//! explaining it; the harness is a few hundred lines of code that a release
//! build's dead-code pass removes, so the trade is not close.

pub mod fixtures;
mod host;
mod wire;

pub use host::{
    ChatMessage, FiredTrigger, HOST_RPCS, LogLine, Recorded, RecordingHost, UiPush, Variable,
};
pub use wire::{CapabilityClient, MockDaemon, WireHarness};

use std::sync::Arc;

use anyhow::{Context, Result};

use crate::capability::{
    AiChunk, AiRequest, AudioChunk, AudioData, PluginCapability, SttEvent, SttLoadState, SttOptions,
    ToolDef, TtsRequest,
};
use crate::context::{Host, PluginContext};
use crate::error::ToolError;
use crate::proto;

/// A plugin under test, before it has started. See the [module docs](self).
pub struct Harness<P: PluginCapability> {
    plugin: P,
    plugin_id: String,
    config_json: Option<String>,
    language: String,
    active_triggers: Vec<String>,
    host: Arc<RecordingHost>,
    daemon: Option<Arc<dyn crate::context::Daemon>>,
    install_ambient: bool,
}

impl<P: PluginCapability> Harness<P> {
    /// A harness around `plugin`, with a fresh [`RecordingHost`].
    pub fn new(plugin: P) -> Self {
        Self {
            plugin,
            plugin_id: "test-plugin".to_string(),
            config_json: None,
            language: "en".to_string(),
            active_triggers: Vec::new(),
            host: RecordingHost::new("test-plugin"),
            daemon: None,
            install_ambient: false,
        }
    }

    /// The settings [`start`](Self::start) delivers, as anything that
    /// serializes — `json!({..})`, or the plugin's own `Config` type.
    ///
    /// Delivered through [`PluginCapability::on_config_changed`], the same path
    /// the daemon uses, so a payload that does not fit the plugin's `Config`
    /// is handled by the plugin's real code and not by the harness.
    pub fn with_config(mut self, config: impl serde::Serialize) -> Self {
        self.config_json = Some(
            serde_json::to_string(&config).expect("harness config must serialize to JSON"),
        );
        self
    }

    /// The settings, as the raw JSON string the daemon would send. For the
    /// payloads that are not valid JSON at all — see
    /// [`fixtures::config_fuzz`].
    pub fn with_config_json(mut self, json: impl Into<String>) -> Self {
        self.config_json = Some(json.into());
        self
    }

    /// The daemon's UI language. Default `"en"`.
    pub fn with_language(mut self, language: impl Into<String>) -> Self {
        self.language = language.into();
        self
    }

    /// The plugin id the context reports. Default `"test-plugin"`.
    pub fn with_plugin_id(mut self, id: impl Into<String>) -> Self {
        let id = id.into();
        self.host = RecordingHost::new(id.clone());
        self.plugin_id = id;
        self
    }

    /// Start with these trigger types already listening, so
    /// `ctx.active_triggers().contains(..)` answers true.
    pub fn with_active_triggers(
        mut self,
        types: impl IntoIterator<Item = impl Into<String>>,
    ) -> Self {
        self.active_triggers = types.into_iter().map(Into::into).collect();
        self
    }

    /// Use this host instead of the default one — to stage failures before
    /// `on_start` runs, or to share one host between two harnesses.
    pub fn with_host(mut self, host: Arc<RecordingHost>) -> Self {
        self.host = host;
        self
    }

    /// Give the context a [`Daemon`](crate::Daemon), as the daemon does for a
    /// plugin that declared the `client` capability. Without this,
    /// `ctx.daemon()` is `None` — which is what a non-client plugin sees.
    pub fn with_daemon(mut self, daemon: Arc<dyn crate::context::Daemon>) -> Self {
        self.daemon = Some(daemon);
        self
    }

    /// Publish the context as the ambient one, so [`ctx()`](crate::ctx) works.
    ///
    /// Off by default and deliberately: the ambient context is process-global,
    /// so two harnesses in one test binary would fight over it. Turn it on for
    /// a plugin that reaches for `ctx()` from a background task, and keep that
    /// test alone in its file (`tests/`) or `#[serial]`.
    pub fn with_ambient_context(mut self) -> Self {
        self.install_ambient = true;
        self
    }

    /// Run the startup sequence — `on_config` → `on_language_changed` →
    /// `on_start` — and hand back the running plugin.
    ///
    /// The order is the runner's, not a convenient one: a plugin that starts a
    /// background loop in `on_start` must already have its settings, and 0.5
    /// ran these the other way round.
    pub async fn start(self) -> Result<Running<P>> {
        let plugin = Arc::new(self.plugin);
        let mut ctx = PluginContext::new(
            self.plugin_id.clone(),
            self.host.clone() as Arc<dyn Host>,
        );
        if let Some(daemon) = self.daemon {
            ctx = ctx.with_daemon(daemon);
        }
        ctx.set_language(self.language.clone());
        ctx.active_triggers().set(self.active_triggers.clone());

        if self.install_ambient {
            crate::context::install_context(ctx.clone());
        }

        if let Some(config) = &self.config_json {
            plugin.on_config_changed(&ctx, config).await;
        }
        plugin.on_language_changed(&ctx, &self.language).await;
        plugin
            .on_start(&ctx)
            .await
            .context("on_start failed; the plugin would not have started")?;

        Ok(Running {
            plugin,
            ctx,
            host: self.host,
        })
    }
}

/// A started plugin. Every method is one hook, called the way the daemon calls
/// it.
pub struct Running<P: PluginCapability> {
    plugin: Arc<P>,
    ctx: PluginContext,
    host: Arc<RecordingHost>,
}

impl<P: PluginCapability> Running<P> {
    /// The plugin itself, for assertions on its own state.
    pub fn plugin(&self) -> &Arc<P> {
        &self.plugin
    }

    /// The context handlers are given.
    pub fn ctx(&self) -> &PluginContext {
        &self.ctx
    }

    /// The recording host, for failure injection mid-test.
    pub fn host(&self) -> &Arc<RecordingHost> {
        &self.host
    }

    /// Every `FireTrigger` the plugin has made, in order.
    pub fn fired_triggers(&self) -> Vec<FiredTrigger> {
        self.host.fired_triggers()
    }
    /// Every `PluginLog`, in order.
    pub fn logs(&self) -> Vec<LogLine> {
        self.host.logs()
    }
    /// Every `SetVariable`, in order.
    pub fn variables(&self) -> Vec<Variable> {
        self.host.variables()
    }
    /// Every `PushToUi`, in order.
    pub fn ui_pushes(&self) -> Vec<UiPush> {
        self.host.ui_pushes()
    }

    /// Wait until the plugin has fired `trigger_type` at least `n` times, or
    /// fail after a second.
    ///
    /// The hook that fires a trigger is frequently not the one that returns —
    /// dice-roller spawns the fire loop so the tool answers immediately — and
    /// asserting on `fired_triggers()` the instant `call_tool` returns is a
    /// race that passes on a fast machine and fails in CI.
    pub async fn wait_for_triggers(&self, trigger_type: &str, n: usize) -> Vec<FiredTrigger> {
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(1);
        loop {
            let got: Vec<FiredTrigger> = self
                .fired_triggers()
                .into_iter()
                .filter(|t| t.trigger_type == trigger_type)
                .collect();
            if got.len() >= n {
                return got;
            }
            assert!(
                std::time::Instant::now() < deadline,
                "waited 1s for {n}× `{trigger_type}`; saw {} ({:?})",
                got.len(),
                self.host.recorded().calls(),
            );
            tokio::time::sleep(std::time::Duration::from_millis(5)).await;
        }
    }

    // ── tools ──

    /// `list_tools()`.
    pub async fn tools(&self) -> Vec<ToolDef> {
        self.plugin.list_tools().await
    }

    /// The declared JSON Schema for one tool's arguments.
    ///
    /// Panics if the plugin declares no such tool — naming the ones it does,
    /// because "no schema" and "the name is spelled differently" are the two
    /// things this is used to tell apart.
    pub async fn schema(&self, tool: &str) -> ToolSchema {
        let tools = self.tools().await;
        let found = tools.iter().find(|t| t.name == tool).unwrap_or_else(|| {
            let names: Vec<&str> = tools.iter().map(|t| t.name.as_str()).collect();
            panic!("no tool named `{tool}`. Declared: {names:?}");
        });
        ToolSchema {
            tool: tool.to_string(),
            json: serde_json::from_str(&found.parameters_json).unwrap_or_else(|e| {
                panic!(
                    "tool `{tool}` declares a schema that is not JSON ({e}): {}",
                    found.parameters_json
                )
            }),
        }
    }

    /// Assert that `tool`'s declared schema is the one `T` generates.
    ///
    /// The failure this catches is a handler that parses `T` while its
    /// `ToolDef` advertises something else — the model is then told about
    /// fields the handler ignores, and calls the tool with arguments that
    /// cannot work. `#[tool]` derives one from the other so they cannot
    /// disagree; this is for the hooks that are hand-written.
    #[cfg(feature = "schema")]
    pub async fn assert_schema_matches<T: crate::schema::JsonSchema>(&self, tool: &str) {
        self.schema(tool).await.assert_matches::<T>();
    }

    /// Call one tool. `args` is anything that serializes — `json!({..})`, or
    /// the argument type itself.
    pub async fn call_tool(&self, name: &str, args: impl serde::Serialize) -> Result<String, ToolError> {
        let args = serde_json::to_string(&args).map_err(ToolError::from)?;
        self.plugin.call_tool(&self.ctx, name, &args).await
    }

    /// Call one tool with raw argument JSON, valid or not.
    pub async fn call_tool_json(&self, name: &str, args: &str) -> Result<String, ToolError> {
        self.plugin.call_tool(&self.ctx, name, args).await
    }

    // ── actions, triggers, UI ──

    /// `action_types()`.
    pub async fn action_types(&self) -> Vec<crate::capability::ActionTypeDef> {
        self.plugin.action_types().await
    }

    /// `execute_action(..)`.
    pub async fn execute_action(
        &self,
        action_type: &str,
        params: impl serde::Serialize,
    ) -> Result<String, ToolError> {
        let params = serde_json::to_string(&params).map_err(ToolError::from)?;
        self.plugin
            .execute_action(&self.ctx, action_type, &params)
            .await
    }

    /// `trigger_types()`.
    pub async fn trigger_types(&self) -> Vec<crate::capability::TriggerTypeDef> {
        self.plugin.trigger_types().await
    }

    /// `ui_contributions()`.
    pub async fn ui_contributions(&self) -> Vec<crate::capability::UiContribution> {
        self.plugin.ui_contributions().await
    }

    /// `handle_ui_call(..)` — what `astra.call(method, params)` reaches.
    pub async fn ui_call(
        &self,
        method: &str,
        params: impl serde::Serialize,
    ) -> Result<String, ToolError> {
        let params = serde_json::to_string(&params).map_err(ToolError::from)?;
        self.plugin.handle_ui_call(&self.ctx, method, &params).await
    }

    // ── STT ──

    /// `stt_transcribe(..)` with one complete buffer.
    pub async fn stt_transcribe(&self, audio: &[u8], sample_rate: u32) -> Result<SttEvent> {
        self.plugin
            .stt_transcribe(&self.ctx, audio, sample_rate, &fixtures::stt_options())
            .await
    }

    /// Drive `stt_transcribe_stream` with `chunks`, deterministically, and
    /// collect every event the plugin emits.
    ///
    /// The channel between the two is sized from `spec/limits.yaml`, exactly as
    /// the runner sizes it — a harness with its own capacity would be testing
    /// itself. Chunks are fed by a task so a hook that emits partials while
    /// audio flows behaves the way it does in production; the whole thing is
    /// still deterministic, because the input is fixed and finite.
    pub async fn stt_stream(
        &self,
        chunks: impl IntoIterator<Item = Vec<u8>>,
    ) -> Result<Vec<SttEvent>> {
        self.stt_stream_with(chunks, fixtures::SAMPLE_RATE, fixtures::stt_options())
            .await
    }

    /// [`stt_stream`](Self::stt_stream) with an explicit rate and options.
    pub async fn stt_stream_with(
        &self,
        chunks: impl IntoIterator<Item = Vec<u8>>,
        sample_rate: u32,
        options: SttOptions,
    ) -> Result<Vec<SttEvent>> {
        let (audio_tx, audio_rx) =
            tokio::sync::mpsc::channel::<Vec<u8>>(crate::limits::STT_AUDIO_CHANNEL_CAPACITY as usize);
        let (events_tx, mut events_rx) = tokio::sync::mpsc::channel::<SttEvent>(8);

        let chunks: Vec<Vec<u8>> = chunks.into_iter().collect();
        let feeder = tokio::spawn(async move {
            for chunk in chunks {
                if audio_tx.send(chunk).await.is_err() {
                    break;
                }
            }
        });

        let plugin = self.plugin.clone();
        let ctx = self.ctx.clone();
        let hook = tokio::spawn(async move {
            plugin
                .stt_transcribe_stream(&ctx, audio_rx, events_tx, sample_rate, options)
                .await
        });

        let mut events = Vec::new();
        while let Some(ev) = events_rx.recv().await {
            events.push(ev);
        }
        let _ = feeder.await;
        hook.await.context("stt_transcribe_stream panicked")??;
        Ok(events)
    }

    /// `stt_languages()`.
    pub async fn stt_languages(&self) -> Vec<String> {
        self.plugin.stt_languages().await
    }

    /// `stt_load_state()`.
    pub async fn stt_load_state(&self) -> Result<SttLoadState> {
        self.plugin.stt_load_state(&self.ctx).await
    }

    // ── TTS ──

    /// `tts_synthesize(..)`.
    pub async fn tts_synthesize(&self, req: TtsRequest) -> Result<AudioData> {
        self.plugin.tts_synthesize(&self.ctx, req).await
    }

    /// `tts_synthesize_stream(..)`, collected. A non-streaming provider answers
    /// here too — the SDK's default forwards to `tts_synthesize`.
    pub async fn tts_stream(&self, req: TtsRequest) -> Result<Vec<AudioChunk>> {
        let (tx, mut rx) = tokio::sync::mpsc::channel::<AudioChunk>(16);
        let plugin = self.plugin.clone();
        let ctx = self.ctx.clone();
        let hook = tokio::spawn(async move { plugin.tts_synthesize_stream(&ctx, req, tx).await });
        let mut chunks = Vec::new();
        while let Some(c) = rx.recv().await {
            chunks.push(c);
        }
        hook.await.context("tts_synthesize_stream panicked")??;
        Ok(chunks)
    }

    /// `tts_voices()`.
    pub async fn tts_voices(&self) -> Vec<crate::capability::VoiceInfo> {
        self.plugin.tts_voices().await
    }

    // ── AI ──

    /// `ai_complete(..)`, collected. The trailing `Done` the SDK appends is
    /// *not* here: this is what the hook emitted, not what the wire carried.
    pub async fn ai_complete(&self, req: AiRequest) -> Result<Vec<AiChunk>> {
        let (tx, mut rx) = tokio::sync::mpsc::channel::<AiChunk>(16);
        let plugin = self.plugin.clone();
        let ctx = self.ctx.clone();
        let hook = tokio::spawn(async move { plugin.ai_complete(&ctx, req, tx).await });
        let mut chunks = Vec::new();
        while let Some(c) = rx.recv().await {
            chunks.push(c);
        }
        hook.await.context("ai_complete panicked")??;
        Ok(chunks)
    }

    // ── lifecycle ──

    /// The daemon rewrote this plugin's settings.
    pub async fn config_changed(&self, config: impl serde::Serialize) {
        let json = serde_json::to_string(&config).expect("config must serialize");
        self.plugin.on_config_changed(&self.ctx, &json).await;
    }

    /// The daemon rewrote this plugin's settings, as raw JSON — valid or not.
    pub async fn config_changed_json(&self, json: &str) {
        self.plugin.on_config_changed(&self.ctx, json).await;
    }

    /// Deliver every payload in [`fixtures::config_fuzz`] and return the ones
    /// the plugin *accepted*, as `(payload, reason)`.
    ///
    /// The assertion this supports is that the plugin is still alive and still
    /// answering afterwards — not that it accepted any particular payload. The
    /// one payload worth asserting on is `{}`: a config type that rejects it
    /// never sees `on_config` at all on a fresh install.
    ///
    /// "Accepted" is read off the host log, because that is where the SDK
    /// reports a payload that did not fit — so a plugin that warns from inside
    /// its own `on_config` will be counted as having rejected one. Assert on
    /// the payloads you care about rather than on the length of this list.
    pub async fn fuzz_config(&self) -> Vec<(&'static str, &'static str)> {
        let warnings = |h: &Self| {
            h.logs()
                .into_iter()
                .filter(|l| l.level == "warn" || l.level == "error")
                .count()
        };
        let mut accepted = Vec::new();
        for (payload, reason) in fixtures::config_fuzz() {
            let before = warnings(self);
            self.config_changed_json(payload).await;
            if warnings(self) == before {
                accepted.push((payload, reason));
            }
        }
        accepted
    }

    /// The daemon's UI language changed. The context is updated first, exactly
    /// as the runner updates it.
    pub async fn language_changed(&self, language: &str) {
        self.ctx.set_language(language);
        self.plugin.on_language_changed(&self.ctx, language).await;
    }

    /// The set of listening trigger types changed. The context is updated
    /// *before* the hook runs — the runner's order, and the one that makes
    /// `ctx.active_triggers()` inside the hook mean anything.
    pub async fn active_triggers(&self, types: impl IntoIterator<Item = impl Into<String>>) {
        let types: Vec<String> = types.into_iter().map(Into::into).collect();
        self.ctx.active_triggers().set(types.clone());
        self.plugin.on_active_triggers(&self.ctx, types).await;
    }

    /// A daemon event, dispatched the way the runner dispatches it: the typed
    /// hook first, then the raw `on_event`.
    pub async fn event(&self, event_type: &str, payload_json: &str) {
        crate::runner::dispatch_event(
            &*self.plugin,
            &self.ctx,
            &proto::PluginEventMsg {
                event_type: event_type.to_string(),
                payload_json: payload_json.to_string(),
                ..Default::default()
            },
        )
        .await;
    }

    /// A chat firehose event — see [`fixtures::firehose_events`]. An event
    /// whose oneof is empty is skipped, as the runner skips it.
    pub async fn conversation_events(
        &self,
        events: impl IntoIterator<Item = proto::FirehoseEventMsg>,
    ) {
        for fe in events {
            if let Some(event) = fe.event {
                self.plugin
                    .on_conversation_event(&self.ctx, &fe.conversation_id, &event)
                    .await;
            }
        }
    }

    /// `health_check()`.
    pub async fn health(&self) -> (bool, String) {
        self.plugin.health_check().await
    }

    /// `on_shutdown()`.
    pub async fn shutdown(&self) {
        self.plugin.on_shutdown(&self.ctx).await;
    }
}

/// One tool's declared argument schema, and the assertions worth making on it.
#[derive(Debug, Clone)]
pub struct ToolSchema {
    tool: String,
    json: serde_json::Value,
}

impl ToolSchema {
    /// The schema as JSON.
    pub fn json(&self) -> &serde_json::Value {
        &self.json
    }

    /// The declared property names, sorted.
    pub fn properties(&self) -> Vec<String> {
        let mut names: Vec<String> = self
            .json
            .get("properties")
            .and_then(|p| p.as_object())
            .map(|o| o.keys().cloned().collect())
            .unwrap_or_default();
        names.sort();
        names
    }

    /// The declared required property names, sorted.
    pub fn required(&self) -> Vec<String> {
        let mut names: Vec<String> = self
            .json
            .get("required")
            .and_then(|r| r.as_array())
            .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
            .unwrap_or_default();
        names.sort();
        names
    }

    /// The description the model is shown for one property.
    pub fn description_of(&self, property: &str) -> Option<String> {
        self.json
            .get("properties")?
            .get(property)?
            .get("description")?
            .as_str()
            .map(String::from)
    }

    /// Every provider rejects a parameters schema that is not object-rooted,
    /// and several reject `$schema` inside one.
    pub fn assert_is_a_parameters_object(&self) {
        assert_eq!(
            self.json.get("type").and_then(|t| t.as_str()),
            Some("object"),
            "tool `{}` declares a schema whose root is not an object: {}",
            self.tool,
            self.json
        );
        assert!(
            self.json.get("$schema").is_none(),
            "tool `{}` declares `$schema` in its parameters object; several \
             providers reject that: {}",
            self.tool,
            self.json
        );
    }

    /// Assert this is the schema `T` generates.
    #[cfg(feature = "schema")]
    pub fn assert_matches<T: crate::schema::JsonSchema>(&self) {
        let expected: serde_json::Value = serde_json::from_str(&crate::schema::of::<T>())
            .expect("generated schema is JSON");
        assert_eq!(
            self.json,
            expected,
            "tool `{}` advertises a schema its handler does not parse.\n\
             declared: {}\n\
             {}:       {}",
            self.tool,
            serde_json::to_string_pretty(&self.json).unwrap_or_default(),
            std::any::type_name::<T>(),
            serde_json::to_string_pretty(&expected).unwrap_or_default(),
        );
    }
}
