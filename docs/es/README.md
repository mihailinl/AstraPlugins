> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/README.md) es la referencia autorizada.

# Documentación de plugins de Astra

Un plugin es un programa independiente que Astra inicia y con el que se
comunica por gRPC. Puede dar herramientas al modelo, aportar un motor de
texto a voz o de voz a texto, añadir pasos y disparadores (triggers) al editor
de comandos, contribuir con interfaz de usuario, o actuar como su propio
cliente de chat.

Aquí hay dos recorridos, y todo en esta página pertenece a uno de los dos.

## Escribir un plugin

| | |
|---|---|
| [Qué es un plugin](1-orientation/what-is-a-plugin.md) | Las diez capacidades (capabilities), y cuál quieres |
| [Arquitectura](1-orientation/architecture.md) | Modelo de procesos, los dos servicios, el handshake de autenticación |
| [Modelo de seguridad](1-orientation/security.md) | Qué demuestran las firmas, qué no, y con qué privilegio se ejecuta un plugin |
| [Plataformas](1-orientation/platforms.md) | linux-x64 y windows-x64, rutas por sistema operativo, requisitos de compilación |
| **[Primeros pasos](2-tutorial/getting-started.md)** | **De cero a un plugin en marcha. Empieza aquí.** |
| [SDK de Rust](4-sdk/rust.md) · [SDK de Python](4-sdk/python.md) · [SDK de TypeScript](4-sdk/typescript.md) | Una página cada uno, incluyendo lo que ese SDK todavía no puede hacer |
| [Ejemplos](7-examples/README.md) | Once plugins en este repositorio, cada uno con su plataforma |

## Publicar un plugin

**Publicar es un release etiquetado que la CI de GitHub compila y certifica
(attest), más una única solicitud de listado, una sola vez.** Subir tu código
fuente a GitHub no es publicar; enviarle a alguien un zip no es publicar;
pedirle a un mantenedor que compile tu plugin no es publicar. El registro fija
tu plugin por el digest exacto del archivo que descarga un usuario, y lee la
attestation de compilación de GitHub para saber qué workflow, qué commit y qué
repositorio produjeron esos bytes — y un archivo compilado en tu portátil no
tiene ninguno de los dos.

| | |
|---|---|
| **[Publicar un plugin](publishing.md)** | **Todo el recorrido en una sola página: de directorio vacío a plugin listado, cada comando con su salida. Empieza aquí.** |
| [Instalar la CLI](install-cli.md) | Descarga un `astra-plugin` precompilado y verifícalo, o compílalo desde el código fuente. No `cargo install` — eso no puede funcionar, y aquí se explica por qué |

Las tres etapas por separado, si prefieres verlas una a una:

1. [Publicar release con CI](5-publish/release-with-ci.md) — `astra-plugin init-ci`, y luego una etiqueta (tag). GitHub compila y certifica el paquete.
2. [Conseguir el listado](5-publish/get-listed.md) — una sola solicitud, una vez, para siempre. Después, los releases no requieren intervención.
3. Los usuarios instalan desde dentro de Astra, con el artefacto fijado por digest.

Existen otras dos formas de llevar un plugin a una máquina. **Ninguna de las
dos es publicar.** Ambas son para desarrolladores, ambas tienen un costo, y
ambas lo dicen claramente:

- [Instalar un archivo local](5-publish/local-install.md) — un `.astraplugin` recibido fuera del registro. Cuatro permisos se rechazan de plano.
- [Sideload de un directorio fuente](5-publish/sideload.md) — el bucle de desarrollo. Requiere el modo desarrollador, ejecuta código sin firmar con tu cuenta de usuario completa.

Además: [política de versionado y desuso](versioning.md) · [migración a 0.6](migration-0.6.md)

## Ejecutar uno

