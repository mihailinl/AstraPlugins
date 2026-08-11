//! `astra-plugin check --fix`: the changes a checker can make **without
//! guessing**.
//!
//! The bar is deliberately high. A fixer that rewrites something it inferred
//! produces a manifest the author did not write and did not read, and the next
//! person to debug it has to work out which lines are theirs. So each fix here
//! is one where there is exactly one correct value and the current one is
//! provably not it. Everything else stays a warning with the command that fixes
//! it in the message.
//!
//! Rewriting is `toml_edit`, never a reserialize: a `plugin.toml` round-tripped
//! through `toml::Value` loses the author's comments, ordering and formatting,
//! which is a much bigger edit than the one being asked for.

use std::path::Path;

use anyhow::{Context, Result};
use toml_edit::{DocumentMut, Item, value};

/// Apply what can be applied. Returns one line per change, for the report.
pub fn apply(dir: &Path, manifest_path: &Path) -> Result<Vec<String>> {
    let src = std::fs::read_to_string(manifest_path).context("Failed to read plugin.toml")?;
    let mut doc: DocumentMut = src
        .parse()
        .context("plugin.toml does not parse, so --fix cannot safely rewrite it")?;

    let mut applied = Vec::new();
    applied.extend(strip_exe_suffix(&mut doc));
    applied.extend(object_root_on_config_schema(&mut doc));
    applied.extend(missing_required_permissions(&mut doc));

    if !applied.is_empty() {
        std::fs::write(manifest_path, doc.to_string()).context("Failed to write plugin.toml")?;
    }

    applied.extend(versions_agree(dir, &doc)?);
    Ok(applied)
}

/// `entry.command = "target/release/foo.exe"` → `"target/release/foo"`.
///
/// A hardcoded `.exe` is a plugin that cannot start on Linux, and it is the
/// single most common portability defect in this repo's own history: nine of
/// eleven shipped examples had it. The daemon appends the host's executable
/// suffix itself, so the portable spelling is the one without.
fn strip_exe_suffix(doc: &mut DocumentMut) -> Vec<String> {
    let Some(command) = doc
        .get("entry")
        .and_then(|e| e.get("command"))
        .and_then(Item::as_str)
    else {
        return vec![];
    };
    if !command.to_ascii_lowercase().ends_with(".exe") {
        return vec![];
    }
    let command = command.to_string();
    let stripped = command[..command.len() - 4].to_string();
    doc["entry"]["command"] = value(&stripped);
    vec![format!(
        "entry.command `{command}` -> `{stripped}`: a hardcoded .exe cannot start on Linux, and \
         the daemon appends the host's suffix itself"
    )]
}

/// `[config] schema` that parses as a JSON object, declares `properties`, and
/// has no root `"type"`.
///
/// Not a guess: a schema with `properties` is an object schema whatever its
/// root says, and the daemon and every model provider read the root type. A
/// schema that declares a root type — even a surprising one — is the author
/// saying something, and is left alone.
fn object_root_on_config_schema(doc: &mut DocumentMut) -> Vec<String> {
    let Some(schema) = doc
        .get("config")
        .and_then(|c| c.get("schema"))
        .and_then(Item::as_str)
    else {
        return vec![];
    };
    let Ok(mut parsed) = serde_json::from_str::<serde_json::Value>(schema) else {
        return vec![];
    };
    let Some(obj) = parsed.as_object_mut() else {
        return vec![];
    };
    if obj.contains_key("type") || !obj.contains_key("properties") {
        return vec![];
    }
    obj.insert("type".into(), serde_json::json!("object"));
    let rendered = serde_json::to_string_pretty(&parsed).unwrap_or_default();
    doc["config"]["schema"] = value(&rendered);
    vec![
        "[config] schema: added the missing \"type\": \"object\" root (it declares `properties`, \
         so it is an object schema)"
            .to_string(),
    ]
}

