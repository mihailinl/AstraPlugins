# Architecture

How a plugin process is started, how it proves who it is, and which of the two
gRPC services carries which call.

## The process model

<!-- doctest: illustrative reason="an ASCII diagram of the two services, not code" -->
```
   ┌──────────────────────────┐                  ┌──────────────────────────┐
   │      Astra daemon        │                  │     your plugin          │
   │                          │   spawns with    │     (a separate OS       │
   │  plugin manager ─────────┼──── argv ───────▶│      process, your       │
   │                          │                  │      user account)       │
   │                          │                  │                          │
   │  PluginHostService       │◀── plugin calls ─┤  HostClient              │
   │  (the daemon serves)     │   x-session-token│                          │
   │                          │                  │                          │
   │  capability client ──────┼── daemon calls ─▶│  PluginCapabilityService │
   │                          │   x-plugin-token │  (your plugin serves)    │
   └──────────────────────────┘                  └──────────────────────────┘
             both ends are gRPC over loopback TCP
```

The daemon spawns the process with four arguments. This is the exact command
line, copied from a real `astra-plugin test` run:

<!-- doctest: output from="astra-plugin test . --no-build, in a scaffolded plugin" -->
```
target/release/dice_roller --daemon-addr=127.0.0.1:46495 --plugin-id=dice-roller \
  --auth-token=mock-daemon-spawn-token --capabilities=tools
```

The SDK parses those for you. `--auth-token` is the interesting one: it is a
secret the daemon minted for this spawn, and it is used in **both** directions.

## Startup order

The SDK runs a fixed sequence (`astra-plugin-sdk/src/runner.rs`):

<!-- doctest: illustrative reason="the startup order as prose, quoted from runner.rs" -->
```
bind → register → build ctx → on_config → on_language_changed → on_start → serve
```

- **bind before register**, because the daemon is told the port during
  `Register` and may call back immediately. The listener is already up, so those
  calls queue in the accept backlog instead of being refused.
- **`on_config` before `on_start`**, because a plugin that starts a background
  loop needs its settings first.
- **`on_start` before `serve`**, and an `Err` from it aborts startup: a plugin
  that cannot do its job must not be one the daemon believes is healthy.

Two numbers bound this, both declared once in
[`spec/limits.yaml`](../../../spec/limits.yaml) and generated into every SDK:

| Limit | Value | What happens when you miss it |
|---|---|---|
| `plugin_start_timeout_secs` | 20 | The daemon declares the start a failure and reaps the process |
| `plugin_stop_grace_secs` | 5 | After `Shutdown`, the process group is killed |

## The handshake

1. The daemon spawns the process with `--auth-token=<spawn token>`.
2. The plugin binds a gRPC server on an OS-assigned loopback port.
3. The plugin calls `PluginHostService.Register`, presenting the spawn token,
   its port, its protocol version and its capability list.
4. The daemon answers with a **session token**.
5. Every later plugin → daemon call carries that session token in the
   `x-session-token` metadata header. `Register` is the only exempt path
   (`astra-plugin-sdk/src/auth.rs`); anything else without it comes back
   `unauthenticated`.

Registration, in a real run against the mock daemon `astra-plugin test` starts:

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
INFO astra_plugin_sdk::runner: Starting plugin 'dice-roller', connecting to daemon at 127.0.0.1:46495
INFO astra_plugin_sdk::runner: Plugin gRPC server listening on port 41627
INFO astra_plugin_sdk::runner: Registering with capabilities: ["tools"]
INFO astra_plugin_sdk::runner: Registered successfully. Daemon version: mock, protocol: 1 (accepts 0+)
```

### The other direction

The daemon → plugin direction uses the *same* spawn token, sent back to the
plugin in the `x-plugin-token` header on every call. Your capability server
checks it, and the SDK does that for you.

**You do not configure this.** The daemon sets
`ASTRA_PLUGIN_CAPABILITY_AUTH=require` in your plugin's environment, which tells
the SDK to refuse any capability call that does not carry the token. That is the
daemon announcing its own half rather than anyone matching version numbers: a
daemon old enough not to send the header sets no variable, and the SDK stays at
`CapabilityAuth::Warn` — a **wrong** token rejected, a **missing** one accepted
with one warning — so your plugin keeps working there.

It matters because loopback is not a boundary. Your capability server listens on
`127.0.0.1` with an OS-assigned port, and every process running as your user can
find it. Without the header, finding it was enough to call `CallTool`,
`OnConfigChanged` — repointing your API base URL at someone else's host, after
which your plugin posts its real credentials there — or `Shutdown`.

`astra-plugin test` sets the same variable and presents the same token, so what
you test locally is what runs on a user's machine.

## The two services

| | `PluginCapabilityService` | `PluginHostService` |
|---|---|---|
| Served by | your plugin | the daemon |
| Called by | the daemon | your plugin |
| Governed by | `[capabilities]` | `[permissions]` |
| Hooks | 25 | 10 |

`PluginService` — the third service in the proto — is served by the daemon to
the Astra UI. No plugin ever calls it; `astra-plugin dev` and
`astra-plugin logs` do, as a local client.

Every hook, with its capability, its permission, whether it is required, and the
daemon source line that calls it: [the parity table](../reference/parity.md).

## Health, shutdown and restarts

- `HealthCheck` runs every 15 s and is **not** treated as optional: any error
  from it, `UNIMPLEMENTED` included, marks the plugin dead.
- `Shutdown` is answered and then you exit. The grace is 5 s.
- A panic inside a handler is caught and returned as an error rather than
  unwinding through the gRPC server (`astra-plugin-sdk/src/panics.rs`). A panic
  is still a bug; it just is not an outage.

## Config

A plugin's settings are JSON, stored by the daemon, edited in Astra's settings
UI from the JSON Schema in your `[config]` section. The daemon delivers them
with `OnConfigChanged`, and the plugin can also ask with
`GetPluginSelfConfig` — one of the four calls that needs no permission.

A fresh install's first payload is `{}`, which is why the SDK's config types
default every field. See [config fields](../3-reference/config-fields.md).

The settings file is `<astra config dir>/plugins/<id>/config.json`
([platforms](platforms.md) has the per-OS directory). It **survives an update**
— an update is stop, install, start, and install used to `remove_dir_all` the
directory the user's settings lived in; the daemon now preserves the file and
asserts it in a test (`config_survives_update`, `astra-daemon/src/plugins/manager.rs`),
and a copy packed into the new archive cannot overwrite it. It does **not**
survive an uninstall: `uninstall_plugin` ends in `remove_dir_all`. Anything that
must outlive an uninstall belongs somewhere you own.

## Where the pieces live

| Thing | Path |
|---|---|
| `plugin.toml` schema | `astra-plugin-cli/vendor/astra-plugin-manifest/` — a byte-identical copy of the crate the daemon uses |
| The wire | [`proto/plugin.proto`](../../../proto/plugin.proto), a generated slice of Astra's `astra.proto` |
| Hook table | [`spec/hooks.yaml`](../../../spec/hooks.yaml) |
| Shared numbers | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| Bundle format | [`spec/bundle-v2.md`](../spec/bundle-v2.md) |