| | |
|---|---|
| [Solución de problemas](6-operate/troubleshooting.md) | Organizado según los errores que realmente imprimen el daemon y la CLI |
| [Logs](6-operate/logs.md) | Dónde están, por sistema operativo, y cómo seguirlos |
| [Rendimiento](6-operate/performance.md) | Tiempos de espera, presupuesto de arranque, margen de apagado, límites de archivo |

## Referencia

La mayor parte del nivel de referencia está **generada** a partir del código
que describe, y la CI falla cuando una página guardada en el repositorio
difiere de una ejecución nueva. Eso es deliberado: una página de referencia
escrita a mano es una segunda definición de la interfaz, y siempre es la que
está equivocada.

| Página | Generada a partir de |
|---|---|
| [`plugin.toml`](reference/manifest.md) | `astra-plugin-manifest` — el crate con el que el daemon analiza tu manifiesto |
| [CLI](reference/cli.md) | las definiciones de `clap`, ejecutando `astra-plugin --help` |
| [Protocolo](reference/protocol.md) | `proto/plugin.proto` |
| [Errores](reference/errors.md) | la taxonomía de errores en los tres SDK |
| [Paridad de hooks](reference/parity.md) | `spec/hooks.yaml` — los 35 hooks en los tres SDK |
| [Permisos](3-reference/permissions.md) | escrito a mano: cada permiso, qué otorga, cómo escribir un motivo |
| [Campos de configuración](3-reference/config-fields.md) | escrito a mano: interfaz de ajustes, `[config]`, y los hooks de campo TTS/STT |

Especificaciones normativas, para quien implemente un verificador o un
registro en lugar de un plugin: [bundle v2](spec/bundle-v2.md) ·
[índice del registro](spec/registry-index.md) · [permisos](spec/permissions.md).

## Idiomas

El inglés es la versión autoritativa. Seis traducciones viven junto a ella, cada
una un espejo archivo por archivo de estas páginas — los mismos archivos, los
mismos encabezados, el mismo orden:

[Deutsch](../de/README.md) · [Español](README.md) · [日本語](../ja/README.md) · [Русский](../ru/README.md) · [Українська](../uk/README.md) · [简体中文](../zh-CN/README.md)

La CI comprueba la forma de una traducción: que tenga exactamente las páginas que
tiene `docs/en`, que todos sus enlaces resuelvan y que cada bloque de código suyo siga
ejecutándose — los bloques idénticos se ejecutan una vez y se reportan como
`identical to` el original inglés, así que uno que se desvió en la traducción
vuelve a ejecutarse por su cuenta. La CI no puede comprobar que una frase siga
significando lo que significaba la inglesa. Por eso el inglés manda ante
cualquier discrepancia, cada página traducida lo dice al principio, y cualquier
corrección es bienvenida.

## Dos cosas con las que toda esta documentación tiene cuidado

**Los plugins no están en un sandbox.** Un plugin es un proceso nativo que se
ejecuta como tú, con tus archivos y tu red. Las firmas responden *quién
publicó estos bytes*; los permisos responden *qué hará el daemon cuando el
plugin lo pida*. Ninguna de las dos responde qué puede hacerle el proceso a tu
máquina. Consulta [el modelo de seguridad](1-orientation/security.md).

**La cadena de confianza está anclada hasta la delegación, pero todavía no a
través del catálogo.** Las claves raíz existen y coinciden en ambos lados, y
el `trust.json` firmado por la raíz que delega en una clave de firma del
índice también existe ya — se verifica bajo `astra-root-2026a` y nombra el
único commit del workflow reutilizable que el registro aceptará en una
attestation de compilación. Lo que todavía falta es la firma del propio
catálogo: `registry/v1/index.json` y `revocations.json` llevan
`"signatures": []`, así que una compilación por defecto no tiene nada que
comprobar, falla cerrado (fail closed) y clasifica cualquier catálogo como sin
firmar. Esto está escrito en
[`spec/registry-index.md` §0.1](spec/registry-index.md) y se repite en todos
los lugares donde importa, en lugar de darlo por implícito en silencio.
</content>
