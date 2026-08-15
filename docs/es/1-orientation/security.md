> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/1-orientation/security.md) es la referencia autorizada.

# El modelo de seguridad

Lee esto antes de publicar nada, y antes de instalar nada.

## La frase clave

**Un plugin es un proceso nativo que se ejecuta con todos los privilegios de
tu cuenta de usuario.** Puede leer tus archivos, abrir sockets y lanzar
programas. Nada en Astra lo aísla en un sandbox ni lo restringe a nivel de
sistema operativo.

Eso no es una carencia que esta página esté disimulando — es el diseño tal
como está hoy. El aislamiento es la **Fase 7** del plan de producción, se
nombra ahí precisamente para que sea una decisión y no una omisión, y **no
está implementado**. Trabajo candidato, cuando llegue: Landlock + seccomp en
Linux, un token de baja integridad o AppContainer en Windows, rlimits. Hasta
entonces, "firmado" y "listado" no dicen nada sobre lo que el proceso puede
hacerle a tu máquina.

En cualquier lugar donde Astra pudiera dar a entender lo contrario, está
*obligado* a decir esto en voz alta — tanto la pantalla de consentimiento de
instalación como el panel de procedencia llevan un aviso permanente de que
una attestation no demuestra que el código sea seguro. El daemon ya lo dice
en el mensaje con el que rechaza una instalación no verificada: *"a plugin
runs as a native process with your full privileges, so an unverified one can
take over your machine"* (`astra-daemon/src/plugins/manager.rs`). Cómo se ven
las propias pantallas de la app es responsabilidad de Astra documentarlo, no
de este repositorio; esta página describe el daemon, la CLI y los formatos.

## Qué responde en realidad cada mecanismo

Cuatro capas, cuatro preguntas distintas. Confundirlas es cómo "está firmado"
se convierte en "es seguro".

| Capa | Mecanismo | Verificado por | Responde |
|---|---|---|---|
| 1. Procedencia de compilación | Attestation de artefacto de GitHub (Sigstore keyless, OIDC) | el bot del registro, en CI | "estos bytes vienen del workflow W en el commit C del repositorio R" |
| 2. Confianza de distribución | Contrafirma Ed25519 sobre el digest del artefacto, en un índice firmado | el daemon, sin conexión | "Astra listó exactamente estos bytes, y no han sido retirados" |
| 3. Continuidad de identidad | un anclaje TOFU de `github:owner/repo` | el daemon, sin conexión | "esta actualización viene del mismo autor que la instalación" |
| 4. Autoridad en tiempo de ejecución | `[permissions]` + `require_permission` en cada RPC del host | el daemon, en cada llamada | "qué puede pedirle este plugin a Astra que haga" |

Ninguno de ellos responde "¿es seguro este código?". Esa pregunta no tiene
una respuesta mecánica, y un sistema que dé a entender lo contrario es peor
que uno que admita que no la tiene.

## Dos cosas que son ciertas hoy y no se van a suavizar

### La cadena de confianza está especificada, implementada, y anclada a un eslabón de distancia

Las claves raíz existen, y la delegación por debajo de ellas ahora también.
**La firma del propio catálogo, no**, así que nada se verifica en la máquina
de un usuario. En concreto
([`spec/registry-index.md` §0.1](../spec/registry-index.md)):

- el `root.json` del registro lleva `"status": "provisioned"` y dos claves
  Ed25519, generadas el 2026-08-11 en una ceremonia fuera de línea;
- `PRODUCTION_ROOT_KEYS` del daemon lista las mismas dos — ese archivo
  existe para que un tercero pueda leerlas sin desensamblar un binario, y
  para que un desacuerdo entre ambas sea visible;
