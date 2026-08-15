> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/install-cli.md) es la referencia autorizada.

# Instalar la CLI

Todo en la vía de publicación empieza con un comando, y esta es la
página que te consigue ese comando. El binario se llama
**`astra-plugin`** — no `astra-plugin-cli`, que es solo el nombre del
crate.

## El estado honesto de esto

**Todavía no hay binarios precompilados, y `astra-plugin-cli` no está en
crates.io.** Verificado hoy: `https://index.crates.io/as/tr/astra-plugin-cli`
responde `404`, mientras que `astra-plugin-sdk` en el mismo índice
responde `200`, así que es una ausencia real y no una búsqueda fallida.
`gh release list --repo mihailinl/AstraPlugins` no imprime nada.

Así que la única forma de conseguir la CLI es compilarla, y compilarla
necesita una toolchain de Rust. Distribuir binarios precompilados es una
tarea conocida, separada, pendiente — la automatización de release para
ello se está escribiendo ahora, y esta página tendrá una línea de descarga
el día que exista un release que descargar. Hasta entonces describe la
totalidad de lo que existe, y nada aquí te pide descargar nada.

Ese costo es real, y vale la pena nombrar por qué merece pagarse de
todos modos: la CLI no es un envoltorio de conveniencia sobre alguna
otra vía más fácil. Es lo único que escribe un workflow de release
correcto, lo único que evita que tus manifiestos discrepen sobre la
versión, y lo único que abre una solicitud de listado que el bot del
registro realmente verá. Eludirla es cómo dos solicitudes reales
terminaron en silencio — consulta [qué es publicar](publishing.md).

## Requisitos previos

| | Por qué | Comprobar |
|---|---|---|
| **Rust 1.85 o más nuevo** | cada crate aquí es `edition = "2024"`, y 1.85 es el primer release que la entiende | `cargo --version` |
| **`protoc` en el `PATH`** | la CLI depende de `astra-plugin-sdk`, cuyo `build.rs` compila `proto/plugin.proto` con `tonic-build`, que invoca externamente un `protoc` | `protoc --version` |
| **`git`** | `cargo install --git` clona con él | `git --version` |

Ningún crate declara un `rust-version`, y la CI compila en `stable`, así
que la edición es el único piso realmente exigido.

Instalar `protoc`, que es lo que la gente se salta:

<!-- doctest: illustrative reason="OS package-manager commands; the doc-test runner has one OS and installing system packages during a documentation check is not something a CI job should be allowed to do" -->
```
Debian/Ubuntu   sudo apt install protobuf-compiler
Arch            sudo pacman -S protobuf
Fedora          sudo dnf install protobuf-compiler
macOS           brew install protobuf
Windows         winget install Google.Protobuf     (or scoop install protobuf)
```

Sin él, la compilación falla en el script de build de
`astra-plugin-sdk`, y el error nombra la solución:

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release, run in astra-plugin-sdk/ — there is no workspace manifest at the repository root, so `-p astra-plugin-sdk` from the root cannot work" unrun="a full SDK build pointed at a protoc that does not exist; minutes long, and it has to fail to print this" -->
```
  Error: Custom { kind: NotFound, error: "Could not find `protoc`. If `protoc` is installed, try setting the `PROTOC` environment variable to the path of the `protoc` binary. To install it on Debian, run `apt-get install protobuf-compiler`. It is also available at https://github.com/protocolbuffers/protobuf/releases  For more information: https://docs.rs/prost-build/#sourcing-protoc" }
```

## Instalarla

**Una línea, sin clonar.** Esta es la que hay que usar:

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

`--locked` compila contra el `Cargo.lock` guardado en el repositorio en
lugar de volver a resolver cada dependencia a su release más nueva, lo
cual marca la diferencia entre una compilación que funciona igual que
funcionó aquí y una que se topa en tu máquina con un release de parche
que rompe algo.

