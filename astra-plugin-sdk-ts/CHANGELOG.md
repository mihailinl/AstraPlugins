# Changelog — `astra-plugin-sdk` (TypeScript)

All notable changes to this package. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

This package is published to npm by the release train in
`.github/workflows/release-sdks.yml`, which runs on a single
`sdk-v<VERSION>` git tag and publishes all three SDKs together. That tag
names the Rust crate's version; this package keeps its own.

**Deprecation policy** — `docs/en/versioning.md`. Nothing is deprecated for less
than two minors and one quarter; a deprecation note names its replacement; and a
**removal appears under a `BREAKING` heading in this file**, naming what went and
what replaced it. Deprecations live under `### Deprecated`, with the release they
are removable in.

## [0.7.0] — unreleased

A plugin can translate its own runtime strings; and `DaemonInfo` finally
declares the language field the wire has always carried.

**This is the minor slot, and the reason is three lines of `.d.ts`, not a
removal.** Nothing was deleted. Three exported interfaces gained a REQUIRED
property, and TypeScript treats that as a break for anybody who writes an
object literal or a class of their own against them:

```
error TS2741: Property 'language' is missing in type
'{ version: string; state: string; grpcPort: number; }'
but required in type 'DaemonInfo'.
```

That is `tsc` refusing a `DaemonInfo` literal that compiled against 0.6.0. Per
[`docs/en/versioning.md`](../docs/en/versioning.md)'s 0.x reading — *minor may
break source compatibility, patch is bug fixes and additions only* — a change
that can stop your build compiling belongs in the minor slot, even though every
runtime behaviour is backward compatible and the fix is one property.

### Changed (breaking)
- **`DaemonInfo.language: string` is required.** The daemon has sent
  `PluginDaemonInfoResponse.language` (field 4) since the field existed; this
  interface did not declare it, so a TypeScript plugin asking the daemon what
  language it was in got a value the type system said was not there. The Rust
  and Python SDKs return the proto message and never had the gap. **If you
  implement `Host` or build a `DaemonInfo` yourself**, add `language`;
  `"en"` is the right value for a test double. The SDK's own `RecordingHost`
  already does.
- **`PluginContext.i18n: I18n` is required**, and so is `ContextSource.i18n`.
  Both are exported types. If you hand-roll a `PluginContext` in a test, take
  `I18n.empty()` — or use the level-1 harness, which builds one for you.

### Added
- **`key()`** — marks a string the DAEMON renders (an action label, a
  config-field title, a `[ui]` label) as a `$key` reference into your
  `locales/`. `this.i18n` is the other plane and resolves in your process; the
  two are not interchangeable and [the reference
  page](../docs/en/3-reference/localisation.md) is the table of which surface
  resolves from which daemon.
- **`Plugin#i18n`** — this plugin's `locales/`, read on first use and kept on
  the plugin's current language. Assigning `this.language` now moves it too, so
  a handler never has to call `setLanguage` itself and a plugin that never
  implemented `onLanguageChanged` still follows the user.
- **`I18n.discover()`** — find `locales/` from `ASTRA_PLUGIN_DIR`
  (`PLUGIN_DIR_ENV`) or the executable's directory, rather than from whatever
  the process's cwd happens to be. **`I18n.empty()`** for the case where there
  is nothing to find, and `new I18n(null)` for the same.
- **`I18n#loadErrors` and `I18n#sourceDir`** — construction still never throws,
  but a locale file that would not parse is now nameable instead of silently
  absent.
- **`I18n#has()`**, **`I18n#ta()`** (named `{name}` placeholders), **`I18n#tn()`**
  (CLDR plurals; `{n}` is not substituted for you), **`I18n#countPrefixed()`**
  (distinct keys under a prefix, across the union of every loaded locale).
- **`plural`** namespace — the generated CLDR cardinal categories for the ten
  codes Astra accepts: `categories`, `isDeclared`, `category`, `CATEGORIES`,
  `SPEC_SHA256`.
- **`PLUGIN_DIR_ENV`** — the `ASTRA_PLUGIN_DIR` name as a constant.
- `ChatChunk.conversationId?` — informational, safe to show or log, and **not**
  a value to cache and send back later. Absent on a daemon older than the one
  that added it.
- `AiProviderCredentialsMsg.api_key` joins `RESERVED_FIELD_NAMES`.

### Fixed
- **`I18n#tf` replaced only the FIRST `{0}`, so the second was left on screen
  as the literal text `{0}`.** Russian and Ukrainian repeat a noun in two cases
  routinely, which is how it was found. Every occurrence is replaced now, as in
  the Rust and Python SDKs.

