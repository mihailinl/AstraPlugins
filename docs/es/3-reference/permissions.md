> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/3-reference/permissions.md) es la referencia autorizada.

# Permisos

Qué otorga cada id de `[permissions]`, qué le cuesta al usuario, y cómo
escribir un `reason` que valga la pena leer.

Esta es la página orientada al autor. Las reglas normativas — concesiones,
techos, `permissions_hash`, la semántica exacta de rechazo — están en
[`spec/permissions.md`](../spec/permissions.md). La tabla generada de qué
RPC bloquea cada id está en
[`reference/manifest.md`](../reference/manifest.md) y
[`reference/parity.md`](../reference/parity.md), ambas derivadas de
`spec/hooks.yaml` y comprobadas contra la propia tabla del daemon mediante
la regla de paridad R6.

## La forma general

`[capabilities]` dice qué puede llamar el daemon **hacia dentro** de tu
plugin. `[permissions]` dice a qué RPC del host puede llamar tu plugin
**hacia fuera**. Dos preguntas, dos secciones; una capability nunca implica
un permiso.

Tres propiedades, todas las cuales sorprenden a alguien tarde o temprano:

1. **Denegación por defecto.** Sin sección `[permissions]` no hay RPC del
   host más allá de las cuatro de arranque.
2. **Declarar es pedir, no recibir.** Tu manifiesto es una solicitud. El
   conjunto concedido lo resuelve el daemon a partir de la procedencia del
   plugin y, para un plugin instalado o importado, se guarda donde el
   plugin no puede escribirlo — el manifiesto vive en el propio directorio
   de tu plugin, que tu plugin sí puede editar. **El sideload invierte
   esto**: para un directorio fuente en modo desarrollador, el manifiesto
   *es* la concesión, releído en cada carga, sin techo. Eso es lo que hace
   funcionar el bucle de creación, y también por qué el sideload es una
   herramienta de desarrollo y no una vía de instalación.
3. **Un id desconocido se conserva e inerte.** Los ids nuevos llegan con
   nuevas versiones de Astra, así que un daemon más antiguo conserva una
   clave que no reconoce en lugar de rechazar tu manifiesto. No concede
   nada. `astra-plugin check` avisa — una errata es indistinguible de un id
   compatible hacia adelante en el momento del análisis, así que es un
   aviso y no un error, y `--strict` lo convierte en una salida fallida:

   <!-- doctest: output from="astra-plugin check --strict ." unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client, read_ai_settings, speak, read_user_identity, receive_attachments, request_settings_change
     FAILED: 1 warning(s), and --strict treats warnings as errors
   ```

   La pantalla de consentimiento de instalación de Astra muestra el mismo
   id bajo su etiqueta `permission.unrecognised`, así que tampoco se
   descarta nunca en silencio al entrar.

## Las cuatro llamadas que no necesitan nada

| RPC | Por qué es gratis |
|---|---|
| `Register` | El handshake. Todavía no hay plugin que tenga permisos |
| `PluginLog` | Escribir en tu propio log |
| `GetPluginSelfConfig` | Leer tu propia configuración |
| `GetDaemonInfo` | `version`, `state`, `grpc_port`, `language` — todo ya entregado en la respuesta de registro |

Que `GetDaemonInfo` sea gratis es una decisión, no un descuido: una casilla
que no protege nada es la forma en que los usuarios aprenden a marcar
casillas sin pensar.

## Los trece ids

| Id | Bloquea | Casilla propia | Rechazado en importación local | Qué te permite hacer |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | no | no | Ejecutar las automatizaciones guardadas del usuario |
| `subscribe_events` | `SubscribeEvents` | no | no | Recibir eventos del daemon — **toma una lista blanca `types`** |
| `set_variable` | `SetVariable` | no | no | Escribir en el contexto de variables del daemon, con espacio propio |
| `send_chat_message` | `SendChatMessage` | **sí** | **sí** | Impulsar un turno de IA como si hubiera hablado el usuario |
| `push_to_ui` | `PushToUi` | **sí** | no | Enviar un evento a tus propios paneles |
| `set_theme_contribution` | `SetThemeContribution` | **sí** | **sí** | Cambiar el estilo de toda la app |
| `dom_access` | — (una superficie) | **sí** | **sí** | Ejecutar tu código dentro de la ventana de Astra, con acceso a conversaciones y a la interfaz de cualquier otro plugin |
| `client` | — (una superficie) | **sí** | **sí** | Ser un frontend de chat con su propia sesión |
| `read_ai_settings` | `GetAiSettings` | no | no | Leer el proveedor, el modelo y el endpoint del chat del usuario — nunca una clave |
| `speak` | `Speak`, `StopSpeaking` | **sí** | no | Decir tus propias palabras en voz alta con la voz de Astra, y detenerlas |
| `read_user_identity` | `GetUserIdentity` | no | no | Leer seudónimos de esta instalación y de la cuenta con sesión iniciada, creados solo para tu plugin |
| `receive_attachments` | — (una entrega) | **sí** | no | Recibir las imágenes que adjuntó la persona, en una herramienta que las pide |
| `request_settings_change` | `RequestSettingsChange` | no | no | Pedir a la persona que cambie un ajuste que el asistente puede cambiar, en una tarjeta que ella responde |

`dom_access` y `client` no bloquean ningún RPC, y ese es el punto: son
**superficies**. `dom_access` decide si una contribución de UI se renderiza
como un script en la ventana de Astra o como un iframe en sandbox; `client`
es un techo sobre lo que puede ser un plugin. Se rechazan donde se entrega
la superficie, no en una puerta de llamada. `receive_attachments` tampoco
bloquea ningún RPC, desde el otro lado: no hay nada que tengas que llamar.
Decide lo que Astra *envía* a una de tus herramientas —
[más abajo](#recibir-las-imágenes-que-adjuntó-la-persona).

`dom_access` además recibe una segunda pantalla de consentimiento. Si vas a
usarlo, lee primero [el modelo de seguridad](../1-orientation/security.md)
y asegúrate de que `push_to_ui` hacia tu propio panel no sea suficiente.

## Argumentos

Dos ids toman argumentos, y ambos acotan lo que obtienes.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "meeting-notes"
name = "Meeting Notes"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/meeting_notes"

[capabilities]
tools = true
event_handlers = true

[permissions]
subscribe_events = { types = ["command_completed", "state_changed"], reason = "Notices when a recording command finishes so it can write the summary" }
set_variable = { scopes = ["plugin"], reason = "Stores the id of the note it just wrote so your commands can open it" }
fire_trigger = { reason = "Fires meeting_summarised when a summary is ready" }
```

