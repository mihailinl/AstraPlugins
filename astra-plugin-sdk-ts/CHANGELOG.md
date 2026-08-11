# Changelog — `astra-plugin-sdk` (TypeScript)

All notable changes to this package. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This package is published to npm by the release train in
`.github/workflows/release-sdks.yml`, which runs on a single
`sdk-v<VERSION>` git tag and publishes all three SDKs together. That tag
names the Rust crate's version; this package keeps its own.

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
- **`errors.ts` — the error taxonomy (production plan §5.2).** Eight classes
  with the same eight codes the Rust and Python SDKs use: `BadArguments`,
  `NotFound`, `NotConfigured`, `Unauthorized`, `RateLimited`, `Unavailable`,
  `Timeout`, `InternalError`, all extending `PluginError`. `code` is a string
  literal on each class, so `AnyPluginError` is a discriminated union and
  `switch (err.code) { case "NOT_CONFIGURED": … }` narrows to the subclass and
  reaches `err.configField` with no cast — `instanceof` narrows too.
  Throw one from `callTool`, `executeAction` or `handleUiCall` and the SDK sets
  **both** halves of the response: the legacy `error` string — now
  `CODE: message (hint)`, the same shape the Rust and Python SDKs produce — and
  the structured `errorDetail` with `configField`, `retryAfterMs` and `docUrl`.
  A failure stays **in-band** (`success: false`) rather than becoming a gRPC
  status, because the AI loop has to read it; `grpcStatus()` is the fixed
  transport mapping, used only by the streaming hooks. Anything else a handler
  throws is adopted as `INTERNAL`, except `SyntaxError`/`TypeError` — what
  `JSON.parse` throws on the model's arguments — which are `BAD_ARGUMENTS`.
- **The six missing capability hooks (§5.4)**, each defaulting to
  `HookUnimplemented`, which the SDK answers as `UNIMPLEMENTED` — the
  protocol's word for *hook absent*, so declaring them changes nothing for a
  plugin that does not override them:
  - `aiComplete(request)` — an **async generator** (`AsyncIterable<AiChunk |
    string>`). The whole of the `ai_provider` capability, which no TypeScript
    plugin could implement before. The SDK appends the terminating `done` chunk
    and turns a thrown `PluginError` into the stream's in-band error chunk.
  - `ttsSynthesizeStream(text, voiceId, speed, pitch)` — an async generator of
    `AudioChunk`s or bare `Buffer`s; the SDK flags the real last chunk
    `isLast`. (The daemon has no call site for `TtsSynthesizeStream` yet.)
  - `sttLoad(modelPath, useGpu)`, `sttUnload()`, `sttLoadState()` — the model
    lifecycle that makes idle-unload actually free VRAM.
  - `ttsActivate(cek, voiceId)` — one-time machine-bound sealing of a licensed
    voice's content key.
  These four used to be registered as hard-coded `UNIMPLEMENTED` stubs, which
  made "this plugin does not do TTS" and "this SDK cannot do TTS"
  indistinguishable on the wire.
- `Plugin.sttTranscribeStream(audio, options)` — streaming STT as an
  `AsyncIterable`, so a recognizer can emit partials as the audio arrives.
  Implementing it takes precedence over `sttTranscribe`. The inbound gRPC stream
  is paused past `limits.STT_AUDIO_CHANNEL_CAPACITY` buffered chunks, so the
  sender feels back-pressure instead of audio being dropped.
- **`HostClient.sendChatMessage` and `HostClient.setThemeContribution`.**
  `client` was a capability no SDK could implement: the session token is scoped
  to `PluginHostService`, so the `DaemonClient`/`ChatService` route is
  `permission_denied` by construction and `SendChatMessage` is the only working
  path. It returns an `AsyncIterable<ChatChunk>` — a `for await`, not a raw
  `ClientReadableStream` — and a stream that ends in error throws out of the
  loop. Both are gated on the matching `[permissions]` key (§5.6);
  `set_theme_contribution` is refused below Tier 1 by Phase 4's consent gate.
- `Plugin.setVariable(name, value, scope)` — the convenience wrapper that
  `fireTrigger`/`pushToUi` already had.
- `sttTranscribe` gained a third argument, `options?: SttOptions` — the
  per-utterance language hint and wake-word bias from the first audio chunk.
  Optional, so an existing two-argument override still satisfies the type.
- New exported types: `AudioChunk`, `SttOptions`, `SttLoadState`,
  `SttLoadStatus`, `SttLoadRequest`, `AiToolCall`, `AiMessage`,
  `AiCompleteRequest` (with `reasoningEffort` and `showReasoning`), `AiChunk`,
  `ThemeContribution`, `ChatChunk`, plus `HookUnimplemented`.
- Capability discovery infers `ai_provider` from an `aiComplete` override rather
  than from `aiGetModels`, which is deprecated and returns `[]` by default — a
  provider that implemented the hook that matters used to register without the
  capability that names it.
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

### Version
- Still **0.5.0**, not 0.6.0. npm is at 0.4.0, so 0.5.0 has never shipped and
  these changes land inside it rather than spending a minor nobody can install.
  Bumping would also strand the CLI's TypeScript scaffold, which pins
  `"astra-plugin-sdk": "^0.5.0"`.

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