/// A declared capability whose host rpc is not granted.
///
/// `[permissions]` is default-deny, so `triggers = true` without `fire_trigger`
/// is a plugin whose own generated example fails at run time with
/// `permission_denied` naming a section the manifest never had. The grant is
/// added with a reason that announces itself as a placeholder — the reason is
/// what the user is shown at install and is the whole basis of their consent,
/// so it is the one thing this must not invent quietly.
fn missing_required_permissions(doc: &mut DocumentMut) -> Vec<String> {
    const NEEDS: &[(&str, &str)] = &[
        ("triggers", "fire_trigger"),
        ("event_handlers", "subscribe_events"),
        ("client", "send_chat_message"),
        ("ui_contributions", "push_to_ui"),
    ];
    const PLACEHOLDER: &str = "TODO: say why, in one line - the user reads this at install";

    let declared: Vec<String> = doc
        .get("capabilities")
        .and_then(Item::as_table)
        .map(|t| {
            t.iter()
                .filter(|(_, v)| v.as_bool() == Some(true))
                .map(|(k, _)| k.to_string())
                .collect()
        })
        .unwrap_or_default();

    let mut added = Vec::new();
    for (cap, perm) in NEEDS {
        if !declared.iter().any(|d| d == cap) {
            continue;
        }
        if doc.get("permissions").and_then(|p| p.get(perm)).is_some() {
            continue;
        }
        if doc.get("permissions").is_none() {
            doc["permissions"] = Item::Table(toml_edit::Table::new());
        }
        // `{ reason = "…" }`, not a bare string. A permission is a
        // `PermissionRequest` (it also carries `types` and `scopes`), and a
        // string here parses in `toml` and then fails the daemon's own
        // deserializer with "expected struct PermissionRequest" — a --fix that
        // produces a manifest the daemon refuses.
        let mut request = toml_edit::InlineTable::new();
        request.insert("reason", PLACEHOLDER.into());
        doc["permissions"][perm] = value(request);
        added.push(format!(
            "[permissions] {perm}: `{cap}` cannot work without it. The reason is a PLACEHOLDER - \
             the user is shown it at install, so write the real one."
        ));
    }
    added
}

