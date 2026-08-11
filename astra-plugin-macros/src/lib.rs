// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! Attribute macros for the Astra plugin SDK.
//!
//! **Do not depend on this crate directly.** Everything here is re-exported by
//! `astra-plugin-sdk`, and only that path is stable:
//!
//! ```ignore
//! use astra_plugin_sdk::prelude::*;
//!
//! #[astra::args]
//! struct Roll {
//!     /// How many dice to roll
//!     #[serde(default = "one")] count: u32,
//! }
//!
//! #[derive(Default)]
//! struct Dice;
//!
//! #[astra::plugin]
//! impl Dice {
//!     /// Roll dice and return the total.
//!     #[tool]
//!     async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> { .. }
//! }
//!
//! astra::main!(Dice::default());
//! ```
//!
//! # The rule these macros follow
//!
//! *The expansion is exactly the code the author would have written by hand.*
//! `#[astra::plugin]` emits the author's own `impl` block plus an
//! `impl PluginCapability for T` whose method bodies `match` on a name and call
//! the author's methods. There is no registry, no link-section trick, no
//! generated runtime and no state the author cannot see. `cargo expand` is a
//! supported migration path off the macros: expand, delete the attribute, keep
//! going — `astra-plugin-macros/tests/expansion_is_the_handwritten_impl.rs`
//! keeps a hand-written twin of a macro plugin and asserts they agree.
//!
//! Every path the expansion names is absolute and rooted at the SDK —
//! `::astra_plugin_sdk::tokio`, `::astra_plugin_sdk::serde_json`,
//! `::astra_plugin_sdk::async_trait`. A plugin's `Cargo.toml` has exactly one
//! dependency, so an expansion that said `tokio::` would break the moment the
//! author stopped listing a crate they never call.

use proc_macro::TokenStream;

mod args;
mod config;
mod hooks;
mod main_macro;
mod plugin;

/// Turn an inherent `impl` block into a `PluginCapability` implementation.
///
/// Mark methods inside it with:
///
/// | attribute | becomes |
/// |---|---|
/// | `#[tool]` | an entry in `list_tools`, an arm in `call_tool` |
/// | `#[action]` | an entry in `action_types`, an arm in `execute_action` |
/// | `#[ui_call]` | an arm in `handle_ui_call` |
/// | `#[hook]` | that `PluginCapability` method, moved across verbatim |
///
/// A handler is `async fn name(&self, ctx: &PluginContext, args: T) -> Result<String, ToolError>`.
/// `ctx` and `args` are both optional; `T` is deserialized from the call's JSON
/// and its JSON Schema comes from `schemars` — mark `T` with
/// [`#[astra::args]`](macro@args). The `///` doc comment is the
/// description the model reads, and it is required — a tool the model cannot
/// tell apart from another tool is a tool it will call at random.
///
/// Arguments: `#[astra::plugin(config = MyConfig)]` sets the associated
/// `Config` type (inferred from a `#[hook] on_config`, else `NoConfig`), and
/// `capabilities = "tools, triggers"` overrides the inferred
/// `DeclaredCapabilities::CAPS` — needed when the manifest declares something no
/// hook implies, such as `triggers` for a plugin that only *fires* triggers.
#[proc_macro_attribute]
pub fn plugin(attr: TokenStream, item: TokenStream) -> TokenStream {
    let item: proc_macro2::TokenStream = item.into();
    match plugin::expand(attr.into(), item.clone()) {
        Ok(ts) => ts.into(),
        // Not `e.to_compile_error()` alone: dropping the impl block would take
        // `PluginCapability` and `DeclaredCapabilities` with it, and the author
        // would read three errors — one real, two saying `astra::main!` cannot
        // find traits that are missing *because* of the real one. See
        // `plugin::recover`.
        Err(e) => plugin::recover(e, item).into(),
    }
}

/// `astra::main!(MyPlugin::default());` — the plugin's entry point.
#[proc_macro]
pub fn main(input: TokenStream) -> TokenStream {
    match main_macro::expand(input.into()) {
        Ok(ts) => ts.into(),
        Err(e) => e.to_compile_error().into(),
    }
}

