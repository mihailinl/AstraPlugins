//! `astra-plugin version <semver>` — set the version everywhere it is written,
//! in one edit, and print the commands that turn it into a release.
//!
//! A plugin carries its version in two to four places: `plugin.toml`, the
//! language's own manifest (`Cargo.toml` / `package.json` / `pyproject.toml`),
//! and often a `__version__` in Python source. They drift the moment a human
//! is responsible for keeping them equal, and the drift is invisible until CI
//! rejects a tag — or worse, does not, and the registry records a bundle whose
//! `plugin.toml` says one thing and whose package metadata says another.
//!
//! Two properties this command must have:
//!
//! * **All or nothing.** Every rewrite is computed in memory first; the first
//!   file is written only once the last one is known. A partial bump is
//!   exactly the state this command exists to prevent.
//! * **Surgical.** `toml_edit` and a byte-level JSON edit, never a
//!   parse-and-reserialize. A `package.json` round-tripped through a map loses
//!   its key order, and a `Cargo.toml` loses every comment the author wrote.

use std::cmp::Ordering;
use std::fmt;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use walkdir::WalkDir;

use crate::commands::init_ci;

/// Directories that never hold a version this command should touch — the same
/// list `build` excludes, for the same reason, plus the two output directories
/// where a stale copy of the old version is expected to sit.
const EXCLUDED_DIRS: &[&str] = &[
    "target",
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
];

/// The tables a `version` may live in, per language manifest.
const CARGO_TABLES: &[&[&str]] = &[&["package"]];
const PYPROJECT_TABLES: &[&[&str]] = &[&["project"], &["tool", "poetry"]];

// ── semver ──────────────────────────────────────────────────────────────────

/// A parsed semver — enough of one to compare, and to reject a typo.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Semver {
    pub major: u64,
    pub minor: u64,
    pub patch: u64,
    /// Dot-separated pre-release identifiers; empty for a release.
    pub pre: Vec<String>,
    pub build: String,
}

impl fmt::Display for Semver {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{}.{}", self.major, self.minor, self.patch)?;
        if !self.pre.is_empty() {
            write!(f, "-{}", self.pre.join("."))?;
        }
        if !self.build.is_empty() {
            write!(f, "+{}", self.build)?;
        }
        Ok(())
    }
}

