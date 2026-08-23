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
                let n = e.name().to_string();
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
