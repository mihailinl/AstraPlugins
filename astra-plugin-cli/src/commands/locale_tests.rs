//! Tests for [`super`] — the locale rules, and the shared fixture corpus.
//!
//! In its own file because the corpus reader below is the load-bearing half of
//! coupling C16 and deserves to be findable, rather than being the last two
//! hundred lines of a nine-hundred-line module.

use super::*;
use std::path::Path;

/// The corpus, from this crate rather than from the process CWD.
fn corpus() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../testdata/locales")
}

/// The fewest cases this reader may find before it concludes that IT broke
/// rather than that the corpus shrank.
///
/// Not the real count. A floor, so growth is free and an empty scan is not —
/// and written here, above the reader, rather than derived from what the reader
/// happened to find.
const MIN_PASS_CASES: usize = 4;
const MIN_FAIL_CASES: usize = 12;

/// Every ERROR id this module can emit. The corpus is held to covering all of
/// them, and anything that cannot be given a fixture goes in the list below
/// with a reason.
const ERROR_IDS: &[&str] = &[
    "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12", "E13", "E14",
    "E15", "E16", "E17", "E20", "N1", "N2", "N3",
];

/// Rules with no `fail/` fixture, and why not.
///
/// **An exemption list rather than a silence.** The rule below is "every error
/// id has a case"; a new id arrives as a one-line answer to *"does this need a
/// fixture, and why not?"* instead of as an absence nobody notices. The
/// exemption list is the load-bearing half — it turns forgetting into a visible
/// blank.
const NO_FIXTURE: &[(&str, &str)] = &[
    (
        "N2",
        "a missing locales.lock.json is a NOTE at check severity and an ERROR only under \
         Gate::Build. A corpus case carries one verdict, so the promotion is pinned by \
         `the_build_gate_promotes_the_lock_notes` below instead.",
    ),
    (
        "N3",
        "same: staleness is a note at check severity. `pass/plural-families` deliberately ships \
         a lock whose digests do NOT match its English, which is what proves it stays a note.",
    ),
];

fn manifest_at(dir: &Path) -> PluginManifest {
    let text = fs::read_to_string(dir.join("plugin.toml"))
        .unwrap_or_else(|e| panic!("{}: {e}", dir.display()));
    toml::from_str(&text).unwrap_or_else(|e| panic!("{}: {e}", dir.display()))
}

fn ids(findings: &Findings) -> BTreeSet<String> {
    findings
        .errors
        .iter()
        .map(|e| {
            e.trim_start_matches('[')
                .split(']')
                .next()
                .unwrap_or_default()
                .to_string()
        })
        .collect()
}

fn cases(kind: &str) -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = fs::read_dir(corpus().join(kind))
        .unwrap_or_else(|e| {
            panic!(
                "cannot read testdata/locales/{kind}: {e}. That directory is the shared fixture \
                 corpus — coupling C16 — and this reader enumerates it. If it is not there, THIS \
                 SCAN is what broke, not the rules."
            )
        })
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_dir())
        .collect();
    out.sort();
    out
}

