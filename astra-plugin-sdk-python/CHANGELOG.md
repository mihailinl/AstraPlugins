# Changelog — `astra-plugin-sdk` (Python)

All notable changes to this package. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This package is published to PyPI on `python-v<VERSION>` git tags via
the `publish-python.yml` workflow.

## [0.5.0] — unreleased

Breaking. **Every 0.4.0 plugin is broken against the current daemon** — the
0.4.0 host stubs pass no `metadata=`, and the daemon answers
`unauthenticated` to every host RPC except `Register`.

### Changed (breaking)
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
- `astra_plugin_sdk.auth` — `CapabilityAuthInterceptor` guards the plugin's own
  `PluginCapabilityService` by demanding the spawn-time `--auth-token` back in
  the `x-plugin-token` header. Staged via `ASTRA_PLUGIN_CAPABILITY_AUTH`.
- `HostClientBootstrap` exported from the package root.
- `__version__` is now kept in lockstep with `pyproject.toml` (it had drifted
  to `0.3.0` while the package shipped as 0.4.0).

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
