# Desarrollo de plugins de Astra

Cree plugins para [Astra](https://github.com/Stella) — el asistente digital con inteligencia artificial — en Rust, Python o TypeScript.

Los plugins son procesos independientes que Astra lanza como procesos acompañantes (sidecar). Se comunican con el daemon mediante gRPC y pueden exponer herramientas de IA, proporcionar backends de TTS/STT, aportar acciones y disparadores personalizados al Command Graph, inyectar paneles de interfaz o actuar como clientes completos del daemon.

## Tabla de contenidos

| Documento | Qué cubre |
| --- | --- |
| [Primeros pasos](getting-started.md) | Instale la CLI, genere la plantilla de su primer plugin, ejecútelo en modo desarrollo y construya un paquete distribuible |
| [Referencia de la CLI](cli.md) | Cada subcomando `astra-plugin` con sus banderas, comportamiento y códigos de salida |
| [SDK de Rust](sdk-rust.md) | API basada en traits (`PluginCapability`), builders de campos, `HostClient`, `DaemonClient` |
| [SDK de Python](sdk-python.md) | API de decoradores (`@tool`, `@action`, `@trigger`), esquema automático desde anotaciones de tipo, integración con UV |
| [SDK de TypeScript](sdk-typescript.md) | API basada en clases, descubrimiento automático de capacidades, runtime `@grpc/grpc-js` |
| [Manifiesto](manifest.md) | Referencia de `plugin.toml` — cada sección y campo |
| [Capacidades](capabilities.md) | Las 9 capacidades, API por SDK, RPCs de proto |
| [Publicación](publishing.md) | Formato del paquete `.astraplugin`, firma con Ed25519, instalación manual |

## Arquitectura de un vistazo

```
┌────────────────────────┐     gRPC     ┌────────────────────────┐
│        Astra           │◀────────────▶│        Plugin          │
│        daemon          │   localhost  │      (sidecar)         │
│                        │              │                        │
│ PluginHostService ─────┼────────────▶│ HostClient             │
│                        │              │                        │
│ plugin-capability ◀────┼──────────────│ PluginCapability       │
│   service client       │              │   service              │
└────────────────────────┘              └────────────────────────┘
```

- El daemon lanza cada plugin como un proceso separado, pasando `--daemon-addr`, `--plugin-id` y, opcionalmente, `--auth-token` en la línea de comandos.
- El plugin inicia un servidor gRPC en un puerto local aleatorio, se conecta de vuelta al `PluginHostService` del daemon y **se registra** — anunciando qué capacidades implementa.
- Tras el registro, el daemon invoca al `PluginCapabilityService` del plugin para llamadas de herramientas, ejecución de acciones, TTS y eventos de ciclo de vida.
- El plugin utiliza `HostClient` para registrar logs, disparar disparadores, leer su propia configuración, establecer variables o enviar eventos a sus iframes de interfaz. Los plugins con capacidad de cliente obtienen además un `DaemonClient` completo con acceso a los servicios Chat, Voice, Command, Media, Monitor y Config.

## Cómo elegir un SDK

| Factor | Rust | Python | TypeScript |
| --- | --- | --- | --- |
| Latencia de arranque | ~10 ms (binario nativo) | ~300 ms (intérprete + importación de grpcio) | ~100 ms (arranque en frío de Node) |
| Huella de memoria | La más baja | La más alta | Media |
| Tamaño del paquete | Binario de ~5–10 MB | Fuentes de ~100 KB + venv gestionado por el daemon | Paquete de ~200 KB (esbuild) |
| Mejor para | Rendimiento crítico, integración con el sistema, proveedores de TTS/STT | Herramientas de IA, procesamiento de datos, bibliotecas de ML | APIs web, trabajo intensivo con JSON, integraciones de interfaz |
| Seguridad de tipos | Completa (en tiempo de compilación) | Opcional mediante anotaciones (generación de esquema en tiempo de ejecución) | Completa (en tiempo de compilación) |

Los tres SDKs son de primera clase — cada capacidad está disponible en cada SDK. Elija el que mejor se adapte al ecosistema del cual desee tomar bibliotecas.

## Siguiente paso

Vaya a [Primeros pasos](getting-started.md) para el recorrido de 5 minutos.
