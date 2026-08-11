//! `astra-plugin doctor` — answer, in one command, every question an author
//! asks when a plugin will not start.
//!
//! # Scope
//!
//! Each check is phrased as the **question** it answers, not as a label, and
//! carries the fix. That is not styling: the questions are the table of
//! contents of the troubleshooting guide, and the guide is generated from
//! `astra-plugin doctor --json` (`ids` are stable, so a section can be linked
//! to). A question that stops being answerable here has to be deleted from both
//! places at once, which is the property that keeps the guide honest.
//!
//! Two halves, and `doctor` runs whichever apply:
//!
//! * **environment** — the toolchains, the daemon, the config directory. Runs
//!   anywhere, including outside a plugin project.
//! * **project** — the manifest, the entry point, the platform block, the
//!   release workflow. Runs when there is a `plugin.toml` to read.
//!
//! # Severity
//!
//! `fail` is *this is why it does not work*; `warn` is *this will bite*; `ok`
//! is an answer worth printing anyway, because half the value of a diagnostic
//! is telling you which things you can stop suspecting. Only `fail` sets the
//! exit code, and it sets it to 1 — the artefact/environment is wrong, the tool
//! worked.

use std::path::{Path, PathBuf};

use anyhow::Result;
use serde_json::{Value, json};

use crate::hprintln;
use crate::output::{Rejected, Verdict};
use crate::toolchain;

pub struct DoctorOptions<'a> {
    /// Plugin directory to inspect. Project checks are skipped when it holds no
    /// `plugin.toml`.
    pub path: &'a str,
    /// Daemon address to probe. Default: the same resolution `dev` uses.
    pub daemon_addr: Option<&'a str>,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Level {
    Ok,
    Warn,
    Fail,
}

impl Level {
    fn as_str(self) -> &'static str {
        match self {
            Level::Ok => "ok",
            Level::Warn => "warn",
            Level::Fail => "fail",
        }
    }
    fn mark(self) -> &'static str {
        match self {
            Level::Ok => "ok  ",
            Level::Warn => "warn",
            Level::Fail => "FAIL",
        }
    }
}

struct Finding {
    /// Stable id. The troubleshooting guide links to it; do not renumber.
    id: &'static str,
    question: &'static str,
    level: Level,
    answer: String,
    /// What to do about it. Empty when the answer is `ok`.
    fix: String,
}

impl Finding {
    fn ok(id: &'static str, question: &'static str, answer: impl Into<String>) -> Self {
        Self { id, question, level: Level::Ok, answer: answer.into(), fix: String::new() }
    }
    fn warn(
        id: &'static str,
        question: &'static str,
        answer: impl Into<String>,
        fix: impl Into<String>,
    ) -> Self {
        Self { id, question, level: Level::Warn, answer: answer.into(), fix: fix.into() }
    }
    fn fail(
        id: &'static str,
        question: &'static str,
        answer: impl Into<String>,
        fix: impl Into<String>,
    ) -> Self {
        Self { id, question, level: Level::Fail, answer: answer.into(), fix: fix.into() }
    }
}

pub async fn run(opts: DoctorOptions<'_>) -> Result<Verdict> {
    let dir = PathBuf::from(opts.path);
    let mut findings = Vec::new();

    findings.push(cli_version());
    findings.push(rust_log());
    findings.extend(config_dir());
    findings.push(daemon(opts.daemon_addr).await);

    let language = crate::commands::build::detect_language(&dir);
    findings.extend(toolchains(&language));

    let manifest_path = dir.join("plugin.toml");
    if manifest_path.exists() {
        findings.extend(project(&dir, &manifest_path));
    } else {
        findings.push(Finding::ok(
            "project.absent",
            "Is there a plugin project here?",
            format!(
                "no plugin.toml at {} — project checks skipped",
                manifest_path.display()
            ),
        ));
    }

    let failures = findings.iter().filter(|f| f.level == Level::Fail).count();
    let warnings = findings.iter().filter(|f| f.level == Level::Warn).count();
    let verdict = Verdict::of(failures == 0);

    for f in &findings {
        hprintln!("  [{}] {}", f.level.mark(), f.question);
        hprintln!("         {}", f.answer);
        if !f.fix.is_empty() {
            hprintln!("         fix: {}", f.fix);
        }
    }
    hprintln!();
    hprintln!(
        "  {} check(s): {} failing, {} warning(s).",
        findings.len(),
        failures,
        warnings
    );

    crate::output::emit(
        "doctor",
        &verdict,
        json!({
            "checks": findings.iter().map(|f| json!({
                "id": f.id,
                "question": f.question,
                "level": f.level.as_str(),
                "answer": f.answer,
                "fix": f.fix,
            })).collect::<Vec<Value>>(),
            "failing": failures,
            "warnings": warnings,
        }),
    );

    if verdict == Verdict::Fail && !crate::output::json_mode() {
        return Err(Rejected::err(format!("{failures} check(s) failed")));
    }
    Ok(verdict)
}

