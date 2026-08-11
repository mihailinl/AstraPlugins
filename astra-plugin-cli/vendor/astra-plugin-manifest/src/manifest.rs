//! `plugin.toml` — the manifest itself.

use std::collections::HashMap;
use std::path::Path;

use anyhow::{Context, Result};
use serde::Deserialize;

use crate::capabilities::Capabilities;
use crate::permissions::Permissions;
use crate::platform::{PlatformRequirements, current_platform};

/// Loaded locale data for a plugin — maps language code to flat key-value translations.
pub type PluginLocales = HashMap<String, HashMap<String, String>>;

/// Complete plugin manifest parsed from `plugin.toml`.
///
/// Deliberately **not** `deny_unknown_fields`: sections are added over releases
/// — `[permissions]` was the last one — and an older daemon must skip a section
/// it does not know rather than refuse the plugin. `[capabilities]` is the
/// exception, and [`Capabilities`] explains why.
#[derive(Debug, Clone, Deserialize)]
pub struct PluginManifest {
    pub plugin: PluginMeta,
    pub entry: EntryConfig,
    /// What the plugin **implements**, daemon→plugin.
    #[serde(default)]
    pub capabilities: Capabilities,
    /// What the plugin asks to **call**, plugin→daemon — and it is an *ask*.
    ///
    /// Absent means no host RPC beyond the always-allowed bootstrap set (§5.6).
    /// The set a plugin actually holds is resolved by the daemon from its
    /// provenance and is never read from here for a plugin that has a trust
    /// record: a manifest lives in the plugin's own directory, which the plugin
    /// can write.
    #[serde(default)]
    pub permissions: Permissions,
    #[serde(default)]
    pub config: Option<ConfigSection>,
    #[serde(default)]
    pub dependencies: HashMap<String, String>,
    #[serde(default)]
    pub platform: PlatformRequirements,
    #[serde(default)]
    pub build: Option<BuildSection>,
    #[serde(default)]
    pub ui: Option<UiSection>,
}

/// Plugin identity and metadata.
#[derive(Debug, Clone, Deserialize)]
pub struct PluginMeta {
    pub id: String,
    pub name: String,
    pub version: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub author: String,
    #[serde(default)]
    pub license: String,
    #[serde(default)]
    pub homepage: String,
    /// The oldest Astra this plugin works on, as a semver version (`"0.9.0"`).
    /// Empty = no requirement.
    ///
    /// Its *syntax* is validated by [`PluginManifest::validate`] everywhere. Its
    /// *value* is compared against the running Astra only in a build that knows
    /// one — see [`crate::host_astra_version`]. It existed for a whole release
    /// as a field that was parsed and never read, so a plugin needing a daemon
    /// feature the host did not have installed cleanly and then failed at the
    /// one call that needed it, which the user reads as "this plugin is broken".
    #[serde(default)]
    pub min_astra_version: String,
    /// How long the daemon waits for `CallTool` / `ExecuteAction` before giving
    /// up, in seconds. `None` → the daemon's `PLUGIN_CALL_TIMEOUT`.
    ///
    /// A plugin that fronts a long-running agent must declare this: the daemon's
    /// default is deliberately lower than "forever", and a plugin whose own work
    /// budget exceeds it would have its result thrown away while its subprocess
    /// keeps running (`coding-agents` ships a 180 s default). Per-plugin, the
    /// same way `McpServerConfig::timeout_secs` is per-server.
    #[serde(default)]
    pub call_timeout_secs: Option<u64>,
}

/// How to start the plugin process.
#[derive(Debug, Clone, Deserialize)]
pub struct EntryConfig {
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default = "default_cwd")]
    pub cwd: String,
    #[serde(default)]
    pub runtimes: Vec<String>,
}

fn default_cwd() -> String {
    ".".to_string()
}

/// JSON Schema for plugin configuration (auto-generates settings UI).
#[derive(Debug, Clone, Deserialize)]
pub struct ConfigSection {
    /// JSON Schema as a string.
    pub schema: String,
}

