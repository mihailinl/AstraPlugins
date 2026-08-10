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
├── SIGNATURE                # Only if you ran `astra-plugin sign` — retiring
└── PUBKEY                   # Only if you ran `astra-plugin sign` — retiring
```

### Trust

`build` **never signs**, whatever is in `~/.astra/plugin-keys/`. Its last line says so:

```
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
```

That is the truth about the artifact and not a limitation to work around. A key you hold is checked against nothing on a user's machine; what Astra checks is `sha256` of the whole file against a registry record that countersigns it. See [What establishes trust](publishing.md#what-establishes-trust).

The practical consequence for you: two builds of the same source produce the same bytes on any machine, so `--reproducible` is a property anyone can verify rather than one only you can.

`--no-sign` is still accepted and does nothing — the pinned release workflow passes it, and dropping the flag would break every author workflow already published. It is removed with the legacy pair.

## `astra-plugin sign`

Append the retiring in-ZIP `SIGNATURE`/`PUBKEY` pair to a bundle `build` has already produced.

```bash
astra-plugin sign <FILE> [--key <PATH>]
```

| Argument / flag | Default | Description |
| --- | --- | --- |
| `FILE` | — | The `.astraplugin` to sign, in place. |
| `--key` | `~/.astra/plugin-keys/private.key` | Path to the Ed25519 seed. A path, never the key itself. |

**This is not a trust signal.** The daemon checks the pair against a pinned *Astra* publisher key, never against the `PUBKEY` in the archive, so a bundle signed with your own key is untrusted exactly as an unsigned one is. Its one genuine use is as a second factor against a GitHub account takeover — an attacker holding your GitHub session can forge a perfect attestation and cannot forge this. Read [Signing](publishing.md#signing) before using it, and skip it if you are unsure.

Signing changes the file, so it changes the `sha256` the registry countersigns. Sign before you upload. Do not sign in CI: the build job holds no secrets by design.

Both this command and the format entries it writes are removed in **astra-plugin 0.5.0 / Astra 0.4.0**.

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

Generate the optional Ed25519 keypair `astra-plugin sign` uses. **You do not need one to publish** — `build` does not read it, and Astra's trust comes from the registry record, not from any key you hold.

```bash
astra-plugin keygen [--force]
```

| Flag | Description |
| --- | --- |
| `--force` | Overwrite an existing keypair. Without this flag the command refuses to replace existing keys. |

Output locations (created if missing):

- `~/.astra/plugin-keys/private.key` — base64 Ed25519 private seed (keep secret).
- `~/.astra/plugin-keys/public.key` — base64 Ed25519 public key (safe to share).

The private key is written 0600 inside a 0700 directory (owner-only DACL on Windows). Nothing reads it unless you run `astra-plugin sign` explicitly.

## Environment

- `RUST_LOG` — controls verbosity of CLI output. Default is warning level; use `RUST_LOG=debug` for a full trace.
- All CLI commands respect the current shell's `PATH` when looking up `cargo`, `node`, `bun`, `npx`, `python`, and `uv`.
