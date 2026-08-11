//! The `PluginCapability` trait — implement this to define your plugin's behavior.
//!
//! Every method has a default, so a plugin implements only the hooks its
//! declared `[capabilities]` need. The one thing that is *not* defaulted is
//! [`PluginCapability::Config`]: see [`NoConfig`] for why, and for the one line
//! that satisfies it.

use std::sync::Arc;

use arc_swap::ArcSwap;
use serde::de::DeserializeOwned;

use crate::context::PluginContext;
use crate::error::{ToolError, unimplemented};
use crate::proto;

// ── Convenience types ──

/// A tool definition exposed to the AI.
#[derive(Debug, Clone)]
pub struct ToolDef {
    pub name: String,
    pub description: String,
    /// JSON Schema for parameters. Must have an object root.
    pub parameters_json: String,
}

impl ToolDef {
    /// A tool taking no arguments.
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            parameters_json: r#"{"type":"object","properties":{}}"#.into(),
        }
    }

    /// Attach the JSON Schema for this tool's arguments.
    pub fn with_schema(mut self, schema_json: impl Into<String>) -> Self {
        self.parameters_json = schema_json.into();
        self
    }
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

impl From<proto::PluginToolDef> for ToolDef {
    fn from(t: proto::PluginToolDef) -> Self {
        Self {
            name: t.name,
            description: t.description,
            parameters_json: t.parameters_json,
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

impl VoiceInfo {
    /// A voice with the fields the picker needs and nothing else.
    pub fn new(id: impl Into<String>, name: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
            language: "any".into(),
            gender: "neutral".into(),
            preview_url: String::new(),
        }
    }

    /// BCP-47-ish language tag, or `"any"`.
    pub fn with_language(mut self, language: impl Into<String>) -> Self {
        self.language = language.into();
        self
    }

    /// `"male"` / `"female"` / `"neutral"`.
    pub fn with_gender(mut self, gender: impl Into<String>) -> Self {
        self.gender = gender.into();
        self
    }

    /// URL of a sample the Voice page can play.
    pub fn with_preview_url(mut self, url: impl Into<String>) -> Self {
        self.preview_url = url.into();
        self
    }
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

/// One synthesis request.
#[derive(Debug, Clone, Default)]
pub struct TtsRequest {
    pub text: String,
    pub voice_id: String,
    /// 1.0 = normal.
    pub speed: f32,
    /// 1.0 = normal.
    pub pitch: f32,
}

impl From<proto::PluginTtsSynthesizeRequest> for TtsRequest {
    fn from(r: proto::PluginTtsSynthesizeRequest) -> Self {
        Self {
            text: r.text,
            voice_id: r.voice_id,
            speed: r.speed,
            pitch: r.pitch,
        }
    }
}

/// Synthesized audio data.
#[derive(Debug, Clone)]
pub struct AudioData {
    pub data: Vec<u8>,
    /// `"mp3"`, `"wav"`, `"pcm"` or `"ogg"`.
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

/// One chunk on the streaming-TTS path.
///
/// The daemon plays chunks as they arrive, which is the entire point: the
/// listener hears the first syllable while the rest is still being synthesized.
#[derive(Debug, Clone)]
pub struct AudioChunk {
    pub data: Vec<u8>,
    pub sample_rate: u32,
    /// Set on the last chunk. The daemon stops reading after it.
    pub is_last: bool,
}

impl AudioChunk {
    /// A chunk that is not the last one.
    pub fn new(data: Vec<u8>, sample_rate: u32) -> Self {
        Self {
            data,
            sample_rate,
            is_last: false,
        }
    }

    /// Mark this chunk as the last.
    pub fn last(mut self) -> Self {
        self.is_last = true;
        self
    }
}

impl From<AudioChunk> for proto::PluginAudioChunk {
    fn from(c: AudioChunk) -> Self {
        Self {
            data: c.data,
            is_last: c.is_last,
            sample_rate: c.sample_rate,
            options: None,
        }
    }
}

/// Per-utterance STT decoding options, carried on the first audio chunk.
///
/// A plugin ignores fields it has no notion of. `language` is `""` for
/// auto-detect; `initial_prompt` is decoding bias — the daemon puts the
/// configured wake-word spellings there, which measurably changes what a
/// Whisper-class model hears.
pub use proto::SttTranscribeOptions as SttOptions;

/// A speech-recognition result emitted on the `SttProcess` stream.
///
/// A non-streaming [`PluginCapability::stt_transcribe`] returns exactly one,
/// normally built with [`SttEvent::transcript`].
#[derive(Debug, Clone)]
pub struct SttEvent {
    pub text: String,
    /// `true` for a complete transcription, `false` for an interim result.
    pub is_final: bool,
    /// Recognition confidence in `0.0..=1.0`.
    pub confidence: f32,
    /// Detected language code (e.g. `"en"`), or empty if unknown.
    pub language: String,
}

impl SttEvent {
    /// A complete transcription — `is_final = true`, `confidence = 1.0`.
    pub fn transcript(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            is_final: true,
            confidence: 1.0,
            language: String::new(),
        }
    }

    /// An interim/partial result — `is_final = false`, `confidence = 1.0`.
    pub fn partial(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            is_final: false,
            confidence: 1.0,
            language: String::new(),
        }
    }

    /// Set the recognition confidence (`0.0..=1.0`).
    pub fn with_confidence(mut self, confidence: f32) -> Self {
        self.confidence = confidence;
        self
    }

    /// Set the detected language code.
    pub fn with_language(mut self, language: impl Into<String>) -> Self {
        self.language = language.into();
        self
    }
}

impl From<SttEvent> for proto::PluginSttEvent {
    fn from(e: SttEvent) -> Self {
        Self {
            text: e.text,
            is_final: e.is_final,
            confidence: e.confidence,
            language: e.language,
        }
    }
}

/// What [`PluginCapability::stt_load`] was asked to load.
///
/// The daemon owns the model catalog and the download manager, so it resolves
/// the concrete file and passes an absolute path; a plugin that manages its own
/// models ignores `model_path`.
#[derive(Debug, Clone, Default)]
pub struct SttLoadRequest {
    /// Daemon-resolved absolute path, or `""` for the provider's default.
    pub model_path: String,
    /// `false` means CPU-only — this is how the daemon retries after a GPU
    /// failure, so honouring it is not optional.
    pub use_gpu: bool,
}

impl From<proto::SttLoadRequest> for SttLoadRequest {
    fn from(r: proto::SttLoadRequest) -> Self {
        Self {
            model_path: r.model_path,
            use_gpu: r.use_gpu,
        }
    }
}

/// Where the recognizer's model is, so the daemon can drive idle-unload.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub enum SttLoadState {
    /// No local model — nothing to load or unload. The fail-safe answer, and
    /// what an absent hook means.
    #[default]
    NotNeeded,
    Unloaded,
    Loading,
    Ready,
    /// Load failed; the string is the human-readable cause.
    Failed(String),
}

impl From<SttLoadState> for proto::SttLoadStateResponse {
    fn from(s: SttLoadState) -> Self {
        use proto::stt_load_state_response::State;
        let (state, detail) = match s {
            SttLoadState::NotNeeded => (State::NotNeeded, String::new()),
            SttLoadState::Unloaded => (State::Unloaded, String::new()),
            SttLoadState::Loading => (State::Loading, String::new()),
            SttLoadState::Ready => (State::Ready, String::new()),
            SttLoadState::Failed(detail) => (State::Failed, detail),
        };
        Self {
            state: state as i32,
            detail,
        }
    }
}

/// An AI model provided by the plugin.
#[derive(Debug, Clone)]
pub struct AiModelInfo {
    pub id: String,
    pub name: String,
}

impl AiModelInfo {
    pub fn new(id: impl Into<String>, name: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
        }
    }
}

impl From<AiModelInfo> for proto::PluginAiModelInfo {
    fn from(m: AiModelInfo) -> Self {
        Self {
            id: m.id,
            name: m.name,
        }
    }
}

/// One completion request, exactly as the daemon's AI loop issues it.
///
/// `reasoning_effort` is `""` (unspecified) / `"auto"` / `"off"` / `"low"` /
/// `"medium"` / `"high"` / `"max"`, and `show_reasoning` says whether the user
/// wants to see the thinking. Both were on the wire and reachable by no SDK
/// before 0.6, which is why every plugin AI provider ignored the user's
/// reasoning setting.
pub use proto::PluginAiCompleteRequest as AiRequest;
/// One message in an [`AiRequest`].
pub use proto::PluginAiMessage as AiMessage;
/// A tool call, in a request (as history) or in a response (as an answer).
pub use proto::PluginAiToolCall as AiToolCall;

/// One piece of a streamed completion.
#[derive(Debug, Clone)]
pub enum AiChunk {
    /// Visible output.
    Text(String),
    /// Reasoning, shown only when [`AiRequest::show_reasoning`] was set.
    Thinking(String),
    /// The model wants a tool run.
    ToolCall(AiToolCall),
    /// The turn is over. The SDK sends one automatically when the hook returns
    /// `Ok`, so a plugin never has to remember to.
    Done,
}

