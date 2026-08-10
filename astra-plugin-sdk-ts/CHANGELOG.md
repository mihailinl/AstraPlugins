# Changelog — `astra-plugin-sdk` (TypeScript)

All notable changes to this package. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This package is published to npm on `ts-v<VERSION>` git tags via the
`publish-ts.yml` workflow.

## [0.5.0] — unreleased

Breaking. **Every 0.4.0 plugin is broken against the current daemon** — the
0.4.0 clients pass no `grpc.Metadata`, so every host RPC but `Register` comes
back `unauthenticated`, and `DaemonClient` loaded an inline proto string that
predates the chat event-sourcing migration, so its methods were `undefined`
at runtime.

### Changed (breaking)
- `HostClient`'s constructor is private. The only way to obtain one is
  `HostClient.register(...)`, which performs the bootstrap `Register` call
  itself and returns a client already holding the `x-session-token` metadata.
  A rejected registration — or one that yields no token — throws
  `RegistrationError`.
- Both clients load the SDK's own `plugin.proto` through a generated
  descriptor instead of the two hand-maintained inline proto strings.
  `assertClientContract` checks every method the client will call against
  that descriptor at connect time and throws `ProtoContractError` rather than
  failing with `TypeError` on the first call.
- `DaemonClient` creation and the chat firehose are gated on `isClient()`,
  not on the session token being non-empty.

### Added
- `capability-auth.ts` — `guardHandlers` wraps every
  `PluginCapabilityService` handler with a check that the caller presented the
  spawn-time `--auth-token` back in the `x-plugin-token` header, so a local
  process that is not the daemon can no longer reach the plugin's tools,
  config or shutdown. Staged via `ASTRA_PLUGIN_CAPABILITY_AUTH`
  (`off` | `warn` | `require`); `warn` is the default while daemons that
  predate the header are in the field.
- `RegistrationError`, `ProtoContractError`, and the `RegisterResponse` /
  `DaemonInfo` / `UiContribution` / `UiCallResult` types are exported.
- `PROTO_SHA256` / `PROTO_SOURCE` / `SERVICE_METHODS` from the generated
  descriptor, so a plugin can assert which proto it was built against.
- `npm run generate` / `typecheck` / `test` scripts; `prebuild` and `pretest`
  regenerate the descriptor so it can never go stale in a published tarball.

## [0.4.0] — 2026-05-24

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

[0.5.0]: https://github.com/mihailinl/AstraPlugins/compare/ts-v0.4.0...HEAD
[0.4.0]: https://github.com/mihailinl/AstraPlugins/compare/ts-v0.3.0...ts-v0.4.0
[0.3.0]: https://github.com/mihailinl/AstraPlugins/compare/ts-v0.2.0...ts-v0.3.0
[0.2.0]: https://github.com/mihailinl/AstraPlugins/releases/tag/ts-v0.2.0