/// Build metadata added by `astra-plugin build`.
#[derive(Debug, Clone, Deserialize)]
pub struct BuildSection {
    #[serde(default)]
    pub bundled: bool,
    #[serde(default)]
    pub language: String,
    #[serde(default)]
    pub python_version: String,
    #[serde(default)]
    pub requirements_lock: String,
}

/// UI contribution definitions declared in plugin.toml.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct UiSection {
    #[serde(default)]
    pub contributions: Vec<UiContributionDef>,
}

/// A static UI contribution definition from the manifest.
#[derive(Debug, Clone, Deserialize)]
pub struct UiContributionDef {
    pub id: String,
    #[serde(default)]
    pub slot: String,
    #[serde(default)]
    pub css_target: String,
    #[serde(default)]
    pub position: String,
    #[serde(default)]
    pub url: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub icon_svg: String,
    #[serde(default)]
    pub width: i32,
    #[serde(default)]
    pub height: i32,
    #[serde(default)]
    pub transparent: bool,
    #[serde(default = "default_pointer_events")]
    pub pointer_events: bool,
    #[serde(default)]
    pub z_index: i32,
    #[serde(default)]
    pub props: HashMap<String, String>,
}

fn default_pointer_events() -> bool {
    true
}

/// Reserved MS-DOS device names. Creating `<plugins_dir>/con/` on Windows does not
/// create a directory — the path resolves to the console device, so opens succeed,
/// writes go nowhere and `remove_dir_all` behaves in ways no caller anticipates.
/// Refused on every OS, not just Windows: a plugin published from Linux with
/// `id = "con"` must not be installable-here / broken-there, and the Linux CI is
/// where this test actually runs.
///
/// `pub` because the registry bot rejects such an id at ingest, before any daemon
/// ever sees the bundle, and it must use this predicate rather than its own.
pub fn is_reserved_device_name(id: &str) -> bool {
    // `plugin.id` is already constrained to lowercase, but compare
    // case-insensitively so this predicate stays correct if reused.
    let lower = id.to_ascii_lowercase();
    // Windows matches the device name before the first '.', so `con.txt` is also
    // the console. Ids carry no dots today; the split keeps that from mattering.
    let stem = lower.split('.').next().unwrap_or("");
    if matches!(stem, "con" | "prn" | "aux" | "nul") {
        return true;
    }
    // `com1`..`com9` / `lpt1`..`lpt9`. Byte-wise: `stem` may hold non-ASCII, and
    // slicing it by index would panic on a char boundary.
    let b = stem.as_bytes();
    b.len() == 4 && matches!(&b[..3], b"com" | b"lpt") && b[3].is_ascii_digit() && b[3] != b'0'
}

impl PluginManifest {
    /// Parse a `plugin.toml` from a file path.
    pub fn from_file(path: &Path) -> Result<Self> {
        let content = std::fs::read_to_string(path)
            .with_context(|| format!("Failed to read {}", path.display()))?;
        Self::from_str(&content)
    }

    /// Parse a `plugin.toml` from a string.
    pub fn from_str(content: &str) -> Result<Self> {
        let manifest: PluginManifest =
            toml::from_str(content).context("Failed to parse plugin.toml")?;
        manifest.validate()?;
        Ok(manifest)
    }

