//! `astra-plugin init-ci` — write the author's `.github/workflows/release.yml`.
//!
//! An Astra plugin author writes no YAML. They run this once, and from then on
//! a tag is the entire release process. The nine lines this generates call the
//! reusable workflow in [`WORKFLOW_REPO`], which owns every real decision —
//! matrix, toolchain, gates, attestation, upload — so a fix to any of that
//! reaches every plugin at its next pin bump instead of never.
//!
//! # Why the `uses:` line is pinned by commit SHA
//!
//! Because `@v1` is a *movable tag in someone else's repository*, and the job
//! it selects runs inside the author's repository with the author's
//! `contents: write` token. Whoever can move that tag can rewrite every plugin
//! that trusts it. The pin removes that: an upgrade is a commit in the
//! author's repo, made by this command, reviewable in a diff.
//!
//! That is only worth anything if upgrading is easy, which is why this command
//! is idempotent — re-running it rewrites the pin and *keeps the author's
//! inputs*. An `init-ci` that silently dropped a `linux-packages` line would
//! be an `init-ci` nobody ever ran a second time.
//!
//! # Where the SHA comes from
//!
//! Not from a constant compiled into this binary: a CLI installed a year ago
//! would then pin a year-old workflow and call it current. It is resolved with
//! `git ls-remote` at the moment the file is written — [`WORKFLOW_TAG`] if that
//! tag exists, otherwise the default branch's head, with a warning saying so.
//! `--ref` takes either an explicit 40-hex commit (used verbatim, no network)
//! or any ref name to resolve.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result};

/// The repository holding the reusable workflow.
pub const WORKFLOW_REPO: &str = "mihailinl/AstraPlugins";

/// Its path inside that repository. This exact string is what identifies a
/// release workflow when `astra-plugin check` reads one back.
pub const WORKFLOW_FILE: &str = ".github/workflows/plugin-release.yml";

/// The tag that tracks the current released workflow. Resolved *once*, here,
/// and never written into the generated file as a ref — only the commit it
/// pointed at goes in.
pub const WORKFLOW_TAG: &str = "plugin-release/v1";

/// Where the generated caller lives, relative to the repository root.
pub const CALLER_FILE: &str = ".github/workflows/release.yml";

/// The three permissions the reusable workflow's jobs need to exist at all. A
/// called workflow can only reduce what the caller granted, so a caller that
/// omits one of these produces a run that fails in `publish`, after the build,
/// with a permissions error — which is why `check` refuses it up front.
pub const REQUIRED_PERMISSIONS: &[&str] = &["contents", "id-token", "attestations"];

/// How the pinned commit was arrived at, so the command can say so out loud.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PinSource {
    /// `--ref <40-hex>`: taken at face value, no network.
    Explicit,
    /// Resolved from [`WORKFLOW_TAG`].
    ReleaseTag,
    /// Resolved from a ref the caller named.
    NamedRef,
    /// [`WORKFLOW_TAG`] does not exist yet, so the default branch head was used.
    DefaultBranch,
    /// Kept from the file that was already there, because nothing else could
    /// be resolved.
    Existing,
}

#[derive(Debug, Clone)]
pub struct Pin {
    pub sha: String,
    pub source: PinSource,
    /// The ref this came from, for the trailing comment on the `uses:` line.
    pub label: String,
}

pub struct InitCiOptions<'a> {
    pub path: &'a str,
    /// A 40-hex commit (used as-is) or a ref name to resolve. `None` resolves
    /// [`WORKFLOW_TAG`], then the default branch.
    pub workflow_ref: Option<&'a str>,
    /// Overrides the `linux-packages:` input. `None` keeps whatever the
    /// existing file had, and `""` on a fresh file.
    pub linux_packages: Option<&'a str>,
    /// Skip the network entirely and keep the pin already in the file. Fails
    /// if there is no file to keep a pin from.
    pub offline: bool,
}