/// C16 — the corpus, read at check severity, in both directions.
#[test]
fn the_shared_locale_corpus_says_what_the_rules_say() {
    let pass = cases("pass");
    let fail = cases("fail");

    // The floor, BEFORE any comparison. The two failures look nothing alike: a
    // shrunken corpus is somebody deleting a rule's only witness, and an empty
    // one is this reader looking in the wrong place. Saying which is worth more
    // than any diff below.
    assert!(
        pass.len() >= MIN_PASS_CASES && fail.len() >= MIN_FAIL_CASES,
        "found {} pass and {} fail case(s) under {} (floor: {MIN_PASS_CASES}/{MIN_FAIL_CASES}).\n\
         If testdata/locales still holds one directory per case, the RULES are what shrank and \
         somebody deleted a fixture.\n\
         If it does not, this SCAN is what broke — the corpus moved, or the sparse-checkout that \
         fetched it does not include testdata/locales.",
        pass.len(),
        fail.len(),
        corpus().display()
    );

    for dir in &pass {
        let f = findings(dir, &manifest_at(dir), Gate::Check);
        assert!(
            f.errors.is_empty(),
            "pass/{} produced {} error(s), and a pass case must produce none:\n{}\n\nWhy this \
             case exists:\n{}",
            dir.file_name().unwrap().to_string_lossy(),
            f.errors.len(),
            f.errors.join("\n"),
            fs::read_to_string(dir.join("WHY")).unwrap_or_default()
        );
    }

    let mut covered: BTreeSet<String> = BTreeSet::new();
    // Every mismatch, not the first. A reader that panics on case 8 has said
    // nothing at all about cases 9 through 18, so a fix and a re-run is the only
    // way to learn there were three problems — which is how a corpus becomes
    // something people run once and stop trusting.
    let mut mismatches: Vec<String> = Vec::new();
    for dir in &fail {
        let name = dir.file_name().unwrap().to_string_lossy().into_owned();
        let expect: BTreeSet<String> = fs::read_to_string(dir.join("EXPECT"))
            .unwrap_or_else(|e| panic!("fail/{name} has no EXPECT: {e}"))
            .lines()
            .map(str::trim)
            .filter(|l| !l.is_empty())
            .map(str::to_string)
            .collect();
        assert!(!expect.is_empty(), "fail/{name}'s EXPECT is empty");
        for id in &expect {
            assert!(
                ERROR_IDS.contains(&id.as_str()),
                "fail/{name} expects `{id}`, which is not a rule this CLI implements. Either the \
                 id is a typo or the rule was removed and its fixture outlived it."
            );
        }

        let f = findings(dir, &manifest_at(dir), Gate::Check);
        let got = ids(&f);
        if got != expect {
            mismatches.push(format!(
                "fail/{name}\n  expected: {expect:?}\n  got:      {got:?}\n  output:\n    {}\n\
                 \x20 why this case exists:\n{}",
                f.errors.join("\n    "),
                fs::read_to_string(dir.join("WHY")).unwrap_or_default()
            ));
        }
        covered.extend(expect);
    }
    assert!(
        mismatches.is_empty(),
        "{} of {} fail case(s) do not match their EXPECT:\n\n{}",
        mismatches.len(),
        fail.len(),
        mismatches.join("\n")
    );

    // Every rule has a witness, or an exemption that says why not.
    for id in ERROR_IDS {
        if covered.contains(*id) {
            continue;
        }
        let exempt = NO_FIXTURE.iter().find(|(x, _)| x == id);
        assert!(
            exempt.is_some(),
            "rule `{id}` has no fail case in testdata/locales and is not on NO_FIXTURE. A rule \
             with no witness is a rule that may already have stopped firing — add a case, or add \
             a line saying why it cannot have one."
        );
    }
    // …and an exemption that is no longer needed is itself a failure, or the
    // list rots into decoration.
    //
    // **Stated plainly, because I broke it on purpose and it did not fire the
    // way I aimed it.** Adding a `fail/` case claiming `N3` makes the EXPECT
    // comparison above go red FIRST — N3 is a note at check severity, so the
    // case produces no such error and never reaches here. So for the two ids
    // currently exempt this loop cannot fire at all; it is live only for a
    // future exemption of an id that CAN be an error at check severity. It
    // stays because that future is the one where an exemption quietly outlives
    // its reason, and it is written down because a guard nobody has watched
    // fire is a guard nobody should count.
    for (id, _) in NO_FIXTURE {
        assert!(
            !covered.contains(*id),
            "`{id}` is on NO_FIXTURE and now HAS a fail case. Delete the exemption."
        );
    }
}

