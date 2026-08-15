> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/1-orientation/platforms.md) es la referencia autorizada.

# Plataformas

Astra distribuye un daemon para **dos** hosts. Todo lo demás se deriva de
eso.

| Clave de plataforma | Host | Astra distribuye un daemon |
|---|---|---|
| `linux-x64` | Linux, x86_64 | sí |
| `windows-x64` | Windows, x86_64 | sí |
| `noarch` | cualquiera — un plugin interpretado sin código nativo | n/a, funciona en ambos |
| `linux-arm64` · `windows-arm64` · `macos-x64` · `macos-arm64` | — | **no** |

La última fila está *reservada, no soportada*. Los nombres existen en el
esquema del registro para que el formato del índice nunca tenga que cambiar
si Astra más adelante distribuye esos hosts, y para que un validador pueda
rechazar una errata (`mac-amd64`) en lugar de escribir una clave que ningún
daemon buscará jamás. Un paquete publicado bajo una de ellas no tiene host
donde ejecutarse. `astra-plugin build` no adivina: en un host para el que no
tiene clave, te dice que pases `--target` explícitamente en lugar de
empaquetar en silencio algo que resuelve a `linux-x64`.

## Un paquete por plataforma, y qué decide cuántos necesitas

<!-- doctest: cli -->
```bash
astra-plugin build --target linux-x64
astra-plugin build --target windows-x64
astra-plugin build --all-targets
```

- **Rust** compila a código nativo, así que necesita un paquete por
  plataforma. El workflow de release los construye en una matriz —
  `ubuntu-24.04` y `windows-2022` — porque un cross-build trae consigo un
  conjunto de errores distinto.
- **TypeScript y Python** producen un único paquete `noarch`. El índice
  escribe la misma URL y el mismo digest bajo cada clave de plataforma
  soportada, así que un paquete `noarch` se encuentra bajo `linux-x64` y
  `windows-x64` como cualquier otro.

`--all-targets` construye todo lo que el plugin necesita para poder
instalarse en cualquier lugar donde Astra se ejecute: un archivo para
TypeScript y Python, uno por plataforma para Rust, cada uno desde su propio
`cargo build --target`.

## `[platform]`, y por qué un bloque omitido es una afirmación

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "native-thing"
name = "Native Thing"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/native_thing"

[capabilities]
tools = true

[platform]
os = ["linux", "windows"]
arch = ["x86_64"]
```

Un bloque `[platform]` vacío o ausente significa *sin requisito*, y el
daemon considera el plugin compatible en todas partes. Eso es correcto para
un plugin `noarch` e incorrecto para uno que distribuye un binario nativo.
`astra-plugin doctor` lo dice exactamente en esos términos:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Will this install on the platforms I expect?
         no [platform] block, so the daemon considers it compatible everywhere. Correct for a
         noarch plugin; wrong for one that ships a native binary.
```

`astra-plugin build` graba la respuesta real a partir de `--target` en el
`MANIFEST` del paquete, así que el archivo empaquetado lleva `{os, arch}`
diga lo que diga el manifiesto.

## Requisitos de compilación

| Lenguaje | Necesita | Comprobado por |
|---|---|---|
| Rust | Rust **1.85 o más nuevo** — el SDK y el andamiaje (scaffold) usan la edición 2024 | `astra-plugin doctor` |
| Rust | **`protoc` en el PATH.** `astra-plugin-sdk/build.rs` compila `proto/plugin.proto` con `tonic_build::configure().compile_protos(…)`, y tonic-build 0.12 invoca `protoc` externamente en lugar de incluir uno propio. `apt install protobuf-compiler` / `pacman -S protobuf` / `brew install protobuf` / `winget install Google.Protobuf` | `astra-plugin doctor` |
| TypeScript | Node 20+ para ejecutar, y `bun` (o el bundler del script `build`) para empaquetar | `astra-plugin doctor` |
| Python | `python3`, más `grpcio` y `protobuf` de `requirements.txt` | `astra-plugin doctor` |

