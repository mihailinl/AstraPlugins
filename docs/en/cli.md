# `astra-plugin` CLI reference

Every subcommand, flag, and behaviour — sourced from `astra-plugin-cli/src/main.rs` and `astra-plugin-cli/src/commands/`.

## Install

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Run `astra-plugin --help` to see the full command list. Each subcommand also accepts `--help`.

## `astra-plugin create`

Scaffold a new plugin project from a language-specific template.

```bash
astra-plugin create <NAME> [--lang <LANG>] [--capabilities <LIST>] [--output <DIR>]
```

| Argument / flag | Default | Description |
| --- | --- | --- |
| `NAME` | — | Plugin id. Must be lowercase alphanumeric with hyphens — this becomes `[plugin].id` in the manifest. |
| `-l, --lang` | `rust` | One of `rust`, `python` (alias `py`), `typescript` (alias `ts`). |
| `-c, --capabilities` | `tools` | Comma-separated list. Valid tokens: `tools`, `tts`, `stt`, `ai_provider`, `actions`, `triggers`, `client`, `event_handlers`, `ui_panels`. Whitespace around commas is trimmed. |
| `-o, --output` | `./<NAME>` | Destination directory. |

### What gets generated

All scaffolds include:

- `plugin.toml` — manifest pre-filled with id, name, version `0.1.0`, and the `[capabilities]` section flipped on for whatever you requested.
- `proto/plugin.proto` — a local copy of the plugin protocol.
- `.gitignore`, `README.md`.

Language-specific extras:

| Lang | Extra files |
| --- | --- |
| `rust` | `Cargo.toml` (with `astra-plugin-sdk`, `tokio`, `serde`, `anyhow`, `async-trait`), `src/main.rs` with a `PluginCapability` impl stub. `entry.command` set to `target/release/<name>.exe`. |
| `python` | `pyproject.toml` (with `astra-plugin-sdk`, `grpcio`, `protobuf`), `src/plugin.py` with a `Plugin` subclass stub. `entry.command = "python"`, `args = ["-m", "src.plugin"]`, `runtimes = ["python"]`. |
| `typescript` | `package.json`, `tsconfig.json`, `src/index.ts` with a `Plugin` subclass stub. `entry.command = "node"`, `args = ["dist/index.js"]`, `runtimes = ["node"]`. |

## `astra-plugin dev`

Run the plugin in development mode with file watching and automatic rebuild/restart.

```bash
astra-plugin dev [PATH] [--daemon-addr <HOST:PORT>]
```

| Argument / flag | Default | Description |
| --- | --- | --- |
| `PATH` | `.` | Plugin directory (the one containing `plugin.toml`). |
| `--daemon-addr` | `127.0.0.1:50051` | gRPC address of the running Astra daemon. |

### What it does

1. Reads `plugin.toml` and determines the build command per language.
2. Starts a file watcher on the plugin directory (ignoring `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`).
3. Runs the build (`cargo build` for Rust, `bun run build` / `tsc` for TypeScript, `uv pip sync` / nothing for Python).
4. Launches the `entry.command` with `--daemon-addr`, `--plugin-id`, and `--auth-token` appended.
5. On file change: terminates the child, rebuilds, relaunches.

Errors are printed inline. Press `Ctrl+C` to stop.

## `astra-plugin build`

Package the plugin into a distributable `.astraplugin` archive.

```bash
astra-plugin build [PATH] [-o <FILE>]
```

| Argument / flag | Default | Description |
| --- | --- | --- |
| `PATH` | `.` | Plugin directory. |
| `-o, --output` | `<id>-<version>.astraplugin` | Archive path. |

### Per-language build steps

| Lang | Steps |
| --- | --- |
| `rust` | Runs `cargo build --release`, copies the binary into `bin/` inside the archive, rewrites `entry.command` to point at the bundled path. |
| `typescript` | Runs `bun build src/index.ts --outdir dist` or falls back to `npx esbuild`. Bundled JS goes into `dist/` inside the archive. |
| `python` | If `uv` is on `PATH`, generates `requirements.lock` via `uv pip compile`. Copies `src/`, `pyproject.toml`, `requirements.txt`, and the lock file. |

### Archive layout

```
<plugin-id>-<version>.astraplugin           (ZIP file)
├── plugin.toml              # Manifest (entry.command rewritten for Rust)
├── bin/                     # Compiled binary (Rust only)
├── dist/                    # Bundled JS (TypeScript only)
├── src/                     # Python source
├── requirements.txt         # Python deps (unlocked)
├── requirements.lock        # Python deps (resolved by uv)
├── ui/                      # Custom UI (if present)
├── locales/                 # i18n JSON files (if present)
├── icon.png / icon.svg      # Optional branding
├── README.md / LICENSE      # Optional
├── SIGNATURE                # Ed25519 signature (if keypair exists)
└── PUBKEY                   # Signing public key (if keypair exists)
```

If `~/.astra/plugin-keys/private.key` exists, the CLI **automatically signs** the archive on every build — no extra flag needed.

## `astra-plugin validate`

Check the manifest and config schema without building.

```bash
astra-plugin validate [PATH]
```

Validated items:

- Required manifest fields: `plugin.id`, `plugin.name`, `plugin.version`, `entry.command`.
- `plugin.id` is lowercase alphanumeric with hyphens.
- `plugin.version` matches `X.Y.Z` SemVer (warning, not error, if not).
- At least one capability is enabled (warning if all are false).
- `[config].schema`, if present, parses as JSON and has `"type": "object"` at root.
- Metadata warnings: missing `description` or `author`.

Exits non-zero only on hard errors (unparseable TOML, missing required fields).

## `astra-plugin keygen`

Generate an Ed25519 keypair used by `build` to sign archives.

```bash
astra-plugin keygen [--force]
```

| Flag | Description |
| --- | --- |
| `--force` | Overwrite an existing keypair. Without this flag the command refuses to replace existing keys. |

Output locations (created if missing):

- `~/.astra/plugin-keys/private.key` — base64 Ed25519 private seed (keep secret).
- `~/.astra/plugin-keys/public.key` — base64 Ed25519 public key (safe to share).

Once a keypair exists, every `astra-plugin build` automatically appends a `SIGNATURE` entry (HMAC-like digest of each ZIP entry, signed with Ed25519) and a `PUBKEY` entry so consumers can verify authenticity.

## Environment

- `RUST_LOG` — controls verbosity of CLI output. Default is warning level; use `RUST_LOG=debug` for a full trace.
- All CLI commands respect the current shell's `PATH` when looking up `cargo`, `node`, `bun`, `npx`, `python`, and `uv`.
