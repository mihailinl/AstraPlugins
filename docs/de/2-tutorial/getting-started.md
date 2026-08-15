> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/2-tutorial/getting-started.md) maßgeblich.

# Erste Schritte

Von null zu einem Plugin, das Würfel wirft, Tests hat und für ein Release
verpackt ist. Etwa fünfzehn Minuten, das meiste davon Wartezeit auf `cargo`.

Jeder Codeblock auf dieser Seite wird in der CI von
[`docs/tools/doctest.py`](../../tools/doctest.py) ausgeführt. Ist einer davon
falsch, ist der Build rot, bevor du ihn liest.

## 1 · Die CLI installieren

Eine Zeile. Sie dauert ein paar Minuten und endet mit der Ausgabe einer
Version.

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

Die Zahl ist mit Absicht ein Platzhalter: `--git` baut den Commit, den
`master` beim Ausführen gerade trägt, ausgegeben wird also dessen Version
und nicht eine, die du ausgewählt hättest.

Aus einem Klon heraus macht `cargo install --path astra-plugin-cli --locked`
dasselbe.

**Du brauchst Rust 1.85 oder neuer und `protoc` im PATH.** Ohne `protoc`
bleibt der Build bei ``Could not find `protoc` `` stehen. Installiere es mit
`apt install protobuf-compiler`, `pacman -S protobuf`, `brew install
protobuf` oder `winget install Google.Protobuf`, und führe die Zeile dann
erneut aus.

