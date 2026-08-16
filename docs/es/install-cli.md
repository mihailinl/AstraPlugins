> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/install-cli.md) es la referencia autorizada.

# Instalar la CLI

Todo en la vía de publicación empieza con un comando, y esta es la
página que te consigue ese comando. El binario se llama
**`astra-plugin`** — no `astra-plugin-cli`, que es solo el nombre del
crate.

## Dos vías, y cuál quieres

**Descarga el binario.** El release [`cli-v0.2.1`][rel] trae archivos
precompilados para Linux y Windows, un archivo de sumas de verificación,
y un paquete Sigstore que puedes verificar. No hay nada que compilar y no
interviene ninguna toolchain. Esta es la vía que quiere la mayoría de la
gente, y es la de abajo.

**O compila desde el código fuente**, lo cual necesita Rust 1.85 o más
nuevo y `protoc`. Toma esta vía si estás en una plataforma sin archivo —
macOS y ARM Linux, hoy — o si quieres leer o modificar la CLI además de
ejecutarla.

**`cargo install astra-plugin-cli` no es una de las vías, y no
funcionará.** El crate depende de un `astra-plugin-manifest` vendorizado
por ruta (`astra-plugin-manifest = { path = "vendor/astra-plugin-manifest" }`),
cargo nunca empaqueta el código fuente de una dependencia por ruta, y la
publicación por tanto falla con *all dependencies must have a version
requirement specified* — así que el crate no está en crates.io en
absoluto (`https://index.crates.io/as/tr/astra-plugin-cli` responde `404`
hoy, mientras que `astra-plugin-sdk` en el mismo índice responde `200`).
Desbloquearlo significa publicar antes el crate del manifiesto desde
Astra, y esta página no promete una fecha para eso.

[rel]: https://github.com/mihailinl/AstraPlugins/releases/tag/cli-v0.2.1

## Descargar un binario

### Qué archivo

| Estás en | Toma |
|---|---|
| **Cualquier Linux** | `astra-plugin-0.2.1-linux-x64-musl.tar.gz` |
| Linux, y quieres específicamente la compilación glibc | `astra-plugin-0.2.1-linux-x64-gnu.tar.gz` |
| **Windows** | `astra-plugin-0.2.1-windows-x64.zip` |

**musl es la opción segura por defecto, y la razón no es gusto.** La
compilación gnu está enlazada dinámicamente y su tabla de símbolos
requiere **glibc 2.39 o más nuevo**, que Ubuntu 22.04 (2.35), Debian 12
(2.36) y RHEL 9 (2.34) no tienen — en cualquiera de ellos falla al
arrancar en lugar de comportarse mal sutilmente. El archivo musl es un
ejecutable `static-pie` sin ninguna dependencia de libc, así que corre en
cualquiera de ellos. Toma gnu solo si sabes que lo quieres.

La lista completa de assets de ese release, es decir, todo lo publicado:

<!-- doctest: output from="gh release view cli-v0.2.1 --repo mihailinl/AstraPlugins --json assets" unrun="reads a GitHub release over the network; re-run the command in the from= to confirm the list, or open the release page" -->
```
astra-plugin-0.2.1-linux-x64-gnu.tar.gz     3372607
astra-plugin-0.2.1-linux-x64-musl.tar.gz    3425289
astra-plugin-0.2.1-windows-x64.zip          3450755
SHA256SUMS.txt                                  314
astra-plugin-0.2.1.sigstore.jsonl             11414
```

### Descárgalo y verifícalo

Linux, usando `curl` — nada aquí necesita `gh` ni una cuenta de GitHub:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1-linux-x64-musl.tar.gz
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
tar xzf astra-plugin-0.2.1-linux-x64-musl.tar.gz
./astra-plugin-0.2.1-linux-x64-musl/astra-plugin --version
```

Esta es una transcripción real de esos comandos:

<!-- doctest: output from="sha256sum -c --ignore-missing SHA256SUMS.txt" unrun="needs the release archive downloaded next to the checksum file; re-run the two curl lines above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
```

**Usa `--ignore-missing`.** `SHA256SUMS.txt` lista los tres archivos, así
que un `sha256sum -c SHA256SUMS.txt` normal reporta los dos que no
descargaste como `FAILED open or read` y **sale con 1** — que se ve
exactamente como una descarga corrupta y no lo es:

