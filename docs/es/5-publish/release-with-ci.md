> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/5-publish/release-with-ci.md) es la referencia autorizada.

# Publicar release con CI

**Una etiqueta (tag) es todo el proceso de release.** Un comando lo
configura, y después de eso nunca vuelves a compilar un paquete a mano.

Todo en esta página parte del binario `astra-plugin`. Si no lo tienes,
[instala primero la CLI](../install-cli.md) — una línea de
`cargo install`, se necesita una toolchain de Rust, todavía sin binarios
precompilados. Para ver todo el recorrido en una sola página en lugar de
solo esta etapa, consulta [Publicar un plugin](../publishing.md).

## ¿Por qué no simplemente `astra-plugin build` y subirlo?

Porque nada responde por un archivo que compilaste en tu portátil. El
registro lee la **attestation de compilación** de GitHub — una firma
Sigstore keyless, acuñada a partir de la identidad OIDC del workflow —
que dice *estos bytes exactos vinieron de ese workflow, en ese commit, en
ese repositorio*. Un paquete compilado a mano no lleva nada de eso y se
rechaza por bueno que sea — con `E_ATTESTATION_MISSING`, por su nombre.

Por la misma razón, **subir tu código fuente a GitHub no es hacer un
release**, ni tampoco enviarle a alguien el `.astraplugin` que compilaste
en local. El registro nunca lee tu árbol de fuentes; lee los assets de un
release etiquetado, y los fija por digest.

No necesitas, ni se te pide, una clave de firma. Consulta
[el modelo de seguridad](../1-orientation/security.md).

## 1 · Escribir el workflow

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

**Esto funciona hoy, y cada mitad de esa afirmación es comprobable.**
`.github/workflows/plugin-release.yml` está en la rama por defecto de
`mihailinl/AstraPlugins` — `git ls-tree -r master --name-only
.github/workflows` lo lista — y la etiqueta publicada existe:
`git ls-remote --tags origin` resuelve `plugin-release/v1` a
`e3329df252a46d747676cb540ae4b986af68a3ad`. Como la etiqueta existe,
`init-ci` fija (pin) ese commit en lugar de una cabeza de rama móvil, y ya
no imprime el aviso "Not verified" que citaban versiones anteriores de
esta página.

Ese SHA es el mismo que el `trust.json` firmado por la raíz del registro
permite en una attestation de compilación —
`node tools/sign-trust.mjs --verify registry/v1/trust.json` en
`astra-registry` lo imprime bajo *reusable-workflow SHAs it allows*. Un
build producido por cualquier otro workflow se rechaza en la ingesta con
`E_WORKFLOW_NOT_ALLOWED`, así que el fijado no es un detalle cosmético; es
lo que hace que tu attestation signifique algo sobre lo que el registro
puede actuar.

Vuelve a ejecutar `init-ci` cada vez que se publique un `plugin-release/vN`
más nuevo; conserva tus entradas y solo mueve el fijado.

Esa es toda la CI del lado del autor. Es corta porque delega:

<!-- doctest: illustrative reason="the file `astra-plugin init-ci` writes; it lives in the author's repository, not in this one, and its pin is resolved at generation time" -->
```yaml
name: Release

on:
  push:
    tags: ["v*"]

# Required, and required HERE: a reusable workflow can only reduce the
# permissions its caller granted, never grant itself more. Leave all three.
permissions:
  contents: write       # create the Release and upload assets
  id-token: write       # mint the OIDC token that makes signing keyless
  attestations: write   # store the build attestation on GitHub

jobs:
  release:
    # Pinned by commit SHA, not by a moving tag: whoever can move
    # `plugin-release/v1` in mihailinl/AstraPlugins would otherwise own the build
    # step of every plugin that trusts it — and that build step runs in YOUR
    # repository with the token above. `astra-plugin init-ci` keeps this current.
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@e3329df252a46d747676cb540ae4b986af68a3ad  # plugin-release/v1
    with:
      plugin-dir: .
      tag-prefix: "v"
      linux-packages: ""      # e.g. "libasound2-dev pkg-config" for audio plugins
    # No `secrets: inherit`, deliberately. This workflow declares no secrets,
    # so the job that runs your build.rs and your npm lifecycle scripts has
    # nothing to leak.
```

Vuelve a ejecutar `init-ci` para avanzar el fijado; conserva las entradas
que configuraste. `--offline` mantiene el fijado ya presente en el
archivo, y `--ref <sha-or-ref>` fija algo específico.

## 2 · Etiquetar (tag)

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

`astra-plugin version` reescribe `plugin.toml` **y** cualquier otro
manifiesto del proyecto en una sola edición — `Cargo.toml`,
`package.json`, `pyproject.toml` — para que no puedan discrepar. Rechaza
una versión que ordene por debajo de la actual a menos que pases
`--allow-downgrade`, porque Astra se niega a instalar un downgrade y ese
release sería no instalable.

La etiqueta debe coincidir con `tag-prefix` más la versión del
manifiesto, y la CI lo comprueba antes de compilar nada.
`astra-plugin version` imprime la etiqueta exacta a usar:

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

