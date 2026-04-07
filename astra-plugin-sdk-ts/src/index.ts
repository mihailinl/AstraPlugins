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
export { HostClient } from "./host-client";
export { Field } from "./types";
export type {
  ToolDef,
  ToolResult,
  VoiceInfo,
  AudioData,
  AiModelInfo,
  ActionResult,
  FieldDef,
  ActionTypeDef,
  TriggerTypeDef,
  UiPanel,
} from "./types";
