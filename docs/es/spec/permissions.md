> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/spec/permissions.md) es la referencia autorizada.

# Permisos — especificación normativa

**Estado:** normativo. El vocabulario, la puerta, los techos, las
cuatro vías de procedencia y el hash están todos implementados y
aplicados; donde algo está especificado pero todavía no aplicado, este
documento lo dice en la fila correspondiente.

Las palabras de requisito siguen RFC 2119.

Existen dos secciones ortogonales en `plugin.toml`, y confundirlas es
exactamente el bug que este vocabulario se creó para arreglar:

|sección|dirección|pregunta|
|---|---|---|
| `[capabilities]` | daemon → plugin | *¿qué implemento, a lo que Astra puede llamar hacia dentro?* |
| `[permissions]` | plugin → daemon | *¿a qué puedo llamar hacia fuera, y qué superficies se me pueden entregar?* |

Eran una sola palabra para dos cosas, y la palabra significaba la
primera — así fue como `dom_access` llegó a ser una capability que un
plugin se concedía a sí mismo con solo declararla.

---

## 1. El vocabulario

Ocho ids, un conjunto cerrado (`astra-plugin-manifest/src/permissions.rs`,
`PERMISSION_NAMES`, anclado al enum mediante una prueba). El registro
valida los ids de un listado contra esta lista, y la tabla de etiquetas
localizadas de Astra está indexada por ella, así que un id añadido en
un sitio y no en los otros se renderiza como una fila en blanco.

| id | bloquea | qué otorga | alto riesgo |
|---|---|---|---|
| `fire_trigger` | `PluginHostService.FireTrigger` | ejecutar las automatizaciones guardadas del usuario | |
| `subscribe_events` | `SubscribeEvents` | recibir eventos del daemon, **restringido a los tipos declarados** (§1.1) | |
| `set_variable` | `SetVariable` | escribir en el contexto de variables del daemon, con espacio de nombres del plugin que llama | |
| `send_chat_message` | `SendChatMessage` | impulsar un turno de IA — gastar los tokens del usuario, hablar con la voz de su asistente | ● |
| `push_to_ui` | `PushToUi` | enviar un evento a la ventana de Astra | ● |
| `set_theme_contribution` | `SetThemeContribution` | cambiar el estilo de toda la app | ● |
| `dom_access` | *sin RPC* — una **superficie** | ejecutar el propio script del plugin dentro de la ventana de Astra, con acceso a las conversaciones del usuario y a la interfaz de cualquier otro plugin | ● |
| `client` | *sin RPC* — una **superficie** | actuar como frontend cliente: su propia superficie de chat, su propia sesión | ● |

**Los cinco marcados con ● son de alto riesgo** (`HIGH_RISK_PERMISSIONS`)
y cada uno recibe su propia casilla de consentimiento. El §4.3 del plan
detalla cuatro casillas y omite `push_to_ui`; el §5.6 lista cinco. La
implementación toma la **unión**, porque el desacuerdo es entre un
párrafo de UI y la sección de seguridad, y una casilla de más cuesta un
clic mientras que una de menos cuesta la propiedad.

**`dom_access` y `client` no bloquean ningún RPC**, precisamente por
eso necesitan un segundo punto de aplicación: se aplican donde se
entrega la *superficie* (§4.2), no donde se responde una llamada.

### 1.1 Argumentos de permiso

Una entrada de `[permissions]` es un objeto, no un booleano:

```toml
[permissions]
fire_trigger     = { reason = "Fires the on_dice_roll trigger you configure" }
subscribe_events = { types = ["command_completed"], reason = "Reacts when a command finishes" }
set_variable     = { scopes = ["plugin"] }
```

| miembro | tipo | significado |
|---|---|---|
| `reason` | string, ≤ 140 caracteres | las propias palabras del autor (§6) |
| `types` | array de string | **solo `subscribe_events`.** La lista blanca de tipos de evento |
| `scopes` | array de string | **solo `set_variable`.** `plugin` / `session` / `persistent`. **Reservado** — el daemon da hoy espacio de nombres a cada escritura de plugin por id de plugin, así que esto todavía no acota nada. Se analiza para que un manifiesto que lo declare sea publicable y hashee idéntico en todas partes |

