//! `astra-plugin locale` — the `locales/` directory, and the rules `check` and
//! `build` run over it.
//!
//! # The two planes, because every rule below sorts into one of them
//!
//! **Declared plane** — anything the *daemon* renders: config-field titles and
//! descriptions, action and trigger labels, field labels, placeholders,
//! dropdown option labels, `[ui]` contribution labels. The plugin emits `$key`
//! and the daemon resolves it per request out of the snapshot it loaded at
//! install. The plugin never re-renders and correctness never depends on an
//! author implementing an optional hook.
//!
//! **Runtime plane** — anything the *plugin process* produces: chat text,
//! notifications, anything with a count in it. The plugin resolves it with
//! `I18n` at the moment it produces the string.
//!
//! **The catalogue** is neither: when a store card is drawn there is no bundle
//! on disk and no process. It is two reserved keys, `listing.name` and
//! `listing.description`, that the registry's ingest bot reads out of the
//! attested bundle it already holds.
//!
//! # What refuses, and what only says something
//!
//! There are **no new warnings here, deliberately**. A warning is strict-fatal
//! on `astra-plugin dev`'s inner loop (`dev.rs` calls `validate::run(&dir,
//! true)`) *and* on the release path (`plugin-release.yml` runs `check
//! --strict`). So a rule is either an ERROR that a fresh scaffold satisfies by
//! construction, or a NOTE. Nothing in between, because the in-between severity
//! is the one that stops an author's inner loop over prose.
//!
//! # Shape is a diagnostic here, never a refusal
//!
//! The daemon's resolver (`plugins/i18n.rs` on Astra `main`) looks up **every**
//! `$`-prefixed string; only the strip-the-marker-on-a-miss fallback is gated
//! behind a dotted-identifier shape. So a plugin that genuinely declares a
//! catalogue key named `USD` keeps its translation, and a rule here of the form
//! *"a `$key` must look like `a.b.c`"* would refuse at pack time something the
//! daemon resolves at run time — the worst direction for a gate to be wrong in.
//!
//! Shape therefore only ever **narrows** a refusal in this file. A `$string`
//! that is not key-shaped is never an error; a `$string` that *is* key-shaped
//! and matches nothing is, because the daemon will put the bare key on a user's
//! screen. `$$` is the daemon's escape for a literal leading dollar and is
//! treated as a literal everywhere below.
//!
//! # The registry's caps, and which of them refuse here
//!
//! Every cap this module enforces is read at run time from the vendored
//! `listing-limits.yaml`, and **that file's rows are the answer** to which of
//! them `astra-plugin check` refuses over: each row names the registry constant
//! it mirrors, its unit, and whether anything local executes on it. Read the
//! rows.
//!
//! Not a paragraph, because the paragraph this replaces was one. It said the
//! three locale caps "exist in no repository yet" and called their absence a
//! decision; they landed upstream two and a half hours later, and the sentence
//! went on explaining why the rules could not be written for a day after they
//! could. A restatement of another file's state is a hostage — the rows and the
//! `cap()` accessor are the thing itself.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use astra_plugin_manifest::PluginManifest;
use astra_plugin_sdk::plural;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};

use crate::hprintln;
use crate::locales::LOCALE_CODES;
use crate::output::{Rejected, Verdict};

/// The staleness lock, at the plugin ROOT and not inside `locales/`.
///
/// `PluginManifest::load_locales` reads every top-level `*.json` in `locales/`
/// as a locale keyed on its stem, so a `locales/locales.lock.json` would become
/// a phantom locale named `locales.lock` — packed, digested, signed, and
/// selectable by nothing.
pub const LOCK_FILE: &str = "locales.lock.json";

/// The lock's own schema string. Bumped only when its shape changes.
pub const LOCK_SCHEMA: &str = "astra.plugin.locales/1";

/// The pseudo-locale `locale pseudo` writes.
///
/// A **named exception inside this CLI** and deliberately *not* a row in
/// `spec/locales.yaml`: that file exists to be compared against the daemon's
/// ten codes, and an eleventh row means the comparison needs a special case.
/// `check` permits it with a NOTE; `build` refuses it.
pub const PSEUDO_CODE: &str = "qps";

/// The two keys the ingest bot reads out of a bundle's `en.json`. Closed.
pub const RESERVED_LISTING_KEYS: &[&str] = &["listing.name", "listing.description"];

/// The CLDR cardinal category names, which are a reserved key SUFFIX namespace.
///
/// Plurals are key suffixes rather than nested objects because `load_locales`
/// deserialises `HashMap<String,String>` and drops the whole file on a nested
/// object — so the flat spelling is the only one the daemon can read.
const PLURAL_CATEGORIES: &[&str] = &["zero", "one", "two", "few", "many", "other"];

/// JSON Schema members whose string value is a LABEL — something a human reads
/// off the settings form — as opposed to a VALUE the daemon would rewrite.
///
/// The daemon's `resolve_json` walks every string with no key filter at all, so
/// this list is not a description of what it resolves. It is a description of
/// what the author *meant*, and it is the only thing that separates a mistyped
/// key (an error) from a `"default": "$HOME/notes"` (a note).
const LABEL_KEYS: &[&str] = &[
    "title",
    "description",
    "placeholder",
    "enumNames",
    "label",
    "help",
    "hint",
];

// ── the caps mirrored from astra-registry ────────────────────────────────────

/// `spec/listing-limits.yaml`, parsed at run time from this crate's own tree.
///
/// Read from the spec file rather than hardcoded for the same reason
/// `ICON_FILENAMES` has a test that reads `spec/icon-formats.yaml`: these four
/// numbers belong to another repository, and a copy nobody compares is a guess.
/// See that file's header, and `tools/check-locales.py --rules C20`.
fn listing_limits() -> &'static BTreeMap<String, usize> {
    use std::sync::OnceLock;
    static LIMITS: OnceLock<BTreeMap<String, usize>> = OnceLock::new();
    LIMITS.get_or_init(|| {
        let mut out = BTreeMap::new();
        for line in LISTING_LIMITS_SPEC.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let Some((name, rest)) = line.split_once(':') else {
                continue;
            };
            let value = rest.split_whitespace().next().unwrap_or("");
            if let Ok(n) = value.replace('_', "").parse::<usize>() {
                out.insert(name.trim().to_string(), n);
            }
        }
        out
    })
}

/// `spec/listing-limits.yaml`, embedded.
///
/// `include_str!` reaches outside this crate's package directory, which
/// `cargo package` refuses — so this is the same trick `conformance.json` uses:
/// a vendored copy inside `src/`, with a test that reads the spec file at test
/// time and fails until the two agree.
const LISTING_LIMITS_SPEC: &str = include_str!("../listing-limits.yaml");

/// One cap by name, or a panic naming the spec file.
///
/// A panic and not a default: a missing row means the vendored copy and the
/// spec disagree, and silently substituting a number is how a cap stops being
/// a cap. The test below fires long before any user could reach this.
///
/// `pub(crate)` since 2026-08-23 because `commands::build` reads
/// `max_artifact_bytes` through it. That cap is not a locale cap and this is
/// not a locale accessor — it is the reader for `listing-limits.yaml`, which
/// happens to live here because the locale caps were the first rows in that
/// file. A second reader with its own copy of the parse is how the three
/// existing readers of that file came to disagree about what a row IS.
pub(crate) fn cap(name: &str) -> usize {
    *listing_limits().get(name).unwrap_or_else(|| {
        panic!(
            "astra-plugin-cli/src/listing-limits.yaml has no `{name}` row. It is a vendored \
             copy of spec/listing-limits.yaml; `the_listing_limits_are_the_ones_the_spec_declares` \
             is the test that keeps them equal."
        )
    })
}

// ── the model ────────────────────────────────────────────────────────────────

/// One `locales/<stem>.json`, loaded or not.
pub struct LocaleFile {
    /// The filename stem, which is the language code the daemon will key on.
    pub code: String,
    pub path: PathBuf,
    /// The file's size in bytes, read from the filesystem and NOT derived from
    /// the parse.
    ///
    /// E18's byte half has to fire on a file that does not parse, because the
    /// registry's cap runs *before* `JSON.parse` — it is the one refusal that
    /// exists to avoid reading the file at all. A size taken from `keys` would
    /// be 0 for exactly the files that matter.
    pub bytes: u64,
    /// Empty when [`error`](Self::error) is set — the daemon drops the whole
    /// file on any problem, and so does this.
    pub keys: BTreeMap<String, String>,
    pub error: Option<String>,
}

/// Everything under `locales/`, plus the root lock.
pub struct LocaleSet {
    pub dir: PathBuf,
    /// `locales/` exists as a directory.
    pub present: bool,
    /// Top-level `*.json`, sorted by code. The only files the daemon reads.
    pub files: Vec<LocaleFile>,
    /// `*.json` BELOW the top level, relative to the plugin root. E5.
    pub nested: Vec<String>,
    /// Non-`.json` files directly under `locales/`. N8.
    pub non_json: Vec<String>,
    pub lock: Option<Lock>,
    pub lock_error: Option<String>,
}

/// `locales.lock.json`, as read.
#[derive(Clone, Default)]
pub struct Lock {
    pub schema: String,
    pub source: String,
    /// code -> key -> the first 12 hex of sha256 of the ENGLISH bytes the
    /// translation was made against.
    pub locales: BTreeMap<String, BTreeMap<String, String>>,
}

/// What a rule concluded.
pub struct Findings {
    pub errors: Vec<String>,
    pub notes: Vec<String>,
}

impl Findings {
    fn new() -> Self {
        Findings { errors: Vec::new(), notes: Vec::new() }
    }
    fn err(&mut self, id: &str, msg: impl Into<String>) {
        self.errors.push(format!("[{id}] {}", msg.into()));
    }
    fn note(&mut self, id: &str, msg: impl Into<String>) {
        self.notes.push(format!("[{id}] {}", msg.into()));
    }
}

/// Which caller is asking. `build` promotes three notes and refuses `qps`.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Gate {
    /// `astra-plugin check` — and `astra-plugin locale check`.
    Check,
    /// `astra-plugin build` — the artifact is about to be sealed.
    Build,
}

// ── loading ──────────────────────────────────────────────────────────────────

impl LocaleSet {
    /// Read `<dir>/locales/` and `<dir>/locales.lock.json`.
    ///
    /// Never fails. A directory that is not there is not an error here — N1 is
    /// the rule that decides what an absent `locales/` means, and it needs the
    /// rest of the tree to decide it.
    pub fn read(plugin_dir: &Path) -> Self {
        let dir = plugin_dir.join("locales");
        let mut set = LocaleSet {
            present: dir.is_dir(),
            dir,
            files: Vec::new(),
            nested: Vec::new(),
            non_json: Vec::new(),
            lock: None,
            lock_error: None,
        };

        if set.present {
            let mut entries: Vec<PathBuf> = fs::read_dir(&set.dir)
                .map(|it| it.flatten().map(|e| e.path()).collect())
                .unwrap_or_default();
            entries.sort();

            for path in entries {
                if path.is_dir() {
                    // Every `*.json` under here is E5's business. The daemon
                    // reads only the top level; the packer ships the lot.
                    for e in walkdir::WalkDir::new(&path).sort_by_file_name() {
                        let Ok(e) = e else { continue };
                        if e.file_type().is_file()
                            && e.path().extension().is_some_and(|x| x == "json")
                        {
                            let rel = e
                                .path()
                                .strip_prefix(plugin_dir)
                                .unwrap_or(e.path())
                                .to_string_lossy()
                                .replace('\\', "/");
                            set.nested.push(rel);
                        }
                    }
                    continue;
                }
                let name = path.file_name().map(|n| n.to_string_lossy().into_owned());
                let Some(name) = name else { continue };
                if !path.extension().is_some_and(|x| x == "json") {
                    set.non_json.push(name);
                    continue;
                }
                let code = path
                    .file_stem()
                    .map(|s| s.to_string_lossy().into_owned())
                    .unwrap_or_default();
                let bytes = fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
                let (keys, error) = match fs::read_to_string(&path) {
                    Err(e) => (BTreeMap::new(), Some(format!("not readable ({e})"))),
                    Ok(text) => match parse_flat(&text) {
                        Ok(map) => (map, None),
                        Err(why) => (BTreeMap::new(), Some(why)),
                    },
                };
                set.files.push(LocaleFile { code, path, bytes, keys, error });
            }
        }

        let lock_path = plugin_dir.join(LOCK_FILE);
        if lock_path.is_file() {
            match fs::read_to_string(&lock_path).map_err(|e| e.to_string()).and_then(|t| {
                serde_json::from_str::<Value>(&t).map_err(|e| e.to_string())
            }) {
                Err(e) => set.lock_error = Some(e),
                Ok(v) => set.lock = Some(Lock::from_json(&v)),
            }
        }

        set
    }

    pub fn get(&self, code: &str) -> Option<&LocaleFile> {
        self.files.iter().find(|f| f.code == code)
    }

    /// The codes this plugin ships, in file order.
    pub fn codes(&self) -> Vec<&str> {
        self.files.iter().map(|f| f.code.as_str()).collect()
    }