pub fn run(opts: InitCiOptions<'_>) -> Result<()> {
    let plugin_dir = Path::new(opts.path)
        .canonicalize()
        .with_context(|| format!("Invalid path: {}", opts.path))?;

    if !plugin_dir.join("plugin.toml").exists() {
        anyhow::bail!(
            "No plugin.toml at {} — run this from a plugin directory.",
            plugin_dir.display()
        );
    }

    // The workflow file belongs at the REPOSITORY root, which is not always the
    // plugin directory: a monorepo holds several plugins and one .github/.
    // Getting this wrong writes a workflow GitHub will never run.
    let root = repo_root(&plugin_dir).unwrap_or_else(|| plugin_dir.clone());
    let computed_input = relative_input_path(&root, &plugin_dir);

    // Rewrite the workflow that already releases THIS plugin, whatever it is
    // called — not a fixed `release.yml`. In a monorepo each plugin needs its
    // own caller, and a second `init-ci` that clobbered the first plugin's
    // workflow would silently stop releasing it.
    let existing_for_me =
        find_release_workflow(&plugin_dir)?.filter(|(_, wf)| targets(&root, wf, &plugin_dir));

    let caller_path = match &existing_for_me {
        Some((p, _)) => p.clone(),
        None if computed_input == "." => root.join(CALLER_FILE),
        None => root
            .join(".github")
            .join("workflows")
            .join(format!("release-{}.yml", plugin_id(&plugin_dir)?)),
    };

    let existing = std::fs::read_to_string(&caller_path).ok();
    let previous = existing.as_deref().map(parse_release_workflow);

    let plugin_dir_input = match previous.as_ref().and_then(|p| p.plugin_dir.clone()) {
        // Never recompute an input the author may have adjusted by hand.
        Some(kept) => kept,
        None => computed_input,
    };

    // Same rule as `plugin-dir`: keep what is there, derive it only the first
    // time. Recomputing would silently move a plugin's tag namespace, and the
    // author would find out when a tag they pushed released nothing.
    let tag_prefix = match previous.as_ref().and_then(|p| p.tag_prefix.clone()) {
        Some(kept) if !kept.is_empty() => kept,
        _ => default_tag_prefix(&plugin_dir_input, &plugin_id(&plugin_dir)?),
    };

    let linux_packages = opts
        .linux_packages
        .map(str::to_string)
        .or_else(|| previous.as_ref().and_then(|p| p.linux_packages.clone()))
        .unwrap_or_default();

    let pin = resolve_pin(
        opts.workflow_ref,
        opts.offline,
        previous.as_ref().and_then(|p| p.uses_ref.clone()),
    )?;

    let rendered = render(&pin, &plugin_dir_input, &linux_packages, &tag_prefix);

    let before = previous.as_ref().and_then(|p| p.uses_ref.clone());
    let unchanged = existing.as_deref() == Some(rendered.as_str());

    if let Some(parent) = caller_path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create {}", parent.display()))?;
    }
    std::fs::write(&caller_path, &rendered)
        .with_context(|| format!("Failed to write {}", caller_path.display()))?;

    let shown = caller_path.strip_prefix(&root).unwrap_or(&caller_path);
    if unchanged {
        println!("  Unchanged: {}", shown.display());
    } else if let Some(before) = before.filter(|b| *b != pin.sha) {
        println!("  Upgraded:  {}", shown.display());
        println!("    pin {} -> {}", short(&before), short(&pin.sha));
    } else if existing.is_some() {
        println!("  Rewrote:   {}", shown.display());
    } else {
        println!("  Created:   {}", shown.display());
    }

    println!("    calls  {WORKFLOW_REPO}/{WORKFLOW_FILE}");
    println!("    pinned {} ({})", pin.sha, pin.label);
    println!("    with   plugin-dir: {plugin_dir_input}");
    println!("           tag-prefix: {tag_prefix}");
    if !linux_packages.is_empty() {
        println!("           linux-packages: {linux_packages}");
    }
    if tag_prefix != "v" {
        println!();
        println!(
            "  This repository holds more than one plugin, so this one releases on\n  \
             '{tag_prefix}<version>' — a bare 'v<version>' would start every plugin's workflow."
        );
    }

    match pin.source {
        PinSource::DefaultBranch => {
            println!();
            println!(
                "  Note: '{WORKFLOW_TAG}' does not exist in {WORKFLOW_REPO} yet, so this pins the"
            );
            println!(
                "  current head of its default branch. Re-run `astra-plugin init-ci` once the"
            );
            println!("  tag exists to move onto a released workflow.");
        }
        PinSource::Existing => {
            println!();
            println!("  Note: could not reach {WORKFLOW_REPO}, so the existing pin was kept.");
        }
        _ => {}
    }

    println!();
    println!("  Next: commit this file, then release with");
    println!("    astra-plugin version <semver>");

    Ok(())
}

