// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! AUTO-GENERATED — DO NOT EDIT.
//!
//! Produced by `tools/gen-i18n.mjs` from `spec/i18n.yaml`.
//! Regenerate with `node tools/gen-i18n.mjs` at the repo root.
//!
//! The CLDR cardinal rules `I18n::tn` selects with. They are generated because
//! the Russian and Ukrainian rules are four lines of modular arithmetic each,
//! and three hand-written copies is three chances to put the wrong noun form in
//! front of a user nobody in this repository can proof-read for. C17.
//!
//! `n` is the ABSOLUTE VALUE of the count, as CLDR defines the operand: `%` is
//! truncated in Rust and JavaScript and floored in Python, so a signed `n`
//! would sort the same count into different categories in different SDKs.
//!
//! Declared semantics, from the same file:
//! lookup_chain: <active language>, then en, then the key itself
//! fallback_granularity: per key
//! empty_value: a translation, not a miss
//! non_string_value: rejects the whole file, and load_errors() names it
//! load_failure: never fatal, always reachable through load_errors()
//! discover_chain: $ASTRA_PLUGIN_DIR/locales, else ./locales
//! tf_placeholder: {0} {1} … , every occurrence, missing index left intact
//! ta_placeholder: {name}, every occurrence, unknown name left intact
//! tn_key_chain: <key>.<category>, then <key>.other, then <key>, then the key
//! unknown_language_category: other
//! declared_plane_marker: key(k) returns "$" + k

/// SHA-256 of the `spec/i18n.yaml` these rules were generated from.
pub const SPEC_SHA256: &str = "a043021affbee3427f88dd094e317f712db9aa37e838f57ff2057e9c1b102c4d";

/// Every language's categories, in the order `spec/i18n.yaml` declares them.
///
/// The last entry is always `"other"`. A locale file is expected to carry
/// `<base>.<category>` for each of its language's entries and no others —
/// that is the parity rule `astra-plugin check` enforces.
pub const CATEGORIES: &[(&str, &[&str])] = &[
    ("en", &["one", "other"]),
    ("ru", &["one", "few", "many", "other"]),
    ("uk", &["one", "few", "many", "other"]),
    ("de", &["one", "other"]),
    ("fr", &["one", "other"]),
    ("es", &["one", "other"]),
    ("pt", &["one", "other"]),
    ("ja", &["other"]),
    ("zh", &["other"]),
    ("ko", &["other"]),
];

/// The categories `lang` uses, or `["other"]` for a language not declared.
pub fn categories(lang: &str) -> &'static [&'static str] {
    for (code, cats) in CATEGORIES {
        if *code == lang {
            return cats;
        }
    }
    &["other"]
}

/// Is `lang` one of the languages Astra can be set to?
///
/// The keys of [`CATEGORIES`] are generated from `spec/locales.yaml` and the
/// generator refuses to run unless the two files name exactly the same
/// languages — so this table doubles as the vocabulary, and `I18n` uses it to
/// say so when a plugin ships a `locales/zh-CN.json` that nothing can select.
pub fn is_declared(lang: &str) -> bool {
    CATEGORIES.iter().any(|(code, _)| *code == lang)
}

/// The CLDR cardinal category for `n` in `lang`.
///
/// `n` is taken as an absolute value: a count of -3 items is grammatically
/// three items. A language this table does not name gets `"other"`.
//
// `n % 10 == 0` rather than `n.is_multiple_of(10)`, which clippy's
// `manual_is_multiple_of` suggests: that method was stabilised in Rust 1.87
// and this crate's floor is 1.85 (edition 2024). A generated file that emits
// warnings is a generated file somebody eventually edits by hand, and raising
// an SDK's minimum toolchain to satisfy a lint is the wrong trade.
// `unknown_lints` first, because the lint does not exist on every clippy this
// crate is built with.
#[allow(unknown_lints, clippy::manual_is_multiple_of)]
pub fn category(lang: &str, n: i64) -> &'static str {
    let n = n.unsigned_abs();
    match lang {
        "en" => {
            if n == 1 {
                return "one";
            }
            "other"
        }
        "ru" => {
            if n % 10 == 1 && n % 100 != 11 {
                return "one";
            }
            if (n % 10 >= 2 && n % 10 <= 4) && (n % 100 < 12 || n % 100 > 14) {
                return "few";
            }
            if n % 10 == 0 || (n % 10 >= 5 && n % 10 <= 9) || (n % 100 >= 11 && n % 100 <= 14) {
                return "many";
            }
            "other"
        }
        "uk" => {
            if n % 10 == 1 && n % 100 != 11 {
                return "one";
            }
            if (n % 10 >= 2 && n % 10 <= 4) && (n % 100 < 12 || n % 100 > 14) {
                return "few";
            }
            if n % 10 == 0 || (n % 10 >= 5 && n % 10 <= 9) || (n % 100 >= 11 && n % 100 <= 14) {
                return "many";
            }
            "other"
        }
        "de" => {
            if n == 1 {
                return "one";
            }
            "other"
        }
        "fr" => {
            if n <= 1 {
                return "one";
            }
            "other"
        }
        "es" => {
            if n == 1 {
                return "one";
            }
            "other"
        }
        "pt" => {
            if n <= 1 {
                return "one";
            }
            "other"
        }
        "ja" => {
            "other"
        }
        "zh" => {
            "other"
        }
        "ko" => {
            "other"
        }
        _ => "other",
    }
}
