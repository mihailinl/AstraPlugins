> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/migration-0.6.md) maßgeblich.

# Ein Plugin auf die 0.6-SDKs migrieren

Für jemanden mit einem funktionierenden Plugin aus der 0.5-Ära. In der
Reihenfolge, in der du auf die Probleme stoßen wirst: **was zur Laufzeit
kaputtgeht, bevor du auch nur eine Zeile änderst**, dann was zur
Kompilierzeit kaputtgeht, dann was kompiliert und sich anders verhält,
dann was nur noch warnt.

Der Release-Zug heißt `sdk-v0.6.0`: die Rust-Crate geht auf 0.6.0, die
Python- und TypeScript-Pakete auf 0.5.0. Siehe [versioning.md](versioning.md)
dafür, warum die Zahlen unterschiedlich sind.

Jedes Snippet unten ist echter Code aus diesem Repository — die neun
Rust-Beispiele wurden im Commit `134f6d1` auf 0.6 portiert, beide Seiten
jedes Diffs existieren also in git und sind von dort zitiert.

---

## 0. Warum du nicht bleiben kannst, wo du bist

Das ist kein „schöne neue API"-Release. **Ein 0.5-Plugin ist gegen den
aktuellen Daemon bereits kaputt**, bevor du irgendetwas änderst:

> Der 0.5-`HostClient` sendet kein `x-session-token`, und der Daemon
> antwortet bei jedem Host-RPC außer `Register` mit `unauthenticated`.

Also scheitern `fire_trigger`, `set_variable`, `log`, `push_to_ui` und der
Rest zur Laufzeit, auf einer Maschine, die nicht dir gehört, mit einer
Nachricht, die dein Nutzer als „das Plugin ist kaputt" liest. Die
Registrierung gelingt weiterhin, was die Verwirrung ausmacht: Das Plugin
scheint zu starten und tut dann nichts.

Das ist der ganze Grund, warum 0.6 existiert, und der Grund, warum sich
die Autoren-API im selben Release ändern durfte.

---

## 1. Der schnelle Weg (Rust): eine Zeile, und es baut

Wenn du das Plugin heute funktionsfähig brauchst und die Migration erst
nächste Woche machen willst, ändere deinen Import:

<!-- doctest: illustrative reason="a one-line diff of the import, not a compilable file" -->
```diff
-use astra_plugin_sdk::prelude::*;
+use astra_plugin_sdk::compat::*;
```

Das ist der gesamte Diff. `compat` ist der 0.5-Trait, die 0.5-Result-Typen
und die 0.5-`HostClient`/`DaemonClient`-Formen, über eine Blanket-Impl auf
den 0.6-Trait weitergeleitet. Verifiziert am echten 0.5-dice-roller — 255
Zeilen, unverändert außer dieser Zeile:

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
warning: use of deprecated trait `astra_plugin_sdk::compat::PluginCapability`: implement
`astra_plugin_sdk::PluginCapability` (0.6): handlers take a `&PluginContext`, return
`Result<_, ToolError>`, and declare `type Config`. See docs/en/migration-0.6.md. This
trait is removed in 0.8
  --> src/main.rs:92:6
   |
