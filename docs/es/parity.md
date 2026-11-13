> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/parity.md) es la referencia autorizada. La página en inglés está GENERADA por `tools/parity/gen.py` a partir de `spec/hooks.yaml` — esta traducción es una instantánea mantenida a mano, no otra copia generada.

# Paridad de hooks

Protocolo **1** · **49** hooks · fuente de verdad [`spec/hooks.yaml`](../../spec/hooks.yaml).

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
| **Punto de llamada del daemon** | El archivo desde el que el daemon llama a este hook, o **ninguno** cuando no lo llama nadie. El número de línea no se imprime aquí a propósito. Vive en `spec/hooks.yaml`, donde la regla R5 lo comprueba contra un punto de llamada real y `--fix-provenance` lo vuelve a apuntar; en una página no lo comprueba nada, se pudre con cada commit del daemon, y un puntero podrido se lee exactamente igual que uno correcto — uno de estos ya había derivado hasta el punto de llamada de otro rpc antes de que nadie se diera cuenta. Busca el nombre en snake_case del rpc en el archivo que se nombra aquí. |
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

## PluginCapabilityService — daemon → plugin

| RPC | Capability | Req | Routing | Stream | Rust | Python | TypeScript | Punto de llamada del daemon |
|---|---|---|---|---|---|---|---|---|
| `ListTools` | `tools` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `CallTool` | `tools` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `TtsSynthesize` | `tts` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `TtsSynthesizeStream` | `tts` | optional | unrouted | server | stable | stable | stable | **ninguno** |
| `TtsListVoices` | `tts` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `TtsGetConfigFields` | `tts` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `TtsActivate` | `tts` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttProcess` | `stt` | required | live | bidi | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttGetLanguages` | `stt` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttGetConfigFields` | `stt` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttLoad` | `stt` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttUnload` | `stt` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `SttGetLoadState` | `stt` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/voice.rs` |
| `AiComplete` | `ai_provider` | required | live | server | stable | stable | stable | `astra-daemon/src/plugins/capability_bridge.rs` |
| `AiGetModels` | `ai_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `WebSearch` | `web_search` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `ImageGenerate` | `image_provider` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `ImageGetModels` | `image_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `MusicSubscribe` | `music_provider` | required | live | server | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `MusicControl` | `music_provider` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `MusicGetQueue` | `music_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `MusicSearch` | `music_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `MusicPlay` | `music_provider` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/music.rs` |
| `ExecuteAction` | `actions` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `GetPluginActionTypes` | `actions` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `GetPluginTriggerTypes` | `triggers` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `OnActiveTriggers` | `triggers` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/capabilities.rs` |
| `GetUiContributions` | `ui_contributions` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/lifecycle.rs` |
| `CallFromUi` | `ui_contributions` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/ui_surface.rs` |
| `OnConfigChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/ui_surface.rs` |
| `OnLanguageChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/ui_surface.rs` |
| `Shutdown` | `core` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/instance.rs` |
| `HealthCheck` | `core` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/manager/health.rs` |

## PluginHostService — plugin → daemon

| RPC | Capability | Permission | Req | Routing | Stream | Rust | Python | TypeScript | Punto de llamada del daemon |
|---|---|---|---|---|---|---|---|---|---|
| `Register` | `core` | `none` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `GetPluginSelfConfig` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `PluginLog` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `GetDaemonInfo` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `SetVariable` | `core` | `set_variable` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `SubscribeEvents` | `event_handlers` | `subscribe_events` | required | live | server | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `FireTrigger` | `triggers` | `fire_trigger` | required | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `SendChatMessage` | `client` | `send_chat_message` | required | live | server | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `PushToUi` | `ui_contributions` | `push_to_ui` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `GetAiSettings` | `core` | `read_ai_settings` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `Speak` | `core` | `speak` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `StopSpeaking` | `core` | `speak` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `GetUserIdentity` | `core` | `read_user_identity` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `RequestSettingsChange` | `core` | `request_settings_change` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `ProposeCommand` | `core` | `propose_commands` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |
| `SetThemeContribution` | `ui_contributions` | `set_theme_contribution` | optional | live | unary | stable | stable | stable | `astra-daemon/src/plugins/host_service.rs` |

## Preparación por capability

¿Puede un plugin escrito en este lenguaje implementar hoy esta
capability en absoluto?

| Capability | Rust | Python | TypeScript |
|---|---|---|---|
| `tools` | sí | sí | sí |
| `tts` | sí | sí | sí |
| `stt` | sí | sí | sí |
| `ai_provider` | sí | sí | sí |
| `web_search` | sí | sí | sí |
| `image_provider` | sí | sí | sí |
| `music_provider` | yes | yes | yes |
| `actions` | sí | sí | sí |
| `triggers` | sí | sí | sí |
| `ui_contributions` | sí | sí | sí |
| `core` | sí | sí | sí |
| `event_handlers` | sí | sí | sí |
| `client` | sí | sí | sí |

## Cobertura de conformidad

