> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/5-publish/sideload.md) maßgeblich.

# Sideloading — ein Entwicklerwerkzeug

> **So wird ein Plugin nicht installiert.** Sideloading zeigt Astra auf
> ein Quellverzeichnis auf deiner Festplatte und führt es unsigniert als
> nativen Prozess mit den vollen Rechten deines Benutzerkontos aus. Es
> existiert, damit du ein Plugin entwickeln kannst. Es steckt hinter einem
> expliziten Opt-in, und dieses Opt-in senkt die Hürde für **jedes**
> Plugin auf der Maschine, nicht nur für deines.
>
> Nutzer installieren aus Astra heraus. Autoren veröffentlichen mit
> [`init-ci` und einem Tag](release-with-ci.md) und werden dann
> [einmal gelistet](get-listed.md) —
> [der ganze Weg ist eine Seite](../publishing.md).
>
> Jemandem zu sagen, er solle dein Repository klonen und sideloaden, ist
> kein Veröffentlichen. Es bittet ihn, unsignierten Code als er selbst
> auszuführen, und erreicht genau die Leute, mit denen du reden kannst.

Sideloade nie ein Plugin, das du nicht selbst geschrieben oder geprüft
hast. Wenn dir jemand ein Verzeichnis und die Anweisung schickt, den
Entwicklermodus einzuschalten, bittet er dich, seinen Code als du selbst
auszuführen.

## Es einschalten

Sideloading wird verweigert, es sei denn,
`safety.allow_unsigned_plugins` ist wahr. Der Daemon sagt das genau so:

<!-- doctest: illustrative reason="the daemon's refusal, quoted from astra-daemon/src/plugins/manager.rs; reproducing it needs a running Astra with the setting off" -->
```
Sideloading is disabled. It runs an unsigned local plugin as native code with
your full privileges. Turn on Settings -> Privacy -> "Allow unsigned plugins"
(`safety.allow_unsigned_plugins`) to sideload (local plugin development only).
```

und die CLI macht daraus dieselbe Anweisung mit dem Fix auf einer eigenen
Zeile (`astra-plugin-cli/src/daemon.rs`). Die beiden Nachrichten nennen
unterschiedliche Abschnitte der Settings — der Daemon sagt Privacy, die
CLI sagt Safety. Der **Settings-Schlüssel ist
`safety.allow_unsigned_plugins`**, und danach ist zu suchen.

## Es benutzen

Ein Befehl, von [der CLI](../install-cli.md) aus:

<!-- doctest: cli -->
```bash
astra-plugin dev
astra-plugin dev . --daemon-addr 127.0.0.1:32000
```

`dev` tut vier Dinge in Reihenfolge und stoppt beim ersten Fehlschlag:

1. `astra-plugin check --strict` — es übergibt dem Daemon kein Manifest,
   das bereits fehlerhaft ist;
2. baut;
3. übergibt das **Verzeichnis** dem Daemon über `SideloadPlugin`, der den
   Prozess startet, sein Auth-Token prägt und von da an seinen
   Lebenszyklus besitzt;
4. beobachtet auf Änderungen, baut neu, stoppt/startet das Plugin und
   verfolgt seine Ausgabe.

<!-- doctest: output from="astra-plugin dev . with no Astra running" unrun="needs a machine with no Astra daemon listening, which a CI runner cannot promise either way" -->
```
Dev mode: plugin 'dice-roller'
  Directory: /tmp/dice-roller
Checking plugin at /tmp/dice-roller...
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 2.48s
Error: Could not read /home/you/.config/astra/daemon.token. Astra does not look
like it is running — start the app first.
```

**Der Daemon besitzt den Prozess, und das ist keine Stilfrage.** Ein
Plugin authentifiziert sich bei `PluginHostService` mit einem Token, das
der Daemon beim Starten des Prozesses prägt, und der Daemon lehnt jedes
`Register` ab, das kein von ihm ausgestelltes Token trägt. Ein von der CLI
gespawntes Plugin hat keine Möglichkeit, eines zu bekommen — die
selbst-spawnende Dev-Schleife, die dies ersetzte, startete einen Prozess,
der mit niemandem sprach.

