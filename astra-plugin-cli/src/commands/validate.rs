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

use std::collections::BTreeSet;
use std::path::Path;

use anyhow::{Context, Result};
use astra_plugin_manifest::{
    KNOWN_ARCH_VALUES, KNOWN_OS_VALUES, PluginManifest, explain_unknown_capability,
    is_known_capability, platform_key_for,
};

use crate::commands::init_ci::{self, REQUIRED_PERMISSIONS, WORKFLOW_FILE, WORKFLOW_REPO};

/// Environment variable carrying the commit the release workflow is running
/// from. Set by `plugin-release.yml`'s build job; unset everywhere else.
pub const WORKFLOW_SHA_ENV: &str = "ASTRA_PLUGIN_WORKFLOW_SHA";

/// Validate one capability name against the daemon's vocabulary.
///
/// The vocabulary itself is [`astra_plugin_manifest::CAPABILITY_NAMES`]. This
/// module used to keep its own copy of it, and that copy drifted: it grew a
/// `ui_panels` no daemon ever had. Ask the shared crate; never restate the list.
///
/// `astra-plugin new --capabilities` calls this before it writes a manifest, so
/// a typo is caught at the moment it is typed rather than by a parse failure
/// afterwards. The manifest parser refuses the same names — see
/// [`astra_plugin_manifest::Capabilities`].
pub fn check_capability_name(name: &str) -> Result<()> {
    if is_known_capability(name) {
        return Ok(());
    }
    anyhow::bail!("{}", explain_unknown_capability(name))
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

    let mut report = Report::default();
    let manifest = parse_manifest(&content, &mut report)?;

    check_capabilities(&manifest, &content, &mut report);
    check_config_schema(&manifest, &mut report);
    check_metadata(&manifest, &mut report);
    check_platform(&manifest, &mut report);
    check_build(&manifest, &mut report);
    check_ui(&manifest, &mut report);
    check_dependencies(&manifest, &mut report);
    check_call_timeout(&manifest, &mut report);

    check_versions_agree(dir, &manifest.plugin.version, &mut report.warnings);
    check_release_workflow(dir, resolve_pin, &mut report.warnings, &mut report.notes);

    // Report results
    for n in &report.notes {
        println!("  NOTE: {n}");
    }
    for w in &report.warnings {
        println!("  WARN: {w}");
    }
    for e in &report.errors {
        println!("  ERROR: {e}");
    }

    if !report.errors.is_empty() {
        anyhow::bail!(
            "Check failed with {} error(s) and {} warning(s)",
            report.errors.len(),
            report.warnings.len()
        );
    }
    if strict && !report.warnings.is_empty() {
        anyhow::bail!(
            "Check failed: {} warning(s), and --strict treats warnings as errors",
            report.warnings.len()
        );
    }

    println!("  sections: {}", sections_present(&manifest).join(", "));
    println!(
        "  OK: plugin '{}' v{} is valid ({} warning(s), {} note(s), capabilities: {})",
        manifest.plugin.id,
        manifest.plugin.version,
        report.warnings.len(),
        report.notes.len(),
        {
            let enabled = manifest.capabilities.as_list();
            if enabled.is_empty() {
                "none".to_string()
            } else {
                enabled.join(", ")
            }
        }
    );
    Ok(())
}

/// The three severities, collected so the checks below can be read one at a
/// time. See the module docs for what belongs in each.
#[derive(Default)]
struct Report {
    errors: Vec<String>,
    /// Things that will bite at run time — `--strict` fails on them.
    warnings: Vec<String>,
    /// Publish-time metadata gaps. Never strict-fatal, or the first
    /// `astra-plugin dev` on a fresh scaffold would fail on an empty `author`
    /// field before the plugin had ever run.
    notes: Vec<String>,
}