/// The three notes `build` promotes, which no corpus case can carry.
#[test]
fn the_build_gate_promotes_the_lock_notes() {
    let dir = corpus().join("pass/plural-families");
    let m = manifest_at(&dir);

    let checked = findings(&dir, &m, Gate::Check);
    assert!(
        checked.errors.is_empty(),
        "stale translations are a NOTE on the hot path — `astra-plugin dev` runs check --strict \
         on every start, and an author must be able to run a plugin whose prose is behind:\n{}",
        checked.errors.join("\n")
    );
    assert!(
        checked.notes.iter().any(|n| n.starts_with("[N3]")),
        "this fixture's lock digests do not match its English; N3 must say so:\n{}",
        checked.notes.join("\n")
    );

    let built = findings(&dir, &m, Gate::Build);
    assert!(
        built.errors.iter().any(|e| e.starts_with("[N3]")),
        "at the artifact a stale translation is an ERROR: a published bundle may not ship a \
         sentence that describes English the author has since rewritten.\n{}",
        built.errors.join("\n")
    );
}

/// `qps` is permitted by `check` and refused by `build`.
#[test]
fn the_pseudo_locale_is_a_named_exception_and_build_refuses_it() {
    let dir = scratch("qps");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture"}"#,
    )
    .unwrap();
    fs::write(dir.join("locales/qps.json"), r#"{"listing.name":"⟦Fixture⟧"}"#).unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    let checked = findings(&dir, &m, Gate::Check);
    assert!(
        checked.errors.is_empty(),
        "check must permit qps — it is the development aid `locale pseudo` writes:\n{}",
        checked.errors.join("\n")
    );
    assert!(checked.notes.iter().any(|n| n.starts_with("[N10]")), "{:?}", checked.notes);
    // …and it is exempt from parity, which is the part that would otherwise
    // make `locale pseudo` write a file `check` rejects.
    assert!(
        !checked.errors.iter().any(|e| e.starts_with("[E2]")),
        "qps must not be held to key parity"
    );

    let built = findings(&dir, &m, Gate::Build);
    assert!(built.errors.iter().any(|e| e.starts_with("[E4]")), "{:?}", built.errors);
    let _ = fs::remove_dir_all(&dir);
}

const FIXTURE_MANIFEST: &str = r#"
[plugin]
id = "fixture"
name = "Fixture"
version = "0.1.0"
description = "A fixture"

[entry]
command = "./bin/fixture"

[capabilities]
tools = true
"#;

fn scratch(tag: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("astra-locale-{tag}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// `spec/listing-limits.yaml` is the list; `src/listing-limits.yaml` mirrors it.
///
/// The spec file sits outside this crate's package directory, so it cannot be
/// `include_str!`d without breaking `cargo package` — the same reason
/// `conformance.json` is vendored. This is the check that keeps the copy equal,
/// and it runs on every `cargo test` with no second checkout.
#[test]
fn the_listing_limits_are_the_ones_the_spec_declares() {
    let spec_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../spec/listing-limits.yaml");
    let spec = fs::read_to_string(&spec_path)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", spec_path.display()));
    assert_eq!(
        spec, LISTING_LIMITS_SPEC,
        "spec/listing-limits.yaml and astra-plugin-cli/src/listing-limits.yaml differ. The spec \
         file is the list; copy it over. And if the REGISTRY is what changed, change it there \
         first — `tools/check-locales.py --rules C20` is what compares the two repositories."
    );

    let parsed = listing_limits();
    assert!(
        parsed.len() >= 4,
        "parsed {} row(s) out of listing-limits.yaml. That file's FORMAT paragraph promises \
         `name: <integer>` per line — if it still looks like that, this reader is what broke.",
        parsed.len()
    );
    for required in [
        "max_name_length",
        "max_summary_length",
        "max_description_length",
        "max_permission_reason_chars",
    ] {
        assert!(parsed.contains_key(required), "no `{required}` row");
        assert!(cap(required) > 0, "`{required}` is zero, which would refuse everything");
    }
}

// ── the pieces, in isolation ─────────────────────────────────────────────────

/// The plural collapse, and the trap it deliberately does not fall into.
#[test]
fn a_family_needs_two_categories_before_it_is_one() {
    let dir = scratch("families");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture",
            "msg.done.one":"one","msg.done.other":"many","thing.other":"the other one"}"#,
    )
    .unwrap();
    let set = LocaleSet::read(&dir);
    let families = plural_families(&set);

    assert!(families.contains("msg.done"), "two categories is a plural family");
    assert!(
        !families.contains("thing"),
        "`thing.other` alone is an ordinary key. Collapsing it would make E15 demand a \
         `thing.one` of English — this CLI refusing a plugin that works."
    );
    assert_eq!(family_id("msg.done.few", &families), "msg.done");
    assert_eq!(family_id("thing.other", &families), "thing.other");
    let _ = fs::remove_dir_all(&dir);
}

