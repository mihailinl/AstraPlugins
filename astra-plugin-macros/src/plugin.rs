//! `#[astra::plugin]` — the inherent impl block becomes a `PluginCapability`.
//!
//! ## What it expands to, and what it deliberately does not
//!
//! The output is two impl blocks and nothing else:
//!
//! 1. the author's inherent `impl`, with the marker attributes removed and
//!    every method left exactly where it was written — so a stack trace, a
//!    breakpoint and `cargo doc` all point at the author's code; and
//! 2. `impl PluginCapability for T`, whose bodies `match` on the wire name and
//!    call those inherent methods, plus `impl DeclaredCapabilities for T`.
//!
//! There is no registry, no `inventory`/`linkme` link-section trick, no
//! `lazy_static` and no generated runtime. Everything the macro writes is
//! something the author could have written, and `cargo expand` is a complete
//! migration path off the macro: paste the output, delete the attribute, keep
//! going. `tests/expansion_is_the_handwritten_impl.rs` holds the hand-written
//! twin of a macro plugin and asserts the two behave identically.
//!
//! Every path the expansion emits is absolute and rooted at the SDK
//! (`::astra_plugin_sdk::serde_json`, `::astra_plugin_sdk::tokio`, …). The whole
//! point of the macro layer is that a plugin's `Cargo.toml` has one dependency;
//! an expansion that named `serde_json::` would compile only until the author
//! deleted the line they no longer need.

use std::collections::BTreeSet;

use proc_macro2::{Span, TokenStream};
use quote::{ToTokens, quote, quote_spanned};
use syn::spanned::Spanned;
use syn::{
    Attribute, Expr, FnArg, ImplItem, ImplItemFn, ItemImpl, Lit, Meta, Pat, PatType, ReturnType,
    Type,
};

use crate::hooks;

// ── attribute arguments on `#[astra::plugin(..)]` ────────────────────────────

#[derive(Default)]
struct PluginArgs {
    config: Option<Type>,
    capabilities: Option<Vec<String>>,
}

fn parse_plugin_args(attr: TokenStream) -> syn::Result<PluginArgs> {
    let mut args = PluginArgs::default();
    if attr.is_empty() {
        return Ok(args);
    }
    let parser = syn::meta::parser(|meta| {
        if meta.path.is_ident("config") {
            args.config = Some(meta.value()?.parse()?);
            Ok(())
        } else if meta.path.is_ident("capabilities") {
            let lit: syn::LitStr = meta.value()?.parse()?;
            args.capabilities = Some(
                lit.value()
                    .split(',')
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty())
                    .collect(),
            );
            Ok(())
        } else {
            Err(meta.error(
                "`#[astra::plugin]` takes `config = <Type>` and \
                 `capabilities = \"tools, triggers\"`, and nothing else",
            ))
        }
    });
    syn::parse::Parser::parse2(parser, attr)?;
    Ok(args)
}

// ── marker attributes on the methods inside ──────────────────────────────────

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Tool,
    Action,
    UiCall,
    Hook,
}

impl Kind {
    fn attr(self) -> &'static str {
        match self {
            Kind::Tool => "#[tool]",
            Kind::Action => "#[action]",
            Kind::UiCall => "#[ui_call]",
            Kind::Hook => "#[hook]",
        }
    }
}

/// `#[tool]`, `#[astra::tool]` — both, so the marker works whether or not the
/// author glob-imported the prelude.
fn marker_kind(attr: &Attribute) -> Option<Kind> {
    let segments = &attr.path().segments;
    let last = segments.last()?.ident.to_string();
    let qualified_ok = match segments.len() {
        1 => true,
        2 => segments[0].ident == "astra",
        _ => false,
    };
    if !qualified_ok {
        return None;
    }
    match last.as_str() {
        "tool" => Some(Kind::Tool),
        "action" => Some(Kind::Action),
        "ui_call" => Some(Kind::UiCall),
        "hook" => Some(Kind::Hook),
        _ => None,
    }
}

#[derive(Default)]
struct MarkerArgs {
    name: Option<String>,
    description: Option<String>,
    label: Option<String>,
    icon: Option<Expr>,
    schema: Option<Expr>,
}

fn parse_marker_args(attr: &Attribute, kind: Kind) -> syn::Result<MarkerArgs> {
    let mut args = MarkerArgs::default();
    if matches!(attr.meta, Meta::Path(_)) {
        return Ok(args);
    }
    let allowed: &[&str] = match kind {
        Kind::Tool => &["name", "description", "schema"],
        Kind::Action => &["name", "label", "description", "icon"],
        Kind::UiCall => &["name"],
        Kind::Hook => &[],
    };
    attr.parse_nested_meta(|meta| {
        let key = meta
            .path
            .get_ident()
            .map(|i| i.to_string())
            .unwrap_or_default();
        if !allowed.contains(&key.as_str()) {
            return Err(meta.error(format!(
                "`{}` does not take `{key}`. It takes: {}",
                kind.attr(),
                if allowed.is_empty() {
                    "no arguments".to_string()
                } else {
                    allowed
                        .iter()
                        .map(|a| format!("`{a}`"))
                        .collect::<Vec<_>>()
                        .join(", ")
                }
            )));
        }
        match key.as_str() {
            "name" => args.name = Some(meta.value()?.parse::<syn::LitStr>()?.value()),
            "description" => args.description = Some(meta.value()?.parse::<syn::LitStr>()?.value()),
            "label" => args.label = Some(meta.value()?.parse::<syn::LitStr>()?.value()),
            "icon" => args.icon = Some(meta.value()?.parse()?),
            "schema" => args.schema = Some(meta.value()?.parse()?),
            _ => unreachable!(),
        }
        Ok(())
    })?;
    Ok(args)
}

