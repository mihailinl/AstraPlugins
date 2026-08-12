# Changelog — `astra-plugin-sdk` (Rust)

All notable changes to this crate. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This crate is published to crates.io by the release train in
`.github/workflows/release-sdks.yml`, which runs on a single
`sdk-v<VERSION>` git tag and publishes all three SDKs together.

**Deprecation policy** — `docs/en/versioning.md`. Nothing is deprecated for less
than two minors and one quarter; a deprecation note names its replacement; and a
**removal appears under a `BREAKING` heading in this file**, naming what went and
what replaced it. Deprecations live under `### Deprecated`, with the release they
are removable in.

## [0.6.0] — unreleased

Breaking. **Every 0.5.0 plugin is broken against the current daemon** — the
0.5.0 `HostClient` sends no `x-session-token`, and the daemon answers
`unauthenticated` to every host RPC except `Register`. Upgrade is not
optional, which is why this is a new minor rather than a patch on 0.5.0.

### Changed (breaking)
- `HostClient` can no longer be constructed directly. Registration is a
  two-step handshake the types enforce:
  `HostClient::connect_bootstrap()` → `BootstrapHostClient` (exposes
  `register` and nothing else) → `register()` consumes it and returns an
  authenticated `HostClient`. No un-upgraded, tokenless client is reachable.
- `register()` now returns `Err` when the daemon issues an empty
  `client_session_token` instead of handing back a client whose every call
  would fail `unauthenticated`.
- The runner gates `DaemonClient` creation and the chat firehose on
  `PluginCapability::is_client()`, not on the token being non-empty — the
  daemon issues a session token to *every* plugin now (SECURITY(B1)), so the
  token no longer says anything about capability. Trigger-only plugins used to
  open a `DaemonClient` they had no permission to use and reconnect it every
  2 s forever.

### Added
- **A trigger fired while handling a daemon call names the call that caused
  it.** `PluginContext::host()` now hands out a host scoped to the invocation
  the runner is dispatching, and a trigger fired through it carries that
  invocation's lease as gRPC metadata (`spec/wire.yaml`'s `x-astra-cause`).
  The daemon redeems the lease to decide which conversation the trigger's
  output belongs in — today it lands in a freshly auto-created chat the user
  never sees, and with two chats driving one plugin at once nothing on the
  wire even distinguishes them.

  **Nothing to do, and nothing to change.** The cause rides inside the
  `Arc<dyn Host>`, so the shipped idiom — clone the host, `tokio::spawn`, fire
  from the detached task — carries it with no author involvement. Rust gets a
  scoped handle rather than a task-local precisely because a
  `tokio::task_local!` does not cross that `spawn`. `ctx()`, a host stashed at
  `on_start`, or a raw `std::thread` gets the unscoped host and its fires are
  root events, which is the honest answer.

  **Inert until a daemon issues leases.** No daemon in the field does, so every
  fire today is a root event exactly as before.
- `Host::fire_trigger_caused_by`, defaulted. Plugin authors never call it; it is
  the seam the scoped host uses. An existing `Host` impl — a test double, a fake
  in another crate — keeps compiling and drops the cause, which degrades to a
  root event rather than to an error.
- `wire` module: the gRPC metadata keys, generated from `spec/wire.yaml`.
  `x-session-token` and `x-plugin-token` used to be spelled by hand in fifteen
  places across the three SDKs and the CLI. A metadata key is a map entry, so a
  misspelling is not an error — it is an absence, and absence is legal for all
  three. The typo silently removes authentication, or attribution, and says
  nothing.
- `limits`: `LEASE_TTL_SECS`, `LEASE_FIRE_GRACE_SECS`, `LEASE_MAX_FIRES` — the
  bounds the daemon enforces on a lease.
- `testing::FiredTrigger` records `caused_by`, so a plugin's own tests can
  assert *where* a trigger's output was going to land and not only that it
  fired. The struct is now `#[non_exhaustive]`: it is a record of what a plugin
  did, so a test reads its fields and never builds one.
