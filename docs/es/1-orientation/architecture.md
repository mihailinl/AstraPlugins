> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/1-orientation/architecture.md) es la referencia autorizada.

# Arquitectura

Cómo se inicia el proceso de un plugin, cómo demuestra quién es, y cuál de
los dos servicios gRPC transporta qué llamada.

## El modelo de procesos

<!-- doctest: illustrative reason="an ASCII diagram of the two services, not code" -->
```
   ┌──────────────────────────┐                  ┌──────────────────────────┐
   │      Astra daemon        │                  │     your plugin          │
   │                          │   spawns with    │     (a separate OS       │
   │  plugin manager ─────────┼──── argv ───────▶│      process, your       │
   │                          │                  │      user account)       │
   │                          │                  │                          │
   │  PluginHostService       │◀── plugin calls ─┤  HostClient              │
   │  (the daemon serves)     │   x-session-token│                          │
   │                          │                  │                          │
   │  capability client ──────┼── daemon calls ─▶│  PluginCapabilityService │
   │                          │   x-plugin-token │  (your plugin serves)    │
   └──────────────────────────┘                  └──────────────────────────┘
             both ends are gRPC over loopback TCP
```

El daemon lanza el proceso con cuatro argumentos. Esta es la línea de
comandos exacta, copiada de una ejecución real de `astra-plugin test`:

<!-- doctest: output from="astra-plugin test . --no-build, in a scaffolded plugin" -->
```
target/release/dice_roller --daemon-addr=127.0.0.1:46495 --plugin-id=dice-roller \
  --auth-token=mock-daemon-spawn-token --capabilities=tools
```

El SDK lo analiza por ti. `--auth-token` es el interesante: es un secreto
que el daemon acuñó para este arranque en concreto, y se usa en **ambas**
direcciones.

## Orden de arranque

El SDK ejecuta una secuencia fija (`astra-plugin-sdk/src/runner.rs`):

<!-- doctest: illustrative reason="the startup order as prose, quoted from runner.rs" -->
```
bind → register → build ctx → on_config → on_language_changed → on_start → serve
```

- **bind antes de register**, porque al daemon se le informa el puerto
  durante `Register` y puede volver a llamar de inmediato. El listener ya
  está activo, así que esas llamadas se encolan en el backlog de aceptación
  en lugar de rechazarse.
- **`on_config` antes de `on_start`**, porque un plugin que arranca un bucle
  en segundo plano necesita primero su configuración.
- **`on_start` antes de `serve`**, y un `Err` de esa función aborta el
  arranque: un plugin que no puede hacer su trabajo no debe ser uno que el
  daemon considere sano.

Dos números acotan esto, ambos declarados una sola vez en
[`spec/limits.yaml`](../../../spec/limits.yaml) y generados en cada SDK:

| Límite | Valor | Qué pasa si lo incumples |
|---|---|---|
| `plugin_start_timeout_secs` | 20 | El daemon declara el arranque fallido y recoge el proceso |
| `plugin_stop_grace_secs` | 5 | Tras `Shutdown`, se mata el grupo de procesos |

## El handshake

1. El daemon lanza el proceso con `--auth-token=<token de arranque>`.
2. El plugin enlaza un servidor gRPC en un puerto loopback asignado por el
   sistema operativo.
3. El plugin llama a `PluginHostService.Register`, presentando el token de
   arranque, su puerto, su versión de protocolo y su lista de capabilities.
4. El daemon responde con un **token de sesión**.
5. Cada llamada posterior de plugin a daemon lleva ese token de sesión en la
   cabecera de metadatos `x-session-token`. `Register` es la única ruta
   exenta (`astra-plugin-sdk/src/auth.rs`); cualquier otra cosa sin él
   vuelve como `unauthenticated`.

Registro, en una ejecución real contra el daemon simulado que arranca
`astra-plugin test`:

<!-- doctest: output from="astra-plugin test . --no-build" -->
```
INFO astra_plugin_sdk::runner: Starting plugin 'dice-roller', connecting to daemon at 127.0.0.1:46495
INFO astra_plugin_sdk::runner: Plugin gRPC server listening on port 41627
INFO astra_plugin_sdk::runner: Registering with capabilities: ["tools"]
INFO astra_plugin_sdk::runner: Registered successfully. Daemon version: mock, protocol: 1 (accepts 0+)
```

### La otra dirección

La dirección daemon → plugin usa el *mismo* token de arranque, devuelto al
plugin en la cabecera `x-plugin-token` en cada llamada. Tu servidor de
capabilities lo comprueba, y el SDK lo hace por ti.

