> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/4-sdk/rust.md) maßgeblich.

# Das Rust-SDK

`astra-plugin-sdk` 0.6.0. Eine Abhängigkeit, und alles, wozu die Makros
expandieren, läuft darüber.

<!-- doctest: illustrative reason="a Cargo.toml fragment; the scaffold this line comes from is built by every rust-plugin block on this page" -->
```toml
[dependencies]
astra-plugin-sdk = "0.6"
```

0.6 ist das erste Release, dessen `HostClient` `x-session-token` anhängt.
Gegen 0.5 und älter antwortet der Daemon bei jedem Host-Aufruf mit
`unauthenticated`, also lockere diese Untergrenze nicht.

## Die Form eines Plugins

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Timer;

#[astra::plugin]
impl Timer {
    /// Start a countdown. Use it when the user asks to be reminded in N minutes.
    #[tool]
    async fn start_timer(&self, ctx: &PluginContext, a: Minutes) -> Result<String, ToolError> {
        if a.minutes == 0 {
            return Err(ToolError::BadArguments("give me at least a minute".into()));
        }
        ctx.host().log_info(&format!("timer for {}m", a.minutes)).await?;
        Ok(format!("timer set for {} minutes", a.minutes))
    }

    /// Runs from the command editor rather than from the model.
    #[action(label = "Cancel all timers")]
    async fn cancel_all(&self, ctx: &PluginContext) -> Result<String, ActionError> {
        ctx.host().log_info("cancelled").await?;
        Ok("cancelled".into())
    }

    /// A trigger a user can attach a command to.
    #[hook]
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {
        vec![TriggerTypeDef {
            r#type: "timer_elapsed".into(),
            label: "Timer elapsed".into(),
            ..Default::default()
        }]
    }
}

#[astra::args]
struct Minutes {
    /// How many minutes to wait
    minutes: u32,
}

