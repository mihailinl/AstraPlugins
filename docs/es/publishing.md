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
el paquete y lo certifica, y lo envías una vez, en el
panel — una sola vez, para siempre.

Estas cosas **no** son publicar, y cada una se ha intentado:

| No es publicar | Por qué no puede funcionar |
|---|---|
| Subir tu código fuente a GitHub | El registro nunca lee tu árbol de fuentes. Lee un archivo `.astraplugin` adjunto a un release, y no hay ninguno |
| Enviarle a alguien un `.zip`, o un paquete que compilaste en tu portátil | Los bytes no llevan attestation de compilación, así que el registro los rechaza por bueno que sea el plugin |
| Pedirle a un mantenedor que lo compile por ti | Nadie compila tu plugin salvo la propia CI de tu repositorio. No hay otro compilador |
| Describir tu plugin al registro en cualquier sitio que no sea la página de envío del panel | El registro actúa sobre un envío hecho en el panel, con la sesión iniciada, para un repositorio vinculado a tu cuenta. No hay otra puerta. Consulta [Enviar](#8--enviar-una-sola-vez-para-siempre) |

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
**[Instalar la CLI](install-cli.md)**. Ahora hay binarios
precompilados — descarga un archivo para Linux o Windows, compruébalo
contra `SHA256SUMS.txt`, y no hace falta ninguna toolchain. Compilar
desde el código fuente sigue funcionando y es la vía en macOS y ARM
Linux. `cargo install astra-plugin-cli` no es una vía en absoluto; esa
página explica por qué.

> **No leas la salud de tu compilación en el número de versión.** Una CLI
> compilada antes del commit `5b8ab22` escribe un workflow de release que
> GitHub rechaza en el momento en que subes tu primera etiqueta. Ese
> arreglo llegó a `master` *antes* del salto a `0.2.1`, así que una
> compilación puede llevarlo y aun así imprimir `0.2.0`, y ninguna `0.2.1`
> carece de él. Instalar hoy desde `master` te da el arreglo diga lo que
> diga el número. Lo que de verdad lo zanja es el SHA que imprime
> `init-ci`, y esta página lo ejecuta en el
> [paso 3](#3--configurar-el-workflow-de-release).

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

<!-- doctest: output from="astra-plugin new dice-roller" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
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

<!-- doctest: output from="astra-plugin test ." unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
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

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned c3f342469d186ef48458992930bf1b7c583c78d4 (plugin-release/v1)
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

**Comprueba el SHA que imprimió antes de continuar.** Debe ser el commit
al que apunta hoy `plugin-release/v1`, y lo único que puede decírtelo es el
remoto: `git ls-remote https://github.com/mihailinl/AstraPlugins.git
refs/tags/plugin-release/v1 'refs/tags/plugin-release/v1^{}'` — ambos
refspecs, y la línea pelada `^{}` gana cuando el remoto envía una, que es
exactamente el par que pide `init-ci`. Si tu fijado no coincide, vuelve a
ejecutar la línea de `cargo install` de [Instalar la CLI](install-cli.md),
luego ejecuta `astra-plugin init-ci` de nuevo — reescribe el fijado y
conserva tus entradas. Nada se repara en su sitio, así que un `release.yml`
existente conserva el SHA obsoleto hasta que lo vuelvas a ejecutar. El
resto es historia, y con fecha: `plugin-release/v1` fue una etiqueta
anotada del 2026-08-11 al 2026-08-19, una CLI anterior al commit `5b8ab22`
fijaba su objeto de etiqueta `dc1a044876926e9cf1170f034e2eab533ec07641`
donde GitHub necesita un commit, y ese es el bug que rompió el primer
release de un autor real con `invalid value workflow reference` antes de
que arrancara ningún job; hoy la etiqueta es ligera, así que ninguna
compilación informa ya de ese SHA.

Detalle, incluyendo qué contiene el archivo generado y por qué es
necesario cada uno de sus tres permisos:
[Publicar release con CI](5-publish/release-with-ci.md).

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  REGISTRY WARN: B_UNBOUND predicted once this listing needs a binding: there is no .well-known/astra-plugin-owner at the repository root (working tree). From the registry's cutover every first listing needs one, and every listing after the binding deadline; a release without it is refused B_UNBOUND. Mint a token in the panel and run `astra-plugin init-ci --binding <token>` — https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository
  NOT CHECKED: B_BINDING_UNUSABLE, B_OWNER_CHANGED, B_REPOSITORY_RECYCLED, E_WORKFLOW_NOT_ALLOWED — only the registry can answer these, from the plugins service, GitHub and trust.json
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` aplica lo que se pueda arreglar mecánicamente. `--resolve-pin`
le pregunta a GitHub si el fijado de tu workflow sigue siendo el
actual; está desactivado por defecto para que ni `dev` ni la CI
necesiten red para ejecutar una comprobación.

## 4 · Subirlo, en público — con el archivo de propiedad

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin init-ci --binding <token>
git add .well-known && git commit -m "Bind this repository to my Minice account" && git push
astra-plugin check --strict
```

Las tres primeras líneas no tienen nada de especial — es un repositorio
normal. Pero fíjate en lo que *no* es: subir esto no es publicar el plugin, y
quedarse aquí es donde se torcieron los dos envíos reales que motivaron esta
página. Lo que lo convierte en un plugin publicado es la etiqueta del paso
siguiente.

**La línea de vinculación es la prueba de propiedad, y no es opcional.** Entre
la subida e `init-ci`, inicia sesión en https://astra.minice.ai/plugins con la
cuenta de Minice que va a publicar y genera un token de vinculación para
`you/dice-roller` — el panel busca el repositorio en GitHub, por eso tiene que
estar subido antes. `init-ci --binding` escribe el token como primera línea de
`.well-known/astra-plugin-owner` en la raíz de tu repositorio; con commit en tu
rama por defecto, es como el registro sabe qué cuenta habla por este
repositorio, que es lo único que la certificación de build no puede decir. Si
la dejas fuera, tu primer envío se rechaza con `B_UNBOUND`.

Cuando hayas etiquetado en el paso siguiente, `astra-plugin check --tag v0.1.0`
vuelve a leer la línea desde el commit de la etiqueta, como lo hará el registro.
El token es público y no autentica ningún release, así que nunca fusiones una
línea de vinculación que no hayas generado tú. Qué registra, cuánto dura y qué le
hace un cambio de nombre está en
[Conseguir el listado — Vincula tu repositorio](5-publish/get-listed.md#vincula-tu-repositorio).

## 5 · Etiquetar — esto es el release

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" unrun="rewrites every manifest in a plugin project; re-run it in your own plugin" -->
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
[Publicar release con CI §3](5-publish/release-with-ci.md#3--qué-hace-la-ci).

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

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" unrun="needs that exact bundle, which is a build artefact and is not committed anywhere" -->
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

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

De esa lista, el veredicto de vinculación es el que decide tu propio trabajo, y
lo resolviste en el
[paso 4](#4--subirlo-en-público--con-el-archivo-de-propiedad). El resto
viene de haber etiquetado un release que compiló el workflow.

## 8 · Enviar, una sola vez, para siempre

**Antes de ejecutar esto**, vuelve a leer la línea de vinculación desde tu
etiqueta, exactamente como lo hará el registro. Es la única comprobación de esta
página que puedes suspender habiendo hecho bien todo lo demás:

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
astra-plugin publish
```

`publish` abre la **página de envío** del panel en tu navegador, con el
repositorio y la etiqueta ya rellenados. No sube nada y no guarda ninguna
credencial — no hay `astra-plugin login`, ni token en tu historial de shell, ni
llavero con el que integrarse. La página no envía nada hasta que lo hagas tú,
con la sesión iniciada en la cuenta de Minice a la que está vinculado tu
repositorio. `--print-url` imprime el enlace en lugar de abrir un navegador:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

El envío lleva **dos datos**: tu repositorio de origen (`you/dice-roller`) y
la etiqueta del release (`v0.1.0`). Todo lo demás se lee del paquete
certificado, porque todo lo que hay en el paquete está cubierto por la
certificación y vale por tanto estrictamente más que cualquier cosa escrita en
un formulario.

## 9 · Qué pasa después

Detalle, incluido cada código: [Conseguir el listado §qué pasa después de
enviar](5-publish/get-listed.md#3--qué-pasa-después-de-enviar). La versión
corta: el panel muestra el estado del envío, y los mismos momentos te llegan
como avisos — a la dirección de correo verificada de tu cuenta de Minice y en
el panel, y por Telegram solo si lo has vinculado.

| Resultado | Significa | Quién interviene |
|---|---|---|
| **Publicado** | Confirmado, y luego en el catálogo firmado | nadie |
| **Retrasado** | Todo pasó; se publica solo a la hora que muestra el panel | nadie |
| **Retenido** | Una decisión que el registro no tiene derecho a tomar automáticamente | un moderador, en el panel |
| **Rechazado** | Una comprobación falló | tú: arréglalo y luego Recheck en el panel o vuelve a etiquetar, según diga el código |

**Un primer listado siempre se retiene para una persona** — uno de exactamente
tres eventos que la necesitan, junto con un permiso de alto riesgo recién
solicitado y un cambio de repositorio o de vinculación. Un moderador lo aprueba
o lo rechaza en el panel; tú no haces nada mientras esperas. Ninguna aprobación
acorta un retraso, y el `docs/POLICY.md` del registro publica las reglas.

## 10 · Cada release a partir de ahí

Nada. Etiqueta y la CI hace el resto; el registro detecta por sí mismo la
etiqueta nueva de un plugin listado, y el panel muestra su estado.

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

No hay nada que enviar ni nada que avisar. Un release que no ha aparecido está
en la página de tu plugin en el panel, con su estado y el motivo.

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
registro, que también imprime los SHA de workflow reutilizable
que el bot aceptará en una attestation — dos de ellos desde que la etiqueta
se movió el 2026-08-19: el commit al que apunta `plugin-release/v1`, y
aquel al que apuntaba antes. Desde el 2026-09-20 el catálogo que reciben
los clientes está firmado con esa clave; las copias confirmadas en `main` del
registro, `registry/v1/index.json` y `revocations.json`, llevan
`"signatures": []` a propósito, y ningún cliente las lee. **El enlace que
todavía falta es una lista de retirada firmada en Pages**, así que la
revocación todavía no se aplica. Nada aquí promete una garantía que todavía no esté en su
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
