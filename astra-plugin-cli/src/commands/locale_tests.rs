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

/// The fewest error ids the scrape below may find before it concludes that IT
/// broke rather than that the rules shrank.
///
/// Written above the reader, and it is 21 because that is what the hand-kept
/// list it replaces contained — so the first run of the scrape had a number to
/// disagree with rather than a number to define.
const MIN_ERROR_IDS: usize = 21;

/// Every ERROR id this module can emit, **scraped from `locale.rs`** rather
/// than kept by hand.
///
/// The list this replaces was a literal, and it was correct: 21 ids, exactly
/// the set `.err(` is called with today. That is the argument for scraping it
/// and not against — a hand list is right until the commit that adds the
/// twenty-second rule, and the failure then is silent in the direction that
/// matters, because "every rule has a witness" would go on passing over a rule
/// with no fixture and no exemption.
///
/// Scope, in the same sentence as the number: this reads `.err("ID"` out of
/// `src/commands/locale.rs` and nothing else. Notes are deliberately not
/// scraped — the coverage rule below is about `findings.errors`, and `N1`,
/// `N2` and `N3` appear here because those three are also raised as errors.
fn error_ids() -> Vec<String> {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src/commands/locale.rs");
    let text = fs::read_to_string(&src)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", src.display()));
    let mut ids: Vec<String> = Vec::new();
    for (at, _) in text.match_indices(".err(") {
        let rest = text[at + ".err(".len()..].trim_start();
        let Some(quoted) = rest.strip_prefix('"') else { continue };
        let Some(end) = quoted.find('"') else { continue };
        let id = &quoted[..end];
        let mut chars = id.chars();
        let shaped = chars.next().is_some_and(|c| c.is_ascii_uppercase())
            && chars.clone().count() > 0
            && chars.all(|c| c.is_ascii_digit());
        if shaped && !ids.iter().any(|x| x == id) {
            ids.push(id.to_string());
        }
    }
    ids.sort_by_key(|id| (id[..1].to_string(), id[1..].parse::<u32>().unwrap_or(0)));
    assert!(
        ids.len() >= MIN_ERROR_IDS,
        "scraped {} error id(s) out of {}. Every rule there raises one as `f.err(\"E4\", …)` \
         with the id a literal — if it still looks like that, this reader is the thing that \
         broke, and the corpus coverage check below is measuring nothing.",
        ids.len(),
        src.display()
    );
    ids
}

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
    (
        "E18",
        "the registry raises this as `E_LOCALE_TOO_LARGE`, and `CORPUS_RULE_IDS` in \
         astra-registry/bot/lib/locales.mjs maps no corpus id to it — a fixture expecting `E18` \
         makes that repository's own corpus reader throw, which is a red catalogue build for a \
         fixture this side added. It becomes a fixture the day that mapping lands. Second \
         reason, and the one that would remain: the fixture IS the size, so it is a 256 KiB or \
         5,001-key file committed here and sparse-checked-out by the ingest job on every run. \
         Witnessed by `an_oversized_locale_file_is_refused_before_it_is_parsed` below.",
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
    let known_ids = error_ids();

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
                known_ids.contains(id),
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
    for id in &known_ids {
        if covered.contains(id) {
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
    add(&dir, &m, "ru", false).unwrap(); // seeds ru.json AND writes the lock
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
    add(&dir, &m, "ru", false).unwrap();
    add(&dir, &m, "ja", false).unwrap();
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

// ── `locale add` and what it deletes ────────────────────────────────────────

/// The scaffold's `en.json`, as `astra-plugin new --template action-trigger`
/// writes it — the tree every case below starts from.
fn seeded_project(tag: &str) -> (PathBuf, PluginManifest) {
    let dir = scratch(tag);
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture",
            "msg.done.one":"Handled {n} item","msg.done.other":"Handled {n} items"}"#,
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();
    (dir, m)
}

/// `locale add` will not delete a translation without being told to.
///
/// The defect this pins, reproduced end to end before it was written: translate
/// six Russian rows, rename `msg.done` to `msg.finished` in `en.json` — an
/// ordinary rename — and `check` prints E2 recommending `locale add ru`.
/// Running exactly that printed `4 key(s) added, 2 kept` and the four Russian
/// plural strings were gone. Nothing anywhere said so, and `check` then said
/// OK.
///
/// The pruning itself is wanted (E3, E15), which is why the answer is to say
/// what is being pruned rather than to stop pruning: this command cannot tell a
/// correction from a destruction, and the author is the only one who can.
#[test]
fn locale_add_refuses_to_delete_a_translation_in_silence() {
    let (dir, m) = seeded_project("add-prune");
    crate::output::set_json(true);
    add(&dir, &m, "ru", false).unwrap();
    crate::output::set_json(false);

    // Translate every row, then rename the English key.
    fs::write(
        dir.join("locales/ru.json"),
        r#"{"listing.name":"Фикстура","listing.description":"Набор",
            "msg.done.one":"Обработан {n} элемент","msg.done.few":"Обработано {n} элемента",
            "msg.done.many":"Обработано {n} элементов","msg.done.other":"Обработано {n} элемента"}"#,
    )
    .unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture",
            "msg.finished.one":"Handled {n} item","msg.finished.other":"Handled {n} items"}"#,
    )
    .unwrap();

    crate::output::set_json(true);
    let refused = add(&dir, &m, "ru", false);
    crate::output::set_json(false);
    let err = refused.expect_err("four translated values were about to be deleted").to_string();
    assert!(err.contains("msg.done.one"), "the refusal names them: {err}");
    assert!(err.contains("--prune"), "and names the way through: {err}");

    // …and the file is untouched. A refusal that had already written is worse
    // than no refusal.
    let ru = LocaleSet::read(&dir);
    assert_eq!(
        ru.get("ru").unwrap().keys.get("msg.done.one").map(String::as_str),
        Some("Обработан {n} элемент"),
        "the refusal must happen before the write"
    );

    // `--prune` deletes them, and names every one it deleted.
    crate::output::set_json(true);
    add(&dir, &m, "ru", true).unwrap();
    crate::output::set_json(false);
    let after = LocaleSet::read(&dir);
    let keys: Vec<&String> = after.get("ru").unwrap().keys.keys().collect();
    assert!(!keys.iter().any(|k| k.starts_with("msg.done.")), "{keys:?}");
    assert!(keys.iter().any(|k| *k == "msg.finished.many"), "{keys:?}");
    let _ = fs::remove_dir_all(&dir);
}

