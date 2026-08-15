> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/3-reference/permissions.md) maßgeblich.

# Permissions

Was jede `[permissions]`-ID gewährt, was sie den Nutzer kostet, und wie man
einen `reason` schreibt, der sich zu lesen lohnt.

Das ist die autorenseitige Seite. Die normativen Regeln — Gewährungen,
Obergrenzen, `permissions_hash`, die genaue Ablehnungssemantik — stehen in
[`spec/permissions.md`](../spec/permissions.md). Die generierte Tabelle,
welches RPC welche ID sperrt, steht in
[`reference/manifest.md`](../reference/manifest.md) und
[`reference/parity.md`](../reference/parity.md), beide abgeleitet aus
`spec/hooks.yaml` und gegen die eigene Tabelle des Daemons durch
Paritätsregel R6 geprüft.

## Die Grundform

`[capabilities]` sagt, was der Daemon **in** dein Plugin hinein aufrufen
darf. `[permissions]` sagt, welche Host-RPCs dein Plugin **hinaus** rufen
darf. Zwei Fragen, zwei Abschnitte; eine Capability impliziert nie eine
Permission.

Drei Eigenschaften, die irgendwann jeden überraschen:

1. **Default-deny.** Kein `[permissions]`-Abschnitt bedeutet keine
   Host-RPCs über die vier Bootstrap-Aufrufe hinaus.
2. **Deklarieren heißt Fragen, nicht Erhalten.** Dein Manifest ist eine
   Anfrage. Die gewährte Menge wird vom Daemon anhand der Herkunft des
   Plugins aufgelöst und, für ein installiertes oder importiertes Plugin,
   dort gespeichert, wo das Plugin sie nicht schreiben kann — das Manifest
   liegt im eigenen Verzeichnis deines Plugins, das dein Plugin bearbeiten
   kann. **Sideloading kehrt das um**: für ein Quellverzeichnis im
   Entwicklermodus *ist* das Manifest die Gewährung, bei jedem Laden neu
   gelesen, ohne Obergrenze. Das ist es, was die Entwicklungsschleife zum
   Laufen bringt, und auch der Grund, warum Sideloading ein
   Entwicklerwerkzeug ist und kein Installationsweg.
