# Changelog — `astra-plugin-sdk` (Rust)

All notable changes to this crate. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This crate is published to crates.io on `rust-v<VERSION>` git tags via
the `publish-rust.yml` workflow.

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
  carries `init_tracing`, `argv`, `bind_addr` and `capability_auth`.
- The SDK filters argv down to the daemon's own flags (`--daemon-addr`,
  `--plugin-id`, `--auth-token`), so a plugin may define its own CLI without
  `Args::parse()` aborting the process.

### Fixed
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