/// Parse `plugin.toml` with **the daemon's own parser**, and run the daemon's
/// own `validate()` over the result.
///
/// This is the whole point of the shared crate: what `check` accepts and what
/// the daemon accepts are now the same function, so a manifest that passes here
/// cannot be refused at install for a reason `check` never mentioned.
///
/// Two-phase on purpose. `[capabilities]` now denies unknown fields, so a stale
/// key is a *parse* failure — and serde's "unknown field `ui_panels`" does not
/// tell the author what to write instead. The capability keys are therefore
/// read from the raw TOML first, so the message names the replacement.
fn parse_manifest(content: &str, report: &mut Report) -> Result<PluginManifest> {
    let raw: toml::Value = toml::from_str(content).context("Failed to parse plugin.toml")?;
    if let Some(table) = raw.get("capabilities").and_then(|v| v.as_table()) {
        let unknown: Vec<&String> = table
            .keys()
            .filter(|name| !is_known_capability(name))
            .collect();
        if !unknown.is_empty() {
            for name in &unknown {
                println!(
                    "  ERROR: [capabilities] {}",
                    explain_unknown_capability(name)
                );
            }
            anyhow::bail!(
                "Check failed with {} error(s): [capabilities] has {} key(s) the daemon does not \
                 know, and a manifest carrying one does not parse at all",
                unknown.len(),
                unknown.len()
            );
        }
    }

    // `PluginManifest::from_str`, split into its two halves so a validation
    // failure still leaves a manifest to run the section checks against. The
    // deserialize is the same one the daemon runs (`deny_unknown_fields` is an
    // attribute on the type, not something a caller opts into) and `validate()`
    // is the same function; a `check` that passed both is a manifest the daemon
    // will accept.
    let manifest: PluginManifest =
        toml::from_str(content).context("Failed to parse plugin.toml")?;

    // The daemon's rules, verbatim: required fields, the `plugin.id` charset and
    // reserved-device-name gates (the id becomes a directory name), and the
    // syntax of `min_astra_version`. It stops at the first, so `check` reports
    // one — better one authoritative message than two forks of the same rule
    // disagreeing about the wording.
    if let Err(e) = manifest.validate() {
        report.errors.push(format!("{e:#}"));
    }

    // Version format (basic semver check) — a warning, not the hard `semver`
    // parse, because `1.0` is a shape the daemon tolerates.
    let parts: Vec<&str> = manifest.plugin.version.split('.').collect();
    if parts.len() < 2 || parts.len() > 3 {
        report
            .warnings
            .push("plugin.version should follow semver (e.g., 1.0.0)".into());
    }

    Ok(manifest)
}

/// Which sections the manifest actually declares.
///
/// Printed on success because the forked struct's failure mode was invisible:
/// it did not report that it had ignored `[platform]`, `[build]`, `[ui]` and
/// `[dependencies]`; it simply never mentioned them.
fn sections_present(m: &PluginManifest) -> Vec<String> {
    let mut out = vec!["[plugin]".to_string(), "[entry]".to_string()];
    if !m.capabilities.as_list().is_empty() {
        out.push("[capabilities]".into());
    }
    if m.config.is_some() {
        out.push("[config]".into());
    }
    if !m.dependencies.is_empty() {
        out.push("[dependencies]".into());
    }
    if !m.platform.os.is_empty() || !m.platform.arch.is_empty() {
        out.push("[platform]".into());
    }
    if m.build.is_some() {
        out.push("[build]".into());
    }
    if m.ui.is_some() {
        out.push("[ui]".into());
    }
    out
}

/// A plugin that declares nothing does nothing. Unknown keys are handled in
/// [`parse_manifest`]; by the time we are here every key is real.
fn check_capabilities(m: &PluginManifest, content: &str, report: &mut Report) {
    if m.capabilities.as_list().is_empty() {
        // Distinguish "no [capabilities] section" from "a section that turns
        // everything off" — the second is usually a half-finished edit.
        let has_section = content.contains("[capabilities]");
        report.warnings.push(if has_section {
            "[capabilities] declares no enabled capability — plugin won't do anything".into()
        } else {
            "No capabilities enabled — plugin won't do anything".into()
        });
    }
}