/// Every other manifest's version set to `plugin.toml`'s.
///
/// `plugin.toml` is the authority — the release workflow asserts the tag
/// against it — so there is exactly one correct value and no judgement to make.
/// Delegates to `astra-plugin version` so there is one implementation of "which
/// files declare a version".
fn versions_agree(dir: &Path, doc: &DocumentMut) -> Result<Vec<String>> {
    let Some(declared) = doc
        .get("plugin")
        .and_then(|p| p.get("version"))
        .and_then(Item::as_str)
    else {
        return Ok(vec![]);
    };
    let drifted: Vec<(String, String, String)> = crate::commands::version::declared_versions(dir)
        .into_iter()
        .filter(|(_, _, found)| found != declared)
        .collect();
    if drifted.is_empty() {
        return Ok(vec![]);
    }
    crate::commands::version::run(crate::commands::version::VersionOptions {
        path: &dir.to_string_lossy(),
        version: declared,
        // Nothing is being downgraded: plugin.toml already says this, and the
        // other files are being brought into line with it.
        allow_downgrade: true,
    })?;
    Ok(drifted
        .into_iter()
        .map(|(file, what, found)| {
            format!("{file} {what}: '{found}' -> '{declared}' (plugin.toml is the authority)")
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn doc(src: &str) -> DocumentMut {
        src.parse().unwrap()
    }

    #[test]
    fn a_hardcoded_exe_is_stripped_and_everything_else_is_left_alone() {
        let mut d = doc("[entry]\ncommand = \"bin/plugin.exe\"\n");
        let applied = strip_exe_suffix(&mut d);
        assert_eq!(applied.len(), 1);
        assert_eq!(d["entry"]["command"].as_str().unwrap(), "bin/plugin");

        for untouched in ["bin/plugin", "node", "python", "bin/plugin.exec"] {
            let mut d = doc(&format!("[entry]\ncommand = \"{untouched}\"\n"));
            assert!(strip_exe_suffix(&mut d).is_empty(), "rewrote {untouched}");
        }
    }

    #[test]
    fn comments_and_ordering_survive_a_fix() {
        // The reason this uses toml_edit at all. A reserialize would drop the
        // comment and reorder the tables, and the author's diff would be the
        // whole file.
        let src = "# my plugin\n[entry]\n# where cargo puts it\ncommand = \"bin/p.exe\"\n";
        let mut d = doc(src);
        strip_exe_suffix(&mut d);
        let out = d.to_string();
        assert!(out.contains("# my plugin"), "{out}");
        assert!(out.contains("# where cargo puts it"), "{out}");
    }

    #[test]
    fn an_object_schema_missing_its_root_type_gets_one() {
        let mut d = doc("[config]\nschema = '{\"properties\": {\"k\": {\"type\": \"string\"}}}'\n");
        let applied = object_root_on_config_schema(&mut d);
        assert_eq!(applied.len(), 1, "{applied:?}");
        let schema: serde_json::Value =
            serde_json::from_str(d["config"]["schema"].as_str().unwrap()).unwrap();
        assert_eq!(schema["type"], "object");
        assert!(schema["properties"]["k"].is_object(), "properties survived");
    }

    #[test]
    fn a_schema_that_says_something_is_never_overruled() {
        for untouched in [
            // The author declared a root type, even a surprising one.
            "{\"type\": \"string\"}",
            // No properties: nothing here proves it is an object schema.
            "{}",
            // Not JSON: `check` reports that as an error, and a fixer that
            // guesses at broken JSON is a fixer that destroys it.
            "not json",
        ] {
            let mut d = doc(&format!("[config]\nschema = '{untouched}'\n"));
            assert!(
                object_root_on_config_schema(&mut d).is_empty(),
                "rewrote {untouched}"
            );
        }
    }

    #[test]
    fn a_capability_gets_the_permission_it_cannot_work_without() {
        let mut d = doc("[capabilities]\ntriggers = true\n");
        let applied = missing_required_permissions(&mut d);
        assert_eq!(applied.len(), 1, "{applied:?}");
        let reason = d["permissions"]["fire_trigger"]["reason"].as_str().unwrap();
        assert!(
            reason.starts_with("TODO"),
            "the reason must announce itself as a placeholder: {reason}"
        );

        // Idempotent: running --fix twice adds nothing the second time.
        assert!(missing_required_permissions(&mut d).is_empty());
    }

    /// The shape, asserted against the daemon's own parser.
    ///
    /// A permission is a `PermissionRequest` table, not a string. A bare string
    /// round-trips through `toml` happily and then fails the daemon with
    /// "expected struct PermissionRequest" — so `--fix` would have produced a
    /// manifest that no longer installs, which is the worst thing a fixer can
    /// do.
    #[test]
    fn what_fix_writes_parses_as_a_manifest() {
        let mut d = doc(
            "[plugin]\nid = \"p\"\nname = \"P\"\nversion = \"0.1.0\"\n\
             [entry]\ncommand = \"./p\"\n[capabilities]\ntriggers = true\nclient = true\n",
        );
        assert_eq!(missing_required_permissions(&mut d).len(), 2);
        let parsed: astra_plugin_manifest::PluginManifest =
            toml::from_str(&d.to_string()).expect("the daemon's parser must accept it");
        assert!(
            parsed
                .permissions
                .contains(astra_plugin_manifest::Permission::FireTrigger)
        );
    }

    #[test]
    fn a_capability_that_is_off_grants_nothing() {
        let mut d = doc("[capabilities]\ntriggers = false\ntools = true\n");
        assert!(
            missing_required_permissions(&mut d).is_empty(),
            "a permission was granted for a capability the manifest turns off - that is a \
             consent prompt the user would see for a feature that does not exist"
        );
    }

    #[test]
    fn an_existing_grant_is_never_overwritten() {
        let mut d = doc(
            "[capabilities]\ntriggers = true\n[permissions]\nfire_trigger = \"my own reason\"\n",
        );
        assert!(missing_required_permissions(&mut d).is_empty());
        assert_eq!(
            d["permissions"]["fire_trigger"].as_str().unwrap(),
            "my own reason"
        );
    }
}