/// A value that is still the English seed is not somebody's work, so removing
/// it needs no permission — only a line saying it happened.
#[test]
fn a_seed_is_removed_without_a_refusal_and_is_still_reported() {
    let (dir, m) = seeded_project("add-seed");
    crate::output::set_json(true);
    add(&dir, &m, "ru", false).unwrap();
    crate::output::set_json(false);

    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture",
            "msg.finished.one":"Handled {n} item","msg.finished.other":"Handled {n} items"}"#,
    )
    .unwrap();

    let set = LocaleSet::read(&dir);
    let base = set.get("en").unwrap().keys.clone();
    let families = plural_families(&set);
    let existing = set.get("ru").unwrap().keys.clone();
    // What `add` would keep, built the way `add` builds it: nothing of
    // `msg.done` survives, so all four rows are removals.
    let out: BTreeMap<String, String> = base
        .iter()
        .flat_map(|(k, v)| {
            let (fam, cat) = split_category(k);
            if cat.is_some() && families.contains(fam) {
                plural::categories("ru")
                    .iter()
                    .map(|c| (format!("{fam}.{c}"), v.clone()))
                    .collect::<Vec<_>>()
            } else {
                vec![(k.clone(), v.clone())]
            }
        })
        .collect();
    let removed = removals(Some(&existing), &out, &base, &families, "ru");
    assert_eq!(removed.len(), 4, "the whole renamed family goes");
    assert!(
        removed.iter().all(|r| !r.translated),
        "every value here is still the English it was seeded with"
    );

    crate::output::set_json(true);
    add(&dir, &m, "ru", false).expect("no refusal: nothing of the author's is at stake");
    crate::output::set_json(false);
    let _ = fs::remove_dir_all(&dir);
}

