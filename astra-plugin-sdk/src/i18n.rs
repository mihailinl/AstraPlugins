// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! Plugin localization: `locales/<code>.json`, and the two planes it serves.
//!
//! A plugin ships one flat JSON file per language beside `plugin.toml`:
//!
//! ```json
//! {
//!     "config.token.title": "API Token",
//!     "msg.done.one": "Handled {n} item",
//!     "msg.done.other": "Handled {n} items"
//! }
//! ```
//!
//! # The two planes, which is the thing to get right
//!
//! **Runtime plane** — anything *this process* produces: chat text,
//! notifications, anything with a count in it. Resolve it here, at the moment
//! you produce it:
//!
//! ```rust,no_run
//! use astra_plugin_sdk::I18n;
//!
//! let i18n = I18n::discover();
//! i18n.set_language("ru");
//! let text = i18n.tn("msg.done", 3, &[("n", "3")]);
//! ```
//!
//! **Declared plane** — anything the *daemon* renders: config-field titles,
//! action and trigger labels, `[ui]` contribution labels. Emit a marker with
//! [`key`] and let the daemon resolve it per request, from the same `locales/`
//! directory, in whatever language the user has set *now*:
//!
//! ```rust
//! use astra_plugin_sdk::i18n::key;
//!
//! assert_eq!(key("action.roll.label"), "$action.roll.label");
//! ```
//!
//! Never [`t`](I18n::t) on the declared plane. The daemon caches a definition
//! unresolved and resolves it per request, so a label you resolved once is
//! frozen in whatever language won the race at startup — and a user who
//! switches language keeps reading it.
//!
//! # What this loader will and will not accept
//!
//! The daemon deserialises a locale file as `HashMap<String, String>` and
//! drops the **whole file** on any non-string value, silently, at install
//! time. This loader does the same, on purpose: an SDK that accepted a nested
//! object would let a plugin's own tests pass on a file the user's machine
//! never loads. Everything it could not use is reachable through
//! [`load_errors`](I18n::load_errors), which `astra-plugin test` prints.
//!
//! Nothing here is fatal. A plugin must start.
//!
//! The declared semantics are `spec/i18n.yaml`, the shared cases are
//! `testdata/i18n/vectors.json`, and all three SDKs are held to them by one
//! test each. This is coupling C17.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::RwLock;

use crate::plural;

/// Environment variable naming the plugin's own install directory.
///
/// A daemon that predates the variable leaves it unset, which is why
/// [`I18n::discover`] prefers it and then falls through to `./locales`. That
/// fallback resolves only because the daemon spawns a plugin with its working
/// directory set to the install directory — one `[entry] cwd` from stopping
/// being true — so the order is deliberate and is not an ordering to reverse:
/// the variable is the daemon naming the directory, the relative path is an
/// inference from how it was started.
pub const PLUGIN_DIR_ENV: &str = "ASTRA_PLUGIN_DIR";

/// Mark a string as a **declared-plane** locale key for the daemon to resolve.
///
/// Returns `format!("${k}")`. Use it in `action_types()`, `trigger_types()`
/// and `ui_contributions()` — anywhere the daemon renders the string rather
/// than this process.
///
/// A key that matches nothing is shown to the user exactly as it stands, so
/// every key passed here must exist in `locales/en.json`. `astra-plugin check`
/// is what tells you when one does not.
pub fn key(k: &str) -> String {
    format!("${k}")
}

/// Thread-safe translation store. Load locale files and resolve keys.
pub struct I18n {
    locales: HashMap<String, HashMap<String, String>>,
    language: RwLock<String>,
    errors: Vec<String>,
    source: Option<PathBuf>,
}

impl I18n {
    /// Load the plugin's `locales/` without depending on the process CWD.
    ///
    /// `$ASTRA_PLUGIN_DIR/locales` when that variable names a directory, else
    /// `./locales`. Two candidates, both owned by the plugin, and no third: a
    /// TypeScript plugin runs as `node dist/index.js` and a Python one as
    /// `python -m src.plugin`, so an executable-relative chain would have this
    /// SDK's siblings stat `/usr/bin/locales` — a directory the plugin does
    /// not own and has no business reading.
    ///
    /// Never fails. [`source_dir`](Self::source_dir) says where it looked and
    /// [`load_errors`](Self::load_errors) says what it could not use.
    pub fn discover() -> Self {
        let from_env = std::env::var_os(PLUGIN_DIR_ENV)
            .map(PathBuf::from)
            .map(|d| d.join("locales"))
            .filter(|d| d.is_dir());
        match from_env {
            Some(dir) => Self::load(&dir),
            None => Self::load(Path::new("locales")),
        }
    }

