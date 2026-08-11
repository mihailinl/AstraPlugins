//! The `PluginCapability` hook table.
//!
//! `#[hook]` is the escape hatch out of `#[astra::plugin]`: it moves a method
//! into the generated `impl PluginCapability` verbatim. That only works if the
//! macro knows which names are hooks — otherwise a typo (`on_startup`) silently
//! produces an inherent method the daemon will never call, which is the exact
//! class of bug a macro is supposed to remove.
//!
//! The table is also how `DeclaredCapabilities::CAPS` is derived: a plugin that
//! implements `tts_synthesize` declares `tts`, because that is what the daemon
//! has to be told before it will ever call it.
//!
//! `tests/hook_table_matches_the_trait.rs` reads `capability.rs` and asserts
//! this list is exactly the trait's method set, so the two cannot drift.

/// `(hook name, the manifest `[capabilities]` key it implies)`.
///
/// `None` means the hook is lifecycle or plumbing and implies no capability —
/// every plugin may implement `on_start`, and doing so declares nothing.
pub const KNOWN_HOOKS: &[(&str, Option<&str>)] = &[
    // Client
    ("is_client", Some("client")),
    // Tools
    ("list_tools", Some("tools")),
    ("call_tool", Some("tools")),
    // TTS
    ("tts_synthesize", Some("tts")),
    ("tts_synthesize_stream", Some("tts")),
    ("tts_voices", Some("tts")),
    ("tts_activate", Some("tts")),
    ("tts_config_fields", Some("tts")),
    // STT
    ("stt_transcribe", Some("stt")),
    ("stt_transcribe_stream", Some("stt")),
    ("stt_languages", Some("stt")),
    ("stt_load", Some("stt")),
    ("stt_unload", Some("stt")),
    ("stt_load_state", Some("stt")),
    ("stt_config_fields", Some("stt")),
    // AI
    ("ai_complete", Some("ai_provider")),
    ("ai_models", Some("ai_provider")),
    // Actions
    ("action_types", Some("actions")),
    ("execute_action", Some("actions")),
    // Triggers
    ("trigger_types", Some("triggers")),
    // UI
    ("ui_contributions", Some("ui_contributions")),
    ("handle_ui_call", Some("ui_contributions")),
    // Events
    ("source_id", None),
    ("subscribed_events", Some("event_handlers")),
    ("on_event", Some("event_handlers")),
    ("on_conversation_event", Some("client")),
    ("on_state_changed", Some("event_handlers")),
    ("on_command_triggered", Some("event_handlers")),
    ("on_command_completed", Some("event_handlers")),
    // Lifecycle — no capability. Every plugin may have settings and a start-up.
    ("on_config", None),
    ("on_config_changed", None),
    ("on_language_changed", None),
    ("on_start", None),
    ("on_active_triggers", None),
    ("on_shutdown", None),
    ("health_check", None),
];

/// The capability a hook implies, or `None`.
pub fn capability_for(hook: &str) -> Option<&'static str> {
    KNOWN_HOOKS
        .iter()
        .find(|(name, _)| *name == hook)
        .and_then(|(_, cap)| *cap)
}

pub fn is_known(hook: &str) -> bool {
    KNOWN_HOOKS.iter().any(|(name, _)| *name == hook)
}

/// Hook names within edit distance 2 of `name`, for a "did you mean" line.
///
/// A misspelled hook is the failure this macro exists to catch, so the error
/// has to do better than "unknown hook".
pub fn suggestions(name: &str) -> Vec<&'static str> {
    let mut scored: Vec<(usize, &'static str)> = KNOWN_HOOKS
        .iter()
        .map(|(hook, _)| (edit_distance(name, hook), *hook))
        .filter(|(d, _)| *d <= 3)
        .collect();
    scored.sort();
    scored.into_iter().take(3).map(|(_, h)| h).collect()
}

fn edit_distance(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut cur = vec![0usize; b.len() + 1];
    for i in 1..=a.len() {
        cur[0] = i;
        for j in 1..=b.len() {
            let sub = prev[j - 1] + usize::from(a[i - 1] != b[j - 1]);
            cur[j] = sub.min(prev[j] + 1).min(cur[j - 1] + 1);
        }
        std::mem::swap(&mut prev, &mut cur);
    }
    prev[b.len()]
}