`--git` compila lo que `master` lleve en ese momento, así que la versión y
el commit que reporta son lo que haya en `master` cuando lo ejecutes. Todo
lo que va entre ángulos abajo cambia según la máquina y según la ejecución
— la versión y el SHA vienen de `master`, las rutas de tu directorio
personal, la duración de tu CPU:

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" unrun="clones over the network and compiles for minutes; a documentation check must not do either" -->
```
   Compiling astra-plugin-cli v<version> (<home>/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in <duration>
  Installing <scratch>/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<short-sha>)` (executable `astra-plugin`)
warning: be sure to add `<scratch>/bin` to your PATH to be able to run the installed binaries
```

Esa transcripción se produjo con `--root <scratch>` para que capturarla no
sobrescribiera el binario instalado de nadie. **Deja `--root` fuera** —
como hace el comando de arriba — y las dos últimas líneas cambian:
`Installing` nombra `<home>/.cargo/bin/astra-plugin`, y el aviso de `PATH`
aparece solo si `~/.cargo/bin` no está ya en tu `PATH`. Los dos SHA son el
mismo commit impreso con dos longitudes distintas, cosa de cargo, no una
discrepancia.

**Desde un clon**, si quieres leer o modificar la CLI además de
ejecutarla:

<!-- doctest: cli -->
```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

Un `git clone` simple hace checkout de `master`, y `master` es donde
está la CLI actual — no hay ninguna rama que necesites conocer.

## Comprobar que funcionó

<!-- doctest: cli -->
```bash
astra-plugin --version
astra-plugin --help
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

El número es un marcador de posición porque ninguna de las dos líneas de
instalación te deja elegir uno: ambas compilan un commit, no un release,
así que lo que obtienes es la versión que está en el `Cargo.toml` de ese
commit. `0.2.1` es la entrada más reciente en
[el changelog de la CLI](../../astra-plugin-cli/CHANGELOG.md), que también
deja constancia de que este crate no tiene tren de releases — ni
crates.io, ni etiqueta, ni binarios.

Si la shell no lo encuentra, `cargo install` lo puso en `~/.cargo/bin`
(o `%USERPROFILE%\.cargo\bin` en Windows) y ese directorio no está en tu
`PATH`. `cargo` imprime un aviso exactamente sobre eso cuando ocurre.

### El bug que rompe un primer release, y cómo saber si tu compilación lleva el arreglo

**`astra-plugin init-ci` fijaba el SHA del *objeto* de una etiqueta anotada
donde GitHub requiere un commit**, así que el primer `git push --tags`
fallaba con `invalid value workflow reference` antes de que arrancara
ningún job. Eso fue
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**El arreglo es el commit `5b8ab22`, no un número de versión**, y esta es
la parte con la que la gente tropieza. Aquí no hay tren de releases — nada
está publicado, así que nadie instala una versión elegida; todo el mundo
compila el commit que clonó. `5b8ab22` llegó a `master` *antes* del salto
que subió el número a `0.2.1`, lo que significa que:

- una compilación hecha desde `master` después de `5b8ab22` **lleva el
  arreglo y aun así imprime `0.2.0`** — eso no es una compilación rota;
- ninguna compilación `0.2.1` puede *carecer* del arreglo, porque
  `5b8ab22` es ancestro del commit del salto de versión;
- una compilación `0.2.0` hecha *antes* de `5b8ab22` es la rota, y
  `--version` no puede distinguirla del primer caso.

Así que `0.2.1` merece la pena — es el primer número que responde la
pregunta por sí solo, que es exactamente para lo que existe — pero un
`0.2.0` que dice `0.2.0` no es evidencia de nada. `0.2.1` no añade ningún
flag ni cambia ninguna API; el único comportamiento que sí cambió es
`publish --notify`, cuyo enlace ahora nombra el formulario de release-ping
del registro en lugar de apoyarse en un issue en blanco que el registro ya
ha desactivado.

Si `--version` imprime `0.2.0`, ejecuta primero `which astra-plugin`
(`where` en Windows): la causa más común es un binario más antiguo por
delante en tu `PATH`, y `--version` por sí sola no puede distinguir eso de
una compilación reciente de un commit más antiguo. Después deja de
adivinar por el número y lee el pin — `init-ci` escribe exactamente aquello
de lo que iba el bug, y responde en una línea.

Esta es la comprobación que no depende de la versión en absoluto:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

Una compilación con el arreglo reporta el fijado
`e3329df252a46d747676cb540ae4b986af68a3ad` — un commit. Una sin él reporta
`dc1a044876926e9cf1170f034e2eab533ec07641`, que es el *objeto* de la
etiqueta `plugin-release/v1` y es lo que GitHub rechaza. Si ves el
segundo, reinstala desde `master` con la línea de arriba y ejecuta
`init-ci` otra vez. Se puede volver a ejecutar sin riesgo: conserva tus
entradas y reescribe el fijado. Nada se repara en su sitio, así que un
`release.yml` existente conserva el SHA malo hasta que lo vuelvas a
ejecutar.

El conjunto de comandos, completo:

<!-- doctest: output from="astra-plugin --help" -->
```
Astra Plugin Development CLI

