/**
 * AUTO-GENERATED — DO NOT EDIT.
 *
 * Produced by `tools/gen-descriptor.mjs` from `proto/plugin.proto`.
 * Regenerate with `npm run generate`; `npm run build` does it for you.
 */

import { descriptorJson } from "./descriptor.js";

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

/**
 * `reserved "name";` declarations, keyed by the message that owns them.
 *
 * Checked at startup by `src/reserved.ts`: a reserved name that comes back as a
 * live field is a wire meaning colliding with the one a daemon in the field
 * still remembers.
 */
export const RESERVED_FIELD_NAMES: Readonly<Record<string, readonly string[]>> = {
  "astra.MoveOfferResponse": ["mode", "offer_text", "consent_text", "problem", "pressed_at", "offer_sha256", "consent_sha256"],
  "astra.SemanticSettings": ["mode", "llm_model_id", "memory_enabled"],
  "astra.AiSettings": ["use_thinking"],
  "astra.AiProviderCredentialsMsg": ["api_key"],
  "astra.CustomAiProviderMsg": ["api_key"],
  "astra.HotkeySettings": ["toggle_listen", "stop_speaking", "open_chat"],
};

/** Repo-relative path of the proto this descriptor was generated from. */
export const PROTO_SOURCE = "proto/plugin.proto";

/** SHA-256 of that proto file, so a drifted descriptor is detectable in CI. */
export const PROTO_SHA256 = "b0482d147a73cb9a722d7f7baec9a0bf4adfc476863dbfb73ccdb589ad3e0720";

/** The protobuf package every Astra service lives in. */
export const PROTO_PACKAGE = "astra";

/**
 * Every service in the descriptor and the methods it declares, in declaration
 * order. The startup contract check in `service-contract.ts` compares handler
 * maps against this.
 */
export const SERVICE_METHODS = {
  CoreService: ["GetState", "Start", "Stop", "Shutdown", "Restart", "SubscribeEvents", "ShowMainWindow", "ToggleOverlay", "GetLogLocation", "CollectLogs", "GetMoveOffer"],
  ChatService: ["SubmitUserMessage", "StopGeneration", "StopAgentRun", "RespondToConfirmation", "ListConversations", "CreateConversation", "DeleteConversation", "ClearConversation", "SubscribeEvents", "FetchConversationBacklog", "RegenerateAssistantMessage", "EditUserMessage", "SetConversationReasoning", "GetConversationPermissions", "SetConversationPermissionMode", "RevokePermissionGrant"],
  VoiceService: ["StartListening", "StopListening", "GetMicrophones", "SetMicrophone", "StartMicCheck", "GetMicLevel", "StopMicCheck", "GetOutputDevices", "SetOutputDevice", "Speak", "StopSpeaking", "GetVoices", "SetVoice", "GetWhisperModels", "DownloadWhisperModel", "GetDownloadProgress", "CancelDownload", "DeleteWhisperModel", "SearchVoices", "GetTtsProviders", "GetSttProviders", "GetVoiceModels", "DownloadVoiceModel", "DeleteVoiceModel", "GetVoiceModelDownloadProgress", "CancelVoiceModelDownload", "SetVoiceModel", "GetWakewordProviders", "GetSupertonicStatus", "DownloadSupertonicModels", "GetSupertonicDownloadProgress", "CancelSupertonicDownload", "DeleteSupertonicModels", "ListSupertonicVoices", "ImportSupertonicVoice", "DeleteSupertonicVoice", "ActivateVoxVoice", "GetEmbeddingModels", "DownloadEmbeddingModel", "GetEmbeddingDownloadProgress", "CancelEmbeddingDownload", "DeleteEmbeddingModel", "SetVoiceConversation", "SetVoicePendingImages", "SetPushToTalk"],
  CommandService: ["List", "Get", "Create", "Update", "Delete", "Execute", "LaunchFile", "SetEnabled", "GetCursorPosition", "ListGroups", "CreateGroup", "UpdateGroup", "DeleteGroup", "MoveCommandToGroup"],
  ConfigService: ["GetSettings", "UpdateSettings", "SetSetting", "SaveWidgetPanel", "CompleteOobe", "ResetSettings", "ResetSettingsGroup", "ExportSettings", "ImportSettings", "GetModels", "GetImageModels", "GetAiProviders", "TestAiProvider", "GetWidgetData", "SaveWidgetData", "ActOnReminder", "GetWidgetDescriptors", "GetIndexerStatus", "GetHotkeyBindings", "ConfigureHotkey", "GetCurrentWeather", "GetWeatherForecast", "DetectLocation", "GetCurrencyRate", "GetCurrencySeries", "GetCryptoRate", "GetCryptoSeries", "ListBrowsers", "StartIndexer", "RescanIndex"],
  MediaService: ["GetMediaState", "ControlMedia", "SubscribeMediaState", "GetMediaSessions", "CaptureScreen"],
  MonitorService: ["GetSystemStats", "SubscribeSystemStats", "SubscribeToolSearchEvents"],
  PluginService: ["ListPlugins", "InstallPlugin", "InstallPluginStream", "CancelPluginInstall", "UninstallPlugin", "ReportPlugin", "SetPluginEnabled", "StartPlugin", "StopPlugin", "GetPluginConfig", "UpdatePluginConfig", "BrowsePluginRegistry", "CheckPluginUpdates", "UpdatePlugin", "SideloadPlugin", "ImportPluginFile", "InspectPluginFile", "ResolvePendingUpdate", "GetPluginLogs", "GetPluginProvenance", "GetAllUiContributions", "GetActiveThemes", "CallPluginFromUi"],
  PluginHostService: ["Register", "SubscribeEvents", "SendChatMessage", "FireTrigger", "GetPluginSelfConfig", "PluginLog", "GetDaemonInfo", "SetVariable", "SetThemeContribution", "PushToUi"],
  PluginCapabilityService: ["ListTools", "CallTool", "TtsSynthesize", "TtsSynthesizeStream", "TtsListVoices", "TtsGetConfigFields", "TtsActivate", "SttProcess", "SttGetLanguages", "SttGetConfigFields", "SttLoad", "SttUnload", "SttGetLoadState", "AiComplete", "AiGetModels", "WebSearch", "MusicSubscribe", "MusicControl", "MusicGetQueue", "MusicSearch", "MusicPlay", "ExecuteAction", "GetPluginActionTypes", "GetPluginTriggerTypes", "GetUiContributions", "CallFromUi", "OnConfigChanged", "OnActiveTriggers", "OnLanguageChanged", "Shutdown", "HealthCheck"],
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
  | "TtsActivate"
  | "SttProcess"
  | "SttGetLanguages"
  | "SttGetConfigFields"
  | "SttLoad"
  | "SttUnload"
  | "SttGetLoadState"
  | "AiComplete"
  | "AiGetModels"
  | "WebSearch"
  | "MusicSubscribe"
  | "MusicControl"
  | "MusicGetQueue"
  | "MusicSearch"
  | "MusicPlay"
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