// ── environment ──────────────────────────────────────────────────────────────

fn cli_version() -> Finding {
    Finding::ok(
        "cli.version",
        "Which astra-plugin am I running?",
        format!(
            "{} {} (protocol {})",
            env!("CARGO_PKG_NAME"),
            env!("CARGO_PKG_VERSION"),
            crate::bundle::PLUGIN_PROTOCOL_VERSION
        ),
    )
}

fn rust_log() -> Finding {
    match std::env::var("RUST_LOG") {
        Ok(v) if !v.is_empty() => Finding::ok(
            "cli.rust_log",
            "Why do I see no trace output from the CLI?",
            format!("RUST_LOG={v} — a subscriber is installed and this filter is in force"),
        ),
        _ => Finding::ok(
            "cli.rust_log",
            "Why do I see no trace output from the CLI?",
            "RUST_LOG is unset, so only warnings and errors are printed. \
             `RUST_LOG=astra_plugin=debug` turns on this CLI's own trace; \
             `RUST_LOG=debug` turns on its dependencies' too.",
        ),
    }
}

/// The config directory, and whether both sides of the connection agree on it.
///
/// `dev` finds the daemon by reading `<config>/daemon.port`, which the daemon
/// writes. If the two processes resolve `<config>` differently, that file is
/// written where nothing reads it and every `dev` falls back to the default
/// port — the failure reads as "the daemon is not running" while it plainly is.
fn config_dir() -> Vec<Finding> {
    let Some(dir) = crate::daemon::config_dir() else {
        return vec![Finding::warn(
            "env.config_dir",
            "Where does the CLI look for the running daemon?",
            "this platform has no home directory the `directories` crate recognises",
            "Pass --daemon-addr explicitly; autodetection cannot work here.",
        )];
    };
    let port_file = dir.join("daemon.port");
    vec![if port_file.exists() {
        Finding::ok(
            "env.config_dir",
            "Where does the CLI look for the running daemon?",
            format!(
                "{} — and {} exists, so a daemon has run and announced its port",
                dir.display(),
                port_file.display()
            ),
        )
    } else {
        Finding::warn(
            "env.config_dir",
            "Where does the CLI look for the running daemon?",
            format!(
                "{} — but there is no daemon.port in it, so the CLI will fall back to {}",
                dir.display(),
                crate::daemon::DEFAULT_DAEMON_ADDR
            ),
            "Start Astra once so it writes the file, or pass --daemon-addr. If Astra IS running, \
             it resolved a different config directory than this CLI did — compare the path above \
             with the one Astra shows in Settings.",
        )
    }]
}

async fn daemon(explicit: Option<&str>) -> Finding {
    let addr = crate::daemon::resolve_addr(explicit);
    match crate::daemon::DaemonClient::connect(&addr).await {
        Ok(c) => Finding::ok(
            "env.daemon",
            "Is the Astra daemon reachable?",
            format!("yes, at {}", c.addr()),
        ),
        Err(e) => Finding::warn(
            "env.daemon",
            "Is the Astra daemon reachable?",
            format!("no: {e:#} (tried {addr})"),
            "`dev`, `logs` and installing need a running Astra; `new`, `build`, `check`, `test`, \
             `sign` and `publish` do not. Start Astra, or pass --daemon-addr <host:port>.",
        ),
    }
}

