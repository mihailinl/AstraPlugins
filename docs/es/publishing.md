> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/publishing.md) es la referencia autorizada.

# Publicar un plugin

**Una página, desde un directorio vacío hasta un plugin que los usuarios
pueden instalar.** Cada comando está aquí en orden, con la salida que
produce. Si vas a leer una sola página sobre publicar, lee esta; las
páginas más profundas están enlazadas donde importan y ninguna de ellas
es necesaria para terminar.

---

## Lee esta parte aunque no leas nada más

Publicar un plugin en Astra significa **una cosa específica**: etiquetas
un release en tu propio repositorio de GitHub, la CI de GitHub compila
el paquete y lo certifica, y le envías al registro una solicitud de
listado — una sola vez, para siempre.

Estas cosas **no** son publicar, y cada una se ha intentado:

| No es publicar | Por qué no puede funcionar |
|---|---|
| Subir tu código fuente a GitHub | El registro nunca lee tu árbol de fuentes. Lee un archivo `.astraplugin` adjunto a un release, y no hay ninguno |
| Enviarle a alguien un `.zip`, o un paquete que compilaste en tu portátil | Los bytes no llevan attestation de compilación, así que el registro los rechaza por bueno que sea el plugin |
| Abrir un issue pidiéndole a un mantenedor que lo compile por ti | Nadie compila tu plugin salvo la propia CI de tu repositorio. No hay otro compilador |
| Abrir un issue en el registro que describa tu plugin, al margen del formulario de listado | Solo el formulario aplica la etiqueta `listing`, y solo esa etiqueta inicia una ingesta. Los issues en blanco ya están desactivados allí, y una solicitud sin etiqueta recibe una respuesta que nombra la etiqueta en lugar de silencio — pero una respuesta no es un listado. Consulta [Enviar](#8-enviar-una-sola-vez-para-siempre) |

**Por qué tiene que ser así, en dos frases.** El registro fija tu
plugin por el SHA-256 exacto del archivo que descargará un usuario, y
lee la attestation de compilación de GitHub — una firma Sigstore
acuñada a partir de la propia identidad OIDC del workflow — que declara
que estos bytes exactos salieron de ese workflow, en ese commit, en ese
repositorio. Un archivo que compilaste en tu portátil y le diste a
alguien no lleva ninguna de las dos cosas, así que no hay nada que
Astra pueda comprobar en la máquina del usuario ni nada que el registro
pueda fijar.

Nada de esto es una afirmación de que tu código es seguro. Consulta
[Qué establece la confianza](#qué-establece-la-confianza) al final de
esta página.

---

## Antes de empezar

<!-- doctest: cli -->
```bash
astra-plugin --version
```

Si eso no imprime nada, detente aquí y haz primero
**[Instalar la CLI](install-cli.md)**. Es una línea de
`cargo install`, necesita una toolchain de Rust, y todavía no hay
binarios precompilados — esa página lo dice con claridad y te indica
qué instalar.

> **Toma `0.2.1` o más nuevo.** `0.2.0` escribe un workflow de release
> que GitHub rechaza en el momento en que subes tu primera etiqueta,
> así que una compilación `0.2.0` no puede completar esta página. Si
> `--version` dice `0.2.0`, vuelve a ejecutar la línea de
> `cargo install` de [Instalar la CLI](install-cli.md) antes de seguir.

También necesitas un repositorio de GitHub **público**. Las
attestations se publican en un registro de transparencia público; en un
repositorio privado necesitan GitHub Enterprise, y el workflow de
release te lo dirá en lugar de producir en silencio paquetes sin
certificar.

---

## 1 · Scaffold

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

`--lang python` y `--lang typescript` generan el scaffold de los otros
dos SDK; `--template` elige de dónde partes (`tool`, `tts`, `stt`,
`stt-streaming`, `ai-provider`, `ui`, `action-trigger`, `client`,
`blank`). Escribir el plugin en sí es
[Primeros pasos](2-tutorial/getting-started.md) y las
[páginas de SDK](4-sdk/rust.md).

**Rellena dos campos en `plugin.toml` antes de seguir.** El scaffold
deja `author` vacío y `description` genérico, y ambos terminan en tu
tarjeta de la tienda:

<!-- doctest: illustrative reason="a fragment of the scaffolded plugin.toml showing the two fields to edit; a complete manifest is checked by the toml-manifest block in reference/manifest.md" -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "An Astra plugin"     # ← what a person reads on the card
author = ""                         # ← fill this in
license = "MIT"                     # ← must be on the registry's SPDX allowlist
```

El `icon.svg` que escribe el scaffold es un marcador de posición;
reemplazarlo es
[Conseguir el listado §cómo se verá tu listado](5-publish/get-listed.md#cómo-se-verá-tu-listado).

## 2 · Demostrar que funciona

<!-- doctest: cli -->
```bash
astra-plugin test .
```

Esta es la suite de conformidad, ejecutada contra tu plugin como un
**proceso real** hablando con un daemon simulado — no contra un tipo en
tu archivo de pruebas. Truncado a su veredicto:

<!-- doctest: output from="astra-plugin test ." -->
```
  Registered: port 37173, protocol 1, sdk astra-plugin-sdk-rust 0.6.0
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] CallTool                 required  `hello` answered
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 42.1ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 837.6µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] a call without the daemon's token is refused: HealthCheck without `x-plugin-token` answered UNAUTHENTICATED
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.1ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 1 host call(s) reached the daemon: log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 6 hook(s) exercised, 7 check(s) passed.
```

Para ejercitarlo dentro de un Astra en ejecución en su lugar,
`astra-plugin dev .` — eso es [sideload](5-publish/sideload.md), el
bucle de creación, y **no** es una forma de darle el plugin a nadie
más.

## 3 · Configurar el workflow de release

No escribes YAML. Un comando lo hace:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned e3329df252a46d747676cb540ae4b986af68a3ad (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

Ese SHA de commit no es decorativo. Es a lo que apunta el workflow
reutilizable publicado `plugin-release/v1`, y es uno de los SHA que
permite el `trust.json` firmado por la raíz del registro — un build
producido por cualquier otro workflow se rechaza con
`E_WORKFLOW_NOT_ALLOWED`. Vuelve a ejecutar `init-ci` en cualquier
momento para avanzar el fijado; conserva las entradas que configuraste.

**Comprueba el SHA que imprimió antes de continuar.** Debe ser
`e3329df252a46d747676cb540ae4b986af68a3ad`. Si es
`dc1a044876926e9cf1170f034e2eab533ec07641`, estás en la CLI `0.2.0`: ese
es el SHA del *objeto de la etiqueta*, y `uses: …@<sha>` necesita un
commit, así que tu primer `git push --tags` falla con
`invalid value workflow reference` antes de que arranque ningún job.
Vuelve a ejecutar la línea de `cargo install` de
[Instalar la CLI](install-cli.md), luego ejecuta
`astra-plugin init-ci` de nuevo — reescribe el fijado y conserva tus
entradas. Nada se repara en su sitio, así que un `release.yml`
existente conserva el SHA malo hasta que lo vuelvas a ejecutar. Este es
el bug que rompió el primer release de un autor real.

Detalle, incluyendo qué contiene el archivo generado y por qué es
necesario cada uno de sus tres permisos:
[Publicar release con CI](5-publish/release-with-ci.md).

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` aplica lo que se pueda arreglar mecánicamente. `--resolve-pin`
le pregunta a GitHub si el fijado de tu workflow sigue siendo el
actual; está desactivado por defecto para que ni `dev` ni la CI
necesiten red para ejecutar una comprobación.