**Eine Versionsnummer kann dir nicht sagen, dass dieser Build gut ist, und
ein `0.2.0` ist kein schlechter.** `init-ci` pinnte früher ein Tag-*Objekt*,
wo GitHub einen Commit braucht, und der erste `git push --tags` eines
Plugins starb daran. Der Fix ist der Commit `5b8ab22`, der auf `master`
*vor* dem Versionssprung landete, der die Zahl auf `0.2.1` hob — ein Build
von `master` kann den Fix also tragen und trotzdem `0.2.0` ausgeben, und
kein `0.2.1`-Build existiert ohne ihn. Wer heute von `master` installiert,
bekommt den Fix, egal was die Zahl sagt; um zu prüfen statt zu vertrauen,
führe `astra-plugin init-ci` aus und lies den ausgegebenen Pin —
`e3329df252a46d747676cb540ae4b986af68a3ad` ist der Commit und ist richtig,
`dc1a044876926e9cf1170f034e2eab533ec07641` ist das Tag-Objekt und ist der
Bug. Lange Fassung:
[Die CLI installieren](../install-cli.md#der-bug-der-ein-erstes-release-kaputtmacht-und-wie-du-erkennst-ob-dein-build-den-fix-hat).

Ein Nebenpunkt, der dich nicht aufhält: Die CLI ist nicht auf crates.io und
hat keine vorgebauten Binärdateien, sodass das Bauen der einzige Weg ist, sie
zu bekommen. Vorgebaute Binärdateien sind geplant. Alle Details,
einschließlich was zu tun ist, wenn es nicht funktioniert:
[Die CLI installieren](../install-cli.md).

Prüfe die Maschine, bevor du dem Code die Schuld gibst:

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

Es beantwortet in einem Durchgang sechzehn Fragen — welche CLI du benutzt,
welches Config-Verzeichnis sie aufgelöst hat, ob Astra erreichbar ist,
welche Toolchains du hast (`protoc` eingeschlossen), und ob dein
Release-Workflow gepinnt ist. Es ist das Erste, was man ausführt, wenn
irgendetwas verwirrend ist.

## 2 · Scaffolding

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang rust --template tool
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller --lang rust --template tool" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

Sechs Dateien:

<!-- doctest: illustrative reason="an annotated tree of what `astra-plugin new` wrote, not a command; the run that produced it is the output block above" -->
```
dice-roller/
├── plugin.toml      das Manifest — id, Version, Capabilities, Einstiegspunkt
├── Cargo.toml       eine Abhängigkeit, plus ein langer Kommentar, warum nur eine
├── src/main.rs      das Plugin: fünfzehn Zeilen, plus ein Testmodul
├── README.md        was der Store neben deinem Plugin zeigt
├── icon.svg         ein Platzhalter-Icon, zum Ersetzen gedacht
└── .gitignore       `target/` und `*.astraplugin`
```

`README.md` und `icon.svg` sind keine Dekoration: der Packer nimmt beide
anhand ihres Namens auf, und die Registry liest sie aus dem verifizierten
Bundle wieder heraus, um die Karte und die Seite deines Listings zu bauen. Sie
sind das, was ein Mensch sieht, bevor er sich entscheidet, dich zu
installieren — ersetze sie also, bevor du veröffentlichst.
[Gelistet werden](../5-publish/get-listed.md) sagt, was jedes von beiden
braucht.

`--lang` akzeptiert `rust`, `python` oder `typescript`; `--template` wählt
die Capabilities und den Beispielcode, und `--capabilities tools,triggers`
überschreibt, was auch immer die Vorlage impliziert.

### Was das Scaffold pinnt

| Sprache | Das Scaffold pinnt | Veröffentlicht |
|---|---|---|
| Rust | `astra-plugin-sdk = "0.6"` | crates.io 0.6.0 |
| Python | `astra-plugin-sdk>=0.5,<0.6` | PyPI 0.5.0 |
| TypeScript | `"astra-plugin-sdk": "^0.5.0"` | npm 0.5.0 |

Das löst aus den Registries auf, sodass `cargo build`, `pip install -r
requirements.txt` und `bun install` in einem frischen Projekt funktionieren,
ohne dass etwas konfiguriert werden muss.

**Die unteren Grenzen sind tragend.** Rust 0.6 ist das erste Release, dessen
`HostClient` `x-session-token` anhängt, und Python und TypeScript 0.5.0 sind
ihre jeweiligen; gegen alles Ältere antwortet der Daemon bei jedem
Host-Aufruf mit `unauthenticated`. Eine Untergrenze zu lockern tauscht einen
Resolver-Fehler gegen einen Laufzeitfehler — der schlechtere Tausch: Das
Plugin startet, bedient Hooks, und kann still nicht zurücksprechen.

Python: `astra-plugin test` führt dein Plugin mit dem `python` aus, das auf
`PATH` liegt — aktiviere also zuerst die virtuelle Umgebung, in die du
installiert hast. Sonst beendet sich das Plugin mit
`ModuleNotFoundError: astra_plugin_sdk`, bevor es sich registriert.

## 3 · Das Plugin schreiben

Ersetze `src/main.rs` durch dies. Es ist das ganze Plugin — typisierte
Argumente, ein Tool, ein Trigger und drei Tests.

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

/// The arguments the model sends. The doc comments become the JSON Schema it
/// reads, so write them for a reader who has never seen this plugin.
#[astra::args]
struct Roll {
    /// How many dice to roll
    #[serde(default = "one")]
    count: u32,
    /// How many sides each die has
    #[serde(default = "six")]
    sides: u32,
}

fn one() -> u32 { 1 }
fn six() -> u32 { 6 }

#[derive(Default)]
struct DiceRoller;

#[astra::plugin]
impl DiceRoller {
    /// Roll dice and return the total. Use it whenever the user asks for a
    /// random number, a dice roll, or a coin flip.
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
        if a.sides < 2 {
            return Err(ToolError::BadArguments("a die needs at least 2 sides".into()));
        }
        let total: u32 = (0..a.count).map(|_| 1 + rand_below(a.sides)).sum();
        ctx.host()
            .fire_trigger("dice_rolled", &json!({ "total": total }).to_string())
            .await?;
        Ok(total.to_string())
    }
}

/// Not a dependency: `SystemTime` is enough entropy for a dice roll.
fn rand_below(n: u32) -> u32 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos();
    nanos % n
}