impl PartialOrd for Semver {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Semver {
    fn cmp(&self, other: &Self) -> Ordering {
        // Build metadata is explicitly NOT part of precedence (semver §10).
        (self.major, self.minor, self.patch)
            .cmp(&(other.major, other.minor, other.patch))
            .then_with(|| match (self.pre.is_empty(), other.pre.is_empty()) {
                // A pre-release sorts BELOW its release (semver §11).
                (true, false) => Ordering::Greater,
                (false, true) => Ordering::Less,
                _ => compare_pre(&self.pre, &other.pre),
            })
    }
}

fn compare_pre(a: &[String], b: &[String]) -> Ordering {
    for (x, y) in a.iter().zip(b) {
        let ord = match (x.parse::<u64>(), y.parse::<u64>()) {
            (Ok(nx), Ok(ny)) => nx.cmp(&ny),
            // Numeric identifiers have lower precedence than alphanumeric ones.
            (Ok(_), Err(_)) => Ordering::Less,
            (Err(_), Ok(_)) => Ordering::Greater,
            (Err(_), Err(_)) => x.as_str().cmp(y.as_str()),
        };
        if ord != Ordering::Equal {
            return ord;
        }
    }
    a.len().cmp(&b.len())
}

/// Strict semver, by hand — the CLI has no `semver` dependency and this is the
/// one place it would need one.
///
/// Strict on purpose. `1.2` and `v1.2.3` both parse under a lenient reader and
/// both break something downstream: the release workflow asserts the tag is
/// exactly `v<version>`, and the daemon's update check parses both sides with a
/// real semver implementation that rejects them.
pub fn parse_semver(s: &str) -> Result<Semver> {
    if s.is_empty() {
        anyhow::bail!("version is empty");
    }
    if let Some(rest) = s.strip_prefix('v')
        && rest.starts_with(|c: char| c.is_ascii_digit())
    {
        anyhow::bail!(
            "'{s}' has a leading 'v'. The manifest carries '{rest}'; the git TAG carries the 'v'."
        );
    }

    let (core, build) = match s.split_once('+') {
        Some((c, b)) => {
            if b.is_empty() || !b.split('.').all(is_build_ident) {
                anyhow::bail!("'{s}': build metadata after '+' must be dot-separated [0-9A-Za-z-]");
            }
            (c, b.to_string())
        }
        None => (s, String::new()),
    };

    let (nums, pre) = match core.split_once('-') {
        Some((n, p)) => {
            let ids: Vec<String> = p.split('.').map(str::to_string).collect();
            if ids.iter().any(|i| !is_pre_ident(i)) {
                anyhow::bail!(
                    "'{s}': pre-release identifiers must be [0-9A-Za-z-], and numeric ones may \
                     not have leading zeros"
                );
            }
            (n, ids)
        }
        None => (core, Vec::new()),
    };

    let parts: Vec<&str> = nums.split('.').collect();
    if parts.len() != 3 {
        anyhow::bail!(
            "'{s}' is not semver: it needs exactly three numbers, e.g. 1.2.3 (got {})",
            parts.len()
        );
    }
    let mut n = [0u64; 3];
    for (i, p) in parts.iter().enumerate() {
        if p.is_empty() || !p.bytes().all(|b| b.is_ascii_digit()) {
            anyhow::bail!("'{s}' is not semver: '{p}' is not a number");
        }
        if p.len() > 1 && p.starts_with('0') {
            anyhow::bail!("'{s}' is not semver: '{p}' has a leading zero");
        }
        n[i] = p
            .parse()
            .with_context(|| format!("'{p}' does not fit in a u64"))?;
    }

    Ok(Semver {
        major: n[0],
        minor: n[1],
        patch: n[2],
        pre,
        build,
    })
}

fn is_pre_ident(i: &str) -> bool {
    if i.is_empty() || !i.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-') {
        return false;
    }
    let numeric = i.bytes().all(|b| b.is_ascii_digit());
    !(numeric && i.len() > 1 && i.starts_with('0'))
}

fn is_build_ident(i: &str) -> bool {
    !i.is_empty() && i.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
}

// ── the command ─────────────────────────────────────────────────────────────

/// One planned rewrite. Nothing touches the disk until every one exists.
struct Edit {
    path: PathBuf,
    content: String,
    /// What changed, for the report — `[plugin] version`, `"version"`, …
    what: String,
    from: String,
}

pub struct VersionOptions<'a> {
    pub path: &'a str,
    pub version: &'a str,
    /// Permit a version that sorts below the current one.
    pub allow_downgrade: bool,
}

