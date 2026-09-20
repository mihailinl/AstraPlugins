//! `astra-plugin check` — check manifest, config schema, structure, the
//! versions the project declares, and the release workflow.
//!
//! Four severities, and every split is load-bearing:
//!
//! * **error** — the daemon will refuse this, or silently do the wrong thing.
//! * **warning** — it will bite at run time. `--strict` fails on these, and
//!   `astra-plugin dev` and CI both run `--strict`.
//! * **note** — publish-time metadata that is absent. Never strict-fatal, or
//!   the first `astra-plugin dev` on a fresh scaffold would fail on an empty
//!   `author` field before the plugin had ever run.
//! * **registry** — the fourth, added with `spec/reserved-ids.yaml`. Somebody
//!   else's rule, about somebody else's repository, and the three above cannot
//!   express it.
//!
//! # Why the fourth one had to exist
//!
//! An error says *the daemon refuses this*, and the daemon does not: a plugin
//! called `moderation` installs, sideloads and runs, and it always will —
//! plugins are native processes with the user's own privileges and a private
//! plugin that never sees the catalogue is a first-class thing to build. A
//! warning says *this will bite at run time*, and it will not: it bites at
//! ingest, once, in a repository the author has never opened, after a tag they
//! cannot unpush. A note says nothing loudly enough for a refusal that costs a
//! rename.
//!
//! So a registry finding is routed by WHO IS ASKING, which is [`Gate`]:
//!
//! * [`Gate::Check`] — `astra-plugin check` and `publish --dry-run`, both of
//!   them a preflight for publishing. A registry **refusal** fails them: that
//!   is the whole point, and it is the last moment it is free. A registry
//!   **warning** never fails them, `--strict` included — see
//!   [`check_registry_ids`] for why this side cannot decide a reserved prefix.
//! * [`Gate::Dev`] — `astra-plugin dev`, which runs `--strict` on every start.
//!   Every registry finding is a note. `dev` is the inner loop of writing a
//!   plugin, and refusing to run somebody's code because a catalogue they may
//!   never submit to would not list it is the sandboxing argument arriving
//!   through the back door.
//!
//! `errors_only` — what `astra-plugin build` calls — is the same decision a
//! third time: it returns errors, and a registry finding is not one, so a
//! bundle packs under any id at all.

use std::collections::BTreeSet;
use std::path::Path;

use anyhow::{Context, Result};
use astra_plugin_manifest::{
    KNOWN_ARCH_VALUES, KNOWN_OS_VALUES, PluginManifest, explain_unknown_capability,
    is_known_capability, platform_key_for,
};

use crate::commands::init_ci::{self, REQUIRED_PERMISSIONS, WORKFLOW_FILE, WORKFLOW_REPO};
use crate::hprintln;
use crate::output::{Rejected, Verdict};

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

/// Which caller is asking, for the registry findings only.
///
/// Everything else `check` reports is the same sentence to everybody. The
/// registry's rules are not: they decide whether a listing request will be
/// accepted, and two of the three callers are not publishing anything. See the
/// module docs for the argument.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Gate {
    /// `astra-plugin check`, and `publish --dry-run`. A preflight for the tag.
    Check,
    /// `astra-plugin dev` — the inner loop. Registry findings are notes.
    Dev,
}

/// Check a plugin directory.
///
/// `strict` promotes every warning to an error — what CI and `astra-plugin dev`
/// use, so a manifest problem is caught before the daemon is asked to run it.
pub fn run(path: &str, strict: bool, gate: Gate) -> Result<()> {
    run_with(path, strict, false, gate)
}

/// `run`, plus the network-dependent half of the CI lint.
///
/// Pin freshness is opt-in because `dev` calls this on every start and a
/// `git ls-remote` on the hot path of the inner loop is a second of latency
/// bought with nothing. In CI the release workflow exports
/// [`WORKFLOW_SHA_ENV`] instead, which is both authoritative and free.
pub fn run_with(path: &str, strict: bool, resolve_pin: bool, gate: Gate) -> Result<()> {
    match run_full(CheckOptions { path, strict, fix: false, resolve_pin, gate })? {
        Verdict::Pass => Ok(()),
        // `dev` and the other internal callers use `?` and want the sentence,
        // not an exit code. `main` gets the code from `run_full` directly.
        Verdict::Fail => Err(Rejected::err(
            "`astra-plugin check` found problems — the lines above say which",
        )),
    }
}

