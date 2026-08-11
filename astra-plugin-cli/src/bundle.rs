//! The `.astraplugin` bundle format, version 2 — one definition, shared by
//! `astra-plugin build` (which writes it) and `astra-plugin verify` (which
//! reads it back).
//!
//! Everything downstream consumes what is defined here: the daemon's installer
//! re-derives the same digests, the release workflow publishes them as the
//! attestation subject, and the registry index carries them as the number a
//! user's machine checks before it extracts a byte. So the format is a
//! contract, and the invariants below are the contract's terms.
//!
//! # The four invariants
//!
//! 1. **`MANIFEST.json` is the first entry and is STORED.** A reader can lift
//!    the manifest out of the local file header at offset 0 — see
//!    [`manifest_from_local_header`] — without an inflate, without the central
//!    directory, and without trusting the rest of the file. That matters
//!    because the manifest is what tells the reader which files it is *allowed*
//!    to find; a reader that had to parse the whole archive first would already
//!    have walked untrusted structure to learn what it should have been.
//!
//! 2. **The artifact digest is `sha256` of the whole file.** Not of the
//!    entries, not of a canonicalisation. One number, in three places (the
//!    attestation subject, the index record, and what the daemon hashes), and
//!    no canonicalisation questions. The retired in-ZIP scheme —
//!    `SHA256(name₀‖content₀‖name₁‖content₁‖…)`, no delimiters — is ambiguous:
//!    entry `"ab"`/content `"c"` collides with `"a"`/`"bc"`.
//!
//! 3. **The manifest digest is domain-separated:**
//!    `SHA256("astra.bundle/2\0" ‖ manifest_bytes)`. A bare `sha256(bytes)`
//!    would let a manifest digest and a file digest be confused for one
//!    another wherever the two travel as the same 64 hex characters — and
//!    `files[]` is full of file digests.
//!
//! 4. **`files` is exhaustive in both directions.** Every archive entry
//!    appears in `files` (minus the small, named exempt set) and every listed
//!    file exists in the archive. One direction alone is a hole: checking only
//!    "listed ⇒ present" lets an attacker *add* an entry that the extractor
//!    writes and nothing hashes; checking only "present ⇒ listed" lets them
//!    *drop* one and call the bundle intact.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::{BufReader, Read, Seek, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use zip::write::SimpleFileOptions;

/// The `schema` value every v2 manifest carries, and the domain-separation
/// prefix's stem. A reader that does not recognise this string must refuse the
/// bundle rather than guess.
pub const SCHEMA: &str = "astra.bundle/2";

/// Domain-separation prefix for [`manifest_digest`]: `"astra.bundle/2\0"`.
const MANIFEST_DIGEST_DOMAIN: &[u8] = b"astra.bundle/2\x00";

/// The manifest entry's archive path. First entry, always, stored.
pub const MANIFEST_ENTRY: &str = "MANIFEST.json";

/// The plugin manifest the daemon parses. Always present in a v2 bundle.
pub const PLUGIN_TOML_ENTRY: &str = "plugin.toml";

/// The retiring in-ZIP signature pair. Appended last, in this order, after the
/// manifest and every listed file, because the legacy digest they cover is
/// computed over the entries that precede them.
pub const LEGACY_SIGNATURE_ENTRY: &str = "SIGNATURE";
pub const LEGACY_PUBKEY_ENTRY: &str = "PUBKEY";

/// The release in which the legacy pair leaves the format: `astra-plugin sign`
/// is removed, [`append_legacy_signature`] and both constants above go with it,
/// and `PUBKEY` stops being a name this format knows.
///
/// Named once, here, and quoted verbatim by every message that mentions the
/// retirement, so the CLI cannot promise the author one date while the daemon
/// plans another. Its counterpart on the daemon side is
/// `plugins::trust::LEGACY_SIGNATURE_SUNSET`, and the two strings agree by
/// review — there is no shared crate to make them agree by construction, which
/// is exactly why they are single constants and not inlined prose.
pub const LEGACY_PAIR_SUNSET: &str = "astra-plugin 0.5.0 / Astra 0.4.0";

/// Archive entries that are deliberately absent from `MANIFEST.files`.
///
/// `MANIFEST.json` cannot list its own digest, and the legacy pair is computed
/// *over* the listed files, so neither can appear in the list it authenticates.
/// This set is closed and short on purpose: everything outside it must be
/// listed, which is what makes the "present ⇒ listed" direction meaningful.
pub const UNLISTED_ENTRIES: &[&str] =
    &[MANIFEST_ENTRY, LEGACY_SIGNATURE_ENTRY, LEGACY_PUBKEY_ENTRY];

/// Deflate level pinned for `--reproducible`.
///
/// `None` means "the encoder's default", which is a property of whichever
/// flate2 backend happened to be compiled in — not of this format. Reproducible
/// output cannot depend on that, so the level is named here.
pub const REPRODUCIBLE_COMPRESSION_LEVEL: i64 = 6;

/// Fixed modification time for every entry under `--reproducible`:
/// 1980-01-01 00:00:00, the earliest a DOS timestamp can express.
///
/// `zip`'s default happens to be this today *only because* the `time` feature
/// is off; with it on, `DateTime::default_for_write()` is `now()`. Naming it
/// here means enabling a cargo feature elsewhere cannot silently stamp build
/// times into every bundle.
pub fn fixed_mtime() -> zip::DateTime {
    zip::DateTime::default()
}

/// The plugin wire protocol a bundle built by this CLI declares.
///
/// Must track `spec/hooks.yaml`'s `protocol:` and the SDKs'
/// `PROTOCOL_VERSION`. It is the version the *host* must support, so it may be
/// pinned lower by a plugin built against an older SDK — `[bundle] protocol`
/// in plugin.toml overrides it. Over-claiming is the dangerous direction: it
/// makes an installable plugin refuse to install.
pub const PLUGIN_PROTOCOL_VERSION: u32 = 1;

/// Ceilings from `spec/limits.yaml` — the daemon refuses to extract past
/// these, so a bundle that exceeds one is uninstallable and must not be built.
/// Keep in sync with `spec/limits.yaml`; the daemon's copy is generated.
pub const MAX_EXTRACT_BYTES: u64 = 524_288_000;
pub const MAX_ARCHIVE_ENTRIES: usize = 10_000;

/// A manifest is metadata; four megabytes of it is a reader-exhaustion attempt,
/// not a plugin.
const MAX_MANIFEST_BYTES: u64 = 4 * 1024 * 1024;

// ---------------------------------------------------------------------------
// Targets
// ---------------------------------------------------------------------------

/// The platform a bundle is built for.
///
/// The string forms are **the registry's platform keys**, verbatim: they are
/// what `platform_downloads` is keyed by in the index and what the daemon's
/// `get_download_url` looks up. One vocabulary, so a bundle filename, an index
/// key and a daemon lookup cannot agree in two places and disagree in a third.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Target {
    LinuxX64,
    WindowsX64,
    /// Platform-independent: TypeScript and Python plugins, which ship source
    /// or bytecode and are run by a runtime the host already has. The index
    /// writes the same URL and digest under every supported platform key, so
    /// no daemon change is needed to install one.
    Noarch,
}