- una clave raíz no firma un catálogo: firma `trust.json`, que delega en una
  clave de firma de índice. **Ese documento ya está firmado.**
  `registry/v1/trust.json` se verifica bajo `astra-root-2026a`, delega en
  `astra-index-2026a` y nombra el único commit del workflow reutilizable que
  el bot del registro aceptará en una attestation de compilación.
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` del propio
  registro imprime todo eso. Así que el bloqueo del lado de ingesta
  `E_TRUST_UNPROVISIONED` ya no se dispara;
- **pero `registry/v1/index.json` todavía lleva `"signatures": []`**, y
  también `revocations.json`. Sin firma en el catálogo, no hay nada que la
  clave delegada pueda comprobar, y todo catálogo se sigue clasificando como
  `UNSIGNED` — con motivo **`NoSignatures`**, no `NoTrustAnchor`: el ancla
  llegó, las firmas no. `NoTrustAnchor` es el caso más antiguo y peor, y
  significa que ningún `trust.json` verificado llegó siquiera a la
  compilación;
- y porque las listas de retirada se verifican de forma estricta, una sin
  firmar se rechaza, así que **la aplicación de revocaciones tampoco está
  activa**.

Una compilación por defecto, por tanto, sigue fallando cerrada (fail
closed). Nada aquí es una promesa sobre una garantía que tengas hoy; el
mecanismo empieza a tener peso para un usuario cuando exista un índice
firmado, y no antes.

### Una clave de firma local no otorga ninguna confianza

`astra-plugin keygen` y `astra-plugin sign` existen. Son un segundo factor
opcional — defensa en profundidad frente a un robo de cuenta de GitHub,
donde el valor está en que la clave vive en un sitio donde una sesión de
GitHub robada no está.

**No** son lo que hace que Astra instale un plugin, y un paquete firmado con
tu propia clave es tan poco fiable (untrusted) como uno sin firmar. El daemon
comprueba el par `SIGNATURE`/`PUBKEY` dentro del ZIP contra una *clave de
publicador de Astra fijada (pinned)*, nunca contra la clave dentro del
archivo. `astra-plugin build` lo dice cada vez que se ejecuta:

<!-- doctest: output from="astra-plugin build ." -->
```
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
```

y `astra-plugin sign` lo dice al tener éxito, deliberadamente no escondido
en `--help`:

<!-- doctest: output from="astra-plugin sign <bundle>" -->
```
This signature is an optional second factor, not a trust signal.