**`subscribe_events.types` es una lista blanca que el daemon aplica por
evento, y una vacía no permite nada.** Tres estados, y el del medio es
todo el propósito:

* permiso ausente → ningún stream en absoluto;
* permiso concedido, `types` vacío → **no permite nada**; el daemon
  rechaza la suscripción con un mensaje que nombra la solución, en
  lugar de devolver un stream que calla para siempre;
* `types` listado → exactamente esos valores de
  `AstraEvent::event_type_str()`.

La lectura intuitiva — "sin filtro significa todo" — es exactamente el
agujero que este permiso existe para cerrar: un suscriptor sin filtro
recibe `speech_recognized`, que es cada palabra que dice el usuario.

### 1.2 Los ids desconocidos se conservan, no se rechazan

Un manifiesto que nombra un id que este build nunca ha oído se
**acepta**. Dos razones, y ambas apuntan en la misma dirección:

1. **Compatibilidad hacia adelante.** Los ids nuevos llegan con nuevas
   versiones de Astra. Un daemon que rechazara un id desconocido
   convertiría cada adición en un día de corte para cada daemon más
   antiguo.
2. **El hash.** `permissions_hash` (§5) se calcula sobre estos bytes
   por tres implementaciones. Descartar una clave que el lector no
   reconoció haría que dos de ellas discreparan sobre qué se firmó.

Un id desconocido es **inerte** — denegación por defecto significa que
nunca concede nada — y no es silencioso. La pantalla de consentimiento
lo renderiza a través de su etiqueta `permission.unrecognised` en lugar
de descartarlo, así que se le dice a un usuario que el plugin pide algo
que esta versión de Astra no conoce. `Permissions::unknown()` existe
para que el tooling pueda enumerarlos; **`astra-plugin check` no lo
hace hoy** — reporta que hay una sección `[permissions]` presente y se
detiene ahí.

(`[capabilities]`, en cambio, es `deny_unknown_fields`: es un conjunto
cerrado de booleanos donde una errata se lee exactamente como `false`.)

## 2. Denegación por defecto, y los cuatro RPC que no necesitan nada

**Una sección `[permissions]` ausente no concede ningún RPC del host
más allá del conjunto siempre permitido.** Una sección faltante no es
"sin especificar"; es una respuesta completa, y la respuesta es no.

El conjunto siempre permitido tiene cuatro miembros, y está escrito
como una tabla (`HOST_RPC_PERMISSIONS` en `host_service.rs`) que dos
canarios comprueban contra cada RPC, así que un RPC nuevo sin
condicionar es un fallo de prueba en lugar de una omisión silenciosa:

| RPC | permiso |
|---|---|
| `Register` | — |
| `PluginLog` | — |
| `GetPluginSelfConfig` | — |
| `GetDaemonInfo` | — |
| `SubscribeEvents` | `subscribe_events` |
| `SendChatMessage` | `send_chat_message` |
| `FireTrigger` | `fire_trigger` |
| `SetVariable` | `set_variable` |
| `SetThemeContribution` | `set_theme_contribution` |
| `PushToUi` | `push_to_ui` |

`GetDaemonInfo` es la única adición a la lista de tres del plan, y es
una decisión y no una omisión: devuelve `version`, `state`,
`grpc_port` y `language`, todo lo cual `PluginRegisterResponse` ya le
había entregado al llamador, así que no revela nada nuevo. Inventar un
id de permiso para ella pondría delante del usuario una casilla que no
protege nada, y las casillas que no protegen nada son cómo los usuarios
aprenden a marcar casillas.

**`client_session_token` se emite a cada plugin.** El token es
*autenticación* (quién llama), no *autorización* (qué puede hacer).
Negárselo a los plugins que no son `client` denegaría `PluginLog`,
`GetPluginSelfConfig`, `SubscribeEvents` y `FireTrigger` — el conjunto
siempre permitido — y rompería cada plugin y ambos sidecars del
propio repositorio. La puerta de `client` pertenece al techo y a las
superficies específicas, no al token.

## 3. Declarar es pedir; conceder es un objeto distinto

**Nada en un `plugin.toml` es una concesión.** Un bloque
`[permissions]` es la *solicitud* del autor. El **conjunto concedido**
es un objeto separado que el daemon resuelve por vía de procedencia y
guarda donde el plugin no puede alcanzarlo —
`<base_dir>/registry/records/<id>.json`, hermano del árbol de plugins
y nunca hijo de él, con MAC mediante una clave que posee el daemon.