- `auth` module: `SessionInterceptor` attaches `x-session-token` to every
  `HostClient` *and* `DaemonClient` call; `CapabilityInterceptor` checks the
  spawn-time token back on the plugin's own `PluginCapabilityService`
  (`x-plugin-token`), staged via `CapabilityAuth` /
  `ASTRA_PLUGIN_CAPABILITY_AUTH`.
  **The daemon now ships its half**: it presents the token on every call into a
  plugin and sets `ASTRA_PLUGIN_CAPABILITY_AUTH=require` on every spawn, so a
  plugin enforces with nothing to configure. Nothing here changes for an author
  — the default stays `Warn`, which is what a daemon too old to send the header
  leaves a plugin in, and that daemon has no way to say so. `astra-plugin test`
  sets the same variable and presents the same token, so a capability server
  that would refuse the real daemon fails locally instead.
- `run_with(RunConfig)` alongside `run()` — `#[non_exhaustive]` `RunConfig`
  carries `init_tracing`, `argv`, `bind_addr`, `capability_auth` and
  `capabilities`.
- The SDK filters argv down to the daemon's own flags (`--daemon-addr`,
  `--plugin-id`, `--auth-token`, `--capabilities`), so a plugin may define its
  own CLI without `Args::parse()` aborting the process.
- A failed host RPC now carries its **kind**, not just a sentence.
  `HostClient` used to `.context("FireTrigger RPC failed")` a `tonic::Status`,
  and `From<anyhow::Error> for ToolError` only looked for a `ToolError` — so
  `ctx.host().fire_trigger(..).await?` turned a daemon `PERMISSION_DENIED` into
  `ToolError::Internal`, telling the AI loop to retry a call that can never
  succeed, and put tonic's `Display` (`details: []`,
  `MetadataMap { headers: {} }`) into the text the model reads. The conversion
  now chains `ToolError` → `tonic::Status` → `Internal`, and `HostClient` maps
  the status itself, so the same line yields `UNAUTHORIZED` and one sentence.
  This is the first failure most authors meet: `[permissions]` is default-deny.

### Fixed
- **The 0.5 compatibility shim could skip `set_host` entirely**, leaving a
  legacy plugin with no host and every tool call answering whatever that plugin
  says when its host is missing. The shim delivers `set_host` once per (plugin,
  context) pair and remembered which pairs it had done in a global set keyed by
  the two *addresses*. Nothing removes from that set, so its entries outlive the
  objects they name — and the allocator hands the same blocks straight back: in a
  200-cycle build-and-drop probe the plugin/host address pair repeated **199
  times**, one distinct pair in all. So a test binary that builds one harness,
  drops it, and builds another matched the dead record and skipped the live
  plugin's delivery. The third key component is now a per-context counter, which
  cannot be recycled. Only a process that constructs more than one plugin or
  context was affected — a plugin's own test suite, and `astra-plugin test`.

### Changed (breaking) — daemon events
- `CommandTriggeredEvent::variables` is gone, replaced by `trigger_text`. The
  daemon's `AstraEvent::CommandTriggered` carries `command_id`, `command_name`
  and `trigger_text` and has never carried a variables map
  (`astra-core/src/event.rs`); `variables` was `#[serde(default)]`, so it
  deserialized to an empty map on every event and a plugin that read it read
  `{}` forever. A field that cannot be populated is worse than an absent one,
  because it looks like an answer. Read `trigger_text` instead — it is the
  utterance that matched the trigger.

### Added — the mock daemon answers for itself
- `Recorded::unauthenticated_calls()` and `MockDaemon::unauthenticated_calls()`:
  every host RPC that arrived without a valid `x-session-token`, in order.
  `astra-plugin test` asserts the list is empty over a real plugin process, so
  a host client that stops authenticating can no longer pass conformance while
  every inbound hook still answers.

### Changed (breaking) — the authoring API

Phase 5a rebuilt the surface an author actually writes against. Every 0.5 trait
impl needs edits; all of them are mechanical, and `docs/en/migration-0.6.md`
walks through them in the order the compiler reports them.

