> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/music-provider-plugins.md) maßgeblich.

# Musikdienst-Plugins

Ein Musikdienst-Plugin deklariert `music_provider = true` im Abschnitt
`[capabilities]` seiner `plugin.toml`. Damit wird es zur Quelle von
**Mediensitzungen** für Astra: Das Musik-Widget, die Dynamic Island und die
Medienwerkzeuge des Assistenten (`get_now_playing`, `control_media`,
`play_music`, `get_music_queue`) erreichen die Dienste, mit denen es spricht —
die Web-API von Spotify, die lokale API eines Desktop-Players, eine Brücke in den
Browser — und können einen Titel IM Dienst liken, seine Warteschlange lesen, den
Katalog durchsuchen und dort die Wiedergabe starten.

Das Plugin zeichnet dafür keine eigene Oberfläche. Das übernimmt Astras Player.

## Was Astra übernimmt, damit das Plugin es nicht tun muss

Der Medien-Hub des Daemons erledigt alles rund um das Plugin:

- **Zuordnung.** Spielt der Dienst auf diesem Computer, hat das Betriebssystem
  meist eine Mediensitzung für genau diese Wiedergabe (die Spotify-App, ein
  Browser-Tab). Der Hub verbindet beide, sodass ein Lied eine Sitzung ist: Die
  OS-Sitzung erhält deinen Like-Knopf und deine Warteschlange, nichts erscheint
  doppelt. Das Betriebssystem bleibt die Wahrheit darüber, was zu HÖREN ist —
  Titel, Cover und Position von dir überschreiben es nie.
- **Entfernte Sitzungen.** Eine Sitzung, die du als NICHT auf diesem Gerät
  meldest (ein Telefon, ein Lautsprecher), erscheint als eigene, entfernte
  Sitzung. Sie wird nie als „dieser Computer“ ausgegeben — die Island ignoriert sie.
- **Weiterleitung.** Bei einer verbundenen Sitzung laufen Play/Pause/Next/Seek
  über das Betriebssystem, was für jede App funktioniert; Like, Unlike, Shuffle,
  Repeat, Lautstärke, Warteschlange und das Abspielen kommen zu dir.
- **Grenzen und Sicherheit.** Cover lädt der Daemon (nur https, nie aus dem
  Netz dieses Rechners); Links sind https oder ein bekanntes App-Schema; Texte
  und Listen werden gekürzt; alles, was das Modell von dir liest, ist als
  nicht vertrauenswürdiger Text markiert.

Das Plugin meldet also, was jeder Dienst spielt, und führt jeweils einen Befehl aus.

## Einen Provider anlegen

<!-- doctest: cli -->
```bash
astra-plugin new my-music --lang python --template blank --capabilities music_provider --output ./my-music
```

`--lang` kann auch `rust` oder `typescript` sein. Eine Musik-Vorlage gibt es
nicht: Die Capability kommt über `--capabilities`, und `music_control` im Gerüst
antwortet `not_configured`, bis du es implementierst. `astra-plugin test` prüft
die Hooks mit einer Sitzung und einem Element, die kein Plugin meldet. Einen
Sitzungsschlüssel, den dein Plugin nie veröffentlicht hat, beantwortet das SDK mit
`not_found`, bevor dein Hook läuft — die Probe kann an deinem eigenen Player also
nichts pausieren oder liken. Ausnahme ist `MusicSearch`: Es schickt eine echte
Suchanfrage, ein angemeldetes Plugin antwortet also aus dem Live-Dienst (Suchen
ändert nichts).

Setze `min_astra_version`: `[capabilities]` ist eine geschlossene Menge, ein
Astra, das älter ist als das mit `music_provider`, lehnt das ganze Manifest ab.

## Melden: immer die ganze Menge veröffentlichen

Melden ist Push. Jedes SDK hält einen Publisher — `self.music` in Python und
TypeScript, einen `MusicPublisher`, den du in Rust aus `music_publisher`
zurückgibst — und bedient daraus den langlebigen `MusicSubscribe`-Stream des
Daemons: den neuesten Stand sofort, erneut bei jeder Veröffentlichung und alle
`music_snapshot_heartbeat_secs` (15 s), damit ein verstummtes Plugin auffällt.
Einem Stand, der älter als `music_session_stale_secs` (45 s) ist, glaubt der
Daemon nicht mehr.