- **`subscribe_events.types` es una lista blanca, aplicada por el daemon**
  — no por el filtro que envía tu plugin. Sin ella, cada suscriptor
  recibía todos los eventos, incluido `speech_recognized`, que lleva las
  transcripciones del usuario. Una lista vacía no permite nada.
- **`set_variable.scopes`** es `"plugin"`, `"session"` o `"persistent"`.

## Leer los ajustes de IA del usuario

Un plugin que llama él mismo al modelo del usuario — un asistente propio, un resumidor — necesita saber qué proveedor, modelo y endpoint eligió el usuario. **Pídeselos a Astra; nunca leas los archivos de Astra.** Declara `read_ai_settings` y llama a `GetAiSettings` (`get_ai_settings()` en Rust y Python, `getAiSettings()` en TypeScript):

| Campo | Qué es |
|---|---|
| `provider` | El id del proveedor del chat. Un endpoint guardado por el usuario es `openai_compatible`; el servicio propio de Astra es `astra` |
| `model` | El id del modelo del chat |
| `api_base_url` | El endpoint. Se eliminan userinfo, query y fragment; la ruta se envía tal como la configuró la persona (un relay que pone un token en la ruta te lo entrega). Vacío para `astra`, cuyo endpoint no te corresponde llamar |
| `is_loopback` | El endpoint está en esta máquina (`127.0.0.0/8`, `::1`, `localhost`) — un modelo local |

Nunca lleva una clave de API, ni los demás endpoints guardados del usuario, ni el prompt del sistema, ni ningún rol salvo el del chat. Un plugin que necesita una clave se la pide al usuario en su propio `[config]` (márcala como secreta). No es de alto riesgo ni se rechaza en una importación local: es el camino honesto a esta información, y ponerle un precio superior al de leer `settings.json` empujaría a los plugins en la dirección equivocada. Leer los archivos propios de Astra es algo que busca la revisión humana en la publicación. Un Astra anterior a esta llamada responde `UNIMPLEMENTED`.

## Hablar con la voz de Astra

Un plugin que tiene algo que anunciar — un temporizador, una compilación que terminó, un mensaje que llegó — puede hacer que Astra lo diga. Declara `speak` y llama a `Speak` (`speak(text)` en Rust y Python, `ctx.speak(text)` en TypeScript).