/// The `///` lines above a method, as one string.
fn doc_comment(attrs: &[Attribute]) -> Option<String> {
    let mut lines: Vec<String> = Vec::new();
    for attr in attrs {
        if !attr.path().is_ident("doc") {
            continue;
        }
        if let Meta::NameValue(nv) = &attr.meta
            && let Expr::Lit(lit) = &nv.value
            && let Lit::Str(s) = &lit.lit
        {
            lines.push(s.value().trim().to_string());
        }
    }
    while lines.last().is_some_and(|l| l.is_empty()) {
        lines.pop();
    }
    let text = lines.join("\n").trim().to_string();
    (!text.is_empty()).then_some(text)
}

// ── one dispatched handler ───────────────────────────────────────────────────

struct Handler {
    ident: syn::Ident,
    /// The name on the wire: the tool name the model calls, the action `type`,
    /// the UI method.
    wire_name: String,
    description: String,
    label: String,
    icon: Option<Expr>,
    has_ctx: bool,
    args_ty: Option<Type>,
    /// The span of the author's `-> …`. The dispatcher's type annotation is
    /// emitted with it, so a return type the SDK cannot use is reported on the
    /// signature that declared it rather than on `#[astra::plugin]`.
    output_span: Span,
    schema: Option<Expr>,
}

/// Does this return type *look* like a `Result`?
///
/// Deliberately by name and not by resolution — a proc macro has no type
/// information, and an author with `type ToolResult = Result<String, ToolError>;`
/// is not making the mistake this check exists to catch. So anything whose final
/// path segment ends in `Result` passes here and is checked by the compiler
/// against the dispatcher's annotation (which carries this signature's span);
/// `-> String`, `-> ()` and a bare `-> impl Future` are what get the sentence.
fn looks_like_result(output: &ReturnType) -> bool {
    let ReturnType::Type(_, ty) = output else {
        return false;
    };
    let Type::Path(p) = &**ty else {
        return false;
    };
    p.path
        .segments
        .last()
        .is_some_and(|s| s.ident.to_string().ends_with("Result"))
}

