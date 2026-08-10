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

[capabilities]
{caps}
"#,
        caps = caps_toml.join("\n"),
    )
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
