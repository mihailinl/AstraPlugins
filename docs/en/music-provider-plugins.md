# Music provider plugins

A music provider plugin declares `music_provider = true` in the `[capabilities]`
section of its `plugin.toml`. It then becomes a source of **media sessions** for
Astra: the music widget, the Dynamic Island and the assistant's media tools
(`get_now_playing`, `control_media`, `play_music`, `get_music_queue`) reach the
services it talks to — Spotify's Web API, a desktop player's local API, a
browser bridge — and can like a track IN the service, read its queue, search its
catalogue and start playback there.

The plugin draws no UI for any of this. Astra's own player does.

## What Astra does, so the plugin does not

The daemon's media hub owns everything around the plugin:

- **Pairing.** When the service plays on this computer, the OS usually has a
  media session for the very same playback (the Spotify app, a browser tab).
  The hub pairs the two, so one song is one session: the OS session gains your
  like button and queue, and nothing is shown twice. The OS stays the truth
  about what is AUDIBLE — your title, artwork and position never overwrite it.
- **Remote sessions.** A session you report as NOT on this device (a phone, a
  speaker) is shown as its own session, marked remote. It is never offered as
  "this computer" — the island ignores it.
- **Routing.** On a paired session, play/pause/next/seek go through the OS,
  which works for every app; like, unlike, shuffle, repeat, volume, the queue
  and playing something come to you.
- **Bounds and safety.** Artwork is fetched by the daemon (https only, never
  this machine's network); links are https or a known app scheme; strings and
  lists are cut; anything the model reads from you is fenced as untrusted text.

So the plugin reports what each service plays, and carries out one verb at a
time.

## Start a provider

<!-- doctest: cli -->
```bash
astra-plugin new my-music --lang python --template blank --capabilities music_provider --output ./my-music
```

`--lang` may also be `rust` or `typescript`. There is no music template: the
capability arrives through `--capabilities`, and the scaffold's `music_control`
answers `not_configured` until you implement it. `astra-plugin test` probes the
hooks with a session and an item no plugin reports. The SDK answers a session
key your plugin never published with `not_found` before your hook runs, so the
probe cannot pause or like anything on your own player. `MusicSearch` is the
exception: it sends a real query, so a signed-in plugin answers it from the
live service (searching changes nothing).

Set `min_astra_version`: `[capabilities]` is a closed set, so an Astra older
than the one that introduced `music_provider` refuses the whole manifest.

## Reporting: publish the whole set

Reporting is push. Every SDK keeps a publisher — `self.music` in Python and
TypeScript, a `MusicPublisher` you return from `music_publisher` in Rust — and
serves the daemon's long-lived `MusicSubscribe` stream from it: the latest
snapshot at once, again on every publish, and every
`music_snapshot_heartbeat_secs` (15 s) so a silent plugin is noticed. A snapshot
older than `music_session_stale_secs` (45 s) is no longer believed.

**Every publish is the WHOLE set.** A session you leave out has ended.

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

The fields that decide pairing:

| Field | Meaning |
|---|---|
| `this_device` | the audio may be coming out of THIS computer. Only such a session can pair with an OS session |
| `exclusive_app_hints` | OS session ids of an app that plays nothing but this service — the Spotify executable, an MPRIS player name. A match pairs on its own |
| `shared_app_hints` | hosts of many things, such as browsers. A match pairs only when the title and artist agree as well |

A hint is compared case-insensitively against the OS session id, its last path
or AppUserModelId segment, that segment without `.exe`, and an MPRIS player's
name — so `spotify` names `C:\…\Spotify.exe`,
`SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify` and
`org.mpris.MediaPlayer2.spotify` alike.

`controls` says which verbs a session takes, from a fixed list; the daemon
drops anything else: `play`, `pause`, `next`, `previous`, `seek`, `like`,
`unlike`, `shuffle`, `repeat`, `volume`, `queue` (you answer `MusicGetQueue`)
and `play_into` (you answer `MusicPlay`).

## Answering: four hooks

| Hook | Requirement | What it does |
|---|---|---|
| `MusicControl` | required | one verb on one session; `value` carries seconds for `seek`, `0`–`100` for `volume`, `on`/`off` for `shuffle`, `off`/`track`/`context` for `repeat` |
| `MusicGetQueue` | optional | the session's queue around the playing item, with `current_index` |
| `MusicSearch` | optional | a catalogue search; each item's `item_ref` is your own and comes back in `MusicPlay` |
| `MusicPlay` | optional | start an item or the first match for words — `mode` is `now`, `next` or `end` |

**A refusal you mean is an answer**, not an error: the user is not signed in,
the service wants a subscription, nothing plays anywhere. Raise or return the
SDK's refusal — `MusicRefusal` in all three — with one of `not_supported`,
`not_found`, `no_active_device`, `auth`, `premium_required`, `rate_limited`,
`unavailable`, `not_configured`. The daemon shows it to the person in their
language. Any other error reports the plugin as broken.

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

## Things that are easy to get wrong

- **Report positions as read, not extrapolated far ahead.** The daemon
  extrapolates a playing session from when that position was first reported:
  a session re-sent unchanged (the heartbeat does that) keeps its stamp, and
  publishing a new position restarts it.
- **Keep session keys stable** (`[A-Za-z0-9._-]{1,64}`) for as long as the
  playback is the same; a new key is a new session.
- **Do not report a browser tab as exclusive.** A browser plays many things;
  claiming it exclusively puts your like button on somebody's video.
- **Keep sign-in tokens out of `[config]`.** Astra stores the config as plain
  JSON and renders it on the Plugins page; use the OS keyring.
