//! [`RecordingHost`] — the daemon, as a value you can read afterwards.
//!
//! Every host RPC a handler makes lands in a [`Recorded`] log, and every one of
//! them can be made to fail on demand. The failure is built exactly the way the
//! real client builds it (`anyhow::Error::new(ToolError…).context("Rpc failed")`,
//! see `host_client::rpc_failed`), so a handler's `?` recovers the same
//! [`ToolError`] kind it would recover in production — which is the whole point
//! of injecting one.

use std::sync::{Arc, Mutex};

use anyhow::Result;

use crate::context::{ChatStream, Host};
use crate::error::ToolError;
use crate::proto;

/// One `FireTrigger`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FiredTrigger {
    pub trigger_type: String,
    pub payload_json: String,
}

/// One `PluginLog`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LogLine {
    /// `debug` / `info` / `warn` / `error`.
    pub level: String,
    pub message: String,
}

/// One `SetVariable`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Variable {
    pub name: String,
    pub value: String,
    /// `session` or `persistent`.
    pub scope: String,
}

/// One `PushToUi`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UiPush {
    pub event: String,
    pub payload_json: String,
}

/// One `SendChatMessage`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ChatMessage {
    pub text: String,
    pub conversation_id: String,
    pub voice_enabled: bool,
}

/// The names this module accepts for a host RPC, in the spelling
/// `spec/hooks.yaml` uses for its `permission` column.
///
/// Injection is by name, and a name with a typo in it would inject nothing at
/// all — a test that silently stops testing. Every entry point that takes one
/// checks it against this list and panics on anything else.
pub const HOST_RPCS: &[&str] = &[
    "fire_trigger",
    "log",
    "get_config",
    "get_daemon_info",
    "set_variable",
    "push_to_ui",
    "send_chat_message",
    "set_theme_contribution",
];

/// Host RPCs the SDK makes on the plugin's behalf, so there is no [`Host`]
/// method to inject a failure into — but which a [`MockDaemon`] can still
/// record and refuse.
///
/// [`MockDaemon`]: crate::testing::MockDaemon
pub(crate) const SDK_HOST_RPCS: &[&str] = &["subscribe_events"];

/// Panic unless `rpc` is a [`Host`] method — what a level-1 failure can be
/// injected into.
pub(crate) fn check_rpc(rpc: &str) {
    if SDK_HOST_RPCS.contains(&rpc) {
        panic!(
            "`{rpc}` is made by the SDK, not by a handler, so there is no \
             `Host` method to fail. Revoke it on a MockDaemon instead."
        );
    }
    assert!(
        HOST_RPCS.contains(&rpc),
        "`{rpc}` is not a host RPC. One of: {}",
        HOST_RPCS.join(", ")
    );
}

/// Panic unless `rpc` is a host RPC of either kind.
pub(crate) fn check_any_rpc(rpc: &str) {
    assert!(
        HOST_RPCS.contains(&rpc) || SDK_HOST_RPCS.contains(&rpc),
        "`{rpc}` is not a host RPC. One of: {}, {}",
        HOST_RPCS.join(", "),
        SDK_HOST_RPCS.join(", "),
    );
}

/// Everything a plugin said to the daemon, in order.
///
/// Cheap to clone — clones share one log, so a [`RecordingHost`] and the
/// harness holding it read the same thing. The same type also backs
/// [`MockDaemon`](crate::testing::MockDaemon), so an assertion written against
/// the in-process harness reads identically against the wire one.
#[derive(Clone, Default)]
pub struct Recorded {
    inner: Arc<Mutex<Inner>>,
}

#[derive(Default)]
struct Inner {
    calls: Vec<String>,
    unauthenticated: Vec<String>,
    triggers: Vec<FiredTrigger>,
    logs: Vec<LogLine>,
    variables: Vec<Variable>,
    ui_pushes: Vec<UiPush>,
    chats: Vec<ChatMessage>,
    themes: Vec<proto::PluginThemeContribution>,
}

impl Recorded {
    /// An empty log.
    pub fn new() -> Self {
        Self::default()
    }

    fn with<T>(&self, f: impl FnOnce(&mut Inner) -> T) -> T {
        // A poisoned lock means some other test task panicked while recording.
        // The recorded facts are still the facts.
        f(&mut self.inner.lock().unwrap_or_else(|e| e.into_inner()))
    }

    /// Every host RPC name, in call order — including the ones that failed.
    pub fn calls(&self) -> Vec<String> {
        self.with(|i| i.calls.clone())
    }

