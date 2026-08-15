> Перевод. Источник истины — [docs/en](../../en/reference/protocol.md); при расхождении верна английская версия. Английская страница сгенерирована `tools/docgen/protocol.py`; эта переводная копия не генерируется автоматически и может отстать при изменении источника.

# Справочник протокола

Поколение протокола **1**. 10 сервисов, 158 RPC. Источник:
[`proto/plugin.proto`](../../../proto/plugin.proto), сгенерированный срез
`astra.proto` Astra (`source-sha256: 3588e1647aca5a7a…`), закреплённый
[`proto/PROTO_VERSION`](../../../proto/PROTO_VERSION) на
`sha256:2bccd2f5cd787f03…`. У каждой завендоренной копии в трёх SDK тот же
самый хеш; `tools/check-proto.sh` — то, что это подтверждает.

## Три сервиса плагина

| Сервис | Направление | RPC | Кто обслуживает |
|---|---|---|---|
| [`PluginCapabilityService`](#plugincapabilityservice) | демон → плагин | 25 | ваш плагин |
| [`PluginHostService`](#pluginhostservice) | плагин → демон | 10 | демон |
| [`PluginService`](#pluginservice) | UI → демон | 23 | демон |

Поколение протокола — это контракт. Плагин отправляет его в
`PluginRegisterRequest.protocol_version`, а демон отвечает собственной
нижней границей в `PluginRegisterResponse.min_supported_protocol`;
`sdk_name` и `sdk_version` едут вместе для диагностики и ничего не
закрывают.

## PluginCapabilityService

**Ваш плагин это обслуживает.** Демон — клиент: он вызывает внутрь, чтобы
запустить инструмент, синтезировать речь, передать вам событие. Каждый
RPC здесь — хук, который вы реализуете, и `UNIMPLEMENTED` — это слово
протокола для *у этого плагина нет такого хука*, а не для ошибки.

| RPC | Возможность | Запрос | Ответ | Поток | Маршрутизирован | Что делает |
|---|---|---|---|---|---|---|
| `ListTools` | `tools` | `Empty` | `PluginToolListResponse` | unary | live | The tool schemas this plugin offers the model, read once at startup. |
| `CallTool` | `tools` | `PluginCallToolRequest` | `PluginCallToolResponse` | unary | live | Run one tool call on behalf of the model and return its result. |
| `TtsSynthesize` | `tts` | `PluginTtsSynthesizeRequest` | `PluginTtsSynthesizeResponse` | unary | live | Synthesize one utterance and return the whole buffer. |
| `TtsSynthesizeStream` | `tts` | `PluginTtsSynthesizeRequest` | `PluginAudioChunk` | server | unrouted | Synthesize one utterance as a chunk stream, for first-audio latency. |
| `TtsListVoices` | `tts` | `Empty` | `PluginTtsVoicesResponse` | unary | live | The voices this provider exposes in the Voice settings picker. |
| `TtsGetConfigFields` | `tts` | `Empty` | `PluginConfigFieldsResponse` | unary | live | Extra TTS settings fields, rendered by DynamicField on the Voice page. |
| `TtsActivate` | `tts` | `PluginTtsActivateRequest` | `PluginTtsActivateResponse` | unary | live | Deliver a licensed-voice content key for one-time machine-bound sealing. |
| `SttProcess` | `stt` | `PluginAudioChunk` | `PluginSttEvent` | bidi | live | Audio chunks in, transcript events out; carries both one-shot and streaming STT. |
| `SttGetLanguages` | `stt` | `Empty` | `PluginSttLanguagesResponse` | unary | live | The language codes this recognizer accepts. |
| `SttGetConfigFields` | `stt` | `Empty` | `PluginConfigFieldsResponse` | unary | live | Extra STT settings fields, rendered by DynamicField on the Voice page. |
| `SttLoad` | `stt` | `SttLoadRequest` | `Empty` | unary | live | Load the recognizer model, with the daemon-resolved path and GPU toggle. |
| `SttUnload` | `stt` | `Empty` | `Empty` | unary | live | Drop the recognizer model so idle-unload actually frees VRAM. |
| `SttGetLoadState` | `stt` | `Empty` | `SttLoadStateResponse` | unary | live | Report Loaded / NotLoaded / NotNeeded so the daemon can drive idle-unload. |
| `AiComplete` | `ai_provider` | `PluginAiCompleteRequest` | `PluginAiStreamChunk` | server | live | Stream a model completion; the only way a plugin can be an AI provider. |
| `AiGetModels` *(устарел)* | `ai_provider` | `Empty` | `PluginAiModelsResponse` | unary | deprecated | List the models this provider can run. |
| `ExecuteAction` | `actions` | `PluginExecuteActionRequest` | `PluginExecuteActionResponse` | unary | live | Run one command-step action this plugin contributed. |
| `GetPluginActionTypes` | `actions` | `Empty` | `PluginActionTypesResponse` | unary | live | The action types this plugin adds to the command editor, read at startup. |
| `GetPluginTriggerTypes` | `triggers` | `Empty` | `PluginTriggerTypesResponse` | unary | live | The trigger types this plugin adds to the command editor, read at startup. |
| `GetUiContributions` | `ui_contributions` | `Empty` | `PluginUiContributionsResponse` | unary | live | The pages, slots, overlays and effects this plugin renders in the Astra window. |
| `CallFromUi` | `ui_contributions` | `PluginUiCallRequest` | `PluginUiCallResponse` | unary | live | A method call from this plugin's own iframe into its backend. |
| `OnConfigChanged` | `core` | `PluginConfigChangedMsg` | `Empty` | unary | live | The user saved new settings; here is the whole config as JSON. |
| `OnActiveTriggers` | `triggers` | `PluginActiveTriggersMsg` | `Empty` | unary | live | Which of this plugin's trigger types a command is currently listening for. |
| `OnLanguageChanged` | `core` | `LanguageChangedMsg` | `Empty` | unary | live | The Astra UI language changed; re-render anything user-visible. |
| `Shutdown` | `core` | `Empty` | `Empty` | unary | live | Stop cleanly; the process group is killed after the grace period. |
| `HealthCheck` | `core` | `Empty` | `PluginHealthResponse` | unary | live | Liveness probe, every 15 s. |

## PluginHostService

**Демон это обслуживает.** Ваш плагин — клиент. `Register` — это
загрузка: он доказывает токен запуска, который демон передал процессу, и
возвращает токен сессии, и это единственный путь, освобождённый
перехватчиком авторизации демона. Каждый другой вызов несёт этот токен, а
закрытые дополнительно сверяются с разрешениями, которые выдал
*пользователь*, — это другой вопрос, отличный от возможностей, которые вы
объявили.

| RPC | Разрешение | Запрос | Ответ | Поток | Маршрутизирован | Что делает |
|---|---|---|---|---|---|---|
| `Register` | `none` | `PluginRegisterRequest` | `PluginRegisterResponse` | unary | live | The handshake: prove the spawn token, receive the per-plugin session token. |
| `SubscribeEvents` | `subscribe_events` | `PluginEventFilter` | `PluginEventMsg` | server | live | The filtered daemon event stream; the whole of the event_handlers capability. |
| `SendChatMessage` | `send_chat_message` | `PluginChatRequest` | `PluginChatChunk` | server | live | Send a chat message as this plugin and stream the assistant's reply back. |
| `FireTrigger` | `fire_trigger` | `PluginFireTriggerRequest` | `Empty` | unary | live | Fire one of this plugin's trigger types and run whatever commands listen. |
| `GetPluginSelfConfig` | `none` | `PluginSelfIdRequest` | `PluginSelfConfigResponse` | unary | live | Read this plugin's own persisted settings. |
| `PluginLog` | `none` | `PluginLogRequest` | `Empty` | unary | live | Write a line into the daemon log buffer the plugin's log pane reads. |
| `GetDaemonInfo` | `none` | `Empty` | `PluginDaemonInfoResponse` | unary | live | Daemon version, state and gRPC port. |
| `SetVariable` | `set_variable` | `PluginSetVariableRequest` | `Empty` | unary | live | Publish a variable that commands and other plugins can read. |
| `SetThemeContribution` | `set_theme_contribution` | `PluginThemeContribution` | `Empty` | unary | live | Contribute colours, wallpaper and shader to the active Astra theme. |
| `PushToUi` | `push_to_ui` | `PluginUiPushRequest` | `Empty` | unary | live | Push an event into this plugin's own iframes — the return path for CallFromUi. |

`none` означает, что любой плагин может вызывать это всегда — стартовый
набор, на который демон вообще не запускает проверку разрешений. Это
утверждение о демоне, а не отговорка: колонка берётся из
[`spec/hooks.yaml`](../../../spec/hooks.yaml), и правило паритета R6
сверяет каждую её строку с `HOST_RPC_PERMISSIONS` в `plugins/host_service.rs`
демона — таблицей, которую читает `require_permission`. RPC хоста без
строки там не закрыт, и R6 называет это находкой по безопасности, а не
опечаткой в спецификации.

Шлюз отвечает в *начале* вызова. `SubscribeEvents` начинается один раз и
работает, пока плагин не выйдет, так что демон завершает поток — с
`permission_denied` и трейлером причины завершения — когда выдача
сужается, согласие отзывается или плагин отзывается. Отозванное
разрешение поэтому отличимо от оборванного соединения.

## PluginService

**Ни одна из сторон плагина.** Демон обслуживает его для UI Astra:
установка, импорт, удаление, происхождение, согласие, логи. Ни один
плагин никогда его не вызывает, и ни один SDK его не привязывает; он
здесь, потому что это поверхность, через которую реально проходит
установка вашего плагина пользователем.

| RPC | Запрос | Ответ | Поток | Что делает |
|---|---|---|---|---|
| `ListPlugins` | `Empty` | `PluginListResponse` | unary | List all installed plugins with status |
| `InstallPlugin` | `InstallPluginRequest` | `PluginStatusMsg` | unary | Install a plugin from the registry |
| `InstallPluginStream` | `InstallPluginRequest` | `PluginInstallProgress` | server | Install a plugin from the registry, reporting every phase as it happens. |
| `CancelPluginInstall` | `PluginIdRequest` | `CancelPluginInstallResponse` | unary | Cancel an install started by InstallPluginStream. |
| `UninstallPlugin` | `UninstallPluginRequest` | `UninstallPluginResponse` | unary | Remove a plugin, and decide separately what happens to its settings. |
| `ReportPlugin` | `ReportPluginRequest` | `ReportPluginResponse` | unary | Report a plugin — and, if the user asks, quarantine it HERE first. |
| `SetPluginEnabled` | `SetPluginEnabledRequest` | `Empty` | unary | Enable/disable a plugin |
| `StartPlugin` | `PluginIdRequest` | `Empty` | unary | Start a stopped plugin |
| `StopPlugin` | `PluginIdRequest` | `Empty` | unary | Stop a running plugin |
| `GetPluginConfig` | `PluginIdRequest` | `PluginConfigResponse` | unary | Get plugin config schema + current values |
| `UpdatePluginConfig` | `UpdatePluginConfigRequest` | `Empty` | unary | Update plugin config |
| `BrowsePluginRegistry` | `PluginBrowseRequest` | `PluginBrowseResponse` | unary | Browse plugin registry |
| `CheckPluginUpdates` | `Empty` | `PluginUpdatesResponse` | unary | Check for updates on installed plugins |
| `UpdatePlugin` | `PluginIdRequest` | `PluginStatusMsg` | unary | Update a plugin to latest version |
| `SideloadPlugin` | `SideloadPluginRequest` | `PluginStatusMsg` | unary | Sideload a plugin from local path (dev mode) |
| `ImportPluginFile` | `ImportPluginFileRequest` | `PluginStatusMsg` | unary | Import a plugin from a local .astraplugin ZIP file |
| `InspectPluginFile` | `InspectPluginFileRequest` | `PluginFileInspection` | unary | Read a `.astraplugin` file WITHOUT installing it, so §4.3's consent sheet can be shown on the import path too. |
| `ResolvePendingUpdate` | `ResolvePendingUpdateRequest` | `PluginStatusMsg` | unary | §4.5/§4.6. |
| `GetPluginLogs` | `PluginLogsRequest` | `PluginLogsResponse` | unary | Get logs from a plugin (last N lines) |
| `GetPluginProvenance` | `PluginProvenanceRequest` | `PluginProvenanceMsg` | unary | Everything Astra recorded about where one INSTALLED plugin came from — production plan §4.2, the provenance panel. |
| `GetAllUiContributions` | `Empty` | `AllUiContributionsResponse` | unary | Get all UI contributions from all running plugins |
| `GetActiveThemes` | `Empty` | `ActiveThemesResponse` | unary | Get active theme contributions from plugins |
| `CallPluginFromUi` | `CallPluginFromUiRequest` | `CallPluginFromUiResponse` | unary | Forward a UI call to a plugin's backend |

## Остальная часть среза

Proto плагина несёт также собственные обращённые к клиенту сервисы Astra,
потому что плагин `client` — тот, что помещает поверхность чата туда, где
Astra нет, как пример с Telegram, — управляет демоном через них с помощью
хендла `Daemon` из SDK. Это не хуки плагина, и ни одна возможность их не
подразумевает.

| Сервис | RPC |
|---|---|
| `CoreService` | 8 |
| `ChatService` | 12 |
| `VoiceService` | 34 |
| `CommandService` | 13 |
| `ConfigService` | 25 |
| `MediaService` | 5 |
| `MonitorService` | 3 |

Полные сигнатуры — в [`proto/plugin.proto`](../../../proto/plugin.proto);
эта страница не переизлагает сотню с лишним RPC, до которых плагин
достаёт только через типизированную обёртку SDK.

## Устаревания

| RPC | Почему |
|---|---|
| `PluginCapabilityService.AiGetModels` | УСТАРЕЛ — у демона нет точки вызова и способа показать ответ. |

Устаревший RPC остаётся объявленным. Удалить его значило бы сломать
сгенерированные реализации трейта, которые испускает каждый SDK, а плагин,
набирающий его, должен продолжать получать `UNIMPLEMENTED` — что значит
*отсутствует* — а не ошибку транспорта.