Usage: astra-plugin [OPTIONS] <COMMAND>

Commands:
  new      Create a new plugin project from a template
  dev      Start a plugin in dev mode (sideload into the running Astra + hot-reload)
  build    Build a plugin into a distributable .astraplugin bundle
  sign     Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle
  verify   Verify a built .astraplugin bundle and print its digests
  test     Run the conformance suite against a real plugin process
  doctor   Answer, in one command, every question asked when a plugin will not start: toolchains, the daemon, the manifest, the entry point, permissions, the platform block, the release workflow
  logs     Read a plugin's output from the daemon that spawned it
  check    Check a plugin manifest, config schema and release workflow
  init-ci  Write .github/workflows/release.yml, pinned to a commit of the Astra reusable workflow. Re-run it to upgrade the pin; it keeps your inputs
  version  Set the version in plugin.toml and every other manifest at once
  publish  Get a release listed: preflight it, or open a prefilled submission
  keygen   Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses
  help     Print this message or the help of the given subcommand(s)

Options:
      --json     Print one JSON document instead of human output. Progress lines are suppressed so the output is safe to pipe
  -h, --help     Print help
  -V, --version  Print version

Exit codes: 0 success · 1 the plugin/bundle is wrong · 2 the CLI could not run the check.
RUST_LOG controls trace output, e.g. RUST_LOG=astra_plugin=debug.
```

No hay **`astra-plugin login`**, y eso es deliberado, no algo sin
terminar: nada en esta toolchain te pide jamás una credencial. Consulta
[Conseguir el listado](5-publish/get-listed.md).

## Mantenerla actualizada

Vuelve a ejecutar la misma línea de `cargo install --git`. Cargo
reemplaza el binario en su sitio. No hay autoactualización, y no la
habrá antes de que existan binarios de release firmados a los que
actualizar.

## Cosas que pueden salir mal

| Síntoma | Causa |
|---|---|
| `Could not find `protoc`` | `protoc` no está en el `PATH`. Consulta la tabla de arriba |
| `feature `edition2024` is required` | Rust anterior a 1.85 |
| `astra-plugin: command not found` tras una instalación exitosa | `~/.cargo/bin` no está en el `PATH` |
| `error: could not find `Cargo.toml`` al ejecutar `cargo install --path .` en la raíz del repositorio | No hay ningún manifiesto de workspace en la raíz. Apunta `--path` a `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | Un `astra-plugin` más antiguo aparece antes en tu `PATH`. `--version` no te dirá cuál es cuál — ejecuta `which astra-plugin` (`where` en Windows) para ver qué archivo estás ejecutando realmente |
| `invalid value workflow reference`, en tu primer push de etiqueta | La CLI que escribió `release.yml` es anterior a `5b8ab22` y fijó un objeto de etiqueta. Consulta [cómo saber si tu compilación lleva el arreglo](#el-bug-que-rompe-un-primer-release-y-cómo-saber-si-tu-compilación-lleva-el-arreglo) |

## Siguiente

- **[Qué es publicar](publishing.md)** — todo el recorrido, de
  directorio vacío a plugin listado, en una página.
- [Primeros pasos](2-tutorial/getting-started.md) — escribir el plugin
  en sí.
</content>