/// Check the shape of a `#[tool]` / `#[action]` / `#[ui_call]` method and pull
/// out what the dispatcher needs.
fn parse_handler(f: &ImplItemFn, kind: Kind, args: MarkerArgs) -> syn::Result<Handler> {
    let ident = f.sig.ident.clone();
    let attr = kind.attr();

    if f.sig.asyncness.is_none() {
        return Err(syn::Error::new(
            f.sig.fn_token.span(),
            format!(
                "`{attr}` handlers must be `async fn` — the SDK awaits them.\n\
                 fix: write `async fn {ident}(..)`."
            ),
        ));
    }
    if !f.sig.generics.params.is_empty() {
        return Err(syn::Error::new(
            f.sig.generics.span(),
            format!(
                "`{attr}` handlers cannot be generic: the daemon calls them by \
                 name at runtime, so there is nothing to infer the parameters \
                 from.\n\
                 fix: take a concrete argument type, or move the generic body \
                 into a helper `{ident}` calls."
            ),
        ));
    }

    let mut inputs = f.sig.inputs.iter();
    match inputs.next() {
        Some(FnArg::Receiver(r)) if r.reference.is_some() && r.mutability.is_none() => {}
        Some(FnArg::Receiver(r)) => {
            return Err(syn::Error::new(
                r.span(),
                format!(
                    "`{attr}` handlers take `&self`: the daemon may run several \
                     calls at once, so the SDK only ever holds a shared \
                     reference.\n\
                     fix: write `&self` and put anything mutable behind \
                     `Config<T>`, an `Atomic*` or a `Mutex`."
                ),
            ));
        }
        _ => {
            return Err(syn::Error::new(
                f.sig.span(),
                format!("`{attr}` handlers must be methods taking `&self` as their first argument"),
            ));
        }
    }

    let rest: Vec<&PatType> = inputs
        .map(|arg| match arg {
            FnArg::Typed(t) => Ok(t),
            FnArg::Receiver(r) => Err(syn::Error::new(r.span(), "unexpected second receiver")),
        })
        .collect::<syn::Result<_>>()?;

    let mut has_ctx = false;
    let mut args_ty: Option<Type> = None;
    let mut rest = rest.into_iter().peekable();

    if let Some(first) = rest.peek()
        && is_plugin_context_ref(&first.ty)
    {
        has_ctx = true;
        rest.next();
    }
    if let Some(a) = rest.next() {
        if let Type::Reference(r) = &*a.ty {
            return Err(syn::Error::new(
                a.ty.span(),
                format!(
                    "`{attr}` deserializes its argument from the daemon's JSON, \
                     so the argument type must be owned — `{}` is a reference.\n\
                     fix: take it by value (`{}`). A `&PluginContext` is only \
                     recognised as the context parameter when its type is \
                     written literally as `&PluginContext`.",
                    r.to_token_stream(),
                    r.elem.to_token_stream(),
                ),
            ));
        }
        args_ty = Some((*a.ty).clone());
    }
    if let Some(extra) = rest.next() {
        return Err(syn::Error::new(
            extra.span(),
            format!(
                "`{attr}` handlers take at most `(&self, ctx: &PluginContext, args: T)`; \
                 `{}` is one argument too many.\n\
                 fix: put the extra parameters into the `T` struct — it is \
                 deserialized from the call's JSON.",
                pat_name(&extra.pat)
            ),
        ));
    }

    // The single most common signature mistake, because returning a plain
    // `String` is what the handler feels like it *does*. Caught here, on the
    // author's own `->`, rather than left to the dispatcher's type annotation:
    // that one reports `expected Result<String, ToolError>, found String` at
    // `#[astra::plugin]` — eleven lines above the mistake, with no indication
    // which of four handlers is wrong, and rustc's canned suggestion is to wrap
    // the attribute itself in `Ok(..)`.
    if !looks_like_result(&f.sig.output) {
        return Err(match &f.sig.output {
            // `ReturnType::Default` has no tokens of its own, so its span is the
            // call site; the signature is the closest thing the author wrote.
            ReturnType::Default => syn::Error::new(
                f.sig.span(),
                format!(
                    "`{attr} {ident}` returns nothing, and a handler returns \
                     `Result<String, ToolError>` — the string is what the daemon \
                     sends back, and the error is what the AI loop and the UI \
                     read.\n\
                     fix: add `-> Result<String, ToolError>`."
                ),
            ),
            out => syn::Error::new(
                out.span(),
                format!(
                    "`{attr} {ident}` returns `{}`, and a handler returns \
                     `Result<String, ToolError>`.\n\
                     The error's *kind* is what tells the AI loop what to do \
                     next: `BadArguments` says retry with different arguments, \
                     `NotConfigured` says stop and send the user to a settings \
                     field, `RateLimited` says wait exactly this long. A handler \
                     that cannot fail says so with `Ok(..)`.\n\
                     fix: write `-> Result<String, ToolError>` and wrap the \
                     value in `Ok(..)`.",
                    out.to_token_stream().to_string().replacen("-> ", "", 1),
                ),
            ),
        });
    }

    let description = args
        .description
        .or_else(|| doc_comment(&f.attrs))
        .ok_or_else(|| {
            syn::Error::new(
                f.sig.ident.span(),
                match kind {
                    Kind::Tool => format!(
                        "`#[tool] {ident}` has no description, and the model \
                         reads the description to decide whether to call it.\n\
                         fix: add a `/// …` doc comment above `{ident}`, or \
                         `#[tool(description = \"…\")]`."
                    ),
                    _ => format!(
                        "`{attr} {ident}` has no description; it is shown in the \
                         command editor.\n\
                         fix: add a `/// …` doc comment above `{ident}`, or \
                         `{}(description = \"…\")]`.",
                        attr.trim_end_matches(']')
                    ),
                },
            )
        })?;

    let wire_name = args.name.unwrap_or_else(|| ident.to_string());
    let label = args.label.unwrap_or_else(|| title_case(&wire_name));

    Ok(Handler {
        ident,
        wire_name,
        description,
        label,
        icon: args.icon,
        has_ctx,
        args_ty,
        output_span: f.sig.output.span(),
        schema: args.schema,
    })
}

fn is_plugin_context_ref(ty: &Type) -> bool {
    let Type::Reference(r) = ty else {
        return false;
    };
    let Type::Path(p) = &*r.elem else {
        return false;
    };
    p.path
        .segments
        .last()
        .is_some_and(|s| s.ident == "PluginContext")
}

fn pat_name(pat: &Pat) -> String {
    match pat {
        Pat::Ident(i) => i.ident.to_string(),
        other => other.to_token_stream().to_string(),
    }
}

