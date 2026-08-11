# Changelog — `astra-plugin-sdk` (Python)

All notable changes to this package. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This package is published to PyPI by the release train in
`.github/workflows/release-sdks.yml`, which runs on a single
`sdk-v<VERSION>` git tag and publishes all three SDKs together. That tag
names the Rust crate's version; this package keeps its own.

**Deprecation policy** — `docs/en/versioning.md`. Nothing is deprecated for less
than two minors and one quarter; a deprecation note names its replacement; and a
**removal appears under a `BREAKING` heading in this file**, naming what went and
what replaced it. Deprecations live under `### Deprecated`, with the release they
are removable in.

## [0.5.0] — unreleased

Breaking. **Every 0.4.0 plugin is broken against the current daemon** — the
0.4.0 host stubs pass no `metadata=`, and the daemon answers
`unauthenticated` to every host RPC except `Register`.

### Changed (breaking)
- **`call_tool` and `execute_action` no longer swallow exceptions.** The default
  decorator dispatch used to catch every `Exception` and flatten it into
  `{"success": False, "error": str(e)}`, which is why every failure looked the
  same. Exceptions now reach the servicer, which turns them into a *coded*
  result (see `errors.py` below). An unknown tool or action raises `NotFound`
  instead of returning a dict.
  **Migration:** none for a plugin that returns dicts from its own `call_tool`
  override — that path is unchanged. A plugin that called
  `super().call_tool(...)` and inspected the returned `error` key for the
  unknown-tool case must catch `NotFound` instead.
- `Plugin.stt_transcribe` gained a third parameter, `options: SttOptions | None`
  — the per-utterance language hint and wake-word bias the daemon puts on the
  first audio chunk. **A 0.5-era two-argument override keeps working**: the
  servicer inspects the signature once at construction and passes only what the
  override accepts. Add `options=None` when you want the hint.
- `HostClient` is split in two. `HostClientBootstrap(daemon_addr, plugin_id)`
  can make exactly one call, `register(port, capabilities, auth_token)`, which
  returns `(response, host)` where `host` is an authenticated `HostClient`
  that owns the channel — or `None` if the daemon refused or issued no token.
  `HostClient` cannot be constructed without a session token, so no object
  exists on which an unauthenticated `log()` / `fire_trigger()` /
  `set_variable()` is reachable.
- Every authenticated stub call carries
  `metadata=(("x-session-token", token),)`.
- `DaemonClient` creation and the chat firehose are gated on `is_client()`,
  not on `response.client_session_token` being non-empty. Since SECURITY(B1)
  the daemon issues a token to *every* plugin, so the old test was trivially
  true: a trigger-only plugin opened a `DaemonClient` it has no permission to
  use and retried the firehose every 2 s for the life of the process.
  Matches `runner.rs` and `plugin.ts`.

### Added
- **`astra_plugin_sdk.errors` — the error taxonomy (production plan §5.2).**
  Eight exceptions with the same eight codes the Rust and TypeScript SDKs use:
  `BadArguments`, `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`,
  `Unavailable`, `Timeout`, `InternalError`, all deriving from `PluginError`
  (aliased `ToolError` / `ActionError`). Raise one from a tool, an action or a
  UI call and the SDK fills in **both** halves of the response: the legacy
  `string error` — now `CODE: message (hint)`, byte-identical to the Rust SDK's
  `wire_string` — and the structured `error_detail`, carrying `config_field`,
  `retry_after_ms` and `doc_url`. `raise NotConfigured("api_key")` is what turns
  "the tool failed" into a link to the exact settings field.
  A failure stays **in-band** (`success=false` on the response) rather than
  becoming a gRPC `Status`, because the AI loop has to read it; `grpc_status()`
  provides the fixed transport mapping for the streaming hooks, which have no
  in-band slot. Anything else a handler raises is adopted as `INTERNAL`, except
  `ValueError`/`TypeError` (→ `BAD_ARGUMENTS`), `KeyError` (→ `NOT_FOUND`),
  `TimeoutError` and `PermissionError`.
