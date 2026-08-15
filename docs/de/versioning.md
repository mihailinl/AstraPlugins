> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/versioning.md) maßgeblich.

# Versionierungs- und Deprecation-Richtlinie

Was die Zahlen bedeuten, wie lange etwas, von dem du abhängst,
garantiert weiter funktioniert, und wo diese Garantie als Daten
niedergeschrieben ist statt als Versprechen, das sich jemand merken
muss.

## Vier Zahlen, und nur eine davon gehört dem SDK

| Zahl | Wo sie lebt | Was sie dir sagt |
| --- | --- | --- |
| **SDK-Version** | `astra-plugin-sdk/Cargo.toml`, `astra-plugin-sdk-python/pyproject.toml`, `astra-plugin-sdk-ts/package.json` | Die Autoren-API, gegen die du schreibst. Jedes Paket hält seine eigene. |
| **Release-Zug** | das `sdk-v<VERSION>`-Git-Tag | Ein Tag veröffentlicht alle drei SDKs auf einmal. Es benennt die Version der **Rust-Crate**. |
| **Protokollversion** | `proto/PROTO_VERSION` (`protocol=1`), gespiegelt als `PROTOCOL_VERSION` in jedem SDK | Der Wire-Vertrag zwischen einem Plugin und dem Daemon. |
| **Die Version deines Plugins** | deine `plugin.toml` | Deine. Die Registry ordnet Releases danach. |

Die drei SDK-Versionen werden absichtlich nicht gleichgehalten. Der
aktuelle Zug ist `sdk-v0.6.0` und veröffentlicht:

| Paket | Registry | Version |
| --- | --- | --- |
| `astra-plugin-sdk` (Rust) | crates.io | 0.6.0 |
| `astra-plugin-macros` | crates.io | 0.6.0 — veröffentlicht **vor** dem SDK, das nach Version davon abhängt |
| `astra-plugin-sdk` (Python) | PyPI | 0.5.0 |
| `astra-plugin-sdk` (TypeScript) | npm | 0.5.0 |

Eine Versionsnummer beantwortet „gegen welche API schreibe ich", ein
Paket mit weniger Breaking-Releases hat also eine kleinere Zahl. Was der
Zug garantiert, ist, dass Pakete, die ein Tag teilen, dasselbe
**Protokoll** sprechen und dieselben Hooks implementieren — dafür sind
`spec/hooks.yaml` und der Paritäts-Checker da.

## SemVer, bei 0.x

Alle drei Pakete sind unter 1.0 und folgen SemVers 0.x-Lesart:

- **minor** (`0.5 → 0.6`) — darf die Quellkompatibilität brechen. Lies
  das CHANGELOG.
- **patch** (`0.6.0 → 0.6.1`) — nur Bugfixes und Ergänzungen. Wenn ein
  Patch-Release dein Plugin zum Nicht-mehr-Kompilieren bringt, ist das
  ein Bug im SDK; melde ihn.

Die Protokollversion ist getrennt und bewegt sich für sich. Sie ist eine
Ganzzahl, kein SemVer, und die Regel dafür ist nicht „lies das
Changelog", sondern ein Mechanismus:

- Ein Hook, den die Gegenseite nicht hat, antwortet mit
  `UNIMPLEMENTED`, was das Protokoll als *fehlend* definiert. Der Daemon
  liest es so und macht weiter. Deshalb läuft ein neueres Plugin gegen
  einen älteren Daemon und umgekehrt.
- `MIN_SUPPORTED_DAEMON_PROTOCOL` in jedem SDK ist der älteste Daemon,
  bei dem sich dieses SDK registriert. Darunter beendet sich das
  Plugin mit einem Satz, der den Fix nennt, statt beim ersten Aufruf zu
  scheitern.

## Die Deprecation-Richtlinie

Wenn etwas in der Autoren-API verschwindet:

1. **Es ist für mindestens zwei Minor-Versionen und mindestens ein
   Kalenderquartal veraltet**, je nachdem, was länger ist. Veraltet in
   0.6 heißt entfernbar in 0.8, und nicht bevor drei Monate vergangen
   sind. Ein Plugin, das heute baut, baut über mindestens ein Release
   hinweg weiter, das du planen kannst.
2. **Der Deprecation-Hinweis benennt den Ersatz.** Nicht „veraltet",
   nicht „benutze die neue API" — der tatsächliche Bezeichner, den du
   stattdessen tippen solltest, oder die Worte *kein Ersatz* und warum
   es keinen gibt. Eine Deprecation, die dir sagt aufzuhören, ohne dir
   zu sagen, wohin, schickt dich in den Issue-Tracker.
3. **Entfernungen stehen unter einer `BREAKING`-Überschrift im
   CHANGELOG**, im Paket, das sie entfernt hat, benennen, was entfernt
   wurde und was es ersetzt hat. Nichts wird in einem Patch-Release
   entfernt.

Wie „veraltet" in jeder Sprache aussieht:

| | Wie es markiert ist | Was du siehst |
| --- | --- | --- |
| Rust | `#[deprecated(since = "0.6.0", note = "…")]` | eine Compiler-Warnung an der Verwendungsstelle, mit dem Hinweis |
| Python | `DeprecationWarning` an der Aufrufstelle | `python -W error::DeprecationWarning` macht daraus einen Fehlschlag, gegen den du CI absichern kannst |
| TypeScript | `/** @deprecated … */` | eine Durchstreichung in deinem Editor und ein Hinweis beim Hover |

Eine Deprecation ist eine Warnung, nie ein Fehler. Wenn ein Release
veralteten Code *nicht mehr kompilieren* lässt, ist das eine Entfernung,
und Entfernungen folgen Regel 3.

### Was gerade veraltet ist

| Was | Veraltet in | Entfernt in | Ersatz |
| --- | --- | --- | --- |
| Rust: die gesamte 0.5-Trait-Oberfläche, als `astra_plugin_sdk::compat` | 0.6.0 | 0.8.0 | `PluginCapability` (0.6): `&PluginContext`, `Result<_, ToolError>`, `type Config`. Siehe [migration-0.6.md](migration-0.6.md) |
| Rust: `PluginCapability::source_id()` | 0.6.0 | 0.8.0 | Übergib die ID an `Host::send_chat_message`; der Daemon filtert nicht mehr nach Source-ID |
| Rust: `compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.6.0 | 0.8.0 | `Result<String, ToolError>` |
| Rust: `compat::HostClient` / `DaemonClient`-Aliase | 0.6.0 | 0.8.0 | `ctx.host()` / `ctx.daemon()` |
| Python: ein `dict`, wo eine Capability-Dataclass erwartet wird | 0.5.0 | 0.7.0 | Die Dataclass — `VoiceInfo`, `ToolDef`, … — oder ihr `to_proto()` |
| TypeScript: der `UiPanel`-Typalias | 0.5.0 | 0.7.0 | `UiContribution` |
| Hook: `AiGetModels` | 0.6.0 | 0.8.0 | Kein Ersatz — nichts im Daemon fragt ein Plugin, welche Modelle es hat |

Zwei Fußnoten, weil beides genau die Art von Sache ist, die diese
Richtlinie verhindern soll:

- Die Python-`DeprecationWarning` für dicts sagt, sie würden „für
  ein weiteres Minor-Release" akzeptiert. **Die Tabelle ist die
  bindende Zahl**: zwei Minor-Versionen und ein Quartal, also
  frühestens 0.7.0.
- `UiPanel` wurde in TypeScript ohne jede aufgezeichnete Version als
  veraltet markiert. Hier ist es auf 0.5.0 datiert — das erste Release,
  das das schriftlich sagt — und entfernbar ab 0.7.0.

## Die Richtlinie ist Daten

Regeln, die nur in einem Dokument leben, geraten genau in dem Moment in
Vergessenheit, in dem es wichtig ist: dem Release, in dem jemand das
Ding löscht. Die Pro-Hook-Hälfte der Richtlinie ist also eine Spalte in
[`spec/hooks.yaml`](../../spec/hooks.yaml):

<!-- doctest: illustrative reason="one row of spec/hooks.yaml, quoted; the file it belongs to is the source of truth and is checked by tools/parity/check.py" -->
```yaml
  - rpc: AiGetModels
    ...
    routing: deprecated
    deprecated_in: "0.6"
    removed_in: "0.8"
    note: "… Deprecated in 0.6, removed in 0.8, and there is no replacement: nothing in the daemon asks a plugin what models it has, and AiComplete carries the chosen model on the request."
