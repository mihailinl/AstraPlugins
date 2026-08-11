//! `[permissions]` — what the plugin may *call*, plugin→daemon.
//!
//! The orthogonal half of [`crate::Capabilities`]. `[capabilities]` says what
//! the plugin implements and the daemon may call **into**; this section says
//! which host RPCs the plugin may call **out** to. They were one word for two
//! things, and the word meant the first one, which is how `dom_access` came to
//! be a capability a plugin granted itself by declaring it.
//!
//! ```toml
//! [permissions]
//! fire_trigger     = { reason = "Fires the on_dice_roll trigger you configure" }
//! subscribe_events = { types = ["command_completed"], reason = "…" }
//! set_variable     = { scopes = ["plugin"] }
//! ```
//!
//! # Default-deny
//!
//! PRODUCTION_PLAN §5.6: *an absent `[permissions]` section means no host RPCs
//! beyond `Register`, `PluginLog` and `GetPluginSelfConfig`.* A missing section
//! is therefore not "unspecified" — it is a complete answer, and the answer is
//! no. [`Permissions::default()`] is that answer.
//!
//! # Declaring is asking, not receiving
//!
//! **Nothing in this file is a grant.** A `[permissions]` block is the author's
//! *request*; the granted set is a separate object the daemon resolves per
//! provenance path (§5.6's four-row table) and stores where the plugin cannot
//! reach it. The daemon's `require_permission` reads the granted set and never
//! this one. That distinction is the whole point of the section: a plugin that
//! could widen its own grants by editing its own manifest would have a
//! permission system that is a comment.
//!
//! # Why unknown ids are kept, not refused
//!
//! [`Capabilities`](crate::Capabilities) is `deny_unknown_fields` because it is
//! a closed set of bools where a typo reads exactly like `false`. This section
//! is the opposite case in two ways, and both point the other direction:
//!
//! 1. **Forward compatibility.** New permission ids ship with new Astras. A
//!    daemon that refused a manifest naming an id it had not heard of would
//!    make every addition a flag day for every older daemon — the same reason
//!    [`PluginManifest`](crate::PluginManifest) is not `deny_unknown_fields`.
//! 2. **The hash.** `permissions_hash` is computed over these bytes by three
//!    implementations (the packer, the registry bot, the daemon) and is what
//!    binds a signed record to a consent decision. Dropping a key the reader
//!    did not recognise would make two implementations disagree about what was
//!    signed.
//!
//! An unknown id is inert — default-deny means it grants nothing, ever — and it
//! is *visible*: [`Permissions::unknown`] lists them so `astra-plugin check`
//! warns the author and the consent sheet can say "this plugin asks for
//! something this version of Astra does not know about" instead of nothing.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

/// One permission a plugin may hold.
///
/// The vocabulary is closed on purpose: every id here is a host RPC (or, for
/// [`Permission::DomAccess`], a renderer surface) the daemon can point at. See
/// [`PERMISSION_NAMES`] for the wire strings and `permission_names_match_the_enum`
/// for the test that keeps the two from drifting.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Permission {
    /// `PluginHostService.FireTrigger` — run the user's saved automations.
    FireTrigger,
    /// `PluginHostService.SubscribeEvents` — receive daemon events.
    ///
    /// Carries an argument: [`PermissionRequest::types`] is the **allowlist** of
    /// event types, and it is enforced by the daemon rather than by the filter
    /// the plugin sends. Without that, every subscriber received every event —
    /// including `speech_recognized`, which carries the user's transcripts.
    SubscribeEvents,
    /// `PluginHostService.SetVariable` — write into the daemon's variable
    /// context (namespaced to the calling plugin).
    SetVariable,
    /// `PluginHostService.SendChatMessage` — drive an AI turn. **High risk.**
    SendChatMessage,
    /// `PluginHostService.PushToUi` — push an event at the Astra window.
    /// **High risk.**
    PushToUi,
    /// `PluginHostService.SetThemeContribution` — restyle the whole app.
    /// **High risk.**
    SetThemeContribution,
    /// Run the plugin's own code inside the Astra window, with access to the
    /// user's conversations and every other plugin's interface. **High risk,
    /// and the one §4.3 gives a second screen.**
    DomAccess,
    /// Act as a client front-end (its own chat surface, its own session).
    /// **High risk.**
    Client,
}

