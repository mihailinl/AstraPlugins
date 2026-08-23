//! `astra-plugin new` — scaffold a plugin project.
//!
//! # Templates
//!
//! A template is a *named starting point*, and what it names is a capability
//! set plus the example code for it. That indirection is the point:
//! `--capabilities ui_contributions,dom_access` requires knowing the daemon's
//! vocabulary before writing a line, and the vocabulary is not the question an
//! author has. The question is "I want to add a tool" / "I am writing a speech
//! engine", and `--template tool` / `--template stt` are those sentences.
//!
//! `--capabilities` still works and still wins, because the templates are a
//! shortcut and not a cage.

use std::fs;
use std::path::Path;

use anyhow::{Context, Result};

use crate::output::Verdict;
use crate::templates;
use crate::{hprintln, output};

/// The template names, in the order `--help` should list them.
///
/// `clap` validates against this, so a typo is refused with the list rather
/// than silently scaffolding the default.
pub const TEMPLATE_NAMES: [&str; 9] = [
    "tool",
    "tts",
    "stt",
    "stt-streaming",
    "ai-provider",
    "ui",
    "action-trigger",
    "client",
    "blank",
];

/// What each template asks the generators for.
///
/// `stt-streaming` is `stt` plus a marker the code generators read: same
/// manifest capability (there is only one STT capability), different example —
/// `stt_transcribe_stream` rather than `stt_transcribe`. Which one an author
/// starts from decides whether their plugin can emit partial results at all,
/// and retrofitting the streaming hook onto a finished unary one is the change
/// people get subtly wrong.
///
/// The marker is filtered out before the manifest is written; see
/// [`manifest_capabilities`].
const TEMPLATE_CAPABILITIES: &[(&str, &[&str])] = &[
    ("tool", &["tools"]),
    ("tts", &["tts"]),
    ("stt", &["stt"]),
    ("stt-streaming", &["stt", STREAMING_MARKER]),
    ("ai-provider", &["ai_provider"]),
    ("ui", &["ui_contributions"]),
    ("action-trigger", &["actions", "triggers"]),
    ("client", &["client", "event_handlers"]),
    ("blank", &[]),
];

/// Not a capability — a instruction to the code generators. Never written to a
/// manifest.
pub const STREAMING_MARKER: &str = "stt_streaming";

pub struct NewOptions<'a> {
    pub name: &'a str,
    pub lang: &'a str,
    pub template: &'a str,
    /// Overrides the template's capability set when present.
    pub capabilities: Option<&'a str>,
    pub out_dir: &'a str,
}

