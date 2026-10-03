> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/wakeword-plugins.md) es la referencia autorizada.

# Plugins de palabra de activación

Un plugin de palabra de activación declara `wakeword = true` en la sección
`[capabilities]` de su `plugin.toml`. Astra muestra los plugins instalados con esa
capability en **Voz → Wake Word**. La elección y sus ajustes desaparecen cuando se
desinstala el plugin. El plugin no necesita una página propia ni una contribución
de UI.

## Crear un detector nuevo

Usa la CLI actual y un directorio de salida nuevo:

<!-- doctest: cli -->
```bash
astra-plugin new my-wakeword --lang rust --template blank --capabilities wakeword --output ./my-wakeword
```

`--lang` también puede ser `python` o `typescript`. Todavía no hay una plantilla
de palabra de activación. El scaffold vacío de Rust incluye una herramienta
`hello` que no tiene nada que ver, y su test: sustituye ambos. Deja
`wakeword = true` como única capability salvo que el plugin sirva de verdad otras
funciones. `astra-plugin check` detecta una discrepancia entre el manifiesto y el
binario compilado.

El daemon envía las tres llamadas descritas abajo a través de `CallFromUi`,
incluso a un plugin que solo declara `wakeword`. Es una reutilización del
transporte; no requiere `ui_contributions`, ni un iframe, ni `push_to_ui`. Las
tablas genéricas de hooks listan `CallFromUi` bajo UI porque ese es su uso
original.

En Rust, implementa el hook del SDK `handle_ui_call(&self, ctx: &PluginContext,
method: &str, params_json: &str) -> Result<String, ToolError>` o usa métodos
`#[ui_call]` (con `#[ui_call(name = "process-audio")]` y
`#[ui_call(name = "reset-audio")]` para los nombres con guion); cada método
`#[ui_call]` necesita un comentario de documentación `///`, o la macro se niega a
compilarlo. Pon `#[astra::plugin(capabilities = "wakeword")]` en el bloque impl
(el scaffold de arriba ya lo hace): de lo contrario, la inferencia automática a
partir de `#[ui_call]` declara `ui_contributions`, lo que contradice el
manifiesto. Dirige `status`, `reset-audio` y `process-audio` a una única
instancia del detector cuyo búfer de tramas se conserve entre llamadas. Devuelve
cadenas JSON con las formas de respuesta de abajo.
En Python, usa los handlers `@ui_call` del SDK; en TypeScript, usa
`ui: { contributions: [], onCall: { ... } }` con los tres nombres de método.
Estos handlers no crean ninguna página de UI visible.
Consulta las guías del SDK de [Rust](4-sdk/rust.md), [Python](4-sdk/python.md) y
[TypeScript](4-sdk/typescript.md) para el punto de entrada, el acceso a la
configuración y el ciclo de vida.

El plugin aporta sus ajustes mediante el JSON Schema de `[config]` que ya
existe. Astra muestra los campos en Voz solo mientras ese plugin está
seleccionado y los guarda mediante `UpdatePluginConfig`. Se admiten propiedades
de tipo cadena, número, booleano y enum. Una cadena con `"format": "password"` usa
un campo de contraseña; `"format": "file"` (o
`"x-astra-field-type": "file_picker"`) ofrece un selector de archivos local.
`"x-astra-field-type": "slider"` y `"textarea"` eligen esos controles para
propiedades numéricas y de cadena. El plugin lee la ruta configurada; Astra no
impone ningún formato de modelo de palabra clave.

El protocolo 1 usa el canal autenticado de petición/respuesta `CallFromUi` para
tres métodos. Es una llamada interna del daemon; no se crea ningún iframe ni
ninguna página.

| Método | JSON de la petición | JSON de la respuesta |
|---|---|---|
| `status` | `{}` | `{"ready": true}` o `{"ready": false, "message": "…"}` |
| `process-audio` | `{"pcm_base64": "…"}` | `{"detected": false}` o `{"detected": true}` |
| `reset-audio` | `{}` | `{}` |

`pcm_base64` contiene PCM mono a 16 kHz, con signo, de 16 bits y little-endian.
Astra envía 100 ms (1600 muestras) por llamada. El plugin debe conservar muestras
entre llamadas si su detector usa otra longitud de trama. `reset-audio` descarta
ese audio conservado y el estado parcial de detección del modelo cuando Astra
reinicia la compuerta de activación. Decodifica el Base64, rechaza el PCM mal
formado o de longitud impar, convierte cada par de bytes little-endian en un
`i16` y pasa las muestras al detector en orden. No trates cada bloque de 100 ms
como un enunciado completo. Cada llamada tiene un plazo de dos segundos; el bucle
de audio usa una cola acotada y nunca espera al plugin.
`astra-plugin test` llama a los tres métodos y comprueba la forma de sus
respuestas JSON, incluido un bloque de audio todo a cero mientras el plugin puede
estar sin configurar. Esa prueba no verifica que se detecte la palabra clave
elegida. Antes de entregarlo, carga un modelo válido y comprueba
`status.ready = true`; reproduce varias grabaciones de la frase de activación
repartidas en varias llamadas de 100 ms; y reproduce silencio, ruido de fondo y
habla corriente como casos negativos. Verifica que `reset-audio` borra una frase
a medias y que la detección funciona después del reinicio. Después instala el
plugin o cárgalo por sideload, selecciónalo en **Voz → Wake Word** y confirma que
Astra empieza a escuchar y se activa con la frase. Un modelo sin configurar
debería informar `ready: false` con un mensaje útil.

Astra comprueba `status.ready` antes de empezar a escuchar. Si el plugin
seleccionado falta, está detenido o no está listo, la escucha falla de forma
cerrada en lugar de convertirse en silencio en una transcripción continua. La
selección en tiempo de ejecución usa `voice.wake_word_mode = "plugin__<id>"`,
sustituyendo los guiones del ID del plugin por guiones bajos, como hacen los IDs
de proveedor de los plugins de STT y TTS.
Informa `ready: true` solo cuando el detector y su modelo configurado puedan
procesar audio; que exista una ruta de archivo no basta.