## 4 · Subirlo, en público

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin check --strict
```

Nada en este paso tiene nada de especial — es un repositorio normal.
Pero nota lo que *no* es: subir esto no publica el plugin, y detenerse
aquí es donde se equivocaron las dos solicitudes reales que motivaron
esta página. Lo que lo convierte en un plugin publicado es la etiqueta
del siguiente paso.

## 5 · Etiquetar — esto es el release

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" -->
```
Setting version to 0.2.0 (plugin.toml was 0.1.0)
  plugin.toml                    [plugin] version           0.1.0 -> 0.2.0
  Cargo.toml                     [package] version          0.1.0 -> 0.2.0
  2 file(s) rewritten

Release it:
  git commit -am "release 0.2.0"
  git tag v0.2.0
  git push && git push --tags

  The tag must be exactly 'v0.2.0': the release workflow asserts it
  against plugin.toml before it builds anything.
```

`astra-plugin version` reescribe `plugin.toml` **y** cualquier otro
manifiesto del proyecto en una sola edición — `Cargo.toml`,
`package.json`, `pyproject.toml` — para que no puedan discrepar.
Rechaza una versión que ordene por debajo de la actual a menos que
pases `--allow-downgrade`, porque Astra se niega a instalar un
downgrade y ese release sería no instalable.

**La etiqueta es todo el proceso de release.** Subirla arranca tu
`release.yml`, que llama al workflow reutilizable fijado, que ejecuta
tres jobs — un job `plan` que lee tu manifiesto como datos y nunca
ejecuta tu código, una matriz `build` que ejecuta tu código y no tiene
ningún token de escritura, y un job `publish` que vuelve a derivar
cada digest por sí mismo y certifica lo que hasheó. Esa separación es
la propiedad de seguridad, y está descrita en
[Publicar release con CI §3](5-publish/release-with-ci.md#3-qué-hace-la-ci).

Cuando termina, tu Release de GitHub lleva:

<!-- doctest: illustrative reason="the asset names a release ends up with; they are produced by GitHub Actions in the author's own repository, so there is no local command that emits this listing" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
dice-roller-0.1.0-windows-x64.astraplugin
dice-roller-0.1.0.sigstore.jsonl
SHA256SUMS.txt
```