`speak` es de **alto riesgo**: tus palabras se oyen con la voz de Astra, como si Astra las hubiera dicho, así que recibe su propia casilla de consentimiento. No se rechaza en una importación local — un aviso es algo corriente que un plugin puede querer, y la casilla es la decisión. Además del permiso concedido, `Speak` necesita **una cuenta que dé acceso a Astra** y **la voz de las respuestas de la persona activada**; se rechaza mientras Astra está bloqueado.

La llamada dura lo que dura el habla y responde con lo que fue de ella:

| Resultado | Qué significa | Qué hacer |
|---|---|---|
| `SPOKEN` | Se oyó | Nada |
| `STOPPED` | Se pidió silencio antes de que terminara: la palabra de activación, la voz de las respuestas desactivada, Detener, tu propio `StopSpeaking` | Nada — **no es un error**. No lo repitas sin que te lo pidan |
| `NOT_SPOKEN` | No se dijo; `error` (el mismo `PluginError` que lleva un fragmento de chat) dice por qué | Lee el código de abajo. Nada rechazado queda en cola |

| `error.code` | Cuándo |
|---|---|
| `PLUGIN_ERROR_BAD_ARGUMENTS` | El texto queda vacío al quitar los caracteres invisibles, o supera los **300 caracteres** (`speak_text_max_chars` en `spec/limits.yaml`). Un texto más largo se rechaza, nunca se recorta |
| `PLUGIN_ERROR_RATE_LIMITED` | Se agotó tu tiempo de habla. Se presupuesta en caracteres — **450 de una vez, luego 3 por segundo**, y cada llamada cuesta al menos 20 — y `retry_after_ms` dice cuándo vuelve a haber sitio |
| `PLUGIN_ERROR_UNAVAILABLE` | La persona desactivó la voz de Astra, Astra está bloqueado, no hay voz, o la cola de habla no pudo aceptarlo. Muestra el texto en su lugar; no le pidas a la persona que lo cambie |

Tus palabras se ponen en cola detrás de las tuyas anteriores, en un carril propio, así que nunca interrumpen una de las respuestas de Astra. `StopSpeaking` detiene todo lo que pediste decir, lo que suena y lo que está en cola, y nada más; comparte el permiso `speak` y funciona haya o no alguien con la sesión iniciada. Los límites son los del daemon: los SDK exportan `SPEAK_TEXT_MAX_CHARS` para que puedas mostrar un contador, y no comprueban nada por su cuenta. Un Astra anterior a esta llamada responde `UNIMPLEMENTED`.

## Saber quién usa Astra

Un plugin que limita el uso por persona o por máquina — una prueba, una cuota, una licencia — necesita un id estable para cada una. **Pídeselo a Astra; nunca leas un número de serie del hardware ni los archivos de Astra.** Declara `read_user_identity` y llama a `GetUserIdentity` (`get_user_identity()` en Rust y Python, `ctx.getUserIdentity()` en TypeScript):

| Campo | Qué es |
|---|---|
| `install_id` | Esta instalación de Astra: la misma tras reinicios y actualizaciones de Astra y de tu plugin, distinta en otra instalación. Vacío mientras Astra aún no tiene clave de instalación |
| `signed_in` | Una persona ha iniciado sesión en Astra |
| `authorized` | …y su cuenta da acceso a Astra |
| `account_id` | La cuenta con sesión iniciada: la misma en cada dispositivo donde la persona inicia sesión. Vacío salvo con `authorized` |

Ambos ids son **seudónimos creados solo para tu plugin**: otro plugin lee ids distintos para la misma persona y la misma máquina, así que dos plugins no pueden cruzar sus registros a través de ellos. Esto vale frente a plugins que usan esta API honestamente: el código nativo de un plugin puede leer los archivos de Astra. Ninguno es secreto, y ninguno es nunca el id propio de la cuenta, el nombre o el correo electrónico de la persona, ni un número de serie del hardware. No es de alto riesgo ni se rechaza en una importación local: es la alternativa honesta a un número de serie de la máquina, y ponerle un precio alto empujaría a un plugin de vuelta a uno. Un Astra anterior a esta llamada responde `UNIMPLEMENTED`.