3. **Eine unbekannte ID wird behalten und ist wirkungslos.** Neue IDs
   erscheinen mit neuen Astra-Versionen, also behält ein älterer Daemon
   einen ihm unbekannten Schlüssel, statt dein Manifest abzulehnen. Er
   gewährt nichts. `astra-plugin check` warnt — ein Tippfehler ist zur
   Parse-Zeit nicht von einer vorwärtskompatiblen ID zu unterscheiden,
   daher eine Warnung statt eines Fehlers, und `--strict` macht daraus einen
   fehlgeschlagenen Exit:

   <!-- doctest: output from="astra-plugin check --strict ." unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client
     FAILED: 1 warning(s), and --strict treats warnings as errors
   ```

   Astras Installations-Einwilligungsblatt zeigt dieselbe ID unter seinem
   Label `permission.unrecognised`, sie wird also auch beim Import nie
   still fallengelassen.

## Die vier kostenlosen Aufrufe

| RPC | Warum es frei ist |
|---|---|
| `Register` | Der Handshake. Es gibt noch kein Plugin, das Permissions haben könnte |
| `PluginLog` | Schreiben ins eigene Log |
| `GetPluginSelfConfig` | Lesen der eigenen Einstellungen |
| `GetDaemonInfo` | `version`, `state`, `grpc_port`, `language` — alles bereits in der Register-Antwort übergeben |

Dass `GetDaemonInfo` frei ist, ist eine Entscheidung, kein Versehen: eine
Checkbox, die nichts schützt, ist der Weg, wie Nutzer lernen, Kästchen
blind anzuhaken.

## Die acht IDs

| ID | Sperrt | Eigene Checkbox | Bei lokalem Import verweigert | Was sie dir erlaubt |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | nein | nein | Die gespeicherten Automatisierungen des Nutzers ausführen |
| `subscribe_events` | `SubscribeEvents` | nein | nein | Daemon-Events empfangen — **nimmt eine `types`-Allowlist** |
| `set_variable` | `SetVariable` | nein | nein | In den Variablenkontext des Daemons schreiben, dir zugeordnet |
| `send_chat_message` | `SendChatMessage` | **ja** | **ja** | Einen AI-Turn auslösen, als hätte der Nutzer gesprochen |
| `push_to_ui` | `PushToUi` | **ja** | nein | Ein Event in deine eigenen Panels pushen |
| `set_theme_contribution` | `SetThemeContribution` | **ja** | **ja** | Die gesamte App umgestalten |
| `dom_access` | — (eine Surface) | **ja** | **ja** | Deinen Code im Astra-Fenster ausführen, mit Zugriff auf Unterhaltungen und die Oberfläche jedes anderen Plugins |
| `client` | — (eine Surface) | **ja** | **ja** | Ein Chat-Frontend mit eigener Session sein |

`dom_access` und `client` sperren kein RPC, und das ist der Punkt: Sie sind
**Surfaces**. `dom_access` entscheidet, ob eine UI-Contribution als Skript
im Astra-Fenster oder als gesandboxtes iframe gerendert wird; `client` ist
eine Obergrenze dafür, was ein Plugin sein darf. Sie werden dort verweigert,
wo die Surface ausgegeben wird, nicht an einem Aufruf-Gate.

`dom_access` bekommt zusätzlich einen zweiten Zustimmungsbildschirm. Wenn du
danach greifst, lies zuerst
[das Sicherheitsmodell](../1-orientation/security.md) und stell sicher,
dass `push_to_ui` in dein eigenes Panel nicht ausreicht.

## Argumente

Zwei IDs nehmen Argumente, und beide schränken ein, was du bekommst.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "meeting-notes"
name = "Meeting Notes"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/meeting_notes"

[capabilities]
tools = true
event_handlers = true

[permissions]
subscribe_events = { types = ["command_completed", "state_changed"], reason = "Notices when a recording command finishes so it can write the summary" }
set_variable = { scopes = ["plugin"], reason = "Stores the id of the note it just wrote so your commands can open it" }
fire_trigger = { reason = "Fires meeting_summarised when a summary is ready" }
```

- **`subscribe_events.types` ist eine Allowlist, vom Daemon durchgesetzt** —
  nicht vom Filter, den dein Plugin sendet. Ohne sie erhielt jeder
  Abonnent jedes Event, einschließlich `speech_recognized`, das die
  Transkripte des Nutzers trägt. Eine leere Liste erlaubt nichts.
- **`set_variable.scopes`** ist `"plugin"`, `"session"` oder
  `"persistent"`.

## Einen Reason schreiben

Der `reason` wird unter Astras eigenem Label für die Permission angezeigt,
visuell untergeordnet, in Anführungszeichen, als Klartext, auf 140 Zeichen
begrenzt, und stets mit *"The author says:"* vorangestellt. Das Label
gehört Astra, in der Sprache des Nutzers; der Reason gehört dir. Du kannst
das Label nicht selbst gestalten, und das ist Absicht: Formulierungs-Fixes
werden mit Astra ausgeliefert und dürfen nicht durch ein Listing schreibbar
sein.

Ein guter Reason:

- **nennt das Feature, das der Nutzer erkennt**, nicht die API — *"Fires the
  on_dice_roll trigger you configure"*, nicht *"calls FireTrigger"*;
- **sagt, wann**, falls nicht immer — *"only while a recording is in
  progress"*;
- **wiederholt nicht das Label.** Astra hat es schon gerendert;
- **drängt nicht.** Keine Dringlichkeit, keine Drohungen, keine
  Anweisungen an den Nutzer. Ein Einwilligungsblatt ist der letzte Ort, um
  eine Ausnahme zu machen, und Text mit bidi-Overrides oder
  Zero-Width-Joinern wird dort abgelehnt, wo er wörtlich angezeigt wird.

