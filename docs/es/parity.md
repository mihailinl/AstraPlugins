> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/parity.md) es la referencia autorizada. La página en inglés está GENERADA por `tools/parity/gen.py` a partir de `spec/hooks.yaml` — esta traducción es una instantánea mantenida a mano, no otra copia generada.

# Paridad de hooks

Protocolo **1** · **35** hooks · fuente de verdad [`spec/hooks.yaml`](../../spec/hooks.yaml).

Un *hook* es un RPC en uno de los dos servicios orientados a plugins.
`PluginCapabilityService` corre **daemon → plugin**: tu plugin lo sirve
y el daemon llama hacia dentro. `PluginHostService` corre
**plugin → daemon**: el daemon lo sirve y tu plugin llama hacia fuera.
`PluginService` no está aquí — el daemon lo sirve a la interfaz de
Astra y ningún plugin lo toca jamás.

| Columna | Significado |
|---|---|
| **Capability** | La clave de `[capabilities]` en `plugin.toml` a la que pertenece este hook, o `core` para los hooks que tiene todo plugin. |
| **Permission** | Solo `PluginHostService`. La clave de `[permissions]` a la que el daemon condiciona la llamada (§5.6), o `none` si cualquier plugin puede llamarla siempre. **No es la misma pregunta que Capability:** la capability dice a qué funcionalidad pertenece la llamada, el permiso es a lo que consintió el usuario, y el daemon responde a partir del conjunto de permisos *concedido*. Verificado contra `HOST_RPC_PERMISSIONS` del daemon mediante la regla R6. |
| **Req** | `required` — la capability no funciona sin el hook. `optional` — el daemon sigue adelante cuando está ausente. |
| **Routing** | `live` — el daemon realmente lo llama, y el punto de llamada está nombrado. `unrouted` — declarado en el proto, no lo llama nadie. `deprecated` — en proceso de retirada. |
| `stable` | El SDK vincula este RPC a un handler que realmente hace trabajo — verificado contra su código fuente por la regla R1 de `tools/parity/check.py`, que resuelve el destino del dispatch (`.bind(this)` de TypeScript, el método servicer de Python, el `async fn` de Rust) y lee *ese* cuerpo. Si la vinculación alcanza algo cuando se ejercita un proceso de plugin real es la pregunta de la regla R7, no de R1. |
| `planned` | Comprometido, no distribuido. La fecha es el plazo de gracia; la regla R4 hace fallar el build una vez que pasa. |
| `n/a` | No implementado y no comprometido. Un handler registrado cuyo cuerpo solo responde `UNIMPLEMENTED` cuenta como `n/a`, porque en el cable eso *es* un hook ausente — R1 lee el cuerpo del handler exactamente para esto. |

## Hallazgos

Derivados de las filas de abajo, no escritos a mano. Cada uno es una
forma en que el código de un autor de plugin falla hoy.

1. **`TtsSynthesizeStream` no está enrutado.** El proto lo declara y no
   existe ningún punto de llamada en el daemon — vinculado de todos
   modos en Rust, Python, TypeScript. O se cablea o se retira; hoy es
   una promesa que el daemon no cumple.
2. **`AiGetModels` está obsoleto pero sigue vinculado** en Rust, Python,
   TypeScript. Conserva las vinculaciones para que un plugin antiguo
   siga recibiendo `UNIMPLEMENTED` en lugar de un error de transporte;
   no añadas ninguna nueva.

## PluginCapabilityService — daemon → plugin

| RPC | Capability | Req | Routing | Stream | Rust | Python | TypeScript | Punto de llamada del daemon |
|---|---|---|---|---|---|---|---|---|
| `ListTools` | `tools` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3624` |
| `CallTool` | `tools` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7601` |
| `TtsSynthesize` | `tts` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7910` |
| `TtsSynthesizeStream` | `tts` | optional | unrouted | server | stable | stable | stable | **ninguno** |
| `TtsListVoices` | `tts` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7958` |
| `TtsGetConfigFields` | `tts` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8198` |
| `TtsActivate` | `tts` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7990` |
| `SttProcess` | `stt` | required | live | bidi | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8045` |
| `SttGetLanguages` | `stt` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8166` |
| `SttGetConfigFields` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8222` |
| `SttLoad` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8246` |
| `SttUnload` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8324` |
| `SttGetLoadState` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8275` |
| `AiComplete` | `ai_provider` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/capability_bridge.rs:157` |
| `AiGetModels` | `ai_provider` | optional | deprecated | unary | stable | stable | stable | **ninguno** |
| `ExecuteAction` | `actions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7755` |
| `GetPluginActionTypes` | `actions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3633` |
| `GetPluginTriggerTypes` | `triggers` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3642` |
| `OnActiveTriggers` | `triggers` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7853` |
| `GetUiContributions` | `ui_contributions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3651` |
| `CallFromUi` | `ui_contributions` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3952` |
| `OnConfigChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:4133` |
| `OnLanguageChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:4074` |
| `Shutdown` | `core` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/instance.rs:1290` |
| `HealthCheck` | `core` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:4394` |