astra::main!(Timer::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn the_manifest_and_the_code_agree() {
        let h = Harness::new(Timer::default()).start().await.unwrap();

        assert_eq!(h.tools().await.len(), 1);
        assert_eq!(h.action_types().await.len(), 1);
        assert_eq!(h.trigger_types().await[0].r#type, "timer_elapsed");

        // The schema is derived from `Minutes`, not hand-written, so it cannot
        // disagree with what the handler parses.
        h.assert_schema_matches::<Minutes>("start_timer").await;
    }
}
```

`#[astra::plugin]` implementiert `PluginCapability` aus den Hooks, die es
findet, und leitet daraus die deklarierte Capability-Menge ab — sodass ein
Plugin keine Capability behaupten kann, die sein Code nicht bedient.
`astra-plugin check` vergleicht das mit `plugin.toml`.

## Die Makro-Schicht

| | Wofür es ist |
|---|---|
| `#[astra::plugin]` | Auf dem `impl`-Block. Verwandelt die untenstehenden Member in den Trait |
| `#[tool]` | Eine Funktion, die das Modell aufrufen darf. Der Doc-Kommentar ist ihre Beschreibung |
| `#[action(label = "…")]` | Ein Schritt im Befehlseditor |
| `#[hook]` | Jede andere `PluginCapability`-Methode, namentlich |
| `#[ui_call]` | Eine Methode, die deine UI-Contribution zurückrufen kann |
| `#[astra::args]` | Auf der Argument-Struct eines Tools |
| `#[astra::config]` | Auf deiner Settings-Struct — `args` plus `#[serde(default)]` |
| `astra::main!(Plugin::default())` | Das `main`, das es ausführt |

**Warum `#[astra::args]` statt `#[derive(Deserialize, JsonSchema)]`:** Das
Derive von serde expandiert zu `extern crate serde as _serde`, was im
Extern-Prelude aufgelöst wird und nicht über einen Re-Export erreicht
werden kann. Das einfache Derive würde daher `serde` in deiner eigenen
`Cargo.toml` brauchen — genau das, worum es beim Ein-Abhängigkeit-Versprechen
geht. `#[astra::args]` sind diese beiden Derives mit `crate = "…"`, das auf
die Kopien des SDK zeigt. Selbst `serde` hinzuzufügen funktioniert
weiterhin; dann überschattet `use serde::Deserialize;` den Namen aus dem
Prelude.

Du kannst `PluginCapability` auch von Hand implementieren. Der Trait ist
öffentlich, jede Methode hat einen Default, und die Makros erzeugen genau
das, was du selbst schreiben würdest.

## `PluginContext`

Jedem Handler wird ein `&PluginContext` übergeben. Er ist nie `None`,
billig in eine Hintergrundaufgabe zu klonen, und bedeutet, dass nichts
hinter einem Lock in deiner Struct liegen muss.

| | |
|---|---|
| `ctx.host()` | `&Arc<dyn Host>` — die zehn Host-RPCs. Immer vorhanden |
| `ctx.daemon()` | `Option<&Arc<dyn Daemon>>` — **nur `Some` für `client`-Plugins** |
| `ctx.language()` | Die Astra-UI-Sprache, aktualisiert von `OnLanguageChanged` |
| `ctx.active_triggers()` | Auf welche deiner Trigger-Typen ein Befehl gerade hört |
| `ctx.plugin_id()` | Deine ID |

Von einer Stelle aus, die kein Parameter erreichen kann — eine
`Drop`-Implementierung, ein Callback aus einer C-Bibliothek, ein beim Start
gespawnter `std::thread` — gibt `astra_plugin_sdk::ctx()` den Kontext des
laufenden Plugins zurück, und `try_ctx()` die fehlbare Version.

### `Host` — die zehn ausgehenden Aufrufe

| Methode | Permission |
|---|---|
| `log_debug` / `log_info` / `log_warn` / `log_error` / `log` | keine |
| `get_config` | keine |
| `get_daemon_info` | keine |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope)` | `set_variable` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(…)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

`set_variable` nimmt **drei** Argumente — Name, Wert und Scope.
Event-Subscription ist nicht auf `Host`: deklariere `subscribed_events()`,
und der Runner besitzt den Stream (unten).

`Host` ist ein Trait, sodass ein Test `RecordingHost` einsetzen und prüfen
kann, was dein Plugin Astra mitgeteilt hat.

### `Daemon` — im SDK vorhanden, vom Daemon abgelehnt

> **`ctx.daemon()` funktioniert heute für kein Plugin.** Die Daemon-seitige
> Hälfte ist nicht vorhanden. Jedes Plugin — `client = true` oder nicht —
> ist als `ClientType::PluginClient` registriert, und der Auth-Interceptor
> des Daemons lehnt diese Identität auf **jedem** Pfad ab, der nicht mit
> `/astra.PluginHostService/` beginnt, mit
> `permission_denied("plugin session tokens are scoped to
> PluginHostService")`. `DaemonClient` verbindet sich mit genau diesem
> Token (`astra-plugin-sdk/src/host_client.rs` übergibt
> `client_session_token` an `DaemonClient::connect`), sodass jeder Aufruf
> unten — `submit_user_message`, `subscribe_chat_events`, `speak`,
> `get_settings` — zur Laufzeit `permission_denied` liefert. Ein Kanarienvogel
> in `consistency.rs` des Daemons hält die Scoping-Prüfung aufrecht, das
> ist also Absicht und keine Regression: die Reverse-Auth-Hälfte ist
> ungebaut, nicht kaputt.
>
> **`Host::send_chat_message` ist der einzige funktionierende Weg, einen
> AI-Turn auszulösen**, und er funktioniert für jedes Plugin, dem
> `send_chat_message` gewährt wurde.

Die API-Oberfläche, für wenn die Daemon-Seite ankommt: `ctx.daemon()` ist
nur `Some`, wenn das Plugin `client = true` deklariert und `is_client()`
true zurückgibt. Sie erreicht sieben Dienste — core, chat, voice, command,
config, media, monitor — mit Methoden wie `submit_user_message`,
`subscribe_chat_events`, `stop_generation`, `list_conversations`, `speak`,
`start_listening`, `execute_command`, `get_settings`,
`get_system_stats`. Es heißt `submit_user_message`, nicht `send_message`.

## Fehler

Handler geben `Result<_, ToolError>` zurück (`ActionError` ist ein Alias
für denselben Typ). Ein Fehlschlag pro Aufruf sind Daten, die die
AI-Schleife liest und nach denen sie handelt, er reist also in der Antwort
mit, nicht als gRPC-Status.

| Variante | Verwenden, wenn |
|---|---|
| `BadArguments(String)` | Das Modell kann das durch einen anders geformten erneuten Aufruf beheben |
| `NotFound(String)` | Unbekannte ID, 404 |
| `NotConfigured { field, message }` | Eine Einstellung fehlt. `field` ist ein Deep-Link-Ziel |
| `Unauthorized(String)` | Zugangsdaten abgelehnt, oder eine Permission wurde nicht gewährt |
| `RateLimited { retry_after, message }` | Ein Upstream-Kontingent. `None` bedeutet unbekannt, nicht „sofort" |
| `Unavailable(String)` | Eine Abhängigkeit ist down; später unverändert erneut versuchen |
| `Timeout(String)` | Zeit abgelaufen |
| `Internal(String)` | Ein Bug. Nichts, worauf das Modell reagieren kann |

`?` funktioniert mit `serde_json::Error`, `std::io::Error`, `tonic::Status`
und `anyhow::Error`. `with_doc_url(…)` umhüllt jeden davon mit einer Seite,
die *diesen* Fehlschlag dokumentiert, was die UI als Link rendert.

Vollständige Taxonomie, einschließlich der Wire-Strings und der
Python-/TypeScript-Schreibweisen:
[`reference/errors.md`](../reference/errors.md).

## Events

Deklariere, was du willst; der Runner abonniert, verbindet neu und
verteilt.

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Watcher;

#[astra::plugin]
impl Watcher {
    /// Requires `[permissions] subscribe_events = { types = [...] }` — and the
    /// daemon enforces that allowlist, not this list.
    #[hook]
    fn subscribed_events(&self) -> Vec<String> {
        vec!["command_completed".into(), "state_changed".into()]
    }

    #[hook]
    async fn on_command_completed(
        &self,
        ctx: &PluginContext,
        e: astra_plugin_sdk::events::CommandCompletedEvent,
    ) {
        let _ = ctx
            .host()
            .log_info(&format!("{} finished, success={}", e.command_name, e.success))
            .await;
    }

    /// The catch-all, called for every event as well as the typed handlers.
    #[hook]
    async fn on_event(&self, _ctx: &PluginContext, event_type: &str, _payload_json: &str) {
        let _ = event_type;
    }
}

astra::main!(Watcher::default());
```

Typisierte Events heute: `StateChangedEvent`, `CommandTriggeredEvent`,
`CommandCompletedEvent`. Chat-Events sind ein anderer Stream —
`on_conversation_event`, gespeist von der Firehose des Daemons, für
`client`-Plugins.

`on_chat_sync` / `ChatSyncEvent` existieren nicht. Das Event wurde
ausgemustert, und kein SDK hat die Methode; wenn du Code portierst, der es
verwendet hat, benutze `is_client()` plus `on_conversation_event`.

## Testen

Zwei Ebenen, beide mit dem SDK ausgeliefert, sodass deine `Cargo.toml` bei
einer Zeile bleibt.

| | Was es antreibt | Was es sehen kann |
|---|---|---|
| `testing::Harness` | die Hooks, im Prozess, gegen einen `RecordingHost` | Tools, Actions, Trigger, Config, Events, UI-Aufrufe, und jeden von dir getätigten Host-Aufruf |
| `testing::WireHarness` | einen echten Prozess, gestartet so wie der Daemon ihn startet | Registrierung, das Session-Token, Streaming-Audio, die Dinge, die nur die Leitung hat |

`RecordingHost` gibt dir `fired_triggers()`, `logs()`, `variables()`,
`ui_pushes()`, `chat_messages()`, plus `deny(rpc)`, `fail(rpc, err)` und
`fail_next(rpc, err)`, um die Fehlschläge zu inszenieren, auf die deine
Nutzer stoßen werden.

Und eine Ebene über beiden: `astra-plugin test` startet deine gebaute
Binärdatei gegen einen Mock-Daemon und treibt jeden Hook an, den deine
Capabilities implizieren. Das kümmert sich nicht darum, in welcher Sprache
das Plugin geschrieben wurde.

## Was dieses SDK noch nicht kann

- **`ctx.daemon()` / `DaemonClient` ist funktionsunfähig.** Der Daemon
  begrenzt das Session-Token jedes Plugins auf `PluginHostService`, sodass
  alle sieben Dienste mit `permission_denied` antworten — auch für
  `client = true`-Plugins. Benutze `Host::send_chat_message`. Siehe
  [`Daemon`](#daemon-im-sdk-vorhanden-vom-daemon-abgelehnt) oben.
- **`TtsSynthesizeStream` ist gebunden und ungeroutet.** Das SDK bedient
  ihn; es gibt keine Aufrufstelle im Daemon. Implementiere ihn gern —
  niemand ruft ihn auf, bis
  [die Paritätstabelle](../reference/parity.md) `live` sagt.
- **`AiGetModels` ist veraltet** (0.6, entfernt in 0.8) und wird von
  niemandem aufgerufen: der Modell-Picker hartkodiert
  `supports_model_discovery = false`. Es gibt keinen Ersatz;
  `AiComplete` trägt das gewählte Modell in der Anfrage.
- **Die Trait-Oberfläche von 0.5 lebt als `astra_plugin_sdk::compat`
  fort**, veraltet in 0.6 und entfernt in 0.8. Siehe
  [Migration auf 0.6](../migration-0.6.md).
- **`PluginCapability::source_id()`** ist veraltet: übergib die ID an
  `Host::send_chat_message`, da der Daemon nicht mehr nach Source-ID
  filtert.
- **Die eingehende Authentifizierung des Capability-Servers braucht keine
  Einstellung.** Der Daemon legt bei jedem Aufruf `x-plugin-token` vor und
  setzt `ASTRA_PLUGIN_CAPABILITY_AUTH=require`, sodass das SDK einen
  Aufruf ohne dieses Token ablehnt. Nur ein Daemon, der zu alt ist, um den
  Header zu senden, lässt dich auf der `warn`-Stufe; siehe
  [Architektur](../1-orientation/architecture.md).

## Siehe auch

[Hook-Tabelle für Rust](../hooks/rust.md) · [Parität](../reference/parity.md) ·
[Fehler](../reference/errors.md) ·
[Versionierungs- und Deprecation-Richtlinie](../versioning.md)
</content>
