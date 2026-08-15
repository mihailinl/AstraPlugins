> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/7-examples/README.md) maßgeblich.

# Beispiele

Elf Plugins in [`examples/`](../../../examples/), alle auf die aktuellen
SDKs portiert und alle in CI gebaut. Lies eines, das tut, was du willst,
und starte dann vom Scaffold statt vom Beispiel — Beispiele tragen kein
Scaffolding, das du löschen müsstest.

Jeder Eintrag unten wird aus der eigenen `plugin.toml` dieses Plugins
gelesen.

## Die zuerst zu lesenden

| | Sprache | Capabilities | Permissions | Warum dieses |
|---|---|---|---|---|
| [`dice-roller`](../../../examples/dice-roller/) | Rust | `tools`, `actions`, `triggers` | `fire_trigger` | Das Referenz-Plugin. Drei Capabilities, eine Permission, und eine Testsuite, die zeigt, wie jede getestet wird |
| [`json-tools`](../../../examples/json-tools/) | TypeScript | `tools`, `actions`, `triggers` | `set_variable` | Dieselbe Form in TypeScript, und das Beispiel, dessen Tests bis zur Wire-Ebene reichen |
| [`text-utils`](../../../examples/text-utils/) | Python | `tools`, `actions`, `triggers` | `fire_trigger` | Dieselbe Form in Python |

Diese drei sind absichtlich dasselbe Plugin auf drei Arten. Wenn du eine
Sprache auswählst, lies alle drei und wähle das Ökosystem, aus dem du
Bibliotheken ziehen willst — jede Capability ist in jedem SDK verfügbar.

## Voice-Provider

| | Sprache | Capabilities | Warum dieses |
|---|---|---|---|
| [`tone-tts`](../../../examples/tone-tts/) | Rust | `tts` | Ein Text-zu-Sprache-Provider, der in Piepsern spricht. Ein Verdrahtungstest, keine Stimme |
| [`mock-stt`](../../../examples/mock-stt/) | Rust | `stt` | Gibt ein deterministisches Transkript zurück, das das erhaltene Audio beschreibt. Der bidirektionale Stream, minus einen Erkenner |
| [`echo-stt`](../../../examples/echo-stt/) | Rust | `stt` | Transkribiert nichts und spielt dein Mikrofon durch den Plugin-Prozess zurück. Um zu hören, was der Daemon dir tatsächlich sendet |

`tone-tts` und `mock-stt` sind zwei der vier Plugins, die der
Conformance-Job bei jedem CI-Lauf treibt, genau weil sie Hooks
ausüben, die sonst nichts tut.

## UI, und `dom_access`

Diese führen Code im Astra-Fenster aus. Sie sind der Grund, warum
[Sideloading keine Permission-Obergrenze hat](../5-publish/sideload.md):
`dom_access` kann auf keinem anderen Weg entwickelt werden.

| | Sprache | Capabilities | Warum dieses |
|---|---|---|---|
| [`companion`](../../../examples/companion/) | Rust | `ui_contributions`, `dom_access` | Eine Katze, die durchs Fenster fliegt und Dinge sagt. Die kleinste vollständige UI-Contribution |
| [`bad-apple`](../../../examples/bad-apple/) | Rust | `ui_contributions`, `dom_access` | Die *Bad Apple!!*-Animation in vier Render-Modi. Liefert eigene Frame-Daten mit; siehe die `SETUP.md` |
| [`doom`](../../../examples/doom/) | Rust | `ui_contributions`, `dom_access` | Eine Doom-Seite, die eine WebAssembly-Engine ausführt. Das Extremste, was eine UI-Contribution sein kann |

`companion` ist das vierte Plugin, das der Conformance-Job für
`ui_contributions` treibt.

## Clients

Ein `client`-Plugin ist ein eigenes Chat-Frontend — eigene Session, eigene
Surface. Es ist eine hochriskante Capability, und wird einer
[lokal importierten Datei](../5-publish/local-install.md) pauschal
verweigert.