impl Target {
    pub const ALL: &'static [Target] = &[Target::LinuxX64, Target::WindowsX64, Target::Noarch];

    /// The registry platform key. This string appears in the bundle filename,
    /// in `index.json`, and in the daemon's platform lookup.
    pub fn key(self) -> &'static str {
        match self {
            Target::LinuxX64 => "linux-x64",
            Target::WindowsX64 => "windows-x64",
            Target::Noarch => "noarch",
        }
    }

    pub fn parse(s: &str) -> Result<Target> {
        Target::ALL
            .iter()
            .copied()
            .find(|t| t.key() == s)
            .with_context(|| {
                format!(
                    "Unknown target '{s}'. Valid targets: {}",
                    Target::ALL
                        .iter()
                        .map(|t| t.key())
                        .collect::<Vec<_>>()
                        .join(", ")
                )
            })
    }

    /// The target that matches the machine this CLI is running on.
    ///
    /// An unhandled host is a hard error, never a fall-through to a plausible
    /// neighbour: a macOS build that quietly resolved to `linux-x64` would
    /// produce a bundle named for a platform whose ELF it does not contain.
    pub fn host() -> Result<Target> {
        match (std::env::consts::OS, std::env::consts::ARCH) {
            ("linux", "x86_64") => Ok(Target::LinuxX64),
            ("windows", "x86_64") => Ok(Target::WindowsX64),
            (os, arch) => bail!(
                "No plugin bundle target exists for {os}-{arch}. Astra ships neither a macOS \
                 nor an arm64 daemon, so a bundle for this host would have nothing to run on. \
                 Pass --target explicitly (linux-x64, windows-x64, noarch) to cross-pack."
            ),
        }
    }

    /// `MANIFEST.platform`, the `{os, arch}` pair. `noarch` is `any`/`any`.
    pub fn platform(self) -> Platform {
        match self {
            Target::LinuxX64 => Platform::new("linux", "x86_64"),
            Target::WindowsX64 => Platform::new("windows", "x86_64"),
            Target::Noarch => Platform::new("any", "any"),
        }
    }

    /// The inverse of [`Target::platform`] — how a reader turns the manifest's
    /// `{os, arch}` back into a registry key without a second table.
    pub fn from_platform(p: &Platform) -> Result<Target> {
        Target::ALL
            .iter()
            .copied()
            .find(|t| t.platform() == *p)
            .with_context(|| {
                format!(
                    "MANIFEST.platform {{os: \"{}\", arch: \"{}\"}} names no bundle target",
                    p.os, p.arch
                )
            })
    }

    /// What `[platform]` in the packed plugin.toml says. The daemon reads
    /// `os`/`arch` as lists where empty means "no requirement", so `noarch`
    /// stamps two empty lists rather than the literal string `any`.
    pub fn toml_platform(self) -> (Vec<String>, Vec<String>) {
        match self {
            Target::Noarch => (vec![], vec![]),
            other => {
                let p = other.platform();
                (vec![p.os], vec![p.arch])
            }
        }
    }

    /// Whether a native binary built on this host can be packed for `self`.
    pub fn matches_host_os(self) -> bool {
        match self {
            Target::Noarch => true,
            Target::LinuxX64 => std::env::consts::OS == "linux",
            Target::WindowsX64 => std::env::consts::OS == "windows",
        }
    }
}

/// `MANIFEST.platform`. Owned `&'static str` pairs in practice, but
/// deserialised from arbitrary input on the read path.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Platform {
    pub os: String,
    pub arch: String,
}

impl Platform {
    fn new(os: &str, arch: &str) -> Platform {
        Platform {
            os: os.to_string(),
            arch: arch.to_string(),
        }
    }
}

// ---------------------------------------------------------------------------
// The manifest
// ---------------------------------------------------------------------------

/// `MANIFEST.json`, exactly the shape in PRODUCTION_PLAN §5.2.
///
/// Field order here is the serialised field order — keep it stable, because
/// the manifest bytes are what [`manifest_digest`] covers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BundleManifest {
    pub schema: String,
    pub plugin_id: String,
    pub version: String,
    pub platform: Platform,
    pub protocol: u32,
    pub min_astra_version: String,
    pub capabilities: Vec<String>,
    /// The `[permissions]` section of `plugin.toml`, verbatim — permission id →
    /// the whole request, not just its `reason`.
    ///
    /// §5.6 gave this a vocabulary in Phase 4 and the daemon now *enforces* it:
    /// a registry install's granted set is read out of the trust record, which
    /// is written from these bytes. So anything dropped here is a permission the
    /// user can never grant, no matter what the author declared.
    pub permissions: BTreeMap<String, ManifestPermission>,
    /// `sha256:<hex>` over [`canonical_permissions`]. Carries its algorithm
    /// prefix because it is compared against a value the *registry* computed,
    /// across a repo boundary; `files[].sha256` is bare hex because both ends
    /// of that comparison live in this file.
    pub permissions_hash: String,
    pub entry: ManifestEntry,
    /// Sorted by `path`, byte-lexicographically. Exhaustive in both directions
    /// against the archive, minus [`UNLISTED_ENTRIES`].
    pub files: Vec<FileEntry>,
}