    /// Every file that loaded, `qps` excluded — the set the parity rules run
    /// over. `qps` is our own pseudo-locale and is never held to parity.
    fn real(&self) -> impl Iterator<Item = &LocaleFile> {
        self.files
            .iter()
            .filter(|f| f.error.is_none() && f.code != PSEUDO_CODE)
    }
}

impl Lock {
    fn from_json(v: &Value) -> Self {
        let mut lock = Lock {
            schema: v.get("schema").and_then(Value::as_str).unwrap_or_default().to_string(),
            source: v.get("source").and_then(Value::as_str).unwrap_or("en").to_string(),
            locales: BTreeMap::new(),
        };
        if let Some(map) = v.get("locales").and_then(Value::as_object) {
            for (code, entries) in map {
                let mut per = BTreeMap::new();
                if let Some(e) = entries.as_object() {
                    for (k, digest) in e {
                        if let Some(d) = digest.as_str() {
                            per.insert(k.clone(), d.to_string());
                        }
                    }
                }
                lock.locales.insert(code.clone(), per);
            }
        }
        lock
    }

    fn to_json(&self) -> Value {
        let mut locales = Map::new();
        for (code, entries) in &self.locales {
            if entries.is_empty() {
                continue;
            }
            let mut per = Map::new();
            for (k, d) in entries {
                per.insert(k.clone(), Value::String(d.clone()));
            }
            locales.insert(code.clone(), Value::Object(per));
        }
        json!({
            "schema": LOCK_SCHEMA,
            "source": if self.source.is_empty() { "en".into() } else { self.source.clone() },
            "locales": Value::Object(locales),
        })
    }
}

/// A locale file's bytes as a flat string map, or why it cannot be one.
///
/// **The daemon's parser is the authority.** It deserialises
/// `HashMap<String,String>` and drops the WHOLE file on any non-string value,
/// silently, at install time — so a nested object, a number, `null`, or a
/// top-level array all mean the same thing on a user's machine: no
/// translations, no message anywhere. This says which, before the bundle is
/// sealed.
fn parse_flat(text: &str) -> std::result::Result<BTreeMap<String, String>, String> {
    let value: Value = serde_json::from_str(text).map_err(|e| format!("not JSON ({e})"))?;
    let Some(obj) = value.as_object() else {
        return Err(format!(
            "the top level is {}, not an object. The daemon deserialises a locale file as a \
             flat map of string to string and drops the whole file on anything else",
            kind_of(&value)
        ));
    };
    let mut out = BTreeMap::new();
    for (k, v) in obj {
        match v.as_str() {
            Some(s) => {
                out.insert(k.clone(), s.to_string());
            }
            None => {
                // The hint is built on the FAMILY base, not on the key as
                // written: `{"msg.done.one": {...}}` used to be answered with
                // `("msg.done.one.one", "msg.done.one.other")`, which is a
                // suggestion no reader of this file would ever have wanted.
                let (base, _) = split_category(k);
                return Err(format!(
                    "\"{k}\" is {}, not a string. The daemon drops the WHOLE file on one \
                     non-string value — not just that key — so every other translation in \
                     this file is lost too. Plurals are key suffixes \
                     (\"{base}.one\", \"{base}.other\"), never nested objects",
                    kind_of(v)
                ));
            }
        }
    }
    Ok(out)
}

fn kind_of(v: &Value) -> &'static str {
    match v {
        Value::Null => "null",
        Value::Bool(_) => "a boolean",
        Value::Number(_) => "a number",
        Value::String(_) => "a string",
        Value::Array(_) => "an array",
        Value::Object(_) => "an object",
    }
}

// ── plural families ──────────────────────────────────────────────────────────

/// Split `msg.done.few` into `("msg.done", Some("few"))`, or `(key, None)`.
fn split_category(key: &str) -> (&str, Option<&str>) {
    match key.rsplit_once('.') {
        Some((base, cat)) if PLURAL_CATEGORIES.contains(&cat) && !base.is_empty() => {
            (base, Some(cat))
        }
        _ => (key, None),
    }
}

/// Every base that is a plural FAMILY, computed over the union of every loaded
/// locale file.
///
/// **A family is a base carrying at least two distinct CLDR categories
/// somewhere in the union.** That threshold is the whole reason parity below is
/// over families and not raw keys: `locale add ru` writes `msg.done.few` and
/// `msg.done.many`, which `en.json` cannot legally contain, so a raw-key parity
/// rule would fire on a file this CLI itself just wrote and recommended.
///
/// Two is also what stops the collapse from being a trap. A plugin with one
/// genuine key literally named `something.other` and no siblings is NOT a
/// plural family, so E15 does not go on to demand `something.one` of it — which
/// would be this file refusing a plugin that works.
fn plural_families(set: &LocaleSet) -> BTreeSet<String> {
    let mut categories: BTreeMap<String, BTreeSet<&str>> = BTreeMap::new();
    for file in set.real() {
        for key in file.keys.keys() {
            if let (base, Some(cat)) = split_category(key) {
                categories.entry(base.to_string()).or_default().insert(cat);
            }
        }
    }
    categories
        .into_iter()
        .filter(|(_, cats)| cats.len() >= 2)
        .map(|(base, _)| base)
        .collect()
}

/// The parity identity of one key: its family when it belongs to one, else
/// itself.
fn family_id(key: &str, families: &BTreeSet<String>) -> String {
    if let (base, Some(_)) = split_category(key)
        && families.contains(base)
    {
        return base.to_string();
    }
    key.to_string()
}

fn family_ids(file: &LocaleFile, families: &BTreeSet<String>) -> BTreeSet<String> {
    file.keys.keys().map(|k| family_id(k, families)).collect()
}

// ── the `$` marker ───────────────────────────────────────────────────────────

/// What a `$`-leading string in a manifest actually is.
enum Marker<'a> {
    /// `$$foo` — the daemon's escape for a literal leading dollar.
    Escaped,
    /// `$foo.bar` — a reference to the catalogue key `foo.bar`.
    Key(&'a str),
}

fn marker(s: &str) -> Option<Marker<'_>> {
    let rest = s.strip_prefix('$')?;
    if rest.starts_with('$') {
        return Some(Marker::Escaped);
    }
    Some(Marker::Key(rest))
}

/// Is this the shape of a catalogue key, as opposed to a value that happens to
/// begin with a dollar?
///
/// A deliberate second implementation of the daemon's `looks_like_key`, and it
/// is allowed to be one **because nothing here refuses on it**. It only ever
/// narrows a refusal — a `$string` that fails this predicate is never an error,
/// so a drift between the two can cost a note, never a rejected bundle. The
/// dot is what separates a key from `$HOME`, `$PATH` and `$USD`.
fn looks_like_key(candidate: &str) -> bool {
    let mut segments = candidate.split('.');
    let Some(first) = segments.next() else {
        return false;
    };
    if !first.starts_with(|c: char| c.is_ascii_alphabetic())
        || !first.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
    {
        return false;
    }
    let mut dotted = false;
    for segment in segments {
        dotted = true;
        if segment.is_empty() || !segment.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
            return false;
        }
    }
    dotted
}

/// One `$string` found in the manifest, and where.
struct Reference {
    key: String,
    /// A human-readable path — `[config] schema properties.token.title`.
    at: String,
    /// A LABEL position (something a human reads) rather than a VALUE the
    /// daemon would rewrite under the user's feet.
    label: bool,
}

/// Walk a config schema, collecting every `$`-leading string with its position.
fn collect_schema_refs(value: &Value, path: &str, label: bool, out: &mut Vec<Reference>) {
    match value {
        Value::String(s) => {
            if let Some(Marker::Key(key)) = marker(s) {
                out.push(Reference { key: key.to_string(), at: path.to_string(), label });
            }
        }
        Value::Object(map) => {
            for (k, v) in map {
                let child = if path.is_empty() { k.clone() } else { format!("{path}.{k}") };
                collect_schema_refs(v, &child, LABEL_KEYS.contains(&k.as_str()), out);
            }
        }
        Value::Array(items) => {
            for (i, v) in items.iter().enumerate() {
                // An array inherits its member's position: `enumNames` holds
                // labels, `enum` and `examples` hold values.
                collect_schema_refs(v, &format!("{path}[{i}]"), label, out);
            }
        }
        _ => {}
    }
}

// ── the script check ─────────────────────────────────────────────────────────

/// Is this character a letter in the Latin script?
///
/// Basic Latin, Latin-1 Supplement, Latin Extended-A and Latin Extended-B —
/// which covers every language written in a Latin alphabet that Astra can be
/// set to, accents and all.
fn is_latin_letter(c: char) -> bool {
    if !c.is_alphabetic() {
        return false;
    }
    matches!(c as u32,
        0x0041..=0x005A | 0x0061..=0x007A | 0x00C0..=0x024F)
}

/// `(latin letters, letters)` in a string.
///
/// **Letters, not CASED letters**, and that is a correction to the plan this
/// came from. Han, kana and hangul have no case at all, so a cased-letters
/// denominator makes a perfectly ordinary Japanese description report
/// *"contains no letters at all"* — a sentence that is simply false, printed at
/// the author in place of the real reason. `char::is_alphabetic` is true for
/// all of them, so the fraction stays meaningful and the no-letters message is
/// reserved for the case it describes: a description made of digits, emoji and
/// punctuation.
fn latin_fraction(text: &str) -> (usize, usize) {
    let letters = text.chars().filter(|c| c.is_alphabetic()).count();
    let latin = text.chars().filter(|c| is_latin_letter(*c)).count();
    (latin, letters)
}

/// Below this fraction of Latin letters, a string is not English.
///
/// 60% and not 100%: an English sentence quoting a Russian command name, or a
/// German product name in an English summary, must pass. This is a SCRIPT
/// check, not a language detector — it catches a card written entirely in
/// another alphabet, and cannot tell English from French. The error message
/// says so in its own last paragraph, because a gate that overstates its reach
/// is one people route around.
const LATIN_FLOOR: f64 = 0.60;

fn is_latin_script(text: &str) -> bool {
    let (latin, letters) = latin_fraction(text);
    letters > 0 && (latin as f64 / letters as f64) >= LATIN_FLOOR
}

// ── digests ──────────────────────────────────────────────────────────────────

/// The first 12 hex of sha256 of the EXACT English UTF-8 bytes, no
/// normalisation.
///
/// Debian's `Description-md5` property: a hash of the English used as the
/// lookup key, so changed English stops matching and the base shows. Derived
/// on every `sync` rather than asserted by a human, because a state field an
/// author maintains by hand is a state field that lies.
pub fn digest(english: &str) -> String {
    let mut h = Sha256::new();
    h.update(english.as_bytes());
    let out = h.finalize();
    out.iter().take(6).map(|b| format!("{b:02x}")).collect()
}

/// The English one key of a non-English locale is measured against.
///
/// Normally `en.json`'s value for the same key. The exception is a plural
/// FAMILY member English cannot legally carry — `ru`'s `few` and `many`, which
/// `locale add ru` writes and E15 requires — and those are anchored on
/// `<base>.other`: the one category every language has, and the row English
/// always carries for a family.
///
/// **This is why the lock now covers a whole plural family.** It used to be a
/// bare `en.keys.get(key)` at three call sites, each of which `continue`d on a
/// miss, so `ru`'s `few` and `many` got no lock entry, were never counted as
/// seeded, and could never be reported stale. Editing both English rows of a
/// four-row Russian family reported **two** stale; `sync --accept` then cleared
/// it and the family shipped two-thirds updated and reading fresh.
///
/// The digest recorded for such a key is still the first 12 hex of sha256 over
/// exact English UTF-8 bytes — the bytes of `<base>.other`. That keeps the
/// lock's single rule intact, which matters because a second implementation in
/// another repository reads these values (coupling C19, and gap 9 is that
/// nothing compares the two).
fn english_for<'a>(
    en: &'a LocaleFile,
    key: &str,
    families: &BTreeSet<String>,
) -> Option<&'a String> {
    if let Some(v) = en.keys.get(key) {
        return Some(v);
    }
    if let (base, Some(_)) = split_category(key)
        && families.contains(base)
    {
        return en.keys.get(&format!("{base}.other"));
    }
    None
}

/// One key's standing against the lock.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
enum Freshness {
    /// The value is byte-identical to TODAY's English — seeded, not translated.
    ///
    /// **It still gets a lock entry**, and that is the fix this enum exists to
    /// carry: recording the English a seed was copied from is what lets a later
    /// English edit turn the seed stale, exactly as it turns a translation
    /// stale. Leaving it unrecorded is what let `sync` stamp today's digest onto
    /// yesterday's English and call it a translation.
    Untranslated,
    /// Translated, and the lock records the English it was made against.
    Fresh,
    /// Differs from English and the lock has never seen this key — a key the
    /// author added by hand since the last `sync`.
    New,
    /// The value hashes to the English the lock recorded for it, so the value
    /// **is** that English: nobody translated this, and the base moved out from
    /// under the seed.
    SeededStale,
    /// Translated, and the English has changed since. The reader gets a
    /// confidently wrong sentence and nothing ever tells them.
    Stale,
}

