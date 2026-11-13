// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! Reading a `.astra` file into the commands a plugin offers with
//! [`Host::propose_command`](crate::Host::propose_command).
//!
//! A `.astra` file is what Astra's Commands page exports (and what dragging a
//! command out of the list writes) — `{format: "astra-commands", version,
//! commands: [...]}`, or a group's `{format: "astra-group", version, group:
//! {name}, commands: [...]}`. `propose_command` takes ONE command, so the usual
//! path is: build the command in Astra, export it, ship the file with the
//! plugin, and offer each command in it.
//!
//! The same helper is in all three SDKs, held to one set of vectors
//! (`testdata/astra-file/vectors.json`).

use anyhow::{Result, anyhow, bail};
use serde_json::Value;

/// The members removed from every command: the file's own `source_id`, and
/// the LOCAL members of a portable command (Astra's
/// `astra-core/src/command/portable_schema.rs::LOCAL_FIELDS`) — this
/// installation's identity, switch, folder and provenance for it. The daemon
/// drops them from an offer anyway; removing them here keeps the offer to
/// what the person is asked about.
const ASTRA_FILE_LOCAL_FIELDS: &[&str] = &[
    "source_id",
    "id",
    "created_at",
    "updated_at",
    "group_id",
    "enabled",
    "marketplace_source",
    "catalogue_source",
    "plugin_source",
];

/// **The commands in a `.astra` file**, each ready to offer with
/// [`Host::propose_command`](crate::Host::propose_command) (serialise it with
/// `serde_json::to_string`).
///
/// Reads the two formats Astra writes — `"astra-commands"` and
/// `"astra-group"` — and nothing else: text that is not JSON, a top level that
/// is not an object, another `format` (a single command on its own, or the
/// pre-group `"astra-command"`), a `version` that is not a number, a group
/// file whose `group` is not an object, `commands` that is not an array, or a
/// command that is not an object is an error that says which. Each command is
/// returned whole except for its top-level local members — `source_id`, `id`,
/// `created_at`, `updated_at`, `group_id`, `enabled`, `marketplace_source`,
/// `catalogue_source` and `plugin_source`; nothing else about it is checked
/// here — that is the daemon's reader's job, and its refusal names what is
/// wrong.
///
/// A member given twice collapses to the last one, as in the Python and
/// TypeScript helpers: the daemon's strict reader would refuse the duplicate,
/// but this helper parses and re-serialises, so what is offered is the last
/// value alone. A number out of range (`1e400`) is not JSON here. An integer
/// past 2^53 is kept exactly (`u64`), where the TypeScript helper refuses it.
///
/// ```
/// use astra_plugin_sdk::commands_from_astra_file;
///
/// let file = r#"{"format":"astra-commands","version":1,"commands":[
///     {"name":"Good morning","triggers":[{"type":"text","phrases":["good morning"]}],
///      "actions":[],"enabled":true,"source_id":"6f1c2a9e"}]}"#;
/// let commands = commands_from_astra_file(file).unwrap();
/// assert_eq!(commands.len(), 1);
/// assert_eq!(commands[0]["name"], "Good morning");
/// assert!(commands[0].get("enabled").is_none() && commands[0].get("source_id").is_none());
///
/// assert!(commands_from_astra_file(r#"{"name":"one command"}"#).is_err());
/// ```
pub fn commands_from_astra_file(text: &str) -> Result<Vec<Value>> {
    let doc: Value = serde_json::from_str(text)
        .map_err(|e| anyhow!("not a .astra file: it is not JSON ({e})"))?;
    let Some(file) = doc.as_object() else {
        bail!("not a .astra file: it is not a JSON object");
    };
    let format = file.get("format");
    let group = match format.and_then(Value::as_str) {
        Some("astra-commands") => false,
        Some("astra-group") => true,
        _ => bail!(
            "not a .astra file: `format` must be \"astra-commands\" or \"astra-group\", not {}",
            format.map_or_else(|| "missing".to_owned(), Value::to_string)
        ),
    };
    if !file.get("version").is_some_and(Value::is_number) {
        bail!("not a .astra file: `version` must be a number");
    }
    if group && !file.get("group").is_some_and(Value::is_object) {
        bail!("not a .astra group file: `group` must be an object");
    }
    let Some(commands) = file.get("commands").and_then(Value::as_array) else {
        bail!("not a .astra file: `commands` must be an array");
    };
    commands
        .iter()
        .enumerate()
        .map(|(i, command)| {
            let mut command = command
                .as_object()
                .ok_or_else(|| anyhow!("not a .astra file: commands[{i}] is not a JSON object"))?
                .clone();
            for field in ASTRA_FILE_LOCAL_FIELDS {
                command.remove(*field);
            }
            Ok(Value::Object(command))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    /// `testdata/` sits at the repository root, one level up from this crate.
    /// It is not inside the packaged `.crate`; the vectors are shared with the
    /// Python and TypeScript SDKs, so a run from a checkout is the only run
    /// that can execute them — and without them this proves nothing, so it
    /// fails rather than skipping.
    fn vectors() -> Value {
        let path =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../testdata/astra-file/vectors.json");
        let text =
            std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
        serde_json::from_str(&text).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
    }

    #[test]
    fn the_local_fields_are_the_vectors_own() {
        let doc = vectors();
        let listed: Vec<&str> = doc["local_fields"]
            .as_array()
            .expect("local_fields")
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        assert_eq!(listed, ASTRA_FILE_LOCAL_FIELDS);
    }

    #[test]
    fn every_accepted_vector_gives_exactly_its_commands() {
        let doc = vectors();
        let cases = doc["accepted"].as_array().expect("accepted");
        assert!(cases.len() >= 3, "the vectors lost their accepted cases");
        for case in cases {
            let name = case["name"].as_str().unwrap();
            let got = commands_from_astra_file(case["text"].as_str().unwrap())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&Value::Array(got), &case["commands"], "{name}");
        }
    }

    /// Numbers a JavaScript number cannot hold exactly: read exactly here (the
    /// TypeScript helper refuses them rather than round).
    #[test]
    fn unsafe_integers_are_read_exactly() {
        let doc = vectors();
        let cases = doc["unsafe_integers"].as_array().expect("unsafe_integers");
        assert!(cases.len() >= 2, "the vectors lost their unsafe integers");
        for case in cases {
            let name = case["name"].as_str().unwrap();
            let got = commands_from_astra_file(case["text"].as_str().unwrap())
                .unwrap_or_else(|e| panic!("{name}: {e}"));
            assert_eq!(&Value::Array(got), &case["commands"], "{name}");
        }
        let got = commands_from_astra_file(
            r#"{"format":"astra-commands","version":1,"commands":[{"priority":9007199254740993}]}"#,
        )
        .unwrap();
        assert_eq!(got[0]["priority"].as_u64(), Some(9_007_199_254_740_993));
    }

    #[test]
    fn every_refused_vector_is_an_error_that_says_why() {
        let doc = vectors();
        let cases = doc["refused"].as_array().expect("refused");
        assert!(cases.len() >= 10, "the vectors lost their refused cases");
        for case in cases {
            let name = case["name"].as_str().unwrap();
            let err = commands_from_astra_file(case["text"].as_str().unwrap())
                .err()
                .unwrap_or_else(|| panic!("{name}: accepted"))
                .to_string();
            let mentions = case["mentions"].as_str().unwrap();
            assert!(err.starts_with("not a .astra"), "{name}: {err}");
            assert!(
                err.contains(mentions),
                "{name}: `{err}` does not mention {mentions}"
            );
        }
    }
}
