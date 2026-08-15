> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/5-publish/get-listed.md) es la referencia autorizada.

# Conseguir el listado

**Un plugin se lista una vez, para siempre.** Después de eso, los
releases no requieren intervención: etiquetar, dejar que la CI compile y
certifique, y el registro lo recoge.

Requisito previo: [un release compilado por CI](release-with-ci.md), en
un repositorio **público**, con los assets `.astraplugin` adjuntos y
certificados. Ese requisito se cumple etiquetando — el workflow
reutilizable está en la rama por defecto de `mihailinl/AstraPlugins` y
publicado como `plugin-release/v1`, así que un push de etiqueta compila y
certifica. Todo en esta página asume que ya hiciste eso; si no, haz
primero [Publicar release con CI](release-with-ci.md), o lee
[Publicar un plugin](../publishing.md), que es todo el recorrido en una
sola página.

**Lo que no lo sustituye**, porque cada uno de estos ya se ha intentado:
un repositorio que contiene tu código fuente, un `.zip` enviado a
alguien, un paquete que compilaste en tu portátil, o un issue pidiéndole
a un mantenedor que lo compile. El registro lista assets de release que
la CI certificó, y nada más.

Casi todos los comandos de abajo son `astra-plugin`; la excepción es
[el paso 2](#2--demuestra-que-controlas-el-repositorio), que es un solo
archivo y un `git commit` en tu propio repositorio. Si no tienes la CLI,
[instálala primero](../install-cli.md) — ahora hay binarios precompilados.

## 1 · Preflight

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

Ejecuta cada comprobación que hace el registro y que se puede ejecutar en
local, y luego — la mitad que importa — **nombra las que solo el registro
puede ejecutar**, para que sepas qué queda por demostrar:

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the release assets are served from your repository's own release namespace
  · that `.well-known/astra-plugin-owner` on your default branch names the account opening the listing request
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan
```

**Una de esas comprobaciones la puedes resolver por adelantado, y
deberías.** La línea de propiedad nombra el archivo, y subirlo es
[el paso 2](#2--demuestra-que-controlas-el-repositorio). Hazlo antes de
enviar y la comprobación pasa a la primera; sáltatelo y la primera
respuesta que obtienes es un rechazo.

### Cómo se verá tu listado

Dos archivos deciden eso, y ambos ya los tienes junto a `plugin.toml`.
Ninguno se nombra en ningún sitio del manifiesto — el empaquetador los
recoge por cómo se llaman, y el registro los relee del paquete que
acaba de verificar. Nunca escribes una URL, y nadie puede escribir una
por ti.

**El icono** — la imagen en la tarjeta de tu plugin. Cualquiera de:

<!-- doctest: illustrative reason="the accepted filenames, not a command; spec/icon-formats.yaml is the list both the packer and the registry read" -->
```
icon.png    icon.webp    icon.svg    icon.jpg    icon.ico
```

`astra-plugin new` genera un `icon.svg` de marcador de posición para que
haya algo que reemplazar. Dibújalo cuadrado; se muestra a
aproximadamente 64 píxeles, así que quiere una silueta marcada en lugar
de detalle fino, y debería leerse bien tanto en fondo claro como en
fondo oscuro porque la tienda sigue el tema del usuario. Un PNG con fondo
transparente es la respuesta habitual.

Si distribuyes un SVG, mantenlo estático: sin `<script>`, sin
manejadores `on*`, sin `<foreignObject>`, y sin referencia a nada fuera
de tu máquina. Un icono que lleve algo de eso se descarta y tu plugin se
lista sin imagen. No hace fallar tu release — un archivo decorativo no es
una barrera para distribuir software — pero recibes un aviso que lo dice,
y nadie ve tu icono.

**`README.md`** — la página de tu plugin, mostrada cuando alguien hace
clic en la tarjeta. Es lo que lee una persona mientras decide si
instalarte, lo que lo hace más valioso que el resumen de una línea.

Se renderiza como markdown al estilo GitHub, tablas incluidas. Las
capturas de pantalla funcionan, y un párrafo formado solo por imágenes se
convierte en una fila de galería:

<!-- doctest: illustrative reason="markdown an author writes in their own README; there is nothing here for a runner to execute" -->
```markdown
![The command editor, mid-roll](docs/editor.png)
![The trigger firing on a natural 20](docs/trigger.png)
```

Tres reglas, todas las cuales aplica el registro al derivar tu listado:

- **Enlaza las imágenes con una ruta relativa**, y súbelas a tu
  repositorio. Se reescriben para apuntar exactamente al commit desde el
  que se compiló tu release, así que una imagen no puede cambiar después
  de que alguien aprobó el listado.
- **Las imágenes alojadas en cualquier sitio que no sea GitHub se
  descartan** y se reemplazan por su texto alternativo. Insignias de
  build incluidas. Es una regla de privacidad más que de seguridad: cada
  imagen remota en un README renderizado es una petición desde la
  máquina de un usuario, hecha antes de que haya instalado nada.
- **El HTML sin procesar se elimina.** Usa markdown para el diseño.

Los README largos se truncan a 16 KB en un límite de línea, con un enlace
al resto en GitHub.

## 2 · Demuestra que controlas el repositorio

**Haz esto antes de abrir el issue.** Es un archivo y un commit, y
saltárselo es la forma más común en que un primer envío correcto y
honesto acaba rechazado.

El registro tiene que responder a una pregunta que nada más en esta
página responde: **¿controla la persona que solicita este listado el
repositorio que se está listando?** La attestation ya demuestra que el
paquete salió de ese repositorio, y el listado queda fijado a él — pero
ninguno de esos dos hechos dice quién eres *tú*. Sin este paso, un
desconocido podría listar el plugin de otra persona y convertirse en la
identidad a través de la cual llegan sus actualizaciones a los usuarios
de Astra.

Sube este archivo a la **rama por defecto** de tu repositorio:

<!-- doctest: illustrative reason="the path and content of a file the author writes in their own repository; there is nothing here for a runner to execute" -->
```
path      .well-known/astra-plugin-owner
content   your GitHub login, one per line
```

El único comando que lo crea, ejecutado en la raíz del repositorio de tu
plugin:

<!-- doctest: illustrative reason="git commands against the author's own repository — the runner has no such repository, and `cli` blocks must contain an astra-plugin command" -->
```bash
mkdir -p .well-known
echo 'your-github-login' > .well-known/astra-plugin-owner
git add .well-known/astra-plugin-owner
git commit -m "Declare the Astra registry owner for this repository"
git push
```

**Qué demuestra:** que alguien capaz de escribir en tu rama por defecto
afirma que este login de GitHub habla por este repositorio — leído en
vivo en el momento en que el bot comprueba, así que quitar un login impide a
esa persona abrir una nueva solicitud de listado o pasar un `/recheck`. **No**
alcanza a un plugin ya listado: [cada release a partir de ahí](#5--cada-release-a-partir-de-ahí)
se comprueba contra la cuenta que publicó el release, y el listado sigue
anclado a este repositorio de todos modos.
**Qué no demuestra:** absolutamente nada sobre tu código, que nadie lee;
no es una firma, y no es una revisión de seguridad.

### El formato, exactamente

Un login por línea. Todo lo que va después de un `#` es un comentario, un
`@` al principio está bien, los espacios alrededor se recortan, y la
comparación no distingue mayúsculas de minúsculas. Solo se leen los
primeros 4 KB. Así que este archivo es válido y lista un propietario:

<!-- doctest: illustrative reason="the contents of a file in the author's repository, not a command" -->
```
# owners of this repository
@Rel0d1x   # primary
```

Lista a cada persona que pueda enviar o reenviar en nombre de este
repositorio. Para un repositorio propiedad de una organización eso suele
ser más de un nombre.

### Comprueba que el registro puede leerlo

El bot lee el archivo a través de la API de contenidos de GitHub, sin
autenticarse, en la rama por defecto. Puedes hacer exactamente la misma
petición que hace él:

<!-- doctest: illustrative reason="gh against the author's own repository; `cli` blocks must contain an astra-plugin command, and this one is deliberately shell-only" -->
```bash
gh api repos/you/dice-roller/contents/.well-known/astra-plugin-owner \
  --header 'Accept: application/vnd.github.raw+json'
```

Debería imprimir tu login de vuelta. Si imprime `Not Found (HTTP 404)`,
el archivo no está donde lo busca el bot — las causas habituales son que
está en una rama distinta a la por defecto, que todavía no se ha
confirmado ni subido, o que el directorio está escrito como `well-known`
sin el punto inicial.

### Por qué esto es un paso y no un plan de reserva

El registro intenta tres formas de establecer control, y este archivo es
la que funciona para un autor normal. Eso no es una preferencia; es
estructural, y a las otras dos se les vio fallar en envíos reales:

| Forma | Por qué no responde por ti |
|---|---|
| **Permiso de colaborador** — preguntarle a GitHub quién tiene `admin` o `maintain` | GitHub solo responde a ese endpoint para quien ya tiene visibilidad de admin sobre el repositorio. El token del registro pertenece al registro, así que para *tu* repositorio obtiene `403` — lo que significa «no te lo voy a decir», no «no», y se trata como si no hubiera respuesta en absoluto |
| **Autor del release** — la cuenta que publicó el release | El workflow de release de [Publicar release con CI](release-with-ci.md) crea el Release de GitHub, así que su autor es `github-actions[bot]` en lugar de una persona. Precisamente seguir la vía documentada anula esta opción |
| **`.well-known/astra-plugin-owner`** | Nada tiene que ser visible para el registro, y no hay que instalar nada. Sí responde |

Un `403` en la primera forma no se usa en tu contra y por sí solo nunca
se convierte en un rechazo. El rechazo solo ocurre cuando las tres no
dan nada, que es exactamente lo que pasa cuando este archivo no existe.

## 3 · Enviar

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

Abre un issue prerrellenado en el registro, en tu navegador. **No sube
nada y no guarda ninguna credencial** — no existe `astra-plugin login`,
ningún token en el historial de tu shell, ningún llavero con el que
integrarse. `--print-url` imprime el enlace en su lugar:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

Esa captura viene de un directorio sin etiqueta git propia. Si ejecutas el
comando dentro de tu checkout antes de haber traído la etiqueta, aparece una
línea extra encima del párrafo — `Note: this checkout has no tag v0.1.0.` Es un
recordatorio, no un error: el registro lee el release desde GitHub, así que lo
que importa es que la etiqueta esté subida y que la CI haya adjuntado los
artefactos.

> **`template=plugin-listing.yml` en esa URL es estructural.** La plantilla
> declara `labels: ["listing", "needs-triage"]`, y el bot del registro solo
> entra en la vía de envío para un issue que lleve `listing`. Nadie más
> aplica esa etiqueta — tampoco el bot, a propósito: allí es un token de
> autoridad y no una categoría, y un bot que la estampara sobre cualquier
> cosa con forma de formulario entregaría la excepción a quien sepa copiar
> un formulario.
>
> Dos solicitudes de listado reales se perdieron exactamente así: llegaron
> sin etiquetas, el triage devolvió `mode: "none"`, los pasos de
> comprobación, publicación y comentario se omitieron todos, y los autores
> **no obtuvieron respuesta alguna, ni siquiera un rechazo**. Eso está
> arreglado ahora por ambos lados. Los issues en blanco están desactivados
> en el registro, así que la página *New issue* solo ofrece formularios; y
> una solicitud que aun así llegue sin etiqueta recibe un comentario que
> dice exactamente qué falta, más el único clic — un maintainer añadiendo
> `listing` — que arranca la verificación en ese mismo issue sin
> reescribir nada. Abrirlo desde este enlace se salta todo eso.

El envío lleva **dos hechos**:

| Campo | Por qué se escribe en lugar de leerse |
|---|---|
| Repositorio fuente (`you/dice-roller`) | El paquete no puede responder por desde dónde se sirve |
| Etiqueta de release (`v0.1.0`) | Lo mismo |

Más tres confirmaciones, todas obligatorias: que has subido
`.well-known/astra-plugin-owner` a la rama por defecto con tu login dentro,
que eres dueño o mantenedor del repositorio, y que has leído la política.

**Todo lo demás se lee del paquete certificado** — el id, la versión, el
nombre a mostrar, el resumen, la licencia, las capabilities, los
permisos, las plataformas, los digests, los tamaños. Eso no es una
comodidad: todo en el paquete está cubierto por la attestation, lo que lo
hace estrictamente más fiable que cualquier cosa escrita en un
formulario. También elimina toda una clase de rechazo, porque no hay
ningún formulario con el que `plugin.toml` pueda discrepar.

## 4 · Qué pasa después de enviar

Esta sección es la que necesitaban dos autores reales y no tuvieron.
Describe el flujo del registro tal como lo definen
`astra-registry/docs/POLICY.md` y `docs/BOT-CHECKS.md`; ambos se generan
a partir del propio código del bot o se verifican contra él
(`bot/lib/policy.mjs`, `bot/lib/codes.mjs`), así que los números aquí no
pueden desviarse en silencio del código que los mantiene.

### La secuencia

1. **Tu issue recibe las etiquetas `listing` y `needs-triage`** — de la
   plantilla del issue, automáticamente. Este es el paso que decide si
   pasa algo en absoluto; ver el aviso en §3.
2. **El bot lo triaje**, lee tus dos hechos, obtiene el release de
   GitHub sin autenticarse, y ejecuta cada comprobación de
   `docs/BOT-CHECKS.md` contra los bytes: la attestation y qué workflow
   la produjo, que las URL de los assets estén bajo el espacio de
   nombres de releases del propio repositorio, que controlas el
   repositorio ([el paso 2](#2--demuestra-que-controlas-el-repositorio)),
   la estructura del archivo, el manifiesto, la licencia, el orden de
   versiones, y el escaneo de RPC del host declarado versus llamado.
3. **El bot comenta en tu issue** con el resultado, el motivo y — cuando
   lo hay — el momento exacto en que publicará. Se te informa de una u
   otra forma.

Si no ha comentado nada en una hora, comprueba las etiquetas del issue.
Sin la etiqueta `listing` significa que el paso 1 no ocurrió y nada
posterior se ejecutó.

### Los cuatro resultados

| Resultado | Significa | Quién está involucrado |
|---|---|---|
| **Published** | Confirmado, y en el catálogo en la próxima compilación del índice | nadie |
| **Delayed** | Todo pasó; se publica solo en un momento indicado | nadie |
| **Held** | Una decisión que el registro no está autorizado a tomar automáticamente | un mantenedor, en 48 h |
| **Refused** | Una comprobación falló. La política nunca tuvo voz | tú: arréglalo y comenta `/recheck` |

Un release se publica solo, sin ningún humano, cuando se cumple todo
esto: viene del repositorio ya listado para ese plugin, cada
comprobación del bot está en verde, la versión es estrictamente más
nueva, no pide ningún permiso de alto riesgo que no tuviera ya, y no pide
ningún permiso o capability nuevo en absoluto. Si solo falla lo último,
igual se autopublica, tras un retraso.

**Un primer listado nunca es uno de esos.** Se retiene para una persona
por definición — ver abajo — así que la respuesta a "cuánto tarda mi
primer plugin en listarse" es *hasta 48 horas después de que el bot
comente*, no *minutos*.

### Cómo se libera un hold

No se requiere nada de ti. Un mantenedor comenta **`/approve`** en tu
issue, y toda la ingesta se vuelve a ejecutar entonces desde cero contra
los bytes tal como están en ese momento — una aprobación es una marca de
"una persona dijo sí, en este momento" y no lleva ningún veredicto en
caché, así que aprobar algo no se salta ni una sola comprobación.
**`/reject <reason>`** es la otra mitad, y debe llevar un motivo, que se
te publica. Ambos comandos se comprueban contra el permiso en el
repositorio del registro: quien comenta necesita `admin` o `maintain`
ahí, vuelto a demostrar mediante la API de GitHub en el momento en que se
lee el comando en lugar de confiarse desde la carga del evento, y un
comando de cualquier otra persona se responde en lugar de ignorarse.

Tú no escribes ninguno de los dos comandos, y no necesitas hacer nada
mientras esperas. Se documentan aquí solo para que "retenido para un
mantenedor" nombre un mecanismo en lugar de un silencio.

*Una advertencia, indicada porque la regla de esta página es indicarlas:*
esta vía de comandos de mantenedor está llegando al registro al mismo
tiempo que esta página. Si tu hold es anterior a ella, el resultado es el
mismo y el SLA es el mismo — un mantenedor sigue decidiendo — pero la
decisión puede quedar registrada a mano en lugar de con el comando.

### Cómo se ve un rechazo

El bot comenta con un código fijo y qué hacer al respecto. Un rechazo no
es un veredicto sobre tu plugin; es una condición nombrada y corregible.
Las que más encuentran los autores:

| Código | Qué significa | Solución |
|---|---|---|
| `E_ATTESTATION_MISSING` | El paquete no tiene attestation de compilación | Subiste un paquete que compilaste tú mismo. Deja que la CI lo compile: [publicar release con CI](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | El release no lleva ningún asset `.astraplugin` | El workflow no se ejecutó, o se ejecutó y falló. Revisa la pestaña Actions de tu repositorio |
| `E_RELEASE_NOT_FOUND` | Ese repositorio no tiene ningún release con esa etiqueta | Un release en borrador es invisible para todos menos para ti, y un repositorio privado se ve idéntico a uno inexistente |
| `E_WORKFLOW_NOT_ALLOWED` | El build usó un workflow que este registro no permite | Fija el workflow reutilizable de Astra por SHA de commit. `astra-plugin init-ci` lo hace por ti |
| `E_ASSET_URL_FOREIGN` | Una URL de asset no está bajo los propios releases de tu repositorio | Cada URL de descarga debe estar bajo `https://github.com/<owner>/<repo>/releases/download/<tag>/` |
| `E_OWNERSHIP_UNPROVEN` | Nada demostró que controlas ese repositorio | Casi con toda seguridad te saltaste [el paso 2](#2--demuestra-que-controlas-el-repositorio). Sube `.well-known/astra-plugin-owner` en la rama por defecto con tu login de GitHub dentro, luego comenta `/recheck` — no hace falta ni un release nuevo ni una etiqueta nueva |
| `E_INPUT_REPO` / `E_INPUT_TAG` | El repositorio o la etiqueta no tiene la forma esperada | `you/dice-roller`, no una URL; `v0.2.0`, no un SHA de commit ni una rama |

Después de arreglarlo, comenta **`/recheck`** en el mismo issue. Cada
comprobación se ejecuta de nuevo desde cero contra los bytes tal como
están en ese momento; nada se reanuda y nada en cola se da por confiado.
La lista completa, con el texto exacto de cada fallo, está en
`docs/BOT-CHECKS.md` en el registro.

Los propios códigos de salida del bot son `0` listed · `1` refused ·
`3` held for a maintainer · `2` el bot mismo falló. Este último es
deliberadamente distinto: "tu plugin está mal" y "nuestro tooling está
mal" nunca deben aparecer como el mismo comentario a un desconocido.

### Las tres cosas que necesitan a una persona

Exactamente tres, y la lista no crece sin un cambio en la política
publicada del registro:

| Evento | Por qué |
|---|---|
| **El primer listado de un plugin** | Una vez, para siempre. Nada está fijado todavía, así que nada posterior se puede comprobar contra ello |
| **Un permiso de alto riesgo recién solicitado** | Se le pedirá al usuario que lo consienta; alguien debería haber leído para qué es primero |
| **El repositorio o la identidad cambiaron** | Cada copia instalada lleva un fijado al repositorio antiguo. Un cambio de repositorio es un cambio de autor hasta que alguien diga lo contrario |

Alto riesgo aquí son cuatro nombres: `client`, `dom_access`,
`send_chat_message`, `set_theme_contribution` — detectados igual en
`[capabilities]` y en `[permissions]`, porque la sección en la que los
declaras no es lo importante. `push_to_ui` recibe una casilla de
consentimiento pero no una revisión: dibuja dentro de un panel que tu
plugin ya posee.

Una comprobación puede, por separado, entregar una decisión a una
persona — un nombre a una edición de distancia de un plugin listado, un
nombre a mostrar que colisiona con uno. Eso llega como `R_CHECK_HELD`, no
es uno de los tres, y lleva el mismo SLA.

**El SLA es de 48 horas** para esos, desde el momento en que comenta el
bot. Hay un mantenedor, que es precisamente por qué la lista tiene tres
elementos. El registro publica qué pasa cuando eso se retrasa, en lugar
de solo la promesa: pasadas 96 horas el mantenedor debe publicar la cola
o sacar el evento desencadenante del conjunto bloqueante, en un commit
revisado que también edita el párrafo que hace la promesa.

### Cuando un release espera en su lugar

Algunos releases pasan todo y aun así no se publican de inmediato:

| Situación | Código | Retraso |
|---|---|---|
| El plugin tiene **algún** permiso de alto riesgo, lo haya cambiado o no este release | `P_DELAY_HIGH_RISK` | 24 h |
| El release pide un permiso o capability que el anterior no tenía, dentro del conjunto de riesgo no alto | `P_DELAY_WIDENED` | 24 h |
| Cualquiera de los dos anteriores, de un autor con **5 releases limpios** en este registro | `P_TRUSTED_AUTHOR` | 6 h |

El bot indica el momento exacto de publicación, y cuando se agota el
reloj, toda la ingesta se vuelve a ejecutar desde cero contra los bytes
tal como están entonces. El retraso compra una sola cosa, y el registro
no afirma más: una ventana en la que un autor cuya cuenta de GitHub fue
tomada pueda ver un release que no hizo y decirlo.

## 5 · Cada release a partir de ahí

Nada. Etiqueta, y la CI hace el resto; el registro nota el release y
regenera el índice.

Si no lo ha notado:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

Ese es el ping manual para un plugin que **ya está listado**. Sin él,
`publish` abre una solicitud de primer listado.

**La propiedad es otra pregunta en esta ruta.** Un ping — y el respaldo por
cron detrás de él — comprueba el release contra la cuenta que lo *publicó*,
no contra quien escribió el ping ni contra `.well-known/astra-plugin-owner`.
Editar ese archivo, por tanto, no cambia quién puede publicar un release de
un plugin ya listado. Lo que lo acota es que un ping solo puede nombrar un
repositorio que el registro **ya tiene anclado**: cambiar de repositorio deja
de ser rutina y vuelve a una persona.

## Lo que un listado no significa

Un listado no es una revisión de seguridad. Nadie lee tu código, y el
registro lo dice en su propia política: un permiso decide qué hará el
daemon *por* un plugin, y nada sobre lo que el proceso del plugin pueda
hacerle a la máquina. No hay sandbox. Consulta
[el modelo de seguridad](../1-orientation/security.md).

## El estado de esto hoy

Algo que un lector merece saber antes de seguir esta página.

**La cadena de firma está anclada hasta la delegación, pero todavía no a
través del catálogo.** En concreto, y cada parte es comprobable:

- las claves raíz existen en ambos lados — `registry/v1/root.json` lleva
  `"status": "provisioned"` con dos claves Ed25519, y
  `PRODUCTION_ROOT_KEYS` del daemon compila las mismas dos;
- `registry/v1/trust.json` **ya está firmado** por `astra-root-2026a` y
  delega en una clave de firma de índice, `astra-index-2026a`. El propio
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` del
  registro lo confirma e imprime el único SHA de workflow reutilizable
  que el bot aceptará en una attestation,
  `e3329df252a46d747676cb540ae4b986af68a3ad` — el commit al que apunta
  `plugin-release/v1`. Así que `E_TRUST_UNPROVISIONED`, que antes
  detenía cada ingesta, ya no se dispara;
- **el catálogo en sí sigue sin firmar.** `registry/v1/index.json` y
  `revocations.json` llevan `"signatures": []`, así que una compilación
  por defecto de Astra no tiene firma que comprobar, clasifica cualquier
  catálogo como sin firmar, y falla cerrada (fail closed). La aplicación
  de revocaciones tampoco está activa, por la misma razón.

Consulta [`spec/registry-index.md` §0.1](../spec/registry-index.md) y
[el modelo de seguridad](../1-orientation/security.md).

Lo que eso significa para ti: la vía de envío de esta página funciona
hoy de principio a fin — tu issue se lee, las comprobaciones se
ejecutan, el bot responde, y un listado se confirma. Lo que sigue
pendiente es la firma que le permite a Astra *instalar* a partir de lo
que publica el registro. Nada de esta página cambia cuando llegue.

## Ver también

- [`spec/registry-index.md`](../spec/registry-index.md) — el índice, las revocaciones, y el algoritmo de verificación
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — qué lee el bot de tu archivo
- [Versionado](../versioning.md) — qué significan los números y cuánto dura una obsolescencia
</content>
