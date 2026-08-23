//! `astra-plugin` — the whole authoring loop: scaffold, run, check, test,
//! build, sign, publish.
//!
//! # The command set, and what is deliberately not in it
//!
//! There is **no `login`**. Getting a plugin listed routes through a browser
//! the author is already signed into — the registry reads attested bundles off
//! a GitHub Release and verifies each one from scratch, so a submission carries
//! a repository and a tag and nothing else. That means no second account to
//! create, no keyring to integrate with, no credentials file to leak, and no
//! token in a shell history. A `login` here would be a credential store built
//! to hold something nothing asks for.
//!
//! # `--json` and exit codes
//!
//! Every subcommand takes `--json` and prints exactly one document. Exit codes
//! are 0 / 1 / 2 and the split matters — see [`crate::output`].
//!
//! # `RUST_LOG`
//!
//! Documented since 0.1 and inert until now: no subscriber was ever installed,
//! so every `tracing` event this CLI and its dependencies emitted went nowhere.
//! `main` installs one.

mod bundle;
mod commands;
mod daemon;
mod locales;
mod output;
mod templates;
mod toolchain;

use std::process::ExitCode;

use anyhow::Result;
use clap::{Parser, Subcommand};

use crate::output::Verdict;

#[derive(Parser)]
#[command(
    name = "astra-plugin",
    version,
    about = "Astra Plugin Development CLI",
    after_help = "Exit codes: 0 success · 1 the plugin/bundle is wrong · 2 the CLI could not run \
                  the check.\nRUST_LOG controls trace output, e.g. RUST_LOG=astra_plugin=debug."
)]
struct Cli {
    /// Print one JSON document instead of human output. Progress lines are
    /// suppressed so the output is safe to pipe.
    #[arg(long, global = true)]
    json: bool,

    #[command(subcommand)]
    command: Commands,
}

impl Commands {
    /// The subcommand's name, for the `RUST_LOG` trace. One place, so a new
    /// subcommand that forgets it shows up as a compile error.
    fn name(&self) -> &'static str {
        match self {
            Commands::New { .. } => "new",
            Commands::Dev { .. } => "dev",
            Commands::Build { .. } => "build",
            Commands::Sign { .. } => "sign",
            Commands::Verify { .. } => "verify",
            Commands::Test { .. } => "test",
            Commands::Doctor { .. } => "doctor",
            Commands::Logs { .. } => "logs",
            Commands::Check { .. } => "check",
            Commands::InitCi { .. } => "init-ci",
            Commands::Version { .. } => "version",
            Commands::Publish { .. } => "publish",
            Commands::Keygen { .. } => "keygen",
            Commands::Locale { .. } => "locale",
        }
    }
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

        /// What kind of plugin this is. Picks the capabilities and the example
        /// code; `--capabilities` overrides the capability set it implies.
        #[arg(short, long, default_value = "tool", value_parser = commands::create::TEMPLATE_NAMES)]
        template: String,

        /// Capabilities (comma-separated: tools, tts, stt, ai_provider, client,
        /// actions, triggers, ui_contributions, event_handlers, dom_access).
        /// Overrides whatever --template implies.
        #[arg(short, long, alias = "caps")]
        capabilities: Option<String>,

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

        /// Build every bundle this plugin needs to be installable everywhere
        /// Astra runs. One file for TypeScript and Python (noarch); one per
        /// platform for Rust, each from its own `cargo build --target`.
        #[arg(long, conflicts_with = "target")]
        all_targets: bool,
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
    },

    /// Run the conformance suite against a real plugin process.
    ///
    /// Starts the plugin the way the daemon starts it, against a mock daemon
    /// serving PluginHostService, and calls every inbound hook that the
    /// manifest's capabilities imply. A hook `spec/hooks.yaml` marks
    /// `required` may not answer UNIMPLEMENTED; an `optional` one may, because
    /// UNIMPLEMENTED is the protocol's way of saying "this hook is absent".
    Test {
        /// Path to plugin directory (default: current directory)
        #[arg(default_value = ".")]
        path: String,

        /// Use whatever is already built instead of building first.
        #[arg(long)]
        no_build: bool,

        /// Write the machine-readable conformance report here.
        #[arg(long)]
        report: Option<String>,
    },

    /// Answer, in one command, every question asked when a plugin will not
    /// start: toolchains, the daemon, the manifest, the entry point,
    /// permissions, the platform block, the release workflow.
    Doctor {
        /// Path to plugin directory (default: current directory). Project
        /// checks are skipped when it holds no plugin.toml.
        #[arg(default_value = ".")]
        path: String,

        /// Daemon gRPC address to probe.
        #[arg(long)]
        daemon_addr: Option<String>,
    },

    /// Read a plugin's output from the daemon that spawned it
    Logs {
        /// Plugin id. Default: the plugin.id of the manifest in --path.
        plugin_id: Option<String>,

        /// Where to look for a plugin.toml when no id is given
        #[arg(long, default_value = ".")]
        path: String,

        /// Daemon gRPC address
        #[arg(long)]
        daemon_addr: Option<String>,

        /// How many lines of tail to ask for
        #[arg(short = 'n', long, default_value_t = 200)]
        lines: i32,

        /// Keep polling until Ctrl+C
        #[arg(short, long)]
        follow: bool,
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

        /// Apply the fixes that can be applied mechanically, then re-check.
        /// Only rewrites what it can prove; everything else is still reported.
        #[arg(long)]
        fix: bool,

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

    /// Manage `locales/` — the plugin's translations, and its store card's text.
    ///
    /// A plugin ships one flat `locales/<code>.json` per language beside
    /// `plugin.toml`. `astra-plugin check` and `astra-plugin build` enforce the
    /// rules over that directory; these commands are how you satisfy them
    /// without reading them.
    Locale {
        #[command(subcommand)]
        command: LocaleCommands,

        /// Path to plugin directory (default: current directory)
        #[arg(long, default_value = ".", global = true)]
        path: String,
    },
}

