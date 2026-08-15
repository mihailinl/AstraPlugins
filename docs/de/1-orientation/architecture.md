> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/1-orientation/architecture.md) maßgeblich.

# Architektur

Wie ein Plugin-Prozess gestartet wird, wie er beweist, wer er ist, und
welcher der beiden gRPC-Dienste welchen Aufruf trägt.

## Das Prozessmodell

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

Der Daemon startet den Prozess mit vier Argumenten. Das ist die exakte
Kommandozeile, kopiert aus einem echten `astra-plugin test`-Lauf:

<!-- doctest: output from="astra-plugin test . --no-build, in a scaffolded plugin" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
target/release/dice_roller --daemon-addr=127.0.0.1:46495 --plugin-id=dice-roller \
  --auth-token=mock-daemon-spawn-token --capabilities=tools
```

Das SDK parst das für dich. `--auth-token` ist der interessante Teil: ein
Geheimnis, das der Daemon für genau diesen Start geprägt hat, und es wird in
**beiden** Richtungen verwendet.

## Startreihenfolge

Das SDK durchläuft eine feste Sequenz (`astra-plugin-sdk/src/runner.rs`):

<!-- doctest: illustrative reason="the startup order as prose, quoted from runner.rs" -->
```
bind → register → build ctx → on_config → on_language_changed → on_start → serve
```

- **bind vor register**, weil dem Daemon der Port während `Register`
  mitgeteilt wird und er sofort zurückrufen kann. Der Listener läuft bereits,
  sodass diese Aufrufe im Accept-Backlog warten, statt abgewiesen zu werden.
- **`on_config` vor `on_start`**, weil ein Plugin, das eine
  Hintergrundschleife startet, zuerst seine Einstellungen braucht.
- **`on_start` vor `serve`**, und ein `Err` daraus bricht den Start ab: ein
  Plugin, das seine Aufgabe nicht erfüllen kann, darf nicht eines sein, das
  der Daemon für gesund hält.

Zwei Zahlen setzen hierfür Grenzen, beide einmal in
[`spec/limits.yaml`](../../../spec/limits.yaml) deklariert und in jedes SDK
generiert:

| Limit | Wert | Was passiert, wenn du es verfehlst |
|---|---|---|
| `plugin_start_timeout_secs` | 20 | Der Daemon erklärt den Start für gescheitert und räumt den Prozess ab |
| `plugin_stop_grace_secs` | 5 | Nach `Shutdown` wird die Prozessgruppe getötet |

## Der Handshake

1. Der Daemon startet den Prozess mit `--auth-token=<Spawn-Token>`.
2. Das Plugin bindet einen gRPC-Server an einen vom Betriebssystem
   zugewiesenen Loopback-Port.
3. Das Plugin ruft `PluginHostService.Register` auf und legt dabei das
   Spawn-Token, seinen Port, seine Protokollversion und seine
   Capability-Liste vor.
4. Der Daemon antwortet mit einem **Session-Token**.
5. Jeder spätere Aufruf vom Plugin zum Daemon trägt dieses Session-Token im
   Metadaten-Header `x-session-token`. `Register` ist der einzige davon
   ausgenommene Pfad (`astra-plugin-sdk/src/auth.rs`); alles andere ohne
   dieses Token kommt als `unauthenticated` zurück.

Registrierung, in einem echten Lauf gegen den Mock-Daemon, den
`astra-plugin test` startet:

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
INFO astra_plugin_sdk::runner: Starting plugin 'dice-roller', connecting to daemon at 127.0.0.1:46495
INFO astra_plugin_sdk::runner: Plugin gRPC server listening on port 41627
INFO astra_plugin_sdk::runner: Registering with capabilities: ["tools"]
INFO astra_plugin_sdk::runner: Registered successfully. Daemon version: mock, protocol: 1 (accepts 0+)
```

### Die andere Richtung

Die Richtung Daemon → Plugin verwendet das *gleiche* Spawn-Token, das bei
jedem Aufruf im Header `x-plugin-token` an das Plugin zurückgeschickt wird.
Dein Capability-Server prüft es, und das SDK erledigt das für dich.

**Das konfigurierst du nicht.** Der Daemon setzt
`ASTRA_PLUGIN_CAPABILITY_AUTH=require` in der Umgebung deines Plugins, was
dem SDK sagt, jeden Capability-Aufruf abzulehnen, der das Token nicht trägt.
Das ist der Daemon, der seine eigene Hälfte ankündigt, statt dass irgendwer
Versionsnummern abgleicht: ein Daemon, der zu alt ist, um den Header zu
senden, setzt keine Variable, und das SDK bleibt bei `CapabilityAuth::Warn`
— ein **falsches** Token wird abgelehnt, ein **fehlendes** wird mit einer
Warnung akzeptiert — sodass dein Plugin dort weiter funktioniert.