<!-- doctest: output from="sha256sum -c SHA256SUMS.txt" unrun="needs one of the three archives present and the other two absent; re-run the curl lines above and then this one to reproduce it" -->
```
sha256sum: astra-plugin-0.2.1-linux-x64-gnu.tar.gz: No such file or directory
astra-plugin-0.2.1-linux-x64-gnu.tar.gz: FAILED open or read
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
sha256sum: astra-plugin-0.2.1-windows-x64.zip: No such file or directory
astra-plugin-0.2.1-windows-x64.zip: FAILED open or read
sha256sum: WARNING: 2 listed files could not be read
```

El archivo se descomprime en un directorio con el binario y sus archivos
de licencia:

<!-- doctest: output from="tar tzf astra-plugin-0.2.1-linux-x64-musl.tar.gz" unrun="needs the downloaded archive; re-run the curl line above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl/
astra-plugin-0.2.1-linux-x64-musl/LICENSE
astra-plugin-0.2.1-linux-x64-musl/NOTICE
astra-plugin-0.2.1-linux-x64-musl/README.md
astra-plugin-0.2.1-linux-x64-musl/astra-plugin
```

Mueve `astra-plugin` a algún lugar de tu `PATH` — `~/.local/bin` es la
respuesta habitual, y no necesita `sudo`:

<!-- doctest: cli -->
```bash
mkdir -p ~/.local/bin
cp astra-plugin-0.2.1-linux-x64-musl/astra-plugin ~/.local/bin/
astra-plugin --version
```

En Windows, descarga el `.zip` de la página del release, descomprímelo, y
pon `astra-plugin.exe` en tu `PATH`. `certutil -hashfile <file> SHA256`
es la herramienta de sumas de verificación integrada, y su salida se
compara con `SHA256SUMS.txt` a simple vista.

### Verifica quién lo compiló

La suma de verificación demuestra que los bytes coinciden con un archivo
nombrado en el release. No demuestra quién produjo ese archivo — para
eso está el paquete Sigstore, y `gh` lo comprueba contra la attestation
de compilación de GitHub:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1.sigstore.jsonl
gh attestation verify astra-plugin-0.2.1-linux-x64-musl.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins
astra-plugin --version
```

**Un éxito no imprime nada cuando la salida no es un terminal, y sale con
`0`.** Eso desconcierta la primera vez; comprueba `echo $?` en lugar de
buscar una marca. Un fallo es ruidoso y sale con `1`:

<!-- doctest: output from="gh attestation verify tampered.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins" unrun="needs the bundle and a deliberately corrupted copy of the archive; append a byte to the archive and re-run to reproduce it" -->
```
Error: verifying with issuer "sigstore.dev"
```

Eso se produjo añadiendo un byte al archivo; apuntar `--repo` a un
repositorio que no lo compiló falla igual. Un paquete cubre los tres
archivos, y lo que certifica se puede leer con `--format json`: el
workflow que firma es
`https://github.com/mihailinl/AstraPlugins/.github/workflows/release-cli.yml@refs/tags/cli-v0.2.1`,
el issuer es `https://token.actions.githubusercontent.com`, y los tres
digests de subject son las tres líneas de `SHA256SUMS.txt`. `gh
attestation verify` necesita acceso a la red para obtener la raíz de
confianza, pero no un login de GitHub.

## Compilar desde el código fuente

Toma esta vía en macOS o ARM Linux, donde todavía no hay archivo, o para
trabajar en la CLI misma. No es un plan de reserva para una descarga
fallida — el binario de arriba es el mismo programa.

### Requisitos previos

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

### Compílala

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

Para compilar exactamente el código con el que se compilaron los
binarios publicados, en lugar de lo que `master` lleve hoy, primero haz
checkout de la etiqueta del release:

<!-- doctest: cli -->
```bash
git clone --branch cli-v0.2.1 https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

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

Un binario descargado imprime `astra-plugin 0.2.1`, porque el archivo está
compilado desde la etiqueta `cli-v0.2.1` y nada más. `<version>` es un
marcador de posición solo en la vía del código fuente: `cargo install
--git` compila lo que `master` lleve en ese momento, así que lo que
obtienes es la versión que está en el `Cargo.toml` de ese commit, que
puede ir por delante del release más reciente. `0.2.1` es la entrada más
reciente en [el changelog de la CLI](../../astra-plugin-cli/CHANGELOG.md).

Si la shell no lo encuentra: un binario descargado está donde lo hayas
copiado, y `cargo install` pone uno en `~/.cargo/bin` (o
`%USERPROFILE%\.cargo\bin` en Windows). De cualquier forma ese directorio
no está en tu `PATH`. `cargo` imprime un aviso exactamente sobre eso
cuando ocurre.

### El bug que rompe un primer release, y cómo saber si tu compilación lleva el arreglo

**`astra-plugin init-ci` fijaba el SHA del *objeto* de una etiqueta anotada
donde GitHub requiere un commit**, así que el primer `git push --tags`
fallaba con `invalid value workflow reference` antes de que arrancara
ningún job. Eso fue
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**Descargar el binario `0.2.1` resuelve esto, y esa es la respuesta
corta.** El archivo está compilado desde la etiqueta `cli-v0.2.1`,
`5b8ab22` es un ancestro suyo, así que un binario descargado ya lleva el
arreglo. El resto de esta sección es para una compilación desde el
código fuente, donde el número no lo resuelve.

**El arreglo es el commit `5b8ab22`, no un número de versión**, y esta es
la parte con la que la gente tropieza. Una compilación desde el código
fuente instala el commit que clonaste, no un release elegido. `5b8ab22`
llegó a `master` *antes* del salto que subió el número a `0.2.1`, lo que
significa que:

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

Si descargaste un binario, descarga el archivo del siguiente release y
reemplaza el archivo — comprueba la suma de verificación otra vez, ya
que un release nuevo significa bytes nuevos. Si compilaste desde el
código fuente, vuelve a ejecutar la misma línea de `cargo install`, y
cargo reemplaza el binario en su sitio. **No hay autoactualización**, y
nada en esta toolchain llama a casa para descubrir que existe una versión
nueva.

## Cosas que pueden salir mal

| Síntoma | Causa |
|---|---|
| `FAILED open or read` de `sha256sum -c` | Descargaste un archivo y el archivo de sumas lista tres. Añade `--ignore-missing` |
| `Error: verifying with issuer "sigstore.dev"` | El archivo no coincide con el paquete, o `--repo` nombra un repositorio que no lo compiló. Vuelve a descargar en lugar de razonar sobre ello |
| `gh attestation verify` no imprimió nada en absoluto | Eso es un éxito. Es silencioso cuando la salida no es un terminal; `echo $?` muestra `0` |
| El binario no arranca, y el loader se queja de que no encuentra una versión `GLIBC_2.39` | Tomaste el archivo gnu en un sistema con glibc más antiguo. Toma el musl, no necesita libc |
| `error: could not find `astra-plugin-cli` in registry `crates-io` with version `*`` | `cargo install astra-plugin-cli` no puede funcionar, y esto es lo que dice al respecto. Ver el principio de esta página |
| `Could not find `protoc`` | `protoc` no está en el `PATH`. Consulta la tabla de arriba |
| `feature `edition2024` is required` | Rust anterior a 1.85 |
| `astra-plugin: command not found` tras una instalación exitosa | El directorio con el binario no está en el `PATH` — para una compilación desde el código fuente eso es `~/.cargo/bin` |
| `error: could not find `Cargo.toml`` al ejecutar `cargo install --path .` en la raíz del repositorio | No hay ningún manifiesto de workspace en la raíz. Apunta `--path` a `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | Un `astra-plugin` más antiguo aparece antes en tu `PATH`. `--version` no te dirá cuál es cuál — ejecuta `which astra-plugin` (`where` en Windows) para ver qué archivo estás ejecutando realmente |
| `invalid value workflow reference`, en tu primer push de etiqueta | La CLI que escribió `release.yml` es anterior a `5b8ab22` y fijó un objeto de etiqueta. Consulta [cómo saber si tu compilación lleva el arreglo](#el-bug-que-rompe-un-primer-release-y-cómo-saber-si-tu-compilación-lleva-el-arreglo) |

## Siguiente

- **[Qué es publicar](publishing.md)** — todo el recorrido, de
  directorio vacío a plugin listado, en una página.
- [Primeros pasos](2-tutorial/getting-started.md) — escribir el plugin
  en sí.
</content>