#[derive(Subcommand)]
enum LocaleCommands {
    /// The vocabulary, what this plugin ships, key counts and deltas.
    ///
    /// Always prints how many codes `spec/locales.yaml` declares beside how
    /// many this plugin ships, so an empty result reads as empty rather than
    /// as a pass.
    Ls,

    /// Seed a locale from `en.json`, with the plural rows that code needs.
    ///
    /// Keeps every value already translated, and NAMES every key it removes
    /// because `en.json` no longer declares it. Refuses a code Astra cannot be
    /// set to — `zh-CN` is packed, digested, signed and read by nothing.
    Add {
        /// A language code from `spec/locales.yaml`, e.g. `ru`.
        code: String,

        /// Delete translated values `en.json` cannot seed, instead of refusing.
        ///
        /// Needed only when a key was renamed or dropped out of `en.json` and
        /// the translation of the old one is still here. Without it those
        /// values are a refusal, because this command cannot tell a rename
        /// from a deletion and a translation is the one thing in `locales/`
        /// that cannot be regenerated.
        #[arg(long)]
        prune: bool,
    },

    /// Rewrite `locales.lock.json`, and `en.json`'s two `listing.*` keys.
    ///
    /// State is DERIVED from what is on disk, never asserted: a value equal to
    /// English is untranslated, a value that differs is stamped with a digest
    /// of the English it was made against, and a digest that no longer matches
    /// is stale. A stale entry is not re-stamped without `--accept`.
    Sync {
        /// `ru` or `ru:msg.done.other` — accept a stale translation as still
        /// correct. Prints what it accepted, and lands in a committed diff.
        #[arg(long, value_name = "CODE[:KEY]")]
        accept: Vec<String>,
    },

    /// The locale rules alone, without the rest of `astra-plugin check`.
    Check,

    /// Which `$keys` in `plugin.toml` are absent from `locales/en.json`.
    Extract,

    /// Walk `[config] schema` locally and print every string, marking which
    /// are `$` references and which are hardcoded literals.
    ///
    /// This is the half `locale pseudo` structurally cannot reach: `qps` is
    /// not a language `Settings::validate` accepts, so the daemon can never be
    /// asked for a `qps` config schema.
    Render {
        /// The language to render as. Falls back to English per key.
        #[arg(long, default_value = "en")]
        lang: String,
    },

    /// Write `locales/qps.json` — every English string, bracketed and padded.
    ///
    /// Run the plugin against it and anything still in plain English is a
    /// string that never reached a locale file. `astra-plugin build` refuses a
    /// bundle carrying it.
    Pseudo,
}

#[tokio::main]
async fn main() -> ExitCode {
    let cli = Cli::parse();
    output::set_json(cli.json);
    init_tracing();

    match dispatch(cli).await {
        Ok(verdict) => ExitCode::from(verdict.code() as u8),
        Err(e) => {
            // Never on stdout: in --json mode stdout carries the document and
            // nothing else, and a caller piping us must not have to strip
            // diagnostics out of it.
            eprintln!("Error: {e:#}");
            ExitCode::from(output::code_for(&e) as u8)
        }
    }
}

/// Install a `tracing` subscriber so `RUST_LOG` does something.
///
/// Default `warn`: this CLI's user-facing output is `println!`, and turning
/// dependency logs on by default would bury it. To stderr for the same reason
/// `--json` exists — a trace line on stdout corrupts the document.
fn init_tracing() {
    use tracing_subscriber::EnvFilter;
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("warn"));
    let _ = tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_writer(std::io::stderr)
        .try_init();
}

