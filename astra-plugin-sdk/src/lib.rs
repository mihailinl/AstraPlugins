// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! Astra Plugin SDK — build plugins for Astra in Rust.
//!
//! # Quick Start
//!
//! ```rust,no_run
//! use astra_plugin_sdk::prelude::*;
//!
//! struct MyPlugin;
//!
//! #[async_trait]
//! impl PluginCapability for MyPlugin {
//!     // Required, and one line when there are no settings. See `NoConfig`.
//!     type Config = NoConfig;
//!
//!     async fn list_tools(&self) -> Vec<ToolDef> {
//!         vec![ToolDef::new("hello", "Say hello")]
//!     }
//!
//!     async fn call_tool(
//!         &self,
//!         ctx: &PluginContext,
//!         name: &str,
//!         _args: &str,
//!     ) -> Result<String, ToolError> {
//!         ctx.host().log_info("saying hello").await?;
//!         Ok(format!("Hello from {name}!"))
//!     }
//! }
//!
//! #[tokio::main]
//! async fn main() -> anyhow::Result<()> {
//!     astra_plugin_sdk::run(MyPlugin).await
//! }
//! ```
//!
//! # The three things to know
//!
//! **Handlers are given a [`PluginContext`].** It carries the host client, the
//! daemon's UI language and the set of live triggers, it is cheap to clone into
//! a background task, and it is never `None`. Nothing has to be stored on your
//! struct behind a lock. From a place a parameter cannot reach, [`ctx()`].
//!
//! **Handlers return `Result`.** A per-call failure is *data* — the AI loop
//! reads it and decides what to do — so [`ToolError`] travels in the response,
//! not as a gRPC `Status`. `?` works on `serde_json::Error`, `std::io::Error`,
//! `tonic::Status` and `anyhow::Error`.
//!
//! **Config is typed.** Declare [`PluginCapability::Config`] and implement
//! [`on_config`](PluginCapability::on_config); the SDK parses, and reports a
//! payload that does not fit rather than running on stale settings in silence.
//!
//! # Testing
//!
//! [`testing`] ships with the SDK, so a plugin's `Cargo.toml` still has one
//! line in it. Two levels:
//! [`Harness`](testing::Harness) runs the hooks in process against a
//! [`RecordingHost`](testing::RecordingHost) — no daemon, no socket — and
//! [`WireHarness`](testing::WireHarness) starts the plugin the way the daemon
//! starts it and drives it over gRPC, which is the only level that can see
//! registration, the session token, and the streaming paths.

pub mod proto {
    tonic::include_proto!("astra");
}

mod auth;
mod capability;
mod context;
mod daemon_client;
mod error;
pub mod events;
mod host_client;
pub mod i18n;
pub mod limits;
pub mod logging;
pub mod panics;
pub mod plural;
pub mod protocol;
mod runner;
pub mod testing;
pub mod wire;

pub use auth::CapabilityAuth;
pub use capability::*;
pub use context::{
    ActiveTriggers, ChatStream, Daemon, EventStream, FirehoseStream, Host, PluginContext, ctx,
    install_context, try_ctx,
};
pub use daemon_client::DaemonClient;
pub use error::{ActionError, HookUnimplemented, ToolError, ToolErrorCode, unimplemented};
pub use host_client::HostClient;
pub use i18n::{I18n, key};
pub use panics::Panicked;
pub use protocol::{EXIT_PROTOCOL_INCOMPATIBLE, MIN_SUPPORTED_DAEMON_PROTOCOL, PROTOCOL_VERSION};
pub use runner::{RunConfig, run, run_with};

// ── The macro layer ──────────────────────────────────────────────────────────

