> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/3-reference/config-fields.md) maßgeblich.

# Config- und Settings-Felder

Drei verschiedene Dinge heißen „Config", und sie sind nicht dasselbe:

| | Bearbeitet von | Deklariert in | Ausgeliefert durch |
|---|---|---|---|
| **Plugin-Settings** | dem Nutzer, in Astras Einstellungen für dein Plugin | `[config] schema` in `plugin.toml` | `OnConfigChanged`, und `GetPluginSelfConfig` auf Anfrage |
| **TTS/STT-Provider-Felder** | dem Nutzer, auf Astras Voice-Seite | `TtsGetConfigFields` / `SttGetConfigFields` — ein Hook, nicht das Manifest | zurückgelesen über denselben Settings-Store |
| **Action-/Trigger-Parameter** | dem Nutzer, im Befehlseditor | `GetPluginActionTypes` / `GetPluginTriggerTypes` | beim `ExecuteAction`-Aufruf |

## 1 · Plugin-Settings

Deklariere ein JSON Schema im Manifest. Astra rendert das Settings-Formular
daraus.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "weather"
name = "Weather"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/weather"

[capabilities]
tools = true

[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key":  { "type": "string", "title": "API key", "description": "From your provider's dashboard" },
    "units":    { "type": "string", "enum": ["metric", "imperial"], "default": "metric" },
    "cache_ttl_secs": { "type": "integer", "minimum": 0, "default": 600 }
  }
}
"""
```

`astra-plugin check` parst es und warnt, wenn die Wurzel nicht
`"type": "object"` ist.

### Es typisiert lesen

Deklariere `type Config` und implementiere `on_config`. Das SDK parst die
Nutzlast und meldet eine nicht passende Nutzlast, statt still mit
veralteten Einstellungen weiterzulaufen.

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;
use std::sync::Mutex;

/// `#[astra::config]` is `#[astra::args]` plus `#[serde(default)]`, and the
/// second half is the load-bearing one: a freshly installed plugin's first
/// config payload is `{}`, so every field must have a default or the first
/// delivery fails.
#[astra::config]
struct Settings {
    api_key: String,
    #[serde(default = "default_units")]
    units: String,
}

fn default_units() -> String {
    "metric".into()
}

#[derive(Default)]
struct Weather {
    settings: Mutex<Settings>,
}

impl Default for Settings {
    fn default() -> Self {
        Self { api_key: String::new(), units: default_units() }
    }
}

#[astra::plugin]
impl Weather {
    /// Called on start and on every settings change.
    #[hook]
    async fn on_config(&self, ctx: &PluginContext, cfg: Settings) {
        if cfg.api_key.is_empty() {
            let _ = ctx.host().log_warn("no API key set — open this plugin's settings").await;
        }
        *self.settings.lock().unwrap() = cfg;
    }

    /// Report the weather. Use it when the user asks about weather or temperature.
    #[tool]
    async fn weather(&self) -> Result<String, ToolError> {
        let settings = self.settings.lock().unwrap();
        if settings.api_key.is_empty() {
            // NotConfigured is its own error code precisely so the model can
            // tell "you have not set this up" from "the call failed", and
            // `field` is a deep-link target: the UI can open that exact input
            // instead of dropping the user on a settings page.
            return Err(ToolError::NotConfigured {
                field: "api_key".into(),
                message: "set an API key in the plugin's settings".into(),
            });
        }
        Ok(format!("18 degrees ({})", settings.units))
    }
}

astra::main!(Weather::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn an_unconfigured_plugin_says_so() {
        let h = Harness::new(Weather::default()).start().await.unwrap();
        let err = h.call_tool("weather", json!({})).await.expect_err("not configured");
        assert!(err.to_string().contains("API key"), "{err}");
    }

    #[tokio::test]
    async fn settings_arrive_and_are_used() {
        let h = Harness::new(Weather::default())
            .with_config(json!({ "api_key": "k", "units": "imperial" }))
            .start()
            .await
            .unwrap();
        assert_eq!(h.call_tool("weather", json!({})).await.unwrap(), "18 degrees (imperial)");
    }

    /// A settings change after start, which is the path that actually breaks.
    #[tokio::test]
    async fn a_later_change_is_picked_up() {
        let h = Harness::new(Weather::default())
            .with_config(json!({ "api_key": "k" }))
            .start()
            .await
            .unwrap();
        h.config_changed(json!({ "api_key": "k2", "units": "imperial" })).await;
        assert_eq!(h.call_tool("weather", json!({})).await.unwrap(), "18 degrees (imperial)");
    }
}
```

Ein Plugin ohne Settings schreibt `type Config = NoConfig;` — der
assoziierte Typ ist erforderlich statt mit einem Default versehen, weil
Defaults für assoziierte Typen sich nie stabilisiert haben. `#[astra::plugin]`
füllt ihn aus, wenn du keinen Config-Typ deklarierst.

### Wo die Datei liegt

`<astra config dir>/plugins/<id>/config.json`. Sie übersteht ein Update und
wird bei der Deinstallation mit dem Plugin gelöscht — siehe
[Architektur](../1-orientation/architecture.md#config).

## 2 · TTS- und STT-Provider-Felder

Die Einstellungen eines Voice-Providers gehören nicht ins Manifest: Astras
Voice-Seite fragt das Plugin zur Laufzeit danach, sodass sie davon abhängen
können, was der Provider vorgefunden hat. Beide Hooks sind **optional** —
ein fehlender Hook bedeutet „keine zusätzlichen Felder", genau das, was
`UNIMPLEMENTED` auf der Leitung bedeutet.

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct ToneTts;

#[astra::plugin]
impl ToneTts {
    #[hook]
    async fn tts_voices(&self) -> Vec<VoiceInfo> {
        vec![VoiceInfo::new("sine", "Sine Tone")]
    }

    #[hook]
    async fn tts_synthesize(
        &self,
        _ctx: &PluginContext,
        _req: TtsRequest,
    ) -> anyhow::Result<AudioData> {
        // 200 ms of silence at 16 kHz, f32-LE PCM — the format the daemon plays.
        Ok(AudioData {
            data: vec![0u8; 16_000 / 5 * 4],
            format: "pcm".into(),
            sample_rate: 16_000,
            duration_ms: 200,
        })
    }

    /// Rendered by Astra's Voice page, under this provider.
    #[hook]
    async fn tts_config_fields(&self) -> Vec<FieldDef> {
        vec![
            FieldDef::number("frequency", "Frequency (Hz)")
                .with_default("440")
                .with_min(50.0)
                .with_max(2000.0)
                .with_description("The pitch of the generated tone"),
            FieldDef::dropdown(
                "waveform",
                "Waveform",
                &[("sine", "Sine"), ("square", "Square")],
            )
            .with_default("sine"),
            FieldDef::toggle("fade", "Fade in and out").with_default("true"),
            // Only shown when `fade` is on. The condition is evaluated by the
            // UI, so a hidden field is hidden — not disabled.
            FieldDef::number("fade_ms", "Fade length (ms)")
                .with_default("20")
                .with_condition("fade", "eq", "true"),
        ]
    }
}

astra::main!(ToneTts::default());
```

### Die Feldtypen

| Konstruktor | `field_type` | Anmerkungen |
|---|---|---|
| `FieldDef::text` | `text` | |
| `FieldDef::textarea` | `textarea` | |
| `FieldDef::textarea_with_variables` | `textarea_with_variables` | Bietet dem Nutzer Astras Variablen-Picker an |
| `FieldDef::number` | `number` | `with_min` / `with_max` / `with_step` |
| `FieldDef::toggle` | `toggle` | `default_value` ist der String `"true"` / `"false"` |
| `FieldDef::dropdown` | `dropdown` | Aus `(value, label)`-Paaren gebaut |
| `FieldDef::hotkey` | `hotkey_recorder` | |
| `FieldDef::file_picker` | `file_picker` | |

Verkettbare Setter: `with_placeholder`, `with_default`, `with_description`,
`with_min`, `with_max`, `with_step`, `with_group(id, label)` für einen
einklappbaren Abschnitt, und `with_condition(field_id, operator, value)`
für Sichtbarkeit.

`default_value` ist in jedem Fall ein **String** auf der Leitung — er trägt
einen JSON-kodierten Default, sodass der Default einer Zahl `"440"` ist und
der eines Toggles `"true"`.

Beide Hooks geben in allen drei SDKs `Vec<FieldDef>` zurück; die Python- und
TypeScript-Formen stehen auf
[ihren SDK-Seiten](../4-sdk/python.md).

## 3 · Action- und Trigger-Parameter

`GetPluginActionTypes` und `GetPluginTriggerTypes` beschreiben, was dein
Plugin zum Befehlseditor hinzufügt, und sie werden **einmal beim Start**
gelesen. Eine Änderung braucht einen Neustart, weshalb sie deklarativ statt
berechnet sind.

Ihre Parameterfelder verwenden dasselbe `FieldDef`-Vokabular wie oben.

## Lokalisierung

`label`, `placeholder` und `description` dürfen i18n-Schlüssel statt
Literale sein. Das SDK liefert `I18n` für die eigenen Strings des Plugins,
und `OnLanguageChanged` teilt dir mit, dass sich die UI-Sprache geändert
hat, sodass alles Nutzersichtbare neu gerendert werden kann. Die Sprache
steht außerdem von der ersten Sekunde an im Kontext: `ctx.language()`.
</content>
