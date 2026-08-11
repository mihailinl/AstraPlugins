# Configuration and settings fields

Three different things are called "config", and they are not the same:

| | Who edits it | Where it is declared | Delivered by |
|---|---|---|---|
| **Plugin settings** | the user, in Astra's settings for your plugin | `[config] schema` in `plugin.toml` | `OnConfigChanged`, and `GetPluginSelfConfig` on request |
| **TTS/STT provider fields** | the user, on Astra's Voice page | `TtsGetConfigFields` / `SttGetConfigFields` — a hook, not the manifest | read back through the same settings store |
| **Action / trigger parameters** | the user, in the command editor | `GetPluginActionTypes` / `GetPluginTriggerTypes` | on the `ExecuteAction` call |

## 1 · Plugin settings

Declare a JSON Schema in the manifest. Astra renders the settings form from it.

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

`astra-plugin check` parses it and warns if the root is not `"type": "object"`.

### Reading it, typed

Declare `type Config` and implement `on_config`. The SDK parses the payload and
reports a payload that does not fit, rather than running on stale settings in
silence.

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

A plugin with no settings writes `type Config = NoConfig;` — the associated type
is required rather than defaulted, because associated type defaults have never
stabilised. `#[astra::plugin]` fills it in when you declare no config type.

### Where the file lives

`<astra config dir>/plugins/<id>/config.json`. It survives an update and is
deleted with the plugin on uninstall — see
[architecture](../1-orientation/architecture.md#config).

## 2 · TTS and STT provider fields

A voice provider's settings do not go in the manifest: Astra's Voice page asks
the plugin for them at runtime, so they can depend on what the provider found
installed. Both hooks are **optional** — an absent hook means "no extra fields",
which is what `UNIMPLEMENTED` means on the wire.

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

### The field types

| Constructor | `field_type` | Notes |
|---|---|---|
| `FieldDef::text` | `text` | |
| `FieldDef::textarea` | `textarea` | |
| `FieldDef::textarea_with_variables` | `textarea_with_variables` | Offers the user Astra's variable picker |
| `FieldDef::number` | `number` | `with_min` / `with_max` / `with_step` |
| `FieldDef::toggle` | `toggle` | `default_value` is the string `"true"` / `"false"` |
| `FieldDef::dropdown` | `dropdown` | Built from `(value, label)` pairs |
| `FieldDef::hotkey` | `hotkey_recorder` | |
| `FieldDef::file_picker` | `file_picker` | |

Chainable setters: `with_placeholder`, `with_default`, `with_description`,
`with_min`, `with_max`, `with_step`, `with_group(id, label)` for a collapsible
section, and `with_condition(field_id, operator, value)` for visibility.

`default_value` is a **string** on the wire in every case — it carries a
JSON-encoded default, so a number's default is `"440"` and a toggle's is
`"true"`.

Both hooks return `Vec<FieldDef>` in all three SDKs; the Python and TypeScript
shapes are in [their SDK pages](../4-sdk/python.md).

## 3 · Action and trigger parameters

`GetPluginActionTypes` and `GetPluginTriggerTypes` describe what your plugin
adds to the command editor, and they are read **once at startup**. A change
needs a restart, which is why they are declarative rather than computed.

Their parameter fields use the same `FieldDef` vocabulary as above.

## Localisation

`label`, `placeholder` and `description` may be i18n keys rather than literals.
The SDK ships `I18n` for the plugin's own strings, and `OnLanguageChanged` tells
you the UI language changed so anything user-visible can be re-rendered. The
language is also on the context from the first moment: `ctx.language()`.