### Changed
- `HostClient#sendChatMessage`'s `conversationId` is documented rather than
  changed: empty means this plugin's own durable thread, an id is only ever one
  you were handed in the same exchange, and a stored id eventually names a
  conversation that is gone.
- The startup-order comment in `plugin.ts` said "the order all three SDKs use".
  It is the Rust and TypeScript order; the Python SDK runs language before
  config and always has. Neither is a protocol requirement.

### Deprecated

Unchanged, and named here because this release reaches the number in the table:
`UiPanel` (deprecated 0.5.0, replacement `UiContribution`) becomes **removable**
from 0.7.0 per [`docs/en/versioning.md`](../docs/en/versioning.md). It is NOT
removed in this release — removals go under a `BREAKING` heading and there is
none. Migrate at your convenience; the alias is a one-line rename.

### Compatibility

`PROTOCOL_VERSION` is unchanged at `1`. A plugin that ships no `locales/`
directory is unaffected: `I18n.discover()` finds nothing, `hasLocales` is
`false`, and `t()` returns the key exactly as before.

## [0.6.0] — 2026-08-16

A trigger a plugin fires from inside a call now names the call that caused it.

A plugin action runs inside a command run the user started by typing. When the
plugin fires a trigger, that starts a second run — and until now the second run
had no idea what caused it, so its output was filed into a fresh conversation
the user never saw. With two chats driving one plugin at once, nothing on the
wire told them apart.

The daemon mints a lease when it calls into a plugin and carries it as
`x-astra-cause`; the SDK echoes it back when the plugin fires. Nothing here
invents a value, and nothing sends the key when it was not handed one.

### Changed (breaking)
- **`CommandTriggeredEvent.triggerText` is gone**, because the daemon no longer
  sends `trigger_text`. It was the phrase the user typed or spoke — or, for a
  plugin's own fire, the whole payload it sent — delivered to every plugin that
  declared `command_triggered`. Asking to hear that commands run is not asking
  to hear what the user said, so the daemon narrows this event now and the
  field has no place on the wire to ride in. Keeping the property would have
  produced `""` on every event forever, which is the same "looks like an
  answer" failure `variables` had before it.
- **`CommandTriggeredEvent.commandName` is now `""` unless YOUR fire started
  the command.** A command's name is the user's own writing. The key is always
  present, so the shape you decode does not depend on who is reading.
- **`CommandCompletedEvent.commandName` is now `""` for everybody.** That event
  carries nothing that says whose fire it was, so there is no reader the daemon
  can safely give the name to. Correlate on `commandId`.

### Added
- `CommandTriggeredEvent.triggerType` — WHICH doorbell rang, as a machine
  identifier: `text`, `hotkey`, `reminder`, `calendar_event`, `schedule`, or
  `plugin__<id>__<event>` for a plugin's own trigger.
- `CommandTriggeredEvent.runId` — the run the fire started, so it can be joined
  to the later `command_completed`.
- `CommandTriggeredEvent.firedBy` — non-null only when the fire was yours, so
  it never enumerates the plugins installed on the machine.
- `fireTriggerCausedBy` on the host client, and the cause carried through the
  call context.
- Generated limits for the invocation lease.

### Compatibility

Breaking for one payload, non-breaking on the wire. `PROTOCOL_VERSION` is unchanged at `1` — a
bump would make the daemon refuse every already-published plugin. Existing
code compiles and runs untouched: `examples/dice-roller` does not change by one
character. A plugin built against an older SDK simply drops the cause, and the
daemon treats absent, unknown, expired and exhausted the same way — the event
becomes a root event rather than an error. **Correct but unattributed, never
wrong.**

Retiring next release, named here so nobody meets it as silence: the event
types `tts_request`, `tts_stream_start`, `tts_stream_chunk`, `tts_stream_end`
and `stop_speaking`. The daemon validates a manifest's `event_types` at
registration against the live set and answers a retired one by name.

## [0.5.0] — 2026-08-11

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
- **Typed daemon events are decoded from the daemon's key names.** The payload
  handed to `onCommandTriggered` / `onCommandCompleted` / `onStateChanged` was
  the parsed `payload_json` `as`-cast to a camelCase shape, so
  `event.commandId` was `undefined` on every event forever while the compiler
  agreed it was a `string`. The daemon serializes `AstraEvent` with
  `#[serde(tag = "type", rename_all = "snake_case")]`, and `rename_all` on an
  enum renames the *variants*, not their fields: the wire keys are
  `command_id`, `command_name`, `trigger_text`. `dispatchEvent` now reads those
  and builds `StateChangedEvent` / `CommandTriggeredEvent` /
  `CommandCompletedEvent` (all three exported from the package root).