fn freshness(lock: Option<&Lock>, code: &str, key: &str, english: &str, theirs: &str) -> Freshness {
    if theirs == english {
        return Freshness::Untranslated;
    }
    let recorded = lock.and_then(|l| l.locales.get(code)).and_then(|m| m.get(key));
    match recorded {
        None => Freshness::New,
        Some(d) if *d == digest(english) => Freshness::Fresh,
        // The value hashes to the English the lock recorded against it, which
        // means the value never stopped being that English. Naming this apart
        // from `Stale` costs one arm and buys the author a true sentence: there
        // is no translation here to have gone wrong.
        Some(d) if *d == digest(theirs) => Freshness::SeededStale,
        Some(_) => Freshness::Stale,
    }
}

/// What the lock says has moved out from under a locale file, per code.
#[derive(Default)]
struct LockDrift {
    /// Translated against English that has since changed. N3.
    stale: BTreeMap<String, Vec<String>>,
    /// Never translated: still the English it was seeded from, and that English
    /// has since changed. N15.
    seeded: BTreeMap<String, Vec<String>>,
}

fn lock_drift(set: &LocaleSet) -> LockDrift {
    let mut out = LockDrift::default();
    let Some(en) = set.get("en").filter(|f| f.error.is_none()) else {
        return out;
    };
    let families = plural_families(set);
    for file in set.real() {
        if file.code == "en" {
            continue;
        }
        for (key, theirs) in &file.keys {
            let Some(english) = english_for(en, key, &families) else { continue };
            match freshness(set.lock.as_ref(), &file.code, key, english, theirs) {
                Freshness::Stale => {
                    out.stale.entry(file.code.clone()).or_default().push(key.clone());
                }
                Freshness::SeededStale => {
                    out.seeded.entry(file.code.clone()).or_default().push(key.clone());
                }
                _ => {}
            }
        }
    }
    out
}

/// Every stale TRANSLATION, per code — N3's input, and `locale ls`'s column.
#[cfg(test)]
fn stale_keys(set: &LocaleSet) -> BTreeMap<String, Vec<String>> {
    lock_drift(set).stale
}

// ── the rules ────────────────────────────────────────────────────────────────

/// Every locale rule, in one pass.
///
/// `check` folds the result into its own report; `build` takes the errors and
/// refuses to pack. Both call this, which is the point: two readers of
/// `plugin.toml` live in one binary and only one of them used to validate, so
/// a rule enforced in `check` alone was one command away from being optional.
pub fn findings(dir: &Path, manifest: &PluginManifest, gate: Gate) -> Findings {
    let set = LocaleSet::read(dir);
    let mut f = Findings::new();

    check_listing_language(manifest, &mut f);
    check_permission_reasons(manifest, &mut f);
    check_declared_plane(dir, manifest, &set, &mut f);

    if !set.present {
        check_absent_locales(dir, &set, &mut f);
        return f;
    }

    check_files(&set, gate, &mut f);
    check_parity(&set, &mut f);
    check_listing_keys(manifest, &set, &mut f);
    check_lock(&set, gate, &mut f);
    check_listing_i18n_budget(manifest, &set, &mut f);
    check_strays(dir, &set, &mut f);
    f
}

/// **E11 / N12 — the English gate.** The store card, the store search index,
/// every client that predates localization, and every user whose language the
/// author has not translated all read `plugin.description`.
fn check_listing_language(m: &PluginManifest, f: &mut Findings) {
    let description = m.plugin.description.trim();
    if !description.is_empty() && !is_latin_script(description) {
        let (latin, letters) = latin_fraction(description);
        let reason = match latin.checked_mul(100).and_then(|n| n.checked_div(letters)) {
            None => "it contains no letters at all".to_string(),
            Some(pct) => {
                format!("{}% of its letters are outside the Latin script", 100 - pct)
            }
        };
        f.err(
            "E11",
            format!(
                "plugin.description is not in English.\n\
                 \x20         \"{description}\"\n\
                 \x20         {reason}.\n\
                 \x20       The store card, the store search index, every client that predates \
                 localization,\n\
                 \x20       and every user whose language you have not translated all show this \
                 string.\n\
                 \x20       English is the base for all of them.\n\
                 \x20       Fix: write plugin.description in English, and put your own language \
                 in\n\
                 \x20            locales/ru.json under the key \"listing.description\".\n\
                 \x20       This is a SCRIPT check, not a language detector. It catches a card \
                 written\n\
                 \x20       entirely in another alphabet. It cannot tell English from French."
            ),
        );
    }

    let name = m.plugin.name.trim();
    if !name.is_empty() && !is_latin_script(name) {
        // Deliberately NOT an error. Product names are legitimately anything,
        // and refusing one would refuse a plugin that is doing nothing wrong.
        // It is not left unobserved either: the registry's ingest PR carries
        // the same finding where a human is already reading.
        f.note(
            "N12",
            format!(
                "plugin.name \"{name}\" is mostly outside the Latin script. That is allowed — a \
                 product name is not prose — but the card's SUMMARY is held to English, so check \
                 the two read as one listing."
            ),
        );
    }

    if description.chars().count() > cap("max_description_length") {
        f.err(
            "E14",
            format!(
                "plugin.description is {} characters; the registry's schema caps a listing \
                 description at {} (spec/listing-limits.yaml). A record over the cap is refused \
                 at ingest, in another repository, after you have pushed the tag.",
                description.chars().count(),
                cap("max_description_length")
            ),
        );
    }
    if name.chars().count() > cap("max_name_length") {
        f.err(
            "E14",
            format!(
                "plugin.name is {} characters; the registry caps a listing name at {} \
                 (spec/listing-limits.yaml).",
                name.chars().count(),
                cap("max_name_length")
            ),
        );
    }
}

/// **E12 / E13 / N7 — `[permissions] reason`.**
fn check_permission_reasons(m: &PluginManifest, f: &mut Findings) {
    for (id, req) in &m.permissions.0 {
        if req.reason.is_empty() {
            continue;
        }
        f.note(
            "N7",
            format!(
                "[permissions.{id}] reason is rendered on the consent sheet untranslated, under \
                 a permission LABEL that Astra has already translated into all ten languages. \
                 Write it in English."
            ),
        );
        if req.reason.starts_with('$') {
            f.err(
                "E12",
                format!(
                    "[permissions.{id}] reason begins with '$'.\n\
                     \x20       A permission reason is rendered on the consent sheet BEFORE the \
                     plugin is\n\
                     \x20       installed, and its exact bytes are inside permissions_hash, which \
                     three\n\
                     \x20       implementations compute and the registry countersigns. A key \
                     resolved after\n\
                     \x20       install is resolved out of the plugin's own install directory — \
                     which the\n\
                     \x20       plugin process can write, because plugins are not sandboxed. That \
                     is text\n\
                     \x20       nobody countersigned, shown as though they had.\n\
                     \x20       Write the reason in English, under {} characters.",
                    cap("max_permission_reason_chars")
                ),
            );
        }
        let limit = cap("max_permission_reason_chars");
        if req.reason.chars().count() > limit {
            f.err(
                "E13",
                format!(
                    "[permissions.{id}] reason is {} characters; the registry's schema caps it at \
                     {limit} (spec/listing-limits.yaml). A version record over the cap fails \
                     schema validation at ingest — in another repository, after the tag is \
                     pushed, with nothing you can do but cut a new version.",
                    req.reason.chars().count()
                ),
            );
        }
    }
}

/// **E7 / E16 / E17 / E20 / N5 / N6 — every `$string` in the manifest.**
fn check_declared_plane(dir: &Path, m: &PluginManifest, set: &LocaleSet, f: &mut Findings) {
    let en = set.get("en").filter(|x| x.error.is_none());
    let known = |key: &str| en.is_some_and(|e| e.keys.contains_key(key));

    // ── [config] schema ──
    let mut refs: Vec<Reference> = Vec::new();
    if let Some(config) = m.config.as_ref()
        && !config.schema.trim().is_empty()
        && let Ok(schema) = serde_json::from_str::<Value>(&config.schema)
    {
        collect_schema_refs(&schema, "", false, &mut refs);
    }

    for r in &refs {
        let at = format!("[config] schema {}", r.at);
        match (r.label, known(&r.key)) {
            (true, true) => {}
            (true, false) if looks_like_key(&r.key) => f.err(
                "E7",
                format!(
                    "{at} references `${}`, which is in no locale file.\n\
                     \x20       The daemon looks that key up and, finding nothing, renders the \
                     BARE KEY —\n\
                     \x20       the user reads `{}` on the settings form, which looks like a \
                     deliberate\n\
                     \x20       identifier rather than a mistake.\n\
                     \x20       Fix: add \"{}\" to locales/en.json, or write the English text \
                     here directly.",
                    r.key, r.key, r.key
                ),
            ),
            (true, false) => f.note(
                "N5",
                format!(
                    "{at} is `${}`, which matches no key in locales/en.json and is not shaped \
                     like one. The daemon leaves it exactly as it stands, dollar included — \
                     which is right if you meant the literal text, and wrong if that is a \
                     misspelt key. If you meant the literal, `$${}` is the escape.",
                    r.key, r.key
                ),
            ),
            (false, true) => f.err(
                "E16",
                format!(
                    "{at} is `${}`, and `{}` IS a key in locales/en.json.\n\
                     \x20       That position is a VALUE, not a label: the daemon resolves every \
                     string in a\n\
                     \x20       config schema including \"default\", so this one is rewritten to \
                     the\n\
                     \x20       translation — and the setting your users end up with then differs \
                     by UI\n\
                     \x20       language, with no rebuild and nothing to tell you.\n\
                     \x20       Fix: rename the locale key, or escape the value as `$${}`.",
                    r.key, r.key, r.key
                ),
            ),
            (false, false) => f.note(
                "N5",
                format!(
                    "{at} is a value beginning with `$` (`${}`). Nothing resolves it today and \
                     the daemon leaves it alone — but if a locale key of that name is ever \
                     added, this default is silently rewritten per UI language. `$${}` is the \
                     escape that makes it permanent.",
                    r.key, r.key
                ),
            ),
        }
    }

    // ── [plugin] name / description ──
    //
    // E20 is unconditional and is NOT gated on min_astra_version, because the
    // reader that breaks is not a daemon. `MANIFEST.json` carries these two
    // strings raw, and the registry's probe reads them raw out of the packed
    // manifest to derive the store card — so a `$key` here puts the literal
    // text `$plugin.name` on the store card of every Astra that has ever
    // existed, including ones that resolve keys perfectly well elsewhere.
    for (field, text) in [("name", &m.plugin.name), ("description", &m.plugin.description)] {
        if let Some(Marker::Key(key)) = marker(text) {
            f.err(
                "E20",
                format!(
                    "[plugin] {field} begins with '$' (`${key}`).\n\
                     \x20       The registry derives the store card from the PACKED plugin.toml, \
                     unresolved,\n\
                     \x20       and MANIFEST.json carries the same bytes. A key here is the \
                     literal text\n\
                     \x20       a user reads on the store card.\n\
                     \x20       Fix: write English here, and put your translation in \
                     locales/<code>.json\n\
                     \x20            under \"listing.{field}\" — the two keys the ingest bot \
                     reads."
                ),
            );
        }
    }

    // ── [ui] contribution labels ──
    //
    // E17 is about the READER'S daemon, not about Astra's git history. Astra's
    // `main` resolves action, trigger and UI labels at serve time (the resolver
    // landed there on 2026-08-22) — and the newest Astra RELEASE is v0.2.0,
    // tagged 2026-08-16, which does not. `min_astra_version` is the only thing
    // in the manifest that stops an older daemon installing this plugin at all,
    // so it is exactly the right gate, and landing the code upstream does not
    // relax it by itself.
    if let Some(ui) = m.ui.as_ref() {
        for c in &ui.contributions {
            let Some(Marker::Key(key)) = marker(&c.label) else { continue };
            if m.plugin.min_astra_version.is_empty() {
                f.err(
                    "E17",
                    format!(
                        "[[ui.contributions]] '{}' has label `${key}` and plugin.min_astra_version \
                         is empty.\n\
                         \x20       Resolving plugin keys outside [config] schema is new. The \
                         newest Astra\n\
                         \x20       RELEASE does not do it, so on every daemon in the world today \
                         this label\n\
                         \x20       renders as the literal text a user cannot act on.\n\
                         \x20       Two ways forward, and only you can pick:\n\
                         \x20         * write the English label here, and translate the plugin's \
                         own\n\
                         \x20           strings with I18n — nothing is lost and it works \
                         everywhere; or\n\
                         \x20         * set plugin.min_astra_version to the first Astra release \
                         that resolves\n\
                         \x20           these, so an older daemon refuses to install rather than \
                         showing a key.\n\
                         \x20           That release is not published yet, so there is no number \
                         to write\n\
                         \x20           today — this CLI will not invent one for you.",
                        c.id
                    ),
                );
            } else {
                f.note(
                    "N6",
                    format!(
                        "[[ui.contributions]] '{}' has label `${key}` and requires Astra {} or \
                         newer. Serve-time resolution of UI labels is newer than the current \
                         Astra release — make sure the version you named is one that has it.",
                        c.id, m.plugin.min_astra_version
                    ),
                );
            }
            if !known(key) && looks_like_key(key) {
                f.err(
                    "E7",
                    format!(
                        "[[ui.contributions]] '{}' references `${key}`, which is in no locale \
                         file. Add \"{key}\" to locales/en.json.",
                        c.id
                    ),
                );
            }
        }
    }

    // ── N13: the TypeScript packaging trap ──
    check_typescript_locale_import(dir, f);
}

