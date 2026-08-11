# The Rust SDK

`astra-plugin-sdk` 0.6.0. One dependency, and everything the macros expand to
comes through it.

<!-- doctest: illustrative reason="a Cargo.toml fragment; the scaffold this line comes from is built by every rust-plugin block on this page" -->
```toml
[dependencies]
astra-plugin-sdk = "0.6"
```

0.6 is the first release whose `HostClient` attaches `x-session-token`. Against
0.5 and earlier the daemon answers `unauthenticated` on every host call, so do
not relax that bound.

## The shape of a plugin

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Timer;

#[astra::plugin]
impl Timer {
    /// Start a countdown. Use it when the user asks to be reminded in N minutes.
    #[tool]
    async fn start_timer(&self, ctx: &PluginContext, a: Minutes) -> Result<String, ToolError> {
        if a.minutes == 0 {
            return Err(ToolError::BadArguments("give me at least a minute".into()));
        }
        ctx.host().log_info(&format!("timer for {}m", a.minutes)).await?;
        Ok(format!("timer set for {} minutes", a.minutes))
    }

    /// Runs from the command editor rather than from the model.
    #[action(label = "Cancel all timers")]
    async fn cancel_all(&self, ctx: &PluginContext) -> Result<String, ActionError> {
        ctx.host().log_info("cancelled").await?;
        Ok("cancelled".into())
    }

    /// A trigger a user can attach a command to.
    #[hook]
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![TriggerTypeDef {
            r#type: "timer_elapsed".into(),
            label: "Timer elapsed".into(),
            ..Default::default()
        }]
    }
}

#[astra::args]
struct Minutes {
    /// How many minutes to wait
    minutes: u32,
}