## PluginHostService — plugin → daemon

| RPC | Capability | Permission | Req | Routing | Stream | Rust | Python | TypeScript | Punto de llamada del daemon |
|---|---|---|---|---|---|---|---|---|---|
| `Register` | `core` | `none` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:1474` |
| `GetPluginSelfConfig` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2045` |
| `PluginLog` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2068` |
| `GetDaemonInfo` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2106` |
| `SetVariable` | `core` | `set_variable` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2126` |
| `SubscribeEvents` | `event_handlers` | `subscribe_events` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:1663` |
| `FireTrigger` | `triggers` | `fire_trigger` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:1860` |
| `SendChatMessage` | `client` | `send_chat_message` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:1717` |
| `PushToUi` | `ui_contributions` | `push_to_ui` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2170` |
| `SetThemeContribution` | `ui_contributions` | `set_theme_contribution` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2201` |

## Preparación por capability

¿Puede un plugin escrito en este lenguaje implementar hoy esta
capability en absoluto?

| Capability | Rust | Python | TypeScript |
|---|---|---|---|
| `tools` | sí | sí | sí |
| `tts` | sí | sí | sí |
| `stt` | sí | sí | sí |
| `ai_provider` | sí | sí | sí |
| `actions` | sí | sí | sí |
| `triggers` | sí | sí | sí |
| `ui_contributions` | sí | sí | sí |
| `core` | sí | sí | sí |
| `event_handlers` | sí | sí | sí |
| `client` | sí | sí | sí |

## Cobertura de conformidad

Los 23 hooks entrantes que una corrida de conformidad debe ejercitar —
cada hook `daemon → plugin` que el daemon realmente llama.
`astra-plugin test` llama a cada uno que impliquen las capabilities
declaradas del plugin y verifica que no haya `UNIMPLEMENTED` para los
`required`; los hooks `optional` están exentos, porque
`Unimplemented → hook ausente` es el contrato de compatibilidad hacia
adelante y un scaffold que declarara todo sería, si no, indistinguible
de un plugin roto. Copia legible por máquina:
[`spec/generated/conformance.json`](../../spec/generated/conformance.json).

| RPC | Capability | Req | Stream | Fase |
|---|---|---|---|---|
| `ListTools` | `tools` | required | unary | probe |
| `CallTool` | `tools` | required | unary | probe |
| `TtsSynthesize` | `tts` | required | unary | probe |
| `TtsListVoices` | `tts` | required | unary | probe |
| `TtsGetConfigFields` | `tts` | optional | unary | probe |
| `TtsActivate` | `tts` | optional | unary | probe |
| `SttProcess` | `stt` | required | bidi | probe |
| `SttGetLanguages` | `stt` | required | unary | probe |
| `SttGetConfigFields` | `stt` | optional | unary | probe |
| `SttLoad` | `stt` | optional | unary | probe |
| `SttUnload` | `stt` | optional | unary | probe |
| `SttGetLoadState` | `stt` | optional | unary | probe |
| `AiComplete` | `ai_provider` | required | server | probe |
| `ExecuteAction` | `actions` | required | unary | probe |
| `GetPluginActionTypes` | `actions` | required | unary | probe |
| `GetPluginTriggerTypes` | `triggers` | required | unary | probe |
| `OnActiveTriggers` | `triggers` | optional | unary | probe |
| `GetUiContributions` | `ui_contributions` | required | unary | probe |
| `CallFromUi` | `ui_contributions` | optional | unary | probe |
| `OnConfigChanged` | `core` | optional | unary | probe |
| `OnLanguageChanged` | `core` | optional | unary | probe |
| `HealthCheck` | `core` | required | unary | probe |
| `Shutdown` | `core` | required | unary | teardown |

## Notas