/// **N13.** `astra-plugin build` bundles TypeScript to one CJS file and packs
/// only `dist/`, so `import en from "./locales/en.json"` gives working runtime
/// strings — esbuild inlines it — and a settings page full of raw keys, because
/// the daemon reads `locales/` off disk and the bundle has none.
fn check_typescript_locale_import(dir: &Path, f: &mut Findings) {
    let src = dir.join("src");
    if !src.is_dir() || !dir.join("package.json").is_file() {
        return;
    }
    for entry in walkdir::WalkDir::new(&src).sort_by_file_name().into_iter().flatten() {
        if !entry.file_type().is_file() {
            continue;
        }
        if !entry.path().extension().is_some_and(|e| e == "ts" || e == "tsx" || e == "js") {
            continue;
        }
        let Ok(text) = fs::read_to_string(entry.path()) else { continue };
        if text.contains("locales/") && (text.contains("import ") || text.contains("require(")) {
            let rel = entry
                .path()
                .strip_prefix(dir)
                .unwrap_or(entry.path())
                .to_string_lossy()
                .replace('\\', "/");
            f.note(
                "N13",
                format!(
                    "{rel} names `locales/` in an import. esbuild inlines a JSON import into \
                     dist/, so your own strings work and the daemon's do not — it reads \
                     locales/ off disk, and only the directory beside plugin.toml is packed. \
                     Use I18n.discover(), which reads the filesystem."
                ),
            );
            return;
        }
    }
}

/// **N1 with teeth.** No `locales/` at all is usually nothing to check — unless
/// a locale-shaped file is sitting somewhere else in the packed tree, which is
/// the Python author who wrote `src/locales/en.json`, got working runtime
/// strings, shipped both files, and got nothing from the daemon.
///
/// # Both halves of the escalation, because dropping them cost a Rust author
///
/// The plan's rule was an ERROR for a locale-shaped file **in the packed tree**
/// and **with no top-level `locales/`**. Both conditions were dropped, so any
/// `<anything>/locales/<code>.json` was fatal — and a Rust plugin with a
/// `tests/locales/ru.json` fixture could not be checked, built or dev-run,
/// over a file its bundle does not contain. `commands::build` is asked what
/// ships rather than told.
fn check_absent_locales(dir: &Path, set: &LocaleSet, f: &mut Findings) {
    let strays = stray_locale_files(dir, set);
    if strays.is_empty() {
        f.note(
            "N1",
            "no locales/ directory — this plugin declares no translations, so there is nothing \
             here to check. `astra-plugin locale add en` starts one."
                .to_string(),
        );
        return;
    }
    for (rel, in_locales_dir) in strays {
        let packed = is_packed(dir, &rel);
        if in_locales_dir && packed {
            f.err(
                "N1",
                format!(
                    "{rel} is named for a language Astra can be set to, and there is no locales/ \
                     directory beside plugin.toml. The daemon reads ONLY \
                     <plugin>/locales/*.json, so this file ships in your bundle and is read by \
                     nothing. Move it to locales/."
                ),
            );
        } else {
            f.note("N1", stray_note(dir, &rel, packed));
        }
    }
}

/// The note for a locale-shaped file the daemon will not read.
///
/// Whether it ships is asked of the packer, never asserted here: the same path
/// under `src/` is packed in a Python project and absent from a Rust one, and
/// the sentence that gets that wrong is the one an author acts on.
fn stray_note(dir: &Path, rel: &str, packed: bool) -> String {
    let language = crate::commands::build::detect_language(dir);
    format!(
        "{rel} is named for a language, and is not the locales/ directory the daemon reads — \
         which is only <plugin>/locales/*.json, beside plugin.toml. {} If it is a test fixture \
         or your own data file, this note is all it needs to be.",
        if packed {
            format!("`astra-plugin build` packs it into a {language} bundle, where nothing opens it.")
        } else {
            format!("A {language} bundle does not contain it, so it is a file only your own code can read.")
        }
    )
}

/// Does `astra-plugin build` put this path in the bundle?
///
/// Delegated to `commands::build`, which owns the answer. `ui/` and `locales/`
/// ship for every language; everything else depends on the language's roots.
fn is_packed(dir: &Path, rel: &str) -> bool {
    if rel.starts_with("ui/") || rel.starts_with("locales/") {
        return true;
    }
    let language = crate::commands::build::detect_language(dir);
    crate::commands::build::packed_source_roots(&language)
        .iter()
        .any(|root| *root == "." || rel.starts_with(&format!("{root}/")))
}

/// `*.json` elsewhere in the tree whose stem is a language code.
///
/// Returns `(relative path, its parent directory is named `locales`)`. The
/// second half is what decides error versus note: `src/locales/en.json` is
/// unambiguous, and a `de.json` in a `data/` directory is very likely a data
/// file that happens to share a name with a language.
fn stray_locale_files(dir: &Path, set: &LocaleSet) -> Vec<(String, bool)> {
    // `locales` is deliberately NOT on this list, and it is the whole point:
    // `src/locales/en.json` is exactly the file this scan exists to find, and an
    // earlier draft skipped every directory of that name and therefore found
    // nothing — a scan that had stopped matching while still reporting a clean
    // tree. The plugin's own top-level `locales/` is excluded by comparing
    // parents below, which is precise rather than by-name.
    //
    // `node_modules` is not optional: `yargs` alone ships `locales/en.json`, so
    // one npm dependency would otherwise make every TypeScript plugin fail this.
    const SKIP: &[&str] = &[
        "target",
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
    ];
    let mut out = Vec::new();
    let walk = walkdir::WalkDir::new(dir).sort_by_file_name().into_iter().filter_entry(|e| {
        !e.file_type().is_dir()
            || e.path() == dir
            || !SKIP.contains(&e.file_name().to_string_lossy().as_ref())
    });
    for entry in walk.flatten() {
        if !entry.file_type().is_file() {
            continue;
        }
        let path = entry.path();
        if path.parent() == Some(set.dir.as_path()) {
            continue;
        }
        let Some(stem) = path.file_stem().and_then(|s| s.to_str()) else { continue };
        if !path.extension().is_some_and(|e| e == "json") || !LOCALE_CODES.contains(&stem) {
            continue;
        }
        let rel = path.strip_prefix(dir).unwrap_or(path).to_string_lossy().replace('\\', "/");
        let in_locales_dir =
            path.parent().and_then(|p| p.file_name()).is_some_and(|n| n == "locales");
        out.push((rel, in_locales_dir));
    }
    out
}

/// The same scan, run when `locales/` DOES exist.
///
/// A NOTE in every case, and that is the second half of the plan's rule: the
/// plugin's translations are already where the daemon reads them, so a second
/// locale-shaped tree is a duplicate or a fixture rather than the mistake N1
/// exists to catch. Escalating it refused a legitimate layout.
fn check_strays(dir: &Path, set: &LocaleSet, f: &mut Findings) {
    for (rel, _) in stray_locale_files(dir, set) {
        let packed = is_packed(dir, &rel);
        f.note("N1", stray_note(dir, &rel, packed));
    }
}

/// **E18 — one locale file over the registry's size caps.**
///
/// Both halves are the registry's numbers (`spec/listing-limits.yaml`), and
/// both are refused at ingest, in another repository, after a tag the author
/// cannot move: a 431 KB `en.json` passed `astra-plugin check` with `OK` and
/// came back `E_LOCALE_TOO_LARGE`.
///
/// **The byte half runs before the parse half and does not depend on it.** The
/// registry checks `entry.bytes.length` before `JSON.parse` precisely so a
/// runaway file is refused without being read, so an oversized file that also
/// fails to parse is E18 *and* E6 here rather than E6 alone — the size is the
/// finding the author has to act on, and it is the one that survives the file
/// being unreadable.
fn check_locale_size(file: &LocaleFile, f: &mut Findings) {
    let max_bytes = cap("max_locale_bytes") as u64;
    if file.bytes > max_bytes {
        f.err(
            "E18",
            format!(
                "locales/{}.json is {} bytes; the registry refuses a locale file over {} \
                 (spec/listing-limits.yaml max_locale_bytes).\n\
                 \x20       That cap is checked BEFORE the file is parsed — the bot must be able \
                 to refuse a\n\
                 \x20       runaway file without reading it — so no amount of valid JSON gets \
                 past it, and\n\
                 \x20       the refusal happens at ingest, after your tag.",
                file.code, file.bytes, max_bytes
            ),
        );
    }
    let max_keys = cap("max_locale_keys");
    if file.keys.len() > max_keys {
        f.err(
            "E18",
            format!(
                "locales/{}.json declares {} keys; the registry refuses a locale file over {} \
                 (spec/listing-limits.yaml max_locale_keys).\n\
                 \x20       The parity rules compare key sets pairwise across every locale a \
                 bundle ships, so\n\
                 \x20       this number bounds work the ingest runner has to do rather than \
                 anything a user sees.",
                file.code,
                file.keys.len(),
                max_keys
            ),
        );
    }
}

/// **E19 — every locale block together, against the listing's byte budget.**
///
/// The `i18n` member of ONE listing record, as the registry DERIVES it: one
/// `{name, summary}` per code, a stale block demoted to English, a block that
/// comes out identical to the English card dropped. `max_listing_i18n_bytes`
/// bounds the lot, in BYTES.
///
/// # Why this is reachable from a tree that passes every other rule here
///
/// E14 bounds `listing.name` and `listing.description` per locale in
/// CHARACTERS, because that is what the registry's own `checkMetadata` counts.
/// This budget is in BYTES. Nine locales of astral-plane text sitting exactly
/// at the character caps come to 9,775 bytes against a budget of 8,192 — so
/// "every rule green" and "refused at ingest" are the same tree.
///
/// # The window, and why the skip is loud
///
/// The registry derives `summary` with `summarise(description,
/// max_summary_length)`, which flattens whitespace and may cut. Re-implementing
/// that cut here would be a second implementation of the one predicate that
/// already caused a catalogue-wide refusal when it existed twice. So this rule
/// computes the budget only in the window where `summarise` is provably the
/// identity — no run of whitespace, and inside the summary cap — and where no
/// value carries a formatting control the registry may replace. Outside that
/// window it says so, by name, and computes nothing: a budget check that
/// quietly guesses is worse than one that admits it cannot look.
fn check_listing_i18n_budget(m: &PluginManifest, set: &LocaleSet, f: &mut Findings) {
    let Some(en) = set.get("en").filter(|x| x.error.is_none()) else {
        return;
    };
    let summary_cap = cap("max_summary_length");
    let mut blocked: Vec<String> = Vec::new();
    // `summarise` is the identity exactly when it neither flattens nor cuts.
    // Returning WHY rather than a bool is what lets the skip name itself.
    let unstable = |text: &str| -> Option<&'static str> {
        if text.chars().count() > summary_cap {
            Some("is over max_summary_length, so the bot re-cuts it")
        } else if text.split_whitespace().collect::<Vec<_>>().join(" ") != text.trim() {
            Some("carries whitespace the bot flattens")
        } else {
            None
        }
    };

    // The English card, which every block is compared against and which fills a
    // missing half. `plugin.toml` and not `en.json`: the registry derives the
    // card's English from the manifest, and C18/E8 are what hold the two equal.
    let english_name = m.plugin.name.clone();
    let english_summary = m.plugin.description.clone();
    if let Some(why) = unstable(&english_summary) {
        note_unbudgeted(&[format!("plugin.toml's description {why}")], f);
        return;
    }

    let mut blocks: BTreeMap<String, (String, String)> = BTreeMap::new();
    for file in set.real() {
        if file.code == "en" || !LOCALE_CODES.contains(&file.code.as_str()) {
            continue;
        }
        let mut name: Option<String> = None;
        let mut summary: Option<String> = None;
        for (key, is_summary) in [("listing.name", false), ("listing.description", true)] {
            let (Some(english), Some(theirs)) = (en.keys.get(key), file.keys.get(key)) else {
                continue;
            };
            // Staleness DEMOTES rather than refusing, on both sides, so the
            // bytes budgeted are the bytes that ship.
            let value = match freshness(set.lock.as_ref(), &file.code, key, english, theirs) {
                Freshness::Stale | Freshness::SeededStale => english,
                _ => theirs,
            };
            if has_format_control(value) {
                blocked.push(format!(
                    "locales/{}.json's \"{key}\" carries a formatting control the registry \
                     replaces",
                    file.code
                ));
                continue;
            }
            if is_summary {
                if let Some(why) = unstable(value) {
                    blocked.push(format!("locales/{}.json's \"{key}\" {why}", file.code));
                    continue;
                }
                summary = Some(value.clone());
            } else {
                name = Some(value.clone());
            }
        }
        if name.is_none() && summary.is_none() {
            continue;
        }
        let name = name.unwrap_or_else(|| english_name.clone());
        let summary = summary.unwrap_or_else(|| english_summary.clone());
        // A block identical to the English card renders identically to no block
        // at all, and the registry drops it rather than paying for it in a
        // document every install downloads whole.
        if name == english_name && summary == english_summary {
            continue;
        }
        blocks.insert(file.code.clone(), (name, summary));
    }

    if !blocked.is_empty() {
        note_unbudgeted(&blocked, f);
        return;
    }
    if blocks.is_empty() {
        return;
    }

    let rendered = Value::Object(
        blocks
            .iter()
            .map(|(code, (name, summary))| {
                (code.clone(), json!({ "name": name, "summary": summary }))
            })
            .collect::<Map<String, Value>>(),
    );
    let size = serde_json::to_string(&rendered).map(|s| s.len()).unwrap_or(0);
    let budget = cap("max_listing_i18n_bytes");
    if size > budget {
        f.err(
            "E19",
            format!(
                "{} locale block(s) come to {size} bytes; the registry's budget for one \
                 listing's translations is {budget}\n\
                 \x20       (spec/listing-limits.yaml max_listing_i18n_bytes). Over it the \
                 whole `i18n` member is\n\
                 \x20       refused and every language falls back to the English card.\n\
                 \x20       This is a BYTE budget and E14's per-locale caps are in CHARACTERS, \
                 so a listing\n\
                 \x20       can satisfy every other rule here and still be over it — shorten \
                 the names and\n\
                 \x20       descriptions in locales/<code>.json, or ship fewer languages on the \
                 card.",
                blocks.len()
            ),
        );
    }
}

