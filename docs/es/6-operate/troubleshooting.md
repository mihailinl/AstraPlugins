> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/6-operate/troubleshooting.md) es la referencia autorizada.

# Solución de problemas

Organizado según los strings que realmente imprimen la CLI y el daemon.
Si tienes un error delante, busca en esta página un fragmento de él.

## Empieza aquí

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

Quince comprobaciones, cada una formulada como la pregunta que responde.
Sabe qué CLI estás ejecutando, qué directorio de config resolvió, si el
daemon es alcanzable, qué toolchains tienes, si tu manifiesto se analiza
correctamente, si el punto de entrada existe, si tus permisos cubren tus
capabilities, si tu bloque `[platform]` es correcto, y si tu workflow de
release está fijado (pinned). Cada fallo lleva una línea `fix:`. En un
proyecto que aún no has compilado, termina con salida distinta de cero
en una de ellas — "Will the daemon find something to start? … does not
exist" — lo cual es correcto: todavía nadie ha producido el binario.

## El proyecto no resuelve su SDK

**`error: failed to select a version for the requirement astra-plugin-sdk = "^0.6"`**
**`ERROR: No matching distribution found for astra-plugin-sdk<0.6,>=0.5`**
**`error: No version matching "^0.5.0" found for specifier "astra-plugin-sdk" (but package exists)`**

Tres lenguajes, una misma forma de error — y la ausencia del SDK ya no es su
causa. `astra-plugin new` fija `astra-plugin-sdk` `0.6` para Rust,
`>=0.5,<0.6` para Python y `^0.5.0` para TypeScript, y los registros públicos
llevan crates.io **0.6.0**, PyPI **0.5.0** y npm **0.5.0**. Cada uno de esos
fijados resuelve en un proyecto nuevo sin configurar nada, así que si el tuyo
no resuelve, la causa está entre tu máquina y el registro:

- **Un índice obsoleto, un lockfile, o un mirror que no se ha sincronizado.**
  El resolutor está respondiendo desde una vista cacheada del registro anterior
  al release, o desde un proxy corporativo que hace lo mismo.
  `cargo update -p astra-plugin-sdk`;
  `pip install --upgrade --no-cache-dir -r requirements.txt`; para npm, borra
  `node_modules` y el lockfile e instala de nuevo. `cargo --offline` y
  `npm --offline` producen este error por diseño.
- **Alguien relajó un límite.** Un fijado editado a `0.5` (Rust) o `0.4`
  (Python, TypeScript) pide algo que ningún registro ofrece bajo esa
  restricción. Devuelve el fijado del scaffold en lugar de ensancharlo más:
  0.6 es el primer release de Rust cuyo `HostClient` adjunta
  `x-session-token`, así que un SDK más antiguo cambia este error por
  `unauthenticated` en cada llamada al host — la sección de abajo.

Ni `doctor` ni `check` mencionan nada de esto, porque ambos leen
`plugin.toml` y el fijado vive en el archivo de compilación del propio
lenguaje.

## El plugin no arranca

**`Could not read /…/astra/daemon.token. Astra does not look like it is running — start the app first.`**
Exactamente lo que dice. `dev`, `logs` e instalar necesitan un Astra en
ejecución; `new`, `build`, `check`, `test`, `sign` y `publish` no. Si
Astra *sí* está corriendo, resolvió un directorio de config distinto al
de la CLI — compara la ruta que imprime `doctor` con la que muestra
Astra en sus ajustes.