fn title_case(s: &str) -> String {
    s.split(['_', '-'])
        .filter(|w| !w.is_empty())
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().to_string() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

// ── expansion ────────────────────────────────────────────────────────────────

pub fn expand(attr: TokenStream, item: TokenStream) -> syn::Result<TokenStream> {
    let args = parse_plugin_args(attr)?;
    let mut block: ItemImpl = syn::parse2(item.clone()).map_err(|e| {
        syn::Error::new(
            e.span(),
            "`#[astra::plugin]` goes on an inherent `impl` block — \
             `impl MyPlugin { … }`.\n\
             fix: move it above the `impl MyPlugin` block that holds your \
             `#[tool]` methods.",
        )
    })?;

    if let Some((_, path, _)) = &block.trait_ {
        return Err(syn::Error::new(
            path.span(),
            "`#[astra::plugin]` goes on an inherent `impl MyPlugin { … }`, not \
             on a trait impl. It *writes* the `impl PluginCapability` for you, \
             so a hand-written one next to it would be a duplicate.\n\
             fix: delete `PluginCapability for` from this line, and mark the \
             hooks inside it with `#[hook]`.",
        ));
    }

    let self_ty = (*block.self_ty).clone();
    let (impl_generics, _, where_clause) = block.generics.split_for_impl();
    let impl_generics = impl_generics.to_token_stream();
    let where_clause = where_clause.to_token_stream();

    let mut tools: Vec<Handler> = Vec::new();
    let mut actions: Vec<Handler> = Vec::new();
    let mut ui_calls: Vec<Handler> = Vec::new();
    let mut hook_fns: Vec<ImplItemFn> = Vec::new();
    let mut hook_names: BTreeSet<String> = BTreeSet::new();
    let mut config_from_hook: Option<Type> = None;

    for item in &mut block.items {
        let ImplItem::Fn(f) = item else { continue };

        // Which marker (at most one) is on this method?
        let mut found: Option<(usize, Kind)> = None;
        for (i, a) in f.attrs.iter().enumerate() {
            if let Some(kind) = marker_kind(a) {
                if let Some((_, first)) = found {
                    return Err(syn::Error::new(
                        a.span(),
                        format!(
                            "`{}` and `{}` on the same method: a method is one \
                             thing.\n\
                             fix: keep one, and add a second method for the \
                             other role — they may both call the same helper.",
                            first.attr(),
                            kind.attr()
                        ),
                    ));
                }
                found = Some((i, kind));
            }
        }
        let Some((idx, kind)) = found else { continue };

        let marker = f.attrs.remove(idx);
        let margs = parse_marker_args(&marker, kind)?;

        if kind == Kind::Hook {
            let name = f.sig.ident.to_string();
            if !hooks::is_known(&name) {
                let suggestions = hooks::suggestions(&name);
                let hint = if suggestions.is_empty() {
                    "see `PluginCapability` for the full list".to_string()
                } else {
                    format!(
                        "did you mean {}?",
                        suggestions
                            .iter()
                            .map(|s| format!("`{s}`"))
                            .collect::<Vec<_>>()
                            .join(" or ")
                    )
                };
                return Err(syn::Error::new(
                    f.sig.ident.span(),
                    format!(
                        "`#[hook] {name}` is not a `PluginCapability` hook, so \
                         the daemon would never call it — {hint}\n\
                         fix: correct the name, or drop `#[hook]` to keep this \
                         as an ordinary method."
                    ),
                ));
            }
            if !hook_names.insert(name.clone()) {
                return Err(syn::Error::new(
                    f.sig.ident.span(),
                    format!("`#[hook] {name}` is declared twice on this plugin"),
                ));
            }
            if name == "on_config"
                && let Some(FnArg::Typed(last)) = f.sig.inputs.iter().next_back()
            {
                config_from_hook = Some((*last.ty).clone());
            }
            let mut moved = f.clone();
            // The method leaves the inherent block entirely: two definitions
            // with one name is a compile error, and the trait impl is where the
            // daemon reaches it.
            moved.vis = syn::Visibility::Inherited;
            hook_fns.push(moved);
            continue;
        }

        let handler = parse_handler(f, kind, margs)?;
        match kind {
            Kind::Tool => tools.push(handler),
            Kind::Action => actions.push(handler),
            Kind::UiCall => ui_calls.push(handler),
            Kind::Hook => unreachable!(),
        }
    }

    // Methods that moved into the trait impl must not stay in the inherent one.
    block.items.retain(|item| match item {
        ImplItem::Fn(f) => !hook_names.contains(&f.sig.ident.to_string()),
        _ => true,
    });

    check_unique("tool", &tools)?;
    check_unique("action", &actions)?;
    check_unique("UI method", &ui_calls)?;

    if tools.is_empty() && actions.is_empty() && ui_calls.is_empty() && hook_fns.is_empty() {
        return Err(syn::Error::new(
            Span::call_site(),
            "`#[astra::plugin]` found nothing to expose on this impl block.\n\
             fix: mark a method with `#[tool]`, `#[action]` or `#[ui_call]`, or \
             a `PluginCapability` hook with `#[hook]`.",
        ));
    }

    // ── the capability set this binary declares ──
    let caps: Vec<String> = match args.capabilities {
        Some(explicit) => explicit,
        None => {
            let mut set: BTreeSet<String> = BTreeSet::new();
            if !tools.is_empty() {
                set.insert("tools".into());
            }
            if !actions.is_empty() {
                set.insert("actions".into());
            }
            if !ui_calls.is_empty() {
                set.insert("ui_contributions".into());
            }
            for name in &hook_names {
                if let Some(cap) = hooks::capability_for(name) {
                    set.insert(cap.into());
                }
            }
            set.into_iter().collect()
        }
    };

    let config_ty: Type = match args.config.or(config_from_hook) {
        Some(ty) => ty,
        None => syn::parse_quote!(::astra_plugin_sdk::NoConfig),
    };

    // ── generated trait methods ──
    let mut trait_items: Vec<TokenStream> = Vec::new();

    if !tools.is_empty() && !hook_names.contains("list_tools") {
        let defs = tools.iter().map(tool_def);
        trait_items.push(quote! {
            async fn list_tools(&self) -> ::std::vec::Vec<::astra_plugin_sdk::ToolDef> {
                ::std::vec![#(#defs),*]
            }
        });
    }
    if !tools.is_empty() && !hook_names.contains("call_tool") {
        let arms = tools.iter().map(dispatch_arm);
        trait_items.push(quote! {
            async fn call_tool(
                &self,
                __ctx: &::astra_plugin_sdk::PluginContext,
                __name: &str,
                __arguments_json: &str,
            ) -> ::std::result::Result<::std::string::String, ::astra_plugin_sdk::ToolError> {
                match __name {
                    #(#arms)*
                    _ => ::std::result::Result::Err(
                        ::astra_plugin_sdk::ToolError::NotFound(
                            ::std::format!("no tool named `{}`", __name),
                        ),
                    ),
                }
            }
        });
    }

    if !actions.is_empty() && !hook_names.contains("action_types") {
        let defs = actions.iter().map(action_def);
        trait_items.push(quote! {
            async fn action_types(&self) -> ::std::vec::Vec<::astra_plugin_sdk::ActionTypeDef> {
                ::std::vec![#(#defs),*]
            }
        });
    }
    if !actions.is_empty() && !hook_names.contains("execute_action") {
        let arms = actions.iter().map(dispatch_arm);
        trait_items.push(quote! {
            async fn execute_action(
                &self,
                __ctx: &::astra_plugin_sdk::PluginContext,
                __name: &str,
                __arguments_json: &str,
            ) -> ::std::result::Result<::std::string::String, ::astra_plugin_sdk::ActionError> {
                match __name {
                    #(#arms)*
                    _ => ::std::result::Result::Err(
                        ::astra_plugin_sdk::ActionError::NotFound(
                            ::std::format!("no action named `{}`", __name),
                        ),
                    ),
                }
            }
        });
    }

    if !ui_calls.is_empty() && !hook_names.contains("handle_ui_call") {
        let arms = ui_calls.iter().map(dispatch_arm);
        trait_items.push(quote! {
            async fn handle_ui_call(
                &self,
                __ctx: &::astra_plugin_sdk::PluginContext,
                __name: &str,
                __arguments_json: &str,
            ) -> ::std::result::Result<::std::string::String, ::astra_plugin_sdk::ToolError> {
                match __name {
                    #(#arms)*
                    _ => ::std::result::Result::Err(
                        ::astra_plugin_sdk::ToolError::NotFound(
                            ::std::format!("no UI method `{}`", __name),
                        ),
                    ),
                }
            }
        });
    }

    let cap_lits = caps.iter().map(|c| syn::LitStr::new(c, Span::call_site()));

    Ok(quote! {
        #block

        #[::astra_plugin_sdk::async_trait]
        impl #impl_generics ::astra_plugin_sdk::PluginCapability for #self_ty #where_clause {
            type Config = #config_ty;

            #(#trait_items)*

            #(#hook_fns)*
        }

        impl #impl_generics ::astra_plugin_sdk::DeclaredCapabilities for #self_ty #where_clause {
            const CAPS: &'static [&'static str] = &[#(#cap_lits),*];
        }
    })
}

/// Emit the author's error, and then enough of a plugin that nothing else
/// fails.
///
/// A proc macro that returns only `compile_error!` deletes the item it was
/// applied to. For `#[astra::plugin]` that means the plugin type loses both
/// `PluginCapability` and `DeclaredCapabilities`, so `astra::main!` — twelve
/// lines further down and entirely correct — reports two more errors about
/// traits that are missing *because* the first error happened. Three errors,
/// two of them about the wrong line, for one typo.
///
/// So: keep the impl block (markers stripped, or they would each add a "this
/// only means something inside `#[astra::plugin]`" of their own), and add the
/// two impls the rest of the file expects. Every method the author wrote stays
/// exactly where they wrote it, and the *only* diagnostic is theirs.
pub fn recover(error: syn::Error, item: TokenStream) -> TokenStream {
    let mut out = error.to_compile_error();

    let Ok(mut block) = syn::parse2::<ItemImpl>(item) else {
        // Not an impl block at all — there is nothing to keep and nothing that
        // could have referred to it. The one error stands alone.
        return out;
    };
    if block.trait_.is_some() {
        // A trait impl: the author wrote `impl PluginCapability for T` by hand.
        // Keeping it is right; adding our own `PluginCapability` would be the
        // duplicate the error is about. `DeclaredCapabilities` is a different
        // trait and nothing else emits it, so it still goes in — otherwise
        // `astra::main!` reports it missing, which is true and useless.
        let self_ty = &block.self_ty;
        let (impl_generics, _, where_clause) = block.generics.split_for_impl();
        let caps = quote! {
            impl #impl_generics ::astra_plugin_sdk::DeclaredCapabilities for #self_ty
                #where_clause
            {
                const CAPS: &'static [&'static str] = &[];
            }
        };
        out.extend(quote!(#block #caps));
        return out;
    }

    for item in &mut block.items {
        if let ImplItem::Fn(f) = item {
            f.attrs.retain(|a| marker_kind(a).is_none());
        }
    }

    let self_ty = &block.self_ty;
    let (impl_generics, _, where_clause) = block.generics.split_for_impl();
    out.extend(quote! {
        #block

        #[::astra_plugin_sdk::async_trait]
        impl #impl_generics ::astra_plugin_sdk::PluginCapability for #self_ty #where_clause {
            type Config = ::astra_plugin_sdk::NoConfig;
        }

        impl #impl_generics ::astra_plugin_sdk::DeclaredCapabilities for #self_ty #where_clause {
            const CAPS: &'static [&'static str] = &[];
        }
    });
    out
}

