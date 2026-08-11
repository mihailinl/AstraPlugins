//! `astra-plugin sign` — append the retiring in-ZIP `SIGNATURE`/`PUBKEY` pair
//! to a bundle that `astra-plugin build` has already produced.
//!
//! # Why this command exists at all
//!
//! Until 3.10, `build` signed automatically whenever an Ed25519 seed happened
//! to exist at `~/.astra/plugin-keys/private.key`, and printed *"Signed with
//! Ed25519 key"*. Three things were wrong with that, in increasing order of how
//! much they cost the author:
//!
//! 1. **The archive's contents depended on the machine.** Two authors building
//!    the same commit produced different files, so `--reproducible` was true of
//!    one of them and not the other, and the digest a release published was not
//!    the digest a reviewer could re-derive.
//! 2. **The signature was checked against nothing.** The daemon verifies the
//!    in-ZIP pair against a *pinned Astra publisher key*, never against the key
//!    in the archive — a self-signed bundle is untrusted by construction, which
//!    is the correct behaviour and also means an author's own key proved
//!    exactly nothing to any user.
//! 3. **The message claimed otherwise.** An author who believes a local
//!    signature protects their users is worse off than one who knows it does
//!    not: they will skip the control that does work.
//!
//! So signing became explicit, and the copy became true. What the command still
//! *does* is a genuine, narrow thing: it is the optional second factor
//! PRODUCTION_PLAN §3.3 describes, defence-in-depth against a GitHub account
//! takeover, where the value comes from the key living somewhere the attacker's
//! stolen GitHub session is not. It is not, and never was, what makes Astra
//! install a plugin.
//!
//! # Sequencing
//!
//! This command and the format entry it writes are removed together at
//! [`crate::bundle::LEGACY_PAIR_SUNSET`]. Until then the daemon keeps *reading*
//! the pair so bundles already in the wild keep installing.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

use crate::bundle::{Bundle, LEGACY_PAIR_SUNSET, append_legacy_signature};
use crate::hprintln;

pub struct SignOptions<'a> {
    /// The `.astraplugin` to sign, in place.
    pub file: &'a str,
    /// Read the Ed25519 seed from here instead of
    /// `~/.astra/plugin-keys/private.key`.
    ///
    /// A path, never the key itself: a seed passed as an argument lands in the
    /// shell history, in `ps` output for every user on the machine, and in CI
    /// logs. There is deliberately no `--key-b64`.
    pub key: Option<&'a str>,
}

pub fn run(opts: SignOptions<'_>) -> Result<()> {
    let path = PathBuf::from(opts.file);
    if !path.is_file() {
        anyhow::bail!("No such bundle: {}", path.display());
    }

    // Verify BEFORE signing. Signing a bundle whose manifest disagrees with its
    // contents would attach a valid signature to a broken artifact, and the
    // signature is the thing that makes people stop looking. `Bundle::open` is
    // the same reader `astra-plugin verify` and the daemon's installer run.
    let bundle = Bundle::open(&path).with_context(|| {
        format!(
            "Refusing to sign {}: it does not verify. Signing an invalid bundle only makes the \
             invalidity harder to notice.",
            path.display()
        )
    })?;

    if bundle.signed {
        anyhow::bail!(
            "{} is already signed. Rebuild it with `astra-plugin build` and sign the fresh \
             bundle; a bundle is signed once or not at all.",
            path.display()
        );
    }

    let signing_key = load_key(opts.key)?;
    let signed = append_legacy_signature(&path, &signing_key)?;

    // Re-open. The append rewrote the central directory, and the reader's
    // structural rules for the pair — last two entries, in order, both present
    // — are checked there and nowhere else.
    let reopened = Bundle::open(&path)
        .context("The bundle stopped verifying after the signature was appended")?;
    anyhow::ensure!(
        reopened.signed,
        "The signature was written but the reader does not see it"
    );

    hprintln!("Signed: {}", path.display());
    hprintln!("  artifact sha256: {}", reopened.artifact_sha256);
    hprintln!("  public key:      {}", signed.public_key_b64);
    hprintln!();
    print_what_this_does_not_mean();
    Ok(())
}

/// The paragraph that has to be here, because the command's name implies the
/// opposite of what it delivers.
///
/// Printed on success, not buried in `--help`: the moment an author has just
/// signed something is the moment they are most likely to conclude their users
/// are now protected.
fn print_what_this_does_not_mean() {
    hprintln!("{}", what_this_does_not_mean());
}

/// Public so `--json` can carry it too: the paragraph is the whole reason this
/// command prints anything, and a machine-readable mode that drops it would let
/// a release pipeline log "signed" with none of the context that makes the word
/// honest.
pub fn what_this_does_not_mean() -> String {
    format!(
        "This signature is an optional second factor, not a trust signal.\n\
         \n\
         Astra does not verify it against your key — the daemon checks the in-ZIP pair against a\n\
         pinned Astra publisher key, so a bundle signed with your own key is untrusted by\n\
         construction, exactly as an unsigned one is. What makes Astra install a plugin is the\n\
         registry record countersigning sha256(whole file), and the GitHub attestation behind it.\n\
         \n\
         Where it does help: an attacker who takes over your GitHub account can produce a perfect\n\
         attestation and cannot produce this, so publishing your public key somewhere users read\n\
         gives them one thing to check that a stolen session cannot forge.\n\
         \n\
         `SIGNATURE`/`PUBKEY` and this command are removed in {LEGACY_PAIR_SUNSET}."
    )
}

