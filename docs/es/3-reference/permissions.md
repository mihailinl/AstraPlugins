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

   <!-- doctest: output from="astra-plugin check --strict ." -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client
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

## Los ocho ids

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

`dom_access` y `client` no bloquean ningún RPC, y ese es el punto: son
**superficies**. `dom_access` decide si una contribución de UI se renderiza
como un script en la ventana de Astra o como un iframe en sandbox; `client`
es un techo sobre lo que puede ser un plugin. Se rechazan donde se entrega
la superficie, no en una puerta de llamada.

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

<!-- doctest: output from="astra-plugin doctor ." -->
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

Los permisos se agrupan por riesgo. Los cinco de alto riesgo reciben cada
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