pub fn run(opts: NewOptions<'_>) -> Result<Verdict> {
    let name = opts.name;
    if name.is_empty()
        || !name
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
    {
        anyhow::bail!("Plugin name must be lowercase alphanumeric with hyphens");
    }

    let lang = opts.lang.to_lowercase();
    if !["rust", "python", "py", "typescript", "ts"].contains(&lang.as_str()) {
        anyhow::bail!("Supported languages: rust, python (py), typescript (ts)");
    }

    // `--capabilities` beats `--template`; a template with no capability
    // (`blank`) is a real answer and not an empty override.
    let owned: Vec<String>;
    let caps: Vec<&str> = match opts.capabilities {
        Some(list) => {
            owned = list
                .split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect();
            owned.iter().map(String::as_str).collect()
        }
        None => template_capabilities(opts.template)?.to_vec(),
    };

    for cap in manifest_capabilities(&caps) {
        super::validate::check_capability_name(cap)?;
    }

    let out_path = Path::new(opts.out_dir);
    if out_path.exists() {
        anyhow::bail!("Directory '{}' already exists", opts.out_dir);
    }

    fs::create_dir_all(out_path)
        .with_context(|| format!("Failed to create directory '{}'", opts.out_dir))?;

    let manifest_caps = manifest_capabilities(&caps);
    let manifest = templates::generate_manifest(name, &lang, &manifest_caps);
    fs::write(out_path.join("plugin.toml"), manifest)?;

    // No proto is scaffolded: the SDKs own the protocol and ship their own
    // generated stubs. A copy in the author's project could only ever drift.

    // The generators see the marker; the manifest never does.
    match lang.as_str() {
        "rust" => generate_rust_project(out_path, name, &caps)?,
        "python" | "py" => generate_python_project(out_path, name, &caps)?,
        "typescript" | "ts" => generate_typescript_project(out_path, name, &caps)?,
        _ => unreachable!(),
    }

    let readme = templates::generate_readme(name, &lang, &manifest_caps);
    fs::write(out_path.join("README.md"), readme)?;

    // Both of these are the plugin's face in the store, and `astra-plugin
    // build` has always packed them when it found them. Scaffolding the icon
    // rather than mentioning it in the docs is the whole point: a file that
    // exists gets replaced, a file that has to be created from nothing does not.
    let icon = templates::generate_icon(name);
    fs::write(out_path.join("icon.svg"), icon)?;

    let gitignore = templates::generate_gitignore(&lang);
    fs::write(out_path.join(".gitignore"), gitignore)?;

    // The store card's text, and the plugin's own strings. Same argument as the
    // icon above: a `locales/` directory that exists gets edited, and one an
    // author has to learn about from a document does not — which is how a
    // listing reaches the catalogue in a language nobody asked about.
    //
    // The lock goes at the ROOT and not inside `locales/`: every top-level
    // `*.json` in there is loaded as a locale keyed on its stem, so
    // `locales/locales.lock.json` would become a phantom locale named
    // `locales.lock`.
    let (en, lock) = templates::generate_locales(name);
    fs::create_dir_all(out_path.join("locales"))?;
    fs::write(out_path.join("locales").join("en.json"), en)?;
    fs::write(out_path.join(super::locale::LOCK_FILE), lock)?;

    hprintln!("Created plugin project '{name}' at {}/", opts.out_dir);
    hprintln!("Language: {lang}");
    hprintln!("Template: {}", opts.template);
    hprintln!(
        "Capabilities: {}",
        if manifest_caps.is_empty() {
            "none".to_string()
        } else {
            manifest_caps.join(", ")
        }
    );
    hprintln!(
        "Locales: locales/en.json — your store card's text and your plugin's strings."
    );
    hprintln!("         `astra-plugin locale add ru` to translate it.");
    hprintln!();
    hprintln!("Next steps:");
    hprintln!("  cd {}", opts.out_dir);
    match lang.as_str() {
        // --release, because that is where entry.command points.
        "rust" => hprintln!("  cargo build --release"),
        "python" | "py" => hprintln!("  pip install -r requirements.txt"),
        "typescript" | "ts" => hprintln!("  npm install"),
        _ => {}
    }
    hprintln!("  astra-plugin test .");
    hprintln!("  astra-plugin dev .");

    output::emit(
        "new",
        &Verdict::Pass,
        serde_json::json!({
            "name": name,
            "path": opts.out_dir,
            "language": lang,
            "template": opts.template,
            "capabilities": manifest_caps,
        }),
    );
    Ok(Verdict::Pass)
}

/// The capability list a template implies, marker included.
fn template_capabilities(template: &str) -> Result<&'static [&'static str]> {
    TEMPLATE_CAPABILITIES
        .iter()
        .find(|(name, _)| *name == template)
        .map(|(_, caps)| *caps)
        .with_context(|| {
            format!(
                "Unknown template '{template}'. Available: {}",
                TEMPLATE_NAMES.join(", ")
            )
        })
}

/// The same list with the code-generator markers removed — what may be written
/// to `plugin.toml`.
fn manifest_capabilities<'a>(caps: &[&'a str]) -> Vec<&'a str> {
    caps.iter()
        .copied()
        .filter(|c| !c.is_empty() && *c != STREAMING_MARKER)
        .collect()
}

fn generate_rust_project(out_path: &Path, name: &str, capabilities: &[&str]) -> Result<()> {
    let src_dir = out_path.join("src");
    fs::create_dir_all(&src_dir)?;

    let cargo_toml = templates::rust::generate_cargo_toml(name);
    fs::write(out_path.join("Cargo.toml"), cargo_toml)?;

    let main_rs = templates::rust::generate_main_rs(name, capabilities);
    fs::write(src_dir.join("main.rs"), main_rs)?;

    Ok(())
}

fn generate_python_project(out_path: &Path, name: &str, capabilities: &[&str]) -> Result<()> {
    let src_dir = out_path.join("src");
    fs::create_dir_all(&src_dir)?;

    let plugin_py = templates::python::generate_plugin_py(name, capabilities);
    fs::write(src_dir.join("plugin.py"), plugin_py)?;

    let requirements = templates::python::generate_requirements();
    fs::write(out_path.join("requirements.txt"), requirements)?;

    let pyproject = templates::python::generate_pyproject(name);
    fs::write(out_path.join("pyproject.toml"), pyproject)?;

    // §5.6: every template ships one passing test. Level 1, through the real
    // capability servicer, so a declared-but-unrouted tool fails here.
    let tests_dir = out_path.join("tests");
    fs::create_dir_all(&tests_dir)?;
    fs::write(
        tests_dir.join("test_plugin.py"),
        templates::python::generate_test_py(name, capabilities),
    )?;

    Ok(())
}