impl AiChunk {
    /// Visible output.
    pub fn text(s: impl Into<String>) -> Self {
        Self::Text(s.into())
    }
    /// Reasoning.
    pub fn thinking(s: impl Into<String>) -> Self {
        Self::Thinking(s.into())
    }
}

impl From<AiChunk> for proto::PluginAiStreamChunk {
    fn from(c: AiChunk) -> Self {
        use proto::plugin_ai_stream_chunk::Content;
        Self {
            content: Some(match c {
                AiChunk::Text(t) => Content::TextDelta(t),
                AiChunk::Thinking(t) => Content::ThinkingDelta(t),
                AiChunk::ToolCall(tc) => Content::ToolCall(tc),
                AiChunk::Done => Content::Done(true),
            }),
            // Set only on the error variant, which the SDK builds itself in
            // `runner.rs` — a plugin cannot emit an `AiChunk::Error`, because a
            // hook that failed should `return Err` and let the SDK decide
            // whether that is still a status or already a stream chunk.
            error_detail: None,
        }
    }
}

/// A field definition for action/trigger type configuration.
pub use proto::FieldDefinitionMsg as FieldDef;
pub use proto::DropdownOptionMsg as DropdownOption;
pub use proto::FieldVisibilityCondition as FieldCondition;
pub use proto::ActionTypeDefinitionMsg as ActionTypeDef;
pub use proto::TriggerTypeDefinitionMsg as TriggerTypeDef;
pub use proto::PluginUiContribution as UiContribution;
/// Colours, wallpaper and shader a plugin contributes to the active theme.
pub use proto::PluginThemeContribution as ThemeContribution;

// ── UiContribution builder methods ──

impl proto::PluginUiContribution {
    /// Create a custom page contribution (shows as a nav tab).
    pub fn page(id: impl Into<String>, label: impl Into<String>, url: impl Into<String>) -> Self {
        Self { id: id.into(), slot: "page.custom".into(), label: label.into(), url: url.into(), pointer_events: true, ..Default::default() }
    }
    /// Create a named slot contribution.
    pub fn slot(slot: impl Into<String>, url: impl Into<String>) -> Self {
        Self { slot: slot.into(), url: url.into(), pointer_events: true, ..Default::default() }
    }
    /// Create a background effect contribution (fullscreen, transparent, no pointer events).
    pub fn effect(url: impl Into<String>) -> Self {
        Self { slot: "background.behind".into(), url: url.into(), transparent: true, pointer_events: false, ..Default::default() }
    }
    /// Create a CSS selector injection contribution.
    pub fn inject(css_target: impl Into<String>, position: impl Into<String>, url: impl Into<String>) -> Self {
        Self { css_target: css_target.into(), position: position.into(), url: url.into(), pointer_events: true, ..Default::default() }
    }
    /// Create a floating overlay contribution.
    pub fn overlay(id: impl Into<String>, url: impl Into<String>) -> Self {
        Self { id: id.into(), slot: "overlay.floating".into(), url: url.into(), transparent: true, pointer_events: true, ..Default::default() }
    }
    pub fn with_id(mut self, id: impl Into<String>) -> Self { self.id = id.into(); self }
    pub fn with_label(mut self, label: impl Into<String>) -> Self { self.label = label.into(); self }
    pub fn with_icon_svg(mut self, svg: impl Into<String>) -> Self { self.icon_svg = svg.into(); self }
    pub fn with_size(mut self, width: i32, height: i32) -> Self { self.width = width; self.height = height; self }
    pub fn transparent(mut self) -> Self { self.transparent = true; self }
    pub fn no_pointer_events(mut self) -> Self { self.pointer_events = false; self }
    pub fn with_z_index(mut self, z: i32) -> Self { self.z_index = z; self }
    pub fn with_prop(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.props.insert(key.into(), value.into());
        self
    }
    pub fn with_audio(self) -> Self { self.with_prop("audio", "true") }
}

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

// ── Typed config ─────────────────────────────────────────────────────────────

/// The config type for a plugin that has no settings.
///
/// [`PluginCapability::Config`] is a **required** associated type, not one with
/// a default: `associated_type_defaults` has never stabilised, so a default
/// would not compile on the stable edition-2024 toolchain this SDK targets. The
/// cost of that is one line —
///
/// ```ignore
/// type Config = NoConfig;
/// ```
///
/// — and the benefit is that a plugin which *does* have settings cannot forget
/// to say what shape they are and silently receive raw JSON forever.
///
/// `NoConfig` deserializes from anything and keeps nothing, so a user who adds
/// settings in the UI before the plugin knows about them does not crash it.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct NoConfig;

impl<'de> serde::Deserialize<'de> for NoConfig {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        serde::Deserialize::deserialize(d).map(|_: serde::de::IgnoredAny| NoConfig)
    }
}

impl serde::Serialize for NoConfig {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        s.serialize_map(Some(0))?.end()
    }
}

/// A config value that a handler on any thread can read without locking.
///
/// The daemon can rewrite a plugin's config at any moment — including in the
/// middle of a tool call — so the plugin needs a store where a read never
/// blocks a write and a write never blocks a read. That is an `ArcSwap`: a read
/// is one atomic load, and the writer's old value stays alive for whoever is
/// still holding it.
///
/// ```ignore
/// struct MyPlugin { config: Config<MyConfig> }
///
/// impl PluginCapability for MyPlugin {
///     type Config = MyConfig;
///     async fn on_config(&self, _ctx: &PluginContext, cfg: MyConfig) {
///         self.config.store(cfg);
///     }
/// }
/// // anywhere else:
/// let opacity = self.config.load().opacity;
/// ```
pub struct Config<T>(ArcSwap<T>);

impl<T> Config<T> {
    /// Start from a value.
    pub fn new(value: T) -> Self {
        Self(ArcSwap::from_pointee(value))
    }

    /// The current value. One atomic load; hold the guard as briefly as you
    /// would hold a lock, or call [`Config::get`] for an owned handle.
    pub fn load(&self) -> arc_swap::Guard<Arc<T>> {
        self.0.load()
    }

    /// The current value as an `Arc`, for moving into a task.
    pub fn get(&self) -> Arc<T> {
        self.0.load_full()
    }

    /// Replace the value. Readers already holding the old one keep it.
    pub fn store(&self, value: T) {
        self.0.store(Arc::new(value));
    }
}

impl<T: Default> Default for Config<T> {
    fn default() -> Self {
        Self::new(T::default())
    }
}

impl<T: std::fmt::Debug> std::fmt::Debug for Config<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_tuple("Config").field(&*self.load()).finish()
    }
}

// ── The main trait ──