/// Every permission id, in [`Permission`]'s declaration order.
///
/// Pinned to the enum by `permission_names_match_the_enum`. The registry bot
/// validates a listing's ids against this list and the app's localized label
/// table (§4.3) is keyed by it, so a name added in one place and not the others
/// is a listing that renders as a blank row.
pub const PERMISSION_NAMES: &[&str] = &[
    "fire_trigger",
    "subscribe_events",
    "set_variable",
    "send_chat_message",
    "push_to_ui",
    "set_theme_contribution",
    "dom_access",
    "client",
];

/// The five §5.6 marks *"high-risk, each its own consent checkbox"*.
///
/// §4.3 spells four checkboxes and omits `push_to_ui`; §5.6 lists five. This is
/// the union, because the disagreement is between a UI paragraph and the
/// security section, and the security section is the one that is normative
/// about risk. A checkbox too many costs a click; one too few costs the
/// property.
pub const HIGH_RISK_PERMISSIONS: &[Permission] = &[
    Permission::SendChatMessage,
    Permission::PushToUi,
    Permission::SetThemeContribution,
    Permission::DomAccess,
    Permission::Client,
];

/// The four §5.5 refuses **outright** to a Tier-2 import — *"refused outright,
/// not warned about"*.
///
/// Deliberately not the same list as [`HIGH_RISK_PERMISSIONS`]: `push_to_ui` is
/// worth a checkbox and is not worth refusing a file the user chose to import.
/// §5.5 names these four and only these four; the ceiling is quoted, not
/// inferred.
///
/// Tier 3 (a source directory the user pointed at, Developer Mode on) does
/// **not** inherit this ceiling — §5.5 is explicit, and `companion`, `doom` and
/// `bad-apple` all need the DOM path.
pub const TIER2_REFUSED_PERMISSIONS: &[Permission] = &[
    Permission::SendChatMessage,
    Permission::SetThemeContribution,
    Permission::DomAccess,
    Permission::Client,
];

impl Permission {
    /// The wire id (`"fire_trigger"`).
    pub fn id(self) -> &'static str {
        match self {
            Permission::FireTrigger => "fire_trigger",
            Permission::SubscribeEvents => "subscribe_events",
            Permission::SetVariable => "set_variable",
            Permission::SendChatMessage => "send_chat_message",
            Permission::PushToUi => "push_to_ui",
            Permission::SetThemeContribution => "set_theme_contribution",
            Permission::DomAccess => "dom_access",
            Permission::Client => "client",
        }
    }

    /// Parse a wire id. `None` for an id this build does not know — see the
    /// module note on why that is not an error.
    pub fn from_id(id: &str) -> Option<Permission> {
        ALL_PERMISSIONS.iter().copied().find(|p| p.id() == id)
    }

    /// Does this one get its own consent checkbox (§5.6)?
    pub fn is_high_risk(self) -> bool {
        HIGH_RISK_PERMISSIONS.contains(&self)
    }

    /// Is this one refused outright to a Tier-2 import (§5.5)?
    pub fn refused_at_tier2(self) -> bool {
        TIER2_REFUSED_PERMISSIONS.contains(&self)
    }
}

/// Every [`Permission`], in declaration order. The iteration source for the
/// name table, the ceiling checks and the tests.
pub const ALL_PERMISSIONS: &[Permission] = &[
    Permission::FireTrigger,
    Permission::SubscribeEvents,
    Permission::SetVariable,
    Permission::SendChatMessage,
    Permission::PushToUi,
    Permission::SetThemeContribution,
    Permission::DomAccess,
    Permission::Client,
];