**`auth_changed` se restringe en consecuencia** (Astra, 2026-11-12). Un plugin al que se le concede el evento `auth_changed` recibía antes el id propio de la cuenta, el nombre visible de la persona y su plan. Ahora recibe `authenticated`, `authorized`, `timestamp` y `account_id` — el mismo seudónimo que responde `GetUserIdentity`, y `""` salvo que tengas `read_user_identity` y la cuenta dé acceso a Astra. `user_id` y `user_name` siguen llegando, como `null`, y `subscription_tier` como `""`, para que un parser escrito para la forma antigua siga funcionando; ninguno lleva ya un valor.

## Recibir las imágenes que adjuntó la persona

Una herramienta que trabaja con una imagen — leer un recibo, identificar una planta, describir una foto — puede pedir las imágenes que la persona adjuntó al mensaje que Astra está respondiendo. **Ninguna versión publicada de Astra lo hace todavía:** el daemon solo las envía cuando está compilado con la build feature `plugin-provider-slots`. Cualquier otro Astra ignora la petición y tu herramienta no recibe imágenes.

Hacen falta dos cosas. Declara `receive_attachments` en `[permissions]` y marca cada herramienta que quiera imágenes; luego léelas en su handler:

| SDK | Marcar la herramienta | Leer las imágenes |
|---|---|---|
| Rust | `#[tool(wants_attachments)]`, o `ToolDef::new(…).with_attachments(true)` | `ctx.attachments()` |
| Python | `@tool("…", wants_attachments=True)`, o `ToolDef(…, wants_attachments=True)` | `current_attachments()` |
| TypeScript | `wantsAttachments: true` en `tool({…})` o en un `ToolDef` | `ctx.attachments`, o `currentAttachments()` |

Cada imagen lleva `mime_type` (`mimeType` en TypeScript), `data` — los bytes — y `filename`, solo el nombre con el que se adjuntó, nunca una carpeta. Una herramienta que no las pidió lee una lista vacía, igual que cualquier llamada que no trae imágenes.

Astra entrega imágenes a una llamada solo cuando se cumple todo esto:

- la herramienta declaró `wants_attachments` en su respuesta a `ListTools`;
- tu plugin tiene `receive_attachments`;
- la llamada se hizo al responder un mensaje que la persona envió en una conversación — la invocación de la llamada nombra esa conversación. Nunca en un report wake, en el paso de IA de un comando ni en el turno de un subagente, y nunca mientras Astra retiene el turno por un comando del Workshop que la persona no ha aprobado.

Lo que llega es solo lo adjuntado a **ese único mensaje**: nunca una imagen de antes en la conversación, nunca una que produjo una herramienta y nunca una que nombró el modelo. Como máximo **4** (`image_input_max_images` en `spec/limits.yaml`) y 20 MiB en total, se conservan las más recientes, en el orden en que se adjuntaron; una imagen que no se puede leer nunca se envía. Cuando algunas no se enviaron — más de las que caben, o a tu plugin le falta la concesión —, se le dice al **modelo** después de tu resultado; tu herramienta simplemente recibe menos, o ninguna.

Hoy el compositor del chat de Astra escala cada imagen adjunta a 768 píxeles como máximo y la vuelve a codificar como JPEG, conservando el nombre de archivo original; eso es lo que recibe tu herramienta. Guíate por `mime_type`, no por la extensión de `filename`.

Una llamada puede traer hasta 20 MiB de imágenes, más que el límite de recepción por defecto de gRPC, 4 MiB. Los servidores de capacidades de los tres SDK reciben hasta 64 MiB (`plugin_max_message_bytes`); un plugin que sirve el protocolo sin un SDK debe subir el límite de recepción de su propio servidor por encima de 4 MiB.

`receive_attachments` es de **alto riesgo**: las fotos de una persona llegan a código que no es de Astra, así que recibe su propia casilla de consentimiento. No se rechaza en una importación local — la casilla es la decisión, como con `speak`.

## Pedir a la persona que cambie un ajuste

Un plugin con una razón real para querer cambiar uno de los ajustes de Astra — un modelo para el que están afinadas sus herramientas, una voz que le va — lo **pide**, y la persona decide en una tarjeta. Nunca escribas tú el `settings.json` de Astra, y nunca tomes prestada la propia sesión de Astra para hacerlo: eso cambia el Astra de la persona a sus espaldas, y la revisión humana al publicar lo busca. Declara `request_settings_change` y llama a `RequestSettingsChange` (`request_settings_change(changes, reason)` en Rust y Python, `ctx.requestSettingsChange(changes, reason)` en TypeScript). **Ninguna versión publicada de Astra lo atiende todavía:** el daemon acepta solicitudes solo cuando está compilado con la característica de compilación `plugin-requests`; cualquier otro Astra responde `REFUSED` con el código `not_compiled`.

