// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! `I18n`, held to `testdata/i18n/vectors.json` — the same file the other two
//! SDKs read.
//!
//! `I18n` shipped in three languages and had never had a test. It disagreed
//! with itself three ways, silently. A per-SDK test would have pinned each
//! implementation to itself; this one reads the shared vectors, so the question
//! it answers is not "does Rust still do what Rust did" but "do the three still
//! do the same thing". Coupling C17; the other half is `tools/gen-i18n.mjs`,
//! which generates the plural tables from `spec/i18n.yaml` so they cannot be
//! three hand-written copies.
//!
//! Every test asserts a floor on what it loaded before it asserts anything
//! else. An emptied vector file must fail as an emptied vector file.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use astra_plugin_sdk::{I18n, key, plural};
use serde_json::Value;

/// Floors, not counts. Each is well under what the file carries today, so
/// adding a case is free and losing most of them is not. Written before the
/// mutation that proved this test can fail, which is the only order in which a
/// floor means anything.
const MIN_FIXTURES: usize = 5;
const MIN_LOADS: usize = 5;
const MIN_CASES: usize = 30;
const MIN_PLURAL: usize = 35;

/// `testdata/` sits at the repository root, one level up from this crate. It is
/// not inside the packaged `.crate` — these vectors are shared with the Python
/// and TypeScript SDKs and with nothing that depends on this one — so a run
/// from a checkout is the only run that can execute them.
fn vectors_path() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../testdata/i18n/vectors.json")
}

fn vectors() -> Value {
    let path = vectors_path();
    let text = fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!(
            "{}: {e}.\nThis test proves the three SDKs agree about i18n; without the \
             shared vectors it proves nothing, so it fails rather than skipping.",
            path.display()
        )
    });
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
}

fn arr<'a>(doc: &'a Value, field: &str) -> &'a Vec<Value> {
    doc[field]
        .as_array()
        .unwrap_or_else(|| panic!("vectors.json has no array `{field}`"))
}

fn s(v: &Value, field: &str) -> String {
    v[field]
        .as_str()
        .unwrap_or_else(|| panic!("`{field}` is not a string in {v}"))
        .to_string()
}

/// Write a fixture's files into a directory of its own and return it.
fn materialise(root: &Path, doc: &Value, name: &str) -> PathBuf {
    if name == "MISSING" {
        return root.join("never-created");
    }
    let dir = root.join(name);
    fs::create_dir_all(&dir).expect("create fixture dir");
    let files = doc["fixtures"][name]["files"]
        .as_object()
        .unwrap_or_else(|| panic!("no fixture named `{name}`"));
    for (filename, text) in files {
        fs::write(dir.join(filename), text.as_str().expect("file text")).expect("write fixture");
    }
    dir
}

/// One scratch directory for the whole run, removed on the way out.
struct Scratch(PathBuf);

