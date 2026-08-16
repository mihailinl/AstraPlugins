> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/6-operate/performance.md) maßgeblich.

# Performance und Limits

Jede Zahl auf dieser Seite ist einmal in einer Datei deklariert und in
die Stellen generiert, die sie brauchen. Keine davon ist geraten.

## Die gemeinsamen Limits

[`spec/limits.yaml`](../../../spec/limits.yaml) ist der eine Ort, an dem
eine Zahl niedergeschrieben ist, die im Daemon und in den SDKs identisch
sein muss. `node tools/gen-limits.mjs` regeneriert die Konstanten in
allen drei SDKs, und ein `const _: () = assert!(…)` neben der Kopie des
Daemons lässt den Build fehlschlagen, bis sich der Daemon ebenfalls
bewegt. Der auslösende Bug: Der Streaming-STT-Audiokanal war im Daemon
500 und im Rust-SDK 32, und die Diskrepanz kürzte jede Äußerung
stillschweigend auf ihren ersten Bruchteil.

| Limit | Wert | Was es begrenzt |
|---|---|---|
| `plugin_start_timeout_secs` | **20** | Vom Spawn bis zur ersten Ausgabezeile des Plugins. Wird es verfehlt, erklärt der Daemon den Start für gescheitert und räumt den Prozess ab |
| `plugin_stop_grace_secs` | **5** | Von `Shutdown` bis zum Töten der Prozessgruppe. Dein eigenes Drain-Budget muss darunter liegen, sonst tötet dich der Daemon, bevor dein Aufräumpfad läuft |
| `stt_audio_channel_capacity` | **500** | Chunks, gepuffert zwischen der Voice-Pipeline des Daemons und deinem `stt`-Hook, an beiden Enden. ~10 s Audio: der Worst-Case-Wake-Word-Seed-Burst plus Live-Audio, das ankommt, während ein langsamer Provider noch inferiert |
| `max_extract_bytes` | **524 288 000** (500 MiB) | Gesamte unkomprimierte Größe, die der Daemon aus einem Archiv extrahiert |
| `max_archive_entries` | **10 000** | Einträge in einem Archiv |

Die letzten beiden sind Zip-Bomb-Abwehr, und gleichzeitig eine
Packaging-Beschränkung: Ein Bundle über einer davon macht ein Plugin
uninstallierbar, die CLI lehnt also schon zur Build-Zeit ab, statt dich
es auf der Maschine eines Nutzers entdecken zu lassen.

## `call_timeout_secs` — die eine, die du selbst setzt

`plugin.call_timeout_secs` im Manifest bestimmt, wie lange der Daemon auf
`CallTool` und `ExecuteAction` wartet, bevor er aufgibt. Unset, benutzt
er das eigene `PLUGIN_CALL_TIMEOUT` des Daemons, das absichtlich unter
„für immer" liegt.

**Ein Plugin, das einen langlaufenden Agenten vertritt, muss das
deklarieren.** Sonst wirft der Daemon dein Ergebnis weg, während dein
Subprozess weiterläuft — der Nutzer sieht einen Fehlschlag, und die
Maschine macht die Arbeit trotzdem weiter.

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

Es gilt pro Plugin, genauso wie das Timeout eines MCP-Servers pro Server
gilt. Setze es auf das, was dein langsamster legitimer Aufruf braucht,
nicht auf die größte Zahl, die dir einfällt: Das Timeout ist auch das,
was ein festhängendes Plugin davon abhält, eine Unterhaltung aufzuhängen.

## Start-Budget, nach Sprache

Die 20 s sind großzügig, und zwei der drei Sprachen schaffen es
trotzdem, sie zu verbrauchen.

| | Typischer Kaltstart | Was ihn frisst |
|---|---|---|
| Rust | Millisekunden | nichts |
| TypeScript | Node-Kaltstart | das Bundle ist eine einzige Datei, also keine Modulauflösung über einen Baum |
| Python | Interpreter + `grpcio`-Import | eine große, im Modulbereich importierte Abhängigkeit |

Der Fix ist in beiden interpretierten Fällen derselbe: **träge (lazy)
importieren, im jeweils benötigten Hook.** Ein Modell, das du in
`on_start` lädst, ist ein Modell, auf das der Nutzer wartet, bevor das
Plugin lebt; ein Modell, das du beim ersten Aufruf lädst, ist eines, auf
das er einmal wartet.

`astra-plugin test` misst die reale Zahl auf deiner Maschine und gibt sie
gegen das Budget aus:

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.5ms after Shutdown
         (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
```

## Herunterfahren innerhalb der Frist

`Shutdown` wird beantwortet, und danach beendest du dich. Fünf Sekunden
später wird die Prozessgruppe getötet. Alles, was du flushen musst — eine
Datei, eine Upstream-Session — flusht innerhalb dieses Fensters oder gar
nicht.

Ein daemonweites Herunterfahren übergibt eine **viel kürzere** Frist,
begrenzt durch die gesamte Teardown-Deadline. Behandle die 5 s nicht als
Budget, das du ausgeben kannst; behandle sie als Obergrenze, unter der du
deutlich bleiben solltest.

## Health-Checks

`HealthCheck` läuft alle 15 s. Er ist nicht über den
Optional-Hook-Helfer des Daemons geroutet, sodass **jeder** Fehler —
`UNIMPLEMENTED` eingeschlossen — das Plugin als tot markiert. Wenn du ihn
überschreibst, mach ihn billig und mach ihn vollständig: ein
Health-Check, der einen Upstream-Dienst aufruft, verwandelt dessen
Ausfall in dein als tot markiertes Plugin.

## Bundle-Größe

Nichts setzt ein Maximum über die Extraktionslimits hinaus durch, aber
zwei Dinge sind es wert, gewusst zu werden:

- Ein Rust-Bundle ist eine gestrippte Release-Binärdatei und typischerweise
  wenige Megabyte groß.
- Ein TypeScript-Bundle liefert **kein** `node_modules` aus —
  `astra-plugin build` erzeugt eine einzige in sich geschlossene
  CommonJS-Datei, und CI stellt sicher, dass nichts zur Laufzeit noch nach
  einem Modul greift.

Reproduzierbares Packen (`--reproducible`) fixiert Eintragsreihenfolge,
mtime und Kompressionsstufe, sodass zwei Builds derselben Eingaben
bytegleich sind. Der Release-Workflow führt bei jedem Release einen
Kanarienvogel aus, was den Nachbau durch Dritte aussagekräftig macht.

## Wo diese Zahlen leben

| Zahl | Deklariert in |
|---|---|
| Die fünf oben | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| `call_timeout_secs` | deiner `plugin.toml` — [Referenz](../reference/manifest.md) |
| Health-Check-Intervall, Standard-Timeout pro Aufruf | dem Daemon |
</content>