Das ist wichtig, weil Loopback keine Grenze ist. Dein Capability-Server
lauscht auf `127.0.0.1` mit einem vom Betriebssystem zugewiesenen Port, und
jeder Prozess, der als dein Nutzer läuft, kann ihn finden. Ohne den Header
genügte es, ihn zu finden, um `CallTool`, `OnConfigChanged` — deine
API-Basis-URL auf den Host von jemand anderem umzubiegen, wonach dein Plugin
dort seine echten Zugangsdaten postet — oder `Shutdown` aufzurufen.

`astra-plugin test` setzt dieselbe Variable und legt dasselbe Token vor,
sodass das, was du lokal testest, dem entspricht, was auf der Maschine eines
Nutzers läuft.

## Die zwei Dienste

| | `PluginCapabilityService` | `PluginHostService` |
|---|---|---|
| Bereitgestellt von | deinem Plugin | dem Daemon |
| Aufgerufen von | dem Daemon | deinem Plugin |
| Geregelt durch | `[capabilities]` | `[permissions]` |
| Hooks | 25 | 10 |

`PluginService` — der dritte Dienst im Proto — wird vom Daemon für die
Astra-UI bereitgestellt. Kein Plugin ruft ihn je auf; `astra-plugin dev` und
`astra-plugin logs` tun es, als lokaler Client.

Jeder Hook, mit seiner Capability, seiner Permission, ob er erforderlich ist,
und der Codezeile im Daemon, die ihn aufruft:
[die Paritätstabelle](../reference/parity.md).

## Health, Shutdown und Neustarts

- `HealthCheck` läuft alle 15 s und wird **nicht** als optional behandelt:
  jeder Fehler davon, `UNIMPLEMENTED` eingeschlossen, markiert das Plugin als
  tot.
- `Shutdown` wird beantwortet, und danach beendest du dich. Die Frist beträgt
  5 s.
- Ein Panic in einem Handler wird abgefangen und als Fehler zurückgegeben,
  statt durch den gRPC-Server hindurch abzuwickeln
  (`astra-plugin-sdk/src/panics.rs`). Ein Panic bleibt ein Bug; er ist nur
  kein Ausfall.

## Config

Die Einstellungen eines Plugins sind JSON, vom Daemon gespeichert, in der
Astra-Settings-UI bearbeitet auf Basis des JSON Schema in deinem
`[config]`-Abschnitt. Der Daemon liefert sie mit `OnConfigChanged` aus, und
das Plugin kann auch mit `GetPluginSelfConfig` danach fragen — einer der
vier Aufrufe, der keine Permission braucht.

Die erste Nutzlast einer frischen Installation ist `{}`, weshalb die
Konfigurationstypen des SDK jedes Feld mit einem Default versehen. Siehe
[Config-Felder](../3-reference/config-fields.md).

Die Einstellungsdatei liegt unter
`<astra config dir>/plugins/<id>/config.json`
([Plattformen](platforms.md) nennt das Verzeichnis je Betriebssystem). Sie
**übersteht ein Update** — ein Update ist Stopp, Installation, Start, und die
Installation rief früher `remove_dir_all` auf das Verzeichnis, in dem die
Einstellungen des Nutzers lagen; der Daemon bewahrt die Datei jetzt und
sichert das per Test ab (`config_survives_update`,
`astra-daemon/src/plugins/manager.rs`), und eine Kopie im neuen Archiv kann
sie nicht überschreiben. Sie übersteht eine Deinstallation **nicht**:
`uninstall_plugin` endet mit `remove_dir_all`. Alles, was eine
Deinstallation überdauern muss, gehört irgendwohin, das dir gehört.

## Wo die Teile liegen

| Sache | Pfad |
|---|---|
| `plugin.toml`-Schema | `astra-plugin-cli/vendor/astra-plugin-manifest/` — eine bytegleiche Kopie der Crate, die der Daemon verwendet |
| Die Leitung (wire) | [`proto/plugin.proto`](../../../proto/plugin.proto), ein generierter Ausschnitt von Astras `astra.proto` |
| Hook-Tabelle | [`spec/hooks.yaml`](../../../spec/hooks.yaml) |
| Gemeinsame Zahlen | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| Bundle-Format | [`spec/bundle-v2.md`](../spec/bundle-v2.md) |
</content>