Cada cambio es una ruta de ajuste con puntos y el valor deseado, como JSON — los SDK serializan el valor por ti. Solo se pueden pedir los ajustes que el propio asistente puede cambiar — la voz, el modelo de IA, el idioma; nunca el modo de permisos, una clave ni Tool Search —, y cada valor se comprueba exactamente igual que el cambio propio del asistente. La tarjeta nombra tu plugin, muestra cada ajuste tal como está y como quedaría, y tu `reason`, con tus palabras. Cambian todos o ninguno, y lo que cambia es exactamente lo que mostró la tarjeta.

**La llamada dura hasta que la persona responde o la tarjeta caduca** — el tiempo de confirmación de Astra, al menos 30 segundos, 120 si la persona no lo cambió. Los SDK no le ponen ningún plazo propio. Nunca la esperes en un camino que deba responder rápido, como una llamada a herramienta que el modelo está esperando.

| Resultado | Qué significa | Qué hacer |
|---|---|---|
| `APPLIED` | La persona lo permitió; los ajustes contienen ahora lo que pediste | Nada |
| `UNCHANGED` | Ya lo contenían. No se preguntó a nadie | Nada |
| `DECLINED` | La persona dijo que no — ahora, o antes a que tu plugin cambiara uno de estos ajustes. Astra vuelve a preguntar por un ajuste así solo cuando ha cambiado de otra forma, o tras un reinicio | Sigue con lo que la persona tiene. **No vuelvas a preguntar sin que te lo pidan** |
| `TIMED_OUT` | Nadie respondió antes de que caducara la tarjeta (no tener ninguna ventana abierta también cuenta) | Pregunta más tarde, cuando la persona esté |
| `REFUSED` | No se preguntó, o no se aplicó: `code` dice por qué, `refused_path` nombra el ajuste cuando se trata de uno, y `error` es un `PluginError` | Lee el código abajo |

| `code` | Cuándo |
|---|---|
| `not_compiled` | Este Astra no acepta solicitudes: se compiló sin la característica `plugin-requests` |
| `locked` | Astra está bloqueado con su código de acceso |
| `invalid` | Ningún cambio, una ruta dos veces, un valor que no es JSON, o más de lo que una tarjeta puede mostrar entero |
| `too_many` | Más de **8** cambios (`settings_change_max_changes` en `spec/limits.yaml`) |
| `reason_too_long` | Un motivo de más de **140 caracteres** (`settings_change_reason_max_chars`). Se muestra entero, así que se rechaza, nunca se recorta |
| `busy` | Una de tus solicitudes ya está esperando a la persona: una tarjeta por plugin a la vez |
| `rate_limited` | **Dos solicitudes de una vez, luego una cada dos minutos**; `error.retry_after_ms` dice cuándo vuelve a haber hueco |
| `not_assistant_editable` | Una ruta que el asistente no puede cambiar |
| `invalid_value`, `unknown_choice` | Un valor que el ajuste no puede contener, o una opción que no ofrece |
| `needs_api_key`, `needs_stt_provider`, `provider_unreachable` | El cambio dejaría a Astra sin lo que necesita: una clave para ese proveedor de IA, un reconocedor de voz, un proveedor que responda |
| `stale` | Los ajustes cambiaron mientras la tarjeta estaba abierta, así que lo que la persona permitió no es lo que se escribiría. No se escribió nada |
| `stopped` | La autoridad de tu plugin terminó antes — se detuvo, se desactivó o se retiró, o la cuenta dejó de dar acceso a Astra |
| `write_refused` | No se pudieron escribir los ajustes |

Los valores actuales nunca se devuelven: lo que tu plugin sabe es el resultado. Los límites son del daemon: los SDK exportan `SETTINGS_CHANGE_MAX_CHANGES` y `SETTINGS_CHANGE_REASON_MAX_CHARS` y no comprueban ninguno por sí mismos. Además del permiso, la llamada necesita **una cuenta que dé acceso a Astra**; un permiso que falta, o una cuenta que no da acceso a Astra, es una llamada fallida como cualquier llamada al host, no un resultado. No es de alto riesgo ni se rechaza en una importación local: cada solicitud es una tarjeta que la persona responde, así que el consentimiento se pide cada vez. Un Astra anterior a esta llamada responde `UNIMPLEMENTED`.

## Escribir un reason