El Release solo se hace visible cuando cada asset está adjunto. Los
plugins de Rust obtienen un archivo por plataforma; TypeScript y Python
obtienen un único archivo `noarch`.

**Si el workflow no se ejecutó en absoluto**, la causa habitual es que
`on: push: tags:` y `tag-prefix:` no coinciden — un glob más estrecho
que el prefijo nunca dispara. El resto de los modos de fallo están en
[Publicar release con CI §cosas que pueden salir mal](5-publish/release-with-ci.md#cosas-que-pueden-salir-mal).

## 6 · Comprobar el release tú mismo

Cualquiera puede hacerlo, sin confiar en Astra ni en el registro:

<!-- doctest: cli -->
```bash
gh release download v0.1.0 --repo you/dice-roller --pattern "*.astraplugin"
gh attestation verify dice-roller-0.1.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
  schema:          astra.bundle/2
  plugin:          dice-roller v0.1.0
  target:          linux-x64 (os=linux, arch=x86_64)
  protocol:        1
  capabilities:    tools
  entry:           ./bin/dice_roller
  permissions:     sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
  artifact sha256: 7f77e3f02a83fdcad96e62b9748c3265b6506e9800e432d0270009bdb4c9fbc3
  manifest digest: a2cc2e1bd38538ca5f087fd0f00efd74328b5b5852c6144ead3849c74e86980d
  size:            2730916 bytes (2666.9 KB)
  legacy in-ZIP signature: absent

  4 listed files:
    0644       1063  a9288520e75b02d6  README.md
    0755    8729640  982348bb71764594  bin/dice_roller
    0644       2509  70e9035f388492b0  icon.svg
    0644       1334  acb85afb406f182c  plugin.toml
  1 unlisted entries: MANIFEST.json

  OK — MANIFEST.json is entry 0 and stored, the file list is exhaustive in both
       directions, and every listed digest, size and mode matches the archive.
```

`astra-plugin verify` sale con **1** cuando el paquete está mal y con
**2** cuando la CLI no pudo responder — un archivo faltante, por
ejemplo. El formato del archivo y qué debe rechazar un verificador
está en [`spec/bundle-v2.md`](spec/bundle-v2.md).

## 7 · Preflight del listado

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

Ejecuta cada comprobación del registro que puede correr en local, y
luego — la mitad que importa — nombra las que solo el registro puede
ejecutar, para que sepas qué queda por demostrar:

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the release assets are served from your repository's own release namespace
  · that you have admin or maintain on the repository
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

## 8 · Enviar, una sola vez, para siempre

<!-- doctest: cli -->
```bash
astra-plugin publish
```

Abre un **issue prerrellenado en el registro** en tu navegador. No sube
nada y no guarda ninguna credencial — no existe `astra-plugin login`,
ningún token en el historial de tu shell, ningún llavero con el que
integrarse. `--print-url` imprime el enlace en lugar de abrir un
navegador:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

> **Usa ese enlace.** El `template=plugin-listing.yml` que lleva es
> estructural: la plantilla del issue declara
> `labels: ["listing", "needs-triage"]`, y el bot del registro solo
> entra en la vía de envío para un issue que lleve la etiqueta
> `listing`. Nadie más la aplica — tampoco el bot, y eso es deliberado:
> en ese repositorio la etiqueta es un token de autoridad, no una
> categoría.
>
> Antes eso fallaba en silencio. Dos solicitudes de un autor real
> llegaron sin etiquetas, el triage devolvió `mode: "none"`, los pasos de
> comprobación, publicación y comentario se omitieron todos, y **no
> obtuvo respuesta alguna, ni siquiera un rechazo** — que es la razón por
> la que existe esta página. Ambas mitades están cerradas ahora: el
> registro desactiva los issues en blanco, así que el formulario es la
> única puerta, y una solicitud que aun así llegue sin etiqueta recibe un
> comentario que nombra la etiqueta y el único clic que arranca la
> verificación en ese mismo issue. Usa el enlace de todos modos: es la vía
> que inicia una ingesta sin que nadie tenga que intervenir.

El envío lleva **dos hechos**: tu repositorio fuente
(`you/dice-roller`) y la etiqueta de release (`v0.1.0`), más dos
confirmaciones — que eres dueño o mantenedor del repositorio, y que has
leído la política. Todo lo demás se lee del paquete certificado, porque
todo en el paquete está cubierto por la attestation y por tanto vale
estrictamente más que cualquier cosa escrita en un formulario.

## 9 · Qué pasa después

Detalle, incluyendo cada código de motivo:
[Conseguir el listado §qué pasa después de enviar](5-publish/get-listed.md#3-qué-pasa-después-de-enviar).
La versión corta:

| Resultado | Significa | Quién está involucrado |
|---|---|---|
| **Published** | Confirmado, y en el catálogo en la próxima compilación del índice | nadie |
| **Delayed** | Todo pasó; se publica solo en un momento indicado | nadie |
| **Held** | Una decisión que el registro no está autorizado a tomar automáticamente | un mantenedor, en **48 h** |
| **Refused** | Una comprobación falló | tú: arréglalo y comenta `/recheck` en el issue |

**Un primer listado siempre se retiene para una persona** — ese es uno
de exactamente tres eventos que necesitan una, junto con un permiso de
alto riesgo recién solicitado y un cambio de repositorio. 48 horas es
el SLA publicado para todos ellos.

Un hold se libera cuando un mantenedor comenta `/approve` en tu issue,
lo que vuelve a ejecutar cada comprobación desde cero en lugar de
confiar en nada en caché. Tú no escribes ese comando y no necesitas
hacer nada mientras esperas. Consulta
[cómo se libera un hold](5-publish/get-listed.md#cómo-se-libera-un-hold).

El bot comenta en tu issue con el resultado y el motivo en cualquier
caso — y ahora comenta incluso cuando *no* va a empezar, que es
justamente el fallo del paso 8. Si nada ha comentado dentro de una hora,
comprueba la etiqueta `listing`. Si falta, pide a un maintainer que la
añada: etiquetar dispara el mismo evento que un envío nuevo, así que la
verificación arranca en ese mismo issue sin nada que reescribir.

## 10 · Cada release a partir de ahí

Nada. Etiqueta, y la CI hace el resto; el registro nota el release y
regenera el índice.

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

Si el registro no lo ha notado en unos minutos:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

Ese es el ping manual para un plugin que **ya está listado**. Sin
`--notify`, `publish` abre en su lugar una solicitud de primer listado,
que no es lo que quieres en tu segundo release.

---

## Qué establece la confianza

`astra-plugin build` enlaza aquí, así que la respuesta vive en este
ancla hasta que ese enlace se mueva.

**No ninguna clave que tengas tú.** `astra-plugin keygen` y
`astra-plugin sign` producen un segundo factor opcional — útil frente a
un robo de cuenta de GitHub, porque la clave vive en un sitio donde una
sesión de GitHub robada no está. Astra no la verifica contra tu clave:
el daemon comprueba el par `SIGNATURE`/`PUBKEY` dentro del ZIP contra
una *clave de publicador de Astra fijada*, así que un paquete firmado
con tu propia clave es tan poco fiable como uno sin firmar. Tanto el
comando como las entradas de formato que escribe están siendo
retirados.

**Sobre lo que realmente actúa Astra** es un registro del registry que
contrafirma el SHA-256 del archivo completo, y — comprobado por el bot
del registro en la ingesta, no por el daemon — la attestation de
compilación de GitHub que dice qué workflow, en qué commit, en qué
repositorio produjo esos bytes.

**Hasta dónde está anclada la cadena hoy.** Las claves raíz existen en
ambos lados: `astra-registry/registry/v1/root.json` lleva
`"status": "provisioned"` y dos claves Ed25519, y
`PRODUCTION_ROOT_KEYS` del daemon compila las mismas dos.
`registry/v1/trust.json` ahora está firmado por `astra-root-2026a` y
delega en una clave de firma de índice, `astra-index-2026a` —
verificado con el propio
`node tools/sign-trust.mjs --verify registry/v1/trust.json` del
registro, que también imprime el único SHA de workflow reutilizable
que el bot aceptará en una attestation
(`e3329df252a46d747676cb540ae4b986af68a3ad`, el commit al que apunta
`plugin-release/v1`). **El enlace que todavía falta es la firma del
propio catálogo:** `registry/v1/index.json` y `revocations.json`
llevan `"signatures": []`, así que una compilación por defecto de
Astra no tiene nada que comprobar y clasifica cualquier catálogo como
sin firmar. Nada aquí promete una garantía que todavía no esté en su
sitio; consulta [el modelo de seguridad](1-orientation/security.md) y
[`spec/registry-index.md` §0.1](spec/registry-index.md).

**Nada de esto dice que el código sea seguro.** Un plugin es un proceso
nativo con todos tus privilegios de usuario; no hay sandbox. Un listado
no es una revisión de seguridad — nadie lee tu código, y el registro lo
dice en su propia política.

---

## Las otras dos formas en que un plugin llega a una máquina

Ambas son para desarrolladores, ambas cuestan algo, y **ninguna de las
dos es publicar**:

- [Instalar un archivo `.astraplugin` local](5-publish/local-install.md)
  — un paquete que llegó fuera del registro. Cuatro permisos se
  rechazan de plano, pida lo que pida el manifiesto.
- [Sideload de un directorio fuente](5-publish/sideload.md) — el
  bucle de creación. Requiere el modo desarrollador, ejecuta código sin
  firmar con tu cuenta de usuario completa, y nunca arranca
  automáticamente.

## Ver también

- [Instalar la CLI](install-cli.md) — de dónde viene cada comando de esta página
- [Publicar release con CI](5-publish/release-with-ci.md) — el workflow, completo
- [Conseguir el listado](5-publish/get-listed.md) — el envío y lo que le sigue
- [Versionado](versioning.md) — qué significan los números y cuánto dura una obsolescencia
- [`spec/bundle-v2.md`](spec/bundle-v2.md) · [`spec/registry-index.md`](spec/registry-index.md)
</content>
