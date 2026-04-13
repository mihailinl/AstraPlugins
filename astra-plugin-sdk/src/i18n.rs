//! Simple i18n helper for plugin localization.
//!
//! Plugins ship `locales/en.json`, `locales/ru.json`, etc. alongside `plugin.toml`.
//! Each file is a flat key-value JSON map:
//!
//! ```json
//! {
//!     "config.token.title": "API Token",
//!     "msg.hello": "Hello!"
//! }
//! ```
//!
//! # Usage
//!
//! ```rust,no_run
//! use astra_plugin_sdk::I18n;
//! use std::path::Path;
//!
//! let i18n = I18n::load(Path::new("locales"));
//! i18n.set_language("ru");
//! let text = i18n.t("msg.hello"); // returns Russian translation or falls back to English
//! ```

use std::collections::HashMap;
use std::path::Path;
use std::sync::RwLock;

/// Thread-safe translation store. Load locale files and resolve keys.
pub struct I18n {
    locales: HashMap<String, HashMap<String, String>>,
    language: RwLock<String>,
}

impl I18n {
    /// Load all locale files from a directory (e.g., `locales/`).
    /// Files should be named `en.json`, `ru.json`, etc.
    pub fn load(locales_dir: &Path) -> Self {
        let mut locales = HashMap::new();
        if let Ok(entries) = std::fs::read_dir(locales_dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.extension().map_or(false, |e| e == "json") {
                    if let Some(lang) = path.file_stem().and_then(|s| s.to_str()) {
                        if let Ok(content) = std::fs::read_to_string(&path) {
                            if let Ok(map) = serde_json::from_str::<HashMap<String, String>>(&content) {
                                locales.insert(lang.to_string(), map);
                            }
                        }
                    }
                }
            }
        }
        Self {
            locales,
            language: RwLock::new("en".to_string()),
        }
    }

    /// Create an empty I18n instance (no locale files loaded).
    pub fn empty() -> Self {
        Self {
            locales: HashMap::new(),
            language: RwLock::new("en".to_string()),
        }
    }

    /// Set the active language.
    pub fn set_language(&self, lang: &str) {
        if let Ok(mut l) = self.language.write() {
            *l = lang.to_string();
        }
    }

    /// Get the current active language.
    pub fn language(&self) -> String {
        self.language.read().map(|l| l.clone()).unwrap_or_else(|_| "en".to_string())
    }

    /// Get a translated string. Falls back to English, then to the key itself.
    pub fn t(&self, key: &str) -> String {
        let lang = self.language();
        self.locales
            .get(&lang)
            .and_then(|m| m.get(key))
            .or_else(|| self.locales.get("en").and_then(|m| m.get(key)))
            .cloned()
            .unwrap_or_else(|| key.to_string())
    }

    /// Get a translated string with format arguments replaced.
    /// Placeholders use `{0}`, `{1}`, etc.
    pub fn tf(&self, key: &str, args: &[&str]) -> String {
        let mut result = self.t(key);
        for (i, arg) in args.iter().enumerate() {
            result = result.replace(&format!("{{{}}}", i), arg);
        }
        result
    }

    /// Check if any locale files were loaded.
    pub fn has_locales(&self) -> bool {
        !self.locales.is_empty()
    }

    /// Get available language codes.
    pub fn available_languages(&self) -> Vec<String> {
        self.locales.keys().cloned().collect()
    }
}