**Esto no lo configuras tú.** El daemon establece
`ASTRA_PLUGIN_CAPABILITY_AUTH=require` en el entorno de tu plugin, lo que le
dice al SDK que rechace cualquier llamada de capability que no lleve el
token. Es el daemon anunciando su propia mitad, en lugar de que alguien
compare números de versión: un daemon lo bastante antiguo como para no
enviar la cabecera no fija ninguna variable, y el SDK se queda en
`CapabilityAuth::Warn` — un token **incorrecto** se rechaza, uno
**ausente** se acepta con un aviso — de modo que tu plugin sigue
funcionando ahí.

Importa porque loopback no es un límite de seguridad. Tu servidor de
capabilities escucha en `127.0.0.1` con un puerto asignado por el sistema
operativo, y cualquier proceso que se ejecute como tu usuario puede
encontrarlo. Sin la cabecera, encontrarlo bastaba para llamar a `CallTool`,
`OnConfigChanged` — redirigir tu URL base de API al host de otra persona,
tras lo cual tu plugin publicaría ahí sus credenciales reales — o
`Shutdown`.

`astra-plugin test` fija la misma variable y presenta el mismo token, así
que lo que pruebas en local es lo que se ejecuta en la máquina de un
usuario.

## Los dos servicios

| | `PluginCapabilityService` | `PluginHostService` |
|---|---|---|
| Servido por | tu plugin | el daemon |
| Llamado por | el daemon | tu plugin |
| Regido por | `[capabilities]` | `[permissions]` |
| Hooks | 25 | 10 |

`PluginService` — el tercer servicio del proto — lo sirve el daemon a la
interfaz de Astra. Ningún plugin lo llama nunca; `astra-plugin dev` y
`astra-plugin logs` sí, como cliente local.

Cada hook, con su capability, su permiso, si es obligatorio, y la línea de
código del daemon que lo llama: [la tabla de paridad](../reference/parity.md).

## Salud, apagado y reinicios

- `HealthCheck` se ejecuta cada 15 s y **no** se trata como opcional:
  cualquier error de esa llamada, `UNIMPLEMENTED` incluido, marca el plugin
  como muerto.
- `Shutdown` se responde y luego sales. El margen es de 5 s.
- Un panic dentro de un handler se captura y se devuelve como error en lugar
  de propagarse a través del servidor gRPC
  (`astra-plugin-sdk/src/panics.rs`). Un panic sigue siendo un error; solo
  que no es una caída del servicio.

## Config

La configuración de un plugin es JSON, almacenada por el daemon, editada en
la interfaz de ajustes de Astra a partir del JSON Schema de tu sección
`[config]`. El daemon la entrega con `OnConfigChanged`, y el plugin también
puede pedirla con `GetPluginSelfConfig` — una de las cuatro llamadas que no
necesita permiso.

La primera carga útil de una instalación nueva es `{}`, por lo que los tipos
de configuración del SDK dan un valor por defecto a cada campo. Consulta
[campos de configuración](../3-reference/config-fields.md).

El archivo de configuración es
`<directorio de config de astra>/plugins/<id>/config.json`
([plataformas](platforms.md) da el directorio por sistema operativo).
**Sobrevive a una actualización** — una actualización es detener, instalar,
arrancar, y la instalación solía ejecutar `remove_dir_all` sobre el
directorio donde vivía la configuración del usuario; ahora el daemon
preserva el archivo y lo verifica con una prueba (`config_survives_update`,
`astra-daemon/src/plugins/manager.rs`), y una copia empaquetada en el nuevo
archivo no puede sobrescribirla. **No** sobrevive a una desinstalación:
`uninstall_plugin` termina con `remove_dir_all`. Cualquier cosa que deba
sobrevivir a una desinstalación pertenece a un lugar que tú controles.

## Dónde vive cada pieza

| Elemento | Ruta |
|---|---|
| Esquema de `plugin.toml` | `astra-plugin-cli/vendor/astra-plugin-manifest/` — una copia idéntica byte a byte del crate que usa el daemon |
| El cable (wire) | [`proto/plugin.proto`](../../../proto/plugin.proto), un recorte generado del `astra.proto` de Astra |
| Tabla de hooks | [`spec/hooks.yaml`](../../../spec/hooks.yaml) |
| Números compartidos | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| Formato de bundle | [`spec/bundle-v2.md`](../spec/bundle-v2.md) |
</content>