    /// How many times `rpc` was called. Panics on a name that is not a host RPC.
    pub fn call_count(&self, rpc: &str) -> usize {
        check_any_rpc(rpc);
        self.with(|i| i.calls.iter().filter(|c| *c == rpc).count())
    }

    /// Every host RPC that arrived **without** a valid session token, in order.
    ///
    /// Empty is the only acceptable answer from a plugin that is talking to a
    /// daemon at all. Before 0.6 no SDK sent `x-session-token` in any language,
    /// so every `fire_trigger`, `log`, `get_config`, `set_variable` and
    /// `push_to_ui` came back `UNAUTHENTICATED` while the plugin's own tools
    /// answered normally and every unit test passed — the protocol was
    /// unusable and nothing said so. Only a server that checks the header can
    /// notice, which is why this list lives on the mock daemon and is what
    /// `astra-plugin test` asserts on.
    ///
    /// Filled by [`MockDaemon`](crate::testing::MockDaemon) only; the level-1
    /// [`RecordingHost`] has no headers to check.
    pub fn unauthenticated_calls(&self) -> Vec<String> {
        self.with(|i| i.unauthenticated.clone())
    }

    /// Every `FireTrigger`, in order.
    pub fn fired_triggers(&self) -> Vec<FiredTrigger> {
        self.with(|i| i.triggers.clone())
    }

    /// Every `PluginLog`, in order.
    pub fn logs(&self) -> Vec<LogLine> {
        self.with(|i| i.logs.clone())
    }

    /// Every `SetVariable`, in order.
    pub fn variables(&self) -> Vec<Variable> {
        self.with(|i| i.variables.clone())
    }

    /// Every `PushToUi`, in order.
    pub fn ui_pushes(&self) -> Vec<UiPush> {
        self.with(|i| i.ui_pushes.clone())
    }

    /// Every `SendChatMessage`, in order.
    pub fn chat_messages(&self) -> Vec<ChatMessage> {
        self.with(|i| i.chats.clone())
    }

    /// Every `SetThemeContribution`, in order.
    pub fn theme_contributions(&self) -> Vec<proto::PluginThemeContribution> {
        self.with(|i| i.themes.clone())
    }

    /// The last value the plugin published for `name`, if any.
    pub fn variable(&self, name: &str) -> Option<String> {
        self.with(|i| {
            i.variables
                .iter()
                .rev()
                .find(|v| v.name == name)
                .map(|v| v.value.clone())
        })
    }

    /// Forget everything. For a test that stages, asserts, then stages again.
    pub fn clear(&self) {
        self.with(|i| *i = Inner::default());
    }

    // ── recording, called by RecordingHost and MockDaemon ──

    pub(crate) fn note(&self, rpc: &str) {
        self.with(|i| i.calls.push(rpc.to_string()));
    }
    pub(crate) fn note_unauthenticated(&self, rpc: &str) {
        self.with(|i| i.unauthenticated.push(rpc.to_string()));
    }
    pub(crate) fn trigger(&self, t: FiredTrigger) {
        self.with(|i| i.triggers.push(t));
    }
    pub(crate) fn log_line(&self, l: LogLine) {
        self.with(|i| i.logs.push(l));
    }
    pub(crate) fn variable_set(&self, v: Variable) {
        self.with(|i| i.variables.push(v));
    }
    pub(crate) fn ui_push(&self, p: UiPush) {
        self.with(|i| i.ui_pushes.push(p));
    }
    pub(crate) fn chat(&self, c: ChatMessage) {
        self.with(|i| i.chats.push(c));
    }
    pub(crate) fn theme(&self, t: proto::PluginThemeContribution) {
        self.with(|i| i.themes.push(t));
    }
}

impl std::fmt::Debug for Recorded {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.with(|i| {
            f.debug_struct("Recorded")
                .field("calls", &i.calls)
                .field("triggers", &i.triggers)
                .field("logs", &i.logs)
                .field("variables", &i.variables)
                .finish_non_exhaustive()
        })
    }
}

/// A staged failure: which RPC, what it fails with, and how many times.
#[derive(Clone, Debug)]
struct Injection {
    rpc: String,
    error: ToolError,
    /// `None` = every call from now on.
    remaining: Option<usize>,
}

