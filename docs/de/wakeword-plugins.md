> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/wakeword-plugins.md) maßgeblich.

# Wake-Word-Plugins

Ein Wake-Word-Plugin deklariert `wakeword = true` im Abschnitt `[capabilities]`
seiner `plugin.toml`. Astra führt installierte Plugins mit dieser Capability unter
**Stimme → Wake Word** auf. Die Auswahl und ihre Einstellungen verschwinden, wenn
das Plugin deinstalliert wird. Das Plugin braucht weder eine eigene Seite noch eine
UI-Contribution.

## Einen neuen Detektor anlegen

Nimm die aktuelle CLI und ein frisches Ausgabeverzeichnis:

<!-- doctest: cli -->
```bash
astra-plugin new my-wakeword --lang rust --template blank --capabilities wakeword --output ./my-wakeword
```

`--lang` kann auch `python` oder `typescript` sein. Ein Wake-Word-Template gibt es
noch nicht. Das leere Rust-Scaffold enthält ein Tool `hello`, das damit nichts zu
tun hat, samt Test: ersetze beides. Lass `wakeword = true` die einzige Capability,
außer das Plugin bedient tatsächlich weitere Funktionen. `astra-plugin check`
findet eine Abweichung zwischen Manifest und kompiliertem Binary.

Der Daemon schickt die drei unten beschriebenen Aufrufe über `CallFromUi`, auch an
ein Plugin, das nur `wakeword` deklariert. Das ist eine Wiederverwendung des
Transports; sie setzt weder `ui_contributions` noch einen iframe noch `push_to_ui`
voraus. Die allgemeinen Hook-Tabellen führen `CallFromUi` unter UI, weil das sein
ursprünglicher Zweck ist.

In Rust implementierst du den SDK-Hook `handle_ui_call(&self, ctx: &PluginContext,
method: &str, params_json: &str) -> Result<String, ToolError>` oder nutzt
`#[ui_call]`-Methoden (mit `#[ui_call(name = "process-audio")]` und
`#[ui_call(name = "reset-audio")]` für die Namen mit Bindestrich); jede
`#[ui_call]`-Methode braucht einen `///`-Doc-Kommentar, sonst verweigert das Makro
die Kompilierung. Setze `#[astra::plugin(capabilities = "wakeword")]` auf den
impl-Block (das Scaffold oben tut das bereits): die automatische Ableitung aus
`#[ui_call]` deklariert sonst `ui_contributions`, was dem Manifest widerspricht.
Leite `status`, `reset-audio` und `process-audio` an eine einzige
Detektor-Instanz, deren Frame-Puffer zwischen den Aufrufen erhalten bleibt. Gib
JSON-Strings in den unten gezeigten Antwortformen zurück.
In Python nimmst du die `@ui_call`-Handler des SDK, in TypeScript
`ui: { contributions: [], onCall: { ... } }` mit den drei Methodennamen.
Diese Handler erzeugen keine sichtbare UI-Seite.
Einstiegspunkt, Zugriff auf die Konfiguration und Lebenszyklus beschreiben die
SDK-Seiten für [Rust](4-sdk/rust.md), [Python](4-sdk/python.md) und
[TypeScript](4-sdk/typescript.md).

Seine Einstellungen liefert das Plugin über das vorhandene JSON-Schema in
`[config]`. Astra zeigt die Felder unter Stimme nur, solange dieses Plugin
ausgewählt ist, und speichert sie über `UpdatePluginConfig`. Unterstützt werden
String-, Zahlen-, Boolean- und Enum-Eigenschaften. Ein String mit
`"format": "password"` wird zum Passwortfeld; `"format": "file"` (oder
`"x-astra-field-type": "file_picker"`) bietet eine lokale Dateiauswahl an.
`"x-astra-field-type": "slider"` und `"textarea"` wählen diese Steuerelemente für
Zahlen- bzw. String-Eigenschaften. Den konfigurierten Pfad liest das Plugin
selbst; ein Format für Keyword-Modelle schreibt Astra nicht vor.

Protokoll 1 nutzt für drei Methoden den authentifizierten
Request/Response-Kanal `CallFromUi`. Das ist ein interner Aufruf des Daemons; es
entsteht weder ein iframe noch eine Seite.

| Methode | Request-JSON | Response-JSON |
|---|---|---|
| `status` | `{}` | `{"ready": true}` oder `{"ready": false, "message": "…"}` |
| `process-audio` | `{"pcm_base64": "…"}` | `{"detected": false}` oder `{"detected": true}` |
| `reset-audio` | `{}` | `{}` |

`pcm_base64` enthält Mono-PCM mit 16 kHz, vorzeichenbehaftet, 16 Bit, Little
Endian. Astra schickt pro Aufruf 100 ms (1600 Samples). Arbeitet der Detektor mit
einer anderen Frame-Länge, muss das Plugin Samples zwischen den Aufrufen
aufbewahren. `reset-audio` verwirft dieses aufbewahrte Audio und den
Zwischenstand der Erkennung im Modell, wenn Astra das Wake-Gate zurücksetzt.
Dekodiere Base64, weise fehlerhaftes PCM und PCM ungerader Länge ab, wandle jedes
Little-Endian-Bytepaar in ein `i16` und füttere die Samples der Reihe nach in den
Detektor. Behandle nicht jeden 100-ms-Block als vollständige Äußerung. Jeder
Aufruf hat eine Frist von zwei Sekunden; die Audioschleife nutzt eine begrenzte
Warteschlange und wartet nie auf das Plugin.
`astra-plugin test` ruft alle drei Methoden auf und prüft die Form ihrer
JSON-Antworten, auch mit einem Audioblock aus lauter Nullen, während das Plugin
womöglich noch nicht konfiguriert ist. Ob das gewählte Keyword erkannt wird,
prüft dieser Test nicht. Lade vor der Auslieferung ein gültiges Modell und prüfe
`status.ready = true`; spiele mehrere aufgenommene Äußerungen der Wake-Phrase über
mehrere 100-ms-Aufrufe hinweg ab; und spiele Stille, Hintergrundgeräusche und
gewöhnliche Sprache als Negativfälle ab. Prüfe, dass `reset-audio` eine halbe
Phrase verwirft und die Erkennung danach weiter funktioniert. Installiere das
Plugin dann oder lade es per Sideload, wähle es unter **Stimme → Wake Word** aus
und bestätige, dass Astra zu hören beginnt und auf die Phrase reagiert. Ein nicht
konfiguriertes Modell sollte `ready: false` mit einer hilfreichen Meldung melden.

Astra prüft `status.ready`, bevor es zu hören beginnt. Fehlt das ausgewählte
Plugin, ist es gestoppt oder nicht bereit, verweigert Astra das Zuhören (fail
closed), statt still in Dauertranskription überzugehen. Zur Laufzeit wird über
`voice.wake_word_mode = "plugin__<id>"` ausgewählt, wobei Bindestriche in der
Plugin-ID durch Unterstriche ersetzt werden, wie bei den Provider-IDs von STT- und
TTS-Plugins.
Melde `ready: true` erst, wenn der Detektor und sein konfiguriertes Modell Audio
verarbeiten können; dass ein Dateipfad vorhanden ist, reicht nicht.
