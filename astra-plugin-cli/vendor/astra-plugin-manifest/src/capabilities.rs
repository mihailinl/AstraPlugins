//! `[capabilities]` — what the plugin implements, daemon→plugin.
//!
//! This is the section that drifted. Read [`Capabilities`]'s `deny_unknown_fields`
//! note before relaxing anything here.

use serde::{Deserialize, Serialize};

/// Which capability interfaces the plugin implements.
///
/// **`deny_unknown_fields` is the point of this struct.** Serde's default is to
/// drop a key it does not recognise, and for a `bool`-only section that means a
/// typo or a stale name reads exactly like "not enabled". That is not a
/// hypothetical: this repository shipped three examples declaring `ui_panels`
/// — a name the daemon has never had — and the only symptom was
/// `astra-plugin check` saying "No capabilities enabled". A section that is
/// entirely opt-in flags has no benign unknown key, so an unknown key is a hard
/// parse error and the author is told the correct name (see
/// [`explain_unknown_capability`]).
///
/// The same attribute is deliberately **not** on [`crate::PluginManifest`]:
/// whole sections are added over time (`[permissions]` is next), and a daemon
/// that refused a manifest carrying a section a newer Astra understands would
/// make every forward-compatible addition a flag day.
#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Capabilities {
    #[serde(default)]
    pub tools: bool,
    #[serde(default)]
    pub tts: bool,
    #[serde(default)]
    pub stt: bool,
    #[serde(default)]
    pub ai_provider: bool,
    #[serde(default)]
    pub client: bool,
    #[serde(default)]
    pub actions: bool,
    #[serde(default)]
    pub triggers: bool,
    #[serde(default)]
    pub ui_contributions: bool,
    #[serde(default)]
    pub event_handlers: bool,
    #[serde(default)]
    pub dom_access: bool,
}

/// Every capability key the daemon deserializes, in declaration order.
///
/// Kept honest against [`Capabilities`]'s own fields by
/// `capability_names_match_the_struct` below — a field added to the struct and
/// not to this list (or the reverse) fails the build's test run rather than
/// producing a validator that accepts a key nothing reads.
pub const CAPABILITY_NAMES: &[&str] = &[
    "tools",
    "tts",
    "stt",
    "ai_provider",
    "client",
    "actions",
    "triggers",
    "ui_contributions",
    "event_handlers",
    "dom_access",
];

/// Capability names that were never real, or stopped being real, and what a
/// manifest carrying them should say instead.
///
/// `ui_panels` was `astra-plugin`'s own invention and no daemon ever read it.
pub const RENAMED_CAPABILITIES: &[(&str, &str)] = &[("ui_panels", "ui_contributions")];

/// The message a tool should show for a `[capabilities]` key the daemon does not
/// know.
///
/// Lives here rather than in the CLI so the CLI, `astra-plugin test` and the
/// registry bot all say the same thing about the same key.
pub fn explain_unknown_capability(name: &str) -> String {
    if let Some((_, replacement)) = RENAMED_CAPABILITIES.iter().find(|(old, _)| *old == name) {
        return format!(
            "Capability '{name}' does not exist — Astra calls it '{replacement}'. Rename it: a \
             manifest carrying '{name}' is now refused outright, and before that it was silently \
             dropped, which is how three shipped examples declared no capabilities at all."
        );
    }
    format!(
        "Unknown capability '{name}'. Valid: {}",
        CAPABILITY_NAMES.join(", ")
    )
}

/// Is `name` a capability the daemon deserializes?
pub fn is_known_capability(name: &str) -> bool {
    CAPABILITY_NAMES.contains(&name)
}

impl Capabilities {
    /// Return a list of capability names that are enabled.
    pub fn as_list(&self) -> Vec<String> {
        let mut list = Vec::new();
        if self.tools {
            list.push("tools".into());
        }
        if self.tts {
            list.push("tts".into());
        }
        if self.stt {
            list.push("stt".into());
        }
        if self.ai_provider {
            list.push("ai_provider".into());
        }
        if self.client {
            list.push("client".into());
        }
        if self.actions {
            list.push("actions".into());
        }
        if self.triggers {
            list.push("triggers".into());
        }
        if self.ui_contributions {
            list.push("ui_contributions".into());
        }
        if self.event_handlers {
            list.push("event_handlers".into());
        }
        if self.dom_access {
            list.push("dom_access".into());
        }
        list
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The vocabulary list, the struct's fields and `as_list` are three
    /// statements of the same fact, and a validator built on the list is only
    /// as good as their agreement.
    ///
    /// Serialising the default value enumerates the struct's *actual* serde
    /// field names, so this catches a field added without a list entry, a list
    /// entry with no field, and a rename on either side. Compared as sorted
    /// sets: `serde_json`'s map is a `BTreeMap` unless `preserve_order` is on,
    /// so its key order is alphabetical and says nothing about declaration
    /// order. Declaration order is asserted through `as_list` below instead.
    #[test]
    fn capability_names_match_the_struct() {
        let value = serde_json::to_value(Capabilities::default()).expect("Capabilities serializes");
        let mut fields: Vec<String> = value
            .as_object()
            .expect("a struct serializes to an object")
            .keys()
            .cloned()
            .collect();
        fields.sort();
        let mut names: Vec<String> = CAPABILITY_NAMES.iter().map(|s| s.to_string()).collect();
        names.sort();
        assert_eq!(
            fields, names,
            "CAPABILITY_NAMES must list exactly the fields of `Capabilities`"
        );

        // …and every name must also reach `as_list`, which is what the daemon
        // reports and the store displays.
        let all_on = CAPABILITY_NAMES
            .iter()
            .map(|n| format!("{n} = true\n"))
            .collect::<String>();
        let caps: Capabilities = toml::from_str(&all_on).expect("every listed name deserializes");
        assert_eq!(caps.as_list(), CAPABILITY_NAMES);
    }

    /// The failure this whole crate exists to prevent: a key that looks like a
    /// capability, is not one, and used to cost nothing to write.
    #[test]
    fn a_misspelled_capability_is_refused_not_dropped() {
        let err = toml::from_str::<Capabilities>("tools = true\nui_panels = true\n")
            .expect_err("an unknown capability key must not parse")
            .to_string();
        assert!(err.contains("ui_panels"), "{err}");

        let err = toml::from_str::<Capabilities>("tolos = true\n")
            .expect_err("a typo must not parse")
            .to_string();
        assert!(err.contains("tolos"), "{err}");
    }

    /// A renamed key is named, with its replacement — "unknown field" alone
    /// leaves the author guessing at a name that exists.
    #[test]
    fn a_renamed_capability_names_its_replacement() {
        let msg = explain_unknown_capability("ui_panels");
        assert!(msg.contains("ui_contributions"), "{msg}");
        let msg = explain_unknown_capability("wat");
        assert!(msg.contains("Unknown capability 'wat'"), "{msg}");
        assert!(msg.contains("ui_contributions"), "{msg}");
    }

    #[test]
    fn an_empty_capabilities_section_is_still_valid() {
        let caps: Capabilities = toml::from_str("").expect("no capabilities is a legal manifest");
        assert!(caps.as_list().is_empty());
    }
}
