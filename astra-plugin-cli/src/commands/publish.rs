//! `astra-plugin publish` — get a release into the Astra registry.
//!
//! Two things, and it is worth being precise about which is which, because the
//! word "publish" does more work in most tools than it does here:
//!
//! * `--dry-run` runs **locally** every check the registry runs that can be run
//!   locally, and then names the ones only the registry can run. It uploads
//!   nothing and needs no network.
//! * with no flags it prints, and offers to open, the panel's **submission
//!   page** (contract FLOW-77) with the repository and the tag filled in. The
//!   page fills in its form from the link and submits nothing: the author
//!   submits it, signed in to the Minice account their repository is bound to.
//!
//! **This command never uploads a bundle and never holds a credential.** The
//! artifacts are GitHub Release assets your CI attached and attested; the
//! registry reads them from your repository and verifies every one from
//! scratch. So all a submission carries is `owner/repo` and a tag, which is
//! exactly why it can be a link you open in a browser you are already signed in
//! to, rather than a token this program would have to be trusted with.
//!
//! # CLI 0.5.0: the panel for everybody (FLOW-45)
//!
//! From the registry's cutover there is no issue channel: no listing form, no
//! release ping, no `/recheck`. A new tag is noticed by the registry's poll, a
//! first listing is submitted in the panel, and everything that follows — a
//! hold, a delay, a stop, a Recheck, an appeal — is the panel's. So `publish`
//! opens the submission page for every repository. A repository with no
//! binding line at `HEAD` is told so first, because the registry refuses its
//! first listing `B_UNBOUND`.
//!
//! `--notify` is kept for this one minor release (FLOW-47): it says detection
//! is automatic and opens the same page. The next minor removes it.
//!
//! What happens to a release after it is submitted — published, delayed, or
//! held for a person — is the registry's `docs/POLICY.md`, and the panel shows
//! which.

use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result};
use astra_plugin_manifest::PluginManifest;

use crate::commands::init_ci::{repo_root, tag_prefix_for};
use crate::hprintln;

pub struct PublishOptions<'a> {
    pub path: &'a str,
    /// `owner/name`. Default: parsed from the `origin` remote.
    pub repo: Option<&'a str>,
    /// The release tag. Default: the plugin's tag prefix + its version.
    pub tag: Option<&'a str>,
    /// Run the local half of the registry's checks and stop.
    pub dry_run: bool,
    /// FLOW-47's one-minor stub: says detection is automatic, then opens the
    /// same page.
    pub notify: bool,
    /// Print the URL and do not try to open a browser.
    pub print_url: bool,
}

/// Returns the submission URL when there is one, so `--json` can carry it.
///
/// `--print-url` exists for scripts, and under `--json` the human line it
/// prints is suppressed — the URL has to reach the document instead, or the two
/// flags together produce nothing at all.
pub fn run(opts: PublishOptions<'_>) -> Result<Option<String>> {
    let dir = Path::new(opts.path)
        .canonicalize()
        .with_context(|| format!("Invalid path: {}", opts.path))?;
    let manifest_path = dir.join("plugin.toml");
    if !manifest_path.exists() {
        anyhow::bail!(
            "No plugin.toml at {} — run this from a plugin directory.",
            dir.display()
        );
    }
    let manifest = PluginManifest::from_file(&manifest_path)?;
    let id = manifest.plugin.id.clone();
    let version = manifest.plugin.version.clone();

    let tag = match opts.tag {
        Some(t) => t.to_string(),
        None => format!("{}{version}", tag_prefix_for(&dir)),
    };

    if opts.dry_run {
        dry_run(&dir, &manifest, &tag)?;
        return Ok(None);
    }

    // The repository is one of the two facts the registry cannot read out of
    // the bundle (the other is the tag), so it is the one thing worth being
    // stubborn about getting right rather than guessing.
    let repo = match opts.repo {
        Some(r) => normalise_repo(r).ok_or_else(|| {
            anyhow::anyhow!("--repo must be `owner/name`, e.g. `you/{id}` — not a URL")
        })?,
        None => detect_repo(&dir)?,
    };

    let url = crate::panel::submission_url(&repo, &tag).map_err(|e| anyhow::anyhow!("{e}"))?;
    let bound = bound_at_head(&dir);

    hprintln!("{id} {version} — submission for {repo}@{tag}, in the panel\n");
    warn_if_tag_is_missing(&dir, &tag);
    if opts.notify {
        // FLOW-47: kept one minor so a script that runs it does not break, and
        // told the truth rather than silently doing something else.
        hprintln!(
            "  `--notify` is no longer needed and goes in the next minor release. The registry\n\
             \x20 detects a new tag of a listed plugin by itself; there is nothing to ping. If a\n\
             \x20 release has not appeared, its state and the reason are on the panel's page for\n\
             \x20 it, which is the link below.\n"
        );
    }
    match &bound {
        Some(token) => hprintln!(
            "  Bound: `astra-binding: {token}` is line 1 of the owner file at HEAD. Submit in the\n\
             \x20 panel signed in to the Minice account that minted that token. The page fills itself\n\
             \x20 in from this link and submits nothing until you do. The registry reads the tag's\n\
             \x20 commit, not HEAD — `astra-plugin check --tag {tag}` reads it the same way.\n"
        ),
        None => hprintln!(
            "  Not bound: the owner file at HEAD carries no binding line, and the registry refuses\n\
             \x20 a first listing without one (B_UNBOUND). Mint a token in the panel, run\n\
             \x20 `astra-plugin init-ci --binding <token>`, commit it, and tag again:\n\
             \x20   {docs}\n",
            docs = crate::commands::init_ci::BINDING_DOCS_URL
        ),
    }
    hprintln!("{url}\n");

    if opts.print_url {
        return Ok(Some(url));
    }
    match open_in_browser(&url) {
        Ok(()) => hprintln!("Opened in your browser. Check the prefilled fields before you submit."),
        Err(e) => hprintln!("Could not open a browser ({e}). Copy the URL above."),
    }
    Ok(Some(url))
}

