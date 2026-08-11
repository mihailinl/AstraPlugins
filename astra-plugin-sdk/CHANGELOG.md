# Changelog — `astra-plugin-sdk` (Rust)

All notable changes to this crate. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This crate is published to crates.io by the release train in
`.github/workflows/release-sdks.yml`, which runs on a single
`sdk-v<VERSION>` git tag and publishes all three SDKs together.

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
- `auth` module: `SessionInterceptor` attaches `x-session-token` to every
  `HostClient` *and* `DaemonClient` call; `CapabilityInterceptor` checks the
  spawn-time token back on the plugin's own `PluginCapabilityService`
  (`x-plugin-token`), staged via `CapabilityAuth` /
  `ASTRA_PLUGIN_CAPABILITY_AUTH`.
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

### Changed (breaking) — the authoring API

Phase 5a rebuilt the surface an author actually writes against. Every 0.5 trait
impl needs edits; all of them are mechanical, and `docs/en/migration-0.6.md`
(task 5.11) walks through them. What changed and why:

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

### Fixed
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
