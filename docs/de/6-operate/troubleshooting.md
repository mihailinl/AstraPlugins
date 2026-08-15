> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/6-operate/troubleshooting.md) maßgeblich.

# Fehlerbehebung

Nach den Strings sortiert, die die CLI und der Daemon tatsächlich
ausgeben. Wenn du einen Fehler vor dir hast, durchsuche diese Seite nach
einem Fragment davon.

## Hier anfangen

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

Fünfzehn Prüfungen, jede formuliert als die Frage, die sie beantwortet.
Es weiß, welche CLI du benutzt, welches Config-Verzeichnis sie aufgelöst
hat, ob der Daemon erreichbar ist, welche Toolchains du hast, ob dein
Manifest parst, ob der Einstiegspunkt existiert, ob deine Permissions
deine Capabilities abdecken, ob dein `[platform]`-Block stimmt, und ob
dein Release-Workflow gepinnt ist. Jeder Fehlschlag trägt eine
`fix:`-Zeile. In einem Projekt, das du noch nicht gebaut hast, endet es
bei einer dieser Prüfungen mit einem Nicht-Null-Exit — „Will the daemon
find something to start? … does not exist" — was korrekt ist: es hat
noch niemand die Binärdatei erzeugt.

## Das Projekt löst sein SDK nicht auf

**`error: failed to select a version for the requirement astra-plugin-sdk = "^0.6"`**
**`ERROR: No matching distribution found for astra-plugin-sdk<0.6,>=0.5`**
**`error: No version matching "^0.5.0" found for specifier "astra-plugin-sdk" (but package exists)`**

Drei Sprachen, eine Fehlerform — und das Fehlen des SDK ist nicht mehr ihre
Ursache. `astra-plugin new` pinnt `astra-plugin-sdk` `0.6` für Rust,
`>=0.5,<0.6` für Python und `^0.5.0` für TypeScript, und die öffentlichen
Registries tragen crates.io **0.6.0**, PyPI **0.5.0** und npm **0.5.0**. Jedes
dieser Pinnings löst sich in einem frischen Projekt ohne jede Konfiguration
auf; wenn es bei dir nicht so ist, liegt die Ursache zwischen deiner Maschine
und der Registry:

- **Ein veralteter Index, eine Lockfile oder ein Mirror, der nicht
  synchronisiert hat.** Der Resolver antwortet aus einer zwischengespeicherten
  Sicht der Registry, die älter ist als das Release, oder aus einem
  Firmen-Proxy, der genau das tut. `cargo update -p astra-plugin-sdk`;
  `pip install --upgrade --no-cache-dir -r requirements.txt`; für npm
  `node_modules` und die Lockfile löschen und neu installieren.
  `cargo --offline` und `npm --offline` erzeugen diesen Fehler per Definition.
- **Jemand hat eine Untergrenze gelockert.** Ein auf `0.5` (Rust) oder `0.4`
  (Python, TypeScript) heruntergesetztes Pinning verlangt etwas, das unter
  dieser Bedingung keine Registry anbietet. Setze das Pinning des Scaffolds
  zurück, statt es weiter aufzuweichen: 0.6 ist das erste Rust-Release, dessen
  `HostClient` `x-session-token` anhängt, ein älteres SDK tauscht diesen Fehler
  also gegen `unauthenticated` bei jedem Host-Aufruf ein — siehe Abschnitt
  unten.

Weder `doctor` noch `check` erwähnt irgendetwas davon, weil beide
`plugin.toml` lesen und das Pinning in der Build-Datei der jeweiligen Sprache
liegt.

## Das Plugin startet nicht

**`Could not read /…/astra/daemon.token. Astra does not look like it is running — start the app first.`**
Genau das, was da steht. `dev`, `logs` und die Installation brauchen ein
laufendes Astra; `new`, `build`, `check`, `test`, `sign` und `publish`
nicht. Wenn Astra *läuft*, hat es ein anderes Config-Verzeichnis
aufgelöst als die CLI — vergleiche den Pfad, den `doctor` ausgibt, mit
dem, den Astra in seinen Settings zeigt.