La aplicación lee el conjunto concedido y nunca el manifiesto — la
forma de la llamada al principio de cada RPC bloqueado (extracto
ilustrativo de `host_service.rs`, no una muestra ejecutable):

```rust
let (plugin_id, grants) =
    self.require_permission(&request, Permission::FireTrigger, "FireTrigger").await?;
```

Un plugin que pudiera ampliar sus propias concesiones editando su
propio manifiesto tendría un sistema de permisos que no es más que un
comentario. Eso era literalmente cierto antes de la Fase 4:
`[capabilities] dom_access = true` — una línea en un archivo dentro del
propio directorio del plugin — se copiaba directamente a la
contribución de UI que el renderizador honra cargando el script del
plugin en la propia ventana de Astra.

**Por qué el registro no está en el directorio del plugin.** El plugin
se ejecuta como el usuario, con `current_dir` fijado a su directorio de
instalación. El modo 0600 protege contra otros usuarios, no contra el
propio sujeto. Un registro que el sujeto pueda escribir le permite a un
plugin malicioso concederse `dom_access` a sí mismo, sobrescribir el
anclaje TOFU, reescribir `artifact_sha256` para evadir la revocación
basada en digest, y reescribir los hashes por archivo para que la
reverificación al arrancar pase.

### 3.1 El puente de capability

`dom_access` y `client` son a la vez booleanos de `[capabilities]` **y**
ids de permiso. Todo plugin escrito antes de la separación dice lo que
quiere en el lugar antiguo — incluidos `companion`, `doom` y
`bad-apple`, ninguno de los cuales declara sección `[permissions]` en
absoluto.

Así que un bit `[capabilities] dom_access = true` se lee como **una
solicitud**, exactamente igual que una entrada de `[permissions]`, y
recibe exactamente la misma respuesta de la misma tabla
(`declared_permissions()`). El puente deliberadamente *no* es "el bit
de capability concede el permiso": pone el bit donde vive una
solicitud, así que hay una sola respuesta a "¿puede?" y no dos.

Consecuencia para los autores: **un plugin publicado a través del
registro debe declarar `[permissions] dom_access`**, porque una
instalación desde el registro concede a partir de su registro de
confianza, que se escribe desde el bloque `[permissions]` del
`MANIFEST.json` del paquete — y esa entrada es lo que renderiza la
pantalla de consentimiento y marca el usuario.

## 4. De dónde viene el conjunto concedido

### 4.1 Las cuatro vías de procedencia

`decide_grants()` es esta tabla como una función pura.

| vía | conjunto concedido |
|---|---|
| **Sidecar integrado** (`builtin_stt`, `builtin_vox`) | un conjunto **declarado en código** junto al `build_manifest()` de ese sidecar. Sin registro de confianza, sin lectura de disco — un sidecar no tiene registro *por diseño*, así que una ruta de código que buscara uno sería una ruta de código que podría fallar por eso |
| **Instalación desde el registro** | el registro de confianza escrito al instalar: `MANIFEST.permissions` del paquete, tras la comprobación de consentimiento, capado por el techo del nivel |
| **`ImportPluginFile`** (un `.astraplugin` fuera del registro) | un registro de confianza en `tier: "local-unverified"` — el conjunto declarado del manifiesto, **capado por el techo del nivel 2** |
| **Sideload** (un directorio fuente, modo desarrollador) | un registro de confianza en `tier: "sideloaded"` — el conjunto declarado del manifiesto, **sin capar** |

Cuatro ramas *no* están en esa tabla y son igualmente normativas:

| estado | concedido |
|---|---|
| `Untrusted` — se esperaba un registro y no se puede creer | **nada** |
| `TamperDetected` — un archivo ya no coincide con el digest registrado para él | **nada** |
| `Revoked` — una lista de retirada firmada lo cubre | **nada** |
| `Unrecorded` — instalado antes de que existieran los registros de confianza, sin ningún registro | el conjunto declarado del manifiesto, **capado por el techo del nivel 2** |

