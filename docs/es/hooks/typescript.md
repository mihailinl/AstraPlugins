> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/hooks/typescript.md) es la referencia autorizada. La página en inglés está GENERADA por `tools/parity/gen.py` a partir de `spec/hooks.yaml` — esta traducción es una instantánea mantenida a mano, no otra copia generada.

# SDK de TypeScript — tabla de hooks

Protocolo **1**. Cada hook que el SDK de TypeScript puede vincular, y si
lo hace. Generado a partir de
[`spec/hooks.yaml`](../../../spec/hooks.yaml); la vista entre lenguajes
es [`parity.md`](../parity.md).

## PluginCapabilityService — daemon → plugin

Estos los implementas tú; el daemon los llama.

| RPC | Capability | Oblig. | Stream | Estado | Qué hace |
|---|---|---|---|---|---|
| `ListTools` | `tools` | required | unary | stable | Los schemas de tools que este plugin ofrece al modelo, leídos una vez al arrancar. |
| `CallTool` | `tools` | required | unary | stable | Ejecuta una llamada a un tool en nombre del modelo y devuelve su resultado. |
| `TtsSynthesize` | `tts` | required | unary | stable | Sintetiza un enunciado y devuelve el búfer completo. |
| `TtsSynthesizeStream` | `tts` | optional | server | stable | Sintetiza un enunciado como un stream de chunks, para reducir la latencia del primer audio. |
| `TtsListVoices` | `tts` | required | unary | stable | Las voces que este proveedor expone en el selector de ajustes de Voice. |
| `TtsGetConfigFields` | `tts` | optional | unary | stable | Campos de ajustes TTS adicionales, renderizados por DynamicField en la página Voice. |
| `TtsActivate` | `tts` | optional | unary | stable | Entrega una clave de contenido de voz licenciada para sellado único vinculado a la máquina. |
| `SttProcess` | `stt` | required | bidi | stable | Chunks de audio entran, eventos de transcripción salen; cubre STT tanto de una sola vez como en streaming. |
| `SttGetLanguages` | `stt` | required | unary | stable | Los códigos de idioma que acepta este reconocedor. |
| `SttGetConfigFields` | `stt` | optional | unary | stable | Campos de ajustes STT adicionales, renderizados por DynamicField en la página Voice. |
| `SttLoad` | `stt` | optional | unary | stable | Carga el modelo del reconocedor, con la ruta resuelta por el daemon y el interruptor de GPU. |
| `SttUnload` | `stt` | optional | unary | stable | Descarga el modelo del reconocedor para que idle-unload libere VRAM de verdad. |
| `SttGetLoadState` | `stt` | optional | unary | stable | Reporta Loaded / NotLoaded / NotNeeded para que el daemon pueda gestionar idle-unload. |
| `AiComplete` | `ai_provider` | required | server | stable | Transmite en streaming una completion de modelo; la única forma en que un plugin puede ser un proveedor de IA. |
| `AiGetModels` | `ai_provider` | optional | unary | stable | Lista los modelos que este proveedor puede ejecutar. |
| `ExecuteAction` | `actions` | required | unary | stable | Ejecuta una acción de paso de comando que aportó este plugin. |
| `GetPluginActionTypes` | `actions` | required | unary | stable | Los tipos de action que este plugin añade al editor de comandos, leídos al arrancar. |
| `GetPluginTriggerTypes` | `triggers` | required | unary | stable | Los tipos de trigger que este plugin añade al editor de comandos, leídos al arrancar. |
| `OnActiveTriggers` | `triggers` | optional | unary | stable | Cuáles de los tipos de trigger de este plugin está escuchando actualmente un comando. |
| `GetUiContributions` | `ui_contributions` | required | unary | stable | Las páginas, slots, overlays y efectos que este plugin renderiza en la ventana de Astra. |
| `CallFromUi` | `ui_contributions` | optional | unary | stable | Una llamada a método desde el propio iframe de este plugin hacia su backend. |
| `OnConfigChanged` | `core` | optional | unary | stable | El usuario guardó nuevos ajustes; aquí está toda la config como JSON. |
| `OnLanguageChanged` | `core` | optional | unary | stable | El idioma de la UI de Astra cambió; vuelve a renderizar todo lo visible para el usuario. |
| `Shutdown` | `core` | required | unary | stable | Detente limpiamente; el grupo de procesos se mata tras el período de gracia. |
| `HealthCheck` | `core` | required | unary | stable | Sonda de actividad (liveness), cada 15 s. |

## PluginHostService — plugin → daemon

Estos los implementa el daemon; tú los llamas.

**Aquí la capability no es suficiente.** Estas son llamadas que haces
hacia el daemon, y el daemon las responde a partir del conjunto de
permisos *concedido* (§5.6). Declarar la capability dice a qué
funcionalidad pertenece la llamada; declarar el permiso es a lo que
consiente el usuario. Un plugin que solo declara la capability recibe
`permission_denied` en la máquina del usuario. `none` significa que
cualquier plugin puede llamarla siempre.

| RPC | Capability | Permiso | Oblig. | Stream | Estado | Qué hace |
|---|---|---|---|---|---|---|
| `Register` | `core` | `none` | required | unary | stable | El handshake: demostrar el token de arranque, recibir el token de sesión propio del plugin. |
| `GetPluginSelfConfig` | `core` | `none` | optional | unary | stable | Lee la propia configuración persistida de este plugin. |
| `PluginLog` | `core` | `none` | optional | unary | stable | Escribe una línea en el búfer de log del daemon que lee el panel de log del plugin. |
| `GetDaemonInfo` | `core` | `none` | optional | unary | stable | Versión del daemon, estado y puerto gRPC. |
| `SetVariable` | `core` | `set_variable` | optional | unary | stable | Publica una variable que comandos y otros plugins pueden leer. |
| `SubscribeEvents` | `event_handlers` | `subscribe_events` | required | server | stable | El stream filtrado de eventos del daemon; toda la capability event_handlers. |
| `FireTrigger` | `triggers` | `fire_trigger` | required | unary | stable | Dispara uno de los tipos de trigger de este plugin y ejecuta los comandos que escuchen. |
| `SendChatMessage` | `client` | `send_chat_message` | required | server | stable | Envía un mensaje de chat como este plugin y transmite en streaming la respuesta del asistente de vuelta. |
| `PushToUi` | `ui_contributions` | `push_to_ui` | optional | unary | stable | Envía un evento a los propios iframes de este plugin — la ruta de retorno para CallFromUi. |
| `SetThemeContribution` | `ui_contributions` | `set_theme_contribution` | optional | unary | stable | Aporta colores, fondo de pantalla y shader al tema activo de Astra. |

## Vacíos

Ninguno. El SDK de TypeScript vincula cada hook de la spec.
</content>
