//! Embedded templates for plugin scaffolding.

pub mod python;
pub mod rust;
pub mod typescript;

/// Generate a `plugin.toml` manifest.
pub fn generate_manifest(name: &str, lang: &str, capabilities: &[&str]) -> String {
    let caps_toml: Vec<String> = capabilities
        .iter()
        .map(|c| format!("{c} = true"))
        .collect();

    let (command, args, runtimes) = match lang {
        // Where `cargo build --release` actually puts it, with cargo's
        // hyphen→underscore crate-name mangling. `./bin/<name>` used to be
        // scaffolded here; cargo never produces that path, so every freshly
        // created Rust plugin failed `astra-plugin build` on every OS.
        // `astra-plugin build` rewrites this to `./bin/<binary>` inside the
        // archive, and resolves the real path from `cargo metadata` anyway.
        "rust" => (
            format!("target/release/{}", name.replace('-', "_")),
            String::new(),
            String::new(),
        ),
        "python" | "py" => (
            "python".into(),
            "args = [\"-m\", \"src.plugin\"]".into(),
            "runtimes = [\"python\"]".into(),
        ),
        "typescript" | "ts" => (
            "node".into(),
            "args = [\"dist/index.js\"]".into(),
            "runtimes = [\"node\"]".into(),
        ),
        _ => ("./plugin".into(), String::new(), String::new()),
    };

    let name_title = name
        .split('-')
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().to_string() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ");

    format!(
        r#"[plugin]
id = "{name}"
name = "{name_title}"
version = "0.1.0"
description = "An Astra plugin"
author = ""
license = "MIT"

[entry]
command = "{command}"
{args}
{runtimes}

# `[capabilities]` is what the daemon may call INTO this plugin.
[capabilities]
{caps}

{permissions}"#,
        caps = caps_toml.join("\n"),
        permissions = generate_permissions(capabilities),
    )
}

/// The `[permissions]` block for a freshly scaffolded plugin.
///
/// `[permissions]` is the other direction from `[capabilities]`: which host
/// RPCs the plugin may call **out** to. It is **default-deny** — a manifest
/// with no `[permissions]` section may call nothing beyond `Register`,
/// `PluginLog` and `GetPluginSelfConfig`, so declaring `triggers = true` is not
/// what lets `fire_trigger` through.
///
/// That is why this exists. Before it, `astra-plugin new x --capabilities
/// triggers` scaffolded a plugin whose own generated comment said to call
/// `ctx.host().fire_trigger(..)` and whose manifest guaranteed that call would
/// come back `permission_denied` — a failure the author could only diagnose at
/// runtime, against a daemon, after writing the trigger.
///
/// Two rules, and the split matters:
///
/// * A permission a declared capability **cannot work without** is written out,
///   with a reason placeholder. `triggers` without `fire_trigger` is not a
///   plugin, it is a dead manifest.
/// * Everything else is written **commented out**. The reason string is shown
///   to the user at install time and is the whole basis of consent, so a
///   scaffold must not pre-request a permission the plugin does not use —
///   least of all `set_theme_contribution` or `dom_access`, which
///   `HIGH_RISK_PERMISSIONS` gives its own consent checkbox and
///   `TIER2_REFUSED_PERMISSIONS` refuses outright to a sideloaded bundle.
///
/// Ids are the wire spellings in `astra_plugin_manifest::permissions::
/// PERMISSION_NAMES`; `permission_ids_are_the_ones_the_manifest_crate_knows`
/// pins them to that list, so a rename there fails here instead of scaffolding
/// a manifest the daemon rejects.
fn generate_permissions(capabilities: &[&str]) -> String {
    // (permission id, the capability that requires it, reason placeholder)
    const REQUIRED: &[(&str, &str, &str)] = &[
        (
            "fire_trigger",
            "triggers",
            "Fires the triggers this plugin declares, so your commands can react to them",
        ),
        (
            "subscribe_events",
            "event_handlers",
            "Receives the Astra events this plugin reacts to",
        ),
        (
            "send_chat_message",
            "client",
            "Sends messages into the conversation on your behalf",
        ),
    ];

    // Not implied by any capability, or optional within one. Commented out.
    const OPTIONAL: &[(&str, &str)] = &[
        ("set_variable", "write a variable your commands can read"),
        (
            "push_to_ui",
            "push updates to a UI panel this plugin contributes",
        ),
        (
            "set_theme_contribution",
            "repaint the active theme (high risk: its own consent checkbox)",
        ),
        (
            "dom_access",
            "reach into the Astra window's DOM (high risk: refused to a sideloaded bundle)",
        ),
    ];

    let mut out = String::from(
        "# `[permissions]` is the other direction: which host RPCs the plugin may call\n\
         # out to. Default-deny — a manifest with no `[permissions]` section may call\n\
         # nothing beyond Register, PluginLog and GetPluginSelfConfig, so declaring a\n\
         # capability above is not what lets the matching host call through. This is.\n\
         #\n\
         # `reason` is shown to the user at install time and is the entire basis of\n\
         # their consent. Rewrite these to say what YOUR plugin does with the call, and\n\
         # delete any line you do not actually need.\n\
         [permissions]\n",
    );

    for (id, cap, reason) in REQUIRED {
        if capabilities.contains(cap) {
            out.push_str(&format!("{id} = {{ reason = \"{reason}\" }}\n"));
        }
    }

    out.push_str("\n# Uncomment only what you call, and say why:\n");
    for (id, what) in OPTIONAL {
        out.push_str(&format!("# {id} = {{ reason = \"…\" }}   # {what}\n"));
    }

    out
}

