> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/reference/cli.md) es la referencia autorizada. La página en inglés está GENERADA por `tools/docgen/cli.py` — esta traducción es una instantánea mantenida a mano, no otra copia generada.

# Referencia de la CLI

`astra-plugin 0.3.0`. Cada flag de abajo se leyó del binario, así que
esta página no puede describir una opción que no exista. La fuente es
[`astra-plugin-cli/src/main.rs`](../../../astra-plugin-cli/src/main.rs).

Astra Plugin Development CLI

## En todas partes

| Opción | Descripción |
|---|---|
| `--json` | Imprime un único documento JSON en lugar de salida legible para humanos. Las líneas de progreso se suprimen para que la salida se pueda canalizar (pipe) con seguridad |
| `-h, --help` | Imprime la ayuda |
| `-V, --version` | Imprime la versión |

## Comandos

| Comando | Alias | Qué hace |
|---|---|---|
| [`new`](#astra-plugin-new) | `create` | Crea un nuevo proyecto de plugin a partir de una plantilla |
| [`dev`](#astra-plugin-dev) | — | Inicia un plugin en modo dev (sideload en el Astra en ejecución + hot-reload) |
| [`build`](#astra-plugin-build) | — | Compila un plugin en un paquete .astraplugin distribuible |
| [`sign`](#astra-plugin-sign) | — | Añade el par SIGNATURE/PUBKEY dentro del ZIP, en retirada, a un paquete compilado |
| [`verify`](#astra-plugin-verify) | — | Verifica un paquete .astraplugin compilado e imprime sus digests |
| [`test`](#astra-plugin-test) | — | Ejecuta la suite de conformidad contra un proceso de plugin real |
| [`doctor`](#astra-plugin-doctor) | — | Responde, en un solo comando, cada pregunta que se hace cuando un plugin no arranca: toolchains, el daemon, el manifiesto, el punto de entrada, permisos, el bloque de plataforma, el workflow de release |
| [`logs`](#astra-plugin-logs) | — | Lee la salida de un plugin desde el daemon que lo lanzó |
| [`check`](#astra-plugin-check) | `validate` | Comprueba un manifiesto de plugin, el schema de config y el workflow de release |
| [`init-ci`](#astra-plugin-init-ci) | — | Escribe .github/workflows/release.yml, fijado a un commit del workflow reutilizable de Astra. Vuelve a ejecutarlo para actualizar el fijado; conserva tus entradas |
| [`version`](#astra-plugin-version) | — | Establece la versión en plugin.toml y en cualquier otro manifiesto a la vez |
| [`publish`](#astra-plugin-publish) | — | Consigue que se liste un release: haz un preflight, o abre un envío prerrellenado |
| [`keygen`](#astra-plugin-keygen) | — | Genera el par de claves Ed25519 OPCIONAL que usa `astra-plugin sign` |

### No existe `astra-plugin login`

No hay **`login`**. Conseguir que se liste un plugin pasa por un
navegador en el que el autor ya tiene sesión iniciada — el registro lee
paquetes certificados de un Release de GitHub y verifica cada uno desde
cero, así que un envío lleva solo un repositorio y una etiqueta y nada
más. Eso significa ninguna segunda cuenta que crear, ningún llavero con
el que integrarse, ningún archivo de credenciales que pueda filtrarse, y
ningún token en un historial de shell. Un `login` aquí sería un
almacén de credenciales construido para guardar algo que nada pide.

## astra-plugin new

También se escribe `astra-plugin create`.

Crea un nuevo proyecto de plugin a partir de una plantilla

```
Usage: astra-plugin new [OPTIONS] <NAME>
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `<NAME>` | Nombre del plugin (minúsculas, se permiten guiones) |

**Opciones**

| Opción | Descripción |
|---|---|
| `-l, --lang <LANG>` | Lenguaje de programación (por defecto `rust`) |
| `-t, --template <TEMPLATE>` | Qué tipo de plugin es. Elige las capabilities y el código de ejemplo; `--capabilities` sobrescribe el conjunto de capabilities que implica (por defecto `tool`; uno de `tool`, `tts`, `stt`, `stt-streaming`, `ai-provider`, `ui`, `action-trigger`, `client`, `blank`) |
| `-c, --capabilities <CAPABILITIES>` | Capabilities (separadas por comas: tools, tts, stt, ai_provider, client, actions, triggers, ui_contributions, event_handlers, dom_access). Sobrescribe lo que implique --template |
| `-o, --output <OUTPUT>` | Directorio de salida (por defecto: ./<name>) |

## astra-plugin dev

Inicia un plugin en modo dev (sideload en el Astra en ejecución + hot-reload)

```
Usage: astra-plugin dev [OPTIONS] [PATH]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `[PATH]` | Ruta al directorio del plugin (por defecto: directorio actual) (por defecto `.`) |

**Opciones**

| Opción | Descripción |
|---|---|
| `--daemon-addr <DAEMON_ADDR>` | Dirección gRPC del daemon. Por defecto, el puerto que el daemon en ejecución escribió en <config>/daemon.port, si no 127.0.0.1:32000 |
| `--standalone` | Lanza el proceso del plugin directamente en lugar de pedírselo al daemon. El plugin no puede registrarse con Astra de esta forma — ver la nota que imprime |

## astra-plugin build

Compila un plugin en un paquete .astraplugin distribuible

```
Usage: astra-plugin build [OPTIONS] [PATH]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `[PATH]` | Ruta al directorio del plugin (por defecto: directorio actual) (por defecto `.`) |

**Opciones**

| Opción | Descripción |
|---|---|
| `-o, --output <OUTPUT>` | Ruta del archivo de salida. Por defecto <id>-<version>-<target>.astraplugin, el nombre que debe tener un paquete publicado — el segmento target es la clave de plataforma del registro |
| `--target <TARGET>` | Plataforma para la que es este paquete: linux-x64, windows-x64, o noarch. Por defecto, el host para plugins nativos y noarch para TypeScript/Python |
| `--reproducible` | Garantiza un empaquetado determinista: entradas ordenadas, mtime 1980-01-01, nivel de compresión fijo. Dos compilaciones de las mismas entradas producen el mismo sha256 |
| `--all-targets` | Compila cada paquete que este plugin necesita para poder instalarse en cualquier lugar donde Astra se ejecute. Un archivo para TypeScript y Python (noarch); uno por plataforma para Rust, cada uno desde su propio `cargo build --target` |

**Oculta: `--no-sign`.** Se acepta, y está ausente de `--help`
(`#[arg(hide = true)]`). No-op obsoleto: `build` nunca firma. Se
conserva porque el workflow de release fijado la pasa, y eliminar el
flag rompería cada workflow de autor ya publicado. Se elimina junto con
el par heredado del formato.

## astra-plugin sign

Añade el par SIGNATURE/PUBKEY dentro del ZIP, en retirada, a un paquete
compilado.

Un segundo factor opcional, no una señal de confianza: Astra comprueba
el par dentro del ZIP contra una clave de publicador de Astra fijada,
así que un paquete firmado con tu propia clave es tan poco fiable como
uno sin firmar. Lo que hace que Astra instale un plugin es el registro
del registry que contrafirma sha256(archivo completo), no ninguna
clave que tengas tú. Tanto este comando como las entradas de formato
que escribe se eliminan en un release futuro.

```
Usage: astra-plugin sign [OPTIONS] <FILE>
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `<FILE>` | El .astraplugin a firmar, en su sitio |

**Opciones**

| Opción | Descripción |
|---|---|
| `--key <KEY>` | Lee la semilla Ed25519 desde esta ruta en lugar de ~/.astra/plugin-keys/private.key. Una ruta, nunca la clave misma |

## astra-plugin verify

Verifica un paquete .astraplugin compilado e imprime sus digests

```
Usage: astra-plugin verify [OPTIONS] <FILE>
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `<FILE>` | Ruta al archivo .astraplugin |

## astra-plugin test

Ejecuta la suite de conformidad contra un proceso de plugin real.

Arranca el plugin tal como lo arranca el daemon, contra un daemon
simulado que sirve PluginHostService, y llama a cada hook entrante que
impliquen las capabilities del manifiesto. Un hook que
`spec/hooks.yaml` marca como `required` no puede responder
UNIMPLEMENTED; uno `optional` sí puede, porque UNIMPLEMENTED es la
forma que tiene el protocolo de decir "este hook no existe".

```
Usage: astra-plugin test [OPTIONS] [PATH]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `[PATH]` | Ruta al directorio del plugin (por defecto: directorio actual) (por defecto `.`) |

**Opciones**

| Opción | Descripción |
|---|---|
| `--no-build` | Usa lo que ya esté compilado en lugar de compilar primero |
| `--report <REPORT>` | Escribe aquí el reporte de conformidad legible por máquina |

## astra-plugin doctor

Responde, en un solo comando, cada pregunta que se hace cuando un
plugin no arranca: toolchains, el daemon, el manifiesto, el punto de
entrada, permisos, el bloque de plataforma, el workflow de release

```
Usage: astra-plugin doctor [OPTIONS] [PATH]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `[PATH]` | Ruta al directorio del plugin (por defecto: directorio actual). Las comprobaciones de proyecto se omiten cuando no contiene plugin.toml (por defecto `.`) |

**Opciones**

| Opción | Descripción |
|---|---|
| `--daemon-addr <DAEMON_ADDR>` | Dirección gRPC del daemon a sondear |

## astra-plugin logs

Lee la salida de un plugin desde el daemon que lo lanzó

```
Usage: astra-plugin logs [OPTIONS] [PLUGIN_ID]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `[PLUGIN_ID]` | Id del plugin. Por defecto: el plugin.id del manifiesto en --path |

**Opciones**

| Opción | Descripción |
|---|---|
| `--path <PATH>` | Dónde buscar un plugin.toml cuando no se da ningún id (por defecto `.`) |
| `--daemon-addr <DAEMON_ADDR>` | Dirección gRPC del daemon |
| `-n, --lines <LINES>` | Cuántas líneas de cola pedir (por defecto `200`) |
| `-f, --follow` | Seguir sondeando hasta Ctrl+C |

## astra-plugin check

También se escribe `astra-plugin validate`.

Comprueba un manifiesto de plugin, el schema de config y el workflow de
release

```
Usage: astra-plugin check [OPTIONS] [PATH]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `[PATH]` | Ruta al directorio del plugin (por defecto: directorio actual) (por defecto `.`) |

**Opciones**

| Opción | Descripción |
|---|---|
| `--strict` | Trata los avisos como errores |
| `--fix` | Aplica las correcciones que se pueden aplicar mecánicamente, luego vuelve a comprobar. Solo reescribe lo que puede demostrar; todo lo demás se sigue reportando |
| `--resolve-pin` | Le pregunta a GitHub si el fijado del workflow de release está actualizado. Desactivado por defecto: `astra-plugin dev` ejecuta `check --strict` en cada arranque, y el workflow de release le dice a la comprobación desde qué se está ejecutando mediante ASTRA_PLUGIN_WORKFLOW_SHA, así que ninguno de los dos necesita la red |

## astra-plugin init-ci

Escribe .github/workflows/release.yml, fijado a un commit del workflow
reutilizable de Astra. Vuelve a ejecutarlo para actualizar el fijado;
conserva tus entradas

```
Usage: astra-plugin init-ci [OPTIONS] [PATH]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `[PATH]` | Ruta al directorio del plugin (por defecto: directorio actual) (por defecto `.`) |

**Opciones**

| Opción | Descripción |
|---|---|
| `--ref <WORKFLOW_REF>` | Un commit de 40 caracteres hex a fijar (usado tal cual, sin red), o un nombre de ref a resolver. Por defecto: la etiqueta de workflow publicada, si no la cabeza de la rama por defecto |
| `--linux-packages <LINUX_PACKAGES>` | Establece la entrada linux-packages, p. ej. "libasound2-dev pkg-config". Si se omite, se conserva el valor de un archivo existente |
| `--offline` | Nunca toca la red: conserva el fijado ya presente en el archivo |

## astra-plugin version

Establece la versión en plugin.toml y en cualquier otro manifiesto a la
vez

```
Usage: astra-plugin version [OPTIONS] <VERSION> [PATH]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `<VERSION>` | La nueva versión, semver estricto y sin 'v' inicial |
| `[PATH]` | Ruta al directorio del plugin (por defecto: directorio actual) (por defecto `.`) |

**Opciones**

| Opción | Descripción |
|---|---|
| `--allow-downgrade` | Permite una versión que ordene por debajo de la actual. Astra se niega a instalar un downgrade, así que ese release sería no instalable |

## astra-plugin publish

Consigue que se liste un release: haz un preflight, o abre un envío
prerrellenado.

No sube nada y no guarda ninguna credencial — el registro lee los
paquetes certificados de tu Release de GitHub y verifica cada uno desde
cero, así que un envío lleva solo tu repositorio y una etiqueta.

```
Usage: astra-plugin publish [OPTIONS] [PATH]
```

**Argumentos**

| Argumento | Descripción |
|---|---|
| `[PATH]` | Ruta al directorio del plugin (por defecto: directorio actual) (por defecto `.`) |

**Opciones**

| Opción | Descripción |
|---|---|
| `--dry-run` | Ejecuta cada comprobación del registro que puede correr en local, nombra las que solo el registro puede ejecutar, y se detiene |
| `--notify` | Un ping de release para un plugin que YA está listado — la vía de escape manual de la tarea 3.4, para cuando el registro no ha notado un release por sí mismo. Sin esto, abre una solicitud de primer listado |
| `--repo <REPO>` | Repositorio fuente como `owner/name`. Por defecto: el remoto `origin` |
| `--tag <TAG>` | Etiqueta de release. Por defecto: el prefijo de etiqueta del plugin más su versión |
| `--print-url` | Imprime la URL y no abre un navegador |

## astra-plugin keygen

Genera el par de claves Ed25519 OPCIONAL que usa `astra-plugin sign`.

No necesitas uno para publicar: `build` no lo lee, y la confianza de
Astra viene del registro del registry sobre sha256(archivo completo),
no de ninguna clave que tengas tú.

```
Usage: astra-plugin keygen [OPTIONS]
```

**Opciones**

| Opción | Descripción |
|---|---|
| `--force` | Sobrescribe el par de claves existente |
</content>
