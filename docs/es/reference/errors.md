> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/reference/errors.md) es la referencia autorizada. La página en inglés está GENERADA por `tools/docgen/errors.py` — esta traducción es una instantánea mantenida a mano, no otra copia generada.

# Referencia de errores

Una taxonomía, cuatro implementaciones, y esta página es la unión. Los
ocho códigos por llamada están escritos por extenso en el proto y en
cada uno de los tres SDK, y nada los enlaza entre lenguajes en tiempo de
compilación — así que se comparan aquí, y una discrepancia hace fallar
el build en lugar de convertirse en una página que documenta la versión
de la verdad de un solo SDK.

## Los dos canales

**En banda — el error que lee el llamador.** Un tool que falló ha
producido un resultado. `NOT_CONFIGURED: OpenAI API key is not set` es
lo que el modelo tiene que ver para decirle al usuario qué hacer, y lo
que la UI convierte en un enlace a ese campo exacto de ajustes. Viaja
dentro del mensaje de respuesta.

**Transporte — `Status` de gRPC.** Reservado para cuando la llamada
nunca llega al handler: no existe tal hook, no autenticado, conexión
perdida. `UNIMPLEMENTED` significa *este plugin no tiene ese hook*, que
es una afirmación sobre la forma del plugin y no sobre esta llamada — el
daemon lo lee como "hook ausente" y sigue adelante. Devolver un error de
transporte para un fallo por llamada tira esa distinción por la borda y,
para un tool, pierde la respuesta del modelo.

La columna de transporte de abajo es el mapeo fijo, usado por los hooks
cuyo mensaje de respuesta no tiene campo de error en banda (TTS, STT,
AI). Es una biyección: un plugin que reenvía un fallo gRPC recibe de
vuelta el mismo código que introdujo.

## Los ocho códigos por llamada

| Código | Proto | Rust | Python | TypeScript | Transporte |
|---|---|---|---|---|---|
| `BAD_ARGUMENTS` | `PLUGIN_ERROR_BAD_ARGUMENTS` = 4 | `ToolError::BadArguments` | `BadArguments` | `BadArguments` | `INVALID_ARGUMENT` |
| `NOT_FOUND` | `PLUGIN_ERROR_NOT_FOUND` = 5 | `ToolError::NotFound` | `NotFound` | `NotFound` | `NOT_FOUND` |
| `NOT_CONFIGURED` | `PLUGIN_ERROR_NOT_CONFIGURED` = 6 | `ToolError::NotConfigured` | `NotConfigured` | `NotConfigured` | `FAILED_PRECONDITION` |
| `UNAUTHORIZED` | `PLUGIN_ERROR_UNAUTHORIZED` = 7 | `ToolError::Unauthorized` | `Unauthorized` | `Unauthorized` | `PERMISSION_DENIED` |
| `RATE_LIMITED` | `PLUGIN_ERROR_RATE_LIMITED` = 8 | `ToolError::RateLimited` | `RateLimited` | `RateLimited` | `RESOURCE_EXHAUSTED` |
| `UNAVAILABLE` | `PLUGIN_ERROR_UNAVAILABLE` = 9 | `ToolError::Unavailable` | `Unavailable` | `Unavailable` | `UNAVAILABLE` |
| `TIMEOUT` | `PLUGIN_ERROR_TIMEOUT` = 10 | `ToolError::Timeout` | `Timeout` | `Timeout` | `DEADLINE_EXCEEDED` |
| `INTERNAL` | `PLUGIN_ERROR_INTERNAL` = 11 | `ToolError::Internal` | `InternalError` | `InternalError` | `INTERNAL` |

### `ToolError::Documented` — una variante sin código propio

Cualquiera de los anteriores, más una página que documenta *este*
fallo — la propia documentación del plugin, o el "cómo conseguir una
clave de API" del proveedor upstream. Se construye con
[`ToolError::with_doc_url`]; la UI lo renderiza como un enlace junto al
mensaje.

### Qué significa cada uno

**`BAD_ARGUMENTS`.** Los argumentos no se analizaron correctamente, o
violan el propio contrato del tool. El llamador puede reintentar con
argumentos distintos; reintentar los mismos no puede ayudar. `message`
nombra el campo culpable.