/// The loud half of E19's skip: what stopped it computing, by name.
fn note_unbudgeted(blocked: &[String], f: &mut Findings) {
    f.note(
        "N16",
        format!(
            "the registry's max_listing_i18n_bytes budget was NOT checked here: {}. That \
             derivation is the bot's (`summarise`, and the unsafe-text rule), and guessing at it \
             would refuse a listing the registry accepts. The budget is still enforced at \
             ingest.",
            preview(blocked)
        ),
    );
}

/// A formatting or control character the registry may refuse or replace.
///
/// **A conservativeness guard, not a copy of a rule.** `unsafeDisplayText` in
/// the bot decides what is refused; this only decides whether E19 can claim to
/// know what the derived block will contain. Anything on this list makes it say
/// it cannot, which is why a superset is the right shape and why nothing here
/// is a finding on its own.
fn has_format_control(s: &str) -> bool {
    s.chars().any(|c| {
        c.is_control()
            || matches!(c,
                '\u{200B}'..='\u{200F}'
                | '\u{202A}'..='\u{202E}'
                | '\u{2060}'..='\u{2064}'
                | '\u{2066}'..='\u{2069}'
                | '\u{FEFF}')
    })
}

/// **E1 / E4 / E5 / E6 / N8 / N10 / N11 — the files themselves.**
fn check_files(set: &LocaleSet, gate: Gate, f: &mut Findings) {
    for rel in &set.nested {
        f.err(
            "E5",
            format!(
                "{rel} is below locales/'s top level.\n\
                 \x20       `astra-plugin build` packs locales/ RECURSIVELY and the daemon reads \
                 only the\n\
                 \x20       top level, so this file is packed, digested, signed, shipped, \
                 installed — and\n\
                 \x20       opened by nothing, with no error at any point.\n\
                 \x20       Fix: flatten it. A locale file is locales/<code>.json and its keys \
                 carry the\n\
                 \x20            structure (\"config.token.title\"), because the daemon \
                 deserialises a\n\
                 \x20            flat map and drops the whole file on a nested object."
            ),
        );
    }
    for name in &set.non_json {
        f.note(
            "N8",
            format!("locales/{name} is not a .json file, so nothing loads it."),
        );
    }

    if set.files.is_empty() {
        f.note("N1", "locales/ exists and holds no .json file.".to_string());
        return;
    }

    for file in &set.files {
        check_locale_size(file, f);
        if let Some(why) = &file.error {
            f.err("E6", format!("locales/{}.json: {why}", file.code));
            continue;
        }
        if file.code == PSEUDO_CODE {
            if gate == Gate::Build {
                f.err(
                    "E4",
                    format!(
                        "locales/{PSEUDO_CODE}.json is a pseudo-locale for finding \
                         un-externalised strings. `Settings::validate` refuses `{PSEUDO_CODE}`, \
                         so it can never be selected — delete it before you pack."
                    ),
                );
            } else {
                f.note(
                    "N10",
                    format!(
                        "locales/{PSEUDO_CODE}.json is present. `astra-plugin check` permits it \
                         and `astra-plugin build` refuses it — it is a development aid, not a \
                         language."
                    ),
                );
            }
            continue;
        }
        if !LOCALE_CODES.contains(&file.code.as_str()) {
            f.err(
                "E4",
                format!(
                    "locales/{}.json is not a language Astra can be set to.\n\
                     \x20       Astra's languages are: {} (spec/locales.yaml).\n\
                     \x20       Language matching is exact string equality, and there are no \
                     region tags\n\
                     \x20       anywhere in this system — Chinese is `zh`, never `zh-CN`. This \
                     file is\n\
                     \x20       packed into your bundle, digested, signed, installed, and read by \
                     nothing.{}",
                    file.code,
                    LOCALE_CODES.join(" "),
                    did_you_mean(&file.code)
                        .map(|c| format!("\n\x20       Did you mean locales/{c}.json?"))
                        .unwrap_or_default()
                ),
            );
        }
        for (key, value) in &file.keys {
            if value.is_empty() {
                f.note(
                    "N11",
                    format!(
                        "locales/{}.json \"{key}\" is an empty string. That is a TRANSLATION, not \
                         a miss — it is the only way to blank a string in one language — so this \
                         note exists to keep a deliberate blank visible. Delete the key to fall \
                         back to English.",
                        file.code
                    ),
                );
            }
        }
    }

    let has_real = set.real().next().is_some();
    if has_real && set.get("en").is_none() {
        let found: Vec<String> =
            set.real().map(|x| format!("{}.json", x.code)).collect();
        f.err(
            "E1",
            format!(
                "locales/ holds {} file(s) and locales/en.json is not one of them.\n\
                 \x20       Found: {}\n\
                 \x20       English is the base every other language falls back to. A user whose \
                 language\n\
                 \x20       file is missing a key falls through to en.json; without en.json there \
                 is\n\
                 \x20       nothing to fall back to at all, and the key itself reaches the screen.\n\
                 \x20       Fix: astra-plugin locale add en",
                found.len(),
                found.join(", ")
            ),
        );
    }
}

/// The closest declared code to a misspelling, for the "did you mean" line.
///
/// Deliberately crude: a prefix match on the first two characters. `zh-CN` →
/// `zh`, `pt_BR` → `pt`, `EN` → `en`. Anything cleverer would start guessing.
fn did_you_mean(code: &str) -> Option<&'static str> {
    let lower = code.to_ascii_lowercase();
    LOCALE_CODES.iter().copied().find(|c| lower.starts_with(c))
}

/// **E2 / E3 / E15 / N4 / N14 — parity, over FAMILIES rather than raw keys.**
fn check_parity(set: &LocaleSet, f: &mut Findings) {
    let Some(en) = set.get("en").filter(|x| x.error.is_none()) else {
        return;
    };
    let families = plural_families(set);
    let en_ids = family_ids(en, &families);

    for file in set.real() {
        if file.code == "en" {
            continue;
        }
        let ids = family_ids(file, &families);

        let missing: Vec<&String> = en_ids.difference(&ids).collect();
        if !missing.is_empty() {
            f.err(
                "E2",
                format!(
                    "locales/{}.json is missing {} key(s) that locales/en.json declares: {}.\n\
                     \x20       Every language must carry every key. Astra's RELEASED daemon \
                     falls back per\n\
                     \x20       FILE, not per key — it picks one whole locale map and then \
                     resolves — so a\n\
                     \x20       key missing here is not filled in from English; the user reads \
                     the key.\n\
                     \x20       Fix: astra-plugin locale add {} — it seeds the missing keys \
                     from en.json and\n\
                     \x20            keeps every value you have translated. It also rewrites \
                     the file, so it\n\
                     \x20            NAMES anything en.json can no longer seed; if you renamed \
                     an English key,\n\
                     \x20            move that translation onto the new name before you run \
                     it.",
                    file.code,
                    missing.len(),
                    preview(&missing),
                    file.code
                ),
            );
        }

        let extra: Vec<&String> = ids.difference(&en_ids).collect();
        if !extra.is_empty() {
            f.err(
                "E3",
                format!(
                    "locales/{}.json declares {} key(s) that locales/en.json does not: {}.\n\
                     \x20       en.json is the base, so a key that is not in it can never be \
                     reached from\n\
                     \x20       any other language and is dead weight in every bundle. Add it to \
                     en.json,\n\
                     \x20       or delete it here.",
                    file.code,
                    extra.len(),
                    preview(&extra)
                ),
            );
        }

        // N4 — the file exists and is still English. Measured through
        // `english_for`, so the plural rows `locale add ru` writes and English
        // cannot carry are counted as seeded like every other row; counting
        // them against a missing `en.json` key made a four-row Russian family
        // report two seeded values and hid the other two.
        let untranslated: Vec<&String> = file
            .keys
            .iter()
            .filter(|(k, v)| english_for(en, k, &families).is_some_and(|e| e == *v) && !v.is_empty())
            .map(|(k, _)| k)
            .collect();
        if !untranslated.is_empty() {
            f.note(
                "N4",
                format!(
                    "locales/{}.json has {} value(s) byte-identical to English: {}. They are \
                     seeded, not translated.",
                    file.code,
                    untranslated.len(),
                    preview(&untranslated)
                ),
            );
        }
    }

    // E15 — the sole rule policing WHICH categories a code carries, in both
    // directions. Parity above is over families and has no exception in it,
    // because an exception inside a parity check is where parity checks stop
    // being checks.
    for base in &families {
        for file in set.real() {
            let present: BTreeSet<&str> = file
                .keys
                .keys()
                .filter_map(|k| match split_category(k) {
                    (b, Some(cat)) if b == base => Some(cat),
                    _ => None,
                })
                .collect();
            if present.is_empty() {
                continue; // E2/E3 own this case.
            }
            let want: BTreeSet<&str> = plural::categories(&file.code).iter().copied().collect();
            if present != want {
                f.err(
                    "E15",
                    format!(
                        "locales/{}.json's plural family \"{base}\" carries {:?} and `{}` needs \
                         exactly {:?} (spec/i18n.yaml).\n\
                         \x20       A count that lands in a category with no row falls back to \
                         \"{base}.other\",\n\
                         \x20       so the wrong noun form reaches a user in a language nobody \
                         here can\n\
                         \x20       proof-read.\n\
                         \x20       Fix: astra-plugin locale add {} rewrites exactly these \
                         rows. A row it has to\n\
                         \x20            DELETE is named, and one somebody translated needs \
                         --prune — a category\n\
                         \x20            this language never selects is text no user can ever \
                         reach.",
                        file.code,
                        present.iter().copied().collect::<Vec<_>>(),
                        file.code,
                        want.iter().copied().collect::<Vec<_>>(),
                        file.code,
                    ),
                );
            }
        }
    }

    // N14 — one lone CLDR-suffixed key. Not a family by the two-category rule
    // above (deliberately: that rule refuses to invent a plural out of one
    // key), so E15 never looks at it and nothing else would ever mention it.
    let mut lone: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for file in set.real() {
        for key in file.keys.keys() {
            if let (base, Some(cat)) = split_category(key)
                && !families.contains(base)
            {
                lone.entry(base).or_default().push(cat);
            }
        }
    }
    for (base, cats) in lone {
        let mut cats = cats;
        cats.sort_unstable();
        cats.dedup();
        f.note(
            "N14",
            format!(
                "\"{base}\" has one CLDR plural suffix ({}) and no siblings, so it is treated as \
                 an ordinary key rather than a plural family. If you meant `tn(\"{base}\", n)`, \
                 add the rest of the rows with `astra-plugin locale add <code>`.",
                cats.join(", ")
            ),
        );
    }
}

