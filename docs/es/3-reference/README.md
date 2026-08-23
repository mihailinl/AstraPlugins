> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/3-reference/README.md) es la referencia autorizada.

# Referencia

Dos niveles, y la diferencia importa.

## Generada — no puede desviarse

Estas páginas las produce [`tools/docgen`](../../../tools/docgen/) a partir
del código que describen, y la CI ejecuta
`python3 tools/docgen/gen.py --check`: una página guardada en el repositorio
que difiere de una ejecución nueva hace fallar el build, con un diff. La
página de la CLI se genera *ejecutando* `astra-plugin --help` en lugar de
analizar `main.rs`, porque un segundo analizador para las macros derive de
clap es una cosa más que puede discrepar en silencio con la herramienta.

Viven un directorio más arriba, en [`../reference/`](../reference/), que es
donde el generador las escribe.

| Página | Generada a partir de |
|---|---|
| [`plugin.toml`](../reference/manifest.md) | `astra-plugin-manifest` — el crate con el que el daemon analiza los manifiestos |
| [CLI](../reference/cli.md) | las definiciones de `clap`, ejecutando el binario |
| [Protocolo](../reference/protocol.md) | [`proto/plugin.proto`](../../../proto/plugin.proto) |
| [Errores](../reference/errors.md) | la taxonomía de errores en los tres SDK |
| [Paridad de hooks](../reference/parity.md) | [`spec/hooks.yaml`](../../../spec/hooks.yaml) — 35 hooks, 3 SDK |

Tablas de hooks por SDK, renderizadas a partir de la misma spec:
[Rust](../hooks/rust.md) · [Python](../hooks/python.md) ·
[TypeScript](../hooks/typescript.md).

## Escrita a mano — revisada por una persona

Dos páginas describen cosas que ningún generador puede leer de un tipo: qué
*significa* un permiso para el usuario al que se le pide concederlo, y cómo
encajan las tres cosas distintas llamadas "config".

| Página | |
|---|---|
| [Permisos](permissions.md) | Cada id, qué otorga, y cómo escribir un `reason` |
| [Campos de config y ajustes](config-fields.md) | `[config]`, ajustes tipados, y los hooks de campo TTS/STT |
| [Localización](localisation.md) | `locales/<code>.json`, el marcador `$key`, y dónde actúa la verificación de inglés — **solo en inglés** |

Cada ejemplo de código en estas páginas se ejecuta en la CI mediante
[`docs/tools/doctest.py`](../../tools/doctest.py).

## Especificaciones normativas

Para quien implemente un verificador, un empaquetador o un registro en
lugar de un plugin. Son documentos estilo RFC 2119 con vectores dorados
(golden vectors), no guías.

[Bundle v2](../spec/bundle-v2.md) · [Índice del registro](../spec/registry-index.md) ·
[Permisos](../spec/permissions.md)
</content>
