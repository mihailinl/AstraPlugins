# Migrating a plugin to the 0.6 SDKs

For someone with a working 0.5-era plugin. It is in the order you will hit the
problems: **what breaks at runtime before you change a line**, then what breaks
at compile time, then what compiles and behaves differently, then what merely
warns.

The release train is `sdk-v0.6.0`: the Rust crate goes to 0.6.0, the Python and
TypeScript packages to 0.5.0. See [versioning.md](versioning.md) for why the
numbers differ.

Every snippet below is real code from this repository — the nine Rust examples
were ported to 0.6 in commit `134f6d1`, so both sides of every diff exist in git
and are quoted from there.

---

## 0. Why you cannot stay where you are

This is not a "nice new API" release. **An 0.5 plugin is already broken against
the current daemon**, before you change anything:

> The 0.5 `HostClient` sends no `x-session-token`, and the daemon answers
> `unauthenticated` to every host RPC except `Register`.

So `fire_trigger`, `set_variable`, `log`, `push_to_ui` and the rest fail at
runtime, on a machine that is not yours, with a message your user will read as
"the plugin is broken". Registration still succeeds, which is what makes it
confusing: the plugin appears to start and then does nothing.

That is the whole reason 0.6 exists, and the reason the authoring API was
allowed to change in the same release.

---

## 1. The fast path (Rust): one line, and it builds

If you need the plugin working today and the migration next week, change your
import:

<!-- doctest: illustrative reason="a one-line diff of the import, not a compilable file" -->
```diff
-use astra_plugin_sdk::prelude::*;
+use astra_plugin_sdk::compat::*;
```

That is the entire diff. `compat` is the 0.5 trait, the 0.5 result types and the
0.5 `HostClient`/`DaemonClient` shapes, forwarded onto the 0.6 trait by a
blanket impl. Verified on the real 0.5 dice-roller — 255 lines, unmodified apart
from that line:

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
warning: use of deprecated trait `astra_plugin_sdk::compat::PluginCapability`: implement
`astra_plugin_sdk::PluginCapability` (0.6): handlers take a `&PluginContext`, return
`Result<_, ToolError>`, and declare `type Config`. See docs/en/migration-0.6.md. This
trait is removed in 0.8
  --> src/main.rs:92:6
   |
