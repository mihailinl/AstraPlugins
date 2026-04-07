//! `astra-plugin validate` — check manifest, config schema, structure.

use std::path::Path;

use anyhow::{Context, Result};
use serde::Deserialize;

pub fn run(path: &str) -> Result<()> {
    let dir = Path::new(path);
    let manifest_path = dir.join("plugin.toml");

    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }

    println!("Validating plugin at {}...", dir.display());

    let content =
        std::fs::read_to_string(&manifest_path).context("Failed to read plugin.toml")?;

    let manifest: PluginManifest =
        toml::from_str(&content).context("Failed to parse plugin.toml")?;

    let mut errors: Vec<String> = Vec::new();
    let mut warnings: Vec<String> = Vec::new();

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

    // Capabilities check
    let caps = &manifest.capabilities;
    let has_any = caps.tools
        || caps.tts
        || caps.stt
        || caps.ai_provider
        || caps.client
        || caps.actions
        || caps.triggers
        || caps.ui_panels
        || caps.event_handlers;
    if !has_any {
        warnings.push("No capabilities enabled — plugin won't do anything".into());
    }

    // Config schema validation
    if let Some(ref config) = manifest.config {
        if !config.schema.is_empty() {
            match serde_json::from_str::<serde_json::Value>(&config.schema) {
                Ok(schema) => {
                    if schema.get("type").and_then(|t| t.as_str()) != Some("object") {
                        warnings
                            .push("config.schema should have \"type\": \"object\" at root".into());
                    }
                }
                Err(e) => {
                    errors.push(format!("config.schema is not valid JSON: {e}"));
                }
            }
        }
    }

    // Metadata completeness
    if manifest.plugin.description.is_empty() {
        warnings.push("Missing plugin.description".into());
    }
    if manifest.plugin.author.is_empty() {
        warnings.push("Missing plugin.author".into());
    }

    // Report results
    for w in &warnings {
        println!("  WARN: {w}");
    }
    for e in &errors {
        println!("  ERROR: {e}");
    }

    if errors.is_empty() {
        println!(
            "  OK: plugin '{}' v{} is valid ({} warning(s))",
            manifest.plugin.id,
            manifest.plugin.version,
            warnings.len()
        );
        Ok(())
    } else {
        anyhow::bail!(
            "Validation failed with {} error(s) and {} warning(s)",
            errors.len(),
            warnings.len()
        )
    }
}

// Minimal manifest struct for validation (mirrors daemon's PluginManifest)
#[derive(Deserialize)]
struct PluginManifest {
    plugin: PluginMeta,
    entry: EntryConfig,
    #[serde(default)]
    capabilities: Capabilities,
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

#[derive(Default, Deserialize)]
struct Capabilities {
    #[serde(default)]
    tools: bool,
    #[serde(default)]
    tts: bool,
    #[serde(default)]
    stt: bool,
    #[serde(default)]
    ai_provider: bool,
    #[serde(default)]
    client: bool,
    #[serde(default)]
    actions: bool,
    #[serde(default)]
    triggers: bool,
    #[serde(default)]
    ui_panels: bool,
    #[serde(default)]
    event_handlers: bool,
}

#[derive(Deserialize)]
struct ConfigSection {
    #[serde(default)]
    schema: String,
}
