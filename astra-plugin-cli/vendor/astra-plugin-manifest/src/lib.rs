//! `plugin.toml` — one definition, shared by everything that reads one.
//!
//! The daemon, `astra-plugin` and the registry bot all have to agree on what a
//! plugin manifest *is*. They did not: the CLI carried its own struct, and it
//! grew a `ui_panels` capability the daemon had never had. Because serde drops
//! unknown fields by default, the disagreement was invisible — three shipped
//! examples declared `ui_panels`, the daemon read no capabilities from them at
//! all, and the only symptom anyone saw was `astra-plugin check` printing
//! "No capabilities enabled". A third fork was about to be written for the
//! registry bot.
//!
//! So there is one crate, and the parse the daemon performs is the parse the
//! author's tooling performs.
//!
//! # What is in here, and what is not
//!
//! Everything that can be decided from the manifest text alone: the types, the
//! `plugin.id` charset and reserved-name rules (`plugin.id` becomes a directory
//! name), the `[platform]` vocabulary, and the capability vocabulary. Nothing
//! that needs a running daemon, a filesystem layout or a network.
//!
//! The one host-dependent rule — is `plugin.min_astra_version` satisfied by the
//! Astra that is *running*? — is behind the `astra-host` feature. Its **syntax**
//! is checked everywhere; its **value** is compared only in a build that is a
//! host. See [`host_astra_version`].
//!
//! # Vendoring
//!
//! This crate is **vendored, not published.** `AstraPlugins` carries a copy at
//! `astra-plugin-cli/vendor/astra-plugin-manifest/` and
//! `AstraPlugins/tools/check-manifest-crate.sh` fails when the two `src/` trees
//! differ. `README.md` records why that was chosen over crates.io.

mod capabilities;
mod manifest;
mod platform;

pub use capabilities::{
    CAPABILITY_NAMES, Capabilities, RENAMED_CAPABILITIES, explain_unknown_capability,
    is_known_capability,
};
pub use manifest::{
    BuildSection, ConfigSection, EntryConfig, PluginLocales, PluginManifest, PluginMeta,
    UiContributionDef, UiSection, is_reserved_device_name,
};
pub use platform::{
    KNOWN_ARCH_VALUES, KNOWN_OS_VALUES, PlatformRequirements, RESERVED_PLATFORM_KEYS,
    UnsupportedHost, current_platform, host_platform_key, platform_key_for,
};

/// The version of Astra this build validates `min_astra_version` against, or
/// `None` when this build is a tool rather than a host.
///
/// Two consumers, two correct answers. The daemon **is** an Astra, so a manifest
/// asking for a newer one must be refused at parse time — that is the check
/// that stops an install which would otherwise succeed and then fail at the one
/// call that needed the missing feature. `astra-plugin` and the registry bot are
/// not an Astra and have no business refusing to *look at* a plugin that targets
/// a newer daemon than the tool's own build; for them the honest answer is
/// "no host here", and only the field's syntax is enforced.
///
/// A `Cargo` feature rather than a runtime setter on purpose: a setter has an
/// initialisation order, and "the daemon forgot to call it in this code path"
/// is exactly the silent-drop failure this crate exists to end.
#[cfg(feature = "astra-host")]
pub fn host_astra_version() -> Option<&'static str> {
    Some(astra_core::VERSION)
}

/// See the `astra-host` variant above. A build without that feature is not a
/// host and says so.
#[cfg(not(feature = "astra-host"))]
pub fn host_astra_version() -> Option<&'static str> {
    None
}
