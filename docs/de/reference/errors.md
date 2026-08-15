> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/reference/errors.md) maßgeblich. Die englische Seite ist GENERIERT von `tools/docgen/errors.py` — diese Übersetzung ist eine von Hand gepflegte Momentaufnahme davon, keine weitere generierte Kopie.

# Fehler-Referenz

Eine Taxonomie, vier Implementierungen, und diese Seite ist der
Zusammenschluss. Die acht Pro-Aufruf-Codes sind im Proto und in jedem
der drei SDKs ausgeschrieben, und nichts verknüpft sie zur Kompilierzeit
über Sprachen hinweg — sie werden also hier verglichen, und eine
Diskrepanz lässt den Build fehlschlagen, statt eine Seite zu werden, die
die Version der Wahrheit eines SDK dokumentiert.

## Die zwei Kanäle

**Im Band — der Fehler, den der Aufrufer liest.** Ein gescheitertes
Tool hat ein Ergebnis erzeugt. `NOT_CONFIGURED: OpenAI API key is not
set` ist das, was das Modell sehen muss, um dem Nutzer zu sagen, was zu
tun ist, und was die UI in einen Link zu genau diesem Settings-Feld
verwandelt. Es reist innerhalb der Antwortnachricht.

**Transport — gRPC `Status`.** Reserviert für den Fall, dass der Aufruf
den Handler nie erreicht: kein solcher Hook, nicht authentifiziert,
Verbindung weg. `UNIMPLEMENTED` bedeutet *dieses Plugin hat diesen Hook
nicht*, was eine Aussage über die Form des Plugins ist und nicht über
diesen Aufruf — der Daemon liest es als „Hook fehlt" und macht weiter.
Einen Transportfehler für einen Pro-Aufruf-Fehlschlag zurückzugeben wirft
diese Unterscheidung weg und verliert bei einem Tool die Antwort des
Modells.

Die Transport-Spalte unten ist die feste Abbildung, verwendet von den
Hooks, deren Antwortnachricht kein Inband-Fehlerfeld hat (TTS, STT, AI).
Es ist eine Bijektion: ein Plugin, das einen gRPC-Fehlschlag
weiterleitet, bekommt denselben Code zurück, den es eingesetzt hat.

## Die acht Pro-Aufruf-Codes

| Code | Proto | Rust | Python | TypeScript | Transport |
|---|---|---|---|---|---|
| `BAD_ARGUMENTS` | `PLUGIN_ERROR_BAD_ARGUMENTS` = 4 | `ToolError::BadArguments` | `BadArguments` | `BadArguments` | `INVALID_ARGUMENT` |
| `NOT_FOUND` | `PLUGIN_ERROR_NOT_FOUND` = 5 | `ToolError::NotFound` | `NotFound` | `NotFound` | `NOT_FOUND` |
| `NOT_CONFIGURED` | `PLUGIN_ERROR_NOT_CONFIGURED` = 6 | `ToolError::NotConfigured` | `NotConfigured` | `NotConfigured` | `FAILED_PRECONDITION` |
| `UNAUTHORIZED` | `PLUGIN_ERROR_UNAUTHORIZED` = 7 | `ToolError::Unauthorized` | `Unauthorized` | `Unauthorized` | `PERMISSION_DENIED` |
| `RATE_LIMITED` | `PLUGIN_ERROR_RATE_LIMITED` = 8 | `ToolError::RateLimited` | `RateLimited` | `RateLimited` | `RESOURCE_EXHAUSTED` |
| `UNAVAILABLE` | `PLUGIN_ERROR_UNAVAILABLE` = 9 | `ToolError::Unavailable` | `Unavailable` | `Unavailable` | `UNAVAILABLE` |
| `TIMEOUT` | `PLUGIN_ERROR_TIMEOUT` = 10 | `ToolError::Timeout` | `Timeout` | `Timeout` | `DEADLINE_EXCEEDED` |
| `INTERNAL` | `PLUGIN_ERROR_INTERNAL` = 11 | `ToolError::Internal` | `InternalError` | `InternalError` | `INTERNAL` |

### `ToolError::Documented` — eine Variante ohne eigenen Code

Jeder der obigen, plus eine Seite, die *diesen* Fehlschlag dokumentiert
— die eigenen Docs des Plugins, oder das „so bekommst du einen API-Key"
des Upstream-Providers. Gebaut mit [`ToolError::with_doc_url`]; die UI
rendert es als Link neben der Nachricht.

### Was jeder bedeutet

**`BAD_ARGUMENTS`.** Die Argumente parsten nicht, oder verletzen den
eigenen Vertrag des Tools. Der Aufrufer kann mit anderen Argumenten
erneut versuchen; dieselben erneut zu versuchen kann nicht helfen.
`message` nennt das betroffene Feld.

**`NOT_FOUND`.** Das Angesprochene existiert nicht (ein unbekannter
Tool-Name, eine ID, für die der eigene Speicher des Plugins keine Zeile
hat).

