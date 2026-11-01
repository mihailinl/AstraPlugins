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
            // The three keys every `--json` document carries, so a caller can
            // branch before it knows which command produced the file. Additive:
            // the release workflow's reproducibility canary reads
            // `artifact_sha256` and is unaffected. A verify that gets this far
            // has passed — `Bundle::open` is what fails, above.
            "command": "verify",
            "ok": true,
            "exit_code": 0,
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

/// `new` → `build` → `verify`, on a scaffold this test creates from nothing.
///
/// The vector suite below proves that three *readers* agree about frozen bytes.
/// This proves the other half: that the **packer** produces bytes its own
/// reader accepts, and that the two digests the release pipeline publishes are
/// what a third party re-derives from the file. A format is only worth its
/// vectors if something still writes it.
///
/// There is no signing leg here any more, and that is 3.10's point: `build`
/// never appends the retiring in-ZIP pair, so a bundle's bytes no longer depend
/// on whether a key happens to sit in the builder's `~/.astra`. The signed
/// round trip moved to `commands::sign`, where it writes its key into a scratch
/// directory rather than the developer's home; the pair's structural rules
/// (last two entries, in that order) are also covered by the
/// `ok-legacy-signed` vector.
#[cfg(test)]
mod roundtrip {
    use sha2::{Digest, Sha256};

    use crate::bundle::{Bundle, Target, hex, manifest_digest, sha256_file};
    use crate::commands::{build, create};

    /// Carve `MANIFEST.json` out of the local file header by hand.
    ///
    /// Deliberately does not call [`crate::bundle::manifest_from_local_header`].
    /// The packer and the reader are the two halves under test here, and a bug
    /// they share — an off-by-one in the header arithmetic, say — would make
    /// them agree on a wrong answer. This is the same offset arithmetic
    /// `testdata/bundles/handcheck.sh` does with `dd` and `od`, written out so
    /// the round trip has a third opinion of its own.
    fn carve_manifest(bytes: &[u8]) -> Vec<u8> {
        let u16_at = |o: usize| u16::from_le_bytes([bytes[o], bytes[o + 1]]) as usize;
        let u32_at = |o: usize| {
            u32::from_le_bytes([bytes[o], bytes[o + 1], bytes[o + 2], bytes[o + 3]]) as usize
        };
        assert_eq!(
            &bytes[0..4],
            b"PK\x03\x04",
            "no local file header at offset 0"
        );
        assert_eq!(u16_at(8), 0, "MANIFEST.json must be STORED");
        let name_len = u16_at(26);
        let extra_len = u16_at(28);
        assert_eq!(&bytes[30..30 + name_len], b"MANIFEST.json");
        let start = 30 + name_len + extra_len;
        bytes[start..start + u32_at(18)].to_vec()
    }

    fn build_and_verify(dir: &std::path::Path, name: &str) -> Bundle {
        let project = dir.join(name);
        create::run(crate::commands::create::NewOptions {
            name,
            lang: "python",
            template: "tool",
            ui: "vanilla",
            capabilities: Some("tools"),
            out_dir: &project.to_string_lossy(),
        })
            .expect("`astra-plugin new` must produce a buildable scaffold");

        let out = dir.join(format!("{name}.astraplugin"));
        build::run(build::BuildOptions {
            path: &project.to_string_lossy(),
            output: Some(&out.to_string_lossy()),
            target: Some(Target::Noarch),
            // Assert determinism while we are here: `--reproducible` packs a
            // second time and compares digests, so a build that depends on the
            // machine rather than on its inputs fails here rather than at the
            // first person who tries to reproduce a published artifact.
            //
            // Unconditional since 3.10, and that is the point: `build` no
            // longer signs, so its output no longer depends on whether a key
            // exists in the builder's home directory, and every build is a
            // build anyone can reproduce.
            reproducible: true,
            no_sign: false,
        })
        .expect("`astra-plugin build` must produce a bundle");

        Bundle::open(&out).expect("`astra-plugin verify` must accept what `build` just wrote")
    }

    /// The failure mode the "deflate slack" belt-and-braces check
    /// (`verify_no_deflate_slack` in bundle.rs) must not introduce: refusing
    /// a perfectly legitimate file because its decompressed length lands
    /// just past a multiple of that function's own 64 KiB output buffer.
    ///
    /// 17×65536+1 bytes is not a round number by accident: it is the
    /// smallest size, found by probing the exact resolved `zlib-rs` backend
    /// pinned in `Cargo.lock`, at which the decoder consumes every declared
    /// compressed byte on a `FlushDecompress::None` call and still has not
    /// reported `Status::StreamEnd` — one pending output byte sits inside
    /// it until a follow-up call with no more input and
    /// `FlushDecompress::Finish` flushes it. 16×65536+1 (naively "1 MiB + 1
    /// byte") does *not* trigger it with this backend version, which is
    /// exactly why this is pinned at the size that was actually verified to,
    /// rather than guessed from the shape of the bug. See the
    /// drain-after-EOF comment on `verify_no_deflate_slack` for the fix this
    /// test pins: removing it makes this test fail.
    #[test]
    fn a_file_just_over_a_multiple_of_64kib_still_verifies() {
        let tmp = tempdir();
        let project = tmp.join("big-zero-plugin");
        create::run(crate::commands::create::NewOptions {
            name: "big-zero-plugin",
            lang: "python",
            template: "tool",
            ui: "vanilla",
            capabilities: Some("tools"),
            out_dir: &project.to_string_lossy(),
        })
        .expect("`astra-plugin new` must produce a buildable scaffold");

        // All zeros: deflate shrinks it to about a kilobyte, but its
        // UNCOMPRESSED length is what the belt-and-braces check drains
        // through `out_buf` in 64 KiB steps, and 17×65536+1 is confirmed
        // (see the doc comment above) to land exactly where the fix matters.
        let big = vec![0u8; 17 * 64 * 1024 + 1];
        std::fs::write(project.join("src").join("zeros.bin"), &big)
            .expect("writing the oversized fixture file into the scaffold");

        let out = tmp.join("big-zero-plugin.astraplugin");
        build::run(build::BuildOptions {
            path: &project.to_string_lossy(),
            output: Some(&out.to_string_lossy()),
            target: Some(Target::Noarch),
            reproducible: true,
            no_sign: false,
        })
        .expect("`astra-plugin build` must produce a bundle");

        Bundle::open(&out).expect(
            "a legitimate large all-zero Deflated entry must verify — `verify_no_deflate_slack` \
             must not mistake a decoder that needs one more drain call past the last byte of \
             input for a stream that never ended",
        );
    }

    #[test]
    fn a_scaffold_builds_into_a_bundle_its_own_reader_accepts() {
        let tmp = tempdir();
        let bundle = build_and_verify(&tmp, "roundtrip-plugin");

        assert_eq!(bundle.manifest.plugin_id, "roundtrip-plugin");
        assert_eq!(bundle.manifest.schema, crate::bundle::SCHEMA);
        assert!(
            !bundle.signed,
            "`build` must not append the legacy pair, whatever is in ~/.astra/plugin-keys"
        );
        assert!(
            bundle
                .manifest
                .files
                .iter()
                .any(|f| f.path == "plugin.toml"),
            "every bundle carries plugin.toml"
        );

        // The packer's ROOT ALLOWLIST, asserted on a real scaffold.
        //
        // `build` sweeps a whole directory only for the unknown-language arm;
        // for rust, typescript and python the root is an explicit list of
        // names. `locales.lock.json` sits at the root precisely because it must
        // NOT be inside `locales/` — every top-level `*.json` in there is loaded
        // as a locale keyed on its stem — and that placement walked it straight
        // into the list's blind spot: it was in no real bundle at all, silently,
        // while the registry's staleness demotion read a lock that had never
        // shipped.
        //
        // ci.yml's archive inspector asserts the same thing across two operating
        // systems and all three languages, which is the coverage that matters.
        // This is here because reverting the allowlist left `cargo test`
        // ENTIRELY GREEN — the packer had no unit-level witness at all, so the
        // one-line regression would have travelled to a runner before anything
        // said a word.
        for want in ["locales/en.json", crate::commands::locale::LOCK_FILE] {
            assert!(
                bundle.manifest.files.iter().any(|f| f.path == want),
                "{want} is not in the bundle. Root files are packed by an explicit allowlist in \
                 commands::build; a scaffolded plugin reaches it by name or not at all. \
                 Bundle carries: {:?}",
                bundle.manifest.files.iter().map(|f| &f.path).collect::<Vec<_>>()
            );
        }

        // Both published numbers, re-derived from the file by a path that does
        // not go through the reader that produced them.
        let path = tmp.join("roundtrip-plugin.astraplugin");
        let raw = std::fs::read(&path).unwrap();
        let (artifact, size) = sha256_file(&path).unwrap();
        assert_eq!(artifact, hex(&Sha256::digest(&raw)));
        assert_eq!(size as usize, raw.len());
        assert_eq!(artifact, bundle.artifact_sha256);

        let carved = carve_manifest(&raw);
        assert_eq!(
            manifest_digest(&carved),
            bundle.manifest_digest,
            "the manifest digest depends on which bytes you think the manifest is"
        );
        // Invariant 3 on bytes this build just produced.
        assert_ne!(bundle.manifest_digest, hex(&Sha256::digest(&carved)));

        // Invariant 4, both directions, on a real scaffold rather than a
        // fixture: `Bundle::open` already enforced it, so this asserts the
        // *packer* had nothing to hide.
        let listed: std::collections::BTreeSet<&str> = bundle
            .manifest
            .files
            .iter()
            .map(|f| f.path.as_str())
            .collect();
        let present: std::collections::BTreeSet<&str> = bundle
            .entries
            .iter()
            .map(|e| e.path.as_str())
            .filter(|p| !crate::bundle::UNLISTED_ENTRIES.contains(p))
            .collect();
        assert_eq!(listed, present);
    }

