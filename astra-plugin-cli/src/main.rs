//! `astra-plugin` CLI — create, develop, build, and validate Astra plugins.

mod bundle;
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

    /// Build a plugin into a distributable .astraplugin bundle
    Build {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Output file path. Defaults to <id>-<version>-<target>.astraplugin,
        /// which is the name a published bundle must have — the target segment
        /// is the registry's platform key.
        #[arg(short, long)]
        output: Option<String>,

        /// Platform this bundle is for: linux-x64, windows-x64, or noarch.
        /// Defaults to the host for native plugins and noarch for
        /// TypeScript/Python.
        #[arg(long)]
        target: Option<String>,

        /// Assert deterministic packing: sorted entries, mtime 1980-01-01,
        /// fixed compression level. Two builds from the same inputs produce
        /// the same sha256.
        #[arg(long)]
        reproducible: bool,

        /// Deprecated no-op: `build` never signs. Kept because the pinned
        /// release workflow passes it, and dropping the flag would break every
        /// already-published author workflow. Removed with the format's
        /// legacy pair.
        #[arg(long, hide = true)]
        no_sign: bool,
    },

    /// Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle.
    ///
    /// An optional second factor, not a trust signal: Astra checks the in-ZIP
    /// pair against a pinned Astra publisher key, so a bundle signed with your
    /// own key is untrusted exactly as an unsigned one is. What makes Astra
    /// install a plugin is the registry record countersigning sha256(whole
    /// file). Both this command and the format entries it writes are removed
    /// in a future release.
    Sign {
        /// The .astraplugin to sign, in place.
        file: String,

        /// Read the Ed25519 seed from this path instead of
        /// ~/.astra/plugin-keys/private.key. A path, never the key itself.
        #[arg(long)]
        key: Option<String>,
    },

    /// Verify a built .astraplugin bundle and print its digests
    Verify {
        /// Path to the .astraplugin file
        file: String,

        /// Emit the report as JSON
        #[arg(long)]
        json: bool,
    },

    /// Check a plugin manifest, config schema and release workflow
    #[command(alias = "validate")]
    Check {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Treat warnings as errors
        #[arg(long)]
        strict: bool,

        /// Ask GitHub whether the release workflow pin is current. Off by
        /// default: `astra-plugin dev` runs `check --strict` on every start,
        /// and the release workflow tells the check what it is running from
        /// through ASTRA_PLUGIN_WORKFLOW_SHA, so neither needs the network.
        #[arg(long)]
        resolve_pin: bool,
    },

    /// Write .github/workflows/release.yml, pinned to a commit of the Astra
    /// reusable workflow. Re-run it to upgrade the pin; it keeps your inputs.
    InitCi {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// A 40-hex commit to pin (used verbatim, no network), or a ref name
        /// to resolve. Default: the released workflow tag, else the default
        /// branch head.
        #[arg(long = "ref")]
        workflow_ref: Option<String>,

        /// Set the linux-packages input, e.g. "libasound2-dev pkg-config".
        /// Omitted, an existing file's value is kept.
        #[arg(long)]
        linux_packages: Option<String>,

        /// Never touch the network: keep the pin already in the file.
        #[arg(long)]
        offline: bool,
    },

    /// Set the version in plugin.toml and every other manifest at once
    Version {
        /// The new version, strict semver and without a leading 'v'
        version: String,

        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Allow a version that sorts below the current one. Astra refuses to
        /// install a downgrade, so such a release is uninstallable.
        #[arg(long)]
        allow_downgrade: bool,
    },

    /// Get a release listed: preflight it, or open a prefilled submission.
    ///
    /// Uploads nothing and holds no credential — the registry reads the
    /// attested bundles off your GitHub Release and verifies every one of them
    /// from scratch, so a submission carries only your repository and a tag.
    Publish {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Run every check the registry runs that can be run locally, name the
        /// ones only the registry can run, and stop.
        #[arg(long)]
        dry_run: bool,

        /// A release ping for a plugin that is ALREADY listed — task 3.4's
        /// manual escape hatch, for when the registry has not noticed a
        /// release by itself. Without it, this opens a first listing request.
        #[arg(long)]
        notify: bool,

        /// Source repository as `owner/name`. Default: the `origin` remote.
        #[arg(long)]
        repo: Option<String>,

        /// Release tag. Default: the plugin's tag prefix plus its version.
        #[arg(long)]
        tag: Option<String>,

        /// Print the URL and do not open a browser.
        #[arg(long)]
        print_url: bool,
    },

    /// Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses.
    ///
    /// You do not need one to publish: `build` does not read it, and Astra's
    /// trust comes from the registry record over sha256(whole file), not from
    /// any key you hold.
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
        Commands::Build {
            path,
            output,
            target,
            reproducible,
            no_sign,
        } => {
            let target = target.as_deref().map(bundle::Target::parse).transpose()?;
            commands::build::run(commands::build::BuildOptions {
                path: &path,
                output: output.as_deref(),
                target,
                reproducible,
                no_sign,
            })?;
        }
        Commands::Sign { file, key } => {
            commands::sign::run(commands::sign::SignOptions {
                file: &file,
                key: key.as_deref(),
            })?;
        }
        Commands::Verify { file, json } => {
            commands::verify::run(&file, json)?;
        }
        Commands::Check {
            path,
            strict,
            resolve_pin,
        } => {
            commands::validate::run_with(&path, strict, resolve_pin)?;
        }
        Commands::InitCi {
            path,
            workflow_ref,
            linux_packages,
            offline,
        } => {
            commands::init_ci::run(commands::init_ci::InitCiOptions {
                path: &path,
                workflow_ref: workflow_ref.as_deref(),
                linux_packages: linux_packages.as_deref(),
                offline,
            })?;
        }
        Commands::Version {
            version,
            path,
            allow_downgrade,
        } => {
            commands::version::run(commands::version::VersionOptions {
                path: &path,
                version: &version,
                allow_downgrade,
            })?;
        }
        Commands::Publish {
            path,
            dry_run,
            notify,
            repo,
            tag,
            print_url,
        } => {
            commands::publish::run(commands::publish::PublishOptions {
                path: &path,
                repo: repo.as_deref(),
                tag: tag.as_deref(),
                dry_run,
                notify,
                print_url,
            })?;
        }
        Commands::Keygen { force } => {
            commands::keygen::run(force)?;
        }
    }

    Ok(())
}