/// `astra::main!`, `#[astra::plugin]`, and the markers that go inside it.
///
/// The module exists so that `use astra_plugin_sdk::prelude::*;` puts the
/// macros behind a short, obvious prefix instead of dropping four bare names
/// called `tool`, `action`, `hook` and `main` into the author's crate root.
///
/// ```ignore
/// use astra_plugin_sdk::prelude::*;
///
/// #[astra::args]
/// struct Roll {
///     /// How many dice to roll
///     #[serde(default = "one")] count: u32,
///     /// Sides per die
///     #[serde(default = "six")] sides: u32,
/// }
///
/// #[derive(Default)]
/// struct Dice;
///
/// #[astra::plugin]
/// impl Dice {
///     /// Roll dice and return the total.
///     #[tool]
///     async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
///         Ok(roll(a).to_string())
///     }
/// }
///
/// astra::main!(Dice::default());
/// ```
///
/// [`#[astra::args]`](macro@astra_plugin_macros::args) is the one that looks
/// like decoration and is not: `serde_derive` emits
/// `extern crate serde as _serde`, which resolves in the extern prelude and
/// cannot be reached through a re-export, so a plain
/// `#[derive(Deserialize, JsonSchema)]` needs `serde` in the plugin's own
/// `Cargo.toml`. `#[astra::args]` expands to that derive plus the two
/// `crate = "…"` attributes that point both derives at the SDK, and is the
/// reason a plugin with typed tool arguments still has one dependency.
pub mod astra {
    pub use astra_plugin_macros::{action, args, config, hook, main, plugin, tool, ui_call};
}

pub use astra_plugin_macros::PluginConfig;

/// The crates the macro expansion names, re-exported so it can name them
/// absolutely.
///
/// A plugin's `Cargo.toml` has one dependency. That is only true if nothing the
/// macros emit says `tokio::`, `serde_json::` or `async_trait` — those paths
/// would resolve today, off the author's own dependency list, and stop
/// resolving the moment they delete a line for a crate they never call. Every
/// path in an expansion is `::astra_plugin_sdk::…`, and these are what makes
/// that legal.
///
/// They are public API for the macros, not for hand-written code — use the real
/// crates if you want them; nothing stops you adding them back.
pub use {anyhow, async_trait::async_trait, serde, serde_json, tokio, tonic};

/// The `[capabilities]` a plugin binary was built to serve.
///
/// `#[astra::plugin]` implements this from the hooks it actually found, so the
/// answer is derived from code rather than asserted by hand. `astra::main!`
/// feeds it to [`RunConfig::capabilities`], which is what `--print-capabilities`
/// prints — so `astra-plugin check` can ask a *built binary* what it declares
/// and compare that against `plugin.toml`, instead of trusting the manifest
/// alone.
///
/// The manifest still wins at registration: the daemon passes `--capabilities`
/// from the file the user consented to, and the SDK prefers it. This is what
/// makes a disagreement between the two *visible* rather than decisive.
pub trait DeclaredCapabilities {
    /// Sorted, deduplicated manifest capability keys — `"tools"`, `"tts"`, ….
    const CAPS: &'static [&'static str];
}

/// A plugin's settings type, as produced by `#[astra::config]` (or by
/// `#[derive(PluginConfig)]` on its own, when serde is already yours).
///
/// The one thing a config type has that a plain `Deserialize` struct does not
/// is a JSON Schema the Settings page can render and `plugin.toml` can carry.
pub trait PluginConfig {
    /// The JSON Schema for this type — an object-rooted schema, ready to paste
    /// into `plugin.toml`'s `[config] schema`.
    fn json_schema() -> String;
}

/// What a `#[derive(PluginConfig)]` type has to be, as one bound with one error
/// message.
///
/// Three requirements, and each earns its place:
///
/// * **`Deserialize`**, because the daemon sends settings as JSON.
/// * **`Default`**, because `on_config_changed` parses that payload and the
///   *first* payload a plugin ever receives is `{}` — a fresh install has no
///   stored settings. A config struct without defaults rejects it, logs a
///   warning on a machine that is not the author's, and runs on nothing.
/// * **`JsonSchema`**, because the only thing a config type has that a plain
///   `Deserialize` struct does not is the schema the Settings page renders.
///   That is what the derive is *for*; without it there is nothing to derive.
///
/// One bound, so a type that is missing any of the three gets this note rather
/// than three unrelated ones from three different call sites.
#[diagnostic::on_unimplemented(
    message = "`{Self}` cannot be a plugin config type",
    label = "needs `Deserialize`, `Default` and `JsonSchema`",
    note = "a complete config type is `#[astra::config]` above \
            `#[derive(Default)]` — `#[astra::config]` supplies `Deserialize`, \
            `JsonSchema` and `PluginConfig` without a `serde` dependency of \
            your own, and puts `#[serde(default)]` on the container",
    note = "`Default` stays yours to write, because `#[serde(default)]` needs \
            it: the daemon's first payload to a freshly installed plugin is \
            `{{}}`, and a config type that rejects it never reaches \
            `on_config` at all",
    note = "if the SDK's `schema` feature is off there is no `JsonSchema` to \
            derive; drop `default-features = false` from astra-plugin-sdk"
)]
pub trait ConfigShape: Default + serde::de::DeserializeOwned + schema::JsonSchema {}