/// The [`Host`] a level-1 test runs against: records everything, fails on
/// request, and needs no daemon, no socket and no Astra installed.
///
/// ```no_run
/// # use astra_plugin_sdk::testing::RecordingHost;
/// let host = RecordingHost::new("dice-roller");
/// // …hand `host.clone()` to a PluginContext, run a handler, then:
/// assert_eq!(host.fired_triggers().len(), 3);
/// ```
pub struct RecordingHost {
    plugin_id: String,
    recorded: Recorded,
    injections: Mutex<Vec<Injection>>,
    chat_reply: Mutex<Vec<String>>,
    config_json: Mutex<String>,
    daemon_info: Mutex<proto::PluginDaemonInfoResponse>,
}

impl RecordingHost {
    /// A host that answers everything with `Ok` and remembers it.
    pub fn new(plugin_id: impl Into<String>) -> Arc<Self> {
        Arc::new(Self {
            plugin_id: plugin_id.into(),
            recorded: Recorded::new(),
            injections: Mutex::new(Vec::new()),
            chat_reply: Mutex::new(Vec::new()),
            config_json: Mutex::new("{}".to_string()),
            daemon_info: Mutex::new(proto::PluginDaemonInfoResponse::default()),
        })
    }

    /// The log. Cloning it is cheap and shares the same storage.
    pub fn recorded(&self) -> Recorded {
        self.recorded.clone()
    }

    /// Every `FireTrigger`, in order.
    pub fn fired_triggers(&self) -> Vec<FiredTrigger> {
        self.recorded.fired_triggers()
    }
    /// Every `PluginLog`, in order.
    pub fn logs(&self) -> Vec<LogLine> {
        self.recorded.logs()
    }
    /// Every `SetVariable`, in order.
    pub fn variables(&self) -> Vec<Variable> {
        self.recorded.variables()
    }
    /// Every `PushToUi`, in order.
    pub fn ui_pushes(&self) -> Vec<UiPush> {
        self.recorded.ui_pushes()
    }
    /// Every `SendChatMessage`, in order.
    pub fn chat_messages(&self) -> Vec<ChatMessage> {
        self.recorded.chat_messages()
    }
    /// The last value published for `name`.
    pub fn variable(&self, name: &str) -> Option<String> {
        self.recorded.variable(name)
    }

    /// What `get_config()` answers. The typed path is
    /// [`Harness::with_config`](crate::testing::Harness::with_config); this is
    /// for a plugin that re-reads its settings from a background task.
    pub fn set_config_json(&self, json: impl Into<String>) {
        *self.config_json.lock().unwrap_or_else(|e| e.into_inner()) = json.into();
    }

    /// What `get_daemon_info()` answers.
    pub fn set_daemon_info(&self, info: proto::PluginDaemonInfoResponse) {
        *self.daemon_info.lock().unwrap_or_else(|e| e.into_inner()) = info;
    }

    /// What `send_chat_message()` streams back, one chunk per string.
    pub fn set_chat_reply(&self, chunks: impl IntoIterator<Item = impl Into<String>>) {
        *self.chat_reply.lock().unwrap_or_else(|e| e.into_inner()) =
            chunks.into_iter().map(Into::into).collect();
    }

    // ── failure injection ──

    /// Fail every `rpc` from now on with `error`.
    ///
    /// Panics unless `rpc` is one of [`HOST_RPCS`] — an injection nobody can
    /// trigger is a test that quietly stopped testing.
    pub fn fail(&self, rpc: &str, error: ToolError) {
        check_rpc(rpc);
        self.injections
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push(Injection {
                rpc: rpc.to_string(),
                error,
                remaining: None,
            });
    }

    /// Fail the next `n` calls to `rpc`, then answer normally.
    pub fn fail_times(&self, rpc: &str, n: usize, error: ToolError) {
        check_rpc(rpc);
        self.injections
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push(Injection {
                rpc: rpc.to_string(),
                error,
                remaining: Some(n),
            });
    }

    /// Fail the next call to `rpc`.
    pub fn fail_next(&self, rpc: &str, error: ToolError) {
        self.fail_times(rpc, 1, error);
    }

    /// Answer `rpc` the way the daemon answers an rpc this plugin's
    /// `[permissions]` do not grant: `UNAUTHORIZED`, every time.
    ///
    /// Default-deny is the first failure most authors meet, and the one whose
    /// handling is worth a test — a plugin that declares `tools` and calls
    /// `fire_trigger` is denied on the user's machine and nowhere else.
    pub fn deny(&self, rpc: &str) {
        check_rpc(rpc);
        let id = &self.plugin_id;
        self.fail(
            rpc,
            ToolError::Unauthorized(format!("plugin '{id}' has no `{rpc}` grant")),
        );
    }

