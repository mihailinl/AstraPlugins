//! `#[astra::args]` — the type on the other side of the JSON boundary.
//!
//! # Why this attribute has to exist
//!
//! §3.1's plugin has one dependency, and the moment a tool takes structured
//! arguments the author writes `#[derive(Deserialize, JsonSchema)]`. Those two
//! derives behave differently, and only one of them survives a re-export:
//!
//! * `schemars_derive` emits **path-based** `schemars::…`, so glob-importing
//!   the prelude (which re-exports `schemars` under its own name) is enough.
//! * `serde_derive` emits `extern crate serde as _serde;`, which resolves in the
//!   **extern prelude** and nowhere else. No re-export can satisfy it. In a
//!   crate that does not list `serde`, `#[derive(Deserialize)]` fails with
//!   `` can't find crate for `serde` `` — pointing at a Cargo.toml line the
//!   whole design says should not be there.
//!
//! Both crates accept `crate = "<path>"` to be told where they live. That is
//! all this attribute does, and it is why it is an *attribute* and not a derive:
//! a derive can only add items, and what is needed here is two more attributes
//! on the author's own type.
//!
//! # The expansion
//!
//! ```ignore
//! #[astra::args]
//! struct Roll { count: u32 }
//! ```
//!
//! becomes, exactly:
//!
//! ```ignore
//! #[derive(::astra_plugin_sdk::serde::Deserialize)]
//! #[serde(crate = "::astra_plugin_sdk::serde")]
//! #[derive(::astra_plugin_sdk::schema::schemars::JsonSchema)]
//! #[schemars(crate = "::astra_plugin_sdk::schema::schemars")]
//! struct Roll { count: u32 }
//! ```
//!
//! Four lines an author can paste in place of the attribute and keep going —
//! or replace with the plain `#[derive(Deserialize, JsonSchema)]` from the
//! prelude the moment they add `serde` to their own dependencies, which nothing
//! stops them doing.
//!
//! `#[serde(…)]` and `#[schemars(…)]` attributes the author already wrote are
//! left where they are; both crates merge repeated attributes, so
//! `#[serde(default)]` next to a generated `#[serde(crate = …)]` is exactly
//! `#[serde(default, crate = …)]`.
//!
//! # Its twin: `#[astra::config]`
//!
//! Settings are the same two derives with one difference that matters — see
//! [`expand_config`]. It is a separate attribute rather than an option because
//! a *required field* is right for tool arguments (the model is told, and can
//! fix a call that omits one) and wrong for settings (the daemon's first
//! payload to a freshly installed plugin is `{}`).

use proc_macro2::TokenStream;
use quote::quote;
use syn::spanned::Spanned;
use syn::{DeriveInput, Item};

pub fn expand(attr: TokenStream, item: TokenStream) -> syn::Result<TokenStream> {
    check(
        &attr,
        &item,
        "#[astra::args]",
        "it is the type a tool's JSON arguments deserialize into",
        "move it onto the argument type, and mark the handler that takes it \
         with `#[tool]`",
    )?;

    Ok(quote! {
        #[derive(::astra_plugin_sdk::serde::Deserialize)]
        #[serde(crate = "::astra_plugin_sdk::serde")]
        #[derive(::astra_plugin_sdk::schema::schemars::JsonSchema)]
        #[schemars(crate = "::astra_plugin_sdk::schema::schemars")]
        #item
    })
}

/// `#[astra::config]` — `#[astra::args]` plus the two things that make a type a
/// plugin's *settings* rather than a tool's arguments.
///
/// # Why this is not `#[astra::args]`
///
/// A required field means opposite things on the two sides of the boundary.
///
/// On a **tool argument** it is correct: the schema says `required: ["count"]`,
/// the model is told, and a call that omits it is the model's mistake to fix.
///
/// On **settings** it is a trap, and it is the trap §5.2 exists to close. The
/// daemon's first payload to a freshly installed plugin is `{}` — nothing is
/// configured yet, because the user has not opened the Settings page. A config
/// type with a required field rejects that payload,
/// `PluginCapability::on_config_changed` logs one `WARN` on a machine that is
/// not the author's, and `on_config` is never called even once: the plugin runs
/// on whatever `Default` gave it, with an empty API key, and fails later
/// somewhere unrelated.
///
/// So this attribute adds `#[serde(default)]` at the container level. A fresh
/// `{}` always parses, "not configured" becomes a *value* the author can test
/// for, and the answer to it is
/// `ToolError::NotConfigured { field: "api_key", .. }` — which carries a
/// deep-link to that exact settings field.
///
/// It also derives `PluginConfig`, because a settings type that has no schema
/// has nothing for the Settings page to render.
///
/// # The expansion
///
/// ```ignore
/// #[astra::config]
/// #[derive(Default)]
/// struct Settings { api_key: String }
/// ```
///
/// becomes, exactly:
///
/// ```ignore
/// #[derive(::astra_plugin_sdk::serde::Deserialize)]
/// #[serde(crate = "::astra_plugin_sdk::serde", default)]
/// #[derive(::astra_plugin_sdk::schema::schemars::JsonSchema)]
/// #[schemars(crate = "::astra_plugin_sdk::schema::schemars")]
/// #[derive(::astra_plugin_sdk::PluginConfig)]
/// #[derive(Default)]
/// struct Settings { api_key: String }
/// ```
///
/// `Default` stays the author's to write — derived, or by hand when the empty
/// value is not the zero value. `#[serde(default)]` needs it, and the SDK's
/// `ConfigShape` bound names it in one error if it is missing.
pub fn expand_config(attr: TokenStream, item: TokenStream) -> syn::Result<TokenStream> {
    check(
        &attr,
        &item,
        "#[astra::config]",
        "it is the type this plugin's settings JSON deserializes into",
        "move it onto the settings type, and name it with \
         `#[astra::plugin(config = ..)]` or a `#[hook] async fn on_config`",
    )?;

    Ok(quote! {
        #[derive(::astra_plugin_sdk::serde::Deserialize)]
        // `default` at the CONTAINER level, which is the entire difference from
        // `#[astra::args]`: the daemon's first payload to a freshly installed
        // plugin is `{}`, and a config type that rejects it never reaches
        // `on_config` at all.
        #[serde(crate = "::astra_plugin_sdk::serde", default)]
        #[derive(::astra_plugin_sdk::schema::schemars::JsonSchema)]
        #[schemars(crate = "::astra_plugin_sdk::schema::schemars")]
        #[derive(::astra_plugin_sdk::PluginConfig)]
        #item
    })
}

