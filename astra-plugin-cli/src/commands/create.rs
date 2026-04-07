//! `astra-plugin create` — scaffold a new plugin project.

use std::fs;
use std::path::Path;

use anyhow::{Context, Result};

use crate::templates;

pub fn run(name: &str, lang: &str, capabilities: &[&str], out_dir: &str) -> Result<()> {
    // Validate plugin name
    if !name
        .chars()
        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
    {
        anyhow::bail!("Plugin name must be lowercase alphanumeric with hyphens");
    }

    let lang = lang.to_lowercase();
    if !["rust", "python", "py", "typescript", "ts"].contains(&lang.as_str()) {
        anyhow::bail!("Supported languages: rust, python (py), typescript (ts)");
    }

    let valid_caps = [
        "tools",
        "tts",
        "stt",
        "ai_provider",
        "actions",
        "triggers",
        "client",
        "event_handlers",
        "ui_panels",
    ];
    for cap in capabilities {
        if !valid_caps.contains(cap) {
            anyhow::bail!("Unknown capability '{cap}'. Valid: {}", valid_caps.join(", "));
        }
    }

    let out_path = Path::new(out_dir);
    if out_path.exists() {
        anyhow::bail!("Directory '{}' already exists", out_dir);
    }

    fs::create_dir_all(out_path)
        .with_context(|| format!("Failed to create directory '{}'", out_dir))?;

    // Generate plugin.toml
    let manifest = templates::generate_manifest(name, &lang, capabilities);
    fs::write(out_path.join("plugin.toml"), manifest)?;

    // Copy proto file
    let proto_dir = out_path.join("proto");
    fs::create_dir_all(&proto_dir)?;
    fs::write(proto_dir.join("plugin.proto"), templates::PLUGIN_PROTO)?;

    // Generate language-specific files
    match lang.as_str() {
        "rust" => generate_rust_project(out_path, name, capabilities)?,
        "python" | "py" => generate_python_project(out_path, name, capabilities)?,
        "typescript" | "ts" => generate_typescript_project(out_path, name, capabilities)?,
        _ => unreachable!(),
    }

    // Generate README
    let readme = templates::generate_readme(name, &lang, capabilities);
    fs::write(out_path.join("README.md"), readme)?;

    // Generate .gitignore
    let gitignore = templates::generate_gitignore(&lang);
    fs::write(out_path.join(".gitignore"), gitignore)?;

    println!("Created plugin project '{name}' at {out_dir}/");
    println!("Language: {lang}");
    println!("Capabilities: {}", capabilities.join(", "));
    println!();
    println!("Next steps:");
    match lang.as_str() {
        "rust" => {
            println!("  cd {out_dir}");
            println!("  cargo build");
            println!("  astra-plugin dev .");
        }
        "python" | "py" => {
            println!("  cd {out_dir}");
            println!("  pip install -r requirements.txt");
            println!("  astra-plugin dev .");
        }
        "typescript" | "ts" => {
            println!("  cd {out_dir}");
            println!("  npm install");
            println!("  astra-plugin dev .");
        }
        _ => {}
    }

    Ok(())
}

fn generate_rust_project(out_path: &Path, name: &str, capabilities: &[&str]) -> Result<()> {
    let src_dir = out_path.join("src");
    fs::create_dir_all(&src_dir)?;

    let cargo_toml = templates::rust::generate_cargo_toml(name);
    fs::write(out_path.join("Cargo.toml"), cargo_toml)?;

    let main_rs = templates::rust::generate_main_rs(name, capabilities);
    fs::write(src_dir.join("main.rs"), main_rs)?;

    Ok(())
}

fn generate_python_project(out_path: &Path, name: &str, capabilities: &[&str]) -> Result<()> {
    let src_dir = out_path.join("src");
    fs::create_dir_all(&src_dir)?;

    let plugin_py = templates::python::generate_plugin_py(name, capabilities);
    fs::write(src_dir.join("plugin.py"), plugin_py)?;

    let requirements = templates::python::generate_requirements();
    fs::write(out_path.join("requirements.txt"), requirements)?;

    let pyproject = templates::python::generate_pyproject(name);
    fs::write(out_path.join("pyproject.toml"), pyproject)?;

    Ok(())
}

fn generate_typescript_project(out_path: &Path, name: &str, capabilities: &[&str]) -> Result<()> {
    let src_dir = out_path.join("src");
    fs::create_dir_all(&src_dir)?;

    let index_ts = templates::typescript::generate_index_ts(name, capabilities);
    fs::write(src_dir.join("index.ts"), index_ts)?;

    let package_json = templates::typescript::generate_package_json(name);
    fs::write(out_path.join("package.json"), package_json)?;

    let tsconfig = templates::typescript::generate_tsconfig();
    fs::write(out_path.join("tsconfig.json"), tsconfig)?;

    Ok(())
}
