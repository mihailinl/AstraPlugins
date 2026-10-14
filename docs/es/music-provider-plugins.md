> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/music-provider-plugins.md) es la referencia autorizada.

# Plugins de servicios de música

Un plugin de servicio de música declara `music_provider = true` en la sección
`[capabilities]` de su `plugin.toml`. Así se convierte en una fuente de
**sesiones multimedia** para Astra: el widget de música, la Dynamic Island y las
herramientas multimedia del asistente (`get_now_playing`, `control_media`,
`play_music`, `get_music_queue`) llegan a los servicios con los que habla —la API
web de Spotify, la API local de un reproductor de escritorio, un puente al
navegador— y pueden marcar «me gusta» EN el servicio, leer su cola, buscar en su
catálogo e iniciar la reproducción allí.

El plugin no dibuja ninguna interfaz para esto. Lo hace el reproductor de Astra.

## Lo que hace Astra para que el plugin no tenga que hacerlo

El hub multimedia del daemon se ocupa de todo lo que rodea al plugin:

- **Emparejamiento.** Cuando el servicio suena en este equipo, el sistema suele
  tener una sesión multimedia de esa misma reproducción (la app de Spotify, una
  pestaña del navegador). El hub las une, de modo que una canción es una sesión:
  la sesión del sistema recibe tu botón de «me gusta» y tu cola, y nada aparece
  dos veces. El sistema sigue siendo la verdad sobre lo que SE OYE: tu título,
  tu carátula y tu posición nunca lo sobrescriben.
- **Sesiones remotas.** Una sesión que indicas que NO suena en este dispositivo
  (un móvil, un altavoz) se muestra como sesión propia, marcada como remota. Nunca
  se ofrece como «este equipo»; la isla la ignora.
- **Enrutamiento.** En una sesión emparejada, play/pause/next/seek van por el
  sistema, que funciona con cualquier app; «me gusta», quitarlo, aleatorio,
  repetición, volumen, la cola y reproducir algo llegan a ti.
- **Límites y seguridad.** Las carátulas las descarga el daemon (solo https y
  nunca desde la red de este equipo); los enlaces son https o un esquema de app
  conocido; los textos y las listas se recortan; todo lo que el modelo lee de ti
  se marca como texto no fiable.

Así que el plugin informa de lo que suena en cada servicio y ejecuta una acción
cada vez.

## Crear un proveedor

<!-- doctest: cli -->
```bash
astra-plugin new my-music --lang python --template blank --capabilities music_provider --output ./my-music
```

`--lang` también puede ser `rust` o `typescript`. No hay plantilla de música:
la capacidad llega con `--capabilities`, y el `music_control` del esqueleto
responde `not_configured` hasta que lo implementes. `astra-plugin test` prueba
los hooks con una sesión y un elemento que ningún plugin informa. El SDK responde
`not_found` a una clave de sesión que tu plugin nunca publicó, antes de que se
ejecute tu hook, así que la prueba no puede pausar ni marcar «me gusta» nada en tu
propio reproductor. La excepción es `MusicSearch`: envía una consulta real, así
que un plugin con sesión iniciada responde desde el servicio en vivo (buscar no
cambia nada).

Fija `min_astra_version`: `[capabilities]` es un conjunto cerrado, y un Astra
anterior al que introdujo `music_provider` rechaza el manifiesto entero.

## Informar: publica siempre el conjunto completo

Informar es push. Cada SDK guarda un publicador —`self.music` en Python y
TypeScript, un `MusicPublisher` que devuelves desde `music_publisher` en Rust— y
sirve con él el flujo de larga duración `MusicSubscribe` del daemon: la última
instantánea al momento, de nuevo con cada publicación y cada
`music_snapshot_heartbeat_secs` (15 s), para notar un plugin que calla. El daemon
deja de creer una instantánea más antigua que `music_session_stale_secs` (45 s).

**Cada publicación es el conjunto COMPLETO.** Una sesión que dejas fuera ha terminado.

