# Primeros pasos

Un recorrido de 5 minutos: instalar la CLI, generar la plantilla de un plugin de herramientas en Rust, ejecutarlo en modo desarrollo y construir un paquete `.astraplugin` distribuible.

## Requisitos previos

- Un **daemon de Astra** en ejecución en `127.0.0.1:50051` (el puerto gRPC por defecto).
- **Rust** 1.75+ (para plugins en Rust o para instalar la CLI desde el código fuente).
- Opcional: **Python** 3.10+ o **Node.js** 20+ si elige esos SDKs.

## 1. Instalar la CLI

La CLI `astra-plugin` crea, ejecuta, construye, valida y firma plugins. Instálela desde el repositorio:

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

Verifique:

```bash
astra-plugin --version
```

## 2. Generar la plantilla de un plugin

```bash
astra-plugin create hello-world --lang rust --capabilities tools
cd hello-world
```

La CLI acepta `--lang rust|python|ts` y una lista separada por comas en `--capabilities`. Consulte la [referencia de la CLI](cli.md) para conocer cada opción.

El proyecto generado en Rust contiene:

```
hello-world/
├── Cargo.toml          # Depende de astra-plugin-sdk
├── plugin.toml         # Manifiesto (id, name, entry, capabilities)
├── src/main.rs         # Implementación de PluginCapability con una herramienta de ejemplo
├── proto/plugin.proto  # Copia del protocolo del plugin
├── .gitignore
└── README.md
```

Abra `src/main.rs` y dé a su herramienta un cuerpo útil:

```rust
use astra_plugin_sdk::prelude::*;

struct HelloWorld;

#[async_trait]
impl PluginCapability for HelloWorld {
    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef {
            name: "greet".into(),
            description: "Return a greeting for the given name".into(),
            parameters_json: r#"{
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }"#.into(),
        }]
    }

    async fn call_tool(&self, _name: &str, arguments_json: &str) -> ToolResult {
        let args: serde_json::Value = serde_json::from_str(arguments_json)
            .unwrap_or_default();
        let who = args.get("name").and_then(|v| v.as_str()).unwrap_or("world");
        ToolResult::ok(format!("Hello, {who}!"))
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(HelloWorld).await
}
```

## 3. Ejecutar en modo desarrollo

```bash
astra-plugin dev
```

Este comando observa el directorio del plugin, reconstruye ante cambios y reinicia el proceso mientras se reconecta al daemon en `127.0.0.1:50051`. Abra el chat de Astra y pídale "greet Ada" — el daemon enrutará la llamada de la herramienta a su plugin y transmitirá el resultado de vuelta al chat.

Directorios ignorados: `target/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`.

Apunte a un daemon distinto al predeterminado con `--daemon-addr`:

```bash
astra-plugin dev --daemon-addr 127.0.0.1:60051
```

## 4. Validar el manifiesto

```bash
astra-plugin validate
```

Detecta campos obligatorios faltantes, SemVer inválido y esquemas de configuración mal formados. Ejecútelo antes de cada build — el daemon rechazará cargar plugins que no pasen la validación.

## 5. Construir un paquete distribuible

```bash
astra-plugin build
```

Produce `hello-world-0.1.0.astraplugin` — un archivo ZIP que contiene el binario compilado, el manifiesto, cualquier recurso de interfaz, traducciones y (si dispone de una clave de firma) una entrada `SIGNATURE` Ed25519.

Use `-o` para especificar una ruta concreta:

```bash
astra-plugin build -o dist/hello-world.astraplugin
```

## 6. (Opcional) Generar una clave de firma

```bash
astra-plugin keygen
```

Crea un par de claves Ed25519 en `~/.astra/plugin-keys/{private,public}.key`. Cada `astra-plugin build` posterior firma automáticamente el archivo. Comparta `public.key` con los usuarios que deseen verificar el paquete.

## 7. Instalar el plugin

Arrastre el archivo `.astraplugin` a la página de Plugins de la interfaz de Astra, o llame al RPC `SideloadPlugin` del daemon. Tras la instalación, el daemon reinicia el proceso del plugin con las credenciales correctas y aparece en la lista de plugins.

## Dónde continuar

- [SDK de Rust](sdk-rust.md) — cada método del trait, builders `FieldDef` / `UiContribution`, `DaemonClient` para plugins cliente.
- [SDK de Python](sdk-python.md) — si prefiere los decoradores `@tool` / `@action` y esquemas automáticos desde anotaciones de tipo.
- [SDK de TypeScript](sdk-typescript.md) — API basada en clases con `@grpc/grpc-js`.
- [Capacidades](capabilities.md) — referencia completa de herramientas, TTS, STT, proveedor de IA, acciones, disparadores, contribuciones de interfaz, manejadores de eventos y modo cliente.
- [Publicación](publishing.md) — firma, distribución y estrategia de actualizaciones.