/// The toolchains, with the ones this project actually needs promoted to
/// failures.
fn toolchains(language: &str) -> Vec<Finding> {
    let mut out = Vec::new();

    let needed = |lang: &str| language == lang;

    // Rust
    out.push(match toolchain::version("cargo") {
        Some(v) => Finding::ok("tool.cargo", "Can I build a Rust plugin?", v),
        None if needed("rust") => Finding::fail(
            "tool.cargo",
            "Can I build a Rust plugin?",
            "cargo is not on PATH, and this project has a Cargo.toml",
            "Install Rust from https://rustup.rs.",
        ),
        None => Finding::warn(
            "tool.cargo",
            "Can I build a Rust plugin?",
            "cargo is not on PATH",
            "Only needed for Rust plugins. https://rustup.rs",
        ),
    });

    // protoc — a hard prerequisite for every Rust build in this project, and
    // the one that is invisible until it fires. `astra-plugin-sdk/build.rs`
    // runs `tonic_build::configure().compile_protos(...)`, and tonic-build 0.12
    // shells out to `protoc`; it does not vendor one. So a machine with cargo
    // and no protoc fails at `cargo install ... astra-plugin-cli` — the very
    // first command an author runs — with `Could not find `protoc``, before
    // they have a project to blame.
    out.push(match toolchain::version("protoc") {
        Some(v) => Finding::ok("tool.protoc", "Can I compile the SDK's protobufs?", v),
        None if needed("rust") => Finding::fail(
            "tool.protoc",
            "Can I compile the SDK's protobufs?",
            "protoc is not on PATH, and this project has a Cargo.toml",
            "The Rust SDK's build.rs compiles proto/plugin.proto with tonic-build, which does \
             not ship a protoc. Install one: apt install protobuf-compiler / pacman -S protobuf \
             / brew install protobuf / winget install Google.Protobuf.",
        ),
        None => Finding::warn(
            "tool.protoc",
            "Can I compile the SDK's protobufs?",
            "protoc is not on PATH",
            "Only needed to build Rust — the SDK's build.rs compiles proto/plugin.proto with \
             tonic-build, which does not ship a protoc. apt install protobuf-compiler / \
             pacman -S protobuf / brew install protobuf.",
        ),
    });

    // Node — the version floor is real: the TS SDK declares engines >= 20.
    out.push(match toolchain::version("node") {
        Some(v) => match toolchain::major(&v) {
            Some(major) if major < 20 => Finding::warn(
                "tool.node",
                "Can I build and run a TypeScript plugin?",
                format!("node {v}, which is older than the SDK's `engines: {{node: \">=20\"}}`"),
                "Upgrade to Node 20 or newer. The SDK uses APIs that are not there before 20, and \
                 the failure shows up at run time as an undefined function, not at install.",
            ),
            _ => Finding::ok("tool.node", "Can I build and run a TypeScript plugin?", format!("node {v}")),
        },
        None if needed("typescript") => Finding::fail(
            "tool.node",
            "Can I build and run a TypeScript plugin?",
            "node is not on PATH, and this project has a package.json",
            "Install Node 20 or newer from https://nodejs.org.",
        ),
        None => Finding::warn(
            "tool.node",
            "Can I build and run a TypeScript plugin?",
            "node is not on PATH",
            "Only needed for TypeScript plugins. https://nodejs.org",
        ),
    });

    // A bundler. `bun` is preferred, `npm` is the fallback — and it is `npm run
    // build`, never `npx run build`, which is not a command at all.
    let bundlers: Vec<&str> = ["bun", "npm", "npx"]
        .into_iter()
        .filter(|b| toolchain::exists(b))
        .collect();
    out.push(if bundlers.is_empty() {
        let answer = "none of bun, npm or npx resolve on PATH";
        let fix = "Install Node (which brings npm and npx) or Bun. On Windows these are `.cmd` \
                   shims — a shell finds them through PATHEXT, and a program has to ask PATH the \
                   way `which` does. This CLI now does; if you are on an older astra-plugin and \
                   it claimed a bundler was missing, that was this bug.";
        if needed("typescript") {
            Finding::fail("tool.bundler", "What will bundle my TypeScript?", answer, fix)
        } else {
            Finding::warn("tool.bundler", "What will bundle my TypeScript?", answer, fix)
        }
    } else {
        Finding::ok(
            "tool.bundler",
            "What will bundle my TypeScript?",
            format!(
                "{} — `astra-plugin build` uses {}",
                bundlers.join(", "),
                if bundlers.contains(&"bun") {
                    "bun run build"
                } else {
                    "npm run build"
                }
            ),
        )
    });

    // Python
    let python = ["python3", "python"]
        .into_iter()
        .find_map(|p| toolchain::version(p).map(|v| (p, v)));
    out.push(match python {
        Some((prog, v)) => Finding::ok("tool.python", "Can I build and run a Python plugin?", format!("{prog}: {v}")),
        None if needed("python") => Finding::fail(
            "tool.python",
            "Can I build and run a Python plugin?",
            "neither python3 nor python is on PATH, and this project has a pyproject.txt/requirements.txt",
            "Install Python 3.10 or newer.",
        ),
        None => Finding::warn(
            "tool.python",
            "Can I build and run a Python plugin?",
            "neither python3 nor python is on PATH",
            "Only needed for Python plugins.",
        ),
    });

    out.push(match toolchain::version("git") {
        Some(v) => Finding::ok("tool.git", "Can `publish` work out my repository?", v),
        None => Finding::warn(
            "tool.git",
            "Can `publish` work out my repository?",
            "git is not on PATH",
            "`astra-plugin publish` reads the `origin` remote to prefill the submission. Without \
             git, pass --repo owner/name.",
        ),
    });

    out
}

