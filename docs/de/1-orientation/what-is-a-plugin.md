> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/1-orientation/what-is-a-plugin.md) maßgeblich.

# Was ein Plugin ist

Ein Plugin ist ein **eigenständiges Programm**, das der Astra-Daemon startet
und das über gRPC auf localhost mit dem Daemon spricht. Es ist keine
Bibliothek, wird nicht in Astras Adressraum geladen und ist kein Skript, das
Astra interpretiert. Astra startet es wie eine Shell, mit Argumenten auf der
Kommandozeile, und stoppt es, indem es zunächst um ein Herunterfahren bittet
und danach, falls das nicht klappt, die Prozessgruppe abschießt.

Diese eine Tatsache bestimmt fast alles Weitere:

- **Du kannst es in allem schreiben**, was gRPC spricht. Hier gibt es drei
  SDKs — Rust, Python, TypeScript — und sie sind in
  [voller Parität](../reference/parity.md): alle 35 Hooks in allen drei.
- **Es hat deine Rechte, nicht weniger.** Siehe [das Sicherheitsmodell](security.md).
- **Es übersteht eigene Bugs schlecht und Astras Absturz gar nicht.** Ein
  Panic in einem Handler wird abgefangen und als Fehler zurückgegeben, statt
  den Prozess zu töten (`astra-plugin-sdk/src/panics.rs`); einen Absturz des
  gesamten Prozesses bemerkt der Health-Check des Daemons innerhalb von 15 s.

## Die zwei Richtungen

Alles, was ein Plugin tut, fällt in eine von zwei Kategorien, und das sind
getrennte Systeme mit getrennten Namen in `plugin.toml`.

| | Richtung | Manifest-Abschnitt | Beantwortet |
|---|---|---|---|
| **Capabilities** | Daemon → Plugin | `[capabilities]` | Was das Plugin implementiert und Astra *hineinrufen* darf |
| **Permissions** | Plugin → Daemon | `[permissions]` | Welche Host-RPCs das Plugin *hinausrufen* darf |

Früher war das ein einziges Wort für beides, und so kam `dom_access` — das
gefährlichste Ding im System — dazu, dass ein Plugin es sich durch bloße
Deklaration selbst gewähren konnte. Heute sind es zwei Wörter. Die Deklaration
`[capabilities] event_handlers = true` erlaubt kein Abonnieren von Events;
`[permissions] subscribe_events` erlaubt es, und auch nur, nachdem der Nutzer
zugestimmt hat.

`[permissions]` ist **standardmäßig verweigernd** (default-deny): ganz ohne
Abschnitt darf ein Plugin `Register`, `PluginLog`, `GetPluginSelfConfig` und
`GetDaemonInfo` aufrufen und sonst nichts
([`spec/permissions.md` §2](../spec/permissions.md)).

## Die zehn Capabilities

Jeder Schlüssel ist ein Boolean, standardmäßig `false`, und verpflichtet dich,
bestimmte Hooks zu bedienen. Die rechte Spalte nennt die *erforderlichen*;
die optionalen stehen in [der Paritätstabelle](../reference/parity.md).

| `[capabilities]`-Schlüssel | Dein Plugin wird zu | Zu bedienende Hooks |
|---|---|---|
| `tools` | einer Menge von Funktionen, die das Modell aufrufen kann | `ListTools`, `CallTool` |
| `tts` | einem Text-zu-Sprache-Anbieter in den Voice-Einstellungen | `TtsSynthesize`, `TtsListVoices` |
| `stt` | einem Sprache-zu-Text-Anbieter | `SttProcess`, `SttGetLanguages` |
| `ai_provider` | einem Modell-Backend | `AiComplete` |
| `actions` | Schritten im Befehlseditor | `ExecuteAction`, `GetPluginActionTypes` |
| `triggers` | Trigger-Typen, auf die Befehle hören können | `GetPluginTriggerTypes`, `FireTrigger` |
| `ui_contributions` | Panels, Seiten und Overlays im Astra-Fenster | `GetUiContributions` |
| `event_handlers` | einem Abonnenten von Daemon-Events | `SubscribeEvents` |
| `client` | einem eigenen Chat-Frontend | `SendChatMessage` |
| `dom_access` | Code, der im Astra-Fenster läuft | keiner — es ist eine Rendering-Entscheidung, kein Hook |

Quelle: [`reference/manifest.md`](../reference/manifest.md), generiert aus der
Crate, mit der der Daemon dein Manifest parst. `ui_panels` ist keine
Capability und war es nie — drei mitgelieferte Beispiele deklarierten es,
serde verwarf den unbekannten Schlüssel stillschweigend, und das einzige
Symptom war, dass `astra-plugin check` überhaupt keine Capabilities meldete.
`[capabilities]` weist unbekannte Schlüssel genau deshalb zurück.

## Wie ein Manifest aussieht

Das kleinste sinnvolle — ein Plugin mit Tools, keinen Permissions, sonst
nichts:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat."
author = "You"
license = "MIT"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
```

Eines, das einen Trigger auslöst, muss die Permission beantragen, und der
`reason` ist das, was der Nutzer liest, wenn Astra ihn um Zustimmung bittet:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice, and fire a trigger when one comes up."
author = "You"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

Jeder Abschnitt und jeder Schlüssel: [`reference/manifest.md`](../reference/manifest.md).

## Was ein Plugin nicht kann

- **Es kann sich nicht selbst eine Permission gewähren — sobald es installiert
  ist.** Der `[permissions]`-Block ist eine Anfrage. Bei einem aus der
  Registry installierten oder als Datei importierten Plugin wird die
  gewährte Menge vom Daemon anhand der Herkunft des Plugins aufgelöst und
  dort gespeichert, wo das Plugin sie nicht überschreiben kann — das Manifest
  liegt im eigenen Verzeichnis des Plugins, das das Plugin bearbeiten kann.
  **Ein sideload­etes Plugin ist die Ausnahme**: auf dieser Stufe *ist* das
  Manifest der Zustimmungs-Nachweis, und es gibt keine Obergrenze, sodass es
  seine eigenen Permissions durch Bearbeiten der eigenen Datei erweitern
  kann. Siehe
  [das Sicherheitsmodell](security.md#die-herkunft-eines-plugins-bestimmt-seine-obergrenze).
- **Es kann Astras `ChatService` nicht direkt erreichen.** Das Session-Token,
  das ein Plugin bei der Registrierung erhält, ist auf `PluginHostService`
  begrenzt. Einen AI-Turn auszulösen läuft über `SendChatMessage`, das an die
  Permission `send_chat_message` gebunden und als hochriskant eingestuft ist.
- **Es kann sich nicht auf einen ungerouteten Hook verlassen.** Ein Hook kann
  im Proto und in allen drei SDKs existieren und trotzdem keine Aufrufstelle
  im Daemon haben: `TtsSynthesizeStream` ist heute so ein Fall. Ihn zu
  implementieren kostet nichts; sich darauf zu verlassen, aufgerufen zu
  werden, ist erst unterstützt, wenn [die Paritätstabelle](../reference/parity.md)
  `live` sagt.
- **Es kann nicht auf einer Plattform installiert werden, für die es kein
  Bundle hat.** Siehe [Plattformen](platforms.md).

## Weiter

[Architektur](architecture.md), wenn du wissen willst, wie der Prozess
gestartet und authentifiziert wird, oder direkt zu
[Erste Schritte](../2-tutorial/getting-started.md).
</content>
