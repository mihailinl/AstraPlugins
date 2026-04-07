//! `astra-plugin dev` — sideload plugin and watch for changes.

use std::path::Path;
use std::process::Stdio;
use std::time::Duration;

use anyhow::{Context, Result};
use notify::{EventKind, RecursiveMode, Watcher};
use tokio::process::{Child, Command};
use tokio::sync::mpsc;

pub async fn run(path: &str, daemon_addr: &str) -> Result<()> {
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

    println!("Dev mode: plugin '{plugin_id}'");
    println!("  Directory: {}", dir.display());
    println!("  Command: {entry_command} {}", entry_args.join(" "));
    println!("  Daemon: {daemon_addr}");
    println!();

    // Set up file watcher
    let (fs_tx, mut fs_rx) = mpsc::channel::<()>(1);

    let dir_clone = dir.clone();
    let mut watcher = notify::recommended_watcher(move |res: notify::Result<notify::Event>| {
        if let Ok(event) = res {
            // Only trigger on file modifications (not metadata changes)
            if matches!(
                event.kind,
                EventKind::Modify(notify::event::ModifyKind::Data(_))
                    | EventKind::Create(_)
                    | EventKind::Remove(_)
            ) {
                // Ignore build artifacts
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
        .watch(&dir_clone, RecursiveMode::Recursive)
        .context("Failed to watch directory")?;

    // Start plugin process
    let mut child = start_plugin(&entry_command, &entry_args, &dir, daemon_addr, &plugin_id)?;
    println!("  Plugin started (PID: {:?})", child.id());

    // Watch loop
    loop {
        tokio::select! {
            // File changed — restart plugin
            Some(()) = fs_rx.recv() => {
                // Debounce: drain any pending notifications
                tokio::time::sleep(Duration::from_millis(500)).await;
                while fs_rx.try_recv().is_ok() {}

                println!("\n  File changed, restarting plugin...");
                let _ = child.kill().await;
                let _ = child.wait().await;

                child = start_plugin(&entry_command, &entry_args, &dir, daemon_addr, &plugin_id)?;
                println!("  Plugin restarted (PID: {:?})", child.id());
            }
            // Plugin exited on its own
            status = child.wait() => {
                match status {
                    Ok(s) => println!("\n  Plugin exited with status: {s}"),
                    Err(e) => println!("\n  Plugin process error: {e}"),
                }
                println!("  Waiting for file changes to restart...");

                // Wait for file change before restarting
                if fs_rx.recv().await.is_some() {
                    tokio::time::sleep(Duration::from_millis(500)).await;
                    while fs_rx.try_recv().is_ok() {}

                    println!("  File changed, restarting...");
                    child = start_plugin(&entry_command, &entry_args, &dir, daemon_addr, &plugin_id)?;
                    println!("  Plugin restarted (PID: {:?})", child.id());
                } else {
                    break;
                }
            }
            // Ctrl+C
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

    Command::new(command)
        .args(&all_args)
        .current_dir(dir)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .with_context(|| format!("Failed to start '{command}'"))
}