Astra does not verify it against your key — the daemon checks the in-ZIP pair against a
pinned Astra publisher key, so a bundle signed with your own key is untrusted by
construction, exactly as an unsigned one is.
```

El par dentro del ZIP es una característica de formato en retirada; tanto el
comando como las entradas que escribe están previstos para eliminarse.

No existe `astra-plugin login`, y no lo habrá: publicar implica un
repositorio y una etiqueta, así que no hay ninguna credencial que guardar ni
ninguna que pueda filtrarse.

## Qué hace la puerta de permisos

El daemon aplica `[permissions]` en un solo lugar: `require_permission`, en
seis de las diez RPC de `PluginHostService`. Las otras cuatro — `Register`,
`GetPluginSelfConfig`, `PluginLog` y `GetDaemonInfo` — están **siempre
permitidas** y no ejecutan ninguna comprobación de permisos; son `(…, None)`
en la tabla `HOST_RPC_PERMISSIONS` del daemon, y no hay ninguna llamada a
`require_permission` en sus cuerpos. Un plugin registrado con un bloque
`[permissions]` vacío puede llegar a esas cuatro y a nada más. Por qué son
gratuitas está
[en la referencia de permisos](../3-reference/permissions.md#las-cuatro-llamadas-que-no-necesitan-nada).
La tabla que lee `require_permission` — `HOST_RPC_PERMISSIONS` en el daemon —
está anclada a [`spec/hooks.yaml`](../../../spec/hooks.yaml) mediante la
regla de paridad R6, de modo que la
[columna de permisos](../reference/parity.md) generada no puede desviarse
del código que la hace cumplir.

Dos puertas independientes, y ambas deben superarse
([`spec/permissions.md` §4.2](../spec/permissions.md)):

1. **la concesión (grant)** — una respuesta por instalación que produjo una
   pantalla de consentimiento y que guarda un registro de confianza;
2. **el techo (ceiling)** — una regla por procedencia que ningún registro
   puede comprar de más.

El manifiesto es una *solicitud*. Para los niveles 1 y 2, el conjunto
concedido vive donde el plugin no puede escribirlo, porque un plugin que
pudiera ampliar sus propias concesiones editando su propio manifiesto tendría
un sistema de permisos que no es más que un comentario.

**El nivel 3 es la excepción, y es deliberada.** Para un directorio fuente
cargado por sideload, `decide_grants` del daemon devuelve
`declared.capped(|_| true)` — el manifiesto *es* el registro de
consentimiento, leído del propio directorio del plugin en cada carga, sin
techo por encima. Un plugin cargado por sideload puede, por tanto, ampliar
sus propios permisos editando su propio `plugin.toml` entre reinicios, hasta
todo el vocabulario. Esa es una razón más por la que el modo desarrollador es
una herramienta de desarrollo y no una vía de instalación.

Cinco permisos son de alto riesgo y cada uno recibe su propia casilla de
consentimiento: `send_chat_message`, `push_to_ui`, `set_theme_contribution`,
`dom_access`, `client`. `dom_access` recibe una segunda pantalla. Detalles,
incluyendo cómo escribir un `reason` que valga la pena leer:
[permisos](../3-reference/permissions.md).

## La procedencia de un plugin determina su techo

| Nivel | Origen | Techo |
|---|---|---|
| **1 · Registro** | instalado desde la tienda, verificado | todo lo que pidió, sujeto a consentimiento. Sin anulación ante un fallo de verificación |
| **2 · Archivo local** | un `.astraplugin` importado a mano | `send_chat_message`, `set_theme_contribution`, `dom_access` y `client` se **rechazan de plano, no solo se advierten** |
| **3 · Sideload** | un directorio fuente, modo desarrollador activado | **sin techo** — y nunca arranca automáticamente |

El nivel 3 no tiene límite a propósito: es el bucle de creación para plugins
de UI, y limitarlo haría que `dom_access` fuera indesarrollable. También está
bloqueado detrás de un ajuste explícito, nunca arranca solo tras un reinicio,
y está [documentado como herramienta de desarrollo](../5-publish/sideload.md)
en lugar de como una forma de instalar cosas.

Cuatro estados no obtienen **nada**, diga lo que diga el manifiesto:
`Untrusted`, `TamperDetected`, `Revoked`, y un plugin `Verified` cuyo
registro no se puede creer. Un plugin instalado antes de que existieran los
registros de confianza (`Unrecorded`) tiene su manifiesto capado al techo del
nivel 2 — "llegó de algún sitio, no demostró nada" es exactamente esa forma.

## Contra qué no hay defensa

Nombrado, en lugar de dejarlo para que el lector lo descubra:

| Amenaza | Estado |
|---|---|
| Un plugin lee tus archivos, tus claves, tu red | **Sin defensa.** No existe aislamiento — Fase 7 |
| Un plugin lee `daemon.token` y se registra como cliente | **Sin defensa.** Mismo motivo |
| Un registro malicioso o comprometido sirve bytes distintos | Defendido *por diseño* — el índice contrafirma un digest y el daemon vuelve a calcular el hash — **pero no en vigor**: las raíces están aprovisionadas (`registry/v1/root.json`, las mismas dos claves compiladas en el daemon), y el índice del catálogo que firman sigue sin firmar |
| Una versión retirada ya instalada | Especificado; no aplicado hoy, porque una lista de retirada sin firmar se rechaza |
| Otro proceso local que llama al servidor de capabilities de tu plugin | **Defendido.** El daemon presenta el token de arranque en cada llamada y fija `ASTRA_PLUGIN_CAPABILITY_AUTH=require`, de modo que el SDK rechaza una llamada sin él. Bajo un daemon demasiado antiguo para enviar la cabecera, el SDK se queda en `warn` — un token incorrecto se rechaza, uno ausente se acepta — porque no hay otra cosa que pueda hacer |
| Un plugin edita su propio manifiesto para ampliar sus permisos | **Defendido en los niveles 1 y 2** — las concesiones vienen de un registro de confianza que posee el daemon, no del manifiesto. **Sin defensa en el nivel 3**: para un directorio en sideload el manifiesto *es* la concesión y no tiene techo, así que puede adquirir cada permiso del vocabulario editando su propio archivo |
| Un marcador de sideload plantado a mano | Defendido. El daemon rechaza un marcador que no escribió él mismo |

## Para usuarios, en un párrafo

Instala desde dentro de Astra. La vía de la tienda fija el artefacto por
digest, y los fallos de verificación son bloqueos duros sin anulación. Si
alguien te envía un archivo `.astraplugin`, importarlo es una decisión que
estás tomando sobre esa persona, y cuatro permisos se rechazarán sea lo que
sea que pida el archivo. Si alguien te dice que actives el modo desarrollador
y apuntes Astra a una carpeta, te está pidiendo que ejecutes código sin
firmar con tu propia cuenta.

## Ver también

- [`spec/registry-index.md`](../spec/registry-index.md) — los formatos de documento y el algoritmo de verificación, de forma normativa
- [`spec/permissions.md`](../spec/permissions.md) — concesiones, techos, consentimiento, `permissions_hash`
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — qué hay dentro de un `.astraplugin` y qué debe rechazar un verificador
- [Solución de problemas](../6-operate/troubleshooting.md) — qué significa cada fallo de verificación cuando te encuentras con uno
</content>
