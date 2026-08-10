//! `astra-plugin build` — package a plugin into a distributable .astraplugin archive.

use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use base64::{Engine, engine::general_purpose};
use walkdir::WalkDir;
use zip::write::SimpleFileOptions;

/// Where a packed binary lands inside the archive, and what `entry.command` is
/// rewritten to point at.
const ARCHIVE_BIN_DIR: &str = "bin";

pub fn run(path: &str, output: Option<&str>) -> Result<()> {
    let dir = Path::new(path).canonicalize().context("Invalid path")?;
    let manifest_path = dir.join("plugin.toml");

    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }

    // Parse manifest to get plugin ID and detect language
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

    let language = detect_language(&dir);

    let output_name = output
        .map(String::from)
        .unwrap_or_else(|| format!("{plugin_id}-{version}.astraplugin"));
    let output_path = Path::new(&output_name);

    println!("Building plugin '{plugin_id}' v{version} ({language})...");

    // Language-specific pre-build step
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
        Some(resolve_rust_binary(&dir, entry_command)?)
    } else {
        None
    };

    // For Rust the binary moves into `bin/` inside the archive, so the manifest
    // the daemon reads must point there instead of at the author's target dir.
    let packed_manifest = match &rust_binary {
        Some(bin) => {
            let bin_name = bin
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .context("Resolved Rust binary has no file name")?;
            rewrite_entry_command(&manifest_str, &format!("./{ARCHIVE_BIN_DIR}/{bin_name}"))?
        }
        None => manifest_str.clone(),
    };

    // Create ZIP archive
    if let Some(parent) = output_path.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create output directory {}", parent.display()))?;
    }
    let file = File::create(output_path)
        .with_context(|| format!("Failed to create {}", output_path.display()))?;
    let mut zip = zip::ZipWriter::new(file);
    let options = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    zip.start_file("plugin.toml", options)?;
    zip.write_all(packed_manifest.as_bytes())?;

    if let Some(bin) = &rust_binary {
        add_rust_artifacts(bin, &mut zip, options)?;
    }

    // Include ui/ directory if it exists (for all languages)
    let ui_dir = dir.join("ui");
    if ui_dir.exists() {
        add_directory_recursive(&ui_dir, &mut zip, options, &dir)?;
    }

    // Include locales/ directory if it exists (for plugin i18n)
    let locales_dir = dir.join("locales");
    if locales_dir.exists() {
        add_directory_recursive(&locales_dir, &mut zip, options, &dir)?;
    }

    // Include files based on language
    match language.as_str() {
        "rust" => {} // binary already handled above
        "typescript" | "ts" => add_typescript_artifacts(&dir, &mut zip, options)?,
        "python" | "py" => add_python_artifacts(&dir, &mut zip, options)?,
        _ => add_directory_recursive(&dir, &mut zip, options, &dir)?,
    }

    // Include optional files
    for name in &["icon.png", "icon.svg", "README.md", "LICENSE"] {
        let p = dir.join(name);
        if p.exists() {
            let content = fs::read(&p)?;
            zip.start_file(*name, options)?;
            zip.write_all(&content)?;
        }
    }

    zip.finish()?;

    // Sign the archive if a signing key is available
    match super::keygen::load_signing_key() {
        Ok(Some(signing_key)) => {
            use ed25519_dalek::Signer;
            use sha2::{Digest, Sha256};

            // Read the finished ZIP and hash individual entries
            // (must match daemon's verify_signature which hashes filename + content per entry)
            let zip_bytes = fs::read(output_path)
                .context("Failed to read built archive for signing")?;
            let reader = std::io::Cursor::new(&zip_bytes);
            let mut read_archive = zip::ZipArchive::new(reader)
                .context("Failed to re-open archive for hashing")?;

            let mut hasher = Sha256::new();
            for i in 0..read_archive.len() {
                let mut entry = read_archive.by_index(i)?;
                let name = entry.name().to_string();
                hasher.update(name.as_bytes());
                let mut buf = Vec::new();
                entry.read_to_end(&mut buf)?;
                hasher.update(&buf);
            }
            let digest = hasher.finalize();

            // Sign the hash
            let signature = signing_key.sign(&digest);
            let public_key = signing_key.verifying_key();

            // Re-open the ZIP and add SIGNATURE + PUBKEY entries
            let file = fs::OpenOptions::new()
                .read(true)
                .write(true)
                .open(output_path)?;
            let mut archive = zip::ZipWriter::new_append(file)
                .context("Failed to open archive for signing")?;

            let sig_b64 = general_purpose::STANDARD.encode(
                signature.to_bytes(),
            );
            let pub_b64 = general_purpose::STANDARD.encode(
                public_key.to_bytes(),
            );

            archive.start_file("SIGNATURE", options)?;
            archive.write_all(sig_b64.as_bytes())?;

            archive.start_file("PUBKEY", options)?;
            archive.write_all(pub_b64.as_bytes())?;

            archive.finish()?;
            println!("  Signed with Ed25519 key");
        }
        Ok(None) => {
            println!("  Warning: No signing key found. Plugin will be unsigned.");
            println!("  Run 'astra-plugin keygen' to generate a signing keypair.");
        }
        Err(e) => {
            println!("  Warning: Failed to load signing key: {}", e);
        }
    }

    let file_size = fs::metadata(output_path)?.len();
    println!(
        "  Built: {} ({:.1} KB)",
        output_path.display(),
        file_size as f64 / 1024.0
    );

    Ok(())
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
            println!("  No build step for language '{language}'");
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
    println!("  Running cargo build --release...");
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