/// The shape checks both attributes share, with each one's own wording.
fn check(
    attr: &TokenStream,
    item: &TokenStream,
    shown: &str,
    what_it_is: &str,
    fix: &str,
) -> syn::Result<()> {
    if !attr.is_empty() {
        return Err(syn::Error::new(
            attr.span(),
            format!(
                "`{shown}` takes no arguments.\n\
                 fix: write `{shown}`, and put `#[serde(…)]` / `#[schemars(…)]` \
                 options in their own attributes below it — they are passed \
                 through unchanged."
            ),
        ));
    }

    // Parsed as a `DeriveInput` for the error message, then re-emitted from the
    // original tokens so nothing about the author's type is reformatted or lost.
    let parsed: Item = syn::parse2(item.clone())?;
    match &parsed {
        Item::Struct(_) | Item::Enum(_) => {}
        other => {
            return Err(syn::Error::new(
                other.span(),
                format!(
                    "`{shown}` goes on a struct or an enum — {what_it_is}.\n\
                     fix: {fix}."
                ),
            ));
        }
    }
    // Confirms the item is one a derive can be applied to at all, so a union
    // fails here rather than inside `serde_derive`.
    let _: DeriveInput = syn::parse2(item.clone())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use quote::quote;

    #[test]
    fn it_points_both_derives_at_the_sdk() {
        let out = expand(TokenStream::new(), quote! { struct Roll { count: u32 } })
            .unwrap()
            .to_string();
        // The two `crate = "…"` pointers are the entire reason this exists: an
        // expansion without them compiles only in a crate that lists `serde` and
        // `schemars` itself, which is the Cargo.toml the design forbids.
        assert!(
            out.contains(r#"crate = "::astra_plugin_sdk::serde""#),
            "{out}"
        );
        assert!(
            out.contains(r#"crate = "::astra_plugin_sdk::schema::schemars""#),
            "{out}"
        );
        assert!(
            out.contains(":: astra_plugin_sdk :: serde :: Deserialize"),
            "{out}"
        );
        assert!(out.contains("struct Roll"), "{out}");
    }

    #[test]
    fn a_misplaced_or_misconfigured_args_says_where_it_goes() {
        let on_a_fn = expand(TokenStream::new(), quote! { fn f() {} })
            .unwrap_err()
            .to_string();
        assert!(on_a_fn.contains("goes on a struct or an enum"), "{on_a_fn}");
        assert!(on_a_fn.contains("mark the handler"), "{on_a_fn}");

        let with_args = expand(quote! { default }, quote! { struct S; })
            .unwrap_err()
            .to_string();
        assert!(with_args.contains("takes no arguments"), "{with_args}");
        assert!(
            with_args.contains("passed through unchanged"),
            "{with_args}"
        );
    }

    /// The one difference between the two attributes, asserted rather than
    /// described: `#[astra::config]` puts `default` at the container level.
    ///
    /// Without it a config type with a required field rejects the daemon's
    /// first payload — which is `{}` on every fresh install — `on_config` is
    /// never called even once, and the plugin runs on whatever `Default` gave
    /// it while a single `WARN` says "keeping the previous config" about a
    /// config that never existed.
    #[test]
    fn config_makes_the_empty_payload_parse() {
        let out = expand_config(TokenStream::new(), quote! { struct S { key: String } })
            .unwrap()
            .to_string();
        assert!(
            out.contains(r#"crate = "::astra_plugin_sdk::serde" , default"#),
            "{out}"
        );
        // And it is a complete settings type on its own: schema included.
        assert!(out.contains(":: astra_plugin_sdk :: PluginConfig"), "{out}");

        // `#[astra::args]` must NOT do this — a tool argument the model omitted
        // is the model's mistake, and the schema's `required` is what tells it.
        let args = expand(TokenStream::new(), quote! { struct S { key: String } })
            .unwrap()
            .to_string();
        assert!(!args.contains("default"), "{args}");
        assert!(!args.contains("PluginConfig"), "{args}");
    }

    /// Each attribute names ITSELF in its errors — a message that said
    /// `#[astra::args]` to someone who wrote `#[astra::config]` sends them
    /// looking at the wrong line.
    #[test]
    fn config_errors_name_config() {
        let on_a_fn = expand_config(TokenStream::new(), quote! { fn f() {} })
            .unwrap_err()
            .to_string();
        assert!(on_a_fn.contains("`#[astra::config]`"), "{on_a_fn}");
        assert!(on_a_fn.contains("settings JSON"), "{on_a_fn}");
    }
}