**They do not all have to happen today.** `astra_plugin_sdk::compat` is the 0.5
surface — the trait, `ToolResult` / `ActionResult` / `UiCallResult`, and
`HostClient` / `DaemonClient` as `Arc<dyn Host>` / `Arc<dyn Daemon>` aliases —
forwarded onto the 0.6 trait by a blanket impl. Changing one import line,
`prelude::*` → `compat::*`, builds an 0.5 plugin against 0.6 with deprecation
warnings and nothing else: verified on the 255-line 0.5 dice-roller, whose tools
answer and whose `set_host`-stored host still fires triggers. It is removed in
0.8. See `### Deprecated` below.

What changed and why:

- **Handlers take a `&PluginContext`.** `set_host(Arc<Mutex<HostClient>>)` and
  `set_daemon_client(Arc<Mutex<DaemonClient>>)` are **gone**. The context is
  cheap to clone, is never `None`, and carries `plugin_id`, `language`,
  `active_triggers`, `host: Arc<dyn Host>` and `daemon: Option<Arc<dyn Daemon>>`.
  From a place a parameter cannot reach, `astra_plugin_sdk::ctx()`.

  This removes a real defect, not just boilerplate. dice-roller kept the host in
  a `Mutex<Option<Arc<Mutex<HostClient>>>>` and reached it with
  `self.host.try_lock().ok().and_then(..)`; when a second tool call held the
  lock, that returned `None`, logged "host client not available yet", and fired
  no triggers at all. `Arc<dyn Host>` has no lock to lose.

  **`Host` and `Daemon` are traits.** Every method takes `&self` — the real
  implementations clone their tonic client per call, which is what tonic clients
  are for. Being traits is what makes the task-5.6 test harness possible: a
  handler can be run against a recording fake with no daemon and no socket.

- **Handlers return `Result`.** `call_tool`, `execute_action` and
  `handle_ui_call` return `Result<String, ToolError>`; `ToolResult`,
  `ActionResult` and `UiCallResult` are deleted. `ToolError` is
  `BadArguments` / `NotFound` / `NotConfigured{field}` / `Unauthorized` /
  `RateLimited{retry_after}` / `Unavailable` / `Timeout` / `Internal`, plus
  `with_doc_url`. `From` impls make `?` work on `serde_json::Error`,
  `std::io::Error`, `tonic::Status`, `anyhow::Error` and the parse errors — and
  each conversion is a claim about *which* kind the failure is, so
  `serde_json::from_str(args)?` inside `call_tool` means BAD_ARGUMENTS, which is
  the one failure the model can fix by retrying. `ActionError = ToolError`.

  Per-call failures travel **in band**: the response carries `success = false`,
  the new structured `error_detail` (`PluginError` with `config_field`,
  `retry_after_ms`, `doc_url`) *and* the old `error` string, so a pre-0.6 peer
  still gets a sentence and the AI loop still gets text to read. gRPC `Status`
  is reserved for transport and for hook absence.

  Both ends are now wired. The daemon reads `error_detail` on the tool path and
  on the UI path (`PluginManager::call_tool` /
  `call_plugin_from_ui` → `PluginCallFailure`), so the model is told the code,
  the hint and the `retry_after_ms`, and `CallPluginFromUiResponse.error_detail`
  carries `config_field` to the panel that turns it into a link to that exact
  settings field. Until that landed, everything above was populated and read by
  nobody.

- **Config is typed, and the associated type is required.**
  `type Config: DeserializeOwned` with `NoConfig` for plugins that have none —
  deliberately not an associated type default, which is unstable Rust and would
  not compile on this crate's stable edition-2024 toolchain. Implement
  `on_config(&self, ctx, cfg: Self::Config)`; `on_config_changed` defaults to
  parse-then-delegate and reports a payload that does not fit at `WARN` **and**
  as a `PluginLog` the user can see, keeping the previous config rather than
  running on half of a new one. `Config<T>` wraps `ArcSwap` for lock-free reads.

  bad-apple's twenty lines of `v.get("opacity").and_then(|n| n.as_f64())` — one
  arm per field, each silently skipping a field of the wrong type — became a
  `#[derive(Deserialize)]` and a two-line `on_config`.