/// One `[permissions]` entry as it appears in `MANIFEST.json`.
///
/// **This is the daemon's own type, aliased — not a copy of it.**
/// [`astra_plugin_manifest::PermissionRequest`] is what
/// `astra-daemon/src/plugins/manifest.rs` deserialises `plugin.toml` into and
/// what §5.6's grant resolution reads, and this crate already links that crate
/// under `tools/check-manifest-crate.sh`'s byte-equality check.
///
/// It was a local one-field struct (`reason` only) until Phase 4, which was
/// defensible while `[permissions]` had no vocabulary and defensible no longer
/// once it did. That struct dropped two things on the floor:
///
/// * `subscribe_events.types` — an **allowlist the daemon enforces per event**,
///   where empty allows nothing. Packing it away meant a registry-published
///   plugin's trust record granted `subscribe_events` over no types at all, and
///   every subscription it opened was refused. Sideload and import were
///   unaffected, which is why it survived testing: those read `plugin.toml`
///   directly and never pass through this packer.
/// * `set_variable.scopes` — reserved today, silently unpublishable tomorrow.
///
/// It also canonicalised differently. `PermissionRequest` skips an empty
/// `reason`, so `set_variable = {}` is `{}`; the local struct always emitted it,
/// so the same declaration was `{"reason":""}` here and `{}` in the daemon.
/// Nothing went red — every side recomputes `permissions_hash` from
/// `MANIFEST.permissions` and so agrees with itself — but two canonical
/// spellings of one declaration is precisely the drift that hash exists to
/// prevent, and aliasing the type makes a third spelling unrepresentable.
pub type ManifestPermission = astra_plugin_manifest::PermissionRequest;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManifestEntry {
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEntry {
    pub path: String,
    /// Lowercase hex, no algorithm prefix.
    pub sha256: String,
    pub size: u64,
    /// Octal, four digits, e.g. `"0755"`. A string, not a number, because JSON
    /// has no octal literal and `755` decimal is a different mode from `0o755`.
    pub mode: String,
}

impl BundleManifest {
    /// The bytes that [`manifest_digest`] covers and that go into the archive.
    ///
    /// Pretty-printed with a trailing newline: a human reading a failed
    /// verification needs to diff this, and the digest is over whatever bytes
    /// are written either way.
    pub fn to_bytes(&self) -> Result<Vec<u8>> {
        let mut bytes = serde_json::to_vec_pretty(self).context("Failed to serialise MANIFEST")?;
        bytes.push(b'\n');
        Ok(bytes)
    }

    pub fn target(&self) -> Result<Target> {
        Target::from_platform(&self.platform)
    }

    /// The filename this manifest's bundle must have:
    /// `<id>-<version>-<target>.astraplugin`.
    pub fn artifact_name(&self) -> Result<String> {
        Ok(format!(
            "{}-{}-{}.astraplugin",
            self.plugin_id,
            self.version,
            self.target()?.key()
        ))
    }

    fn file(&self, path: &str) -> Option<&FileEntry> {
        self.files.iter().find(|f| f.path == path)
    }
}

/// `SHA256("astra.bundle/2\0" ‖ manifest_bytes)`, lowercase hex.
///
/// The prefix is the whole point: without it this is `sha256(some bytes)`, the
/// same shape as every `files[].sha256`, and a value lifted from one context
/// verifies in the other.
pub fn manifest_digest(manifest_bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(MANIFEST_DIGEST_DOMAIN);
    hasher.update(manifest_bytes);
    hex(&hasher.finalize())
}

/// Canonical bytes of the permission map: compact JSON with keys in byte order.
///
/// `BTreeMap` gives the sort and `serde_json`'s compact form gives the
/// whitespace-free encoding, which is RFC 8785 for a value of this shape
/// (strings and objects only — no numbers, where JCS's rules actually bite).
pub fn canonical_permissions(
    permissions: &BTreeMap<String, ManifestPermission>,
) -> Result<Vec<u8>> {
    serde_json::to_vec(permissions).context("Failed to canonicalise permissions")
}

pub fn permissions_hash(permissions: &BTreeMap<String, ManifestPermission>) -> Result<String> {
    Ok(format!(
        "sha256:{}",
        hex(&Sha256::digest(canonical_permissions(permissions)?))
    ))
}

pub fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        use std::fmt::Write;
        let _ = write!(s, "{b:02x}");
    }
    s
}

/// `sha256` of a whole file, streamed. This is the artifact digest when the
/// file is a `.astraplugin`.
pub fn sha256_file(path: &Path) -> Result<(String, u64)> {
    let file = File::open(path).with_context(|| format!("Failed to open {}", path.display()))?;
    let mut reader = BufReader::new(file);
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 64 * 1024];
    let mut size = 0u64;
    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
        size += n as u64;
    }
    Ok((hex(&hasher.finalize()), size))
}

pub fn format_mode(mode: u32) -> String {
    format!("{:04o}", mode & 0o7777)
}

pub fn parse_mode(s: &str) -> Result<u32> {
    let trimmed = s.strip_prefix("0o").unwrap_or(s);
    u32::from_str_radix(trimmed, 8).with_context(|| format!("Invalid octal file mode '{s}'"))
}

// ---------------------------------------------------------------------------
// Archive paths
// ---------------------------------------------------------------------------

/// Names Windows cannot create no matter what follows the dot.
const DOS_RESERVED: &[&str] = &[
    "con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8",
    "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
];

