# Changelog — `astra-plugin-sdk` (TypeScript)

All notable changes to this package. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This package is published to npm on `ts-v<VERSION>` git tags via the
`publish-ts.yml` workflow.

## [0.4.0] — unreleased

### Added
- `Plugin.ttsConfigFields()` and `Plugin.sttConfigFields()` hooks
  (default `[]`). A plugin's TTS/STT provider can declare extra
  Voice-settings fields the daemon renders generically via its
  `DynamicField` component. Use the exported `fields` builder
  (`fields.text(...).withDefault(...)`) for ergonomics. Backed by
  new RPCs `TtsGetConfigFields` / `SttGetConfigFields` on
  `PluginCapabilityService`.

### Daemon compatibility
- Requires the data-driven Voice settings work in `astra-rs:refactor/
  voice-architecture` (Wave 4.2g-5).

## [0.3.0] — unreleased

### Added
- `Plugin.sttTranscribe(audio, sampleRate)` — non-streaming STT
  hook. The SDK accumulates every `PluginAudioChunk` the daemon
  streams over `SttProcess`, then calls this once with the
  concatenated PCM payload. Returns one `SttEvent`.
- `SttProcess` handler — previously the RPC returned
  `UNIMPLEMENTED` for any plugin.

## [0.2.0] — 2025

Earlier development; see git history.

[0.4.0]: https://github.com/mihailinl/AstraPlugins/compare/ts-v0.3.0...HEAD
[0.3.0]: https://github.com/mihailinl/AstraPlugins/compare/ts-v0.2.0...ts-v0.3.0
[0.2.0]: https://github.com/mihailinl/AstraPlugins/releases/tag/ts-v0.2.0