astra::main!(DiceRoller::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn it_rolls_and_fires_the_trigger() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();

        let total: u32 = h
            .call_tool("roll_dice", json!({ "count": 3, "sides": 6 }))
            .await
            .expect("the tool answered")
            .parse()
            .unwrap();
        assert!((3..=18).contains(&total), "three d6 cannot total {total}");

        assert_eq!(h.fired_triggers().len(), 1);
        assert_eq!(h.fired_triggers()[0].trigger_type, "dice_rolled");
    }

    #[tokio::test]
    async fn a_one_sided_die_is_rejected() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        let err = h
            .call_tool("roll_dice", json!({ "sides": 1 }))
            .await
            .expect_err("a die needs two sides");
        assert!(err.to_string().contains("2 sides"), "{err}");
    }

    /// What the user sees if they never granted `fire_trigger`.
    #[tokio::test]
    async fn a_denied_permission_surfaces_as_an_error() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        h.host().deny("fire_trigger");
        let err = h.call_tool("roll_dice", json!({})).await.expect_err("denied");
        assert!(err.to_string().contains("fire_trigger"), "{err}");
    }
}
```

Fünf Dinge sind es wert, benannt zu werden:

- **`#[astra::args]`, nicht `#[derive(Deserialize, JsonSchema)]`.** Das
  Derive von serde erzeugt `extern crate serde`, was über das Extern-Prelude
  aufgelöst wird und nicht über einen Re-Export erreicht werden kann — das
  einfache Derive würde also `serde` in *deiner* `Cargo.toml` brauchen, genau
  das, was das Scaffold verspricht, dass du es nicht brauchst.
  `#[astra::args]` sind diese beiden Derives, auf die Kopien des SDK
  gerichtet.
- **Der Doc-Kommentar ist die Beschreibung, die das Modell liest.** Sowohl am
  Tool als auch an jedem Feld. Sag, wann das Tool zu benutzen ist, nicht wie
  es funktioniert.
- **Handler geben `Result<_, ToolError>` zurück.** Ein Fehlschlag pro Aufruf
  ist *Daten*: Die AI-Schleife liest ihn und entscheidet, was zu tun ist, er
  reist also in der Antwort mit, nicht als gRPC-Status. `?` funktioniert mit
  `serde_json::Error`, `std::io::Error`, `tonic::Status` und `anyhow::Error`.
- **`ctx.host()` ist immer da.** Der Kontext trägt den Host-Client, die
  UI-Sprache und die aktuelle Trigger-Menge; er ist billig in eine
  Hintergrundaufgabe zu klonen und ist nie `None`. Nichts liegt in deiner
  Struct hinter einem Lock.
- **`h.host().deny("fire_trigger")` inszeniert eine Verweigerung.** So sieht
  ein Nutzer aus, der nicht zugestimmt hat, und das ist einen Test wert — es
  ist der Fehler, den sonst dein Issue-Tracker bekommt.

`cargo test` führt diese drei gegen einen aufzeichnenden Host aus: kein
Daemon, kein Socket, kein installiertes Astra.

<!-- doctest: illustrative reason="the block above carries test=1, so the doc-test already ran cargo test on it" -->
```bash
cargo test
```

## 4 · Deklarieren, was du brauchst

Das Tool ruft `fire_trigger` auf, und `[permissions]` ist standardmäßig
verweigernd, also muss es fragen. Der `reason` ist das, was der Nutzer liest,
wenn Astra ihn um Zustimmung bittet — schreib ihn als Satz über *dein
Plugin*, nicht über die Permission.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat, and fire a trigger with the result."
author = "Your Name"
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

Dann prüfen:

<!-- doctest: cli -->
```bash
astra-plugin check --strict
astra-plugin check --fix
```

`check` liest das Manifest mit dem eigenen Parser des Daemons — derselben
Crate, gevendort und bytegleich gehalten — sodass es nicht von dem
abweichen kann, was bei der Installation passieren wird. `--fix` wendet die
Korrekturen an, die es beweisen kann, und meldet den Rest.

## 5 · Die Conformance-Suite ausführen

<!-- doctest: cli -->
```bash
astra-plugin test
```

Das ist eine Stufe über `cargo test`: Es startet dein Plugin so, wie der
Daemon es startet, gegen einen Mock-Daemon, der `PluginHostService`
bedient, und ruft jeden eingehenden Hook auf, den deine deklarierten
Capabilities implizieren.

