//! `astra-plugin check` — check manifest, config schema, structure.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result};
use serde::Deserialize;

/// The capability vocabulary, verbatim from the daemon's `Capabilities` struct
/// (`Astra/astra-rs/astra-daemon/src/plugins/manifest.rs`).
///
/// The daemon is the only authority here: a name it does not deserialize is a
/// capability the plugin does not have, however plausible it looks. This list
/// is duplicated rather than shared only until the shared manifest crate lands.
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

/// Capability names that were renamed, and what they became.
///
/// `ui_panels` never existed in the daemon — it was this CLI's own invention,
/// so a manifest carrying it declared nothing at all and the plugin's UI
/// contributions were silently dropped.
const RENAMED_CAPABILITIES: &[(&str, &str)] = &[("ui_panels", "ui_contributions")];

/// Validate one capability name against the daemon's vocabulary.
pub fn check_capability_name(name: &str) -> Result<()> {
    if CAPABILITY_NAMES.contains(&name) {
        return Ok(());
    }
    if let Some((_, replacement)) = RENAMED_CAPABILITIES.iter().find(|(old, _)| *old == name) {
        anyhow::bail!(
            "Capability '{name}' does not exist — Astra calls it '{replacement}'. \
             A plugin declaring '{name}' declares nothing: the daemon ignores the key."
        );
    }
    anyhow::bail!(
        "Unknown capability '{name}'. Valid: {}",
        CAPABILITY_NAMES.join(", ")
    )
}

/// Check a plugin directory.
///
/// `strict` promotes every warning to an error — what CI and `astra-plugin dev`
/// use, so a manifest problem is caught before the daemon is asked to run it.
pub fn run(path: &str, strict: bool) -> Result<()> {
    let dir = Path::new(path);
    let manifest_path = dir.join("plugin.toml");

    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }

    println!("Checking plugin at {}...", dir.display());

    let content =
        std::fs::read_to_string(&manifest_path).context("Failed to read plugin.toml")?;

    let manifest: PluginManifest =
        toml::from_str(&content).context("Failed to parse plugin.toml")?;

    let mut errors: Vec<String> = Vec::new();
    // Warnings are things that will bite at run time — `--strict` fails on them.
    let mut warnings: Vec<String> = Vec::new();
    // Notes are publish-time metadata gaps. They must NOT be strict-fatal, or
    // the first `astra-plugin dev` on a fresh scaffold would fail on an empty
    // `author` field before the plugin ever ran.
    let mut notes: Vec<String> = Vec::new();

    // Required fields
    if manifest.plugin.id.is_empty() {
        errors.push("plugin.id is required".into());
    }
    if manifest.plugin.name.is_empty() {
        errors.push("plugin.name is required".into());
    }
    if manifest.plugin.version.is_empty() {
        errors.push("plugin.version is required".into());
    }
    if manifest.entry.command.is_empty() {
        errors.push("entry.command is required".into());
    }

    // ID format
    if !manifest
        .plugin
        .id
        .chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
    {
        errors.push(format!(
            "plugin.id must be lowercase alphanumeric with hyphens, got '{}'",
            manifest.plugin.id
        ));
    }

    // Version format (basic semver check)
    let version_parts: Vec<&str> = manifest.plugin.version.split('.').collect();
    if version_parts.len() < 2 || version_parts.len() > 3 {
        warnings.push("plugin.version should follow semver (e.g., 1.0.0)".into());
    }

    // Capabilities check. The keys are validated by name against the daemon's
    // vocabulary: an unknown key is an error, not a warning, because the daemon
    // drops it in silence and the author would ship a plugin that does nothing.
    let mut enabled: Vec<&str> = Vec::new();
    let mut bad_capability_names = false;
    for (name, on) in &manifest.capabilities {
        if let Err(e) = check_capability_name(name) {
            errors.push(format!("[capabilities] {e}"));
            bad_capability_names = true;
            continue;
        }
        if *on {
            enabled.push(name);
        }
    }
    if enabled.is_empty() && !bad_capability_names {
        warnings.push("No capabilities enabled — plugin won't do anything".into());
    }

    // Config schema validation
    if let Some(ref config) = manifest.config
        && !config.schema.is_empty()
    {
        match serde_json::from_str::<serde_json::Value>(&config.schema) {
            Ok(schema) => {
                if schema.get("type").and_then(|t| t.as_str()) != Some("object") {
                    warnings.push("config.schema should have \"type\": \"object\" at root".into());
                }
            }
            Err(e) => {
                errors.push(format!("config.schema is not valid JSON: {e}"));
            }
        }
    }

    // Metadata completeness — needed to publish, not to run.
    if manifest.plugin.description.is_empty() {
        notes.push("Missing plugin.description".into());
    }
    if manifest.plugin.author.is_empty() {
        notes.push("Missing plugin.author".into());
    }

    // Report results
    for n in &notes {
        println!("  NOTE: {n}");
    }
    for w in &warnings {
        println!("  WARN: {w}");
    }
    for e in &errors {
        println!("  ERROR: {e}");
    }

    if !errors.is_empty() {
        anyhow::bail!(
            "Check failed with {} error(s) and {} warning(s)",
            errors.len(),
            warnings.len()
        );
    }
    if strict && !warnings.is_empty() {
        anyhow::bail!(
            "Check failed: {} warning(s), and --strict treats warnings as errors",
            warnings.len()
        );
    }

    println!(
        "  OK: plugin '{}' v{} is valid ({} warning(s), {} note(s), capabilities: {})",
        manifest.plugin.id,
        manifest.plugin.version,
        warnings.len(),
        notes.len(),
        if enabled.is_empty() {
            "none".to_string()
        } else {
            enabled.join(", ")
        }
    );
    Ok(())
}

// Minimal manifest struct for validation (mirrors the daemon's PluginManifest).
#[derive(Deserialize)]
struct PluginManifest {
    plugin: PluginMeta,
    entry: EntryConfig,
    /// Deliberately NOT a struct: a forked copy of the daemon's `Capabilities`
    /// drifted once already (it grew `ui_panels`, which the daemon has never
    /// had) and a struct silently swallows any key it does not know. A map lets
    /// the check above validate names against one list.
    #[serde(default)]
    capabilities: BTreeMap<String, bool>,
    #[serde(default)]
    config: Option<ConfigSection>,
}

#[derive(Deserialize)]
struct PluginMeta {
    #[serde(default)]
    id: String,
    #[serde(default)]
    name: String,
    #[serde(default)]
    version: String,
    #[serde(default)]
    description: String,
    #[serde(default)]
    author: String,
}

#[derive(Deserialize)]
struct EntryConfig {
    #[serde(default)]
    command: String,
}

#[derive(Deserialize)]
struct ConfigSection {
    #[serde(default)]
    schema: String,
}