    /// Load every `*.json` in a directory as a locale named after its stem.
    ///
    /// The signature is unchanged from 0.7: this is the same call it always
    /// was, and the failures it always swallowed are now *reachable* through
    /// [`load_errors`](Self::load_errors) rather than fatal.
    pub fn load(locales_dir: &Path) -> Self {
        let mut locales = HashMap::new();
        let mut errors = Vec::new();

        match std::fs::read_dir(locales_dir) {
            Err(e) => errors.push(format!(
                "{}: not readable ({e}). No locale file was loaded, so every t() call \
                 returns its key.",
                locales_dir.display()
            )),
            Ok(entries) => {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if !path.extension().is_some_and(|e| e == "json") {
                        continue;
                    }
                    let Some(lang) = path.file_stem().and_then(|s| s.to_str()) else {
                        errors.push(format!("{}: the filename is not UTF-8", path.display()));
                        continue;
                    };
                    match std::fs::read_to_string(&path) {
                        Err(e) => errors.push(format!("{}: not readable ({e})", path.display())),
                        Ok(content) => match parse_locale(&content) {
                            Err(why) => errors.push(format!("{}: {why}", path.display())),
                            Ok(map) => {
                                if !plural::is_declared(lang) {
                                    // Not a refusal: the daemon loads this file
                                    // too, keys it by this stem, and never
                                    // selects it. Saying so is the only signal
                                    // the author will ever get — otherwise the
                                    // file is packed, digested, signed,
                                    // shipped, and read by nothing.
                                    errors.push(format!(
                                        "{}: `{lang}` is not a language Astra can be set to \
                                         (spec/locales.yaml). The file loaded, and nothing \
                                         will ever select it.",
                                        path.display()
                                    ));
                                }
                                locales.insert(lang.to_string(), map);
                            }
                        },
                    }
                }
            }
        }

