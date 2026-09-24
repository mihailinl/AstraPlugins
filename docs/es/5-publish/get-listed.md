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
alguien, un paquete que compilaste en tu portátil, o un mensaje pidiéndole
a un mantenedor que lo compile. El registro lista assets de release que
la CI certificó, y nada más.

Cada paso de abajo es `astra-plugin`, un commit en tu propio repositorio o el
panel en https://astra.minice.ai/plugins, con la sesión iniciada en tu cuenta de
Minice. Si no tienes la CLI, [instálala primero](../install-cli.md) — hay
binarios precompilados.

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
  · that the attestation's workflow commit is one the registry's trust.json allows (E_WORKFLOW_NOT_ALLOWED)
  · that the release assets are served from your repository's own release namespace
  · the binding verdict: that the token on the binding line at the tagged commit is bound to a Minice account (B_BINDING_UNUSABLE)
  · eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)
  · the ids against the identity record: that the repository and its owner are the ones this listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan
```

**Una de esas la resuelves por adelantado, y debes.** El veredicto de
vinculación lee la línea que escribe [Vincula tu repositorio](#vincula-tu-repositorio).
Haz commit de ella antes de etiquetar y la comprobación tiene algo que
encontrar; déjala fuera y la primera respuesta es `B_UNBOUND`.

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

## Vincula tu repositorio

**Un listado pertenece a una cuenta de Minice.** Todo primer listado, y todo
release de un listado que la tenga, se lee contra una **vinculación**: una línea
en `.well-known/astra-plugin-owner` en la raíz de tu repositorio, escrita por la
CLI a partir de un token que generas en el panel, con la sesión iniciada en la
cuenta de Minice que va a publicar. Es el único paso de esta página que no es un
comando, y saltárselo es la forma más común de que un primer envío correcto y
honesto sea rechazado.

**1 · Genera un token.** Inicia sesión en https://astra.minice.ai/plugins con la
cuenta de Minice que será dueña del listado — necesita `astraUser`, que viene con
ser propietario de Astra — y genera un token de vinculación para este
repositorio.

**2 · Escribe la línea.** En cualquier lugar dentro del repositorio:

<!-- doctest: cli -->
```bash
astra-plugin init-ci --binding <token>
```

Escribe `astra-binding: <token>` como **primera línea** de
`.well-known/astra-plugin-owner` en la raíz del repositorio, elimina cualquier
línea de vinculación anterior en cualquier grafía, conserva tus líneas de login y
no usa la red:

<!-- doctest: output from="astra-plugin init-ci --binding k3Vq9ZtW2xLr8NfBcY5pHd" unrun="rewrites .well-known/astra-plugin-owner in a git repository; re-run it at the root of your own" -->
```
  Rewrote: .well-known/astra-plugin-owner
    line 1   astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd
    kept     1 other line(s), byte for byte

  This token is public once you push it. It records one Minice account's consent
  to publish from this repository, and it authenticates no release: never merge a
  binding line you did not mint yourself. What that means, and what a rename or a
  transfer does to it:
    https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository

  Next: commit this file on your default branch, then tag. Before you push the tag,
    astra-plugin check --tag <tag>
  reads the line back from the tagged commit, as the registry will.
```

**3 · Haz commit en tu rama por defecto y luego etiqueta.** Antes de subir la
etiqueta, vuelve a leer la línea exactamente como lo hará el registro — desde el
commit de la etiqueta, no desde tu árbol de trabajo:

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
```

Una línea mal formada falla aquí, con `B_BINDING_MALFORMED`, mientras arreglarla
todavía no cuesta nada. Una que falta es una advertencia que predice
`B_UNBOUND`. Cuatro respuestas que solo el registro puede dar se nombran cada
vez como no comprobadas.

**4 · Envía en el panel.**
`astra-plugin publish` abre la página de envío del panel con el repositorio y la
etiqueta ya rellenados, por ejemplo
https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0 — la
página no envía nada hasta que tú lo hagas, con la sesión iniciada.

**Qué es el token, y qué no es.** Un token de vinculación es **público**: está en
un archivo de un repositorio público. Registra el **consentimiento de una
cuenta** para publicar desde este repositorio, y **no autentica ningún
release** — un release que nada retrasa se publica antes de que la cuenta se
entere. Así que **nunca fusiones una línea de vinculación que no hayas generado
tú**: un pull request que añade o cambia una te está pidiendo que entregues tu
listado a la cuenta de otra persona.