    /// Drop every staged failure.
    pub fn clear_failures(&self) {
        self.injections
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clear();
    }

    /// The error this call should fail with, if one is staged.
    ///
    /// Built the way `host_client::rpc_failed` builds it: a `ToolError` under a
    /// `"<Rpc> failed"` context, so a handler's `?` recovers the kind.
    fn staged(&self, rpc: &str, wire_name: &str) -> Option<anyhow::Error> {
        let mut injections = self.injections.lock().unwrap_or_else(|e| e.into_inner());
        let idx = injections.iter().position(|i| i.rpc == rpc)?;
        let error = injections[idx].error.clone();
        if let Some(n) = injections[idx].remaining.as_mut() {
            *n -= 1;
            if *n == 0 {
                injections.remove(idx);
            }
        }
        Some(anyhow::Error::new(error).context(format!("{wire_name} failed")))
    }
}

#[async_trait::async_trait]
impl Host for RecordingHost {
    fn plugin_id(&self) -> &str {
        &self.plugin_id
    }

    async fn fire_trigger(&self, trigger_type: &str, payload_json: &str) -> Result<()> {
        self.recorded.note("fire_trigger");
        if let Some(e) = self.staged("fire_trigger", "FireTrigger") {
            return Err(e);
        }
        self.recorded.trigger(FiredTrigger {
            trigger_type: trigger_type.to_string(),
            payload_json: payload_json.to_string(),
        });
        Ok(())
    }

    async fn log(&self, level: &str, message: &str) -> Result<()> {
        self.recorded.note("log");
        if let Some(e) = self.staged("log", "PluginLog") {
            return Err(e);
        }
        self.recorded.log_line(LogLine {
            level: level.to_string(),
            message: message.to_string(),
        });
        Ok(())
    }

    async fn get_config(&self) -> Result<String> {
        self.recorded.note("get_config");
        if let Some(e) = self.staged("get_config", "GetPluginSelfConfig") {
            return Err(e);
        }
        Ok(self
            .config_json
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone())
    }

    async fn get_daemon_info(&self) -> Result<proto::PluginDaemonInfoResponse> {
        self.recorded.note("get_daemon_info");
        if let Some(e) = self.staged("get_daemon_info", "GetDaemonInfo") {
            return Err(e);
        }
        Ok(self
            .daemon_info
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone())
    }

    async fn set_variable(&self, name: &str, value: &str, scope: &str) -> Result<()> {
        self.recorded.note("set_variable");
        if let Some(e) = self.staged("set_variable", "SetVariable") {
            return Err(e);
        }
        self.recorded.variable_set(Variable {
            name: name.to_string(),
            value: value.to_string(),
            scope: scope.to_string(),
        });
        Ok(())
    }

    async fn push_to_ui(&self, event: &str, payload_json: &str) -> Result<()> {
        self.recorded.note("push_to_ui");
        if let Some(e) = self.staged("push_to_ui", "PushToUi") {
            return Err(e);
        }
        self.recorded.ui_push(UiPush {
            event: event.to_string(),
            payload_json: payload_json.to_string(),
        });
        Ok(())
    }

    async fn send_chat_message(
        &self,
        text: &str,
        conversation_id: &str,
        voice_enabled: bool,
    ) -> Result<ChatStream> {
        self.recorded.note("send_chat_message");
        if let Some(e) = self.staged("send_chat_message", "SendChatMessage") {
            return Err(e);
        }
        self.recorded.chat(ChatMessage {
            text: text.to_string(),
            conversation_id: conversation_id.to_string(),
            voice_enabled,
        });
        let chunks: Vec<_> = self
            .chat_reply
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .iter()
            .map(|c| {
                Ok(proto::PluginChatChunk {
                    content: Some(proto::plugin_chat_chunk::Content::Text(c.clone())),
                    ..Default::default()
                })
            })
            .collect();
        Ok(Box::pin(tokio_stream::iter(chunks)))
    }

    async fn set_theme_contribution(&self, theme: proto::PluginThemeContribution) -> Result<()> {
        self.recorded.note("set_theme_contribution");
        if let Some(e) = self.staged("set_theme_contribution", "SetThemeContribution") {
            return Err(e);
        }
        self.recorded.theme(theme);
        Ok(())
    }
}