impl<T> ConfigShape for T where T: Default + serde::de::DeserializeOwned + schema::JsonSchema {}

/// JSON Schema generation, behind the `schema` feature (on by default).
///
/// `#[tool]` calls [`schema::of`] on a handler's argument type to produce the
/// `parameters_json` the model sees. Turning the feature off drops `schemars`
/// from the build and turns that call into one named compile error rather than
/// a mystery.
pub mod schema {
    /// Re-exported so a plugin can `#[derive(JsonSchema)]` without depending on
    /// `schemars` itself.
    #[cfg(feature = "schema")]
    pub use schemars::{self, JsonSchema};

    /// The JSON Schema for `T`, as the object-rooted JSON a `ToolDef` carries.
    ///
    /// `$schema` is stripped: it is metadata about the schema document, and the
    /// value here is a *parameters* object embedded in a tool definition, not a
    /// document. Several model providers reject unknown top-level keys.
    #[cfg(feature = "schema")]
    pub fn of<T: JsonSchema>() -> String {
        let mut schema = schemars::SchemaGenerator::default().into_root_schema_for::<T>();
        schema.remove("$schema");
        serde_json::to_string(&schema)
            .unwrap_or_else(|_| r#"{"type":"object","properties":{}}"#.to_string())
    }

    /// Stand-in for `schemars::JsonSchema` when the `schema` feature is off, so
    /// that `#[tool]` fails with a sentence instead of a missing path.
    #[cfg(not(feature = "schema"))]
    #[diagnostic::on_unimplemented(
        message = "no JSON Schema for `{Self}`: the SDK's `schema` feature is off",
        note = "re-enable it — drop `default-features = false` from \
                astra-plugin-sdk in Cargo.toml",
        note = "or write the schema yourself: `#[tool(schema = r#\"{{\"type\":\"object\"}}\"#)]`"
    )]
    pub trait JsonSchema {}

    #[cfg(not(feature = "schema"))]
    pub fn of<T: JsonSchema + ?Sized>() -> String {
        unreachable!("no type implements the `schema`-disabled JsonSchema stand-in")
    }

    /// Stand-in for the `schemars` crate when the `schema` feature is off.
    ///
    /// `#[astra::args]` expands to
    /// `#[derive(::astra_plugin_sdk::schema::schemars::JsonSchema)]`, and that
    /// path has to resolve to *something* in every feature configuration or the
    /// author's error is "could not find `schemars` in `schema`" — a report
    /// about the SDK's internals rather than about their build. It resolves
    /// here, and says which flag to flip.
    #[cfg(not(feature = "schema"))]
    pub mod schemars {
        pub use astra_plugin_macros::JsonSchema;
    }

    /// [`of`], but bounded on [`ConfigShape`](crate::ConfigShape) so that a
    /// config type missing any of `Deserialize` / `Default` / `JsonSchema`
    /// produces exactly one error, on the author's own type, naming all three.
    ///
    /// This is what `#[derive(PluginConfig)]` calls. Calling `of` there instead
    /// would report only the missing `JsonSchema`, from inside the SDK, and say
    /// nothing about the `Default` that matters more.
    pub fn of_config<T: crate::ConfigShape>() -> String {
        of::<T>()
    }
}

/// Everything a plugin normally needs, in one `use`.
pub mod prelude {
    pub use crate::capability::*;
    pub use crate::context::{ActiveTriggers, Daemon, Host, PluginContext, ctx, try_ctx};
    pub use crate::daemon_client::DaemonClient;
    pub use crate::error::{ActionError, ToolError, ToolErrorCode};
    pub use crate::events::{CommandCompletedEvent, CommandTriggeredEvent, StateChangedEvent};
    pub use crate::host_client::HostClient;
    pub use crate::i18n::{I18n, key};
    pub use crate::{CapabilityAuth, RunConfig, run, run_with};
    pub use async_trait::async_trait;