**Jede Veröffentlichung ist die GANZE Menge.** Eine weggelassene Sitzung ist beendet.

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

Die Felder, die über die Zuordnung entscheiden:

| Feld | Bedeutung |
|---|---|
| `this_device` | der Ton kann aus DIESEM Computer kommen. Nur eine solche Sitzung kann sich mit einer OS-Sitzung verbinden |
| `exclusive_app_hints` | OS-Sitzungs-IDs einer App, die nur diesen Dienst spielt — die Spotify-Programmdatei, ein MPRIS-Playername. Eine Übereinstimmung genügt |
| `shared_app_hints` | Hosts für vieles, etwa Browser. Verbunden wird nur, wenn auch Titel und Interpret übereinstimmen |

Ein Hinweis wird ohne Groß-/Kleinschreibung mit der OS-Sitzungs-ID verglichen,
mit ihrem letzten Pfad- oder AppUserModelId-Segment, diesem Segment ohne `.exe`
und dem Namen eines MPRIS-Players — `spotify` benennt also
`C:\…\Spotify.exe`, `SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify` und
`org.mpris.MediaPlayer2.spotify` gleichermaßen.

`controls` nennt die Verben einer Sitzung aus einer festen Liste; alles andere
verwirft der Daemon: `play`,
`pause`, `next`, `previous`, `seek`, `like`, `unlike`, `shuffle`, `repeat`,
`volume`, `queue` (du beantwortest `MusicGetQueue`) und `play_into` (du
beantwortest `MusicPlay`).

## Antworten: vier Hooks

| Hook | Pflicht | Was er tut |
|---|---|---|
| `MusicControl` | erforderlich | ein Befehl für eine Sitzung; `value` enthält Sekunden für `seek`, `0`–`100` für `volume`, `on`/`off` für `shuffle`, `off`/`track`/`context` für `repeat` |
| `MusicGetQueue` | optional | die Warteschlange der Sitzung um das laufende Element, mit `current_index` |
| `MusicSearch` | optional | eine Katalogsuche; das `item_ref` jedes Elements gehört dir und kommt in `MusicPlay` zurück |
| `MusicPlay` | optional | ein Element oder den ersten Treffer zu Wörtern starten — `mode` ist `now`, `next` oder `end` |

**Eine Ablehnung, die du meinst, ist eine Antwort**, kein Fehler: Der Nutzer ist
nicht angemeldet, der Dienst verlangt ein Abo, nirgends läuft etwas. Wirf oder
gib die Ablehnung des SDK zurück — `MusicRefusal` in allen dreien — mit einem von
`not_supported`, `not_found`, `no_active_device`, `auth`, `premium_required`,
`rate_limited`, `unavailable`, `not_configured`. Der Daemon zeigt sie der Person
in ihrer Sprache. Jeder andere Fehler meldet das Plugin als defekt.

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

## Typische Fehler

- **Melde Positionen so, wie du sie gelesen hast**, nicht weit vorausgerechnet.
  Der Daemon rechnet eine laufende Sitzung ab dem Zeitpunkt weiter, zu dem diese
  Position zuerst gemeldet wurde: Eine unverändert erneut gesendete Sitzung (der
  Heartbeat tut das) behält ihren Zeitstempel, eine neue Position startet ihn neu.
- **Halte Sitzungsschlüssel stabil** (`[A-Za-z0-9._-]{1,64}`), solange es dieselbe
  Wiedergabe ist; ein neuer Schlüssel ist eine neue Sitzung.
- **Melde einen Browser-Tab nicht als exklusiv.** Ein Browser spielt vieles; so
  landet dein Like-Knopf auf dem Video eines anderen.
- **Halte Anmelde-Tokens aus `[config]` heraus.** Astra speichert die Konfiguration
  als einfaches JSON und zeigt sie auf der Plugins-Seite; nutze den Schlüsselbund
  des Betriebssystems.