**`NOT_FOUND`.** Lo referenciado no existe (un nombre de tool
desconocido, un id para el que el propio almacén del plugin no tiene
fila).

**`NOT_CONFIGURED`.** El plugin necesita una configuración que el
usuario no ha suministrado. EL código que debe establecer
`config_field`: es lo que convierte "este tool necesita una clave de
API" en un enlace que abre exactamente ese campo de ajustes.

**`UNAUTHORIZED`.** Las propias credenciales del plugin fueron
rechazadas por aquello con lo que habla, o al llamador no se le permite
invocar esto. Distinto de NOT_CONFIGURED: un valor SÍ está presente,
simplemente no se acepta.

**`RATE_LIMITED`.** Un límite de tasa — propio del plugin, o de un
servicio upstream. Establece `retry_after_ms` cuando el límite indica
cuándo.

**`UNAVAILABLE`.** Una dependencia que el plugin necesita está caída o
inalcanzable. Se asume transitorio; una llamada idéntica posterior
podría tener éxito.

**`TIMEOUT`.** El plugin dejó de esperar algo. Se distingue de
UNAVAILABLE solo en que fue el plugin, no el llamador, quien se quedó
sin tiempo.

**`INTERNAL`.** Un fallo inesperado dentro del plugin — un bug, un
panic capturado por el SDK. El comodín, y el código que usa un SDK
cuando no tiene nada mejor.

## Rechazos de registro

El mismo enum lleva los códigos con los que un daemon responde a
`Register`. Un plugin nunca produce uno; lo recibe, y luego sale.

| Código | Número | Qué significa |
|---|---|---|
| `PLUGIN_ERROR_PROTOCOL_TOO_OLD` | 1 | El plugin habla un protocolo de cable más antiguo que el piso de este daemon (`PluginRegisterResponse.min_supported_protocol`). La solución es siempre "recompilar contra un SDK más nuevo"; `hint` lo dice, con los números. |
| `PLUGIN_ERROR_AUTH` | 2 | El `auth_token` del momento de arranque faltaba o no coincidía. |
| `PLUGIN_ERROR_UNKNOWN_PLUGIN` | 3 | El daemon no conoce ese id de plugin, o no está en un estado registrable. |

`PLUGIN_ERROR_UNSPECIFIED = 0` es el valor cero de proto3 y significa
que el emisor no estableció nada.

## Los campos que lleva un error

| Campo | Para | Qué es |
|---|---|---|
| `code` | cada código | Uno de los códigos de arriba. |
| `message` | cada código | Qué salió mal. |
| `hint` | cada código | Qué HACER al respecto. |
| `config_field` | `NOT_CONFIGURED` | Destino de deep-link: el campo de config del plugin que el usuario debe rellenar, nombrado exactamente como aparece en el schema de config del plugin (`api_key`, `account.token`). |
| `retry_after_ms` | `RATE_LIMITED` | Cuánto esperar antes de reintentar, en milisegundos. |
| `doc_url` | cada código | Una página que documenta ESTE fallo — la propia documentación del plugin, el "cómo conseguir una clave de API" de un proveedor upstream. |

Ambas mitades se envían siempre. El mensaje estructurado es una
adición, no un reemplazo: un plugin construido contra un protocolo más
antiguo no envía detalle estructurado, y uno construido contra este
protocolo que habla con un daemon más antiguo lo pierde en el parser
del receptor. En ambas direcciones sobrevive el string legible por
humanos, así que ambos emparejamientos siguen funcionando — que es
también por qué el string lleva el código como prefijo
(`NOT_CONFIGURED: …`): ese prefijo es lo que le dice al bucle de IA que
deje de reintentar.

## Los hooks ausentes no son errores

"This plugin does not have that hook."

Cada hook con valor por defecto que no tiene un fallback sensato
devuelve esto, y `runner.rs` lo convierte en `Status::unimplemented` —
la palabra del protocolo para *ausente*, que el helper `optional_hook`
del daemon lee como tal (`astra-daemon/src/plugins/manager.rs`). Es
deliberadamente distinto de [`ToolError::Internal`]: "no tengo TTS" y
"mi TTS falló" tienen consecuencias distintas, y responder la segunda
cuando quieres decir la primera hace que el daemon marque como muerto a
un plugin que funciona.
</content>