    /// `anyhow`, `tokio` and `serde_json`, under their own names.
    ///
    /// Not a convenience — a requirement of "one dependency". Several
    /// `PluginCapability` hooks *spell these crates in their own signatures*:
    /// `tts_synthesize` returns `anyhow::Result<AudioData>` and `ai_complete`
    /// takes a `tokio::sync::mpsc::Sender<AiChunk>`. An author whose
    /// `Cargo.toml` lists only `astra-plugin-sdk` has no other way to write
    /// those two type names down. `serde_json` is here because a plugin that
    /// handles arbitrary JSON — `execute_action`'s `params_json`, say — needs
    /// `from_str` and `Value`, and `json!` alone does not cover it.
    ///
    /// Not re-exported: `serde`. `serde_derive` emits
    /// `extern crate serde as _serde`, which resolves in the extern prelude and
    /// nowhere else, so a re-export cannot make `#[derive(Deserialize)]` work
    /// in a crate that does not list `serde`. That is what `#[astra::args]` is
    /// for. The crate is still reachable as `astra_plugin_sdk::serde`.
    pub use crate::{anyhow, serde_json, tokio};

    // The macro layer. `astra::` is a module, not a crate: `#[astra::plugin]`
    // and `astra::main!` both resolve through it.
    pub use crate::astra;
    pub use crate::{ConfigShape, DeclaredCapabilities, PluginConfig};

    // Bare `#[tool]` / `#[action]` / `#[ui_call]` / `#[hook]`, so the markers
    // read the way they do in the docs. `#[astra::plugin]` consumes them before
    // they are ever expanded; these definitions exist so that one written
    // outside a plugin impl reports what it is instead of "cannot find
    // attribute".
    pub use astra_plugin_macros::{action, hook, tool, ui_call};

    /// `Deserialize` and `Serialize` — the two names a re-export **cannot**
    /// supply, occupying their own slot so the failure is a sentence.
    ///
    /// These are not serde's derives. `serde_derive` emits
    /// `extern crate serde as _serde;`, which resolves in the *extern* prelude —
    /// the crate graph — and nowhere else, so no `pub use` can make
    /// `#[derive(Deserialize)]` work in a crate whose `Cargo.toml` lists only
    /// `astra-plugin-sdk`. Re-exporting the real derive here handed the author a
    /// name that resolved and then failed inside someone else's expansion with
    /// `` can't find crate for `serde` ``, naming the one Cargo.toml line the
    /// scaffold's own comments say not to add — and rustc's canned advice
    /// (`#[derive(serde::Deserialize)]`) loops straight back to the same note.
    ///
    /// What stands here instead says the true thing: in a one-dependency plugin
    /// the answer is [`#[astra::args]`](macro@astra_plugin_macros::args), or
    /// [`#[astra::config]`](macro@astra_plugin_macros::config) for settings.
    ///
    /// **Adding `serde` yourself keeps working.** `use serde::Deserialize;` is
    /// an explicit import and shadows a glob one, so a crate that lists serde
    /// and imports it by name never sees these at all.
    pub use astra_plugin_macros::{Deserialize, Serialize};

    // The schema half, which *does* survive a re-export: `schemars_derive`
    // emits path-based `schemars::…`, and the prelude puts that name in scope.
    #[cfg(feature = "schema")]
    pub use crate::schema::JsonSchema;

    /// The `schemars` crate itself, under its own name.
    ///
    /// Not decoration: `#[derive(JsonSchema)]` expands to paths that begin
    /// `schemars::`, unqualified, so the name has to *be in scope* in the
    /// author's module or the derive fails with "unresolved module or unlinked
    /// crate `schemars`" — in a crate whose `Cargo.toml` correctly lists one
    /// dependency and will never list that one. Glob-importing the prelude puts
    /// it there.
    ///
    /// Without the prelude glob, name it explicitly instead:
    /// `#[schemars(crate = "astra_plugin_sdk::schema::schemars")]`.
    ///
    /// `astra-plugin-macros/tests/expansion_is_the_handwritten_impl.rs` derives
    /// `JsonSchema` from a crate that does not depend on `schemars`, so this
    /// stops working loudly rather than in someone else's project.
    #[cfg(feature = "schema")]
    pub use crate::schema::schemars;

    /// `serde_json::json!` without a `serde_json` dependency — §3.1's
    /// `json!({ "total": total })` in a crate whose Cargo.toml has one line.
    pub use serde_json::{Value as JsonValue, json};
}