Los 24 hooks entrantes que una corrida de conformidad debe ejercitar —
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
| `AiGetModels` | `ai_provider` | optional | unary | probe |
| `WebSearch` | `web_search` | required | unary | probe |
| `ImageGenerate` | `image_provider` | required | unary | probe |
| `ImageGetModels` | `image_provider` | optional | unary | probe |
| `MusicSubscribe` | `music_provider` | required | server | probe |
| `MusicControl` | `music_provider` | required | unary | probe |
| `MusicGetQueue` | `music_provider` | optional | unary | probe |
| `MusicSearch` | `music_provider` | optional | unary | probe |
| `MusicPlay` | `music_provider` | optional | unary | probe |
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
- **`TtsGetConfigFields`** — Campos de ajustes TTS adicionales, renderizados por DynamicField en la página Voice. Enrutado a través del helper `optional_hook` del daemon (manager/voice.rs:450), así que UNIMPLEMENTED significa ausente, y un fallo real sigue siendo un fallo.
- **`TtsActivate`** — Entrega una clave de contenido de voz licenciada para sellado único vinculado a la máquina. El proto dice que UNIMPLEMENTED se trata como "no se necesita activación"; el daemon NO lo enruta a través de `optional_hook` — manager/voice.rs:131 propaga el error y vox_activation.rs:319 hace fallar la activación. El comentario del proto es el que está equivocado.
- **`SttProcess`** — Chunks de audio entran, eventos de transcripción salen; cubre STT tanto de una sola vez como en streaming. También se ejercita en vivo en manager/voice.rs:342. La capacidad del canal en ambos extremos es spec/limits.yaml:stt_audio_channel_capacity.
- **`SttLoad`** — Carga el modelo del reconocedor, con la ruta resuelta por el daemon y el interruptor de GPU. manager/voice.rs:488 lo enruta a través de `optional_hook`, por eso es opcional.
- **`SttGetLoadState`** — Reporta Loaded / NotLoaded / NotNeeded para que el daemon pueda gestionar idle-unload. manager/voice.rs:530 mapea un hook ausente a NotNeeded, que es el comportamiento previo al hook.
- **`AiComplete`** — Transmite en streaming una completion de modelo; la única forma en que un plugin puede ser un proveedor de IA. Python y TypeScript lo vinculan como un generador async; Rust como un stream de servidor alimentado por canal que espera el primer chunk antes de abrir la respuesta, de modo que un hook sin sobrescribir puede seguir respondiendo UNIMPLEMENTED. Los tres SDK lo vinculan desde 5.4, así que `ai_provider` es implementable en cada lenguaje.
- **`AiGetModels`** — Lista los modelos que este proveedor puede ejecutar, y cómo quiere usarse cada uno (sus hints), para el selector de modelos de Astra. Se consulta al arrancar el plugin, junto con sus demás definiciones, y de nuevo cuando se actualiza la página de IA; UNIMPLEMENTED o un error significa que no hay lista. El modelo elegido llega en el `model` de AiComplete, y uno vacío significa `default_model`. Los `hints` de un modelo (si no, los `provider_hints` de la lista) solo cambian los turnos de Astra con ese modelo, y solo en un daemon compilado con `plugin-provider-slots`; un plugin que declara `accepts_images` debe aceptar mensajes de 64 MiB, como hace el servidor de capacidades de cada SDK.
- **`OnActiveTriggers`** — Cuáles de los tipos de trigger de este plugin está escuchando actualmente un comando. manager/capabilities.rs:438 lo enruta a través de `optional_hook`.
- **`OnLanguageChanged`** — El idioma de la UI de Astra cambió; vuelve a renderizar todo lo visible para el usuario. manager/ui_surface.rs:352 lo enruta a través de `optional_hook`.
- **`Shutdown`** — Detente limpiamente; el grupo de procesos se mata tras el período de gracia. El período de gracia es spec/limits.yaml:plugin_stop_grace_secs. Responde, luego sal.
- **`HealthCheck`** — Sonda de actividad (liveness), cada 15 s. Obligatorio en el sentido más estricto: este hook NO se enruta a través de `optional_hook`, así que cualquier error — UNIMPLEMENTED incluido — marca el plugin como muerto (manager/health.rs:337).
- **`Register`** — El handshake: demostrar el token de arranque, recibir el token de sesión propio del plugin. La única ruta exenta del interceptor de autenticación. Cada RPC posterior del host debe llevar el token devuelto como x-session-token.
- **`SendChatMessage`** — Envía un mensaje de chat como este plugin y transmite en streaming la respuesta del asistente de vuelta. El token de sesión está limitado a PluginHostService, así que la ruta DaemonClient/ChatService a la que los SDK solían dirigir a los autores es permission_denied — este rpc es la única vía que funciona. Vinculado en los tres SDK desde 5.4.
- **`PushToUi`** — Envía un evento a los propios iframes de este plugin — la ruta de retorno para CallFromUi. Ahora vinculado en los tres. Python tuvo CallFromUi y no PushToUi durante tres releases, así que un plugin de UI en Python podía ser llamado y no podía responder de forma asíncrona.
- **`GetAiSettings`** — El proveedor, el modelo y el endpoint del chat del usuario (nunca una clave), para que un plugin no tenga que leer los archivos de Astra. Un Astra anterior a 2026-11-10 responde UNIMPLEMENTED; un endpoint guardado se lee como openai_compatible y el servicio propio de Astra como astra sin URL.
- **`Speak`** — Dice en voz alta las propias palabras del plugin con la voz de Astra; responde cuando se dijeron, se detuvieron o se rechazaron. speak es de alto riesgo (su propia casilla de consentimiento). Necesita una cuenta que dé acceso a Astra y la voz de las respuestas de la persona activada. Como máximo 300 caracteres, rechazado y nunca recortado (spec/limits.yaml:speak_text_max_chars); 450 caracteres de tiempo de habla de una vez, luego 3 por segundo, y más allá NOT_SPOKEN lleva RATE_LIMITED y retry_after_ms. STOPPED no es un error. Un Astra anterior a 2026-11-12 responde UNIMPLEMENTED.
- **`StopSpeaking`** — Detiene todo lo que este plugin pidió decir, lo que suena y lo que está en cola, y nada más de lo que Astra esté diciendo. Bloqueado por speak, el único permiso que comparten dos rpc del host; permitido haya o no alguien con la sesión iniciada. Cada Speak que corta responde STOPPED.
- **`GetUserIdentity`** — Seudónimos de esta instalación y de la cuenta con sesión iniciada, creados solo para este plugin; nunca el id propio de la cuenta, un nombre, un correo electrónico ni un número de serie del hardware. account_id está vacío salvo con authorized y es el mismo en cada dispositivo donde la persona inicia sesión; el mismo valor llega como account_id en los eventos auth_changed de este plugin. Un Astra anterior a 2026-11-12 responde UNIMPLEMENTED.
- **`RequestSettingsChange`** — Pedir a la persona que cambie algunos ajustes de Astra — solo los que el propio asistente puede cambiar — en una tarjeta que ella responde; nada cambia sin su Permitir. Necesita una cuenta que dé acceso a Astra y un Astra compilado con la característica de compilación plugin-requests (si no, REFUSED con el código not_compiled). De 1 a 8 cambios, cada ruta una vez, todos o ninguno, y un motivo de como máximo 140 caracteres, rechazado y nunca recortado (spec/limits.yaml:settings_change_max_changes, settings_change_reason_max_chars). Una tarjeta por plugin a la vez (una segunda solicitud mientras una está abierta es busy); una ráfaga de 2 solicitudes y luego 1 cada 120 s (rate_limited con retry_after_ms). Responde APPLIED, UNCHANGED (no se preguntó a nadie), DECLINED (también para un ajuste que la persona ya rechazó, hasta que cambie de otra forma o Astra se reinicie), TIMED_OUT o REFUSED con un código; nunca un valor actual. La llamada dura hasta que la persona responde o la tarjeta caduca. Un Astra anterior a 2026-11-13 responde UNIMPLEMENTED.
- **`ProposeCommand`** — Ofrecer a la persona un comando portable para conservar, bajo la clave propia de este plugin; solo lo conserva desde la hoja del Workshop de Astra, que muestra cada disparador y cada paso. propose_commands es de alto riesgo (su propia casilla de consentimiento): un comando conservado se ejecuta más tarde, con sus disparadores, como un comando propio de la persona — sus pasos, incluidos los integrados como un comando de shell, se ejecutan sin volver a preguntar. Necesita una cuenta que dé acceso a Astra y un Astra compilado con la característica de compilación plugin-requests (si no, REFUSED con el código not_compiled; en un Astra anterior a 2026-11-13 la llamada falla con UNIMPLEMENTED). La clave tiene de 1 a 64 caracteres de a-z A-Z 0-9 . _ - y la misma clave ofrecida de nuevo actualiza el mismo comando; el comando es como máximo 1 MiB de JSON portable, leído por el propio lector del Workshop (sin los campos locales), y puede usar las acciones y disparadores integrados de Astra y los propios de este plugin — nunca los de otro plugin (foreign_plugin); el motivo tiene como máximo 140 caracteres, rechazado y nunca recortado (spec/limits.yaml:propose_command_max_bytes, propose_command_reason_max_chars). Una tarjeta por plugin a la vez (una segunda oferta mientras una está abierta es busy); una ráfaga de 2 ofertas y luego 1 cada 120 s (rate_limited con retry_after_ms). Responde SAVED (enabled: si el comando queda activado una vez conservado), UNCHANGED (lo conservado bajo la clave vino de esta misma oferta — también si la persona lo editó; no se preguntó a nadie), DECLINED (también para este mismo comando rechazado antes, hasta que Astra se reinicie), TIMED_OUT o REFUSED con un código. La llamada dura hasta que la persona responde o la tarjeta caduca.
- **`SetThemeContribution`** — Aporta colores, fondo de pantalla y shader al tema activo de Astra. La Fase 4 lo clasifica como de alto riesgo y lo rechaza por debajo del nivel 1, así que una vinculación sin el permiso concedido es un permission_denied, no un tema repintado. Vinculado en los tres SDK desde 5.4.
</content>
