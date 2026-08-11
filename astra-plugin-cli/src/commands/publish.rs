//! `astra-plugin publish` — get a release into the Astra registry.
//!
//! Three things, and it is worth being precise about which is which, because
//! the word "publish" does more work in most tools than it does here:
//!
//! * `--dry-run` runs **locally** every check the registry bot runs that can be
//!   run locally, and then names the ones only the registry can run. It uploads
//!   nothing and needs no network.
//! * with no flags it prints (and offers to open) a prefilled **listing
//!   request** — the one-time submission that gets a plugin into the catalogue
//!   at all.
//! * `--notify` prints a prefilled **release ping** for a plugin that is already
//!   listed: PRODUCTION_PLAN task 3.4's manual escape hatch, for when the
//!   registry has not noticed a release by itself.
//!
//! **This command never uploads a bundle and never holds a credential.** The
//! artifacts are GitHub Release assets your CI attached and attested; the
//! registry reads them from your repository and verifies every one from
//! scratch. So all a notification carries is `owner/repo` and a tag, which is
//! exactly why it can be a URL you open in a browser you are already signed in
//! to, rather than a token this program would have to be trusted with.
//!
//! What the registry does with it afterwards — published immediately, delayed
//! 24 hours, or held for a person — is `docs/POLICY.md` in the registry
//! repository, and the bot says which on the issue.

use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result};
use astra_plugin_manifest::PluginManifest;

use crate::commands::init_ci::{repo_root, tag_prefix_for};
use crate::hprintln;

/// Where listing requests and release pings go.
pub const REGISTRY_REPO: &str = "mihailinl/astra-registry";

/// The issue template a first listing uses.
pub const LISTING_TEMPLATE: &str = "plugin-listing.yml";

pub struct PublishOptions<'a> {
    pub path: &'a str,
    /// `owner/name`. Default: parsed from the `origin` remote.
    pub repo: Option<&'a str>,
    /// The release tag. Default: the plugin's tag prefix + its version.
    pub tag: Option<&'a str>,
    /// Run the local half of the registry's checks and stop.
    pub dry_run: bool,
    /// A release ping for a plugin that is already listed, rather than a first
    /// listing request.
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

    let (what, url) = if opts.notify {
        (
            "release ping",
            format!(
                "https://github.com/{REGISTRY_REPO}/issues/new?title={}&body={}",
                encode(&format!("[release] {repo} {tag}")),
                encode(&release_ping_body(&repo, &tag, &id, &version)),
            ),
        )
    } else {
        (
            "listing request",
            format!(
                "https://github.com/{REGISTRY_REPO}/issues/new?template={LISTING_TEMPLATE}\
                 &title={}&repository={}&release_tag={}",
                encode(&format!("[listing] {repo}")),
                encode(&repo),
                encode(&tag),
            ),
        )
    };

    hprintln!("{id} {version} — {what} for {repo}@{tag}\n");
    warn_if_tag_is_missing(&dir, &tag);
    if opts.notify {
        hprintln!(
            "  The registry usually notices a release by itself, within minutes. Use this when it\n\
             \x20 has not: it carries your repository and the tag, and nothing else. The bot then\n\
             \x20 re-verifies the release from scratch, which is why the link needs no token.\n"
        );
    } else {
        hprintln!(
            "  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI\n\
             \x20 build and attest, and the registry picks it up. Everything on the store card —\n\
             \x20 name, summary, licence, capabilities, permissions, digests — is read out of the\n\
             \x20 attested bundle, so there is nothing else to fill in and nothing to keep in sync.\n"
        );
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
    crate::commands::validate::run_with(&dir.to_string_lossy(), true, false)?;

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
const REGISTRY_ONLY_CHECKS: &[&str] = &[
    "the build attestation, and that it was produced by the pinned Astra release workflow \
     (a hand-built bundle is refused however good it is)",
    "that the release assets are served from your repository's own release namespace",
    "that you have admin or maintain on the repository",
    "that the id and display name do not collide with a listed plugin",
    "that the licence is on the registry's SPDX allowlist",
    "that the version is strictly newer than the listed one",
    "the declared-vs-called host RPC scan",
];

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

// ── the ping ────────────────────────────────────────────────────────────────

/// The body of a release ping.
///
/// The first line is the machine-readable part and has to be exactly that: the
/// registry's `bot/triage.mjs` reads `/release <owner/repo> <tag>` from the
/// first line and nothing else, so a sentence above it turns the ping into an
/// ordinary issue nobody acts on.
pub fn release_ping_body(repo: &str, tag: &str, id: &str, version: &str) -> String {
    format!(
        "/release {repo} {tag}\n\
         \n\
         `{id}` {version} is released and the registry has not picked it up yet.\n\
         \n\
         This carries the repository and the tag and nothing else — every check runs again from \
         scratch against the release itself, so nothing here is trusted. Sent by \
         `astra-plugin publish --notify`.\n"
    )
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

/// Percent-encode for a query-string value.
///
/// Written out rather than pulled in: this CLI has no URL dependency, the rule
/// is four lines, and the alternative — pasting a tag into a URL unencoded — is
/// how a plugin named with a `#` in its version silently submits half a form.
pub fn encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 16);
    for b in s.as_bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(*b as char);
            }
            b' ' => out.push('+'),
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
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

    #[test]
    fn the_ping_is_machine_readable_on_its_first_line() {
        let body = release_ping_body("you/dice-roller", "v0.2.0", "dice-roller", "0.2.0");
        assert_eq!(
            body.lines().next().unwrap(),
            "/release you/dice-roller v0.2.0",
            "the registry reads the first line and nothing else",
        );
    }

    #[test]
    fn a_query_value_survives_a_round_trip() {
        assert_eq!(encode("[listing] you/thing"), "%5Blisting%5D+you%2Fthing");
        assert_eq!(encode("v1.0.0-rc.1+build"), "v1.0.0-rc.1%2Bbuild");
        assert_eq!(encode("plain"), "plain");
    }
}