fn build_typescript(dir: &Path) -> Result<()> {
    // Try bun, fallback to npx esbuild
    let bundler = if which_exists("bun") {
        "bun"
    } else {
        "npx"
    };
    println!("  Bundling with {bundler}...");

    let dist_dir = dir.join("dist");
    fs::create_dir_all(&dist_dir)?;

    // Use the project's own build script if available
    let has_build_script = dir.join("package.json").exists()
        && fs::read_to_string(dir.join("package.json"))
            .map(|s| s.contains("\"build\""))
            .unwrap_or(false);

    let mut cmd;
    if has_build_script {
        cmd = std::process::Command::new(bundler);
        cmd.args(["run", "build"]);
    } else if bundler == "bun" {
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

    let status = cmd.status().context("Failed to run bundler")?;
    if !status.success() {
        anyhow::bail!("TypeScript bundling failed");
    }
    Ok(())
}

fn build_python(dir: &Path) -> Result<()> {
    // Generate requirements.lock if uv is available
    if which_exists("uv") && dir.join("requirements.txt").exists() {
        println!("  Generating requirements.lock with uv...");
        let status = std::process::Command::new("uv")
            .args(["pip", "compile", "requirements.txt", "-o", "requirements.lock"])
            .current_dir(dir)
            .status()
            .context("Failed to run uv pip compile")?;
        if !status.success() {
            println!("  Warning: uv pip compile failed, skipping lock file");
        }
    }
    Ok(())
}

fn which_exists(cmd: &str) -> bool {
    std::process::Command::new(cmd)
        .arg("--version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .is_ok()
}

/// Locate the release binary cargo actually produced for this plugin.
///
/// `cargo metadata` is the authority: it knows the real `target-dir` (which
/// `CARGO_TARGET_DIR`, `build.target-dir` or a parent workspace can move) and
/// the real bin-target names (which cargo mangles hyphen→underscore). A plugin
/// whose binary is not where cargo puts it declares `entry.command`; that is
/// treated as an override and wins whenever it resolves to a real file.
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

/// Rewrite `entry.command` in a plugin.toml, preserving everything else.
///
/// A textual `replace` used to do this; it silently no-oped on any manifest
/// whose spacing or quoting differed from the template's, shipping an archive
/// whose command pointed at the author's `target/` directory.
fn rewrite_entry_command(manifest_str: &str, command: &str) -> Result<String> {
    let mut doc: toml_edit::DocumentMut = manifest_str
        .parse()
        .context("Failed to parse plugin.toml for rewriting")?;
    doc["entry"]["command"] = toml_edit::value(command);
    Ok(doc.to_string())
}

/// Pack the resolved release binary into `bin/` inside the archive.
fn add_rust_artifacts(
    binary: &Path,
    zip: &mut zip::ZipWriter<File>,
    options: SimpleFileOptions,
) -> Result<()> {
    let name = binary
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .context("Resolved Rust binary has no file name")?;
    let archive_path = format!("{ARCHIVE_BIN_DIR}/{name}");

    let mut buf = Vec::new();
    File::open(binary)
        .with_context(|| format!("Failed to open {}", binary.display()))?
        .read_to_end(&mut buf)?;

    // The extractor on the other end has to be able to exec this; a ZIP entry
    // written with the default mode comes out 0644 on Unix.
    zip.start_file(&archive_path, options.unix_permissions(0o755))?;
    zip.write_all(&buf)?;
    println!("  Added: {archive_path}");
    Ok(())
}

fn add_typescript_artifacts(
    dir: &Path,
    zip: &mut zip::ZipWriter<File>,
    options: SimpleFileOptions,
) -> Result<()> {
    let dist_dir = dir.join("dist");
    if dist_dir.exists() {
        add_directory_recursive(&dist_dir, zip, options, dir)?;
    }
    Ok(())
}

fn add_python_artifacts(
    dir: &Path,
    zip: &mut zip::ZipWriter<File>,
    options: SimpleFileOptions,
) -> Result<()> {
    // Include src/ directory
    let src_dir = dir.join("src");
    if src_dir.exists() {
        add_directory_recursive(&src_dir, zip, options, dir)?;
    }
    // Include requirements.lock if exists
    for name in &["requirements.lock", "requirements.txt"] {
        let p = dir.join(name);
        if p.exists() {
            let content = fs::read(&p)?;
            zip.start_file(*name, options)?;
            zip.write_all(&content)?;
        }
    }
    Ok(())
}

fn add_directory_recursive(
    target: &Path,
    zip: &mut zip::ZipWriter<File>,
    options: SimpleFileOptions,
    base: &Path,
) -> Result<()> {
    for entry in WalkDir::new(target).into_iter().filter_map(|e| e.ok()) {
        let path = entry.path();
        if path.is_file() {
            let rel = path
                .strip_prefix(base)
                .unwrap_or(path)
                .to_string_lossy()
                .replace('\\', "/");

            // Skip common build artifacts
            if rel.starts_with("target/")
                || rel.starts_with("node_modules/")
                || rel.starts_with(".git/")
                || rel.starts_with("__pycache__/")
                || rel.starts_with(".venv/")
            {
                continue;
            }

            let mut buf = Vec::new();
            File::open(path)?.read_to_end(&mut buf)?;
            zip.start_file(&rel, options)?;
            zip.write_all(&buf)?;
        }
    }
    Ok(())
}
