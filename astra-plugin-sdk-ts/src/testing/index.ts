/**
 * `astra-plugin-sdk/testing` — the two levels a plugin is tested at.
 *
 * ```typescript
 * import { Harness, MockDaemon, utteranceChunks } from "astra-plugin-sdk/testing";
 * ```
 *
 * **Level 1, {@link Harness}** — in process, no socket. Drives the SDK's real
 * handler map with fake call objects, so the wire projections, the error
 * mapping and the bounded STT queue are all exercised. Fast enough to run on
 * every keystroke.
 *
 * **Level 2, {@link MockDaemon}** — a real gRPC server, a real handshake, a
 * real session token, real protobuf encoding. Slower, and the only place the
 * registration path, the interceptor and the casing can be checked at all.
 *
 * A suite wants both. Level 1 alone was green for the whole three releases in
 * which no SDK sent `x-session-token` and every host RPC failed on a user's
 * machine; level 2 alone is too slow to run per-tool.
 *
 * This entry point is exported separately from the SDK's own (`exports` map in
 * `package.json`), so a shipped plugin does not carry the harness.
 */

export { Harness, HookStatusError, SchemaAssertionError } from "./harness.js";
export type { Testable, SttRun } from "./harness.js";
export { RecordingHost } from "./recording-host.js";
export type {
  RecordedChat,
  RecordedLog,
  RecordedTrigger,
  RecordedUiPush,
  RecordedVariable,
  HostRpc,
} from "./recording-host.js";
export { MockDaemon, WirePlugin } from "./mock-daemon.js";
export type { MockDaemonOptions, RegisterRecord, HostCall } from "./mock-daemon.js";
export {
  FakeDuplexCall,
  FakeWritableCall,
  invokeBidi,
  invokeServerStream,
  invokeUnary,
  unaryCall,
} from "./calls.js";
export type { FakeStatus, UnaryOutcome } from "./calls.js";
export {
  SAMPLE_RATE,
  checksum,
  configFuzz,
  firehoseEvents,
  pcm16,
  totalBytes,
  utteranceChunks,
} from "./fixtures.js";
export type { UtteranceOptions } from "./fixtures.js";
