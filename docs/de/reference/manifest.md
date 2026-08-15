> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/reference/manifest.md) maßgeblich. Die englische Seite ist GENERIERT von `tools/docgen/manifest.py` — diese Übersetzung ist eine von Hand gepflegte Momentaufnahme davon, keine weitere generierte Kopie.

# `plugin.toml`-Referenz

Jeder Abschnitt, jeder Schlüssel, und alles, was einen ablehnt.
Abgeleitet aus
[`astra-plugin-manifest`](../../../astra-plugin-cli/vendor/astra-plugin-manifest/src/manifest.rs)
— der Crate, mit der der Daemon dein Manifest parst, in dieses
Repository gevendort und bytegleich mit Astras Kopie gehalten von
`tools/check-manifest-crate.sh`. Es gibt keine zweite Definition eines
Manifests, die dieser Seite widersprechen könnte.

Vollständiges Plugin-Manifest, geparst aus `plugin.toml`.

Absichtlich **nicht** `deny_unknown_fields`: Abschnitte kommen über
Releases hinweg hinzu — `[permissions]` war der letzte — und ein
älterer Daemon muss einen ihm unbekannten Abschnitt überspringen können,
statt das Plugin abzulehnen. `[capabilities]` ist die Ausnahme, und
[`Capabilities`] erklärt warum.

## Abschnitte