/// **E8 / E9 / E10 — the two reserved keys.** Coupling C18.
fn check_listing_keys(m: &PluginManifest, set: &LocaleSet, f: &mut Findings) {
    let Some(en) = set.get("en").filter(|x| x.error.is_none()) else {
        return;
    };

    for file in set.real() {
        for key in file.keys.keys() {
            if key.starts_with("listing.") && !RESERVED_LISTING_KEYS.contains(&key.as_str()) {
                f.err(
                    "E9",
                    format!(
                        "locales/{}.json declares \"{key}\". The `listing.` namespace is reserved \
                         and closed: the ingest bot reads exactly {} out of a bundle and nothing \
                         else. A key under that prefix is one an author expects to appear on the \
                         store card and which never will. Use your own prefix.",
                        file.code,
                        RESERVED_LISTING_KEYS.join(" and ")
                    ),
                );
            }
        }
    }

    for key in RESERVED_LISTING_KEYS {
        if !en.keys.contains_key(*key) {
            f.err(
                "E10",
                format!(
                    "locales/en.json has no \"{key}\". Once a plugin ships locales/, the store \
                     card's English text lives there too — the ingest bot reads {} out of \
                     en.json, and a locale block missing half of it is dropped whole rather \
                     than filled in.\n\
                     \x20       Fix: astra-plugin locale sync",
                    RESERVED_LISTING_KEYS.join(" and ")
                ),
            );
        }
    }

    for (key, manifest_value, field) in [
        ("listing.name", &m.plugin.name, "name"),
        ("listing.description", &m.plugin.description, "description"),
    ] {
        let Some(theirs) = en.keys.get(key) else { continue };
        if theirs != manifest_value {
            f.err(
                "E8",
                format!(
                    "locales/en.json's \"{key}\" does not match plugin.toml's {field}.\n\
                     \x20         plugin.toml:  {manifest_value:?}\n\
                     \x20         en.json:      {theirs:?}\n\
                     \x20       These are the same fact in two files because the manifest crate is \
                     byte-locked\n\
                     \x20       to Astra and cannot hold a locale table. That duplication is \
                     checked, not\n\
                     \x20       tolerated — the registry compares them again at ingest, after \
                     your tag.\n\
                     \x20       Fix: astra-plugin locale sync    (rewrites en.json from \
                     plugin.toml)"
                ),
            );
        }
    }

    // E14, per locale, on the resolved card text.
    for file in set.real() {
        for (key, limit_name) in
            [("listing.name", "max_name_length"), ("listing.description", "max_description_length")]
        {
            let Some(v) = file.keys.get(key) else { continue };
            if v.chars().count() > cap(limit_name) {
                f.err(
                    "E14",
                    format!(
                        "locales/{}.json's \"{key}\" is {} characters; the registry caps it at {} \
                         (spec/listing-limits.yaml). The whole locale block is refused at ingest, \
                         so this language's card falls back to English with no explanation.",
                        file.code,
                        v.chars().count(),
                        cap(limit_name)
                    ),
                );
            }
        }
    }
}

/// **N2 / N3 — the lock.** Notes on the hot path, errors at the artifact.
fn check_lock(set: &LocaleSet, gate: Gate, f: &mut Findings) {
    let translated = set.real().filter(|x| x.code != "en").count();

    if let Some(e) = &set.lock_error {
        f.err("N2", format!("{LOCK_FILE} does not parse: {e}. Fix: astra-plugin locale sync"));
        return;
    }

    if translated > 0 && set.lock.is_none() {
        let msg = format!(
            "{translated} translated locale file(s) and no {LOCK_FILE}. Without it nothing can \
             tell a fresh translation from one that describes English you have since rewritten, \
             and a reader gets a confidently wrong sentence with nothing to tell them.\n\
             \x20       Fix: astra-plugin locale sync"
        );
        if gate == Gate::Build {
            f.err("N2", msg);
        } else {
            f.note("N2", msg);
        }
    }

    if let Some(lock) = &set.lock
        && lock.schema != LOCK_SCHEMA
        && !lock.schema.is_empty()
    {
        f.note(
            "N2",
            format!("{LOCK_FILE} declares schema {:?}; this CLI writes {LOCK_SCHEMA}.", lock.schema),
        );
    }

    let drift = lock_drift(set);

    for (code, keys) in drift.stale {
        let msg = format!(
            "locales/{code}.json: {} stale translation(s) ({}).\n\
             \x20       The English these were translated from has changed since. A published \
             bundle may\n\
             \x20       not ship a translation that describes older English — a reader gets a \
             sentence\n\
             \x20       that is confidently wrong and nothing ever corrects it.\n\
             \x20       Fix: retranslate and run `astra-plugin locale sync`, or accept them as \
             still\n\
             \x20            correct with `astra-plugin locale sync --accept {code}`.",
            keys.len(),
            preview(&keys.iter().collect::<Vec<_>>())
        );
        if gate == Gate::Build {
            f.err("N3", msg);
        } else {
            f.note("N3", msg);
        }
    }

    // N15 — the same lock entry going out of date, on a value nobody ever
    // translated. It is a NOTE at BOTH gates, deliberately, and the reason is
    // the harm and not the mechanism: an N3 key puts a confidently wrong
    // sentence in front of a reader in their own language, which is why `build`
    // refuses it. An N15 key puts English in front of a reader who was always
    // going to get English — out-of-date English, which is worth saying and is
    // not worth refusing somebody's release over a file they never claimed to
    // have translated.
    for (code, keys) in drift.seeded {
        f.note(
            "N15",
            format!(
                "locales/{code}.json: {} value(s) that were never translated, and the English \
                 they were seeded from has changed ({}).\n\
                 \x20       Each is byte-identical to the English {LOCK_FILE} recorded for it, so \
                 there is no\n\
                 \x20       translation here to have gone wrong — it is an older en.json sitting \
                 in a {code}\n\
                 \x20       file. A {code} reader gets English either way; this says out loud \
                 that it is\n\
                 \x20       English you have since rewritten.\n\
                 \x20       Fix: translate them, or copy today's en.json value in. `astra-plugin \
                 locale sync\n\
                 \x20            --accept {code}` records them as correct as they stand, which is \
                 a promise\n\
                 \x20            that this English is the right {code} text.",
                keys.len(),
                preview(&keys.iter().collect::<Vec<_>>())
            ),
        );
    }
}

/// A count with at most three examples, never an enumeration.
///
/// Nine locale files each missing four thousand keys would otherwise render
/// megabytes at somebody who wanted a verdict.
fn preview<S: AsRef<str>>(items: &[S]) -> String {
    let shown: Vec<&str> = items.iter().take(3).map(|s| s.as_ref()).collect();
    if items.len() <= 3 {
        shown.join(", ")
    } else {
        format!("{}, and {} more", shown.join(", "), items.len() - 3)
    }
}

// ── `astra-plugin locale` ────────────────────────────────────────────────────

pub enum Sub {
    Ls,
    Add { code: String, prune: bool },
    Sync { accept: Vec<String> },
    Check,
    Extract,
    Render { lang: String },
    Pseudo,
}

pub fn run(path: &str, sub: Sub) -> Result<Verdict> {
    let dir = Path::new(path);
    let manifest_path = dir.join("plugin.toml");
    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }
    let content = fs::read_to_string(&manifest_path).context("Failed to read plugin.toml")?;
    let manifest: PluginManifest =
        toml::from_str(&content).context("Failed to parse plugin.toml")?;

    match sub {
        Sub::Ls => ls(dir, &manifest),
        Sub::Add { code, prune } => add(dir, &manifest, &code, prune),
        Sub::Sync { accept } => sync(dir, &manifest, &accept),
        Sub::Check => check(dir, &manifest),
        Sub::Extract => extract(dir, &manifest),
        Sub::Render { lang } => render(dir, &manifest, &lang),
        Sub::Pseudo => pseudo(dir, &manifest),
    }
}

/// The vocabulary, what this plugin ships, key counts, deltas.
fn ls(dir: &Path, _m: &PluginManifest) -> Result<Verdict> {
    let set = LocaleSet::read(dir);
    // Printed FIRST and unconditionally, so an empty result reads as empty
    // rather than as a pass.
    hprintln!(
        "spec/locales.yaml declares {} codes; this plugin ships {}.",
        LOCALE_CODES.len(),
        set.files.len()
    );
    if !set.present {
        hprintln!("  no locales/ directory. `astra-plugin locale add en` starts one.");
    }

    let families = plural_families(&set);
    let en_ids = set.get("en").map(|e| family_ids(e, &families)).unwrap_or_default();
    let LockDrift { stale, seeded } = lock_drift(&set);

    let mut rows = Vec::new();
    for file in &set.files {
        if let Some(why) = &file.error {
            hprintln!("  {:<6} UNREADABLE — {why}", file.code);
            rows.push(json!({ "code": file.code, "error": why }));
            continue;
        }
        let ids = family_ids(file, &families);
        let missing = en_ids.difference(&ids).count();
        let extra = ids.difference(&en_ids).count();
        let stale_here = stale.get(&file.code).map(Vec::len).unwrap_or(0);
        let seeded_here = seeded.get(&file.code).map(Vec::len).unwrap_or(0);
        hprintln!(
            "  {:<6} {:>4} key(s), {:>3} famil{}   missing {missing}, extra {extra}, stale \
             {stale_here}{}{}",
            file.code,
            file.keys.len(),
            ids.len(),
            if ids.len() == 1 { "y " } else { "ies" },
            // Appended only when it is not zero: this column is the one an
            // author reads for a verdict, and a permanent `, seeded-stale 0`
            // would be noise on every well-kept plugin.
            if seeded_here > 0 { format!(", seeded-stale {seeded_here}") } else { String::new() },
            if LOCALE_CODES.contains(&file.code.as_str()) {
                ""
            } else if file.code == PSEUDO_CODE {
                "   (pseudo-locale; build refuses it)"
            } else {
                "   (NOT a language Astra can be set to)"
            }
        );
        rows.push(json!({
            "code": file.code,
            "keys": file.keys.len(),
            "families": ids.len(),
            "missing": missing,
            "extra": extra,
            "stale": stale_here,
            "seeded_stale": seeded_here,
            "selectable": LOCALE_CODES.contains(&file.code.as_str()),
        }));
    }

    let untranslated: Vec<&&str> =
        LOCALE_CODES.iter().filter(|c| set.get(c).is_none()).collect();
    if !untranslated.is_empty() {
        hprintln!(
            "  not translated: {}",
            untranslated.iter().map(|c| **c).collect::<Vec<_>>().join(" ")
        );
    }

    crate::output::emit(
        "locale ls",
        &Verdict::Pass,
        json!({
            "declared": LOCALE_CODES,
            "shipped": set.codes(),
            "locales": rows,
        }),
    );
    Ok(Verdict::Pass)
}

/// One key `locale add` is about to delete out of a locale file.
struct Removal {
    key: String,
    /// The value is not one `en.json` could have seeded, so a person wrote it.
    translated: bool,
    why: RemovalReason,
}

enum RemovalReason {
    /// `en.json` declares neither this key nor a plural family of that name.
    NotDeclared,
    /// The family survives; this CATEGORY is one `code` can never select.
    WrongCategory(String),
}

/// What rewriting `<code>.json` from the base would delete.
///
/// The `translated` half is the load-bearing one, and it is deliberately
/// conservative in the direction that keeps text: a seed is by construction a
/// byte-for-byte copy of an English value, so a value that is still one of
/// `en.json`'s values is one this command wrote and may rewrite. Anything else
/// is treated as somebody's work — including the case where the English was
/// renamed AND retyped, where nothing on disk can prove it either way.
fn removals(
    existing: Option<&BTreeMap<String, String>>,
    out: &BTreeMap<String, String>,
    base: &BTreeMap<String, String>,
    families: &BTreeSet<String>,
    _code: &str,
) -> Vec<Removal> {
    let english: BTreeSet<&str> = base.values().map(String::as_str).collect();
    let surviving: BTreeSet<String> = out.keys().map(|k| family_id(k, families)).collect();
    let mut removed = Vec::new();
    for (key, value) in existing.into_iter().flatten() {
        if out.contains_key(key) {
            continue;
        }
        let why = match split_category(key) {
            (fam, Some(cat)) if families.contains(fam) && surviving.contains(fam) => {
                RemovalReason::WrongCategory(cat.to_string())
            }
            _ => RemovalReason::NotDeclared,
        };
        removed.push(Removal {
            key: key.clone(),
            translated: !english.contains(value.as_str()),
            why,
        });
    }
    removed
}

/// One line per removal, capped — `key — why`.
///
/// Capped at six because this is read by somebody deciding whether to type
/// `--prune`, and a hundred lines is an enumeration wearing a report's clothes.
/// The count is always exact even when the list is not.
fn removal_lines(removed: &[&Removal], code: &str) -> Vec<String> {
    const SHOWN: usize = 6;
    let mut lines: Vec<String> = removed
        .iter()
        .take(SHOWN)
        .map(|r| {
            let why = match &r.why {
                RemovalReason::NotDeclared => {
                    "locales/en.json does not declare it".to_string()
                }
                RemovalReason::WrongCategory(cat) => format!(
                    "`{code}` never selects the `{cat}` plural category (spec/i18n.yaml)"
                ),
            };
            format!("{} — {why}", r.key)
        })
        .collect();
    if removed.len() > SHOWN {
        lines.push(format!("…and {} more", removed.len() - SHOWN));
    }
    lines
}