## 3 · Qué hace la CI

Esta sección describe `.github/workflows/plugin-release.yml` tal como
está escrito en este repositorio, en `master`, en el commit al que apunta
`plugin-release/v1` — que es el commit que llama tu `release.yml`.

Tres jobs, y la separación es la propiedad de seguridad.

| Job | Ejecuta tu código | Tiene un token de escritura | Qué hace |
|---|---|---|---|
| **plan** | **no** | sí | Lee `plugin.toml` con `tomllib` de Python como *datos*, comprueba tag == version, decide la matriz de build, crea el Release en borrador |
| **build** (matriz) | sí | **no** | `astra-plugin check --strict`, `astra-plugin build`, verify, desempaqueta, verifica el piso de glibc y que el paquete TypeScript sea autocontenido |
| **publish** | no | sí | Vuelve a derivar cada digest por sí mismo, escribe `SHA256SUMS.txt`, certifica, sube, saca el Release del estado de borrador |

`plan` nunca ejecuta nada fuera del repositorio — sin submódulos, sin
credenciales persistidas en `.git/config`. `build` ejecuta tu `build.rs`
y tus scripts de ciclo de vida de npm y no tiene ningún token que robar.
`publish` descarga los artefactos, los hashea él mismo, y certifica lo
que hasheó.

La matriz se decide a partir del lenguaje de tu plugin: `linux-x64` +
`windows-x64` para Rust, una sola rama `noarch` para TypeScript y Python.

### Qué termina en el Release

| Asset | |
|---|---|
| `<id>-<version>-linux-x64.astraplugin` | uno por clave de plataforma |
| `<id>-<version>-windows-x64.astraplugin` | |
| `<id>-<version>.sigstore.jsonl` | el paquete de attestation, para que un usuario sin acceso a GitHub aún pueda comprobar |
| `SHA256SUMS.txt` | los mismos digests que registra el registro |

El Release solo se hace visible cuando cada asset está adjunto.

### La attestation necesita un repositorio público

Las attestations de compilación se publican en un registro de
transparencia público; en un repositorio privado requieren GitHub
Enterprise. El workflow resuelve la visibilidad de tu repositorio y,
cuando no es público, lo dice en el resumen del job y produce paquetes
**sin certificar** — que el registro no listará. Esa es una restricción
real, y falla con estruendo en lugar de producir un release que parece
correcto.

### Reproducibilidad

`astra-plugin build --reproducible` garantiza un empaquetado
determinista: entradas ordenadas, un mtime fijo, un nivel de compresión
fijo. Dos compilaciones desde las mismas entradas producen el mismo
sha256. La CI ejecuta un canario de reproducibilidad en cada release, lo
que hace significativa la recompilación por parte de un tercero.

## 4 · Comprobarlo tú mismo

Cualquiera puede verificar un release sin confiar en Astra ni en el
registro:

<!-- doctest: cli -->
```bash
gh attestation verify dice-roller-0.2.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.2.0-linux-x64.astraplugin
```

`astra-plugin verify` lee el propio paquete e imprime lo que encontró:

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

Los códigos de salida importan aquí, y cada workflow de release
ramifica según ellos: **1** significa que el paquete está mal, **2**
significa que la CLI no pudo responder — un archivo faltante, por
ejemplo. El formato del archivo, y qué debe rechazar un verificador, está
en [`spec/bundle-v2.md`](../spec/bundle-v2.md).

## 5 · Luego conseguir el listado

Una vez. → [Conseguir el listado](get-listed.md).

## Cosas que pueden salir mal

| Síntoma | Causa |
|---|---|
| El workflow nunca arranca | `on: push: tags:` y `tag-prefix:` no coinciden. Un glob más estrecho que el prefijo nunca dispara |
| "tag does not match the manifest version" | Ejecuta `astra-plugin version <v>` y haz commit antes de etiquetar |
| El build de Linux falla por una cabecera faltante | Configura `linux-packages: "libasound2-dev pkg-config"` en el workflow que llama |
| El paquete no está certificado | El repositorio es privado |
| `MODULE_NOT_FOUND` en el primer arranque | Una dependencia de TypeScript que el bundler no pudo seguir. La CI verifica esto; revisa los externals del bundler |
| Un error de glibc en la máquina de un usuario | Algo en el archivo necesita un símbolo por encima de `GLIBC_2.39`. La CI también verifica esto |
| `invalid value workflow reference` antes de que arranque ningún job | El fijado nombra un commit que no lleva `plugin-release.yml`. Vuelve a ejecutar `astra-plugin init-ci` para refijar a `plugin-release/v1` |
| El registro rechaza el release con `E_WORKFLOW_NOT_ALLOWED` | El build no se ejecutó a través del workflow reutilizable de Astra fijado. Vuelve a ejecutar `init-ci`, vuelve a etiquetar, y deja que la CI recompile |

Más: [solución de problemas](../6-operate/troubleshooting.md).
</content>