/// Load the Ed25519 seed from an explicit path, or from the keygen default.
fn load_key(explicit: Option<&str>) -> Result<ed25519_dalek::SigningKey> {
    match explicit {
        Some(path) => super::keygen::load_signing_key_at(Path::new(path))?.with_context(|| {
            format!("No signing key at {path}. `astra-plugin keygen` writes one.")
        }),
        None => super::keygen::load_signing_key()?.context(
            "No signing key found at ~/.astra/plugin-keys/private.key.\n\
             Run `astra-plugin keygen` first, or pass --key <path>.\n\
             \n\
             You do not need one to publish: Astra's trust comes from the registry record and the\n\
             GitHub attestation, neither of which involves a key you hold.",
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A key written under a scratch directory, never under the user's home and
    /// never on a command line.
    fn scratch_key(dir: &Path) -> PathBuf {
        use base64::{Engine, engine::general_purpose::STANDARD};
        let key = ed25519_dalek::SigningKey::from_bytes(&[42u8; 32]);
        let path = dir.join("test-only.key");
        std::fs::write(&path, STANDARD.encode(key.to_bytes())).unwrap();
        path
    }

    fn tempdir(tag: &str) -> PathBuf {
        let mut p = std::env::temp_dir();
        p.push(format!("astra-plugin-sign-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&p);
        std::fs::create_dir_all(&p).unwrap();
        p
    }

    /// Build → sign → verify, over a real scaffold.
    ///
    /// This is the round trip that used to be one command. The assertion that
    /// matters is the *first* one: `build` produced an unsigned bundle on a
    /// machine where a key exists, which is the whole of 3.10's CLI half.
    #[test]
    fn build_leaves_it_unsigned_and_sign_is_what_signs_it() {
        let tmp = tempdir("roundtrip");
        let project = tmp.join("sign-roundtrip");
        crate::commands::create::run(crate::commands::create::NewOptions {
            name: "sign-roundtrip",
            lang: "python",
            template: "tool",
            capabilities: None,
            out_dir: &project.to_string_lossy(),
        })
        .unwrap();

        let out = tmp.join("sign-roundtrip.astraplugin");
        crate::commands::build::run(crate::commands::build::BuildOptions {
            path: &project.to_string_lossy(),
            output: Some(&out.to_string_lossy()),
            target: Some(crate::bundle::Target::Noarch),
            reproducible: true,
            // The flag is a no-op now; passing `false` is the case that used to
            // sign, and must not any more.
            no_sign: false,
        })
        .unwrap();

        let built = Bundle::open(&out).unwrap();
        assert!(
            !built.signed,
            "`astra-plugin build` must never append the legacy pair, key present or not"
        );
        let digest_before = built.artifact_sha256.clone();

        let key = scratch_key(&tmp);
        run(SignOptions {
            file: &out.to_string_lossy(),
            key: Some(&key.to_string_lossy()),
        })
        .unwrap();

        let signed = Bundle::open(&out).expect("a signed bundle must still verify");
        assert!(signed.signed);
        let names: Vec<&str> = signed.entries.iter().map(|e| e.path.as_str()).collect();
        assert_eq!(
            &names[names.len() - 2..],
            &["SIGNATURE", "PUBKEY"],
            "the pair is the last two entries, in that order"
        );
        assert_ne!(
            signed.artifact_sha256, digest_before,
            "signing changes the file, so it changes the number the registry countersigns — which \
             is why it cannot be something a build does by accident"
        );

        // Signing twice is refused rather than silently producing an archive
        // with two SIGNATURE entries.
        assert!(
            run(SignOptions {
                file: &out.to_string_lossy(),
                key: Some(&key.to_string_lossy()),
            })
            .is_err()
        );

        let _ = std::fs::remove_dir_all(&tmp);
    }

    /// The success text is where the author's belief about trust is formed, so
    /// it is asserted like any other output contract.
    #[test]
    fn the_success_text_says_what_the_signature_is_not() {
        let text = what_this_does_not_mean();
        assert!(text.contains("not a trust signal"), "{text}");
        assert!(text.contains("untrusted by\nconstruction"), "{text}");
        assert!(text.contains("registry record"), "{text}");
        // And it names the release it disappears in, from the one constant.
        assert!(text.contains(LEGACY_PAIR_SUNSET), "{text}");
        assert!(LEGACY_PAIR_SUNSET.contains("astra-plugin"));
        assert!(LEGACY_PAIR_SUNSET.contains("Astra"));
    }
}
