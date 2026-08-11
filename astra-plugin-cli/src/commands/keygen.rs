//! `astra-plugin keygen` — generate an Ed25519 keypair for plugin signing.

use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result};
use base64::{Engine, engine::general_purpose};
use ed25519_dalek::SigningKey;
use rand::rngs::OsRng;
use crate::hprintln;

/// Get the plugin keys directory (~/.astra/plugin-keys/).
fn keys_dir() -> Result<PathBuf> {
    let home = directories::BaseDirs::new().context("Failed to determine home directory")?;
    let dir = home.home_dir().join(".astra").join("plugin-keys");
    Ok(dir)
}

/// Where `sign` looks for the OPTIONAL private key, if this machine has a home
/// directory at all. `None` is not an error: no key is needed to publish.
pub fn default_key_path() -> Option<PathBuf> {
    keys_dir().ok().map(|d| d.join("private.key"))
}

pub fn run(force: bool) -> Result<()> {
    let dir = keys_dir()?;
    let private_path = dir.join("private.key");
    let public_path = dir.join("public.key");

    if private_path.exists() && !force {
        hprintln!("Keypair already exists at:");
        hprintln!("  Private: {}", private_path.display());
        hprintln!("  Public:  {}", public_path.display());
        hprintln!("\nUse --force to overwrite.");
        return Ok(());
    }

    ensure_private_dir(&dir)
        .with_context(|| format!("Failed to create keys directory: {}", dir.display()))?;

    // Generate Ed25519 keypair
    let signing_key = SigningKey::generate(&mut OsRng);
    let verifying_key = signing_key.verifying_key();

    // Save private key (raw 32 bytes, base64 encoded)
    let private_b64 = general_purpose::STANDARD.encode(signing_key.to_bytes());
    write_secret_file(&private_path, &private_b64)
        .with_context(|| format!("Failed to write private key: {}", private_path.display()))?;

    // Save public key (raw 32 bytes, base64 encoded)
    let public_b64 = general_purpose::STANDARD.encode(verifying_key.to_bytes());
    fs::write(&public_path, &public_b64)
        .with_context(|| format!("Failed to write public key: {}", public_path.display()))?;

    hprintln!("Generated Ed25519 keypair:");
    hprintln!("  Private: {}", private_path.display());
    hprintln!("  Public:  {}", public_path.display());
    hprintln!("\nPublic key (base64):");
    hprintln!("  {public_b64}");
    // The keypair is optional and does not gate publishing. Saying so here is
    // the difference between an author who treats `keygen` as step one of
    // shipping and one who knows it is a defence-in-depth extra: `build` does
    // not read this key, and Astra installs a plugin on the strength of the
    // registry record over sha256(whole file), not on any key the author holds.
    hprintln!(
        "\nThis key is optional and is not what makes Astra trust a plugin. `astra-plugin build`\n\
         does not use it; only `astra-plugin sign` does, and only as a second factor against a\n\
         GitHub account takeover. You can publish without ever running this command."
    );

    Ok(())
}

/// Create a directory and make it owner-only.
///
/// SECURITY(key-at-rest): the directory holds the plugin signing seed. A
/// world-readable (0755, the default umask result) directory lets any other
/// local user list and read it. 0700 keeps the tree owner-only.
fn ensure_private_dir(dir: &std::path::Path) -> std::io::Result<()> {
    fs::create_dir_all(dir)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700))?;
    }
    #[cfg(windows)]
    {
        restrict_to_owner_windows(dir);
    }
    Ok(())
}

/// Write a file containing a secret with owner-only permissions.
///
/// SECURITY(key-at-rest): this is the Ed25519 seed the docs call secret —
/// whoever reads it can sign a bundle as this author. `fs::write` used to leave
/// it at the process umask default, which is 0644 on a stock Linux install.
/// Mirrors `write_secret_file` in the daemon (`Astra/.../astra-daemon/src/main.rs`):
/// create at 0600 and re-assert, because the mode on `OpenOptions` applies only
/// to a freshly-created file and `--force` overwrites an existing one.
fn write_secret_file(path: &std::path::Path, contents: &str) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        use std::io::Write;
        use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
        let mut f = fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(path)?;
        f.write_all(contents.as_bytes())?;
        f.flush()?;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
        Ok(())
    }
    #[cfg(not(unix))]
    {
        fs::write(path, contents)?;
        #[cfg(windows)]
        restrict_to_owner_windows(path);
        Ok(())
    }
}

/// Replace a path's inherited ACL with an owner-only DACL.
///
/// SECURITY(key-at-rest): the Unix mode has no Windows equivalent — a file
/// under the user profile inherits whatever the profile grants, which on a
/// domain-joined or multi-admin machine is not always the owner alone.
/// `icacls /inheritance:r /grant:r <user>:F` is the same edit the platform's
/// own tooling makes, and keeps this crate free of a `windows-sys` dependency
/// for one call. Best-effort: a failure is reported, not fatal, because the
/// default profile ACL is already owner-only on a stock install.
#[cfg(windows)]
fn restrict_to_owner_windows(path: &std::path::Path) {
    let user = match std::env::var("USERNAME") {
        Ok(u) if !u.is_empty() => u,
        _ => {
            eprintln!(
                "  Warning: USERNAME is unset; leaving inherited permissions on {}",
                path.display()
            );
            return;
        }
    };
    let result = std::process::Command::new("icacls")
        .arg(path)
        .arg("/inheritance:r")
        .arg("/grant:r")
        .arg(format!("{user}:F"))
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status();
    match result {
        Ok(status) if status.success() => {}
        _ => eprintln!(
            "  Warning: could not restrict permissions on {} — check it is readable only by you",
            path.display()
        ),
    }
}

/// Load the signing key from the default location. `None` if there is none.
///
/// Since 3.10 the only caller is `astra-plugin sign`. `build` used to call it
/// too, which is how a bundle's contents came to depend on whether a file
/// existed in the builder's home directory.
pub fn load_signing_key() -> Result<Option<SigningKey>> {
    let dir = keys_dir()?;
    load_signing_key_at(&dir.join("private.key"))
}

/// Load the seed from an explicit path — `astra-plugin sign --key`.
///
/// A path and not the key: a base64 seed passed as an argument is visible in
/// `ps` to every user on the machine, is written to the shell history, and is
/// echoed by CI log collectors. This crate offers no way to pass one inline.
pub fn load_signing_key_at(private_path: &std::path::Path) -> Result<Option<SigningKey>> {
    if !private_path.exists() {
        return Ok(None);
    }

    let b64 = fs::read_to_string(private_path)
        .with_context(|| format!("Failed to read private key: {}", private_path.display()))?;
    let bytes = general_purpose::STANDARD
        .decode(b64.trim())
        .context("Invalid base64 in private key file")?;

    let key_bytes: [u8; 32] = bytes
        .try_into()
        .map_err(|_| anyhow::anyhow!("Private key must be 32 bytes"))?;

    Ok(Some(SigningKey::from_bytes(&key_bytes)))
}