- **Capabilities come from the daemon, not from introspection.**
  `discover_capabilities` is deleted. The daemon states the manifest's
  `[capabilities]` in **`ASTRA_PLUGIN_CAPABILITIES`** (comma-separated, always
  set, empty included), because `plugin.toml` is not reliably next to the
  executable — in a packaged bundle it sits at the install root while the binary
  is under `bin/`. Falls back to `RunConfig::capabilities` (which
  `#[astra::plugin]` will fill in) only when the variable is *absent*, which is
  what an Astra older than §5.4 looks like; a variable that is set-but-empty is
  the daemon saying this manifest declares none, and is obeyed.
  `--print-capabilities` prints the binary's own list and exits 0, with no
  daemon needed.

  It travelled briefly on argv as `--capabilities=a,b,c`, and that was a
  compatibility bug: the only Python SDK ever published (PyPI 0.4.0) parses argv
  with `argparse.parse_args()`, which exits 2 on an unrecognised argument before
  the plugin binds its port. Every Python plugin already installed would have
  stopped starting on daemon upgrade. An SDK still honours an explicit
  `--capabilities` if some harness passes one.

  The old behaviour inferred capabilities from which trait methods happened to
  return a non-empty vector at startup, so a plugin's advertised capability set
  could silently disagree with the manifest the user consented to.

- **Startup order is fixed:** bind → register → build ctx → `on_config` →
  `on_language_changed` → `on_start` → serve. `on_start` is new; returning
  `Err` **aborts startup** and the process exits non-zero, instead of leaving a
  plugin the daemon believes is healthy and that fails every call the same way.

- `source_id()` is deprecated — the daemon stopped filtering by source id.
- `ActiveTriggers::contains` / `update` are now synchronous (`ArcSwap`, not
  `tokio::RwLock`), and `update` is renamed `set`.
- The shutdown grace is now `limits::PLUGIN_STOP_GRACE_SECS` rather than a
  private `5`, so it cannot drift past the daemon's own grace.

### Added — hooks that had no Rust binding

- `ai_complete` (streaming), `tts_synthesize_stream`, `tts_activate`,
  `stt_load`, `stt_unload`, `stt_load_state`. A Rust plugin can now be an AI
  provider and stream TTS. The streaming hooks answer `UNIMPLEMENTED` when not
  overridden — the SDK waits for the first chunk before opening the response, so
  "this plugin has no such hook" is still expressible after the call starts.
- `HostClient::send_chat_message` and `set_theme_contribution`. `SendChatMessage`
  was bound by **no** SDK in any language, which made `client` a capability
  nobody could implement.
- `stt_transcribe` / `stt_transcribe_stream` receive `SttOptions` (the daemon's
  per-utterance language hint and wake-word bias, carried on the first audio
  chunk); `ai_complete` receives `reasoning_effort` and `show_reasoning`. All
  three were on the wire and reachable from no SDK.
- `ToolDef::new`/`with_schema`, `VoiceInfo::new`, `AudioChunk`, `AiChunk`,
  `SttLoadState`, `TtsRequest`, `SttLoadRequest` — small constructors that
  replace five-field struct literals in every example.
- `PluginContext::new` / `with_daemon` / `with_language` and `install_context`
  are public, so a harness can build one around a fake host.
- Dependency: `arc-swap`.

### Added — `astra-plugin-macros`, and a plugin that is one dependency

The §3.1 target is a plugin whose `Cargo.toml` lists **one** dependency and
whose `src/main.rs` is **12 lines**. `astra-plugin new p --lang rust` now emits
exactly that, and it builds.