    /// The build is byte-identical whether or not this machine has a signing
    /// key — the property 3.10 bought by taking signing out of `build`.
    ///
    /// Before 3.10 this test could not have been written: the two builds below
    /// would differ on a developer's laptop and agree on a bare CI runner, so
    /// "reproducible" meant something different depending on who ran it. That
    /// is precisely the failure an author discovers only when a reviewer cannot
    /// re-derive a published digest.
    #[test]
    fn the_build_is_the_same_bundle_with_or_without_a_key_on_the_machine() {
        let tmp = tempdir();
        let first = build_and_verify(&tmp, "roundtrip-nokey");

        // Same project, packed a second time to a different path.
        let project = tmp.join("roundtrip-nokey");
        let out = tmp.join("roundtrip-nokey-again.astraplugin");
        build::run(build::BuildOptions {
            path: &project.to_string_lossy(),
            output: Some(&out.to_string_lossy()),
            target: Some(Target::Noarch),
            reproducible: true,
            no_sign: false,
        })
        .unwrap();
        let second = Bundle::open(&out).unwrap();

        assert_eq!(
            first.artifact_sha256, second.artifact_sha256,
            "two builds of the same source must produce the same artifact digest"
        );
        assert!(!first.signed && !second.signed);
        // The key that used to change this outcome is not even consulted.
        let _ = crate::commands::keygen::load_signing_key();
    }

    /// A scratch directory that does not need the `tempfile` crate in this
    /// binary's dependency list.
    ///
    /// **It removes itself.** The first version of this helper called
    /// `remove_dir_all` on ENTRY and never on exit, which is correct in every
    /// single execution — each run starts from a clean directory — and wrong in
    /// aggregate: the name is keyed by pid and thread id, so a fresh pid means a
    /// fresh directory and the previous run's tree stays. 320 of them had
    /// accumulated on one developer machine, the oldest four days old. Nothing
    /// about reading the old function suggested a leak, because no individual
    /// call leaked.
    ///
    /// That machine's `/tmp` is a tmpfs, so the leak was resident memory rather
    /// than disk, invisible to `free` as anything but "used" and attributable to
    /// no process.
    ///
    /// The entry-side `remove_dir_all` is kept: it is what clears a tree left by
    /// a run that was killed before `Drop` could run.
    struct Scratch(std::path::PathBuf);

