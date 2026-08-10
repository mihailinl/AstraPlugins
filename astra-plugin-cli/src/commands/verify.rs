//! `astra-plugin verify` — read a `.astraplugin` back and check every
//! invariant the format promises.
//!
//! This is the author-side half of what the daemon does on install, running the
//! same code in [`crate::bundle`]. Its job is to make a bundle that would fail
//! to install fail *here*, on the machine that built it, with the file in front
//! of the person who can fix it.
//!
//! It also prints the two digests a release needs: `artifact sha256` (the
//! attestation subject and the registry's `sha256` field, over the whole file)
//! and the domain-separated `manifest digest`.

use std::path::Path;

use anyhow::{Context, Result};

use crate::bundle::{Bundle, UNLISTED_ENTRIES};

pub fn run(path: &str, json: bool) -> Result<()> {
    let file = Path::new(path);
    if !file.is_file() {
        anyhow::bail!("No such file: {}", file.display());
    }

    let bundle = Bundle::open(file)
        .with_context(|| format!("{} is not a valid v2 bundle", file.display()))?;

    let expected_name = bundle.manifest.artifact_name()?;
    let actual_name = file
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();

    if json {
        // Machine-readable, for the release workflow's reproducibility canary
        // and for whatever writes the registry's version record.
        let report = serde_json::json!({
            "file": file.display().to_string(),
            "artifact_sha256": bundle.artifact_sha256,
            "size": bundle.artifact_size,
            "manifest_digest": bundle.manifest_digest,
            "plugin_id": bundle.manifest.plugin_id,
            "version": bundle.manifest.version,
            "target": bundle.manifest.target()?.key(),
            "platform": bundle.manifest.platform,
            "protocol": bundle.manifest.protocol,
            "min_astra_version": bundle.manifest.min_astra_version,
            "capabilities": bundle.manifest.capabilities,
            "permissions_hash": bundle.manifest.permissions_hash,
            "entry": bundle.manifest.entry,
            "file_count": bundle.manifest.files.len(),
            "expected_name": expected_name,
            "legacy_signature": bundle.signed,
        });
        println!("{}", serde_json::to_string_pretty(&report)?);
        return Ok(());
    }

    println!("{}", file.display());
    println!("  schema:          {}", bundle.manifest.schema);
    println!(
        "  plugin:          {} v{}",
        bundle.manifest.plugin_id, bundle.manifest.version
    );
    println!(
        "  target:          {} (os={}, arch={})",
        bundle.manifest.target()?.key(),
        bundle.manifest.platform.os,
        bundle.manifest.platform.arch
    );
    println!("  protocol:        {}", bundle.manifest.protocol);
    if !bundle.manifest.min_astra_version.is_empty() {
        println!("  min astra:       {}", bundle.manifest.min_astra_version);
    }
    println!(
        "  capabilities:    {}",
        if bundle.manifest.capabilities.is_empty() {
            "(none)".to_string()
        } else {
            bundle.manifest.capabilities.join(", ")
        }
    );
    println!(
        "  entry:           {} {}",
        bundle.manifest.entry.command,
        bundle.manifest.entry.args.join(" ")
    );
    println!("  permissions:     {}", bundle.manifest.permissions_hash);
    println!("  artifact sha256: {}", bundle.artifact_sha256);
    println!("  manifest digest: {}", bundle.manifest_digest);
    println!(
        "  size:            {} bytes ({:.1} KB)",
        bundle.artifact_size,
        bundle.artifact_size as f64 / 1024.0
    );
    println!(
        "  legacy in-ZIP signature: {}",
        if bundle.signed {
            "present (retiring)"
        } else {
            "absent"
        }
    );

    println!("\n  {} listed files:", bundle.manifest.files.len());
    for entry in &bundle.manifest.files {
        // `chars().take`, not a byte slice: this prints a value that came out
        // of a file, and a hostile manifest is not obliged to make it 64 hex
        // characters. A verifier must not panic on the input it is verifying.
        let short: String = entry.sha256.chars().take(16).collect();
        println!(
            "    {} {:>10}  {}  {}",
            entry.mode, entry.size, short, entry.path
        );
    }

    let unlisted: Vec<&str> = bundle
        .entries
        .iter()
        .map(|e| e.path.as_str())
        .filter(|p| UNLISTED_ENTRIES.contains(p))
        .collect();
    println!(
        "  {} unlisted entries: {}",
        unlisted.len(),
        unlisted.join(", ")
    );

    println!("\n  OK — MANIFEST.json is entry 0 and stored, the file list is exhaustive in both");
    println!("       directions, and every listed digest, size and mode matches the archive.");

    if actual_name != expected_name {
        // A warning, not a failure: `-o` exists and a local build may name the
        // file anything. What is published must match, and the release workflow
        // is where that becomes fatal.
        println!(
            "\n  Warning: this file is named '{actual_name}', but a published bundle for this \
             manifest must be named '{expected_name}' — that is the name the registry's platform \
             key is derived from."
        );
    }

    Ok(())
}
