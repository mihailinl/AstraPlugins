# astra-plugin-sdk (Rust)

Write a plugin for Astra in Rust. One dependency, fifteen lines.

Repository: <https://github.com/mihailinl/AstraPlugins>

## Installing today

**Do not run `cargo add astra-plugin-sdk` yet.** crates.io has 0.5.0. The
daemon rejects every host RPC but `Register` without an `x-session-token`, and
**0.6.0 is the first release whose `HostClient` attaches one** — a 0.5.0 plugin
starts, answers inbound hooks, and gets `unauthenticated` on every `log`,
`fire_trigger` and `set_variable` it attempts. 0.5.0 also predates
`#[astra::plugin]`; it does not have the API below at all.

Until 0.6.0 ships, depend on this checkout:

```bash
git clone -b feat/plugin-production https://github.com/mihailinl/AstraPlugins
```

```toml
[dependencies]
astra-plugin-sdk = { path = "../AstraPlugins/astra-plugin-sdk" }
```

> **The branch is not optional here.** A bare `git clone` checks out the default
> branch, where this crate is **0.5.0** — the version the paragraph above tells
> you not to use. `#[astra::plugin]` does not exist there (`git grep astra::plugin
> master -- astra-plugin-sdk` finds nothing) and neither does the
> `astra-plugin-macros` crate that provides it, so the first sample below fails
> to compile on a macro the README itself uses. Check
> `AstraPlugins/astra-plugin-sdk/Cargo.toml` says `version = "0.6.0"` before
> going on. `feat/plugin-production` is not pushed yet
> (`git ls-remote origin`), so for now this means a local checkout of that
> branch; delete this note once it is the default.

That is exactly what the nine Rust examples in this repository do, and what CI
builds. Once 0.6.0 is on crates.io the line becomes `astra-plugin-sdk = "0.6"`
and nothing else changes — that is already what `astra-plugin new` writes.

`edition = "2024"`, so Rust 1.85 or newer.

### Why one dependency

`tokio`, `serde_json`, `anyhow`, `async_trait` and `schemars` all arrive through
`astra_plugin_sdk::prelude`, and every path the macros expand to is
`::astra_plugin_sdk::…`. `serde`'s derives are the one thing a re-export
**cannot** supply — `serde_derive` emits `extern crate serde as _serde`, which
resolves in the extern prelude and nowhere else. That is what `#[astra::args]`
and `#[astra::config]` are for. Adding `serde` to your own `Cargo.toml` still
works and shadows the prelude's names.

## The smallest working plugin

```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct MyPlugin;

#[astra::plugin]
impl MyPlugin {
    /// Say hello. Describe when to use the tool, not how it works.
    #[tool]
    async fn hello(&self) -> Result<String, ToolError> {
        Ok("Hello from the plugin!".into())
    }
}

astra::main!(MyPlugin::default());
```

The doc comment is the tool's description — the sentence the model reads to
decide whether to call it. `#[astra::plugin]` reads the `#[tool]`, `#[action]`,
`#[ui_call]` and `#[hook]` members and derives both the trait impl and the
capability set, so your `plugin.toml` and your code cannot claim different
things; `astra-plugin check` compares the built binary against the manifest to
prove it.

`astra-plugin new my-plugin` writes this file, a `plugin.toml`, and the test
below. Verified: `cargo test` on a fresh scaffold passes.

## Structured arguments

```rust
#[astra::args]
struct Roll {
    /// How many dice to roll
    #[serde(default)]
    count: u32,
    /// How many sides each die has
    sides: u32,
}

#[derive(Default)]
struct DiceRoller;

#[astra::plugin]
impl DiceRoller {
    /// Roll dice. Use for any request that involves dice or random numbers.
    #[tool]
    async fn roll(&self, args: Roll) -> Result<String, ToolError> {
        Ok(format!("{} d{}", args.count, args.sides))
    }
}
```

`#[astra::args]` is `#[derive(Deserialize, JsonSchema)]` aimed at the SDK's own
copies of both crates. The doc comments become the schema the model reads. A
field without `#[serde(default)]` is required.

Settings use `#[astra::config]` — the same, plus `#[serde(default)]` on the
struct, because the daemon's first config payload to a freshly installed plugin
is `{}`.

## Config

`PluginCapability::Config` is a required associated type. `#[astra::plugin]`
fills in `type Config = NoConfig;` when you declare no config type; `NoConfig`
deserializes from anything and keeps nothing, so a user who adds keys to a
plugin that reads none does not break it.

## Talking back to Astra

Handlers can take `ctx: &PluginContext`:

```rust
#[tool]
async fn roll(&self, ctx: &PluginContext, args: Roll) -> Result<String, ToolError> {
    ctx.host().log_info("rolling").await?;
    ctx.host().fire_trigger("on_roll_value", r#"{"value":20}"#).await?;
    Ok("20".into())
}
```