fn check_config_schema(m: &PluginManifest, report: &mut Report) {
    let Some(config) = m.config.as_ref() else {
        return;
    };
    if config.schema.is_empty() {
        return;
    }
    match serde_json::from_str::<serde_json::Value>(&config.schema) {
        Ok(schema) => {
            if schema.get("type").and_then(|t| t.as_str()) != Some("object") {
                report
                    .warnings
                    .push("config.schema should have \"type\": \"object\" at root".into());
            }
        }
        Err(e) => report
            .errors
            .push(format!("config.schema is not valid JSON: {e}")),
    }
}

/// Metadata completeness — needed to publish, not to run.
fn check_metadata(m: &PluginManifest, report: &mut Report) {
    if m.plugin.description.is_empty() {
        report.notes.push("Missing plugin.description".into());
    }
    if m.plugin.author.is_empty() {
        report.notes.push("Missing plugin.author".into());
    }
    if !m.plugin.min_astra_version.is_empty() {
        report.notes.push(format!(
            "Requires Astra {} or newer",
            m.plugin.min_astra_version
        ));
    }
}

/// `[platform]` — the section the forked struct did not have at all.
///
/// A typo here is silent and total: `os = ["win"]` matches no host, so the
/// plugin is incompatible everywhere and the daemon's only message is that it
/// is incompatible. That is an error, not a warning.
fn check_platform(m: &PluginManifest, report: &mut Report) {
    if m.platform.os.is_empty() && m.platform.arch.is_empty() {
        // No `[platform]` section: runs anywhere Astra does. Saying so on every
        // check would be noise on ten of the eleven examples.
        return;
    }
    for os in &m.platform.os {
        if !KNOWN_OS_VALUES.contains(&os.as_str()) {
            report.errors.push(format!(
                "[platform] os = \"{os}\" is not an OS Astra knows. Valid: {}. A value the daemon \
                 does not recognise matches no host, so the plugin is incompatible everywhere",
                KNOWN_OS_VALUES.join(", ")
            ));
        }
    }
    for arch in &m.platform.arch {
        if !KNOWN_ARCH_VALUES.contains(&arch.as_str()) {
            report.errors.push(format!(
                "[platform] arch = \"{arch}\" is not an architecture Astra knows. Valid: {}",
                KNOWN_ARCH_VALUES.join(", ")
            ));
        }
    }

    // Declaring a host Astra ships no daemon for is legal — but if EVERY
    // declared combination is such a host, nobody can install this plugin, and
    // the author should hear it here rather than from an empty store listing.
    let os_list: Vec<&str> = if m.platform.os.is_empty() {
        KNOWN_OS_VALUES.to_vec()
    } else {
        m.platform.os.iter().map(String::as_str).collect()
    };
    let arch_list: Vec<&str> = if m.platform.arch.is_empty() {
        KNOWN_ARCH_VALUES.to_vec()
    } else {
        m.platform.arch.iter().map(String::as_str).collect()
    };
    let installable: BTreeSet<&str> = os_list
        .iter()
        .flat_map(|os| arch_list.iter().map(move |arch| (*os, *arch)))
        .filter_map(|(os, arch)| platform_key_for(os, arch).ok())
        .collect();
    if installable.is_empty() && !os_list.is_empty() && !arch_list.is_empty() {
        report.warnings.push(format!(
            "[platform] os = {:?} / arch = {:?} names no host Astra ships a daemon for, so no \
             user could install this. Astra releases: linux-x64, windows-x64",
            m.platform.os, m.platform.arch
        ));
    } else if !installable.is_empty() {
        report.notes.push(format!(
            "[platform] installable on: {}",
            installable.into_iter().collect::<Vec<_>>().join(", ")
        ));
    }
}

