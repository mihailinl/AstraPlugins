> Переклад. Джерело істини — [docs/en](../../en/reference/protocol.md); за розбіжності відповідає англійська версія. Англійська сторінка згенерована `tools/docgen/protocol.py`; ця перекладна копія не генерується автоматично і може відстати при зміні джерела.

# Довідник протоколу

Покоління протоколу **1**. 10 сервісів, 158 RPC. Джерело:
[`proto/plugin.proto`](../../../proto/plugin.proto), згенерований зріз
`astra.proto` Astra (`source-sha256: 3588e1647aca5a7a…`), закріплений
[`proto/PROTO_VERSION`](../../../proto/PROTO_VERSION) на
`sha256:2bccd2f5cd787f03…`. У кожної завендореної копії в трьох SDK той
самий хеш; `tools/check-proto.sh` — те, що це підтверджує.

## Три сервіси плагіна

| Сервіс | Напрямок | RPC | Хто обслуговує |
|---|---|---|---|
| [`PluginCapabilityService`](#plugincapabilityservice) | демон → плагін | 25 | ваш плагін |
| [`PluginHostService`](#pluginhostservice) | плагін → демон | 10 | демон |
| [`PluginService`](#pluginservice) | UI → демон | 23 | демон |

Покоління протоколу — це контракт. Плагін надсилає його в
`PluginRegisterRequest.protocol_version`, а демон відповідає власною
нижньою межею в `PluginRegisterResponse.min_supported_protocol`;
`sdk_name` і `sdk_version` їдуть разом для діагностики і нічого не
закривають.

## PluginCapabilityService

**Ваш плагін це обслуговує.** Демон — клієнт: він викликає всередину, щоб
запустити інструмент, синтезувати мовлення, передати вам подію. Кожен
RPC тут — хук, який ви реалізуєте, і `UNIMPLEMENTED` — це слово протоколу
для *у цього плагіна немає такого хука*, а не для помилки.

| RPC | Можливість | Запит | Відповідь | Потік | Маршрутизований | Що робить |
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
| `AiGetModels` *(застарілий)* | `ai_provider` | `Empty` | `PluginAiModelsResponse` | unary | deprecated | List the models this provider can run. |
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

**Демон це обслуговує.** Ваш плагін — клієнт. `Register` — це
завантаження: він доводить токен запуску, який демон передав процесу, і
повертає токен сесії, і це єдиний шлях, звільнений перехоплювачем
авторизації демона. Кожен інший виклик несе цей токен, а закриті
додатково звіряються з дозволами, які видав *користувач*, — це інше
питання, відмінне від можливостей, які ви оголосили.

| RPC | Дозвіл | Запит | Відповідь | Потік | Маршрутизований | Що робить |
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

`none` означає, що будь-який плагін може викликати це завжди — стартовий
набір, на який демон взагалі не запускає перевірку дозволів. Це
твердження про демона, а не відмовка: колонка береться з
[`spec/hooks.yaml`](../../../spec/hooks.yaml), і правило паритету R6
звіряє кожен її рядок з `HOST_RPC_PERMISSIONS` у `plugins/host_service.rs`
демона — таблицею, яку читає `require_permission`. RPC хоста без рядка
там не закритий, і R6 називає це знахідкою з безпеки, а не одруківкою в
специфікації.

Шлюз відповідає на *початку* виклику. `SubscribeEvents` починається один
раз і працює, поки плагін не вийде, тож демон завершує потік — з
`permission_denied` і трейлером причини завершення — коли видача
звужується, згода відкликається або плагін відкликається. Відкликаний
дозвіл тому відрізнимий від обірваного з'єднання.

## PluginService

**Жодна зі сторін плагіна.** Демон обслуговує його для UI Astra:
встановлення, імпорт, видалення, походження, згода, логи. Жоден плагін
ніколи його не викликає, і жоден SDK його не прив'язує; він тут, тому що
це поверхня, через яку реально проходить встановлення вашого плагіна
користувачем.

| RPC | Запит | Відповідь | Потік | Що робить |
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

## Решта зрізу

Proto плагіна несе також власні звернені до клієнта сервіси Astra, тому
що плагін `client` — той, що поміщає поверхню чату туди, де Astra немає,
як приклад з Telegram, — керує демоном через них за допомогою хендла
`Daemon` з SDK. Це не хуки плагіна, і жодна можливість їх не передбачає.

| Сервіс | RPC |
|---|---|
| `CoreService` | 8 |
| `ChatService` | 12 |
| `VoiceService` | 34 |
| `CommandService` | 13 |
| `ConfigService` | 25 |
| `MediaService` | 5 |
| `MonitorService` | 3 |

Повні сигнатури — в [`proto/plugin.proto`](../../../proto/plugin.proto);
ця сторінка не переказує сотню з гаком RPC, до яких плагін дістає лише
через типізовану обгортку SDK.

## Застарівання

| RPC | Чому |
|---|---|
| `PluginCapabilityService.AiGetModels` | ЗАСТАРІВ — у демона немає точки виклику і способу показати відповідь. |

Застарілий RPC залишається оголошеним. Видалити його означало б зламати
згенеровані реалізації трейта, які випускає кожен SDK, а плагін, що
набирає його, повинен продовжувати отримувати `UNIMPLEMENTED` — що
означає *відсутній* — а не помилку транспорту.