/// Everything the registry checks that can be checked here, and a plain list of
/// what cannot.
///
/// The second half is the point. A dry run that printed only green ticks would
/// be telling an author that their submission will pass, and the checks that
/// actually reject submissions — the build attestation, repository ownership,
/// a name that collides with a listed one — are all checks about the world, not
/// about the files on this disk. Naming them is the difference between a
/// preflight and a promise nobody can keep.
fn dry_run(dir: &Path, manifest: &PluginManifest, tag: &str) -> Result<()> {
    let id = &manifest.plugin.id;
    let version = &manifest.plugin.version;
    hprintln!("Dry run: {id} {version}, expected release tag {tag}\n");

    hprintln!("── checked here ─────────────────────────────────────────────");
    // `Gate::Check`: this IS the preflight for a listing request, so a reserved
    // or unlistable id stops it here rather than at ingest.
    crate::commands::validate::run_with(
        &dir.to_string_lossy(),
        true,
        false,
        crate::commands::validate::Gate::Check,
    )?;

    let bundles = find_bundles(dir, id, version);
    if bundles.is_empty() {
        hprintln!(
            "\n  no {id}-{version}-*.astraplugin next to the plugin — `astra-plugin build` first,\n\
             \x20 or let CI build it. The registry reads the bundle CI attested, never a local one,\n\
             \x20 so this is a preflight on the same bytes rather than a check of what gets listed."
        );
    } else {
        for bundle in &bundles {
            hprintln!("\n  {}", bundle.display());
            crate::commands::verify::run(&bundle.to_string_lossy(), false)?;
        }
    }

    hprintln!("\n── only the registry can check these ────────────────────────");
    for line in REGISTRY_ONLY_CHECKS {
        hprintln!("  · {line}");
    }
    hprintln!(
        "\n  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code\n\
         \x20 each failure produces. What happens to a release that passes — published now,\n\
         \x20 delayed 24 hours, or held for a person — is docs/POLICY.md."
    );
    Ok(())
}

/// The checks that need the network, the catalogue, or a signature — named
/// rather than implied.
///
/// FLOW-48: the four the binding brings, each with the code a failure
/// produces, so an author can search for the same word twice. The owner-file
/// login line left with the issue form it belonged to (CLI 0.5.0).
pub const REGISTRY_ONLY_CHECKS: &[&str] = &[
    "the build attestation, and that it was produced by the pinned Astra release workflow \
     (a hand-built bundle is refused however good it is)",
    "that the attestation's workflow commit is one the registry's trust.json allows \
     (E_WORKFLOW_NOT_ALLOWED)",
    "that the release assets are served from your repository's own release namespace",
    "the binding verdict: that the token on the binding line at the tagged commit is bound to \
     a Minice account (B_BINDING_UNUSABLE)",
    "eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)",
    "the ids against the identity record: that the repository and its owner are the ones this \
     listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)",
    "that the id and display name do not collide with a listed plugin",
    "that the licence is on the registry's SPDX allowlist",
    "that the version is strictly newer than the listed one",
    "the declared-vs-called host RPC scan",
];