/// The English base for `locale add en` on a plugin that has no `en.json`.
///
/// Returns the seed map, and which file each borrowed value came from.
///
/// The values are **not English** and this cannot make them so — they are the
/// only text that exists for those keys, and the alternative (an empty string,
/// or the key itself) throws away the one thing the author needs in order to
/// write the English. So they are copied, and `add` says per file that it did.
fn english_base_from_union(
    m: &PluginManifest,
    set: &LocaleSet,
) -> (BTreeMap<String, String>, Vec<(String, String)>) {
    let mut base = BTreeMap::new();
    base.insert("listing.name".to_string(), m.plugin.name.clone());
    base.insert("listing.description".to_string(), m.plugin.description.clone());
    let mut borrowed = Vec::new();
    for file in set.real() {
        for (key, value) in &file.keys {
            if base.contains_key(key) {
                continue;
            }
            base.insert(key.clone(), value.clone());
            borrowed.push((key.clone(), file.code.clone()));
        }
    }
    (base, borrowed)
}

/// Seed a locale from `en.json`, with the plural rows that code needs.
///
/// # What it removes, and why that has to be said out loud
///
/// The output is built from the English base, so a key the target file holds
/// and the base does not is **deleted** — `write_locale` overwrites. That
/// pruning is wanted: `locale add ja` correctly strips a `few` row Japanese can
/// never select, and E3 exists to refuse a key `en.json` does not declare.
///
/// It is also how an ordinary rename ate four Russian plurals in silence. This
/// command cannot tell a correction from a destruction — the two are the same
/// operation on the same bytes, and only the author knows which one they meant.
/// So every removal is named, and one whose value is not still the English seed
/// is refused until `--prune` says so.
fn add(dir: &Path, m: &PluginManifest, code: &str, prune: bool) -> Result<Verdict> {
    if code != PSEUDO_CODE && !LOCALE_CODES.contains(&code) {
        let hint = did_you_mean(code)
            .map(|c| format!("\n       Did you mean `astra-plugin locale add {c}`?"))
            .unwrap_or_default();
        anyhow::bail!(
            "'{code}' is not a language Astra can be set to.\n\
             \x20      Astra's languages are: {} (spec/locales.yaml).\n\
             \x20      Language matching is exact string equality and no region tags exist \
             anywhere in\n\
             \x20      this system, so locales/{code}.json would be packed into your bundle, \
             digested,\n\
             \x20      signed, installed, and read by nothing.{hint}",
            LOCALE_CODES.join(" ")
        );
    }

    let locales_dir = dir.join("locales");
    fs::create_dir_all(&locales_dir).context("could not create locales/")?;
    let target = locales_dir.join(format!("{code}.json"));

    let set = LocaleSet::read(dir);

    // The English base every other locale is seeded from.
    //
    // `locale add en` on a plugin with no en.json BUILDS it instead of reading
    // it: the two reserved keys from plugin.toml, and every other key from the
    // union of the locales that survived. Seeding the two alone is what left
    // E1's own printed fix standing on E3 and E15 — one error told the author
    // to run this command, and running it produced two more, for every key the
    // languages they already had were carrying.
    let (base, borrowed) = match set.get("en").filter(|x| x.error.is_none()) {
        Some(en) => (en.keys.clone(), Vec::new()),
        None if code == "en" => english_base_from_union(m, &set),
        None => anyhow::bail!(
            "locales/en.json is missing or unreadable, and every other locale is seeded from it. \
             Run `astra-plugin locale add en` first."
        ),
    };

    let existing = set.get(code).filter(|x| x.error.is_none()).map(|x| x.keys.clone());
    let families = plural_families(&set);
    let want: Vec<&str> = plural::categories(code).to_vec();

    let mut out: BTreeMap<String, String> = BTreeMap::new();
    let mut seeded = 0usize;
    let mut plural_rows: Vec<String> = Vec::new();

    for (key, english) in &base {
        match split_category(key) {
            (family, Some(_)) if families.contains(family) => {
                // One family, rewritten into exactly the categories this code
                // needs — which is what E15 will hold it to.
                for cat in &want {
                    let k = format!("{family}.{cat}");
                    if out.contains_key(&k) {
                        continue;
                    }
                    let kept = existing.as_ref().and_then(|e| e.get(&k)).cloned();
                    let is_new = kept.is_none();
                    let value = kept.unwrap_or_else(|| {
                        base.get(&k)
                            .or_else(|| base.get(&format!("{family}.other")))
                            .cloned()
                            .unwrap_or_else(|| english.clone())
                    });
                    if is_new && !base.contains_key(&k) {
                        plural_rows.push(k.clone());
                    }
                    if is_new {
                        seeded += 1;
                    }
                    out.insert(k, value);
                }
            }
            _ => {
                let kept = existing.as_ref().and_then(|e| e.get(key)).cloned();
                if kept.is_none() {
                    seeded += 1;
                }
                out.insert(key.clone(), kept.unwrap_or_else(|| english.clone()));
            }
        }
    }

    // ── what this rewrite would DELETE ──
    //
    // Everything above builds `out` from the base; `write_locale` overwrites.
    // So a key the target file has and `out` does not is gone, and until this
    // block existed it was gone without a word — `4 key(s) added, 2 kept` was
    // printed over four deleted Russian sentences.
    let removed = removals(existing.as_ref(), &out, &base, &families, code);
    let destructive: Vec<&Removal> = removed.iter().filter(|r| r.translated).collect();
    if !destructive.is_empty() && !prune {
        anyhow::bail!(
            "locales/{code}.json holds {} translated value(s) that locales/en.json cannot seed, \
             and this\n\
             \x20      command rewrites the file from en.json — so they would be deleted:\n\
             \x20        {}\n\
             \x20      Nothing here can tell a rename from a deletion. A translation is the one \
             thing in\n\
             \x20      this directory that cannot be regenerated, so it is not deleted on a \
             guess:\n\
             \x20        * want the text? move it onto a key locales/en.json declares first; or\n\
             \x20        * meant it? astra-plugin locale add {code} --prune  (deletes them, and \
             names each one)",
            destructive.len(),
            removal_lines(&destructive, code).join("\n\x20        "),
        );
    }

    let existed = target.exists();
    write_locale(&target, &out)?;

    if existed {
        hprintln!(
            "Updated locales/{code}.json — {seeded} key(s) added, {} kept{}.",
            out.len() - seeded,
            if removed.is_empty() {
                String::new()
            } else {
                format!(", {} REMOVED", removed.len())
            }
        );
    } else if code == "en" {
        // Not "seeded from en.json, values still English": this IS en.json, and
        // the values that came out of another locale are in that locale.
        hprintln!(
            "Created locales/en.json — {} key(s): the two the store card needs, from \
             plugin.toml, and\n\
             \x20 every key your other locales already carry.",
            out.len()
        );
    } else {
        hprintln!(
            "Created locales/{code}.json — {} key(s) seeded from locales/en.json, values still \
             English.",
            out.len()
        );
    }
    for line in removal_lines(&removed.iter().collect::<Vec<_>>(), code) {
        hprintln!("  REMOVED  {line}");
    }
    if !borrowed.is_empty() {
        // Said every time, because these values are NOT English and nothing
        // downstream can tell: E11 reads plugin.toml, not this file, and every
        // untranslated language falls back to whatever is written here.
        let mut by_code: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for (key, from) in &borrowed {
            by_code.entry(from.as_str()).or_default().push(key.as_str());
        }
        for (from, keys) in by_code {
            hprintln!(
                "  {} value(s) were copied from locales/{from}.json and are NOT English: {}.",
                keys.len(),
                preview(&keys)
            );
        }
        hprintln!(
            "  Rewrite them in English — en.json is what every language you have not \
             translated shows.\n\
             \x20 Until you do, `astra-plugin check` reports them as untranslated in the file \
             they came from."
        );
    }
    if !plural_rows.is_empty() {
        hprintln!(
            "  Added the plural rows {code} needs: {}.",
            preview(&plural_rows.iter().collect::<Vec<_>>())
        );
    }
    if code != "en" {
        let written = rewrite_lock(dir, &LocaleSet::read(dir), &[])?;
        hprintln!("  {written}");
        hprintln!("Translate the values in place; leave the keys alone. Then `astra-plugin locale sync`.");
    }
    Ok(Verdict::Pass)
}

/// The two reserved keys beside the manifest values they are a copy of.
fn reserved_pairs<'a>(name: &'a str, description: &'a str) -> [(&'static str, &'a str); 2] {
    [("listing.name", name), ("listing.description", description)]
}

/// Which reserved keys `locales/en.json` disagrees with `plugin.toml` about.
///
/// E8's input, and E10's — a missing key disagrees too. Exposed so that
/// `check --fix` can ask before it writes anything: a fixer that rewrites the
/// lock on a plugin that needed nothing is a fixer that reports "nothing was
/// fixable" over a modified file.
pub fn listing_keys_out_of_date(dir: &Path, name: &str, description: &str) -> Vec<&'static str> {
    let set = LocaleSet::read(dir);
    let Some(en) = set.get("en").filter(|x| x.error.is_none()) else {
        return Vec::new();
    };
    reserved_pairs(name, description)
        .into_iter()
        .filter(|(key, want)| en.keys.get(*key).map(String::as_str) != Some(*want))
        .map(|(key, _)| key)
        .collect()
}

/// `locale sync`'s body, without the printing.
///
/// `check --fix` calls THIS and not a copy of it. E8/E10 are the only purely
/// mechanical errors in this module — one fact in two files, one of which is by
/// definition the copy — and they are the ones that fire on the first edit
/// every author makes.
///
/// Returns which reserved keys were rewritten, and the lock's own report line.
pub fn sync_from_manifest(
    dir: &Path,
    name: &str,
    description: &str,
    accept: &[String],
) -> Result<(Vec<&'static str>, String)> {
    let changed = listing_keys_out_of_date(dir, name, description);
    if !changed.is_empty() {
        let set = LocaleSet::read(dir);
        if let Some(en) = set.get("en").filter(|x| x.error.is_none()) {
            let mut keys = en.keys.clone();
            for (key, want) in reserved_pairs(name, description) {
                keys.insert(key.to_string(), want.to_string());
            }
            write_locale(&en.path, &keys)?;
        }
    }
    let set = LocaleSet::read(dir);
    let written = rewrite_lock(dir, &set, accept)?;
    Ok((changed, written))
}

/// Rewrite `locales.lock.json`, and refuse to re-stamp a stale entry.
fn sync(dir: &Path, m: &PluginManifest, accept: &[String]) -> Result<Verdict> {
    // The two reserved keys are by definition a copy of plugin.toml, so there
    // is nothing to lose by rewriting them — and E8 would otherwise fire on the
    // very first edit every author makes.
    let (changed, written) =
        sync_from_manifest(dir, &m.plugin.name, &m.plugin.description, accept)?;
    if !changed.is_empty() {
        hprintln!("Rewrote locales/en.json's {} from plugin.toml.", changed.join(" and "));
    }
    hprintln!("{written}");
    crate::output::emit("locale sync", &Verdict::Pass, json!({ "path": dir.display().to_string() }));
    Ok(Verdict::Pass)
}