// ── project ──────────────────────────────────────────────────────────────────

fn project(dir: &Path, manifest_path: &Path) -> Vec<Finding> {
    let mut out = Vec::new();

    let text = match std::fs::read_to_string(manifest_path) {
        Ok(t) => t,
        Err(e) => {
            return vec![Finding::fail(
                "project.manifest",
                "Does my plugin.toml parse?",
                format!("could not read {}: {e}", manifest_path.display()),
                "Check the file's permissions.",
            )];
        }
    };
    let manifest: astra_plugin_manifest::PluginManifest = match toml::from_str(&text) {
        Ok(m) => m,
        Err(e) => {
            return vec![Finding::fail(
                "project.manifest",
                "Does my plugin.toml parse?",
                format!("no: {e}"),
                "Run `astra-plugin check` — it uses the daemon's own parser and names the field.",
            )];
        }
    };
    out.push(Finding::ok(
        "project.manifest",
        "Does my plugin.toml parse?",
        format!(
            "yes: '{}' v{}, capabilities: {}",
            manifest.plugin.id,
            manifest.plugin.version,
            {
                let caps = manifest.capabilities.as_list();
                if caps.is_empty() { "none".to_string() } else { caps.join(", ") }
            }
        ),
    ));

    // The single most common "my plugin does not start": entry.command names a
    // file that is not there.
    out.push(entry_point(dir, &manifest));

    // `[capabilities]` says what the daemon may call in; `[permissions]` says
    // what the plugin may call out. Declaring the first does not buy the
    // second, and the failure is a `permission_denied` at run time naming a
    // section the manifest never had.
    out.push(permissions(&manifest));

    // Platform.
    out.push(platform(&manifest));

    // The release workflow, and whether it is pinned.
    out.push(release_workflow(dir));

    // The optional key. Present or absent, the honest sentence about what it
    // does is the same, and it is the one authors most often have backwards.
    out.push(signing_key());

    out
}

fn entry_point(dir: &Path, manifest: &astra_plugin_manifest::PluginManifest) -> Finding {
    const Q: &str = "Will the daemon find something to start?";
    let command = manifest.entry.command.trim();
    if command.is_empty() {
        return Finding::fail(
            "project.entry",
            Q,
            "entry.command is empty",
            "Set `[entry] command` to the executable, or to the interpreter with `args`.",
        );
    }
    // A bare word is resolved on PATH by the OS; a path is relative to the
    // plugin directory.
    if !command.contains('/') && !command.contains('\\') {
        return match toolchain::locate(command) {
            Some(p) => Finding::ok(
                "project.entry",
                Q,
                format!("entry.command = `{command}` resolves on PATH to {}", p.display()),
            ),
            None => Finding::fail(
                "project.entry",
                Q,
                format!("entry.command = `{command}` does not resolve on PATH"),
                format!(
                    "Install `{command}`, or point entry.command at a file inside the plugin \
                     directory (a value containing a path separator is resolved there, never on \
                     PATH)."
                ),
            ),
        };
    }
    let joined = dir.join(command);
    let suffixed = if std::env::consts::EXE_SUFFIX.is_empty() {
        None
    } else {
        Some(dir.join(format!("{command}{}", std::env::consts::EXE_SUFFIX)))
    };
    if joined.is_file() {
        Finding::ok("project.entry", Q, format!("{} exists", joined.display()))
    } else if suffixed.as_ref().is_some_and(|p| p.is_file()) {
        Finding::ok(
            "project.entry",
            Q,
            format!(
                "{} exists — entry.command omits the `{}` suffix, which is correct: the daemon \
                 applies it, so the manifest stays portable",
                suffixed.unwrap().display(),
                std::env::consts::EXE_SUFFIX
            ),
        )
    } else {
        Finding::fail(
            "project.entry",
            Q,
            format!("{} does not exist", joined.display()),
            "Build first (`astra-plugin build`, or `cargo build --release`). If you built and the \
             file is still not there, entry.command names a path cargo does not produce — cargo \
             mangles hyphens to underscores, so `my-plugin` builds as \
             `target/release/my_plugin`.",
        )
    }
}