/// Nearest ancestor holding a `.git`, i.e. the directory GitHub treats as the
/// repository root.
///
/// Canonicalised first, and that is not incidental: `astra-plugin check .` in a
/// monorepo passes the relative path `.`, whose only ancestors are `.` and `""`.
/// Walking those finds nothing, the repository root silently becomes the plugin
/// directory, and every check that reads `.github/workflows` reports "no CI" at
/// a repository that has it.
pub fn repo_root(from: &Path) -> Option<PathBuf> {
    let from = from.canonicalize().ok()?;
    from.ancestors()
        .find(|d| d.join(".git").exists())
        .map(Path::to_path_buf)
}

/// `plugin-dir:` as the reusable workflow wants it — forward slashes, relative
/// to the repository root, `.` when they are the same directory.
fn relative_input_path(root: &Path, plugin_dir: &Path) -> String {
    let rel = plugin_dir.strip_prefix(root).unwrap_or(Path::new("."));
    let s = rel.to_string_lossy().replace('\\', "/");
    if s.is_empty() { ".".to_string() } else { s }
}

/// Does this workflow's `plugin-dir` resolve to this plugin?
fn targets(root: &Path, wf: &ReleaseWorkflow, plugin_dir: &Path) -> bool {
    let Some(input) = wf.plugin_dir.as_deref() else {
        // No input at all means the default, `.` — the repository root.
        return root == plugin_dir;
    };
    match (root.join(input).canonicalize(), plugin_dir.canonicalize()) {
        (Ok(a), Ok(b)) => a == b,
        _ => false,
    }
}

/// The tag namespace a plugin at `plugin_dir` should release under, when
/// nothing has been written down yet.
///
/// A repository holds one tag namespace and a monorepo holds several plugins,
/// so `v0.1.1` cannot mean all of them. Push it and every caller fires: the
/// ones whose `plugin.toml` says another version die on the workflow's tag
/// assertion, and the ones that agree race each other to create the same
/// Release. The id in the tag is what makes eleven plugins in one repository
/// releasable at all — and it is derived from `plugin-dir`, the same input
/// that already tells us which shape we are in, so an author never chooses it.
pub fn default_tag_prefix(plugin_dir_input: &str, id: &str) -> String {
    if plugin_dir_input == "." {
        "v".to_string()
    } else {
        format!("{id}-v")
    }
}

/// The tag prefix that will *actually* release this plugin: whatever its own
/// caller workflow declares, falling back to what `init-ci` would write.
///
/// Read from the workflow rather than recomputed, because an author is free to
/// hand-edit `tag-prefix:` and `astra-plugin version` must print the tag that
/// works, not the tag we would have chosen.
pub fn tag_prefix_for(plugin_dir: &Path) -> String {
    let root = repo_root(plugin_dir).unwrap_or_else(|| plugin_dir.to_path_buf());
    if let Ok(Some((_, wf))) = find_release_workflow(plugin_dir)
        && targets(&root, &wf, plugin_dir)
    {
        // A caller with no `tag-prefix:` is one the reusable workflow defaults
        // to "v" for. Say the same thing it will.
        return wf
            .tag_prefix
            .filter(|p| !p.is_empty())
            .unwrap_or_else(|| "v".to_string());
    }
    let input = relative_input_path(&root, plugin_dir);
    let id = plugin_id(plugin_dir).unwrap_or_default();
    default_tag_prefix(&input, &id)
}

fn plugin_id(dir: &Path) -> Result<String> {
    let src = std::fs::read_to_string(dir.join("plugin.toml"))?;
    let doc: toml::Value = toml::from_str(&src).context("plugin.toml is not valid TOML")?;
    doc.get("plugin")
        .and_then(|p| p.get("id"))
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .context("plugin.toml has no [plugin] id")
}

