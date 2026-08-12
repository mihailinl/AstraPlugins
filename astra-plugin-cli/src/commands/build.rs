//! `astra-plugin build` — package a plugin into a distributable
//! `.astraplugin` bundle.
//!
//! The format itself lives in [`crate::bundle`]; this module is the part that
//! decides *what goes in*: it runs the language's build step, resolves the
//! artifacts, rewrites the manifest so `entry.command` points where the files
//! actually landed, and stamps `[platform]`/`[bundle]` from `--target`.
//!
//! Every build ends by re-opening the finished file and running the full
//! verification pass over it. That is not belt-and-braces: the manifest's
//! digests are computed in a first pass over the source files and the bytes are
//! written in a second, so a file mutated between the two would otherwise ship
//! a bundle whose manifest disagrees with its contents — and the first person
//! to notice would be a user whose install failed.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use walkdir::WalkDir;

use crate::bundle::{
    Bundle, BundleBuilder, ManifestEntry, ManifestMeta, ManifestPermission,
    PLUGIN_PROTOCOL_VERSION, PLUGIN_TOML_ENTRY, SCHEMA, Target,
};
use crate::hprintln;

/// Where `build` sends an author who wants to know what *does* establish trust.
///
/// A URL rather than a paragraph because the answer is longer than one line and
/// changes as the registry does, and this string is printed on every single
/// build — the one place an author reliably reads.
const TRUST_DOC_URL: &str = "https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/publishing.md#what-establishes-trust";

/// Where a packed binary lands inside the archive, and what `entry.command` is
/// rewritten to point at.
const ARCHIVE_BIN_DIR: &str = "bin";

/// The icon filenames packed into the bundle, in `spec/icon-formats.yaml`'s
/// order.
///
/// Kept in step with the registry's own list by
/// `the_packed_icon_formats_are_the_ones_the_spec_declares` below. Drift here
/// is silent at both ends — see that file's header for what it costs.
const ICON_FILENAMES: &[&str] = &[
    "icon.png",
    "icon.webp",
    "icon.svg",
    "icon.jpg",
    "icon.jpeg",
    "icon.ico",
];

/// Directory names that are never part of a plugin, wherever they appear.
const EXCLUDED_DIRS: &[&str] = &[
    "target",
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
];

pub struct BuildOptions<'a> {
    pub path: &'a str,
    pub output: Option<&'a str>,
    /// `None` → derive from the language: native code follows the host,
    /// interpreted code is `noarch`.
    pub target: Option<Target>,
    /// Assert determinism: refuse anything that would make the output depend
    /// on this machine rather than on the inputs.
    pub reproducible: bool,
    /// **Accepted and ignored since 3.10.** `build` never signs, so `--no-sign`
    /// asks for what already happens.
    ///
    /// The flag stays because `plugin-release.yml` passes it and every author
    /// workflow pins that file by commit SHA — removing the flag would make
    /// `astra-plugin build … --no-sign` fail with "unexpected argument" on
    /// every already-published release workflow, which is a release outage for
    /// people who changed nothing. It is hidden from `--help` and documented as
    /// a no-op; it goes at [`crate::bundle::LEGACY_PAIR_SUNSET`], with the rest.
    pub no_sign: bool,
}

/// `--all-targets`: every bundle this plugin needs to be installable everywhere
/// Astra runs.
///
/// For TypeScript and Python that is exactly one file — `noarch`, which the
/// index writes under every platform key — and saying so is more useful than
/// producing three identical archives with different names.
///
/// For Rust it is one per platform, and each needs a binary cross-compiled for
/// it. This does not run the cross-build: the toolchain, the linker and the
/// system libraries for another OS are not something a packaging tool can
/// conjure, and pretending otherwise is how a host binary ends up inside a
/// foreign bundle. It builds what is there and names what is missing.
pub fn run_all_targets(opts: BuildOptions<'_>) -> Result<()> {
    let dir = Path::new(opts.path).canonicalize().context("Invalid path")?;
    let language = detect_language(&dir);

    if matches!(language.as_str(), "typescript" | "ts" | "python" | "py") {
        hprintln!(
            "  --all-targets: {language} plugins are noarch — one bundle serves every platform."
        );
        return run(BuildOptions {
            target: Some(Target::Noarch),
            ..opts
        });
    }

    if opts.output.is_some() {
        anyhow::bail!(
            "--all-targets and --output are mutually exclusive: each target gets its own file, \
             named <id>-<version>-<target>.astraplugin, which is the name the registry requires."
        );
    }

    let mut built = Vec::new();
    let mut skipped = Vec::new();
    for target in [Target::LinuxX64, Target::WindowsX64] {
        hprintln!();
        match run(BuildOptions {
            path: opts.path,
            output: None,
            target: Some(target),
            reproducible: opts.reproducible,
            no_sign: false,
        }) {
            Ok(()) => built.push(target.key()),
            Err(e) => skipped.push((target.key(), format!("{e:#}"))),
        }
    }

    hprintln!();
    hprintln!("  Built: {}", if built.is_empty() { "nothing".into() } else { built.join(", ") });
    if !skipped.is_empty() {
        for (key, why) in &skipped {
            hprintln!("  Skipped {key}: {why}");
        }
        anyhow::bail!(
            "{} of {} targets could not be built. A release that ships only some platforms is a \
             release most users cannot install.",
            skipped.len(),
            skipped.len() + built.len()
        );
    }
    Ok(())
}

