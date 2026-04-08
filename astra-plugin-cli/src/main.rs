//! `astra-plugin` CLI — create, develop, build, and validate Astra plugins.

mod commands;
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
    Create {
        /// Plugin name (lowercase, hyphens allowed)
        name: String,

        /// Programming language
        #[arg(short, long, default_value = "rust")]
        lang: String,

        /// Capabilities (comma-separated: tools,tts,stt,ai_provider,actions,triggers,client)
        #[arg(short, long, default_value = "tools")]
        capabilities: String,

        /// Output directory (default: ./<name>)
        #[arg(short, long)]
        output: Option<String>,
    },

    /// Start a plugin in dev mode (sideload + hot-reload)
    Dev {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Daemon gRPC address
        #[arg(long, default_value = "127.0.0.1:50051")]
        daemon_addr: String,
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

    /// Validate a plugin manifest and config schema
    Validate {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,
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
        Commands::Create {
            name,
            lang,
            capabilities,
            output,
        } => {
            let caps: Vec<&str> = capabilities.split(',').map(str::trim).collect();
            let out_dir = output.unwrap_or_else(|| name.clone());
            commands::create::run(&name, &lang, &caps, &out_dir)?;
        }
        Commands::Dev { path, daemon_addr } => {
            commands::dev::run(&path, &daemon_addr).await?;
        }
        Commands::Build { path, output } => {
            commands::build::run(&path, output.as_deref())?;
        }
        Commands::Validate { path } => {
            commands::validate::run(&path)?;
        }
        Commands::Keygen { force } => {
            commands::keygen::run(force)?;
        }
    }

    Ok(())
}