<!-- doctest: output from="astra-plugin test . --no-build, in the dice-roller project this page builds (the plugin's own tracing lines, which go to stderr, are left out)" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] GetPluginTriggerTypes    required  0 trigger type(s)
  [ok  ] CallTool                 required  `roll_dice` answered
  [ok  ] OnActiveTriggers         optional  accepted 0 active trigger(s)
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 40.8ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 775.4µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] Shutdown is honoured within the grace period: the process exited 40.8ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 2 host call(s) reached the daemon: fire_trigger, log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 8 hook(s) exercised, 6 check(s) passed.
```

`GetPluginTriggerTypes` meldet **0**, obwohl das Plugin einen Trigger
auslöst. Einen Trigger auszulösen und ihn *anzubieten* sind unterschiedliche
Dinge: Der Befehlseditor listet auf, was das Plugin deklariert, also einen
`#[hook] async fn trigger_types(&self) -> Vec<TriggerTypeDef>`, und das
Plugin oben hat keinen. Scaffolding mit `--capabilities tools,triggers`
schreibt diesen Hook für dich; §3 ließ ihn weg, um die Datei auf einen
Bildschirm zu begrenzen. Löst du ohne Deklaration aus, feuert der Trigger
trotzdem — aber niemand kann einen Befehl daran verdrahten.

Ein `required`-Hook darf nicht mit `UNIMPLEMENTED` antworten; ein
`optional`-Hook darf das, weil `UNIMPLEMENTED` auf der Leitung *bedeutet*
„dieser Hook fehlt".

## 6 · Es innerhalb von Astra ausführen

Dieser Schritt braucht ein laufendes Astra und den **Entwicklermodus**, weil
er ein unsigniertes Verzeichnis sideloaded:

<!-- doctest: cli -->
```bash
astra-plugin dev
```

Es führt `check --strict` aus, baut, übergibt das Verzeichnis dem Daemon —
der den Prozess startet, sein Token prägt und seinen Lebenszyklus besitzt —
und beobachtet dann auf Änderungen, baut neu, startet neu und verfolgt die
Logs.

Lies [Sideloading](../5-publish/sideload.md), bevor du den Entwicklermodus
einschaltest. Es ist ein Entwicklerwerkzeug: Es führt unsignierten lokalen
Code mit deinen vollen Benutzerrechten aus, und der Schalter senkt die
Hürde für jedes Plugin auf der Maschine, nicht nur für dieses eine. So
installiert niemand ein Plugin.

Wenn `dev` Astra nicht erreicht, sagt dir `astra-plugin doctor`, was von
beidem falsch ist — der Daemon läuft nicht, oder er hat ein anderes
Config-Verzeichnis aufgelöst als die CLI.

## 7 · Verpacken

<!-- doctest: cli -->
```bash
astra-plugin build
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin build ., in the dice-roller project this page builds (the size and the two digests are properties of your build, not constants)" unrun="needs a scaffolded, compiled plugin on disk; re-run it in the project this page builds" -->
```
Building plugin 'dice-roller' v0.1.0 (rust) for linux-x64...
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 0.04s
  Added: README.md (0644)
  Added: bin/dice_roller (0755)
  Added: plugin.toml (0644)
  Built: dice-roller-0.1.0-linux-x64.astraplugin (2757.1 KB, 3 files)
  target:          linux-x64
  artifact sha256: 3ae95e05f49156b137afe4b528dc1feb4df4c36c5e8c284b52b7b15e4f3345fa
  manifest digest: 11b1b78dd55232877c881e862e109ec594aa535167d27063a2e3fcbe373d9824
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
  See https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/publishing.md#what-establishes-trust
```

`verify` liest erneut, was `build` gerade geschrieben hat, und beantwortet
eine andere Frage: dass `MANIFEST.json` Eintrag 0 und gespeichert ist, dass
die Dateiliste in beide Richtungen vollständig ist, und dass jeder
aufgeführte Digest, jede Größe und jeder Modus mit dem Archiv
übereinstimmt. Es sagt nichts darüber, wer es geschrieben hat — das ist die
Aufgabe der Registry.

Der Dateiname ist nicht kosmetisch: `<id>-<version>-<target>.astraplugin` ist
der Name, den ein veröffentlichtes Bundle haben muss, und das
Target-Segment ist der Plattform-Schlüssel der Registry.

**`build` signiert nicht, und du brauchst keinen Schlüssel.** Was Astra dazu
bringt, ein Plugin zu installieren, ist ein Registry-Eintrag, der den
sha256 der gesamten Datei gegensigniert — nicht irgendein Schlüssel, den du
besitzt. Siehe [das Sicherheitsmodell](../1-orientation/security.md).

## 8 · Veröffentlichen

Jetzt der Teil, der zählt, und es sind zwei Befehle:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
astra-plugin version 0.1.1
```