```

`tools/parity/spec.py` validiert das bei jedem Parsen — also bei jedem
`gen.py`-Lauf, jedem `check.py`-Lauf, und damit bei jedem CI-Lauf:

| Regel | Der Fehlschlag, den sie verhindert |
| --- | --- |
| `routing: deprecated` verlangt `deprecated_in` | ein Hook, der seit Jahren „veraltet" ist, ohne dass ein Datum daranhängt |
| `deprecated_in` verlangt `removed_in` | eine Deprecation ohne Ende, was nur ein unhöflicher Kommentar ist |
| `removed_in` ≥ `deprecated_in` + 2 Minor-Versionen | eine Entfernung, die landet, bevor irgendjemand ein Release zum Migrieren hatte |
| die `note` einer veralteten Zeile nennt ein anderes RPC, oder sagt `no replacement` | „veraltet" ohne Nachsendeadresse |

Machst du dabei einen Fehler, sagt der Checker das, mit der Zeilennummer:

<!-- doctest: illustrative reason="the failure `tools/parity/check.py` prints for a hooks.yaml row that violates the removal policy; no such row exists in the tree, so producing it means editing hooks.yaml first" -->
```
spec/hooks.yaml is malformed:
  hooks.yaml:336: `AiGetModels` is deprecated in 0.6 and removed in 0.7 — the policy is
  2 minors and one quarter minimum, so the earliest removal is 0.8
```

Die Versionen in diesen Spalten sind **SDK-Minor-Versionen**, keine
Protokollversionen: `0.6` ist die Zahl in deiner `Cargo.toml` und die
Zahl, unter der die CHANGELOG-Überschrift abgelegt ist. Die
Ein-Quartal-Hälfte der Richtlinie ist Kalender statt Daten — der
Release-Zug datiert sie, und dieses Dokument ist, wo es niedergeschrieben
ist.

## Was von all dem nicht abgedeckt ist

- **Das eigene Verhalten des Daemons.** Astras UI, sein Config-Layout
  und seine internen Dienste sind keine Plugin-API. Worauf sich ein
  Plugin verlassen darf, sind das Protokoll, die Hooks in
  `spec/hooks.yaml`, und die Permissions in seinem Manifest.
- **Alles, was `#[doc(hidden)]`, `_private` markiert ist, oder für den
  Test-Harness exportiert wird.** Es kann sich in einem Patch ändern.
- **`unrouted`-Hooks.** Ein Hook kann im Proto und in allen drei SDKs
  existieren und keine Aufrufstelle im Daemon haben —
  `TtsSynthesizeStream` ist heute so einer. Ihn zu implementieren ist
  sicher und kostet nichts; sich *darauf zu verlassen*, dass der Daemon
  ihn aufruft, ist erst unterstützt, wenn sein `routing:` `live` sagt.

## Wenn ein Deprecation-Fenster nicht reicht

Sag es, bevor es schließt. Eine Entfernung, die gelandet ist, ist eine
Entfernung; eine Entfernung, die noch ein `removed_in` in
`spec/hooks.yaml` ist, ist ein Datum, und Daten können sich verschieben,
wenn jemand rechtzeitig sagt, warum.
</content>