<!-- doctest: illustrative reason="needs a running service account; shows the publish call shape only" -->
```python
self.music.publish(
    [MusicService("spotify", "Spotify", can_search=True, can_play=True)],
    [MusicSession(
        session_key="spotify",
        service_id="spotify",
        this_device=True,
        device_name="DESKTOP-1",
        exclusive_app_hints=["spotify", "spotify.exe"],
        status="playing",
        title="Believer",
        artist="Imagine Dragons",
        artwork_url="https://i.scdn.co/image/…",
        position_seconds=42.0,
        duration_seconds=204.0,
        liked=True,
        controls=["play", "pause", "next", "previous", "seek", "like", "unlike", "queue", "play_into"],
    )],
)
```

Los campos que deciden el emparejamiento:

| Campo | Significado |
|---|---|
| `this_device` | el audio puede salir de ESTE equipo. Solo una sesión así puede emparejarse con una del sistema |
| `exclusive_app_hints` | identificadores de sesión del sistema de una app que solo reproduce este servicio: el ejecutable de Spotify, el nombre de un reproductor MPRIS. Basta con que coincida |
| `shared_app_hints` | anfitriones de muchas cosas, como los navegadores. Solo se empareja si además coinciden el título y el artista |

Una pista se compara sin distinguir mayúsculas con el identificador de la sesión
del sistema, su último segmento de ruta o de AppUserModelId, ese segmento sin
`.exe` y el nombre de un reproductor MPRIS; así `spotify` nombra por igual
`C:\…\Spotify.exe`, `SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify` y
`org.mpris.MediaPlayer2.spotify`.

`controls` indica qué verbos admite una sesión, de una lista fija; el daemon
descarta todo lo demás: `play`,
`pause`, `next`, `previous`, `seek`, `like`, `unlike`, `shuffle`, `repeat`,
`volume`, `queue` (respondes a `MusicGetQueue`) y `play_into` (respondes a
`MusicPlay`).

## Respuestas: cuatro hooks

| Hook | Requisito | Qué hace |
|---|---|---|
| `MusicControl` | obligatorio | una acción sobre una sesión; `value` lleva segundos para `seek`, `0`–`100` para `volume`, `on`/`off` para `shuffle`, `off`/`track`/`context` para `repeat` |
| `MusicGetQueue` | opcional | la cola de la sesión alrededor del elemento que suena, con `current_index` |
| `MusicSearch` | opcional | una búsqueda en el catálogo; el `item_ref` de cada elemento es tuyo y vuelve en `MusicPlay` |
| `MusicPlay` | opcional | iniciar un elemento o la primera coincidencia de unas palabras; `mode` es `now`, `next` o `end` |

**Un rechazo que quieres expresar es una respuesta**, no un error: el usuario no
ha iniciado sesión, el servicio exige suscripción, no suena nada en ningún sitio.
Lanza o devuelve el rechazo del SDK —`MusicRefusal` en los tres— con uno de
`not_supported`, `not_found`, `no_active_device`, `auth`, `premium_required`,
`rate_limited`, `unavailable`, `not_configured`. El daemon se lo muestra a la
persona en su idioma. Cualquier otro error indica que el plugin está roto.

<!-- doctest: illustrative reason="the service calls are placeholders; shows the refusal shape only" -->
```python
async def music_control(self, request):
    if not self.signed_in:
        raise MusicRefusal(MusicErrorCode.NOT_CONFIGURED, "Connect Spotify in the plugin's settings")
    device = self.devices.get(request.session_key)  # act on THE session named
    if device is None:
        raise MusicRefusal(MusicErrorCode.NOT_FOUND, "That player has gone")
    await device.do(request.action, request.value)
```

## Errores fáciles de cometer

- **Informa las posiciones tal como las lees**, sin extrapolarlas mucho por
  delante. El daemon extrapola una sesión en curso desde que esa posición se
  informó por primera vez: una sesión reenviada sin cambios (el latido lo hace)
  conserva su marca de tiempo, y publicar una posición nueva la reinicia.
- **Mantén estables las claves de sesión** (`[A-Za-z0-9._-]{1,64}`) mientras sea
  la misma reproducción; una clave nueva es una sesión nueva.
- **No declares exclusiva una pestaña del navegador.** Un navegador reproduce
  muchas cosas; así tu botón de «me gusta» acabaría en el vídeo de otro.
- **No guardes los tokens de acceso en `[config]`.** Astra guarda la configuración
  como JSON plano y la muestra en la página de plugins; usa el llavero del sistema.
