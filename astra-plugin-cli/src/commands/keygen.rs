//! `astra-plugin keygen` — generate an Ed25519 keypair for plugin signing.

use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result};
use base64::{Engine, engine::general_purpose};
use ed25519_dalek::SigningKey;
use rand::rngs::OsRng;

/// Get the plugin keys directory (~/.astra/plugin-keys/).
fn keys_dir() -> Result<PathBuf> {
    let home = directories::BaseDirs::new()
        .context("Failed to determine home directory")?;
    let dir = home.home_dir().join(".astra").join("plugin-keys");
    Ok(dir)
}

pub fn run(force: bool) -> Result<()> {
    let dir = keys_dir()?;
    let private_path = dir.join("private.key");
    let public_path = dir.join("public.key");

    if private_path.exists() && !force {
        println!("Keypair already exists at:");
        println!("  Private: {}", private_path.display());
        println!("  Public:  {}", public_path.display());
        println!("\nUse --force to overwrite.");
        return Ok(());
    }

    fs::create_dir_all(&dir)
        .with_context(|| format!("Failed to create keys directory: {}", dir.display()))?;

    // Generate Ed25519 keypair
    let signing_key = SigningKey::generate(&mut OsRng);
    let verifying_key = signing_key.verifying_key();

    // Save private key (raw 32 bytes, base64 encoded)
    let private_b64 = general_purpose::STANDARD.encode(
        signing_key.to_bytes(),
    );
    fs::write(&private_path, &private_b64)
        .with_context(|| format!("Failed to write private key: {}", private_path.display()))?;

    // Save public key (raw 32 bytes, base64 encoded)
    let public_b64 = general_purpose::STANDARD.encode(
        verifying_key.to_bytes(),
    );
    fs::write(&public_path, &public_b64)
        .with_context(|| format!("Failed to write public key: {}", public_path.display()))?;

    println!("Generated Ed25519 keypair:");
    println!("  Private: {}", private_path.display());
    println!("  Public:  {}", public_path.display());
    println!("\nPublic key (share this for verification):");
    println!("  {}", public_b64);

    Ok(())
}

/// Load the signing key from disk. Returns None if not found.
pub fn load_signing_key() -> Result<Option<SigningKey>> {
    let dir = keys_dir()?;
    let private_path = dir.join("private.key");

    if !private_path.exists() {
        return Ok(None);
    }

    let b64 = fs::read_to_string(&private_path)
        .with_context(|| format!("Failed to read private key: {}", private_path.display()))?;
    let bytes = general_purpose::STANDARD.decode(
        b64.trim(),
    )
    .context("Invalid base64 in private key file")?;

    let key_bytes: [u8; 32] = bytes
        .try_into()
        .map_err(|_| anyhow::anyhow!("Private key must be 32 bytes"))?;

    Ok(Some(SigningKey::from_bytes(&key_bytes)))
}
