# Referencia de `plugin.toml`

Cada plugin se declara a sí mismo en un manifiesto `plugin.toml` ubicado en la raíz de su proyecto. Este archivo indica al daemon cómo lanzar el plugin, qué capacidades implementa y qué configuración acepta.

## Ejemplo completo

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"
description = "Word count, case conversion, regex matching"
author = "Astra Team"
license = "MIT"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
tts = false
stt = false
ai_provider = false
client = false
ui_contributions = false
event_handlers = false

[config]
schema = """
{
  "type": "object",
  "properties": {
    "max_text_length": {
      "type": "number",
      "default": 10000,
      "title": "Max Text Length"
    }
  }
}
"""
```

## `[plugin]` — metadatos

| Campo | Tipo | Requerido | Descripción |
| --- | --- | --- | --- |
| `id` | string | sí | Alfanumérico en minúsculas con guiones. Identifica de forma única al plugin. |
| `name` | string | sí | Nombre para mostrar en la interfaz de Plugins. |
| `version` | string | sí | Versión semántica (`X.Y.Z`). Se utiliza para detectar actualizaciones. |
| `description` | string | recomendado | Resumen breve. Se muestra en la interfaz de Plugins. |
| `author` | string | recomendado | Nombre del autor u organización. |
| `license` | string | recomendado | Identificador SPDX de la licencia (`MIT`, `Apache-2.0`, …). |

## `[entry]` — cómo lanzar el plugin

| Campo | Tipo | Requerido | Descripción |
| --- | --- | --- | --- |
| `command` | string | sí | Ejecutable a invocar. Para Rust, es la ruta del binario compilado; para Python `"python"`; para TypeScript `"node"`. |
| `args` | array de strings | no | Argumentos que se anteponen a `--daemon-addr`, `--plugin-id`, `--auth-token`. Valores típicos: `["-m", "src.plugin"]` para Python o `["dist/index.js"]` para Node. |
| `runtimes` | array de strings | no | Pista para el daemon. Soportados: `"python"`, `"node"`, `"rust"`. Los plugins de Python/Node siempre deberían establecerlo para que el daemon prepare el runtime (por ejemplo, crear un venv con `uv` para Python). |

El daemon añade `--daemon-addr <addr> --plugin-id <id>` a cada invocación y, opcionalmente, `--auth-token <token>` para plugins cliente.

## `[capabilities]` — qué implementa el plugin

Cada campo es un booleano con valor por defecto `false`. Establezca `true` solo para las capacidades que su código realmente maneje — el daemon lo utiliza para asignar recursos y decidir si expone el plugin en la interfaz correspondiente (por ejemplo, añadir sus voces al selector de TTS).

| Capacidad | Propósito |
| --- | --- |
| `tools` | Herramientas de IA invocables por el modelo de chat. |
| `tts` | Proveedor de voces de síntesis de voz. |
| `stt` | Proveedor de idiomas para reconocimiento de voz. |
| `ai_provider` | Backend alternativo de completado de IA. |
| `actions` | Tipos de acciones personalizadas en el Command Graph. |
| `triggers` | Tipos de disparadores personalizados en el Command Graph. |
| `client` | Cliente completo del daemon (requiere token de sesión). |
| `ui_contributions` | Páginas de interfaz, overlays, efectos e inyecciones en slots. |
| `event_handlers` | Suscripción al flujo de eventos del daemon. |

Consulte [Capacidades](capabilities.md) para el comportamiento completo por capacidad.

## `[config]` — ajustes visibles para el usuario

```toml
[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "Token for the remote service",
      "x-secret": true
    },
    "timeout_ms": {
      "type": "number",
      "default": 5000,
      "minimum": 100,
      "maximum": 60000,
      "title": "Timeout (ms)"
    },
    "mode": {
      "type": "string",
      "enum": ["fast", "accurate"],
      "default": "fast",
      "title": "Mode"
    }
  },
  "required": ["api_key"]
}
"""
```

Reglas:

- `schema` es una **cadena con un JSON Schema**. La raíz debe tener `"type": "object"`.
- El daemon renderiza el esquema como un formulario en la página de ajustes del plugin.
- `title` proporciona la etiqueta del campo; `description` se muestra como texto de ayuda.
- `default` suministra el valor inicial.
- `x-secret: true` enmascara el valor en la interfaz y lo almacena cifrado.
- `enum` se renderiza como un desplegable.
- El array `required` marca los campos obligatorios.
- Cuando el usuario actualiza los ajustes, el daemon invoca `OnConfigChanged` con el nuevo bloque JSON.

## Campos TOML fuera del esquema

Los plugins pueden añadir secciones arbitrarias de nivel superior que el daemon ignora — útiles para herramientas. La CLI advierte sobre campos desconocidos pero no los rechaza.

## Localizar el manifiesto

Puede incluir archivos `locales/<lang>.json` dentro del paquete del plugin para traducir las cadenas visibles al usuario (`name`, `description`, etiquetas de acciones, etiquetas de campos, etc.). Utilice el helper `I18n` de cada SDK para leerlos desde su código. Solo se localiza el **texto** del manifiesto — las claves, los IDs y los valores de enum permanecen constantes.

## Validar el manifiesto

```bash
astra-plugin validate
```

Verifica:

- Campos obligatorios presentes (`plugin.id`, `plugin.name`, `plugin.version`, `entry.command`).
- `plugin.id` coincide con alfanumérico en minúsculas más guiones.
- `plugin.version` coincide con SemVer (`X.Y.Z`).
- Al menos una capacidad está habilitada.
- `[config].schema` se analiza como JSON y tiene `"type": "object"` en la raíz.
- Metadatos (description, author) presentes.

Consulte [Referencia de la CLI → validate](cli.md#astra-plugin-validate).