    impl std::ops::Deref for Scratch {
        type Target = std::path::Path;
        fn deref(&self) -> &std::path::Path {
            &self.0
        }
    }

    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn tempdir() -> Scratch {
        let mut p = std::env::temp_dir();
        p.push(format!(
            "astra-plugin-roundtrip-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        let _ = std::fs::remove_dir_all(&p);
        std::fs::create_dir_all(&p).expect("scratch directory");
        Scratch(p)
    }
}

/// The cross-repo bundle vectors (`testdata/bundles/`), read by this suite, by
/// the daemon's `plugins/bundle.rs`, and by `astra-registry/tools/selftest.mjs`.
///
/// Three implementations of one written-down format, in three languages, in
/// three repositories that release on three schedules. Nothing structural stops
/// two of them drifting apart for a release, and the failure is quiet in both
/// directions: too strict makes a legitimate plugin uninstallable, too lax
/// publishes a bundle the others refuse. So all three answer the same questions
/// about the same frozen bytes, and the expected answers are written down next
/// to them rather than derived from whichever implementation happens to be
/// running.
///
/// This crate reads the canonical directory directly — it lives in this repo,
/// beside the packer that defines the format. The other two hold copies
/// vendored by `tools/vendor-testdata.sh` and verified against `SHA256SUMS`
/// both by that script and by their own suites at run time.
///
/// See `testdata/bundles/README.md`.
#[cfg(test)]
mod vectors {
    use std::collections::BTreeMap;
    use std::path::PathBuf;

    use serde_json::Value;
    use sha2::{Digest, Sha256};

    use crate::bundle::{
        Bundle, ManifestPermission, canonical_permissions, hex, manifest_digest,
        manifest_from_local_header, sha256_file,
    };

    fn dir() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .expect("astra-plugin-cli has a parent directory")
            .join("testdata/bundles")
    }

    fn vectors() -> Vec<Value> {
        let raw = std::fs::read(dir().join("vectors.json")).expect(
            "testdata/bundles/vectors.json is missing. It is committed; a checkout without it \
             is incomplete, not a reason to skip.",
        );
        let doc: Value = serde_json::from_slice(&raw).expect("vectors.json is not valid JSON");
        assert_eq!(doc["schema"], "astra.testdata.bundles/1");
        doc["vectors"]
            .as_array()
            .expect("vectors.json has a `vectors` array")
            .clone()
    }

    fn s<'a>(v: &'a Value, key: &str) -> &'a str {
        v[key]
            .as_str()
            .unwrap_or_else(|| panic!("vector {} has no string `{key}`", v["name"]))
    }

    /// Nothing else in this module means anything if the bytes have moved.
    ///
    /// Every consumer re-checks its own copy for the same reason: a fixture
    /// that was edited in place produces a digest disagreement that looks
    /// exactly like an implementation bug, and the two are diagnosed in
    /// completely different places.
    #[test]
    fn the_vector_directory_matches_its_own_sha256sums() {
        let sums = std::fs::read_to_string(dir().join("SHA256SUMS"))
            .expect("testdata/bundles/SHA256SUMS is missing");
        let mut checked = 0;
        for line in sums.lines().filter(|l| !l.trim().is_empty()) {
            let (want, file) = line
                .split_once("  ")
                .unwrap_or_else(|| panic!("malformed SHA256SUMS line: {line}"));
            let bytes = std::fs::read(dir().join(file))
                .unwrap_or_else(|e| panic!("SHA256SUMS lists {file}, which cannot be read: {e}"));
            assert_eq!(
                hex(&Sha256::digest(&bytes)),
                want,
                "{file} does not match SHA256SUMS. A golden was edited in place; regenerate \
                 with `node testdata/bundles/generate.mjs` rather than adjusting the digest."
            );
            checked += 1;
        }
        assert!(checked >= 20, "only {checked} files in SHA256SUMS");
    }

    /// The verdict half: what this CLI does with each vector, compared against
    /// what is written down for it rather than against whatever the reader
    /// happens to do today.
    ///
    /// Which gate is asked is chosen by the vector's `layer`. `bundle-structure`
    /// is [`Bundle::open`], the same code `astra-plugin verify` runs. The other
    /// two layers — `plugin-id` and `permissions-hash` — have **no gate in this
    /// CLI at all** (divergences F4 and F5), so what is asserted for them is
    /// that `Bundle::open` passes them: the vector is still pinning the
    /// structural reader's behaviour, and the missing check is recorded where
    /// somebody will find it rather than implied by a test that does not exist.
    #[test]
    fn every_vector_gets_the_verdict_recorded_for_it() {
        let mut accepted = 0;
        let mut rejected = 0;
        for v in vectors() {
            let name = s(&v, "name");
            let want = v["expect"]["cli"]
                .as_str()
                .unwrap_or_else(|| panic!("vector {name} has no expect.cli"));
            let path = dir().join(s(&v, "file"));
            let outcome = Bundle::open(&path);

            if s(&v, "layer") != "bundle-structure" {
                assert!(
                    outcome.is_ok(),
                    "vector `{name}` is a `{}` case, so the structural reader is expected to pass \
                     it — if it now refuses it, the vector is testing something other than what \
                     it says",
                    s(&v, "layer")
                );
                assert_eq!(
                    want,
                    "accept",
                    "vector `{name}` records expect.cli = `{want}`, but this CLI has no `{}` gate \
                     — see the divergence block in vectors.json",
                    s(&v, "layer")
                );
                accepted += 1;
                continue;
            }

            match (want, &outcome) {
                ("accept", Err(e)) => panic!(
                    "vector `{name}` is recorded as accepted by the CLI and was refused:\n  {e:#}\n\
                     Why it matters: {}",
                    s(&v, "why_it_matters")
                ),
                ("reject", Ok(_)) => panic!(
                    "vector `{name}` is recorded as REJECTED by the CLI and `Bundle::open` \
                     accepted it.\n  Why it matters: {}\n  If this reader legitimately does not \
                     catch it, that is a divergence and belongs in vectors.json with a reason — \
                     not a silently passing test.",
                    s(&v, "why_it_matters")
                ),
                ("accept", Ok(_)) => accepted += 1,
                ("reject", Err(_)) => rejected += 1,
                (other, _) => panic!("vector {name}: unknown expect.cli `{other}`"),
            }
        }
        assert!(accepted >= 5, "only {accepted} accept-vectors ran");
        assert!(rejected >= 15, "only {rejected} reject-vectors ran");
    }

    /// The digest half, and the reason this is a *cross-repo* fixture rather
    /// than three sets of unit tests.
    ///
    /// Both numbers are recomputed here and compared against the recorded ones.
    /// The recorded ones are not this program's output: `testdata/bundles/`
    /// carries `handcheck.sh`, which derives the same two values with `dd`,
    /// `printf` and `sha256sum` and nothing of ours. Three implementations that
    /// share a mistake can agree with each other; they cannot agree with
    /// coreutils.
    #[test]
    fn both_digests_match_the_recorded_values() {
        let mut n = 0;
        for v in vectors() {
            let name = s(&v, "name");
            let path = dir().join(s(&v, "file"));

            let (artifact, size) = sha256_file(&path).expect("vector file is readable");
            assert_eq!(
                artifact,
                s(&v, "artifact_sha256"),
                "vector `{name}`: artifact digest (sha256 of the whole file) disagrees with \
                 vectors.json. This is the number the index carries and the attestation subject."
            );
            assert_eq!(
                size,
                v["artifact_size"].as_u64().unwrap(),
                "vector `{name}`: size disagrees with vectors.json"
            );

            // The manifest digest is over the bytes at offset 0 — the local
            // file header — not over whatever the central directory points at.
            // `manifest-not-first` and `manifest-compressed` have no readable
            // manifest there by construction, and record `null`.
            if let Some(want) = v["manifest_digest"].as_str() {
                let bytes = std::fs::read(&path).unwrap();
                let manifest_bytes = manifest_from_local_header(&bytes).unwrap_or_else(|e| {
                    panic!(
                        "vector `{name}` records a manifest digest but entry 0 is unreadable: {e:#}"
                    )
                });
                assert_eq!(
                    hex(&Sha256::digest(&manifest_bytes)),
                    s(&v, "manifest_sha256"),
                    "vector `{name}`: plain sha256 of the manifest bytes disagrees"
                );
                assert_eq!(
                    manifest_digest(&manifest_bytes),
                    want,
                    "vector `{name}`: the domain-separated manifest digest disagrees with \
                     vectors.json"
                );
                // Invariant 3, restated on real bytes: the domain-separated
                // digest must never equal the plain one, or a manifest digest
                // and a `files[].sha256` are the same 64 characters and one
                // verifies in the other's place.
                assert_ne!(
                    manifest_digest(&manifest_bytes),
                    hex(&Sha256::digest(&manifest_bytes))
                );
                n += 1;
            }
        }
        assert!(n >= 20, "only {n} manifest digests checked");
    }

    /// The `"ab"+"c"` / `"a"+"bc"` collision, on real archives.
    ///
    /// The retired in-ZIP digest was
    /// `SHA256(name₀‖content₀‖name₁‖content₁‖…)` in ZIP index order: no
    /// delimiters, no length prefixes, no entry count, no domain separator.
    /// The two vectors below carry byte-for-byte identical `MANIFEST.json` and
    /// differ only in whether the archive holds `a`/`bc` or `ab`/`c` — so that
    /// digest maps both to one number, and one legacy `SIGNATURE` authenticates
    /// either. This test recomputes it from the archives to show the collision
    /// is real, then shows that v2 separates them.
    #[test]
    fn the_legacy_concatenation_digest_collides_where_v2_does_not() {
        let all = vectors();
        let find = |name: &str| {
            all.iter()
                .find(|v| v["name"] == name)
                .unwrap_or_else(|| panic!("vector {name} is missing"))
                .clone()
        };
        let honest = find("collision-a-bc");
        let attack = find("collision-ab-c");

        // Recomputed from the bytes, exactly as `PluginManager::verify_signature`
        // does it — the only place in this project that number should appear.
        let legacy = |file: &str| -> String {
            let f = std::fs::File::open(dir().join(file)).unwrap();
            let mut zip = zip::ZipArchive::new(std::io::BufReader::new(f)).unwrap();
            let mut h = Sha256::new();
            for i in 0..zip.len() {
                use std::io::Read;
                let mut e = zip.by_index(i).unwrap();
                let n = e.name().unwrap().into_owned();
                if n == "SIGNATURE" || n == "PUBKEY" {
                    continue;
                }
                let mut buf = Vec::new();
                e.read_to_end(&mut buf).unwrap();
                h.update(n.as_bytes());
                h.update(&buf);
            }
            hex(&h.finalize())
        };

        let a = legacy(s(&honest, "file"));
        let b = legacy(s(&attack, "file"));
        assert_eq!(a, s(&honest, "legacy_concat_sha256"));
        assert_eq!(b, s(&attack, "legacy_concat_sha256"));
        assert_eq!(
            a, b,
            "the collision pair no longer collides under the retired scheme, so this vector has \
             stopped demonstrating anything"
        );

        // Identical manifests, identical legacy digest — and different files.
        assert_eq!(s(&honest, "manifest_digest"), s(&attack, "manifest_digest"));
        assert_ne!(s(&honest, "artifact_sha256"), s(&attack, "artifact_sha256"));

        // And v2 tells them apart, in both directions of the exhaustiveness
        // check: `ab` is an entry no manifest line covers, `a` is a manifest
        // line no entry satisfies.
        assert!(
            Bundle::open(&dir().join(s(&honest, "file"))).is_ok(),
            "the honest half of the collision pair must open"
        );
        let chain = match Bundle::open(&dir().join(s(&attack, "file"))) {
            Ok(_) => panic!("the swapped half of the collision pair must be refused"),
            Err(e) => format!("{e:#}"),
        };
        assert!(
            chain.contains("exhaustive")
                || chain.contains("not in MANIFEST")
                || chain.contains("'ab'"),
            "the refusal should name the exhaustiveness failure: {chain}"
        );
    }

    /// `permissions_hash` is compared across a repository boundary — the
    /// registry computes one side and the daemon the other — so three
    /// independent RFC 8785 implementations have to agree on the canonical
    /// bytes of the permission map. For a value of this shape (strings and
    /// objects only) JCS reduces to "sort the keys, drop the whitespace", and
    /// that is what all three must do.
    #[test]
    fn the_permission_hash_is_recomputed_from_the_manifests_own_permissions() {
        let all = vectors();

        let recompute = |perms: &BTreeMap<String, ManifestPermission>| -> String {
            format!(
                "sha256:{}",
                hex(&Sha256::digest(canonical_permissions(perms).unwrap()))
            )
        };

        // The honest case: what the manifest records is what its permissions
        // hash to.
        let ok = all.iter().find(|v| v["name"] == "ok-permissions").unwrap();
        let bundle = Bundle::open(&dir().join(s(ok, "file"))).unwrap();
        assert!(
            !bundle.manifest.permissions.is_empty(),
            "the ok-permissions vector must carry a non-empty permission map, or it pins nothing"
        );
        assert_eq!(
            recompute(&bundle.manifest.permissions),
            bundle.manifest.permissions_hash
        );
        assert_eq!(bundle.manifest.permissions_hash, s(ok, "permissions_hash"));

        // The adversarial case: `permissions` asks for `fire_trigger` while
        // `permissions_hash` is the hash of an EMPTY map. The vector's whole
        // point is that the two describe different plugins, so assert that
        // first — a fixture that quietly stopped mismatching would make the
        // divergence below look closed.
        let bad = all
            .iter()
            .find(|v| v["name"] == "permissions-hash-mismatch")
            .unwrap();
        let bundle = Bundle::open(&dir().join(s(bad, "file")))
            .expect("recorded as accepted today — see divergence F5");
        let correct = recompute(&bundle.manifest.permissions);
        assert_eq!(correct, s(bad, "correct_permissions_hash"));
        assert_eq!(
            bundle.manifest.permissions_hash,
            s(bad, "recorded_permissions_hash")
        );
        assert_ne!(
            correct, bundle.manifest.permissions_hash,
            "the permissions-hash-mismatch vector no longer mismatches"
        );
    }

    /// Every recorded divergence is a defect with a test attached.
    ///
    /// A gap written in a comment becomes folklore. A gap written here fails
    /// the build the day somebody closes it, and the fix is to delete the entry
    /// — which is the only moment anyone would think to.
    #[test]
    fn recorded_divergences_still_diverge() {
        for v in vectors() {
            let Some(d) = v.get("divergence") else {
                continue;
            };
            let name = s(&v, "name");
            let want = v["expect"]["cli"].as_str().unwrap();
            let verdict = s(&v, "verdict");
            if want == verdict {
                continue; // this divergence is about another implementation
            }
            let outcome = Bundle::open(&dir().join(s(&v, "file")));
            assert_eq!(
                outcome.is_ok(),
                want == "accept",
                "divergence {} on vector `{name}` no longer describes this reader.\n  {}\n\
                 If it has been fixed, delete the `divergence` block and set expect.cli to \
                 \"{verdict}\".",
                d["finding"].as_str().unwrap_or("?"),
                d["summary"].as_str().unwrap_or("")
            );
        }
    }
}

