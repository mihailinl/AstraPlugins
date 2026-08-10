/**
 * Astra Plugin SDK for TypeScript
 *
 * @example
 * ```typescript
 * import { Plugin } from "@astra/plugin-sdk";
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
 */

export { Plugin } from "./plugin";
export { HostClient, RegistrationError } from "./host-client";
export type { RegisterResponse, RegisterErrorDetail, DaemonInfo } from "./host-client";
export {
  evaluateProtocol,
  ProtocolMismatchError,
  EXIT_PROTOCOL_INCOMPATIBLE,
  MIN_SUPPORTED_DAEMON_PROTOCOL,
  PROTOCOL_VERSION,
  SDK_NAME,
  SDK_VERSION,
} from "./protocol";
export { DaemonClient } from "./daemon-client";
export { I18n } from "./i18n";
export { Field, UiContrib } from "./types";
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
} from "./types";
export { ProtoContractError } from "./service-contract";
export { PROTO_SHA256, PROTO_SOURCE, SERVICE_METHODS } from "./generated";
export * as limits from "./generated/limits";