> **Beide sind der Daemon-Seite voraus.** Die Daemon-seitige Hälfte des
> Client-Pfads ist nicht gebaut: jedes Plugin ist als
> `ClientType::PluginClient` registriert, und der Auth-Interceptor lehnt
> diese Identität auf jedem gRPC-Pfad außerhalb von
> `/astra.PluginHostService/` ab. Der `DaemonClient`, gegen den diese
> beiden geschrieben sind, antwortet also bei jedem Aufruf mit
> `permission_denied`. Lies sie für die Form eines Client-Plugins — die
> Surface, den Event-Fluss, das I18n — nicht als etwas, das du heute
> Ende-zu-Ende ausführen kannst. Siehe
> [den `Daemon`-Abschnitt des Rust-SDK](../4-sdk/rust.md#daemon--im-sdk-vorhanden-vom-daemon-abgelehnt).

| | Sprache | Capabilities | Warum dieses |
|---|---|---|---|
| [`telegram-client`](../../../examples/telegram-client/) | Rust | `client` | Jede Astra-Unterhaltung wird zu einem Telegram-Thema, mit gestreamten Antworten |
| [`web-chat`](../../../examples/web-chat/) | Rust | `client` | Ein Browserfenster, das mit Astra spricht. Um beim Multi-Client-Sync zuzusehen |

## Plattformen

Keines der elf deklariert einen `[platform]`-Block, was bedeutet, dass der
Daemon jedes für überall kompatibel hält — richtig für die zwei
interpretierten, und etwas, das ein *veröffentlichtes* natives Plugin
verschärfen sollte. Siehe [Plattformen](../1-orientation/platforms.md).

| Sprache | Was ein Release baut |
|---|---|
| Rust (neun davon) | `linux-x64` **und** `windows-x64`, je ein Bundle |
| TypeScript (`json-tools`) | ein `noarch`-Bundle |
| Python (`text-utils`) | ein `noarch`-Bundle |

`doom` und `bad-apple` liefern zusätzlich Daten aus — eine
WebAssembly-Engine, einige Megabyte an Frames — und ihre `SETUP.md` sagt,
woher sie kommen und wie man sie regeneriert.

## Womit sie getestet werden

| Ebene | Was läuft | Welche Beispiele |
|---|---|---|
| Unit | der In-Process-Harness des SDK, in den eigenen Tests jedes Beispiels | `dice-roller`, `mock-stt`, `text-utils`, `json-tools` |
| Build | jedes Beispiel wird bei jedem CI-Lauf gebaut | alle elf |
| Conformance | `astra-plugin test` startet den echten Prozess gegen einen Mock-Daemon und treibt jeden Hook, den seine Capabilities implizieren | `dice-roller`, `mock-stt`, `tone-tts`, `companion` |

Die Conformance-Menge ist für Abdeckung der Hook-Tabelle gewählt, nicht
für Vielfalt — Tools/Actions/Triggers, den STT-bidirektionalen Stream,
TTS, und UI-Contributions. **`ai_provider` hat kein Beispiel und ist
daher nicht abgedeckt**, was laut auszusprechen sich lohnt: eine
Abdeckungslücke, die niemand benennt, wird zu einer, von der jeder
annimmt, sie sei geschlossen.

Python- und TypeScript-Beispiele sind noch nicht im Conformance-Job,
weil ihre SDKs nicht veröffentlicht sind und ein Conformance-Lauf, der
ein SDK halb installiert, über die Installation berichtet statt über das
Plugin. `astra-plugin test` treibt einen Prozess und kümmert sich nicht
darum, in welcher Sprache er geschrieben wurde, sie treten dem Job also
an dem Tag bei, an dem die SDKs veröffentlicht werden.

## Eines ausführen

<!-- doctest: cli -->
```bash
cd examples/dice-roller
astra-plugin check --strict
astra-plugin test
astra-plugin dev
```

`dev` braucht ein laufendes Astra und den Entwicklermodus — lies zuerst
[was das kostet](../5-publish/sideload.md).
</content>