**Dónde debe estar la línea.** En la raíz del repositorio, esté tu plugin en el
directorio que esté; en el commit al que apunta tu etiqueta de release; y dentro
de los primeros 4096 bytes del archivo. Una línea cubre todos los plugins del
repositorio. Borrarla después de la rama por defecto no termina nada que ya esté
vinculado.

**Cuánto dura un token generado.** Un token generado caduca 30 días después de
generarse, salvo que un envío vivo lo nombre o que su línea esté en la rama por
defecto del repositorio cuando se aplica la regla — la regla se vuelve a
comprobar antes de cada decisión de caducidad. Así que un autor que etiqueta
mucho más tarde sin la línea en la rama por defecto genera otro, y uno cuya línea
sigue en esa rama cuando se aplica la regla no. Una línea con commit y quitada
después no mantiene vivo un token.

**Iniciar sesión.** El registro lee la elegibilidad de la cuenta de su último
inicio de sesión verificado, que cuenta durante 12 horas. Un release de un
repositorio vinculado espera mientras la cuenta no haya iniciado sesión en ese
tiempo; el panel lo dice, y un aviso `notice.sign_in` te pide que inicies
sesión. Nada se publica hasta que lo hagas.

**Adónde van los avisos.** A la dirección de correo verificada de la cuenta de
Minice, y al panel. Telegram es un canal adicional opcional que puedes vincular;
nada lo exige.

**Un cambio de nombre o una transferencia deja varadas las copias instaladas.**
Astra identifica un plugin instalado por su repositorio, `github:owner/name`.
Cambia el nombre del repositorio o transfiérelo a otro dueño y todas las copias
instaladas dejan de recibir actualizaciones hasta que se reinstalen desde el
nombre nuevo. Nada anula esto.

**Para un plugin que ya está listado.** Un listado sin vincular está
`grandfathered`: sigue publicando como hoy hasta lo que llegue después, el plazo
de vinculación o el cutover del registro. El plazo se fija antes de que se abran
las vinculaciones de terceros, y lo publica el registro. Después, un listado sin
vincular queda `frozen`: las copias instaladas siguen funcionando y sigue siendo
instalable, pero no se publica ningún release nuevo suyo hasta que se publique
uno con línea de vinculación — un release vinculado lo descongela, sin
penalización. El primer release con línea de vinculación se retiene una vez para
que lo revise una persona, `R_FIRST_BINDING`. Y desde el cutover, un release
retrasado o revisado de un listado `grandfathered` espera hasta que el listado
esté vinculado.

**Comprobación previa.** `astra-plugin check` rechaza un id que el registro
rechaza — un id reservado, o uno fuera del patrón de ids del registro — y una
línea de vinculación mal formada. `astra-plugin dev` y `astra-plugin build` no
rechazan ninguno de los dos: las reglas del registro deciden qué se lista, nunca
qué puedes ejecutar.

## 2 · Envía en el panel

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

Abre la **página de envío** del panel en tu navegador, con tu repositorio y tu
etiqueta ya rellenados. **No sube nada y no guarda ninguna credencial** — no hay
`astra-plugin login`, ni token en tu historial de shell, ni llavero con el que
integrarse. La página se rellena a partir del enlace y no envía nada: lo envías
tú, con la sesión iniciada en la cuenta de Minice a la que está vinculado tu
repositorio. `--print-url` imprime el enlace en su lugar:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

A un repositorio sin línea de vinculación se le dice encima del enlace, junto
con dónde leer cómo vincularlo; un checkout sin la etiqueta recibe una línea
diciendo que la etiqueta tiene que estar subida. Las dos cosas son
recordatorios, no errores: el registro lee el commit de la etiqueta y el
release desde GitHub, así que lo que cuenta es lo que subiste.

El envío lleva **dos datos**:

| Campo | Por qué se escribe en vez de leerse |
|---|---|
| Repositorio de origen (`you/dice-roller`) | El paquete no puede responder de desde dónde se sirve |
| Etiqueta de release (`v0.1.0`) | Lo mismo |

**Todo lo demás se lee del paquete certificado** — el id, la versión, el nombre
visible, el resumen, la licencia, las capacidades, los permisos, las
plataformas, los digests, los tamaños. No es una comodidad: todo lo que hay en
el paquete está cubierto por la certificación, lo que lo hace estrictamente más
fiable que cualquier cosa escrita en un formulario. También elimina toda una
clase de rechazos, porque no hay formulario con el que `plugin.toml` pueda
discrepar.

## 3 · Qué pasa después de enviar

