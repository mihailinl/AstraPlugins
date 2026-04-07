//! The PluginCapability trait — implement this to define your plugin's behavior.

use crate::proto;

// ── Convenience types ──

/// A tool definition exposed to the AI.
#[derive(Debug, Clone)]
pub struct ToolDef {
    pub name: String,
    pub description: String,
    /// JSON Schema for parameters.
    pub parameters_json: String,
}

impl From<ToolDef> for proto::PluginToolDef {
    fn from(t: ToolDef) -> Self {
        Self {
            name: t.name,
            description: t.description,
            parameters_json: t.parameters_json,
        }
    }
}

/// Result of a tool call.
#[derive(Debug, Clone)]
pub struct ToolResult {
    pub success: bool,
    pub result: String,
    pub error: String,
}

impl ToolResult {
    pub fn ok(result: impl Into<String>) -> Self {
        Self {
            success: true,
            result: result.into(),
            error: String::new(),
        }
    }

    pub fn err(error: impl Into<String>) -> Self {
        Self {
            success: false,
            result: String::new(),
            error: error.into(),
        }
    }
}

impl From<ToolResult> for proto::PluginCallToolResponse {
    fn from(r: ToolResult) -> Self {
        Self {
            success: r.success,
            result: r.result,
            error: r.error,
        }
    }
}

/// A TTS voice provided by the plugin.
#[derive(Debug, Clone)]
pub struct VoiceInfo {
    pub id: String,
    pub name: String,
    pub language: String,
    pub gender: String,
    pub preview_url: String,
}

impl From<VoiceInfo> for proto::PluginVoiceInfo {
    fn from(v: VoiceInfo) -> Self {
        Self {
            id: v.id,
            name: v.name,
            language: v.language,
            gender: v.gender,
            preview_url: v.preview_url,
        }
    }
}

/// Synthesized audio data.
#[derive(Debug, Clone)]
pub struct AudioData {
    pub data: Vec<u8>,
    pub format: String,
    pub sample_rate: u32,
    pub duration_ms: u32,
}

impl From<AudioData> for proto::PluginTtsSynthesizeResponse {
    fn from(a: AudioData) -> Self {
        Self {
            audio_data: a.data,
            format: a.format,
            sample_rate: a.sample_rate,
            duration_ms: a.duration_ms,
        }
    }
}

/// An AI model provided by the plugin.
#[derive(Debug, Clone)]
pub struct AiModelInfo {
    pub id: String,
    pub name: String,
}

impl From<AiModelInfo> for proto::PluginAiModelInfo {
    fn from(m: AiModelInfo) -> Self {
        Self {
            id: m.id,
            name: m.name,
        }
    }
}

/// Result of executing an action.
#[derive(Debug, Clone)]
pub struct ActionResult {
    pub success: bool,
    pub result: String,
    pub error: String,
}

impl ActionResult {
    pub fn ok(result: impl Into<String>) -> Self {
        Self {
            success: true,
            result: result.into(),
            error: String::new(),
        }
    }

    pub fn err(error: impl Into<String>) -> Self {
        Self {
            success: false,
            result: String::new(),
            error: error.into(),
        }
    }
}

impl From<ActionResult> for proto::PluginExecuteActionResponse {
    fn from(r: ActionResult) -> Self {
        Self {
            success: r.success,
            result: r.result,
            error: r.error,
        }
    }
}

/// A field definition for action/trigger type configuration.
pub use proto::FieldDefinitionMsg as FieldDef;
pub use proto::DropdownOptionMsg as DropdownOption;
pub use proto::FieldVisibilityCondition as FieldCondition;
pub use proto::ActionTypeDefinitionMsg as ActionTypeDef;
pub use proto::TriggerTypeDefinitionMsg as TriggerTypeDef;
pub use proto::PluginUiPanel as UiPanel;

// ── FieldDef builder methods ──