pub fn run(opts: VersionOptions<'_>) -> Result<()> {
    let dir = Path::new(opts.path)
        .canonicalize()
        .with_context(|| format!("Invalid path: {}", opts.path))?;

    let new = parse_semver(opts.version)?;
    let new_s = new.to_string();

    let manifest_path = dir.join("plugin.toml");
    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml at {}", manifest_path.display());
    }

    let mut edits: Vec<Edit> = Vec::new();

    // ── plugin.toml, the authority ──────────────────────────────────────────
    let manifest_src = std::fs::read_to_string(&manifest_path)
        .with_context(|| format!("Failed to read {}", manifest_path.display()))?;
    let mut doc: toml_edit::DocumentMut = manifest_src
        .parse()
        .with_context(|| format!("{} is not valid TOML", manifest_path.display()))?;
    let current = doc
        .get("plugin")
        .and_then(|p| p.get("version"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    // A downgrade is nearly always a typo, and the one that is not is a
    // deliberate act that can say so. The daemon refuses to install a lower
    // version over a higher one, so shipping one produces a release nobody can
    // install, and no error anywhere that names the reason.
    if !opts.allow_downgrade
        && let Ok(cur) = parse_semver(&current)
        && new < cur
    {
        anyhow::bail!(
            "{new_s} is lower than the current {current}. Astra refuses to install a downgrade, \
             so this release would be uninstallable. Pass --allow-downgrade if you mean it."
        );
    }

    if doc.get("plugin").is_none() {
        anyhow::bail!("{} has no [plugin] table", manifest_path.display());
    }
    set_version(&mut doc["plugin"], &new_s);
    edits.push(Edit {
        path: manifest_path.clone(),
        content: doc.to_string(),
        what: "[plugin] version".into(),
        from: current.clone(),
    });

    // ── the language's own manifest ─────────────────────────────────────────
    if let Some(e) = toml_versions(&dir.join("Cargo.toml"), CARGO_TABLES, &new_s)? {
        edits.push(e);
    }
    if let Some(e) = json_top_level_version(&dir.join("package.json"), &new_s)? {
        edits.push(e);
    }
    if let Some(e) = toml_versions(&dir.join("pyproject.toml"), PYPROJECT_TABLES, &new_s)? {
        edits.push(e);
    }

    // ── every `__version__` in the tree ─────────────────────────────────────
    edits.extend(dunder_version_edits(&dir, &new_s)?);

    // ── commit, all at once ─────────────────────────────────────────────────
    println!(
        "Setting version to {new_s} (plugin.toml was {})",
        if current.is_empty() {
            "unset"
        } else {
            &current
        }
    );
    for e in &edits {
        std::fs::write(&e.path, &e.content)
            .with_context(|| format!("Failed to write {}", e.path.display()))?;
        let shown = e.path.strip_prefix(&dir).unwrap_or(&e.path);
        println!(
            "  {:<30} {:<26} {} -> {new_s}",
            shown.display().to_string(),
            e.what,
            if e.from.is_empty() {
                "(unset)"
            } else {
                &e.from
            }
        );
    }
    println!("  {} file(s) rewritten", edits.len());

    // The tag this plugin's own caller workflow will accept, which in a
    // monorepo is `<id>-v<version>` and not `v<version>`. Printing the wrong
    // one here is how an author ends up pushing a tag that starts every other
    // plugin's release and none of their own.
    let prefix = init_ci::tag_prefix_for(&dir);

    println!();
    println!("Release it:");
    println!("  git commit -am \"release {new_s}\"");
    println!("  git tag {prefix}{new_s}");
    println!("  git push && git push --tags");
    println!();
    println!(
        "  The tag must be exactly '{prefix}{new_s}': the release workflow asserts it\n  \
         against plugin.toml before it builds anything."
    );

    Ok(())
}

/// Every version this plugin declares outside `plugin.toml`, as
/// `(file, what, version)`.
///
/// `astra-plugin check` compares these against `plugin.toml`. A mismatch is a
/// release that fails at the tag assertion in CI — or, if the author tags the
/// other file's number, one that succeeds and publishes a bundle whose package
/// metadata disagrees with its manifest. Catching it locally costs nothing.
pub fn declared_versions(dir: &Path) -> Vec<(String, String, String)> {
    let mut out = Vec::new();

    for (file, tables) in [
        ("Cargo.toml", CARGO_TABLES),
        ("pyproject.toml", PYPROJECT_TABLES),
    ] {
        let path = dir.join(file);
        let Ok(src) = std::fs::read_to_string(&path) else {
            continue;
        };
        let Ok(doc) = src.parse::<toml_edit::DocumentMut>() else {
            continue;
        };
        for table in tables {
            let mut node = doc.as_item();
            let mut ok = true;
            for key in *table {
                match node.get(key) {
                    Some(next) => node = next,
                    None => {
                        ok = false;
                        break;
                    }
                }
            }
            if !ok {
                continue;
            }
            if let Some(v) = node.get("version").and_then(|v| v.as_str()) {
                out.push((
                    file.to_string(),
                    format!("[{}] version", table.join(".")),
                    v.to_string(),
                ));
            }
        }
    }

    if let Ok(src) = std::fs::read_to_string(dir.join("package.json"))
        && let Some((_, v)) = find_top_level_string_value(&src, "version")
    {
        out.push(("package.json".into(), "\"version\"".into(), v));
    }

    out
}

/// Set `version` inside each of `tables` that exists and already carries a
/// string one, in a single pass over one document.
///
/// "Already carries a string one" is the condition that matters: a `Cargo.toml`
/// whose `[package] version` is `{ workspace = true }` must not be rewritten
/// into a literal, and a `pyproject.toml` with no `[project]` table at all is a
/// `setup.py` project this command has no business editing.
fn toml_versions(path: &Path, tables: &[&[&str]], new: &str) -> Result<Option<Edit>> {
    if !path.is_file() {
        return Ok(None);
    }
    let src = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read {}", path.display()))?;
    let mut doc: toml_edit::DocumentMut = src
        .parse()
        .with_context(|| format!("{} is not valid TOML", path.display()))?;

    let mut touched: Vec<String> = Vec::new();
    let mut from = String::new();

    for table in tables {
        // Read first: `get_mut` on a missing key would create nothing, but the
        // borrow makes the "does it exist and is it a string" test awkward to
        // express in one pass.
        let existing = {
            let mut node = doc.as_item();
            let mut ok = true;
            for key in *table {
                match node.get(key) {
                    Some(next) => node = next,
                    None => {
                        ok = false;
                        break;
                    }
                }
            }
            if ok {
                node.get("version")
                    .and_then(|v| v.as_str())
                    .map(str::to_string)
            } else {
                None
            }
        };
        let Some(old) = existing else { continue };

        let mut node = doc.as_item_mut();
        for key in *table {
            node = node.get_mut(key).expect("resolved immediately above");
        }
        set_version(node, new);

        if from.is_empty() {
            from = old;
        }
        touched.push(format!("[{}] version", table.join(".")));
    }

    if touched.is_empty() {
        return Ok(None);
    }
    Ok(Some(Edit {
        path: path.to_path_buf(),
        content: doc.to_string(),
        what: touched.join(" + "),
        from,
    }))
}

/// Replace `table.version` while keeping its decor.
///
/// `toml_edit::value(x)` builds a fresh value with default decor, which drops
/// the whitespace and the *trailing comment* attached to the old one — so
/// `version = "0.9.0"   # pinned for the 1.x line` would come back as
/// `version = "1.0.0"`, quietly deleting a sentence the author wrote. Cloning
/// the decor across is the difference between a surgical edit and a lossy one.
fn set_version(table: &mut toml_edit::Item, new: &str) {
    match table.get_mut("version").and_then(|i| i.as_value_mut()) {
        Some(v) => {
            let decor = v.decor().clone();
            *v = toml_edit::Value::from(new);
            *v.decor_mut() = decor;
        }
        None => table["version"] = toml_edit::value(new),
    }
}

/// Rewrite the *top-level* `"version"` of a `package.json`, byte for byte.
///
/// Depth matters: `"version"` also appears inside `dependencies`, inside
/// `engines`, and inside anything an author nested. A regex on the first match
/// would eventually rewrite the wrong one, and the bug would be a published
/// package whose manifest disagrees with its bundle.
fn json_top_level_version(path: &Path, new: &str) -> Result<Option<Edit>> {
    if !path.is_file() {
        return Ok(None);
    }
    let src = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read {}", path.display()))?;

    let Some((span, from)) = find_top_level_string_value(&src, "version") else {
        return Ok(None);
    };
    let mut content = String::with_capacity(src.len() + new.len());
    content.push_str(&src[..span.0]);
    content.push_str(new);
    content.push_str(&src[span.1..]);

    Ok(Some(Edit {
        path: path.to_path_buf(),
        content,
        what: "\"version\"".into(),
        from,
    }))
}

/// Byte range of the *contents* of the string value of a depth-1 key, and the
/// old value. `None` when the key is absent or is not a plain string.
fn find_top_level_string_value(src: &str, key: &str) -> Option<((usize, usize), String)> {
    let b = src.as_bytes();
    let mut depth: i32 = 0;
    let mut i = 0usize;

    while i < b.len() {
        match b[i] {
            b'{' | b'[' => {
                depth += 1;
                i += 1;
            }
            b'}' | b']' => {
                depth -= 1;
                i += 1;
            }
            b'"' => {
                let (text, end) = scan_json_string(b, i)?;
                // A key sits at depth 1 and is followed by a colon.
                let mut j = end;
                while j < b.len() && b[j].is_ascii_whitespace() {
                    j += 1;
                }
                if depth == 1 && text == key && j < b.len() && b[j] == b':' {
                    j += 1;
                    while j < b.len() && b[j].is_ascii_whitespace() {
                        j += 1;
                    }
                    if j < b.len() && b[j] == b'"' {
                        let (value, vend) = scan_json_string(b, j)?;
                        return Some(((j + 1, vend - 1), value));
                    }
                    return None;
                }
                i = end;
            }
            _ => i += 1,
        }
    }
    None
}

/// Reads the JSON string starting at `start` (the opening quote). Returns its
/// contents and the index just past the closing quote.
fn scan_json_string(b: &[u8], start: usize) -> Option<(String, usize)> {
    let mut i = start + 1;
    let mut out = String::new();
    while i < b.len() {
        match b[i] {
            b'\\' => {
                // Good enough for a key name and a semver: the only thing that
                // matters is not mistaking an escaped quote for the end.
                if i + 1 < b.len() {
                    out.push(b[i + 1] as char);
                }
                i += 2;
            }
            b'"' => return Some((out, i + 1)),
            c => {
                out.push(c as char);
                i += 1;
            }
        }
    }
    None
}

/// Every `__version__ = "…"` in the tree.
fn dunder_version_edits(dir: &Path, new: &str) -> Result<Vec<Edit>> {
    let mut out = Vec::new();
    let walk = WalkDir::new(dir)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|e| {
            !e.file_type().is_dir()
                || e.path() == dir
                || !EXCLUDED_DIRS.contains(&e.file_name().to_string_lossy().as_ref())
        });

    for entry in walk {
        let entry = entry.context("Failed to walk the plugin directory")?;
        if !entry.file_type().is_file() {
            continue;
        }
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("py") {
            continue;
        }
        let Ok(src) = std::fs::read_to_string(path) else {
            continue;
        };
        let Some((content, from)) = rewrite_dunder_version(&src, new) else {
            continue;
        };
        out.push(Edit {
            path: path.to_path_buf(),
            content,
            what: "__version__".into(),
            from,
        });
    }
    Ok(out)
}

