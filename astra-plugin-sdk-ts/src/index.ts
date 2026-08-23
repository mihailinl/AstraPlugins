// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * Astra Plugin SDK for TypeScript.
 *
 * The npm package is **`astra-plugin-sdk`** — unscoped. `@astra/plugin-sdk` was
 * scaffolded for a scope that was never registered, so every project that
 * copied it 404'd on install.
 *
 * Two ways to write a plugin, and they compose: the object form for a plugin
 * that is a bag of tools, the class for one with state and a lifecycle.
 *
 * @example The object form — the schema is written once and narrows the handler.
 * ```typescript
 * import { plugin, tool, s } from "astra-plugin-sdk";
 *
 * plugin({
 *   tools: {
 *     hello: tool({
 *       description: "Greet someone.",
 *       input: s.object({ name: s.string(), excited: s.boolean().optional() }),
 *       run: ({ name, excited }) => `Hello, ${name}${excited ? "!" : "."}`,
 *     }),
 *   },
 * }).run();
 * ```
 *
 * @example The class form.
 * ```typescript
 * import { Plugin } from "astra-plugin-sdk";
 *
 * class MyPlugin extends Plugin {
 *   async listTools() {
 *     return [{ name: "hello", description: "Say hi", parametersJson: "{}" }];
 *   }
 *   async callTool(name: string, argumentsJson: string) {
 *     return { success: true, result: "Hello!" };
 *   }
 * }
 *
 * new MyPlugin().run();
 * ```
 *
 * Tests live behind a second entry point, so a shipped plugin does not carry
 * the harness: `import { Harness } from "astra-plugin-sdk/testing"`.
 */

export { Plugin, HookUnimplemented } from "./plugin.js";
export { plugin, tool, action } from "./define.js";
export type {
  PluginApp,
  PluginDefinition,
  ToolSpec,
  ToolEntry,
  ActionSpec,
  ActionEntry,
  TriggerEntry,
  TtsDefinition,
  SttDefinition,
  AiDefinition,
  UiDefinition,
  EventsDefinition,
  ToolOutcome,
} from "./define.js";
export { s, Schema, ObjectSchema, validate, formatIssues } from "./schema.js";
export type {
  AnySchema,
  AnyObjectSchema,
  ArrayOptions,
  Infer,
  InferShape,
  JsonSchema,
  NumberOptions,
  ObjectOptions,
  SchemaOptions,
  Shape,
  Simplify,
  StringOptions,
  ValidationIssue,
} from "./schema.js";
export { PluginContextImpl, NoHostError } from "./context.js";
export type { PluginContext, ContextSource } from "./context.js";
export type { Host, DaemonInfo } from "./host.js";
export { HostClient, RegistrationError } from "./host-client.js";
export type { RegisterResponse, RegisterErrorDetail } from "./host-client.js";
export {
  PluginError,
  BadArguments,
  NotFound,
  NotConfigured,
  Unauthorized,
  RateLimited,
  Unavailable,
  Timeout,
  InternalError,
  structuredErrorsSupported,
} from "./errors.js";
export type {
  PluginErrorCode,
  PluginErrorDetail,
  PluginErrorOptions,
  AnyPluginError,
  ToolError,
  ActionError,
} from "./errors.js";
export {
  evaluateProtocol,
  ProtocolMismatchError,
  EXIT_PROTOCOL_INCOMPATIBLE,
  MIN_SUPPORTED_DAEMON_PROTOCOL,
  PROTOCOL_VERSION,
  SDK_NAME,
  SDK_VERSION,
} from "./protocol.js";
export {
  EXIT_UNCAUGHT,
  LogBridge,
  consoleBridge,
  installConsoleBridge,
  installFatalHandlers,
  removeFatalHandlers,
  restoreConsole,
} from "./logging.js";
export type { LogLevel } from "./logging.js";
export { DaemonClient } from "./daemon-client.js";
export { I18n, key, PLUGIN_DIR_ENV } from "./i18n.js";
export { Field, UiContrib } from "./types.js";
export type {
  ToolDef,
  ToolResult,
  VoiceInfo,
  AudioData,
  SttEvent,
  AiModelInfo,
  ActionResult,
  FieldDef,
  ActionTypeDef,
  TriggerTypeDef,
  UiContribution,
  UiCallResult,
  UiPanel,
  AudioChunk,
  SttOptions,
  SttLoadState,
  SttLoadStatus,
  SttLoadRequest,
  AiToolCall,
  AiMessage,
  AiCompleteRequest,
  AiChunk,
  ThemeContribution,
  ChatChunk,
  StateChangedEvent,
  CommandTriggeredEvent,
  CommandCompletedEvent,
} from "./types.js";
export { ProtoContractError } from "./service-contract.js";
export { assertNoReservedNames, descriptorProblems, RETIRED_NAMES } from "./reserved.js";
export type { DescriptorProblem } from "./reserved.js";
export { PROTO_SHA256, PROTO_SOURCE, RESERVED_FIELD_NAMES, SERVICE_METHODS } from "./generated/index.js";
export * as limits from "./generated/limits.js";
export * as plural from "./generated/plural.js";
export * as wire from "./generated/wire.js";
