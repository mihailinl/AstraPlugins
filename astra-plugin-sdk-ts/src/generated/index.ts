/**
 * AUTO-GENERATED — DO NOT EDIT.
 *
 * Produced by `tools/gen-descriptor.mjs` from `proto/plugin.proto`.
 * Regenerate with `npm run generate`; `npm run build` does it for you.
 */

import descriptorJson from "./descriptor.json";

/**
 * A protobuf.js JSON namespace (`protobuf.Root#toJSON()`), narrowed to the one
 * property `@grpc/proto-loader`'s `fromJSON()` needs. Kept structural so the
 * SDK carries no runtime dependency on protobufjs' type declarations.
 */
export interface ProtoDescriptorJson {
  nested: Record<string, unknown>;
}

/** The compiled protocol descriptor. Load it with `protoLoader.fromJSON()`. */
export const descriptor: ProtoDescriptorJson = descriptorJson as ProtoDescriptorJson;

/** Repo-relative path of the proto this descriptor was generated from. */
export const PROTO_SOURCE = "proto/plugin.proto";

/** SHA-256 of that proto file, so a drifted descriptor is detectable in CI. */
export const PROTO_SHA256 = "36536b547e14a1eeab3620964828d5cde59c0dcf5deed574fbd6b98fca1d667b";

/** The protobuf package every Astra service lives in. */
export const PROTO_PACKAGE = "astra";

/**
 * Every service in the descriptor and the methods it declares, in declaration
 * order. The startup contract check in `service-contract.ts` compares handler
 * maps against this.
 */
export const SERVICE_METHODS = {
  CoreService: ["GetState", "Start", "Stop", "Shutdown", "SubscribeEvents"],
  AuthService: ["GetStatus", "StartLogin", "Logout", "RefreshToken"],
  ChatService: ["SubmitUserMessage", "StopGeneration", "RespondToConfirmation", "ListConversations", "CreateConversation", "DeleteConversation", "ClearConversation", "SubscribeEvents"],
  VoiceService: ["StartListening", "StopListening", "GetMicrophones", "SetMicrophone", "Speak", "StopSpeaking", "GetVoices", "SetVoice", "GetWhisperModels", "DownloadWhisperModel", "GetDownloadProgress", "CancelDownload", "DeleteWhisperModel", "SearchVoices", "GetTtsProviders", "GetEmbeddingModels", "DownloadEmbeddingModel", "GetEmbeddingDownloadProgress", "CancelEmbeddingDownload", "DeleteEmbeddingModel", "GetLlmMatchModels", "DownloadLlmMatchModel", "GetLlmMatchDownloadProgress", "CancelLlmMatchDownload", "DeleteLlmMatchModel", "SetVoiceConversation"],
  CommandService: ["List", "Get", "Create", "Update", "Delete", "Execute", "SetEnabled", "GetCursorPosition"],
  ConfigService: ["GetSettings", "UpdateSettings", "CompleteOobe", "ResetSettings", "ExportSettings", "ImportSettings", "GetModels", "GetAiProviders", "GetWidgetData", "SaveWidgetData", "GetIndexerStatus"],
  MediaService: ["GetMediaState", "ControlMedia", "SubscribeMediaState", "GetMediaSessions"],
  RegistryService: ["GetActionTypes", "GetTriggerTypes"],
  TaskService: ["GetTasks", "CancelTask"],
  MonitorService: ["GetSystemStats", "SubscribeSystemStats"],
  CompanionService: ["SubscribeCommands", "ReportStatus", "ReportBlendshapes", "SendCommand", "GetCompanionStatus"],
  McpService: ["ListServers", "AddServer", "UpdateServer", "RemoveServer", "StartServer", "StopServer", "GetServerTools", "SetToolEnabled", "RefreshServerTools", "SearchCatalog", "GetCatalogServer", "InstallCatalogServer", "CheckRuntimes", "InstallRuntime"],
  MarketplaceService: ["Browse", "GetFeatured", "GetListing", "Install", "CheckUpdates", "UpdateInstalled", "Uninstall", "GetInstalled", "Publish", "GetMyListings", "ToggleStar", "SubmitReview", "GetReviews", "ReportListing"],
  OobeService: ["DiscoverApps", "FilterApps", "GenerateTriggers"],
  PluginService: ["ListPlugins", "InstallPlugin", "UninstallPlugin", "SetPluginEnabled", "StartPlugin", "StopPlugin", "GetPluginConfig", "UpdatePluginConfig", "BrowsePluginRegistry", "CheckPluginUpdates", "UpdatePlugin", "SideloadPlugin", "ImportPluginFile", "GetPluginLogs", "GetAllUiContributions", "GetActiveThemes", "CallPluginFromUi"],
  PluginHostService: ["Register", "SubscribeEvents", "SendChatMessage", "FireTrigger", "GetPluginSelfConfig", "PluginLog", "GetDaemonInfo", "SetVariable", "SetThemeContribution", "PushToUi"],
  PluginCapabilityService: ["ListTools", "CallTool", "TtsSynthesize", "TtsSynthesizeStream", "TtsListVoices", "TtsGetConfigFields", "SttProcess", "SttGetLanguages", "SttGetConfigFields", "AiComplete", "AiGetModels", "ExecuteAction", "GetPluginActionTypes", "GetPluginTriggerTypes", "GetUiContributions", "CallFromUi", "OnConfigChanged", "OnActiveTriggers", "OnLanguageChanged", "Shutdown", "HealthCheck"],
  ClientAuthService: ["RegisterClient", "DisconnectClient"],
} as const satisfies Record<string, readonly string[]>;

/** Name of a service declared by `proto/plugin.proto`. */
export type ServiceName = keyof typeof SERVICE_METHODS;

/** Every RPC the daemon may call on a plugin. A plugin must handle all of them. */
export type PluginCapabilityMethod =
  | "ListTools"
  | "CallTool"
  | "TtsSynthesize"
  | "TtsSynthesizeStream"
  | "TtsListVoices"
  | "TtsGetConfigFields"
  | "SttProcess"
  | "SttGetLanguages"
  | "SttGetConfigFields"
  | "AiComplete"
  | "AiGetModels"
  | "ExecuteAction"
  | "GetPluginActionTypes"
  | "GetPluginTriggerTypes"
  | "GetUiContributions"
  | "CallFromUi"
  | "OnConfigChanged"
  | "OnActiveTriggers"
  | "OnLanguageChanged"
  | "Shutdown"
  | "HealthCheck";

/** Every RPC a plugin may call on the daemon. */
export type PluginHostMethod =
  | "Register"
  | "SubscribeEvents"
  | "SendChatMessage"
  | "FireTrigger"
  | "GetPluginSelfConfig"
  | "PluginLog"
  | "GetDaemonInfo"
  | "SetVariable"
  | "SetThemeContribution"
  | "PushToUi";
