# Changelog — `astra-plugin-sdk` (Python)

All notable changes to this package. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This package is published to PyPI on `python-v<VERSION>` git tags via
the `publish-python.yml` workflow.

## [0.4.0] — unreleased

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

[0.4.0]: https://github.com/mihailinl/AstraPlugins/compare/python-v0.3.0...HEAD
[0.3.0]: https://github.com/mihailinl/AstraPlugins/compare/python-v0.2.0...python-v0.3.0
[0.2.0]: https://github.com/mihailinl/AstraPlugins/releases/tag/python-v0.2.0