        Self {
            locales,
            language: RwLock::new("en".to_string()),
            errors,
            source: Some(locales_dir.to_path_buf()),
        }
    }

    /// Create an empty I18n instance (no locale files loaded).
    pub fn empty() -> Self {
        Self {
            locales: HashMap::new(),
            language: RwLock::new("en".to_string()),
            errors: Vec::new(),
            source: None,
        }
    }

    /// Every file this loader could not use, and why.
    ///
    /// Never fatal — see the module docs. `astra-plugin test` prints these, so
    /// a misnamed or malformed locale file is a line an author reads before
    /// they ship rather than a settings page that is quietly English.
    pub fn load_errors(&self) -> &[String] {
        &self.errors
    }

    /// The directory [`load`](Self::load) or [`discover`](Self::discover) read,
    /// or `None` for [`empty`](Self::empty).
    pub fn source_dir(&self) -> Option<&Path> {
        self.source.as_deref()
    }

    /// Set the active language. The SDK calls this for you on
    /// `OnLanguageChanged` — see [`crate::PluginContext::i18n`].
    pub fn set_language(&self, lang: &str) {
        if let Ok(mut l) = self.language.write() {
            *l = lang.to_string();
        }
    }

    /// Get the current active language.
    pub fn language(&self) -> String {
        self.language
            .read()
            .map(|l| l.clone())
            .unwrap_or_else(|_| "en".to_string())
    }

    /// Look a key up, or `None`.
    ///
    /// Active language, then `en`, **per key** — not per file. An empty string
    /// is a translation and wins; an absent key is how a locale says it does
    /// not translate something.
    fn lookup(&self, key: &str) -> Option<&String> {
        let lang = self.language();
        self.locales
            .get(&lang)
            .and_then(|m| m.get(key))
            .or_else(|| self.locales.get("en").and_then(|m| m.get(key)))
    }

    /// Get a translated string. Falls back to English, then to the key itself.
    pub fn t(&self, key: &str) -> String {
        self.lookup(key).cloned().unwrap_or_else(|| key.to_string())
    }

    /// Is this key translated in the active language or in English?
    pub fn has(&self, key: &str) -> bool {
        self.lookup(key).is_some()
    }

    /// Get a translated string with positional arguments substituted.
    ///
    /// Placeholders are `{0}`, `{1}`, … and **every** occurrence is replaced.
    /// Russian and Ukrainian repeat a noun in two cases routinely, and the
    /// TypeScript SDK replacing only the first left the second on screen as
    /// the literal `{0}`.
    pub fn tf(&self, key: &str, args: &[&str]) -> String {
        let mut result = self.t(key);
        for (i, arg) in args.iter().enumerate() {
            result = result.replace(&format!("{{{i}}}"), arg);
        }
        result
    }

    /// Get a translated string with **named** arguments substituted.
    ///
    /// Placeholders are `{name}`. A name with no argument is left exactly as
    /// it stands — a half-formatted sentence is easier to see than a blank.
    pub fn ta(&self, key: &str, args: &[(&str, &str)]) -> String {
        substitute(self.t(key), args)
    }

    /// Get the plural form of `key` for `n`, with named arguments substituted.
    ///
    /// Resolves `<key>.<category>`, where the category comes from the active
    /// language's CLDR cardinal rules (`spec/i18n.yaml`, generated into
    /// [`crate::plural`]), then falls back to `<key>.other`, then `<key>`,
    /// then the key text.
    ///
    /// `{n}` is **not** substituted for you. Pass it: a count that formats
    /// itself is a count the author cannot localise.
    pub fn tn(&self, key: &str, n: i64, args: &[(&str, &str)]) -> String {
        let category = plural::category(&self.language(), n);
        let resolved = [format!("{key}.{category}"), format!("{key}.other"), key.to_string()]
            .iter()
            .find_map(|k| self.lookup(k))
            .cloned()
            .unwrap_or_else(|| key.to_string());
        substitute(resolved, args)
    }

    /// How many distinct keys begin with `prefix`, across the **union** of
    /// every loaded locale.
    ///
    /// Union, not the active language: a locale the author has not finished
    /// translating must not change a count the plugin's own logic depends on.
    pub fn count_prefixed(&self, prefix: &str) -> usize {
        let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::new();
        for map in self.locales.values() {
            for k in map.keys() {
                if k.starts_with(prefix) {
                    seen.insert(k.as_str());
                }
            }
        }
        seen.len()
    }

    /// Check if any locale files were loaded.
    pub fn has_locales(&self) -> bool {
        !self.locales.is_empty()
    }

    /// Get available language codes, sorted.
    ///
    /// Sorted because a `HashMap`'s iteration order is not stable between
    /// runs, and an unsorted list is not something a test can be written
    /// against.
    pub fn available_languages(&self) -> Vec<String> {
        let mut langs: Vec<String> = self.locales.keys().cloned().collect();
        langs.sort();
        langs
    }
}

fn substitute(mut text: String, args: &[(&str, &str)]) -> String {
    for (name, value) in args {
        text = text.replace(&format!("{{{name}}}"), value);
    }
    text
}

/// A locale file's bytes as a flat string map, or why it cannot be one.
///
/// Deliberately as strict as the daemon (`HashMap<String, String>`), with a
/// message the daemon has no way to produce.
fn parse_locale(content: &str) -> Result<HashMap<String, String>, String> {
    let value: serde_json::Value = serde_json::from_str(content)
        .map_err(|e| format!("not valid JSON ({e}). The daemon drops this file whole."))?;
    let serde_json::Value::Object(obj) = value else {
        return Err(format!(
            "the top level is {}, not an object. A locale file is a flat map of key to string.",
            kind_of(&value)
        ));
    };
    let mut map = HashMap::with_capacity(obj.len());
    for (k, v) in obj {
        match v {
            serde_json::Value::String(s) => {
                map.insert(k, s);
            }
            other => {
                return Err(format!(
                    "the value of `{k}` is {}, not a string. The daemon deserialises a locale \
                     file as a flat map of string to string and drops the WHOLE file on the \
                     first value that is not one — so on a user's machine every key in this \
                     file would render as itself while this plugin's own tests passed. \
                     Flatten it: \"{k}.title\": \"…\".",
                    kind_of(&other)
                ));
            }
        }
    }
    Ok(map)
}

fn kind_of(v: &serde_json::Value) -> &'static str {
    match v {
        serde_json::Value::Null => "null",
        serde_json::Value::Bool(_) => "a boolean",
        serde_json::Value::Number(_) => "a number",
        serde_json::Value::String(_) => "a string",
        serde_json::Value::Array(_) => "an array",
        serde_json::Value::Object(_) => "a nested object",
    }
}
