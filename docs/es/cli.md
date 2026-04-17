# Referencia de la CLI `astra-plugin`

Cada subcomando, bandera y comportamiento — con origen en `astra-plugin-cli/src/main.rs` y `astra-plugin-cli/src/commands/`.

## Instalación

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Ejecute `astra-plugin --help` para ver la lista completa de comandos. Cada subcomando también acepta `--help`.

## `astra-plugin create`

Genera la plantilla de un nuevo proyecto de plugin a partir de una plantilla específica del lenguaje.

```bash
astra-plugin create <NAME> [--lang <LANG>] [--capabilities <LIST>] [--output <DIR>]
```

| Argumento / bandera | Valor por defecto | Descripción |
| --- | --- | --- |
| `NAME` | — | Id del plugin. Debe ser alfanumérico en minúsculas con guiones — se convierte en `[plugin].id` en el manifiesto. |
| `-l, --lang` | `rust` | Uno de `rust`, `python` (alias `py`), `typescript` (alias `ts`). |
| `-c, --capabilities` | `tools` | Lista separada por comas. Tokens válidos: `tools`, `tts`, `stt`, `ai_provider`, `actions`, `triggers`, `client`, `event_handlers`, `ui_panels`. Los espacios en blanco alrededor de las comas se recortan. |
| `-o, --output` | `./<NAME>` | Directorio de destino. |

### Qué se genera

Todas las plantillas incluyen:

- `plugin.toml` — manifiesto precompletado con id, nombre, versión `0.1.0` y la sección `[capabilities]` activada para lo que haya solicitado.
- `proto/plugin.proto` — una copia local del protocolo del plugin.
- `.gitignore`, `README.md`.

Extras específicos por lenguaje:

| Lenguaje | Archivos adicionales |
| --- | --- |
| `rust` | `Cargo.toml` (con `astra-plugin-sdk`, `tokio`, `serde`, `anyhow`, `async-trait`), `src/main.rs` con una implementación de ejemplo de `PluginCapability`. `entry.command` establecido en `target/release/<name>.exe`. |
| `python` | `pyproject.toml` (con `astra-plugin-sdk`, `grpcio`, `protobuf`), `src/plugin.py` con una subclase `Plugin` de ejemplo. `entry.command = "python"`, `args = ["-m", "src.plugin"]`, `runtimes = ["python"]`. |
| `typescript` | `package.json`, `tsconfig.json`, `src/index.ts` con una subclase `Plugin` de ejemplo. `entry.command = "node"`, `args = ["dist/index.js"]`, `runtimes = ["node"]`. |

## `astra-plugin dev`

Ejecuta el plugin en modo desarrollo con observación de archivos y recompilación/reinicio automáticos.

```bash
astra-plugin dev [PATH] [--daemon-addr <HOST:PORT>]
```

| Argumento / bandera | Valor por defecto | Descripción |
| --- | --- | --- |
| `PATH` | `.` | Directorio del plugin (el que contiene `plugin.toml`). |
| `--daemon-addr` | `127.0.0.1:50051` | Dirección gRPC del daemon de Astra en ejecución. |

### Qué hace

1. Lee `plugin.toml` y determina el comando de compilación según el lenguaje.
2. Inicia un observador de archivos sobre el directorio del plugin (ignorando `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`).
3. Ejecuta la compilación (`cargo build` para Rust, `bun run build` / `tsc` para TypeScript, `uv pip sync` / nada para Python).
4. Lanza el `entry.command` con `--daemon-addr`, `--plugin-id` y `--auth-token` añadidos.
5. Ante cambios en archivos: termina el proceso hijo, recompila y lo relanza.

Los errores se imprimen en línea. Pulse `Ctrl+C` para detener.

## `astra-plugin build`

Empaqueta el plugin en un archivo `.astraplugin` distribuible.

```bash
astra-plugin build [PATH] [-o <FILE>]
```