/// The token on the binding line of the owner file at `HEAD`, when there is
/// exactly one valid line — `None` for no line, a malformed file, no commit,
/// or no git repository at all.
///
/// `HEAD`, not the working tree: a line typed and never committed binds
/// nothing, and linking such an author to the panel would send them to a
/// submission the registry refuses. `check --tag` is the exact prediction for
/// a tag; this only decides which door to print.
pub fn bound_at_head(dir: &Path) -> Option<String> {
    let root = repo_root(dir)?;
    let out = Command::new("git")
        .arg("-C")
        .arg(&root)
        .args(["cat-file", "blob", &format!("HEAD:{}", crate::binding::OWNER_FILE)])
        .env_remove("GIT_DIR")
        .env_remove("GIT_WORK_TREE")
        .env_remove("GIT_INDEX_FILE")
        .env_remove("GIT_COMMON_DIR")
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    match crate::binding::parse(&out.stdout) {
        crate::binding::Outcome::One { token, .. } => Some(token),
        _ => None,
    }
}

// ── the repository ──────────────────────────────────────────────────────────

/// `owner/name` out of a git remote, or an explanation of what to pass instead.
fn detect_repo(dir: &Path) -> Result<String> {
    let root = repo_root(dir).unwrap_or_else(|| dir.to_path_buf());
    let out = Command::new("git")
        .arg("-C")
        .arg(&root)
        .args(["remote", "get-url", "origin"])
        .output();

    let url = match out {
        Ok(o) if o.status.success() => String::from_utf8_lossy(&o.stdout).trim().to_string(),
        _ => String::new(),
    };
    if let Some(repo) = parse_remote(&url) {
        return Ok(repo);
    }
    anyhow::bail!(
        "Could not work out which GitHub repository this is{}.\n\
         Pass it: astra-plugin publish --repo you/your-plugin\n\
         \n\
         It has to be a GitHub repository with the release on it: the registry lists a plugin \
         by its repository identity, and every installed copy is pinned to it.",
        if url.is_empty() {
            String::new()
        } else {
            format!(" (`origin` is {url})")
        }
    )
}

/// The three shapes a GitHub remote comes in, and nothing else.
pub fn parse_remote(url: &str) -> Option<String> {
    let url = url.trim();
    let rest = [
        "git@github.com:",
        "ssh://git@github.com/",
        "https://github.com/",
        "http://github.com/",
    ]
    .iter()
    .find_map(|p| url.strip_prefix(p))?;
    normalise_repo(rest)
}

/// `owner/name`, with the decorations people paste taken off.
pub fn normalise_repo(raw: &str) -> Option<String> {
    let s = raw
        .trim()
        .trim_start_matches('@')
        .trim_end_matches('/')
        .trim_end_matches(".git")
        .trim_end_matches('/');
    let mut parts = s.split('/');
    let (owner, name) = (parts.next()?, parts.next()?);
    if parts.next().is_some() || owner.is_empty() || name.is_empty() {
        return None;
    }
    let ok = |s: &str| {
        s.chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.')
    };
    if !ok(owner) || !ok(name) {
        return None;
    }
    Some(format!("{owner}/{name}"))
}

/// A tag that does not exist yet is the most common reason a submission bounces
/// straight back with `E_RELEASE_NOT_FOUND`, and it costs one local git call to
/// say so first. A warning, never an error: the tag may live only on the remote.
fn warn_if_tag_is_missing(dir: &Path, tag: &str) {
    let root = repo_root(dir).unwrap_or_else(|| dir.to_path_buf());
    let out = Command::new("git")
        .arg("-C")
        .arg(&root)
        .args(["tag", "--list", tag])
        .output();
    if let Ok(o) = out
        && o.status.success()
        && String::from_utf8_lossy(&o.stdout).trim().is_empty()
    {
        hprintln!(
            "  Note: this checkout has no tag `{tag}`. The registry reads the release, so the tag \
             has to exist and be pushed, with the .astraplugin assets attached by CI.\n"
        );
    }
}

// ── plumbing ────────────────────────────────────────────────────────────────

/// Bundles for this exact id and version, next to the plugin or under `dist/`.
fn find_bundles(dir: &Path, id: &str, version: &str) -> Vec<PathBuf> {
    let prefix = format!("{id}-{version}-");
    let mut out = Vec::new();
    for base in [dir.to_path_buf(), dir.join("dist"), dir.join("target")] {
        let Ok(entries) = std::fs::read_dir(&base) else {
            continue;
        };
        for e in entries.flatten() {
            let name = e.file_name().to_string_lossy().to_string();
            if name.starts_with(&prefix) && name.ends_with(".astraplugin") {
                out.push(e.path());
            }
        }
    }
    out.sort();
    out
}