/// What an author wrote for one permission id.
///
/// Field-compatible with `astra-plugin`'s `bundle::ManifestPermission` for the
/// common case: with `types` and `scopes` empty, this serialises to exactly
/// `{"reason":"…"}`, so a bundle packed by the CLI and a manifest read by the
/// daemon hash to the same `permissions_hash`.
///
/// Not `deny_unknown_fields`: an argument key added for a future permission has
/// to survive an older reader, for the same reason an unknown *id* does.
#[derive(Debug, Clone, Default, PartialEq, Eq, Deserialize, Serialize)]
pub struct PermissionRequest {
    /// The author's own words, rendered *subordinate* to the app-owned label
    /// (§4.3: quoted, plain text, ≤140 chars, always prefixed "The author
    /// says:"). It is never the label itself — wording fixes ship with Astra
    /// and must not be craftable by a listing.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub reason: String,
    /// `subscribe_events.types` — the event types asked for.
    ///
    /// **An allowlist, and an empty one allows nothing.** See
    /// [`Permissions::event_types`].
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub types: Vec<String>,
    /// `set_variable.scopes` — `"plugin"` / `"session"` / `"persistent"`.
    /// Reserved; the daemon namespaces every plugin write by plugin id today,
    /// so this narrows nothing yet and is parsed so a manifest declaring it
    /// hashes the same everywhere.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub scopes: Vec<String>,
}

impl PermissionRequest {
    /// A bare request with only a reason — the shape most permissions take.
    pub fn with_reason(reason: impl Into<String>) -> Self {
        Self {
            reason: reason.into(),
            ..Default::default()
        }
    }
}

/// The whole `[permissions]` section: id → request.
///
/// A `BTreeMap` because the order has to be an intrinsic property of the
/// content and not of the reader — `permissions_hash` is computed over these
/// bytes in three repositories.
#[derive(Debug, Clone, Default, PartialEq, Eq, Deserialize, Serialize)]
#[serde(transparent)]
pub struct Permissions(pub BTreeMap<String, PermissionRequest>);

impl Permissions {
    /// The empty section — §5.6's default-deny answer, named so the call sites
    /// that mean it are greppable.
    pub fn none() -> Self {
        Self(BTreeMap::new())
    }

    /// Build from `(id, request)` pairs. Ids this build does not know are kept,
    /// exactly as they would be if they had been parsed.
    pub fn from_pairs<I, S>(pairs: I) -> Self
    where
        I: IntoIterator<Item = (S, PermissionRequest)>,
        S: Into<String>,
    {
        Self(pairs.into_iter().map(|(k, v)| (k.into(), v)).collect())
    }

    /// Nothing is asked for at all.
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    /// The raw section, ids and all — including ones this build cannot resolve.
    pub fn raw(&self) -> &BTreeMap<String, PermissionRequest> {
        &self.0
    }

    /// The request for `permission`, if the section names it.
    pub fn get(&self, permission: Permission) -> Option<&PermissionRequest> {
        self.0.get(permission.id())
    }

    /// Does the section name `permission`?
    ///
    /// On a *declared* set this answers "did the author ask?"; on a *granted*
    /// set it answers "may they?". Only the daemon's granted set is an
    /// authorisation.
    pub fn contains(&self, permission: Permission) -> bool {
        self.0.contains_key(permission.id())
    }

    /// Every id in the section that this build recognises, in enum order.
    pub fn known(&self) -> Vec<Permission> {
        ALL_PERMISSIONS
            .iter()
            .copied()
            .filter(|p| self.contains(*p))
            .collect()
    }

    /// Ids in the section that this build does not recognise, sorted.
    ///
    /// Not an error (see the module note) and not silent either: tooling warns
    /// on these and the consent sheet shows them as unrecognised rather than
    /// pretending the author asked for nothing.
    pub fn unknown(&self) -> Vec<&str> {
        self.0
            .keys()
            .map(String::as_str)
            .filter(|id| Permission::from_id(id).is_none())
            .collect()
    }

    /// The **event-type allowlist** for `subscribe_events`.
    ///
    /// * `None` — the permission is not held. No stream at all.
    /// * `Some(&[])` — held, with no types named. **Allows nothing**, and the
    ///   daemon refuses the subscription with a message naming the fix rather
    ///   than handing back a stream that is silent forever.
    /// * `Some(types)` — exactly those `AstraEvent::event_type_str()` values.
    ///
    /// The empty case is the one worth stating out loud, because the intuitive
    /// reading ("no filter = everything") is the hole this permission exists to
    /// close: today a subscriber with no types receives `speech_recognized`,
    /// i.e. every word the user says.
    pub fn event_types(&self) -> Option<&[String]> {
        self.get(Permission::SubscribeEvents)
            .map(|r| r.types.as_slice())
    }

