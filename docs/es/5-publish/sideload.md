> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/5-publish/sideload.md) es la referencia autorizada.

# Sideload — una herramienta de desarrollo

> **Así no se instala un plugin.** El sideload apunta Astra a un
> directorio fuente en tu disco y lo ejecuta, sin firmar, como un proceso
> nativo con todos los privilegios de tu cuenta de usuario. Existe para
> que puedas desarrollar un plugin. Está detrás de una activación
> explícita, y esa activación baja el listón para **cada** plugin de la
> máquina, no solo el tuyo.
>
> Los usuarios instalan desde dentro de Astra. Los autores publican con
> [`init-ci` y una etiqueta](release-with-ci.md) y luego
> [consiguen el listado una vez](get-listed.md) —
> [todo el recorrido en una página](../publishing.md).
>
> Decirle a alguien que clone tu repositorio y lo cargue por sideload no
> es publicar. Le pide que ejecute código sin firmar como él mismo, y
> alcanza exactamente a las personas con las que puedes hablar.

Nunca cargues por sideload un plugin que no hayas escrito o auditado tú.
Si alguien te envía un directorio e instrucciones para activar el modo
desarrollador, te está pidiendo que ejecutes su código como tú mismo.

## Activarlo

El sideload se rechaza a menos que `safety.allow_unsigned_plugins` sea
verdadero. El daemon lo dice exactamente en esos términos:

<!-- doctest: illustrative reason="the daemon's refusal, quoted from astra-daemon/src/plugins/manager.rs; reproducing it needs a running Astra with the setting off" -->
```
Sideloading is disabled. It runs an unsigned local plugin as native code with
your full privileges. Turn on Settings -> Privacy -> "Allow unsigned plugins"
(`safety.allow_unsigned_plugins`) to sideload (local plugin development only).
```

y la CLI convierte eso en la misma instrucción con la solución en su
propia línea (`astra-plugin-cli/src/daemon.rs`). Los dos mensajes nombran
secciones distintas de Settings — el daemon dice Privacy, la CLI dice
Safety. La **clave del ajuste es `safety.allow_unsigned_plugins`**, y eso
es lo que hay que buscar.

## Usarlo

Un comando, desde [la CLI](../install-cli.md):

<!-- doctest: cli -->
```bash
astra-plugin dev
astra-plugin dev . --daemon-addr 127.0.0.1:32000
```

`dev` hace cuatro cosas en orden, y se detiene en el primer fallo:

1. `astra-plugin check --strict` — no le entregará al daemon un
   manifiesto que ya esté mal;
2. compila;
3. entrega el **directorio** al daemon mediante `SideloadPlugin`, que
   lanza el proceso, acuña su token de autenticación y posee su ciclo de
   vida a partir de ahí;
4. observa cambios, recompila, detiene/arranca el plugin, y sigue su
   salida.

<!-- doctest: output from="astra-plugin dev . with no Astra running" unrun="needs a machine with no Astra daemon listening, which a CI runner cannot promise either way" -->
```
Dev mode: plugin 'dice-roller'
  Directory: /tmp/dice-roller
Checking plugin at /tmp/dice-roller...
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 2.48s
Error: Could not read /home/you/.config/astra/daemon.token. Astra does not look
like it is running — start the app first.
```

**El daemon posee el proceso, y eso no es una cuestión de estilo.** Un
plugin se autentica ante `PluginHostService` con un token que el daemon
acuña al lanzar el proceso, y el daemon rechaza cualquier `Register` que
no lleve un token que él haya emitido. Un plugin lanzado por la CLI no
tiene forma de obtener uno — el bucle de dev que se auto-lanzaba, al que
esto reemplaza, arrancaba un proceso que no hablaba con nadie.

`--standalone` conserva ese comportamiento anterior para los casos en que
sigue siendo útil (comprobar que un binario arranca, manejarlo a mano), y
avisa por adelantado de que el plugin no puede registrarse con Astra de
esa manera.

`dev --json` se rechaza deliberadamente: `--json` promete un documento por
ejecución, y `dev` nunca termina. `astra-plugin check --json`,
`astra-plugin test --json` y `astra-plugin logs --json` son las mitades
legibles por máquina de lo que hace.

## Lo que cuesta exactamente el sideload

| | |
|---|---|
| **Firma** | ninguna. Nada responde por el código |
| **Privilegios** | toda tu cuenta de usuario. No hay sandbox — [la Fase 7 no existe](../1-orientation/security.md) |
| **Radio de impacto del interruptor** | `allow_unsigned_plugins` se aplica a cada plugin de la máquina, incluidos los archivos sin firmar que importes después |
| **Auto-arranque** | **nunca.** El modo desarrollador es obligatorio en el momento de la carga, y un reinicio deja un plugin en sideload detenido hasta que lo arranques de nuevo |
| **Techo de permisos** | **ninguno** — ver abajo |
| **Procedencia mostrada al usuario** | nivel `sideloaded` — "cargado desde una carpeta" — en el panel de procedencia |

### Por qué no hay techo de permisos aquí

Un [`.astraplugin` importado localmente](local-install.md) tiene cuatro
permisos rechazados de plano. Un **directorio fuente** en sideload no, y
la excepción es deliberada, no un descuido: este es el bucle de creación
para plugins de UI, y `dom_access` es exactamente lo que necesitan
`companion`, `doom` y `bad-apple`. Limitar el nivel 3 los haría
indesarrollables.

El intercambio es que el nivel 3 está bloqueado detrás de un ajuste
explícito, nunca arranca automáticamente, y es un directorio al que tú
mismo apuntaste — tres hechos que el nivel 2 (un archivo que llegó de
algún sitio) no puede reclamar.

El plan también pide una insignia permanente, no descartable, de
"DEVELOPER — unverified code from a local directory" en la tarjeta del
plugin y en el marco de la ventana siempre que `dom_access` esté activo.
**Esa insignia no está hoy en la interfaz**, y esta página no afirma que
lo esté.

## Lo que no funciona, y no funcionará

**Escribir a mano un marcador `sideload.json` en el directorio de
plugins.** El daemon rechaza un marcador del que no tiene ningún registro
que lo autorice:

<!-- doctest: illustrative reason="a daemon log line, quoted from astra-daemon/src/plugins/manager.rs; it is emitted on a machine with a planted marker" -->
```
Refusing sideload marker in <path>: this daemon never authorised a sideload of
'<id>' from <source> (no matching record in <registry path>). A marker file
alone does not authorise running unsigned native code.
```

Instrucciones antiguas les decían a los autores que dejaran un marcador
en `~/.config/astra/astra/plugins` — una ruta que no existe, encima de un
mecanismo que ya no funciona, sin mencionar el requisito previo
`allow_unsigned_plugins`. Se han eliminado en lugar de corregirse. El
reemplazo es una línea: `astra-plugin dev`.

## Cuando termines de desarrollar

Nada en esta vía produce algo que otra persona pueda instalar. Para
distribuirlo:

1. [`astra-plugin init-ci`](release-with-ci.md), luego una etiqueta — la
   CI lo compila y lo certifica;
2. [`astra-plugin publish`](get-listed.md) — una vez, para siempre;
3. los usuarios lo instalan desde dentro de Astra, con el digest fijado.

Volver a desactivar `allow_unsigned_plugins` cuando no estés
desarrollando vale los dos clics.
</content>