| Statt | Schreib |
|---|---|
| `"needs fire_trigger"` | `"Fires the trigger you configure when a roll completes"` |
| `"required for the plugin to work"` | `"Reads command-completion events so it can log the run"` |
| `"full access to the UI"` | `"Draws the timer in the panel this plugin adds to the sidebar"` |
| `"REQUIRED! Do not disable!"` | — die Permission entfernen, oder sagen, wofür sie ist |

Eine Permission ohne plausiblen Reason ist eine Permission, die aus dem
Manifest zu löschen ist. Nichts prüft das automatisch; eine Person, die
dein Listing liest, ist die einzige Rückfallebene, und `astra-plugin check`
sagt dir, wenn du eine Permission deklariert hast, die deine Capabilities
nicht brauchen.

## Was passiert, wenn eine Permission fehlt

Der Aufruf kommt als `permission_denied` zurück, mit einer Nachricht, die
die Permission **und** die Herkunft der gewährten Menge nennt. In einem
Test kannst du genau das inszenieren:

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Notifier;

#[astra::plugin]
impl Notifier {
    /// Announce that something happened.
    #[tool]
    async fn announce(&self, ctx: &PluginContext) -> Result<String, ToolError> {
        // Handle the denial rather than propagating it: a tool that returns an
        // error the model cannot act on is worse than one that says what it did.
        match ctx.host().fire_trigger("announced", "{}").await {
            Ok(()) => Ok("announced".into()),
            // `{e:#}` and not `{e}`: the host call fails with a short outer
            // message and the useful half — the permission id and where the
            // granted set came from — is in the cause chain.
            Err(e) => Ok(format!("could not fire the trigger: {e:#}")),
        }
    }
}

astra::main!(Notifier::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn a_missing_grant_is_reported_not_hidden() {
        let h = Harness::new(Notifier::default()).start().await.unwrap();
        h.host().deny("fire_trigger");

        let answer = h.call_tool("announce", json!({})).await.unwrap();
        assert!(answer.contains("fire_trigger"), "{answer}");
    }
}
```

`astra-plugin doctor` beantwortet dieselbe Frage über ein Manifest, bevor
du es je ausführst:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## Woher die gewährte Menge kommt

| Installationsweg | Gewährt |
|---|---|
| Aus dem Store, verifiziert | was das Manifest anfragte, nach Zustimmung |
| Eine `.astraplugin`-Datei, von Hand importiert | das Manifest, **gekappt**: `send_chat_message`, `set_theme_contribution`, `dom_access`, `client` werden pauschal verweigert |
| Ein sideload­etes Quellverzeichnis, Entwicklermodus an | das Manifest, ungekappt |
| `Untrusted` / `TamperDetected` / `Revoked` | nichts |
| Vor Existenz von Trust-Records installiert | das Manifest, gekappt wie eine importierte Datei |

Vollständige Tabelle und Begründung:
[`spec/permissions.md` §4](../spec/permissions.md).

## Zustimmung, aus Sicht des Nutzers

Permissions sind nach Risiko gruppiert. Die fünf hochriskanten bekommen
jeweils eine eigene Checkbox, und „Installieren" bleibt deaktiviert, bis
jede angehakt ist; `dom_access` bekommt einen zweiten Bildschirm. Es gibt
absichtlich **kein Tippen-zum-Bestätigen**: das ist das Muster für
unumkehrbare Zerstörung, und Nutzer daran zu gewöhnen, sich hindurchzutippen,
zerstört das Signal, das die Checkbox trägt.

Bei einem Update: unveränderte oder verengte Permissions greifen still;
**erweiterte** Permissions stellen das Update bereit, ohne es zu
installieren, und lassen die alte Version laufen, bis der Nutzer die
Änderung prüft. Ablehnen kostet nichts.
</content>