fn permissions(manifest: &astra_plugin_manifest::PluginManifest) -> Finding {
    const Q: &str = "Why is a host call coming back `permission_denied`?";
    let granted: Vec<String> = manifest.permissions.raw().keys().cloned().collect();
    let caps = manifest.capabilities.as_list();

    // The pairs a capability cannot work without. Same table the scaffold
    // writes, and the same reason: declaring the capability does not grant the
    // permission.
    const NEEDS: &[(&str, &str)] = &[
        ("triggers", "fire_trigger"),
        ("event_handlers", "subscribe_events"),
        ("client", "send_chat_message"),
        ("ui_contributions", "push_to_ui"),
    ];
    let missing: Vec<String> = NEEDS
        .iter()
        .filter(|(cap, perm)| {
            caps.iter().any(|c| c == cap) && !granted.iter().any(|g| g == perm)
        })
        .map(|(cap, perm)| format!("`{cap}` needs `{perm}`"))
        .collect();

    if missing.is_empty() {
        Finding::ok(
            "project.permissions",
            Q,
            format!(
                "[permissions] grants: {}. Every declared capability has the host rpc it needs.",
                if granted.is_empty() { "none".to_string() } else { granted.join(", ") }
            ),
        )
    } else {
        Finding::fail(
            "project.permissions",
            Q,
            format!(
                "[permissions] is default-deny and {} — {}",
                if granted.is_empty() {
                    "this manifest grants nothing".to_string()
                } else {
                    format!("this manifest grants only {}", granted.join(", "))
                },
                missing.join("; ")
            ),
            "Add the permission to [permissions] with a one-line reason. The reason is shown to \
             the user at install and is the whole basis of their consent, so write it for them.",
        )
    }
}

fn platform(manifest: &astra_plugin_manifest::PluginManifest) -> Finding {
    const Q: &str = "Will this install on the platforms I expect?";
    let os = &manifest.platform.os;
    if os.is_empty() {
        return Finding::ok(
            "project.platform",
            Q,
            "no [platform] block, so the daemon considers it compatible everywhere. Correct for \
             a noarch plugin; wrong for one that ships a native binary.",
        );
    }
    let host = std::env::consts::OS;
    let host_named = os.iter().any(|o| o == host);
    if host_named {
        Finding::ok(
            "project.platform",
            Q,
            format!("[platform] os = {os:?}, which includes this host ({host})"),
        )
    } else {
        Finding::warn(
            "project.platform",
            Q,
            format!("[platform] os = {os:?} does not include this host ({host})"),
            "The daemon on this machine will refuse to install it. That is fine if you are \
             cross-building; if not, add this OS to the list.",
        )
    }
}