/// Rewrite every `__version__ = "…"`; `None` if the file has none.
fn rewrite_dunder_version(src: &str, new: &str) -> Option<(String, String)> {
    let mut from: Option<String> = None;
    let mut out = String::with_capacity(src.len());

    for line in src.split_inclusive('\n') {
        // Preserve the file's own line ending rather than normalising it: a
        // CRLF file rewritten with LF is a whole-file diff for one word.
        let (body, eol) = match line.strip_suffix('\n') {
            Some(b) => match b.strip_suffix('\r') {
                Some(b2) => (b2, "\r\n"),
                None => (b, "\n"),
            },
            None => (line, ""),
        };
        match split_dunder(body) {
            Some((prefix, value)) => {
                from.get_or_insert_with(|| value.to_string());
                out.push_str(prefix);
                out.push('"');
                out.push_str(new);
                out.push('"');
                out.push_str(eol);
            }
            None => out.push_str(line),
        }
    }
    from.map(|f| (out, f))
}

/// `("__version__ = ", "0.1.0")` for a line that assigns a quoted literal.
fn split_dunder(line: &str) -> Option<(&str, &str)> {
    let trimmed = line.trim_start();
    let rest = trimmed.strip_prefix("__version__")?;
    let after_eq = rest.trim_start().strip_prefix('=')?;
    let value_part = after_eq.trim_start();
    let quote = value_part.chars().next()?;
    if quote != '"' && quote != '\'' {
        return None;
    }
    let body = &value_part[1..];
    let end = body.find(quote)?;
    // Only a bare literal: `__version__ = get_version()` or a concatenation is
    // somebody's code, not a constant to rewrite.
    if !body[end + 1..].trim().is_empty() {
        return None;
    }
    let prefix_len = line.len() - value_part.len();
    Some((&line[..prefix_len], &body[..end]))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strict_semver_accepts_and_rejects() {
        assert!(parse_semver("1.2.3").is_ok());
        assert!(parse_semver("0.0.0").is_ok());
        assert!(parse_semver("1.2.3-rc.1").is_ok());
        assert!(parse_semver("1.2.3-rc.1+build.5").is_ok());

        for bad in ["1.2", "1.2.3.4", "v1.2.3", "01.2.3", "1.2.3-", "", "1.2.x"] {
            assert!(parse_semver(bad).is_err(), "{bad} should be rejected");
        }
    }

    #[test]
    fn a_prerelease_sorts_below_its_release() {
        assert!(parse_semver("1.0.0-rc.1").unwrap() < parse_semver("1.0.0").unwrap());
        assert!(parse_semver("1.0.0-alpha").unwrap() < parse_semver("1.0.0-beta").unwrap());
        assert!(parse_semver("1.0.0-1").unwrap() < parse_semver("1.0.0-alpha").unwrap());
        // The bug this exists for: string comparison puts 0.10.0 below 0.9.0.
        assert!(parse_semver("0.10.0").unwrap() > parse_semver("0.9.0").unwrap());
    }

    /// Build metadata is not part of precedence, so two versions differing only
    /// in it compare equal — not "newer", which would let a rebuild masquerade
    /// as an update.
    #[test]
    fn build_metadata_does_not_affect_precedence() {
        assert_eq!(
            parse_semver("1.0.0+a")
                .unwrap()
                .cmp(&parse_semver("1.0.0+b").unwrap()),
            Ordering::Equal
        );
    }

    #[test]
    fn json_edit_takes_the_top_level_version_only() {
        let src = r#"{
  "name": "dice-roller",
  "version": "0.1.0",
  "dependencies": {
    "left-pad": "1.0.0",
    "version": "9.9.9"
  }
}"#;
        let (span, from) = find_top_level_string_value(src, "version").unwrap();
        assert_eq!(from, "0.1.0");
        assert_eq!(&src[span.0..span.1], "0.1.0");
    }

    /// A nested `"version"` must not be found when the top-level one is absent:
    /// silently bumping a dependency's range is far worse than doing nothing.
    #[test]
    fn json_edit_ignores_a_nested_version_when_there_is_no_top_level_one() {
        let src = r#"{ "dependencies": { "version": "9.9.9" } }"#;
        assert!(find_top_level_string_value(src, "version").is_none());
    }

    #[test]
    fn dunder_version_is_rewritten_in_place() {
        let src = "\"\"\"doc\"\"\"\n\n__version__ = \"0.1.0\"\n\nX = 1\n";
        let (out, from) = rewrite_dunder_version(src, "1.2.3").unwrap();
        assert_eq!(from, "0.1.0");
        assert_eq!(out, "\"\"\"doc\"\"\"\n\n__version__ = \"1.2.3\"\n\nX = 1\n");
    }

    #[test]
    fn a_computed_dunder_version_is_left_alone() {
        assert!(rewrite_dunder_version("__version__ = get_version()\n", "1.2.3").is_none());
        assert!(rewrite_dunder_version("__version__ = \"a\" + b\n", "1.2.3").is_none());
    }

    #[test]
    fn crlf_survives() {
        let src = "__version__ = '0.1.0'\r\nX = 1\r\n";
        let (out, _) = rewrite_dunder_version(src, "2.0.0").unwrap();
        assert_eq!(out, "__version__ = \"2.0.0\"\r\nX = 1\r\n");
    }

    #[test]
    fn a_workspace_inherited_cargo_version_is_left_alone() {
        let dir = std::env::temp_dir().join(format!("astra-ver-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("Cargo.toml");
        std::fs::write(&p, "[package]\nname = \"x\"\nversion.workspace = true\n").unwrap();
        assert!(toml_versions(&p, CARGO_TABLES, "1.2.3").unwrap().is_none());
        std::fs::remove_dir_all(&dir).ok();
    }
}
