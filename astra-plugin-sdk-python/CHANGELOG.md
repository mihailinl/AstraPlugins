# Changelog — `astra-plugin-sdk` (Python)

All notable changes to this package. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This package is published to PyPI by the release train in
`.github/workflows/release-sdks.yml`, which runs on a single
`sdk-v<VERSION>` git tag and publishes all three SDKs together. That tag
names the Rust crate's version; this package keeps its own.

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
- `HostClientBootstrap` exported from the package root.
- `__version__` is now kept in lockstep with `pyproject.toml` (it had drifted
  to `0.3.0` while the package shipped as 0.4.0).

### Fixed
- `plugin_pb2.py` / `plugin_pb2_grpc.py` regenerated from the vendored proto.
  They had drifted: `tools/sync-proto.sh` copies `plugin.proto` and
  `tools/check-proto.sh` verifies the copy, but **nothing regenerates or checks
  the Python stubs**, so they still described `UninstallPlugin` as taking a
  `PluginIdRequest` several proto revisions after it stopped. Every stale method
  was on `PluginService` — the UI-facing service no plugin touches — so nothing
  broke, but the same gap would have silently dropped the §5.2 `error_detail`
  field. A CI check belongs with the conformance work in §5.7.

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