fn short(sha: &str) -> String {
    sha.chars().take(10).collect()
}

/// Resolve the commit to pin.
fn resolve_pin(workflow_ref: Option<&str>, offline: bool, existing: Option<String>) -> Result<Pin> {
    if let Some(r) = workflow_ref {
        if is_commit_sha(r) {
            return Ok(Pin {
                sha: r.to_ascii_lowercase(),
                source: PinSource::Explicit,
                label: "--ref".to_string(),
            });
        }
        if offline {
            anyhow::bail!("--offline cannot resolve the ref '{r}'; pass --ref <40-hex commit>");
        }
        let sha = ls_remote(r)?.with_context(|| format!("{WORKFLOW_REPO} has no ref '{r}'"))?;
        return Ok(Pin {
            sha,
            source: PinSource::NamedRef,
            label: r.to_string(),
        });
    }

    if offline {
        let sha = existing.context(
            "--offline needs a pin to keep, and there is no .github/workflows/release.yml yet",
        )?;
        return Ok(Pin {
            sha,
            source: PinSource::Existing,
            label: "kept, offline".to_string(),
        });
    }

    match ls_remote(&format!("refs/tags/{WORKFLOW_TAG}")) {
        Ok(Some(sha)) => Ok(Pin {
            sha,
            source: PinSource::ReleaseTag,
            label: WORKFLOW_TAG.to_string(),
        }),
        // The tag does not exist yet. Pinning the default branch head is still
        // an immutable commit — the property that matters — it just is not a
        // reviewed release, so the caller is told.
        Ok(None) => {
            let sha = ls_remote("HEAD")?
                .with_context(|| format!("{WORKFLOW_REPO} answered but reported no HEAD"))?;
            Ok(Pin {
                sha,
                source: PinSource::DefaultBranch,
                label: "default branch".to_string(),
            })
        }
        Err(e) => match existing {
            Some(sha) => Ok(Pin {
                sha,
                source: PinSource::Existing,
                label: "kept, offline".to_string(),
            }),
            None => Err(e).context(
                "Could not resolve the workflow commit, and there is no existing pin to keep. \
                 Pass --ref <40-hex commit> to pin one by hand.",
            ),
        },
    }
}

/// The commit `init-ci` would pin right now, for `check --resolve-pin`.
///
/// `Ok(None)` means the remote answered and has neither the release tag nor a
/// HEAD, which should not happen; every network failure is an `Err`, so the
/// caller can report "not checked" rather than "stale".
pub fn current_upstream_pin() -> Result<Option<String>> {
    if let Some(sha) = ls_remote(&format!("refs/tags/{WORKFLOW_TAG}"))? {
        return Ok(Some(sha));
    }
    ls_remote("HEAD")
}

pub fn is_commit_sha(s: &str) -> bool {
    s.len() == 40 && s.chars().all(|c| c.is_ascii_hexdigit())
}

