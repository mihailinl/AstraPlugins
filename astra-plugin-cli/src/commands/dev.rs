//! `astra-plugin dev` — build, sideload into the running daemon, watch, reload.
//!
//! The daemon owns the plugin process. That is not a stylistic choice: a plugin
//! authenticates to `PluginHostService` with an `--auth-token` the daemon mints
//! when it spawns the process, and the daemon's fail-closed gate rejects any
//! `Register` that does not carry a token it issued. A CLI-spawned plugin has
//! no way to obtain one, so the self-spawning dev loop this replaced could
//! never register — it started a process that talked to nobody. `--standalone`
//! keeps that behaviour for the cases where it is still useful (checking that a
//! binary starts, driving it by hand) and says up front what it cannot do.

use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use anyhow::{Context, Result};
use notify::{EventKind, RecursiveMode, Watcher};
use tokio::process::{Child, Command};
use tokio::sync::mpsc;

use crate::daemon::{self, DaemonClient};

/// How often the daemon is polled for new plugin output.
const LOG_POLL_INTERVAL: Duration = Duration::from_millis(750);

/// How much log tail to ask for. The daemon keeps a bounded ring buffer per
/// plugin; asking for more than it holds is harmless.
const LOG_TAIL_LINES: i32 = 400;

/// Quiet period after a file event before rebuilding.
const DEBOUNCE: Duration = Duration::from_millis(500);

pub async fn run(path: &str, daemon_addr: Option<&str>, standalone: bool) -> Result<()> {
    let dir = Path::new(path)
        .canonicalize()
        .context("Invalid plugin path")?;
    let manifest_path = dir.join("plugin.toml");

    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }

    let manifest_str = std::fs::read_to_string(&manifest_path)?;
    let manifest: toml::Value = toml::from_str(&manifest_str)?;

    let plugin_id = manifest
        .get("plugin")
        .and_then(|p| p.get("id"))
        .and_then(|v| v.as_str())
        .context("plugin.id not found")?
        .to_string();

    if standalone {
        return run_standalone(&dir, &plugin_id, &manifest, daemon_addr).await;
    }

    println!("Dev mode: plugin '{plugin_id}'");
    println!("  Directory: {}", dir.display());

    // 1. Refuse to hand the daemon a manifest that is already wrong.
    crate::commands::validate::run(&dir.to_string_lossy(), true)
        .context("`astra-plugin check --strict` failed — fix the manifest before sideloading")?;

    // 2. Build once before the daemon is asked to spawn anything.
    crate::commands::build::build_project(&dir)?;

    // 3. Hand the source directory to the daemon: it spawns the process, mints
    //    the auth token and owns the lifecycle from here on.
    let addr = daemon::resolve_addr(daemon_addr);
    let mut client = DaemonClient::connect(&addr).await?;
    println!("  Daemon: {}", client.addr());

    let status = client
        .sideload_plugin(&dir)
        .await
        .map_err(|s| daemon::explain("Sideloading the plugin", s))?;
    report_status(&status);

    let watch_id = if status.id.is_empty() {
        plugin_id.clone()
    } else {
        status.id.clone()
    };

    let (_watcher, mut fs_rx) = watch_directory(&dir)?;
    println!("  Watching for changes. Ctrl+C to stop.\n");

    let mut printed: Vec<String> = Vec::new();
    pump_logs(&mut client, &watch_id, &mut printed).await;

    loop {
        tokio::select! {
            _ = tokio::time::sleep(LOG_POLL_INTERVAL) => {
                pump_logs(&mut client, &watch_id, &mut printed).await;
            }
            Some(()) = fs_rx.recv() => {
                tokio::time::sleep(DEBOUNCE).await;
                while fs_rx.try_recv().is_ok() {}

                println!("\n  File changed, rebuilding...");
                if let Err(e) = crate::commands::build::build_project(&dir) {
                    println!("  Build failed: {e:#}");
                    println!("  Keeping the previous build running. Waiting for the next change...");
                    continue;
                }

                // Stop → start rather than re-sideload: the daemon already
                // holds this plugin's registration, and a fresh spawn is what
                // picks up the new binary.
                if let Err(s) = client.stop_plugin(&watch_id).await {
                    println!("  Warning: StopPlugin failed: {}", s.message());
                }
                match client.start_plugin(&watch_id).await {
                    Ok(()) => println!("  Reloaded '{watch_id}'.\n"),
                    Err(s) => return Err(daemon::explain("Restarting the plugin", s)),
                }
                // `printed` is deliberately NOT cleared: the daemon's per-plugin
                // ring buffer survives a stop/start, so clearing would reprint
                // the whole tail. `fresh_lines` handles either case — a buffer
                // the daemon did reset simply shares no overlap.
                pump_logs(&mut client, &watch_id, &mut printed).await;
            }
            _ = tokio::signal::ctrl_c() => {
                println!("\n  Stopping '{watch_id}'...");
                if let Err(s) = client.stop_plugin(&watch_id).await {
                    println!("  Warning: StopPlugin failed: {}", s.message());
                }
                println!("  The plugin stays sideloaded in Astra; run `astra-plugin dev` again to resume.");
                break;
            }
        }
    }

    Ok(())
}

