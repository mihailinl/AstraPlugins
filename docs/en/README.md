# Astra Plugin Development

Build plugins for [Astra](https://github.com/Stella) — the AI-powered digital assistant — in Rust, Python, or TypeScript.

Plugins are independent processes that Astra launches as sidecars. They communicate with the daemon over gRPC and can expose AI tools, provide TTS/STT backends, contribute custom actions and triggers to the Command Graph, inject UI panels, or act as full daemon clients.

## Table of contents

| Document | What it covers |
| --- | --- |
| [Getting started](getting-started.md) | Install the CLI, scaffold your first plugin, run it in dev mode, build a distributable bundle |
| [CLI reference](cli.md) | Every `astra-plugin` subcommand with flags, behaviour and exit codes |
| [Rust SDK](sdk-rust.md) | Trait-based API (`PluginCapability`), field builders, `HostClient`, `DaemonClient` |
| [Python SDK](sdk-python.md) | Decorator API (`@tool`, `@action`, `@trigger`), auto-schema from type hints, UV integration |
| [TypeScript SDK](sdk-typescript.md) | Class-based API, capability auto-discovery, `@grpc/grpc-js` runtime |
| [Manifest](manifest.md) | `plugin.toml` reference — every section and field |
| [Capabilities](capabilities.md) | All 9 capabilities, per-SDK API, proto RPCs |
| [Publishing](publishing.md) | `.astraplugin` bundle format, Ed25519 signing, sideloading |

## Architecture at a glance

```
┌────────────────────────┐     gRPC     ┌────────────────────────┐
│        Astra           │◀────────────▶│        Plugin          │
│        daemon          │   localhost  │      (sidecar)         │
│                        │              │                        │
│ PluginHostService ─────┼────────────▶│ HostClient             │
│                        │              │                        │
│ plugin-capability ◀────┼──────────────│ PluginCapability       │
│   service client       │              │   service              │
└────────────────────────┘              └────────────────────────┘
```

- The daemon launches each plugin as a separate process, passing `--daemon-addr`, `--plugin-id`, and optionally `--auth-token` on the command line.
- The plugin starts a gRPC server on a random local port, connects back to the daemon's `PluginHostService`, and **registers** — advertising which capabilities it implements.
- After registration the daemon calls into the plugin's `PluginCapabilityService` for tool calls, action execution, TTS, and lifecycle events.
- The plugin uses `HostClient` to log, fire triggers, read its own config, set variables, or push events to its UI iframes. Client-capable plugins additionally get a full `DaemonClient` with access to Chat, Voice, Command, Media, Monitor and Config services.

## Picking an SDK

| Factor | Rust | Python | TypeScript |
| --- | --- | --- | --- |
| Startup latency | ~10 ms (native binary) | ~300 ms (interpreter + grpcio import) | ~100 ms (Node cold start) |
| Memory footprint | Lowest | Highest | Medium |
| Bundle size | ~5–10 MB binary | ~100 KB source + daemon-managed venv | ~200 KB bundle (esbuild) |
| Best for | Performance-critical, system integration, TTS/STT providers | AI tooling, data processing, ML libraries | Web APIs, JSON-heavy work, UI integrations |
| Type safety | Full (compile time) | Opt-in via hints (runtime schema generation) | Full (compile time) |

All three SDKs are first-class — every capability is available in every SDK. Pick the one that matches the ecosystem you want to pull libraries from.

## Next step

Go to [Getting started](getting-started.md) for the 5-minute walkthrough.