/// Implement this trait to define your plugin's capabilities.
///
/// Every method but the [`Config`](Self::Config) associated type has a default,
/// so implement only what the `[capabilities]` in your `plugin.toml` declare.
/// A hook you do not implement answers `UNIMPLEMENTED`, which is the protocol's
/// word for *absent* — the daemon reads it as such and carries on.
///
/// Handlers receive a [`PluginContext`]. It is cheap to clone, it is never
/// `None`, and it carries the host client — so nothing here needs to be stored
/// on your struct behind a lock.
#[async_trait::async_trait]
pub trait PluginCapability: Send + Sync + 'static {
    /// This plugin's settings, as a type.
    ///
    /// Use [`NoConfig`] when there are none. The SDK parses the daemon's JSON
    /// into this once at startup and again on every change, so
    /// [`on_config`](Self::on_config) receives a value, not a string.
    type Config: DeserializeOwned + Send + Sync + 'static;

    // ── Client ──

    /// Return true if this plugin acts as a full daemon client.
    ///
    /// A client plugin is given [`PluginContext::daemon`] — access to chat,
    /// voice, commands and media — provided the daemon issued it a client
    /// session token. Declaring `client = true` in `plugin.toml` is what makes
    /// the daemon willing to; this method is how the SDK knows to ask.
    fn is_client(&self) -> bool {
        false
    }

    // ── Tools ──

    /// The tools this plugin offers the model. Read once at startup.
    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![]
    }

    /// Run one tool call.
    ///
    /// Return the result as a string — that string goes to the model. Return a
    /// [`ToolError`] for anything that went wrong; the error's *kind* is what
    /// tells the AI loop whether to retry, and tells the UI whether to offer the
    /// user a link to a settings field. `?` works on `serde_json::Error`,
    /// `std::io::Error`, `tonic::Status` and `anyhow::Error`.
    ///
    /// ```ignore
    /// async fn call_tool(&self, ctx: &PluginContext, name: &str, args: &str)
    ///     -> Result<String, ToolError>
    /// {
    ///     let a: Roll = serde_json::from_str(args)?;
    ///     if a.sides < 2 { return Err(ToolError::BadArguments("sides must be >= 2".into())); }
    ///     ctx.host().fire_trigger("dice_rolled", "{}").await?;
    ///     Ok(roll(a).to_string())
    /// }
    /// ```
    async fn call_tool(
        &self,
        _ctx: &PluginContext,
        name: &str,
        _arguments_json: &str,
    ) -> Result<String, ToolError> {
        Err(ToolError::NotFound(format!("no tool named `{name}`")))
    }

    // ── TTS ──

    /// Synthesize one utterance and return the whole buffer.
    async fn tts_synthesize(
        &self,
        _ctx: &PluginContext,
        _req: TtsRequest,
    ) -> anyhow::Result<AudioData> {
        Err(unimplemented("tts_synthesize"))
    }

    /// Synthesize one utterance as a chunk stream, for first-audio latency.
    ///
    /// Send chunks on `chunks` as they are produced; returning `Ok` closes the
    /// stream. The default synthesizes the whole utterance with
    /// [`tts_synthesize`](Self::tts_synthesize) and sends it as one chunk, so a
    /// non-streaming provider needs no code — and a provider that implements
    /// neither still answers `UNIMPLEMENTED`, because the default's failure is
    /// the inner hook's.
    async fn tts_synthesize_stream(
        &self,
        ctx: &PluginContext,
        req: TtsRequest,
        chunks: tokio::sync::mpsc::Sender<AudioChunk>,
    ) -> anyhow::Result<()> {
        let audio = self.tts_synthesize(ctx, req).await?;
        let sample_rate = audio.sample_rate;
        let _ = chunks
            .send(AudioChunk::new(audio.data, sample_rate).last())
            .await;
        Ok(())
    }

    /// The voices this provider exposes in the Voice settings picker.
    async fn tts_voices(&self) -> Vec<VoiceInfo> {
        vec![]
    }

    /// Accept a licensed voice's content-encryption key for one-time,
    /// machine-bound sealing.
    ///
    /// Only protected-voice providers implement this. `UNIMPLEMENTED` is *not*
    /// treated as "no activation needed" by the daemon despite what the proto
    /// comment says — it propagates and fails the activation, which is correct:
    /// a provider that was handed a key and cannot store it has not activated
    /// anything.
    async fn tts_activate(
        &self,
        _ctx: &PluginContext,
        _cek: Vec<u8>,
        _voice_id: &str,
    ) -> anyhow::Result<()> {
        Err(unimplemented("tts_activate"))
    }

    /// Extra TTS settings, rendered by the daemon's generic `DynamicField`
    /// component on the Voice page — there is no per-plugin frontend code.
    async fn tts_config_fields(&self) -> Vec<FieldDef> {
        vec![]
    }

    // ── STT ──

    /// Transcribe a complete utterance.
    ///
    /// The SDK accumulates every audio chunk the daemon streams over
    /// `SttProcess` and calls this once the final one arrives: `audio` is the
    /// concatenated f32-LE PCM, `sample_rate` its declared rate, `options` the
    /// per-utterance decoding hints (language, wake-word bias).
    async fn stt_transcribe(
        &self,
        _ctx: &PluginContext,
        _audio: &[u8],
        _sample_rate: u32,
        _options: &SttOptions,
    ) -> anyhow::Result<SttEvent> {
        Err(unimplemented("stt_transcribe"))
    }

    /// Live-streaming STT: chunks arrive on `audio` as the daemon captures them
    /// (f32-LE PCM, all at `sample_rate`); the closed channel is
    /// end-of-utterance. Emit zero or more [`SttEvent::partial`]s while audio
    /// flows, then one [`SttEvent::transcript`] before returning.
    ///
    /// The default accumulates every byte and forwards to
    /// [`stt_transcribe`](Self::stt_transcribe), so a non-streaming recognizer
    /// needs no code.
    async fn stt_transcribe_stream(
        &self,
        ctx: &PluginContext,
        mut audio: tokio::sync::mpsc::Receiver<Vec<u8>>,
        events: tokio::sync::mpsc::Sender<SttEvent>,
        sample_rate: u32,
        options: SttOptions,
    ) -> anyhow::Result<()> {
        let mut buf: Vec<u8> = Vec::new();
        while let Some(chunk) = audio.recv().await {
            buf.extend_from_slice(&chunk);
        }
        if buf.is_empty() {
            return Ok(());
        }
        let ev = self
            .stt_transcribe(ctx, &buf, sample_rate, &options)
            .await?;
        let _ = events.send(ev).await;
        Ok(())
    }

    /// The language codes this recognizer accepts.
    async fn stt_languages(&self) -> Vec<String> {
        vec![]
    }

    /// Load the recognizer's model.
    ///
    /// Implement this together with [`stt_unload`](Self::stt_unload) and
    /// [`stt_load_state`](Self::stt_load_state) or not at all: the daemon's
    /// idle-unload timer drives all three, and a plugin that answers one of them
    /// and not the others tells it a model it never loaded is not resident.
    async fn stt_load(&self, _ctx: &PluginContext, _req: SttLoadRequest) -> anyhow::Result<()> {
        Err(unimplemented("stt_load"))
    }

    /// Drop the recognizer's model so idle-unload actually frees VRAM.
    async fn stt_unload(&self, _ctx: &PluginContext) -> anyhow::Result<()> {
        Err(unimplemented("stt_unload"))
    }

    /// Where the model is. See [`SttLoadState`].
    async fn stt_load_state(&self, _ctx: &PluginContext) -> anyhow::Result<SttLoadState> {
        Err(unimplemented("stt_load_state"))
    }

    /// Extra STT settings, rendered by `DynamicField` on the Voice page.
    async fn stt_config_fields(&self) -> Vec<FieldDef> {
        vec![]
    }

    // ── AI Provider ──

    /// Stream a model completion. The whole of the `ai_provider` capability.
    ///
    /// Send [`AiChunk`]s on `chunks` as they arrive from the model; returning
    /// `Ok` ends the turn and the SDK appends [`AiChunk::Done`]. Returning
    /// `Err` before the first chunk answers the daemon with a status; after it,
    /// the error is sent as a chunk, because the stream has already started.
    async fn ai_complete(
        &self,
        _ctx: &PluginContext,
        _req: AiRequest,
        _chunks: tokio::sync::mpsc::Sender<AiChunk>,
    ) -> anyhow::Result<()> {
        Err(unimplemented("ai_complete"))
    }

    /// The models this provider can run, and the default one.
    async fn ai_models(&self) -> (Vec<AiModelInfo>, String) {
        (vec![], String::new())
    }

    // ── Actions ──

    /// The action types this plugin contributes to the command editor.
    async fn action_types(&self) -> Vec<ActionTypeDef> {
        vec![]
    }

    /// Run one action. Same error contract as
    /// [`call_tool`](Self::call_tool) — [`crate::ActionError`] is `ToolError`.
    async fn execute_action(
        &self,
        _ctx: &PluginContext,
        action_type: &str,
        _params_json: &str,
    ) -> Result<String, ToolError> {
        Err(ToolError::NotFound(format!(
            "no action named `{action_type}`"
        )))
    }

    // ── Triggers ──

    /// The trigger types this plugin can fire.
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![]
    }

    // ── UI ──

    /// UI contributions: pages, effects, settings sections, injections.
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![]
    }

    /// Handle a call from this plugin's own UI iframe. Return the JSON result.
    async fn handle_ui_call(
        &self,
        _ctx: &PluginContext,
        method: &str,
        _params_json: &str,
    ) -> Result<String, ToolError> {
        Err(ToolError::NotFound(format!("no UI method `{method}`")))
    }

    // ── Events ──

    /// Source id used when sending chat messages.
    ///
    /// The daemon stopped filtering by source id — every client sees every
    /// event — so this affects nothing but a display hint.
    #[deprecated(
        since = "0.6.0",
        note = "the daemon no longer filters by source_id; pass the id to \
                Host::send_chat_message instead, or delete this override"
    )]
    fn source_id(&self) -> &str {
        ""
    }

    /// Daemon-level event types to subscribe to over the host event bus.
    ///
    /// **Chat events do not come through here** — implement
    /// [`on_conversation_event`](Self::on_conversation_event), which is fed by
    /// the firehose.
    fn subscribed_events(&self) -> Vec<String> {
        vec![]
    }

    /// Raw daemon-event fallback. Prefer the typed handlers below.
    async fn on_event(&self, _ctx: &PluginContext, _event_type: &str, _payload_json: &str) {}

    /// Every chat event in every conversation — tool calls, text deltas, user
    /// messages, errors. The single way a plugin observes the chat system, and
    /// only for plugins with the `client` capability.
    async fn on_conversation_event(
        &self,
        _ctx: &PluginContext,
        _conv_id: &str,
        _event: &proto::ConversationEventMsg,
    ) {
    }

    /// Daemon state changed (e.g. Ready → Listening).
    async fn on_state_changed(&self, _ctx: &PluginContext, _event: crate::events::StateChangedEvent) {}

    /// A command was triggered.
    async fn on_command_triggered(
        &self,
        _ctx: &PluginContext,
        _event: crate::events::CommandTriggeredEvent,
    ) {
    }

    /// A command finished.
    async fn on_command_completed(
        &self,
        _ctx: &PluginContext,
        _event: crate::events::CommandCompletedEvent,
    ) {
    }

    // ── Lifecycle ──

    /// This plugin's settings changed, parsed into [`Self::Config`].
    ///
    /// Called once at startup with the daemon's stored config, and again on
    /// every change. Override this one, not
    /// [`on_config_changed`](Self::on_config_changed).
    async fn on_config(&self, _ctx: &PluginContext, _config: Self::Config) {}

    /// Raw config JSON. The default parses it into [`Self::Config`] and calls
    /// [`on_config`](Self::on_config).
    ///
    /// A parse failure is reported at `WARN` *and* as a `PluginLog` the user can
    /// see in the plugin's log pane, and the old config keeps running. The
    /// alternative — swallowing it — is how a plugin ends up quietly using
    /// settings from three edits ago while the UI shows the new ones.
    ///
    /// Override only to handle config the type system cannot describe.
    async fn on_config_changed(&self, ctx: &PluginContext, config_json: &str) {
        let empty = config_json.trim().is_empty() || config_json.trim() == "{}";
        let json = if config_json.trim().is_empty() {
            "{}"
        } else {
            config_json
        };
        match serde_json::from_str::<Self::Config>(json) {
            Ok(config) => self.on_config(ctx, config).await,
            // The message has to tell these two apart, because they are
            // different bugs with different fixes and the second one is the
            // one that actually happens.
            //
            // A payload that fails to parse when it is `{}` is not a user who
            // typed something wrong: it is a FRESH INSTALL. The daemon's first
            // config payload to a plugin nobody has configured yet is `{}`, and
            // a `Config` with a required field rejects it. `on_config` is then
            // never called even once — not "the previous config keeps running",
            // because there is no previous config — and the plugin serves every
            // call on whatever `Default` gave it: an empty API key, a trigger
            // name that is the empty string. The one WARN lands in the log pane,
            // which is not where the author is looking.
            Err(e) if empty => {
                let msg = format!(
                    "this plugin has no settings saved yet, and its `Config` \
                     type rejects the empty payload the daemon sends on a fresh \
                     install ({e}). `on_config` was NOT called, so the plugin is \
                     running on `Config::default()`. \
                     fix: mark the config type `#[astra::config]` (it adds \
                     `#[serde(default)]`, so `{{}}` parses), then answer a value \
                     that is still missing with \
                     `ToolError::not_configured(\"<field>\")` — which is what \
                     sends the user to that exact settings field."
                );
                tracing::warn!("{msg}");
                let _ = ctx.host().log_warn(&msg).await;
            }
            Err(e) => {
                let msg = format!(
                    "config did not match this plugin's expected shape ({e}); \
                     keeping the previous config"
                );
                tracing::warn!("{msg}");
                let _ = ctx.host().log_warn(&msg).await;
            }
        }
    }

    /// The daemon's UI language changed. Update your locale here (e.g.
    /// [`crate::I18n::set_language`]). [`PluginContext::language`] is already
    /// updated when this is called.
    async fn on_language_changed(&self, _ctx: &PluginContext, _language: &str) {}

    /// Everything is wired: registered, config applied, language set.
    ///
    /// Start background work here. Returning `Err` **aborts startup** — the
    /// plugin never begins serving and the process exits non-zero, which is the
    /// honest answer for "I cannot do my job". The alternative is a plugin the
    /// daemon believes is healthy and that answers every call with the same
    /// failure.
    async fn on_start(&self, _ctx: &PluginContext) -> anyhow::Result<()> {
        Ok(())
    }

    /// The set of trigger types with at least one command listening changed.
    /// [`PluginContext::active_triggers`] is already updated when this is
    /// called, so most plugins do not need this hook at all — they just check
    /// `ctx.active_triggers().contains(..)` before firing.
    async fn on_active_triggers(&self, _ctx: &PluginContext, _active_types: Vec<String>) {}

    /// The daemon asked this plugin to stop. Flush state here; the SDK has
    /// already stopped accepting calls.
    async fn on_shutdown(&self, _ctx: &PluginContext) {}

    /// Liveness probe, every 15 s.
    ///
    /// Not routed through the daemon's `optional_hook`: any error, including
    /// `UNIMPLEMENTED`, marks the plugin dead. Answer quickly and locally.
    async fn health_check(&self) -> (bool, String) {
        (true, "ok".into())
    }
}

