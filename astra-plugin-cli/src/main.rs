//! `astra-plugin` CLI — create, develop, build, and validate Astra plugins.

mod commands;
mod daemon;
mod templates;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "astra-plugin", version, about = "Astra Plugin Development CLI")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Create a new plugin project from a template
    #[command(alias = "create")]
    New {
        /// Plugin name (lowercase, hyphens allowed)
        name: String,

        /// Programming language
        #[arg(short, long, default_value = "rust")]
        lang: String,

        /// Capabilities (comma-separated: tools, tts, stt, ai_provider, client,
        /// actions, triggers, ui_contributions, event_handlers, dom_access)
        #[arg(short, long, alias = "caps", default_value = "tools")]
        capabilities: String,

        /// Output directory (default: ./<name>)
        #[arg(short, long)]
        output: Option<String>,
    },

    /// Start a plugin in dev mode (sideload into the running Astra + hot-reload)
    Dev {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Daemon gRPC address. Defaults to the port the running daemon wrote
        /// to <config>/daemon.port, else 127.0.0.1:32000.
        #[arg(long)]
        daemon_addr: Option<String>,

        /// Spawn the plugin process directly instead of asking the daemon to.
        /// The plugin cannot register with Astra this way — see the note it prints.
        #[arg(long)]
        standalone: bool,
    },

    /// Build a plugin into a distributable .astraplugin archive
    Build {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Output file path
        #[arg(short, long)]
        output: Option<String>,
    },

    /// Check a plugin manifest and config schema
    #[command(alias = "validate")]
    Check {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Treat warnings as errors
        #[arg(long)]
        strict: bool,
    },

    /// Generate an Ed25519 keypair for plugin signing
    Keygen {
        /// Overwrite existing keypair
        #[arg(long)]
        force: bool,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::New {
            name,
            lang,
            capabilities,
            output,
        } => {
            let caps: Vec<&str> = capabilities.split(',').map(str::trim).collect();
            let out_dir = output.unwrap_or_else(|| name.clone());
            commands::create::run(&name, &lang, &caps, &out_dir)?;
        }
        Commands::Dev {
            path,
            daemon_addr,
            standalone,
        } => {
            commands::dev::run(&path, daemon_addr.as_deref(), standalone).await?;
        }
        Commands::Build { path, output } => {
            commands::build::run(&path, output.as_deref())?;
        }
        Commands::Check { path, strict } => {
            commands::validate::run(&path, strict)?;
        }
        Commands::Keygen { force } => {
            commands::keygen::run(force)?;
        }
    }

    Ok(())
}