pub struct CheckOptions<'a> {
    pub path: &'a str,
    pub strict: bool,
    /// Apply the fixes that can be applied mechanically, then re-check.
    pub fix: bool,
    pub resolve_pin: bool,
    /// Who is asking. Decides what a registry finding costs — nothing else.
    pub gate: Gate,
}

/// `check`, with `--fix` and `--json`.
///
/// Returns a [`Verdict`] rather than an `Err` for a manifest that is merely
/// wrong: the manifest being wrong is the answer to the question, so it is
/// exit 1. An `Err` from here means the check could not be run at all — no
/// `plugin.toml`, an unreadable file — and exits 2.
pub fn run_full(opts: CheckOptions<'_>) -> Result<Verdict> {
    let dir = Path::new(opts.path);
    let manifest_path = dir.join("plugin.toml");

    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }

    hprintln!("Checking plugin at {}...", dir.display());

    let mut applied: Vec<String> = Vec::new();
    if opts.fix {
        applied = crate::commands::fix::apply(dir, &manifest_path)?;
        for line in &applied {
            hprintln!("  FIXED: {line}");
        }
        if applied.is_empty() {
            hprintln!("  --fix: nothing was mechanically fixable.");
        }
    }

    let content = std::fs::read_to_string(&manifest_path).context("Failed to read plugin.toml")?;

    let mut report = Report::default();
    let manifest = parse_manifest(&content, &mut report)?;

    check_capabilities(&manifest, &content, &mut report);
    check_permissions(&manifest, &mut report);
    check_config_schema(&manifest, &mut report);
    check_metadata(&manifest, &mut report);
    check_platform(&manifest, &mut report);
    check_build(&manifest, &mut report);
    check_ui(&manifest, &mut report);
    check_dependencies(&manifest, &mut report);
    check_call_timeout(&manifest, &mut report);
    check_registry_ids(&manifest, &mut report);

    check_versions_agree(dir, &manifest.plugin.version, &mut report.warnings);
    check_release_workflow(dir, opts.resolve_pin, &mut report.warnings, &mut report.notes);

    // `locales/`, the two reserved listing keys, and the English gate. See
    // `commands::locale` for what each rule costs when it is not there. It
    // contributes ERRORS and NOTES only, never a warning: a warning is
    // strict-fatal on `astra-plugin dev`'s inner loop and on the release path,
    // so a rule about prose would stop an author running their own plugin.
    let l = crate::commands::locale::findings(dir, &manifest, crate::commands::locale::Gate::Check);
    report.errors.extend(l.errors);
    report.notes.extend(l.notes);

    for n in &report.notes {
        hprintln!("  NOTE: {n}");
    }
    // The fourth severity prints under its own word, not under WARN or ERROR.
    // An author who is told `ERROR` about a plugin that runs perfectly goes
    // looking for a bug in their plugin; the line has to say whose rule it is
    // and where it bites, and `dev` has to be able to say the same sentence
    // without it reading as a refusal.
    for f in &report.registry {
        match (opts.gate, f.refusal) {
            (Gate::Check, true) => hprintln!("  REGISTRY: {}", f.message),
            (Gate::Check, false) => hprintln!("  REGISTRY WARN: {}", f.message),
            (Gate::Dev, _) => hprintln!("  NOTE: {}", f.message),
        }
    }
    for w in &report.warnings {
        hprintln!("  WARN: {w}");
    }
    for e in &report.errors {
        hprintln!("  ERROR: {e}");
    }

    // `--strict` is deliberately absent from the registry clause. It promotes
    // warnings, and a registry warning is not a warning about this plugin: it
    // is this side saying it cannot decide, because the allowlist that would
    // decide it is the one thing `spec/reserved-ids.yaml` refuses to copy.
    // Promoting "I cannot tell" to an error fails every first-party release.
    let registry_refuses =
        opts.gate == Gate::Check && report.registry.iter().any(|f| f.refusal);
    let failed = !report.errors.is_empty()
        || (opts.strict && !report.warnings.is_empty())
        || registry_refuses;
    let verdict = Verdict::of(!failed);

    if failed {
        if registry_refuses && report.errors.is_empty() {
            hprintln!(
                "  FAILED: {} registry refusal(s) — the plugin is fine, the id is not listable",
                report.registry.iter().filter(|f| f.refusal).count()
            );
        } else if !report.errors.is_empty() {
            hprintln!(
                "  FAILED: {} error(s) and {} warning(s)",
                report.errors.len(),
                report.warnings.len()
            );
        } else {
            hprintln!(
                "  FAILED: {} warning(s), and --strict treats warnings as errors",
                report.warnings.len()
            );
        }
    } else {
        hprintln!("  sections: {}", sections_present(&manifest).join(", "));
        hprintln!(
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
    }

    crate::output::emit(
        "check",
        &verdict,
        serde_json::json!({
            "path": dir.display().to_string(),
            "plugin_id": manifest.plugin.id,
            "version": manifest.plugin.version,
            "capabilities": manifest.capabilities.as_list(),
            "strict": opts.strict,
            "errors": report.errors,
            "warnings": report.warnings,
            "notes": report.notes,
            // Its own key, with the code on each finding. A script that
            // branches on `errors` must not start failing releases because a
            // name was reserved upstream, and a script that wants to know
            // "would the registry take this id" must not have to grep prose.
            "registry": report.registry.iter().map(|f| serde_json::json!({
                "code": f.code,
                "refusal": f.refusal,
                "message": f.message,
            })).collect::<Vec<_>>(),
            "fixed": applied,
        }),
    );

    Ok(verdict)
}