fn release_workflow(dir: &Path) -> Finding {
    const Q: &str = "Is my release workflow set up, and pinned?";
    let path = dir.join(".github/workflows/release.yml");
    if !path.exists() {
        return Finding::warn(
            "project.ci",
            Q,
            "no .github/workflows/release.yml",
            "Run `astra-plugin init-ci`. The registry reads attested bundles off a GitHub \
             Release; without a workflow producing them there is nothing to list.",
        );
    }
    let text = std::fs::read_to_string(&path).unwrap_or_default();
    let unpinned: Vec<&str> = text
        .lines()
        .map(str::trim)
        .filter(|l| l.starts_with("uses:"))
        .filter(|l| match l.rsplit_once('@') {
            // The ref runs to the end of the line or to a trailing YAML
            // comment, whichever comes first. `init-ci` writes exactly such a
            // comment — `…@<sha>  # default branch` — so without this the only
            // file this CLI produces fails this CLI's own check, and the fix it
            // suggests (`init-ci`) regenerates the identical file.
            Some((_, r)) => !crate::commands::init_ci::is_commit_sha(
                r.split('#').next().unwrap_or(r).trim(),
            ),
            None => true,
        })
        .collect();
    if unpinned.is_empty() {
        Finding::ok("project.ci", Q, format!("{} exists and every `uses:` is pinned to a commit", path.display()))
    } else {
        Finding::warn(
            "project.ci",
            Q,
            format!("{} has {} `uses:` line(s) not pinned to a commit SHA", path.display(), unpinned.len()),
            "Run `astra-plugin init-ci` to repin. A tag can be moved by whoever owns the \
             repository it names; a commit cannot.",
        )
    }
}

fn signing_key() -> Finding {
    const Q: &str = "Do I need a signing key to publish?";
    let path = crate::commands::keygen::default_key_path();
    let have = path.as_ref().is_some_and(|p| p.exists());
    Finding::ok(
        "project.signing",
        Q,
        format!(
            "No. {} What makes Astra install a plugin is the registry record countersigning \
             sha256 of the whole file — not any key you hold. `astra-plugin sign` writes an \
             optional in-ZIP pair that is checked against a pinned Astra publisher key, so a \
             bundle signed with your own key is untrusted exactly as an unsigned one is.",
            if have {
                "You have a keypair, and `build` does not read it."
            } else {
                "You have no keypair, and you do not need one."
            }
        ),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_check_id_is_unique_and_namespaced() {
        // The ids are what the troubleshooting guide links to. A duplicate
        // would make one of the two sections unreachable, and a bare id would
        // collide the first time a check is added in another area.
        let ids: Vec<&str> = vec![
            "cli.version",
            "cli.rust_log",
            "env.config_dir",
            "env.daemon",
            "tool.cargo",
            "tool.protoc",
            "tool.node",
            "tool.bundler",
            "tool.python",
            "tool.git",
            "project.absent",
            "project.manifest",
            "project.entry",
            "project.permissions",
            "project.platform",
            "project.ci",
            "project.signing",
        ];
        let mut sorted = ids.clone();
        sorted.sort_unstable();
        sorted.dedup();
        assert_eq!(sorted.len(), ids.len(), "duplicate doctor check id");
        assert!(ids.iter().all(|id| id.contains('.')), "every id is <area>.<name>");
    }

    #[test]
    fn a_missing_entry_point_is_a_failure_and_names_the_path() {
        let dir = std::env::temp_dir().join("astra-doctor-entry-test");
        let _ = std::fs::create_dir_all(&dir);
        let manifest: astra_plugin_manifest::PluginManifest = toml::from_str(
            r#"
[plugin]
id = "p"
name = "P"
version = "0.1.0"
[entry]
command = "target/release/nope"
"#,
        )
        .unwrap();
        let f = entry_point(&dir, &manifest);
        assert_eq!(f.level, Level::Fail);
        assert!(f.answer.contains("nope"), "the answer names the path: {}", f.answer);
        assert!(f.fix.contains("hyphens to underscores"));
    }

    #[test]
    fn a_capability_without_its_permission_is_a_failure() {
        let manifest: astra_plugin_manifest::PluginManifest = toml::from_str(
            r#"
[plugin]
id = "p"
name = "P"
version = "0.1.0"
[entry]
command = "./p"
[capabilities]
triggers = true
"#,
        )
        .unwrap();
        let f = permissions(&manifest);
        assert_eq!(f.level, Level::Fail, "{}", f.answer);
        assert!(f.answer.contains("fire_trigger"), "{}", f.answer);

        let granted: astra_plugin_manifest::PluginManifest = toml::from_str(
            r#"
[plugin]
id = "p"
name = "P"
version = "0.1.0"
[entry]
command = "./p"
[capabilities]
triggers = true
[permissions]
fire_trigger = { reason = "so commands can react" }
"#,
        )
        .unwrap();
        assert_eq!(permissions(&granted).level, Level::Ok);
    }
}