`--standalone` behält dieses ältere Verhalten für die Fälle, in denen es
weiterhin nützlich ist (prüfen, dass eine Binärdatei startet, sie von Hand
treiben), und sagt vorab, dass sich das Plugin so nicht bei Astra
registrieren kann.

`dev --json` wird absichtlich abgelehnt: `--json` verspricht ein Dokument
pro Lauf, und `dev` endet nie. `astra-plugin check --json`,
`astra-plugin test --json` und `astra-plugin logs --json` sind die
maschinenlesbaren Hälften dessen, was es tut.

## Was Sideloading genau kostet

| | |
|---|---|
| **Signatur** | keine. Nichts bürgt für den Code |
| **Rechte** | dein volles Benutzerkonto. Es gibt keine Sandbox — [Phase 7 existiert nicht](../1-orientation/security.md) |
| **Auswirkungsradius des Schalters** | `allow_unsigned_plugins` gilt für jedes Plugin auf der Maschine, einschließlich unsignierter Dateien, die du später importierst |
| **Auto-Start** | **nie.** Der Entwicklermodus ist zur Ladezeit erforderlich, und ein Neustart lässt ein sideload­etes Plugin gestoppt, bis du es erneut startest |
| **Permission-Obergrenze** | **keine** — siehe unten |
| **Dem Nutzer angezeigte Provenienz** | Stufe `sideloaded` — „aus einem Ordner geladen" — im Provenance-Panel |

### Warum es hier keine Permission-Obergrenze gibt

Eine [lokal importierte `.astraplugin`](local-install.md) hat vier
Permissions pauschal verweigert. Ein sideload­etes **Quellverzeichnis**
nicht, und die Ausnahme ist Absicht, kein Versehen: Das ist die
Entwicklungsschleife für UI-Plugins, und `dom_access` ist genau das, was
`companion`, `doom` und `bad-apple` brauchen. Stufe 3 zu deckeln würde
diese unentwickelbar machen.

Der Tausch ist, dass Stufe 3 hinter einer expliziten Einstellung gesperrt
ist, nie automatisch startet, und ein Verzeichnis ist, auf das du selbst
gezeigt hast — drei Tatsachen, die Stufe 2 (eine Datei, die irgendwoher
ankam) nicht für sich beanspruchen kann.

Der Plan verlangt außerdem ein dauerhaftes, nicht wegklickbares
„DEVELOPER — unverified code from a local directory"-Abzeichen auf der
Plugin-Karte und im Fensterrahmen, immer wenn `dom_access` aktiv ist.
**Dieses Abzeichen gibt es heute nicht in der UI**, und diese Seite
behauptet das auch nicht.

## Was nicht funktioniert, und nicht funktionieren wird

**Von Hand einen `sideload.json`-Marker ins Plugins-Verzeichnis zu
schreiben.** Der Daemon lehnt einen Marker ab, für den er keine
autorisierende Aufzeichnung hat:

<!-- doctest: illustrative reason="a daemon log line, quoted from astra-daemon/src/plugins/manager.rs; it is emitted on a machine with a planted marker" -->
```
Refusing sideload marker in <path>: this daemon never authorised a sideload of
'<id>' from <source> (no matching record in <registry path>). A marker file
alone does not authorise running unsigned native code.
```

Ältere Anleitungen sagten Autoren, einen Marker in
`~/.config/astra/astra/plugins` abzulegen — ein Pfad, den es nicht gibt,
obendrauf ein Mechanismus, der nicht mehr funktioniert, ohne die
Voraussetzung `allow_unsigned_plugins` zu erwähnen. Sie wurden gelöscht
statt korrigiert. Der Ersatz ist eine Zeile: `astra-plugin dev`.

## Wenn du mit der Entwicklung fertig bist

Nichts an diesem Weg erzeugt etwas, das eine andere Person installieren
kann. Zum Ausliefern:

1. [`astra-plugin init-ci`](release-with-ci.md), dann ein Tag — CI baut es
   und bezeugt es;
2. [`astra-plugin publish`](get-listed.md) — einmal, für immer;
3. Nutzer installieren es aus Astra heraus, mit gepinntem Digest.

`allow_unsigned_plugins` wieder auszuschalten, wenn du nicht entwickelst,
sind die zwei Klicks wert.
</content>
