//! `#[derive(PluginConfig)]`.
//!
//! A plugin's settings are three things at once: a Rust type the handlers read,
//! a `serde` shape the daemon's JSON has to fit, and a JSON Schema the Settings
//! page renders from. The first two are `#[derive(Deserialize, Default)]` and
//! this derive does not try to reinvent them — it is a *marker* that ties them
//! together:
//!
//! * it implements [`PluginConfig`], whose `json_schema()` is what
//!   `astra-plugin check` stamps into `plugin.toml`'s `[config] schema` and what
//!   the level-1 test harness compares against; and
//! * it asserts, at compile time and on the author's own type name, that the
//!   type really does deserialize *and* has a `Default` — because
//!   `PluginCapability::on_config_changed` parses the daemon's payload into it,
//!   and a config struct without defaults rejects the very first, empty payload
//!   the daemon sends at startup.
//!
//! The assertion is the whole value. Without it the failure is a `WARN` at
//! runtime, once, on a machine that is not the author's.

use proc_macro2::TokenStream;
use quote::quote;
use syn::DeriveInput;

pub fn expand(input: TokenStream) -> syn::Result<TokenStream> {
    let input: DeriveInput = syn::parse2(input)?;
    let ident = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();

    Ok(quote! {
        impl #impl_generics ::astra_plugin_sdk::PluginConfig for #ident #ty_generics
            #where_clause
        {
            fn json_schema() -> ::std::string::String {
                // `of_config`, not `of`: its bound is `ConfigShape`, which is
                // `Deserialize + Default + JsonSchema` behind one
                // `#[diagnostic::on_unimplemented]`. A config type missing any
                // of the three then produces one error naming all three and the
                // exact derive line to write, instead of one error per missing
                // trait from three different places inside the SDK.
                ::astra_plugin_sdk::schema::of_config::<Self>()
            }
        }
    })
}