/// The "zip cloaking" gap (the CRITICAL Dependabot advisory for Rust `zip` <
/// 9.0.5): a crafted archive whose local file headers disagree with its
/// central directory makes a validator and an extractor see different
/// entries. zip 9 does not refuse this by itself — `ZipArchive::by_index`
/// still reads metadata off the central directory alone — so `Bundle::open`
/// now calls `ZipArchive::validate_header_consistency()` explicitly, before
/// trusting anything `by_index` returns.
///
/// This fixture is built one byte at a time rather than with `zip::ZipWriter`
/// because every writer in this codebase — and in the `zip` crate itself —
/// keeps local and central headers in sync by construction. The attack this
/// guards against can only be expressed below the writer's API, the same way
/// `roundtrip::carve_manifest` reads below the reader's.
#[cfg(test)]
mod cloaking {
    use std::collections::BTreeMap;
    use std::io::Write;

    use sha2::{Digest, Sha256};

    use crate::bundle::{Bundle, BundleManifest, FileEntry, ManifestEntry, Platform, SCHEMA, hex, permissions_hash};

    fn le16(n: u16) -> [u8; 2] {
        n.to_le_bytes()
    }
    fn le32(n: u32) -> [u8; 4] {
        n.to_le_bytes()
    }

    /// CRC-32 (ZIP's polynomial), computed independently of the `zip` crate's
    /// own implementation so this fixture does not borrow the correctness of
    /// the thing it is attacking.
    fn crc32(data: &[u8]) -> u32 {
        let mut crc: u32 = 0xFFFF_FFFF;
        for &byte in data {
            crc ^= byte as u32;
            for _ in 0..8 {
                crc = if crc & 1 != 0 {
                    (crc >> 1) ^ 0xEDB8_8320
                } else {
                    crc >> 1
                };
            }
        }
        !crc
    }

    /// A real, valid raw DEFLATE stream (no zlib wrapper — the same framing
    /// PKZIP method 8 uses), produced independently of `bundle.rs`'s own
    /// decoder: this is what a legitimate packer writes, and what the real
    /// compressed region of a slack attack's bytes actually decode to.
    fn raw_deflate(data: &[u8]) -> Vec<u8> {
        let mut encoder = flate2::write::DeflateEncoder::new(Vec::new(), flate2::Compression::best());
        encoder.write_all(data).unwrap();
        encoder.finish().unwrap()
    }

    /// The Info-ZIP Unicode Path (0x7075) extra field: tag, size, a version
    /// byte, the CRC32 of the *raw* name this field accompanies, and the
    /// UTF-8 "real" name a reader that honours this field resolves to
    /// instead. Byte-for-byte what `gen.py`'s `upath()` helper builds.
    fn unicode_path_extra(raw_name: &[u8], target: &[u8]) -> Vec<u8> {
        let mut body = vec![1u8]; // version
        body.extend_from_slice(&crc32(raw_name).to_le_bytes());
        body.extend_from_slice(target);
        let mut field = Vec::new();
        field.extend_from_slice(&le16(0x7075));
        field.extend_from_slice(&le16(body.len() as u16));
        field.extend_from_slice(&body);
        field
    }

    /// A local file header, fully parameterised, appended to `out`. Returns
    /// the header's starting offset — what a central directory record's
    /// "relative offset of local header" field points at. `method`/`flags`/
    /// `crc`/the two sizes are the header's own claims, independent of
    /// `content`'s real length: that gap is what lets this module build
    /// archives no legitimate writer would.
    #[allow(clippy::too_many_arguments)]
    fn write_local_header_raw(
        out: &mut Vec<u8>,
        name: &[u8],
        method: u16,
        flags: u16,
        crc: u32,
        compressed_size: u32,
        uncompressed_size: u32,
        extra: &[u8],
        content: &[u8],
    ) -> u32 {
        let offset = out.len() as u32;
        out.extend_from_slice(&0x0403_4b50u32.to_le_bytes());
        out.extend_from_slice(&le16(20)); // version needed to extract
        out.extend_from_slice(&le16(flags));
        out.extend_from_slice(&le16(method));
        out.extend_from_slice(&le16(0)); // last mod time
        out.extend_from_slice(&le16(0x21)); // last mod date: 1980-01-01
        out.extend_from_slice(&le32(crc));
        out.extend_from_slice(&le32(compressed_size));
        out.extend_from_slice(&le32(uncompressed_size));
        out.extend_from_slice(&le16(name.len() as u16));
        out.extend_from_slice(&le16(extra.len() as u16));
        out.extend_from_slice(name);
        out.extend_from_slice(extra);
        out.extend_from_slice(content);
        offset
    }

    /// A stored (uncompressed), fully consistent local file header plus its
    /// content — the common case every other helper here is a deliberate
    /// departure from.
    fn write_local_header(out: &mut Vec<u8>, name: &[u8], content: &[u8]) -> u32 {
        write_local_header_raw(
            out,
            name,
            0,
            0,
            crc32(content),
            content.len() as u32,
            content.len() as u32,
            &[],
            content,
        )
    }