92 | impl PluginCapability for DiceRoller {
   |      ^^^^^^^^^^^^^^^^

warning: `dice_roller` (bin "dice_roller") generated 12 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 16.38s
```

(One warning per deprecated item you touch — eleven of them here, plus one
`unused_mut` that the old `let mut h = host.lock().await` no longer needs.)

It builds, its tools answer, and the host it stored in `set_host` still reaches
the daemon. The SDK's own test suite pins that: seven tests written *against the
0.5 trait*, run through the 0.6 harness, in `astra-plugin-sdk/src/capability.rs`
(`mod compat::tests`).

Three things to know before you rely on it:

- **`compat::*` replaces `prelude::*`; it is not an addition.** Import both and
  you have two traits called `PluginCapability` in scope, and `impl
  PluginCapability for MyPlugin` becomes ambiguous (E0659) instead of
  deprecated.
- **It goes away in 0.8** — two minors, per [versioning.md](versioning.md).
- **Hooks 0.5 never had stay absent.** `ai_complete`, `tts_activate`,
  `stt_load` / `stt_unload` / `stt_load_state` answer `UNIMPLEMENTED` through
  the shim, which the protocol reads as *hook absent*. To implement them you
  have to migrate the trait.

`compat::*` also re-exports the 0.6 names — `PluginContext`, `ToolError`,
`Host`, `Daemon`, `Config`, `NoConfig` — so you can move hooks onto the new
signatures one at a time without the import line changing again. When the last
one is across, swap `compat::*` back to `prelude::*` and the warnings are gone.

The rest of this document is that migration.

---

## 2. What breaks at compile time (Rust)

These are the real errors from building the unmodified 0.5 dice-roller against
0.6 — 15 of them, in five kinds.

### 2.1 `Config` is a required associated type

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0046]: not all trait items implemented, missing: `Config`
  --> src/main.rs:92:1
   |
92 | impl PluginCapability for DiceRoller {
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ missing `Config` in implementation
   |
   = help: implement the missing item: `type Config = /* Type */;`
```

If your plugin has no settings, that is one line:

<!-- doctest: illustrative reason="the single line that satisfies the associated type; the whole impl it belongs to is the block above" -->
```rust
type Config = NoConfig;
```

If it does, declare the type and implement `on_config` — the SDK parses the
daemon's JSON for you. bad-apple, before (`examples/bad-apple/src/main.rs` at
`134f6d1^`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn on_config_changed(&self, config_json: &str) {
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(config_json) {
        let mut cfg = self.config.lock().unwrap();
        if let Some(s) = v.get("render_mode").and_then(|s| s.as_str()) {
            cfg.render_mode = s.to_string();
        }
        if let Some(n) = v.get("opacity").and_then(|n| n.as_f64()) {
            cfg.opacity = n;
        }
        // …three more arms, each silently skipping a field of the wrong type
    }
}
```

and after (`examples/bad-apple/src/main.rs`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
#[derive(Serialize, Deserialize)]
#[serde(default)]
struct BadAppleConfig {
    render_mode: String,
    opacity: f64,
    charset: String,
    color: String,
    #[serde(rename = "loop")]
    do_loop: bool,
}

#[async_trait]
impl PluginCapability for BadApple {
    type Config = BadAppleConfig;

    async fn on_config(&self, _ctx: &PluginContext, config: BadAppleConfig) {
        self.config.store(config);
    }
}
```

Twenty lines to two, and a field of the wrong type is now reported instead of
skipped.

> **Use `#[serde(default)]` (or `#[astra::config]`, which adds it).** The first
> config payload the daemon sends a freshly installed plugin is `{}`. A config
> type with a required field rejects it, `on_config` is then never called even
> once, and your plugin serves every call on `Config::default()` — an empty API
> key, a trigger name that is the empty string. The SDK warns loudly about
> exactly this case, but the log pane is not where you are looking.

`Config<T>` is the lock-free store to keep it in: `self.config.load()` is one
atomic read, and a config rewrite mid-tool-call cannot block it.

### 2.2 Handlers take a `&PluginContext`

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0050]: method `call_tool` has 3 parameters but the declaration in trait
              `astra_plugin_sdk::PluginCapability::call_tool` has 4
   --> src/main.rs:117:24
    |
