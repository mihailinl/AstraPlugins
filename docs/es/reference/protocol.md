> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/reference/protocol.md) es la referencia autorizada. La página en inglés está GENERADA por `tools/docgen/protocol.py` — esta traducción es una instantánea mantenida a mano, no otra copia generada.

# Referencia del protocolo

Generación de protocolo **1**. 10 servicios, 158 RPC. Fuente:
[`proto/plugin.proto`](../../../proto/plugin.proto), un recorte
generado del `astra.proto` de Astra
(`source-sha256: 3588e1647aca5a7a…`), fijado por
[`proto/PROTO_VERSION`](../../../proto/PROTO_VERSION) en
`sha256:2bccd2f5cd787f03…`. Cada copia vendorizada en los tres SDK tiene
ese mismo hash; `tools/check-proto.sh` es lo que lo confirma.

## Los tres servicios de plugin

| Servicio | Dirección | RPC | Quién lo sirve |
|---|---|---|---|
| [`PluginCapabilityService`](#plugincapabilityservice) | daemon → plugin | 25 | tu plugin |
| [`PluginHostService`](#pluginhostservice) | plugin → daemon | 10 | el daemon |
| [`PluginService`](#pluginservice) | UI → daemon | 23 | el daemon |

La generación de protocolo es el contrato. Un plugin la envía en
`PluginRegisterRequest.protocol_version`, y el daemon responde con su
propio piso en `PluginRegisterResponse.min_supported_protocol`;
`sdk_name` y `sdk_version` viajan para triaje y no condicionan nada.

## PluginCapabilityService

**Tu plugin sirve esto.** El daemon es el cliente: llama hacia dentro
para ejecutar un tool, sintetizar voz, entregarte un evento. Cada RPC
aquí es un hook que implementas, y `UNIMPLEMENTED` es la palabra del
protocolo para *este plugin no tiene ese hook* — no para un error.

| RPC | Capability | Request | Response | Stream | Enrutado | Qué hace |
|---|---|---|---|---|---|---|
| `ListTools` | `tools` | `Empty` | `PluginToolListResponse` | unary | live | Los schemas de tools que este plugin ofrece al modelo, leídos una vez al arrancar. |
| `CallTool` | `tools` | `PluginCallToolRequest` | `PluginCallToolResponse` | unary | live | Ejecuta una llamada a un tool en nombre del modelo y devuelve su resultado. |
| `TtsSynthesize` | `tts` | `PluginTtsSynthesizeRequest` | `PluginTtsSynthesizeResponse` | unary | live | Sintetiza un enunciado y devuelve el búfer completo. |
| `TtsSynthesizeStream` | `tts` | `PluginTtsSynthesizeRequest` | `PluginAudioChunk` | server | unrouted | Sintetiza un enunciado como un stream de chunks, para reducir la latencia del primer audio. |
| `TtsListVoices` | `tts` | `Empty` | `PluginTtsVoicesResponse` | unary | live | Las voces que este proveedor expone en el selector de ajustes de Voice. |
| `TtsGetConfigFields` | `tts` | `Empty` | `PluginConfigFieldsResponse` | unary | live | Campos de ajustes TTS adicionales, renderizados por DynamicField en la página Voice. |
| `TtsActivate` | `tts` | `PluginTtsActivateRequest` | `PluginTtsActivateResponse` | unary | live | Entrega una clave de contenido de voz licenciada para sellado único vinculado a la máquina. |
| `SttProcess` | `stt` | `PluginAudioChunk` | `PluginSttEvent` | bidi | live | Chunks de audio entran, eventos de transcripción salen; cubre STT tanto de una sola vez como en streaming. |
| `SttGetLanguages` | `stt` | `Empty` | `PluginSttLanguagesResponse` | unary | live | Los códigos de idioma que acepta este reconocedor. |
| `SttGetConfigFields` | `stt` | `Empty` | `PluginConfigFieldsResponse` | unary | live | Campos de ajustes STT adicionales, renderizados por DynamicField en la página Voice. |
| `SttLoad` | `stt` | `SttLoadRequest` | `Empty` | unary | live | Carga el modelo del reconocedor, con la ruta resuelta por el daemon y el interruptor de GPU. |
| `SttUnload` | `stt` | `Empty` | `Empty` | unary | live | Descarga el modelo del reconocedor para que idle-unload libere VRAM de verdad. |
| `SttGetLoadState` | `stt` | `Empty` | `SttLoadStateResponse` | unary | live | Reporta Loaded / NotLoaded / NotNeeded para que el daemon pueda gestionar idle-unload. |
| `AiComplete` | `ai_provider` | `PluginAiCompleteRequest` | `PluginAiStreamChunk` | server | live | Transmite en streaming una completion de modelo; la única forma en que un plugin puede ser un proveedor de IA. |
| `AiGetModels` *(obsoleto)* | `ai_provider` | `Empty` | `PluginAiModelsResponse` | unary | deprecated | Lista los modelos que este proveedor puede ejecutar. |
| `ExecuteAction` | `actions` | `PluginExecuteActionRequest` | `PluginExecuteActionResponse` | unary | live | Ejecuta una acción de paso de comando que aportó este plugin. |
| `GetPluginActionTypes` | `actions` | `Empty` | `PluginActionTypesResponse` | unary | live | Los tipos de action que este plugin añade al editor de comandos, leídos al arrancar. |
| `GetPluginTriggerTypes` | `triggers` | `Empty` | `PluginTriggerTypesResponse` | unary | live | Los tipos de trigger que este plugin añade al editor de comandos, leídos al arrancar. |
| `GetUiContributions` | `ui_contributions` | `Empty` | `PluginUiContributionsResponse` | unary | live | Las páginas, slots, overlays y efectos que este plugin renderiza en la ventana de Astra. |
| `CallFromUi` | `ui_contributions` | `PluginUiCallRequest` | `PluginUiCallResponse` | unary | live | Una llamada a método desde el propio iframe de este plugin hacia su backend. |
| `OnConfigChanged` | `core` | `PluginConfigChangedMsg` | `Empty` | unary | live | El usuario guardó nuevos ajustes; aquí está toda la config como JSON. |
| `OnActiveTriggers` | `triggers` | `PluginActiveTriggersMsg` | `Empty` | unary | live | Cuáles de los tipos de trigger de este plugin está escuchando actualmente un comando. |
| `OnLanguageChanged` | `core` | `LanguageChangedMsg` | `Empty` | unary | live | El idioma de la UI de Astra cambió; vuelve a renderizar todo lo visible para el usuario. |
| `Shutdown` | `core` | `Empty` | `Empty` | unary | live | Detente limpiamente; el grupo de procesos se mata tras el período de gracia. |
| `HealthCheck` | `core` | `Empty` | `PluginHealthResponse` | unary | live | Sonda de actividad (liveness), cada 15 s. |

## PluginHostService

**El daemon sirve esto.** Tu plugin es el cliente. `Register` es el
arranque: demuestra el token de arranque que el daemon le pasó al
proceso y devuelve un token de sesión, y es la única ruta que exime el
interceptor de autenticación del daemon. Cualquier otra llamada lleva
ese token, y las que están condicionadas se comprueban además contra
los permisos que concedió el *usuario* — una pregunta distinta de las
capabilities que declaraste.

| RPC | Permission | Request | Response | Stream | Enrutado | Qué hace |
|---|---|---|---|---|---|---|
| `Register` | `none` | `PluginRegisterRequest` | `PluginRegisterResponse` | unary | live | El handshake: demostrar el token de arranque, recibir el token de sesión propio del plugin. |
| `SubscribeEvents` | `subscribe_events` | `PluginEventFilter` | `PluginEventMsg` | server | live | El stream filtrado de eventos del daemon; toda la capability event_handlers. |
| `SendChatMessage` | `send_chat_message` | `PluginChatRequest` | `PluginChatChunk` | server | live | Envía un mensaje de chat como este plugin y transmite en streaming la respuesta del asistente de vuelta. |
| `FireTrigger` | `fire_trigger` | `PluginFireTriggerRequest` | `Empty` | unary | live | Dispara uno de los tipos de trigger de este plugin y ejecuta los comandos que escuchen. |
| `GetPluginSelfConfig` | `none` | `PluginSelfIdRequest` | `PluginSelfConfigResponse` | unary | live | Lee la propia configuración persistida de este plugin. |
| `PluginLog` | `none` | `PluginLogRequest` | `Empty` | unary | live | Escribe una línea en el búfer de log del daemon que lee el panel de log del plugin. |
| `GetDaemonInfo` | `none` | `Empty` | `PluginDaemonInfoResponse` | unary | live | Versión del daemon, estado y puerto gRPC. |
| `SetVariable` | `set_variable` | `PluginSetVariableRequest` | `Empty` | unary | live | Publica una variable que comandos y otros plugins pueden leer. |
| `SetThemeContribution` | `set_theme_contribution` | `PluginThemeContribution` | `Empty` | unary | live | Aporta colores, fondo de pantalla y shader al tema activo de Astra. |
| `PushToUi` | `push_to_ui` | `PluginUiPushRequest` | `Empty` | unary | live | Envía un evento a los propios iframes de este plugin — la ruta de retorno para CallFromUi. |

`none` significa que cualquier plugin puede llamarla siempre — el
conjunto de arranque, sobre el que el daemon no ejecuta ninguna
comprobación de permisos en absoluto. Es una afirmación sobre el daemon,
no un encogimiento de hombros: la columna viene de
[`spec/hooks.yaml`](../../../spec/hooks.yaml), y la regla de paridad R6
comprueba cada una de sus filas contra `HOST_RPC_PERMISSIONS` en
`plugins/host_service.rs` del daemon, la tabla que lee
`require_permission`. Un RPC del host sin fila ahí no está condicionado,
y R6 lo llama un hallazgo de seguridad y no una errata de la spec.

La puerta responde al *inicio* de una llamada. `SubscribeEvents`
arranca una vez y corre hasta que el plugin sale, así que el daemon
termina el stream — con `permission_denied` y un trailer de motivo de
cierre — cuando una concesión se estrecha, se rechaza el consentimiento
o el plugin se revoca. Un permiso retirado es, por tanto, distinguible
de una conexión caída.

## PluginService

**Ningún lado de un plugin.** El daemon sirve esto a la interfaz de
Astra: instalar, importar, desinstalar, procedencia, consentimiento,
logs. Ningún plugin lo llama nunca y ningún SDK lo vincula; está aquí
porque es la superficie por la que realmente pasa la instalación de tu
plugin en un usuario.

| RPC | Request | Response | Stream | Qué hace |
|---|---|---|---|---|
| `ListPlugins` | `Empty` | `PluginListResponse` | unary | Lista todos los plugins instalados con su estado |
| `InstallPlugin` | `InstallPluginRequest` | `PluginStatusMsg` | unary | Instala un plugin desde el registro |
| `InstallPluginStream` | `InstallPluginRequest` | `PluginInstallProgress` | server | Instala un plugin desde el registro, reportando cada fase a medida que ocurre. |
| `CancelPluginInstall` | `PluginIdRequest` | `CancelPluginInstallResponse` | unary | Cancela una instalación iniciada por InstallPluginStream. |
| `UninstallPlugin` | `UninstallPluginRequest` | `UninstallPluginResponse` | unary | Elimina un plugin, y decide por separado qué pasa con sus ajustes. |
| `ReportPlugin` | `ReportPluginRequest` | `ReportPluginResponse` | unary | Reporta un plugin — y, si el usuario lo pide, lo pone en cuarentena AQUÍ primero. |
| `SetPluginEnabled` | `SetPluginEnabledRequest` | `Empty` | unary | Activa/desactiva un plugin |
| `StartPlugin` | `PluginIdRequest` | `Empty` | unary | Arranca un plugin detenido |
| `StopPlugin` | `PluginIdRequest` | `Empty` | unary | Detiene un plugin en ejecución |
| `GetPluginConfig` | `PluginIdRequest` | `PluginConfigResponse` | unary | Obtiene el schema de config del plugin + valores actuales |
| `UpdatePluginConfig` | `UpdatePluginConfigRequest` | `Empty` | unary | Actualiza la config del plugin |
| `BrowsePluginRegistry` | `PluginBrowseRequest` | `PluginBrowseResponse` | unary | Explora el registro de plugins |
| `CheckPluginUpdates` | `Empty` | `PluginUpdatesResponse` | unary | Comprueba actualizaciones de los plugins instalados |
| `UpdatePlugin` | `PluginIdRequest` | `PluginStatusMsg` | unary | Actualiza un plugin a la última versión |
| `SideloadPlugin` | `SideloadPluginRequest` | `PluginStatusMsg` | unary | Hace sideload de un plugin desde una ruta local (modo dev) |
| `ImportPluginFile` | `ImportPluginFileRequest` | `PluginStatusMsg` | unary | Importa un plugin desde un archivo ZIP .astraplugin local |
| `InspectPluginFile` | `InspectPluginFileRequest` | `PluginFileInspection` | unary | Lee un archivo `.astraplugin` SIN instalarlo, para que la pantalla de consentimiento del §4.3 también pueda mostrarse en la vía de importación. |
| `ResolvePendingUpdate` | `ResolvePendingUpdateRequest` | `PluginStatusMsg` | unary | §4.5/§4.6. |
| `GetPluginLogs` | `PluginLogsRequest` | `PluginLogsResponse` | unary | Obtiene logs de un plugin (últimas N líneas) |
| `GetPluginProvenance` | `PluginProvenanceRequest` | `PluginProvenanceMsg` | unary | Todo lo que Astra registró sobre de dónde vino un plugin INSTALADO — plan de producción §4.2, el panel de procedencia. |
| `GetAllUiContributions` | `Empty` | `AllUiContributionsResponse` | unary | Obtiene todas las contribuciones de UI de todos los plugins en ejecución |
| `GetActiveThemes` | `Empty` | `ActiveThemesResponse` | unary | Obtiene las contribuciones de tema activas de los plugins |
| `CallPluginFromUi` | `CallPluginFromUiRequest` | `CallPluginFromUiResponse` | unary | Reenvía una llamada de UI al backend de un plugin |

## El resto del recorte

El proto de plugins también lleva los propios servicios orientados a
cliente de Astra, porque un plugin `client` — uno que pone una
superficie de chat en algún lugar donde Astra no está, como el ejemplo
de Telegram — impulsa el daemon a través de ellos con el handle
`Daemon` del SDK. No son hooks de plugin y ninguna capability los
implica.

| Servicio | RPC |
|---|---|
| `CoreService` | 8 |
| `ChatService` | 12 |
| `VoiceService` | 34 |
| `CommandService` | 13 |
| `ConfigService` | 25 |
| `MediaService` | 5 |
| `MonitorService` | 3 |

Las firmas completas están en
[`proto/plugin.proto`](../../../proto/plugin.proto); esta página no
repite el centenar largo de RPC a los que un plugin solo llega a través
del wrapper tipado del SDK.

## Obsolescencias

| RPC | Por qué |
|---|---|
| `PluginCapabilityService.AiGetModels` | OBSOLETO — el daemon no tiene punto de llamada ni forma de mostrar la respuesta. |

Un RPC obsoleto sigue declarado. Eliminarlo rompería las
implementaciones de trait generadas que emite cada SDK, y un plugin que
lo marque debería seguir recibiendo `UNIMPLEMENTED` — que significa
*ausente* — en lugar de un error de transporte.
</content>