| Abschnitt | Erforderlich | Was er deklariert |
|---|---|---|
| [`[plugin]`](#plugin) | **ja** | Plugin-Identität und Metadaten. |
| [`[entry]`](#entry) | **ja** | Wie der Plugin-Prozess gestartet wird. |
| [`[capabilities]`](#capabilities) | nein | Was das Plugin **implementiert**, Daemon→Plugin. |
| [`[permissions]`](#permissions) | nein | Was das Plugin zu **rufen** anfragt, Plugin→Daemon — und es ist eine *Anfrage*. |
| [`[config]`](#config) | nein | JSON Schema für die Plugin-Konfiguration (generiert die Settings-UI automatisch). |
| [`[dependencies]`](#dependencies) | nein | Eine Tabelle von Strings, ohne eigenes Schema. |
| [`[platform]`](#platform) | nein | Plattform-Anforderungen — `[platform]` in `plugin.toml`. |
| [`[build]`](#build) | nein | Build-Metadaten, die `astra-plugin build` hinzufügt. |
| [`[ui]`](#ui) | nein | UI-Contribution-Definitionen, in plugin.toml deklariert. |

Ein Abschnitt, den dieses Astra nicht kennt, wird **behalten, nicht
abgelehnt** — Abschnitte kommen über Releases hinweg hinzu, und ein
älterer Daemon muss einen überspringen können. `[capabilities]` ist die
einzige Ausnahme, und der Grund steht unten.

## `[plugin]`

Plugin-Identität und Metadaten.

| Schlüssel | Typ | Erforderlich | Default | Was es ist |
|---|---|---|---|---|
| `id` [†](#was-abgelehnt-wird) | string | **ja** | — | — |
| `name` [†](#was-abgelehnt-wird) | string | **ja** | — | — |
| `version` [†](#was-abgelehnt-wird) | string | **ja** | — | — |
| `description` | string | nein | `""` | — |
| `author` | string | nein | `""` | — |
| `license` | string | nein | `""` | — |
| `homepage` | string | nein | `""` | — |
| `min_astra_version` [†](#was-abgelehnt-wird) | string | nein | `""` | Das älteste Astra, mit dem dieses Plugin funktioniert, als Semver-Version (`"0.9.0"`). |
| `call_timeout_secs` | integer | nein | abwesend | Wie lange der Daemon auf `CallTool` / `ExecuteAction` wartet, bevor er aufgibt, in Sekunden. |

† hat eine Regel, die das Manifest pauschal ablehnt — siehe
[was abgelehnt wird](#was-abgelehnt-wird) für die Bedingung und die
Nachricht.

**`plugin.min_astra_version`.** Das älteste Astra, mit dem dieses Plugin
funktioniert, als Semver-Version (`"0.9.0"`). Leer = keine Anforderung.

Ihre *Syntax* wird überall von [`PluginManifest::validate`] geprüft. Ihr
*Wert* wird nur in einem Build verglichen, der eines kennt — siehe
[`crate::host_astra_version`]. Sie existierte ein ganzes Release lang
als Feld, das geparst und nie gelesen wurde, sodass ein Plugin, das ein
Daemon-Feature brauchte, das der Host nicht installiert hatte, sauber
installierte und dann bei genau dem einen Aufruf scheiterte, der es
brauchte — was der Nutzer als „dieses Plugin ist kaputt" liest.

**`plugin.call_timeout_secs`.** Wie lange der Daemon auf `CallTool` /
`ExecuteAction` wartet, bevor er aufgibt, in Sekunden. `None` → das
eigene `PLUGIN_CALL_TIMEOUT` des Daemons.

Ein Plugin, das einen langlaufenden Agenten vertritt, muss das
deklarieren: der Default des Daemons liegt absichtlich unter „für
immer", und ein Plugin, dessen eigenes Arbeitsbudget das überschreitet,
würde sein Ergebnis weggeworfen bekommen, während sein Subprozess
weiterläuft (`coding-agents` liefert einen Default von 180 s). Pro
Plugin, genauso wie `McpServerConfig::timeout_secs` pro Server gilt.

## `[entry]`

Wie der Plugin-Prozess gestartet wird.

| Schlüssel | Typ | Erforderlich | Default | Was es ist |
|---|---|---|---|---|
| `command` [†](#was-abgelehnt-wird) | string | **ja** | — | — |
| `args` | Array von Strings | nein | leer | — |
| `cwd` | string | nein | `.` | — |
| `runtimes` | Array von Strings | nein | leer | — |

† hat eine Regel, die das Manifest pauschal ablehnt — siehe
[was abgelehnt wird](#was-abgelehnt-wird) für die Bedingung und die
Nachricht.

## `[capabilities]`

Was das Plugin **implementiert**, Daemon→Plugin.

**Ein unbekannter Schlüssel hier lässt das ganze Manifest scheitern.**
`Capabilities` ist `#[serde(deny_unknown_fields)]`, allein unter den
Abschnitten: es besteht ausschließlich aus Opt-in-Booleans, ein
Tippfehler würde sonst genau wie `false` gelesen, und das Plugin würde
installieren, ohne etwas deklariert zu haben. Das ist nicht hypothetisch
— drei mitgelieferte Beispiele deklarierten `ui_panels`, einen Namen,
den kein Daemon je hatte, und das einzige Symptom war, dass
`astra-plugin check` „No capabilities enabled" ausgab.

Jeder Schlüssel ist ein Boolean und ist standardmäßig `false`. Die
rechte Spalte ist die Verbindung zu
[`spec/hooks.yaml`](../../../spec/hooks.yaml): die Hooks, die dein
Plugin bedienen muss, damit die Capability überhaupt funktioniert.
`optional`-Hooks sind hier ausgelassen; [`parity.md`](./parity.md) hat
sie alle.

| Schlüssel | Hooks, zu deren Implementierung er verpflichtet |
|---|---|
| `tools` | `ListTools`, `CallTool` |
| `tts` | `TtsSynthesize`, `TtsListVoices` |
| `stt` | `SttProcess`, `SttGetLanguages` |
| `ai_provider` | `AiComplete` |
| `client` | `SendChatMessage` |
| `actions` | `ExecuteAction`, `GetPluginActionTypes` |
| `triggers` | `GetPluginTriggerTypes`, `FireTrigger` |
| `ui_contributions` | `GetUiContributions` |
| `event_handlers` | `SubscribeEvents` |
| `dom_access` | keine |

**Namen, die nie echt waren:**

- `ui_panels` → `ui_contributions`

## `[permissions]`

Was das Plugin zu **rufen** anfragt, Plugin→Daemon — und es ist eine
*Anfrage*.

Abwesend bedeutet kein Host-RPC über die immer erlaubte Bootstrap-Menge
hinaus (§5.6). Die Menge, die ein Plugin tatsächlich hält, wird vom
Daemon aus seiner Provenienz aufgelöst und für ein Plugin mit
Trust-Record nie von hier gelesen: ein Manifest liegt im eigenen
Verzeichnis des Plugins, das das Plugin schreiben kann.

Jeder Schlüssel ist eine Permission-ID, und jeder Wert ist eine Tabelle.

Eine ID, die dieses Astra nicht kennt, wird behalten und ist wirkungslos:
Vorwärtskompatibilität, und `permissions_hash` wird über diese Bytes von
drei Implementierungen berechnet, ein Leser, der einen unbekannten
Schlüssel fallenließe, wäre also mit den anderen beiden uneins darüber,
was signiert wurde.

| ID | Sperrt | Eigene Zustimmungs-Checkbox | Bei lokalem Import verweigert | Was sie gewährt |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | nein | nein | Führt die gespeicherten Automatisierungen des Nutzers aus. |
| `subscribe_events` | `SubscribeEvents` | nein | nein | Empfängt Daemon-Events. |
| `set_variable` | `SetVariable` | nein | nein | Schreibt in den Variablenkontext des Daemons (dem aufrufenden Plugin zugeordnet). |
| `send_chat_message` | `SendChatMessage` | **ja** | **ja** | Löst einen AI-Turn aus. |
| `push_to_ui` | `PushToUi` | **ja** | nein | Pusht ein Event ins Astra-Fenster. |
| `set_theme_contribution` | `SetThemeContribution` | **ja** | **ja** | Gestaltet die gesamte App um. |
| `dom_access` | — | **ja** | **ja** | Führt den eigenen Code des Plugins im Astra-Fenster aus, mit Zugriff auf die Unterhaltungen des Nutzers und die Oberfläche jedes anderen Plugins. |
| `client` | — | **ja** | **ja** | Agiert als Client-Frontend (eigene Chat-Oberfläche, eigene Session). |

*Sperrt* ist das Host-RPC, das der Daemon ohne die Permission ablehnt,
aus [`spec/hooks.yaml`](../../../spec/hooks.yaml); Paritätsregel R6
prüft diese Spalte gegen die eigene `HOST_RPC_PERMISSIONS` des Daemons,
die Tabelle, die `require_permission` liest. Eine leere Zelle ist eine
**Surface**-Permission, die kein RPC sperrt: `dom_access` entscheidet,
wie eine UI-Contribution gerendert wird, und `client` ist eine
Capability-Obergrenze.

*Bei lokalem Import verweigert* ist die Obergrenze für eine
`.astraplugin`-Datei, die der Nutzer von Hand importiert statt aus dem
Store installiert hat: diese IDs werden pauschal fallengelassen, nicht
nur mit Warnung versehen. Ein mit eingeschaltetem Entwicklermodus
geladenes Quellverzeichnis ist absichtlich nicht gekappt — es ist die
Entwicklungsschleife für UI-Plugins.

### Der Wert eines Permission-Schlüssels

| Schlüssel | Typ | Erforderlich | Default | Was es ist |
|---|---|---|---|---|
| `reason` | string | nein | `""` | Die eigenen Worte des Autors, *untergeordnet* zum app-eigenen Label gerendert (§4.3: in Anführungszeichen, Klartext, ≤140 Zeichen, stets mit „The author says:" vorangestellt). |
| `types` | Array von Strings | nein | leer | `subscribe_events.types` — die angefragten Event-Typen. |
| `scopes` | Array von Strings | nein | leer | `set_variable.scopes` — `"plugin"` / `"session"` / `"persistent"`. |

**`<permission>.reason`.** Die eigenen Worte des Autors, *untergeordnet*
zum app-eigenen Label gerendert (§4.3: in Anführungszeichen, Klartext,
≤140 Zeichen, stets mit „The author says:" vorangestellt). Es ist nie
das Label selbst — Formulierungs-Fixes werden mit Astra ausgeliefert und
dürfen nicht durch ein Listing gestaltet werden können.

**`<permission>.types`.** `subscribe_events.types` — die angefragten
Event-Typen.

**Eine Allowlist, und eine leere erlaubt nichts.** Siehe
[`Permissions::event_types`].

**`<permission>.scopes`.** `set_variable.scopes` — `"plugin"` /
`"session"` / `"persistent"`. Reserviert; der Daemon ordnet heute jeden
Plugin-Schreibvorgang nach Plugin-ID zu, das schränkt also noch nichts
ein und wird geparst, damit ein Manifest, das es deklariert, überall
gleich hasht.

**`fire_trigger`.** `PluginHostService.FireTrigger` — führt die
gespeicherten Automatisierungen des Nutzers aus.

**`subscribe_events`.** `PluginHostService.SubscribeEvents` — empfängt
Daemon-Events.

Trägt ein Argument: [`PermissionRequest::types`] ist die **Allowlist**
der Event-Typen, und sie wird vom Daemon durchgesetzt, nicht vom Filter,
den das Plugin sendet. Ohne das erhielt jeder Abonnent jedes Event —
einschließlich `speech_recognized`, das die Transkripte des Nutzers
trägt.

**`set_variable`.** `PluginHostService.SetVariable` — schreibt in den
Variablenkontext des Daemons (dem aufrufenden Plugin zugeordnet).

**`send_chat_message`.** `PluginHostService.SendChatMessage` — löst
einen AI-Turn aus. **Hohes Risiko.**

**`push_to_ui`.** `PluginHostService.PushToUi` — pusht ein Event ins
Astra-Fenster. **Hohes Risiko.**

**`set_theme_contribution`.** `PluginHostService.SetThemeContribution`
— gestaltet die gesamte App um. **Hohes Risiko.**

**`dom_access`.** Führt den eigenen Code des Plugins im Astra-Fenster
aus, mit Zugriff auf die Unterhaltungen des Nutzers und die Oberfläche
jedes anderen Plugins. **Hohes Risiko, und die eine, der §4.3 einen
zweiten Bildschirm gibt.**

**`client`.** Agiert als Client-Frontend (eigene Chat-Oberfläche,
eigene Session). **Hohes Risiko.**

## `[config]`

JSON Schema für die Plugin-Konfiguration (generiert die Settings-UI
automatisch).

| Schlüssel | Typ | Erforderlich | Default | Was es ist |
|---|---|---|---|---|
| `schema` | string | **ja** | — | JSON Schema als String. |

## `[dependencies]`

Eine freie Tabelle aus `name = "Versionsanforderung"`. Beide Hälften
sind Strings, und die Crate liest sie als solche —
`HashMap<String, String>`, kein Schema, keine Auflösung, und nichts
installiert daraus irgendetwas. `astra-plugin check` listet auf, was
deklariert ist, und warnt, wenn eine Anforderung leer ist; das ist die
gesamte Wirkung.

## `[platform]`

| Schlüssel | Typ | Erforderlich | Default | Was es ist |
|---|---|---|---|---|
| `os` | Array von Strings | nein | leer | — |
| `arch` | Array von Strings | nein | leer | — |

**`KNOWN_OS_VALUES`** — `linux`, `windows`, `macos`

Die `os`-Werte, die `[platform] os = [...]` benennen darf, im
Vokabular, das [`current_platform`] spricht.

Weiter als die Menge, für die Astra einen Daemon ausliefert: `os =
["macos"]` zu deklarieren ist eine Aussage über das Plugin, keine
Behauptung, dass ein Host existiert, und ein Validator, der das ablehnte,
würde ein korrektes Manifest ablehnen.

**`KNOWN_ARCH_VALUES`** — `x86_64`, `aarch64`

Die `arch`-Werte, die `[platform] arch = [...]` benennen darf.

**`RESERVED_PLATFORM_KEYS`** — `linux-x64`, `windows-x64`,
`linux-arm64`, `windows-arm64`, `macos-x64`, `macos-arm64`, `noarch`

Jeder Artefakt-Schlüssel, den das Registry-Schema reserviert, in der
Reihenfolge, in der ein Generator sie ausgeben sollte.

Nur [`platform_key_for`] entscheidet, welche davon ein *laufender
Daemon* akzeptiert, und er akzeptiert zwei. Der Rest ist reserviert,
damit sich das Index-Format nie ändern muss, falls Astra diese Hosts
später ausliefert, und damit ein Registry-Validator einen Tippfehler
(`mac-arm64`, `linux-amd64`) ablehnen kann, statt einen Schlüssel zu
schreiben, den kein Daemon je nachschlägt.

**Reserviert bedeutet nicht unterstützt.** Astras Release-Workflow baut
weder einen macOS- noch einen arm64-Daemon, sodass ein unter
`macos-x64`, `macos-arm64`, `linux-arm64` oder `windows-arm64`
veröffentlichtes Bundle keinen Host hat, auf dem es läuft. Ein
Generator, der eines davon ausgibt, veröffentlicht eine Datei, die
niemand installieren kann.

`noarch` ist der Fall interpretierter Sprachen (TypeScript, Python). Es
ist hier für Validatoren reserviert, aber der Daemon schlägt es
**nicht** nach: gemäß der Bundle-Spec schreibt der Index dieselbe URL
und denselben Digest unter jeden *unterstützten* Plattform-Schlüssel,
sodass ein `noarch`-Bundle wie jedes andere unter `linux-x64` /
`windows-x64` gefunden wird.

Nichts im Laufzeitpfad des Daemons liest diese Liste — ihre Konsumenten
sind der Index-Generator im Registry-Repository, das `check` der CLI,
und der untenstehende Test, der die beiden Hälften ehrlich hält. Sie
liegt neben der Funktion, die entscheidet, welcher dieser Schlüssel
real ist, weil das der einzige Ort ist, an dem die beiden Tatsachen
zusammen gelesen werden können.

## `[build]`

Build-Metadaten, die `astra-plugin build` hinzufügt.

| Schlüssel | Typ | Erforderlich | Default | Was es ist |
|---|---|---|---|---|
| `bundled` | boolean | nein | `false` | — |
| `language` | string | nein | `""` | — |
| `python_version` | string | nein | `""` | — |
| `requirements_lock` | string | nein | `""` | — |

## `[ui]`

UI-Contribution-Definitionen, in plugin.toml deklariert.

| Schlüssel | Typ | Erforderlich | Default | Was es ist |
|---|---|---|---|---|
| `contributions` | Array von Tabellen | nein | leer | — |

### `[[ui.contributions]]`

Eine statische UI-Contribution-Definition aus dem Manifest.

| Schlüssel | Typ | Erforderlich | Default | Was es ist |
|---|---|---|---|---|
| `id` | string | **ja** | — | — |
| `slot` | string | nein | `""` | — |
| `css_target` | string | nein | `""` | — |
| `position` | string | nein | `""` | — |
| `url` | string | nein | `""` | — |
| `label` | string | nein | `""` | — |
| `icon_svg` | string | nein | `""` | — |
| `width` | integer | nein | `0` | — |
| `height` | integer | nein | `0` | — |
| `transparent` | boolean | nein | `false` | — |
| `pointer_events` | boolean | nein | `true` | — |
| `z_index` | integer | nein | `0` | — |
| `props` | Tabelle von Strings | nein | leer | — |

## Was abgelehnt wird

Jede Ablehnung, die `PluginManifest::validate` erzeugen kann, mit der
Bedingung, die sie auslöst. Die Bedingungen sind die Rust-Ausdrücke
selbst: `plugin.id` wird zu einer Pfadkomponente —
`<plugins_dir>/<id>/`, erstellt und später per `remove_dir_all`
gelöscht — die Charset-Regel zu paraphrasieren ist also nichts, was
diese Seite tun will.

| Das Manifest wird abgelehnt, wenn | Die Nachricht |
|---|---|
| `self.plugin.id.is_empty()` | plugin.id is required |
| `self.plugin.name.is_empty()` | plugin.name is required |
| `self.plugin.version.is_empty()` | plugin.version is required |
| `self.entry.command.is_empty()` | entry.command is required |
| `!self.plugin.id.chars().all(\|c\| c.is_ascii_lowercase() \|\| c.is_ascii_digit() \|\| c == '-')` | plugin.id must be lowercase alphanumeric with hyphens: '{}' |
| `self.plugin.id.ends_with('.') \|\| self.plugin.id.ends_with(' ')` | plugin.id must not end with a dot or space: '{}' |
| `is_reserved_device_name(&self.plugin.id)` | plugin.id '{}' is a reserved Windows device name |
| `not (running >= required)` | Plugin '{}' requires Astra {} or newer, but this is Astra {}. Update Astra, or install a build of the plugin that supports {}. |
| ``semver::Version::parse(required)` returns Err` | plugin.min_astra_version '{}' is not a semver version (expected e.g. "0.9.0") |

`min_astra_version` ist die eine Regel mit zwei Hälften. Ihre **Syntax**
wird überall geprüft, auch in `astra-plugin check`: ein Wert, der keine
Semver-Version ist, ist eine deklarierte Einschränkung, die nichts
einschränkt. Ihr **Wert** wird nur in einem Build verglichen, der selbst
ein Astra ist — ein Tool, das sich weigert, ein Plugin anzusehen, weil
es einen neueren Daemon anvisiert als das Tool selbst, wäre Unsinn.
</content>
