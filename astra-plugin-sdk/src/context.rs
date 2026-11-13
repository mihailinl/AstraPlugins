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

    /// The user's chat provider, model and endpoint — never a key.
    /// Permission: `read_ai_settings`.
    ///
    /// For a plugin that calls the user's model itself: ask Astra, never read
    /// Astra's files for it. `provider` is `openai_compatible` for an endpoint
    /// the user saved, `astra` (with an empty `api_base_url`) for Astra's own
    /// service. An Astra older than this RPC answers `UNIMPLEMENTED`.
    ///
    /// Defaulted on purpose, like [`Host::fire_trigger_caused_by`]: a `Host`
    /// written before this method existed (a test double, a fake in someone
    /// else's crate) keeps compiling, and answers with an error that says so
    /// instead of inventing settings. Every `Host` in this crate — the client,
    /// the forwarding wrappers, the testing hosts — overrides it, and
    /// `tests::every_in_repo_host_answers_get_ai_settings_without_the_default`
    /// turns red for one that forgets.
    async fn get_ai_settings(&self) -> Result<proto::PluginAiSettings> {
        Err(anyhow::anyhow!(
            "this Host does not implement GetAiSettings (get_ai_settings)"
        ))
    }

    /// Say `text` aloud in Astra's voice. Permission: `speak` — **high-risk**,
    /// its own consent checkbox, because the words are heard as Astra's.
    ///
    /// Besides the grant it needs an account that opens Astra, and the person's
    /// reply voice on. The call lasts as long as the speech, and answers with
    /// what became of it — read [`outcome()`](proto::PluginSpeakResponse::outcome):
    ///
    /// * `PluginSpeechOutcome::Spoken` — it was heard.
    /// * `PluginSpeechOutcome::Stopped` — silence was asked for before it
    ///   finished: the wake word, reply voice turned off, Stop, your own
    ///   [`stop_speaking`](Self::stop_speaking). **Not an error**; do not say it
    ///   again unasked.
    /// * `PluginSpeechOutcome::NotSpoken` — it was not said, and `error` (a
    ///   [`proto::PluginError`], the same message a chat chunk's `error_detail`
    ///   carries) says why: `PluginErrorBadArguments` for an empty text or one
    ///   longer than [`limits::SPEAK_TEXT_MAX_CHARS`](crate::limits::SPEAK_TEXT_MAX_CHARS)
    ///   characters (refused, never cut); `PluginErrorRateLimited` with
    ///   `retry_after_ms` once this plugin's speaking time is used up (450
    ///   characters at once, then 3 a second, each call costing at least 20);
    ///   `PluginErrorUnavailable` while voice is off, Astra is locked, there is
    ///   no voice, or the speech queue could not take it. Nothing refused is
    ///   queued.
    ///
    /// ```ignore
    /// use astra_plugin_sdk::proto::{PluginErrorCode, PluginSpeechOutcome};
    ///
    /// let said = ctx.host().speak("The kettle has boiled.").await?;
    /// if said.outcome() == PluginSpeechOutcome::NotSpoken {
    ///     let why = said.error.unwrap_or_default();
    ///     if why.code() == PluginErrorCode::PluginErrorRateLimited {
    ///         // wait why.retry_after_ms, or show the text instead
    ///     }
    /// }
    /// ```
    ///
    /// Your words queue behind your own earlier ones on a lane of their own, so
    /// they never cut Astra's replies. A refusal by the daemon's gates (no
    /// grant, no account that opens Astra) is an `Err`, like every host call.
    /// An Astra older than this RPC answers `UNIMPLEMENTED`.
    ///
    /// Defaulted, like [`Host::get_ai_settings`]: a `Host` written before this
    /// method existed keeps compiling and answers with an error that says so,
    /// never an invented outcome. Every `Host` in this crate overrides it.
    async fn speak(&self, text: &str) -> Result<proto::PluginSpeakResponse> {
        let _ = text;
        Err(anyhow::anyhow!("this Host does not implement Speak (speak)"))
    }

    /// Stop everything this plugin asked to be said, sounding and queued.
    /// Permission: `speak` — stopping your own speech is part of speaking.
    ///
    /// Never touches anything else Astra is saying, and is allowed whether or
    /// not anybody is signed in. Each [`speak`](Self::speak) it cuts answers
    /// `PluginSpeechOutcome::Stopped`. Defaulted like [`Host::speak`].
    async fn stop_speaking(&self) -> Result<()> {
        Err(anyhow::anyhow!(
            "this Host does not implement StopSpeaking (stop_speaking)"
        ))
    }

    /// Who is using Astra, as THIS plugin may know it.
    /// Permission: `read_user_identity` (not high-risk).
    ///
    /// Both ids are pseudonyms made for this plugin alone: another plugin reads
    /// different ones for the same person and machine, so two plugins using
    /// this API cannot join their records on them (it holds against honest
    /// plugins: native plugin code can read Astra's files, and neither id is a
    /// secret). Never the account's own id, a name, an email or a hardware
    /// serial.
    ///
    /// * `install_id` — this installation of Astra, stable across restarts and
    ///   updates; empty while Astra has no installation key yet.
    /// * `signed_in` — a person is signed in; `authorized` — and their account
    ///   opens Astra.
    /// * `account_id` — the signed-in account, the same on every device the
    ///   person signs in on; empty unless `authorized`. The same value arrives
    ///   as `account_id` on this plugin's `auth_changed` events.
    ///
    /// An Astra older than this RPC answers `UNIMPLEMENTED`. Defaulted like
    /// [`Host::speak`].
    async fn get_user_identity(&self) -> Result<proto::PluginUserIdentity> {
        Err(anyhow::anyhow!(
            "this Host does not implement GetUserIdentity (get_user_identity)"
        ))
    }

    /// **Ask the person** to change some of Astra's settings, on a card they
    /// answer. Permission: `request_settings_change` (not high-risk: nothing
    /// changes without the person's Allow). It also needs an account that opens
    /// Astra, and **no Astra release answers it yet**: an Astra built without
    /// the `plugin-requests` feature answers `Refused` / `not_compiled`, and
    /// one older than 2026-11-13 — every release today — fails the call with
    /// `UNIMPLEMENTED`, an `Err`, not an outcome.
    ///
    /// Only the settings the assistant itself may change can be asked for (the
    /// voice, the AI model, the language — never the permission mode, a key or
    /// Tool Search), each value checked exactly as the assistant's own change
    /// is. The card names this plugin, each setting as it is and as it would
    /// be, and `reason` (the plugin's own words). What changes on Allow is
    /// exactly what the card showed; all of `changes` change, or none.
    ///
    /// The call **lasts until the person answers or the card expires** —
    /// Astra's confirmation timeout, at least 30 s, 120 s unless the person
    /// changed it. Never await it on a path that must answer quickly; the SDK
    /// puts no deadline of its own on it. Read
    /// [`outcome()`](proto::PluginSettingsChangeResponse::outcome):
    ///
    /// * `PluginSettingsChangeOutcome::Applied` — the person allowed it; the
    ///   settings now hold what was asked for.
    /// * `PluginSettingsChangeOutcome::Unchanged` — they already held it.
    ///   Nobody was asked.
    /// * `PluginSettingsChangeOutcome::Declined` — the person said no, now or
    ///   to this plugin changing one of these settings before (Astra asks
    ///   again about a setting only after it has changed some other way, or
    ///   after a restart). **Do not ask again unasked.**
    /// * `PluginSettingsChangeOutcome::TimedOut` — nobody answered before the
    ///   card expired (no window open counts).
    /// * `PluginSettingsChangeOutcome::Refused` — not asked, or not applied:
    ///   `code` says why, `refused_path` names the setting when it is about
    ///   one, and `error` is the same as a [`proto::PluginError`] — a sentence,
    ///   and `retry_after_ms` for `rate_limited`. The words: `not_compiled`
    ///   (this Astra takes no requests: it was built without the
    ///   `plugin-requests` feature), `locked`, `invalid` (no changes, a path
    ///   twice, a value that is not JSON, or more than a card can show whole),
    ///   `too_many` (more than
    ///   [`limits::SETTINGS_CHANGE_MAX_CHANGES`](crate::limits::SETTINGS_CHANGE_MAX_CHANGES)),
    ///   `reason_too_long` (more than
    ///   [`limits::SETTINGS_CHANGE_REASON_MAX_CHARS`](crate::limits::SETTINGS_CHANGE_REASON_MAX_CHARS)
    ///   characters — refused, never cut), `busy` (one of this plugin's
    ///   requests is already waiting), `rate_limited` (a burst of two, then
    ///   one every two minutes), `not_assistant_editable`, `invalid_value`,
    ///   `unknown_choice`, `needs_api_key`, `needs_stt_provider`,
    ///   `provider_unreachable`, `stale` (the settings changed while the card
    ///   was up), `stopped` (this plugin's authority ended first),
    ///   `write_refused`.
    ///
    /// The current values are never returned: what the plugin learns is the
    /// outcome.
    ///
    /// ```ignore
    /// use astra_plugin_sdk::proto::{PluginSettingChange, PluginSettingsChangeOutcome};
    ///
    /// let asked = ctx
    ///     .host()
    ///     .request_settings_change(
    ///         &[PluginSettingChange::new("ai.model", "gpt-4.1")],
    ///         "PrimeAI's tools are tuned for this model",
    ///     )
    ///     .await?;
    /// match asked.outcome() {
    ///     PluginSettingsChangeOutcome::Applied | PluginSettingsChangeOutcome::Unchanged => {}
    ///     PluginSettingsChangeOutcome::Refused if asked.code == "rate_limited" => {
    ///         // ask later: asked.error.unwrap_or_default().retry_after_ms
    ///     }
    ///     _ => {} // declined, timed out, refused: carry on with what the person has
    /// }
    /// ```
    ///
    /// The daemon is the authority on every limit; the SDK checks none, so it
    /// can never disagree with the Astra it talks to. A refusal by the
    /// daemon's gates (no grant, no account that opens Astra) is an `Err`,
    /// like every host call. An Astra older than this RPC answers
    /// `UNIMPLEMENTED`.
    ///
    /// Defaulted, like [`Host::speak`]: a `Host` written before this method
    /// existed keeps compiling and answers with an error that says so, never
    /// an invented outcome. Every `Host` in this crate overrides it.
    async fn request_settings_change(
        &self,
        changes: &[proto::PluginSettingChange],
        reason: &str,
    ) -> Result<proto::PluginSettingsChangeResponse> {
        let _ = (changes, reason);
        Err(anyhow::anyhow!(
            "this Host does not implement RequestSettingsChange (request_settings_change)"
        ))
    }

    /// **Offer the person a command** to keep, on a card they answer.
    /// Permission: `propose_commands` (**high-risk**: a command the person
    /// keeps runs later, on its own triggers, as the person's own command — its
    /// steps, built-ins such as a shell command included, run without asking
    /// again). It also needs an account that opens Astra, and **no Astra
    /// release answers it yet**: an Astra built without the `plugin-requests`
    /// feature answers `Refused` / `not_compiled`, and one older than
    /// 2026-11-13 — every release today — fails the call with `UNIMPLEMENTED`,
    /// an `Err`, not an outcome.
    ///
    /// `key` is this plugin's own name for the command — 1 to 64 characters of
    /// `a-z`, `A-Z`, `0-9`, `.`, `_` and `-`; the same key offered again is the
    /// same command, updated in place. `command_json` is ONE portable command
    /// as JSON (what a `.astra` file's `commands[]` holds — split a file with
    /// [`commands_from_astra_file`](crate::commands_from_astra_file)), read by
    /// the same reader as a Workshop command: strict JSON, known action and
    /// trigger types only, the local fields (id, switch, folder, provenance)
    /// dropped, and it may use Astra's built-in actions and triggers and **this
    /// plugin's own** — never another plugin's. `reason` is the plugin's own
    /// words, shown on the card.
    ///
    /// The card names this plugin and the command and offers Review / Deny;
    /// the command is kept only from Astra's Workshop sheet, which shows every
    /// trigger by its full value and every step with what it may do, and an
    /// Enable switch — never by a bare Allow. What is kept is exactly what the
    /// sheet showed.
    ///
    /// The call **lasts until the person answers or the card expires** —
    /// Astra's confirmation timeout, at least 30 s, 120 s unless the person
    /// changed it. Never await it on a path that must answer quickly; the SDK
    /// puts no deadline of its own on it. Offer one command at a time: a second
    /// offer while one is waiting is `busy`, even one that would be
    /// `Unchanged`. Read
    /// [`outcome()`](proto::PluginProposeCommandResponse::outcome):
    ///
    /// * `PluginProposeCommandOutcome::Saved` — the person kept it; `enabled`
    ///   says whether the command is on after it was kept (Astra may keep it
    ///   switched off). Record it.
    /// * `PluginProposeCommandOutcome::Unchanged` — what is kept under this
    ///   key came from this very offer — also after the person edited it.
    ///   Nobody was asked.
    /// * `PluginProposeCommandOutcome::Declined` — the person said no, now or
    ///   to this very command before (until Astra restarts). Record it: **do
    ///   not offer it again unasked.** Astra's own memory of a no ends at a
    ///   restart, and a command the person deleted is offered as new.
    /// * `PluginProposeCommandOutcome::TimedOut` — nobody answered before the
    ///   card expired (no window open counts).
    /// * `PluginProposeCommandOutcome::Refused` — not asked, or not kept:
    ///   `code` says why, and `error` is the same as a [`proto::PluginError`] —
    ///   a sentence, and `retry_after_ms` for `rate_limited`. The words:
    ///   `not_compiled` (this Astra takes no offers: it was built without the
    ///   `plugin-requests` feature), `locked`, `invalid_key`, `reason_too_long`
    ///   (more than
    ///   [`limits::PROPOSE_COMMAND_REASON_MAX_CHARS`](crate::limits::PROPOSE_COMMAND_REASON_MAX_CHARS)
    ///   characters — refused, never cut), `too_large` (more than
    ///   [`limits::PROPOSE_COMMAND_MAX_BYTES`](crate::limits::PROPOSE_COMMAND_MAX_BYTES)
    ///   bytes of JSON), `invalid_command` (`error.message` usually leads with
    ///   the Workshop's own code: `E_COMMAND_FORMAT`,
    ///   `E_COMMAND_UNKNOWN_ACTION`, … — not when the card itself cannot be
    ///   shown), `foreign_plugin` (it uses another plugin's action or trigger),
    ///   `busy` (one of this plugin's offers is already waiting),
    ///   `rate_limited` (a burst of two, then one every two minutes), `stopped`
    ///   (this plugin's authority ended first), `stale` (the command it updates
    ///   changed or went while the card was up), `write_refused`.
    ///
    /// ```ignore
    /// use astra_plugin_sdk::commands_from_astra_file;
    /// use astra_plugin_sdk::proto::PluginProposeCommandOutcome;
    ///
    /// let commands = commands_from_astra_file(include_str!("../morning.astra"))?;
    /// let offered = ctx
    ///     .host()
    ///     .propose_command(
    ///         "morning-briefing",
    ///         &serde_json::to_string(&commands[0])?,
    ///         "Reads you the news when you say good morning",
    ///     )
    ///     .await?;
    /// match offered.outcome() {
    ///     PluginProposeCommandOutcome::Saved | PluginProposeCommandOutcome::Unchanged => {}
    ///     PluginProposeCommandOutcome::Refused if offered.code == "rate_limited" => {
    ///         // offer later: offered.error.unwrap_or_default().retry_after_ms
    ///     }
    ///     _ => {} // declined, timed out, refused: the person goes without it
    /// }
    /// ```
    ///
    /// The daemon is the authority on every limit; the SDK checks none, so it
    /// can never disagree with the Astra it talks to. A refusal by the
    /// daemon's gates (no grant, no account that opens Astra) is an `Err`,
    /// like every host call. An Astra older than this RPC answers
    /// `UNIMPLEMENTED`.
    ///
    /// Defaulted, like [`Host::speak`]: a `Host` written before this method
    /// existed keeps compiling and answers with an error that says so, never
    /// an invented outcome. Every `Host` in this crate overrides it.
    async fn propose_command(
        &self,
        key: &str,
        command_json: &str,
        reason: &str,
    ) -> Result<proto::PluginProposeCommandResponse> {
        let _ = (key, command_json, reason);
        Err(anyhow::anyhow!(
            "this Host does not implement ProposeCommand (propose_command)"
        ))
    }

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
    ///
    /// # Where it lands
    ///
    /// An empty `conversation_id` posts to this plugin's own durable thread,
    /// which is the right default for anything that is not an answer to a
    /// specific call. Pass an id only when you were TOLD one: the chunks of a
    /// reply you are streaming carry it, and so does
    /// [`PluginContext::invocation`] inside a tool call or an action. An id from
    /// an invocation may be stored, across restarts, and sent back later.
    ///
    /// # Never await this inside the call that told you the id
    ///
    /// **This is a deadlock, not a slow path.** The conversation that invoked
    /// your tool is still running the turn that is waiting for your answer. A
    /// message declares an intent for the *next* turn, so it queues behind that
    /// one — and the turn cannot finish until your tool returns. Awaiting the
    /// reply from inside the handler waits for a turn that is waiting for you,
    /// and the call times out.
    ///
    /// Spawn it, or send later:
    ///
    /// ```ignore
    /// let host = ctx.host().clone();
    /// let id = ctx.invocation().and_then(|i| i.conversation()).map(str::to_string);
    /// tokio::spawn(async move {
    ///     if let Some(id) = id {
    ///         let _ = host.send_chat_message("done", &id, false).await;
    ///     }
    /// });
    /// return Ok("started".into());          // the turn can now finish
    /// ```
    ///
    /// # Two things your text is not
    ///
    /// A message beginning `/` reaches the model as those literal characters.
    /// A plugin cannot invoke a slash command by writing one, and cannot
    /// supersede a person's turn by writing one.
    ///
    /// And the stream always ends. A line that reached the conversation but
    /// that no turn will answer ends it with an error chunk — `INTERNAL`,
    /// *"this message reached the conversation, but no turn will answer it"* —
    /// whose hint says not to resend. It was delivered; sending it again posts
    /// it twice.
    ///
    /// # When the conversation is gone
    ///
    /// A stored id can name a deleted conversation. That is refused, never
    /// redirected: `NOT_FOUND` whose message begins `conversation_gone:` —
    /// forget the id and fall back to your own thread. `INVALID_ARGUMENT` means
    /// the id is not a UUID, or names a chat an Astra surface owns. A message
    /// that was accepted and then outlived its chat ends the stream with an
    /// error chunk whose `error_detail.code` is `PLUGIN_ERROR_NOT_FOUND`. A
    /// daemon older than this contract says `INTERNAL`, *"chat processing
    /// failed: conversation … does not exist"*, for the same situation.
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

