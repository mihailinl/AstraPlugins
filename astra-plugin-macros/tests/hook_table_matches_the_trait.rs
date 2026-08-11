//! `#[hook]` rejects a name that is not a `PluginCapability` method, which is
//! only useful while the macro's table and the trait agree.
//!
//! The table lives in `src/hooks.rs` and the trait lives in the SDK, so nothing
//! but this test stops 5.4-style hook additions from making `#[hook]` reject a
//! method that exists — or, worse, accept one that does not and quietly produce
//! an inherent method the daemon never calls.
//!
//! It reads the trait out of `capability.rs`. That is deliberately cruder than
//! parsing with `syn`: the file is the source of truth, and a test that can
//! only fail when the *text* changes is a test whose failure always has an
//! obvious cause.

use std::collections::BTreeSet;
use std::path::PathBuf;

/// The names in `src/hooks.rs`, which is compiled into this crate.
///
/// `allow(dead_code)`: this file is compiled a second time here, on its own,
/// and only part of it is called from these tests.
#[path = "../src/hooks.rs"]
#[allow(dead_code)]
mod hooks;

fn trait_method_names() -> BTreeSet<String> {
    let path =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../astra-plugin-sdk/src/capability.rs");
    let src = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()));

    let body = src
        .split_once("pub trait PluginCapability: Send + Sync + 'static {")
        .expect("`pub trait PluginCapability` not found — did the trait move or get renamed?")
        .1;

    let mut names = BTreeSet::new();
    let mut depth = 1usize;
    for line in body.lines() {
        // Method signatures are at one level of nesting inside the trait; the
        // bodies of defaulted methods are deeper, and `fn` inside a default body
        // (there are none today, but there could be) must not be picked up.
        let trimmed = line.trim();
        if depth == 1
            && let Some(rest) = trimmed
                .strip_prefix("async fn ")
                .or_else(|| trimmed.strip_prefix("fn "))
            && let Some(name) = rest.split(['(', '<']).next()
        {
            names.insert(name.to_string());
        }
        depth += line.matches('{').count();
        let closes = line.matches('}').count();
        if closes >= depth {
            break; // end of the trait
        }
        depth -= closes;
    }
    names
}

#[test]
fn every_trait_hook_is_in_the_table_and_nothing_else_is() {
    let from_trait = trait_method_names();
    let from_table: BTreeSet<String> = hooks::KNOWN_HOOKS
        .iter()
        .map(|(n, _)| (*n).to_string())
        .collect();

    assert!(
        from_trait.len() > 30,
        "only found {} methods on PluginCapability — the scraper broke, not the table: {from_trait:?}",
        from_trait.len()
    );

    let missing: Vec<_> = from_trait.difference(&from_table).collect();
    assert!(
        missing.is_empty(),
        "these PluginCapability hooks are missing from astra-plugin-macros' \
         KNOWN_HOOKS, so `#[hook]` rejects them: {missing:?}"
    );

    let extra: Vec<_> = from_table.difference(&from_trait).collect();
    assert!(
        extra.is_empty(),
        "KNOWN_HOOKS names methods PluginCapability does not have, so `#[hook]` \
         would accept them and produce a method the daemon never calls: {extra:?}"
    );
}

#[test]
fn a_typo_suggests_the_hook_it_meant() {
    assert!(hooks::suggestions("on_startt").contains(&"on_start"));
    assert!(hooks::suggestions("on_startup").contains(&"on_start"));
    assert!(hooks::suggestions("list_tool").contains(&"list_tools"));
    assert!(hooks::suggestions("qqqqqqqqqqqqqqq").is_empty());
}

#[test]
fn capabilities_are_only_claimed_by_hooks_that_need_them() {
    assert_eq!(hooks::capability_for("call_tool"), Some("tools"));
    assert_eq!(hooks::capability_for("tts_synthesize"), Some("tts"));
    assert_eq!(hooks::capability_for("stt_load"), Some("stt"));
    assert_eq!(hooks::capability_for("ai_complete"), Some("ai_provider"));
    // Lifecycle declares nothing. A plugin with settings is not thereby a
    // plugin with capabilities.
    assert_eq!(hooks::capability_for("on_config"), None);
    assert_eq!(hooks::capability_for("on_start"), None);
    assert_eq!(hooks::capability_for("health_check"), None);
}
