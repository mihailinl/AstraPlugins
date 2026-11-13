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
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client, read_ai_settings, speak, read_user_identity, receive_attachments, request_settings_change, propose_commands
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

## Die vierzehn IDs

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
| `read_ai_settings` | `GetAiSettings` | nein | nein | Den Chat-Provider, das Modell und den Endpunkt des Nutzers lesen — nie einen Schlüssel |
| `speak` | `Speak`, `StopSpeaking` | **ja** | nein | Deine eigenen Worte mit Astras Stimme laut aussprechen und sie anhalten |
| `read_user_identity` | `GetUserIdentity` | nein | nein | Pseudonyme für diese Installation und das angemeldete Konto lesen, nur für dein Plugin erzeugt |
| `receive_attachments` | — (eine Zustellung) | **ja** | nein | Die Bilder bekommen, die die Person angehängt hat, in einem Tool, das darum bittet |
| `request_settings_change` | `RequestSettingsChange` | nein | nein | Die Person bitten, eine Einstellung zu ändern, die der Assistent ändern darf, auf einer Karte, die sie beantwortet |
| `propose_commands` | `ProposeCommand` | **ja** | nein | Der Person einen Befehl zum Behalten anbieten, den sie über das Workshop-Blatt von Astra behält |

`dom_access` und `client` sperren kein RPC, und das ist der Punkt: Sie sind
**Surfaces**. `dom_access` entscheidet, ob eine UI-Contribution als Skript
im Astra-Fenster oder als gesandboxtes iframe gerendert wird; `client` ist
eine Obergrenze dafür, was ein Plugin sein darf. Sie werden dort verweigert,
wo die Surface ausgegeben wird, nicht an einem Aufruf-Gate.
`receive_attachments` sperrt ebenfalls kein RPC, von der anderen Seite her:
Es gibt nichts für dich aufzurufen. Es entscheidet, was Astra einem deiner
Tools *schickt* — [siehe unten](#die-bilder-empfangen-die-die-person-angehängt-hat).

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

## Die KI-Einstellungen des Nutzers lesen

Ein Plugin, das das Modell des Nutzers selbst aufruft — ein eigener Assistent, ein Zusammenfasser —, muss wissen, welchen Provider, welches Modell und welchen Endpunkt der Nutzer gewählt hat. **Frag Astra danach; lies niemals Astras Dateien.** Deklariere `read_ai_settings` und rufe `GetAiSettings` auf (`get_ai_settings()` in Rust und Python, `getAiSettings()` in TypeScript):

| Feld | Was es ist |
|---|---|
| `provider` | Die Provider-ID des Chats. Ein vom Nutzer gespeicherter Endpunkt ist `openai_compatible`; Astras eigener Dienst ist `astra` |
| `model` | Die Modell-ID des Chats |
| `api_base_url` | Der Endpunkt. Userinfo, Query und Fragment sind entfernt; der Pfad wird so gesendet, wie die Person ihn konfiguriert hat (ein Relay, das ein Token in den Pfad legt, gibt es dir weiter). Leer bei `astra`, dessen Endpunkt nicht für dich zum Aufrufen da ist |
| `is_loopback` | Der Endpunkt liegt auf diesem Rechner (`127.0.0.0/8`, `::1`, `localhost`) — ein lokales Modell |

Er enthält nie einen API-Schlüssel, nie die anderen gespeicherten Endpunkte des Nutzers, nie den System-Prompt und keine andere Rolle als die des Chats. Ein Plugin, das einen Schlüssel braucht, fragt den Nutzer in seiner eigenen `[config]` danach (als geheim markieren). Er ist weder hochriskant noch bei einem lokalen Import abgelehnt: Es ist der ehrliche Weg zu dieser Information, und ihn teurer zu machen als das Lesen von `settings.json` würde Plugins in die falsche Richtung schieben. Astras eigene Dateien zu lesen ist etwas, wonach die menschliche Prüfung bei der Veröffentlichung sucht. Ein Astra, das älter als dieser Aufruf ist, antwortet mit `UNIMPLEMENTED`.

## Mit Astras Stimme sprechen

Ein Plugin, das etwas anzukündigen hat — einen Timer, einen fertigen Build, eine eingetroffene Nachricht —, kann Astra das sagen lassen. Deklariere `speak` und rufe `Speak` auf (`speak(text)` in Rust und Python, `ctx.speak(text)` in TypeScript).

`speak` ist **hochriskant**: Deine Worte werden mit Astras Stimme gehört, als hätte Astra sie gesagt, deshalb bekommt es eine eigene Zustimmungs-Checkbox. Bei einem lokalen Import wird es nicht abgelehnt — eine Ansage ist etwas Gewöhnliches, das ein Plugin wollen kann, und die Checkbox ist die Entscheidung. Neben der Gewährung braucht `Speak` **ein Konto, das Astra freischaltet**, und **die eingeschaltete Antwortstimme der Person**; solange Astra gesperrt ist, wird es abgelehnt.

Der Aufruf dauert so lange wie die Sprachausgabe und antwortet damit, was aus ihr wurde:

| Ergebnis | Was es bedeutet | Was zu tun ist |
|---|---|---|
| `SPOKEN` | Es wurde gehört | Nichts |
| `STOPPED` | Bevor es zu Ende war, wurde um Stille gebeten: das Wake-Word, die ausgeschaltete Antwortstimme, Stopp, dein eigenes `StopSpeaking` | Nichts — **es ist kein Fehler**. Sag es nicht ungefragt noch einmal |
| `NOT_SPOKEN` | Es wurde nicht gesagt; `error` (derselbe `PluginError`, den ein Chat-Chunk trägt) sagt, warum | Lies den Code unten. Nichts Abgelehntes wird eingereiht |

| `error.code` | Wann |
|---|---|
| `PLUGIN_ERROR_BAD_ARGUMENTS` | Der Text ist leer, sobald unsichtbare Zeichen entfernt sind, oder länger als **300 Zeichen** (`speak_text_max_chars` in `spec/limits.yaml`). Ein längerer Text wird abgelehnt, nie gekürzt |
| `PLUGIN_ERROR_RATE_LIMITED` | Deine Sprechzeit ist aufgebraucht. Sie wird in Zeichen bemessen — **450 auf einmal, danach 3 pro Sekunde**, jeder Aufruf kostet mindestens 20 —, und `retry_after_ms` sagt, wann wieder Platz ist |
| `PLUGIN_ERROR_UNAVAILABLE` | Die Person hat Astras Stimme ausgeschaltet, Astra ist gesperrt, es gibt keine Stimme, oder die Sprachwarteschlange konnte es nicht aufnehmen. Zeig stattdessen den Text; bitte die Person nicht, das zu ändern |

Deine Worte reihen sich hinter deine eigenen früheren ein, auf einer eigenen Spur, sodass sie nie eine von Astras Antworten unterbrechen. `StopSpeaking` hält alles an, was du sagen lassen wolltest — was gerade erklingt und was noch wartet —, und nichts sonst; es teilt sich die Permission `speak` und funktioniert, ob jemand angemeldet ist oder nicht. Die Grenzen sind die des Daemons: Die SDKs exportieren `SPEAK_TEXT_MAX_CHARS`, damit du einen Zähler anzeigen kannst, und prüfen selbst nichts. Ein Astra, das älter als dieser Aufruf ist, antwortet mit `UNIMPLEMENTED`.

## Wissen, wer Astra benutzt

Ein Plugin, das die Nutzung pro Person oder pro Rechner begrenzt — eine Testphase, ein Kontingent, eine Lizenz —, braucht für jede eine stabile ID. **Frag Astra danach; lies nie eine Hardware-Seriennummer oder Astras Dateien.** Deklariere `read_user_identity` und rufe `GetUserIdentity` auf (`get_user_identity()` in Rust und Python, `ctx.getUserIdentity()` in TypeScript):

| Feld | Was es ist |
|---|---|
| `install_id` | Diese Installation von Astra: gleich über Neustarts und Updates von Astra und deinem Plugin hinweg, anders auf einer anderen Installation. Leer, solange Astra noch keinen Installationsschlüssel hat |
| `signed_in` | Eine Person ist bei Astra angemeldet |
| `authorized` | …und ihr Konto schaltet Astra frei |
| `account_id` | Das angemeldete Konto: gleich auf jedem Gerät, auf dem sich die Person anmeldet. Leer, außer bei `authorized` |

Beide IDs sind **Pseudonyme, nur für dein Plugin erzeugt**: Ein anderes Plugin liest für dieselbe Person und denselben Rechner andere IDs, sodass zwei Plugins ihre Datensätze nicht darüber verknüpfen können. Das gilt gegenüber Plugins, die diese API ehrlich nutzen: nativer Plugin-Code kann die Dateien von Astra lesen. Keine ist geheim, und keine ist je die eigene ID des Kontos, der Name oder die E-Mail-Adresse der Person oder eine Hardware-Seriennummer. Die Permission ist weder hochriskant noch bei einem lokalen Import abgelehnt: Sie ist die ehrliche Alternative zu einer Seriennummer des Rechners, und ein hoher Preis würde ein Plugin zu einer solchen zurücktreiben. Ein Astra, das älter als dieser Aufruf ist, antwortet mit `UNIMPLEMENTED`.

**`auth_changed` ist entsprechend eingeschränkt** (Astra, 2026-11-12). Ein Plugin, dem das Event `auth_changed` gewährt ist, erhielt früher die eigene ID des Kontos, den Anzeigenamen der Person und ihren Tarif. Jetzt erhält es `authenticated`, `authorized`, `timestamp` und `account_id` — dasselbe Pseudonym, das `GetUserIdentity` liefert, und `""`, außer du hältst `read_user_identity` und das Konto schaltet Astra frei. `user_id` und `user_name` kommen weiterhin an, als `null`, und `subscription_tier` als `""`, damit ein Parser für die alte Form weiter parst; keines davon trägt noch einen Wert.

## Die Bilder empfangen, die die Person angehängt hat

Ein Tool, das mit einem Bild arbeitet — einen Kassenbon lesen, eine Pflanze bestimmen, ein Foto beschreiben —, kann um die Bilder bitten, die die Person an die Nachricht angehängt hat, die Astra gerade beantwortet. **Noch kein Astra-Release tut das:** Der Daemon schickt sie nur, wenn er mit dem Build-Feature `plugin-provider-slots` gebaut ist. Jedes andere Astra ignoriert die Bitte, und dein Tool bekommt keine Bilder.

Zwei Dinge sind nötig. Deklariere `receive_attachments` in `[permissions]` und markiere jedes Tool, das Bilder möchte; dann liest du sie in seinem Handler:

| SDK | Das Tool markieren | Die Bilder lesen |
|---|---|---|
| Rust | `#[tool(wants_attachments)]` oder `ToolDef::new(…).with_attachments(true)` | `ctx.attachments()` |
| Python | `@tool("…", wants_attachments=True)` oder `ToolDef(…, wants_attachments=True)` | `current_attachments()` |
| TypeScript | `wantsAttachments: true` in `tool({…})` oder an einem `ToolDef` | `ctx.attachments` oder `currentAttachments()` |

Jedes Bild trägt `mime_type` (`mimeType` in TypeScript), `data` — die Bytes — und `filename`, den bloßen Namen, unter dem es angehängt wurde, nie einen Ordner. Ein Tool, das nicht darum gebeten hat, liest eine leere Liste, ebenso jeder Aufruf, der keine Bilder trägt.

Astra übergibt einem Aufruf nur dann Bilder, wenn all das gilt:

- das Tool hat in seiner `ListTools`-Antwort `wants_attachments` deklariert;
- dein Plugin hält `receive_attachments`;
- der Aufruf entstand beim Beantworten einer Nachricht, die die Person in einer Unterhaltung geschickt hat — die Invocation des Aufrufs nennt diese Unterhaltung. Nie in einem Report-Wake, im KI-Schritt eines Befehls oder im Turn eines Sub-Agenten, und nie, solange Astra den Turn für einen Workshop-Befehl zurückhält, den die Person nicht freigegeben hat.

Es kommt nur an, was an **genau diese eine Nachricht** angehängt war: nie ein Bild von früher in der Unterhaltung, nie eines, das ein Tool erzeugt hat, und nie eines, das das Modell genannt hat. Höchstens **4** (`image_input_max_images` in `spec/limits.yaml`) und insgesamt 20 MiB, die neuesten werden behalten, in der Reihenfolge, in der sie angehängt wurden; ein Bild, das sich nicht lesen lässt, wird nie geschickt. Wurden einige nicht geschickt — mehr als passen, oder deinem Plugin fehlt die Gewährung —, erfährt es das **Modell** nach deinem Ergebnis; dein Tool bekommt einfach weniger oder keine.

Heute skaliert Astras Chat-Eingabe jedes angehängte Bild auf höchstens 768 Pixel und kodiert es als JPEG neu, wobei der ursprüngliche Dateiname bleibt; genau das bekommt dein Tool. Richte dich nach `mime_type`, nicht nach der Endung in `filename`.

Ein Aufruf kann bis zu 20 MiB Bilder tragen, mehr als das Standard-Empfangslimit von gRPC, 4 MiB. Die Capability-Server der drei SDKs empfangen bis zu 64 MiB (`plugin_max_message_bytes`); ein Plugin, das das Protokoll ohne SDK bedient, muss das Empfangslimit seines eigenen Servers über 4 MiB anheben.

`receive_attachments` ist **hochriskant**: Die Fotos einer Person erreichen Code, der nicht Astras ist, deshalb bekommt es eine eigene Zustimmungs-Checkbox. Bei einem lokalen Import wird es nicht abgelehnt — die Checkbox ist die Entscheidung, wie bei `speak`.

## Die Person bitten, eine Einstellung zu ändern

Ein Plugin mit einem echten Grund, eine von Astras Einstellungen geändert haben zu wollen — ein Modell, auf das seine Tools abgestimmt sind, eine Stimme, die zu ihm passt —, **bittet** darum, und die Person entscheidet auf einer Karte. Schreib Astras `settings.json` nie selbst, und leih dir dafür nie Astras eigene Sitzung: Das ändert das Astra der Person hinter ihrem Rücken, und die menschliche Prüfung bei der Veröffentlichung sucht genau danach. Deklariere `request_settings_change` und rufe `RequestSettingsChange` auf (`request_settings_change(changes, reason)` in Rust und Python, `ctx.requestSettingsChange(changes, reason)` in TypeScript). **Noch kein Astra-Release beantwortet ihn.** Ein Astra, das mit dem Build-Feature `plugin-requests` gebaut ist, nimmt Anfragen an; ein neueres Astra ohne es antwortet `REFUSED` mit dem Code `not_compiled`; bei einem älteren — heute jedem Release — scheitert der Aufruf mit `UNIMPLEMENTED`, einem Fehler, keinem Ergebnis.

Jede Änderung ist ein Einstellungspfad mit Punkten und der gewünschte Wert, als JSON — die SDKs serialisieren den Wert für dich. Erbitten lassen sich nur die Einstellungen, die der Assistent selbst ändern darf — die Stimme, das KI-Modell, die Sprache; nie der Berechtigungsmodus, ein Schlüssel oder Tool Search —, und jeder Wert wird genau so geprüft wie die eigene Änderung des Assistenten. Die Karte nennt dein Plugin, zeigt jede Einstellung, wie sie ist und wie sie würde, und deinen `reason` in deinen Worten. Alle ändern sich oder keine, und was sich ändert, ist genau das, was die Karte gezeigt hat.

**Der Aufruf dauert, bis die Person antwortet oder die Karte abläuft** — Astras Bestätigungs-Timeout, mindestens 30 Sekunden, 120, wenn die Person ihn nicht geändert hat. Die SDKs setzen keine eigene Frist darauf. Warte nie darauf auf einem Weg, der schnell antworten muss, etwa in einem Tool-Aufruf, auf den das Modell wartet.

| Ergebnis | Was es bedeutet | Was zu tun ist |
|---|---|---|
| `APPLIED` | Die Person hat es erlaubt; die Einstellungen halten jetzt, was du erbeten hast | Nichts |
| `UNCHANGED` | Sie hielten es schon. Niemand wurde gefragt | Nichts |
| `DECLINED` | Die Person hat Nein gesagt — jetzt, oder schon früher dazu, dass dein Plugin eine dieser Einstellungen ändert. Astra fragt zu so einer Einstellung erst wieder, wenn sie sich auf anderem Weg geändert hat, oder nach einem Neustart | Mach mit dem weiter, was die Person hat. **Frag nicht ungebeten noch einmal** |
| `TIMED_OUT` | Niemand hat geantwortet, bevor die Karte ablief (auch kein offenes Fenster zählt dazu) | Frag später, wenn die Person da ist |
| `REFUSED` | Nicht gefragt oder nicht angewendet: `code` sagt warum, `refused_path` nennt die Einstellung, wenn es um eine geht, und `error` ist ein `PluginError` | Lies den Code unten |

| `code` | Wann |
|---|---|
| `not_compiled` | Dieses Astra nimmt keine Anfragen an: Es wurde ohne das Feature `plugin-requests` gebaut |
| `locked` | Astra ist mit seinem Passcode gesperrt |
| `invalid` | Keine Änderungen, ein Pfad zweimal, ein Wert, der kein JSON ist, oder mehr, als eine Karte vollständig zeigen kann |
| `too_many` | Mehr als **8** Änderungen (`settings_change_max_changes` in `spec/limits.yaml`) |
| `reason_too_long` | Ein Reason länger als **140 Zeichen** (`settings_change_reason_max_chars`). Er wird vollständig gezeigt, deshalb wird er abgelehnt, nie gekürzt |
| `busy` | Eine deiner Anfragen wartet schon auf die Person: eine Karte pro Plugin zur selben Zeit |
| `rate_limited` | **Ein Schub von zwei Anfragen, danach eine alle zwei Minuten**; `error.retry_after_ms` sagt, wann wieder Platz ist |
| `not_assistant_editable` | Ein Pfad, den der Assistent nicht ändern darf |
| `invalid_value`, `unknown_choice` | Ein Wert, den die Einstellung nicht halten kann, oder eine Auswahl, die sie nicht anbietet |
| `needs_api_key`, `needs_stt_provider`, `provider_unreachable` | Die Änderung ließe Astra ohne das, was es braucht: einen Schlüssel für diesen KI-Anbieter, eine Spracherkennung, einen Anbieter, der antwortet |
| `stale` | Die Einstellungen haben sich geändert, während die Karte offen war, also ist das, was die Person erlaubt hat, nicht das, was geschrieben würde. Es wurde nichts geschrieben |
| `stopped` | Die Befugnis deines Plugins endete zuerst — es wurde gestoppt, deaktiviert oder zurückgezogen, oder das Konto schaltet Astra nicht mehr frei |
| `write_refused` | Die Einstellungen ließen sich nicht schreiben |

Die aktuellen Werte werden nie zurückgegeben: Was dein Plugin erfährt, ist das Ergebnis. Die Limits sind die des Daemons: Die SDKs exportieren `SETTINGS_CHANGE_MAX_CHANGES` und `SETTINGS_CHANGE_REASON_MAX_CHARS` und prüfen selbst keins davon. Neben der Gewährung braucht der Aufruf **ein Konto, das Astra freischaltet**; eine fehlende Gewährung oder ein Konto, das Astra nicht freischaltet, ist ein fehlgeschlagener Aufruf wie jeder Host-Aufruf, kein Ergebnis. Er ist weder hochriskant noch bei einem lokalen Import abgelehnt: Jede Anfrage ist eine Karte, die die Person beantwortet, die Zustimmung wird also jedes Mal eingeholt. Ein Astra, das älter ist als dieser Aufruf, antwortet `UNIMPLEMENTED`.

## Der Person einen Befehl anbieten

Ein Plugin, das eine nützliche Automatisierung zu geben hat — „lies mir die Nachrichten vor, wenn ich Guten Morgen sage", gebaut aus seinen eigenen Aktionen —, **bietet** sie an, und die Person entscheidet. Ein Plugin kann die Befehlsbibliothek der Person nicht selbst schreiben: `CommandService` ist für die Sitzung eines Plugins gesperrt, und vor diesem Aufruf konnte ein Plugin einen Befehl nur im Chat beschreiben und hoffen, dass die Person ihn nachbaut. Deklariere `propose_commands` und rufe `ProposeCommand` auf (`propose_command(key, command, reason)` in Rust und Python, `ctx.proposeCommand(key, command, reason)` in TypeScript). **Noch kein Astra-Release beantwortet ihn.** Ein Astra, das mit dem Build-Feature `plugin-requests` gebaut ist, nimmt Angebote an; ein neueres Astra ohne es antwortet `REFUSED` mit dem Code `not_compiled`; bei einem älteren — heute jedem Release — scheitert der Aufruf mit `UNIMPLEMENTED`, einem Fehler, keinem Ergebnis.

Der Befehl ist **ein portabler Befehl** — das, was `commands[]` einer `.astra`-Datei enthält. Am einfachsten baust du ihn in Astra, exportierst ihn auf der Befehlsseite und lieferst die Datei mit deinem Plugin aus; jedes SDK hat eine Hilfsfunktion, die eine solche Datei in ihre Befehle zerlegt (`commands_from_astra_file` in Rust und Python, `commandsFromAstraFile` in TypeScript), jeden ohne die Felder, die zu einer einzelnen Installation gehören (`id`, `enabled`, der Ordner, die Herkunft). Der Daemon liest den Befehl mit dem eigenen Leser des Workshops — striktes JSON, nur bekannte Aktions- und Auslösertypen, diese lokalen Felder entfernt, sodass ein Plugin weder fälschen kann, woher ein Befehl stammt, noch ihn einschalten —, und er darf die eingebauten Aktionen und Auslöser von Astra und die **eigenen** deines Plugins verwenden, nie die eines anderen Plugins (`foreign_plugin`). Zu den eingebauten gehören ein Shell-Befehl, Tastendrücke und Dateioperationen: Das Blatt zeigt jeden Schritt mit dem, was er tun darf, und dem stimmt die Person zu.

`key` ist der eigene Name deines Plugins für den Befehl: 1 bis 64 Zeichen aus `a-z`, `A-Z`, `0-9`, `.`, `_` und `-`. Derselbe Schlüssel noch einmal angeboten ist derselbe Befehl, an Ort und Stelle aktualisiert — seine ID und sein Ordner bleiben —, sobald die Person wieder zustimmt; genau den Befehl noch einmal anzubieten, der unter dem Schlüssel schon behalten ist, fragt niemanden (`UNCHANGED`).

Was Astra sich merkt, ist enger, als es aussieht; biete also nicht einfach jeden Befehl bei jedem Start an:

- ein `DECLINED` wird nur bis zum Neustart von Astra gemerkt — danach ist dasselbe Angebot wieder eine Karte;
- ein Befehl, den die Person gelöscht hat, steht nicht mehr unter seinem Schlüssel, also ist ein erneutes Angebot ein neues — wieder eine Karte;
- ein Befehl, der beim Deinstallieren deines Plugins ausgeschaltet wurde, bleibt nach einer Neuinstallation aus, und dasselbe Angebot antwortet `UNCHANGED`;
- `UNCHANGED` vergleicht dein Angebot mit dem, was unter dem Schlüssel angeboten und behalten wurde, ist also auch die Antwort, nachdem die Person den behaltenen Befehl bearbeitet hat.

Halte `SAVED` und `DECLINED` pro Schlüssel im eigenen Zustand deines Plugins fest und biete beim Start nur die Schlüssel an, für die du keine Antwort hast — und einen Befehl, den du geändert hast.

Die Person sieht eine Karte, die dein Plugin und den Befehl nennt, mit deinem `reason` in deinen Worten, und zwei Möglichkeiten: Prüfen und Ablehnen. **Behalten wird der Befehl nur über das Workshop-Blatt von Astra** — jeder Auslöser mit seinem vollen Wert, jeder Schritt mit dem, was er tun darf, und ein Schalter zum Aktivieren —, nie über ein bloßes Erlauben, und behalten wird genau das, was das Blatt gezeigt hat. Ein behaltener Befehl trägt das Zeichen deines Plugins; wird dein Plugin deinstalliert, werden seine Befehle ausgeschaltet.

**Der Aufruf dauert, bis die Person antwortet oder die Karte abläuft** — Astras Bestätigungs-Timeout, mindestens 30 Sekunden, 120, wenn die Person ihn nicht geändert hat. Die SDKs setzen keine eigene Frist darauf. Warte nie darauf auf einem Weg, der schnell antworten muss, und **biete einen Befehl nach dem anderen an**: Ein zweites Angebot, während eines von dir wartet, wird als `busy` abgelehnt, selbst eines, das `UNCHANGED` wäre.

| Ergebnis | Was es bedeutet | Was zu tun ist |
|---|---|---|
| `SAVED` | Die Person hat ihn behalten; `enabled` sagt, ob der Befehl nach dem Behalten eingeschaltet ist (Astra kann ihn ausgeschaltet behalten) | Halte es fest |
| `UNCHANGED` | Was unter diesem Schlüssel behalten ist, stammt aus genau diesem Angebot — auch nachdem die Person es bearbeitet hat. Niemand wurde gefragt | Nichts |
| `DECLINED` | Die Person hat Nein gesagt — jetzt, oder schon früher zu genau diesem Befehl (bis Astra neu startet) | Halte es fest. **Biete ihn nicht ungebeten noch einmal an** |
| `TIMED_OUT` | Niemand hat geantwortet, bevor die Karte ablief (auch kein offenes Fenster zählt dazu) | Biete ihn später an, wenn die Person da ist |
| `REFUSED` | Nicht gefragt oder nicht behalten: `code` sagt warum, und `error` ist ein `PluginError` | Lies den Code unten |

| `code` | Wann |
|---|---|
| `not_compiled` | Dieses Astra nimmt keine Angebote an: Es wurde ohne das Feature `plugin-requests` gebaut |
| `locked` | Astra ist mit seinem Passcode gesperrt |
| `invalid_key` | Ein Schlüssel, der nicht aus 1 bis 64 Zeichen aus `a-z`, `A-Z`, `0-9`, `.`, `_` und `-` besteht |
| `reason_too_long` | Eine Begründung länger als **140 Zeichen** (`propose_command_reason_max_chars` in `spec/limits.yaml`). Sie wird ganz gezeigt, deshalb wird sie abgelehnt, nie gekürzt |
| `too_large` | Mehr als **1 MiB** JSON (`propose_command_max_bytes`), die eigene Grenze eines Workshop-Befehls |
| `invalid_command` | Kein Befehl, den der Leser des Workshops annimmt; `error.message` beginnt meist mit dessen eigenem Code — `E_COMMAND_FORMAT`, `E_COMMAND_UNKNOWN_ACTION`, … —, aber nicht, wenn die Karte selbst nicht gezeigt werden kann (der Name des Befehls und deine Begründung sind zu lang für sie) |
| `foreign_plugin` | Der Befehl verwendet eine Aktion oder einen Auslöser eines anderen Plugins |
| `busy` | Eines deiner Angebote wartet schon auf die Person: eine Karte pro Plugin zur selben Zeit |
| `rate_limited` | **Ein Schub von zwei Angeboten, danach eines alle zwei Minuten**; `error.retry_after_ms` sagt, wann wieder Platz ist. Ein Angebot, das niemanden fragt (`UNCHANGED`, ein gemerktes `DECLINED`), verbraucht nichts |
| `stopped` | Die Befugnis deines Plugins endete zuerst — es wurde gestoppt, deaktiviert oder zurückgezogen, oder das Konto schaltet Astra nicht mehr frei |
| `stale` | Der Befehl, den es aktualisiert, hat sich geändert oder ist verschwunden, während die Karte offen war, sodass das, was die Person gesehen hat, nicht das ist, was geschrieben würde. Nichts wurde geschrieben |
| `write_refused` | Der Befehl ließ sich nicht speichern |

Die Grenzen gehören dem Daemon: Die SDKs exportieren `PROPOSE_COMMAND_MAX_BYTES` und `PROPOSE_COMMAND_REASON_MAX_CHARS` und prüfen keine davon selbst. Neben der Berechtigung braucht der Aufruf **ein Konto, das Astra freischaltet**; eine fehlende Berechtigung oder ein Konto, das Astra nicht freischaltet, ist ein fehlgeschlagener Aufruf wie jeder Host-Aufruf, kein Ergebnis. `propose_commands` ist **hochriskant**: Ein behaltener Befehl läuft später, auf seine eigenen Auslöser hin, als eigener Befehl der Person — seine Schritte, eingebaute wie ein Shell-Befehl eingeschlossen, laufen, ohne noch einmal zu fragen —, deshalb bekommt es eine eigene Zustimmungs-Checkbox. Bei einem lokalen Import wird es nicht verweigert: Das Blatt ist die Entscheidung, jedes Mal. Ein Astra älter als dieser Aufruf antwortet `UNIMPLEMENTED`.

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

Permissions sind nach Risiko gruppiert. Die acht hochriskanten bekommen
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