fn check_unique(what: &str, handlers: &[Handler]) -> syn::Result<()> {
    let mut seen: BTreeSet<&str> = BTreeSet::new();
    for h in handlers {
        if !seen.insert(&h.wire_name) {
            return Err(syn::Error::new(
                h.ident.span(),
                format!(
                    "two methods claim the {what} name `{}`, and the daemon \
                     dispatches by that name.\n\
                     fix: rename one, or give it a different wire name with \
                     `(name = \"…\")`.",
                    h.wire_name
                ),
            ));
        }
    }
    Ok(())
}

fn tool_def(h: &Handler) -> TokenStream {
    let name = &h.wire_name;
    let desc = &h.description;
    let schema = schema_expr(h);
    quote! {
        ::astra_plugin_sdk::ToolDef::new(#name, #desc).with_schema(#schema)
    }
}

/// The JSON Schema for a handler's argument type.
///
/// `#[tool(schema = …)]` wins. Otherwise: a handler with an argument type gets
/// the schema `schemars` derives for it, and one without gets the empty object
/// — which is the truth, not a placeholder.
fn schema_expr(h: &Handler) -> TokenStream {
    if let Some(expr) = &h.schema {
        return quote!(#expr);
    }
    // `#ty` is interpolated with the author's own spans, so
    // "`Roll` does not implement `JsonSchema`" is reported on `Roll` in the
    // handler's signature, where the fix goes.
    match &h.args_ty {
        Some(ty) => quote!(::astra_plugin_sdk::schema::of::<#ty>()),
        None => quote!(r#"{"type":"object","properties":{}}"#),
    }
}

fn action_def(h: &Handler) -> TokenStream {
    let type_id = &h.wire_name;
    let label = &h.label;
    let desc = &h.description;
    let icon = match &h.icon {
        Some(e) => quote!(::std::convert::Into::into(#e)),
        None => quote!(::std::string::String::new()),
    };
    quote! {
        ::astra_plugin_sdk::ActionTypeDef {
            r#type: ::std::convert::Into::into(#type_id),
            label: ::std::convert::Into::into(#label),
            icon_svg: #icon,
            // The command editor's parameter rows cannot be derived from a Rust
            // type: `FieldDef` carries placeholders, defaults, groups and
            // visibility conditions that no `#[derive]` can invent. Declare them
            // with `#[hook] async fn action_types`, which replaces this whole
            // method.
            fields: ::std::vec![],
            ai_available: true,
            ai_description: ::std::convert::Into::into(#desc),
            ai_primary_field: ::std::string::String::new(),
            platforms: ::std::vec![],
            hidden: false,
        }
    }
}

/// One `match` arm: parse the JSON into the handler's argument type, call the
/// inherent method, return what it returned.
///
/// Every token here carries a span the author can point at.
///
/// `#ty` and `#ident` are interpolated with the author's own spans, so a
/// missing `Deserialize` on the argument type is reported on the parameter that
/// named it. The type annotation on `__out` is emitted with
/// [`quote_spanned!`] at the handler's `->` for the same reason: written at
/// `Span::call_site()` it reported `expected Result<String, ToolError>, found
/// String` **on the `#[astra::plugin]` attribute**, eleven lines above the
/// mistake, with no indication which of four handlers was wrong and a canned
/// suggestion to wrap the attribute itself in `Ok(..)`.
///
/// `parse_handler` rejects a return type that is visibly not a `Result` before
/// it ever gets here, so this annotation is the belt to that braces: it catches
/// the residue — `anyhow::Result<String>`, `Result<u32, ToolError>`, a type
/// alias that resolves to the wrong thing — and lands it on the signature.
///
/// Binding the call's result to the declared type, rather than letting the
/// `match` infer it, is what makes that mismatch a *type* error with both types
/// named.
fn dispatch_arm(h: &Handler) -> TokenStream {
    let name = &h.wire_name;
    let ident = &h.ident;
    let ctx = h.has_ctx.then(|| quote!(__ctx,));

    let (bind, call_args) = match &h.args_ty {
        // Spanned at the author's argument type, not at the call site: the
        // `Deserialize` bound comes from `serde_json::from_str`, and at
        // call_site "the trait bound `Roll: Deserialize` is not satisfied" was
        // reported on the `#[astra::plugin]` attribute. `JsonSchema` was always
        // reported correctly, because `schema::of::<#ty>()` interpolates `#ty`
        // as the turbofish and inherits its span; this is the same fix for the
        // other half of the pair.
        Some(ty) => (
            quote_spanned! {ty.span()=>
                let __args: #ty = ::astra_plugin_sdk::serde_json::from_str(
                    if __arguments_json.trim().is_empty() { "{}" } else { __arguments_json },
                )?;
            },
            quote!(#ctx __args),
        ),
        None => (quote!(), quote!(#ctx)),
    };

    let out = h.output_span;
    let binding = quote_spanned! {out=>
        let __out: ::std::result::Result<
            ::std::string::String,
            ::astra_plugin_sdk::ToolError,
        > = Self::#ident(self, #call_args).await;
    };

    quote! {
        #name => {
            #bind
            #binding
            __out
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use quote::quote;

    fn err(item: TokenStream) -> String {
        expand(TokenStream::new(), item)
            .expect_err("expected this to be rejected")
            .to_string()
    }

    /// Every one of these is a mistake someone will make on their first day,
    /// and the test asserts the two things that make an error message worth
    /// anything: it names the attribute, and it says what to do.
    #[test]
    fn a_misused_attribute_names_itself_and_the_fix() {
        let cases: &[(TokenStream, &str, &str)] = &[
            (
                quote! { impl P { /// d
                #[tool] fn t(&self) -> Result<String, ToolError> { todo!() } } },
                "#[tool]",
                "async fn t(..)",
            ),
            (
                quote! { impl P {
                #[tool] async fn t(&self) -> Result<String, ToolError> { todo!() } } },
                "#[tool] t",
                "doc comment above `t`",
            ),
            (
                quote! { impl P { /// d
                #[tool(label = "x")] async fn t(&self) -> Result<String, ToolError> { todo!() } } },
                "`#[tool]` does not take `label`",
                "`name`, `description`, `schema`",
            ),
            (
                quote! { impl P { /// d
                #[tool] async fn t(self) -> Result<String, ToolError> { todo!() } } },
                "`#[tool]` handlers take `&self`",
                "put anything mutable behind",
            ),
            (
                quote! { impl P { /// d
                #[tool] async fn t(&self, a: &Roll) -> Result<String, ToolError> { todo!() } } },
                "the argument type must be owned",
                "take it by value (`Roll`)",
            ),
            (
                quote! { impl P { /// d
                #[tool] async fn t(&self, a: Roll, b: u32) -> Result<String, ToolError> { todo!() } } },
                "one argument too many",
                "put the extra parameters into the `T` struct",
            ),
            (
                quote! { impl P {
                #[hook] async fn on_startup(&self) {} } },
                "did you mean `on_start`?",
                "drop `#[hook]`",
            ),
            (
                quote! { impl P { /// d
                #[tool] #[action] async fn t(&self) -> Result<String, ToolError> { todo!() } } },
                "on the same method",
                "add a second method",
            ),
            (
                quote! { impl P { /// d
                #[tool] async fn a(&self) -> Result<String, ToolError> { todo!() }
                /// d
                #[tool(name = "a")] async fn b(&self) -> Result<String, ToolError> { todo!() } } },
                "two methods claim the tool name `a`",
                "give it a different wire name",
            ),
            (
                quote! { impl PluginCapability for P { type Config = NoConfig; } },
                "not on a trait impl",
                "delete `PluginCapability for`",
            ),
            (
                quote! { impl P {} },
                "found nothing to expose",
                "mark a method with `#[tool]`",
            ),
            // The most common signature mistake of all: returning the string the
            // tool "produces". Left to the dispatcher's type annotation this
            // reported `expected Result<String, ToolError>, found String` on the
            // `#[astra::plugin]` attribute, and suggested `Ok(#[astra::plugin])`.
            (
                quote! { impl P { /// d
                #[tool] async fn t(&self, a: Roll) -> String { todo!() } } },
                "`#[tool] t` returns `String`",
                "wrap the value in `Ok(..)`",
            ),
            (
                quote! { impl P { /// d
                #[action] async fn t(&self) {} } },
                "`#[action] t` returns nothing",
                "add `-> Result<String, ToolError>`",
            ),
            (
                quote! { impl P { /// d
                #[ui_call] async fn t(&self) -> Vec<u8> { todo!() } } },
                "`#[ui_call] t` returns `Vec < u8 >`",
                "wrap the value in `Ok(..)`",
            ),
        ];
        for (item, names_it, says_the_fix) in cases {
            let msg = err(item.clone());
            assert!(
                msg.contains(names_it),
                "{msg:?}\n… did not name {names_it:?}"
            );
            assert!(
                msg.contains(says_the_fix),
                "{msg:?}\n… did not say the fix {says_the_fix:?}"
            );
        }
    }

    /// The return-type check is a *name* check, and it must not reject the
    /// author who wrote an alias.
    ///
    /// A proc macro has no type information: `type ToolResult = Result<String,
    /// ToolError>;` is indistinguishable from `String` except by the name, and
    /// an author using one is not making the mistake the check exists to catch.
    /// So anything ending in `Result` passes here and is checked by the
    /// compiler against the dispatcher's annotation — which now carries the
    /// author's own `->` span, so a wrong alias still lands on the signature.
    #[test]
    fn a_result_alias_is_still_a_result() {
        for output in [
            quote!(-> Result<String, ToolError>),
            quote!(-> ToolResult),
            quote!(-> anyhow::Result<String>),
            quote!(-> ::std::result::Result<String, ToolError>),
        ] {
            let item = quote! { impl P { /// d
            #[tool] async fn t(&self) #output { todo!() } } };
            assert!(
                expand(TokenStream::new(), item).is_ok(),
                "rejected {output}, which the compiler is the one to judge",
            );
        }
    }

    /// The dispatcher's type annotation carries the handler's `->` span.
    ///
    /// Asserted on the token stream rather than through a compile-fail fixture
    /// because that is what the fix *is*: `Span::call_site()` here is what put
    /// `expected Result<String, ToolError>, found String` on the
    /// `#[astra::plugin]` attribute line.
    #[test]
    fn the_dispatch_annotation_points_at_the_authors_return_type() {
        let sig: syn::ImplItemFn = syn::parse_quote! {
            /// d
            async fn t(&self) -> ToolResult { todo!() }
        };
        let h = parse_handler(&sig, Kind::Tool, MarkerArgs::default()).expect("parses");
        assert_eq!(
            format!("{:?}", h.output_span),
            format!("{:?}", sig.sig.output.span()),
            "the Handler must remember where the author wrote `->`",
        );
    }

    /// One mistake must produce one error.
    ///
    /// A proc macro that answers an error by deleting the item it was applied to
    /// takes `PluginCapability` and `DeclaredCapabilities` with it, and
    /// `astra::main!` — correct, and twelve lines further down — then reports
    /// two more errors about traits that are missing because of the first. The
    /// recovery path keeps the block and stubs both impls.
    #[test]
    fn a_rejected_block_still_defines_the_traits_the_rest_of_the_file_needs() {
        let item = quote! { impl P {
        #[tool] async fn t(&self) -> Result<String, ToolError> { todo!() } } };
        let out = recover(expand(TokenStream::new(), item.clone()).unwrap_err(), item).to_string();
        assert!(out.contains("compile_error"), "{out}");
        assert!(out.contains("PluginCapability for P"), "{out}");
        assert!(out.contains("DeclaredCapabilities for P"), "{out}");
        // The author's method survives, so nothing that calls it fails too.
        assert!(out.contains("async fn t"), "{out}");
        // …with the marker gone, or `#[tool]`'s own stray-marker error would be
        // a second diagnostic about the same line.
        assert!(!out.contains("# [tool]"), "{out}");
    }

    /// A hand-written `impl PluginCapability` must not be duplicated by the
    /// recovery stub — but `DeclaredCapabilities` still has to appear, since
    /// nothing else in the file provides it.
    #[test]
    fn recovery_does_not_duplicate_a_hand_written_trait_impl() {
        let item = quote! { impl PluginCapability for P { type Config = NoConfig; } };
        let out = recover(expand(TokenStream::new(), item.clone()).unwrap_err(), item).to_string();
        assert_eq!(out.matches("PluginCapability for P").count(), 1, "{out}");
        assert!(out.contains("DeclaredCapabilities for P"), "{out}");
    }

    /// `#[astra::plugin]` emits absolute `::astra_plugin_sdk::…` paths and
    /// nothing else. A bare `tokio::` or `serde_json::` would resolve today off
    /// the author's own dependency list and stop resolving the moment they
    /// deleted a line for a crate they never call — which is exactly what "one
    /// dependency" means.
    #[test]
    fn every_emitted_path_is_rooted_at_the_sdk() {
        let item = quote! { impl P {
            /// d
            #[tool] async fn t(&self, a: Roll) -> Result<String, ToolError> { todo!() }
            /// d
            #[action] async fn x(&self) -> Result<String, ActionError> { todo!() }
            /// d
            #[ui_call] async fn u(&self) -> Result<String, ToolError> { todo!() }
            #[hook] async fn health_check(&self) -> (bool, String) { todo!() }
        } };
        let out = expand(TokenStream::new(), item).unwrap().to_string();
        for bare in [
            "tokio ::",
            "serde_json ::",
            "serde ::",
            "async_trait ::",
            "schemars ::",
            "anyhow ::",
            "tonic ::",
        ] {
            let leaked = out
                .match_indices(bare)
                .filter(|(i, _)| !out[..*i].ends_with(":: astra_plugin_sdk :: "))
                .count();
            assert_eq!(
                leaked, 0,
                "expansion names `{bare}` without the SDK prefix:\n{out}"
            );
        }
    }
}
