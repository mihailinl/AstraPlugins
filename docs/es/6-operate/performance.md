> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/6-operate/performance.md) es la referencia autorizada.

# Rendimiento y límites

Cada número de esta página se declara una vez, en un archivo, y se
genera en los sitios que lo necesitan. Ninguno es una suposición.

## Los límites compartidos

[`spec/limits.yaml`](../../../spec/limits.yaml) es el único lugar donde
se escribe un número que debe ser idéntico en el daemon y en los SDK.
`node tools/gen-limits.mjs` regenera las constantes en los tres SDK, y un
`const _: () = assert!(…)` junto a la copia del daemon hace fallar la
compilación hasta que el daemon también se mueva. El bug que lo motivó:
el canal de audio de STT en streaming era 500 en el daemon y 32 en el SDK
de Rust, y el desajuste truncaba en silencio cada enunciado a su primera
fracción.

| Límite | Valor | Qué acota |
|---|---|---|
| `plugin_start_timeout_secs` | **20** | Desde el arranque hasta la primera línea de salida del plugin. Si se incumple, el daemon declara el arranque fallido y recoge el proceso |
| `plugin_stop_grace_secs` | **5** | Desde `Shutdown` hasta que se mata el grupo de procesos. Tu propio presupuesto de drenaje debe estar por debajo de esto, o el daemon te mata antes de que corra tu ruta de limpieza |
| `stt_audio_channel_capacity` | **500** | Chunks almacenados en búfer entre el pipeline de voz del daemon y tu hook `stt`, en ambos extremos. ~10 s de audio: el peor caso de ráfaga inicial de wake-word más audio en vivo llegando mientras un proveedor lento todavía está infiriendo |
| `max_extract_bytes` | **524 288 000** (500 MiB) | Tamaño total sin comprimir que el daemon extraerá de un archivo |
| `max_archive_entries` | **10 000** | Entradas en un archivo |

Los dos últimos son mitigación de zip-bomb, y también una restricción de
empaquetado: un paquete que supere cualquiera de los dos produce un
plugin no instalable, así que la CLI lo rechaza en el momento de la
compilación en lugar de dejar que lo descubras en la máquina de un
usuario.

## `call_timeout_secs` — el que fijas tú

`plugin.call_timeout_secs` en el manifiesto es cuánto espera el daemon a
`CallTool` y `ExecuteAction` antes de rendirse. Sin fijar, usa el propio
`PLUGIN_CALL_TIMEOUT` del daemon, que es deliberadamente menor que "para
siempre".

**Un plugin que da la cara por un agente de larga ejecución debe
declararlo.** Si no, el daemon descarta tu resultado mientras tu
subproceso sigue corriendo — el usuario ve un fallo y la máquina sigue
haciendo el trabajo.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "coding-agent"
name = "Coding Agent"
version = "0.1.0"
license = "MIT"
author = "You"
# This plugin runs an agent that can legitimately take minutes.
call_timeout_secs = 180

[entry]
command = "bin/coding_agent"

[capabilities]
tools = true
```

Es por plugin, del mismo modo que el timeout de un servidor MCP es por
servidor. Ajústalo a lo que necesite tu llamada legítima más lenta, no a
la mayor cifra que se te ocurra: el timeout es también lo que impide que
un plugin atascado cuelgue una conversación.

## Presupuesto de arranque, por lenguaje

Los 20 s son generosos, y dos de los tres lenguajes aun así logran
gastarlos.

| | Arranque en frío típico | Lo que se lo come |
|---|---|---|
| Rust | milisegundos | nada |
| TypeScript | arranque en frío de Node | el paquete es un solo archivo, así que no hay resolución de módulos sobre un árbol |
| Python | intérprete + importación de `grpcio` | una dependencia grande importada en el ámbito del módulo |

El arreglo es el mismo en ambos casos interpretados: **importa de forma
perezosa, dentro del hook que lo necesite.** Un modelo que cargas en
`on_start` es un modelo que el usuario espera antes de que el plugin
esté vivo; un modelo que cargas en la primera llamada es uno que espera
una sola vez.

`astra-plugin test` mide el número real en tu máquina y lo imprime junto
al presupuesto:

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.5ms after Shutdown
         (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
```

## Apagarse dentro del margen de gracia

`Shutdown` se responde, y luego sales. Cinco segundos después se mata el
grupo de procesos. Todo lo que debas descargar (flush) — un archivo, una
sesión upstream — se descarga dentro de esa ventana o no se descarga en
absoluto.

Un apagado a nivel de todo el daemon concede un margen **mucho más
corto**, acotado por el plazo total de desmontaje. No trates los 5 s
como un presupuesto que puedes gastar; trátalos como un techo bajo el
que deberías quedarte con margen de sobra.

## Chequeos de salud

`HealthCheck` se ejecuta cada 15 s. No pasa por el helper de hook
opcional del daemon, así que **cualquier** error — `UNIMPLEMENTED`
incluido — marca el plugin como muerto. Si lo sobrescribes, hazlo barato
y hazlo total: un chequeo de salud que llama a un servicio upstream
convierte la caída de ese servicio en que tu plugin quede marcado como
muerto.

## Tamaño del paquete

Nada impone un máximo más allá de los límites de extracción, pero vale
la pena saber dos cosas:

- Un paquete de Rust es un binario de release sin símbolos y suele
  pesar unos pocos megabytes.
- Un paquete de TypeScript **no** distribuye `node_modules` —
  `astra-plugin build` produce un único archivo CommonJS autocontenido, y
  la CI verifica que nada quede buscando un módulo en tiempo de
  ejecución.

El empaquetado reproducible (`--reproducible`) fija el orden de las
entradas, el mtime y el nivel de compresión para que dos compilaciones de
las mismas entradas sean idénticas byte a byte. El workflow de release
ejecuta un canario en cada release, lo que hace significativa la
recompilación por parte de un tercero.

## Dónde viven estos números

| Número | Declarado en |
|---|---|
| Los cinco de arriba | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| `call_timeout_secs` | tu `plugin.toml` — [referencia](../reference/manifest.md) |
| Intervalo de chequeo de salud, timeout por llamada por defecto | el daemon |
</content>