- **New sibling crate `astra-plugin-macros`,** re-exported as
  `astra_plugin_sdk::astra`. It is a non-optional dependency of this crate and
  is published to crates.io from the same `sdk-v<VERSION>` tag, at the same
  version — **it must go up before `astra-plugin-sdk`**, because the SDK depends
  on it by version and `cargo publish` resolves that from the registry. The
  release workflow does this in order and waits for the index.
  - `#[astra::plugin]` on an inherent impl emits `impl PluginCapability` plus
    `impl DeclaredCapabilities`. `#[tool]` / `#[action]` / `#[ui_call]` inside it
    become the list-and-dispatch arms; `#[hook]` moves a named trait method
    across verbatim.
  - `astra::main!(P::default())` writes the tokio runtime and feeds
    `DeclaredCapabilities::CAPS` into `RunConfig::capabilities`.
  - `#[derive(PluginConfig)]` implements `json_schema()`; `#[astra::args]`
    supplies `Deserialize` + `JsonSchema` for a tool-argument struct.
  - The expansion is exactly the trait impl an author would have written, and
    every path it emits is rooted at `::astra_plugin_sdk::` — which is what lets
    the author's crate not depend on tokio, serde, serde_json, anyhow,
    async-trait or schemars. Both properties are asserted by tests in
    `astra-plugin-macros/tests/`.
- **`#[astra::args]`, and why it exists.** §3.1 writes tool-argument types as
  `#[derive(Deserialize, JsonSchema)]`. That cannot work at one dependency:
  `serde_derive` emits `extern crate serde as _serde`, which resolves only
  through the extern prelude and cannot be reached through a re-export, so a
  crate depending on `astra-plugin-sdk` alone gets ``can't find crate for
  `serde` ``. `#[astra::args]` is those two derives pointed at the SDK's copies
  of both crates, and is the form the docs should use.

  **The prelude no longer re-exports serde's derives.** It used to, twenty lines
  below a doc comment correctly explaining that a re-export cannot make them
  work — so pasting §3.1's own sample produced `` can't find crate for `serde` ``
  pointing at a Cargo.toml line the scaffold says not to add, and rustc's canned
  suggestion (`#[derive(serde::Deserialize)]`) looped back to the same note.
  `prelude::Deserialize` / `prelude::Serialize` are now placeholders that fail
  with a sentence naming `#[astra::args]` and `#[astra::config]`.
  **Migration:** either mark the type `#[astra::args]` (one line, no new
  dependency), or add `serde` to your own `Cargo.toml` and write
  `use serde::Deserialize;` — an explicit import shadows a glob one, so that
  path is unchanged.

- **`#[astra::config]`** — `#[astra::args]` plus `#[serde(default)]` at the
  container level plus `#[derive(PluginConfig)]`. A required field is right for
  tool arguments and wrong for settings: the daemon's *first* config payload to
  a freshly installed plugin is `{}`, a config type with a required field
  rejects it, and `on_config` was then never called even once — the plugin ran
  on `Config::default()` with an empty API key and failed later somewhere that
  named nothing useful. With `#[astra::config]` the empty payload always parses
  and "not configured" becomes a value you test for and answer with
  `ToolError::not_configured("api_key")`, which carries the field the UI turns
  into a link. `on_config_changed`'s warning now tells a fresh install apart
  from a malformed edit instead of claiming it is "keeping the previous config"
  when there is no previous config.

- **`#[tool]` / `#[action]` / `#[ui_call]` check the return type**, on the
  author's own `->`. Writing `-> String` — the most common signature mistake,
  because returning the string is what the handler feels like it *does* — used
  to be reported as `expected Result<String, ToolError>, found String` **on the
  `#[astra::plugin]` attribute**, eleven lines above the mistake, with a
  suggestion to wrap the attribute in `Ok(..)`. The dispatcher's type annotation
  and its JSON parse are now emitted with the handler's own spans, so the
  residue that only the compiler can catch (`anyhow::Result<String>`, a missing
  `Deserialize` on the argument type) lands on the signature too.
- **New default-on `schema` feature**, gating an optional `schemars`
  dependency. `default-features = false` drops it and turns `#[tool]` on a typed
  argument, `#[derive(PluginConfig)]` and `#[astra::args]` into compile errors
  that name the flag to flip. Nothing else changes.
- `astra_plugin_sdk::schema` (`schemars` re-export, `of` / `of_config`),
  `DeclaredCapabilities`, `PluginConfig`, `ConfigShape`, and prelude re-exports
  of `anyhow` / `tokio` / `serde_json` / `schemars`.