/// Generate a README.md.
pub fn generate_readme(name: &str, lang: &str, capabilities: &[&str]) -> String {
    let name_title = name
        .split('-')
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().to_string() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ");

    format!(
        r#"# {name_title}

An Astra plugin providing: {caps}.

## Development

Language: {lang}

```bash
astra-plugin dev .
```

## Build

```bash
astra-plugin build
```

This produces a `.astraplugin` file for distribution.
"#,
        caps = capabilities.join(", "),
    )
}

/// Generate a .gitignore.
pub fn generate_gitignore(lang: &str) -> String {
    let mut lines = vec![
        "# Build artifacts",
        "*.astraplugin",
        "",
    ];

    match lang {
        "rust" => lines.extend_from_slice(&["target/", ""]),
        "python" | "py" => lines.extend_from_slice(&[
            "__pycache__/",
            "*.pyc",
            ".venv/",
            "requirements.lock",
            "",
        ]),
        "typescript" | "ts" => lines.extend_from_slice(&[
            "node_modules/",
            "dist/",
            "",
        ]),
        _ => {}
    }

    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_manifest::PERMISSION_NAMES;

    /// Every capability that pulls a permission in, in one list.
    const EVERY_PERMISSIONED_CAPABILITY: &[&str] = &[
        "tools",
        "triggers",
        "event_handlers",
        "client",
        "ui_contributions",
        "dom_access",
    ];

    /// Every id this module can write must be one the manifest crate knows.
    ///
    /// The scaffold is the one place an id is typed as a string literal rather
    /// than derived from the enum, because it is emitted into TOML the author
    /// then edits. A rename in `permissions.rs` has to fail here, not in a
    /// `permission_denied` the author reads six steps later.
    #[test]
    fn permission_ids_are_the_ones_the_manifest_crate_knows() {
        let block = generate_permissions(EVERY_PERMISSIONED_CAPABILITY);

        let mut seen = 0;
        for line in block.lines() {
            // Both `id = { .. }` and `# id = { .. }`.
            let line = line.trim_start_matches("# ").trim();
            let Some((id, _)) = line.split_once(" = {") else {
                continue;
            };
            assert!(
                PERMISSION_NAMES.contains(&id),
                "the scaffold writes `{id}`, which astra-plugin-manifest does not \
                 know. Known ids: {PERMISSION_NAMES:?}"
            );
            seen += 1;
        }
        assert!(
            seen >= 4,
            "parsed only {seen} permission lines from:\n{block}"
        );
    }

    /// A capability whose host call is default-denied must arrive granted.
    #[test]
    fn a_triggers_scaffold_may_actually_fire_a_trigger() {
        let manifest = generate_manifest("d", "rust", &["tools", "triggers"]);
        assert!(
            manifest.contains("\nfire_trigger = { reason = \""),
            "a scaffolded triggers plugin whose manifest does not request \
             `fire_trigger` gets `permission_denied` from the daemon on the very \
             call its own generated comment tells the author to make:\n{manifest}"
        );
    }

    /// …and a plugin that declares no such capability must not pre-request it.
    /// The reason string is the basis of the user's consent; asking for what you
    /// do not use is how that stops meaning anything.
    #[test]
    fn a_tools_only_scaffold_requests_nothing() {
        let manifest = generate_manifest("p", "rust", &["tools"]);
        let granted: Vec<&str> = manifest
            .lines()
            .skip_while(|l| !l.starts_with("[permissions]"))
            .skip(1)
            .filter(|l| !l.trim_start().starts_with('#') && l.contains(" = {"))
            .collect();
        assert!(
            granted.is_empty(),
            "a tools-only scaffold pre-requests {granted:?}"
        );
    }

    /// The two high-risk ids are never granted by a scaffold, whatever it
    /// declares: `TIER2_REFUSED_PERMISSIONS` refuses both to a sideloaded
    /// bundle, so a scaffold that requested them would produce a plugin the
    /// author cannot install by the very route `astra-plugin dev` uses.
    #[test]
    fn the_high_risk_ids_are_only_ever_commented_out() {
        // The permissions block only: `[capabilities]` legitimately carries
        // `dom_access = true`, which is the plugin declaring what it is, not the
        // manifest requesting consent to reach the DOM.
        let block = generate_permissions(EVERY_PERMISSIONED_CAPABILITY);
        for id in ["set_theme_contribution", "dom_access"] {
            for line in block.lines().filter(|l| l.contains(id)) {
                assert!(
                    line.trim_start().starts_with('#'),
                    "the scaffold grants `{id}`, which TIER2_REFUSED_PERMISSIONS \
                     refuses outright to a sideloaded bundle: {line}"
                );
            }
        }
    }

    /// The generated manifest has to be a manifest — the daemon's own parser is
    /// the oracle, and it is the same crate `astra-plugin check` runs.
    #[test]
    fn every_generated_manifest_parses_with_the_daemons_own_parser() {
        for caps in [
            &["tools"][..],
            &["tools", "triggers"][..],
            EVERY_PERMISSIONED_CAPABILITY,
        ] {
            for lang in ["rust", "python", "typescript"] {
                let toml_src = generate_manifest("x", lang, caps);
                let parsed: astra_plugin_manifest::PluginManifest = toml::from_str(&toml_src)
                    .unwrap_or_else(|e| panic!("{lang} {caps:?}: {e}\n{toml_src}"));
                assert!(
                    parsed.permissions.unknown().is_empty(),
                    "{lang} {caps:?} requests unknown permissions: {:?}",
                    parsed.permissions.unknown()
                );
            }
        }
    }
}