- **The six missing capability hooks (§5.4)**, each defaulting to
  "not implemented" — which the daemon reads as *hook absent*, so declaring
  them changes nothing for a plugin that does not override them:
  - `ai_complete(request)` — an **async generator** of `AiChunk`s (or bare
    strings for text deltas). The whole of the `ai_provider` capability, which
    no Python plugin could implement before. The SDK appends the terminating
    `done` chunk and turns a raised `PluginError` into the stream's in-band
    error chunk.
  - `tts_synthesize_stream(text, voice_id, speed, pitch)` — an async generator
    of `AudioChunk`s or raw `bytes`; the SDK flags the real last chunk
    `is_last`. (The daemon has no call site for `TtsSynthesizeStream` yet.)
  - `stt_load(model_path, use_gpu)`, `stt_unload()`, `stt_load_state()` — the
    model lifecycle that makes idle-unload actually free VRAM.
  - `tts_activate(cek, voice_id)` — one-time machine-bound sealing of a
    licensed voice's content key.
- `Plugin.stt_transcribe_stream(audio, options)` — streaming STT as an **async
  generator**, so a recognizer can emit partial results as the audio arrives.
  Overriding it takes precedence over `stt_transcribe`. Back-pressure is bounded
  by `limits.STT_AUDIO_CHANNEL_CAPACITY`, the same number the daemon's half of
  the bridge uses.
- **`HostClient.push_to_ui`, `HostClient.send_chat_message`,
  `HostClient.set_theme_contribution`.** Python could receive a `CallFromUi` and
  had no way to answer asynchronously; `client` was a capability no Python
  plugin could implement, because the session token is scoped to
  `PluginHostService` and the `DaemonClient`/`ChatService` route is
  `permission_denied` by construction. `send_chat_message` returns an async
  iterator of reply chunks. All three are gated on the matching `[permissions]`
  key (§5.6) — `push_to_ui`, `send_chat_message`, `set_theme_contribution`.
  `Plugin.push_to_ui(event, payload)` is the convenience wrapper.
- `astra_plugin_sdk.types` — `AiCompleteRequest` (with `reasoning_effort` and
  `show_reasoning`), `AiChunk`, `AiMessage`, `AiToolCall`, `AudioChunk`,
  `SttOptions`, `SttLoadState`, `SttLoadStatus`, `ThemeContribution`. Plain
  dataclasses with `from_proto`/`to_proto`, so a plugin never imports
  `plugin_pb2`.
- **`ASTRA_PLUGIN_CAPABILITIES`** is read and supersedes capability discovery —
  the manifest is the authority, and `plugin.toml` is not reliably next to the
  executable in a packaged bundle. A set-but-empty value is the daemon saying
  this manifest declares none and is obeyed; only the variable being *absent*
  falls back to probing the subclass. `--capabilities` on the command line is
  still honoured and outranks it, for a harness or a `dev` sideload.

  The daemon states it in the environment rather than on argv **because of this
  package**. Published 0.4.0 calls `argparse.ArgumentParser.parse_args()`, which
  prints `error: unrecognized arguments` and `sys.exit(2)` before the gRPC
  server binds — so a daemon that appended one new flag would have stopped every
  already-installed Python plugin from starting, and no release here could have
  rescued them. `parse_known_args()` below is the belt to that braces.
- Unknown arguments are now warned about instead of aborting the process
  (`parse_known_args`), so a daemon that learns a new flag cannot kill a plugin
  built against this version.
- Capability discovery (the fallback path) infers `ai_provider` from an
  `ai_complete` override rather than from `ai_get_models`, which is deprecated
  and returns `[]` by default — a provider that implemented the hook that
  matters used to register without the capability that names it.
- `astra_plugin_sdk.auth` — `CapabilityAuthInterceptor` guards the plugin's own
  `PluginCapabilityService` by demanding the spawn-time `--auth-token` back in
  the `x-plugin-token` header. Staged via `ASTRA_PLUGIN_CAPABILITY_AUTH`.
  **The daemon now ships its half**: it presents the token on every call into a
  plugin and sets that variable to `require` on every spawn, so a plugin
  enforces with nothing to configure. The default stays `warn`, which is what a
  daemon too old to send the header leaves a plugin in — the variable's absence
  is the only signal such a daemon gives.
- `HostClientBootstrap` exported from the package root.
- `__version__` is now kept in lockstep with `pyproject.toml` (it had drifted
  to `0.3.0` while the package shipped as 0.4.0).
- **`py.typed` (production plan §5.8).** The PEP 561 marker, listed in
  `[tool.setuptools.package-data]` so it actually reaches the wheel. Without it
  every annotation this package ships was invisible to a type checker running in
  a plugin's own repo — which is precisely where they are meant to help.