/// `[build]` — written by `astra-plugin build`, and internally inconsistent
/// values here produce a bundle that cannot start.
fn check_build(m: &PluginManifest, report: &mut Report) {
    let Some(build) = m.build.as_ref() else {
        return;
    };
    if build.language.is_empty() {
        report
            .notes
            .push("[build] has no `language` — `astra-plugin build` writes one".into());
    }
    if build.bundled && build.language == "python" {
        if build.python_version.is_empty() {
            report.warnings.push(
                "[build] bundled = true for python but python_version is empty — the daemon \
                 cannot resolve `{venv}/python`"
                    .into(),
            );
        }
        if build.requirements_lock.is_empty() {
            report.warnings.push(
                "[build] bundled = true for python but requirements_lock is empty — the bundle \
                 would carry no pinned dependency set"
                    .into(),
            );
        }
    }
    report.notes.push(format!(
        "[build] {}{}",
        if build.language.is_empty() {
            "unknown language".to_string()
        } else {
            build.language.clone()
        },
        if build.bundled { ", bundled" } else { "" }
    ));
}

/// `[ui]` — this is where the drift showed. A plugin can declare contributions
/// and forget the capability that makes the daemon look at them.
fn check_ui(m: &PluginManifest, report: &mut Report) {
    let Some(ui) = m.ui.as_ref() else {
        return;
    };
    if ui.contributions.is_empty() {
        report
            .notes
            .push("[ui] declares no contributions".to_string());
        return;
    }
    if !m.capabilities.ui_contributions {
        report.errors.push(format!(
            "[ui] declares {} contribution(s) but [capabilities] ui_contributions is not true — \
             the daemon never asks a plugin for contributions it did not declare, so none of them \
             would appear",
            ui.contributions.len()
        ));
    }
    let mut seen: BTreeSet<&str> = BTreeSet::new();
    for c in &ui.contributions {
        if c.id.is_empty() {
            report
                .errors
                .push("[[ui.contributions]] has an entry with an empty `id`".into());
            continue;
        }
        if !seen.insert(c.id.as_str()) {
            report.errors.push(format!(
                "[[ui.contributions]] declares id '{}' twice — the second silently replaces the \
                 first",
                c.id
            ));
        }
        if c.slot.is_empty() && c.css_target.is_empty() {
            report.warnings.push(format!(
                "[[ui.contributions]] '{}' names neither `slot` nor `css_target`, so there is \
                 nowhere to mount it",
                c.id
            ));
        }
    }
    report.notes.push(format!(
        "[ui] {} contribution(s): {}",
        ui.contributions.len(),
        ui.contributions
            .iter()
            .map(|c| c.id.as_str())
            .collect::<Vec<_>>()
            .join(", ")
    ));
}

/// `[dependencies]` — declared runtime/SDK requirements. Invisible to the
/// forked struct, so an empty requirement never got mentioned.
fn check_dependencies(m: &PluginManifest, report: &mut Report) {
    if m.dependencies.is_empty() {
        return;
    }
    let mut listed: Vec<String> = m
        .dependencies
        .iter()
        .map(|(k, v)| format!("{k} {v}"))
        .collect();
    listed.sort();
    for (name, req) in &m.dependencies {
        if req.trim().is_empty() {
            report.warnings.push(format!(
                "[dependencies] '{name}' has an empty version requirement"
            ));
        }
    }
    report.notes.push(format!(
        "[dependencies] {}: {}",
        m.dependencies.len(),
        listed.join(", ")
    ));
}

