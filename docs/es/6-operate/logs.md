> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/6-operate/logs.md) es la referencia autorizada.

# Logs

Hay tres lugares donde puede terminar la salida de un plugin, y saber
cuál es cuál ahorra una hora.

| | A dónde va | Quién puede verlo |
|---|---|---|
| `tracing::info!` / `logging.info(...)` (el puente de log del SDK) | reenviado al daemon como `PluginLog`, **y** a stderr | tú *y* el usuario, en el panel de logs de Astra |
| `ctx.host().log_info(...)` — la llamada explícita | al daemon | tú y el usuario |
| `println!` / stderr sin más | stdout/stderr del proceso, que el daemon captura | tú, mediante `astra-plugin logs` |

Antes de que existiera el puente, estos eran dos conjuntos distintos, y
las líneas interesantes — un panic, una petición fallida, un reintento —
casi siempre estaban en el conjunto que el usuario no podía ver.

## Leerlos

<!-- doctest: cli -->
```bash
astra-plugin logs
astra-plugin logs dice-roller -f
astra-plugin logs dice-roller -n 500 --daemon-addr 127.0.0.1:32000
astra-plugin logs --json
```

Sin id, lee `plugin.id` del manifiesto en `--path`. Funciona para
plugins **instalados**, que es precisamente el caso que
`astra-plugin dev` no puede atender en absoluto.

El daemon mantiene un **búfer circular acotado por plugin**, y
`GetPluginLogs` es unario sobre él — así que `-f` es un sondeo cada
750 ms, y las líneas "nuevas" son el sufijo de esta cola que no continúa
la anterior. Un reinicio reinicia el búfer.

Pedir más líneas de las que contiene el búfer es inofensivo. `--json`
imprime un documento y sale, que es la forma de instantánea; `-f` y
`--json` no son un par útil.

## Qué reenvía el SDK, y qué no

La capa `tracing` que instala el SDK reenvía al daemon:

- **`INFO` y superiores** por defecto. `ASTRA_PLUGIN_LOG_LEVEL` lo
  cambia; `DEBUG` pertenece a `RUST_LOG` y a stderr, porque el panel es
  para el usuario.
- **No** la pila de transporte — `h2`, `hyper`, `tonic`, `tower`,
  `rustls`, `tokio`. Enviar una línea de log es en sí mismo un RPC, y un
  RPC que registra produce una línea de log: sin esa exclusión, un
  `WARN` de `h2` se convierte en un bucle sin límite.
- **No más de lo que contiene la cola.** El canal está acotado y el
  envío no es bloqueante, así que un plugin en un bucle intenso descarta
  líneas en lugar de generar contrapresión sobre sus propios handlers
  hacia el daemon.

### Python

`install_logging_bridge()` enruta el módulo estándar `logging` de la
misma manera. Úsalo en lugar de `print`: el SDK reconfigura stdout a
**buffering por línea** porque el supervisor del daemon lee stdout para
saber que el plugin está vivo, y una salida con buffering por bloques
llegó a hacer que el supervisor recogiera plugins sanos al llegar al
tiempo de espera de arranque.

## Subir el trace propio de la CLI

`RUST_LOG` controla `astra-plugin` mismo. Estuvo documentado desde 0.1 y
no hacía nada hasta que se instaló un subscriber — cada evento de
`tracing` que emitían la CLI y sus dependencias no iba a ningún sitio.

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

Por defecto es `warn`, y va a **stderr** — la salida orientada al
usuario de la CLI está en stdout, y una línea de trace ahí corrompería un
documento `--json`.

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why do I see no trace output from the CLI?
         RUST_LOG is unset, so only warnings and errors are printed.
         `RUST_LOG=astra_plugin=debug` turns on this CLI's own trace;
         `RUST_LOG=debug` turns on its dependencies' too.
```

## Archivos en disco

| | Linux | Windows |
|---|---|---|
| Logs del daemon | `~/.config/astra/logs/` | `%APPDATA%\astra\astra\config\logs\` |
| Directorio de config que resolvió la CLI | pregúntale a `astra-plugin doctor` | pregúntale a `astra-plugin doctor` |

Los archivos de log del daemon están fechados
(`daemon.log.2026-08-05`). Las líneas propias de un plugin aparecen ahí
vía `PluginLog`, y su stdout/stderr crudo es lo que lee
`astra-plugin logs` del búfer en memoria del daemon — ese búfer no es un
archivo, así que no sobrevive a un reinicio del daemon.

Pregunta, en lugar de asumir, qué directorio usa esta máquina: `doctor`
imprime el que resolvió la CLI, y si Astra discrepa, ambos resolvieron
directorios distintos, lo cual es en sí mismo el bug.

## Cuando no hay ningún log en absoluto

El proceso está fallando antes de que el SDK instale su logging.
Ejecútalo a mano:

<!-- doctest: cli -->
```bash
astra-plugin dev --standalone
```

Eso lanza el plugin directamente en lugar de pedírselo al daemon.
Imprime lo que no puede hacer de esa forma — el plugin no puede
registrarse, porque solo el daemon puede acuñar el token que
`Register` exige.
</content>