El `reason` se muestra debajo de la etiqueta propia de Astra para el
permiso, visualmente subordinado, entrecomillado, texto plano, limitado a
140 caracteres, y siempre precedido de *"The author says:"*. La etiqueta es
de Astra, en el idioma del usuario; el reason es tuyo. No puedes redactar
la etiqueta, y es deliberado: las correcciones de redacción se distribuyen
con Astra y no deben ser escribibles desde un listado.

Un buen reason:

- **nombra la funcionalidad que el usuario reconoce**, no la API — *"Fires
  the on_dice_roll trigger you configure"*, no *"calls FireTrigger"*;
- **dice cuándo**, si no es siempre — *"only while a recording is in
  progress"*;
- **no repite la etiqueta.** Astra ya la mostró;
- **no presiona.** Sin urgencia, sin amenazas, sin instrucciones al
  usuario. Una pantalla de consentimiento es el último lugar para hacer una
  excepción, y el texto con overrides bidi o joiners de ancho cero se
  rechaza donde se muestra tal cual.

| En lugar de | Escribe |
|---|---|
| `"needs fire_trigger"` | `"Fires the trigger you configure when a roll completes"` |
| `"required for the plugin to work"` | `"Reads command-completion events so it can log the run"` |
| `"full access to the UI"` | `"Draws the timer in the panel this plugin adds to the sidebar"` |
| `"REQUIRED! Do not disable!"` | — elimina el permiso, o di para qué es |

Un permiso sin un reason plausible es un permiso que hay que borrar del
manifiesto. Nada lo comprueba automáticamente; una persona que lea tu
listado es la única red de seguridad, y `astra-plugin check` te dirá
cuándo has declarado un permiso que tus capabilities no necesitan.

## Qué pasa cuando falta un permiso

La llamada vuelve como `permission_denied`, con un mensaje que nombra el
permiso **y** de dónde vino el conjunto concedido. En una prueba puedes
simular exactamente eso:

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Notifier;

#[astra::plugin]
impl Notifier {
    /// Announce that something happened.
    #[tool]
    async fn announce(&self, ctx: &PluginContext) -> Result<String, ToolError> {
        // Handle the denial rather than propagating it: a tool that returns an
        // error the model cannot act on is worse than one that says what it did.
        match ctx.host().fire_trigger("announced", "{}").await {
            Ok(()) => Ok("announced".into()),
            // `{e:#}` and not `{e}`: the host call fails with a short outer
            // message and the useful half — the permission id and where the
            // granted set came from — is in the cause chain.
            Err(e) => Ok(format!("could not fire the trigger: {e:#}")),
        }
    }
}

astra::main!(Notifier::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn a_missing_grant_is_reported_not_hidden() {
        let h = Harness::new(Notifier::default()).start().await.unwrap();
        h.host().deny("fire_trigger");

        let answer = h.call_tool("announce", json!({})).await.unwrap();
        assert!(answer.contains("fire_trigger"), "{answer}");
    }
}
```

`astra-plugin doctor` responde la misma pregunta sobre un manifiesto antes
de que lo ejecutes nunca:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## De dónde viene el conjunto concedido

| Vía de instalación | Concedido |
|---|---|
| Desde la tienda, verificado | lo que pidió el manifiesto, tras el consentimiento |
| Un archivo `.astraplugin` importado a mano | el manifiesto, **capado**: `send_chat_message`, `set_theme_contribution`, `dom_access`, `client` se rechazan de plano |
| Un directorio fuente en sideload, modo desarrollador activado | el manifiesto, sin capar |
| `Untrusted` / `TamperDetected` / `Revoked` | nada |
| Instalado antes de que existieran los registros de confianza | el manifiesto, capado como un archivo importado |

Tabla completa y el razonamiento:
[`spec/permissions.md` §4](../spec/permissions.md).

## Consentimiento, desde el lado del usuario

Los permisos se agrupan por riesgo. Los siete de alto riesgo reciben cada
uno su propia casilla, e Instalar permanece deshabilitado hasta que todas
estén marcadas; `dom_access` recibe una segunda pantalla. Deliberadamente
**no hay "escribe para confirmar"**: ese es el patrón para destrucción
irreversible, y acostumbrar a los usuarios a teclear para pasarlo destruye
la señal que lleva la casilla.

En una actualización: los permisos sin cambios o reducidos se aplican en
silencio; los permisos **ampliados** dejan la actualización preparada sin
instalarla y mantienen la versión anterior en ejecución hasta que el
usuario revise la diferencia. Rechazar no cuesta nada.
</content>