fn generate_typescript_project(out_path: &Path, name: &str, capabilities: &[&str]) -> Result<()> {
    let src_dir = out_path.join("src");
    fs::create_dir_all(&src_dir)?;

    let index_ts = templates::typescript::generate_index_ts(name, capabilities);
    fs::write(src_dir.join("index.ts"), index_ts)?;

    let package_json = templates::typescript::generate_package_json(name);
    fs::write(out_path.join("package.json"), package_json)?;

    let tsconfig = templates::typescript::generate_tsconfig();
    fs::write(out_path.join("tsconfig.json"), tsconfig)?;

    // The scaffold's `test` script globs `test/*.test.mjs`. Without this file it
    // matches nothing, and `node --test` reports `pass 0, fail 0` and exits 0 —
    // a green check that asserts nothing, which is worse than no check at all.
    let test_dir = out_path.join("test");
    fs::create_dir_all(&test_dir)?;
    fs::write(
        test_dir.join("plugin.test.mjs"),
        templates::typescript::generate_test_ts(name, capabilities),
    )?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_named_template_has_a_capability_set() {
        for name in TEMPLATE_NAMES {
            assert!(
                template_capabilities(name).is_ok(),
                "`--template {name}` is offered in --help and maps to nothing"
            );
        }
        assert_eq!(
            TEMPLATE_CAPABILITIES.len(),
            TEMPLATE_NAMES.len(),
            "a capability set exists for a template --help does not offer"
        );
    }

    #[test]
    fn every_template_capability_is_one_the_daemon_knows() {
        // The marker is the one exception, and it is filtered before it can
        // reach a manifest. Everything else has to be a real capability, or
        // `astra-plugin new --template x` scaffolds a manifest the daemon
        // refuses to parse.
        for (name, caps) in TEMPLATE_CAPABILITIES {
            for cap in manifest_capabilities(caps) {
                assert!(
                    crate::commands::validate::check_capability_name(cap).is_ok(),
                    "template `{name}` declares `{cap}`, which is not a capability"
                );
            }
        }
    }

    #[test]
    fn the_streaming_marker_never_reaches_a_manifest() {
        let caps = template_capabilities("stt-streaming").unwrap();
        assert!(caps.contains(&STREAMING_MARKER), "the generators need it");
        assert_eq!(
            manifest_capabilities(caps),
            vec!["stt"],
            "plugin.toml must see only real capabilities"
        );
    }

    #[test]
    fn blank_is_blank() {
        assert!(manifest_capabilities(template_capabilities("blank").unwrap()).is_empty());
    }

    #[test]
    fn an_unknown_template_names_the_alternatives() {
        let err = template_capabilities("webhook").unwrap_err().to_string();
        assert!(err.contains("stt-streaming"), "{err}");
    }

    /// A scratch directory, without pulling in `tempfile` for three tests.
    fn scratch(tag: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("astra-new-{tag}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// §5.6: *every* `astra-plugin new` template contains one passing test.
    ///
    /// Rust carries its test inside `src/main.rs`; Python and TypeScript get a
    /// file each. The TypeScript scaffold is the reason this test is worth
    /// having: its `package.json` has always declared `"test": "node --test
    /// test/*.test.mjs"`, and for as long as no `test/` directory was written
    /// that glob matched nothing — `node --test` then reports `pass 0, fail 0`
    /// and exits 0. A green check asserting nothing is worse than no check.
    #[test]
    fn every_scaffold_ships_a_test_that_exercises_the_plugin() {
        let caps = vec!["tools"];

        let py = scratch("py");
        generate_python_project(&py, "gate-py", &caps).unwrap();
        let py_test = fs::read_to_string(py.join("tests/test_plugin.py")).unwrap();
        assert!(py_test.contains("def test_"), "no test function:\n{py_test}");
        assert!(
            py_test.contains("Harness") && py_test.contains("call_tool(\"hello\""),
            "the Python test must drive the scaffolded tool through the harness:\n{py_test}"
        );
        // The class it imports has to be the class the scaffold defines.
        let py_src = fs::read_to_string(py.join("src/plugin.py")).unwrap();
        assert!(py_src.contains("class GatePy(Plugin):"), "{py_src}");
        assert!(py_test.contains("from src.plugin import GatePy"), "{py_test}");
        let _ = fs::remove_dir_all(&py);

        let ts = scratch("ts");
        generate_typescript_project(&ts, "gate-ts", &caps).unwrap();
        let ts_test = fs::read_to_string(ts.join("test/plugin.test.mjs")).unwrap();
        assert!(ts_test.contains("test("), "no test:\n{ts_test}");
        assert!(
            ts_test.contains("Harness") && ts_test.contains("callTool(\"hello\""),
            "the TypeScript test must drive the scaffolded tool:\n{ts_test}"
        );
        // The glob in `package.json` has to match the file we just wrote.
        let pkg = fs::read_to_string(ts.join("package.json")).unwrap();
        assert!(pkg.contains("test/*.test.mjs"), "{pkg}");
        let _ = fs::remove_dir_all(&ts);

        let rs = scratch("rs");
        generate_rust_project(&rs, "gate-rs", &caps).unwrap();
        let rs_src = fs::read_to_string(rs.join("src/main.rs")).unwrap();
        assert!(rs_src.contains("#[cfg(test)]"), "{rs_src}");
        assert!(rs_src.contains("Harness::new"), "{rs_src}");
        let _ = fs::remove_dir_all(&rs);
    }

    /// No template may scaffold a required hook that refuses to answer.
    ///
    /// `astra-plugin test` is this project's own conformance suite, and a fresh
    /// scaffold has to pass it on the first run — otherwise the first red run an
    /// author ever sees is one they did not cause, which teaches them that red
    /// is normal. The TTS and STT templates used to `bail!`/`throw`/`raise` in
    /// exactly the hook their capability makes required, so
    /// `astra-plugin new --template tts && astra-plugin test .` failed out of
    /// the box in all three languages.
    #[test]
    fn no_template_scaffolds_a_hook_that_refuses_to_answer() {
        for (template, caps) in TEMPLATE_CAPABILITIES {
            let py = templates::python::generate_plugin_py("demo", caps);
            let ts = templates::typescript::generate_index_ts("demo", caps);
            let rs = templates::rust::generate_main_rs("demo", caps);

            for (lang, src) in [("python", &py), ("typescript", &ts), ("rust", &rs)] {
                for refusal in ["NotImplementedError", "not yet implemented", "not implemented yet"]
                {
                    assert!(
                        !src.contains(refusal),
                        "template `{template}` ({lang}) scaffolds a hook that refuses to \
                         answer ({refusal:?}); `astra-plugin test` fails on it out of the box"
                    );
                }
            }

            // A declared capability whose required hook is simply absent fails
            // the same way, as UNIMPLEMENTED. `ai_provider` is the one that got
            // missed: Python and TypeScript scaffolded an empty plugin for it.
            if caps.contains(&"ai_provider") {
                assert!(py.contains("ai_complete"), "python `{template}`:\n{py}");
                assert!(ts.contains("complete("), "typescript `{template}`:\n{ts}");
                assert!(rs.contains("ai_complete"), "rust `{template}`:\n{rs}");
            }
        }
    }

    /// `--template stt-streaming` must scaffold the STREAMING hook.
    ///
    /// It is the only thing separating it from `--template stt`: both declare
    /// the same single `stt` capability, and the hook the author starts from is
    /// what decides whether their plugin can ever emit a partial result.
    #[test]
    fn the_streaming_template_scaffolds_the_streaming_hook() {
        let streaming = template_capabilities("stt-streaming").unwrap();
        let unary = template_capabilities("stt").unwrap();

        let py = templates::python::generate_plugin_py("demo", streaming);
        assert!(py.contains("async def stt_transcribe_stream"), "{py}");
        let ts = templates::typescript::generate_index_ts("demo", streaming);
        assert!(ts.contains("async *transcribeStream"), "{ts}");
        let rs = templates::rust::generate_main_rs("demo", streaming);
        assert!(rs.contains("stt_transcribe_stream"), "{rs}");

        // And `--template stt` must still scaffold the unary one, or the two
        // templates are the same template.
        let py = templates::python::generate_plugin_py("demo", unary);
        assert!(!py.contains("stt_transcribe_stream"), "{py}");
        let ts = templates::typescript::generate_index_ts("demo", unary);
        // The unary template MENTIONS `transcribeStream` in a comment pointing
        // at it; what it must not do is implement it.
        assert!(!ts.contains("async *transcribeStream"), "{ts}");
        assert!(ts.contains("transcribe: ("), "{ts}");
    }

    /// A scaffold must not warn about the SDK it was scaffolded with.
    ///
    /// The Python capability types are dataclasses now; a hook that returns a
    /// bare dict still works for one more minor and emits a
    /// `DeprecationWarning` naming the replacement. Emitting that on a freshly
    /// generated plugin's first daemon call teaches the author to ignore the
    /// warning, which is the opposite of what it is for.
    #[test]
    fn the_python_scaffold_uses_the_types_it_tells_authors_to_use() {
        for (template, caps) in TEMPLATE_CAPABILITIES {
            let caps = manifest_capabilities(caps);
            let src = templates::python::generate_plugin_py("demo", &caps);
            assert!(
                !src.contains("\"parameters_json\":"),
                "template `{template}` returns a raw tool dict; use `@tool`:\n{src}"
            );
            if caps.contains(&"tts") {
                assert!(
                    src.contains("VoiceInfo("),
                    "template `{template}` returns a raw voice dict:\n{src}"
                );
            }
        }
    }
}
