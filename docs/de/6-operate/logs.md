> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/6-operate/logs.md) maßgeblich.

# Logs

Es gibt drei Orte, an denen die Ausgabe eines Plugins landen kann, und zu
wissen, welcher welcher ist, spart eine Stunde.

| | Wohin es geht | Wer es sehen kann |
|---|---|---|
| `tracing::info!` / `logging.info(...)` (die Log-Bridge des SDK) | an den Daemon als `PluginLog` weitergeleitet, **und** nach stderr | du *und* der Nutzer, im Log-Panel von Astra |
| `ctx.host().log_info(...)` — der explizite Aufruf | an den Daemon | du und der Nutzer |
| `println!` / rohes stderr | stdout/stderr des Prozesses, das der Daemon einfängt | du, über `astra-plugin logs` |

Bevor es die Bridge gab, waren das zwei verschiedene Mengen, und die
interessanten Zeilen — ein Panic, eine fehlgeschlagene Anfrage, ein
Retry — waren fast immer in der Menge, die der Nutzer nicht sehen konnte.

## Sie lesen

<!-- doctest: cli -->
```bash
astra-plugin logs
astra-plugin logs dice-roller -f
astra-plugin logs dice-roller -n 500 --daemon-addr 127.0.0.1:32000
astra-plugin logs --json
```

Ohne ID liest es `plugin.id` aus dem Manifest in `--path`. Es funktioniert
für **installierte** Plugins, was genau der Fall ist, den
`astra-plugin dev` überhaupt nicht bedienen kann.

Der Daemon hält einen **begrenzten Ringpuffer pro Plugin**, und
`GetPluginLogs` ist unär darüber — `-f` ist also ein Poll alle 750 ms, und
„neue" Zeilen sind das Suffix dieses Tails, das die vorherige Abfrage nicht
fortsetzt. Ein Neustart setzt den Puffer zurück.

Nach mehr Zeilen zu fragen, als der Puffer hält, ist harmlos. `--json`
gibt ein Dokument aus und beendet sich, was die Snapshot-Form ist; `-f`
und `--json` sind kein sinnvolles Paar.

## Was das SDK weiterleitet, und was nicht

Die vom SDK installierte `tracing`-Schicht leitet an den Daemon weiter:

- **`INFO` und darüber**, standardmäßig. `ASTRA_PLUGIN_LOG_LEVEL` ändert
  das; `DEBUG` gehört zu `RUST_LOG` und stderr, weil das Panel für den
  Nutzer ist.
- **Nicht** den Transport-Stack — `h2`, `hyper`, `tonic`, `tower`,
  `rustls`, `tokio`. Eine Log-Zeile zu verschicken ist selbst ein RPC, und
  ein RPC, das loggt, erzeugt eine Log-Zeile: ohne diesen Ausschluss wird
  ein `WARN` von `h2` zu einer unbegrenzten Schleife.
- **Nicht mehr, als die Queue hält.** Der Kanal ist begrenzt und das
  Senden nicht-blockierend, sodass ein Plugin in einer heißen Schleife
  Zeilen fallen lässt, statt seinen eigenen Handlern gegenüber dem Daemon
  Rückstau zu erzeugen.

### Python

`install_logging_bridge()` routet das Standard-`logging`-Modul auf
dieselbe Weise. Benutze es statt `print`: das SDK konfiguriert stdout auf
**zeilenweise Pufferung** um, weil der Supervisor des Daemons stdout
liest, um zu erfahren, dass das Plugin lebt, und blockgepufferte Ausgabe
ließ den Supervisor einst gesunde Plugins beim Start-Timeout abräumen.

## Das eigene Trace der CLI hochdrehen

`RUST_LOG` steuert `astra-plugin` selbst. Es war seit 0.1 dokumentiert
und tat nichts, bis ein Subscriber installiert wurde — jedes
`tracing`-Event, das die CLI und ihre Abhängigkeiten aussandten, ging
nirgendwohin.

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

Standard ist `warn`, und es geht nach **stderr** — die nutzerseitige
Ausgabe der CLI liegt auf stdout, und eine Trace-Zeile dort würde ein
`--json`-Dokument beschädigen.

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why do I see no trace output from the CLI?
         RUST_LOG is unset, so only warnings and errors are printed.
         `RUST_LOG=astra_plugin=debug` turns on this CLI's own trace;
         `RUST_LOG=debug` turns on its dependencies' too.
```

## Dateien auf der Festplatte

| | Linux | Windows |
|---|---|---|
| Daemon-Logs | `~/.config/astra/logs/` | `%APPDATA%\astra\astra\config\logs\` |
| Von der CLI aufgelöstes Config-Verzeichnis | `astra-plugin doctor` fragen | `astra-plugin doctor` fragen |

Daemon-Logdateien sind datiert (`daemon.log.2026-08-05`). Die eigenen
Zeilen eines Plugins erscheinen dort via `PluginLog`, und sein rohes
stdout/stderr ist das, was `astra-plugin logs` aus dem
In-Memory-Puffer des Daemons liest — dieser Puffer ist keine Datei,
übersteht also keinen Daemon-Neustart.

Frag nach, statt anzunehmen, welches Verzeichnis diese Maschine benutzt:
`doctor` gibt aus, welches die CLI aufgelöst hat, und wenn Astra
widerspricht, haben beide unterschiedliche Verzeichnisse aufgelöst, was
selbst der Bug ist.

## Wenn es überhaupt keine Logs gibt

Der Prozess scheitert, bevor das SDK sein Logging installiert. Führe ihn
von Hand aus:

<!-- doctest: cli -->
```bash
astra-plugin dev --standalone
```

Das startet das Plugin direkt, statt den Daemon darum zu bitten. Es gibt
aus, was auf diesem Weg nicht geht — das Plugin kann sich nicht
registrieren, weil nur der Daemon das von `Register` verlangte Token
prägen kann.
</content>
