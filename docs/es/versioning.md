> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/versioning.md) es la referencia autorizada.

# Política de versionado y desuso

Qué significan los números, cuánto tiempo se garantiza que siga
funcionando algo de lo que dependes, y dónde está escrita esa garantía
como datos en lugar de como una promesa que alguien tiene que recordar.

## Cuatro números, y solo uno de ellos es del SDK

| Número | Dónde vive | Qué te dice |
| --- | --- | --- |
| **Versión del SDK** | `astra-plugin-sdk/Cargo.toml`, `astra-plugin-sdk-python/pyproject.toml`, `astra-plugin-sdk-ts/package.json` | La API de autoría contra la que escribes. Cada paquete mantiene la suya. |
| **Tren de release** | la etiqueta git `sdk-v<VERSION>` | Una etiqueta publica los tres SDK a la vez. Nombra la versión del **crate de Rust**. |
| **Versión de protocolo** | `proto/PROTO_VERSION` (`protocol=1`), reflejada como `PROTOCOL_VERSION` en cada SDK | El contrato de cable entre un plugin y el daemon. |
| **La versión de tu plugin** | tu `plugin.toml` | La tuya. El registro ordena los releases por ella. |

Las tres versiones de SDK deliberadamente no se mantienen iguales. El
tren actual es `sdk-v0.6.0`, y publica:

| Paquete | Registro | Versión |
| --- | --- | --- |
| `astra-plugin-sdk` (Rust) | crates.io | 0.6.0 |
| `astra-plugin-macros` | crates.io | 0.6.0 — publicado **antes** que el SDK, que depende de él por versión |
| `astra-plugin-sdk` (Python) | PyPI | 0.5.0 |
| `astra-plugin-sdk` (TypeScript) | npm | 0.5.0 |

Un número de versión responde "contra qué API estoy escribiendo", así
que un paquete que ha tenido menos releases con cambios incompatibles
tiene un número menor. Lo que garantiza el tren es que los paquetes que
comparten una etiqueta hablan el **mismo protocolo** e implementan los
mismos hooks — para eso están `spec/hooks.yaml` y el verificador de
paridad.

## SemVer, en 0.x

Los tres paquetes están por debajo de 1.0, y siguen la lectura 0.x de
SemVer:

- **minor** (`0.5 → 0.6`) — puede romper la compatibilidad de código
  fuente. Lee el CHANGELOG.
- **patch** (`0.6.0 → 0.6.1`) — solo correcciones de bugs y adiciones.
  Si un release de patch hace que tu plugin deje de compilar, eso es un
  bug del SDK; repórtalo.

La versión de protocolo es independiente y se mueve por su cuenta. Es
un entero, no SemVer, y la regla para ella no es "lee el changelog"
sino un mecanismo:

- Un hook que la contraparte no tiene responde `UNIMPLEMENTED`, que el
  protocolo define como *ausente*. El daemon lo interpreta así y sigue
  adelante. Por eso un plugin más nuevo funciona contra un daemon más
  antiguo y viceversa.
- `MIN_SUPPORTED_DAEMON_PROTOCOL` en cada SDK es el daemon más antiguo
  con el que ese SDK se registrará. Por debajo de eso, el plugin sale
  con una frase que nombra la solución en lugar de fallar en la primera
  llamada.

## La política de desuso

Cuando algo en la API de autoría va a desaparecer:

1. **Está obsoleto durante al menos dos versiones menores y al menos
   un trimestre calendario**, lo que sea más largo. Obsoleto en 0.6
   significa eliminable en 0.8, y no antes de que pasen tres meses. Un
   plugin que compila hoy sigue compilando durante al menos un release
   que puedas planificar.
2. **La nota de desuso nombra el reemplazo.** Ni "obsoleto", ni "usa la
   nueva API" — el identificador real que deberías escribir en su
   lugar, o las palabras *sin reemplazo* y por qué no lo hay. Un desuso
   que te dice que pares sin decirte adónde ir te manda al rastreador
   de issues.
3. **Las eliminaciones van bajo un encabezado `BREAKING` en el
   CHANGELOG**, en el paquete que lo eliminó, nombrando qué se eliminó
   y qué lo reemplazó. Nada se elimina en un release de patch.

Cómo se ve "obsoleto" en cada lenguaje:

| | Cómo se marca | Qué ves |
| --- | --- | --- |
| Rust | `#[deprecated(since = "0.6.0", note = "…")]` | una advertencia del compilador en el punto de uso, con la nota |
| Python | `DeprecationWarning` en el punto de llamada | `python -W error::DeprecationWarning` lo convierte en un fallo contra el que puedes bloquear la CI |
| TypeScript | `/** @deprecated … */` | un tachado en tu editor y una nota al pasar el cursor |

Un desuso es un aviso, nunca un error. Si un release hace que el código
obsoleto *deje de compilar*, eso es una eliminación, y las eliminaciones
siguen la regla 3.

### Qué está obsoleto ahora mismo