/// Refuse, at build time, any path that an extractor would have to refuse at
/// install time.
///
/// The daemon has to make these checks too — it cannot trust a bundle it did
/// not build. Making them here as well means the author finds out on their own
/// machine instead of from a user's failed install.
pub fn check_archive_path(path: &str) -> Result<()> {
    if path.is_empty() {
        bail!("Empty archive path");
    }
    if path.contains('\\') {
        bail!("Archive path '{path}' contains a backslash; ZIP paths use '/' only");
    }
    if path.starts_with('/') {
        bail!("Archive path '{path}' is absolute");
    }
    if path.contains(':') {
        bail!("Archive path '{path}' contains ':', which names an NTFS alternate data stream");
    }
    if path.chars().any(|c| c.is_control()) {
        bail!("Archive path '{path}' contains a control character");
    }
    for component in path.split('/') {
        if component.is_empty() {
            bail!("Archive path '{path}' has an empty component");
        }
        if component == "." || component == ".." {
            bail!("Archive path '{path}' contains a '{component}' component");
        }
        if component.ends_with('.') || component.ends_with(' ') {
            bail!(
                "Archive path '{path}': component '{component}' ends in a dot or space, which \
                 Windows silently strips — two different entries would extract to one file"
            );
        }
        let stem = component
            .split_once('.')
            .map(|(head, _)| head)
            .unwrap_or(component)
            .to_ascii_lowercase();
        if DOS_RESERVED.contains(&stem.as_str()) {
            bail!(
                "Archive path '{path}': '{component}' is a reserved Windows device name and \
                 cannot be created on a Windows host"
            );
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Writing
// ---------------------------------------------------------------------------

/// Where an entry's bytes come from.
///
/// Files stay on disk until the write pass rather than being slurped into a
/// `Vec`: a plugin shipping a 200 MB runtime is inside the format's limits and
/// must not need 200 MB of RSS to package.
pub enum Source {
    Path(PathBuf),
    Inline(Vec<u8>),
}

pub struct PackedFile {
    pub source: Source,
    /// Set by the packer for artifacts it knows are executable (the resolved
    /// entry binary), unioned with the on-disk exec bit and with
    /// `[bundle] executables`.
    pub executable: bool,
}

/// Collects the entries of one bundle, then writes them.
///
/// Ordering is a property of the builder, not of the caller: entries live in a
/// `BTreeMap` keyed by archive path, so they come out byte-lexicographically
/// sorted however they went in. `MANIFEST.json` is written first and the
/// legacy signature pair last, both outside that order and both by name.
pub struct BundleBuilder {
    entries: BTreeMap<String, PackedFile>,
    /// Archive paths the author declared executable in `[bundle] executables`.
    ///
    /// This is the cross-pack case: packing a `linux-x64` bundle on Windows,
    /// where no file on disk has an exec bit to derive from. It is an explicit
    /// list rather than a `bin/` prefix rule because a plugin that ships
    /// `runtime/python` or `run.sh` needs the exec bit just as much, and a
    /// prefix rule is the same one-directory limitation the daemon's fallback
    /// already has.
    executables: BTreeSet<String>,
    reproducible: bool,
}

/// The parts of the manifest the packer knows and the builder cannot derive.
pub struct ManifestMeta {
    pub plugin_id: String,
    pub version: String,
    pub target: Target,
    pub protocol: u32,
    pub min_astra_version: String,
    pub capabilities: Vec<String>,
    pub permissions: BTreeMap<String, ManifestPermission>,
    pub entry: ManifestEntry,
}

impl BundleBuilder {
    pub fn new(reproducible: bool, executables: BTreeSet<String>) -> BundleBuilder {
        BundleBuilder {
            entries: BTreeMap::new(),
            executables,
            reproducible,
        }
    }

    /// Add a file from disk. `archive_path` is the path inside the bundle.
    pub fn add_path(&mut self, archive_path: &str, fs_path: &Path) -> Result<()> {
        self.insert(
            archive_path,
            PackedFile {
                source: Source::Path(fs_path.to_path_buf()),
                executable: false,
            },
        )
    }

    /// Add a file from disk, asserting it must be executable wherever it lands
    /// (the resolved entry binary). Independent of the on-disk bit, which does
    /// not exist when cross-packing from Windows.
    pub fn add_executable_path(&mut self, archive_path: &str, fs_path: &Path) -> Result<()> {
        self.insert(
            archive_path,
            PackedFile {
                source: Source::Path(fs_path.to_path_buf()),
                executable: true,
            },
        )
    }

    /// Add bytes the packer generated — the rewritten `plugin.toml`.
    pub fn add_inline(&mut self, archive_path: &str, bytes: Vec<u8>) -> Result<()> {
        self.insert(
            archive_path,
            PackedFile {
                source: Source::Inline(bytes),
                executable: false,
            },
        )
    }

    pub fn contains(&self, archive_path: &str) -> bool {
        self.entries.contains_key(archive_path)
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    fn insert(&mut self, archive_path: &str, file: PackedFile) -> Result<()> {
        check_archive_path(archive_path)?;
        if UNLISTED_ENTRIES.contains(&archive_path) {
            bail!(
                "'{archive_path}' is a reserved bundle entry and cannot come from the plugin \
                 directory — it would shadow the one this build generates. Remove it from your \
                 source tree."
            );
        }
        if self.entries.contains_key(archive_path) {
            bail!(
                "Duplicate archive entry '{archive_path}'. Two sources map to one path; an \
                 extractor would write one over the other and only one would be hashed."
            );
        }
        self.entries.insert(archive_path.to_string(), file);
        Ok(())
    }

    /// The mode an entry gets: 0755 if executable by any of the three routes,
    /// 0644 otherwise.
    ///
    /// Modes are normalised rather than copied verbatim from disk. A checkout
    /// under a different umask, or a file that happens to be 0600, would
    /// otherwise change the bundle's bytes without changing its content — and
    /// a 0600 file inside an installed plugin is a file the daemon can read
    /// and nothing else can. Only the exec bit carries meaning here.
    fn mode_for(&self, archive_path: &str, file: &PackedFile) -> u32 {
        let mut executable = file.executable || self.executables.contains(archive_path);
        #[cfg(unix)]
        if let Source::Path(p) = &file.source {
            use std::os::unix::fs::PermissionsExt;
            if let Ok(meta) = std::fs::metadata(p) {
                executable |= meta.permissions().mode() & 0o111 != 0;
            }
        }
        if executable { 0o755 } else { 0o644 }
    }

    fn options(&self, mode: u32, stored: bool) -> SimpleFileOptions {
        let method = if stored {
            zip::CompressionMethod::Stored
        } else {
            zip::CompressionMethod::Deflated
        };
        let mut options = SimpleFileOptions::default()
            .compression_method(method)
            .unix_permissions(mode);
        // Both are pinned unconditionally, not only under --reproducible: a
        // build that is deterministic by default is one fewer flag between an
        // author and a bundle whose digest a third party can re-derive. The
        // flag exists to *assert* the property, and to switch off signing's
        // dependence on a key that only one machine has.
        options = options.last_modified_time(fixed_mtime());
        if !stored {
            options = options.compression_level(Some(REPRODUCIBLE_COMPRESSION_LEVEL));
        }
        options
    }

    /// Hash every entry and build the manifest. First of the two passes.
    fn build_manifest(&self, meta: &ManifestMeta) -> Result<BundleManifest> {
        let mut files = Vec::with_capacity(self.entries.len());
        let mut total: u64 = 0;
        for (path, file) in &self.entries {
            let (digest, size) = match &file.source {
                Source::Path(p) => sha256_file(p)?,
                Source::Inline(bytes) => (hex(&Sha256::digest(bytes)), bytes.len() as u64),
            };
            total = total.saturating_add(size);
            files.push(FileEntry {
                path: path.clone(),
                sha256: digest,
                size,
                mode: format_mode(self.mode_for(path, file)),
            });
        }

        // The daemon refuses to extract past these, so building past them
        // produces a plugin that installs nowhere. Fail here, where the author
        // can see it, rather than in a user's install log.
        if self.entries.len() + 1 > MAX_ARCHIVE_ENTRIES {
            bail!(
                "This bundle has {} entries; the daemon refuses any archive over {} \
                 (spec/limits.yaml: max_archive_entries)",
                self.entries.len() + 1,
                MAX_ARCHIVE_ENTRIES
            );
        }
        if total > MAX_EXTRACT_BYTES {
            bail!(
                "This bundle unpacks to {total} bytes; the daemon refuses to extract more than \
                 {MAX_EXTRACT_BYTES} (spec/limits.yaml: max_extract_bytes)"
            );
        }

        // `files` comes out of a BTreeMap, so it is already sorted by path.
        Ok(BundleManifest {
            schema: SCHEMA.to_string(),
            plugin_id: meta.plugin_id.clone(),
            version: meta.version.clone(),
            platform: meta.target.platform(),
            protocol: meta.protocol,
            min_astra_version: meta.min_astra_version.clone(),
            capabilities: meta.capabilities.clone(),
            permissions_hash: permissions_hash(&meta.permissions)?,
            permissions: meta.permissions.clone(),
            entry: meta.entry.clone(),
            files,
        })
    }

    /// Write the bundle. Second pass: `MANIFEST.json` stored first, then every
    /// entry in sorted order.
    ///
    /// Under `--reproducible` this packs a second time to a sibling temporary
    /// file and compares the two digests. That is the repack-and-compare canary
    /// the release workflow needs, run where an author can see it: a flag that
    /// only *claims* determinism is worth nothing, and the ways to lose it
    /// (a `time`-feature default, an encoder default level, a file system's
    /// directory order) all look fine right up until two machines disagree.
    pub fn write(&self, out_path: &Path, meta: &ManifestMeta) -> Result<BundleManifest> {
        if !self.entries.contains_key(PLUGIN_TOML_ENTRY) {
            bail!("A bundle must contain {PLUGIN_TOML_ENTRY}");
        }

        let manifest = self.build_manifest(meta)?;
        let manifest_bytes = manifest.to_bytes()?;

        if let Some(parent) = out_path.parent().filter(|p| !p.as_os_str().is_empty()) {
            std::fs::create_dir_all(parent).with_context(|| {
                format!("Failed to create output directory {}", parent.display())
            })?;
        }
        self.pack(out_path, &manifest_bytes)?;

        if self.reproducible {
            let canary = out_path.with_file_name(format!(
                "{}.repack",
                out_path.file_name().unwrap_or_default().to_string_lossy()
            ));
            let result = (|| -> Result<()> {
                self.pack(&canary, &manifest_bytes)?;
                let (a, _) = sha256_file(out_path)?;
                let (b, _) = sha256_file(&canary)?;
                if a != b {
                    bail!(
                        "--reproducible: packing the same inputs twice produced two different \
                         archives.\n  first:  {a}\n  second: {b}\nSomething in this build depends \
                         on the machine rather than on its inputs."
                    );
                }
                Ok(())
            })();
            let _ = std::fs::remove_file(&canary);
            result?;
        }

        Ok(manifest)
    }

    fn pack(&self, out_path: &Path, manifest_bytes: &[u8]) -> Result<()> {
        let file = File::create(out_path)
            .with_context(|| format!("Failed to create {}", out_path.display()))?;
        let mut zip = zip::ZipWriter::new(file);

        // Invariant 1: first entry, STORED. A reader lifts it straight out of
        // the local file header at offset 0.
        zip.start_file(MANIFEST_ENTRY, self.options(0o644, true))?;
        zip.write_all(manifest_bytes)?;

        for (path, packed) in &self.entries {
            let mode = self.mode_for(path, packed);
            zip.start_file(path.as_str(), self.options(mode, false))?;
            match &packed.source {
                Source::Inline(bytes) => zip.write_all(bytes)?,
                Source::Path(p) => {
                    let mut reader = BufReader::new(
                        File::open(p).with_context(|| format!("Failed to open {}", p.display()))?,
                    );
                    std::io::copy(&mut reader, &mut zip)
                        .with_context(|| format!("Failed to pack {}", p.display()))?;
                }
            }
        }

        zip.finish()?;
        Ok(())
    }

    /// Options the legacy signature pair is appended with. Same fixed mtime and
    /// mode as everything else, so signing does not make a bundle
    /// irreproducible on its own — Ed25519 over a fixed message with a fixed
    /// key is deterministic.
    pub fn legacy_signature_options() -> SimpleFileOptions {
        SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .compression_level(Some(REPRODUCIBLE_COMPRESSION_LEVEL))
            .unix_permissions(0o644)
            .last_modified_time(fixed_mtime())
    }
}

// ---------------------------------------------------------------------------
// The retiring in-ZIP pair
// ---------------------------------------------------------------------------

/// The legacy digest: `SHA256(name₀ ‖ content₀ ‖ name₁ ‖ content₁ ‖ …)` over
/// every entry in ZIP index order, skipping the pair itself.
///
/// **This construction is broken and is reproduced here only to keep verifying
/// bundles that already exist.** There are no delimiters, no length prefixes,
/// no entry count and no domain separator, so entry `"ab"` with content `"c"`
/// hashes identically to entry `"a"` with content `"bc"` — an attacker who
/// controls two adjacent names can move bytes across the boundary and keep the
/// signature valid. Invariant 2 (`sha256` of the whole file) is what replaced
/// it, and it is a different number in a different place for that reason.
///
/// Do not reach for this to authenticate anything new. It exists so that
/// [`append_legacy_signature`] and the daemon compute the same bytes until
/// [`LEGACY_PAIR_SUNSET`].
pub fn legacy_digest<R: Read + Seek>(archive: &mut zip::ZipArchive<R>) -> Result<[u8; 32]> {
    let mut hasher = Sha256::new();
    for i in 0..archive.len() {
        let mut entry = archive
            .by_index(i)
            .with_context(|| format!("Failed to read archive entry {i}"))?;
        let name = entry.name().to_string();
        // The daemon skips the pair when it verifies, so the writer must skip it
        // when it signs — otherwise re-signing an already-signed bundle would
        // produce a signature over a message nothing ever checks.
        if name == LEGACY_SIGNATURE_ENTRY || name == LEGACY_PUBKEY_ENTRY {
            continue;
        }
        hasher.update(name.as_bytes());
        let mut buf = Vec::new();
        entry
            .read_to_end(&mut buf)
            .with_context(|| format!("Failed to read archive entry '{name}'"))?;
        hasher.update(&buf);
    }
    Ok(hasher.finalize().into())
}

/// Append `SIGNATURE` + `PUBKEY` to a finished bundle, in that order, as the
/// last two entries.
///
/// This is the whole of what `astra-plugin sign` does, and — since 3.10 — the
/// only place in this CLI that writes the pair. `astra-plugin build` no longer
/// calls it: a build that signed whenever a key happened to be on the machine
/// made the archive's contents depend on the machine, and printed a sentence
/// about trust that the key could not deliver.
///
/// Refuses a bundle that already carries the pair. Re-signing would mean
/// rewriting entries that the existing signature covers, and appending a second
/// pair would leave two `SIGNATURE` entries where the reader takes the first —
/// both are ways of ending up with an archive whose signature answers a
/// question about a different set of bytes.
pub fn append_legacy_signature(
    path: &Path,
    signing_key: &ed25519_dalek::SigningKey,
) -> Result<LegacySignature> {
    use base64::{Engine, engine::general_purpose::STANDARD};
    use ed25519_dalek::Signer;

    let bytes = std::fs::read(path)
        .with_context(|| format!("Failed to read {} for signing", path.display()))?;
    let mut archive = zip::ZipArchive::new(std::io::Cursor::new(&bytes))
        .with_context(|| format!("{} is not a readable ZIP archive", path.display()))?;

    for name in [LEGACY_SIGNATURE_ENTRY, LEGACY_PUBKEY_ENTRY] {
        if archive.by_name(name).is_ok() {
            bail!(
                "{} already carries a {name} entry. Rebuild it with `astra-plugin build` and sign \
                 the fresh bundle; a bundle is signed once or not at all.",
                path.display()
            );
        }
    }

    let digest = legacy_digest(&mut archive)?;
    drop(archive);

    let signature = signing_key.sign(&digest);
    let public_key = signing_key.verifying_key();
    let public_b64 = STANDARD.encode(public_key.to_bytes());

    let file = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open(path)
        .with_context(|| format!("Failed to open {} for appending", path.display()))?;
    let mut writer = zip::ZipWriter::new_append(file)
        .with_context(|| format!("Failed to append to {}", path.display()))?;
    let options = BundleBuilder::legacy_signature_options();

    writer.start_file(LEGACY_SIGNATURE_ENTRY, options)?;
    writer.write_all(STANDARD.encode(signature.to_bytes()).as_bytes())?;
    writer.start_file(LEGACY_PUBKEY_ENTRY, options)?;
    writer.write_all(public_b64.as_bytes())?;
    writer.finish()?;

    Ok(LegacySignature {
        public_key_b64: public_b64,
    })
}

/// What [`append_legacy_signature`] wrote, for the caller to print.
pub struct LegacySignature {
    /// Base64 of the raw 32-byte Ed25519 public key, exactly as it now sits in
    /// the archive's `PUBKEY` entry.
    pub public_key_b64: String,
}

// ---------------------------------------------------------------------------
// Reading
// ---------------------------------------------------------------------------

/// One entry as the archive actually stores it.
#[derive(Debug, Clone)]
pub struct ArchiveEntry {
    pub path: String,
    pub sha256: String,
    pub size: u64,
    pub mode: Option<u32>,
    pub stored: bool,
}

/// A bundle opened and fully checked.
pub struct Bundle {
    pub manifest: BundleManifest,
    pub manifest_digest: String,
    pub artifact_sha256: String,
    pub artifact_size: u64,
    pub entries: Vec<ArchiveEntry>,
    pub signed: bool,
}

/// Lift `MANIFEST.json` out of a bundle **without inflating anything and
/// without reading the central directory**.
///
/// This is the reason the manifest is entry zero and STORED. Everything a
/// reader needs to know about what the archive is allowed to contain is
/// available from the first few hundred bytes, before any decompressor has
/// touched attacker-controlled input, and before the reader has trusted a
/// central directory that a crafted archive can make disagree with the local
/// headers.
///
/// `bytes` need only be a prefix of the file long enough to cover the header
/// and the manifest.
pub fn manifest_from_local_header(bytes: &[u8]) -> Result<Vec<u8>> {
    let u16_at = |off: usize| -> Result<u16> {
        bytes
            .get(off..off + 2)
            .map(|s| u16::from_le_bytes([s[0], s[1]]))
            .context("Truncated local file header")
    };
    let u32_at = |off: usize| -> Result<u32> {
        bytes
            .get(off..off + 4)
            .map(|s| u32::from_le_bytes([s[0], s[1], s[2], s[3]]))
            .context("Truncated local file header")
    };

    if u32_at(0)? != 0x0403_4b50 {
        bail!("Not a ZIP archive: no local file header at offset 0");
    }

    // The name comes first, before every other complaint. An archive whose
    // entry zero is some other file will trip whichever check that file's
    // headers happen to fail, and naming *that* sends the reader looking for a
    // problem with a manifest they do not have.
    let name_len = u16_at(26)? as usize;
    let extra_len = u16_at(28)? as usize;
    let name = bytes
        .get(30..30 + name_len)
        .context("Truncated local file header name")?;
    if name != MANIFEST_ENTRY.as_bytes() {
        bail!(
            "The first archive entry is '{}', not {MANIFEST_ENTRY}. A v2 bundle puts the \
             manifest first so it can be read without parsing the rest.",
            String::from_utf8_lossy(name)
        );
    }

    let flags = u16_at(6)?;
    if flags & 0x0008 != 0 {
        bail!(
            "{MANIFEST_ENTRY} uses a data descriptor, so its size is not in the local header. A \
             v2 bundle's manifest must be readable from offset 0 alone."
        );
    }
    if flags & 0x0001 != 0 {
        bail!("{MANIFEST_ENTRY} is encrypted");
    }
    if u16_at(8)? != 0 {
        bail!(
            "{MANIFEST_ENTRY} is compressed. A v2 bundle stores it uncompressed so a reader can \
             find it without inflating attacker-controlled bytes."
        );
    }
    let size = u32_at(18)? as u64;
    if size == u32::MAX as u64 {
        bail!("{MANIFEST_ENTRY} declares a ZIP64 size; a manifest that large is not a manifest");
    }
    if size > MAX_MANIFEST_BYTES {
        bail!("{MANIFEST_ENTRY} is {size} bytes, over the {MAX_MANIFEST_BYTES}-byte ceiling");
    }
    let start = 30 + name_len + extra_len;
    let end = start + size as usize;
    Ok(bytes
        .get(start..end)
        .context("Truncated MANIFEST.json")?
        .to_vec())
}

impl Bundle {
    /// Open a `.astraplugin` and check every invariant in this module's docs.
    ///
    /// The checks are the same ones the daemon must make. They live here so
    /// `astra-plugin verify` and CI can make them too, on the author's machine,
    /// against the exact bytes that will be published.
    pub fn open(path: &Path) -> Result<Bundle> {
        let (artifact_sha256, artifact_size) = sha256_file(path)?;

        let mut file =
            File::open(path).with_context(|| format!("Failed to open {}", path.display()))?;

        // Invariant 1, checked the way a reader that trusts nothing would:
        // straight off the front of the file. `read_to_end` on a `take`, not a
        // single `read` — a short read on a large file would truncate the
        // manifest and report it as corrupt.
        let head_len = MAX_MANIFEST_BYTES.min(artifact_size) + 4096;
        let mut head = Vec::with_capacity(head_len as usize);
        Read::by_ref(&mut file)
            .take(head_len)
            .read_to_end(&mut head)?;
        let manifest_bytes = manifest_from_local_header(&head)?;
        let manifest_digest = manifest_digest(&manifest_bytes);
        let manifest: BundleManifest = serde_json::from_slice(&manifest_bytes)
            .context("MANIFEST.json is not a valid v2 bundle manifest")?;

        if manifest.schema != SCHEMA {
            bail!(
                "MANIFEST.schema is '{}', not '{SCHEMA}'. This reader does not know that format.",
                manifest.schema
            );
        }

        // Now the central directory, and a cross-check that it agrees with the
        // local header about entry zero.
        file.rewind()?;
        let mut archive = zip::ZipArchive::new(BufReader::new(file))
            .with_context(|| format!("Failed to read {} as a ZIP archive", path.display()))?;

        if archive.len() > MAX_ARCHIVE_ENTRIES {
            bail!(
                "Archive has {} entries; the daemon refuses more than {MAX_ARCHIVE_ENTRIES}",
                archive.len()
            );
        }

        let mut entries = Vec::with_capacity(archive.len());
        let mut seen: BTreeSet<String> = BTreeSet::new();
        let mut total: u64 = 0;
        for i in 0..archive.len() {
            let mut entry = archive.by_index(i)?;
            let path = entry.name().to_string();
            if i == 0 && path != MANIFEST_ENTRY {
                bail!("The central directory's first entry is '{path}', not {MANIFEST_ENTRY}");
            }
            if entry.is_dir() {
                bail!(
                    "Archive contains a directory entry '{path}'. A v2 bundle stores files only; \
                     directories are implied by the paths and cannot carry a digest."
                );
            }
            #[cfg(unix)]
            if let Some(mode) = entry.unix_mode() {
                const S_IFMT: u32 = 0o170000;
                const S_IFLNK: u32 = 0o120000;
                if mode & S_IFMT == S_IFLNK {
                    bail!("Archive entry '{path}' is a symlink; a v2 bundle contains no symlinks");
                }
            }
            if !seen.insert(path.clone()) {
                bail!(
                    "Duplicate archive entry '{path}'. Extraction would write one over the other \
                     and only one of them would have been hashed."
                );
            }
            check_archive_path(&path)?;

            let stored = entry.compression() == zip::CompressionMethod::Stored;
            let mut hasher = Sha256::new();
            let mut buf = vec![0u8; 64 * 1024];
            let mut size = 0u64;
            loop {
                let n = entry.read(&mut buf)?;
                if n == 0 {
                    break;
                }
                hasher.update(&buf[..n]);
                size += n as u64;
                total += n as u64;
                if total > MAX_EXTRACT_BYTES {
                    bail!(
                        "Archive unpacks to more than {MAX_EXTRACT_BYTES} bytes \
                         (spec/limits.yaml: max_extract_bytes)"
                    );
                }
            }
            entries.push(ArchiveEntry {
                path,
                sha256: hex(&hasher.finalize()),
                size,
                mode: entry.unix_mode().map(|m| m & 0o7777),
                stored,
            });
        }

        let first = entries.first().context("Archive is empty")?;
        if !first.stored {
            bail!("{MANIFEST_ENTRY} is compressed; a v2 bundle stores it");
        }
        if first.sha256 != hex(&Sha256::digest(&manifest_bytes)) {
            bail!(
                "The {MANIFEST_ENTRY} in the central directory differs from the one in the local \
                 header at offset 0"
            );
        }

        let signed = seen.contains(LEGACY_SIGNATURE_ENTRY);
        let bundle = Bundle {
            manifest,
            manifest_digest,
            artifact_sha256,
            artifact_size,
            entries,
            signed,
        };
        bundle.check_exhaustive()?;
        bundle.check_digests()?;
        bundle.check_entry_command()?;
        bundle.check_legacy_pair_position()?;
        Ok(bundle)
    }

    /// Invariant 4, both directions.
    fn check_exhaustive(&self) -> Result<()> {
        let listed: BTreeSet<&str> = self
            .manifest
            .files
            .iter()
            .map(|f| f.path.as_str())
            .collect();
        if listed.len() != self.manifest.files.len() {
            bail!("MANIFEST.files lists the same path twice");
        }
        let present: BTreeSet<&str> = self
            .entries
            .iter()
            .map(|e| e.path.as_str())
            .filter(|p| !UNLISTED_ENTRIES.contains(p))
            .collect();

        let unlisted: Vec<&str> = present.difference(&listed).copied().collect();
        if !unlisted.is_empty() {
            bail!(
                "MANIFEST.files is not exhaustive: the archive contains {} file(s) it does not \
                 list — {}. An extractor would write these and nothing would have hashed them.",
                unlisted.len(),
                unlisted.join(", ")
            );
        }
        let missing: Vec<&str> = listed.difference(&present).copied().collect();
        if !missing.is_empty() {
            bail!(
                "MANIFEST.files lists {} file(s) the archive does not contain — {}. The bundle \
                 is incomplete or an entry was removed after it was manifested.",
                missing.len(),
                missing.join(", ")
            );
        }

        // Sorted, byte-lexicographically. A reader is allowed to binary-search
        // this list; an unsorted one would make that quietly wrong.
        let mut sorted = self.manifest.files.clone();
        sorted.sort_by(|a, b| a.path.as_bytes().cmp(b.path.as_bytes()));
        if sorted
            .iter()
            .zip(&self.manifest.files)
            .any(|(a, b)| a.path != b.path)
        {
            bail!("MANIFEST.files is not sorted byte-lexicographically by path");
        }
        Ok(())
    }

    fn check_digests(&self) -> Result<()> {
        for entry in &self.entries {
            if UNLISTED_ENTRIES.contains(&entry.path.as_str()) {
                continue;
            }
            let listed = self
                .manifest
                .file(&entry.path)
                .with_context(|| format!("'{}' is not in MANIFEST.files", entry.path))?;
            if listed.sha256 != entry.sha256 {
                bail!(
                    "Digest mismatch for '{}':\n  MANIFEST says {}\n  archive has  {}",
                    entry.path,
                    listed.sha256,
                    entry.sha256
                );
            }
            if listed.size != entry.size {
                bail!(
                    "Size mismatch for '{}': MANIFEST says {}, archive has {}",
                    entry.path,
                    listed.size,
                    entry.size
                );
            }
            let listed_mode = parse_mode(&listed.mode)?;
            if let Some(mode) = entry.mode
                && mode & 0o777 != listed_mode & 0o777
            {
                bail!(
                    "Mode mismatch for '{}': MANIFEST says {}, archive has {}",
                    entry.path,
                    listed.mode,
                    format_mode(mode)
                );
            }
        }
        Ok(())
    }

    /// `entry.command` must resolve to a file the manifest lists, or to a
    /// runtime the host provides. A command that points at neither is a bundle
    /// that installs and then fails to start.
    fn check_entry_command(&self) -> Result<()> {
        let command = self.manifest.entry.command.trim();
        if command.is_empty() {
            bail!("MANIFEST.entry.command is empty");
        }
        let is_runtime = matches!(command, "python" | "python3" | "node" | "bun" | "deno");
        if is_runtime {
            return Ok(());
        }
        if Path::new(command).is_absolute() || command.contains("..") {
            bail!(
                "MANIFEST.entry.command '{command}' is absolute or contains '..'; it must name a \
                 file inside the bundle"
            );
        }
        let relative = command.trim_start_matches("./").replace('\\', "/");
        if self.manifest.file(&relative).is_none() {
            bail!(
                "MANIFEST.entry.command is '{command}', which is not one of the {} files in this \
                 bundle. The plugin would install and then fail to start.",
                self.manifest.files.len()
            );
        }
        Ok(())
    }

    /// The legacy pair, while it exists, is last and in a fixed order — it is
    /// computed over everything before it, so anything after it would be
    /// outside what it covers.
    fn check_legacy_pair_position(&self) -> Result<()> {
        let names: Vec<&str> = self.entries.iter().map(|e| e.path.as_str()).collect();
        let sig = names.iter().position(|n| *n == LEGACY_SIGNATURE_ENTRY);
        let key = names.iter().position(|n| *n == LEGACY_PUBKEY_ENTRY);
        match (sig, key) {
            (None, None) => Ok(()),
            (Some(s), Some(k)) => {
                if s != names.len() - 2 || k != names.len() - 1 {
                    bail!(
                        "{LEGACY_SIGNATURE_ENTRY} and {LEGACY_PUBKEY_ENTRY} must be the last two \
                         archive entries, in that order; anything after them is outside what the \
                         signature covers"
                    );
                }
                Ok(())
            }
            _ => bail!(
                "The bundle has one of {LEGACY_SIGNATURE_ENTRY}/{LEGACY_PUBKEY_ENTRY} but not the \
                 other"
            ),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifest_digest_is_domain_separated() {
        let bytes = b"{}";
        assert_ne!(
            manifest_digest(bytes),
            hex(&Sha256::digest(bytes)),
            "a manifest digest that equals the plain file digest can be swapped for one"
        );
        // And it is the construction the plan names, computed independently.
        let mut h = Sha256::new();
        h.update(b"astra.bundle/2\x00");
        h.update(bytes);
        assert_eq!(manifest_digest(bytes), hex(&h.finalize()));
    }

    #[test]
    fn target_keys_are_the_registry_platform_keys() {
        assert_eq!(Target::LinuxX64.key(), "linux-x64");
        assert_eq!(Target::WindowsX64.key(), "windows-x64");
        assert_eq!(Target::Noarch.key(), "noarch");
        for t in Target::ALL {
            assert_eq!(Target::parse(t.key()).unwrap(), *t);
            assert_eq!(Target::from_platform(&t.platform()).unwrap(), *t);
        }
    }

    #[test]
    fn noarch_stamps_no_platform_requirement() {
        let (os, arch) = Target::Noarch.toml_platform();
        assert!(os.is_empty() && arch.is_empty());
        assert_eq!(Target::Noarch.platform().os, "any");
    }

    #[test]
    fn archive_paths_that_extractors_must_refuse_are_refused_at_build_time() {
        for bad in [
            "/etc/passwd",
            "../escape",
            "a/../b",
            "bin\\x",
            "stream:ads",
            "trailing./x",
            "con",
            "CON.txt",
            "a//b",
            "",
        ] {
            assert!(
                check_archive_path(bad).is_err(),
                "'{bad}' should be refused"
            );
        }
        for good in [
            "plugin.toml",
            "bin/dice_roller",
            "runtime/python",
            "ui/a.js",
        ] {
            check_archive_path(good).unwrap_or_else(|e| panic!("'{good}' should pass: {e}"));
        }
    }

    #[test]
    fn mode_round_trips() {
        assert_eq!(format_mode(0o755), "0755");
        assert_eq!(format_mode(0o644), "0644");
        assert_eq!(parse_mode("0755").unwrap(), 0o755);
        assert_eq!(parse_mode("0644").unwrap(), 0o644);
    }

    #[test]
    fn permissions_hash_is_stable_and_order_independent() {
        let mut a = BTreeMap::new();
        a.insert(
            "fire_trigger".to_string(),
            ManifestPermission::with_reason("to roll"),
        );
        a.insert("net".to_string(), ManifestPermission::default());
        let mut b = BTreeMap::new();
        b.insert("net".to_string(), ManifestPermission::default());
        b.insert(
            "fire_trigger".to_string(),
            ManifestPermission::with_reason("to roll"),
        );
        assert_eq!(permissions_hash(&a).unwrap(), permissions_hash(&b).unwrap());
        assert!(permissions_hash(&a).unwrap().starts_with("sha256:"));
        // A request with nothing in it is `{}`, not `{"reason":""}`. That is the
        // daemon's spelling — `PermissionRequest` skips an empty `reason` — and
        // the packer is now the same type rather than a lookalike that always
        // emitted the member. Both sides recompute this hash from
        // `MANIFEST.permissions` and so always agreed with themselves, which is
        // why nothing ever went red; two canonical spellings of one declaration
        // is still exactly the drift `permissions_hash` exists to prevent.
        assert_eq!(
            String::from_utf8(canonical_permissions(&a).unwrap()).unwrap(),
            r#"{"fire_trigger":{"reason":"to roll"},"net":{}}"#
        );
    }

    /// `subscribe_events.types` is an allowlist the daemon enforces per event,
    /// and an empty one allows **nothing** (§5.6, task 4.1). A packer that drops
    /// it publishes a plugin whose every subscription the daemon then refuses —
    /// visible only on the registry path, because sideload and import read
    /// `plugin.toml` directly and never come through here.
    #[test]
    fn a_permission_reaches_the_manifest_with_its_types_and_scopes() {
        let mut perms = BTreeMap::new();
        perms.insert(
            "subscribe_events".to_string(),
            ManifestPermission {
                reason: "Watches for command_completed".into(),
                types: vec!["command_completed".into(), "tool_started".into()],
                scopes: vec![],
            },
        );
        perms.insert(
            "set_variable".to_string(),
            ManifestPermission {
                reason: String::new(),
                types: vec![],
                scopes: vec!["plugin".into()],
            },
        );

        let canonical = String::from_utf8(canonical_permissions(&perms).unwrap()).unwrap();
        assert_eq!(
            canonical,
            r#"{"set_variable":{"scopes":["plugin"]},"subscribe_events":{"reason":"Watches for command_completed","types":["command_completed","tool_started"]}}"#
        );

        // And the same bytes deserialise back into the daemon's own type, so
        // what the packer wrote is what §5.6's grant resolution will read.
        let back: astra_plugin_manifest::Permissions = serde_json::from_str(&canonical).unwrap();
        assert_eq!(
            back.0["subscribe_events"].types,
            vec!["command_completed".to_string(), "tool_started".to_string()]
        );
        assert_eq!(back.0["set_variable"].scopes, vec!["plugin".to_string()]);
    }

    #[test]
    fn empty_permissions_hash_is_the_hash_of_an_empty_object() {
        let empty = BTreeMap::new();
        assert_eq!(canonical_permissions(&empty).unwrap(), b"{}");
        assert_eq!(
            permissions_hash(&empty).unwrap(),
            format!("sha256:{}", hex(&Sha256::digest(b"{}")))
        );
    }

    #[test]
    fn local_header_reader_rejects_a_compressed_first_entry() {
        // A minimal local file header claiming deflate.
        let mut head = vec![0u8; 30];
        head[0..4].copy_from_slice(&0x0403_4b50u32.to_le_bytes());
        head[8..10].copy_from_slice(&8u16.to_le_bytes()); // deflate
        head[26..28].copy_from_slice(&(MANIFEST_ENTRY.len() as u16).to_le_bytes());
        head.extend_from_slice(MANIFEST_ENTRY.as_bytes());
        let err = manifest_from_local_header(&head).unwrap_err().to_string();
        assert!(err.contains("compressed"), "{err}");
    }

    #[test]
    fn local_header_reader_rejects_a_wrong_first_entry() {
        let name = "plugin.toml";
        let mut head = vec![0u8; 30];
        head[0..4].copy_from_slice(&0x0403_4b50u32.to_le_bytes());
        head[26..28].copy_from_slice(&(name.len() as u16).to_le_bytes());
        head.extend_from_slice(name.as_bytes());
        let err = manifest_from_local_header(&head).unwrap_err().to_string();
        assert!(
            err.contains("The first archive entry is 'plugin.toml'"),
            "a wrong first entry must be named as such, not diagnosed as a \
             malformed manifest: {err}"
        );
    }
}