// ── 0.5 compatibility, for one minor ─────────────────────────────────────────

/// The 0.5 authoring surface, forwarded onto the 0.6 one.
///
/// Deprecated in **0.6**, removed in **0.8** — the window `docs/en/versioning.md`
/// promises. Until then an 0.5-era plugin builds against this SDK by changing
/// its import line and nothing else:
///
/// ```ignore
/// -use astra_plugin_sdk::*;          // 0.5
/// +use astra_plugin_sdk::compat::*;  // 0.6, deprecated, still works
/// ```
///
/// Every item here is `#[deprecated]`, so the build tells the author what to fix
/// and `cargo build` still succeeds. [`docs/en/migration-0.6.md`] is the hook-by-hook
/// version; this module is the thing that buys the time to read it.
///
/// # What the shim can and cannot do
///
/// * `HostClient` and `DaemonClient` are **type aliases** for `Arc<dyn Host>` and
///   `Arc<dyn Daemon>`, so a field declared `Arc<Mutex<HostClient>>` and a call
///   written `host.lock().await.fire_trigger(..)` both compile unchanged — the
///   guard derefs through the `Arc` to the trait object. What is *not* there is
///   the concrete 0.5 client's inherent surface: `HostClient::connect_bootstrap`
///   and `subscribe_events` are gone, because in 0.6 the runner owns the event
///   subscription and hands events to [`PluginCapability::on_event`].
/// * `set_host` / `set_daemon_client` are delivered **once**, immediately before
///   the first 0.6 hook that carries a [`PluginContext`] — in practice
///   `on_config_changed`, which is the first thing the runner calls. In 0.5 they
///   arrived just after registration. Nothing observable moved, but a plugin
///   that assumed the host was set before *any* of its code ran should read
///   [`PluginContext`] instead: `ctx.host()` is never `None`.
/// * A `ToolResult::err` becomes [`ToolError::Internal`]. 0.5 had one failure
///   and it was a sentence; 0.6 has eight kinds and the kind is what the AI loop
///   reads. `Internal` is the one that promises the model nothing, which is the
///   honest answer for a string.
/// * Hooks that did not exist in 0.5 — `ai_complete`, `tts_activate`,
///   `stt_load`/`stt_unload`/`stt_load_state` — stay `UNIMPLEMENTED`, which the
///   protocol reads as *absent*. Implement them by migrating the trait.
///
/// [`docs/en/migration-0.6.md`]: https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/migration-0.6.md
pub mod compat {
    // Everything in here mentions the deprecated items on purpose. The lint is
    // for the author's crate, where it fires at the `impl` site; inside the shim
    // it would only be noise.
    #![allow(deprecated)]

    use std::any::TypeId;
    use std::collections::HashSet;
    use std::sync::{Arc, Mutex as StdMutex, OnceLock};

    use tokio::sync::Mutex;

    use crate::proto;

    /// The rest of 0.5's prelude, unchanged in 0.6 and re-exported here so that
    /// `use astra_plugin_sdk::compat::*;` is a drop-in for
    /// `use astra_plugin_sdk::prelude::*;` — **one line, and the whole 0.5 plugin
    /// still builds**.
    ///
    /// It has to be a replacement rather than an addition: importing both globs
    /// puts two traits called `PluginCapability` in scope, and
    /// `impl PluginCapability for MyPlugin` is then ambiguous (E0659) rather
    /// than deprecated.
    pub use super::{
        ActionTypeDef, AiModelInfo, AudioData, Config, DropdownOption, FieldCondition, FieldDef,
        NoConfig, SttEvent, ToolDef, TriggerTypeDef, UiContribution, VoiceInfo,
    };
    // Under their own names, so a hook can be moved onto the 0.6 signature one
    // at a time without the import line changing again.
    pub use crate::context::{ActiveTriggers, Daemon, Host, PluginContext};
    pub use crate::error::{ActionError, ToolError};
    pub use crate::events::{CommandCompletedEvent, CommandTriggeredEvent, StateChangedEvent};
    pub use crate::i18n::I18n;
    pub use crate::{CapabilityAuth, RunConfig, run, run_with};
    pub use async_trait::async_trait;