`Untrusted` todavía puede arrancarse a mano, y cuando eso ocurre, corre
sin concesiones: "el usuario lo pidió" no es evidencia sobre los bytes.
`Unrecorded` se capa en lugar de rechazarse porque no concederle nada a
esos plugins rompería instalaciones que funcionan al actualizar, sin
forma de que el usuario lo arregle, y concederles su manifiesto sin
capar le permitiría a cualquiera de ellos concederse `dom_access` a sí
mismo editando un archivo en su propio directorio. El techo del nivel 2
es exactamente la forma de "llegó de algún sitio, no demostró nada".

Un plugin `Verified` sin ningún registro creíble no obtiene **nada**:
`Verified` *significa* un registro creíble, y la respuesta a la
combinación imposible no es recurrir al manifiesto.

Cada denegación nombra su fuente (`GrantSource::describe`) — "denegado"
sin "y aquí está la fuente que no tenía nada que decir al respecto" es
el modo de fallo que hace que se revierta un sistema de permisos.

### 4.2 Dos puertas, no una

Un permiso se honra solo cuando se cumplen **ambas**:

1. la **concesión** — una respuesta por instalación que produjo una
   pantalla de consentimiento y que guarda un registro de confianza;
2. el **techo** — una regla por procedencia que ningún registro puede
   comprar de más.

`require_permission` pregunta la primera para las seis RPC del host
que bloquea un permiso — `SubscribeEvents`, `SendChatMessage`,
`FireTrigger`, `SetVariable`, `SetThemeContribution`, `PushToUi`. Las
cuatro restantes (`Register`, `GetPluginSelfConfig`, `PluginLog`,
`GetDaemonInfo`) llevan `None` en `HOST_RPC_PERMISSIONS` y siempre
están permitidas; el §2 tiene la tabla y el razonamiento.
`ceiling_admits` pregunta la segunda en cualquier lugar donde se
entrega una *superficie* — `PluginStatusMsg`, la respuesta de
contribuciones de UI, la respuesta de temas activos — así que el
renderizador nunca recibe un valor que pudiera honrar. Un plugin
ausente del mapa de concesiones se rechaza: "no se resolvió nada sobre
él" no es razón para servirle la superficie de mayor riesgo del
sistema.

## 5. Techos por nivel

| nivel | fuente | techo |
|---|---|---|
| **1 · Registro** | verificado según el algoritmo de instalación | **todo**, sujeto a consentimiento. Sin anulación ante un fallo |
| **2 · Archivo local** (`ImportPluginFile`) | un `.astraplugin` recibido fuera del registro | `send_chat_message`, `set_theme_contribution`, `dom_access` y `client` se **rechazan de plano, no solo se advierten** |
| **3 · Sideload** | un directorio fuente al que el usuario apuntó un diálogo de archivos, modo desarrollador activado | **ninguno** — y **nunca arranca automáticamente**: el modo desarrollador es obligatorio al cargar y un reinicio lo deja detenido hasta que el usuario lo arranca de nuevo |

El nivel de sideload se muestra al usuario como
`provenance.tier.sideloaded` ("cargado desde una carpeta") en el panel
de procedencia. El plan también pide una insignia permanente, no
descartable, de "DEVELOPER — unverified code from a local directory"
en la tarjeta y en el marco de la ventana para `dom_access`; **esa
insignia no está hoy en la interfaz**, y este documento no lo afirma.

**La promoción del nivel 2 no está implementada.** El plan describe
promover un archivo importado al nivel 1 cuando su digest aparece en
un índice nuevo y se cumplen los pisos de versión; hoy
`import_plugin_file` no pasa ningún release verificado a la vía de
instalación, así que un paquete importado es **siempre**
`local-unverified`, diga lo que diga el índice sobre su digest. No le
digas a un autor que publicar levantará retroactivamente el techo de un
archivo que le envió a alguien por correo.

La lista de rechazo del nivel 2 es `TIER2_REFUSED_PERMISSIONS` —
deliberadamente **no** la misma lista que `HIGH_RISK_PERMISSIONS`:
`push_to_ui` vale una casilla y no vale la pena rechazar un archivo que
el usuario eligió importar. Los cuatro están citados del §5.5, no
inferidos.