fn report_status(status: &daemon::PluginStatus) {
    let state = if status.status.is_empty() {
        "unknown"
    } else {
        &status.status
    };
    println!("  Sideloaded '{}' v{} [{}]", status.id, status.version, state);
    if !status.capabilities.is_empty() {
        println!("  Capabilities: {}", status.capabilities.join(", "));
    }
    if !status.error.is_empty() {
        println!("  Daemon reported an error: {}", status.error);
    }
}

/// Fetch the log tail and print whatever is new since last time.
///
/// `GetPluginLogs` is unary and returns the last N lines of a ring buffer, so
/// "new" means "the part of this tail that does not continue the previous one".
async fn pump_logs(client: &mut DaemonClient, plugin_id: &str, printed: &mut Vec<String>) {
    let lines = match client.plugin_logs(plugin_id, LOG_TAIL_LINES).await {
        Ok(lines) => lines,
        Err(status) => {
            // A plugin that is mid-restart has no log buffer yet; that is not
            // worth a message on every poll.
            if status.code() != tonic::Code::NotFound {
                eprintln!("  (log poll failed: {})", status.message());
            }
            return;
        }
    };

    for line in fresh_lines(printed, &lines) {
        println!("  | {line}");
    }
    *printed = lines;
}

/// The suffix of `current` that does not overlap the tail of `previous`.
///
/// Shared with `astra-plugin logs -f`, which polls the same ring buffer: two
/// copies of this would be two chances to reprint the whole history on every
/// poll.
pub fn fresh_lines<'a>(previous: &[String], current: &'a [String]) -> &'a [String] {
    let max = previous.len().min(current.len());
    for overlap in (0..=max).rev() {
        if previous[previous.len() - overlap..] == current[..overlap] {
            return &current[overlap..];
        }
    }
    current
}

/// Watch a plugin directory, collapsing every interesting event into a tick.
///
/// The returned watcher must be held for as long as the events matter — it
/// stops watching on drop.
fn watch_directory(dir: &Path) -> Result<(notify::RecommendedWatcher, mpsc::Receiver<()>)> {
    let (fs_tx, fs_rx) = mpsc::channel::<()>(1);

    let mut watcher = notify::recommended_watcher(move |res: notify::Result<notify::Event>| {
        if let Ok(event) = res {
            // Only trigger on file modifications (not metadata changes)
            if matches!(
                event.kind,
                EventKind::Modify(notify::event::ModifyKind::Data(_))
                    | EventKind::Create(_)
                    | EventKind::Remove(_)
            ) {
                // Ignore build artifacts — our own rebuild writes into them.
                let dominated_by_build = event.paths.iter().all(|p| {
                    let s = p.to_string_lossy();
                    s.contains("target")
                        || s.contains("node_modules")
                        || s.contains("__pycache__")
                        || s.contains(".venv")
                        || s.contains("dist")
                });
                if !dominated_by_build {
                    let _ = fs_tx.try_send(());
                }
            }
        }
    })
    .context("Failed to create file watcher")?;

    watcher
        .watch(dir, RecursiveMode::Recursive)
        .context("Failed to watch directory")?;

    Ok((watcher, fs_rx))
}