impl proto::FieldDefinitionMsg {
    /// Create a text field.
    pub fn text(id: impl Into<String>, label: impl Into<String>) -> Self {
        Self { id: id.into(), label: label.into(), field_type: "text".into(), ..Default::default() }
    }
    /// Create a textarea field.
    pub fn textarea(id: impl Into<String>, label: impl Into<String>) -> Self {
        Self { id: id.into(), label: label.into(), field_type: "textarea".into(), ..Default::default() }
    }
    /// Create a textarea with variable support.
    pub fn textarea_with_variables(id: impl Into<String>, label: impl Into<String>) -> Self {
        Self { id: id.into(), label: label.into(), field_type: "textarea_with_variables".into(), ..Default::default() }
    }
    /// Create a dropdown field from `(value, label)` pairs.
    pub fn dropdown(id: impl Into<String>, label: impl Into<String>, options: &[(&str, &str)]) -> Self {
        Self {
            id: id.into(), label: label.into(), field_type: "dropdown".into(),
            options: options.iter().map(|(v, l)| proto::DropdownOptionMsg {
                value: (*v).into(), label: (*l).into(),
            }).collect(),
            ..Default::default()
        }
    }
    /// Create a number field.
    pub fn number(id: impl Into<String>, label: impl Into<String>) -> Self {
        Self { id: id.into(), label: label.into(), field_type: "number".into(), ..Default::default() }
    }
    /// Create a toggle (boolean) field.
    pub fn toggle(id: impl Into<String>, label: impl Into<String>) -> Self {
        Self { id: id.into(), label: label.into(), field_type: "toggle".into(), ..Default::default() }
    }
    /// Create a hotkey recorder field.
    pub fn hotkey(id: impl Into<String>, label: impl Into<String>) -> Self {
        Self { id: id.into(), label: label.into(), field_type: "hotkey_recorder".into(), ..Default::default() }
    }
    /// Create a file picker field.
    pub fn file_picker(id: impl Into<String>, label: impl Into<String>) -> Self {
        Self { id: id.into(), label: label.into(), field_type: "file_picker".into(), ..Default::default() }
    }

    // Chainable setters

    /// Set placeholder text.
    pub fn with_placeholder(mut self, p: impl Into<String>) -> Self { self.placeholder = p.into(); self }
    /// Set default value.
    pub fn with_default(mut self, v: impl Into<String>) -> Self { self.default_value = v.into(); self }
    /// Set description text.
    pub fn with_description(mut self, d: impl Into<String>) -> Self { self.description = d.into(); self }
    /// Set minimum value (for number fields).
    pub fn with_min(mut self, v: f64) -> Self { self.min = v; self.has_min = true; self }
    /// Set maximum value (for number fields).
    pub fn with_max(mut self, v: f64) -> Self { self.max = v; self.has_max = true; self }
    /// Set step value (for number fields).
    pub fn with_step(mut self, v: f64) -> Self { self.step = v; self.has_step = true; self }
    /// Set group for collapsible sections.
    pub fn with_group(mut self, id: impl Into<String>, label: impl Into<String>) -> Self {
        self.group = id.into(); self.group_label = label.into(); self
    }
    /// Add a visibility condition.
    pub fn with_condition(mut self, field_id: &str, operator: &str, value: &str) -> Self {
        self.conditions.push(proto::FieldVisibilityCondition {
            field_id: field_id.into(), operator: operator.into(), value: value.into(),
        });
        self
    }
}

/// Thread-safe set of active trigger types. Updated automatically by the SDK
/// when the daemon sends `OnActiveTriggers`. Plugins can check
/// `active_triggers.contains("on_time")` before firing.
#[derive(Debug, Clone, Default)]
pub struct ActiveTriggers {
    inner: std::sync::Arc<tokio::sync::RwLock<std::collections::HashSet<String>>>,
}

impl ActiveTriggers {
    pub fn new() -> Self {
        Self::default()
    }