- The hidden `--print-capabilities` flag answers before argv is parsed and exits
  0 with no daemon, so tooling can ask a built binary what it declares. It is
  only truthful for a plugin that goes through `astra::main!`; a plugin calling
  `astra_plugin_sdk::run(P)` directly prints nothing, which tooling must read as
  "this binary does not answer", not as "this binary declares nothing".

### Added — `astra_plugin_sdk::testing`, both levels

Not feature-gated, deliberately: a `testing` feature would force a second
`[dev-dependencies] astra-plugin-sdk = { …, features = ["testing"] }` line into
every plugin's `Cargo.toml`, which breaks the one-dependency bar above. A
release build's dead-code pass removes it.

- **Level 1, in process.** `Harness::new(plugin).with_config(json!(…))
  .with_language(..).with_active_triggers(..).with_host(..).with_daemon(..)
  .start()` runs the runner's real startup order — `on_config` →
  `on_language_changed` → `on_start` — and returns a `Running<P>` exposing every
  hook the way the daemon calls it: `call_tool`, `execute_action`, `ui_call`,
  `stt_transcribe`, `stt_stream` (channel sized from `spec/limits.yaml`),
  `tts_stream`, `ai_complete`, `config_changed`, `fuzz_config`,
  `language_changed`, `active_triggers`, `event` (through the runner's own
  `dispatch_event`), `conversation_events`, `health`, `shutdown`, plus
  `wait_for_triggers` for hooks that fire from a spawned task.
- `RecordingHost` implements `Host` with `fired_triggers()` / `logs()` /
  `variables()` / `ui_pushes()` / `chat_messages()` and failure injection
  (`deny`, `fail`, `fail_next`, `fail_times`, `clear_failures`) that builds the
  error exactly as `host_client::rpc_failed` does, so a handler's `?` recovers
  the same `ToolError` kind. Injection names are validated against the host RPC
  list — a typo panics instead of arming nothing and passing.
- `h.schema("roll_dice")` returns a `ToolSchema` with `properties()` /
  `required()` / `description_of()` / `assert_is_a_parameters_object()` /
  `assert_matches::<T>()`, and `h.assert_schema_matches::<T>("roll_dice")`.
  It takes a tool NAME: a plugin declares many tools and the zero-argument form
  has no way to say which one it means.
- **Level 2, over the wire.** `MockDaemon` serves the real `PluginHostService`
  on loopback and enforces what the daemon enforces — Register is the only
  auth-exempt path, everything else needs `x-session-token`, and each rpc is
  gated on its `spec/hooks.yaml` permission, so `revoke("fire_trigger")` yields
  `PERMISSION_DENIED`. `WireHarness::start(plugin)` spawns the *actual*
  `run_with` against it and connects a client carrying the spawn token, so
  handler registration, the interceptor, descriptor mismatch and 500-slot
  back-pressure are all on the path. `registration()` is the only place a
  capability list, protocol version and SDK name are observable at all.
- **Fixtures.** Golden 16 kHz f32-LE PCM in the daemon's 1600-sample batches:
  `pcm(n)`, `utterance()`, `wake_seed_burst()` (~8 s of wake pre-roll) and
  `channel_saturating_burst()`, sized by reading
  `limits::STT_AUDIO_CHANNEL_CAPACITY` rather than a literal.
  `firehose_events()` is one complete assistant turn; `firehose_error_turn()`
  adds an error turn and an event whose oneof is empty (a daemon newer than this
  SDK). `config_fuzz()` is 15 payloads the daemon actually produces, starting
  with `{}` — a fresh install — and including the two that are not JSON.

### Added — structured logs and panic containment (§5.10)