    /// A central directory record, fully parameterised. `name`, `method`,
    /// `flags`, `content_crc`, the two sizes and `extra` are the CENTRAL
    /// directory's own claims — independent of whatever is physically
    /// written at `local_header_offset`. That gap is the entire point of
    /// this module: a reader that trusts the central directory for
    /// everything (as `by_index` does) never looks at what disagrees.
    #[allow(clippy::too_many_arguments)]
    fn write_central_entry_raw(
        out: &mut Vec<u8>,
        name: &[u8],
        method: u16,
        flags: u16,
        content_crc: u32,
        compressed_size: u32,
        uncompressed_size: u32,
        extra: &[u8],
        local_header_offset: u32,
    ) {
        out.extend_from_slice(&0x0201_4b50u32.to_le_bytes());
        out.extend_from_slice(&le16(0)); // version made by: MS-DOS host, no unix mode
        out.extend_from_slice(&le16(20)); // version needed to extract
        out.extend_from_slice(&le16(flags));
        out.extend_from_slice(&le16(method));
        out.extend_from_slice(&le16(0)); // last mod time
        out.extend_from_slice(&le16(0x21)); // last mod date
        out.extend_from_slice(&le32(content_crc));
        out.extend_from_slice(&le32(compressed_size));
        out.extend_from_slice(&le32(uncompressed_size));
        out.extend_from_slice(&le16(name.len() as u16));
        out.extend_from_slice(&le16(extra.len() as u16));
        out.extend_from_slice(&le16(0)); // file comment length
        out.extend_from_slice(&le16(0)); // disk number start
        out.extend_from_slice(&le16(0)); // internal file attributes
        out.extend_from_slice(&le32(0)); // external file attributes
        out.extend_from_slice(&le32(local_header_offset));
        out.extend_from_slice(name);
        out.extend_from_slice(extra);
    }

    /// A stored, fully consistent central directory record.
    fn write_central_entry(
        out: &mut Vec<u8>,
        name: &[u8],
        content_crc: u32,
        content_len: u32,
        local_header_offset: u32,
    ) {
        write_central_entry_raw(
            out,
            name,
            0,
            0,
            content_crc,
            content_len,
            content_len,
            &[],
            local_header_offset,
        );
    }

    /// The end-of-central-directory record.
    fn write_eocd(out: &mut Vec<u8>, entries: u16, central_size: u32, central_start: u32) {
        out.extend_from_slice(&0x0605_4b50u32.to_le_bytes());
        out.extend_from_slice(&le16(0)); // disk number
        out.extend_from_slice(&le16(0)); // disk with central directory
        out.extend_from_slice(&le16(entries)); // entries on this disk
        out.extend_from_slice(&le16(entries)); // total entries
        out.extend_from_slice(&le32(central_size));
        out.extend_from_slice(&le32(central_start));
        out.extend_from_slice(&le16(0)); // comment length
    }

    /// A minimal, otherwise-valid v2 manifest naming `files`, serialised the
    /// same way the real packer does (`BundleManifest::to_bytes`).
    fn build_manifest(files: Vec<FileEntry>) -> Vec<u8> {
        BundleManifest {
            schema: SCHEMA.to_string(),
            plugin_id: "cloak-test".to_string(),
            version: "0.1.0".to_string(),
            platform: Platform {
                os: "any".to_string(),
                arch: "any".to_string(),
            },
            protocol: 1,
            min_astra_version: String::new(),
            capabilities: vec![],
            permissions: BTreeMap::new(),
            permissions_hash: permissions_hash(&BTreeMap::new()).unwrap(),
            entry: ManifestEntry {
                command: "python".to_string(),
                args: vec![],
            },
            files,
        }
        .to_bytes()
        .unwrap()
    }

    /// Build a two-entry archive where entry 0 (`MANIFEST.json`) is entirely
    /// consistent — local and central agree, exactly as a real bundle built by
    /// this CLI would be — and entry 1 is the cloak: its local file header
    /// names it `evil.txt`, but the central directory's record for that same
    /// offset names it `note.txt`, with the central directory's CRC32 and size
    /// set to the real bytes' values (so a reader that trusts the central
    /// directory for everything, as `by_index` does, reads them without
    /// complaint).
    ///
    /// A verifier built on `by_index` alone — every reader before
    /// `validate_header_consistency` existed — sees a `note.txt` whose hash
    /// matches `MANIFEST.files` and calls the bundle good. An extractor that
    /// resolves names from local headers instead (streaming scanners and
    /// several real-world unzip implementations do, for exactly the files
    /// that matter to them) would write that same payload to `evil.txt` — a
    /// path the manifest never mentioned and nothing hashed under that name.
    /// `verify` vouching for "note.txt" says nothing about what `evil.txt`
    /// contains.
    fn build_cloaked_bundle() -> Vec<u8> {
        let note_content: &[u8] = b"hello123";
        let manifest_bytes = build_manifest(vec![FileEntry {
            path: "note.txt".to_string(),
            sha256: hex(&Sha256::digest(note_content)),
            size: note_content.len() as u64,
            mode: "0644".to_string(),
        }]);

        let mut out = Vec::new();
        let manifest_offset = write_local_header(&mut out, b"MANIFEST.json", &manifest_bytes);
        let note_offset = write_local_header(&mut out, b"evil.txt", note_content);

        let central_start = out.len() as u32;
        write_central_entry(
            &mut out,
            b"MANIFEST.json",
            crc32(&manifest_bytes),
            manifest_bytes.len() as u32,
            manifest_offset,
        );
        write_central_entry(
            &mut out,
            b"note.txt", // <-- disagrees with the local header's "evil.txt"
            crc32(note_content),
            note_content.len() as u32,
            note_offset,
        );
        let central_size = out.len() as u32 - central_start;
        write_eocd(&mut out, 2, central_size, central_start);
        out
    }

    /// Entry 1 is `a.txt`, Deflated, with general-purpose bit 3 (trailing
    /// data descriptor) set — but otherwise entirely honest: the real
    /// deflate stream, the data descriptor right after it, and the central
    /// directory's sizes all agree, with nothing hidden. This is the shape
    /// `gen.py`'s `slack.zip` vector depends on to defer its local header's
    /// sizes in the first place — rebuilt here without the nested-header
    /// payload, to isolate the one thing this fixture exists to prove: that
    /// `Bundle::open` refuses bit 3 *on its own*, before any question of
    /// slack even arises.
    fn build_bit3_bundle() -> Vec<u8> {
        let content: &[u8] = b"hello world\n";
        let compressed = raw_deflate(content);
        let crc = crc32(content);
        let manifest_bytes = build_manifest(vec![FileEntry {
            path: "a.txt".to_string(),
            sha256: hex(&Sha256::digest(content)),
            size: content.len() as u64,
            mode: "0644".to_string(),
        }]);

        let mut data_descriptor = Vec::new();
        data_descriptor.extend_from_slice(&0x0807_4b50u32.to_le_bytes()); // optional signature
        data_descriptor.extend_from_slice(&le32(crc));
        data_descriptor.extend_from_slice(&le32(compressed.len() as u32));
        data_descriptor.extend_from_slice(&le32(content.len() as u32));
        let mut a_content = compressed.clone();
        a_content.extend_from_slice(&data_descriptor);

        let mut out = Vec::new();
        let manifest_offset = write_local_header(&mut out, b"MANIFEST.json", &manifest_bytes);
        let a_offset = write_local_header_raw(
            &mut out,
            b"a.txt",
            8,      // Deflated
            0x0008, // general-purpose bit 3: sizes deferred to the trailing descriptor
            0,
            0,
            0,
            &[],
            &a_content,
        );

        let central_start = out.len() as u32;
        write_central_entry(
            &mut out,
            b"MANIFEST.json",
            crc32(&manifest_bytes),
            manifest_bytes.len() as u32,
            manifest_offset,
        );
        write_central_entry_raw(
            &mut out,
            b"a.txt",
            8,
            0x0008,
            crc,
            compressed.len() as u32,
            content.len() as u32,
            &[],
            a_offset,
        );
        let central_size = out.len() as u32 - central_start;
        write_eocd(&mut out, 2, central_size, central_start);
        out
    }