    /// Drop every permission `keep` rejects.
    ///
    /// The ceilings in §5.5 are applied with this: a Tier-2 import is
    /// `capped(|p| !p.refused_at_tier2())`. Unknown ids are dropped too — a
    /// ceiling that let through the ids it could not classify would be a
    /// ceiling with a hole shaped like the next release.
    pub fn capped(&self, keep: impl Fn(Permission) -> bool) -> Permissions {
        Permissions(
            self.0
                .iter()
                .filter(|(id, _)| Permission::from_id(id).is_some_and(&keep))
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect(),
        )
    }
}

/// The message tooling shows for a `[permissions]` id the daemon does not know.
///
/// Lives here rather than in the CLI so `astra-plugin check`, `astra-plugin
/// test` and the registry bot say the same thing about the same id — the same
/// reason [`explain_unknown_capability`](crate::explain_unknown_capability)
/// does.
pub fn explain_unknown_permission(id: &str) -> String {
    if crate::is_known_capability(id) && Permission::from_id(id).is_none() {
        return format!(
            "'{id}' is a [capabilities] key, not a [permissions] id. [capabilities] says what \
             your plugin implements and Astra may call into; [permissions] says which host RPCs \
             your plugin may call out to. Valid permissions: {}",
            PERMISSION_NAMES.join(", ")
        );
    }
    format!(
        "Unknown permission '{id}'. This Astra grants nothing for it. Valid: {}",
        PERMISSION_NAMES.join(", ")
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The enum, the name list and `from_id` are three statements of one fact.
    /// A variant added without a name (or the reverse) would produce a
    /// validator that accepts an id nothing can grant.
    #[test]
    fn permission_names_match_the_enum() {
        let ids: Vec<&str> = ALL_PERMISSIONS.iter().map(|p| p.id()).collect();
        assert_eq!(
            ids, PERMISSION_NAMES,
            "PERMISSION_NAMES must list exactly ALL_PERMISSIONS, in declaration order"
        );
        for name in PERMISSION_NAMES {
            assert_eq!(
                Permission::from_id(name).map(Permission::id),
                Some(*name),
                "{name} must round-trip through from_id"
            );
        }
        assert_eq!(Permission::from_id("ui_panels"), None);
        assert_eq!(Permission::from_id(""), None);
    }

    /// §5.5's ceiling is a quotation, not a derivation. If someone later
    /// "tidies" it into `is_high_risk`, a Tier-2 import silently gains
    /// `push_to_ui`; if they tidy the other way, a verified plugin loses a
    /// checkbox. Both lists are pinned here, by name.
    #[test]
    fn the_two_risk_lists_are_deliberately_different() {
        assert!(Permission::PushToUi.is_high_risk());
        assert!(
            !Permission::PushToUi.refused_at_tier2(),
            "§5.5 names four refusals and push_to_ui is not one of them"
        );
        for p in TIER2_REFUSED_PERMISSIONS {
            assert!(
                p.is_high_risk(),
                "{} is refused at Tier 2 but not marked high-risk",
                p.id()
            );
        }
        assert_eq!(HIGH_RISK_PERMISSIONS.len(), 5);
        assert_eq!(TIER2_REFUSED_PERMISSIONS.len(), 4);
    }

    /// The section as §5.6 writes it, parsed.
    #[test]
    fn the_section_from_the_plan_parses() {
        let toml = r#"
fire_trigger     = { reason = "Fires the on_dice_roll trigger you configure" }
subscribe_events = { types = ["command_completed"], reason = "watch commands" }
set_variable     = { scopes = ["plugin"] }
"#;
        let perms: Permissions = toml::from_str(toml).expect("the plan's own example parses");
        assert!(perms.contains(Permission::FireTrigger));
        assert_eq!(
            perms.get(Permission::FireTrigger).unwrap().reason,
            "Fires the on_dice_roll trigger you configure"
        );
        assert_eq!(
            perms.event_types(),
            Some(["command_completed".to_string()].as_slice())
        );
        assert_eq!(
            perms.get(Permission::SetVariable).unwrap().scopes,
            vec!["plugin"]
        );
        assert!(!perms.contains(Permission::DomAccess));
        assert_eq!(perms.known().len(), 3);
        assert!(perms.unknown().is_empty());
    }

    /// Absent means **no**, not "unspecified". The whole default-deny rule is
    /// this one assertion.
    #[test]
    fn an_absent_section_grants_nothing() {
        let perms = Permissions::default();
        assert!(perms.is_empty());
        for p in ALL_PERMISSIONS {
            assert!(!perms.contains(*p), "{} must not be granted", p.id());
        }
        assert_eq!(perms.event_types(), None);
    }

    /// Held with no types is not "all types". The intuitive reading is the
    /// hole: a subscriber with no filter receives `speech_recognized`.
    #[test]
    fn subscribe_events_with_no_types_allows_nothing() {
        let perms: Permissions =
            toml::from_str(r#"subscribe_events = { reason = "everything please" }"#).unwrap();
        assert_eq!(
            perms.event_types(),
            Some([].as_slice()),
            "held-but-empty is a distinct state from not-held, and it allows nothing"
        );
    }

    /// An id from a newer Astra costs nothing and is not hidden.
    #[test]
    fn an_unknown_id_is_kept_inert_and_visible() {
        let perms: Permissions = toml::from_str(
            "fire_trigger = { reason = \"a\" }\nread_the_users_mail = { reason = \"b\" }\n",
        )
        .expect("an unknown id must not fail the parse — an older daemon meets newer manifests");
        assert_eq!(perms.unknown(), vec!["read_the_users_mail"]);
        assert_eq!(perms.known(), vec![Permission::FireTrigger]);
        assert_eq!(
            perms.raw().len(),
            2,
            "the unknown id stays in the map: permissions_hash covers these bytes in three repos"
        );
        let msg = explain_unknown_permission("read_the_users_mail");
        assert!(msg.contains("read_the_users_mail"), "{msg}");
        assert!(msg.contains("fire_trigger"), "{msg}");
    }

    /// The confusion the two sections exist to end, caught by name.
    #[test]
    fn a_capability_key_used_as_a_permission_is_explained() {
        let msg = explain_unknown_permission("tools");
        assert!(msg.contains("[capabilities]"), "{msg}");
        assert!(msg.contains("[permissions]"), "{msg}");
        // …and the two names that are BOTH is not a mistake to explain away.
        assert!(Permission::from_id("dom_access").is_some());
        assert!(Permission::from_id("client").is_some());
    }

    /// The Tier-2 ceiling, applied. An unknown id is dropped as well: a
    /// ceiling that passed through what it could not classify would have a hole
    /// shaped like the next release.
    #[test]
    fn capping_drops_the_refused_and_the_unclassifiable() {
        let perms: Permissions = toml::from_str(
            "dom_access = {}\nclient = {}\nsend_chat_message = {}\nset_theme_contribution = {}\n\
             push_to_ui = {}\nfire_trigger = {}\nfrom_the_future = {}\n",
        )
        .unwrap();
        let capped = perms.capped(|p| !p.refused_at_tier2());
        assert_eq!(
            capped.known(),
            vec![Permission::FireTrigger, Permission::PushToUi],
        );
        assert!(
            capped.unknown().is_empty(),
            "unknown ids do not survive a cap"
        );
        // …and a Tier-3 sideload's "no ceiling" keeps everything it knows.
        let uncapped = perms.capped(|_| true);
        assert_eq!(uncapped.known().len(), 6);
    }

    /// The bytes three repositories hash. A bare `{reason}` request must
    /// serialise to exactly what `astra-plugin`'s `ManifestPermission` does, or
    /// the packer's `permissions_hash` and the daemon's disagree about a
    /// manifest neither of them changed.
    #[test]
    fn a_bare_request_serialises_like_the_packers() {
        let perms =
            Permissions::from_pairs([("fire_trigger", PermissionRequest::with_reason("x"))]);
        assert_eq!(
            serde_json::to_string(&perms).unwrap(),
            r#"{"fire_trigger":{"reason":"x"}}"#
        );
        let empty = Permissions::from_pairs([("client", PermissionRequest::default())]);
        assert_eq!(serde_json::to_string(&empty).unwrap(), r#"{"client":{}}"#);
        assert_eq!(serde_json::to_string(&Permissions::none()).unwrap(), "{}");
    }
}