/// Every error `check` would report, at BUILD severity, and nothing else.
///
/// `astra-plugin build` calls this before it packs anything. Two readers of
/// `plugin.toml` live in this binary and only one of them validated:
/// `build.rs` hand-parses a `toml::Value` for the four fields it stamps, so
/// until this existed every rule `check` enforced was one command away from
/// being optional — and it was proven, not supposed: a fixture whose
/// description was Russian and whose only locale file was `ru.json` built
/// clean, exit 0.
///
/// **Errors only, never warnings**, so `build` can never be stricter than a
/// non-strict `check` — with the three named exceptions the build gate
/// promotes (`qps` in the bundle, a missing lock, a stale translation), each of
/// which explains itself at the point it fires.
///
/// **And never a registry finding.** [`check_registry_ids`] runs here so that
/// the rule has one implementation and one set of messages, and its findings
/// go nowhere: `build` packs a bundle, and a bundle is not a listing. An id the
/// catalogue would refuse is still an id somebody can sideload, hand to a
/// colleague, or ship inside a company that has never heard of the registry.
/// `build_packs_a_plugin_whose_id_the_registry_refuses` is what holds this,
/// because it is one line to "fix" and the fix would make `astra-plugin build`
/// the first place in this project where the catalogue decides what a user may
/// run on their own machine.
///
/// Nothing here touches the network: `check_release_workflow` produces
/// warnings and notes only, so it is not run at all.
pub fn errors_only(dir: &Path) -> Result<Vec<String>> {
    let manifest_path = dir.join("plugin.toml");
    let content = std::fs::read_to_string(&manifest_path).context("Failed to read plugin.toml")?;

    let mut report = Report::default();
    let manifest = parse_manifest(&content, &mut report)?;

    check_capabilities(&manifest, &content, &mut report);
    check_permissions(&manifest, &mut report);
    check_config_schema(&manifest, &mut report);
    check_metadata(&manifest, &mut report);
    check_platform(&manifest, &mut report);
    check_build(&manifest, &mut report);
    check_ui(&manifest, &mut report);
    check_dependencies(&manifest, &mut report);
    check_call_timeout(&manifest, &mut report);
    check_registry_ids(&manifest, &mut report);

    let l = crate::commands::locale::findings(dir, &manifest, crate::commands::locale::Gate::Build);
    report.errors.extend(l.errors);

    // `report.registry` is dropped on the floor here, deliberately and
    // visibly. Returning it would make every caller decide again; the decision
    // is in the doc comment above and the test named in it.
    Ok(report.errors)
}

/// The four severities, collected so the checks below can be read one at a
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
    /// Another repository's rules about this id. What each one costs is
    /// [`Gate`]'s business and not this struct's — the same finding is a
    /// refusal to `check` and a note to `dev`.
    registry: Vec<RegistryFinding>,
}