El panel muestra el estado de tu envío y cada motivo asociado, y los mismos
momentos te llegan como avisos: a la dirección de correo verificada de la
cuenta de Minice y en el panel, y por Telegram solo si lo has vinculado — nada
exige Telegram. Las reglas de abajo son las del registro, publicadas en su
`docs/POLICY.md`; los códigos son los que muestra el panel, con títulos en
inglés en el lanzamiento.

### Los estados por los que pasa un envío

| Estado | Significa |
|---|---|
| `received` | El panel aceptó tu envío y nada lo ha leído todavía |
| `checking` | El bot del registro está leyendo el release y verificando cada asset desde cero |
| `held` | Todo lo que puede decidir una máquina pasó, y una decisión es de una persona — ver abajo |
| `approved` | Un moderador aprobó la retención; se publica cuando no quede nada más esperando |
| `delayed` | Todo pasó; se publica solo a la hora que muestra el panel |
| `published` | Confirmado en el registro |
| `served` | En el catálogo firmado desde el que instala Astra |
| `refused` | Una comprobación falló. El panel nombra el código, y si un Recheck puede resolverlo o necesita una etiqueta nueva |
| `stopped` | Lo detuviste antes de que se publicara, y no se publicará |

Un release se publica solo, sin ninguna persona, cuando se cumple todo esto:
viene del repositorio ya listado para ese plugin, vinculado a la misma cuenta;
todas las comprobaciones del bot están en verde; la versión es estrictamente
más nueva; no pide ningún permiso de alto riesgo que no tuviera ya; y no pide
ningún permiso ni capacidad nuevos en absoluto. Quita solo la última condición
y aun así se publica solo, tras un retraso.

**Un primer listado nunca es uno de esos.** Se retiene para una persona una
vez, para siempre, así que la respuesta a «cuánto tarda en listarse mi primer
plugin» es *cuando un moderador lo haya leído*, y el panel muestra que está
esperando.

### Cuando la respuesta es un código

Un rechazo no es un veredicto sobre tu plugin; es una condición con nombre y
arreglable, y el panel dice por cuál de dos vías se resuelve. **Recheck**, un
botón del panel, vuelve a ejecutar todas las comprobaciones desde cero contra la
misma etiqueta — para un arreglo fuera de los bytes etiquetados, como un asset
de release que olvidaste adjuntar. **Una etiqueta nueva** es la única forma de
cambiar algo dentro de ellos, porque la certificación cubre exactamente esos
bytes. Los códigos de vinculación:

| Código | Qué significa | Arreglo |
|---|---|---|
| `B_UNBOUND` | No hay línea de vinculación en el commit etiquetado, y este listado necesita una | Vincula el repositorio y vuelve a etiquetar: [Vincula tu repositorio](#vincula-tu-repositorio) |
| `B_BINDING_MALFORMED` | Dos líneas de vinculación, o una línea pensada como tal que no lo es (`Astra-Binding:`, un token corto) | `astra-plugin init-ci --binding <token>` reescribe el archivo con exactamente una línea; vuelve a etiquetar. `astra-plugin check --tag` lo muestra antes de que subas |
| `B_BINDING_UNUSABLE` | El token de la línea no vincula nada que este release pueda usar: revocado, caducado, generado para otro repositorio, o su cuenta no puede publicar | Genera en el panel un token nuevo para este repositorio y vuelve a etiquetar; el panel dice cuál de los dos casos de abajo es el tuyo |
| `B_BINDING_INVALID` | Solo lo ves tú y los moderadores: el problema es el propio token — desconocido, revocado, caducado, o generado para otro repositorio | Genera uno nuevo para este repositorio |
| `B_ACCOUNT_INELIGIBLE` | Solo lo ves tú y los moderadores: la cuenta detrás del token no puede publicar, por ejemplo porque ya no tiene `astraUser` | Arregla la cuenta y luego Recheck |
| `B_OWNER_CHANGED` | El repositorio pertenece ahora a un dueño distinto de aquel con el que está registrado este listado | Una transferencia es un cambio de autor. Espera a un moderador; las copias instaladas conservan el nombre antiguo hasta que se reinstalen |
| `B_REPOSITORY_RECYCLED` | El nombre del repositorio pertenece ahora a un repositorio distinto del listado | Permanente: ningún Recheck, etiqueta ni aprobación lo resuelve. Solo un moderador puede restablecer la identidad del listado |

Y los códigos de release con los que más tropiezan los autores:

| Código | Qué significa | Arreglo |
|---|---|---|
| `E_ATTESTATION_MISSING` | El paquete no tiene certificación de build | Subiste un paquete que compilaste tú. Deja que lo compile la CI: [release con CI](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | El release no lleva ningún asset `.astraplugin` | El workflow no se ejecutó, o se ejecutó y falló. Mira la pestaña Actions, adjunta los assets y luego Recheck |
| `E_RELEASE_NOT_FOUND` | Ese repositorio no tiene ningún release con esa etiqueta | Un borrador de release es invisible para todos menos para ti, y un repositorio privado parece idéntico a uno inexistente. Publícalo y luego Recheck |
| `E_WORKFLOW_NOT_ALLOWED` | El build ejecutó un workflow que este registro no permite | Fija el workflow reutilizable de Astra por SHA de commit — `astra-plugin init-ci` lo hace — y vuelve a etiquetar |
| `E_ASSET_URL_FOREIGN` | Una URL de asset no está bajo los releases de tu propio repositorio | Toda URL de descarga debe estar bajo `https://github.com/<owner>/<repo>/releases/download/<tag>/` |
| `E_INPUT_REPO` / `E_INPUT_TAG` | El repositorio o la etiqueta no tienen la forma esperada | `you/dice-roller`, no una URL; `v0.2.0`, no un SHA de commit ni una rama |

La lista completa, con el título y el arreglo de cada código, es
`docs/BOT-CHECKS.md` en el registro.

Dos esperas parecen un envío atascado y no lo son:

| Código | Qué significa |
|---|---|
| `W_ELIGIBILITY_UNREADABLE` | El registro lee la elegibilidad de tu cuenta de su último inicio de sesión verificado, que cuenta durante 12 horas. Inicia sesión en el panel y el release sigue adelante; un aviso `notice.sign_in` dice lo mismo |
| `W_REGISTRY_UNACKNOWLEDGED` | El bot del registro cambió y espera la confirmación de un operador. A tu release no le pasa nada, y no se te pide nada |

### Las tres cosas que necesitan a una persona

Exactamente tres, y la lista no crece sin un cambio en la política publicada
del registro:

| Evento | Código | Por qué |
|---|---|---|
| **El primer listado de un plugin**, o el primer release con línea de vinculación de uno ya listado | `R_FIRST_LISTING`, `R_FIRST_BINDING` | Una vez, para siempre. Todavía no hay nada fijado, así que nada posterior puede comprobarse contra ello |
| **Un permiso de alto riesgo recién solicitado** | `R_NEW_HIGH_RISK` | Se pedirá al usuario que dé su consentimiento; alguien debería haber leído antes para qué es |
| **El repositorio, su identidad o su vinculación cambiaron** | `R_IDENTITY_CHANGED`, `R_BINDING_CHANGED` | Cada copia instalada lleva fijado el repositorio antiguo. Un cambio es un cambio de autor hasta que alguien diga lo contrario |

Alto riesgo aquí son cuatro nombres: `client`, `dom_access`,
`send_chat_message`, `set_theme_contribution` — detectados tanto en
`[capabilities]` como en `[permissions]`, porque la sección en la que los
declaras no es lo importante. `push_to_ui` recibe una casilla de consentimiento
pero no una revisión: dibuja dentro de un panel que tu plugin ya posee.

Una comprobación también puede pasar una decisión a una persona — un nombre a
una edición de distancia de un plugin listado, un nombre visible que choca con
uno. Eso llega como `R_CHECK_HELD` y no es una de las tres.

Un moderador aprueba o rechaza en el panel, y un rechazo lleva un motivo, que te
llega. Mientras esperas no haces nada; el panel muestra la retención.

### Cuando un release espera en su lugar

Algunos releases lo pasan todo y aun así no se publican de inmediato:

| Situación | Código |
|---|---|
| El plugin tiene **cualquier** permiso de alto riesgo, lo haya cambiado este release o no | `P_DELAY_HIGH_RISK` |
| El release pide un permiso o capacidad que el anterior no tenía, dentro del conjunto que no es de alto riesgo | `P_DELAY_WIDENED` |
| Cualquiera de los anteriores, de un autor con un historial de releases limpio en este registro | `P_TRUSTED_AUTHOR` |

El panel indica la hora exacta de publicación, y cuando se agota el plazo toda
la comprobación vuelve a ejecutarse desde cero contra los bytes tal como estén
entonces. **Ninguna aprobación acorta un retraso.** El retraso compra una sola
cosa y el registro no afirma más: una ventana en la que un autor cuya cuenta fue
tomada puede ver un release que no hizo, y detenerlo. Las duraciones están en el
`docs/POLICY.md` del registro.

Un listado que sigue `grandfathered` — listado antes de las vinculaciones y aún
sin vincular — tiene una espera más: desde el cutover, un release retrasado o
revisado suyo espera hasta que el listado esté vinculado.

### Detener, retirar, apelar, denunciar

- **Detener.** Hasta que un release se publique, puedes detenerlo en el panel, y
  no se publicará.
- **Retirar (yank).** Después de publicarse, puedes retirar una versión en el
  panel. Un yank no se deshace nunca — publica una versión nueva en su lugar — y
  queda registrado con un registro de decisión, como cualquier otra decisión
  sobre un listado. Mientras tu listado aún no esté vinculado, pide en el panel
  a un moderador que la retire por ti.
- **Apelar.** Una decisión sobre tu listado que crees equivocada se apela en el
  panel, y la respuesta queda registrada allí.
- **Las valoraciones** son solo estrellas: sin texto, sin respuestas, sin
  nombres.
- **Las denuncias** sobre el plugin de otra persona van por
  https://astra.minice.ai/plugins, no por GitHub. Un problema de seguridad en
  Astra, el daemon, el registro o la cadena de firmas va a security@minice.ai —
  ver [`CONTRIBUTING.md`](../../../CONTRIBUTING.md#security).

## 4 · Cada release a partir de ahí

Nada. Etiqueta y la CI hace el resto: el registro detecta por sí mismo una
etiqueta nueva de un plugin listado, la verifica, y el panel muestra su estado.
No hay nada que enviar ni nada que avisar. Un release que no ha aparecido está
en la página de tu plugin en el panel, con su estado y el motivo.

**La vinculación se comprueba en cada release, no solo en el primero.** Cada uno
se lee contra la línea de vinculación de su commit etiquetado y el registro de
identidad del listado, así que un repositorio cuya línea cambió, o que pasó a
otro dueño, espera a una persona en lugar de publicarse — que es lo que hace de
un token robado o de un repositorio transferido un suceso que alguien ve.

## Lo que un listado no significa

Un listado no es una revisión de seguridad. Nadie lee tu código, y el
registro lo dice en su propia política: un permiso decide qué hará el
daemon *por* un plugin, y nada sobre lo que el proceso del plugin pueda
hacerle a la máquina. No hay sandbox. Consulta
[el modelo de seguridad](../1-orientation/security.md).

## El estado de esto hoy

Algo que un lector merece saber antes de seguir esta página.

**La cadena de firma está anclada a través del catálogo, pero todavía no a
través de la lista de retirada.** En concreto, y cada parte es comprobable:

- las claves raíz existen en ambos lados — `registry/v1/root.json` lleva
  `"status": "provisioned"` con dos claves Ed25519, y
  `PRODUCTION_ROOT_KEYS` del daemon compila las mismas dos;
- `registry/v1/trust.json` **ya está firmado** por `astra-root-2026a` y
  delega en una clave de firma de índice, `astra-index-2026a`. El propio
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` del
  registro lo confirma e imprime los SHA de workflow reutilizable
  que el bot aceptará en una attestation — dos de ellos desde que la
  etiqueta se movió el 2026-08-19: el commit al que apunta
  `plugin-release/v1`, y aquel al que apuntaba antes. Así que
  `E_TRUST_UNPROVISIONED`, que antes detenía cada ingesta, ya no se
  dispara;
- **el catálogo que reciben los clientes está firmado.** Desde el 2026-09-20
  el firmante del registro firma `index.json` con `astra-index-2026a` y lo
  despliega en Pages. Las copias confirmadas en `main`,
  `registry/v1/index.json` y `revocations.json`, llevan `"signatures": []`
  a propósito, y ningún cliente las lee. La lista de retirada que sirve Pages
  sigue siendo la confirmada sin firmar, así que la aplicación de
  revocaciones todavía no está activa.

Consulta [`spec/registry-index.md` §0.1](../spec/registry-index.md) y
[el modelo de seguridad](../1-orientation/security.md).

Lo que eso significa para ti: la vía de envío de esta página funciona
hoy de principio a fin — tu envío se lee, las comprobaciones se
ejecutan, el panel muestra la respuesta, y un listado se confirma. Lo que sigue
pendiente es la lista de retirada firmada en Pages, que le permite al
registro retirar una versión de las copias ya instaladas. Nada de esta página
cambia cuando llegue.

## Ver también

- [`spec/registry-index.md`](../spec/registry-index.md) — el índice, las revocaciones, y el algoritmo de verificación
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — qué lee el bot de tu archivo
- [Versionado](../versioning.md) — qué significan los números y cuánto dura una obsolescencia
</content>