/// The script check, on the string this whole project was filed from.
#[test]
fn the_english_gate_measures_letters_and_not_case() {
    let live = "Шахматы против локального бота или выбранной модели Astra с игровым чатом.";
    assert!(!is_latin_script(live), "the live failure must not pass");

    // Japanese has NO cased letters at all. Counting cased letters would report
    // "contains no letters at all" here — a sentence that is simply false — so
    // the denominator is `is_alphabetic`, and the no-letters message stays
    // reserved for the case it describes.
    let (latin, letters) = latin_fraction("ローカライズ規則の検証用フィクスチャ");
    assert_eq!(latin, 0);
    assert!(letters > 0, "kana and kanji are letters; a cased-letters count would say 0 here");

    assert!(is_latin_script("Roll dice from a command"));
    assert!(is_latin_script("Wärmepumpen-Rechner für Ihr Zuhause"), "accents are Latin");
    assert!(
        is_latin_script("Bridge Telegram topics to Astra — including Привет"),
        "a mostly-English sentence quoting another script must pass: this is a script check, \
         not a purity test"
    );
    assert_eq!(latin_fraction("🎲🎲🎲 123"), (0, 0), "no letters at all");
    assert!(!is_latin_script("🎲🎲🎲 123"));
}

/// `$$` is the daemon's escape, and nothing here may read it as a key.
#[test]
fn the_dollar_escape_is_a_literal_everywhere() {
    assert!(matches!(marker("$$5 and up"), Some(Marker::Escaped)));
    assert!(matches!(marker("$config.token.title"), Some(Marker::Key("config.token.title"))));
    assert!(marker("plain").is_none());

    // Astra's own predicate, and the four shapes its doc names as rejects.
    assert!(looks_like_key("config.token.title"));
    assert!(looks_like_key("USD.rate"));
    assert!(!looks_like_key("USD"), "one segment is a shell variable, not a key");
    assert!(!looks_like_key("config."));
    assert!(!looks_like_key("a..b"));
    assert!(!looks_like_key("9lives.thing"));
    assert!(!looks_like_key("has-a-dash.thing"));
}

/// Shape narrows a refusal here and never widens one.
///
/// This is the property that makes a second copy of `looks_like_key` safe to
/// keep: if it ever drifts from the daemon's, the cost is a note, not a
/// rejected bundle.
#[test]
fn no_string_is_ever_refused_for_its_shape_alone() {
    let dir = corpus().join("pass/dollar-literals");
    let f = findings(&dir, &manifest_at(&dir), Gate::Check);
    assert!(
        f.errors.is_empty(),
        "`$HOME/notes`, `$$5 and up` and a `$USD` with a real `USD` key must all pass:\n{}",
        f.errors.join("\n")
    );
    // The one that is neither key-shaped nor defined is still SAID, because it
    // is the case Astra's narrowing made silent.
    assert!(
        f.notes.iter().any(|n| n.starts_with("[N5]") && n.contains("HOME")),
        "a `$` value with no key must produce a note stating both readings:\n{}",
        f.notes.join("\n")
    );
}

