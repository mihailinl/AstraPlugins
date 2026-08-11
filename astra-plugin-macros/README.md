# astra-plugin-macros

Attribute macros for the Astra plugin SDK.

**Use [`astra-plugin-sdk`](../astra-plugin-sdk/README.md). This crate is its
implementation detail.** It is a hard, non-optional dependency of the SDK,
re-exported as `astra_plugin_sdk::astra` and through
`astra_plugin_sdk::prelude`, and it has no useful API of its own — nothing here
resolves without the SDK in the crate graph, because every token these macros
emit is an `::astra_plugin_sdk::…` path.

Repository: <https://github.com/mihailinl/AstraPlugins>

Not published to crates.io yet — `index.crates.io` has no entry for it.

## What it emits

| Macro | Reached as | What it does |
|---|---|---|
| `plugin` | `#[astra::plugin]` | On an `impl` block: reads the `#[tool]`, `#[action]`, `#[ui_call]` and `#[hook]` members, writes the `PluginCapability` impl, derives `DeclaredCapabilities::CAPS` from the hooks that are really present, and fills in `type Config = NoConfig` when none is declared. `capabilities = "…"` adds ones no hook can imply, such as `dom_access` |
| `main` | `astra::main!(MyPlugin::default())` | The entry point |
| `args` | `#[astra::args]` | `#[derive(Deserialize, JsonSchema)]` aimed at the SDK's own copies of both crates, so a one-dependency plugin can take structured tool arguments. Doc comments become the schema the model reads |
| `config` | `#[astra::config]` | `#[astra::args]` plus `#[serde(default)]`, because the daemon's first config payload to a freshly installed plugin is `{}` |
| `PluginConfig` | `#[derive(PluginConfig)]` | The config-shape impl |
| `tool` `action` `hook` `ui_call` | bare attributes | Markers. `#[astra::plugin]` consumes them before they are ever expanded; the definitions exist so that one written *outside* a plugin impl reports what it is instead of "cannot find attribute" |

There are also shim derives for `Deserialize`, `Serialize` and `JsonSchema`.
They are **not** serde's or schemars' derives — they occupy those names in the
prelude so that `#[derive(Deserialize)]` in a crate whose `Cargo.toml` lists only
`astra-plugin-sdk` fails with a sentence pointing at `#[astra::args]`, instead of
failing inside someone else's expansion with ``can't find crate for `serde` ``.
Adding `serde` yourself keeps working: an explicit `use serde::Deserialize;`
shadows a glob import.

## Why it is not a feature flag

A `macros` feature would mean two documented ways to write the same plugin. The
whole point of this crate is that a plugin is one dependency and fifteen lines;
a flag that could turn that off would make the shorter form the exception.

## Tests

`astra-plugin-sdk` is a **dev-dependency of this crate** — a cycle back onto the
crate that depends on it. Cargo allows exactly this shape, and it is the only
way to test that an expansion compiles and behaves identically to the
hand-written impl it claims to be. The dev-dependency list is deliberately two
entries long: `serde`, `serde_json` and `schemars` are absent, because the test
crate stands in for the author's crate, and the author's crate has one
dependency. Every path these macros emit has to work with nothing but
`astra-plugin-sdk` in the extern prelude, and a test that listed those crates
could not prove it.

## License

MIT.