- **The seven capability types, as dataclasses with `to_proto()` (§5.8).**
  `ToolDef`, `VoiceInfo`, `AiModelInfo`, `FieldDef`, `ActionTypeDef`,
  `TriggerTypeDef`, `UiContribution`, plus `DropdownOption` / `FieldCondition`
  for the two things a field nests. Each capability hook now returns these
  instead of `list[dict]`.
  **Dicts still work for one more minor**, with a `DeprecationWarning` naming
  the hook and the type to switch to; they are removed in the release after
  next. A typo in a legacy dict now names the key and lists the valid ones,
  instead of the protobuf `ValueError` it used to raise from inside the
  servicer on the daemon's first call. `@tool` / `@action` / `@trigger` and the
  `Field` builder produce the dataclasses, so a plugin that uses the SDK's own
  helpers never sees the warning. `_field_dict_to_proto`, the bespoke converter
  that existed because `Msg(**d)` cannot build sub-messages, is gone — every
  type nests properly now.
- **`@ui_call`, and `@ui_page` / `@ui_slot` / `@ui_effect` / `@ui_overlay` /
  `@ui_inject` as *registering* decorators (§5.8).** `@ui_call` on a method
  makes it reachable from the plugin's own iframe over `CallFromUi`;
  `Plugin.handle_ui_call` dispatches to it, so UI→backend calls no longer need
  a hand-written `if/elif` chain and an unknown method answers `NOT_FOUND`
  listing the ones that exist. The five contribution decorators go on the
  Plugin **class** and `Plugin.get_ui_contributions` returns what they
  registered.
  **Why:** the old `Plugin.ui_page(...)` was a `@staticmethod` that built a dict
  and handed it back for the author to plumb into `get_ui_contributions` — and
  the SDK's own documented example did not, in seven translations. A builder
  whose return value must be remembered is a builder that gets dropped. The
  builders still exist, unchanged apart from returning `UiContribution`, for a
  plugin that assembles its contributions at runtime.
- **A startup assertion that the loaded proto has not revived a retired field
  name (§5.8, `astra_plugin_sdk.reserved`).** Rust gets a compile error for
  this; Python got an `AttributeError` on the one line that touched the field,
  typically inside the handler that runs when a user changes a setting — so a
  broken build shipped and failed later, in the field. `Plugin.run()` now checks
  the `reserved` declarations against the descriptors actually loaded, before
  binding the port, and refuses to start on a stale or foreign `plugin_pb2`.
- **`astra_plugin_sdk.testing` — the two-level test harness (§5.6).**
  - `Harness` (level 1): the plugin driven through its own gRPC servicer,
    in-process and synchronous, so a plugin author's test is a plain
    `def test_x():` with no `pytest-asyncio` and no event-loop fixtures.
    Tool dispatch, schemas (`h.schema`, `h.assert_schema_accepts`), actions, UI
    calls, config, language, active triggers, deterministic `h.stt(chunks)`.
  - `RecordingHost`: every host call recorded — `fired_triggers()`, `logs()`,
    `variables()`, `ui_pushes()` — with `fail_next` / `fail_always` failure
    injection, which is the only way to reach the branch a plugin takes when
    the daemon denies a permission. Arming a failure on a method that does not
    exist is refused, because a typo there silently arms nothing.
  - `WireHarness` + `MockDaemon` (level 2): the plugin's real `run()` path
    registering over loopback gRPC against a mock `PluginHostService` that
    enforces the daemon's own rules — `Register` exempt, `x-session-token` on
    everything else, `permission_denied` on request. Catches handler
    registration by wire path, descriptor mismatch, the capability interceptor
    in its `require` stage, and stream back-pressure.
  - Fixtures, registered as a pytest plugin (no `conftest.py` to write):
    `astra_harness`, `astra_wire`, `golden_pcm`, `wake_seed`, `fuzz_config`,
    plus `wake_seed_burst()` (the 8-second wake-word dump in 100 ms batches)
    and `backpressure_burst()` (more chunks than the 500-slot audio queue
    holds, each stamped with its index).
  - `pip install astra-plugin-sdk[test]` installs pytest; the harness itself
    needs nothing the SDK does not already depend on.