/// A category the language never selects is a removal with its own reason —
/// the `locale add ja` case that strips a spurious `few`, which is the reason
/// pruning exists at all.
#[test]
fn a_category_this_language_cannot_select_says_so_by_name() {
    let (dir, m) = seeded_project("add-cat");
    crate::output::set_json(true);
    add(&dir, &m, "ja", false).unwrap();
    crate::output::set_json(false);

    // Somebody translated a row Japanese has no category for.
    let mut ja = LocaleSet::read(&dir).get("ja").unwrap().keys.clone();
    ja.insert("msg.done.few".to_string(), "いくつか処理しました".to_string());
    write_locale(&dir.join("locales/ja.json"), &ja).unwrap();

    crate::output::set_json(true);
    let refused = add(&dir, &m, "ja", false);
    crate::output::set_json(false);
    let err = refused.expect_err("a translated row was about to be deleted").to_string();
    assert!(
        err.contains("never selects the `few` plural category"),
        "the reason is the category and not a missing key: {err}"
    );
    let _ = fs::remove_dir_all(&dir);
}

/// `locale add en` seeds from the UNION, so E1's own printed fix does not land
/// the author on E3.
///
/// Before: `add en` wrote the two `listing.*` keys and ignored every key the
/// surviving locales carried, so following E1's fix produced E3 (and E15) for
/// each of them. The values copied out of another locale are NOT English and
/// nothing downstream can tell, so `add` says which file each came from.
#[test]
fn locale_add_en_seeds_from_every_locale_that_survived() {
    let dir = scratch("add-en");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/ru.json"),
        r#"{"listing.name":"Фикстура","listing.description":"Набор",
            "msg.done.one":"Обработан {n} элемент","msg.done.few":"Обработано {n} элемента",
            "msg.done.many":"Обработано {n} элементов","msg.done.other":"Обработано {n} элемента"}"#,
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();
    assert!(
        findings(&dir, &m, Gate::Check).errors.iter().any(|e| e.starts_with("[E1]")),
        "the fixture starts on the error whose fix is under test"
    );

    crate::output::set_json(true);
    add(&dir, &m, "en", false).unwrap();
    crate::output::set_json(false);

    let set = LocaleSet::read(&dir);
    let en = set.get("en").unwrap();
    // The two reserved keys come from plugin.toml — they are its copy, and a
    // Russian store card must not become the English one.
    assert_eq!(en.keys.get("listing.name").map(String::as_str), Some("Fixture"));
    // The rest come from the union, collapsed to English's own categories.
    assert!(en.keys.contains_key("msg.done.one"), "{:?}", en.keys.keys().collect::<Vec<_>>());
    assert!(en.keys.contains_key("msg.done.other"));
    assert!(!en.keys.contains_key("msg.done.few"), "English has no `few` category");

    let errors = findings(&dir, &m, Gate::Check).errors;
    assert!(
        !errors.iter().any(|e| e.starts_with("[E1]") || e.starts_with("[E3]")),
        "E1's fix must not hand the author E3:\n{}",
        errors.join("\n")
    );
    let _ = fs::remove_dir_all(&dir);
}

