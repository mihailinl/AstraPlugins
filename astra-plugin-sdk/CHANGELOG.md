# Changelog — `astra-plugin-sdk` (Rust)

All notable changes to this crate. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This crate is published to crates.io on `rust-v<VERSION>` git tags via
the `publish-rust.yml` workflow.

## [0.5.0] — unreleased

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

[0.5.0]: https://github.com/mihailinl/AstraPlugins/compare/rust-v0.4.0...HEAD
[0.4.0]: https://github.com/mihailinl/AstraPlugins/compare/rust-v0.3.0...rust-v0.4.0
[0.3.0]: https://github.com/mihailinl/AstraPlugins/compare/rust-v0.2.0...rust-v0.3.0
[0.2.0]: https://github.com/mihailinl/AstraPlugins/releases/tag/rust-v0.2.0