**`NOT_CONFIGURED`.** Das Plugin braucht eine Konfiguration, die der
Nutzer nicht geliefert hat. DER eine Code, der `config_field` setzen
muss: er ist das, was „dieses Tool braucht einen API-Key" in einen Link
verwandelt, der genau das Settings-Feld öffnet.

**`UNAUTHORIZED`.** Die eigenen Zugangsdaten des Plugins wurden von
dem, womit es spricht, abgelehnt, oder der Aufrufer darf das nicht
aufrufen. Anders als NOT_CONFIGURED: ein Wert IST vorhanden, er wird
schlicht nicht akzeptiert.

**`RATE_LIMITED`.** Ein Rate-Limit — das eigene des Plugins, oder das
eines Upstream-Dienstes. Setzt `retry_after_ms`, wenn das Limit sagt,
wann.

**`UNAVAILABLE`.** Eine Abhängigkeit, die das Plugin braucht, ist down
oder unerreichbar. Als vorübergehend angenommen; ein späterer
identischer Aufruf könnte gelingen.

**`TIMEOUT`.** Das Plugin hat aufgegeben, auf etwas zu warten. Anders
als UNAVAILABLE nur darin, dass dem Plugin die Zeit ausging, nicht dem
Aufrufer.

**`INTERNAL`.** Ein unerwarteter Fehlschlag innerhalb des Plugins — ein
Bug, ein vom SDK aufgefangener Panic. Der Auffangcode, den ein SDK
verwendet, wenn es nichts Besseres hat.

## Registrierungs-Ablehnungen

Dasselbe Enum trägt die Codes, mit denen ein Daemon auf `Register`
antwortet. Ein Plugin erzeugt nie einen davon; es empfängt einen und
beendet sich dann.

| Code | Nummer | Was es bedeutet |
|---|---|---|
| `PLUGIN_ERROR_PROTOCOL_TOO_OLD` | 1 | Das Plugin spricht ein Wire-Protokoll, das älter ist als die Untergrenze dieses Daemons (`PluginRegisterResponse.min_supported_protocol`). Der Fix ist immer „gegen ein neueres SDK neu bauen"; `hint` sagt das, mit den Zahlen. |
| `PLUGIN_ERROR_AUTH` | 2 | Das Spawn-Zeit-`auth_token` fehlte oder stimmte nicht überein. |
| `PLUGIN_ERROR_UNKNOWN_PLUGIN` | 3 | Der Daemon kennt keine solche Plugin-ID, oder sie ist nicht in einem registrierbaren Zustand. |

`PLUGIN_ERROR_UNSPECIFIED = 0` ist der Nullwert von proto3 und bedeutet,
der Absender hat nichts gesetzt.

## Die Felder, die ein Fehler trägt

| Feld | Für | Was es ist |
|---|---|---|
| `code` | jeden Code | Einer der obigen Codes. |
| `message` | jeden Code | Was schiefging. |
| `hint` | jeden Code | Was zu TUN ist. |
| `config_field` | `NOT_CONFIGURED` | Deep-Link-Ziel: das Plugin-Config-Feld, das der Nutzer ausfüllen muss, genau so benannt, wie es im Config-Schema des Plugins erscheint (`api_key`, `account.token`). |
| `retry_after_ms` | `RATE_LIMITED` | Wie lange vor einem erneuten Versuch zu warten ist, in Millisekunden. |
| `doc_url` | jeden Code | Eine Seite, die GENAU DIESEN Fehlschlag dokumentiert — die eigenen Docs des Plugins, das „so bekommst du einen API-Key" eines Upstream-Providers. |

Beide Hälften werden immer gesendet. Die strukturierte Nachricht ist
eine Ergänzung, kein Ersatz: ein gegen ein älteres Protokoll gebautes
Plugin sendet kein strukturiertes Detail, und eines, das gegen dieses
Protokoll gebaut ist und mit einem älteren Daemon spricht, wird es vom
Parser des Empfängers fallengelassen. In beiden Richtungen überlebt der
menschenlesbare String, beide Paarungen funktionieren also weiter —
weshalb dem String auch der Code vorangestellt wird
(`NOT_CONFIGURED: …`): dieses Präfix ist das, was der AI-Schleife sagt,
mit erneuten Versuchen aufzuhören.

## Fehlende Hooks sind keine Fehler

„This plugin does not have that hook."

Jeder Hook mit Default, der keinen sinnvollen Fallback hat, gibt das
zurück, und `runner.rs` macht daraus `Status::unimplemented` — das Wort
des Protokolls für *fehlend*, das der `optional_hook`-Helfer des Daemons
so liest (`astra-daemon/src/plugins/manager.rs`). Es ist absichtlich
verschieden von [`ToolError::Internal`]: „Ich habe kein TTS" und „mein
TTS ist abgestürzt" haben unterschiedliche Konsequenzen, und das Zweite
zu beantworten, wenn du das Erste meinst, lässt den Daemon ein
funktionierendes Plugin für tot erklären.
</content>