**El daemon recogió el proceso al arrancar.** El presupuesto es
`plugin_start_timeout_secs` = **20 s** hasta la primera línea de salida.
Un plugin de Python que importa una pila de ML grande en el ámbito del
módulo puede no llegar a tiempo; importa de forma perezosa dentro del
hook que lo necesite. `astra-plugin test` mide esto e imprime el número:

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
```

**El plugin arranca y muere de inmediato.** Comprueba primero
`astra-plugin logs -f`; si ahí no hay nada en absoluto, el proceso está
fallando antes de que el SDK instale su logging. Ejecuta el binario a
mano — `astra-plugin dev --standalone` hace eso y te dice qué no puede
hacer de esa forma.

**Los errores de `HealthCheck` marcan el plugin como muerto.** Se
ejecuta cada 15 s y no pasa por el helper de hook opcional del daemon:
*cualquier* error, `UNIMPLEMENTED` incluido, significa muerto. Si
sobrescribiste `health_check`, asegúrate de que no pueda lanzar
excepciones.

## Una llamada al host vuelve como `permission_denied`

El mensaje nombra el permiso y de dónde vino el conjunto concedido. Tres
causas, en orden de probabilidad:

1. **No lo declaraste.** `[permissions]` es de denegación por defecto.
   Declarar `[capabilities] event_handlers = true` no compra
   `SubscribeEvents`; `[permissions] subscribe_events` sí.
2. **El usuario no lo concedió**, o la vía de instalación lo capó. Un
   [archivo importado localmente](../5-publish/local-install.md) tiene
   `send_chat_message`, `set_theme_contribution`, `dom_access` y
   `client` rechazados de plano.
3. **Estás desconectado o la app está bloqueada.** Astra rechaza los
   RPC de plugins en ambos estados, y la CLI lo dice: *"Astra refuses
   plugin RPCs while signed out or locked — sign in and unlock the app,
   then try again."*

`astra-plugin doctor` responde al punto 1 sin ejecutar nada:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## Una llamada al host vuelve como `unauthenticated`

Cada llamada de `PluginHostService` salvo `Register` debe llevar el
token de sesión en `x-session-token`. Los tres SDK lo adjuntan — **desde
0.6 en Rust, 0.5 en Python y TypeScript**. Contra un SDK más antiguo,
cada llamada al host falla de esta forma, por lo que el límite de
dependencia del scaffold no baja más.

`astra-plugin test` lo verifica de extremo a extremo:

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`
```

## Se rechaza el sideload

**`Sideloading is disabled.`** `safety.allow_unsigned_plugins` está
desactivado. Lee [qué cuesta activarlo](../5-publish/sideload.md) antes
de hacerlo.

**`Refusing sideload marker in …: this daemon never authorised a sideload of …`**
Alguien plantó a mano un `sideload.json`. Eso no funciona desde que el
daemon empezó a llevar su propio registro de lo que autorizó. Usa
`astra-plugin dev`.

## Se rechaza una instalación

Cada fallo de verificación en la vía del registro es un **bloqueo duro
sin anulación**, y cada uno nombra cuál de dos cosas ocurrió.

| Lo que ves | Lo que significa |
|---|---|
| El archivo descargado no coincide con lo que firmó el registro | `DIGEST_MISMATCH` — la descarga se descartó. Repórtalo |
| Astra no pudo verificar la firma del catálogo de plugins | `SIGNATURE_INVALID` — la tienda se deshabilita en lugar de recurrir a datos sin verificar |
| Esta actualización viene de un repositorio distinto al que instalaste | `IDENTITY_CHANGED` — nunca hay anulación. Solo una desinstalación borra el fijado |
| El plugin fue retirado | `REVOKED` — con el aviso y desinstalación de un clic. Los archivos nunca se borran en silencio |
| Este paquete es para otra plataforma | `PLATFORM_UNSUPPORTED` |
| Este plugin necesita un Astra más nuevo | `PROTOCOL_UNSUPPORTED` |
| Red, o tu reloj está mal | Reintentable, y redactado como tal. Esto nunca debe parecer un fallo de verificación |

**`nothing here vouches for these bytes`** en un archivo local:
instálalo desde la página de Plugins en su lugar, o lee
[instalación local](../5-publish/local-install.md) para saber qué cuesta
importarlo.

Hoy la cadena de confianza está anclada **un eslabón corta**: las claves
raíz existen y el `trust.json` firmado por la raíz que delega una clave
de firma de índice también existe ya, pero `registry/v1/index.json` y
`revocations.json` todavía llevan `"signatures": []`. Sin firma en el
catálogo, no hay nada que la clave delegada pueda comprobar, así que un
catálogo se clasifica como sin firmar y la revocación no se aplica.
Consulta [`spec/registry-index.md` §0.1](../spec/registry-index.md).

## Una llamada a un tool falla de una forma que el modelo no puede arreglar

Usa el código correcto; eso es lo que lee el modelo.

| Código | Di esto cuando |
|---|---|
| `BAD_ARGUMENTS` | Reintentar con argumentos distintos podría funcionar |
| `NOT_CONFIGURED` | Falta un ajuste — **y establece `config_field`**, que es lo que convierte el error en un enlace a esa entrada exacta |
| `UNAUTHORIZED` | Hay un valor presente y se rechazó. Distinto de `NOT_CONFIGURED` |
| `RATE_LIMITED` | Con `retry_after_ms` cuando el upstream indicó uno |
| `UNAVAILABLE` / `TIMEOUT` | Transitorio. Una llamada idéntica posterior podría funcionar |
| `INTERNAL` | Un bug. Nada sobre lo que el modelo pueda actuar |

`UNIMPLEMENTED` **no** es un error: significa "este hook no existe", y el
daemon lo interpreta así. Devolverlo porque tu TTS falló hace que el
daemon crea que no tienes TTS. Taxonomía completa:
[`reference/errors.md`](../reference/errors.md).

## `astra-plugin check` se queja

**`config.schema is not valid JSON`** o **`should have "type": "object" at
root`** — el formulario de ajustes se genera a partir de ese schema.

**Una clave desconocida en `[capabilities]` hace fallar todo el
manifiesto.** Esa sección es el único lugar donde se rechazan claves
desconocidas, porque cada clave es un booleano de opt-in y una errata,
si no, se leería exactamente como `false`. `ui_panels` es el clásico: se
llama `ui_contributions`, y tres ejemplos incluidos en el repositorio no
declararon nada en absoluto durante meses por eso.

**Un id desconocido de `[permissions]` se conserva y se avisa**, no se
rechaza — los ids nuevos llegan con nuevas versiones de Astra, y el
bloque de permisos lo hashean byte a byte tres implementaciones, así que
descartar una clave las haría discrepar sobre qué se firmó.

`astra-plugin check --fix` aplica lo que puede demostrar y reporta el
resto.

## La CLI no imprime nada útil

`RUST_LOG` funciona ahora — estuvo documentado desde 0.1 e inerte hasta
que se instaló un subscriber:

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

El trace va a **stderr**, así que `--json` en stdout se mantiene como un
único documento limpio.

## Códigos de salida

| | |
|---|---|
| `0` | éxito |
| `1` | el plugin o el paquete está mal |
| `2` | la CLI no pudo ejecutar la comprobación — un archivo faltante, una toolchain faltante |

La separación es estructural: un workflow de release que trata igual
"el paquete está mal" y "no pude mirar" termina enviando uno de los dos.

## ¿Sigues atascado?

- [Logs](logs.md) — dónde están, por sistema operativo
- [Rendimiento](performance.md) — tiempos de espera y los números detrás de ellos
- [Ejemplos](../7-examples/README.md) — once plugins funcionando, varios de los cuales ejercitan la ruta que estás depurando
</content>