| Qué | Obsoleto en | Eliminado en | Reemplazo |
| --- | --- | --- | --- |
| Rust: toda la superficie del trait 0.5, como `astra_plugin_sdk::compat` | 0.6.0 | 0.8.0 | `PluginCapability` (0.6): `&PluginContext`, `Result<_, ToolError>`, `type Config`. Consulta [migration-0.6.md](migration-0.6.md) |
| Rust: `PluginCapability::source_id()` | 0.6.0 | 0.8.0 | Pasa el id a `Host::send_chat_message`; el daemon dejó de filtrar por source id |
| Rust: `compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.6.0 | 0.8.0 | `Result<String, ToolError>` |
| Rust: alias `compat::HostClient` / `DaemonClient` | 0.6.0 | 0.8.0 | `ctx.host()` / `ctx.daemon()` |
| Python: un `dict` donde se espera una dataclass de capability | 0.5.0 | 0.7.0 | La dataclass — `VoiceInfo`, `ToolDef`, … — o su `to_proto()` |
| TypeScript: el alias de tipo `UiPanel` | 0.5.0 | 0.7.0 | `UiContribution` |
| Hook: `AiGetModels` | 0.6.0 | 0.8.0 | Sin reemplazo — nada en el daemon le pregunta a un plugin qué modelos tiene |

Dos notas al pie, porque ambas son precisamente el tipo de cosa que
esta política existe para prevenir:

- El `DeprecationWarning` de Python para dicts dice que se aceptan
  "durante un release menor más". **La tabla es el número
  vinculante**: dos versiones menores y un trimestre, así que 0.7.0 como
  muy pronto.
- `UiPanel` se marcó obsoleto en TypeScript sin ninguna versión
  registrada en absoluto. Aquí está fechado en 0.5.0 — el primer
  release que lo dice por escrito — y eliminable a partir de 0.7.0.

## La política son datos

Las reglas que solo viven en un documento se olvidan justo en el
momento en que importan: el release en que alguien borra la cosa. Así
que la mitad de la política por hook es una columna en
[`spec/hooks.yaml`](../../spec/hooks.yaml):

<!-- doctest: illustrative reason="one row of spec/hooks.yaml, quoted; the file it belongs to is the source of truth and is checked by tools/parity/check.py" -->
```yaml
  - rpc: AiGetModels
    ...
    routing: deprecated
    deprecated_in: "0.6"
    removed_in: "0.8"
    note: "… Deprecated in 0.6, removed in 0.8, and there is no replacement: nothing in the daemon asks a plugin what models it has, and AiComplete carries the chosen model on the request."
```

`tools/parity/spec.py` valida eso en cada análisis — es decir, en cada
ejecución de `gen.py`, cada ejecución de `check.py`, y por tanto en
cada ejecución de CI:

| Regla | El fallo que previene |
| --- | --- |
| `routing: deprecated` requiere `deprecated_in` | un hook que lleva años "obsoleto" sin ninguna fecha adjunta |
| `deprecated_in` requiere `removed_in` | un desuso sin final, que no es más que un comentario grosero |
| `removed_in` ≥ `deprecated_in` + 2 versiones menores | una eliminación que llega antes de que nadie tuviera un release para migrar |
| la `note` de una fila obsoleta nombra otro rpc, o dice `no replacement` | "obsoleto" sin dirección de reenvío |

Si te equivocas en algo, el verificador lo dice, con el número de línea:

<!-- doctest: output from="python3 tools/parity/check.py on a row whose removed_in violates the policy" -->
```
spec/hooks.yaml is malformed:
  hooks.yaml:336: `AiGetModels` is deprecated in 0.6 and removed in 0.7 — the policy is
  2 minors and one quarter minimum, so the earliest removal is 0.8
```

Las versiones en esas columnas son **versiones menores del SDK**, no
versiones de protocolo: `0.6` es el número en tu `Cargo.toml` y el
número bajo el que se archiva el encabezado del CHANGELOG. La mitad de
un trimestre de la política es calendario en lugar de datos — el tren
de release la fecha, y este documento es donde queda escrito.

## Lo que nada de esto cubre

- **El propio comportamiento del daemon.** La UI de Astra, su
  disposición de config y sus servicios internos no son una API de
  plugin. En lo que un plugin puede confiar es el protocolo, los hooks
  en `spec/hooks.yaml`, y los permisos de su manifiesto.
- **Cualquier cosa marcada `#[doc(hidden)]`, `_private`, o exportada
  para el harness de pruebas.** Puede cambiar en un patch.
- **Hooks `unrouted`.** Un hook puede existir en el proto y en los tres
  SDK y no tener ningún punto de llamada en el daemon —
  `TtsSynthesizeStream` es uno de esos hoy. Implementarlo es seguro y no
  cuesta nada; *depender* de que el daemon lo llame no está soportado
  hasta que su `routing:` diga `live`.

## Si una ventana de desuso no es suficiente

Dilo antes de que se cierre. Una eliminación que ya ha llegado es una
eliminación; una eliminación que todavía es un `removed_in` en
`spec/hooks.yaml` es una fecha, y las fechas pueden moverse si alguien
dice por qué a tiempo.
</content>