astra::main!(Timer::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn the_manifest_and_the_code_agree() {
        let h = Harness::new(Timer::default()).start().await.unwrap();

        assert_eq!(h.tools().await.len(), 1);
        assert_eq!(h.action_types().await.len(), 1);
        assert_eq!(h.trigger_types().await[0].r#type, "timer_elapsed");

        // The schema is derived from `Minutes`, not hand-written, so it cannot
        // disagree with what the handler parses.
        h.assert_schema_matches::<Minutes>("start_timer").await;
    }
}
```

`#[astra::plugin]` implements `PluginCapability` from the hooks it finds, and
derives the declared capability set from them — so a plugin cannot claim a
capability its code does not serve. `astra-plugin check` compares that against
`plugin.toml`.

## The macro layer

| | What it is for |
|---|---|
| `#[astra::plugin]` | On the `impl` block. Turns the members below into the trait |
| `#[tool]` | A function the model may call. The doc comment is its description |
| `#[action(label = "…")]` | A step in the command editor |
| `#[hook]` | Any other `PluginCapability` method, by name |
| `#[ui_call]` | A method your UI contribution can call back into |
| `#[astra::args]` | On a tool's argument struct |
| `#[astra::config]` | On your settings struct — `args` plus `#[serde(default)]` |
| `astra::main!(Plugin::default())` | The `main` that runs it |

**Why `#[astra::args]` rather than `#[derive(Deserialize, JsonSchema)]`:**
serde's derive expands to `extern crate serde as _serde`, which resolves in the
extern prelude and cannot be reached through a re-export. The plain derive would
therefore need `serde` in your own `Cargo.toml` — the one thing the one-dependency
promise is about. `#[astra::args]` is those two derives with `crate = "…"`
pointing at the SDK's copies. Adding `serde` yourself still works; then
`use serde::Deserialize;` shadows the prelude's name.

You can also implement `PluginCapability` by hand. The trait is public, every
method has a default, and the macros produce exactly what you would write.

## `PluginContext`

Every handler is handed a `&PluginContext`. It is never `None`, it is cheap to
clone into a background task, and it means nothing has to live on your struct
behind a lock.

| | |
|---|---|
| `ctx.host()` | `&Arc<dyn Host>` — the ten host RPCs. Always present |
| `ctx.daemon()` | `Option<&Arc<dyn Daemon>>` — **`Some` only for `client` plugins** |
| `ctx.language()` | The Astra UI language, updated by `OnLanguageChanged` |
| `ctx.active_triggers()` | Which of your trigger types a command is currently listening for |
| `ctx.plugin_id()` | Your id |

From a place a parameter cannot reach — a `Drop` impl, a callback from a C
library, a `std::thread` spawned at startup — `astra_plugin_sdk::ctx()` returns
the running plugin's context, and `try_ctx()` the fallible version.

### `Host` — the ten calls out

| Method | Permission |
|---|---|
| `log_debug` / `log_info` / `log_warn` / `log_error` / `log` | none |
| `get_config` | none |
| `get_daemon_info` | none |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope)` | `set_variable` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(…)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

`set_variable` takes **three** arguments — name, value and scope. Event
subscription is not on `Host`: declare `subscribed_events()` and the runner owns
the stream (below).

`Host` is a trait, so a test can substitute `RecordingHost` and assert on what
your plugin told Astra.

### `Daemon` — present in the SDK, refused by the daemon

> **`ctx.daemon()` does not work today, for any plugin.** The daemon-side half
> is not in place. Every plugin — `client = true` or not — is registered as
> `ClientType::PluginClient`, and the daemon's auth interceptor rejects that
> identity on **any** path that does not start `/astra.PluginHostService/`,
> with `permission_denied("plugin session tokens are scoped to
> PluginHostService")`. `DaemonClient` connects with exactly that token
> (`astra-plugin-sdk/src/host_client.rs` hands `client_session_token` to
> `DaemonClient::connect`), so every call below — `submit_user_message`,
> `subscribe_chat_events`, `speak`, `get_settings` — returns
> `permission_denied` at run time. A canary in the daemon's `consistency.rs`
> keeps the scoping check in place, so this is deliberate and not a regression:
> the reverse-auth half is unbuilt, not broken.
>
> **`Host::send_chat_message` is the only working way to drive an AI turn**, and
> it works for any plugin that has been granted `send_chat_message`.

The API surface, for when the daemon side lands: `ctx.daemon()` is `Some` only
when the plugin declares `client = true` and `is_client()` returns true. It
reaches seven services — core, chat, voice, command, config, media, monitor —
with methods including `submit_user_message`, `subscribe_chat_events`,
`stop_generation`, `list_conversations`, `speak`, `start_listening`,
`execute_command`, `get_settings`, `get_system_stats`. It is
`submit_user_message`, not `send_message`.

## Errors

Handlers return `Result<_, ToolError>` (`ActionError` is an alias for the same
type). A per-call failure is data the AI loop reads and acts on, so it travels
in the response rather than as a gRPC status.

| Variant | Use it when |
|---|---|
| `BadArguments(String)` | The model can fix this by calling again differently |
| `NotFound(String)` | Unknown id, 404 |
| `NotConfigured { field, message }` | A setting is missing. `field` is a deep-link target |
| `Unauthorized(String)` | Credentials refused, or a permission was not granted |
| `RateLimited { retry_after, message }` | An upstream quota. `None` means unknown, not "immediately" |
| `Unavailable(String)` | A dependency is down; retry later unchanged |
| `Timeout(String)` | Ran out of time |
| `Internal(String)` | A bug. Nothing the model can act on |

`?` works on `serde_json::Error`, `std::io::Error`, `tonic::Status` and
`anyhow::Error`. `with_doc_url(…)` wraps any of them with a page that documents
*that* failure, which the UI renders as a link.

Full taxonomy, including the wire strings and the Python/TypeScript spellings:
[`reference/errors.md`](../reference/errors.md).

## Events

Declare what you want; the runner subscribes, reconnects and dispatches.

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Watcher;

#[astra::plugin]
impl Watcher {
    /// Requires `[permissions] subscribe_events = { types = [...] }` — and the
    /// daemon enforces that allowlist, not this list.
    #[hook]
    fn subscribed_events(&self) -> Vec<String> {
        vec!["command_completed".into(), "state_changed".into()]
    }

    #[hook]
    async fn on_command_completed(
        &self,
        ctx: &PluginContext,
        e: astra_plugin_sdk::events::CommandCompletedEvent,
    ) {
        let _ = ctx
            .host()
            .log_info(&format!("{} finished, success={}", e.command_name, e.success))
            .await;
    }

    /// The catch-all, called for every event as well as the typed handlers.
    #[hook]
    async fn on_event(&self, _ctx: &PluginContext, event_type: &str, _payload_json: &str) {
        let _ = event_type;
    }
}

astra::main!(Watcher::default());
```

Typed events today: `StateChangedEvent`, `CommandTriggeredEvent`,
`CommandCompletedEvent`. Chat events are a different stream —
`on_conversation_event`, fed by the daemon's firehose, for `client` plugins.

`on_chat_sync` / `ChatSyncEvent` do not exist. The event was retired and no SDK
has the method; if you are porting code that used it, use `is_client()` plus
`on_conversation_event`.

## Testing

Two levels, both shipped with the SDK so your `Cargo.toml` stays at one line.

| | What it drives | What it can see |
|---|---|---|
| `testing::Harness` | the hooks, in process, against a `RecordingHost` | tools, actions, triggers, config, events, UI calls, and every host call you made |
| `testing::WireHarness` | a real process, started the way the daemon starts it | registration, the session token, streaming audio, the things only the wire has |

`RecordingHost` gives you `fired_triggers()`, `logs()`, `variables()`,
`ui_pushes()`, `chat_messages()`, plus `deny(rpc)`, `fail(rpc, err)` and
`fail_next(rpc, err)` to stage the failures your users will hit.

And a level above both: `astra-plugin test` starts your built binary against a
mock daemon and drives every hook your capabilities imply. That one does not
care what language wrote the plugin.

## What this SDK cannot do yet

- **`ctx.daemon()` / `DaemonClient` is non-functional.** The daemon scopes every
  plugin's session token to `PluginHostService`, so all seven services answer
  `permission_denied` — including for `client = true` plugins. Use
  `Host::send_chat_message`. See [`Daemon`](#daemon-present-in-the-sdk-refused-by-the-daemon)
  above.
- **`TtsSynthesizeStream` is bound and unrouted.** The SDK serves it; no daemon
  call site exists. Implement it if you like — nothing will call it until
  [the parity table](../reference/parity.md) says `live`.
- **`AiGetModels` is deprecated** (0.6, removed in 0.8) and called by nobody:
  the model picker hardcodes `supports_model_discovery = false`. There is no
  replacement; `AiComplete` carries the chosen model on the request.
- **The 0.5 trait surface lives on as `astra_plugin_sdk::compat`**, deprecated
  in 0.6 and removed in 0.8. See [migrating to 0.6](../migration-0.6.md).
- **`PluginCapability::source_id()`** is deprecated: pass the id to
  `Host::send_chat_message`, since the daemon stopped filtering by source id.
- **The capability server's inbound auth is staged.** A missing `x-plugin-token`
  is accepted with a warning until the daemon ships its half; see
  [architecture](../1-orientation/architecture.md).

## See also

[Hook table for Rust](../hooks/rust.md) · [parity](../reference/parity.md) ·
[errors](../reference/errors.md) ·
[versioning and deprecation policy](../versioning.md)