    /// 0.5's `HostClient`, as a handler held it.
    ///
    /// A field typed `Arc<Mutex<HostClient>>` and a call written
    /// `host.lock().await.log_info("..")` are unchanged: the guard derefs
    /// through the `Arc` onto [`Host`].
    #[deprecated(
        since = "0.6.0",
        note = "use `ctx.host()` — a `&Arc<dyn Host>` on the `PluginContext` every \
                0.6 handler is given, with no lock to lose"
    )]
    pub type HostClient = Arc<dyn Host>;

    /// 0.5's `DaemonClient`, as a client plugin held it.
    #[deprecated(
        since = "0.6.0",
        note = "use `ctx.daemon()` — `Option<&Arc<dyn Daemon>>`, `Some` exactly when \
                the daemon issued this plugin a client session"
    )]
    pub type DaemonClient = Arc<dyn Daemon>;

    /// 0.5's tool result.
    #[deprecated(
        since = "0.6.0",
        note = "return `Result<String, ToolError>`: `Ok(text)` for `ToolResult::ok`, \
                and the `ToolError` variant that says *why* for `ToolResult::err`"
    )]
    #[derive(Debug, Clone)]
    pub struct ToolResult {
        pub success: bool,
        pub result: String,
        pub error: String,
    }

    impl ToolResult {
        pub fn ok(result: impl Into<String>) -> Self {
            Self { success: true, result: result.into(), error: String::new() }
        }
        pub fn err(error: impl Into<String>) -> Self {
            Self { success: false, result: String::new(), error: error.into() }
        }
    }

    /// 0.5's action result.
    #[deprecated(
        since = "0.6.0",
        note = "return `Result<String, ActionError>` (`ActionError` is `ToolError`)"
    )]
    #[derive(Debug, Clone)]
    pub struct ActionResult {
        pub success: bool,
        pub result: String,
        pub error: String,
    }

    impl ActionResult {
        pub fn ok(result: impl Into<String>) -> Self {
            Self { success: true, result: result.into(), error: String::new() }
        }
        pub fn err(error: impl Into<String>) -> Self {
            Self { success: false, result: String::new(), error: error.into() }
        }
    }

    /// 0.5's UI-call result.
    #[deprecated(
        since = "0.6.0",
        note = "return `Result<String, ToolError>`; `ToolError::NotFound` is the \
                one for an unknown method name"
    )]
    #[derive(Debug, Clone)]
    pub struct UiCallResult {
        pub result_json: String,
        pub error: String,
    }

    impl UiCallResult {
        pub fn ok(json: impl Into<String>) -> Self {
            Self { result_json: json.into(), error: String::new() }
        }
        pub fn err(msg: impl Into<String>) -> Self {
            Self { result_json: String::new(), error: msg.into() }
        }
    }

    /// One `Result` out of an 0.5 pair of (`success`, `result`, `error`).
    fn legacy_outcome(success: bool, result: String, error: String) -> Result<String, ToolError> {
        if success {
            Ok(result)
        } else {
            // 0.5 had exactly one failure and it was a sentence. `Internal` is
            // the 0.6 kind that promises the model nothing, which is the only
            // honest reading of a string whose author never said what it was.
            Err(ToolError::Internal(error))
        }
    }

    /// The plugin trait as 0.5 spelled it.
    ///
    /// Implementing this instead of [`crate::PluginCapability`] still produces a
    /// working plugin: the blanket impl below forwards every hook. It warns at
    /// the `impl` line, and it stops working in 0.8.
    #[deprecated(
        since = "0.6.0",
        note = "implement `astra_plugin_sdk::PluginCapability` (0.6): handlers take a \
                `&PluginContext`, return `Result<_, ToolError>`, and declare \
                `type Config`. See docs/en/migration-0.6.md. This trait is removed in 0.8"
    )]
    #[async_trait::async_trait]
    pub trait PluginCapability: Send + Sync + 'static {
        // ── Client ──

        fn is_client(&self) -> bool {
            false
        }

        async fn set_daemon_client(&self, _client: Arc<Mutex<DaemonClient>>) {}

        // ── Tools ──

        async fn list_tools(&self) -> Vec<ToolDef> {
            vec![]
        }

        async fn call_tool(&self, _name: &str, _arguments_json: &str) -> ToolResult {
            ToolResult::err("Not implemented")
        }

        // ── TTS ──

        async fn tts_synthesize(
            &self,
            _text: &str,
            _voice_id: &str,
            _speed: f32,
            _pitch: f32,
        ) -> anyhow::Result<AudioData> {
            anyhow::bail!("TTS not implemented")
        }

        async fn tts_voices(&self) -> Vec<VoiceInfo> {
            vec![]
        }

        async fn tts_config_fields(&self) -> Vec<FieldDef> {
            vec![]
        }

        // ── STT ──

        async fn stt_transcribe(&self, _audio: &[u8], _sample_rate: u32) -> anyhow::Result<SttEvent> {
            anyhow::bail!("STT not implemented")
        }

        /// 0.5's streaming STT hook. The default accumulates and forwards to
        /// [`stt_transcribe`](Self::stt_transcribe), exactly as 0.5's did — which
        /// is why the forwarding impl below routes 0.6's stream hook *here* and
        /// not at `stt_transcribe`. Routing it at the non-streaming hook would
        /// silently drop a plugin's real streaming implementation, along with
        /// every partial it emits.
        async fn stt_transcribe_stream(
            &self,
            mut audio_rx: tokio::sync::mpsc::Receiver<Vec<u8>>,
            events_tx: tokio::sync::mpsc::Sender<SttEvent>,
            sample_rate: u32,
        ) -> anyhow::Result<()> {
            let mut buf: Vec<u8> = Vec::new();
            while let Some(chunk) = audio_rx.recv().await {
                buf.extend_from_slice(&chunk);
            }
            if buf.is_empty() {
                return Ok(());
            }
            let ev = self.stt_transcribe(&buf, sample_rate).await?;
            let _ = events_tx.send(ev).await;
            Ok(())
        }

        async fn stt_languages(&self) -> Vec<String> {
            vec![]
        }

        async fn stt_config_fields(&self) -> Vec<FieldDef> {
            vec![]
        }

        // ── AI provider ──

        async fn ai_models(&self) -> (Vec<AiModelInfo>, String) {
            (vec![], String::new())
        }

        // ── Actions and triggers ──

        async fn action_types(&self) -> Vec<ActionTypeDef> {
            vec![]
        }

        async fn execute_action(&self, _action_type: &str, _params_json: &str) -> ActionResult {
            ActionResult::err("Not implemented")
        }

        async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
            vec![]
        }

        // ── UI ──

        async fn ui_contributions(&self) -> Vec<UiContribution> {
            vec![]
        }

        async fn handle_ui_call(&self, _method: &str, _params_json: &str) -> UiCallResult {
            UiCallResult::err("No UI call handler implemented")
        }

        // ── Events ──

        fn source_id(&self) -> &str {
            ""
        }

        fn subscribed_events(&self) -> Vec<String> {
            vec![]
        }

        async fn on_event(&self, _event_type: &str, _payload_json: &str) {}

        async fn on_conversation_event(&self, _conv_id: &str, _event: &proto::ConversationEventMsg) {}

        async fn on_state_changed(&self, _event: crate::events::StateChangedEvent) {}

        async fn on_command_triggered(&self, _event: crate::events::CommandTriggeredEvent) {}

        async fn on_command_completed(&self, _event: crate::events::CommandCompletedEvent) {}

        // ── Lifecycle ──

        async fn set_host(&self, _host: Arc<Mutex<HostClient>>) {}

        async fn on_config_changed(&self, _config_json: &str) {}

        async fn on_language_changed(&self, _language: &str) {}

        async fn on_active_triggers(&self, _active_types: Vec<String>) {}

        async fn on_shutdown(&self) {}

        async fn health_check(&self) -> (bool, String) {
            (true, "ok".into())
        }
    }

    // ── delivering the host exactly once ──

    /// Which `(plugin, host)` pairs have already been handed their `set_host`.
    ///
    /// The 0.5 runner called `set_host` at line 223 and `on_config_changed` at
    /// line 300 — the host was there before any of the plugin's own code ran,
    /// and an 0.5 `on_config_changed` that logs through the host is entitled to
    /// work. 0.6 has no such call (the context is a parameter), so the shim
    /// delivers from whichever forwarded hook runs first, and this registry is
    /// what keeps "first" from meaning "every".
    ///
    /// A blanket impl has no field to hold a `OnceCell`, so identity has to come
    /// from somewhere else. The key is the plugin's address *and* the host's,
    /// both with the type id: keying on the type alone would starve the second
    /// instance in any test process that runs two, and keying on the plugin
    /// address alone would mis-skip if a dropped instance's allocation were
    /// recycled — a recycled pair is a great deal less likely than a recycled
    /// address, and re-delivering the same host to the same plugin is the
    /// harmless direction anyway.
    type DeliveryKey = (TypeId, usize, usize);
    static DELIVERED: OnceLock<StdMutex<HashSet<DeliveryKey>>> = OnceLock::new();

    fn delivery_key<T: PluginCapability>(plugin: &T, ctx: &PluginContext) -> DeliveryKey {
        (
            TypeId::of::<T>(),
            plugin as *const T as *const () as usize,
            Arc::as_ptr(ctx.host()) as *const () as usize,
        )
    }

    /// Hand the plugin its 0.5 host (and daemon client), the first time only.
    async fn deliver_once<T: PluginCapability>(plugin: &T, ctx: &PluginContext) {
        let first = DELIVERED
            .get_or_init(StdMutex::default)
            .lock()
            .expect("legacy-host registry poisoned")
            .insert(delivery_key(plugin, ctx));
        if !first {
            return;
        }
        plugin.set_host(Arc::new(Mutex::new(ctx.host().clone()))).await;
        if let Some(daemon) = ctx.daemon() {
            plugin
                .set_daemon_client(Arc::new(Mutex::new(daemon.clone())))
                .await;
        }
    }

    /// Forget one delivery, so a test can hand the same plugin the same host
    /// twice. Nothing in a plugin process needs this.
    #[doc(hidden)]
    pub fn forget_delivery<T: PluginCapability>(plugin: &T, ctx: &PluginContext) {
        if let Some(reg) = DELIVERED.get() {
            reg.lock()
                .expect("legacy-host registry poisoned")
                .remove(&delivery_key(plugin, ctx));
        }
    }

    // ── the forwarding impl ──

    /// Every 0.5 plugin is a 0.6 plugin.
    ///
    /// The two rules this impl exists to get right:
    ///
    /// 1. **Stream hooks forward to stream hooks.** 0.6's
    ///    `stt_transcribe_stream` calls 0.5's `stt_transcribe_stream`, whose own
    ///    default buffers into `stt_transcribe`. Forwarding at the non-streaming
    ///    hook instead would compile, pass a naive test, and silently discard the
    ///    partials of every plugin that had a real streaming backend.
    /// 2. **Hooks 0.5 never had stay absent.** `ai_complete`, `tts_activate` and
    ///    the three `stt_load*` hooks are left at the 0.6 defaults, so they answer
    ///    `UNIMPLEMENTED` — which the protocol reads as "no such hook", and the
    ///    daemon carries on. Forwarding them to something plausible would tell the
    ///    daemon a plugin supports idle-unload when it does not.
    #[async_trait::async_trait]
    impl<T: PluginCapability> super::PluginCapability for T {
        // 0.5 had no typed config: the raw JSON goes straight through
        // `on_config_changed` below, and `on_config` is never reached.
        type Config = NoConfig;

        fn is_client(&self) -> bool {
            PluginCapability::is_client(self)
        }

        async fn list_tools(&self) -> Vec<ToolDef> {
            PluginCapability::list_tools(self).await
        }

        async fn call_tool(
            &self,
            ctx: &PluginContext,
            name: &str,
            arguments_json: &str,
        ) -> Result<String, ToolError> {
            deliver_once(self, ctx).await;
            let r = PluginCapability::call_tool(self, name, arguments_json).await;
            legacy_outcome(r.success, r.result, r.error)
        }

        async fn tts_synthesize(
            &self,
            ctx: &PluginContext,
            req: super::TtsRequest,
        ) -> anyhow::Result<AudioData> {
            deliver_once(self, ctx).await;
            PluginCapability::tts_synthesize(self, &req.text, &req.voice_id, req.speed, req.pitch)
                .await
        }

        async fn tts_voices(&self) -> Vec<VoiceInfo> {
            PluginCapability::tts_voices(self).await
        }

        async fn tts_config_fields(&self) -> Vec<FieldDef> {
            PluginCapability::tts_config_fields(self).await
        }

        async fn stt_transcribe(
            &self,
            ctx: &PluginContext,
            audio: &[u8],
            sample_rate: u32,
            _options: &super::SttOptions,
        ) -> anyhow::Result<SttEvent> {
            deliver_once(self, ctx).await;
            PluginCapability::stt_transcribe(self, audio, sample_rate).await
        }

        async fn stt_transcribe_stream(
            &self,
            ctx: &PluginContext,
            audio: tokio::sync::mpsc::Receiver<Vec<u8>>,
            events: tokio::sync::mpsc::Sender<SttEvent>,
            sample_rate: u32,
            _options: super::SttOptions,
        ) -> anyhow::Result<()> {
            deliver_once(self, ctx).await;
            PluginCapability::stt_transcribe_stream(self, audio, events, sample_rate).await
        }

        async fn stt_languages(&self) -> Vec<String> {
            PluginCapability::stt_languages(self).await
        }

        async fn stt_config_fields(&self) -> Vec<FieldDef> {
            PluginCapability::stt_config_fields(self).await
        }

        async fn ai_models(&self) -> (Vec<AiModelInfo>, String) {
            PluginCapability::ai_models(self).await
        }

        async fn action_types(&self) -> Vec<ActionTypeDef> {
            PluginCapability::action_types(self).await
        }

        async fn execute_action(
            &self,
            ctx: &PluginContext,
            action_type: &str,
            params_json: &str,
        ) -> Result<String, ToolError> {
            deliver_once(self, ctx).await;
            let r = PluginCapability::execute_action(self, action_type, params_json).await;
            legacy_outcome(r.success, r.result, r.error)
        }

        async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
            PluginCapability::trigger_types(self).await
        }

        async fn ui_contributions(&self) -> Vec<UiContribution> {
            PluginCapability::ui_contributions(self).await
        }

        async fn handle_ui_call(
            &self,
            ctx: &PluginContext,
            method: &str,
            params_json: &str,
        ) -> Result<String, ToolError> {
            deliver_once(self, ctx).await;
            let r = PluginCapability::handle_ui_call(self, method, params_json).await;
            // 0.5's UiCallResult had no `success` flag: a non-empty `error` is
            // the failure, and an empty one with an empty result is the legal
            // answer "nothing to say".
            if r.error.is_empty() {
                Ok(r.result_json)
            } else {
                Err(ToolError::Internal(r.error))
            }
        }

        fn source_id(&self) -> &str {
            PluginCapability::source_id(self)
        }

        fn subscribed_events(&self) -> Vec<String> {
            PluginCapability::subscribed_events(self)
        }

        async fn on_event(&self, ctx: &PluginContext, event_type: &str, payload_json: &str) {
            deliver_once(self, ctx).await;
            PluginCapability::on_event(self, event_type, payload_json).await
        }

        async fn on_conversation_event(
            &self,
            ctx: &PluginContext,
            conv_id: &str,
            event: &proto::ConversationEventMsg,
        ) {
            deliver_once(self, ctx).await;
            PluginCapability::on_conversation_event(self, conv_id, event).await
        }

        async fn on_state_changed(
            &self,
            ctx: &PluginContext,
            event: crate::events::StateChangedEvent,
        ) {
            deliver_once(self, ctx).await;
            PluginCapability::on_state_changed(self, event).await
        }

        async fn on_command_triggered(
            &self,
            ctx: &PluginContext,
            event: crate::events::CommandTriggeredEvent,
        ) {
            deliver_once(self, ctx).await;
            PluginCapability::on_command_triggered(self, event).await
        }

        async fn on_command_completed(
            &self,
            ctx: &PluginContext,
            event: crate::events::CommandCompletedEvent,
        ) {
            deliver_once(self, ctx).await;
            PluginCapability::on_command_completed(self, event).await
        }

        /// Straight through, unparsed. `on_config` — and with it the 0.6
        /// warning about a config that does not fit — is deliberately not
        /// reached: an 0.5 plugin parses its own JSON, and `NoConfig` would
        /// accept anything anyway.
        async fn on_config_changed(&self, ctx: &PluginContext, config_json: &str) {
            deliver_once(self, ctx).await;
            PluginCapability::on_config_changed(self, config_json).await
        }

        async fn on_language_changed(&self, ctx: &PluginContext, language: &str) {
            deliver_once(self, ctx).await;
            PluginCapability::on_language_changed(self, language).await
        }

        /// 0.5 had no `on_start`; this exists to make sure the host has been
        /// delivered before the plugin starts serving, whatever else ran first.
        async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
            deliver_once(self, ctx).await;
            Ok(())
        }

        async fn on_active_triggers(&self, ctx: &PluginContext, active_types: Vec<String>) {
            deliver_once(self, ctx).await;
            PluginCapability::on_active_triggers(self, active_types).await
        }

        async fn on_shutdown(&self, ctx: &PluginContext) {
            deliver_once(self, ctx).await;
            PluginCapability::on_shutdown(self).await
        }

        async fn health_check(&self) -> (bool, String) {
            PluginCapability::health_check(self).await
        }
    }

    // ── the shim, tested against the trait it is a shim for ──────────────────
    //
    // Every plugin below is written the way an 0.5 plugin was written: the 0.5
    // trait, the 0.5 result types, `Mutex<Option<Arc<Mutex<HostClient>>>>` for
    // the host. They are then run through the 0.6 harness, which only knows
    // about the 0.6 trait — so what these tests exercise is the forwarding impl
    // and nothing else.
    #[cfg(test)]
    mod tests {
        use std::sync::Mutex as StdMutex;

        use super::*;
        use crate::testing::Harness;

        // ── an 0.5 tool plugin, verbatim ──

        /// dice-roller as it was written in 0.5, down to the host field.
        #[derive(Default)]
        struct LegacyDice {
            host: Mutex<Option<Arc<Mutex<HostClient>>>>,
            /// How many times `set_host` was called, which must be once.
            host_deliveries: std::sync::atomic::AtomicUsize,
            config_json: StdMutex<String>,
            /// Whether the host was already there when `on_config_changed` ran,
            /// which in 0.5 it always was.
            config_had_host: std::sync::atomic::AtomicBool,
        }

        #[async_trait::async_trait]
        impl PluginCapability for LegacyDice {
            async fn set_host(&self, host: Arc<Mutex<HostClient>>) {
                self.host_deliveries
                    .fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                *self.host.lock().await = Some(host);
            }

            async fn list_tools(&self) -> Vec<ToolDef> {
                vec![ToolDef {
                    name: "roll_dice".into(),
                    description: "Roll dice.".into(),
                    parameters_json: r#"{"type":"object","properties":{}}"#.into(),
                }]
            }

            async fn call_tool(&self, name: &str, _arguments_json: &str) -> ToolResult {
                if name != "roll_dice" {
                    return ToolResult::err(format!("Unknown tool: {name}"));
                }
                // The 0.5 way of reaching the daemon: through the stored host.
                let host = self.host.lock().await.clone();
                match host {
                    Some(h) => {
                        let h = h.lock().await;
                        let _ = h.fire_trigger("on_roll_value", r#"{"value":"4"}"#).await;
                        ToolResult::ok("Rolled 1d6: [4] = 4")
                    }
                    None => ToolResult::err("host client not available yet"),
                }
            }

            async fn execute_action(&self, action_type: &str, _params: &str) -> ActionResult {
                match action_type {
                    "roll_dice" => ActionResult::ok("1d6: [4] = 4"),
                    other => ActionResult::err(format!("Unknown action: {other}")),
                }
            }

            async fn handle_ui_call(&self, method: &str, _params: &str) -> UiCallResult {
                match method {
                    "getConfig" => UiCallResult::ok(r#"{"default_sides":6}"#),
                    other => UiCallResult::err(format!("Unknown method: {other}")),
                }
            }

            async fn on_config_changed(&self, config_json: &str) {
                *self.config_json.lock().unwrap() = config_json.to_string();
                self.config_had_host.store(
                    self.host.lock().await.is_some(),
                    std::sync::atomic::Ordering::SeqCst,
                );
            }
        }

        /// The acceptance criterion of task 5.11, in one test: an 0.5-era plugin
        /// runs unmodified on the 0.6 SDK — its tools answer, and the host it
        /// stored in `set_host` still reaches the daemon.
        #[tokio::test]
        async fn an_0_5_plugin_still_serves_tools_and_still_fires_triggers() {
            let h = Harness::new(LegacyDice::default())
                .with_config_json(r#"{"default_sides":20}"#)
                .start()
                .await
                .unwrap();

            let tools = h.tools().await;
            assert_eq!(tools.len(), 1);
            assert_eq!(tools[0].name, "roll_dice");

            let out = h.call_tool("roll_dice", serde_json::json!({})).await.unwrap();
            assert_eq!(out, "Rolled 1d6: [4] = 4");

            let fired = h.fired_triggers();
            assert_eq!(fired.len(), 1, "the stored host must still work: {fired:?}");
            assert_eq!(fired[0].trigger_type, "on_roll_value");

            // The raw config JSON reaches the 0.5 hook unparsed, and `on_config`
            // (which an 0.5 plugin does not have) is not involved.
            assert_eq!(
                *h.plugin().config_json.lock().unwrap(),
                r#"{"default_sides":20}"#
            );

            // 0.5's runner called `set_host` (runner.rs:223) before
            // `on_config_changed` (runner.rs:300). An 0.5 `on_config_changed`
            // that logs through the host is entitled to still work.
            assert!(
                h.plugin()
                    .config_had_host
                    .load(std::sync::atomic::Ordering::SeqCst),
                "the host must arrive before the first 0.5 hook, as it did in 0.5"
            );

            // And exactly one `set_host`, no matter how many hooks ran.
            assert_eq!(
                h.plugin()
                    .host_deliveries
                    .load(std::sync::atomic::Ordering::SeqCst),
                1
            );
        }

        /// 0.5's three result types had one failure between them, and it was a
        /// sentence. Each maps onto a `ToolError` that still carries it.
        #[tokio::test]
        async fn an_0_5_failure_becomes_a_tool_error_with_the_same_sentence() {
            let h = Harness::new(LegacyDice::default()).start().await.unwrap();

            let err = h.call_tool("nope", serde_json::json!({})).await.unwrap_err();
            assert!(matches!(err, ToolError::Internal(ref m) if m == "Unknown tool: nope"), "{err:?}");

            let err = h.execute_action("nope", serde_json::json!({})).await.unwrap_err();
            assert!(matches!(err, ToolError::Internal(ref m) if m == "Unknown action: nope"), "{err:?}");

            assert_eq!(
                h.ui_call("getConfig", serde_json::json!({})).await.unwrap(),
                r#"{"default_sides":6}"#
            );
            let err = h.ui_call("nope", serde_json::json!({})).await.unwrap_err();
            assert!(matches!(err, ToolError::Internal(ref m) if m == "Unknown method: nope"), "{err:?}");
        }

        // ── the streaming hooks, which are the ones worth doubting ──

        /// echo-stt as it was written in 0.5: a real streaming backend, which
        /// overrides the *stream* hook and never implements `stt_transcribe`.
        struct LegacyStreamingStt;

        #[async_trait::async_trait]
        impl PluginCapability for LegacyStreamingStt {
            async fn stt_transcribe_stream(
                &self,
                mut audio_rx: tokio::sync::mpsc::Receiver<Vec<u8>>,
                events_tx: tokio::sync::mpsc::Sender<SttEvent>,
                _sample_rate: u32,
            ) -> anyhow::Result<()> {
                let mut chunks = 0usize;
                while let Some(chunk) = audio_rx.recv().await {
                    chunks += 1;
                    let _ = events_tx
                        .send(SttEvent::partial(format!("chunk {chunks} ({} bytes)", chunk.len())))
                        .await;
                }
                let _ = events_tx
                    .send(SttEvent::transcript(format!("{chunks} chunks")))
                    .await;
                Ok(())
            }
        }

        /// The failure this exists to catch: forwarding 0.6's stream hook to
        /// 0.5's *non-streaming* `stt_transcribe` compiles, and silently throws
        /// away every partial a real streaming backend emits. Change
        /// `stt_transcribe_stream` in the impl above to forward at
        /// `stt_transcribe` and this test fails with one event instead of four.
        #[tokio::test]
        async fn a_streaming_0_5_recognizer_keeps_emitting_partials() {
            let h = Harness::new(LegacyStreamingStt).start().await.unwrap();

            let events = h
                .stt_stream(vec![vec![0u8; 8], vec![0u8; 8], vec![0u8; 4]])
                .await
                .unwrap();

            let partials: Vec<&SttEvent> = events.iter().filter(|e| !e.is_final).collect();
            assert_eq!(
                partials.len(),
                3,
                "the plugin's own streaming hook must be the one that ran: {events:?}"
            );
            assert_eq!(partials[0].text, "chunk 1 (8 bytes)");
            let finals: Vec<&SttEvent> = events.iter().filter(|e| e.is_final).collect();
            assert_eq!(finals.len(), 1);
            assert_eq!(finals[0].text, "3 chunks");
        }

        /// mock-stt as it was written in 0.5: non-streaming, and reached through
        /// 0.5's own buffering default. The daemon only ever calls `SttProcess`,
        /// so this path is the one every non-streaming 0.5 recognizer takes.
        struct LegacyBufferedStt;

        #[async_trait::async_trait]
        impl PluginCapability for LegacyBufferedStt {
            async fn stt_transcribe(
                &self,
                audio: &[u8],
                sample_rate: u32,
            ) -> anyhow::Result<SttEvent> {
                Ok(SttEvent::transcript(format!(
                    "{} bytes at {sample_rate} Hz",
                    audio.len()
                )))
            }
        }

        #[tokio::test]
        async fn a_non_streaming_0_5_recognizer_still_gets_the_whole_utterance() {
            let h = Harness::new(LegacyBufferedStt).start().await.unwrap();

            let events = h
                .stt_stream_with(
                    vec![vec![0u8; 8], vec![0u8; 8], vec![0u8; 4]],
                    16_000,
                    crate::testing::fixtures::stt_options(),
                )
                .await
                .unwrap();

            assert_eq!(events.len(), 1, "{events:?}");
            assert!(events[0].is_final);
            assert_eq!(events[0].text, "20 bytes at 16000 Hz");
        }

        /// tone-tts as it was written in 0.5: one buffer, no streaming hook —
        /// 0.5 had none. The daemon's streaming path must still reach it, which
        /// it does through the 0.6 default, through the shim, into 0.5's
        /// four-argument `tts_synthesize`.
        struct LegacyTts;

        #[async_trait::async_trait]
        impl PluginCapability for LegacyTts {
            async fn tts_voices(&self) -> Vec<VoiceInfo> {
                vec![VoiceInfo::new("tone", "Tone")]
            }

            async fn tts_synthesize(
                &self,
                text: &str,
                voice_id: &str,
                speed: f32,
                _pitch: f32,
            ) -> anyhow::Result<AudioData> {
                Ok(AudioData {
                    data: format!("{text}/{voice_id}/{speed}").into_bytes(),
                    format: "pcm".into(),
                    sample_rate: 24_000,
                    duration_ms: 100,
                })
            }
        }

        #[tokio::test]
        async fn an_0_5_tts_provider_answers_on_the_streaming_path_too() {
            let h = Harness::new(LegacyTts).start().await.unwrap();

            assert_eq!(h.tts_voices().await.len(), 1);

            let req = crate::capability::TtsRequest {
                text: "hello".into(),
                voice_id: "tone".into(),
                speed: 1.5,
                pitch: 1.0,
            };
            let audio = h.tts_synthesize(req.clone()).await.unwrap();
            assert_eq!(String::from_utf8(audio.data).unwrap(), "hello/tone/1.5");

            // The daemon's streaming TTS path, which 0.5 had no hook for: the
            // 0.6 default synthesizes the whole utterance and sends one chunk.
            let chunks = h.tts_stream(req).await.unwrap();
            assert_eq!(chunks.len(), 1);
            assert!(chunks[0].is_last);
            assert_eq!(chunks[0].sample_rate, 24_000);
        }

        /// Hooks that did not exist in 0.5 must stay absent, not answer
        /// plausibly. `UNIMPLEMENTED` is the protocol's word for "no such hook",
        /// and the daemon's idle-unload timer reads `stt_load_state` — a shim
        /// that answered `NotNeeded` would tell it a resident model is not
        /// resident.
        #[tokio::test]
        async fn hooks_0_5_never_had_stay_unimplemented() {
            let h = Harness::new(LegacyBufferedStt).start().await.unwrap();

            let e = h.stt_load_state().await.unwrap_err();
            assert!(
                e.downcast_ref::<crate::error::HookUnimplemented>().is_some(),
                "stt_load_state must answer UNIMPLEMENTED, got {e:?}"
            );

            let e = h.ai_complete(crate::capability::AiRequest::default()).await.unwrap_err();
            assert!(
                e.downcast_ref::<crate::error::HookUnimplemented>().is_some(),
                "ai_complete must answer UNIMPLEMENTED, got {e:?}"
            );
        }

        /// Two instances of one 0.5 plugin in one process each get their own
        /// host. The registry that makes `set_host` happen once must key on the
        /// instance, not on the type — a test process runs several, and so does
        /// `astra-plugin test`.
        #[tokio::test]
        async fn two_instances_of_one_0_5_plugin_each_get_a_host() {
            let a = Harness::new(LegacyDice::default()).start().await.unwrap();
            let b = Harness::new(LegacyDice::default()).start().await.unwrap();

            for h in [&a, &b] {
                h.call_tool("roll_dice", serde_json::json!({})).await.unwrap();
                assert_eq!(h.fired_triggers().len(), 1);
                assert_eq!(
                    h.plugin()
                        .host_deliveries
                        .load(std::sync::atomic::Ordering::SeqCst),
                    1
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_config_accepts_whatever_the_user_typed() {
        // A user adding settings before the plugin knows about them must not
        // break the plugin.
        serde_json::from_str::<NoConfig>("{}").unwrap();
        serde_json::from_str::<NoConfig>(r#"{"surprise":[1,2,3]}"#).unwrap();
        serde_json::from_str::<NoConfig>("null").unwrap();
        assert_eq!(serde_json::to_string(&NoConfig).unwrap(), "{}");
    }

    #[test]
    fn config_reads_are_lock_free_and_see_the_last_write() {
        let c = Config::new(7u32);
        assert_eq!(**c.load(), 7);
        c.store(9);
        assert_eq!(*c.get(), 9);
    }

    #[test]
    fn stt_load_state_maps_onto_the_daemons_enum() {
        use proto::stt_load_state_response::State;
        let r: proto::SttLoadStateResponse = SttLoadState::Failed("no vram".into()).into();
        assert_eq!(r.state, State::Failed as i32);
        assert_eq!(r.detail, "no vram");
        let r: proto::SttLoadStateResponse = SttLoadState::default().into();
        assert_eq!(r.state, State::NotNeeded as i32);
    }

    #[test]
    fn ai_chunks_map_onto_the_oneof() {
        use proto::plugin_ai_stream_chunk::Content;
        let c: proto::PluginAiStreamChunk = AiChunk::text("hi").into();
        assert!(matches!(c.content, Some(Content::TextDelta(t)) if t == "hi"));
        let c: proto::PluginAiStreamChunk = AiChunk::Done.into();
        assert!(matches!(c.content, Some(Content::Done(true))));
    }

    // ── the fresh install, which is the config case that actually happens ────

    /// A host that remembers what the plugin told the user.
    struct Recorder(std::sync::Mutex<Vec<String>>);

    #[async_trait::async_trait]
    impl crate::Host for Recorder {
        fn plugin_id(&self) -> &str {
            "fresh"
        }
        async fn fire_trigger(&self, _: &str, _: &str) -> anyhow::Result<()> {
            Ok(())
        }
        async fn log(&self, level: &str, message: &str) -> anyhow::Result<()> {
            self.0.lock().unwrap().push(format!("{level}: {message}"));
            Ok(())
        }
        async fn get_config(&self) -> anyhow::Result<String> {
            Ok("{}".into())
        }
        async fn get_daemon_info(&self) -> anyhow::Result<proto::PluginDaemonInfoResponse> {
            Ok(Default::default())
        }
        async fn set_variable(&self, _: &str, _: &str, _: &str) -> anyhow::Result<()> {
            Ok(())
        }
        async fn push_to_ui(&self, _: &str, _: &str) -> anyhow::Result<()> {
            Ok(())
        }
        async fn send_chat_message(
            &self,
            _: &str,
            _: &str,
            _: bool,
        ) -> anyhow::Result<crate::context::ChatStream> {
            Ok(Box::pin(tokio_stream::empty()))
        }
        async fn set_theme_contribution(
            &self,
            _: proto::PluginThemeContribution,
        ) -> anyhow::Result<()> {
            Ok(())
        }
    }

    /// A `Config` with a required field, which is the ordinary way an author
    /// models "the user must supply an API key" — and the shape that silently
    /// never reaches the plugin.
    #[derive(serde::Deserialize, Default)]
    struct Required {
        #[allow(dead_code)]
        api_key: String,
    }

    struct Fresh;
    #[async_trait::async_trait]
    impl PluginCapability for Fresh {
        type Config = Required;
    }

    /// The daemon's first payload to a freshly installed plugin is `{}`, and the
    /// warning about it must not claim there was a previous config.
    ///
    /// "keeping the previous config" is false at startup — there is no previous
    /// config, `on_config` has not run once, and the plugin is about to serve
    /// every call on `Config::default()` with an empty API key. The old message
    /// sent the author looking for a config they had edited; the new one names
    /// the shape that fixes it and the error the author should return instead.
    #[tokio::test]
    async fn a_fresh_install_is_told_it_is_a_fresh_install() {
        for payload in ["", "{}", "  {}  "] {
            let host = std::sync::Arc::new(Recorder(std::sync::Mutex::new(Vec::new())));
            let ctx = PluginContext::new("fresh", host.clone());
            Fresh.on_config_changed(&ctx, payload).await;

            let logs = host.0.lock().unwrap().clone();
            let msg = logs.join("\n");
            assert!(
                msg.contains("no settings saved yet"),
                "payload {payload:?} produced {msg:?}"
            );
            assert!(msg.contains("#[astra::config]"), "{msg}");
            assert!(msg.contains("not_configured"), "{msg}");
            assert!(
                !msg.contains("keeping the previous config"),
                "there is no previous config on a fresh install: {msg}"
            );
        }
    }

    /// And a payload that is genuinely the wrong shape still says so — the two
    /// are different bugs with different fixes.
    #[tokio::test]
    async fn a_wrong_shape_still_keeps_the_previous_config() {
        let host = std::sync::Arc::new(Recorder(std::sync::Mutex::new(Vec::new())));
        let ctx = PluginContext::new("fresh", host.clone());
        Fresh
            .on_config_changed(&ctx, r#"{"api_key":[1,2,3]}"#)
            .await;

        let msg = host.0.lock().unwrap().join("\n");
        assert!(msg.contains("keeping the previous config"), "{msg}");
        assert!(!msg.contains("no settings saved yet"), "{msg}");
    }
}