`ctx.host()` is `&Arc<dyn Host>` — the outbound RPCs every plugin may attempt.
`ctx.daemon()` is `Option<&Arc<dyn Daemon>>`, `Some` only for a plugin whose
`is_client()` returns `true`.

> **`ctx.daemon()` does not reach anything yet.** The daemon registers every
> plugin as `ClientType::PluginClient` and its auth interceptor rejects that
> identity on any gRPC path outside `/astra.PluginHostService/`, so all seven
> daemon services answer `permission_denied` — `client = true` plugins included.
> `Host::send_chat_message` is the only working way to drive an AI turn. The
> daemon-side half of this is unbuilt; the SDK surface is here first.

**Every one of those calls is default-deny.** A manifest with no `[permissions]`
section may call `Register`, `PluginLog`, `GetPluginSelfConfig` and
`GetDaemonInfo`, and nothing else. `fire_trigger` needs

```toml
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

and the `reason` is what the user reads on the install consent sheet. A refused
call comes back as `ToolError` with code `UNAUTHORIZED` and one sentence — not
as `Internal`, and not as tonic's `Display` — so the AI loop stops retrying a
call that can never succeed. This is the first failure most authors meet.

## Errors

`ToolError` / `ActionError` carry one of eight codes shared with the Python and
TypeScript SDKs: `BAD_ARGUMENTS`, `NOT_FOUND`, `NOT_CONFIGURED`, `UNAUTHORIZED`,
`RATE_LIMITED`, `UNAVAILABLE`, `TIMEOUT`, `INTERNAL`. A failure stays **in-band**
(`success: false`) rather than becoming a gRPC status, because the assistant has
to read it. `ToolError::not_configured("api_key")` is what turns "the tool
failed" into a link to the exact settings field.

## Testing

Two levels, both in `astra_plugin_sdk::testing`, so `[dev-dependencies]` stays
empty:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn it_starts_and_answers() {
        let h = Harness::new(MyPlugin::default())
            .with_config(json!({}))
            .start()
            .await
            .expect("the plugin started");

        let answer = h.call_tool("hello", json!({})).await.expect("the tool answered");
        assert_eq!(answer, "Hello from the plugin!");

        assert!(h.health().await.0);
    }
}
```

- **`Harness`** — level 1. In process, no daemon, no socket. `h.host().logs()`,
  `.fired_triggers()`, `.variables()` say what the plugin told Astra;
  `h.host().deny("fire_trigger")` stages the refusal a user's `[permissions]`
  would produce.
- **`WireHarness`** / **`MockDaemon`** — level 2. A real gRPC server, a real
  `Register` handshake, a real session token, real protobuf encoding. The only
  place a descriptor mismatch or the auth interceptor can be checked at all.
  `MockDaemon::unauthenticated_calls()` lists every host RPC that arrived
  without a valid token; `astra-plugin test` asserts that list is empty over a
  real plugin process.

The block above is the generated scaffold's own test, verbatim, and it passes.

## What this SDK does not do

- **No isolation.** Your plugin is a native process with the user's full
  privileges. Permissions constrain what the *daemon* will do for you; nothing
  constrains what your process does to the machine.
- `TtsSynthesizeStream` is bound here and **no daemon call site exists** — it is
  a hook the daemon does not yet call. `AiGetModels` is deprecated and still
  bound so old plugins get `UNIMPLEMENTED` rather than a transport error. Both
  are listed under "Findings" in the generated hook-parity page, which
  `tools/parity` renders from [`spec/hooks.yaml`](../spec/hooks.yaml).

## Upgrading from 0.5

`astra_plugin_sdk::compat` is the 0.5 surface — the trait, `ToolResult` /
`ActionResult` / `UiCallResult`, and `HostClient` / `DaemonClient` as
`Arc<dyn Host>` / `Arc<dyn Daemon>` — forwarded onto the 0.6 trait by a blanket
impl. Changing one import line, `prelude::*` → `compat::*`, builds an 0.5 plugin
against 0.6. It is removed in 0.8.

Full list, in the order the compiler reports it:
the 0.6 migration guide under [`docs/en/`](../docs/en/README.md). Everything breaking
is in [`CHANGELOG.md`](CHANGELOG.md).

## License

**MPL-2.0** — see [LICENSE](LICENSE).

Using this crate does not affect your plugin's licence. MPL is file-level
copyleft: modify one of these files and that file's source must be published;
everything else you write stays yours, proprietary if you want. It is MPL
rather than LGPL precisely so static linking carries no relinking obligation.

Attribution: see [NOTICE](NOTICE). Nothing is required beyond keeping the
headers in the source files.

Copyright (C) 2026 Minice — https://minice.ai