/// One thing astra-registry would say about this id, in the registry's own
/// vocabulary of codes so that the author can search for the same word twice.
struct RegistryFinding {
    /// The registry's code — `bot/lib/codes.mjs` and `docs/BOT-CHECKS.md` over
    /// there carry the same one, with the remedy.
    code: &'static str,
    /// True when ingest would reject the listing outright.
    refusal: bool,
    message: String,
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
    // Phase 4 added `[permissions]` and this list did not follow it, which is
    // the exact failure mode above: a manifest that requests `fire_trigger` and
    // a `check` that never says so reads as a section the tool ignored.
    if !m.permissions.is_empty() {
        out.push("[permissions]".into());
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

/// `[permissions]` ids this build does not know.
///
/// Deliberately a warning and not an error: the section is forward-compatible
/// by design, so an older CLI must not refuse a manifest written for a newer
/// Astra. But "kept and inert" is only safe if somebody says so — a typo'd id
/// grants nothing at run time and looks identical to a correct one on the page.
/// `Permissions::unknown()` and `explain_unknown_permission` live in the
/// manifest crate precisely so `check`, `test` and the registry bot say the
/// same sentence about the same id.
fn check_permissions(m: &PluginManifest, report: &mut Report) {
    for id in m.permissions.unknown() {
        report
            .warnings
            .push(astra_plugin_manifest::explain_unknown_permission(id));
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

// ── the registry's id rules, mirrored ────────────────────────────────────────

/// `spec/reserved-ids.yaml`, embedded.
///
/// A vendored copy inside `src/`, for the same reason `listing-limits.yaml`
/// and `conformance.json` are: `include_str!` reaching outside this crate's
/// package directory is what `cargo package` refuses, and a published crate
/// that cannot see the spec file is a published crate that cannot check
/// anything. `the_reserved_ids_are_the_ones_the_spec_declares` reads the spec
/// at test time and fails until the two are byte-identical.
const RESERVED_IDS_SPEC: &str = include_str!("../reserved-ids.yaml");

/// `spec/reserved-ids.yaml`, parsed once.
///
/// Hand-parsed for the reason the file's own FORMAT paragraph gives. The
/// parser is deliberately dull: `key: value`, `key:` then `  - item`, `#`
/// comments, and anything it does not understand is skipped rather than
/// guessed at — a reader that invents a row is worse than one that finds none,
/// because the floor in the test notices none.
struct ReservedIds {
    ids: BTreeSet<String>,
    prefixes: Vec<String>,
    id_pattern: String,
    refuse_double_hyphen: bool,
}

fn reserved_ids() -> &'static ReservedIds {
    use std::sync::OnceLock;
    static PARSED: OnceLock<ReservedIds> = OnceLock::new();
    PARSED.get_or_init(|| {
        let mut out = ReservedIds {
            ids: BTreeSet::new(),
            prefixes: Vec::new(),
            id_pattern: String::new(),
            refuse_double_hyphen: false,
        };
        let mut list: Option<&str> = None;
        for raw in RESERVED_IDS_SPEC.lines() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some(item) = line.strip_prefix("- ") {
                match list {
                    Some("reserved") => {
                        out.ids.insert(item.trim().to_string());
                    }
                    Some("reserved_prefixes") => out.prefixes.push(item.trim().to_string()),
                    _ => {}
                }
                continue;
            }
            let Some((key, value)) = line.split_once(':') else {
                continue;
            };
            let (key, value) = (key.trim(), value.trim());
            if value.is_empty() {
                list = Some(match key {
                    "reserved" => "reserved",
                    "reserved_prefixes" => "reserved_prefixes",
                    _ => "",
                });
                continue;
            }
            list = None;
            match key {
                "id_pattern" => out.id_pattern = value.trim_matches('"').to_string(),
                "refuse_double_hyphen" => out.refuse_double_hyphen = value == "true",
                _ => {}
            }
        }
        out
    })
}

/// Why the registry's charset refuses this id, or `None`.
///
/// The spec's `id_pattern` written out by hand, plus the one rule that is not
/// in the pattern. There is no regex crate in this CLI's graph and a five-line
/// predicate is not a reason to add one — C26 reads the lockfile and would
/// have something to say about it. The cost of hand-implementing is that the
/// implementation can quietly stop being the pattern, so the two are pinned
/// together by `ID_PATTERN_IMPLEMENTED` in this module's tests: the registry
/// narrowing `{0,62}` turns that test red with both strings printed, and
/// nobody gets to copy a new pattern across without reading what it now says.
///
/// The reason is returned as a sentence rather than a boolean because the
/// pattern is unreadable to most authors, and "does not match
/// `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$`" is a refusal nobody can act on
/// without counting characters.
fn id_charset_violation(id: &str) -> Option<String> {
    let chars: Vec<char> = id.chars().collect();
    if chars.len() < 2 {
        return Some(format!(
            "{} character{}; the shortest listable id is two",
            chars.len(),
            if chars.len() == 1 { "" } else { "s" }
        ));
    }
    if chars.len() > 64 {
        return Some(format!("{} characters; the cap is 64", chars.len()));
    }
    if let Some(bad) = chars
        .iter()
        .find(|c| !(c.is_ascii_lowercase() || c.is_ascii_digit() || **c == '-'))
    {
        return Some(format!(
            "contains {bad:?}; only lowercase ASCII letters, digits and hyphens are allowed"
        ));
    }
    if chars[0] == '-' {
        return Some("starts with a hyphen; the first character must be a letter or digit".into());
    }
    if chars[chars.len() - 1] == '-' {
        return Some("ends with a hyphen; the last character must be a letter or digit".into());
    }
    if reserved_ids().refuse_double_hyphen && id.contains("--") {
        return Some(
            "contains a double hyphen. This one is not in the charset pattern — it is a separate \
             refusal in the registry's `invalidId`, so an id that reads as legal by the pattern \
             alone still dies at ingest"
                .into(),
        );
    }
    None
}

/// What astra-registry would say about `plugin.id`, said here instead.
///
/// Three findings, and the third is the interesting one.
///
/// * `E_ID_RESERVED` — a refusal. The name is on a list nobody but the
///   registry's maintainers may list under, and the list is mirrored, so this
///   side can answer it outright.
/// * `E_ID_CHARSET` — a refusal. The registry's charset is *tighter* than the
///   daemon's, which is why this can fire on an id `check` has already
///   accepted: the daemon cares whether the id is a safe directory name, the
///   registry also caps it at 64 characters and refuses a single character.
/// * `E_ID_RESERVED_PREFIX` — a **warning, and never fatal, `--strict`
///   included.** Whether `astra-foo` is refused depends on
///   `first_party_repos` / `first_party_owners` in
///   `astra-registry/policy/reserved-ids.json`, matched against a repository
///   the registry has proved the author owns. `spec/reserved-ids.yaml`
///   deliberately does not mirror those two lists — a copy of a trust
///   allowlist is a second place to grant trust, and a stale one grants it to
///   an account somebody else has since registered. So this side genuinely
///   does not know, and says so. Promoting it under `--strict` would fail
///   every first-party release in CI, which is the shape of check that gets
///   deleted rather than fixed.
///
/// Every message names where the refusal happens and what it costs, because
/// the failure this whole file exists for is an author reading `ERROR` about a
/// plugin that works perfectly and going to look for the bug in their code.
fn check_registry_ids(m: &PluginManifest, report: &mut Report) {
    let id = m.plugin.id.as_str();
    if id.is_empty() {
        // The manifest crate's own `validate()` has already said so, as an
        // error. A second sentence about the same empty field, in another
        // vocabulary, is noise.
        return;
    }

    if reserved_ids().ids.contains(id) {
        report.registry.push(RegistryFinding {
            code: "E_ID_RESERVED",
            refusal: true,
            message: format!(
                "E_ID_RESERVED: plugin.id '{id}' is reserved by the registry, so a listing \
                 request for it is refused at ingest — after your tag is pushed and your release \
                 is public, and the only way out is a different id. The list is \
                 astra-registry/policy/reserved-ids.json, mirrored in spec/reserved-ids.yaml; \
                 that file's `reserved_note` says why each name is kept. Nothing here stops you \
                 building, signing, sideloading or `astra-plugin dev`-ing this plugin under this \
                 id — it is the catalogue that will not carry it."
            ),
        });
    }

    if let Some(why) = id_charset_violation(id) {
        report.registry.push(RegistryFinding {
            code: "E_ID_CHARSET",
            refusal: true,
            message: format!(
                "E_ID_CHARSET: plugin.id '{id}' is not a shape the registry accepts — {why}. Its \
                 charset is {pattern} (spec/reserved-ids.yaml). The daemon's rules are looser and \
                 this plugin installs, so `check` is the only place you hear about it before the \
                 tag.",
                pattern = reserved_ids().id_pattern,
            ),
        });
    }

    for prefix in &reserved_ids().prefixes {
        if id.starts_with(prefix.as_str()) {
            report.registry.push(RegistryFinding {
                code: "E_ID_RESERVED_PREFIX",
                refusal: false,
                message: format!(
                    "E_ID_RESERVED_PREFIX: plugin.id '{id}' begins with '{prefix}', which the \
                     registry reserves for first-party repositories. Whether yours is one is \
                     decided by an allowlist this CLI does not mirror — copying a trust allowlist \
                     would be a second place to grant trust — so this cannot be answered here, \
                     and it is a warning rather than a refusal even under --strict. If your \
                     repository is not on it, the listing is refused at ingest."
                ),
            });
            break;
        }
    }
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

[permissions]
push_to_ui = { reason = "Updates the Sink panel" }

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
            check_permissions(m, &mut report);
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
            "[permissions]",
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

    // ── the registry's id rules ─────────────────────────────────────────────

    /// The pattern [`id_charset_violation`] implements, written once more so
    /// that the spec's literal has something to be compared against.
    ///
    /// It lives here rather than beside the implementation because it is not
    /// an input to anything: the code does not read it, the test does. Two
    /// spellings of one rule with nothing comparing them is the shape this
    /// file's whole mirror exists to avoid, so the comparison is the point of
    /// the constant.
    const ID_PATTERN_IMPLEMENTED: &str = "^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$";

    /// `spec/reserved-ids.yaml` is the list; `src/reserved-ids.yaml` mirrors it.
    ///
    /// Byte-equality first, because the spec file sits outside this crate's
    /// package directory and cannot be `include_str!`d — the same reason
    /// `listing-limits.yaml` and `conformance.json` are vendored, and the same
    /// test.
    ///
    /// **Then the names, and only then the counts.** A name deleted from one
    /// file is caught by the byte comparison; a name deleted from BOTH is
    /// byte-equal and clears any floor by one. With the floor asserted first,
    /// dropping `moderation` reports *"lists 21 and listed 22"* — true, and it
    /// never says the word that a stranger may now list under, so the reader
    /// goes counting instead of reading. astra-registry's
    /// `tools/selftest/validation.mjs` was written the other way round,
    /// watched saying exactly that, and turned around on 2026-09-19; this is
    /// the same lesson on this side of the mirror.
    ///
    /// The named set is deliberately small, and it is NOT a second copy of the
    /// eight panel names — astra-registry's selftest enumerates those, with
    /// the eight it released beside them, and a third copy here is the third
    /// place a policy change has to be remembered. What is named here is what
    /// this crate's own behaviour rests on. Everything else is held by C27
    /// against the registry itself, which is the only check that can tell a
    /// deletion from a deliberate release.
    #[test]
    fn the_reserved_ids_are_the_ones_the_spec_declares() {
        let spec_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../spec/reserved-ids.yaml");
        let spec = std::fs::read_to_string(&spec_path)
            .unwrap_or_else(|e| panic!("cannot read {}: {e}", spec_path.display()));
        // `assert!`, not `assert_eq!`, and the difference is whether anybody
        // reads the failure. These files are a hundred and forty lines and
        // `assert_eq!` prints both of them, escaped, on two lines — watched
        // doing it, while dropping `trust` from the vendored copy. The line
        // that differs is the whole answer.
        if spec != RESERVED_IDS_SPEC {
            let at = spec
                .lines()
                .zip(RESERVED_IDS_SPEC.lines())
                .position(|(a, b)| a != b);
            let differs = match at {
                Some(n) => format!(
                    "line {}: the spec says {:?}, the vendored copy says {:?}",
                    n + 1,
                    spec.lines().nth(n).unwrap_or(""),
                    RESERVED_IDS_SPEC.lines().nth(n).unwrap_or(""),
                ),
                None => format!(
                    "one file is a prefix of the other — {} line(s) against {}",
                    spec.lines().count(),
                    RESERVED_IDS_SPEC.lines().count(),
                ),
            };
            panic!(
                "spec/reserved-ids.yaml and astra-plugin-cli/src/reserved-ids.yaml differ at \
                 {differs}. The spec file is the list; copy it over. And if astra-registry is \
                 what changed, change it THERE first — `python3 \
                 tools/check-registry-mirrors.py --rules C27` is what compares the two \
                 repositories, and a name added here reserves nothing."
            );
        }

        let parsed = reserved_ids();

        // Which names, before any count.
        for (id, why) in [
            (
                "astra",
                "the bare form of the `astra-` prefix, and the plainest impersonation there is",
            ),
            (
                "moderation",
                "the panel page a user is sent to when they report a plugin, and the exemplar \
                 `check_refuses_what_the_registry_refuses` is written against",
            ),
            (
                "test",
                "one of the oldest reservations, and the id a scaffold reaches for by accident",
            ),
        ] {
            assert!(
                parsed.ids.contains(id),
                "'{id}' is no longer in spec/reserved-ids.yaml, so `astra-plugin check` now tells \
                 an author it is theirs to publish under — {why}. If astra-registry released it \
                 on purpose, its `reserved_note` says so and this list changes with the mirror; \
                 read that note before deciding which side is wrong."
            );
        }
        for prefix in ["astra-", "official-", "verified-"] {
            assert!(
                parsed.prefixes.iter().any(|p| p == prefix),
                "the reserved prefix '{prefix}' is not in spec/reserved-ids.yaml. A prefix \
                 dropped here is an impersonation primitive handed back, and this side stops \
                 warning about it a release before the registry stops refusing it."
            );
        }

        // And then the counts, which are about the entries nothing above names.
        assert!(
            parsed.ids.len() >= 22,
            "parsed {} reserved id(s); astra-registry listed 22 on 2026-09-19 and every name \
             asserted above is still here, so either an older reservation was taken out — a \
             security change, not a cleanup — or this file's FORMAT changed and the parser above \
             is what broke.",
            parsed.ids.len()
        );
        assert!(
            parsed.prefixes.len() >= 3,
            "parsed {} reserved prefix(es), and there were 3.",
            parsed.prefixes.len()
        );

        // The pattern is hand-implemented, so the literal is what pins it.
        assert_eq!(
            parsed.id_pattern, ID_PATTERN_IMPLEMENTED,
            "spec/reserved-ids.yaml declares a charset this module does not implement. \
             `id_charset_violation` is `{ID_PATTERN_IMPLEMENTED}` written out by hand; somebody \
             has to read the new pattern and change the code, and copying the literal across is \
             not that."
        );
        assert!(
            parsed.refuse_double_hyphen,
            "the double-hyphen row is gone from spec/reserved-ids.yaml, so `a--b` now passes \
             `check` and is refused at ingest."
        );
    }

    /// The pattern, at its edges, without a manifest in the way.
    #[test]
    fn the_registry_charset_is_the_pattern_the_spec_declares() {
        for ok in ["ab", "a1", "dice-roller", &"a".repeat(64)] {
            assert!(
                id_charset_violation(ok).is_none(),
                "'{ok}' is a listable id and was refused: {:?}",
                id_charset_violation(ok)
            );
        }
        for (bad, expect) in [
            ("p", "shortest listable id is two"),
            (&"a".repeat(65), "the cap is 64"),
            ("Bad", "only lowercase"),
            ("-lead", "starts with a hyphen"),
            ("trail-", "ends with a hyphen"),
            ("a--b", "double hyphen"),
        ] {
            let why = id_charset_violation(bad)
                .unwrap_or_else(|| panic!("'{bad}' is not listable and was accepted"));
            assert!(why.contains(expect), "'{bad}': {why}");
        }
    }

    fn scratch(tag: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "astra-reserved-{tag}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// A plugin directory whose only unusual feature is its id.
    ///
    /// The control below is what makes every assertion in these tests legible:
    /// `kitchen-sink` passes `check --strict` with no locales, no workflow and
    /// no lock, so a failure under another id is about the NAME and not about
    /// the tree. astra-registry's selftest builds its reserved-id fixtures the
    /// same way, for the same reason.
    fn plugin_dir(tag: &str, id: &str) -> std::path::PathBuf {
        let dir = scratch(tag);
        std::fs::write(
            dir.join("plugin.toml"),
            KITCHEN_SINK.replace("kitchen-sink", id),
        )
        .unwrap();
        dir
    }

    fn check_verdict(dir: &Path, strict: bool, gate: Gate) -> Verdict {
        run_full(CheckOptions {
            path: &dir.to_string_lossy(),
            strict,
            fix: false,
            resolve_pin: false,
            gate,
        })
        .expect("the check ran")
    }

    /// `check` is the preflight for the tag, so it fails on what ingest fails
    /// on — while a rename is still free.
    #[test]
    fn check_refuses_what_the_registry_refuses() {
        let control = plugin_dir("control", "dice-roller");
        assert_eq!(
            check_verdict(&control, true, Gate::Check),
            Verdict::Pass,
            "the fixture is refused under a name nobody reserved, so nothing below is about the \
             id at all"
        );

        // `test` and `moderation` are reserved; `p` is one character and the
        // 65th is one past the cap. `search` was this test's exemplar until
        // 2026-09-19, when astra-registry released it along with seven other
        // ordinary words — written against `search` this test would have gone
        // red on the day the mirror first held the real list, which is the
        // mirror working and reads as the mirror broken.
        for id in ["test", "moderation", "p", &"a".repeat(65)] {
            let dir = plugin_dir("refused", id);
            assert_eq!(
                check_verdict(&dir, false, Gate::Check),
                Verdict::Fail,
                "`astra-plugin check` accepted '{id}', which the registry refuses at ingest — \
                 after the author's tag is pushed"
            );
        }

        // The prefix, the other way. Not fatal, `--strict` included: this side
        // does not mirror the first-party allowlist, so it cannot know, and a
        // "cannot know" promoted to an error fails every first-party release.
        let prefixed = plugin_dir("prefixed", "astra-foo");
        assert_eq!(
            check_verdict(&prefixed, true, Gate::Check),
            Verdict::Pass,
            "a reserved PREFIX became strict-fatal. Whether `astra-foo` may be listed depends on \
             astra-registry's first_party_repos / first_party_owners, which spec/reserved-ids.yaml \
             deliberately does not copy — so the honest answer here is a warning, and it stays a \
             warning under --strict."
        );
        let mut report = Report::default();
        let m = parse_manifest(&KITCHEN_SINK.replace("kitchen-sink", "astra-foo"), &mut report)
            .expect("the manifest parses");
        check_registry_ids(&m, &mut report);
        let f = report
            .registry
            .iter()
            .find(|f| f.code == "E_ID_RESERVED_PREFIX")
            .expect("no E_ID_RESERVED_PREFIX finding for 'astra-foo'");
        assert!(!f.refusal, "the prefix finding is a refusal: {}", f.message);
    }

    /// `dev` runs the author's code. It is not the catalogue's gate.
    #[test]
    fn dev_runs_a_plugin_whose_id_the_registry_refuses() {
        let dir = plugin_dir("dev", "moderation");
        assert_eq!(
            check_verdict(&dir, true, Gate::Check),
            Verdict::Fail,
            "the control for this test: `check` must refuse this id, or Gate::Dev passing below \
             proves nothing"
        );
        assert_eq!(
            check_verdict(&dir, true, Gate::Dev),
            Verdict::Pass,
            "`astra-plugin dev` refused to start a plugin because a catalogue this author may \
             never submit to would not list its id. Plugins are not sandboxed and this would be \
             the first place in the project where the registry decides what a user may run on \
             their own machine — Gate::Dev makes every registry finding a note."
        );
    }

    /// `build` packs a bundle. A bundle is not a listing.
    #[test]
    fn build_packs_a_plugin_whose_id_the_registry_refuses() {
        let dir = plugin_dir("build", "moderation");
        let refusals = errors_only(&dir).expect("errors_only ran");
        assert!(
            refusals.is_empty(),
            "`astra-plugin build` refused to pack an id the registry would not list: {refusals:?}. \
             A bundle is sideloaded, handed to a colleague and installed inside companies that \
             have never heard of the catalogue."
        );
    }
}