- **`logging` is routed into `PluginLog` (§5.10, `install_logging_bridge`).**
  `logging.getLogger(__name__).info(...)` now reaches Astra's log pane, from
  any thread, including from before registration completes. Installed
  automatically by `Plugin.run()`. The queue is bounded (an unbounded one in
  front of a stalled daemon is an OOM kill reported to the user as a crash),
  overflow is counted and reported rather than silent, and the transport's own
  loggers are never forwarded — forwarding a `grpc` record over `grpc` is how a
  bridge eats itself.

### Deprecated

Removed in **0.7.0** — two minors and one quarter, the minimum window
`docs/en/versioning.md` promises. Each emits a `DeprecationWarning` naming the
replacement, so `python -W error::DeprecationWarning -m pytest` turns the whole
list into a CI gate you can hold yourself to before the removal lands.

- **A `dict` where a capability dataclass is expected.** `coerce()` accepts one
  and warns, naming the hook and the class to return instead
  (`capability_types.py`). Replacement: the dataclass — `ToolDef`, `VoiceInfo`,
  `AudioData`, `SttEvent`, `AiModelInfo`, `FieldDef`, `UiContribution` — or its
  `to_proto()`. **The runtime warning says dicts are accepted "for one more
  minor release"; the binding number is 0.7.0**, per the policy, and
  `docs/en/versioning.md` is the table that settles it.
- **`ai_get_models()`** — the daemon never asks: `all_ai_providers` hardcodes
  `supports_model_discovery=false`. No replacement; the chosen model arrives on
  the `AiComplete` request. Recorded as `deprecated_in: "0.6"` /
  `removed_in: "0.8"` on the `AiGetModels` row of `spec/hooks.yaml` — the row is
  versioned against the Rust crate, which is the number the spec's rows use.

### Fixed
- **Registration is logged through the bridge, not only printed.** `Plugin.run`
  now emits `log.info("Registered with Astra …")` next to the existing
  `print`, which the logging bridge turns into a `PluginLog`. Two things follow:
  every Python plugin makes at least one authenticated host call on start — so
  `astra-plugin test` can assert a plugin talked to the daemon at all, and a
  host client that stopped sending `x-session-token` cannot pass conformance —
  and the bridge's stderr handler writes the line unbuffered, which is a second
  readiness signal for the daemon (it accepts a first line on either stream)
  even if this process's stdout is block-buffered for a reason the SDK cannot
  reach.
- `plugin_pb2.py` / `plugin_pb2_grpc.py` regenerated from the vendored proto.
  They had drifted: `tools/sync-proto.sh` copies `plugin.proto` and
  `tools/check-proto.sh` verifies the copy, but **nothing regenerates or checks
  the Python stubs**, so they still described `UninstallPlugin` as taking a
  `PluginIdRequest` several proto revisions after it stopped. Every stale method
  was on `PluginService` — the UI-facing service no plugin touches — so nothing
  broke, but the same gap would have silently dropped the §5.2 `error_detail`
  field. A CI check belongs with the conformance work in §5.7.
- **A handler that raises no longer takes the plugin with it (§5.10).** Every
  servicer method now catches `BaseException`, not `Exception`. The difference
  is not academic: `SystemExit` is not an `Exception`, so a library calling
  `sys.exit()` on a bad configuration escaped the handler, killed the `grpc.aio`
  RPC task, and left a plugin that was alive, passing its health check, and
  answering nothing. `asyncio.CancelledError` is deliberately re-raised —
  swallowing it turns a clean shutdown into a hang.
- The nine hooks that previously had no error handling at all are covered:
  `list_tools`, `tts_list_voices`, `stt_get_languages`, the two config-field
  hooks, `ai_get_models`, the two type-list hooks and `get_ui_contributions`
  fail with a status instead of an unhandled exception; `on_config_changed`,
  `on_language_changed` and `on_active_triggers` report rather than escaping as
  an UNKNOWN transport fault while the plugin runs on with stale state; a
  raising `health_check` answers `healthy=false` with the reason instead of
  looking like a dead process; and a raising `on_shutdown` no longer stops the
  shutdown, which the daemon's grace timer would otherwise end with a SIGKILL.
- `PluginError.detail` carries `traceback.format_exception` output for the
  exception that was adopted. It goes to the logger — and from there to the
  daemon's per-plugin log — and deliberately **not** into the response: the
  legacy `error` string is read by the AI loop, and a Python stack trace in the
  model's context costs tokens and teaches it nothing.
