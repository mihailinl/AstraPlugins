// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! `astra::main!(MyPlugin::default());`

use proc_macro2::TokenStream;
use quote::quote;
use syn::Expr;

/// Expand to a `fn main` that builds a Tokio runtime and runs the plugin.
///
/// This is `#[tokio::main]` written out — which is all `#[tokio::main]` ever
/// was — plus the two lines that make `--print-capabilities` answer truthfully.
/// Nothing is hidden: the whole body is code the author could paste in place of
/// the macro and keep working.
///
/// `__declared` is a local generic fn rather than an SDK helper so that the
/// plugin's type never has to be named. `astra::main!` takes an *expression*
/// (`MyPlugin::default()`, `MyPlugin::new(x)?` won't work — see below), and
/// inference recovers `P` from the value.
pub fn expand(input: TokenStream) -> syn::Result<TokenStream> {
    let expr: Expr = syn::parse2(input).map_err(|e| {
        syn::Error::new(
            e.span(),
            "`astra::main!` takes one expression: the plugin to run.\n\
             fix: `astra::main!(MyPlugin::default());`",
        )
    })?;

    Ok(quote! {
        fn main() -> ::astra_plugin_sdk::anyhow::Result<()> {
            // What this binary was built to serve. The daemon's `--capabilities`
            // still wins at registration — it read the manifest the user
            // consented to — but this is the answer to `--print-capabilities`,
            // which is how `astra-plugin check` compares the binary against
            // `plugin.toml` without trusting the manifest alone.
            fn __declared_capabilities<P: ::astra_plugin_sdk::DeclaredCapabilities>(
                _: &P,
            ) -> ::std::vec::Vec<::std::string::String> {
                <P as ::astra_plugin_sdk::DeclaredCapabilities>::CAPS
                    .iter()
                    .map(|c| ::std::string::ToString::to_string(c))
                    .collect()
            }

            let __plugin = #expr;
            let mut __config = ::astra_plugin_sdk::RunConfig::default();
            __config.capabilities = __declared_capabilities(&__plugin);

            ::astra_plugin_sdk::tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .build()?
                .block_on(::astra_plugin_sdk::run_with(__plugin, __config))
        }
    })
}