**El nivel 3 no es el nivel 2 con una insignia más bonita.** La
separación es por *intención*, no por estado de verificación. Un
usuario que apuntó un diálogo de archivos a un directorio en su propio
disco ha dado una señal más fuerte que un archivo sin verificar que
llegó de otro sitio — y `companion`, `doom` y `bad-apple`, los propios
ejemplos insignia de este proyecto, todos necesitan la vía DOM que el
nivel 2 rechaza. Limitar el nivel 3 haría imposible `astra-plugin dev`.

Los ids desconocidos se descartan en cada techo (`capped()` filtra por
`Permission::from_id(id).is_some_and(keep)`): un techo que dejara pasar
los ids que no pudiera clasificar sería un techo con un agujero con la
forma del próximo release.

**La regla de diseño, mantenida en todas partes:** *lo único que puede
comprar una anulación del usuario es el derecho a ejecutar código de
una fuente que Astra no ha revisado. Nunca puede comprar un permiso
que un plugin verificado habría tenido que pedir.*

## 6. Consentimiento

La pantalla de consentimiento se renderiza **antes de cualquier
descarga**, a partir del campo `permissions` del registro del catálogo
— que el registro copió del bloque `[permissions]` del `MANIFEST.json`
del paquete en la ingesta.

* Cada id se renderiza a través de la **propia tabla de etiquetas
  localizadas de Astra**. El `reason` del autor es subordinado:
  entrecomillado, texto plano, ≤ 140 caracteres, siempre precedido de
  "The author says:". Nunca es la etiqueta misma — las correcciones de
  redacción se distribuyen con Astra y no deben poder redactarse desde
  un listado.
* Cada permiso de alto riesgo recibe su **propia casilla**;
  `dom_access` recibe una segunda pantalla.
* La respuesta viaja hacia la instalación como un **techo, no una
  solicitud** (`InstallOptions::consent`): la instalación se rechaza
  con `PERMISSIONS_NOT_CONSENTED` si el *paquete* pide algo que la
  pantalla no mostró. Las dos listas vienen de lugares distintos — la
  pantalla renderiza el registro del catálogo, el registro de confianza
  concede a partir del propio manifiesto del paquete — y nada más las
  hace coincidir. Un listado que no declara nada mientras distribuye
  un paquete que pide `dom_access` es el caso del "registro malicioso"
  apuntado directamente a la pantalla de consentimiento.
* `consent: None` — la instalación unaria, una importación, una
  prueba, una adopción — conserva el comportamiento previo al
  consentimiento: conceder el conjunto declarado del paquete, capado
  por nivel.

**Actualizaciones.** Una versión que pide un permiso que la versión
instalada no tenía concedido se rechaza con `PERMISSIONS_WIDENED` y se
convierte en un aviso de revisión; la aprobación explícita del usuario
es lo que la convierte en una instalación. La comparación es **por
nombre de permiso, nunca por el objeto de solicitud completo**: un
autor que mejora la redacción de un `reason` no ha ampliado nada, y una
puerta de actualización que tratara eso como una ampliación entrenaría
a los usuarios a hacer clic sin mirar en el único diálogo que importa.

**La retirada surte efecto de inmediato.** Ante cualquier cambio en
`granted_permissions`, ante el rechazo del consentimiento, y ante la
revocación, el daemon descarta la suscripción del lado del servidor e
invalida el token de sesión, así que un stream de eventos en vivo no
puede sobrevivir a un estrechamiento. Al plugin se le informa cuál de
esos ocurrió mediante el trailer `x-astra-teardown-reason`
(`grants_changed`, `consent_declined`, `revoked`, `trust_lost`,
`disabled`, `uninstalled`, `re_registered`) — un token estable, así que
un SDK nunca tiene que analizar inglés para saber si reintentar es
inútil.

### 6.1 Escribir un buen `reason`

Se muestra a un usuario que está decidiendo. **DEBE** tener ≤ 140
caracteres y **DEBERÍA**:

* nombrar la **funcionalidad que el usuario reconoce**, no la API —
  *"Fires the on_dice_roll trigger you configure"*, no *"calls
  FireTrigger"*;
* decir **cuándo**, si no es siempre — *"only while a recording is in
  progress"*;
* evitar repetir la propia etiqueta del permiso; Astra ya la renderiza;
* evitar urgencia, amenazas o instrucciones al usuario. El generador
  rechaza texto que contenga overrides bidi o joiners de ancho cero en
  cualquier lugar donde se muestre tal cual, y una pantalla de
  consentimiento es el último lugar para hacer una excepción.