/// E6's plural hint is built on the family BASE.
///
/// `{"msg.done.one": {…}}` used to be answered with `("msg.done.one.one",
/// "msg.done.one.other")` — a suggestion nobody could act on.
#[test]
fn the_plural_hint_does_not_append_a_category_to_a_category() {
    let err = parse_flat(r#"{"msg.done.one": {"n": "Handled {n} item"}}"#).unwrap_err();
    assert!(err.contains(r#"("msg.done.one", "msg.done.other")"#), "{err}");
    assert!(!err.contains("msg.done.one.one"), "{err}");

    // A key that is not a category keeps its own name.
    let err = parse_flat(r#"{"greeting": 1}"#).unwrap_err();
    assert!(err.contains(r#"("greeting.one", "greeting.other")"#), "{err}");
}

/// `locale render --lang` refuses a code Astra cannot be set to, the way
/// `locale add` does.
///
/// `--lang zh-CN` and `--lang klingon` both printed `… as a klingon user reads
/// it:` and exited 0, while `locale add zh-CN` refused with a five-line
/// lecture. One of the two was teaching a spelling that reaches nothing.
#[test]
fn render_refuses_a_language_astra_cannot_be_set_to() {
    let dir = scratch("render-lang");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    crate::output::set_json(true);
    let err = render(&dir, &m, "zh-CN").expect_err("zh-CN is not a language").to_string();
    assert!(err.contains("--lang zh"), "the did-you-mean is the whole point: {err}");
    assert!(render(&dir, &m, "klingon").is_err());
    // The ten, and the pseudo-locale `locale render` exists to reach.
    for ok in ["en", "ru", "qps"] {
        assert!(render(&dir, &m, ok).is_ok(), "{ok} must still render");
    }
    crate::output::set_json(false);
    let _ = fs::remove_dir_all(&dir);
}

/// N1 escalates on both of the plan's conditions, not on one of them.
///
/// A Rust plugin with a `tests/locales/ru.json` fixture could not be checked,
/// built or dev-run: N1 hard-errored on any `<dir>/locales/<code>.json` and
/// told the author it was "packed, digested and signed", which is false for a
/// language whose packer never walks `tests/`.
#[test]
fn n1_errors_only_on_a_stray_that_actually_ships() {
    let dir = scratch("n1");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::write(dir.join("Cargo.toml"), "[package]\nname = \"fixture\"\n").unwrap();
    fs::create_dir_all(dir.join("tests/locales")).unwrap();
    fs::write(dir.join("tests/locales/ru.json"), r#"{"a.b":"x"}"#).unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    // No top-level locales/, but a Rust bundle contains no `tests/`.
    let f = findings(&dir, &m, Gate::Check);
    assert!(f.errors.is_empty(), "a test fixture is not a release blocker:\n{}", f.errors.join("\n"));
    let n1 = f.notes.iter().find(|n| n.starts_with("[N1]")).expect("it is still said");
    assert!(n1.contains("does not contain it"), "{n1}");

    // The Python case N1 grew teeth for: `src/` IS packed there, so the same
    // shape of file really does ship and really is read by nothing.
    fs::remove_file(dir.join("Cargo.toml")).unwrap();
    fs::write(dir.join("pyproject.toml"), "[project]\nname = \"fixture\"\n").unwrap();
    fs::create_dir_all(dir.join("src/locales")).unwrap();
    fs::write(dir.join("src/locales/en.json"), r#"{"a.b":"x"}"#).unwrap();
    let f = findings(&dir, &m, Gate::Check);
    assert!(
        f.errors.iter().any(|e| e.starts_with("[N1]") && e.contains("src/locales/en.json")),
        "the Python author who ships two copies is the case this rule exists for:\n{:?}",
        f.errors
    );
    let _ = fs::remove_dir_all(&dir);
}

/// Whether a stray ships is asked of the packer, so the two cannot drift.
#[test]
fn is_packed_agrees_with_the_packer_about_every_language() {
    let dir = scratch("packed");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();

    // A floor before the comparison: a language whose roots list is empty
    // would make every case below pass for the wrong reason.
    let roots = crate::commands::build::packed_source_roots("python");
    assert!(!roots.is_empty(), "packed_source_roots stopped naming anything");

    for (marker, rel, packed) in [
        ("Cargo.toml", "src/locales/en.json", false),
        ("Cargo.toml", "locales/en.json", true),
        ("pyproject.toml", "src/locales/en.json", true),
        ("pyproject.toml", "tests/locales/en.json", false),
        ("package.json", "dist/locales/en.json", true),
        ("package.json", "src/locales/en.json", false),
    ] {
        for f in ["Cargo.toml", "pyproject.toml", "package.json"] {
            let _ = fs::remove_file(dir.join(f));
        }
        fs::write(dir.join(marker), "{}").unwrap();
        assert_eq!(is_packed(&dir, rel), packed, "{marker} / {rel}");
    }
    let _ = fs::remove_dir_all(&dir);
}

// ── E18 / E19, the two caps whose numbers arrived before their rules ────────

/// E18's byte half runs BEFORE the parse and does not depend on it.
///
/// The registry checks `entry.bytes.length` before `JSON.parse` precisely so a
/// runaway file is refused without being read, so a file that is both oversized
/// and malformed must produce E18 as well as E6 — the size is what the author
/// has to act on, and it is the half that survives the file being unreadable.
#[test]
fn an_oversized_locale_file_is_refused_before_it_is_parsed() {
    let dir = scratch("e18");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture"}"#,
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    // A floor on the numbers this rule is made of, before the mutation that
    // matters: a cap read as 0 would refuse everything, and a cap read as
    // usize::MAX would refuse nothing while still passing this test's shape.
    let max_bytes = cap("max_locale_bytes");
    let max_keys = cap("max_locale_keys");
    assert!(max_bytes >= 1024 && max_keys >= 10, "{max_bytes} bytes / {max_keys} keys");

    // Malformed AND over the byte cap. `keys` is empty for this file, so the
    // key half cannot fire and the byte half is on its own.
    let big = format!("{{{}", "x".repeat(max_bytes));
    fs::write(dir.join("locales/ru.json"), &big).unwrap();
    let f = findings(&dir, &m, Gate::Check);
    let e18: Vec<&String> = f.errors.iter().filter(|e| e.starts_with("[E18]")).collect();
    assert_eq!(e18.len(), 1, "{:?}", f.errors);
    assert!(e18[0].contains("max_locale_bytes"), "{}", e18[0]);
    assert!(
        f.errors.iter().any(|e| e.starts_with("[E6]")),
        "and the parse failure is still reported: {:?}",
        f.errors
    );

    // The key half, on a file well inside the byte cap.
    let mut many = String::from("{\"listing.name\":\"Fixture\"");
    for i in 0..=max_keys {
        many.push_str(&format!(",\"k.{i}\":\"v\""));
    }
    many.push('}');
    fs::write(dir.join("locales/ru.json"), &many).unwrap();
    assert!(many.len() < max_bytes, "this case must not also trip the byte cap");
    let f = findings(&dir, &m, Gate::Check);
    assert!(
        f.errors.iter().any(|e| e.starts_with("[E18]") && e.contains("max_locale_keys")),
        "{:?}",
        f.errors
    );

    // …and a plugin inside both caps is not told anything about them.
    fs::write(dir.join("locales/ru.json"), r#"{"listing.name":"Фикстура"}"#).unwrap();
    let f = findings(&dir, &m, Gate::Check);
    assert!(!f.errors.iter().any(|e| e.starts_with("[E18]")), "{:?}", f.errors);
    let _ = fs::remove_dir_all(&dir);
}

/// E19 computes the registry's own number, and says so when it cannot.
///
/// The byte count this produces was compared against the bot's own
/// `deriveLocaleText` on the same tree, built from a real scaffold plus nine
/// `locale add`s: **9,775 bytes on both sides**, against a budget of 8,192,
/// with `astra-plugin check` returning `OK` before this rule existed.
///
/// The window matters as much as the arithmetic. The registry derives `summary`
/// with `summarise`, which flattens whitespace and may cut; re-implementing
/// that cut here would be a second copy of the one predicate whose duplication
/// already cost this system a catalogue-wide refusal. So outside the window
/// where `summarise` is provably the identity, this rule computes nothing and
/// says which value stopped it.
#[test]
fn the_listing_i18n_budget_is_the_registrys_own_number() {
    let dir = scratch("e19");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture"}"#,
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    // The floor: the budget and the caps this rule reasons about are real
    // numbers out of the vendored spec, asserted before anything is built to
    // exceed them.
    let budget = cap("max_listing_i18n_bytes");
    let summary_cap = cap("max_summary_length");
    assert!(budget >= 1024 && summary_cap >= 20, "{budget} bytes / {summary_cap} chars");

    // Nine locales of astral-plane text at the summary cap. Each character is
    // one `char` and four bytes, which is the whole point: E14 counts the
    // first, this budget counts the second.
    let name = "\u{1F600}".repeat(cap("max_name_length"));
    let description = "\u{1F600}".repeat(summary_cap);
    for code in LOCALE_CODES.iter().filter(|c| **c != "en") {
        let block = json!({ "listing.name": name, "listing.description": description });
        fs::write(
            dir.join(format!("locales/{code}.json")),
            serde_json::to_string(&block).unwrap(),
        )
        .unwrap();
    }
    let f = findings(&dir, &m, Gate::Check);
    let e19: Vec<&String> = f.errors.iter().filter(|e| e.starts_with("[E19]")).collect();
    assert_eq!(e19.len(), 1, "{:?}", f.errors);
    assert!(
        e19[0].contains("9775 bytes"),
        "9,775 is what astra-registry's own `deriveLocaleText` returned for this exact tree on \
         2026-08-23, and the two agreeing to the byte is the whole claim of this rule. If a cap \
         above moved, this number moves with it — recompute it against the bot rather than \
         against this rule. Got: {}",
        e19[0]
    );
    assert!(e19[0].contains(&budget.to_string()), "{}", e19[0]);

    // Outside the window it refuses to guess, by name.
    fs::write(
        dir.join("locales/ru.json"),
        r#"{"listing.name":"Фикстура","listing.description":"Набор  с двойным пробелом"}"#,
    )
    .unwrap();
    let f = findings(&dir, &m, Gate::Check);
    assert!(
        !f.errors.iter().any(|e| e.starts_with("[E19]")),
        "a budget computed outside its window would refuse a listing the registry accepts:\n{:?}",
        f.errors
    );
    let n16 = f
        .notes
        .iter()
        .find(|n| n.starts_with("[N16]"))
        .expect("and the skip is loud, or it is a rule that quietly stopped running");
    assert!(n16.contains("locales/ru.json"), "{n16}");

    // A plugin whose blocks are ordinary says nothing at all.
    for code in LOCALE_CODES.iter().filter(|c| **c != "en") {
        fs::write(
            dir.join(format!("locales/{code}.json")),
            r#"{"listing.name":"Фикстура","listing.description":"Набор"}"#,
        )
        .unwrap();
    }
    let f = findings(&dir, &m, Gate::Check);
    assert!(f.errors.is_empty(), "{:?}", f.errors);
    assert!(!f.notes.iter().any(|n| n.starts_with("[N16]")), "{:?}", f.notes);
    let _ = fs::remove_dir_all(&dir);
}

/// A stale translation is DEMOTED to English before the budget is measured, on
/// both sides — so the bytes budgeted are the bytes that ship.
///
/// Without this the CLI would count a translation the registry replaces, and
/// the two numbers would disagree in the direction that refuses a listing the
/// registry accepts.
#[test]
fn a_stale_block_is_budgeted_as_the_english_it_falls_back_to() {
    let dir = scratch("e19-stale");
    fs::write(dir.join("plugin.toml"), FIXTURE_MANIFEST).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        r#"{"listing.name":"Fixture","listing.description":"A fixture"}"#,
    )
    .unwrap();
    let m: PluginManifest = toml::from_str(FIXTURE_MANIFEST).unwrap();

    let name = "\u{1F600}".repeat(cap("max_name_length"));
    let description = "\u{1F600}".repeat(cap("max_summary_length"));
    let big = json!({ "listing.name": name, "listing.description": description });
    for code in LOCALE_CODES.iter().filter(|c| **c != "en") {
        fs::write(
            dir.join(format!("locales/{code}.json")),
            serde_json::to_string(&big).unwrap(),
        )
        .unwrap();
    }
    assert!(
        findings(&dir, &m, Gate::Check).errors.iter().any(|e| e.starts_with("[E19]")),
        "the fixture must start over budget, or the assertion below proves nothing"
    );

    // Now say every one of those translations was made against English that has
    // since been rewritten. The bot falls each block back to the English card
    // and then drops it as identical; so must this.
    let mut locales = Map::new();
    for code in LOCALE_CODES.iter().filter(|c| **c != "en") {
        locales.insert(
            (*code).to_string(),
            json!({
                "listing.name": digest("Older name"),
                "listing.description": digest("Older description"),
            }),
        );
    }
    fs::write(
        dir.join(LOCK_FILE),
        serde_json::to_string(&json!({
            "schema": LOCK_SCHEMA, "source": "en", "locales": Value::Object(locales),
        }))
        .unwrap(),
    )
    .unwrap();

    let f = findings(&dir, &m, Gate::Check);
    assert!(
        !f.errors.iter().any(|e| e.starts_with("[E19]")),
        "every block is stale, so every block ships as English and the budget is empty:\n{:?}",
        f.errors
    );
    assert!(
        f.notes.iter().any(|n| n.starts_with("[N3]")),
        "and the staleness itself is still reported: {:?}",
        f.notes
    );
    let _ = fs::remove_dir_all(&dir);
}


/// A block that comes out identical to the English card is DROPPED before the
/// budget is measured, and the tree below is built so that the drop decides.
///
/// **The first version of this test could not decide anything, and the mutation
/// is what said so.** It dropped two blocks equal to a short English card —
/// about 45 bytes each — so removing the rule moved the total by 90 bytes
/// against a budget of 8,192, and `if false` stayed green. A witness has to be
/// built at the line it is testing: here the English card is a 64-character
/// astral name (256 bytes) beside a 200-character Latin description, so a block
/// equal to it costs ~500 bytes and two of them are the difference between
/// 7,602 and 8,594.
#[test]
fn a_block_identical_to_the_english_card_costs_nothing() {
    let dir = scratch("e19-drop");
    let name = "\u{1F600}".repeat(cap("max_name_length"));
    let description = "a".repeat(cap("max_summary_length"));
    // A name outside the Latin script is a NOTE (N12) and not an error — a
    // product name is not prose — which is what makes an English card this
    // wide reachable at all.
    let manifest = format!(
        "[plugin]\nid = \"fixture\"\nname = \"{name}\"\nversion = \"0.1.0\"\n\
         description = \"{description}\"\n\n[entry]\ncommand = \"./bin/fixture\"\n"
    );
    fs::write(dir.join("plugin.toml"), &manifest).unwrap();
    let m: PluginManifest = toml::from_str(&manifest).unwrap();
    fs::create_dir_all(dir.join("locales")).unwrap();
    fs::write(
        dir.join("locales/en.json"),
        serde_json::to_string(&json!({
            "listing.name": name, "listing.description": description,
        }))
        .unwrap(),
    )
    .unwrap();

    let translated = "\u{1F600}".repeat(cap("max_summary_length"));
    let english_card = json!({ "listing.name": name, "listing.description": description });
    let big = json!({ "listing.name": name, "listing.description": translated });
    let codes: Vec<&&str> = LOCALE_CODES.iter().filter(|c| **c != "en").collect();
    assert!(codes.len() >= 9, "{} card locales", codes.len());

    for (i, code) in codes.iter().enumerate() {
        let block = if i < 2 { &english_card } else { &big };
        fs::write(
            dir.join(format!("locales/{code}.json")),
            serde_json::to_string(block).unwrap(),
        )
        .unwrap();
    }
    let f = findings(&dir, &m, Gate::Check);
    assert!(
        !f.errors.iter().any(|e| e.starts_with("[E19]")),
        "the bot drops a block identical to the English card before it measures, so counting \
         those two here refuses a listing the registry accepts:\n{:?}",
        f.errors
    );

    // …and translating one of the two puts the same tree over the budget,
    // which is what proves the case above sat just under the line rather than
    // far below it.
    fs::write(
        dir.join(format!("locales/{}.json", codes[0])),
        serde_json::to_string(&big).unwrap(),
    )
    .unwrap();
    let f = findings(&dir, &m, Gate::Check);
    assert!(
        f.errors.iter().any(|e| e.starts_with("[E19]")),
        "one more translated block is over the budget: {:?}",
        f.errors
    );
    let _ = fs::remove_dir_all(&dir);
}