`init-ci` schreibt `.github/workflows/release.yml`, per Commit-SHA an Astras
wiederverwendbaren Release-Workflow gepinnt. Danach ist **ein Tag der ganze
Release-Prozess**: CI baut jedes Target, bezeugt jedes Bundle mit GitHubs
Build-Provenienz und hängt sie an ein GitHub-Release an.

Dann eine einzige Einreichung, ein einziges Mal, und jedes spätere Release
läuft ohne weiteres Zutun.

Beachte, was Veröffentlichen **nicht** ist: Dieses Repository auf GitHub zu
pushen veröffentlicht dein Plugin nicht, ebenso wenig jemandem die gerade
gebaute `.astraplugin` zu schicken. Die Registry pinnt den Digest einer von
CI erzeugten Datei und liest die daran angehängte Build-Attestation, und
eine auf deinem Laptop gebaute Datei trägt keines von beidem.

**→ [Ein Plugin veröffentlichen](../publishing.md)** — der ganze Weg auf
einer Seite, von hier bis zum gelisteten Plugin, mit jedem Befehl und
seiner erwarteten Ausgabe. Die Stufenseiten dahinter:
[Mit CI veröffentlichen](../5-publish/release-with-ci.md) ·
[Gelistet werden](../5-publish/get-listed.md)

## Dasselbe in Python

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang python --template tool
```

<!-- doctest: python-plugin -->
```python
"""DiceRoller — an Astra plugin."""

from astra_plugin_sdk import Plugin, tool


class DiceRoller(Plugin):
    """Roll dice from chat."""

    @tool("Roll dice and return the total.")
    async def roll_dice(self, count: int = 1, sides: int = 6) -> str:
        # The parameters ARE the schema: a parameter with no default is
        # required, one with a default is optional, and the type hints become
        # the JSON types the model is shown.
        if sides < 2:
            raise ValueError("a die needs at least 2 sides")
        total = sum(1 + (i % sides) for i in range(count))
        await self.host.fire_trigger("dice_rolled", f'{{"total": {total}}}')
        return str(total)


if __name__ == "__main__":
    DiceRoller().run()
```

Der Einstiegspunkt ist `[entry] command = "python"`,
`args = ["-m", "src.plugin"]`, `runtimes = ["python"]`, und das Bundle ist
`noarch`.

## Dasselbe in TypeScript

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang typescript --template tool
```

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    roll_dice: tool({
      description: "Roll dice and return the total.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs.
      input: s.object({
        count: s.number({ description: "How many dice to roll" }).optional(),
        sides: s.number({ description: "How many sides each die has" }).optional(),
      }),
      run: ({ count, sides }) => {
        const n = count ?? 1;
        const faces = sides ?? 6;
        if (faces < 2) throw new Error("a die needs at least 2 sides");
        let total = 0;
        for (let i = 0; i < n; i++) total += 1 + Math.floor(Math.random() * faces);
        return String(total);
      },
    }),
  },
});

// `astra-plugin build` bundles this to CommonJS, so `require.main` is the
// honest "am I the entrypoint" test. Importing this module — as a test does —
// does not start a server.
if (require.main === module) app.run();
```

## Wie es weitergeht

| Wenn du willst | Lies |
|---|---|
| Die ganze Rust-API | [Rust-SDK](../4-sdk/rust.md) |
| Jeden `plugin.toml`-Schlüssel | [Manifest-Referenz](../reference/manifest.md) |
| Jeden Hook, in jedem SDK | [Parität](../reference/parity.md) |
| Es ausliefern | [Mit CI veröffentlichen](../5-publish/release-with-ci.md) |
| Etwas ist kaputt | [Fehlerbehebung](../6-operate/troubleshooting.md) |
| Ein durchgearbeitetes Beispiel | [Beispiele](../7-examples/README.md) — elf davon |
</content>