// ---------------------------------------------------------------------------
// --standalone: the old self-spawning loop
// ---------------------------------------------------------------------------

async fn run_standalone(
    dir: &Path,
    plugin_id: &str,
    manifest: &toml::Value,
    daemon_addr: Option<&str>,
) -> Result<()> {
    let entry_command = manifest
        .get("entry")
        .and_then(|e| e.get("command"))
        .and_then(|v| v.as_str())
        .context("entry.command not found")?
        .to_string();

    let entry_args: Vec<String> = manifest
        .get("entry")
        .and_then(|e| e.get("args"))
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let addr = daemon::resolve_addr(daemon_addr);

    println!("Dev mode (standalone): plugin '{plugin_id}'");
    println!("  Directory: {}", dir.display());
    println!("  Command: {entry_command} {}", entry_args.join(" "));
    println!("  Daemon: {addr}");
    println!();
    println!("  NOTE: a standalone plugin CANNOT register with Astra.");
    println!("        Registration requires an --auth-token that only the daemon can mint, when");
    println!("        the daemon itself spawns the plugin. Expect the plugin's Register call to");
    println!("        be refused. Use plain `astra-plugin dev` for a working dev loop.");
    println!();

    let (_watcher, mut fs_rx) = watch_directory(dir)?;

    let mut child = start_plugin(&entry_command, &entry_args, dir, &addr, plugin_id)?;
    println!("  Plugin started (PID: {:?})", child.id());

    loop {
        tokio::select! {
            Some(()) = fs_rx.recv() => {
                tokio::time::sleep(DEBOUNCE).await;
                while fs_rx.try_recv().is_ok() {}

                println!("\n  File changed, restarting plugin...");
                let _ = child.kill().await;
                let _ = child.wait().await;

                child = start_plugin(&entry_command, &entry_args, dir, &addr, plugin_id)?;
                println!("  Plugin restarted (PID: {:?})", child.id());
            }
            status = child.wait() => {
                match status {
                    Ok(s) => println!("\n  Plugin exited with status: {s}"),
                    Err(e) => println!("\n  Plugin process error: {e}"),
                }
                println!("  Waiting for file changes to restart...");

                if fs_rx.recv().await.is_some() {
                    tokio::time::sleep(DEBOUNCE).await;
                    while fs_rx.try_recv().is_ok() {}

                    println!("  File changed, restarting...");
                    child = start_plugin(&entry_command, &entry_args, dir, &addr, plugin_id)?;
                    println!("  Plugin restarted (PID: {:?})", child.id());
                } else {
                    break;
                }
            }
            _ = tokio::signal::ctrl_c() => {
                println!("\n  Shutting down...");
                let _ = child.kill().await;
                let _ = child.wait().await;
                break;
            }
        }
    }

    Ok(())
}

fn start_plugin(
    command: &str,
    args: &[String],
    dir: &Path,
    daemon_addr: &str,
    plugin_id: &str,
) -> Result<Child> {
    let mut all_args = args.to_vec();
    all_args.push(format!("--daemon-addr={daemon_addr}"));
    all_args.push(format!("--plugin-id={plugin_id}"));

    // A bare relative command is a path inside the plugin directory, not a
    // lookup on PATH — `current_dir` does not affect how the OS resolves it.
    let program: PathBuf = if command.contains('/') || command.contains('\\') {
        dir.join(command)
    } else {
        PathBuf::from(command)
    };

    Command::new(&program)
        .args(&all_args)
        .current_dir(dir)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .with_context(|| format!("Failed to start '{}'", program.display()))
}
