//! The language codes Astra can be set to — this binary's copy of them.
//!
//! `spec/locales.yaml` is the list; this file only mirrors it, the way
//! `ICON_FILENAMES` in `commands::build` mirrors `spec/icon-formats.yaml`.
//! The mirror exists because that spec file sits outside this crate's package
//! directory, so it cannot be `include_str!`d without breaking `cargo package`
//! — and it is a mirror rather than a habit because
//! `the_locale_codes_are_the_ones_the_spec_declares` reads the spec file at
//! test time and fails until the two agree.
//!
//! That test is the floor of the whole locale story, and it is the only part of
//! it that runs everywhere: `cargo test` on any machine, on a pull request from
//! a fork, with no secret and no second checkout. C12 — the comparison against
//! the daemon's own `SUPPORTED_LANGUAGES` — needs the private Astra repository
//! and is skipped, loudly, on every fork PR. If those two ever disagree about
//! what this file should contain, C12 is the one that is right; this one is the
//! one that always runs.
//!
//! # What a wrong entry here costs
//!
//! Language matching is exact string equality on both sides: the daemon's
//! `PluginManager::get_config_schema` does `instance.locales.get(language)` on
//! a `HashMap`, and all three SDKs do the same. A plugin that ships
//! `locales/zh-CN.json` — the spelling this repository's own documentation tree
//! used until the commit that added this file — has that file packed into the
//! bundle, hashed into `manifest_digest`, covered by `artifact_sha256`,
//! countersigned by the registry, installed, and read by nothing. There is no
//! error at any point. The author's only symptom is a settings page that stays
//! English in a language they translated.

/// Every language Astra can be set to, in `spec/locales.yaml`'s order.
///
/// `en` is first because it is the base every other locale falls back to.
// This list is what every rule that refuses an unknown code refuses it
// against; `grep -rn LOCALE_CODES src/` is the current set of readers, and it
// has never been the number written here. The sentence this replaces said
// "nothing consumes this yet — the consumers are the next commit", which was
// true for one commit and then sent every later reader looking for work that
// was already done. What the list is WORTH is a separate question from who
// reads it, and the answer to that is the test below.
pub const LOCALE_CODES: &[&str] = &[
    "en", "ru", "uk", "de", "fr", "es", "pt", "ja", "zh", "ko",
];

/// The subset whose Astra UI translation is held complete; the rest fall back
/// to English per key inside Astra's own shell.
///
/// Not a rule about plugins. A plugin that ships `de.json` is not shipping into
/// a half-translated app on the strength of this list — it is a fact about
/// Astra, mirrored so that whoever reads `spec/locales.yaml` can see it.
#[allow(dead_code)]
pub const MAINTAINED_LOCALE_CODES: &[&str] = &["en", "ru", "uk"];

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::Path;

    /// One row of `spec/locales.yaml`: the code, and whether it is maintained.
    ///
    /// The hand-parse that file's FORMAT paragraph promises — split on
    /// whitespace, first field is the code, last field is `maintained` or is
    /// not. `tools/check-locales.py` implements the same three lines, and
    /// neither takes a dependency to do it.
    fn declared() -> Vec<(String, bool)> {
        let spec = Path::new(env!("CARGO_MANIFEST_DIR")).join("../spec/locales.yaml");
        let text = fs::read_to_string(&spec)
            .unwrap_or_else(|e| panic!("cannot read {}: {e}", spec.display()));
        text.lines()
            .map(str::trim)
            .filter(|l| !l.is_empty() && !l.starts_with('#'))
            .map(|l| {
                let fields: Vec<&str> = l.split_whitespace().collect();
                (
                    fields[0].to_string(),
                    fields.last() == Some(&"maintained"),
                )
            })
            .collect()
    }

    /// `spec/locales.yaml` is the list; this file only mirrors it.
    ///
    /// The failure this prevents is silent from end to end. A code in one list
    /// and not the other is either a locale file the CLI will happily pack and
    /// the daemon can never select, or a language the CLI refuses to pack for
    /// while the daemon offers it in Settings. Nothing between here and the
    /// user's screen raises anything about either.
    #[test]
    fn the_locale_codes_are_the_ones_the_spec_declares() {
        let rows = declared();

        // A floor before a comparison, because the two failures look nothing
        // alike: an empty parse means this reader broke, and saying so is worth
        // more than a diff against ten expected strings.
        assert!(
            rows.len() >= 2,
            "parsed {} row(s) out of spec/locales.yaml. That file's FORMAT paragraph \
             promises one language per line, `#` comments, blank lines ignored — if it \
             still looks like that, this reader is the thing that broke.",
            rows.len()
        );

        let codes: Vec<&str> = rows.iter().map(|(c, _)| c.as_str()).collect();
        assert_eq!(
            codes, LOCALE_CODES,
            "spec/locales.yaml and LOCALE_CODES disagree. The spec file is the list; \
             change it there first, then mirror it here. If the daemon is what changed, \
             C12 in the `proto-upstream` job is where the two are compared — and it can \
             only run where the private Astra repository is visible."
        );

        let maintained: Vec<&str> = rows
            .iter()
            .filter(|(_, m)| *m)
            .map(|(c, _)| c.as_str())
            .collect();
        assert_eq!(
            maintained, MAINTAINED_LOCALE_CODES,
            "spec/locales.yaml's `maintained` rows and MAINTAINED_LOCALE_CODES disagree."
        );
    }

    /// No region tags, in the one place that could introduce one.
    ///
    /// `docs/zh-CN` existed in this repository for months and taught the
    /// spelling to anyone reading the documentation tree. `SUPPORTED_LANGUAGES`
    /// is bare ISO-639-1 and `Settings::validate` refuses everything else, so a
    /// region-tagged row here would be a code the CLI accepts, packs, and the
    /// daemon can never send. This makes that row unrepresentable rather than
    /// merely discouraged — and it is a property of the *file*, so it holds
    /// against an edit that never touches this crate.
    #[test]
    fn the_spec_declares_no_region_tags_and_no_duplicates() {
        let rows = declared();
        assert!(rows.len() >= 2, "empty parse; see the test above");

        for (code, _) in &rows {
            assert!(
                code.len() == 2 && code.bytes().all(|b| b.is_ascii_lowercase()),
                "spec/locales.yaml declares {code:?}. Every language Astra can be set to \
                 is two lower-case ASCII letters — no region tags exist anywhere in this \
                 system, so `zh-CN`, `pt_BR` and `EN` are all names nothing can select."
            );
        }

        let mut seen: Vec<&str> = rows.iter().map(|(c, _)| c.as_str()).collect();
        seen.sort_unstable();
        let before = seen.len();
        seen.dedup();
        assert_eq!(
            before,
            seen.len(),
            "spec/locales.yaml lists a code twice. Every reader of it builds a set, so \
             the duplicate would be invisible in all of them."
        );

        assert_eq!(
            rows[0].0, "en",
            "`en` must be the first row: it is the base every other locale falls back \
             to, per file in the daemon and per key in the SDKs."
        );

        let codes: Vec<&str> = rows.iter().map(|(c, _)| c.as_str()).collect();
        for m in MAINTAINED_LOCALE_CODES {
            assert!(
                codes.contains(m),
                "{m:?} is marked maintained and is not a declared language."
            );
        }
    }
}