impl Scratch {
    fn new(tag: &str) -> Self {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let dir = std::env::temp_dir().join(format!("astra-i18n-{tag}-{}-{nanos}", std::process::id()));
        fs::create_dir_all(&dir).expect("create scratch dir");
        Scratch(dir)
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn the_vector_file_is_the_one_this_test_was_written_against() {
    let doc = vectors();
    assert_eq!(
        doc["schema"].as_str(),
        Some("astra.i18n.vectors/1"),
        "the vectors file changed shape; this reader has not"
    );
    let fixtures = doc["fixtures"].as_object().expect("fixtures object");
    assert!(
        fixtures.len() >= MIN_FIXTURES,
        "{} fixture(s), floor is {MIN_FIXTURES}",
        fixtures.len()
    );
    for (field, floor) in [
        ("loads", MIN_LOADS),
        ("cases", MIN_CASES),
        ("plural", MIN_PLURAL),
    ] {
        let n = arr(&doc, field).len();
        assert!(n >= floor, "{n} `{field}` vector(s), floor is {floor}");
    }
}

#[test]
fn loading_a_fixture_gives_the_shared_answer() {
    let doc = vectors();
    let scratch = Scratch::new("load");
    let mut failures: Vec<String> = Vec::new();
    let mut ran = 0usize;

    for vector in arr(&doc, "loads") {
        ran += 1;
        let name = s(vector, "name");
        let dir = materialise(&scratch.0, &doc, &s(vector, "fixture"));
        let i18n = I18n::load(&dir);

        let want_langs: Vec<String> = vector["languages"]
            .as_array()
            .expect("languages")
            .iter()
            .map(|v| v.as_str().expect("language code").to_string())
            .collect();
        if i18n.available_languages() != want_langs {
            failures.push(format!(
                "{name}: languages are {:?}, expected {want_langs:?}",
                i18n.available_languages()
            ));
        }

        let want_errors = vector["error_count"].as_u64().expect("error_count") as usize;
        let errors = i18n.load_errors();
        if errors.len() != want_errors {
            failures.push(format!(
                "{name}: {} load error(s), expected {want_errors}: {errors:?}",
                errors.len()
            ));
        }
        let blob = errors.join("\n");
        for needle in vector["errors_contain"].as_array().expect("errors_contain") {
            let needle = needle.as_str().expect("needle");
            if !blob.contains(needle) {
                failures.push(format!("{name}: no load error mentions {needle:?}: {errors:?}"));
            }
        }
    }

    // The floor, and it earned its place: without it this test passed over an
    // emptied vectors file while its three siblings went red. A loop over
    // nothing agrees with everything.
    assert!(ran >= MIN_LOADS, "only {ran} load vector(s) ran, floor is {MIN_LOADS}");
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

#[test]
fn every_case_gives_the_shared_answer() {
    let doc = vectors();
    let scratch = Scratch::new("case");
    let mut failures: Vec<String> = Vec::new();
    let mut ran = 0usize;

    for case in arr(&doc, "cases") {
        let name = s(case, "name");
        let dir = materialise(&scratch.0, &doc, &s(case, "fixture"));
        let i18n = I18n::load(&dir);
        i18n.set_language(&s(case, "language"));
        let k = s(case, "key");

        let got: Value = match s(case, "call").as_str() {
            "t" => Value::String(i18n.t(&k)),
            "has" => Value::Bool(i18n.has(&k)),
            "tf" => {
                let owned: Vec<String> = case["args"]
                    .as_array()
                    .expect("args")
                    .iter()
                    .map(|v| v.as_str().expect("arg").to_string())
                    .collect();
                let borrowed: Vec<&str> = owned.iter().map(String::as_str).collect();
                Value::String(i18n.tf(&k, &borrowed))
            }
            "ta" => {
                let owned = named(case);
                let borrowed: Vec<(&str, &str)> =
                    owned.iter().map(|(a, b)| (a.as_str(), b.as_str())).collect();
                Value::String(i18n.ta(&k, &borrowed))
            }
            "tn" => {
                let owned = named(case);
                let borrowed: Vec<(&str, &str)> =
                    owned.iter().map(|(a, b)| (a.as_str(), b.as_str())).collect();
                let n = case["n"].as_i64().expect("n");
                Value::String(i18n.tn(&k, n, &borrowed))
            }
            "count_prefixed" => Value::from(i18n.count_prefixed(&k)),
            "key" => Value::String(key(&k)),
            other => panic!(
                "{name}: the vectors use a call this test does not implement: {other:?}. \
                 Implement it here rather than dropping the case, or the vector is \
                 carried by two SDKs and not by three."
            ),
        };

        ran += 1;
        if got != case["expect"] {
            failures.push(format!("{name}: got {got}, expected {}", case["expect"]));
        }
    }

    assert!(ran >= MIN_CASES, "only {ran} case(s) ran, floor is {MIN_CASES}");
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

/// Named arguments in a stable order — a `BTreeMap` so the substitution order
/// is the same on every run and in every SDK.
fn named(case: &Value) -> Vec<(String, String)> {
    case["named"]
        .as_object()
        .expect("named")
        .iter()
        .map(|(k, v)| (k.clone(), v.as_str().expect("named value").to_string()))
        .collect::<BTreeMap<_, _>>()
        .into_iter()
        .collect()
}

#[test]
fn the_generated_plural_table_gives_the_shared_answer() {
    let doc = vectors();
    let mut failures: Vec<String> = Vec::new();
    let mut ran = 0usize;

    for vector in arr(&doc, "plural") {
        let lang = s(vector, "language");
        let n = vector["n"].as_i64().expect("n");
        let want = s(vector, "expect");
        let got = plural::category(&lang, n);
        ran += 1;
        if got != want {
            failures.push(format!("{lang} n={n}: got {got:?}, expected {want:?}"));
        }
    }

    assert!(ran >= MIN_PLURAL, "only {ran} plural vector(s) ran, floor is {MIN_PLURAL}");
    assert!(failures.is_empty(), "{}", failures.join("\n"));
}

#[test]
fn every_declared_language_ends_in_other() {
    // `tn` falls back `<key>.<category>` -> `<key>.other` -> `<key>`, so a
    // language whose table did not end in `other` would have counts that
    // resolve to nothing at all.
    assert!(
        plural::CATEGORIES.len() >= 2,
        "the generated table holds {} language(s) — that is a broken generator, not a \
         shrunken vocabulary",
        plural::CATEGORIES.len()
    );
    for (lang, categories) in plural::CATEGORIES {
        assert_eq!(categories.last(), Some(&"other"), "{lang} does not end in `other`");
        assert!(plural::is_declared(lang));
    }
    assert!(!plural::is_declared("zh-CN"));
}