/// The lock derives state; it never asks the author to assert it.
#[test]
fn the_lock_reads_stale_from_the_english_it_recorded() {
    let english = "Handled {n} items";
    let d = digest(english);
    assert_eq!(d.len(), 12, "12 hex of sha256 over the exact English bytes");
    assert_ne!(d, digest("Handled {n} item(s)"), "changed English changes the digest");

    let mut lock = Lock { schema: LOCK_SCHEMA.into(), source: "en".into(), ..Lock::default() };
    lock.locales
        .entry("ru".into())
        .or_default()
        .insert("k".into(), d.clone());

    assert_eq!(freshness(Some(&lock), "ru", "k", english, "перевод"), Freshness::Fresh);
    assert_eq!(
        freshness(Some(&lock), "ru", "k", "Handled {n} item(s)", "перевод"),
        Freshness::Stale,
        "the English moved and the translation did not"
    );
    assert_eq!(freshness(None, "ru", "k", english, "перевод"), Freshness::New);
    assert_eq!(
        freshness(Some(&lock), "ru", "k", english, english),
        Freshness::Untranslated,
        "a value equal to English is seeded, not translated"
    );

    // The state this module had no name for, and the whole of the blocking
    // defect. The lock recorded `english`; the value IS `english`; the English
    // has since moved. Nobody translated this, so it is not `Stale` — and it is
    // emphatically not `New`, which is what it used to come back as, one `sync`
    // away from carrying the digest of English it has never been compared with.
    assert_eq!(
        freshness(Some(&lock), "ru", "k", "Handled {n} item(s)", english),
        Freshness::SeededStale,
        "the value hashes to the English the lock recorded, so it never stopped being that \
         English"
    );
}

/// The lock covers a plural family whose rows English cannot legally carry.
///
/// `ru` needs `few` and `many`; `en` needs `one` and `other`, and E15 refuses it
/// any more than that. Keyed on `en.keys.get(key)` those two rows have no
/// English, get no lock entry, and can never be reported stale — so rewriting
/// both English rows of a four-row Russian family reported **two**, `--accept`
/// cleared it, and the family shipped two-thirds updated and reading fresh.
#[test]
fn the_lock_covers_a_plural_family_english_cannot_carry() {
    let dir = corpus().join("pass/lock-plural-family-stale");
    let m = manifest_at(&dir);
    let set = LocaleSet::read(&dir);

    let families = plural_families(&set);
    let en = set.get("en").unwrap();
    assert!(
        !en.keys.contains_key("msg.done.few"),
        "this fixture is pointless if English carries the row — E15 refuses it"
    );
    assert_eq!(
        english_for(en, "msg.done.few", &families),
        en.keys.get("msg.done.other"),
        "a category English cannot carry is measured against `<base>.other`"
    );

    let stale = stale_keys(&set);
    let ru: Vec<&str> = stale.get("ru").map(|v| v.iter().map(String::as_str).collect())
        .unwrap_or_default();
    assert_eq!(
        ru,
        ["msg.done.few", "msg.done.many", "msg.done.one", "msg.done.other"],
        "all four Russian rows describe English that has been rewritten"
    );

    let built = findings(&dir, &m, Gate::Build);
    assert!(
        built.errors.iter().any(|e| e.starts_with("[N3]") && e.contains("4 stale")),
        "build must refuse the whole family, and say four:\n{}",
        built.errors.join("\n")
    );
}

/// A seed the English moved out from under is named as one, at both gates.
#[test]
fn the_lock_notices_a_seed_the_english_moved_out_from_under() {
    let dir = corpus().join("pass/lock-seeded-english-moved");
    let m = manifest_at(&dir);

    let checked = findings(&dir, &m, Gate::Check);
    assert!(checked.errors.is_empty(), "{}", checked.errors.join("\n"));
    assert!(
        checked.notes.iter().any(|n| n.starts_with("[N15]") && n.contains("listing.description")),
        "the seed whose English moved must be named:\n{}",
        checked.notes.join("\n")
    );
    assert!(
        !checked.notes.iter().any(|n| n.starts_with("[N3]")),
        "nothing here was ever translated, so N3's sentence about a translation describing \
         older English would be false:\n{}",
        checked.notes.join("\n")
    );

    // N15 is a note at BOTH gates. `build` refuses a stale TRANSLATION because
    // a reader gets a confidently wrong sentence in their own language; a
    // reader of this file gets English either way, and refusing somebody's
    // release over a file they never claimed to have translated is a different
    // trade.
    let built = findings(&dir, &m, Gate::Build);
    assert!(built.errors.is_empty(), "N15 must never be promoted:\n{}", built.errors.join("\n"));
}