    /// Basic validation of required fields.
    ///
    /// SECURITY: `plugin.id` becomes a **path component** — `<plugins_dir>/<id>/` —
    /// the moment an archive is installed, and that directory is created and
    /// `remove_dir_all`'d. So this is the charset gate that stops an
    /// attacker-supplied id from naming a directory somewhere else. It is not the
    /// only gate: the install path also proves component-wise that the resolved
    /// directory is a direct child of `plugins_dir`
    /// (`PluginManager::plugin_dir_for`). Two independent checks, because this
    /// one is only reached if every parse site remembers to go through
    /// [`Self::from_str`] / [`Self::from_file`] — a bare `toml::from_str` on the
    /// install path skipped it for a whole release.
    pub fn validate(&self) -> Result<()> {
        if self.plugin.id.is_empty() {
            anyhow::bail!("plugin.id is required");
        }
        if self.plugin.name.is_empty() {
            anyhow::bail!("plugin.name is required");
        }
        if self.plugin.version.is_empty() {
            anyhow::bail!("plugin.version is required");
        }
        if self.entry.command.is_empty() {
            anyhow::bail!("entry.command is required");
        }
        // Validate plugin ID: lowercase alphanumeric + hyphens
        if !self
            .plugin
            .id
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
        {
            anyhow::bail!(
                "plugin.id must be lowercase alphanumeric with hyphens: '{}'",
                self.plugin.id
            );
        }
        // A trailing dot or space is silently STRIPPED by the Win32 path layer, so
        // `foo.` and `foo` name the same directory there while comparing unequal in
        // Rust — enough to make an id-vs-directory check disagree with the filesystem.
        // The charset rule above already excludes both characters; this is deliberate
        // belt-and-braces, so relaxing the charset later (dots in ids are a common
        // request) cannot silently reintroduce the hole.
        if self.plugin.id.ends_with('.') || self.plugin.id.ends_with(' ') {
            anyhow::bail!(
                "plugin.id must not end with a dot or space: '{}'",
                self.plugin.id
            );
        }
        if is_reserved_device_name(&self.plugin.id) {
            anyhow::bail!(
                "plugin.id '{}' is a reserved Windows device name",
                self.plugin.id
            );
        }
        // Syntax always, in every consumer: a `min_astra_version` that is not a
        // semver version is a declared constraint that constrains nothing, and
        // the author must hear about it from `astra-plugin check` rather than
        // from a user's daemon.
        self.required_astra_version()?;
        // Value only where a host version exists to compare against. A tool
        // validating a manifest is not a host, and refusing to *check* a plugin
        // because it needs a newer Astra than the CLI's own version would be
        // nonsense.
        if let Some(host) = crate::host_astra_version() {
            self.check_min_astra_version(host)?;
        }
        Ok(())
    }

    /// The parsed `plugin.min_astra_version`, or `None` when the manifest
    /// declares no requirement.
    ///
    /// `Err` when the field is present and unparseable — see [`Self::validate`].
    pub fn required_astra_version(&self) -> Result<Option<semver::Version>> {
        let required = self.plugin.min_astra_version.trim();
        if required.is_empty() {
            return Ok(None);
        }
        let parsed = semver::Version::parse(required).with_context(|| {
            format!(
                "plugin.min_astra_version '{}' is not a semver version (expected e.g. \"0.9.0\")",
                self.plugin.min_astra_version
            )
        })?;
        Ok(Some(parsed))
    }

    /// Refuse a plugin that needs a newer Astra than `astra_version`.
    ///
    /// Called from [`Self::validate`] in a build that knows the running Astra,
    /// so it covers every path that parses a manifest through the validating
    /// constructors — install from an archive, import, sideload, and `discover()`
    /// at boot. That last one is deliberate and not merely incidental: a plugin
    /// can also become incompatible without anyone installing anything, by the
    /// user *downgrading* Astra, and the honest answer there is the same named
    /// refusal rather than a plugin that starts and then misbehaves.
    ///
    /// `astra_version` is a parameter rather than a read of the host constant so
    /// the rule is testable at versions this build is not — and so the registry
    /// bot can ask "would this install on Astra 0.9.0?" without being one.
    ///
    /// Semver comparison throughout, including its pre-release rule:
    /// `0.2.0-rc1 < 0.2.0`, so a release candidate does NOT satisfy a plugin
    /// that asked for the final. That is the conservative reading and the one
    /// semver specifies.
    pub fn check_min_astra_version(&self, astra_version: &str) -> Result<()> {
        let Some(required) = self.required_astra_version()? else {
            return Ok(());
        };
        // Our own version comes from `CARGO_PKG_VERSION`, which cargo guarantees
        // is semver — but if that ever stopped being true, disabling every
        // plugin on the machine would be a far worse failure than not enforcing
        // this one field, so an unparseable host version skips the comparison.
        let Ok(running) = semver::Version::parse(astra_version) else {
            return Ok(());
        };
        anyhow::ensure!(
            running >= required,
            "Plugin '{}' requires Astra {} or newer, but this is Astra {}. Update Astra, or \
             install a build of the plugin that supports {}.",
            self.plugin.id,
            required,
            running,
            running
        );
        Ok(())
    }