Un permiso sin un reason plausible es un permiso que hay que eliminar
del manifiesto — nada lo comprueba automáticamente, y un revisor que
lea el listado es la única red de seguridad.

## 7. `permissions_hash`

```
permissions_hash = "sha256:" ‖ lowercase_hex( SHA256( JCS(permissions) ) )
```

* `JCS` es JSON canónico según RFC 8785 — claves ordenadas por unidad
  de código UTF-16, compacto. Consulta
  [`registry-index.md` §3](registry-index.md#3-canonicalización-perfil-jcs)
  para el perfil que implementan ambos repositorios.
* **`null` y `{}` son el mismo valor** y hashean igual, así que un
  productor que omite el miembro y uno que escribe un objeto vacío
  coinciden:
  `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`.
* **Los miembros vacíos se omiten, no se emiten vacíos.**
  `set_variable = {}` es `{}`, nunca `{"reason":""}`. Dos ortografías
  canónicas de una declaración son exactamente la desviación que este
  hash existe para prevenir.
* El prefijo `sha256:` es parte del valor, porque cruza un límite de
  repositorio.

Tres implementaciones lo calculan y las tres se comparan: el
empaquetador de `astra-plugin` lo escribe en `MANIFEST.json`; el bot
del registro lo vuelve a derivar en la ingesta y rechaza una
discrepancia (`E_PERMISSIONS_HASH_MISMATCH`); el daemon lo vuelve a
derivar antes de creer el manifiesto y bloquea la instalación
(`PERMISSIONS_HASH_MISMATCH`). Vectores dorados: `ok-permissions` (un
mapa correcto no vacío) y `permissions-hash-mismatch` — consulta
[`bundle-v2.md` §10](bundle-v2.md#10-permissions-y-permissions_hash)
y la divergencia F5, que afecta únicamente al lector de la CLI.

El hash también se registra en el registro de confianza y se vuelve a
comprobar en el descubrimiento, así que un `plugin.toml` editado en su
sitio después de instalar se detecta en lugar de obedecerse.

## 8. Lo que los permisos no son

`[permissions]` responde *qué hará el daemon por un plugin*. No
responde *qué puede hacerle el proceso a la máquina*.

Un plugin es un proceso nativo, iniciado por el daemon, que se ejecuta
como el usuario con todos sus privilegios. Puede leer los archivos del
usuario, abrir sockets y — hoy — leer el propio token del daemon desde
disco. **No hay sandbox.** El aislamiento (Landlock/seccomp, un
AppContainer o token de baja integridad en Windows, rlimits) está
delimitado como trabajo futuro y explícitamente no está en este
release.

Dos consecuencias a las que este documento obliga a todo consumidor:

* **La UI de Astra nunca debe dar a entender un sandbox.** El bloque
  "does not prove" del panel de procedencia y la línea de la pantalla
  de consentimiento existen exactamente por esto.
* **Una denegación de permiso es un límite real solo para la propia
  autoridad del daemon** — las automatizaciones, el turno de chat, el
  tema, la ventana. Para todo lo demás es una alarma, no una cárcel.

Ser honesto aquí no es una salvedad añadida al final. Un modelo de
permisos que se describe como un sandbox es un modelo de permisos cuyos
usuarios toman decisiones peores que las que tomarían sin ningún
modelo en absoluto.

---

*Fuentes comprobadas al escribir este documento:
`Astra/astra-rs/astra-plugin-manifest/src/permissions.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/host_service.rs`
(`HOST_RPC_PERMISSIONS`, `decide_grants`, `ceiling_for`, `declared_permissions`,
`resolve_grants`, `TeardownReason`);
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs` (`InstallOptions::consent`,
`ceiling_admits`, `granted_and_admitted`, `UpdateGate`, `block_codes`);
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs` (`permissions_hash`,
`permission_names`, `Tier`, `TrustRecord`);
`astra-plugin-cli/src/bundle.rs` (`canonical_permissions`, `permissions_hash`);
`astra-registry/schema/version-v1.json`; `astra-registry/bot/lib/bundle.mjs`;
`testdata/bundles/vectors.json`.*
</content>
