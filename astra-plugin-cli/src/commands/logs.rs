//! `astra-plugin logs` — read a plugin's output from the daemon that owns it.
//!
//! The daemon spawns plugin processes, so the daemon holds their stdout and
//! stderr; `astra-plugin dev` already tails them, and this is the same tail
//! without the build-and-watch loop around it. That matters when the plugin
//! under investigation is an *installed* one — the case `dev` cannot serve at
//! all, and until now the only way to read those lines was to run the daemon in
//! a terminal.
//!
//! `GetPluginLogs` is unary over a bounded per-plugin ring buffer, so `-f` is a
//! poll, and the "new" lines are the suffix of this tail that does not continue
//! the previous one. That de-duplication is shared with `dev`
//! ([`crate::commands::dev::fresh_lines`]) rather than written twice: a restart
//! resets the buffer, and getting the overlap wrong reprints the whole history
//! on every poll.

use std::time::Duration;

use anyhow::{Context, Result};
use serde_json::json;

use crate::commands::dev::fresh_lines;
use crate::daemon::{self, DaemonClient};
use crate::hprintln;
use crate::output::Verdict;

/// How often the daemon is polled with `-f`. Same cadence as `dev`.
const POLL_INTERVAL: Duration = Duration::from_millis(750);

pub struct LogsOptions<'a> {
    /// Plugin id. Defaults to the `plugin.id` of the manifest in `path`.
    pub plugin_id: Option<&'a str>,
    /// Where to look for a `plugin.toml` when no id is given.
    pub path: &'a str,
    pub daemon_addr: Option<&'a str>,
    /// Number of lines of tail to ask for.
    pub lines: i32,
    /// Keep polling until Ctrl+C.
    pub follow: bool,
}

pub async fn run(opts: LogsOptions<'_>) -> Result<Verdict> {
    let plugin_id = match opts.plugin_id {
        Some(id) => id.to_string(),
        None => id_from_manifest(opts.path)?,
    };

    let addr = daemon::resolve_addr(opts.daemon_addr);
    let mut client = DaemonClient::connect(&addr).await.with_context(|| {
        format!(
            "Could not reach the Astra daemon at {addr}. Plugin output lives in the daemon that \
             spawned the plugin, so there is nothing to read without one. Start Astra, or pass \
             --daemon-addr."
        )
    })?;

    if opts.follow && crate::output::json_mode() {
        // One document per run is the contract; a follow that never ends could
        // only ever stream fragments of one.
        anyhow::bail!("--json and -f are mutually exclusive: --json prints one document and -f never finishes");
    }

    let first = client
        .plugin_logs(&plugin_id, opts.lines)
        .await
        .map_err(|s| daemon::explain(&format!("Reading logs for '{plugin_id}'"), s))?;

    if crate::output::json_mode() {
        crate::output::emit(
            "logs",
            &Verdict::Pass,
            json!({ "plugin_id": plugin_id, "daemon": client.addr(), "lines": first }),
        );
        return Ok(Verdict::Pass);
    }

    for line in &first {
        println!("{line}");
    }

    if !opts.follow {
        return Ok(Verdict::Pass);
    }

    let mut printed = first;
    loop {
        tokio::select! {
            _ = tokio::time::sleep(POLL_INTERVAL) => {}
            _ = tokio::signal::ctrl_c() => {
                hprintln!();
                return Ok(Verdict::Pass);
            }
        }

        match client.plugin_logs(&plugin_id, opts.lines).await {
            Ok(lines) => {
                for line in fresh_lines(&printed, &lines) {
                    println!("{line}");
                }
                printed = lines;
            }
            Err(status) => {
                // A plugin mid-restart has no buffer yet. Saying so on every
                // poll would drown the output it is waiting for.
                if status.code() != tonic::Code::NotFound {
                    eprintln!("  (log poll failed: {})", status.message());
                }
            }
        }
    }
}

/// The `plugin.id` of the manifest in `path`, with a message that names the
/// alternative when there is no manifest to read.
fn id_from_manifest(path: &str) -> Result<String> {
    let manifest = std::path::Path::new(path).join("plugin.toml");
    if !manifest.exists() {
        anyhow::bail!(
            "No plugin id given and no plugin.toml at {}. Run this from a plugin directory, or \
             name the plugin: `astra-plugin logs <plugin-id>`.",
            manifest.display()
        );
    }
    let text = std::fs::read_to_string(&manifest)?;
    let value: toml::Value = toml::from_str(&text).context("Failed to parse plugin.toml")?;
    value
        .get("plugin")
        .and_then(|p| p.get("id"))
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .context("plugin.id not found in plugin.toml")
}