- **`logging::layer()`** is a `tracing_subscriber` Layer forwarding events to
  the daemon as `PluginLog`; `run_with` composes it with the `EnvFilter` and
  `fmt` layers at init, and `logging::attach(host)` plugs the host client in
  right after registration. `tracing`'s five levels map to the daemon's four,
  INFO-and-above by default, overridable with `ASTRA_PLUGIN_LOG_LEVEL`. Three
  guards against the log → RPC → log loop: a task-local set for the shipper
  task, a target denylist (h2/hyper/tonic/tower/rustls/tokio/mio, matched on
  `::` boundaries so `h2o_plugin` still ships), and a bounded 256-slot queue
  with `try_send` and a `dropped()` counter — a busy handler drops lines rather
  than waiting on the daemon.
- **`panics::catch(hook, fut)`** wraps every `CapabilityServiceImpl` handler.
  `call_tool` / `execute_action` / `handle_ui_call` answer in band with a coded
  error; the discovery and lifecycle hooks answer `INTERNAL`; `health_check`
  answers `(false, "…panicked: …")`; `on_start` aborts startup with a sentence
  naming the hook and the line. Never `UNIMPLEMENTED`, which the daemon reads as
  "hook absent" and stops calling. `panics::install_hook()` runs first in
  `run_with`, chains the previous hook, and reports payload, location and
  backtrace at error level — which, once logging is attached, is a `PluginLog`
  in the user's pane.
- **`panic = "abort"` turns all of this off** and must not be set in a plugin
  profile: with it, a panicking tool takes the process down instead of returning
  an error.

### Deprecated

Everything here is removed in **0.8.0** — two minors and one quarter, the
minimum window `docs/en/versioning.md` promises. Each carries a
`#[deprecated(since = "0.6.0", note = …)]` whose note names what to use instead,
so the compiler tells you at the use site and `cargo build` still succeeds.

- **`astra_plugin_sdk::compat`** — the whole 0.5 authoring surface:
  - `compat::PluginCapability`, the 0.5 trait, with
    `impl<T: compat::PluginCapability> PluginCapability for T` forwarding every
    hook onto the 0.6 one. Replacement: the 0.6 `PluginCapability`.
  - `compat::ToolResult` / `ActionResult` / `UiCallResult`. Replacement:
    `Result<String, ToolError>`. A legacy `err(..)` becomes `ToolError::Internal`
    carrying the same sentence — 0.5 had one failure and it was a string, and
    `Internal` is the kind that promises the model nothing.
  - `compat::HostClient` / `compat::DaemonClient`, aliases for `Arc<dyn Host>`
    and `Arc<dyn Daemon>`, so a field typed `Arc<Mutex<HostClient>>` and a call
    written `host.lock().await.fire_trigger(..)` both still compile.
    Replacement: `ctx.host()` / `ctx.daemon()`.
  - `compat::*` re-exports the rest of the 0.5 prelude unchanged, so the whole
    migration is one import line. It is a **replacement** for `prelude::*`, not
    an addition: both globs in scope makes `impl PluginCapability` ambiguous
    (E0659).
  - Two things the shim deliberately does not do. `set_host` /
    `set_daemon_client` are delivered once, from whichever 0.6 hook carrying a
    context runs first — the 0.5 runner delivered them at line 223 and called
    `on_config_changed` at line 300, so the ordering an 0.5 plugin can observe is
    preserved, but a plugin that assumed the host existed before *any* of its
    code ran should read `ctx.host()`. And hooks 0.5 never had — `ai_complete`,
    `tts_activate`, `stt_load`/`stt_unload`/`stt_load_state` — stay
    `UNIMPLEMENTED` rather than answering something plausible, because the
    daemon's idle-unload timer reads `stt_load_state` and a shim that answered
    `NotNeeded` would tell it a resident model is not resident.
  - Covered by seven harness tests written *against the 0.5 trait*
    (`src/capability.rs`, `mod compat::tests`). The one that earns its keep is
    `a_streaming_0_5_recognizer_keeps_emitting_partials`: forwarding 0.6's
    `stt_transcribe_stream` to 0.5's *non-streaming* `stt_transcribe` compiles,
    passes a naive test, and silently discards every partial a real streaming
    backend emits.
- **`PluginCapability::source_id()`** — the daemon stopped filtering by source
  id; every client sees every event. Replacement: pass the id to
  `Host::send_chat_message`, or delete the override.