| Argumento / bandera | Valor por defecto | Descripción |
| --- | --- | --- |
| `PATH` | `.` | Directorio del plugin. |
| `-o, --output` | `<id>-<version>.astraplugin` | Ruta del archivo. |

### Pasos de compilación por lenguaje

| Lenguaje | Pasos |
| --- | --- |
| `rust` | Ejecuta `cargo build --release`, copia el binario en `bin/` dentro del archivo y reescribe `entry.command` para apuntar a la ruta empaquetada. |
| `typescript` | Ejecuta `bun build src/index.ts --outdir dist` o recurre a `npx esbuild`. El JS empaquetado va a `dist/` dentro del archivo. |
| `python` | Si `uv` está en `PATH`, genera `requirements.lock` mediante `uv pip compile`. Copia `src/`, `pyproject.toml`, `requirements.txt` y el archivo de lock. |

### Estructura del archivo

```
<plugin-id>-<version>.astraplugin           (archivo ZIP)
├── plugin.toml              # Manifiesto (entry.command reescrito para Rust)
├── bin/                     # Binario compilado (solo Rust)
├── dist/                    # JS empaquetado (solo TypeScript)
├── src/                     # Fuentes de Python
├── requirements.txt         # Dependencias de Python (sin resolver)
├── requirements.lock        # Dependencias de Python (resueltas por uv)
├── ui/                      # Interfaz personalizada (si existe)
├── locales/                 # Archivos JSON de i18n (si existen)
├── icon.png / icon.svg      # Branding opcional
├── README.md / LICENSE      # Opcionales
├── SIGNATURE                # Firma Ed25519 (si existe un par de claves)
└── PUBKEY                   # Clave pública de firma (si existe un par de claves)
```

Si existe `~/.astra/plugin-keys/private.key`, la CLI **firma automáticamente** el archivo en cada build — no se necesita ninguna bandera adicional.

## `astra-plugin validate`

Verifica el manifiesto y el esquema de configuración sin compilar.

```bash
astra-plugin validate [PATH]
```

Elementos validados:

- Campos obligatorios del manifiesto: `plugin.id`, `plugin.name`, `plugin.version`, `entry.command`.
- `plugin.id` es alfanumérico en minúsculas con guiones.
- `plugin.version` coincide con SemVer `X.Y.Z` (advertencia, no error, si no lo hace).
- Al menos una capacidad está habilitada (advertencia si todas son `false`).
- `[config].schema`, si está presente, se analiza como JSON y tiene `"type": "object"` en la raíz.
- Advertencias de metadatos: falta de `description` o `author`.

Sale con código distinto de cero solo ante errores duros (TOML no analizable, campos obligatorios faltantes).

## `astra-plugin keygen`

Genera un par de claves Ed25519 utilizado por `build` para firmar archivos.

```bash
astra-plugin keygen [--force]
```

| Bandera | Descripción |
| --- | --- |
| `--force` | Sobrescribe un par de claves existente. Sin esta bandera el comando rehúsa reemplazar claves existentes. |

Ubicaciones de salida (creadas si no existen):

- `~/.astra/plugin-keys/private.key` — semilla privada Ed25519 en base64 (manténgala secreta).
- `~/.astra/plugin-keys/public.key` — clave pública Ed25519 en base64 (es seguro compartirla).

Una vez que existe un par de claves, cada `astra-plugin build` añade automáticamente una entrada `SIGNATURE` (resumen tipo HMAC de cada entrada del ZIP, firmado con Ed25519) y una entrada `PUBKEY` para que los consumidores puedan verificar la autenticidad.

## Entorno

- `RUST_LOG` — controla la verbosidad de la salida de la CLI. El valor por defecto es nivel warning; use `RUST_LOG=debug` para una traza completa.
- Todos los comandos de la CLI respetan el `PATH` del shell actual al buscar `cargo`, `node`, `bun`, `npx`, `python` y `uv`.