    /// Entry 1 is `a.txt`, Deflated, bit 3 *unset* — local and central agree
    /// on every field, including a `compressed_size` that is a flat lie:
    /// the real deflate stream (`compressed`) ends partway through it, and
    /// the rest is `junk`, physically present but never a byte either
    /// header admits to. Because local and central agree exactly,
    /// `validate_header_consistency` finds nothing wrong — there is no
    /// disagreement to find — and because bit 3 is unset, `build_bit3_bundle`'s
    /// refusal does not fire either. Only re-inflating the raw bytes and
    /// noticing the decoder stopped needing input before `compressed_size`
    /// was reached catches this one.
    fn build_slack_bundle() -> Vec<u8> {
        let content: &[u8] = b"hello world\n";
        let compressed = raw_deflate(content);
        let crc = crc32(content);
        let junk = b"JUNK-AFTER-THE-REAL-STREAM-ENDS";
        let declared_compressed_size = (compressed.len() + junk.len()) as u32;

        let manifest_bytes = build_manifest(vec![FileEntry {
            path: "a.txt".to_string(),
            sha256: hex(&Sha256::digest(content)),
            size: content.len() as u64,
            mode: "0644".to_string(),
        }]);

        let mut a_content = compressed.clone();
        a_content.extend_from_slice(junk);

        let mut out = Vec::new();
        let manifest_offset = write_local_header(&mut out, b"MANIFEST.json", &manifest_bytes);
        let a_offset = write_local_header_raw(
            &mut out,
            b"a.txt",
            8, // Deflated
            0, // bit 3 unset — sizes are not deferred, and both headers lie about them identically
            crc,
            declared_compressed_size,
            content.len() as u32,
            &[],
            &a_content,
        );

        let central_start = out.len() as u32;
        write_central_entry(
            &mut out,
            b"MANIFEST.json",
            crc32(&manifest_bytes),
            manifest_bytes.len() as u32,
            manifest_offset,
        );
        write_central_entry_raw(
            &mut out,
            b"a.txt",
            8,
            0,
            crc,
            declared_compressed_size,
            content.len() as u32,
            &[],
            a_offset,
        );
        let central_size = out.len() as u32 - central_start;
        write_eocd(&mut out, 2, central_size, central_start);
        out
    }

    /// Rebuilds `gen.py`'s `upath.zip` vector: a single entry whose raw name
    /// is `notes.txt` on both the local header and the central directory —
    /// in full agreement, so `validate_header_consistency` finds nothing
    /// wrong — but both also carry an *identical* Unicode Path (0x7075)
    /// extra field whose target is `launch.sh`. `zip::ZipFile::name()`
    /// resolves through that field, so `Bundle::open`'s own `path` for this
    /// entry becomes `launch.sh`, not `notes.txt` — and nothing about the
    /// two headers disagreeing ever gets a chance to say so.
    fn build_unicode_path_bundle() -> Vec<u8> {
        let raw_name = b"notes.txt";
        let target = b"launch.sh";
        let content: &[u8] = b"payload";
        let extra = unicode_path_extra(raw_name, target);

        let manifest_bytes = build_manifest(vec![FileEntry {
            path: String::from_utf8(target.to_vec()).unwrap(),
            sha256: hex(&Sha256::digest(content)),
            size: content.len() as u64,
            mode: "0644".to_string(),
        }]);

        let mut out = Vec::new();
        let manifest_offset = write_local_header(&mut out, b"MANIFEST.json", &manifest_bytes);
        let entry_offset = write_local_header_raw(
            &mut out,
            raw_name,
            0, // Stored
            0,
            crc32(content),
            content.len() as u32,
            content.len() as u32,
            &extra,
            content,
        );

        let central_start = out.len() as u32;
        write_central_entry(
            &mut out,
            b"MANIFEST.json",
            crc32(&manifest_bytes),
            manifest_bytes.len() as u32,
            manifest_offset,
        );
        write_central_entry_raw(
            &mut out,
            raw_name,
            0,
            0,
            crc32(content),
            content.len() as u32,
            content.len() as u32,
            &extra,
            entry_offset,
        );
        let central_size = out.len() as u32 - central_start;
        write_eocd(&mut out, 2, central_size, central_start);
        out
    }

    /// Entry 1 is `notes.txt`, **Stored** (not Deflated), with bit 3 set —
    /// `gen.py`'s round-2 `stored-dd.zip` vector's own trick, wrapped inside
    /// an otherwise ordinary bundle rather than left as the bare archive
    /// `testdata/zip-cloaking/stored-dd.zip` is. Bit 3 on a Stored entry is
    /// unusual (there is nothing to defer: its size is as "deferred" as a
    /// length ever gets) but legal per APPNOTE, and `entry.flags().
    /// is_using_data_descriptor()` does not care which compression method
    /// an entry uses. This isolates that: the committed vector gets refused
    /// for an *earlier*, unrelated reason (it has no `MANIFEST.json` at all,
    /// so invariant 1 refuses it first); this fixture is shaped like a real
    /// bundle specifically so the bit-3 check is the thing that catches it.
    fn build_stored_bit3_bundle() -> Vec<u8> {
        let content: &[u8] = b"harmless notes\n";
        let manifest_bytes = build_manifest(vec![FileEntry {
            path: "notes.txt".to_string(),
            sha256: hex(&Sha256::digest(content)),
            size: content.len() as u64,
            mode: "0644".to_string(),
        }]);

        let mut out = Vec::new();
        let manifest_offset = write_local_header(&mut out, b"MANIFEST.json", &manifest_bytes);
        let entry_offset = write_local_header_raw(
            &mut out,
            b"notes.txt",
            0,      // Stored
            0x0008, // general-purpose bit 3, on a Stored entry
            0,
            0,
            0,
            &[],
            content,
        );

        let central_start = out.len() as u32;
        write_central_entry(
            &mut out,
            b"MANIFEST.json",
            crc32(&manifest_bytes),
            manifest_bytes.len() as u32,
            manifest_offset,
        );
        write_central_entry_raw(
            &mut out,
            b"notes.txt",
            0,
            0x0008,
            crc32(content),
            content.len() as u32,
            content.len() as u32,
            &[],
            entry_offset,
        );
        let central_size = out.len() as u32 - central_start;
        write_eocd(&mut out, 2, central_size, central_start);
        out
    }

    /// The ZIP64 Extended Information extra field (tag 0x0001), carrying
    /// only a replacement `compressed_size` — the shape APPNOTE 4.5.3 uses
    /// when just one 32-bit field held the `0xFFFFFFFF` sentinel: the block
    /// holds only the field that was asked for, in order, so here that is
    /// one bare `u64`, no `uncompressed_size` slot reserved ahead of it.
    fn zip64_compressed_size_extra(real_compressed_size: u64) -> Vec<u8> {
        let mut field = Vec::new();
        field.extend_from_slice(&le16(0x0001));
        field.extend_from_slice(&le16(8)); // block size: one u64
        field.extend_from_slice(&real_compressed_size.to_le_bytes());
        field
    }

    /// The same lie `build_slack_bundle` tells — a Deflated entry's
    /// declared `compressed_size` overshoots where its real deflate stream
    /// ends, hiding `junk` in the gap — except this time the base 32-bit
    /// `compressed_size` field holds the ZIP64 sentinel `0xFFFFFFFF`, and
    /// the real (still lying) value lives in a ZIP64 extra field instead.
    /// Bit 3 is unset and local/central agree on everything, including the
    /// sentinel and the extra field, so neither `validate_header_consistency`
    /// nor the bit-3 refusal fire. This exists to prove
    /// `verify_no_deflate_slack` runs against the *resolved* size `zip`
    /// hands back from `entry.compressed_size()` — not the raw sentinel,
    /// and not skipped because resolving it took an extra field to do.
    fn build_zip64_slack_bundle() -> Vec<u8> {
        let content: &[u8] = b"hello world\n";
        let compressed = raw_deflate(content);
        let crc = crc32(content);
        let junk = b"JUNK-AFTER-THE-REAL-STREAM-ENDS";
        let real_compressed_size = (compressed.len() + junk.len()) as u64;
        let extra = zip64_compressed_size_extra(real_compressed_size);

        let manifest_bytes = build_manifest(vec![FileEntry {
            path: "a.txt".to_string(),
            sha256: hex(&Sha256::digest(content)),
            size: content.len() as u64,
            mode: "0644".to_string(),
        }]);

        let mut a_content = compressed.clone();
        a_content.extend_from_slice(junk);

        let mut out = Vec::new();
        let manifest_offset = write_local_header(&mut out, b"MANIFEST.json", &manifest_bytes);
        let a_offset = write_local_header_raw(
            &mut out,
            b"a.txt",
            8, // Deflated
            0, // bit 3 unset
            crc,
            0xFFFF_FFFF, // ZIP64 sentinel: the real compressed_size is in `extra`
            content.len() as u32,
            &extra,
            &a_content,
        );

        let central_start = out.len() as u32;
        write_central_entry(
            &mut out,
            b"MANIFEST.json",
            crc32(&manifest_bytes),
            manifest_bytes.len() as u32,
            manifest_offset,
        );
        write_central_entry_raw(
            &mut out,
            b"a.txt",
            8,
            0,
            crc,
            0xFFFF_FFFF,
            content.len() as u32,
            &extra,
            a_offset,
        );
        let central_size = out.len() as u32 - central_start;
        write_eocd(&mut out, 2, central_size, central_start);
        out
    }