/// The type a tool's JSON arguments deserialize into: `Deserialize` +
/// `JsonSchema`, in a crate whose `Cargo.toml` has one dependency.
///
/// ```ignore
/// #[astra::args]
/// struct Roll {
///     /// How many dice to roll — this line becomes the schema's description.
///     #[serde(default = "one")]
///     count: u32,
/// }
/// ```
///
/// It expands to the plain `#[derive(Deserialize, JsonSchema)]` plus the two
/// `crate = "…"` attributes that tell `serde_derive` and `schemars_derive`
/// where those crates live. `serde_derive` emits
/// `extern crate serde as _serde`, which resolves in the extern prelude and
/// cannot be satisfied by a re-export — so without this the author's second
/// dependency is `serde`, and the first thing they do after `astra-plugin new`
/// is edit `Cargo.toml` to fix `` can't find crate for `serde` ``.
///
/// Also the config type's other half: `#[astra::args]` next to
/// `#[derive(Default, PluginConfig)]` is a complete settings type.
///
/// Adding `serde` to your own dependencies is a supported choice — do that and
/// `#[derive(Deserialize, JsonSchema)]` from the prelude works directly.
#[proc_macro_attribute]
pub fn args(attr: TokenStream, item: TokenStream) -> TokenStream {
    match args::expand(attr.into(), item.into()) {
        Ok(ts) => ts.into(),
        Err(e) => e.to_compile_error().into(),
    }
}

/// A plugin's settings type: [`#[astra::args]`](macro@args) plus
/// `#[serde(default)]` at the container level and `#[derive(PluginConfig)]`.
///
/// ```ignore
/// #[astra::config]
/// #[derive(Default)]
/// struct Settings {
///     /// Paste the key from your provider's dashboard.
///     api_key: String,
/// }
///
/// impl Settings {
///     fn key(&self) -> Result<&str, ToolError> {
///         if self.api_key.is_empty() {
///             return Err(ToolError::not_configured("api_key"));
///         }
///         Ok(&self.api_key)
///     }
/// }
/// ```
///
/// # Why it is not `#[astra::args]`
///
/// A required field is right for tool arguments and wrong for settings. The
/// daemon's **first** config payload to a freshly installed plugin is `{}` —
/// the user has not opened the Settings page yet. A config type with a required
/// field rejects it, `on_config_changed` logs one warning, and `on_config` is
/// never called at all: the plugin runs on `Default` with an empty key and
/// fails later somewhere that names nothing useful.
///
/// `#[serde(default)]` makes `{}` parse, so "not configured" becomes a value
/// the author tests for and answers with `ToolError::not_configured("api_key")`,
/// which carries the field name the UI turns into a link.
#[proc_macro_attribute]
pub fn config(attr: TokenStream, item: TokenStream) -> TokenStream {
    match args::expand_config(attr.into(), item.into()) {
        Ok(ts) => ts.into(),
        Err(e) => e.to_compile_error().into(),
    }
}

// ── the two names a re-export cannot supply ──────────────────────────────────
//
// `serde_derive` emits `extern crate serde as _serde;`, which resolves in the
// EXTERN prelude — the crate graph — and nowhere else. No `pub use` can put
// `serde` there. So a prelude that re-exported `serde::Deserialize` handed the
// author a name that resolves and then fails inside someone else's expansion
// with `` can't find crate for `serde` ``, naming a Cargo.toml line the
// scaffold's own comments say not to add. rustc's canned advice
// (`#[derive(serde::Deserialize)]`) loops straight back to the same note.
//
// These two derives occupy those names instead and say the one thing that is
// true: in a one-dependency plugin the answer is `#[astra::args]`. An author who
// does add `serde` writes `use serde::Deserialize;`, and an explicit import
// shadows a glob import, so that path keeps working unchanged.

/// Placeholder for `serde`'s `Deserialize` derive, so that the mistake the
/// scaffold invites has an answer instead of `` can't find crate for `serde` ``.
///
/// Reachable only through `astra_plugin_sdk::prelude::*`. `use serde::Deserialize;`
/// shadows it.
#[proc_macro_derive(Deserialize, attributes(serde))]
pub fn derive_deserialize_shim(_item: TokenStream) -> TokenStream {
    serde_shim("Deserialize", "args")
}