92 | impl PluginCapability for DiceRoller {
   |      ^^^^^^^^^^^^^^^^

warning: `dice_roller` (bin "dice_roller") generated 12 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 16.38s
```

(Eine Warnung pro veraltetem Element, das du berührst — elf davon hier,
plus ein `unused_mut`, das das alte `let mut h = host.lock().await` nicht
mehr braucht.)

Es baut, seine Tools antworten, und der Host, den es in `set_host`
gespeichert hat, erreicht weiterhin den Daemon. Die eigene Testsuite des
SDK sichert das ab: sieben Tests, geschrieben *gegen den 0.5-Trait*, über
den 0.6-Harness ausgeführt, in `astra-plugin-sdk/src/capability.rs`
(`mod compat::tests`).

Drei Dinge, die du wissen musst, bevor du dich darauf verlässt:

- **`compat::*` ersetzt `prelude::*`; es ist keine Ergänzung.** Importierst
  du beide, hast du zwei Traits namens `PluginCapability` im Scope, und
  `impl PluginCapability for MyPlugin` wird mehrdeutig (E0659) statt
  veraltet.
- **Es verschwindet in 0.8** — zwei Minor-Versionen, gemäß
  [versioning.md](versioning.md).
- **Hooks, die 0.5 nie hatte, bleiben abwesend.** `ai_complete`,
  `tts_activate`, `stt_load` / `stt_unload` / `stt_load_state` antworten
  über den Shim mit `UNIMPLEMENTED`, was das Protokoll als *Hook fehlt*
  liest. Um sie zu implementieren, musst du den Trait migrieren.

`compat::*` re-exportiert auch die 0.6-Namen — `PluginContext`,
`ToolError`, `Host`, `Daemon`, `Config`, `NoConfig` — sodass du Hooks
nacheinander auf die neuen Signaturen umstellen kannst, ohne die
Import-Zeile erneut zu ändern. Wenn der letzte umgestellt ist, tausche
`compat::*` zurück zu `prelude::*`, und die Warnungen sind weg.

Der Rest dieses Dokuments ist genau diese Migration.

---

## 2. Was zur Kompilierzeit kaputtgeht (Rust)

Das sind die echten Fehler beim Bauen des unveränderten 0.5-dice-rollers
gegen 0.6 — 15 davon, in fünf Arten.

### 2.1 `Config` ist ein erforderlicher assoziierter Typ

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0046]: not all trait items implemented, missing: `Config`
  --> src/main.rs:92:1
   |
92 | impl PluginCapability for DiceRoller {
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ missing `Config` in implementation
   |
   = help: implement the missing item: `type Config = /* Type */;`
```

Wenn dein Plugin keine Settings hat, ist das eine Zeile:

<!-- doctest: illustrative reason="the single line that satisfies the associated type; the whole impl it belongs to is the block above" -->
```rust
type Config = NoConfig;
```

Falls doch, deklariere den Typ und implementiere `on_config` — das SDK
parst das JSON des Daemons für dich. bad-apple, vorher
(`examples/bad-apple/src/main.rs` bei `134f6d1^`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn on_config_changed(&self, config_json: &str) {
    if let Ok(v) = serde_json::from_str::<serde_json::Value>(config_json) {
        let mut cfg = self.config.lock().unwrap();
        if let Some(s) = v.get("render_mode").and_then(|s| s.as_str()) {
            cfg.render_mode = s.to_string();
        }
        if let Some(n) = v.get("opacity").and_then(|n| n.as_f64()) {
            cfg.opacity = n;
        }
        // …three more arms, each silently skipping a field of the wrong type
    }
}
```

und nachher (`examples/bad-apple/src/main.rs`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
#[derive(Serialize, Deserialize)]
#[serde(default)]
struct BadAppleConfig {
    render_mode: String,
    opacity: f64,
    charset: String,
    color: String,
    #[serde(rename = "loop")]
    do_loop: bool,
}

#[async_trait]
impl PluginCapability for BadApple {
    type Config = BadAppleConfig;

    async fn on_config(&self, _ctx: &PluginContext, config: BadAppleConfig) {
        self.config.store(config);
    }
}
```

Zwanzig Zeilen zu zwei, und ein Feld des falschen Typs wird jetzt
gemeldet statt übersprungen.

> **Benutze `#[serde(default)]` (oder `#[astra::config]`, das es
> hinzufügt).** Die erste Config-Nutzlast, die der Daemon einem frisch
> installierten Plugin sendet, ist `{}`. Ein Config-Typ mit einem
> erforderlichen Feld lehnt sie ab, `on_config` wird dann nicht ein
> einziges Mal aufgerufen, und dein Plugin bedient jeden Aufruf mit
> `Config::default()` — ein leerer API-Key, ein Trigger-Name, der der
> leere String ist. Das SDK warnt laut genau vor diesem Fall, aber das
> Log-Panel ist nicht, wo du hinschaust.

`Config<T>` ist der lock-freie Speicher, um sie darin zu halten:
`self.config.load()` ist ein atomarer Lesevorgang, und ein
Config-Rewrite mitten in einem Tool-Aufruf kann ihn nicht blockieren.

### 2.2 Handler nehmen ein `&PluginContext`

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0050]: method `call_tool` has 3 parameters but the declaration in trait
              `astra_plugin_sdk::PluginCapability::call_tool` has 4
   --> src/main.rs:117:24
    |
117 |     async fn call_tool(&self, name: &str, arguments_json: &str) -> ToolResult {
    |                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ expected 4 parameters, found 3
```

Füge `ctx: &PluginContext` (oder `_ctx`) nach `&self` hinzu. Es trägt
`plugin_id`, `language`, `active_triggers`, `host` und `daemon`; es ist
billig zu klonen; es ist nie `None`. mock-stt, vorher und nachher:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5 — examples/mock-stt/src/main.rs at 134f6d1^
async fn stt_transcribe(&self, audio: &[u8], sample_rate: u32) -> anyhow::Result<SttEvent> {
```

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.6 — examples/mock-stt/src/main.rs
async fn stt_transcribe(
    &self,
    _ctx: &PluginContext,
    audio: &[u8],
    sample_rate: u32,
    options: &SttOptions,
) -> anyhow::Result<SttEvent> {
```

TTS fasste gleichzeitig seine vier Argumente in ein einziges
`TtsRequest` zusammen — tone-tts ging von
`(&self, text, voice_id, speed, _pitch)` zu `(&self, _ctx, req: TtsRequest)`,
liest `req.text`, `req.voice_id`, `req.speed`.

Von einer Stelle aus, die ein Parameter nicht erreichen kann — eine
gespawnte Task, ein `Drop`, ein Callback aus der Crate von jemand
anderem — gibt `astra_plugin_sdk::ctx()` denselben Kontext zurück.

### 2.3 `set_host` und `set_daemon_client` sind weg

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0407]: method `set_host` is not a member of trait `PluginCapability`
  --> src/main.rs:95:5
   |
95 | /     async fn set_host(&self, host: Arc<Mutex<HostClient>>) {
96 | |         *self.host.lock().await = Some(host);
97 | |         info!("Host client received");
98 | |     }
   | |_____^ not a member of trait `PluginCapability`
```

Lösche den Hook, lösche das Feld, benutze `ctx.host()`. Das lohnt sich,
richtig statt über den Shim zu erledigen, weil die 0.5-Form einen Defekt
hatte. dice-roller, vorher (`examples/dice-roller/src/main.rs` bei
`134f6d1^`):

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
struct DiceRoller {
    default_sides: AtomicU32,
    total_rolls: AtomicU64,
    host: Mutex<Option<Arc<Mutex<HostClient>>>>,
}

fn fire_roll_triggers_bg(&self, results: Vec<u32>, sides: u32) {
    let host = self.host.try_lock().ok().and_then(|g| g.clone());
    let host = match host {
        Some(h) => h,
        None => {
            info!("Cannot fire triggers: host client not available yet");
            return;
        }
    };
    // …
}
```

Wenn ein zweiter Tool-Aufruf dieses Lock hielt, gab `try_lock` `None`
zurück, das Plugin loggte „host client not available yet", und **löste
nichts aus**. Nachher:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
fn fire_roll_values(&self, ctx: &PluginContext, results: &[u32], sides: u32) {
    let host = ctx.host().clone();
    let results = results.to_vec();
    tokio::spawn(async move {
        for v in results {
            let payload = json!({ "value": v.to_string(), "roll": format!("1d{sides}"), "sum": v.to_string() });
            if let Err(e) = host.fire_trigger("on_roll_value", &payload.to_string()).await {
                let _ = host.log_warn(&format!("failed to fire on_roll_value: {e}")).await;
            }
        }
    });
}
```

`Arc<dyn Host>` hat kein Lock zu verlieren. Dasselbe gilt für
Client-Plugins: `ctx.daemon()` ist für das gesamte Leben eines Plugins
mit der `client`-Capability `Some`, jeder
„daemon client not ready"-Zweig fällt also weg. telegram-client verlor
sein `SharedDaemon`-Feld und diese Prüfung:

> `Some` bezieht sich auf das Handle, nicht darauf, was es erreichen
> kann. Der Daemon begrenzt das Session-Token jedes Plugins auf
> `PluginHostService`, Aufrufe über `ctx.daemon()` antworten also derzeit
> mit `permission_denied` — siehe
> [die Rust-SDK-Seite](4-sdk/rust.md#daemon--im-sdk-vorhanden-vom-daemon-abgelehnt).
> Dieser Abschnitt handelt von der Form der Migration, nicht von einem
> Pfad, der heute Ende-zu-Ende funktioniert.

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
// 0.5
if self.daemon.lock().await.is_none() {
    info!("Daemon client not ready, not starting");
    return;
}
```

### 2.4 `ToolResult` / `ActionResult` / `UiCallResult` sind gelöscht

<!-- doctest: illustrative reason="a rustc diagnostic from building a 0.5-era plugin against the 0.6 SDK; `from=` was prose, not a command, and no plugin in this tree is still on 0.5 to reproduce it from" -->
```
error[E0433]: cannot find type `ToolResult` in this scope
```

Handler geben `Result<String, ToolError>` zurück (`ActionError` ist ein
Alias für `ToolError`). Die Zuordnung ist mechanisch:

| 0.5 | 0.6 |
| --- | --- |
| `ToolResult::ok(text)` | `Ok(text)` |
| `ToolResult::err("unknown tool")` | `Err(ToolError::NotFound(…))` |
| `ToolResult::err("bad JSON")` | `Err(ToolError::BadArguments(…))`, oder einfach `?` beim Parsen |
| `ToolResult::err("no API key")` | `Err(ToolError::not_configured("api_key"))` |
| `UiCallResult::ok(json)` / `::err(msg)` | `Ok(json)` / `Err(ToolError::…)` |

Die Art ist keine Dekoration. Sie sagt der AI-Schleife, ob ein erneuter
Versuch überhaupt helfen könnte, und `NotConfigured { field }` ist das,
was „das Tool ist gescheitert" in einen Link zu genau diesem
Settings-Eingabefeld verwandelt. bad-apple, nachher:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
async fn handle_ui_call(
    &self,
    _ctx: &PluginContext,
    method: &str,
    _params_json: &str,
) -> Result<String, ToolError> {
    match method {
        "getConfig" => Ok(serde_json::to_string(&*self.config.get())?),
        _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
    }
}
```

Beachte das `?` bei `serde_json::to_string`: `From`-Implementierungen
existieren für `serde_json::Error`, `std::io::Error`, `tonic::Status` und
`anyhow::Error`, und jede Konvertierung ist eine Behauptung darüber,
welcher Art der Fehlschlag ist — `serde_json::from_str(args)?` innerhalb
von `call_tool` bedeutet `BAD_ARGUMENTS`, den einen Fehlschlag, den das
Modell durch einen erneuten Versuch beheben kann.

Gehst du stattdessen über den Shim, wird jeder 0.5-Fehlschlag zu
`ToolError::Internal` mit demselben Satz. Das ist die ehrliche Lesart
eines Strings, dessen Autor nie gesagt hat, was er war, und schlechter
als das, was du selbst in fünf Minuten sagen kannst.

### 2.5 Kleinere Kompilierzeit-Brüche

| Was | 0.5 | 0.6 |
| --- | --- | --- |
| `discover_capabilities` | ein Hook | **gelöscht.** Der Daemon nennt das `[capabilities]` des Manifests in `ASTRA_PLUGIN_CAPABILITIES` |
| `ActiveTriggers::contains` / `update` | `async`, `tokio::RwLock` | synchron (`ArcSwap`), und `update` heißt jetzt `set` |
| `HostClient::new(..)` | konstruierbar | nur `connect_bootstrap` → `register` → authentifizierter Client |
| `use astra_plugin_sdk::prelude::{Deserialize, Serialize}` | funktionierte | Platzhalter, die mit einem Satz scheitern: benutze `#[astra::args]`, oder füge `serde` zu deiner eigenen `Cargo.toml` hinzu |
| `on_shutdown()`, `on_event()`, `on_state_changed()` und die anderen Event-Hooks | kein `ctx` | `ctx` zuerst, wie überall sonst |

---

## 3. Was zur Laufzeit kaputtgeht (es kompiliert, verhält sich aber anders)

### 3.1 `[permissions]` ist default-deny

Das, was zuerst auf der Maschine eines Nutzers zubeißt, und es ist gar
keine SDK-Änderung — es ist Phase 4. Ein Manifest ohne
`[permissions]`-Abschnitt darf `Register`, `PluginLog` und
`GetPluginSelfConfig` aufrufen, und **sonst nichts**. `fire_trigger`,
`set_variable`, `push_to_ui`, `send_chat_message`, `subscribe_events`
und `set_theme_contribution` brauchen jeweils eine deklarierte,
gewährte Permission, und eine Ablehnung kommt als `PERMISSION_DENIED` →
`ToolError::Unauthorized` an.

Die Capability zu deklarieren reicht nicht. Aus
`examples/dice-roller/plugin.toml`:

<!-- doctest: illustrative reason="an excerpt of the [permissions] block from examples/dice-roller/plugin.toml, not a whole manifest" -->
```toml
# `[permissions]` is the other direction: which host RPCs the plugin may call
# out to. Default-deny — a manifest with no `[permissions]` section may call
# nothing beyond Register, PluginLog and GetPluginSelfConfig, so declaring
# `triggers = true` is not what lets `fire_trigger` through. This is.
[permissions]
fire_trigger = { reason = "Fires the on_roll_value trigger so your commands can react to what you rolled" }
```

Der `reason` wird dem Nutzer bei der Installation gezeigt. Schreib ihn
für ihn.

### 3.2 Startreihenfolge, und `on_start`

0.6 korrigiert die Reihenfolge: bind → register → build ctx →
`on_config` → `on_language_changed` → `on_start` → serve. `on_start` ist
neu, und `Err` zurückzugeben **bricht den Start ab**: der Prozess endet
mit Nicht-Null-Exit, statt ein Plugin zu hinterlassen, das der Daemon für
gesund hält und das jeden Aufruf auf dieselbe Weise scheitern lässt.

Hierhin gehören Warm-up und Hintergrundaufgaben. echo-stt verschob
seinen Audio-Thread dorthin, aus `main` heraus; telegram-client verschob
seinen gesamten Bot-Start aus `set_daemon_client` heraus, was ein
Rennen gegen `on_config_changed` beseitigte:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
/// Config has already been applied by the time this runs, so the bot token
/// is there and the bot starts once, in one place, instead of racing
/// `set_daemon_client` against `on_config_changed`.
async fn on_start(&self, ctx: &PluginContext) -> anyhow::Result<()> {
    let daemon = ctx
        .daemon()
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("telegram-client needs the `client` capability"))?;
```

### 3.3 Verhalten, das sich still geändert hat

- **`ActiveTriggers` hat einen Schreiber.** In 0.5 schrieb nichts jemals
  hinein, `contains()` antwortete also immer mit false. Wenn du eine
  teure Nutzlast dahinter abgesichert hast, war diese Absicherung immer
  geschlossen und ist jetzt offen — die Nutzlast wird gebaut werden.
- **Der STT-Audiokanal hält 500 Chunks, nicht 32.** Ein
  Streaming-Recognizer, der still Audio unter Last fallen ließ, tut das
  nicht mehr. Hast du das kompensiert, hör damit auf.
- **`source_id()` beeinflusst nichts.** Der Daemon filtert nicht mehr
  nach Source-ID; jeder Client sieht jedes Event. Veraltet in 0.6, weg in
  0.8. Übergib die ID stattdessen an `Host::send_chat_message`.
- **Capabilities kommen vom Daemon**, in `ASTRA_PLUGIN_CAPABILITIES`,
  nicht aus der Introspektion, welche deiner Methoden einen nicht-leeren
  Vector zurückgeben. Ein Plugin, dessen beworbene Capabilities früher
  mit seinem Manifest uneins waren, bewirbt jetzt das Manifest, dem der
  Nutzer zugestimmt hat.

---

## 4. Was nur noch warnt

| Warnung | Frist | Stattdessen tun |
| --- | --- | --- |
| `use of deprecated trait compat::PluginCapability` | 0.8 | der 0.6-Trait — §2 |
| `use of deprecated struct compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.8 | `Result<String, ToolError>` — §2.4 |
| `use of deprecated type alias compat::HostClient` / `DaemonClient` | 0.8 | `ctx.host()` / `ctx.daemon()` — §2.3 |
| `use of deprecated method source_id` | 0.8 | den Override löschen |
| Python `DeprecationWarning: … returned a dict` | 0.7 | die Dataclass zurückgeben |
| `AiGetModels` / `ai_models()` | 0.8 | nichts — der Daemon fragt nie |

Nichts in dieser Tabelle ist bereits ein Fehler, und nichts darin wird
innerhalb eines Minor-Releases eines werden: siehe
[versioning.md](versioning.md) für die Garantie und wie sie durchgesetzt
wird.

---

## 5. Python

Das Paket geht von 0.4.0 → 0.5.0. Die Klasse heißt weiterhin `Plugin`,
und die Decorators sind weiterhin `@tool` / `@action` / `@trigger`, die
meisten Dateien ändern sich also nur wenig.

**Fehlschläge sind jetzt kodiert.** `call_tool` und `execute_action`
fingen früher jede `Exception` und flachten sie zu
`{"success": False, "error": str(e)}` ab — weshalb jeder Fehlschlag
identisch aussah. Wirf stattdessen einen der acht Fehler, und das SDK
füllt sowohl den Legacy-String als auch die strukturierte
`error_detail` aus:

Aus `examples/text-utils/src/plugin.py`:

<!-- doctest: illustrative reason="one decorated method from examples/text-utils/src/plugin.py, not a whole module" -->
```python
@tool("Convert text case: upper, lower, title, snake, camel.")
async def case_convert(self, text: str, mode: str):
    self._check_length(text)
    if mode not in CASE_MODES:
        # BAD_ARGUMENTS, not INTERNAL: the model is the caller here, and this
        # code is what tells it to try again with a different `mode` rather
        # than to give up and apologise to the user.
        raise BadArguments(f"unknown mode {mode!r}; use one of {', '.join(CASE_MODES)}")
    self.operations_count += 1
    return self._convert_case(text, mode)
```

`raise NotConfigured("api_key")` ist derjenige, der zu einem Link auf
genau das Settings-Feld wird.

Was noch zu prüfen ist:

- **`stt_transcribe` nimmt einen dritten Parameter**,
  `options: SttOptions | None`. Ein Override mit zwei Argumenten
  funktioniert weiterhin — der Servicer untersucht deine Signatur einmal
  und übergibt nur, was sie akzeptiert — das ist also optional, und
  `options=None` hinzuzufügen ist, wie du den Sprach-Hinweis und die
  Wake-Word-Präferenz des Daemons bekommst.
- **Gib Dataclasses zurück, keine dicts**, aus den Capability-Hooks.
  Dicts funktionieren weiterhin und geben eine `DeprecationWarning` aus,
  die die zurückzugebende Klasse nennt; sie gehen in 0.7.
- **`HostClient` kann nicht unauthentifiziert konstruiert werden.**
  `HostClientBootstrap(addr, plugin_id).register(...)` gibt den echten
  zurück.
- **`@ui_call` / `@ui_page` registrieren.** Sie waren früher
  `@staticmethod`s, die ein dict zurückgaben, das der Aufrufer verwarf.
- Sichere CI gegen die Warnungen ab:
  `python -W error::DeprecationWarning -m pytest`.

## 6. TypeScript

Das Paket geht von 0.4.0 → 0.5.0, und der veröffentlichte Name ist
`astra-plugin-sdk` — nicht `@astra/plugin-sdk`, wie es früher an vier
Stellen hieß.

- **Fehlschläge sind kodiert**, dieselben acht wie überall sonst, und
  `code` ist ein String-Literal pro Klasse, sodass
  `switch (err.code) { case "NOT_CONFIGURED": … }` auf die Unterklasse
  eingrenzt und `err.configField` ohne Cast erreicht.
- **Der Konstruktor von `HostClient` ist privat**; `HostClient.register(...)`
  ist der einzige Weg, einen zu bekommen, und er wirft
  `RegistrationError`, wenn der Daemon ablehnt.
- **Die Clients laden den eigenen generierten Deskriptor des SDK**
  statt zwei von Hand gepflegter Inline-Proto-Strings, und prüfen jede
  Methode, die sie aufrufen werden, beim Verbindungsaufbau — eine
  Diskrepanz ist ein `ProtoContractError` beim Start statt ein
  `TypeError` beim ersten Aufruf.
- **`UiPanel` ist veraltet**; es ist ein Alias für `UiContribution`.
- Wenn deine `package.json` von vor 0.5.0 stammt, beachte die neue
  `exports`-Map, `"type": "commonjs"`, `engines: { node: ">=20" }` und die
  duale CJS+ESM-Ausgabe.

---

## 7. Die Migration verifizieren

Du brauchst kein installiertes Astra, um zu wissen, ob die Portierung
funktioniert hat. Die 0.6-SDKs liefern einen Test-Harness aus, der deine
Handler in-process gegen einen aufzeichnenden Host ausführt:

<!-- doctest: illustrative reason="a before/after fragment of one item, quoted from the example named above it; it does not compile on its own" -->
```rust
use astra_plugin_sdk::testing::Harness;

#[tokio::test]
async fn the_0_5_dice_roller_still_rolls_and_still_fires() {
    let h = Harness::new(DiceRoller::new())
        .with_config_json(r#"{"default_sides":20}"#)
        .start()
        .await
        .unwrap();

    let out = h
        .call_tool("roll_dice", serde_json::json!({"count": 3, "sides": 6}))
        .await
        .unwrap();
    assert!(out.starts_with("Rolled 3d6:"), "{out}");

    // The triggers the 0.5 `try_lock` used to drop when it lost the race.
    assert_eq!(h.wait_for_triggers("on_roll_value", 3).await.len(), 3);
}
```

Dieser Test ist, wie der Shim akzeptiert wurde: `DiceRoller` dort ist der
**0.5**-dice-roller, unverändert außer seiner Import-Zeile, läuft auf
0.6. Kein Daemon, kein Socket, kein installiertes Astra — `Harness` baut
einen `PluginContext` um einen aufzeichnenden Host, `fired_triggers()`
ist also eine Liste, auf die du prüfen kannst.

Eine kurze Checkliste:

1. Es baut ohne `compat::`-Import.
2. Deine `plugin.toml` hat einen `[permissions]`-Abschnitt für jeden von
   dir aufgerufenen Host-RPC, jeweils mit einem für den Nutzer
   geschriebenen `reason`.
3. `on_config` sieht `{}`, ohne umzufallen — das ist eine frische
   Installation.
4. Alles, was du früher in `set_host` / `set_daemon_client` gemacht hast,
   passiert in `on_start`, und `on_start` gibt `Err` zurück, wenn das
   Plugin wirklich nicht funktionieren kann.
5. Jedes `ToolResult::err` ist zur `ToolError`-Variante geworden, die
   sagt, warum.
</content>