**Der Daemon hat den Prozess beim Start abgeräumt.** Das Budget beträgt
`plugin_start_timeout_secs` = **20 s** bis zur ersten Ausgabezeile. Ein
Python-Plugin, das im Modulbereich einen großen ML-Stack importiert, kann
das verpassen; importiere träge (lazy), im jeweils benötigten Hook.
`astra-plugin test` misst das und gibt die Zahl aus:

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
```

**Das Plugin startet und stirbt sofort wieder.** Prüfe zuerst
`astra-plugin logs -f`; wenn dort überhaupt nichts steht, scheitert der
Prozess, bevor das SDK sein Logging installiert. Führe die Binärdatei von
Hand aus — `astra-plugin dev --standalone` tut das und sagt dir, was auf
diesem Weg nicht geht.

**`HealthCheck`-Fehler markieren das Plugin als tot.** Er läuft alle
15 s und ist nicht über den Optional-Hook-Helfer des Daemons geroutet:
*jeder* Fehler, `UNIMPLEMENTED` eingeschlossen, bedeutet tot. Wenn du
`health_check` überschrieben hast, stell sicher, dass es nicht werfen
kann.

## Ein Host-Aufruf kommt als `permission_denied` zurück

Die Nachricht nennt die Permission und die Herkunft der gewährten Menge.
Drei Ursachen, nach Wahrscheinlichkeit geordnet:

1. **Du hast sie nicht deklariert.** `[permissions]` ist default-deny.
   `[capabilities] event_handlers = true` zu deklarieren erkauft nicht
   `SubscribeEvents`; `[permissions] subscribe_events` schon.
2. **Der Nutzer hat sie nicht gewährt**, oder der Installationsweg hat
   sie gekappt. Eine [lokal importierte Datei](../5-publish/local-install.md)
   hat `send_chat_message`, `set_theme_contribution`, `dom_access` und
   `client` pauschal verweigert.
3. **Du bist abgemeldet oder die App ist gesperrt.** Astra lehnt
   Plugin-RPCs in beiden Zuständen ab, und die CLI sagt das:
   *"Astra refuses plugin RPCs while signed out or locked — sign in and
   unlock the app, then try again."*

`astra-plugin doctor` beantwortet 1, ohne irgendetwas auszuführen:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## Ein Host-Aufruf kommt als `unauthenticated` zurück

Jeder `PluginHostService`-Aufruf außer `Register` muss das Session-Token
in `x-session-token` tragen. Alle drei SDKs hängen es an — **ab 0.6 in
Rust, 0.5 in Python und TypeScript**. Gegen ein älteres SDK scheitert
jeder Host-Aufruf auf diese Weise, weshalb die Abhängigkeits-Untergrenze
des Scaffolds nicht niedriger geht.

`astra-plugin test` sichert das Ende-zu-Ende ab:

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`
```

## Sideloading wird abgelehnt

**`Sideloading is disabled.`** `safety.allow_unsigned_plugins` ist aus.
Lies [was das Einschalten kostet](../5-publish/sideload.md), bevor du es
tust.

**`Refusing sideload marker in …: this daemon never authorised a sideload of …`**
Jemand hat von Hand einen `sideload.json`-Marker platziert. Das hat
nicht mehr funktioniert, seit der Daemon eine eigene Aufzeichnung dessen
führt, was er autorisiert hat. Benutze `astra-plugin dev`.

## Eine Installation wird abgelehnt

Jeder Verifikationsfehler auf dem Registry-Weg ist eine **harte Blockade
ohne Override**, und jeder benennt, welches von zwei Dingen passiert ist.

| Was du siehst | Was es bedeutet |
|---|---|
| Die heruntergeladene Datei stimmt nicht mit dem überein, was die Registry signiert hat | `DIGEST_MISMATCH` — der Download wurde verworfen. Melde es |
| Astra konnte die Signatur des Plugin-Katalogs nicht verifizieren | `SIGNATURE_INVALID` — der Store wird deaktiviert, statt auf unverifizierte Daten zurückzufallen |
| Dieses Update stammt aus einem anderen Repository als dem, aus dem du installiert hast | `IDENTITY_CHANGED` — nie ein Override. Nur eine Deinstallation löscht das Pinning |
| Das Plugin wurde zurückgezogen | `REVOKED` — mit dem Advisory und Ein-Klick-Deinstallation. Dateien werden nie still gelöscht |
| Dieses Bundle ist für eine andere Plattform | `PLATFORM_UNSUPPORTED` |
| Dieses Plugin braucht ein neueres Astra | `PROTOCOL_UNSUPPORTED` |
| Netzwerk, oder deine Uhr geht falsch | Wiederholbar, und entsprechend formuliert. Das darf nie wie ein Verifikationsfehler aussehen |

**`nothing here vouches for these bytes`** bei einer lokalen Datei:
installiere sie stattdessen von der Plugins-Seite, oder lies
[lokale Installation](../5-publish/local-install.md) dafür, was der
Import kostet.

Heute ist die Vertrauenskette **einen Link zu kurz** verankert: die
Root-Schlüssel existieren und die root-signierte `trust.json`, die einen
Index-Signierschlüssel delegiert, existiert jetzt auch, aber
`registry/v1/index.json` und `revocations.json` tragen weiterhin
`"signatures": []`. Ohne Signatur auf dem Katalog gibt es nichts, das der
delegierte Schlüssel prüfen könnte, ein Katalog wird also als unsigniert
eingestuft, und Widerruf wird nicht durchgesetzt. Siehe
[`spec/registry-index.md` §0.1](../spec/registry-index.md).

## Ein Tool-Aufruf scheitert auf eine Weise, die das Modell nicht beheben kann

Benutze den richtigen Code; das ist es, was das Modell liest.

| Code | Sag das, wenn |
|---|---|
| `BAD_ARGUMENTS` | Ein erneuter Versuch mit anderen Argumenten könnte funktionieren |
| `NOT_CONFIGURED` | Eine Einstellung fehlt — **und setze `config_field`**, was den Fehler in einen Link zu genau diesem Eingabefeld verwandelt |
| `UNAUTHORIZED` | Ein Wert ist vorhanden und wurde abgelehnt. Anders als `NOT_CONFIGURED` |
| `RATE_LIMITED` | Mit `retry_after_ms`, wenn der Upstream einen genannt hat |
| `UNAVAILABLE` / `TIMEOUT` | Vorübergehend. Ein späterer identischer Aufruf könnte funktionieren |
| `INTERNAL` | Ein Bug. Nichts, worauf das Modell reagieren kann |

`UNIMPLEMENTED` ist **kein** Fehler: es bedeutet „dieser Hook fehlt", und
der Daemon liest es so. Ihn zurückzugeben, weil dein TTS abgestürzt ist,
lässt den Daemon glauben, du hättest kein TTS. Vollständige Taxonomie:
[`reference/errors.md`](../reference/errors.md).

## `astra-plugin check` beschwert sich

**`config.schema is not valid JSON`** oder **`should have "type": "object" at
root`** — das Settings-Formular wird aus diesem Schema generiert.

**Ein unbekannter Schlüssel in `[capabilities]` lässt das ganze Manifest
scheitern.** Dieser Abschnitt ist der einzige Ort, an dem unbekannte
Schlüssel abgelehnt werden, weil jeder Schlüssel ein Opt-in-Boolean ist
und ein Tippfehler sonst genau wie `false` gelesen würde. `ui_panels` ist
der Klassiker: es heißt `ui_contributions`, und drei mitgelieferte
Beispiele deklarierten deswegen monatelang gar nichts.

**Eine unbekannte `[permissions]`-ID wird behalten und mit einer Warnung
versehen**, nicht abgelehnt — neue IDs erscheinen mit neuen
Astra-Versionen, und der Permissions-Block wird von drei Implementierungen
byteweise gehasht, das Fallenlassen eines Schlüssels würde sie also
uneins darüber machen, was signiert wurde.

`astra-plugin check --fix` wendet an, was es beweisen kann, und meldet
den Rest.

## Die CLI gibt nichts Nützliches aus

`RUST_LOG` funktioniert jetzt — es war seit 0.1 dokumentiert und
wirkungslos, bis ein Subscriber installiert wurde:

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

Trace geht nach **stderr**, sodass `--json` auf stdout ein sauberes
Einzeldokument bleibt.

## Exit-Codes

| | |
|---|---|
| `0` | Erfolg |
| `1` | das Plugin oder das Bundle ist fehlerhaft |
| `2` | die CLI konnte die Prüfung nicht ausführen — eine fehlende Datei, eine fehlende Toolchain |

Die Trennung ist tragend: ein Release-Workflow, der „das Bundle ist
schlecht" und „ich konnte nicht nachsehen" gleich behandelt, liefert
eines von beiden aus.

## Immer noch festgefahren

- [Logs](logs.md) — wo sie liegen, je Betriebssystem
- [Performance](performance.md) — Timeouts und die Zahlen dahinter
- [Beispiele](../7-examples/README.md) — elf funktionierende Plugins, von denen mehrere genau den Pfad durchlaufen, den du gerade debuggst
</content>