    /// Load locale files from a plugin's `locales/` directory.
    /// Files should be named `en.json`, `ru.json`, etc. — flat key-value JSON maps.
    pub fn load_locales(plugin_dir: &Path) -> PluginLocales {
        let locales_dir = plugin_dir.join("locales");
        let mut locales = HashMap::new();
        if let Ok(entries) = std::fs::read_dir(&locales_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().is_some_and(|e| e == "json") {
                    if let Some(lang) = path.file_stem().and_then(|s| s.to_str()) {
                        if let Ok(content) = std::fs::read_to_string(&path) {
                            if let Ok(map) =
                                serde_json::from_str::<HashMap<String, String>>(&content)
                            {
                                locales.insert(lang.to_string(), map);
                            }
                        }
                    }
                }
            }
        }
        locales
    }

    /// Check if this plugin is compatible with the current platform.
    ///
    /// Reads the host from [`current_platform`] — the same single source
    /// [`crate::host_platform_key`] derives the registry artifact key from, so
    /// the "which host is this?" answer cannot differ between the compatibility
    /// check and the download lookup.
    pub fn is_platform_compatible(&self) -> bool {
        let (current_os, current_arch) = current_platform();

        let os_ok = self.platform.os.is_empty() || self.platform.os.iter().any(|s| s == current_os);
        let arch_ok =
            self.platform.arch.is_empty() || self.platform.arch.iter().any(|s| s == current_arch);

        os_ok && arch_ok
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::host_astra_version;

    /// A plugin whose own work budget exceeds the daemon default declares it
    /// here. If this key ever stops deserializing, the daemon silently reverts
    /// to `PLUGIN_CALL_TIMEOUT` and starts discarding results from long-running
    /// plugins (agent runners) while their subprocess keeps going — a failure
    /// that looks like the plugin being broken.
    #[test]
    fn call_timeout_is_optional_and_parses() {
        let base = r#"
[plugin]
id = "slow-plugin"
name = "Slow Plugin"
version = "1.0.0"
"#;
        let manifest = PluginManifest::from_str(&format!(
            r#"{base}
[entry]
command = "python"
"#
        ))
        .unwrap();
        assert_eq!(
            manifest.plugin.call_timeout_secs, None,
            "absent key must mean 'use the daemon default', not zero"
        );

        let manifest = PluginManifest::from_str(&format!(
            r#"{base}call_timeout_secs = 300

[entry]
command = "python"
"#
        ))
        .unwrap();
        assert_eq!(manifest.plugin.call_timeout_secs, Some(300));
    }

    #[test]
    fn test_parse_basic_manifest() {
        let toml = r#"
[plugin]
id = "test-plugin"
name = "Test Plugin"
version = "1.0.0"
description = "A test plugin"
author = "Test"

[entry]
command = "python"
args = ["-m", "test_plugin"]
runtimes = ["python"]

[capabilities]
tools = true
tts = true
"#;
        let manifest = PluginManifest::from_str(toml).unwrap();
        assert_eq!(manifest.plugin.id, "test-plugin");
        assert_eq!(manifest.plugin.name, "Test Plugin");
        assert!(manifest.capabilities.tools);
        assert!(manifest.capabilities.tts);
        assert!(!manifest.capabilities.stt);
        assert_eq!(manifest.entry.command, "python");
        assert_eq!(manifest.entry.args, vec!["-m", "test_plugin"]);
        assert_eq!(manifest.capabilities.as_list(), vec!["tools", "tts"]);
    }

    /// The whole manifest, not the four sections a fork happened to know.
    ///
    /// `[platform]`, `[build]`, `[ui]`, `[dependencies]` and
    /// `plugin.call_timeout_secs` are the five the CLI's own struct silently
    /// dropped; this asserts one type parses all of them.
    #[test]
    fn every_section_of_the_manifest_round_trips() {
        let toml = r#"
[plugin]
id = "kitchen-sink"
name = "Kitchen Sink"
version = "1.2.3"
description = "Every section"
author = "Astra Team"
license = "MIT"
homepage = "https://example.invalid/"
min_astra_version = "0.0.1"
call_timeout_secs = 180

[entry]
command = "{venv}/python"
args = ["-m", "sink"]
cwd = "."
runtimes = ["python"]

[capabilities]
tools = true
ui_contributions = true

[permissions]
fire_trigger = { reason = "rolls the dice" }
subscribe_events = { types = ["command_completed"] }

[dependencies]
astra-plugin-sdk = ">=0.6,<0.7"

[platform]
os = ["linux", "windows"]
arch = ["x86_64"]

[build]
bundled = true
language = "python"
python_version = "3.12"
requirements_lock = "requirements.lock"

[ui]
[[ui.contributions]]
id = "sink-panel"
slot = "sidebar"
label = "Sink"
width = 320
height = 240
z_index = 5

[ui.contributions.props]
theme = "dark"
"#;
        let m = PluginManifest::from_str(toml).unwrap();
        assert_eq!(m.plugin.call_timeout_secs, Some(180));
        assert_eq!(
            m.permissions.known(),
            vec![
                crate::Permission::FireTrigger,
                crate::Permission::SubscribeEvents
            ],
            "[permissions] is a section of the ONE manifest type, not a second parse"
        );
        assert_eq!(
            m.permissions.event_types(),
            Some(["command_completed".to_string()].as_slice())
        );
        assert_eq!(m.plugin.min_astra_version, "0.0.1");
        assert_eq!(m.dependencies.len(), 1);
        assert_eq!(
            m.dependencies.get("astra-plugin-sdk").map(String::as_str),
            Some(">=0.6,<0.7")
        );
        assert_eq!(m.platform.os, vec!["linux", "windows"]);
        assert_eq!(m.platform.arch, vec!["x86_64"]);
        let build = m.build.as_ref().expect("[build] parses");
        assert!(build.bundled);
        assert_eq!(build.python_version, "3.12");
        let ui = m.ui.as_ref().expect("[ui] parses");
        assert_eq!(ui.contributions.len(), 1);
        assert_eq!(ui.contributions[0].id, "sink-panel");
        assert_eq!(ui.contributions[0].width, 320);
        assert!(
            ui.contributions[0].pointer_events,
            "pointer_events defaults to true"
        );
        assert_eq!(
            ui.contributions[0].props.get("theme").map(String::as_str),
            Some("dark")
        );
    }

    /// The drift, as a manifest. `ui_panels` was the CLI's invention; a plugin
    /// carrying it declared nothing at all, and the only symptom was the store
    /// showing no capabilities.
    #[test]
    fn a_misspelled_capability_key_fails_the_whole_manifest() {
        let toml = r#"
[plugin]
id = "drifted"
name = "Drifted"
version = "1.0.0"

[entry]
command = "./bin/x"

[capabilities]
ui_panels = true
"#;
        let err = PluginManifest::from_str(toml)
            .expect_err("an unknown capability key must fail the parse")
            .to_string();
        assert!(err.contains("plugin.toml"), "{err}");
    }

    /// §5.6's default-deny, at the manifest level: the overwhelming majority of
    /// plugin.tomls in the wild have no `[permissions]` section at all, and the
    /// parse must give them the empty set rather than fail or invent one.
    #[test]
    fn a_manifest_with_no_permissions_section_parses_as_the_empty_set() {
        let m = PluginManifest::from_str(
            "[plugin]\nid = \"quiet\"\nname = \"Quiet\"\nversion = \"1.0.0\"\n\n\
             [entry]\ncommand = \"./bin/x\"\n",
        )
        .expect("no [permissions] is a legal manifest");
        assert!(m.permissions.is_empty());
        assert!(!m.permissions.contains(crate::Permission::FireTrigger));
    }

    /// `[capabilities]` and `[permissions]` are orthogonal and share two names.
    /// A manifest that implements `dom_access` and one that is allowed to *use*
    /// it are different claims, and the parse keeps them apart.
    #[test]
    fn dom_access_as_a_capability_is_not_dom_access_as_a_permission() {
        let m = PluginManifest::from_str(
            "[plugin]\nid = \"dommy\"\nname = \"Dommy\"\nversion = \"1.0.0\"\n\n\
             [entry]\ncommand = \"./bin/x\"\n\n[capabilities]\ndom_access = true\n",
        )
        .unwrap();
        assert!(m.capabilities.dom_access);
        assert!(
            !m.permissions.contains(crate::Permission::DomAccess),
            "declaring the capability must not carry the permission across"
        );
    }

    #[test]
    fn test_parse_with_config_schema() {
        let toml = r#"
[plugin]
id = "my-plugin"
name = "My Plugin"
version = "0.1.0"

[entry]
command = "./plugin"

[config]
schema = """
{
  "type": "object",
  "properties": {
    "name": { "type": "string", "default": "test" }
  }
}
"""
"#;
        let manifest = PluginManifest::from_str(toml).unwrap();
        assert!(manifest.config.is_some());
        let schema = &manifest.config.unwrap().schema;
        assert!(schema.contains("\"type\": \"object\""));
    }

    #[test]
    fn test_invalid_id() {
        let toml = r#"
[plugin]
id = "Invalid Plugin"
name = "Test"
version = "1.0.0"

[entry]
command = "test"
"#;
        assert!(PluginManifest::from_str(toml).is_err());
    }

    /// SECURITY canary for the id-as-path-component rule. Every string here would
    /// have become `<plugins_dir>/<id>/` — created, then `remove_dir_all`'d — if the
    /// install path had trusted the archive's manifest.
    #[test]
    fn ids_that_are_not_safe_path_components_are_refused() {
        let manifest_with = |id: &str| {
            format!(
                r#"
[plugin]
id = "{id}"
name = "Test"
version = "1.0.0"

[entry]
command = "test"
"#
            )
        };
        for id in [
            "../evil",
            "../../../x",
            "..",
            "/etc",
            "a/b",
            r"a\b",
            "con",
            "prn",
            "aux",
            "nul",
            "com1",
            "lpt9",
            "foo.",
            "foo ",
        ] {
            assert!(
                PluginManifest::from_str(&manifest_with(id)).is_err(),
                "plugin.id '{id}' must be refused — it is not a safe path component"
            );
        }
        // …and the shape a real plugin uses still parses.
        assert!(PluginManifest::from_str(&manifest_with("my-plugin-2")).is_ok());
    }

    #[test]
    fn test_missing_command() {
        let toml = r#"
[plugin]
id = "test"
name = "Test"
version = "1.0.0"

[entry]
command = ""
"#;
        assert!(PluginManifest::from_str(toml).is_err());
    }

    #[test]
    fn test_build_section() {
        let toml = r#"
[plugin]
id = "test"
name = "Test"
version = "1.0.0"

[entry]
command = "{venv}/python"
args = ["-m", "test"]
runtimes = ["python"]

[build]
bundled = true
language = "python"
python_version = "3.12"
requirements_lock = "requirements.lock"
"#;
        let manifest = PluginManifest::from_str(toml).unwrap();
        let build = manifest.build.unwrap();
        assert!(build.bundled);
        assert_eq!(build.language, "python");
        assert_eq!(build.python_version, "3.12");
    }

    // ── `min_astra_version` (production plan 1.4) ──

    fn manifest_needing(min_astra_version: &str) -> String {
        format!(
            "[plugin]\nid = \"needy\"\nname = \"Needy\"\nversion = \"1.0.0\"\n\
             min_astra_version = \"{min_astra_version}\"\n\n[entry]\ncommand = \"./bin/x\"\n"
        )
    }

    /// The acceptance case: a bundle asking for an Astra that does not exist yet
    /// is refused, and the refusal names both versions — the one it wants and the
    /// one it got. Anything less leaves the user reading "failed to install".
    ///
    /// Only a build that *is* a host enforces this. In the CLI's build there is
    /// no running Astra, and a `check` that refused to look at a plugin because
    /// it targets a newer daemon than the tool would be useless — so the
    /// assertion there is the opposite one: it parses.
    #[test]
    fn a_plugin_needing_a_newer_astra_is_refused_by_name() {
        let Some(host) = host_astra_version() else {
            PluginManifest::from_str(&manifest_needing("99.0.0"))
                .expect("a tool build validates the manifest, not a particular host");
            return;
        };
        let err = PluginManifest::from_str(&manifest_needing("99.0.0"))
            .expect_err("99.0.0 is newer than any Astra this code can be built as")
            .to_string();
        assert!(err.contains("99.0.0"), "{err}");
        assert!(err.contains(host), "{err}");
    }

    /// Absent, equal and older all install. Equal especially: `>=`, not `>`, or
    /// every plugin that pins the current release locks itself out of it.
    #[test]
    fn absent_equal_and_older_requirements_are_satisfied() {
        let manifest = PluginManifest::from_str(
            "[plugin]\nid = \"plain\"\nname = \"Plain\"\nversion = \"1.0.0\"\n\n\
             [entry]\ncommand = \"./bin/x\"\n",
        )
        .expect("no requirement means no check");
        assert_eq!(manifest.plugin.min_astra_version, "");

        if let Some(host) = host_astra_version() {
            PluginManifest::from_str(&manifest_needing(host))
                .expect("a plugin pinning exactly this Astra must install on it");
        }
        PluginManifest::from_str(&manifest_needing("0.0.1"))
            .expect("an older requirement is satisfied by a newer Astra");
    }

    /// A typo in the field must not read as "no requirement" — that is how a
    /// declared constraint silently stops constraining anything. Enforced in
    /// **every** consumer, host or not: this is the check `astra-plugin check`
    /// owes the author before a release exists.
    #[test]
    fn an_unparseable_requirement_is_an_error_not_a_pass() {
        let err = PluginManifest::from_str(&manifest_needing("nightly"))
            .expect_err("'nightly' is not a semver version")
            .to_string();
        assert!(err.contains("min_astra_version"), "{err}");
    }

    /// Semver's pre-release rule, stated as a test because it is the one place
    /// the comparison is not obvious: 0.2.0-rc1 is BEFORE 0.2.0, so a release
    /// candidate does not satisfy a plugin that asked for the final.
    #[test]
    fn a_release_candidate_does_not_satisfy_the_final_version() {
        let manifest: PluginManifest = toml::from_str(&manifest_needing("0.2.0")).unwrap();
        assert!(manifest.check_min_astra_version("0.2.0-rc1").is_err());
        assert!(manifest.check_min_astra_version("0.2.0").is_ok());
        assert!(manifest.check_min_astra_version("0.2.1").is_ok());
        assert!(manifest.check_min_astra_version("0.1.9").is_err());
    }

    /// Disabling every plugin on the machine because our OWN version string went
    /// strange is a worse failure than not enforcing one manifest field.
    #[test]
    fn an_unparseable_host_version_skips_the_check_rather_than_refusing_everything() {
        let manifest: PluginManifest = toml::from_str(&manifest_needing("99.0.0")).unwrap();
        assert!(manifest.check_min_astra_version("not-a-version").is_ok());
    }
}