fn open_in_browser(url: &str) -> Result<()> {
    #[cfg(target_os = "windows")]
    let mut cmd = {
        let mut c = Command::new("cmd");
        c.args(["/C", "start", ""]).arg(url);
        c
    };
    #[cfg(target_os = "macos")]
    let mut cmd = {
        let mut c = Command::new("open");
        c.arg(url);
        c
    };
    #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
    let mut cmd = {
        let mut c = Command::new("xdg-open");
        c.arg(url);
        c
    };

    let status = cmd
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .context("no browser opener on PATH")?;
    if !status.success() {
        anyhow::bail!("the browser opener exited {status}");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_github_remote_shape_is_one_repository() {
        for url in [
            "git@github.com:you/dice-roller.git",
            "ssh://git@github.com/you/dice-roller.git",
            "https://github.com/you/dice-roller.git",
            "https://github.com/you/dice-roller",
            "https://github.com/you/dice-roller/",
        ] {
            assert_eq!(
                parse_remote(url).as_deref(),
                Some("you/dice-roller"),
                "{url}"
            );
        }
    }

    #[test]
    fn a_remote_that_is_not_github_is_not_guessed_at() {
        // The registry lists GitHub repositories. Inventing an `owner/name` out
        // of a GitLab URL would produce a submission that fails at the far end
        // with a message about a repository that does not exist.
        assert_eq!(parse_remote("https://gitlab.com/you/thing.git"), None);
        assert_eq!(parse_remote(""), None);
        assert_eq!(parse_remote("https://github.com/you"), None);
        assert_eq!(parse_remote("https://github.com/you/thing/extra"), None);
    }

    #[test]
    fn a_pasted_address_bar_is_a_repository() {
        assert_eq!(normalise_repo("@you/thing/").as_deref(), Some("you/thing"));
        assert_eq!(
            normalise_repo("you/thing.git").as_deref(),
            Some("you/thing")
        );
        assert_eq!(normalise_repo("you/thing evil").as_deref(), None);
    }

    /// FLOW-45 and AP-15's URL test: what `publish` opens is the page
    /// `spec/panel.yaml` declares — its address, and every query parameter
    /// it names, in order, each filled. Read from the spec file at test time,
    /// not from the vendored copy the binary embeds, so the two cannot agree
    /// with each other and disagree with the spec.
    #[test]
    fn publish_opens_the_page_spec_panel_yaml_declares() {
        let spec = std::fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../spec/panel.yaml"),
        )
        .expect("spec/panel.yaml");
        let url_line = spec
            .lines()
            .find_map(|l| l.strip_prefix("url: "))
            .expect("spec/panel.yaml has a url");
        let names: Vec<&str> = spec
            .lines()
            .skip_while(|l| !l.starts_with("query:"))
            .skip(1)
            .take_while(|l| l.starts_with("  - "))
            .map(|l| l.trim_start_matches("  - ").trim())
            .collect();
        assert_eq!(names, ["repo", "tag"]);

        let got = crate::panel::submission_url("you/dice-roller", "v0.1.0").unwrap();
        let (address, query) = got.split_once('?').expect("the link carries a query");
        assert_eq!(address, url_line);
        let params: Vec<(&str, &str)> = query
            .split('&')
            .map(|kv| kv.split_once('=').expect("name=value"))
            .collect();
        assert_eq!(
            params.iter().map(|(k, _)| *k).collect::<Vec<_>>(),
            names,
            "every parameter the page declares, in its order"
        );
        assert_eq!(params, [("repo", "you/dice-roller"), ("tag", "v0.1.0")]);
        assert!(
            !got.contains("github.com") && !got.contains("template="),
            "the submission link still reaches a GitHub issue form: {got}"
        );
    }

    /// FLOW-48, and the login line gone with the issue form (AP-15).
    #[test]
    fn the_dry_run_names_what_only_the_registry_can_check() {
        let all = REGISTRY_ONLY_CHECKS.join("\n");
        for code in [
            "B_BINDING_UNUSABLE",
            "B_ACCOUNT_INELIGIBLE",
            "B_OWNER_CHANGED",
            "B_REPOSITORY_RECYCLED",
            "E_WORKFLOW_NOT_ALLOWED",
        ] {
            assert!(all.contains(code), "{code} is not named");
        }
        assert!(
            !all.contains("names the account opening"),
            "the owner-file login check belonged to the issue form, which is gone"
        );
    }

}