async fn dispatch(cli: Cli) -> Result<Verdict> {
    tracing::debug!(
        version = env!("CARGO_PKG_VERSION"),
        json = cli.json,
        command = cli.command.name(),
        "astra-plugin starting"
    );
    match cli.command {
        Commands::New {
            name,
            lang,
            template,
            capabilities,
            output,
        } => {
            let out_dir = output.unwrap_or_else(|| name.clone());
            commands::create::run(commands::create::NewOptions {
                name: &name,
                lang: &lang,
                template: &template,
                capabilities: capabilities.as_deref(),
                out_dir: &out_dir,
            })
        }
        Commands::Dev {
            path,
            daemon_addr,
            standalone,
        } => {
            // `--json` promises one document per run, and `dev` is a loop that
            // does not finish — it would have to emit fragments, which is a
            // different contract wearing the same flag. Refusing is the honest
            // answer; `astra-plugin check --json` and `astra-plugin test --json`
            // are the machine-readable halves of what `dev` does.
            if cli.json {
                anyhow::bail!(
                    "`dev --json` is not a thing: --json prints one document and `dev` never \
                     finishes. Use `astra-plugin check --json` and `astra-plugin test --json`, \
                     or `astra-plugin logs --json` for a snapshot of the output."
                );
            }
            commands::dev::run(&path, daemon_addr.as_deref(), standalone).await?;
            Ok(Verdict::Pass)
        }
        Commands::Build {
            path,
            output,
            target,
            reproducible,
            no_sign,
            all_targets,
        } => {
            let target = target.as_deref().map(bundle::Target::parse).transpose()?;
            let opts = commands::build::BuildOptions {
                path: &path,
                output: output.as_deref(),
                target,
                reproducible,
                no_sign,
            };
            if all_targets {
                commands::build::run_all_targets(opts)?;
            } else {
                commands::build::run(opts)?;
            }
            output::emit("build", &Verdict::Pass, serde_json::json!({ "path": path }));
            Ok(Verdict::Pass)
        }
        Commands::Sign { file, key } => {
            commands::sign::run(commands::sign::SignOptions {
                file: &file,
                key: key.as_deref(),
            })?;
            output::emit(
                "sign",
                &Verdict::Pass,
                serde_json::json!({
                    "file": file,
                    "what_this_does_not_mean": commands::sign::what_this_does_not_mean(),
                }),
            );
            Ok(Verdict::Pass)
        }
        Commands::Verify { file } => match commands::verify::run(&file, cli.json) {
            Ok(()) => Ok(Verdict::Pass),
            // A file that is there and does not verify is the bundle being
            // wrong — exit 1. A file that is not there is the CLI being unable
            // to answer — exit 2. Every release workflow branches on this.
            //
            // `Rejected` is the OUTER error and the original is folded into
            // its message, not the other way round: `err.context(Rejected)`
            // attaches Rejected as a context *object*, which `anyhow`'s
            // `chain()` does not yield, so the classification would be
            // invisible to `code_for`.
            Err(e) if std::path::Path::new(&file).is_file() => Err(output::Rejected::err(
                format!("the bundle did not verify: {e:#}"),
            )),
            Err(e) => Err(e),
        },
        Commands::Test {
            path,
            no_build,
            report,
        } => {
            commands::test::run(commands::test::TestOptions {
                path: &path,
                no_build,
                report: report.as_deref(),
            })
            .await
        }
        Commands::Doctor { path, daemon_addr } => {
            commands::doctor::run(commands::doctor::DoctorOptions {
                path: &path,
                daemon_addr: daemon_addr.as_deref(),
            })
            .await
        }
        Commands::Logs {
            plugin_id,
            path,
            daemon_addr,
            lines,
            follow,
        } => {
            commands::logs::run(commands::logs::LogsOptions {
                plugin_id: plugin_id.as_deref(),
                path: &path,
                daemon_addr: daemon_addr.as_deref(),
                lines,
                follow,
            })
            .await
        }
        Commands::Check {
            path,
            strict,
            fix,
            resolve_pin,
        } => commands::validate::run_full(commands::validate::CheckOptions {
            path: &path,
            strict,
            fix,
            resolve_pin,
        }),
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
            output::emit("init-ci", &Verdict::Pass, serde_json::json!({ "path": path }));
            Ok(Verdict::Pass)
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
            output::emit(
                "version",
                &Verdict::Pass,
                serde_json::json!({ "path": path, "version": version }),
            );
            Ok(Verdict::Pass)
        }
        Commands::Publish {
            path,
            dry_run,
            notify,
            repo,
            tag,
            print_url,
        } => {
            let url = commands::publish::run(commands::publish::PublishOptions {
                path: &path,
                repo: repo.as_deref(),
                tag: tag.as_deref(),
                dry_run,
                notify,
                print_url,
            })?;
            output::emit(
                "publish",
                &Verdict::Pass,
                serde_json::json!({ "path": path, "dry_run": dry_run, "url": url }),
            );
            Ok(Verdict::Pass)
        }
        Commands::Keygen { force } => {
            commands::keygen::run(force)?;
            output::emit("keygen", &Verdict::Pass, serde_json::json!({}));
            Ok(Verdict::Pass)
        }
        Commands::Locale { command, path } => {
            use commands::locale::Sub;
            let sub = match command {
                LocaleCommands::Ls => Sub::Ls,
                LocaleCommands::Add { code, prune } => Sub::Add { code, prune },
                LocaleCommands::Sync { accept } => Sub::Sync { accept },
                LocaleCommands::Check => Sub::Check,
                LocaleCommands::Extract => Sub::Extract,
                LocaleCommands::Render { lang } => Sub::Render { lang },
                LocaleCommands::Pseudo => Sub::Pseudo,
            };
            commands::locale::run(&path, sub)
        }
    }
}