pub fn run(opts: BuildOptions<'_>) -> Result<()> {
    let dir = Path::new(opts.path)
        .canonicalize()
        .context("Invalid path")?;
    let manifest_path = dir.join("plugin.toml");

    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }

    let manifest_str = fs::read_to_string(&manifest_path)?;
    let manifest: toml::Value = toml::from_str(&manifest_str)?;

    let plugin_id = manifest
        .get("plugin")
        .and_then(|p| p.get("id"))
        .and_then(|v| v.as_str())
        .context("plugin.id not found")?;

    let version = manifest
        .get("plugin")
        .and_then(|p| p.get("version"))
        .and_then(|v| v.as_str())
        .unwrap_or("0.0.0");

    if opts.no_sign {
        // Consumed rather than ignored in silence: the flag is passed by every
        // release workflow generated before 3.10, and the people who maintain
        // those workflows only ever see this build's output.
        hprintln!(
            "  Note: --no-sign is accepted and ignored — `build` never signs. Drop it; it is \
             removed in {}.",
            crate::bundle::LEGACY_PAIR_SUNSET
        );
    }

    let language = detect_language(&dir);
    let target = resolve_target(opts.target, &language)?;

    hprintln!(
        "Building plugin '{plugin_id}' v{version} ({language}) for {}...",
        target.key()
    );
    if !target.matches_host_os() && language == "rust" {
        hprintln!(
            "  Warning: packing a {} bundle on {}. The binary this picks up must already be \
             cross-compiled for that platform.",
            target.key(),
            std::env::consts::OS
        );
    }

    // The filename is `<id>-<version>-<target>.astraplugin` and the target
    // segment is the registry's platform key, so the artifact a release
    // uploads and the key an index writes are the same string by construction.
    let output_name = opts
        .output
        .map(String::from)
        .unwrap_or_else(|| format!("{plugin_id}-{version}-{}.astraplugin", target.key()));
    let output_path = PathBuf::from(&output_name);

    build_for_language(&dir, &language)?;

    let entry_command = manifest
        .get("entry")
        .and_then(|e| e.get("command"))
        .and_then(|v| v.as_str())
        .unwrap_or("");

    // Everything that can fail is resolved BEFORE the output file is created:
    // a missing binary or an unparseable manifest must not leave a truncated
    // .astraplugin on disk for the author to mistake for a build.
    let rust_binary = if language == "rust" {
        Some(resolve_rust_binary_for(&dir, entry_command, target)?)
    } else {
        None
    };

    // For Rust the binary moves into `bin/` inside the archive, so the manifest
    // the daemon reads must point there instead of at the author's target dir.
    let packed_entry_command = match &rust_binary {
        Some(bin) => {
            let bin_name = bin
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .context("Resolved Rust binary has no file name")?;
            format!("./{ARCHIVE_BIN_DIR}/{bin_name}")
        }
        None => entry_command.to_string(),
    };

    let executables = declared_executables(&manifest)?;
    let packed_manifest = stamp_manifest(&manifest_str, &packed_entry_command, target)?;

    let mut builder = BundleBuilder::new(opts.reproducible, executables);
    builder.add_inline(PLUGIN_TOML_ENTRY, packed_manifest.into_bytes())?;

    if let Some(bin) = &rust_binary {
        let name = bin
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .context("Resolved Rust binary has no file name")?;
        // Marked executable at the source, not by a `bin/` prefix rule: the
        // packer is the thing that knows this file is the program.
        builder.add_executable_path(&format!("{ARCHIVE_BIN_DIR}/{name}"), bin)?;
    }

    // ui/ and locales/ ship for every language.
    for sub in ["ui", "locales"] {
        let path = dir.join(sub);
        if path.exists() {
            add_directory_recursive(&path, &mut builder, &dir)?;
        }
    }

    match language.as_str() {
        "rust" => {} // binary already handled above
        "typescript" | "ts" => add_typescript_artifacts(&dir, &mut builder)?,
        "python" | "py" => add_python_artifacts(&dir, &mut builder)?,
        _ => add_directory_recursive(&dir, &mut builder, &dir)?,
    }

    // The plugin's face: whatever picture the author put next to plugin.toml,
    // plus the prose and the licence. The registry reads all three straight out
    // of the bundle when it derives a listing, so these travel covered by the
    // build attestation rather than being retyped into a form.
    //
    // The icon list mirrors `astra-registry/bot/lib/assets.mjs` ICON_FORMATS
    // and is checked against it by the parity job: a format packed here that the
    // registry does not accept is an icon that silently never appears, and one
    // accepted there but not packed here is an icon an author added and this
    // tool threw away.
    for name in ICON_FILENAMES.iter().chain(&["README.md", "LICENSE"]) {
        let p = dir.join(name);
        if p.exists() && !builder.contains(name) {
            builder.add_path(name, &p)?;
        }
    }

    let meta = ManifestMeta {
        plugin_id: plugin_id.to_string(),
        version: version.to_string(),
        target,
        protocol: declared_protocol(&manifest),
        min_astra_version: manifest
            .get("plugin")
            .and_then(|p| p.get("min_astra_version"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        capabilities: declared_capabilities(&manifest),
        permissions: declared_permissions(&manifest)?,
        entry: ManifestEntry {
            command: packed_entry_command.clone(),
            args: manifest
                .get("entry")
                .and_then(|e| e.get("args"))
                .and_then(|v| v.as_array())
                .map(|a| {
                    a.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default(),
        },
    };

    let file_count = builder.len();
    let packed = builder.write(&output_path, &meta)?;
    for entry in &packed.files {
        hprintln!("  Added: {} ({})", entry.path, entry.mode);
    }

    // Round-trip. Everything this build asserted is now checked against the
    // bytes on disk, by the same code `astra-plugin verify` runs.
    let verified = Bundle::open(&output_path)
        .context("The bundle this build just produced does not verify")?;

    let size = verified.artifact_size;
    hprintln!(
        "  Built: {} ({:.1} KB, {} files)",
        output_path.display(),
        size as f64 / 1024.0,
        file_count
    );
    hprintln!("  target:          {}", target.key());
    hprintln!("  artifact sha256: {}", verified.artifact_sha256);
    hprintln!("  manifest digest: {}", verified.manifest_digest);
    if opts.reproducible {
        hprintln!(
            "  reproducible:    entries sorted, mtime 1980-01-01, deflate level {}",
            crate::bundle::REPRODUCIBLE_COMPRESSION_LEVEL
        );
    }
    print_trust_note();

    Ok(())
}

/// What `build` says about trust, on every build, signed or not.
///
/// It used to say "Signed with Ed25519 key" whenever a key happened to sit in
/// `~/.astra/plugin-keys/`, and that sentence claimed an outcome the key cannot
/// deliver: the daemon pins *Astra's* publisher key, never the author's, so an
/// author's signature was checked against nothing and proved nothing to anyone.
/// An author who believes a local signature protects their users is worse off
/// than one who knows it does not — the first ships with a false sense of a
/// control they do not have.
///
/// So the copy states the true state of the artifact and where trust actually
/// comes from. It is printed unconditionally: a build with a key on the machine
/// produces the same bundle and the same message as a build without one, which
/// is also what makes `--reproducible` mean the same thing on both.
fn print_trust_note() {
    hprintln!("{}", trust_note());
}

/// The note as one string, so a test can read the sentence the author reads.
fn trust_note() -> String {
    format!(
        "  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.\n\
         \x20 See {TRUST_DOC_URL}"
    )
}

/// `--target`, or the language's natural target.
///
/// Native code follows the host because that is the only platform whose binary
/// this build can have produced. Interpreted plugins are `noarch`: the index
/// writes one URL under every platform key, so a TypeScript plugin is built
/// once and installs everywhere.
fn resolve_target(explicit: Option<Target>, language: &str) -> Result<Target> {
    if let Some(target) = explicit {
        return Ok(target);
    }
    match language {
        "typescript" | "ts" | "python" | "py" => Ok(Target::Noarch),
        _ => Target::host(),
    }
}

/// `[bundle] executables = [...]` — archive paths that must carry the exec bit.
///
/// This is how a `linux-x64` bundle gets a runnable binary when it is packed on
/// Windows, where nothing on disk has an exec bit to derive from. It is a list
/// of paths rather than a `bin/` rule because a plugin shipping
/// `runtime/python` needs exactly the same thing and lives in a different
/// directory.
fn declared_executables(manifest: &toml::Value) -> Result<BTreeSet<String>> {
    let Some(value) = manifest.get("bundle").and_then(|b| b.get("executables")) else {
        return Ok(BTreeSet::new());
    };
    let array = value
        .as_array()
        .context("[bundle] executables must be an array of archive paths")?;
    let mut out = BTreeSet::new();
    for item in array {
        let path = item
            .as_str()
            .context("[bundle] executables entries must be strings")?;
        crate::bundle::check_archive_path(path)
            .with_context(|| format!("[bundle] executables: '{path}'"))?;
        out.insert(path.to_string());
    }
    Ok(out)
}

/// The protocol the bundle declares the host must speak.
fn declared_protocol(manifest: &toml::Value) -> u32 {
    manifest
        .get("bundle")
        .and_then(|b| b.get("protocol"))
        .and_then(|v| v.as_integer())
        .and_then(|v| u32::try_from(v).ok())
        .unwrap_or(PLUGIN_PROTOCOL_VERSION)
}

fn declared_capabilities(manifest: &toml::Value) -> Vec<String> {
    let Some(table) = manifest.get("capabilities").and_then(|c| c.as_table()) else {
        return Vec::new();
    };
    let mut caps: Vec<String> = table
        .iter()
        .filter(|(_, v)| v.as_bool() == Some(true))
        .map(|(k, _)| k.clone())
        .collect();
    caps.sort();
    caps
}

/// The whole `[permissions]` section, read with the daemon's own deserialiser.
///
/// **Deliberately not hand-parsed.** This used to pick `reason` out of each
/// entry by hand and build a one-field struct, which silently discarded
/// `subscribe_events.types` and `set_variable.scopes` — see
/// [`ManifestPermission`] for what that cost. Deserialising into
/// [`astra_plugin_manifest::Permissions`] means the packer cannot know a smaller
/// set of fields than the daemon does: a field added to `PermissionRequest`
/// starts being packed here with no edit, which is the only version of this that
/// stays true.
///
/// An absent section is the empty map, and §5.6's default-deny reads it as
/// "nothing". `permissions_hash` over `{}` is a number the registry can
/// countersign, so a plugin asking for nothing is not a special case anywhere.
///
/// Unknown permission ids are **kept, not dropped**: `permissions_hash` has to
/// cover the bytes three repositories hash, and an id this build of the CLI does
/// not recognise may well be one the user's daemon does. The daemon treats them
/// as inert, and §4.3's consent sheet renders them as "not recognised by this
/// version" rather than hiding them.
fn declared_permissions(manifest: &toml::Value) -> Result<BTreeMap<String, ManifestPermission>> {
    let Some(section) = manifest.get("permissions") else {
        return Ok(BTreeMap::new());
    };
    let permissions: astra_plugin_manifest::Permissions = section.clone().try_into().context(
        "Failed to read [permissions] in plugin.toml. Each entry is a table: \
         `fire_trigger = { reason = \"…\" }`, with optional `types` and `scopes` \
         string lists",
    )?;
    Ok(permissions.0)
}

/// Rewrite the manifest that goes *into the bundle*: `entry.command` points at
/// the packed path, and `[platform]`/`[bundle]` record what this artifact
/// actually is.
///
/// A textual `replace` used to do the command half; it silently no-oped on any
/// manifest whose spacing or quoting differed from the template's, shipping an
/// archive whose command pointed at the author's `target/` directory. This is a
/// real TOML edit, so the author's comments, ordering and formatting survive.
fn stamp_manifest(manifest_str: &str, command: &str, target: Target) -> Result<String> {
    let mut doc: toml_edit::DocumentMut = manifest_str
        .parse()
        .context("Failed to parse plugin.toml for rewriting")?;

    if !command.is_empty() {
        doc["entry"]["command"] = toml_edit::value(command);
    }

    // `[platform]` is stamped, not merged: this artifact runs on exactly one
    // platform and the author's guess about that is not the authority — the
    // target the bundle was built for is. `noarch` stamps two empty lists,
    // which is how the daemon spells "no requirement".
    let (os, arch) = target.toml_platform();
    let mut platform = toml_edit::Table::new();
    platform.set_implicit(false);
    platform["os"] = toml_edit::value(os.into_iter().collect::<toml_edit::Array>());
    platform["arch"] = toml_edit::value(arch.into_iter().collect::<toml_edit::Array>());
    doc.insert("platform", toml_edit::Item::Table(platform));

    // `[bundle]` keeps whatever the author put there (`executables`), so it is
    // edited in place when it exists.
    let bundle = ensure_table(&mut doc, "bundle");
    bundle["schema"] = toml_edit::value(SCHEMA);
    bundle["target"] = toml_edit::value(target.key());

    Ok(doc.to_string())
}

/// Get `[key]` as a real, printed table — creating it if absent, and promoting
/// an inline `key = { … }` if the author wrote one.
///
/// Assigning through `doc["key"]["sub"]` on a missing key produces a root-level
/// inline table instead, which is valid TOML that lands above `[plugin]` and
/// reads like a mistake to anyone who opens the packed manifest.
fn ensure_table<'a>(doc: &'a mut toml_edit::DocumentMut, key: &str) -> &'a mut toml_edit::Table {
    let existing = doc.get(key).cloned();
    let mut table = match existing {
        Some(toml_edit::Item::Table(t)) => t,
        Some(toml_edit::Item::Value(toml_edit::Value::InlineTable(inline))) => inline.into_table(),
        _ => toml_edit::Table::new(),
    };
    table.set_implicit(false);
    doc.insert(key, toml_edit::Item::Table(table));
    doc[key].as_table_mut().expect("just inserted as a table")
}

/// Run the language's build step for a plugin directory.
///
/// Shared with `astra-plugin dev`, which rebuilds on every file change and must
/// use exactly the same command `build` would.
pub fn build_project(dir: &Path) -> Result<()> {
    let language = detect_language(dir);
    build_for_language(dir, &language)
}

fn build_for_language(dir: &Path, language: &str) -> Result<()> {
    match language {
        "rust" => build_rust(dir),
        "typescript" | "ts" => build_typescript(dir),
        "python" | "py" => build_python(dir),
        _ => {
            hprintln!("  No build step for language '{language}'");
            Ok(())
        }
    }
}

pub fn detect_language(dir: &Path) -> String {
    if dir.join("Cargo.toml").exists() {
        "rust".into()
    } else if dir.join("package.json").exists() {
        "typescript".into()
    } else if dir.join("pyproject.toml").exists() || dir.join("requirements.txt").exists() {
        "python".into()
    } else {
        "unknown".into()
    }
}

fn build_rust(dir: &Path) -> Result<()> {
    hprintln!("  Running cargo build --release...");
    let status = std::process::Command::new("cargo")
        .args(["build", "--release"])
        .current_dir(dir)
        .status()
        .context("Failed to run cargo build")?;
    if !status.success() {
        anyhow::bail!("cargo build failed");
    }
    Ok(())
}

/// Does this project define a `scripts.build` in `package.json`?
///
/// Parsed, not searched. The substring test this replaces (`s.contains(
/// "\"build\"")`) matched the string `"build"` anywhere in the file — a
/// dependency named `build`, a `"prebuild"` script, the word inside a
/// description, `"files": ["build"]`. Each of those made the CLI run
/// `<bundler> run build` against a script that does not exist, and npm's
/// failure for a missing script is indistinguishable from a failed build.
fn has_build_script(dir: &Path) -> bool {
    let Ok(text) = fs::read_to_string(dir.join("package.json")) else {
        return false;
    };
    let Ok(json) = serde_json::from_str::<serde_json::Value>(&text) else {
        return false;
    };
    json.get("scripts")
        .and_then(|s| s.get("build"))
        .and_then(|b| b.as_str())
        .is_some_and(|s| !s.trim().is_empty())
}

fn build_typescript(dir: &Path) -> Result<()> {
    // bun if it is there, else the Node toolchain. Which Node program depends
    // on what is being run: a package script is `npm run build`; a one-off
    // binary from the registry is `npx esbuild`. `npx run build` — what this
    // used to emit — is neither. npx has no `run` subcommand, so it treated
    // `run` as a package name and went looking for a package called `run` on
    // the registry, which is a network fetch that either fails or, worse,
    // succeeds and executes somebody else's code.
    let bundler = if crate::toolchain::exists("bun") {
        "bun"
    } else {
        "npx"
    };

    let dist_dir = dir.join("dist");
    fs::create_dir_all(&dist_dir)?;

    let has_build_script = has_build_script(dir);

    let mut cmd;
    if has_build_script {
        let runner = if bundler == "bun" { "bun" } else { "npm" };
        hprintln!("  Bundling with {runner} run build...");
        cmd = std::process::Command::new(runner);
        cmd.args(["run", "build"]);
    } else if bundler == "bun" {
        hprintln!("  Bundling with bun build...");
        cmd = std::process::Command::new(bundler);
        cmd.args([
            "build",
            "src/index.ts",
            "--outdir",
            "dist",
            "--target",
            "node",
        ]);
    } else {
        hprintln!("  Bundling with npx esbuild...");
        cmd = std::process::Command::new(bundler);
        cmd.args([
            "esbuild",
            "src/index.ts",
            "--bundle",
            "--platform=node",
            "--format=cjs",
            "--outfile=dist/index.js",
        ]);
    }
    cmd.current_dir(dir);

    let program = cmd.get_program().to_string_lossy().to_string();
    let status = cmd
        .status()
        .with_context(|| format!("Failed to run `{program}`"))?;
    if !status.success() {
        anyhow::bail!("TypeScript bundling failed (`{program}` exited {status})");
    }
    Ok(())
}

fn build_python(dir: &Path) -> Result<()> {
    // Generate requirements.lock if uv is available
    if crate::toolchain::exists("uv") && dir.join("requirements.txt").exists() {
        hprintln!("  Generating requirements.lock with uv...");
        let status = std::process::Command::new("uv")
            .args([
                "pip",
                "compile",
                "requirements.txt",
                "-o",
                "requirements.lock",
            ])
            .current_dir(dir)
            .status()
            .context("Failed to run uv pip compile")?;
        if !status.success() {
            hprintln!("  Warning: uv pip compile failed, skipping lock file");
        }
    }
    Ok(())
}

/// Locate the release binary cargo actually produced for this plugin.
///
/// `cargo metadata` is the authority: it knows the real `target-dir` (which
/// `CARGO_TARGET_DIR`, `build.target-dir` or a parent workspace can move) and
/// the real bin-target names (which cargo mangles hyphen→underscore). A plugin
/// whose binary is not where cargo puts it declares `entry.command`; that is
/// treated as an override and wins whenever it resolves to a real file.
/// [`resolve_rust_binary`], except when the bundle is for a platform this
/// machine is not.
///
/// Cross-packing is where a build tool can do real damage quietly. The default
/// target directory holds the **host's** binary; packing it into a
/// `…-windows-x64.astraplugin` produces a bundle that installs on Windows and
/// cannot start, and nothing between here and the user's machine would notice —
/// the digests are all correct, the signature verifies, the manifest is
/// well-formed. Astra already shipped one bug of exactly this shape
/// (`get_download_url` mapping a macOS host to `linux-x64`).
///
/// So a foreign target is resolved **only** from `target/<triple>/release/`,
/// which is where `cargo build --target <triple>` puts it and where nothing
/// else can. If it is not there, the build fails and says how to produce it.
fn resolve_rust_binary_for(dir: &Path, entry_command: &str, target: Target) -> Result<PathBuf> {
    if target.matches_host_os() || target == Target::Noarch {
        return resolve_rust_binary(dir, entry_command);
    }

    let triples: &[&str] = match target {
        Target::LinuxX64 => &["x86_64-unknown-linux-gnu", "x86_64-unknown-linux-musl"],
        Target::WindowsX64 => &["x86_64-pc-windows-msvc", "x86_64-pc-windows-gnu"],
        Target::Noarch => &[],
    };
    let suffix = if target == Target::WindowsX64 { ".exe" } else { "" };

    // The bin name is a property of the package, not of the host, so the host
    // resolution is reused for it and only the directory changes.
    let host_path = cargo_release_binary(dir)?;
    let stem = host_path
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .context("Resolved Rust binary has no file name")?;
    let target_root = host_path
        .parent()
        .and_then(Path::parent)
        .context("Could not find the cargo target directory")?;

    for triple in triples {
        let candidate = target_root
            .join(triple)
            .join("release")
            .join(format!("{stem}{suffix}"));
        if candidate.is_file() {
            return Ok(candidate);
        }
    }

    anyhow::bail!(
        "Cross-packing a {} bundle on {}, and no binary for it exists.\n  Looked in: {}\n\
         Build it first:  cargo build --release --target {}\n\
         Refusing to pack this machine's binary under that platform key — it would install and \
         then fail to start, with every digest and signature correct.",
        target.key(),
        std::env::consts::OS,
        triples
            .iter()
            .map(|t| target_root.join(t).join("release").join(format!("{stem}{suffix}")).display().to_string())
            .collect::<Vec<_>>()
            .join(", "),
        triples.first().copied().unwrap_or("<triple>")
    )
}

fn resolve_rust_binary(dir: &Path, entry_command: &str) -> Result<PathBuf> {
    let from_cargo = cargo_release_binary(dir);

    // The override: `entry.command` relative to the plugin directory. On
    // Windows a manifest written on Linux says `target/release/foo`, so try the
    // executable suffix too rather than failing on a portable manifest.
    if !entry_command.is_empty() {
        let declared = dir.join(entry_command);
        if declared.is_file() {
            return Ok(declared);
        }
        let suffix = std::env::consts::EXE_SUFFIX;
        if !suffix.is_empty() {
            let with_suffix = dir.join(format!("{entry_command}{suffix}"));
            if with_suffix.is_file() {
                return Ok(with_suffix);
            }
        }
    }

    match from_cargo {
        Ok(path) if path.is_file() => Ok(path),
        Ok(path) => anyhow::bail!(
            "No plugin binary found.\n  cargo would produce: {}\n  entry.command says:  {}\n\
             Run `cargo build --release` first.",
            path.display(),
            if entry_command.is_empty() {
                "(not set)".to_string()
            } else {
                dir.join(entry_command).display().to_string()
            }
        ),
        Err(e) => Err(e.context(
            "Could not work out which binary this plugin builds. Set `entry.command` in \
             plugin.toml to the path of the built binary, relative to the plugin directory.",
        )),
    }
}

/// Ask cargo where the release binary for this package lands.
fn cargo_release_binary(dir: &Path) -> Result<PathBuf> {
    let output = std::process::Command::new("cargo")
        .args(["metadata", "--format-version", "1", "--no-deps"])
        .current_dir(dir)
        .output()
        .context("Failed to run `cargo metadata`")?;
    if !output.status.success() {
        anyhow::bail!(
            "`cargo metadata` failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }

    let metadata: serde_json::Value =
        serde_json::from_slice(&output.stdout).context("`cargo metadata` returned invalid JSON")?;

    let target_dir = metadata
        .get("target_directory")
        .and_then(|v| v.as_str())
        .context("`cargo metadata` has no target_directory")?;

    let packages = metadata
        .get("packages")
        .and_then(|v| v.as_array())
        .context("`cargo metadata` has no packages")?;

    // `--no-deps` limits this to the workspace, but a plugin living inside a
    // workspace still sees its siblings — prefer the package rooted at `dir`.
    let mut bins: Vec<String> = Vec::new();
    let mut own_bins: Vec<String> = Vec::new();
    for package in packages {
        let is_own = package
            .get("manifest_path")
            .and_then(|v| v.as_str())
            .map(|p| Path::new(p).parent() == Some(dir))
            .unwrap_or(false);
        let targets = package.get("targets").and_then(|v| v.as_array());
        for target in targets.into_iter().flatten() {
            let is_bin = target
                .get("kind")
                .and_then(|v| v.as_array())
                .map(|kinds| kinds.iter().any(|k| k.as_str() == Some("bin")))
                .unwrap_or(false);
            if !is_bin {
                continue;
            }
            if let Some(name) = target.get("name").and_then(|v| v.as_str()) {
                if is_own {
                    own_bins.push(name.to_string());
                }
                bins.push(name.to_string());
            }
        }
    }

    let candidates = if own_bins.is_empty() { bins } else { own_bins };
    let name = match candidates.len() {
        0 => anyhow::bail!("This cargo package defines no [[bin]] target"),
        1 => candidates.into_iter().next().unwrap(),
        _ => anyhow::bail!(
            "This cargo package defines several binaries ({}). Set `entry.command` in \
             plugin.toml to pick one.",
            candidates.join(", ")
        ),
    };

    Ok(Path::new(target_dir)
        .join("release")
        .join(format!("{name}{}", std::env::consts::EXE_SUFFIX)))
}

fn add_typescript_artifacts(dir: &Path, builder: &mut BundleBuilder) -> Result<()> {
    let dist_dir = dir.join("dist");
    if dist_dir.exists() {
        add_directory_recursive(&dist_dir, builder, dir)?;
    }
    // `package.json` is deliberately not packed. `dist/index.js` is CJS, and
    // Node decides a `.js` file's module type from the nearest package.json —
    // shipping one that says `"type": "module"` would break the very bundle it
    // came with. Its dependencies are already inlined by the bundler.
    Ok(())
}

fn add_python_artifacts(dir: &Path, builder: &mut BundleBuilder) -> Result<()> {
    let src_dir = dir.join("src");
    if src_dir.exists() {
        add_directory_recursive(&src_dir, builder, dir)?;
    }
    for name in &["requirements.lock", "requirements.txt"] {
        let p = dir.join(name);
        if p.exists() && !builder.contains(name) {
            builder.add_path(name, &p)?;
        }
    }
    Ok(())
}

fn add_directory_recursive(target: &Path, builder: &mut BundleBuilder, base: &Path) -> Result<()> {
    // Sorted so the walk order is a property of the tree, not of the file
    // system's directory iteration order. The builder sorts too, but a
    // deterministic walk is what makes the *error* on a duplicate path
    // deterministic as well.
    let walk = WalkDir::new(target)
        .sort_by_file_name()
        .into_iter()
        .filter_entry(|e| {
            !e.file_type().is_dir()
                || !EXCLUDED_DIRS.contains(&e.file_name().to_string_lossy().as_ref())
        });

    for entry in walk {
        let entry = entry.context("Failed to walk the plugin directory")?;
        let path = entry.path();

        // Symlinks are not followed (WalkDir's default) and are not packed: a
        // ZIP symlink entry is a link the extractor would have to resolve
        // against a directory the archive controls.
        if !entry.file_type().is_file() {
            continue;
        }

        let rel = path
            .strip_prefix(base)
            .unwrap_or(path)
            .to_string_lossy()
            .replace('\\', "/");

        // The bundle's own generated entries never come from the tree.
        if rel == PLUGIN_TOML_ENTRY {
            continue;
        }
        // Nor does a bundle from an earlier build sitting in the plugin
        // directory. Without this, the second `astra-plugin build` in a row
        // packs the first one's output, and the third packs the second.
        if rel.ends_with(".astraplugin") {
            continue;
        }
        if builder.contains(&rel) {
            continue;
        }
        builder.add_path(&rel, path)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `spec/icon-formats.yaml` is the list; this file only mirrors it.
    ///
    /// The failure this prevents is silent at both ends. `astra-plugin build`
    /// packs the formats below; `astra-registry`'s `ICON_FORMATS` decides which
    /// ones become a store card. A format in one list and not the other is an
    /// author who added an icon, watched the build pack it, and got a blank
    /// card with no error anywhere to explain it. The registry checks the same
    /// spec file from its side, so the two lists can only ever be wrong
    /// together with this file.
    #[test]
    fn the_packed_icon_formats_are_the_ones_the_spec_declares() {
        let spec = Path::new(env!("CARGO_MANIFEST_DIR")).join("../spec/icon-formats.yaml");
        let text = fs::read_to_string(&spec)
            .unwrap_or_else(|e| panic!("cannot read {}: {e}", spec.display()));
        let declared: Vec<&str> = text
            .lines()
            .map(str::trim)
            .filter(|l| !l.is_empty() && !l.starts_with('#'))
            .collect();

        assert_eq!(
            declared, ICON_FILENAMES,
            "spec/icon-formats.yaml and ICON_FILENAMES disagree. Order matters: it is the \
             preference order both this packer and the registry's picker use when a plugin \
             ships more than one icon."
        );
    }

    /// The substring test this replaces said "yes" to every one of these.
    ///
    /// Each is a real shape of `package.json`: a dependency called `build`
    /// (there is one on npm), a `prebuild` script, `"files": ["build"]`, and
    /// the word in a description. `<bundler> run build` against any of them
    /// fails with npm's "Missing script: build", which reads exactly like a
    /// build error and sent authors looking at their TypeScript.
    #[test]
    fn only_a_real_scripts_build_counts_as_a_build_script() {
        let dir = std::env::temp_dir().join("astra-cli-has-build-script");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let write = |json: &str| std::fs::write(dir.join("package.json"), json).unwrap();

        write(r#"{"scripts":{"build":"esbuild src/index.ts"}}"#);
        assert!(has_build_script(&dir));

        for decoy in [
            r#"{"dependencies":{"build":"^1.0.0"}}"#,
            r#"{"scripts":{"prebuild":"rm -rf dist"}}"#,
            r#"{"files":["build"]}"#,
            r#"{"description":"tools you build with"}"#,
            r#"{"scripts":{"build":"   "}}"#,
            r#"{"scripts":{}}"#,
            r#"{}"#,
            r#"not json at all"#,
        ] {
            write(decoy);
            assert!(
                !has_build_script(&dir),
                "substring-matched a decoy: {decoy}"
            );
        }

        std::fs::remove_file(dir.join("package.json")).unwrap();
        assert!(!has_build_script(&dir), "no package.json, no build script");
        let _ = std::fs::remove_dir_all(&dir);
    }

    const BASE: &str = r#"
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.1"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
actions = true
"#;

    #[test]
    fn stamping_rewrites_the_command_and_records_the_target() {
        let out = stamp_manifest(BASE, "./bin/dice_roller", Target::LinuxX64).unwrap();
        let parsed: toml::Value = toml::from_str(&out).unwrap();
        assert_eq!(
            parsed["entry"]["command"].as_str().unwrap(),
            "./bin/dice_roller"
        );
        assert_eq!(parsed["platform"]["os"][0].as_str().unwrap(), "linux");
        assert_eq!(parsed["platform"]["arch"][0].as_str().unwrap(), "x86_64");
        assert_eq!(parsed["bundle"]["target"].as_str().unwrap(), "linux-x64");
        assert_eq!(parsed["bundle"]["schema"].as_str().unwrap(), SCHEMA);
        // The author's other keys survive the edit.
        assert_eq!(parsed["plugin"]["name"].as_str().unwrap(), "Dice Roller");
    }

    #[test]
    fn noarch_stamps_empty_platform_lists() {
        let out = stamp_manifest(BASE, "node", Target::Noarch).unwrap();
        let parsed: toml::Value = toml::from_str(&out).unwrap();
        assert!(parsed["platform"]["os"].as_array().unwrap().is_empty());
        assert!(parsed["platform"]["arch"].as_array().unwrap().is_empty());
        assert_eq!(parsed["bundle"]["target"].as_str().unwrap(), "noarch");
    }

    #[test]
    fn stamping_overrides_an_authors_wrong_platform_claim() {
        let authored = format!("{BASE}\n[platform]\nos = [\"windows\"]\narch = [\"aarch64\"]\n");
        let out = stamp_manifest(&authored, "./bin/x", Target::LinuxX64).unwrap();
        let parsed: toml::Value = toml::from_str(&out).unwrap();
        assert_eq!(parsed["platform"]["os"].as_array().unwrap().len(), 1);
        assert_eq!(parsed["platform"]["os"][0].as_str().unwrap(), "linux");
        assert_eq!(parsed["platform"]["arch"][0].as_str().unwrap(), "x86_64");
    }

    #[test]
    fn executables_come_from_the_declared_list_not_a_directory_prefix() {
        let toml_str =
            format!("{BASE}\n[bundle]\nexecutables = [\"runtime/python\", \"run.sh\"]\n");
        let manifest: toml::Value = toml::from_str(&toml_str).unwrap();
        let execs = declared_executables(&manifest).unwrap();
        assert!(execs.contains("runtime/python"));
        assert!(execs.contains("run.sh"));
        assert!(!execs.iter().any(|e| e.starts_with("bin/")));
    }

    #[test]
    fn a_traversing_executable_declaration_is_refused() {
        let toml_str = format!("{BASE}\n[bundle]\nexecutables = [\"../../bin/sh\"]\n");
        let manifest: toml::Value = toml::from_str(&toml_str).unwrap();
        assert!(declared_executables(&manifest).is_err());
    }

    #[test]
    fn capabilities_are_the_true_ones_sorted() {
        let manifest: toml::Value = toml::from_str(BASE).unwrap();
        assert_eq!(declared_capabilities(&manifest), vec!["actions", "tools"]);
    }

    /// **3.10's acceptance criterion, as a test.** `build` never claims a trust
    /// outcome it cannot deliver.
    ///
    /// The words are asserted rather than merely the absence of "Signed",
    /// because the failure this guards against is a future edit that reaches
    /// for a reassuring phrase — "verified", "trusted", "authentic" — over an
    /// artifact that has none of those properties. The only positive claim the
    /// note is allowed to make is about the *registry*.
    #[test]
    fn the_build_note_never_claims_a_trust_outcome() {
        let note = trust_note();
        assert!(note.contains("Unsigned."), "{note}");
        assert!(
            note.contains("Local keys are not a trust signal in Astra"),
            "{note}"
        );
        assert!(note.contains("trust comes from the registry"), "{note}");
        assert!(note.contains(TRUST_DOC_URL), "{note}");
        for forbidden in [
            "Signed with",
            "signed with",
            "verified",
            "trusted",
            "authentic",
        ] {
            assert!(
                !note.contains(forbidden),
                "the build note must not say {forbidden:?}: {note}"
            );
        }
    }

    /// `build` holds no reference to a signing key at all — not a call, not an
    /// import. The 3.10 change is that signing *moved*, and a module that still
    /// knew how to sign would be one careless `if` away from doing it again.
    #[test]
    fn build_does_not_link_the_signing_path() {
        let src = include_str!("build.rs");
        for forbidden in ["load_signing_key", "append_legacy_signature", "SIGNATURE"] {
            // The test module names them; the code above it must not.
            let code = src.split("#[cfg(test)]").next().unwrap();
            assert!(
                !code.contains(forbidden),
                "build.rs must not reference {forbidden:?} outside its tests"
            );
        }
    }

    /// The regression this file's `declared_permissions` was written wrong for.
    ///
    /// It read `reason` out of each entry by hand, so `types` and `scopes` never
    /// left `plugin.toml`. Reading the section with the daemon's own
    /// deserialiser is what makes the packer structurally unable to know fewer
    /// fields than the daemon does.
    #[test]
    fn the_whole_permission_request_survives_plugin_toml() {
        let manifest: toml::Value = toml::from_str(
            r#"
            [permissions]
            fire_trigger     = { reason = "Fires the on_dice_roll trigger you configure" }
            subscribe_events = { types = ["command_completed", "tool_started"], reason = "Watches" }
            set_variable     = { scopes = ["plugin"] }
            "#,
        )
        .unwrap();

        let packed = declared_permissions(&manifest).unwrap();
        assert_eq!(packed.len(), 3);
        assert_eq!(
            packed["subscribe_events"].types,
            vec!["command_completed".to_string(), "tool_started".to_string()],
            "subscribe_events.types is an allowlist the daemon enforces; dropping it \
             grants the permission over no events at all"
        );
        assert_eq!(packed["set_variable"].scopes, vec!["plugin".to_string()]);
        assert_eq!(
            packed["fire_trigger"].reason,
            "Fires the on_dice_roll trigger you configure"
        );
        // A bare `{reason}` request carries no empty lists into the hash.
        assert!(packed["fire_trigger"].types.is_empty());
        assert!(packed["fire_trigger"].scopes.is_empty());
    }

    /// An id this build does not recognise is packed anyway. `permissions_hash`
    /// covers the bytes three repositories hash, so dropping one here would make
    /// an old CLI and a new daemon disagree about what the author declared —
    /// and the id may be one the *user's* daemon knows perfectly well.
    #[test]
    fn an_unknown_permission_id_is_packed_rather_than_dropped() {
        let manifest: toml::Value =
            toml::from_str("[permissions]\ntime_travel = { reason = \"Nope\" }\n").unwrap();
        let packed = declared_permissions(&manifest).unwrap();
        assert_eq!(packed["time_travel"].reason, "Nope");
    }

    /// An absent section is the empty set, which §5.6 reads as default-deny.
    #[test]
    fn no_permissions_section_is_the_empty_set() {
        let manifest: toml::Value = toml::from_str("[capabilities]\ntools = true\n").unwrap();
        assert!(declared_permissions(&manifest).unwrap().is_empty());
    }

    #[test]
    fn interpreted_languages_default_to_noarch() {
        assert_eq!(resolve_target(None, "typescript").unwrap(), Target::Noarch);
        assert_eq!(resolve_target(None, "python").unwrap(), Target::Noarch);
        assert_eq!(
            resolve_target(Some(Target::WindowsX64), "rust").unwrap(),
            Target::WindowsX64
        );
    }
}