/// One `git ls-remote`. `Ok(None)` means the remote answered and has no such
/// ref, which is a different fact from "the network is down" and is why this
/// is not a bare `Result<String>`.
fn ls_remote(reference: &str) -> Result<Option<String>> {
    let url = format!("https://github.com/{WORKFLOW_REPO}.git");
    let out = Command::new("git")
        // Without this, a private or renamed repo turns into a credential
        // prompt on a terminal that may not be attached to anything.
        .env("GIT_TERMINAL_PROMPT", "0")
        .args(["ls-remote", &url, reference])
        .output()
        .context("Failed to run `git ls-remote` — is git installed?")?;

    if !out.status.success() {
        anyhow::bail!(
            "git ls-remote {url} {reference} failed: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }

    let text = String::from_utf8_lossy(&out.stdout);
    let mut plain = None;
    for line in text.lines() {
        let mut parts = line.split('\t');
        let (Some(sha), Some(name)) = (parts.next(), parts.next()) else {
            continue;
        };
        // An annotated tag's own object is not a commit. `^{}` is the peeled
        // line, and it is the one a checkout must use; prefer it whenever the
        // remote sent both.
        if name.ends_with("^{}") {
            return Ok(Some(sha.to_string()));
        }
        plain.get_or_insert_with(|| sha.to_string());
    }
    Ok(plain)
}

/// The generated file. Verbatim output — no templating engine, no partial
/// rewrite of an existing file: `init-ci` owns this file completely, which is
/// what makes re-running it a safe way to upgrade.
pub fn render(pin: &Pin, plugin_dir: &str, linux_packages: &str, tag_prefix: &str) -> String {
    format!(
        r#"# Generated by `astra-plugin init-ci`. Re-run that command to upgrade the pin
# below; it keeps the inputs you set here.
#
# A tag is the whole release process:
#
#   astra-plugin version 0.2.0
#   git commit -am "release 0.2.0"
#   git tag {tag_prefix}0.2.0 && git push --tags
name: Release

on:
  push:
    # Narrowed to this plugin's own tag namespace, and it must stay in step with
    # `tag-prefix:` below. A glob wider than the prefix starts this workflow on
    # another plugin's tag, where it fails the version assertion; a glob
    # narrower than it never starts at all, and a release that silently does
    # nothing is the worst of the two.
    tags: ["{tag_prefix}*"]

# Required, and required HERE: a reusable workflow can only reduce the
# permissions its caller granted, never grant itself more. Leave all three.
permissions:
  contents: write       # create the Release and upload assets
  id-token: write       # mint the OIDC token that makes signing keyless
  attestations: write   # store the build attestation on GitHub

jobs:
  release:
    # Pinned by commit SHA, not by a moving tag: whoever can move `{tag}`
    # in {repo} would otherwise own the build step of every plugin
    # that trusts it — and that build step runs in YOUR repository with the
    # token above. `astra-plugin init-ci` keeps this line current.
    uses: {repo}/{file}@{sha}  # {label}
    with:
      plugin-dir: {plugin_dir}
      # The tag that releases THIS plugin, and nothing else in this repository.
      tag-prefix: "{tag_prefix}"
      # Extra apt packages the Linux build needs, e.g. "libasound2-dev pkg-config".
      linux-packages: "{linux_packages}"
    # No `secrets: inherit`, deliberately. This workflow declares no secrets,
    # so the job that runs your build.rs and your npm lifecycle scripts has
    # nothing to leak.
"#,
        tag = WORKFLOW_TAG,
        repo = WORKFLOW_REPO,
        file = WORKFLOW_FILE,
        sha = pin.sha,
        label = pin.label,
        plugin_dir = plugin_dir,
        tag_prefix = tag_prefix,
        linux_packages = linux_packages,
    )
}

// ── reading one back ────────────────────────────────────────────────────────
//
// This is a targeted scan, not a YAML parse, and the distinction is worth
// stating plainly: the CLI has no YAML dependency, and adding a deprecated or
// unmaintained one to read a file this same command generates would be a poor
// trade. It reads indentation and `key: value`, which is enough for the
// generated file and for any hand edit that stays in block style. A workflow
// written in flow style (`permissions: {contents: write}`) reads as "not
// found", so `check` reports what it did not find rather than claiming a pass.

/// What `check` needs to know about a caller workflow.
#[derive(Debug, Default, Clone)]
pub struct ReleaseWorkflow {
    /// `owner/repo` from the `uses:` line.
    pub uses_repo: Option<String>,
    /// Whatever followed the `@`.
    pub uses_ref: Option<String>,
    pub plugin_dir: Option<String>,
    /// `tag-prefix:`, absent when the caller relies on the workflow's `"v"`.
    pub tag_prefix: Option<String>,
    pub linux_packages: Option<String>,
    /// Top-level `permissions:` mapping.
    pub permissions: BTreeMap<String, String>,
    pub secrets_inherit: bool,
    /// A `tags:` key under `on: push:`.
    pub tag_trigger: bool,
    /// The raw `tags:` value, so `check` can tell whether the trigger can fire
    /// on the tag `tag-prefix` asks for. A trigger and a prefix that disagree
    /// are a plugin that never releases, and nothing else reports it.
    pub tag_globs: Vec<String>,
}

impl ReleaseWorkflow {
    /// True when this file calls the Astra reusable workflow at all.
    pub fn is_astra_release(&self) -> bool {
        self.uses_ref.is_some()
    }
}

/// The caller workflow that releases *this* plugin, if there is one.
///
/// Every `*.yml`/`*.yaml` under `.github/workflows/` is read, not just
/// `release.yml`: an author is free to name it anything, and a check that only
/// looked at one filename would report "no release workflow" at a repository
/// that has a perfectly good one.
///
/// When several call the reusable workflow — the normal shape of a monorepo,
/// one caller per plugin — the one whose `plugin-dir` resolves to this
/// directory wins. Without that, `check` in `plugins/b` would read `plugins/a`'s
/// workflow and report that its `plugin-dir` is wrong, which is both false and
/// unfixable.
pub fn find_release_workflow(plugin_dir: &Path) -> Result<Option<(PathBuf, ReleaseWorkflow)>> {
    let all = all_release_workflows(plugin_dir)?;
    if all.is_empty() {
        return Ok(None);
    }
    let root = repo_root(plugin_dir).unwrap_or_else(|| plugin_dir.to_path_buf());
    if let Some(mine) = all.iter().find(|(_, wf)| targets(&root, wf, plugin_dir)) {
        return Ok(Some(mine.clone()));
    }
    // No match: return the first anyway, so the caller reports the mismatch
    // rather than "no release workflow", which would send the author to
    // `init-ci` when the real problem is a wrong `plugin-dir`.
    Ok(all.into_iter().next())
}

fn all_release_workflows(plugin_dir: &Path) -> Result<Vec<(PathBuf, ReleaseWorkflow)>> {
    let Some(dir) = workflows_dir(plugin_dir) else {
        return Ok(Vec::new());
    };
    let mut entries: Vec<PathBuf> = std::fs::read_dir(&dir)
        .with_context(|| format!("Failed to read {}", dir.display()))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            p.extension()
                .and_then(|e| e.to_str())
                .is_some_and(|e| e == "yml" || e == "yaml")
        })
        .collect();
    // Deterministic: two workflows both calling it would otherwise be reported
    // differently depending on readdir order.
    entries.sort();

    let mut out = Vec::new();
    for path in entries {
        let Ok(text) = std::fs::read_to_string(&path) else {
            continue;
        };
        let wf = parse_release_workflow(&text);
        if wf.is_astra_release() {
            out.push((path, wf));
        }
    }
    Ok(out)
}