/// Placeholder for `serde`'s `Serialize` derive. See
/// [`Deserialize`](derive@Deserialize).
#[proc_macro_derive(Serialize, attributes(serde))]
pub fn derive_serialize_shim(_item: TokenStream) -> TokenStream {
    serde_shim("Serialize", "args")
}

fn serde_shim(name: &str, attr: &str) -> TokenStream {
    // `{{` / `}}` are `format!` escapes; the emitted text is a `compile_error!`.
    format!(
        r#"::core::compile_error!{{"`#[derive({name})]` cannot work in a plugin \
whose Cargo.toml lists only `astra-plugin-sdk`: serde's derive expands to \
`extern crate serde`, which resolves in the crate graph and cannot be reached \
through a re-export.\n\
fix: write `#[astra::{attr}]` above the type instead — it is \
`#[derive(Deserialize, JsonSchema)]` pointed at the SDK's own copy of both \
crates. For a settings type, `#[astra::config]`.\n\
or: add `serde = {{ version = \"1\", features = [\"derive\"] }}` to your \
Cargo.toml and write `use serde::{name};` — an explicit import shadows the \
prelude's glob and this message goes away."}}"#
    )
    .parse()
    .expect("generated compile_error! must parse")
}

/// Stand-in for `schemars`' `JsonSchema` derive when the SDK's `schema` feature
/// is off.
///
/// Reachable only as `astra_plugin_sdk::schema::schemars::JsonSchema`, which is
/// what `#[astra::args]` expands to — under `--no-default-features` that path
/// resolves here and the author is told which flag to flip, instead of being
/// shown a missing module inside the SDK. The `schemars` helper attribute is
/// registered so `#[schemars(crate = "…")]` beside it is not a second,
/// unrelated error.
#[proc_macro_derive(JsonSchema, attributes(schemars))]
pub fn derive_json_schema_feature_off(_item: TokenStream) -> TokenStream {
    r#"::core::compile_error!{"no JSON Schema to derive: the SDK's `schema` \
       feature is off.\nfix: drop `default-features = false` from \
       astra-plugin-sdk in Cargo.toml, or write the schema by hand with \
       `#[tool(schema = ...)]` and drop `#[astra::args]`."}"#
        .parse()
        .expect("generated compile_error! must parse")
}

/// Mark a type as a plugin's settings: implements `PluginConfig` (whose
/// `json_schema()` is what `plugin.toml`'s `[config] schema` is generated from)
/// and asserts at compile time that the type both `Deserialize`s and has a
/// `Default`.
#[proc_macro_derive(PluginConfig)]
pub fn derive_plugin_config(item: TokenStream) -> TokenStream {
    match config::expand(item.into()) {
        Ok(ts) => ts.into(),
        Err(e) => e.to_compile_error().into(),
    }
}

// ── markers ──────────────────────────────────────────────────────────────────
//
// `#[astra::plugin]` consumes these before the compiler ever resolves them, so
// these definitions exist for exactly one reason: a marker written *outside* a
// `#[astra::plugin]` block would otherwise fail with "cannot find attribute
// `tool` in this scope", which names neither the cause nor the fix.

macro_rules! stray_marker {
    ($name:ident, $shown:literal) => {
        #[doc = concat!("Only meaningful inside an `#[astra::plugin]` impl block.")]
        #[proc_macro_attribute]
        pub fn $name(_attr: TokenStream, item: TokenStream) -> TokenStream {
            let mut out: TokenStream = format!(
                "::core::compile_error!{{\"`{}` only means something inside an \
                 `#[astra::plugin]` impl block, which is what expands it.\\n\
                 fix: add `#[astra::plugin]` above the `impl` block this method \
                 is in.\"}}",
                $shown
            )
            .parse()
            .expect("generated compile_error! must parse");
            // Keep the item, so the author sees this one error and not a
            // cascade of "cannot find function" from every call site.
            out.extend(item);
            out
        }
    };
}

stray_marker!(tool, "#[tool]");
stray_marker!(action, "#[action]");
stray_marker!(ui_call, "#[ui_call]");
stray_marker!(hook, "#[hook]");