    /// Check if a trigger type currently has commands listening.
    pub async fn contains(&self, trigger_type: &str) -> bool {
        self.inner.read().await.contains(trigger_type)
    }

    /// Replace the active set (called by SDK on `OnActiveTriggers`).
    pub async fn update(&self, types: Vec<String>) {
        *self.inner.write().await = types.into_iter().collect();
    }
}

// ── The main trait ──

/// Implement this trait to define your plugin's capabilities.
///
/// All methods have default no-op implementations, so you only need to override
/// the ones matching the capabilities declared in your `plugin.toml`.
#[async_trait::async_trait]
pub trait PluginCapability: Send + Sync + 'static {
    // ── Tools ──

    /// Return the list of tools this plugin provides.
    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![]
    }

    /// Execute a tool call.
    async fn call_tool(&self, _name: &str, _arguments_json: &str) -> ToolResult {
        ToolResult::err("Not implemented")
    }

    // ── TTS ──

    /// Synthesize text to audio (non-streaming).
    async fn tts_synthesize(
        &self,
        _text: &str,
        _voice_id: &str,
        _speed: f32,
        _pitch: f32,
    ) -> anyhow::Result<AudioData> {
        anyhow::bail!("TTS not implemented")
    }

    /// List available TTS voices.
    async fn tts_voices(&self) -> Vec<VoiceInfo> {
        vec![]
    }

    // ── STT ──

    /// Get supported STT languages.
    async fn stt_languages(&self) -> Vec<String> {
        vec![]
    }

    // ── AI Provider ──

    /// Get available AI models.
    async fn ai_models(&self) -> (Vec<AiModelInfo>, String) {
        (vec![], String::new())
    }

    // ── Actions ──

    /// Return action type definitions this plugin provides.
    async fn action_types(&self) -> Vec<ActionTypeDef> {
        vec![]
    }

    /// Execute an action.
    async fn execute_action(
        &self,
        _action_type: &str,
        _params_json: &str,
    ) -> ActionResult {
        ActionResult::err("Not implemented")
    }

    // ── Triggers ──

    /// Return trigger type definitions this plugin provides.
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![]
    }

    // ── UI ──

    /// Return UI panel definitions.
    async fn ui_panels(&self) -> Vec<UiPanel> {
        vec![]
    }

    // ── Events ──

    /// Return event types this plugin wants to subscribe to.
    /// Return empty vec (default) if no event subscription is needed.
    ///
    /// Available event types: "chat_message_sync", "speech_recognized",
    /// "command_triggered", "command_completed", "settings_changed",
    /// "state_changed", "tts_started", "tts_completed", etc.
    fn subscribed_events(&self) -> Vec<String> {
        vec![]
    }

    /// Called when a subscribed event arrives from the daemon.
    ///
    /// `event_type` is the event tag (e.g. "chat_message_sync").
    /// `payload_json` is the full event serialized as JSON.
    async fn on_event(&self, _event_type: &str, _payload_json: &str) {}

    // ── Lifecycle ──

    /// Called after registration with a reference to the host client.
    /// Override this to store the host reference for calling daemon APIs
    /// (fire_trigger, set_variable, log, etc.) from within your plugin.
    async fn set_host(&self, _host: std::sync::Arc<tokio::sync::Mutex<crate::HostClient>>) {}

    /// Called when the plugin's config changes.
    async fn on_config_changed(&self, _config_json: &str) {}

    /// Called when the set of active trigger types changes.
    /// `active_types` contains the un-namespaced trigger types that have
    /// at least one command listening. If a type is NOT in this list,
    /// the plugin should skip firing it (nobody's listening).
    async fn on_active_triggers(&self, _active_types: Vec<String>) {}

    /// Called when the daemon requests shutdown.
    async fn on_shutdown(&self) {}

    /// Health check — return true if healthy.
    async fn health_check(&self) -> (bool, String) {
        (true, "ok".into())
    }
}