/// `<repo root>/.github/workflows`, if it exists.
pub fn workflows_dir(plugin_dir: &Path) -> Option<PathBuf> {
    let root = repo_root(plugin_dir).unwrap_or_else(|| plugin_dir.to_path_buf());
    let dir = root.join(".github").join("workflows");
    dir.is_dir().then_some(dir)
}

pub fn parse_release_workflow(text: &str) -> ReleaseWorkflow {
    let mut wf = ReleaseWorkflow::default();

    // Indent of the `permissions:`/`on:`/`uses:` blocks currently being read,
    // so a nested `permissions:` under a job is not mistaken for the top-level
    // one (a called workflow cannot be granted permissions per-job by its
    // caller, so only the top-level block counts).
    let mut permissions_indent: Option<usize> = None;
    let mut on_indent: Option<usize> = None;
    let mut push_indent: Option<usize> = None;
    let mut with_indent: Option<usize> = None;

    for raw in text.lines() {
        let line = strip_comment(raw);
        if line.trim().is_empty() {
            continue;
        }
        let indent = line.len() - line.trim_start().len();
        let trimmed = line.trim();

        // Leaving a block we were reading.
        if permissions_indent.is_some_and(|i| indent <= i) {
            permissions_indent = None;
        }
        if with_indent.is_some_and(|i| indent <= i) {
            with_indent = None;
        }
        if push_indent.is_some_and(|i| indent <= i) {
            push_indent = None;
        }
        if on_indent.is_some_and(|i| indent <= i) {
            on_indent = None;
        }

        if let Some(pi) = permissions_indent
            && indent > pi
            && let Some((k, v)) = split_kv(trimmed)
        {
            wf.permissions.insert(k.to_string(), v.to_string());
            continue;
        }

        if let Some(wi) = with_indent
            && indent > wi
            && let Some((k, v)) = split_kv(trimmed)
        {
            match k {
                "plugin-dir" => wf.plugin_dir = Some(unquote(v)),
                "tag-prefix" => wf.tag_prefix = Some(unquote(v)),
                "linux-packages" => wf.linux_packages = Some(unquote(v)),
                _ => {}
            }
            continue;
        }

        if let Some((k, v)) = split_kv(trimmed) {
            match k {
                "permissions" if indent == 0 && v.is_empty() => permissions_indent = Some(indent),
                "on" if indent == 0 => on_indent = Some(indent),
                "push" if on_indent.is_some_and(|i| indent > i) => push_indent = Some(indent),
                "tags" if push_indent.is_some_and(|i| indent > i) => {
                    wf.tag_trigger = true;
                    wf.tag_globs = parse_flow_list(v);
                }
                "with" if v.is_empty() => with_indent = Some(indent),
                "secrets" if v.trim() == "inherit" => wf.secrets_inherit = true,
                "uses" if v.contains(WORKFLOW_FILE) => {
                    let value = unquote(v);
                    let (target, at) = match value.rsplit_once('@') {
                        Some((t, a)) => (t, Some(a.to_string())),
                        None => (value.as_str(), None),
                    };
                    wf.uses_repo = target
                        .strip_suffix(&format!("/{WORKFLOW_FILE}"))
                        .map(str::to_string);
                    wf.uses_ref = at;
                }
                _ => {}
            }
        }
    }

    wf
}

