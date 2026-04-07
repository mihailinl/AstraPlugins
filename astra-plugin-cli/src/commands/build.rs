//! `astra-plugin build` — package a plugin into a distributable .astraplugin archive.

use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::Path;

use anyhow::{Context, Result};
use walkdir::WalkDir;
use zip::write::SimpleFileOptions;

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
    match language.as_str() {
        "rust" => build_rust(&dir)?,
        "typescript" | "ts" => build_typescript(&dir)?,
        "python" | "py" => build_python(&dir)?,
        _ => println!("  No build step for language '{language}'"),
    }

    // Create ZIP archive
    let file = File::create(output_path)
        .with_context(|| format!("Failed to create {}", output_path.display()))?;
    let mut zip = zip::ZipWriter::new(file);
    let options = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    // For Rust: read entry.command, resolve the binary, pack into bin/, rewrite manifest
    // For others: include plugin.toml as-is
    let entry_command = manifest
        .get("entry")
        .and_then(|e| e.get("command"))
        .and_then(|v| v.as_str())
        .unwrap_or("");

    match language.as_str() {
        "rust" => {
            // Resolve the binary from entry.command relative to plugin dir
            let bin_path = dir.join(entry_command);
            if !bin_path.exists() {
                anyhow::bail!(
                    "Binary not found at '{}' (from entry.command = '{}')",
                    bin_path.display(),
                    entry_command
                );
            }
            let bin_name = bin_path.file_name().unwrap().to_string_lossy();
            let archive_bin_path = format!("bin/{}", bin_name);

            // Write modified plugin.toml with command pointing to bin/ in archive
            let modified_manifest = manifest_str.replace(
                &format!("command = \"{}\"", entry_command),
                &format!("command = \"./bin/{}\"", bin_name),
            );
            zip.start_file("plugin.toml", options)?;
            zip.write_all(modified_manifest.as_bytes())?;

            // Pack the binary
            let mut buf = Vec::new();
            File::open(&bin_path)?.read_to_end(&mut buf)?;
            zip.start_file(&archive_bin_path, options)?;
            zip.write_all(&buf)?;
            println!("  Added: {}", archive_bin_path);
        }
        _ => {
            // Non-Rust: include plugin.toml unchanged
            zip.start_file("plugin.toml", options)?;
            zip.write_all(manifest_str.as_bytes())?;
        }
    }

    // Include files based on language
    match language.as_str() {
        "rust" => {} // already handled above
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

    let file_size = fs::metadata(output_path)?.len();
    println!(
        "  Built: {} ({:.1} KB)",
        output_path.display(),
        file_size as f64 / 1024.0
    );

    Ok(())
}

fn detect_language(dir: &Path) -> String {
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

fn add_rust_artifacts(
    dir: &Path,
    zip: &mut zip::ZipWriter<File>,
    options: SimpleFileOptions,
) -> Result<()> {
    // Include the release binary from target/release/
    let target_dir = dir.join("target").join("release");
    if target_dir.exists() {
        let bin_dir_name = "bin";
        for entry in fs::read_dir(&target_dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_file() {
                let name = path.file_name().unwrap().to_string_lossy();
                // Include executables (no extension on Linux, .exe on Windows)
                let is_exe = name.ends_with(".exe")
                    || (!name.contains('.') && is_executable_unix(&path));
                if is_exe {
                    let mut buf = Vec::new();
                    File::open(&path)?.read_to_end(&mut buf)?;
                    zip.start_file(format!("{bin_dir_name}/{name}"), options)?;
                    zip.write_all(&buf)?;
                    println!("  Added: {bin_dir_name}/{name}");
                }
            }
        }
    }
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

#[cfg(unix)]
fn is_executable_unix(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    if let Ok(meta) = path.metadata() {
        meta.permissions().mode() & 0o111 != 0
    } else {
        false
    }
}

#[cfg(not(unix))]
fn is_executable_unix(_path: &Path) -> bool {
    false
}