117 |     async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult {
    |                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ expected 4 parameters, found 3
```

Add `ctx: &PluginContext` (or `_ctx`) after `&self`. It carries `plugin_id`,
`language`, `active_triggers`, `host` and `daemon`; it is cheap to clone; it is
never `None`. mock-stt, before and after:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5 — examples/mock-stt/src/main.rs at 134f6d1^
async fn stt_transcribe(&self, audio: &[u8], sample_rate: u32) -> anyhow::Result<SttEvent> {
```

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.6 — examples/mock-stt/src/main.rs
async fn stt_transcribe(
    &self,
    _ctx: &PluginContext,
    audio: &[u8],
    sample_rate: u32,
    options: &SttOptions,
) -> anyhow::Result<SttEvent> {
```

TTS collapsed its four arguments into one `TtsRequest` at the same time —
tone-tts went from `(&self, text, voice_id, speed, _pitch)` to
`(&self, _ctx, req: TtsRequest)`, reading `req.text`, `req.voice_id`,
`req.speed`.

From a place a parameter cannot reach — a spawned task, a `Drop`,
a callback from someone else's crate — `astra_plugin_sdk::ctx()` returns the
same context.

### 2.3 `set_host` and `set_daemon_client` are gone

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0407]: method `set_host` is not a member of trait `PluginCapability`
  --> src/main.rs:95:5
   |
95 | /     async fn set_host(&self, host: Arc<Mutex<HostClient>>) {
96 | |         *self.host.lock().await = Some(host);
97 | |         info!("Host client received");
98 | |     }
   | |_____^ not a member of trait `PluginCapability`
```

Delete the hook, delete the field, use `ctx.host()`. This one is worth doing
properly rather than through the shim, because the 0.5 shape had a defect in it.
dice-roller, before (`examples/dice-roller/src/main.rs` at `134f6d1^`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
struct DiceRoller {
    default_sides: AtomicU32,
    total_rolls: AtomicU64,
    host: Mutex<Option<Arc<Mutex<HostClient>>>>,
}

fn fire_roll_triggers_bg(&self, results: Vec<u32>, sides: u32) {
    let host = self.host.try_lock().ok().and_then(|g| g.clone());
    let host = match host {
        Some(h) => h,
        None => {
            info!("Cannot fire triggers: host client not available yet");
            return;
        }
    };
    // …
}
```

When a second tool call held that lock, `try_lock` returned `None`, the plugin
logged "host client not available yet", and **fired nothing**. After:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
fn fire_roll_values(&self, ctx: &PluginContext, results: &[u32], sides: u32) {
    let host = ctx.host().clone();
    let results = results.to_vec();
    tokio::spawn(async move {
        for v in results {
            let payload = json!({ "value": v.to_string(), "roll": format!("1d{sides}"), "sum": v.to_string() });
            if let Err(e) = host.fire_trigger("on_roll_value", &payload.to_string()).await {
                let _ = host.log_warn(&format!("failed to fire on_roll_value: {e}")).await;
            }
        }
    });
}
```

`Arc<dyn Host>` has no lock to lose. The same applies to client plugins:
`ctx.daemon()` is `Some` for the whole life of a plugin with the `client`
capability, so every "daemon client not ready" branch goes away. telegram-client
lost its `SharedDaemon` field and this check:

> `Some` is about the handle, not about what it can reach. The daemon scopes
> every plugin's session token to `PluginHostService`, so calls made through
> `ctx.daemon()` currently answer `permission_denied` — see
> [the Rust SDK page](4-sdk/rust.md#daemon--present-in-the-sdk-refused-by-the-daemon).
> This section is about the shape of the migration, not about a path that works
> end-to-end today.

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5
if self.daemon.lock().await.is_none() {
    info!("Daemon client not ready, not starting");
    return;
}
```

### 2.4 `ToolResult` / `ActionResult` / `UiCallResult` are deleted

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0433]: cannot find type `ToolResult` in this scope
```

Handlers return `Result<String, ToolError>` (`ActionError` is an alias for
`ToolError`). The mapping is mechanical:

| 0.5 | 0.6 |
| --- | --- |
| `ToolResult::ok(text)` | `Ok(text)` |
| `ToolResult::err("unknown tool")` | `Err(ToolError::NotFound(…))` |
| `ToolResult::err("bad JSON")` | `Err(ToolError::BadArguments(…))`, or just `?` on the parse |
| `ToolResult::err("no API key")` | `Err(ToolError::not_configured("api_key"))` |
| `UiCallResult::ok(json)` / `::err(msg)` | `Ok(json)` / `Err(ToolError::…)` |

The kind is not decoration. It is what tells the AI loop whether retrying can
possibly help, and `NotConfigured { field }` is what turns "the tool failed"
into a link to that exact settings input. bad-apple, after:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn handle_ui_call(
    &self,
    _ctx: &PluginContext,
    method: &str,
    _params_json: &str,
) -> Result<String, ToolError> {
    match method {
        "getConfig" => Ok(serde_json::to_string(&*self.config.get())?),
        _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
    }
}
```

Note the `?` on `serde_json::to_string`: `From` impls exist for
`serde_json::Error`, `std::io::Error`, `tonic::Status` and `anyhow::Error`, and
each conversion is a claim about which kind the failure is —
`serde_json::from_str(args)?` inside `call_tool` means `BAD_ARGUMENTS`, the one
failure the model can fix by trying again.

If you go through the shim instead, every 0.5 failure becomes
`ToolError::Internal` carrying the same sentence. That is the honest reading of
a string whose author never said what it was, and it is worse than what you can
say yourself in five minutes.

### 2.5 Smaller compile-time breaks

| What | 0.5 | 0.6 |
| --- | --- | --- |
| `discover_capabilities` | a hook | **deleted.** The daemon states the manifest's `[capabilities]` in `ASTRA_PLUGIN_CAPABILITIES` |
| `ActiveTriggers::contains` / `update` | `async`, `tokio::RwLock` | synchronous (`ArcSwap`), and `update` is now `set` |
| `HostClient::new(..)` | constructible | only `connect_bootstrap` → `register` → authenticated client |
| `use astra_plugin_sdk::prelude::{Deserialize, Serialize}` | worked | placeholders that fail with a sentence: use `#[astra::args]`, or add `serde` to your own `Cargo.toml` |
| `on_shutdown()`, `on_event()`, `on_state_changed()` and the other event hooks | no `ctx` | `ctx` first, same as everything else |

---

## 3. What breaks at runtime (it compiles, and behaves differently)

### 3.1 `[permissions]` is default-deny

The one that will bite first on a user's machine, and it is not an SDK change at
all — it is Phase 4. A manifest with no `[permissions]` section may call
`Register`, `PluginLog` and `GetPluginSelfConfig`, and **nothing else**.
`fire_trigger`, `set_variable`, `push_to_ui`, `send_chat_message`,
`subscribe_events` and `set_theme_contribution` each need a declared, granted
permission, and a denial arrives as `PERMISSION_DENIED` → `ToolError::Unauthorized`.

Declaring the capability is not enough. From `examples/dice-roller/plugin.toml`:

<!-- doctest: illustrative reason="an excerpt of the [permissions] block from examples/dice-roller/plugin.toml, not a whole manifest" -->
```toml
# `[permissions]` is the other direction: which host RPCs the plugin may call
# out to. Default-deny — a manifest with no `[permissions]` section may call
# nothing beyond Register, PluginLog and GetPluginSelfConfig, so declaring
# `triggers = true` is not what lets `fire_trigger` through. This is.
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

The `reason` is shown to the user at install time. Write it for them.

### 3.2 Startup order, and `on_start`

0.6 fixes the order: bind → register → build ctx → `on_config` →
`on_language_changed` → `on_start` → serve. `on_start` is new, and returning
`Err` **aborts startup**: the process exits non-zero instead of leaving a plugin
the daemon believes is healthy and that fails every call the same way.

This is where warm-up and background tasks belong. echo-stt moved its audio
thread there, out of `main`; telegram-client moved its whole bot start out of
`set_daemon_client`, which is what removed a race with `on_config_changed`:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
/// Config has already been applied by the time this runs, so the bot token
/// is there and the bot starts once, in one place, instead of racing
/// `set_daemon_client` against `on_config_changed`.
async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
    let daemon = ctx
        .daemon()
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("telegram-client needs the `client` capability"))?;
```

### 3.3 Behaviour that silently changed

- **`ActiveTriggers` has a writer.** In 0.5 nothing ever wrote it, so
  `contains()` always answered false. If you guarded an expensive payload behind
  it, that guard was always closed and is now open — the payload will be built.
- **The STT audio channel holds 500 chunks, not 32.** A streaming recognizer
  that was quietly dropping audio under load no longer is. If you compensated
  for the drops, stop.
- **`source_id()` affects nothing.** The daemon stopped filtering by source id;
  every client sees every event. Deprecated in 0.6, gone in 0.8. Pass the id to
  `Host::send_chat_message` instead.
- **Capabilities come from the daemon**, in `ASTRA_PLUGIN_CAPABILITIES`, not
  from introspecting which of your methods return a non-empty vector. A plugin
  whose advertised capabilities used to disagree with its manifest now
  advertises the manifest, which is what the user consented to.

---

## 4. What merely warns

| Warning | Deadline | Do instead |
| --- | --- | --- |
| `use of deprecated trait compat::PluginCapability` | 0.8 | the 0.6 trait — §2 |
| `use of deprecated struct compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.8 | `Result<String, ToolError>` — §2.4 |
| `use of deprecated type alias compat::HostClient` / `DaemonClient` | 0.8 | `ctx.host()` / `ctx.daemon()` — §2.3 |
| `use of deprecated method source_id` | 0.8 | delete the override |
| Python `DeprecationWarning: … returned a dict` | 0.7 | return the dataclass |
| `AiGetModels` / `ai_models()` | 0.8 | nothing — the daemon never asks |

Nothing in that table is an error yet, and nothing in it will become one inside
one minor: see [versioning.md](versioning.md) for the guarantee and for how it
is enforced.

---

## 5. Python

The package goes 0.4.0 → 0.5.0. The class is still `Plugin` and the decorators
are still `@tool` / `@action` / `@trigger`, so most files change very little.

**Failures are coded now.** `call_tool` and `execute_action` used to catch every
`Exception` and flatten it to `{"success": False, "error": str(e)}` — which is
why every failure looked identical. Raise one of the eight errors instead, and
the SDK fills in both the legacy string and the structured `error_detail`:

From `examples/text-utils/src/plugin.py`:

<!-- doctest: illustrative reason="one decorated method from examples/text-utils/src/plugin.py, not a whole module" -->
```python
@tool("Convert text case: upper, lower, title, snake, camel.")
async def case_convert(self, text: str, mode: str):
    self._check_length(text)
    if mode not in CASE_MODES:
        # BAD_ARGUMENTS, not INTERNAL: the model is the caller here, and this
        # code is what tells it to try again with a different `mode` rather
        # than to give up and apologise to the user.
        raise BadArguments(f"unknown mode {mode!r}; use one of {', '.join(CASE_MODES)}")
    self.operations_count += 1
    return self._convert_case(text, mode)
```

`raise NotConfigured("api_key")` is the one that becomes a link to the exact
settings field.

What else to check:

- **`stt_transcribe` takes a third parameter**, `options: SttOptions | None`. A
  two-argument override keeps working — the servicer inspects your signature
  once and passes only what it accepts — so this is optional, and adding
  `options=None` is how you get the daemon's language hint and wake-word bias.
- **Return dataclasses, not dicts**, from the capability hooks. Dicts still work
  and emit a `DeprecationWarning` naming the class to return; they go in 0.7.
- **`HostClient` cannot be constructed unauthenticated.**
  `HostClientBootstrap(addr, plugin_id).register(...)` returns the real one.
- **`@ui_call` / `@ui_page` register.** They used to be `@staticmethod`s
  returning a dict that the caller discarded.
- Gate CI on the warnings: `python -W error::DeprecationWarning -m pytest`.

## 6. TypeScript

The package goes 0.4.0 → 0.5.0, and the published name is `astra-plugin-sdk` —
not `@astra/plugin-sdk`, which four places used to say.

- **Failures are coded**, same eight as everywhere else, and `code` is a string
  literal per class, so `switch (err.code) { case "NOT_CONFIGURED": … }` narrows
  to the subclass and reaches `err.configField` with no cast.
- **`HostClient`'s constructor is private**; `HostClient.register(...)` is the
  only way to get one, and it throws `RegistrationError` if the daemon refuses.
- **The clients load the SDK's own generated descriptor** instead of two
  hand-maintained inline proto strings, and check every method they will call at
  connect time — a mismatch is a `ProtoContractError` at startup rather than a
  `TypeError` on the first call.
- **`UiPanel` is deprecated**; it is an alias for `UiContribution`.
- If your `package.json` predates 0.5.0, note the new `exports` map,
  `"type": "commonjs"`, `engines: { node: ">=20" }` and dual CJS+ESM output.

---

## 7. Verifying the migration

You do not need Astra installed to know whether the port worked. The 0.6 SDKs
ship a test harness that runs your handlers in-process against a recording host:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
use astra_plugin_sdk::testing::Harness;

#[tokio::test]
async fn the_0_5_dice_roller_still_rolls_and_still_fires() {
    let h = Harness::new(DiceRoller::new())
        .with_config_json(r#"{"default_sides":20}"#)
        .start()
        .await
        .unwrap();

    let out = h
        .call_tool("roll_dice", serde_json::json!({"count": 3, "sides": 6}))
        .await
        .unwrap();
    assert!(out.starts_with("Rolled 3d6:"), "{out}");

    // The triggers the 0.5 `try_lock` used to drop when it lost the race.
    assert_eq!(h.wait_for_triggers("on_roll_value", 3).await.len(), 3);
}
```

That test is how the shim was accepted: `DiceRoller` there is the **0.5**
dice-roller, unmodified except for its import line, running on 0.6. No daemon,
no socket, no Astra installed — `Harness` builds a `PluginContext` around a
recording host, so `fired_triggers()` is a list you can assert on.

A short checklist:

1. It builds with no `compat::` import.
2. Your `plugin.toml` has a `[permissions]` section for every host RPC you call,
   each with a `reason` written for the user.
3. `on_config` sees `{}` without falling over — that is a fresh install.
4. Anything you used to do in `set_host` / `set_daemon_client` happens in
   `on_start`, and `on_start` returns `Err` when the plugin genuinely cannot
   work.
5. Every `ToolResult::err` has become the `ToolError` variant that says why.