- **`TtsSynthesizeStream`** — Sintetiza una expresión como un stream de chunks, para reducir la latencia del primer audio. HALLAZGO: no existe ningún punto de llamada en el daemon dentro de astra-rs. Los tres SDK ya lo sirven y nada lo llama — la desviación que esta archivo existe para detectar ya no está, el rpc sin enrutar sí.
- **`TtsGetConfigFields`** — Campos de ajustes TTS adicionales, renderizados por DynamicField en la página Voice. Enrutado a través del helper `optional_hook` del daemon (manager.rs:2878), así que UNIMPLEMENTED significa ausente, y un fallo real sigue siendo un fallo.
- **`TtsActivate`** — Entrega una clave de contenido de voz licenciada para sellado único vinculado a la máquina. El proto dice que UNIMPLEMENTED se trata como "no se necesita activación"; el daemon NO lo enruta a través de `optional_hook` — manager.rs:2664 propaga el error y vox_activation.rs:319 hace fallar la activación. El comentario del proto es el que está equivocado.
- **`SttProcess`** — Chunks de audio entran, eventos de transcripción salen; cubre STT tanto de una sola vez como en streaming. También se ejercita en vivo en manager.rs:2808. La capacidad del canal en ambos extremos es spec/limits.yaml:stt_audio_channel_capacity.
- **`SttLoad`** — Carga el modelo del reconocedor, con la ruta resuelta por el daemon y el interruptor de GPU. manager.rs:2918 lo enruta a través de `optional_hook`, por eso es opcional.
- **`SttGetLoadState`** — Reporta Loaded / NotLoaded / NotNeeded para que el daemon pueda gestionar idle-unload. manager.rs:2960 mapea un hook ausente a NotNeeded, que es el comportamiento previo al hook.
- **`AiComplete`** — Transmite en streaming una completion de modelo; la única forma en que un plugin puede ser un proveedor de IA. Python y TypeScript lo vinculan como un generador async; Rust como un stream de servidor alimentado por canal que espera el primer chunk antes de abrir la respuesta, de modo que un hook sin sobrescribir puede seguir respondiendo UNIMPLEMENTED. Los tres SDK lo vinculan desde 5.4, así que `ai_provider` es implementable en cada lenguaje.
- **`AiGetModels`** — Lista los modelos que este proveedor puede ejecutar. HALLAZGO: implementado en los tres SDK y llamado por nadie. `all_ai_providers` tiene codificado supports_model_discovery=false, así que el selector nunca pregunta. Marcado obsoleto en el proto; conserva las vinculaciones, no añadas más. Obsoleto en 0.6, eliminado en 0.8, y no hay reemplazo: nada en el daemon le pregunta a un plugin qué modelos tiene, y AiComplete lleva el modelo elegido en la petición.
- **`OnActiveTriggers`** — Cuáles de los tipos de trigger de este plugin está escuchando actualmente un comando. manager.rs:2523 lo enruta a través de `optional_hook`.
- **`OnLanguageChanged`** — El idioma de la UI de Astra cambió; vuelve a renderizar todo lo visible para el usuario. manager.rs:1133 lo enruta a través de `optional_hook`.
- **`Shutdown`** — Detente limpiamente; el grupo de procesos se mata tras el período de gracia. El período de gracia es spec/limits.yaml:plugin_stop_grace_secs. Responde, luego sal.
- **`HealthCheck`** — Sonda de actividad (liveness), cada 15 s. Obligatorio en el sentido más estricto: este hook NO se enruta a través de `optional_hook`, así que cualquier error — UNIMPLEMENTED incluido — marca el plugin como muerto (manager.rs:1464).
- **`Register`** — El handshake: demostrar el token de arranque, recibir el token de sesión propio del plugin. La única ruta exenta del interceptor de autenticación. Cada RPC posterior del host debe llevar el token devuelto como x-session-token.
- **`SendChatMessage`** — Envía un mensaje de chat como este plugin y transmite en streaming la respuesta del asistente de vuelta. El token de sesión está limitado a PluginHostService, así que la ruta DaemonClient/ChatService a la que los SDK solían dirigir a los autores es permission_denied — este rpc es la única vía que funciona. Vinculado en los tres SDK desde 5.4.
- **`PushToUi`** — Envía un evento a los propios iframes de este plugin — la ruta de retorno para CallFromUi. Ahora vinculado en los tres. Python tuvo CallFromUi y no PushToUi durante tres releases, así que un plugin de UI en Python podía ser llamado y no podía responder de forma asíncrona.
- **`SetThemeContribution`** — Aporta colores, fondo de pantalla y shader al tema activo de Astra. La Fase 4 lo clasifica como de alto riesgo y lo rechaza por debajo del nivel 1, así que una vinculación sin el permiso concedido es un permission_denied, no un tema repintado. Vinculado en los tres SDK desde 5.4.
</content>