- `Plugin` publishes `port` once its capability server binds, and `_stop_event`
  so an embedder can stop it. `loop.add_signal_handler` failing off the main
  thread is no longer fatal — it raises `ValueError`, not the
  `NotImplementedError` the old code caught, so a plugin embedded in a larger
  process refused to start.
- **`Shutdown` now ends the process, not merely the gRPC server.** The handler
  stopped `self._server` and returned, while `_run_async` stayed parked on
  `_stop_event.wait()` — so the interpreter went on living with nothing left to
  serve, the daemon's grace timer expired, and the process group was SIGKILLed.
  Every Python plugin was killed rather than stopped, on every restart and every
  quit, and `on_shutdown`'s cleanup never ran on a user's machine.
  `astra-plugin test` reports the old behaviour as "the process was still
  running 5s after Shutdown"; the regression test is
  `test_shutdown_makes_the_process_exit_and_not_merely_the_server_stop`.
  `Shutdown` hands off to `_run_async`'s tidy path rather than duplicating it,
  so `on_shutdown` still runs exactly once.
- `Harness.call_tool` / `execute_action` / `ui_call` and their `WireHarness`
  counterparts take the RPC's target as a **positional-only** parameter. Written
  `call_tool(self, name, **arguments)`, a tool with a parameter of its own
  called `name` — which the scaffolded `hello` has, and which is about as common
  as a parameter gets — raised `TypeError: got multiple values for argument
  'name'`, with no spelling of the call that worked.
- `inspect.iscoroutinefunction`, not `asyncio.iscoroutinefunction`, in the
  `@tool` and `@action` dispatch. The latter is deprecated since 3.14 and
  removed in 3.16, and it made a freshly scaffolded plugin's first test run
  print a `DeprecationWarning` about the SDK.

### Version
- Still **0.5.0**, not 0.6.0. PyPI is at 0.4.0, so 0.5.0 has never shipped and
  these breaking changes land inside it rather than spending a minor nobody can
  install. Bumping would also strand the CLI's Python scaffold, which pins
  `astra-plugin-sdk>=0.5,<0.6`.

## [0.4.0] — 2026-05-24

### Added
- `Plugin.tts_config_fields()` and `Plugin.stt_config_fields()` hooks
  (default `[]`). A plugin's TTS/STT provider can declare extra
  Voice-settings fields the daemon renders generically via its
  `DynamicField` component. Field dicts mirror `FieldDefinitionMsg`:
  ``{id, label, field_type, default_value, min, max, has_min, ...}``.
  Internally backed by new RPCs `TtsGetConfigFields` /
  `SttGetConfigFields`.

### Fixed
- `plugin_pb2_grpc.py` regenerated import: top-level
  `import plugin_pb2` → relative `from . import plugin_pb2`, so
  the SDK imports correctly when installed via pip.

### Daemon compatibility
- Requires the data-driven Voice settings work in `astra-rs:refactor/
  voice-architecture` (Wave 4.2g-5).

## [0.3.0] — unreleased

### Added
- `Plugin.stt_transcribe(audio, sample_rate)` — non-streaming STT
  hook (default `raise NotImplementedError`). The SDK accumulates
  every `PluginAudioChunk` the daemon streams over `SttProcess`,
  then calls this once with the concatenated PCM payload. Returns
  either a transcript string or a dict
  ``{text, is_final, confidence, language}``.
- `SttProcess` servicer added — previously the RPC returned
  `UNIMPLEMENTED` for any plugin.

### Fixed
- Proto stubs (`plugin_pb2.py`, `plugin_pb2_grpc.py`) regenerated
  to match the canonical proto. Before this version,
  `daemon_client.py` imported `SubmitUserMessageResponse` /
  `FirehoseEventMsg` from outdated stubs and the package would
  crash on import in any plugin.

## [0.2.0] — 2025

Earlier development; see git history.

[0.5.0]: https://github.com/mihailinl/AstraPlugins/compare/python-v0.4.0...HEAD
[0.4.0]: https://github.com/mihailinl/AstraPlugins/compare/python-v0.3.0...python-v0.4.0
[0.3.0]: https://github.com/mihailinl/AstraPlugins/compare/python-v0.2.0...python-v0.3.0
[0.2.0]: https://github.com/mihailinl/AstraPlugins/releases/tag/python-v0.2.0
