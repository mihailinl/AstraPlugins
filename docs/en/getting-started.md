# Getting started

A 5-minute walkthrough: install the CLI, scaffold a Rust tools plugin, run it in dev mode, and build a distributable `.astraplugin` bundle.

## Prerequisites

- A running **Astra daemon** on `127.0.0.1:50051` (the default gRPC port).
- **Rust** 1.75+ (for Rust plugins or to install the CLI from source).
- Optional: **Python** 3.10+ or **Node.js** 20+ if you pick those SDKs.

## 1. Install the CLI

The `astra-plugin` CLI creates, runs, builds, validates, and signs plugins. Install it from the repo:

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Verify:

```bash
astra-plugin --version
```

## 2. Scaffold a plugin

```bash
astra-plugin create hello-world --lang rust --capabilities tools
cd hello-world
```

The CLI accepts `--lang rust|python|ts` and a comma-separated `--capabilities` list. See the [CLI reference](cli.md) for every option.

The scaffolded Rust project contains:

```
hello-world/
├── Cargo.toml          # Depends on astra-plugin-sdk
├── plugin.toml         # Manifest (id, name, entry, capabilities)
├── src/main.rs         # PluginCapability impl with a stub tool
├── proto/plugin.proto  # Copy of the plugin protocol
├── .gitignore
└── README.md
```

Open `src/main.rs` and give your tool a useful body:

```rust
use astra_plugin_sdk::prelude::*;

struct HelloWorld;

#[async_trait]
impl PluginCapability for HelloWorld {
    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef {
            name: "greet".into(),
            description: "Return a greeting for the given name".into(),
            parameters_json: r#"{
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }"#.into(),
        }]
    }

    async fn call_tool(&self, _name: &str, arguments_json: &str) -> ToolResult {
        let args: serde_json::Value = serde_json::from_str(arguments_json)
            .unwrap_or_default();
        let who = args.get("name").and_then(|v| v.as_str()).unwrap_or("world");
        ToolResult::ok(format!("Hello, {who}!"))
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(HelloWorld).await
}
```

## 3. Run in dev mode

```bash
astra-plugin dev
```

This command watches the plugin directory, rebuilds on changes, and restarts the process while reconnecting to the daemon at `127.0.0.1:50051`. Open Astra's chat and ask it to "greet Ada" — the daemon will route the tool call to your plugin and stream the result back into chat.

Ignored directories: `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`.

Point at a non-default daemon with `--daemon-addr`:

```bash
astra-plugin dev --daemon-addr 127.0.0.1:60051
```

## 4. Validate the manifest

```bash
astra-plugin validate
```

Catches missing required fields, invalid SemVer, malformed config schemas. Run this before every build — the daemon will refuse to load plugins that fail validation.

## 5. Build a distributable bundle

```bash
astra-plugin build
```

Produces `hello-world-0.1.0.astraplugin` — a ZIP archive containing the compiled binary, manifest, any UI assets, locales, and (if you have a signing key) an Ed25519 `SIGNATURE` entry.

Output a specific path with `-o`:

```bash
astra-plugin build -o dist/hello-world.astraplugin
```

## 6. (Optional) Generate a signing key

```bash
astra-plugin keygen
```

Creates an Ed25519 keypair at `~/.astra/plugin-keys/{private,public}.key`. Every subsequent `astra-plugin build` automatically signs the archive. Share `public.key` with users who want to verify the bundle.

## 7. Install the plugin

Drag the `.astraplugin` file into the Astra UI's Plugins page, or call the daemon's `SideloadPlugin` RPC. After installation the daemon restarts the plugin process with the correct credentials and it appears in the plugin list.

## Where to go next

- [Rust SDK](sdk-rust.md) — every trait method, `FieldDef` / `UiContribution` builders, `DaemonClient` for client plugins.
- [Python SDK](sdk-python.md) — if you prefer `@tool` / `@action` decorators and auto-schema from type hints.
- [TypeScript SDK](sdk-typescript.md) — class-based API with `@grpc/grpc-js`.
- [Capabilities](capabilities.md) — full reference for tools, TTS, STT, AI provider, actions, triggers, UI contributions, event handlers, and client mode.
- [Publishing](publishing.md) — signing, distribution, upgrade strategy.