/// Derive the lock from what is on disk. Returns the line to print.
///
/// `sync` DERIVES state and never asks the author to assert it. **Every key in
/// every non-English locale gets an entry**, including one whose value is still
/// byte-identical to English: entry matches today's English → fresh (or seeded,
/// which is the same entry and a different report); entry matches the value
/// itself → the seed's English moved and nothing was ever translated; entry
/// matches neither → stale; no entry at all → a key the author added by hand,
/// stamped with today's digest.
///
/// **Recording the seeds is the whole point.** A value equal to English used to
/// get no entry, so the next `sync` after an English edit saw "differs from
/// English, no entry", read it as *newly translated*, and stamped it with the
/// digest of the **new** English. The staleness gate could then never fire for
/// that key on either side of the release, and the registry published the
/// plugin's previous English text as its Russian and Japanese store card.
///
/// Re-stamping a stale or seeded entry takes an explicit `--accept`, which is
/// the author's word landing in a diff somebody can review.
fn rewrite_lock(dir: &Path, set: &LocaleSet, accept: &[String]) -> Result<String> {
    let Some(en) = set.get("en").filter(|x| x.error.is_none()) else {
        return Ok(format!("{LOCK_FILE} not written: locales/en.json is missing or unreadable."));
    };
    let families = plural_families(set);

    let accept_all: BTreeSet<&str> =
        accept.iter().filter(|a| !a.contains(':')).map(String::as_str).collect();
    let accept_one: BTreeSet<(&str, &str)> =
        accept.iter().filter_map(|a| a.split_once(':')).collect();

    let mut lock = Lock { schema: LOCK_SCHEMA.into(), source: "en".into(), ..Lock::default() };
    let mut fresh = 0usize;
    let mut newly = 0usize;
    let mut refused: Vec<String> = Vec::new();
    let mut seeded_stale: Vec<String> = Vec::new();
    let mut accepted: Vec<String> = Vec::new();
    let mut untranslated = 0usize;

    for file in set.real() {
        if file.code == "en" {
            continue;
        }
        let mut per = BTreeMap::new();
        for (key, theirs) in &file.keys {
            let Some(english) = english_for(en, key, &families) else { continue };
            let state = freshness(set.lock.as_ref(), &file.code, key, english, theirs);
            match state {
                // Seeded, and the seed is today's English. Stamped like every
                // other key: what is recorded is the English this value was
                // copied from, and a copy is exactly the thing an English edit
                // must be able to invalidate.
                Freshness::Untranslated => {
                    untranslated += 1;
                    per.insert(key.clone(), digest(english));
                }
                Freshness::Fresh => {
                    fresh += 1;
                    per.insert(key.clone(), digest(english));
                }
                Freshness::New => {
                    newly += 1;
                    per.insert(key.clone(), digest(english));
                }
                Freshness::Stale | Freshness::SeededStale => {
                    let ok = accept_all.contains(file.code.as_str())
                        || accept_one.contains(&(file.code.as_str(), key.as_str()));
                    if ok {
                        accepted.push(format!("{}:{key}", file.code));
                        per.insert(key.clone(), digest(english));
                    } else {
                        if state == Freshness::SeededStale {
                            seeded_stale.push(format!("{}:{key}", file.code));
                        } else {
                            refused.push(format!("{}:{key}", file.code));
                        }
                        // The OLD digest is kept, so the entry stays out of date
                        // and `build` keeps refusing (N3) or `check` keeps
                        // saying so (N15). A sync that quietly re-stamped would
                        // turn a caught problem into a silent one.
                        if let Some(old) =
                            set.lock.as_ref().and_then(|l| l.locales.get(&file.code)).and_then(
                                |m| m.get(key),
                            )
                        {
                            per.insert(key.clone(), old.clone());
                        }
                    }
                }
            }
        }
        if !per.is_empty() {
            lock.locales.insert(file.code.clone(), per);
        }
    }

    let path = dir.join(LOCK_FILE);
    let text = format!("{}\n", serde_json::to_string_pretty(&lock.to_json())?);
    fs::write(&path, text).with_context(|| format!("could not write {}", path.display()))?;

    for a in &accepted {
        hprintln!("  ACCEPTED as still correct: {a}");
    }
    for r in &refused {
        hprintln!(
            "  STALE, not re-stamped: {r} — retranslate it, or `astra-plugin locale sync \
             --accept {r}`"
        );
    }
    for s in &seeded_stale {
        hprintln!(
            "  NEVER TRANSLATED and the English moved: {s} — it is still the English it was \
             seeded from. Translate it, or `astra-plugin locale sync --accept {s}`"
        );
    }
    // The seeded count is appended only when it is not zero, so the ordinary
    // line stays the four numbers every author and every doc sample knows.
    let seeded_clause = if seeded_stale.is_empty() {
        String::new()
    } else {
        format!(", {} seeded against English that has since changed", seeded_stale.len())
    };
    Ok(format!(
        "{LOCK_FILE}: {fresh} fresh, {newly} newly translated, {untranslated} untranslated, {} \
         stale{seeded_clause}.",
        refused.len()
    ))
}

/// The L-rules alone, machine-readable.
fn check(dir: &Path, m: &PluginManifest) -> Result<Verdict> {
    let f = findings(dir, m, Gate::Check);
    for n in &f.notes {
        hprintln!("  NOTE: {n}");
    }
    for e in &f.errors {
        hprintln!("  ERROR: {e}");
    }
    let verdict = Verdict::of(f.errors.is_empty());
    if f.errors.is_empty() {
        let set = LocaleSet::read(dir);
        hprintln!(
            "  OK: {} locale file(s), {} note(s).",
            set.files.len(),
            f.notes.len()
        );
    } else {
        hprintln!("  FAILED: {} error(s)", f.errors.len());
    }
    crate::output::emit(
        "locale check",
        &verdict,
        json!({ "errors": f.errors, "notes": f.notes }),
    );
    if verdict == Verdict::Fail && !crate::output::json_mode() {
        return Err(Rejected::err("`astra-plugin locale check` found problems"));
    }
    Ok(verdict)
}

/// Which `$keys` in `plugin.toml` are absent from `en.json`.
fn extract(dir: &Path, m: &PluginManifest) -> Result<Verdict> {
    let set = LocaleSet::read(dir);
    let en = set.get("en").filter(|x| x.error.is_none());

    let mut refs: Vec<Reference> = Vec::new();
    if let Some(config) = m.config.as_ref()
        && !config.schema.trim().is_empty()
        && let Ok(schema) = serde_json::from_str::<Value>(&config.schema)
    {
        collect_schema_refs(&schema, "", false, &mut refs);
    }
    if let Some(ui) = m.ui.as_ref() {
        for c in &ui.contributions {
            if let Some(Marker::Key(key)) = marker(&c.label) {
                refs.push(Reference {
                    key: key.to_string(),
                    at: format!("[[ui.contributions]] {}", c.id),
                    label: true,
                });
            }
        }
    }

    let missing: Vec<&Reference> =
        refs.iter().filter(|r| !en.is_some_and(|e| e.keys.contains_key(&r.key))).collect();

    hprintln!(
        "plugin.toml references {} key(s); locales/en.json defines {} of them.",
        refs.len(),
        refs.len() - missing.len()
    );
    for r in &missing {
        hprintln!(
            "  MISSING  {:<40} {}{}",
            r.key,
            r.at,
            if looks_like_key(&r.key) { "" } else { "   (not key-shaped — probably a literal)" }
        );
    }
    // The heading is printed only when something goes under it. `Add them to
    // locales/en.json:` over nothing at all is what an author sees when the
    // only miss is `$HOME/notes` — a heading promising a list, followed by the
    // end of the output.
    let addable: Vec<&&Reference> = missing.iter().filter(|r| looks_like_key(&r.key)).collect();
    if !addable.is_empty() {
        hprintln!();
        hprintln!("Add them to locales/en.json:");
        for r in &addable {
            hprintln!("  \"{}\": \"\",", r.key);
        }
    } else if !missing.is_empty() {
        hprintln!();
        hprintln!(
            "Nothing to add: {}, so {} a value that begins with a dollar rather than a\n\
             \x20 reference. `$$` is the escape that keeps one literal for good.",
            if missing.len() == 1 {
                "that one is not key-shaped"
            } else {
                "none of these is key-shaped"
            },
            if missing.len() == 1 { "it is" } else { "each is" }
        );
    }
    crate::output::emit(
        "locale extract",
        &Verdict::Pass,
        json!({
            "referenced": refs.iter().map(|r| &r.key).collect::<Vec<_>>(),
            "missing": missing.iter().map(|r| &r.key).collect::<Vec<_>>(),
        }),
    );
    Ok(Verdict::Pass)
}

/// Walk `[config] schema` locally and print every string.
///
/// This exists because `locale pseudo` structurally CANNOT reach the declared
/// plane: `qps` is not in `SUPPORTED_LANGUAGES`, `Settings::validate` refuses
/// it, so `get_config_schema(id, "qps")` can never be called. The pseudo-locale
/// finds runtime strings an author forgot to externalise and is blind to config
/// titles — which is where authors forget most. This gives the CLI what the
/// daemon cannot: a local walk showing a hardcoded literal sitting in a label
/// position, with no daemon and no round trip.
fn render(dir: &Path, m: &PluginManifest, lang: &str) -> Result<Verdict> {
    // `--lang klingon` used to print "as a klingon user reads it" and exit 0,
    // while `locale add klingon` refused with five lines. One of the two is
    // teaching a spelling, and it is not the one that writes a file.
    if lang != PSEUDO_CODE && !LOCALE_CODES.contains(&lang) {
        anyhow::bail!(
            "'{lang}' is not a language Astra can be set to.\n\
             \x20      Astra's languages are: {} (spec/locales.yaml), plus `{PSEUDO_CODE}` for \
             the pseudo-locale.\n\
             \x20      This flag names the language a user's Astra is SET to, and matching is \
             exact string\n\
             \x20      equality — so rendering '{lang}' would be a screen no user can ever \
             see.{}",
            LOCALE_CODES.join(" "),
            did_you_mean(lang)
                .map(|c| format!("\n\x20      Did you mean `--lang {c}`?"))
                .unwrap_or_default()
        );
    }
    let set = LocaleSet::read(dir);
    let Some(config) = m.config.as_ref().filter(|c| !c.schema.trim().is_empty()) else {
        hprintln!("This plugin declares no [config] schema, so there is nothing to render.");
        return Ok(Verdict::Pass);
    };
    let schema: Value =
        serde_json::from_str(&config.schema).context("[config] schema is not valid JSON")?;

    let lookup = |key: &str| -> Option<&String> {
        set.get(lang)
            .filter(|f| f.error.is_none())
            .and_then(|f| f.keys.get(key))
            .or_else(|| set.get("en").filter(|f| f.error.is_none()).and_then(|f| f.keys.get(key)))
    };

    let mut refs: Vec<Reference> = Vec::new();
    collect_schema_refs(&schema, "", false, &mut refs);
    let mut literals: Vec<(String, String)> = Vec::new();
    collect_literals(&schema, "", false, &mut literals);

    hprintln!("[config] schema as a {lang} user reads it:");
    for r in &refs {
        match lookup(&r.key) {
            Some(v) => hprintln!("  $  {:<38} {:?}", r.at, v),
            None if looks_like_key(&r.key) => {
                hprintln!("  !  {:<38} ${} -> the bare key reaches the screen", r.at, r.key)
            }
            None => hprintln!("  =  {:<38} ${} (literal; nothing resolves it)", r.at, r.key),
        }
    }
    for (at, text) in &literals {
        hprintln!("  =  {at:<38} {text:?}   <- HARDCODED, never translated");
    }
    hprintln!();
    hprintln!(
        "  {} reference(s), {} hardcoded literal(s) in label positions.",
        refs.len(),
        literals.len()
    );
    crate::output::emit(
        "locale render",
        &Verdict::Pass,
        json!({
            "language": lang,
            "references": refs.len(),
            "literals": literals.iter().map(|(a, t)| json!({"at": a, "text": t}))
                .collect::<Vec<_>>(),
        }),
    );
    Ok(Verdict::Pass)
}

/// Every string in a LABEL position that is not a `$` reference.
fn collect_literals(value: &Value, path: &str, label: bool, out: &mut Vec<(String, String)>) {
    match value {
        Value::String(s) => {
            if label && marker(s).is_none() && !s.is_empty() {
                out.push((path.to_string(), s.clone()));
            }
        }
        Value::Object(map) => {
            for (k, v) in map {
                let child = if path.is_empty() { k.clone() } else { format!("{path}.{k}") };
                collect_literals(v, &child, LABEL_KEYS.contains(&k.as_str()), out);
            }
        }
        Value::Array(items) => {
            for (i, v) in items.iter().enumerate() {
                collect_literals(v, &format!("{path}[{i}]"), label, out);
            }
        }
        _ => {}
    }
}

/// Write `locales/qps.json`.
fn pseudo(dir: &Path, _m: &PluginManifest) -> Result<Verdict> {
    let set = LocaleSet::read(dir);
    let Some(en) = set.get("en").filter(|x| x.error.is_none()) else {
        anyhow::bail!("locales/en.json is missing or unreadable — pseudo-localization seeds from it.");
    };
    let mut out = BTreeMap::new();
    for (key, value) in &en.keys {
        // Bracketed and padded: bracketed so an un-externalised string is
        // visible at a glance, padded because a translation is routinely 30%
        // longer than English and a layout that only fits English is the other
        // half of what this finds.
        out.insert(key.clone(), format!("⟦{value}{}⟧", "·".repeat(value.chars().count() / 3)));
    }
    let path = dir.join("locales").join(format!("{PSEUDO_CODE}.json"));
    write_locale(&path, &out)?;
    hprintln!("Wrote locales/{PSEUDO_CODE}.json — {} key(s).", out.len());
    hprintln!(
        "  Run the plugin with I18n set to `{PSEUDO_CODE}`. Anything still in plain English is a \
         string that never reached a locale file."
    );
    hprintln!(
        "  It CANNOT reach the declared plane: `{PSEUDO_CODE}` is not in SUPPORTED_LANGUAGES, so \
         the daemon can never be asked for a `{PSEUDO_CODE}` config schema. Use `astra-plugin \
         locale render` for that half."
    );
    hprintln!("  `astra-plugin build` refuses a bundle carrying it.");
    Ok(Verdict::Pass)
}

/// Write a locale file: pretty JSON, sorted keys, trailing newline.
fn write_locale(path: &Path, keys: &BTreeMap<String, String>) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).ok();
    }
    let mut map = Map::new();
    for (k, v) in keys {
        map.insert(k.clone(), Value::String(v.clone()));
    }
    let text = format!("{}\n", serde_json::to_string_pretty(&Value::Object(map))?);
    fs::write(path, text).with_context(|| format!("could not write {}", path.display()))
}

#[cfg(test)]
#[path = "locale_tests.rs"]
mod tests;
