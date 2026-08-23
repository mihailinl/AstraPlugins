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

    // The same function `generate_locales` uses, because `en.json`'s
    // `listing.name` must equal this byte for byte — E8 compares them here and
    // the registry compares them again at ingest, after the tag.
    let name_title = title_case(name);

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
/// `locales/en.json` and `locales.lock.json` for a fresh scaffold.
///
/// **Scaffolded rather than documented, for the reason this file already gives
/// about the icon: a file that exists gets replaced, a file that has to be
/// created from nothing does not.** An author who never sees a `locales/`
/// directory writes their store card once, in whatever language they think in,
/// and finds out at ingest.
///
/// # Why the labels in the generated source are LITERAL ENGLISH
///
/// The daemon resolving `$keys` for action labels, trigger labels and UI
/// contributions is **new code on Astra's `main` and is in no Astra release**.
/// The newest tag is `v0.2.0` (2026-08-16); the resolver merged on 2026-08-22.
/// So a scaffold that emitted `key("action.example.label")` would hand every
/// author created between now and that release a plugin whose command editor
/// reads `$action.example.label` on a fresh install — on every daemon in the
/// world, with nothing the author can do about it and no error anywhere to
/// explain it.
///
/// The keys below are the ones that work TODAY on every daemon:
/// `listing.*` is read by the registry's ingest bot straight out of the bundle
/// (no daemon involved at all), and `msg.done.*` is the runtime plane, which is
/// the plugin's own `I18n` and has never needed anything from the host.
///
/// # Why `msg.done.*` is conditional
///
/// It used to be unconditional, and no generated source referenced it in any
/// language — two keys an author finds in a file, cannot trace to anything, and
/// reasonably deletes. The generated source now resolves them where the
/// scaffold has somewhere to resolve them, [`uses_runtime_plane`] is the
/// predicate that says where, and a scaffold outside it gets the two
/// `listing.*` keys and no invented ones.
///
/// **What would change this**, precisely: an Astra RELEASE whose tag contains
/// the label resolver. At that point this function emits `key(...)` in the
/// generated source and `generate_manifest` starts writing a
/// `min_astra_version` naming that release — which it does not write today,
/// because there is no number to write. `tools/check-locales.py --rules C22`
/// watches for exactly that and fails when it happens, so the flip is a red
/// build rather than a paragraph somebody has to remember.
pub fn generate_locales(name: &str, capabilities: &[&str]) -> (String, String) {
    let title = title_case(name);
    let runtime = if uses_runtime_plane(capabilities) {
        ",\n  \"msg.done.one\": \"Handled {n} item\",\n  \"msg.done.other\": \"Handled {n} items\""
    } else {
        ""
    };
    let en = format!(
        r#"{{
  "listing.name": "{title}",
  "listing.description": "An Astra plugin"{runtime}
}}
"#
    );
    // The lock is EMPTY and that is correct: it records which translations were
    // made against which English, and there are no translations yet. It is
    // scaffolded anyway so that `astra-plugin locale add ru` has something to
    // update rather than something to invent, and so that the file is in the
    // bundle from the first build — `build.rs`'s root allowlist has to name it,
    // and an allowlist nobody exercises is an allowlist with a hole in it.
    let lock = format!(
        r#"{{
  "schema": "{}",
  "source": "en",
  "locales": {{}}
}}
"#,
        crate::commands::locale::LOCK_SCHEMA
    );
    (en, lock)
}

/// Does the generated source for these capabilities resolve `msg.done.*`?
///
/// One predicate, read by the seed above and by the three code generators, so
/// a key in `en.json` and a `tn(…)` in the source cannot arrive separately —
/// which is exactly how the two used to disagree.
///
/// `actions` and not `tools`: every language's scaffolded tool returns a string
/// its own generated test asserts byte-for-byte, and a scaffold whose first
/// `cargo test` fails would be a worse trade than two unused keys ever were.
pub fn uses_runtime_plane(capabilities: &[&str]) -> bool {
    capabilities.contains(&"actions")
}

pub fn generate_readme(name: &str, lang: &str, capabilities: &[&str]) -> String {
    let name_title = title_case(name);

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

## How this file is used

When this plugin is listed, Astra's store shows this README on the plugin's
page — so what you write here is what someone reads while deciding whether to
install it. `icon.svg` next to `plugin.toml` becomes the store card's picture;
replace it with your own.

Screenshots work, and are the reason to add any:

```markdown
![The command editor, mid-roll](docs/screenshot.png)
```

Commit the images to this repository and link them with a **relative path**.
The registry rewrites those to point at the exact commit your release was built
from, so a picture cannot change after somebody approved the listing. Images
hosted anywhere but GitHub are dropped rather than rendered — a remote image is
a request from the user's machine, made before they have installed anything.

Raw HTML is stripped, so use markdown for layout.
"#,
        caps = capabilities.join(", "),
    )
}