impl proto::PluginSettingChange {
    /// One setting for [`Host::request_settings_change`]: a dotted settings
    /// path the assistant may change (`ai.model`, `voice.tts_speed`) and the
    /// value wanted, serialised to JSON for `value_json`.
    ///
    /// Anything `serde_json::Value` is made from works — `"gpt-4.1"`, `true`,
    /// `1.2`, or `serde_json::json!(…)`. A float JSON cannot hold (`NaN`,
    /// infinity) becomes `null`, as `serde_json` always makes it.
    ///
    /// ```
    /// use astra_plugin_sdk::proto::PluginSettingChange;
    ///
    /// let change = PluginSettingChange::new("voice.tts_speed", 1.2);
    /// assert_eq!(change.path, "voice.tts_speed");
    /// assert_eq!(change.value_json, "1.2");
    /// assert_eq!(PluginSettingChange::new("ai.model", "gpt-4.1").value_json, r#""gpt-4.1""#);
    /// ```
    pub fn new(path: impl Into<String>, value: impl Into<serde_json::Value>) -> Self {
        Self {
            path: path.into(),
            value_json: value.into().to_string(),
        }
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
/// What the daemon said about the ONE call being handled.
///
/// Reached through [`PluginContext::invocation`], and `None` unless this
/// handler is running a tool call or an action. Every other hook — UI calls,
/// triggers, TTS, STT, AI — gets `None`, because the daemon does not send an
/// invocation on those and an SDK must never invent one.
///
/// # What `None` means, and what it does not
///
/// `None` means **this call was not made from a conversation**, and it is the
/// answer for several different situations that a plugin cannot tell apart and
/// does not need to:
///
/// - nothing conversational caused the call — a trigger fired, a timer ran, the
///   user pressed something in your own UI;
/// - the run that caused it has no conversation to name, such as a nested agent
///   or a `SendToAi` run;
/// - the daemon predates this field.
///
/// It is **never** a reason to guess. Do not fall back to "the conversation the
/// user is looking at": there is no such API, on purpose, and a plugin that
/// posted into a chat the user never pointed at would be doing something nobody
/// asked for.
///
/// # Storing it
///
/// [`conversation`](Self::conversation) returns a UUID you MAY keep, including
/// across restarts, and send back later as the conversation to post into. That
/// is the whole point of the field: a plugin told "you were called from here"
/// can answer there later, as itself.
///
/// The conversation can be deleted while you hold the id. See the send path's
/// own documentation for the error that says so and for the one rule that
/// matters: never await a send into the conversation that is calling you, from
/// inside that call.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
#[non_exhaustive]
pub struct Invocation {
    conversation: Option<String>,
}

impl Invocation {
    /// Build one. Mostly for tests and harnesses — the runner builds the real
    /// ones off the wire.
    ///
    /// An empty string is normalised to `None`: on the wire `""` is how a
    /// daemon says "no conversation", and letting it through as `Some("")`
    /// would hand plugins an id that can never resolve.
    pub fn new(conversation: Option<impl Into<String>>) -> Self {
        let conversation = conversation.map(Into::into).filter(|c| !c.is_empty());
        Self { conversation }
    }

    /// The conversation whose turn made this call, or `None`.
    ///
    /// A UUID. Safe to store and send back later; see the type's documentation
    /// for what `None` covers and why it is not a cue to guess.
    pub fn conversation(&self) -> Option<&str> {
        self.conversation.as_deref()
    }
}

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
    /// What the daemon said about this one call. Beside `inner` for the same
    /// reason `scoped_host` is: it varies per invocation, and `Inner` must not.
    ///
    /// `Arc` so that cloning a context — which every forwarded hook does — stays
    /// a refcount bump rather than a string copy.
    invocation: Option<Arc<Invocation>>,
    /// The pictures the person attached, for the one tool call being handled
    /// ([`attachments`](Self::attachments)). Beside `inner` for the reason
    /// `invocation` is, and `Arc` for the same reason again: up to 20 MiB must
    /// not be copied by every clone. `None` is "none", so a context with no
    /// pictures costs nothing.
    attachments: Option<Arc<[crate::AiImage]>>,
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
    /// This plugin's `locales/`, read once, on first use.
    ///
    /// Lazy rather than eager because most plugins ship no locale files and
    /// would pay a `read_dir` on every start for nothing — and because
    /// `PluginContext::new` is public API a test calls with a fake host, in a
    /// working directory that is nobody's plugin.
    i18n: std::sync::OnceLock<crate::I18n>,
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
            // A context built at startup belongs to no call. The runner scopes
            // a per-invocation clone for the two hooks that have one.
            invocation: None,
            attachments: None,
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
                i18n: std::sync::OnceLock::new(),
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
    /// the conversation that made the call. That property rides in
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
                invocation: self.invocation.clone(),
                attachments: self.attachments.clone(),
            },
            None => self.clone(),
        }
    }

    /// This context, carrying what the daemon said about one call.
    ///
    /// Separate from [`for_invocation`](Self::for_invocation), and applied
    /// after it, because the two read different halves of the same RPC: the
    /// cause lease is in the request's METADATA and is readable before the body
    /// is, while the invocation is a field IN the body and is not readable
    /// until `into_inner()`. The runner does the metadata half as the request
    /// arrives and this half once it has the message.
    ///
    /// `None` clears it, so an arm that has no invocation cannot inherit one
    /// from a context it was cloned from.
    pub(crate) fn with_invocation(mut self, invocation: Option<Invocation>) -> Self {
        self.invocation = invocation.map(Arc::new);
        self
    }

    /// What the daemon said about the call being handled, or `None`.
    ///
    /// `Some` only inside a tool call or an action, and only when that call was
    /// made from a conversation. See [`Invocation`] for everything `None`
    /// covers — it is several situations, and none of them is a cue to guess a
    /// conversation.
    ///
    /// ```ignore
    /// async fn call_tool(&self, ctx: &PluginContext, name: &str, args: &str)
    ///     -> Result<String, ToolError>
    /// {
    ///     if let Some(id) = ctx.invocation().and_then(|i| i.conversation()) {
    ///         self.remember(id);           // safe to store, across restarts
    ///     }
    ///     Ok("done".into())
    /// }
    /// ```
    pub fn invocation(&self) -> Option<&Invocation> {
        self.invocation.as_deref()
    }

    /// This context, carrying the pictures handed to one tool call.
    ///
    /// Applied by the runner to the `CallTool` arm only, once it has the
    /// message — the pictures are a field in the BODY, like the invocation. An
    /// empty list clears them, so no arm can inherit another call's pictures
    /// from the context it was cloned from.
    pub(crate) fn with_attachments(mut self, attachments: Vec<crate::AiImage>) -> Self {
        self.attachments = (!attachments.is_empty()).then(|| Arc::from(attachments));
        self
    }

    /// The pictures the person attached to the message THIS tool call answers,
    /// in the order attached — [`AiImage`](crate::AiImage)s: `mime_type`,
    /// `data` (the bytes, never re-encoded) and `filename` (the bare name).
    ///
    /// Empty everywhere else: outside a tool call, for a tool that did not
    /// declare `wants_attachments` on its [`ToolDef`](crate::ToolDef) (or
    /// `#[tool(wants_attachments)]`), and whenever Astra sent none. Astra
    /// sends them only to a tool that declared it, of a plugin granted the
    /// `receive_attachments` permission, on a call made while answering a
    /// message the person sent in a conversation, and only when built with the
    /// `plugin-provider-slots` build feature — which no release has yet. At most
    /// [`IMAGE_INPUT_MAX_IMAGES`](crate::limits::IMAGE_INPUT_MAX_IMAGES) (4)
    /// pictures and 20 MiB, the newest kept; when some were not sent, the model
    /// is told so after your result.
    ///
    /// ```ignore
    /// /// Describe the picture the person attached.
    /// #[tool(wants_attachments)]
    /// async fn describe_photo(&self, ctx: &PluginContext) -> Result<String, ToolError> {
    ///     let Some(photo) = ctx.attachments().first() else {
    ///         return Ok("No picture was attached.".into());
    ///     };
    ///     Ok(format!("{}: {} bytes of {}", photo.filename, photo.data.len(), photo.mime_type))
    /// }
    /// ```
    pub fn attachments(&self) -> &[crate::AiImage] {
        self.attachments.as_deref().unwrap_or(&[])
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
    ///
    /// Also moves [`i18n`](Self::i18n), if anything has asked for it yet, so
    /// that the runtime plane follows the user's language whether or not the
    /// author has heard of `OnLanguageChanged`. That hook stays advisory: an
    /// optional override an author has to implement is not a mechanism a
    /// user's language can depend on.
    pub fn set_language(&self, language: impl Into<String>) {
        let language = language.into();
        if let Some(i18n) = self.inner.i18n.get() {
            i18n.set_language(&language);
        }
        self.inner.language.store(Arc::new(language));
    }

    /// This plugin's translations, for the **runtime** plane.
    ///
    /// Loaded from `locales/` on first use — see [`I18n::discover`] for where
    /// it looks — and kept on the context's current language from then on, so
    /// a handler never has to remember to call `set_language`.
    ///
    /// For anything the DAEMON renders (action labels, config-field titles,
    /// `[ui]` labels) use [`crate::key`] instead. See the [`crate::i18n`]
    /// module docs for why the difference matters.
    ///
    /// ```rust,no_run
    /// # use astra_plugin_sdk::PluginContext;
    /// # fn f(ctx: &PluginContext, n: i64) -> String {
    /// ctx.i18n().tn("msg.done", n, &[("n", &n.to_string())])
    /// # }
    /// ```
    pub fn i18n(&self) -> &crate::I18n {
        self.inner.i18n.get_or_init(|| {
            let i18n = crate::I18n::discover();
            i18n.set_language(&self.language());
            i18n
        })
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

    async fn get_ai_settings(&self) -> Result<proto::PluginAiSettings> {
        self.inner.get_ai_settings().await
    }

    // The five below are defaulted on `Host`, so forgetting one here would
    // compile and answer "this Host does not implement …" from inside a
    // handler while the real client underneath implements it perfectly well.
    // `tests::the_scoping_wrapper_forwards_speech_and_identity`,
    // `tests::the_scoping_wrapper_forwards_settings_requests` and
    // `tests::the_scoping_wrapper_forwards_command_offers` are the guards.

    async fn speak(&self, text: &str) -> Result<proto::PluginSpeakResponse> {
        self.inner.speak(text).await
    }

    async fn stop_speaking(&self) -> Result<()> {
        self.inner.stop_speaking().await
    }

    async fn get_user_identity(&self) -> Result<proto::PluginUserIdentity> {
        self.inner.get_user_identity().await
    }

    async fn request_settings_change(
        &self,
        changes: &[proto::PluginSettingChange],
        reason: &str,
    ) -> Result<proto::PluginSettingsChangeResponse> {
        self.inner.request_settings_change(changes, reason).await
    }

    async fn propose_command(
        &self,
        key: &str,
        command_json: &str,
        reason: &str,
    ) -> Result<proto::PluginProposeCommandResponse> {
        self.inner.propose_command(key, command_json, reason).await
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
    /// Every `speak` text, and `"<stop>"` for each `stop_speaking`, in order —
    /// so a test can tell "forwarded to the inner host" from "answered by the
    /// trait's default".
    spoken: std::sync::Mutex<Vec<String>>,
    /// Every `request_settings_change`, as it arrived — the same proof for
    /// the settings request.
    asked: std::sync::Mutex<Vec<proto::PluginSettingsChangeRequest>>,
    /// Every `propose_command`, as it arrived — the same proof for the offer.
    offered: std::sync::Mutex<Vec<proto::PluginProposeCommandRequest>>,
}

#[cfg(test)]
impl CauseSpy {
    pub(crate) fn causes(&self) -> Vec<Option<String>> {
        self.fires.lock().unwrap().iter().map(|(_, c)| c.clone()).collect()
    }

    pub(crate) fn spoken(&self) -> Vec<String> {
        self.spoken.lock().unwrap().clone()
    }

    pub(crate) fn asked(&self) -> Vec<proto::PluginSettingsChangeRequest> {
        self.asked.lock().unwrap().clone()
    }

    pub(crate) fn offered(&self) -> Vec<proto::PluginProposeCommandRequest> {
        self.offered.lock().unwrap().clone()
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
    async fn get_ai_settings(&self) -> Result<proto::PluginAiSettings> {
        Ok(proto::PluginAiSettings {
            provider: "from-inner".into(),
            ..Default::default()
        })
    }
    async fn speak(&self, text: &str) -> Result<proto::PluginSpeakResponse> {
        self.spoken.lock().unwrap().push(text.to_owned());
        Ok(proto::PluginSpeakResponse {
            outcome: proto::PluginSpeechOutcome::Spoken as i32,
            error: None,
        })
    }
    async fn stop_speaking(&self) -> Result<()> {
        self.spoken.lock().unwrap().push("<stop>".to_owned());
        Ok(())
    }
    async fn get_user_identity(&self) -> Result<proto::PluginUserIdentity> {
        Ok(proto::PluginUserIdentity {
            install_id: "from-inner".into(),
            ..Default::default()
        })
    }
    async fn request_settings_change(
        &self,
        changes: &[proto::PluginSettingChange],
        reason: &str,
    ) -> Result<proto::PluginSettingsChangeResponse> {
        self.asked
            .lock()
            .unwrap()
            .push(proto::PluginSettingsChangeRequest {
                changes: changes.to_vec(),
                reason: reason.to_owned(),
            });
        Ok(proto::PluginSettingsChangeResponse {
            outcome: proto::PluginSettingsChangeOutcome::Applied as i32,
            ..Default::default()
        })
    }
    async fn propose_command(
        &self,
        key: &str,
        command_json: &str,
        reason: &str,
    ) -> Result<proto::PluginProposeCommandResponse> {
        self.offered
            .lock()
            .unwrap()
            .push(proto::PluginProposeCommandRequest {
                key: key.to_owned(),
                command_json: command_json.to_owned(),
                reason: reason.to_owned(),
            });
        Ok(proto::PluginProposeCommandResponse {
            outcome: proto::PluginProposeCommandOutcome::Saved as i32,
            enabled: true,
            ..Default::default()
        })
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
        async fn get_ai_settings(&self) -> Result<proto::PluginAiSettings> {
            Ok(Default::default())
        }
        async fn speak(&self, _: &str) -> Result<proto::PluginSpeakResponse> {
            Ok(proto::PluginSpeakResponse {
                outcome: proto::PluginSpeechOutcome::Spoken as i32,
                error: None,
            })
        }
        async fn stop_speaking(&self) -> Result<()> {
            Ok(())
        }
        async fn get_user_identity(&self) -> Result<proto::PluginUserIdentity> {
            Ok(Default::default())
        }
        async fn request_settings_change(
            &self,
            _: &[proto::PluginSettingChange],
            _: &str,
        ) -> Result<proto::PluginSettingsChangeResponse> {
            Ok(proto::PluginSettingsChangeResponse {
                outcome: proto::PluginSettingsChangeOutcome::Unchanged as i32,
                ..Default::default()
            })
        }
        async fn propose_command(
            &self,
            _: &str,
            _: &str,
            _: &str,
        ) -> Result<proto::PluginProposeCommandResponse> {
            Ok(proto::PluginProposeCommandResponse {
                outcome: proto::PluginProposeCommandOutcome::Unchanged as i32,
                ..Default::default()
            })
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

    /// A `Host` that never heard of `get_ai_settings`, `speak`,
    /// `stop_speaking`, `get_user_identity`, `request_settings_change` or
    /// `propose_command`: the defaulted methods.
    struct BareHost;

    #[async_trait::async_trait]
    impl Host for BareHost {
        fn plugin_id(&self) -> &str {
            "bare"
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

    /// Additive: a `Host` written before `get_ai_settings` compiles unchanged
    /// and gets a plain error, not invented settings.
    #[tokio::test]
    async fn a_host_without_get_ai_settings_answers_with_a_plain_error() {
        let err = BareHost.get_ai_settings().await.unwrap_err().to_string();
        assert!(err.contains("does not implement GetAiSettings"), "{err}");
    }

    /// The forwarding wrapper (`for_invocation` scopes through `CausalHost`)
    /// must reach the inner host's answer, not fall to the default error.
    #[tokio::test]
    async fn the_scoping_wrapper_forwards_get_ai_settings() {
        let (ctx, _spy) = spied();
        let scoped = ctx.for_invocation(Some(Arc::from("lease-1")));
        let got = scoped.host().get_ai_settings().await.expect("forwarded, not defaulted");
        assert_eq!(got.provider, "from-inner");
    }

    /// Every `Host` impl in this crate answers without the default. A wrapper
    /// or fake added later that forgets to override goes red here: add it to
    /// the list.
    #[tokio::test]
    async fn every_in_repo_host_answers_get_ai_settings_without_the_default() {
        let recording = crate::testing::RecordingHost::new("rec");
        recording.set_ai_settings(proto::PluginAiSettings {
            provider: "staged".into(),
            ..Default::default()
        });
        let hosts: Vec<(&str, Arc<dyn Host>)> = vec![
            ("testing::RecordingHost", recording),
            ("NullHost", Arc::new(NullHost)),
        ];
        for (name, h) in hosts {
            h.get_ai_settings()
                .await
                .unwrap_or_else(|e| panic!("{name} fell to the default: {e}"));
        }
    }

    /// Additive: a `Host` written before `Speak`, `StopSpeaking` and
    /// `GetUserIdentity` compiles unchanged and gets a plain error for each —
    /// never an invented outcome or an invented identity.
    #[tokio::test]
    async fn a_host_without_speech_or_identity_answers_with_plain_errors() {
        let err = BareHost.speak("hello").await.unwrap_err().to_string();
        assert!(err.contains("does not implement Speak"), "{err}");
        let err = BareHost.stop_speaking().await.unwrap_err().to_string();
        assert!(err.contains("does not implement StopSpeaking"), "{err}");
        let err = BareHost.get_user_identity().await.unwrap_err().to_string();
        assert!(err.contains("does not implement GetUserIdentity"), "{err}");
    }

    /// The scoped host a handler is given (`for_invocation` wraps the real one
    /// in `CausalHost`) must reach the inner host for all three, not fall to
    /// the trait's defaults — those compile, so only this test notices.
    #[tokio::test]
    async fn the_scoping_wrapper_forwards_speech_and_identity() {
        let (ctx, spy) = spied();
        let scoped = ctx.for_invocation(Some(Arc::from("lease-1")));

        let said = scoped.host().speak("The kettle has boiled.").await.expect("forwarded");
        assert_eq!(said.outcome(), proto::PluginSpeechOutcome::Spoken);
        scoped.host().stop_speaking().await.expect("forwarded");
        let who = scoped.host().get_user_identity().await.expect("forwarded");
        assert_eq!(who.install_id, "from-inner");

        assert_eq!(
            spy.spoken(),
            vec!["The kettle has boiled.".to_string(), "<stop>".to_string()]
        );
        // Speaking is not a fire: nothing about it spends or carries the lease.
        assert!(spy.causes().is_empty());
    }

    /// Every `Host` impl in this crate answers the three without the default.
    /// Add a new wrapper or fake to the list.
    #[tokio::test]
    async fn every_in_repo_host_answers_speech_and_identity_without_the_default() {
        let recording = crate::testing::RecordingHost::new("rec");
        let hosts: Vec<(&str, Arc<dyn Host>)> = vec![
            ("testing::RecordingHost", recording),
            ("NullHost", Arc::new(NullHost)),
        ];
        for (name, h) in hosts {
            h.speak("hi")
                .await
                .unwrap_or_else(|e| panic!("{name}.speak fell to the default: {e}"));
            h.stop_speaking()
                .await
                .unwrap_or_else(|e| panic!("{name}.stop_speaking fell to the default: {e}"));
            h.get_user_identity()
                .await
                .unwrap_or_else(|e| panic!("{name}.get_user_identity fell to the default: {e}"));
        }
    }

    /// Additive: a `Host` written before `RequestSettingsChange` compiles
    /// unchanged and gets a plain error — never an invented outcome, least of
    /// all an `Applied` nobody allowed.
    #[tokio::test]
    async fn a_host_without_settings_requests_answers_with_a_plain_error() {
        let err = BareHost
            .request_settings_change(&[proto::PluginSettingChange::new("ai.model", "m")], "why")
            .await
            .unwrap_err()
            .to_string();
        assert!(
            err.contains("does not implement RequestSettingsChange"),
            "{err}"
        );
    }

    /// The scoped host a handler is given must reach the inner host's
    /// `request_settings_change` with the changes and the reason as written,
    /// not fall to the trait's default.
    #[tokio::test]
    async fn the_scoping_wrapper_forwards_settings_requests() {
        let (ctx, spy) = spied();
        let scoped = ctx.for_invocation(Some(Arc::from("lease-1")));

        let changes = [
            proto::PluginSettingChange::new("ai.model", "gpt-4.1"),
            proto::PluginSettingChange::new("voice.tts_speed", 1.2),
        ];
        let asked = scoped
            .host()
            .request_settings_change(&changes, "tuned for this model")
            .await
            .expect("forwarded");
        assert_eq!(asked.outcome(), proto::PluginSettingsChangeOutcome::Applied);
        assert_eq!(
            spy.asked(),
            vec![proto::PluginSettingsChangeRequest {
                changes: changes.to_vec(),
                reason: "tuned for this model".into(),
            }]
        );
        // Asking is not a fire: nothing about it spends or carries the lease.
        assert!(spy.causes().is_empty());
    }

    /// Every `Host` impl in this crate answers `request_settings_change`
    /// without the default. Add a new wrapper or fake to the list.
    #[tokio::test]
    async fn every_in_repo_host_answers_settings_requests_without_the_default() {
        let recording = crate::testing::RecordingHost::new("rec");
        let hosts: Vec<(&str, Arc<dyn Host>)> = vec![
            ("testing::RecordingHost", recording),
            ("NullHost", Arc::new(NullHost)),
        ];
        let change = [proto::PluginSettingChange::new("ai.model", "m")];
        for (name, h) in hosts {
            h.request_settings_change(&change, "why")
                .await
                .unwrap_or_else(|e| {
                    panic!("{name}.request_settings_change fell to the default: {e}")
                });
        }
    }

    /// The level-1 host records what was asked for and answers what was
    /// staged — `Applied` by default, any outcome when told — and a denied
    /// grant is an `Err` with nothing on the record.
    #[tokio::test]
    async fn the_recording_host_records_settings_requests_and_answers_what_was_staged() {
        let host = crate::testing::RecordingHost::new("rec");
        let change = [proto::PluginSettingChange::new("ai.model", "gpt-4.1")];

        let asked = host.request_settings_change(&change, "why").await.unwrap();
        assert_eq!(asked.outcome(), proto::PluginSettingsChangeOutcome::Applied);

        host.set_settings_change_response(proto::PluginSettingsChangeResponse {
            outcome: proto::PluginSettingsChangeOutcome::Refused as i32,
            refused_path: "ai.model".into(),
            code: "needs_api_key".into(),
            error: Some(proto::PluginError {
                message: "the provider needs a key first".into(),
                ..Default::default()
            }),
        });
        let asked = host
            .request_settings_change(&change, "again")
            .await
            .unwrap();
        assert_eq!(asked.outcome(), proto::PluginSettingsChangeOutcome::Refused);
        assert_eq!(
            (asked.code.as_str(), asked.refused_path.as_str()),
            ("needs_api_key", "ai.model")
        );

        let recorded = host.settings_change_requests();
        assert_eq!(recorded.len(), 2);
        assert_eq!(recorded[0].changes, change.to_vec());
        assert_eq!(recorded[1].reason, "again");

        host.deny("request_settings_change");
        assert!(host.request_settings_change(&change, "no").await.is_err());
        assert_eq!(
            host.settings_change_requests().len(),
            2,
            "a denied call asked nobody"
        );
        assert_eq!(host.recorded().call_count("request_settings_change"), 3);
    }

    /// `value_json` is the value as JSON — any JSON value, compact, strings
    /// quoted and escaped — so the daemon reads back exactly what was meant.
    #[test]
    fn a_setting_change_serialises_its_value_as_json() {
        use proto::PluginSettingChange as C;
        assert_eq!(C::new("ai.model", "gpt-4.1").value_json, r#""gpt-4.1""#);
        assert_eq!(C::new("voice.enabled", true).value_json, "true");
        assert_eq!(C::new("voice.tts_speed", 1.2).value_json, "1.2");
        assert_eq!(C::new("ai.max_tool_rounds", 24).value_json, "24");
        assert_eq!(C::new("x", serde_json::Value::Null).value_json, "null");
        assert_eq!(
            C::new("x", serde_json::json!({"a": [1, "two"]})).value_json,
            r#"{"a":[1,"two"]}"#
        );
        assert_eq!(C::new("x", "say \"hi\"\n").value_json, r#""say \"hi\"\n""#);
        // `path` is carried as written: checking it is the daemon's job.
        assert_eq!(C::new(String::from("ai.model"), "m").path, "ai.model");
    }

    /// Additive: a `Host` written before `ProposeCommand` compiles unchanged
    /// and gets a plain error — never an invented outcome, least of all a
    /// `Saved` nobody kept.
    #[tokio::test]
    async fn a_host_without_command_offers_answers_with_a_plain_error() {
        let err = BareHost
            .propose_command("k", "{}", "why")
            .await
            .unwrap_err()
            .to_string();
        assert!(err.contains("does not implement ProposeCommand"), "{err}");
    }

    /// The scoped host a handler is given must reach the inner host's
    /// `propose_command` with the key, the JSON and the reason as written, not
    /// fall to the trait's default.
    #[tokio::test]
    async fn the_scoping_wrapper_forwards_command_offers() {
        let (ctx, spy) = spied();
        let scoped = ctx.for_invocation(Some(Arc::from("lease-1")));

        let json = r#"{"name":"Morning","triggers":[],"actions":[]}"#;
        let offered = scoped
            .host()
            .propose_command("morning", json, "reads you the news")
            .await
            .expect("forwarded");
        assert_eq!(offered.outcome(), proto::PluginProposeCommandOutcome::Saved);
        assert!(offered.enabled);
        assert_eq!(
            spy.offered(),
            vec![proto::PluginProposeCommandRequest {
                key: "morning".into(),
                command_json: json.into(),
                reason: "reads you the news".into(),
            }]
        );
        // Offering is not a fire: nothing about it spends or carries the lease.
        assert!(spy.causes().is_empty());
    }

    /// Every `Host` impl in this crate answers `propose_command` without the
    /// default. Add a new wrapper or fake to the list.
    #[tokio::test]
    async fn every_in_repo_host_answers_command_offers_without_the_default() {
        let recording = crate::testing::RecordingHost::new("rec");
        let hosts: Vec<(&str, Arc<dyn Host>)> = vec![
            ("testing::RecordingHost", recording),
            ("NullHost", Arc::new(NullHost)),
        ];
        for (name, h) in hosts {
            h.propose_command("k", "{}", "why")
                .await
                .unwrap_or_else(|e| panic!("{name}.propose_command fell to the default: {e}"));
        }
    }

    /// The level-1 host records what was offered and answers what was staged —
    /// `Saved` and switched on by default, any outcome when told — and a denied
    /// grant is an `Err` with nothing on the record.
    #[tokio::test]
    async fn the_recording_host_records_command_offers_and_answers_what_was_staged() {
        let host = crate::testing::RecordingHost::new("rec");
        let json = r#"{"name":"Morning"}"#;

        let offered = host.propose_command("morning", json, "why").await.unwrap();
        assert_eq!(offered.outcome(), proto::PluginProposeCommandOutcome::Saved);
        assert!(offered.enabled);

        host.set_command_offer_response(proto::PluginProposeCommandResponse {
            outcome: proto::PluginProposeCommandOutcome::Refused as i32,
            code: "foreign_plugin".into(),
            error: Some(proto::PluginError {
                message: "the command uses the plugin `other`".into(),
                ..Default::default()
            }),
            ..Default::default()
        });
        let offered = host
            .propose_command("morning", json, "again")
            .await
            .unwrap();
        assert_eq!(
            offered.outcome(),
            proto::PluginProposeCommandOutcome::Refused
        );
        assert_eq!(offered.code, "foreign_plugin");
        assert!(!offered.enabled);

        let recorded = host.command_offers();
        assert_eq!(recorded.len(), 2);
        assert_eq!(
            (recorded[0].key.as_str(), recorded[0].command_json.as_str()),
            ("morning", json)
        );
        assert_eq!(recorded[1].reason, "again");

        host.deny("propose_command");
        assert!(host.propose_command("morning", json, "no").await.is_err());
        assert_eq!(
            host.command_offers().len(),
            2,
            "a denied call offered nothing"
        );
        assert_eq!(host.recorded().call_count("propose_command"), 3);
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