/// `plugin.call_timeout_secs` — the daemon's per-call budget for this plugin.
fn check_call_timeout(m: &PluginManifest, report: &mut Report) {
    let Some(secs) = m.plugin.call_timeout_secs else {
        return;
    };
    if secs == 0 {
        report.errors.push(
            "plugin.call_timeout_secs = 0 — every CallTool and ExecuteAction would time out \
             immediately. Remove the key to use the daemon's default"
                .into(),
        );
        return;
    }
    report
        .notes
        .push(format!("plugin.call_timeout_secs = {secs}"));
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

// There is no manifest struct here any more, and that is the change.
//
// This file used to carry a "minimal manifest struct for validation (mirrors
// the daemon's PluginManifest)". It did not mirror it. It knew `[plugin]`,
// `[entry]`, `[capabilities]` and `[config]`, and it silently ignored
// `[platform]`, `[build]`, `[ui]`, `[dependencies]` and
// `plugin.call_timeout_secs` — so `astra-plugin check` could not report a
// problem in five of the manifest's nine sections, and its `[capabilities]`
// vocabulary drifted to include a `ui_panels` the daemon has never had.
//
// The type now comes from `astra-plugin-manifest`, vendored from
// `Astra/astra-rs/astra-plugin-manifest` and kept byte-identical by
// `tools/check-manifest-crate.sh`. Do not add a local mirror back.

#[cfg(test)]
mod tests {
    use super::*;

    /// Every section, in one manifest, exercised through the real entry point.
    ///
    /// This is task 3.7's acceptance written down: `[platform]`, `[build]`,
    /// `[ui]`, `[dependencies]` and `call_timeout_secs` were invisible to the
    /// forked struct — a `check` that passed said nothing about them because it
    /// had never deserialized them.
    const KITCHEN_SINK: &str = r#"
[plugin]
id = "kitchen-sink"
name = "Kitchen Sink"
version = "1.2.3"
description = "Every section of the manifest, in one plugin"
author = "Astra Team"
license = "MIT"
min_astra_version = "0.0.1"
call_timeout_secs = 180

[entry]
command = "{venv}/python"
args = ["-m", "sink"]
runtimes = ["python"]

[capabilities]
tools = true
ui_contributions = true

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
"#;

    fn report_for(content: &str) -> (Result<PluginManifest>, Report) {
        let mut report = Report::default();
        let parsed = parse_manifest(content, &mut report);
        if let Ok(ref m) = parsed {
            check_capabilities(m, content, &mut report);
            check_config_schema(m, &mut report);
            check_metadata(m, &mut report);
            check_platform(m, &mut report);
            check_build(m, &mut report);
            check_ui(m, &mut report);
            check_dependencies(m, &mut report);
            check_call_timeout(m, &mut report);
        }
        (parsed, report)
    }

    fn joined(lines: &[String]) -> String {
        lines.join("\n")
    }

    #[test]
    fn check_sees_every_section_of_the_manifest() {
        let (parsed, report) = report_for(KITCHEN_SINK);
        let m = parsed.expect("the kitchen-sink manifest parses");
        assert!(
            report.errors.is_empty(),
            "unexpected errors: {}",
            joined(&report.errors)
        );

        // Parsed, not ignored.
        assert_eq!(m.plugin.call_timeout_secs, Some(180));
        assert_eq!(m.platform.os, vec!["linux", "windows"]);
        assert_eq!(m.dependencies.len(), 1);
        assert!(m.build.is_some());
        assert_eq!(m.ui.as_ref().unwrap().contributions.len(), 1);

        // …and reported, which is the part the author sees.
        let sections = sections_present(&m).join(", ");
        for expected in [
            "[plugin]",
            "[entry]",
            "[capabilities]",
            "[dependencies]",
            "[platform]",
            "[build]",
            "[ui]",
        ] {
            assert!(
                sections.contains(expected),
                "`sections:` omitted {expected}: {sections}"
            );
        }
        let notes = joined(&report.notes);
        assert!(notes.contains("call_timeout_secs = 180"), "{notes}");
        assert!(notes.contains("[dependencies] 1"), "{notes}");
        assert!(notes.contains("[build] python, bundled"), "{notes}");
        assert!(notes.contains("[ui] 1 contribution"), "{notes}");
        assert!(notes.contains("linux-x64"), "{notes}");
        assert!(notes.contains("windows-x64"), "{notes}");
        assert!(notes.contains("Requires Astra 0.0.1"), "{notes}");
    }

    /// The failure that started all this: a capability key the daemon does not
    /// know must stop the check, not be dropped.
    #[test]
    fn a_misspelled_capability_is_an_error_not_silence() {
        let manifest = KITCHEN_SINK.replace("ui_contributions = true", "ui_panels = true");
        let (parsed, _) = report_for(&manifest);
        let err = parsed
            .expect_err("a stale capability key must fail the check")
            .to_string();
        assert!(err.contains("[capabilities]"), "{err}");

        let manifest = KITCHEN_SINK.replace("tools = true", "tolos = true");
        let (parsed, _) = report_for(&manifest);
        assert!(parsed.is_err(), "a typo'd capability key must fail");
    }

    /// `[platform]` typos are total and silent in the daemon: an unknown `os`
    /// matches no host.
    #[test]
    fn an_unknown_platform_value_is_an_error() {
        let manifest = KITCHEN_SINK.replace(r#"os = ["linux", "windows"]"#, r#"os = ["win"]"#);
        let (parsed, report) = report_for(&manifest);
        assert!(parsed.is_ok(), "it parses — it is simply wrong");
        let errors = joined(&report.errors);
        assert!(errors.contains("[platform] os = \"win\""), "{errors}");
    }

    /// Declaring only hosts Astra ships no daemon for is legal and useless.
    #[test]
    fn a_platform_no_daemon_ships_for_is_a_warning() {
        let manifest = KITCHEN_SINK
            .replace(r#"os = ["linux", "windows"]"#, r#"os = ["macos"]"#)
            .replace(r#"arch = ["x86_64"]"#, r#"arch = ["aarch64"]"#);
        let (parsed, report) = report_for(&manifest);
        assert!(parsed.is_ok());
        assert!(
            report.errors.is_empty(),
            "macos/aarch64 are legal values: {}",
            joined(&report.errors)
        );
        let warnings = joined(&report.warnings);
        assert!(
            warnings.contains("no host Astra ships a daemon for"),
            "{warnings}"
        );
    }

    /// Contributions without the capability that makes the daemon ask for them
    /// is the `ui_panels` symptom with a different cause.
    #[test]
    fn ui_contributions_without_the_capability_are_an_error() {
        let manifest = KITCHEN_SINK.replace("ui_contributions = true", "");
        let (parsed, report) = report_for(&manifest);
        assert!(parsed.is_ok());
        let errors = joined(&report.errors);
        assert!(errors.contains("ui_contributions is not true"), "{errors}");
    }

    #[test]
    fn a_zero_call_timeout_is_an_error() {
        let manifest = KITCHEN_SINK.replace("call_timeout_secs = 180", "call_timeout_secs = 0");
        let (parsed, report) = report_for(&manifest);
        assert!(parsed.is_ok());
        assert!(
            joined(&report.errors).contains("call_timeout_secs = 0"),
            "{}",
            joined(&report.errors)
        );
    }

    /// The CLI is not an Astra: it validates the field's syntax and refuses to
    /// pretend it knows which daemon the user will run.
    #[test]
    fn min_astra_version_is_checked_for_syntax_not_for_this_build() {
        let (parsed, _) = report_for(&KITCHEN_SINK.replace("0.0.1", "99.0.0"));
        assert!(
            parsed.is_ok(),
            "targeting a future Astra is a legal manifest for a tool to check"
        );

        let mut report = Report::default();
        let _ = parse_manifest(
            &KITCHEN_SINK.replace("\"0.0.1\"", "\"nightly\""),
            &mut report,
        );
        assert!(
            joined(&report.errors).contains("min_astra_version"),
            "{}",
            joined(&report.errors)
        );
    }

    /// `plugin.id` becomes a directory name. The daemon's own gate runs here.
    #[test]
    fn the_daemons_id_rules_apply_here_too() {
        for id in ["../evil", "con", "Bad Id"] {
            let mut report = Report::default();
            let _ = parse_manifest(&KITCHEN_SINK.replace("kitchen-sink", id), &mut report);
            assert!(
                !report.errors.is_empty(),
                "plugin.id '{id}' must be refused by `check`"
            );
        }
    }
}