/// The placeholder icon, as a 16×16 pixel-art plug.
///
/// `.` is the coloured plate, `#` the plug face, `o` its shadow. Sixteen
/// characters per row, sixteen rows — the map IS the picture, so editing it
/// needs no arithmetic.
const ICON_PIXELS: [&str; 16] = [
    "................",
    "................",
    "....##....##....",
    "....##....##....",
    "..############..",
    "..###########o..",
    "..###########o..",
    "..###########o..",
    "..###########o..",
    "..#ooooooooooo..",
    "....########....",
    "....#######o....",
    "......####......",
    "......###o......",
    "......###o......",
    "................",
];

/// Plate colours, all of which a near-white foreground reads against.
///
/// Astra's store renders on a light or a dark background depending on the
/// user's theme, and a picture that is mostly one or the other disappears into
/// half of them. A saturated plate carries its own contrast either way, which
/// is why the icon is a coloured square rather than a transparent glyph.
const ICON_PLATES: [&str; 8] = [
    "#2f6df6", "#7c3aed", "#db2777", "#dc2626", "#ea580c", "#ca8a04", "#059669", "#0891b2",
];

/// Generate `icon.svg` — the plugin's picture in Astra's store.
///
/// Scaffolded rather than left to the author, because an icon nobody adds is
/// the default outcome: `astra-plugin build` has always packed `icon.svg` when
/// it found one, and no generated project has ever contained one, so every
/// plugin ever scaffolded shipped without a picture and the store rendered a
/// wall of identical cards. A file that already exists gets replaced; a file
/// that has to be created from nothing does not.
///
/// The plate colour is chosen from the plugin's id so two plugins in a list are
/// usually different colours. Deliberately not random: scaffolding the same
/// name twice has to produce the same bytes, or the CLI's own tests cannot
/// assert anything about its output.
pub fn generate_icon(name: &str) -> String {
    // FNV-1a. Any stable hash would do; this one is four lines and has no deps.
    let mut hash: u32 = 0x811c_9dc5;
    for byte in name.as_bytes() {
        hash ^= u32::from(*byte);
        hash = hash.wrapping_mul(0x0100_0193);
    }
    let plate = ICON_PLATES[(hash as usize) % ICON_PLATES.len()];

    let mut rects = String::new();
    for (y, row) in ICON_PIXELS.iter().enumerate() {
        // Merge horizontal runs of one colour into a single <rect>. A rect per
        // pixel would be 256 of them, and this file is read by humans.
        let cells: Vec<char> = row.chars().collect();
        let mut x = 0;
        while x < cells.len() {
            let ch = cells[x];
            let mut run = 1;
            while x + run < cells.len() && cells[x + run] == ch {
                run += 1;
            }
            if let Some(fill) = match ch {
                '#' => Some("#f8fafc"),
                'o' => Some("#94a3b8"),
                _ => None,
            } {
                rects.push_str(&format!(
                    "  <rect x=\"{x}\" y=\"{y}\" width=\"{run}\" height=\"1\" fill=\"{fill}\"/>\n"
                ));
            }
            x += run;
        }
    }

    let title = title_case(name);
    format!(
        r#"<!-- Replace me. This is a placeholder so your plugin has *a* picture
     from the first minute; it is not a house style and nothing expects your
     icon to look anything like it.

     `astra-plugin build` packs whichever of these it finds next to plugin.toml,
     and Astra's store draws it on your card:

         icon.png   icon.webp   icon.svg   icon.jpg   icon.ico

     PNG with a transparent background is the usual answer. Draw it square; it
     is displayed at about 64px, so it wants a bold silhouette rather than fine
     detail, and it should read on both a light and a dark background because
     the store follows the user's theme.

     If you do ship an SVG, keep it static: no <script>, no on* handlers, no
     <foreignObject>, and no reference to anything off this machine. The
     registry drops an icon carrying any of those, and your plugin would list
     with no picture at all. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="64" height="64"
     shape-rendering="crispEdges" role="img" aria-label="{title}">
  <title>{title}</title>
  <rect width="16" height="16" fill="{plate}"/>
{rects}</svg>
"#
    )
}

/// `dice-roller` → `Dice Roller`.
///
/// Three callers now, and that is the point of it being one function: the
/// icon's `<title>`, `plugin.toml`'s `name`, and `locales/en.json`'s
/// `listing.name`. The last two must be byte-identical — E8 compares them, and
/// the registry compares them again at ingest, after the tag. `generate_manifest`
/// used to carry its own inlined copy of this loop.
fn title_case(name: &str) -> String {
    name.split('-')
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().to_string() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
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
