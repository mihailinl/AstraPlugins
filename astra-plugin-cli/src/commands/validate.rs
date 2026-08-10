//! `astra-plugin check` — check manifest, config schema, structure, the
//! versions the project declares, and the release workflow.
//!
//! Three severities, and the split is load-bearing:
//!
//! * **error** — the daemon will refuse this, or silently do the wrong thing.
//! * **warning** — it will bite at run time. `--strict` fails on these, and
//!   `astra-plugin dev` and CI both run `--strict`.
//! * **note** — publish-time metadata that is absent. Never strict-fatal, or
//!   the first `astra-plugin dev` on a fresh scaffold would fail on an empty
//!   `author` field before the plugin had ever run.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result};
use serde::Deserialize;

use crate::commands::init_ci::{self, REQUIRED_PERMISSIONS, WORKFLOW_FILE, WORKFLOW_REPO};

/// Environment variable carrying the commit the release workflow is running
/// from. Set by `plugin-release.yml`'s build job; unset everywhere else.
pub const WORKFLOW_SHA_ENV: &str = "ASTRA_PLUGIN_WORKFLOW_SHA";

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
    run_with(path, strict, false)
}

/// `run`, plus the network-dependent half of the CI lint.
///
/// Pin freshness is opt-in because `dev` calls this on every start and a
/// `git ls-remote` on the hot path of the inner loop is a second of latency
/// bought with nothing. In CI the release workflow exports
/// [`WORKFLOW_SHA_ENV`] instead, which is both authoritative and free.
pub fn run_with(path: &str, strict: bool, resolve_pin: bool) -> Result<()> {
    let dir = Path::new(path);
    let manifest_path = dir.join("plugin.toml");

    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }

    println!("Checking plugin at {}...", dir.display());

    let content = std::fs::read_to_string(&manifest_path).context("Failed to read plugin.toml")?;

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

    check_versions_agree(dir, &manifest.plugin.version, &mut warnings);
    check_release_workflow(dir, resolve_pin, &mut warnings, &mut notes);

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

/// `plugin.toml` is the authority; every other manifest in the project must
/// agree with it.
fn check_versions_agree(dir: &Path, declared: &str, warnings: &mut Vec<String>) {
    if declared.is_empty() {
        return;
    }
    for (file, what, found) in crate::commands::version::declared_versions(dir) {
        if found != declared {
            warnings.push(format!(
                "{file} {what} is '{found}', but plugin.toml says '{declared}'. \
                 Fix both with: astra-plugin version {declared}"
            ));
        }
    }
}