`protoc` es el que muerde primero y se lee como otra cosa. La CLI depende
del SDK de Rust, así que se necesita para *instalar `astra-plugin` mismo* —
antes de tener un proyecto, un manifiesto, o cualquier razón para sospechar
de un compilador de protobuf. Sin él, `cargo install` se detiene en
`error: failed to run custom build command for astra-plugin-sdk`, con
`Could not find `protoc`` unas líneas más abajo. La propia CI de este
repositorio lo instala en cada job de Rust (`arduino/setup-protoc@v3`, siete
veces en `.github/workflows/ci.yml`), lo cual es la prueba más clara de que
no es opcional.

`astra-plugin doctor` responde todo esto con un solo comando, en la máquina
en la que realmente estás:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Can I build a Rust plugin?
         cargo 1.97.0 (c980f4866 2026-06-30)
  [ok  ] Can I compile the SDK's protobufs?
         libprotoc 35.1
  [ok  ] Can I build and run a TypeScript plugin?
         node v26.4.0
  [ok  ] What will bundle my TypeScript?
         bun — `astra-plugin build` uses bun run build
  [ok  ] Can I build and run a Python plugin?
         python3: Python 3.14.6
```

### El piso de glibc

Un paquete Linux construido en CI se comprueba contra **GLIBC_2.39** — el
workflow de release desensambla cada objeto ELF del archivo terminado y hace
fallar la compilación si algo necesita una versión de símbolo más nueva. Eso
es lo que hace que un plugin construido en `ubuntu-24.04` se ejecute en las
distribuciones que Astra apunta, y es el tipo de fallo que de otro modo solo
aparece en la máquina de un usuario.

Si construyes un paquete Linux a mano en una distribución más nueva, nada
comprueba esto. Esa es una de varias razones por las que el camino de
release pasa por CI.

### Los paquetes TypeScript no llevan `node_modules`

Un `.astraplugin` distribuye la salida empaquetada, no un árbol de
dependencias. El workflow de release verifica que el paquete sea
autocontenido: un `require("chalk")` perdido que el bundler no pudo seguir
se instala sin problema y muere en el primer arranque con
`MODULE_NOT_FOUND`, en una máquina donde nadie puede arreglarlo.

## Dónde vive cada cosa, por sistema operativo

Astra resuelve sus directorios con el crate `directories`, a partir de
`("com", "astra", "astra")` — la CLI usa la misma llamada exacta, así que
ambas no pueden discrepar (`astra-plugin-cli/src/daemon.rs`).

| | Linux | Windows |
|---|---|---|
| Directorio de config | `~/.config/astra` | `%APPDATA%\astra\astra\config` |
| Archivo de puerto del daemon | `<config>/daemon.port` | igual |
| Secreto de arranque del daemon | `<config>/daemon.token` | igual |
| Plugins instalados | `<config>/plugins/<id>/` | igual |
| Configuración de un plugin | `<config>/plugins/<id>/config.json` | igual |
| Logs del daemon | `<config>/logs/` | igual |

Pregunta, en lugar de asumir — `doctor` imprime la ruta que esta máquina
resolvió:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [warn] Where does the CLI look for the running daemon?
         /home/you/.config/astra — but there is no daemon.port in it, so the CLI will fall
         back to 127.0.0.1:32000
```

El daemon toma un puerto asignado por el sistema operativo cuando el 32000
está ocupado, así que `127.0.0.1:32000` es una suposición de respaldo y
`daemon.port` es el hecho real.

## macOS

No soportado, y no por omisión. El propio workflow de release de Astra solo
compila `linux-x64` y `windows-x64`, así que un paquete de plugin
`macos-arm64` no tendría host donde ejecutarse; macOS además exigiría
notarización de Apple para cada autor externo. Los nombres de clave están
reservados en el esquema del índice, nada los emite, y un host no manejado
es un error duro en lugar de un respaldo silencioso. Revisar de nuevo en el
release en que Astra distribuya un daemon para ese objetivo.
</content>