/// The positive control: an up-to-date lock says nothing at all.
///
/// Without it, a reader that has started calling every key stale passes both
/// fixtures above and fails nothing.
#[test]
fn a_lock_that_is_up_to_date_produces_no_lock_findings() {
    let dir = corpus().join("pass/lock-up-to-date");
    let m = manifest_at(&dir);
    let built = findings(&dir, &m, Gate::Build);
    assert!(built.errors.is_empty(), "{}", built.errors.join("\n"));
    for id in ["[N2]", "[N3]", "[N15]"] {
        assert!(
            !built.notes.iter().any(|n| n.starts_with(id)),
            "{id} on a lock whose every digest is the real sha256 of the English beside it:\n{}",
            built.notes.join("\n")
        );
    }
    let drift = lock_drift(&LocaleSet::read(&dir));
    assert!(drift.stale.is_empty() && drift.seeded.is_empty());
}

/// **The blocking defect, end to end.** `sync` must not turn a seed into a
/// fresh translation the moment the English moves.
///
/// Driven the way an author hits it: seed `ru` from English, rewrite the
/// English, run `sync`. The old reader saw *differs from English, no lock
/// entry*, called it **newly translated**, and stamped the digest of the **new**
/// English — after which `locale ls` said `stale 0`, `check` said OK, `build`
/// packed it, and the registry published the plugin's previous English text as
/// its Russian store card with no finding anywhere.
#[test]
fn sync_does_not_relabel_a_seed_as_a_translation_when_the_english_moves() {
    let dir = scratch("seed-moved");
    let old_english = "A fixture";
    let new_english = "A fixture for the shared locale rule corpus";
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        format!(r#"{{"listing.name":"Fixture","listing.description":"{old_english}"}}"#),
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    crate::output::set_json(true);
    add(&dir, &m, "ru").unwrap(); // seeds ru.json AND writes the lock
    crate::output::set_json(false);

    // The seed carries an entry. That is the fix: without one, the next `sync`
    // has nothing to notice with.
    let seeded = LocaleSet::read(&dir);
    assert_eq!(
        seeded
            .lock
            .as_ref()
            .and_then(|l| l.locales.get("ru"))
            .and_then(|m| m.get("listing.description")),
        Some(&digest(old_english)),
        "a value equal to English must still be recorded against the English it was copied from"
    );

    // The author rewrites the English. `sync` rewrites en.json from plugin.toml
    // and then rewrites the lock — the one invocation the defect lived in.
    fs::write(
        dir.join("plugin.toml"),
        FIXTURE_MANIFEST.replace(
            &format!("description = \"{old_english}\""),
            &format!("description = \"{new_english}\""),
        ),
    )
    .unwrap();
    let m2: PluginManifest =
        toml::from_str(&fs::read_to_string(dir.join("plugin.toml")).unwrap()).unwrap();
    crate::output::set_json(true);
    sync(&dir, &m2, &[]).unwrap();
    crate::output::set_json(false);

    let after = LocaleSet::read(&dir);
    let recorded = after
        .lock
        .as_ref()
        .and_then(|l| l.locales.get("ru"))
        .and_then(|m| m.get("listing.description"))
        .cloned();
    assert_eq!(
        recorded.as_deref(),
        Some(digest(old_english).as_str()),
        "sync re-stamped an untranslated seed with the digest of English it has never been \
         compared against. The registry reads this number: a match means `not stale`, and the \
         card then ships the plugin's previous English as its Russian summary."
    );
    assert_ne!(
        recorded.as_deref(),
        Some(digest(new_english).as_str()),
        "this is the exact value the defect wrote"
    );

    let drift = lock_drift(&after);
    assert_eq!(
        drift.seeded.get("ru").map(Vec::as_slice),
        Some(["listing.description".to_string()].as_slice()),
        "and it must be reported, not merely left unstamped"
    );
    assert!(findings(&dir, &m2, Gate::Check).notes.iter().any(|n| n.starts_with("[N15]")));

    // `--accept` is still the author's word, and still the only way through.
    crate::output::set_json(true);
    sync(&dir, &m2, &["ru:listing.description".to_string()]).unwrap();
    crate::output::set_json(false);
    assert!(lock_drift(&LocaleSet::read(&dir)).seeded.is_empty());
    let _ = fs::remove_dir_all(&dir);
}

/// `locale add` writes exactly the rows the code's plural rules need.
#[test]
fn locale_add_writes_the_plural_rows_that_code_needs() {
    let dir = scratch("add");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture",
            "msg.done.one":"Handled {n} item","msg.done.other":"Handled {n} items"}"#,
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    crate::output::set_json(true); // silence the progress lines
    add(&dir, &m, "ru").unwrap();
    add(&dir, &m, "ja").unwrap();
    crate::output::set_json(false);

    let set = LocaleSet::read(&dir);
    let ru: Vec<&String> = set.get("ru").unwrap().keys.keys().collect();
    assert!(
        ru.iter().any(|k| *k == "msg.done.few") && ru.iter().any(|k| *k == "msg.done.many"),
        "Russian needs few and many: {ru:?}"
    );
    let ja: Vec<&String> = set.get("ja").unwrap().keys.keys().collect();
    assert!(!ja.iter().any(|k| *k == "msg.done.one"), "Japanese does not inflect: {ja:?}");

    // And the thing that matters: what it wrote passes the rules it will be
    // checked against. The merged design's raw-key parity rule failed exactly
    // here, on a file the CLI itself had just recommended.
    let f = findings(&dir, &m, Gate::Check);
    assert!(
        f.errors.is_empty(),
        "`locale add` wrote a tree its own `check` refuses:\n{}",
        f.errors.join("\n")
    );
    let _ = fs::remove_dir_all(&dir);
}