    /// A scratch path that does not need the `tempfile` crate, mirroring
    /// `roundtrip::tempdir`'s reasoning in this same binary.
    struct ScratchFile(std::path::PathBuf);

    impl Drop for ScratchFile {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.0);
        }
    }

    /// Writes `bytes` to a scratch `.astraplugin`, calls `Bundle::open`, and
    /// panics with `what_accepted` if it was accepted — every fixture in
    /// this module is a bundle it must refuse. Returns the refusal's full
    /// context chain (`{:#}`) for the caller's own assertions about *why*.
    fn expect_refused(bytes: &[u8], what_accepted: &str) -> String {
        static NONCE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let nonce = NONCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let path = ScratchFile(std::env::temp_dir().join(format!(
            "astra-plugin-cloak-{}-{:?}-{nonce}.astraplugin",
            std::process::id(),
            std::thread::current().id(),
        )));
        std::fs::write(&path.0, bytes).unwrap();
        match Bundle::open(&path.0) {
            Ok(_) => panic!("{what_accepted}"),
            Err(e) => format!("{e:#}"),
        }
    }

    /// The test this whole module exists for: `Bundle::open` — and so
    /// `astra-plugin verify` and `astra-plugin sign`, which calls it first —
    /// must refuse a bundle whose local headers disagree with its central
    /// directory, rather than silently reading the central directory's view
    /// and calling it verified.
    ///
    /// MUTATION PROOF: deleting the `archive.validate_header_consistency()?`
    /// call this fixes adds to `Bundle::open` (bundle.rs) makes this test
    /// fail — every other invariant `Bundle::open` already checked (entry 0
    /// is `MANIFEST.json` and stored, its hash matches the local header at
    /// offset 0, `MANIFEST.files` is exhaustive, every listed digest and size
    /// matches, the entry command resolves) is satisfied by this fixture on
    /// purpose, because the central directory's own bookkeeping is
    /// self-consistent. Only cross-checking it against the local headers
    /// catches the swap.
    #[test]
    fn verify_refuses_an_archive_whose_local_header_disagrees_with_its_central_directory() {
        let bytes = build_cloaked_bundle();
        let path = ScratchFile(std::env::temp_dir().join(format!(
            "astra-plugin-cloak-{}-{:?}.astraplugin",
            std::process::id(),
            std::thread::current().id()
        )));
        std::fs::write(&path.0, &bytes).unwrap();

        let err = match Bundle::open(&path.0) {
            Ok(_) => panic!(
                "Bundle::open accepted an archive whose local file header names 'evil.txt' \
                 where the central directory claims 'note.txt' at the same offset. `verify` \
                 would vouch for contents an extractor trusting local headers would write under \
                 a different name."
            ),
            Err(e) => format!("{e:#}"),
        };
        assert!(
            err.contains("header-consistency") || err.contains("header inconsistency"),
            "the refusal should name the header-consistency check, not some other invariant: \
             {err}"
        );
        assert!(
            err.contains("filename mismatch") || err.contains("evil.txt") || err.contains("note.txt"),
            "the refusal should be traceable to the name disagreement, not a coincidence: {err}"
        );
    }

    /// Rebuilds the shape `gen.py`'s `slack.zip` vector depends on (minus its
    /// nested-header payload, which `build_slack_bundle` below isolates
    /// instead): a Deflated entry with general-purpose bit 3 set.
    ///
    /// MUTATION PROOF: removing the `entry.flags().is_using_data_descriptor()`
    /// refusal in `Bundle::open` (bundle.rs) makes this test fail. Nothing
    /// else in this fixture is wrong — the deflate stream, its trailing data
    /// descriptor and the central directory's sizes all agree with each
    /// other and with `MANIFEST.files` — so `validate_header_consistency`
    /// and every other existing check pass it. Only the explicit bit-3 ban
    /// catches it, which is the point: bit 3 is what lets a local header's
    /// sizes defer to a value the central directory alone states, the exact
    /// precondition `verify_no_deflate_slack`'s attack needs, so this CLI
    /// refuses the flag outright rather than trusting its own slack check
    /// to catch every byte pattern that flag makes possible.
    #[test]
    fn verify_refuses_a_deflated_entry_with_a_trailing_data_descriptor() {
        let err = expect_refused(
            &build_bit3_bundle(),
            "Bundle::open accepted an entry with general-purpose bit 3 (a trailing data \
             descriptor) set. astra-plugin build never writes one, and bit 3 is exactly what \
             lets a local header's sizes defer to the central directory alone — the \
             precondition the deflate-slack attack needs.",
        );
        assert!(
            err.contains("data descriptor") || err.contains("bit 3"),
            "the refusal should name the data-descriptor flag, not some other invariant: {err}"
        );
    }

    /// A Deflated entry with bit 3 *unset* whose declared `compressed_size`
    /// is a flat lie, agreed on by both the local header and the central
    /// directory: the real deflate stream (for `b"hello world\n"`) ends
    /// partway through the declared region, and 31 bytes of
    /// `JUNK-AFTER-THE-REAL-STREAM-ENDS` fill the rest — physically present,
    /// never admitted to by either header, and never reached by a reader
    /// that decodes forward and stops the moment the real stream ends.
    ///
    /// MUTATION PROOF: removing the `verify_no_deflate_slack` call in
    /// `Bundle::open` makes this test fail. `validate_header_consistency`
    /// finds nothing to object to — local and central agree on every field,
    /// including the lie — and bit 3 is unset, so
    /// `verify_refuses_a_deflated_entry_with_a_trailing_data_descriptor`'s
    /// check does not fire either. Only re-inflating the raw bytes
    /// independently and comparing how much input the real stream actually
    /// needed against the declared size catches this one.
    #[test]
    fn verify_refuses_a_deflated_entry_whose_declared_compressed_size_hides_slack() {
        let err = expect_refused(
            &build_slack_bundle(),
            "Bundle::open accepted an entry whose declared compressed_size runs past where its \
             real deflate stream ends. The trailing bytes are slack a reader that decodes \
             forward and stops there would never look at — exactly where a crafted archive can \
             hide an entire extra file.",
        );
        assert!(
            err.contains("slack") || err.contains("compressed size"),
            "the refusal should be traceable to the slack/size check, not a coincidence: {err}"
        );
    }

    /// Rebuilds `gen.py`'s `upath.zip` vector exactly: a single entry named
    /// `notes.txt` on both the local header and the central directory — in
    /// full agreement — but both also carry an identical Unicode Path
    /// (0x7075) extra field targeting `launch.sh`.
    ///
    /// MUTATION PROOF: removing the `extra_data_fields` scan for
    /// `ExtraField::UnicodePath`/the 0x7075 `Custom` tag in `Bundle::open`
    /// makes this test fail. `validate_header_consistency` finds nothing
    /// wrong here either — local and central carry byte-for-byte the same
    /// extra field, so there is no disagreement for it to catch — and
    /// `zip::ZipFile::name()` resolves through the field to `launch.sh`,
    /// which this fixture also lists (correctly) in `MANIFEST.files`, so
    /// every other existing check — exhaustiveness, the digest, the entry
    /// command — passes too. Only refusing the field outright, agreement or
    /// not, catches a reader that would have resolved `notes.txt` instead.
    #[test]
    fn verify_refuses_an_entry_with_a_unicode_path_extra_field() {
        let err = expect_refused(
            &build_unicode_path_bundle(),
            "Bundle::open accepted an entry carrying a Unicode Path (0x7075) extra field. A \
             reader that resolves names through this field and one that does not would extract \
             the same bytes under two different names.",
        );
        assert!(
            err.contains("Unicode Path") || err.contains("0x7075"),
            "the refusal should name the Unicode Path extra field, not some other invariant: \
             {err}"
        );
    }

    /// `build_stored_bit3_bundle`, isolated: a **Stored** entry with bit 3
    /// set, inside an otherwise ordinary bundle.
    ///
    /// MUTATION PROOF: removing the `entry.flags().is_using_data_descriptor()`
    /// refusal makes this test fail. Nothing else here is wrong — the
    /// entry's declared size (0, deferred) and its mode are exactly what a
    /// Stored, bit-3 entry's local header is supposed to say, matching the
    /// central directory's real values, and `MANIFEST.files` is accurate —
    /// so only the bit-3 ban itself catches a Stored entry carrying it,
    /// proving the check does not quietly assume Deflated.
    #[test]
    fn verify_refuses_a_stored_entry_with_a_trailing_data_descriptor() {
        let err = expect_refused(
            &build_stored_bit3_bundle(),
            "Bundle::open accepted a Stored entry with general-purpose bit 3 (a trailing data \
             descriptor) set. The bit-3 refusal must not assume Deflated.",
        );
        assert!(
            err.contains("data descriptor") || err.contains("bit 3"),
            "the refusal should name the data-descriptor flag, not some other invariant: {err}"
        );
    }

    /// Resolves `testdata/zip-cloaking/<name>` and checks its sha256 against
    /// the shared `SHA256SUMS` recorded beside it in that same directory —
    /// never a hash pinned in this crate's own source — so a vector edited
    /// in place, or a `SHA256SUMS` that drifted from it, fails loudly here
    /// instead of silently testing bytes nobody meant to test.
    ///
    /// This directory is the shared golden every consumer of these vectors
    /// pins (`testdata/zip-cloaking/README.md`): the registry bot, the
    /// games catalogue, minice's upload ingest, the Astra daemon, and this
    /// CLI. Reading it from here rather than keeping a private copy is what
    /// makes "the same bytes" true instead of asserted — see `gen.py` and
    /// `gen_stored_dd.py` in that directory for how the goldens were made.
    fn zip_cloaking_vector(name: &str) -> std::path::PathBuf {
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .expect("astra-plugin-cli has a parent directory")
            .join("testdata/zip-cloaking");
        let path = dir.join(name);
        let bytes = std::fs::read(&path).unwrap_or_else(|e| {
            panic!(
                "{} is missing or unreadable: {e}. It is committed; a checkout without it is \
                 incomplete, not a reason to skip.",
                path.display()
            )
        });
        let sums = std::fs::read_to_string(dir.join("SHA256SUMS"))
            .expect("testdata/zip-cloaking/SHA256SUMS is missing");
        let want = sums
            .lines()
            .find_map(|line| {
                let (hash, file) = line.split_once("  ")?;
                (file == name).then(|| hash.to_string())
            })
            .unwrap_or_else(|| panic!("SHA256SUMS has no entry for {name}"));
        let got = hex(&Sha256::digest(&bytes));
        assert_eq!(
            got, want,
            "{} does not match the sha256 recorded in SHA256SUMS — either the vector was edited \
             in place, or SHA256SUMS is stale. Regenerate with gen.py/gen_stored_dd.py; do not \
             patch either file by hand.",
            path.display()
        );
        path
    }

    /// `testdata/zip-cloaking/stored-dd.zip`, received from astra-ce's
    /// second review round, kept byte-for-byte rather than rebuilt: a
    /// Stored entry (`notes.txt`) with bit 3 set, whose real trailing data
    /// descriptor sits *after* a second entry (`launch.sh`) rather than
    /// right after its own content, with a CRC32 computed over all three
    /// (`notes.txt`'s content plus `launch.sh`'s entire local header and
    /// content) — so a streaming reader with no central directory, hunting
    /// for a CRC match to learn where `notes.txt` ends, absorbs `launch.sh`
    /// whole and never sees it as a separate entry.
    ///
    /// `Bundle::open` refuses this file — but for an earlier, unrelated
    /// reason than the bit-3 flag: it has no `MANIFEST.json` at all (it is
    /// not a `.astraplugin` bundle, just a bare ZIP exercising the
    /// underlying container format this reader hardens), so invariant 1 —
    /// the very first thing `Bundle::open` checks, straight off the raw
    /// bytes at offset 0 — refuses it before the bit-3 check is ever
    /// reached. `verify_refuses_a_stored_entry_with_a_trailing_data_descriptor`
    /// above is what proves the bit-3 mechanism itself catches this shape
    /// when it is wrapped in something that otherwise looks like a bundle;
    /// this test is the literal committed vector, kept refused.
    #[test]
    fn verify_refuses_the_committed_stored_bit3_vector() {
        let path = zip_cloaking_vector("stored-dd.zip");
        // Refused — for whichever reason; see the doc comment above.
        if Bundle::open(&path).is_ok() {
            panic!(
                "Bundle::open accepted testdata/zip-cloaking/stored-dd.zip, a Stored bit-3 \
                 entry whose real data descriptor sits after the next entry"
            );
        }
    }

    /// `testdata/zip-cloaking/slack.zip` — the committed, cross-consumer
    /// vector for the same deflate-slack-plus-bit-3 shape
    /// `build_bit3_bundle`/`build_slack_bundle` isolate separately above.
    /// This one is the integrated attack as astra-ce's review wrote it: a
    /// bit-3 Deflated entry (`a.txt`) whose declared `compressed_size`
    /// swallows a nested local header (`readme.txt`) that itself contains
    /// the *real* next entry's local header and content (`launch.sh`), so
    /// a streaming reader with no central directory sees `a.txt` +
    /// `readme.txt` while a central-directory reader sees `a.txt` +
    /// `launch.sh`.
    ///
    /// Like `stored-dd.zip`, this is refused by `Bundle::open`'s invariant
    /// 1 before the bit-3 check is reached — it is not a `.astraplugin`,
    /// just the bare container. The isolated fixtures above are what prove
    /// the specific checks; this is the literal shared golden, kept
    /// refused and kept byte-identical to `SHA256SUMS` by
    /// `zip_cloaking_vector`.
    #[test]
    fn verify_refuses_the_committed_slack_vector() {
        let path = zip_cloaking_vector("slack.zip");
        if Bundle::open(&path).is_ok() {
            panic!(
                "Bundle::open accepted testdata/zip-cloaking/slack.zip, a bit-3 Deflated entry \
                 whose declared compressed_size hides a second entry's local header"
            );
        }
    }

    /// `testdata/zip-cloaking/upath.zip` — the committed, cross-consumer
    /// vector for the same Unicode Path shape `build_unicode_path_bundle`
    /// isolates separately above, kept byte-identical to `SHA256SUMS` by
    /// `zip_cloaking_vector`. Refused by `Bundle::open`'s invariant 1 for
    /// the same reason as the other two committed vectors: it carries no
    /// `MANIFEST.json`.
    #[test]
    fn verify_refuses_the_committed_unicode_path_vector() {
        let path = zip_cloaking_vector("upath.zip");
        if Bundle::open(&path).is_ok() {
            panic!(
                "Bundle::open accepted testdata/zip-cloaking/upath.zip, an entry carrying a \
                 Unicode Path (0x7075) extra field"
            );
        }
    }

    /// `build_zip64_slack_bundle`, isolated: the same `compressed_size`
    /// overshoot `verify_refuses_a_deflated_entry_whose_declared_compressed_size_hides_slack`
    /// proves, except the real (still lying) size is resolved from a ZIP64
    /// extra field rather than stated directly in the 32-bit header.
    ///
    /// MUTATION PROOF: removing the `verify_no_deflate_slack` call makes
    /// this test fail too — the same mutation
    /// `verify_refuses_a_deflated_entry_whose_declared_compressed_size_hides_slack`
    /// pins, now proven against a size this reader had to resolve through
    /// `zip`'s own ZIP64 handling first rather than read verbatim. That
    /// resolution happens before `Bundle::open` ever sees a number — see
    /// `ZipFileData::apply_extra_fields` in the `zip` crate — so there was
    /// no separate branch in `verify_no_deflate_slack` that could have
    /// skipped it; this is what confirms that rather than assuming it.
    #[test]
    fn verify_refuses_a_deflated_entry_whose_zip64_resolved_compressed_size_hides_slack() {
        let err = expect_refused(
            &build_zip64_slack_bundle(),
            "Bundle::open accepted an entry whose ZIP64-resolved compressed_size runs past \
             where its real deflate stream ends.",
        );
        assert!(
            err.contains("slack") || err.contains("compressed size"),
            "the refusal should be traceable to the slack/size check, not a coincidence: {err}"
        );
    }
}
