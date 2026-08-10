//! Which host is this, and which registry artifact key does it ask for.
//!
//! One mapping, in one place. The pair of independent `cfg!` chains this
//! replaced is what let a macOS host be "incompatible" in the manifest check and
//! "linux-x64" in the download lookup at the same time.

use serde::Deserialize;

/// Platform requirements — `[platform]` in `plugin.toml`.
///
/// Both lists empty means "any host". A non-empty list is a whitelist matched
/// against [`current_platform`].
#[derive(Debug, Clone, Default, Deserialize)]
pub struct PlatformRequirements {
    #[serde(default)]
    pub os: Vec<String>,
    #[serde(default)]
    pub arch: Vec<String>,
}

/// Every artifact key the registry schema reserves, in the order a generator
/// should emit them.
///
/// Only [`platform_key_for`] decides which of these a *running daemon* accepts,
/// and it accepts two. The rest are reserved so the index format never has to
/// change if Astra later ships those hosts, and so a registry validator can
/// reject a typo (`mac-arm64`, `linux-amd64`) instead of writing a key no
/// daemon will ever look up.
///
/// **Reserved is not supported.** Astra's release workflow builds neither a
/// macOS nor an arm64 daemon, so a bundle published under `macos-x64`,
/// `macos-arm64`, `linux-arm64` or `windows-arm64` has no host to run on. A
/// generator that emits one is publishing a file nobody can install.
///
/// `noarch` is the interpreted-language case (TypeScript, Python). It is
/// reserved here for validators, but the daemon does **not** look it up: per
/// the bundle spec the index writes the same URL and digest under every
/// *supported* platform key, so a `noarch` bundle is found under `linux-x64` /
/// `windows-x64` like any other.
///
/// Nothing in the daemon's runtime path reads this list — its consumers are the
/// index generator in the registry repo, the CLI's `check`, and the test below
/// that keeps the halves honest. It lives next to the function that decides
/// which of these keys is real, because that is the only place the two facts
/// can be read together.
pub const RESERVED_PLATFORM_KEYS: &[&str] = &[
    // Supported — a daemon exists for these and `platform_key_for` returns them.
    "linux-x64",
    "windows-x64",
    // Reserved, never emitted: no daemon ships for these hosts.
    "linux-arm64",
    "windows-arm64",
    "macos-x64",
    "macos-arm64",
    // Reserved for validators; expanded to the supported keys by the index
    // generator rather than looked up at install time.
    "noarch",
];

/// The `os` values `[platform] os = [...]` may name, in the vocabulary
/// [`current_platform`] speaks.
///
/// Wider than the set Astra ships a daemon for: declaring `os = ["macos"]` is a
/// statement about the plugin, not a claim that a host exists, and a validator
/// that rejected it would be rejecting a correct manifest.
pub const KNOWN_OS_VALUES: &[&str] = &["linux", "windows", "macos"];

/// The `arch` values `[platform] arch = [...]` may name.
pub const KNOWN_ARCH_VALUES: &[&str] = &["x86_64", "aarch64"];

/// The host this daemon runs on is not one Astra publishes plugin artifacts for.
///
/// Returned instead of silently falling back to another platform's key. The
/// fallback is what this type exists to prevent: before it, a macOS host
/// resolved to `linux-x64`, downloaded a Linux ELF, and failed at exec with an
/// error that named neither the platform nor the download.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[error(
    "PLATFORM_UNSUPPORTED: Astra publishes no plugin artifacts for {os}-{arch}. \
     Supported hosts: linux-x86_64, windows-x86_64."
)]
pub struct UnsupportedHost {
    pub os: String,
    pub arch: String,
}

/// Map an `(os, arch)` pair — in the vocabulary [`current_platform`] speaks —
/// to the registry artifact key for that host.
///
/// This is the **only** place the mapping exists.
/// [`crate::PluginManifest::is_platform_compatible`] matches a manifest's
/// `[platform]` lists against [`current_platform`] and the registry client looks
/// up `platform_downloads` by the key this returns; both therefore describe the
/// same host by construction.
///
/// An unknown host is an `Err`, never a default. See [`RESERVED_PLATFORM_KEYS`]
/// for why macOS and arm64 are not in the `Ok` arm.
pub fn platform_key_for(os: &str, arch: &str) -> Result<&'static str, UnsupportedHost> {
    match (os, arch) {
        ("linux", "x86_64") => Ok("linux-x64"),
        ("windows", "x86_64") => Ok("windows-x64"),
        _ => Err(UnsupportedHost {
            os: os.to_string(),
            arch: arch.to_string(),
        }),
    }
}