- **`AiGetModels` / `ai_models()`** — implemented in all three SDKs and called by
  nobody; `all_ai_providers` hardcodes `supports_model_discovery=false`, so the
  picker never asks. No replacement: nothing in the daemon asks a plugin what
  models it has, and `AiComplete` carries the chosen model on the request.
  Recorded as `deprecated_in: "0.6"` / `removed_in: "0.8"` in `spec/hooks.yaml`,
  where `tools/parity/spec.py` enforces the window on every CI run.

### Fixed
- **`SttProcess` no longer swallows the STT hook's failure.** The plugin task's
  `Err` — including the SDK's own `unimplemented("stt_transcribe")` default —
  was `warn!`ed and the response stream closed normally, so a Rust plugin that
  declared `stt` and implemented no `stt_transcribe` answered `SttProcess` with
  **OK and zero events**, where Python and TypeScript both answered
  `UNIMPLEMENTED`. Phase 1 fixed `Unimplemented` to mean *the hook is absent*,
  and this was the one language that could not say it. The failure now travels
  on the stream, mapped by `hook_status` — so does a genuine mid-utterance
  recognizer error, which used to be a moving waveform, no text ever, and
  nothing in the daemon log.
- `OnActiveTriggers` now updates `ctx.active_triggers()` **before** dispatching
  to the hook. `ActiveTriggers` previously had no writer at all: every
  `contains()` answered false, so the "is anyone listening" check the type
  exists for could never be true.
- STT audio channel capacity raised from 32 to 500 chunks, in lockstep with
  the daemon — a streaming STT backend dropped audio under load.

## [0.5.0] — 2026-05-24

### Added
- `PluginCapability::tts_config_fields()` and `stt_config_fields()` hooks
  (default `vec![]`). A plugin's TTS/STT provider can declare extra
  Voice-settings fields that the daemon renders generically via its
  `DynamicField` component — no per-plugin frontend code. Backed by
  new RPCs `TtsGetConfigFields` / `SttGetConfigFields` on
  `PluginCapabilityService`, returning `PluginConfigFieldsResponse`.

### Daemon compatibility
- Requires the data-driven Voice settings work landed in
  `astra-rs:refactor/voice-architecture` (Wave 4.2g-5). Older daemons
  silently ignore the new RPCs — plugins still register and run, they
  just won't see their config fields on the Voice page.

## [0.4.0] — unreleased

### Added
- `PluginCapability::stt_transcribe_stream(audio_rx, events_tx,
  sample_rate)` — true streaming STT hook. The default implementation
  buffers and forwards to the non-streaming `stt_transcribe` (so
  existing plugins are unchanged), but a streaming backend (Vosk,
  Deepgram, an echo-stt-style live plugin) can override it to consume
  chunks as they arrive.

### Examples
- `echo-stt` — plays every captured audio chunk back through the
  daemon's playback path in real time; demonstrates the streaming hook.

## [0.3.0] — unreleased

### Added
- `PluginCapability::stt_transcribe(audio, sample_rate)` —
  non-streaming STT hook (default `bail!("STT not implemented")`).
  The SDK accumulates every `PluginAudioChunk` the daemon streams over
  `SttProcess` until `is_last`, then calls this once with the
  concatenated PCM payload. Yields one `SttEvent` per utterance.
- `SttEvent` helper type with `transcript(...)` / `partial(...)`
  constructors and `with_confidence` / `with_language` chainable
  setters.

## [0.2.0] — 2025

Earlier development; see git history.

[0.6.0]: https://github.com/mihailinl/AstraPlugins/compare/rust-v0.5.0...HEAD
[0.5.0]: https://github.com/mihailinl/AstraPlugins/compare/rust-v0.4.0...rust-v0.5.0
[0.4.0]: https://github.com/mihailinl/AstraPlugins/compare/rust-v0.3.0...rust-v0.4.0
[0.3.0]: https://github.com/mihailinl/AstraPlugins/compare/rust-v0.2.0...rust-v0.3.0
[0.2.0]: https://github.com/mihailinl/AstraPlugins/releases/tag/rust-v0.2.0