/// Drop a trailing `# …`, without eating a `#` that is inside a quoted scalar.
fn strip_comment(line: &str) -> &str {
    let bytes = line.as_bytes();
    let mut quote: Option<u8> = None;
    for (i, &b) in bytes.iter().enumerate() {
        match quote {
            Some(q) if b == q => quote = None,
            Some(_) => {}
            None if b == b'"' || b == b'\'' => quote = Some(b),
            // A `#` only starts a comment at the start of a line or after
            // whitespace — `a#b` is the scalar `a#b`.
            None if b == b'#' && (i == 0 || bytes[i - 1].is_ascii_whitespace()) => {
                return &line[..i];
            }
            None => {}
        }
    }
    line
}

fn split_kv(trimmed: &str) -> Option<(&str, &str)> {
    let t = trimmed.strip_prefix("- ").unwrap_or(trimmed);
    let (k, v) = t.split_once(':')?;
    let k = k.trim();
    if k.is_empty() || k.contains(' ') {
        return None;
    }
    Some((k, v.trim()))
}

/// A YAML flow sequence on one line: `["v*", "x"]` -> `["v*", "x"]`.
///
/// Returns empty for anything else, including the block form
/// (`tags:` then `- "v*"` on the next lines). Empty therefore means "could not
/// tell", never "there are none" — the one caller treats it that way and stays
/// quiet rather than reporting a glob mismatch it did not actually read.
fn parse_flow_list(v: &str) -> Vec<String> {
    let v = v.trim();
    let Some(inner) = v.strip_prefix('[').and_then(|s| s.strip_suffix(']')) else {
        return Vec::new();
    };
    inner
        .split(',')
        .map(unquote)
        .filter(|s| !s.is_empty())
        .collect()
}