/// The registry artifact key for the host this build runs on.
///
/// `Err` on a host Astra ships no daemon for — a build that reaches this on
/// macOS or arm64 must refuse the download, not pick a neighbour's bundle.
pub fn host_platform_key() -> Result<&'static str, UnsupportedHost> {
    let (os, arch) = current_platform();
    platform_key_for(os, arch)
}

/// The OS / architecture strings this build matches `[platform]` requirements
/// against. Returned as a pair so an error message can name the host in the same
/// vocabulary the manifest uses (`os = ["windows"]`, `arch = ["x86_64"]`).
pub fn current_platform() -> (&'static str, &'static str) {
    let os = if cfg!(windows) {
        "windows"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else {
        "unknown"
    };

    let arch = if cfg!(target_arch = "x86_64") {
        "x86_64"
    } else if cfg!(target_arch = "aarch64") {
        "aarch64"
    } else {
        "unknown"
    };

    (os, arch)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The two hosts Astra actually releases a daemon for, and nothing else.
    ///
    /// Written as a table over *strings* rather than through
    /// `host_platform_key()` so the macOS and arm64 arms are exercised on the
    /// Linux CI runner — the whole point of the change is a host this test
    /// suite never runs on.
    #[test]
    fn platform_key_covers_exactly_the_hosts_astra_ships() {
        assert_eq!(platform_key_for("linux", "x86_64").unwrap(), "linux-x64");
        assert_eq!(
            platform_key_for("windows", "x86_64").unwrap(),
            "windows-x64"
        );
    }

    /// A macOS host must produce a NAMED error, not another platform's key.
    ///
    /// Before this, `get_download_url()`'s own `cfg!` chain fell through to
    /// `linux-x64` on macOS: the daemon downloaded a Linux ELF and tried to
    /// exec it. The regression this guards is a silent one, so the assertion is
    /// on the error text too — `PLATFORM_UNSUPPORTED` is the code §4.6 of the
    /// production plan puts in front of the user.
    #[test]
    fn a_macos_host_is_refused_by_name_not_resolved_to_linux() {
        let err = platform_key_for("macos", "x86_64").expect_err("macOS must not resolve to a key");
        assert_eq!(err.os, "macos");
        assert_eq!(err.arch, "x86_64");
        let msg = err.to_string();
        assert!(msg.contains("PLATFORM_UNSUPPORTED"), "message was {msg:?}");
        assert!(msg.contains("macos-x86_64"), "message was {msg:?}");
        assert!(
            !msg.contains("linux-x64"),
            "must not name a fallback: {msg:?}"
        );

        // Apple silicon, and the arm64 hosts on the other two OSes.
        assert!(platform_key_for("macos", "aarch64").is_err());
        assert!(platform_key_for("linux", "aarch64").is_err());
        assert!(platform_key_for("windows", "aarch64").is_err());
        // `current_platform()` yields "unknown" rather than panicking on an
        // exotic target; that must not become a key either.
        assert!(platform_key_for("unknown", "unknown").is_err());
    }

    /// The reserved-key list is the registry schema's vocabulary. Every key a
    /// daemon can actually ask for must appear in it, or the generator would be
    /// free to reject the one key that matters.
    #[test]
    fn every_supported_key_is_a_reserved_key() {
        for (os, arch) in [("linux", "x86_64"), ("windows", "x86_64")] {
            let key = platform_key_for(os, arch).unwrap();
            assert!(
                RESERVED_PLATFORM_KEYS.contains(&key),
                "{key} is returned by platform_key_for but absent from the schema list"
            );
        }
        for reserved in ["macos-x64", "macos-arm64", "linux-arm64", "windows-arm64"] {
            assert!(RESERVED_PLATFORM_KEYS.contains(&reserved));
        }
    }

    /// The host key and the manifest compatibility check read the same source,
    /// so on any host where one says "linux" the other says "linux-x64".
    #[test]
    fn host_key_agrees_with_current_platform() {
        let (os, arch) = current_platform();
        assert_eq!(host_platform_key(), platform_key_for(os, arch));
    }

    /// The vocabulary a validator checks `[platform]` against has to contain
    /// every string `current_platform` can produce, or `astra-plugin check`
    /// would flag a manifest that names this very machine.
    #[test]
    fn the_known_vocabularies_cover_every_host_astra_ships() {
        for (os, arch) in [("linux", "x86_64"), ("windows", "x86_64")] {
            assert!(KNOWN_OS_VALUES.contains(&os));
            assert!(KNOWN_ARCH_VALUES.contains(&arch));
            assert!(platform_key_for(os, arch).is_ok());
        }
        // Declaring a host Astra does not ship a daemon for is a legal manifest.
        assert!(KNOWN_OS_VALUES.contains(&"macos"));
        assert!(KNOWN_ARCH_VALUES.contains(&"aarch64"));
    }
}