/// `locale sync` refuses to re-stamp a stale entry without being told to.
#[test]
fn sync_will_not_quietly_relabel_a_stale_translation_as_fresh() {
    let dir = scratch("sync");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture","k":"New English"}"#,
    )
    .unwrap();
    fs::write(
        dir.join("locales/ru.json"),
        r#"{"listing.name":"Fixture","listing.description":"Набор","k":"Старый перевод"}"#,
    )
    .unwrap();
    fs::write(
        dir.join(LOCK_FILE),
        format!(
            r#"{{"schema":"{LOCK_SCHEMA}","source":"en","locales":{{"ru":{{"k":"{}"}}}}}}"#,
            digest("Old English")
        ),
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    crate::output::set_json(true);
    sync(&dir, &m, &[]).unwrap();
    crate::output::set_json(false);
    assert!(
        !stale_keys(&LocaleSet::read(&dir)).is_empty(),
        "a bare `sync` must leave a stale entry stale — re-stamping it turns a caught problem \
         into a silent one, and `build` would then pack it"
    );

    crate::output::set_json(true);
    sync(&dir, &m, &["ru:k".to_string()]).unwrap();
    crate::output::set_json(false);
    assert!(
        stale_keys(&LocaleSet::read(&dir)).is_empty(),
        "`--accept ru:k` is the author saying the translation is still correct, and it lands in \
         a committed diff"
    );
    let _ = fs::remove_dir_all(&dir);
}

/// `locale sync` rewrites the two reserved keys, so E8 is one command from
/// green rather than a rule that fires on every author's first edit.
#[test]
fn sync_rewrites_the_listing_keys_from_the_manifest() {
    let dir = scratch("listing");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Stale Name","listing.description":"An Astra plugin"}"#,
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();
    assert!(findings(&dir, &m, Gate::Check).errors.iter().any(|e| e.starts_with("[E8]")));

    crate::output::set_json(true);
    sync(&dir, &m, &[]).unwrap();
    crate::output::set_json(false);

    let f = findings(&dir, &m, Gate::Check);
    assert!(f.errors.is_empty(), "{}", f.errors.join("\n"));
    let _ = fs::remove_dir_all(&dir);
}