/// The CI half of `check`.
///
/// **Scope, stated plainly:** this looks at `.github/workflows/` only when that
/// directory exists. A plugin that has never run `init-ci` gets a note, not a
/// failure — `--strict` is what `astra-plugin dev` runs on every start, and a
/// freshly scaffolded plugin must be able to run before it can be released.
/// Once there *is* a workflows directory, the author has declared an intent to
/// publish from GitHub, and every finding below is strict-fatal.
fn check_release_workflow(
    dir: &Path,
    resolve_pin: bool,
    warnings: &mut Vec<String>,
    notes: &mut Vec<String>,
) {
    if init_ci::workflows_dir(dir).is_none() {
        notes.push(
            "No .github/workflows — `astra-plugin init-ci` writes the release workflow".into(),
        );
        return;
    }

    let found = match init_ci::find_release_workflow(dir) {
        Ok(f) => f,
        Err(e) => {
            notes.push(format!("Could not read .github/workflows: {e}"));
            return;
        }
    };

    let Some((path, wf)) = found else {
        warnings.push(format!(
            "no workflow in .github/workflows calls {WORKFLOW_REPO}/{WORKFLOW_FILE} — \
             tagging this repository would build nothing. Run: astra-plugin init-ci"
        ));
        return;
    };

    let name = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| path.display().to_string());

    // ── the pin ─────────────────────────────────────────────────────────────
    match wf.uses_ref.as_deref() {
        None => warnings.push(format!("{name}: the `uses:` line has no `@<ref>`")),
        Some(r) if !init_ci::is_commit_sha(r) => warnings.push(format!(
            "{name}: pinned to '{r}', which is a movable ref. Whoever can move it owns the \
             build step of this repository, and that job runs with `contents: write`. \
             Run: astra-plugin init-ci"
        )),
        Some(r) => {
            // Two sources, in order of authority: what the running workflow
            // says it is, then — only if asked — what upstream currently is.
            let expected = std::env::var(WORKFLOW_SHA_ENV)
                .ok()
                .filter(|s| !s.is_empty());
            let expected = match expected {
                Some(e) => Some(e),
                None if resolve_pin => match init_ci::current_upstream_pin() {
                    Ok(sha) => sha,
                    Err(e) => {
                        notes.push(format!("Pin freshness not checked: {e}"));
                        None
                    }
                },
                None => {
                    notes.push(format!(
                        "Pin freshness not checked (pass --resolve-pin, or set {WORKFLOW_SHA_ENV})"
                    ));
                    None
                }
            };
            if let Some(expected) = expected
                && !expected.eq_ignore_ascii_case(r)
            {
                warnings.push(format!(
                    "{name}: stale pin. It calls the workflow at {}, but the current one is {}. \
                     Run: astra-plugin init-ci",
                    &r[..12.min(r.len())],
                    &expected[..12.min(expected.len())]
                ));
            }
        }
    }

    // ── the permissions block ───────────────────────────────────────────────
    //
    // A called workflow can only REDUCE what its caller granted. Every one of
    // these missing produces a run that fails in `publish`, after a full
    // matrix build, with a permissions error nowhere near the cause.
    for perm in REQUIRED_PERMISSIONS {
        match wf.permissions.get(*perm).map(String::as_str) {
            Some("write") => {}
            Some(other) => warnings.push(format!(
                "{name}: top-level permissions has `{perm}: {other}`, and the release workflow \
                 needs `write` — a called workflow cannot grant itself more"
            )),
            None => warnings.push(format!(
                "{name}: top-level permissions is missing `{perm}: write`. \
                 Run: astra-plugin init-ci"
            )),
        }
    }

    if wf.secrets_inherit {
        warnings.push(format!(
            "{name}: `secrets: inherit`. The release workflow declares no secrets, and the job \
             that runs your build.rs and npm lifecycle scripts is meant to hold none"
        ));
    }

    if !wf.tag_trigger {
        warnings.push(format!(
            "{name}: no `on: push: tags:` trigger, so a `git push --tags` releases nothing"
        ));
    }

    // ── the inputs ──────────────────────────────────────────────────────────
    if let Some(input) = wf.plugin_dir.as_deref() {
        let root = init_ci::repo_root(dir).unwrap_or_else(|| dir.to_path_buf());
        let pointed = root.join(input);
        let same = match (pointed.canonicalize(), dir.canonicalize()) {
            (Ok(a), Ok(b)) => a == b,
            // Cannot resolve it, so cannot claim it is wrong.
            _ => true,
        };
        if !same {
            warnings.push(format!(
                "{name}: `plugin-dir: {input}` does not point at this plugin. The release would \
                 build whatever is at that path instead"
            ));
        }
    }

    // ── the tag namespace ───────────────────────────────────────────────────
    //
    // Two independent knobs have to agree or the plugin never releases: the
    // `tags:` glob decides whether this workflow STARTS, and `tag-prefix`
    // decides whether it then accepts the tag. Nothing downstream reports a
    // disagreement — GitHub does not warn when a push matches no trigger, so
    // the symptom is a tag that lands and a repository that does nothing. A
    // hand edit to one and not the other is the whole failure mode.
    let prefix = wf.tag_prefix.as_deref().unwrap_or("v");
    if !wf.tag_globs.is_empty() && !wf.tag_globs.iter().any(|g| glob_can_match(g, prefix)) {
        warnings.push(format!(
            "{name}: `tag-prefix: {prefix}` releases on '{prefix}<version>', but no `tags:` \
             pattern ({}) can match that tag — pushing it would start nothing",
            wf.tag_globs.join(", ")
        ));
    }

    // A monorepo caller left on the default prefix fires on every other
    // plugin's tag and asserts it against this plugin.toml, so a repository
    // with eleven plugins goes ten-tenths red on every release.
    if wf.tag_prefix.is_none()
        && wf
            .plugin_dir
            .as_deref()
            .is_some_and(|d| d != "." && !d.is_empty())
    {
        warnings.push(format!(
            "{name}: no `tag-prefix:`, so this plugin releases on a bare 'v<version>' — but \
             `plugin-dir: {}` says this repository holds more than one plugin, and they cannot \
             share one tag. Run: astra-plugin init-ci",
            wf.plugin_dir.as_deref().unwrap_or(".")
        ));
    }

    if let Some(repo) = wf.uses_repo.as_deref()
        && repo != WORKFLOW_REPO
    {
        notes.push(format!(
            "{name}: calls a fork of the release workflow ({repo}, not {WORKFLOW_REPO})"
        ));
    }
}

/// Could a `tags:` pattern ever match `{prefix}<version>`?
///
/// Deliberately permissive: this answers "is it possible", not "is it exactly
/// right", so an author who wrote a broader glob than `init-ci` would is not
/// nagged. Only a pattern that provably cannot fire is worth a warning. The
/// leading literal run is compared and a `*` is taken as "anything from here",
/// which is the only part of GitHub's glob syntax that matters for a prefix.
pub(crate) fn glob_can_match(glob: &str, prefix: &str) -> bool {
    let literal = glob.split(['*', '?', '[']).next().unwrap_or("");
    // `v*` vs prefix `v` -> literal "v", prefix starts with it: possible.
    // `v*` vs prefix `dice-roller-v` -> "v" is not a prefix of it: impossible.
    // `dice-roller-v*` vs prefix `dice-roller-v`: possible.
    prefix.starts_with(literal) || literal.starts_with(prefix)
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