- `CommandTriggeredEvent.variables` is gone, replaced by `triggerText`. No
  daemon has ever sent a variables map on this event in any language.
- The registration line is logged *after* the console bridge is installed, so
  it reaches the daemon as a `PluginLog`. Every plugin now makes at least one
  authenticated host call on start, which is what lets `astra-plugin test`
  assert that a plugin talked to the daemon at all.

### Added
- **A trigger fired while handling a daemon call names the call that caused
  it.** The capability server enters an `AsyncLocalStorage` store around every
  handler, and `HostClient.fireTrigger` reads it and attaches the invocation
  lease as gRPC metadata (`spec/wire.yaml`'s `x-astra-cause`). The daemon
  redeems the lease to decide which conversation the trigger's output belongs
  in — today it lands in a freshly auto-created chat the user never sees, and
  with two chats driving one plugin at once nothing on the wire even
  distinguishes them.

  **The read is in the transport, deliberately.** All three ways to fire —
  `HostClient.fireTrigger`, `PluginContext.fireTrigger` and the
  `Plugin.fireTrigger` wrapper — converge there, and the wrapper routes to the
  process-global host. A read one layer up would leave unstamped the very path
  the docs teach.

  **Nothing to do, and nothing to change.** The store follows `await`,
  `setTimeout` and promise chains, so a handler that defers still fires with its
  cause. A `child_process`, a `worker_threads` worker, or a timer started
  outside a handler gets none, and its fires are root events — the honest
  answer, and where every plugin lands today.

  **Inert until a daemon issues leases.** No daemon in the field does.
- `MockDaemon.firedTriggers()` reports `causedBy`, read off the metadata as it
  arrived on the socket. A plugin's own tests can now assert *where* a
  trigger's output was going to land, not only that it fired. `HostCall` grows
  the same field, and `WirePlugin.callTool` takes `{ causedBy }` so a test can
  issue a call the way the daemon will.
- `wire` module (`export * as wire`): the gRPC metadata keys, generated from
  `spec/wire.yaml`. `x-session-token` and `x-plugin-token` used to be spelled by
  hand in fifteen places across the three SDKs and the CLI. A metadata key is a
  map entry, so a misspelling is not an error — it is an absence, and absence is
  legal for all three. The typo silently removes authentication, or attribution,
  and says nothing.
- `limits`: `LEASE_TTL_SECS`, `LEASE_FIRE_GRACE_SECS`, `LEASE_MAX_FIRES`.
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
  (`off` | `warn` | `require`). **The daemon now ships its half**: it presents
  the token on every call into a plugin and sets that variable to `require` on
  every spawn, so a plugin enforces with nothing to configure. The default stays
  `warn`, which is what a daemon too old to send the header leaves a plugin in —
  the variable's absence is the only signal such a daemon gives.
- `RegistrationError`, `ProtoContractError`, and the `RegisterResponse` /
  `DaemonInfo` / `UiContribution` / `UiCallResult` types are exported.
- `PROTO_SHA256` / `PROTO_SOURCE` / `SERVICE_METHODS` from the generated
  descriptor, so a plugin can assert which proto it was built against.
- `npm run generate` / `typecheck` / `test` scripts; `prebuild` and `pretest`
  regenerate the descriptor so it can never go stale in a published tarball.
- **`plugin({...})` — the object form, and the `s` schema builder (§5.8).**
  A tool declares its parameters once as `s.object({...})`; the SDK emits the
  JSON Schema the model reads, validates the arguments the model sends, and
  hands the handler a parameter whose TypeScript type came from that same
  declaration. `Infer<typeof schema>` names it elsewhere. `.optional()` means
  both "not in `required`" and `key?: T`, and the two cannot drift:
  `types-test/schema-agreement.ts` compiles only if the inferred type accepts
  every fixture the emitted schema validates and rejects every one it does not,
  which `tools/schema.test.mjs` then checks from the runtime side. Objects emit
  `additionalProperties: false`. `tool()` / `action()` are the per-entry
  wrappers that make the inference work (a generic is inferred per call, and a
  bare object literal inside `tools: { … }` is one context for all of them).
  The class form is unchanged and unaffected.
- **`PluginContext` (§5.1, in TypeScript).** `ctx()` on `Plugin`, and the second
  argument of every handler in the object form: `config`, `language`,
  `activeTriggers`, `host`, plus `log`/`info`/`warn`/`error`, `fireTrigger`,
  `setVariable`, `pushToUi`, `setThemeContribution`, `sendChatMessage` and
  `configValue(key, fallback)`. It reads through to the live plugin, so a task
  that captured it at `onStart` sees the config as it is now. Reaching for the
  daemon before there is one **rejects** with `NoHostError` instead of doing
  nothing quietly, which is what `Plugin`'s own convenience wrappers do.
- **`onStart(ctx)`**, and the lifecycle order all three SDKs now share:
  bind → register → ctx → `onConfigChanged` → `onLanguageChanged` → `onStart` →
  serve. Config now arrives before language, not after.
- **`astra-plugin-sdk/testing` — the two test levels (§5.6).**
  `Harness` is level 1: in process, no socket, driving the SDK's real handler
  map through fake call objects that honour `pause()`/`resume()`, so the wire
  projections, the error mapping and the bounded STT queue are all exercised.
  `RecordingHost` implements the whole `Host` interface in memory, records
  every call (`firedTriggers()`, `logs()`, `variables()`, `uiPushes()`,
  `chatMessages()`) and injects failures (`fail`, `failAlways`).
  `MockDaemon` is level 2: a real gRPC server serving `PluginHostService`, a
  real spawn token, a real session-token check on every call but `Register`,
  and a `PluginCapabilityService` client dialling the port the plugin bound —
  the only place handler registration, descriptor mismatch, the interceptor and
  `keepCase` casing can be checked at all. Fixtures: `utteranceChunks()` (a
  golden 16 kHz utterance with an 8 s wake-seed burst, longer than the 500-slot
  channel), `firehoseEvents()`, and `configFuzz()` behind `h.fuzzConfig()`.
- **`Host` is an interface** (`src/host.ts`), and `Plugin.host` is typed as it.
  `HostClient implements Host`, so a host RPC added to one and not the other is
  a compile error rather than a hook no test can reach.
- **`console` → `PluginLog`, and crash containment (§5.10).**
  `installConsoleBridge` routes `console.log/info/debug/warn/error` into the
  daemon's log pane while still printing locally; the queue is bounded at 512
  lines, drops the oldest and says how many with the next line that gets
  through, and a re-entrancy guard stops a transport that logs from feeding
  itself. `installFatalHandlers` turns an `uncaughtException` or
  `unhandledRejection` into an `error`-level `PluginLog` and an exit with
  `EXIT_UNCAUGHT` (70, `EX_SOFTWARE`) — a code the daemon can tell apart from an
  orderly stop.
- **The reserved-name startup assertion (§5.8).** `assertNoReservedNames()`
  runs in `run()` before the server binds and answers three questions the
  descriptor cannot answer itself: is every generated service and method really
  reachable on the loaded stub (TypeScript's own failure mode is `undefined`,
  which is how three handlers were dropped for a release); has a field the
  proto `reserved` come back as live; has a name Phase 1 retired come back.
  `RESERVED_FIELD_NAMES` is generated from the proto; `RETIRED_NAMES` is the
  Phase 1 deletions. `descriptorProblems()` returns the list for a test.

### Deprecated

Removed in **0.7.0** — two minors and one quarter, the minimum window
`docs/en/versioning.md` promises. Both are marked `/** @deprecated … */`, so the
note reaches you in the editor rather than in a release note nobody re-reads.

- **`UiPanel`** — an alias for `UiContribution`, and the only deprecation in
  this package that carried **no version at all**, which is precisely what the
  policy exists to stop. It is dated 0.5.0 here, the first release that says so
  in writing, and removable from 0.7.0. Replacement: `UiContribution`.
- **`aiGetModels()`** — the daemon never asks: `all_ai_providers` hardcodes
  `supports_model_discovery=false`, so the picker never calls it. No
  replacement; the chosen model arrives on the `aiComplete` request. Recorded as
  `deprecated_in: "0.6"` / `removed_in: "0.8"` on the `AiGetModels` row of
  `spec/hooks.yaml`, whose versions track the Rust crate.

### Packaging
- **Dual CommonJS + ESM.** `"type": "commonjs"`, an `exports` map with `.` and
  `./testing`, `engines: { node: ">=20" }`, `moduleResolution: "node16"`.
  CommonJS stays at `dist/` (what `main`, `types` and every existing `require`
  already point at); ES modules are emitted to `dist/esm/` with a
  `{"type":"module"}` marker written by `tools/finish-build.mjs`. Every relative
  import in `src/` now carries its `.js` extension, which is what lets one
  source tree emit both formats.
- The generated descriptor is imported as a TypeScript module
  (`src/generated/descriptor.ts`) rather than as a JSON import: Node's ESM
  loader refuses a JSON specifier without an import attribute, so the ESM build
  would have thrown on first use. `descriptor.json` is still generated, still
  shipped, and asserted byte-equal to the module by the test suite.
- The four places that said `@astra/plugin-sdk` — a scope that was never
  registered — now say `astra-plugin-sdk`. The name still appears in prose that
  names it as the bug it was.

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