fn unquote(v: &str) -> String {
    let v = v.trim();
    for q in ['"', '\''] {
        if v.len() >= 2 && v.starts_with(q) && v.ends_with(q) {
            return v[1..v.len() - 1].to_string();
        }
    }
    v.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pin(sha: &str) -> Pin {
        Pin {
            sha: sha.to_string(),
            source: PinSource::Explicit,
            label: "--ref".to_string(),
        }
    }

    #[test]
    fn render_round_trips_through_the_reader() {
        let sha = "4f1a9c2e6b8d3057af21e94c7b0d6a58e3c1f902";
        let text = render(
            &pin(sha),
            "plugins/dice-roller",
            "libasound2-dev pkg-config",
            "dice-roller-v",
        );
        let wf = parse_release_workflow(&text);

        assert_eq!(wf.uses_repo.as_deref(), Some(WORKFLOW_REPO));
        assert_eq!(wf.uses_ref.as_deref(), Some(sha));
        assert_eq!(wf.plugin_dir.as_deref(), Some("plugins/dice-roller"));
        assert_eq!(
            wf.linux_packages.as_deref(),
            Some("libasound2-dev pkg-config")
        );
        assert_eq!(wf.tag_prefix.as_deref(), Some("dice-roller-v"));
        assert!(wf.tag_trigger);
        // The trigger and the prefix are the two halves that must agree, and
        // the generated file is the one place they are guaranteed to.
        assert_eq!(wf.tag_globs, vec!["dice-roller-v*".to_string()]);
        assert!(!wf.secrets_inherit);
        for p in REQUIRED_PERMISSIONS {
            assert_eq!(wf.permissions.get(*p).map(String::as_str), Some("write"));
        }
    }

    /// The whole point of the generated file: two runs at the same pin must
    /// produce identical bytes, or "re-run it to upgrade" is a lie that shows
    /// up as noise in every diff.
    #[test]
    fn render_is_deterministic() {
        let sha = "0".repeat(40);
        assert_eq!(
            render(&pin(&sha), ".", "", "v"),
            render(&pin(&sha), ".", "", "v")
        );
    }

    /// The monorepo rule, which is the whole reason `tag-prefix` exists: a
    /// repository root keeps the bare `v`, and anything below it takes the
    /// plugin's id. Eleven plugins sharing `v0.1.1` is eleven workflows firing
    /// on one tag.
    #[test]
    fn a_monorepo_plugin_gets_its_own_tag_namespace() {
        assert_eq!(default_tag_prefix(".", "dice-roller"), "v");
        assert_eq!(
            default_tag_prefix("examples/dice-roller", "dice-roller"),
            "dice-roller-v"
        );
        // The id, not the directory: examples/companion carries the id
        // `companion-cat`, and the tag has to be the one the registry lists.
        assert_eq!(
            default_tag_prefix("examples/companion", "companion-cat"),
            "companion-cat-v"
        );
    }

    /// A generated file's trigger must be able to fire on its own prefix, and a
    /// caller left on `v*` in a monorepo must not.
    #[test]
    fn the_trigger_and_the_prefix_are_checked_against_each_other() {
        assert!(crate::commands::validate::glob_can_match("v*", "v"));
        assert!(crate::commands::validate::glob_can_match(
            "dice-roller-v*",
            "dice-roller-v"
        ));
        // The bug this catches: prefix moved to the monorepo form, glob left
        // behind. The tag lands and nothing runs.
        assert!(!crate::commands::validate::glob_can_match(
            "v*",
            "dice-roller-v"
        ));
        // Block-style `tags:` reads as "could not tell", never as "none".
        assert!(parse_flow_list("").is_empty());
        assert_eq!(parse_flow_list(r#"["a*", 'b*']"#), vec!["a*", "b*"]);
    }

    /// A job-level `permissions:` is not the caller's grant, and reading it as
    /// one would pass a workflow whose top-level block is missing entirely.
    #[test]
    fn nested_permissions_are_not_the_top_level_block() {
        let text = "\
name: Release
on:
  push:
    tags: [\"v*\"]
jobs:
  release:
    permissions:
      contents: write
      id-token: write
      attestations: write
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@abc
";
        let wf = parse_release_workflow(text);
        assert!(wf.is_astra_release());
        assert!(wf.permissions.is_empty(), "{:?}", wf.permissions);
    }

    #[test]
    fn secrets_inherit_is_seen() {
        let text = "\
jobs:
  release:
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@abc
    secrets: inherit
";
        assert!(parse_release_workflow(text).secrets_inherit);
    }

    #[test]
    fn a_hash_inside_a_quoted_scalar_is_not_a_comment() {
        assert_eq!(
            strip_comment("  key: \"a # b\"  # tail"),
            "  key: \"a # b\"  "
        );
        assert_eq!(strip_comment("  key: a#b"), "  key: a#b");
    }

    #[test]
    fn commit_shas_are_recognised_and_tags_are_not() {
        assert!(is_commit_sha("4f1a9c2e6b8d3057af21e94c7b0d6a58e3c1f902"));
        assert!(!is_commit_sha("v1"));
        assert!(!is_commit_sha("plugin-release/v1"));
        assert!(!is_commit_sha("4f1a9c2e"));
    }
}
