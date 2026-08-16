> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../../en/3-reference/config-fields.md) es la referencia autorizada.

# Campos de configuración y ajustes

Tres cosas distintas se llaman "config", y no son lo mismo:

| | Quién lo edita | Dónde se declara | Entregado por |
|---|---|---|---|
| **Ajustes del plugin** | el usuario, en los ajustes de Astra para tu plugin | `[config] schema` en `plugin.toml` | `OnConfigChanged`, y `GetPluginSelfConfig` bajo demanda |
| **Campos de proveedor TTS/STT** | el usuario, en la página Voice de Astra | `TtsGetConfigFields` / `SttGetConfigFields` — un hook, no el manifiesto | releído a través del mismo almacén de ajustes |
| **Parámetros de action/trigger** | el usuario, en el editor de comandos | `GetPluginActionTypes` / `GetPluginTriggerTypes` | en la llamada `ExecuteAction` |

## 1 · Ajustes del plugin

Declara un JSON Schema en el manifiesto. Astra renderiza el formulario de
ajustes a partir de él.

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

`astra-plugin check` lo analiza y avisa si la raíz no es
`"type": "object"`.

### Leerlo de forma tipada

Declara `type Config` e implementa `on_config`. El SDK analiza la carga
útil y reporta una carga que no encaja, en lugar de seguir en silencio con
ajustes obsoletos.

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

Un plugin sin ajustes escribe `type Config = NoConfig;` — el tipo asociado
es obligatorio en lugar de tener un valor por defecto, porque los defaults
para tipos asociados nunca se estabilizaron. `#[astra::plugin]` lo rellena
cuando no declaras ningún tipo de config.

### Dónde vive el archivo

`<directorio de config de astra>/plugins/<id>/config.json`. Sobrevive a una
actualización y se elimina junto con el plugin al desinstalar — consulta
[arquitectura](../1-orientation/architecture.md#config).

## 2 · Campos de proveedor TTS y STT

Los ajustes de un proveedor de voz no van en el manifiesto: la página Voice
de Astra se los pide al plugin en tiempo de ejecución, así que pueden
depender de lo que el proveedor encontró instalado. Ambos hooks son
**opcionales** — un hook ausente significa "sin campos adicionales", que es
lo que `UNIMPLEMENTED` significa en el cable.

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

### Los tipos de campo

| Constructor | `field_type` | Notas |
|---|---|---|
| `FieldDef::text` | `text` | |
| `FieldDef::textarea` | `textarea` | |
| `FieldDef::textarea_with_variables` | `textarea_with_variables` | Ofrece al usuario el selector de variables de Astra |
| `FieldDef::number` | `number` | `with_min` / `with_max` / `with_step` |
| `FieldDef::toggle` | `toggle` | `default_value` es el string `"true"` / `"false"` |
| `FieldDef::dropdown` | `dropdown` | Construido a partir de pares `(value, label)` |
| `FieldDef::hotkey` | `hotkey_recorder` | |
| `FieldDef::file_picker` | `file_picker` | |

Setters encadenables: `with_placeholder`, `with_default`,
`with_description`, `with_min`, `with_max`, `with_step`,
`with_group(id, label)` para una sección colapsable, y
`with_condition(field_id, operator, value)` para la visibilidad.

`default_value` es un **string** en el cable en todos los casos — lleva un
valor por defecto codificado en JSON, así que el default de un número es
`"440"` y el de un toggle es `"true"`.

Ambos hooks devuelven `Vec<FieldDef>` en los tres SDK; las formas en Python
y TypeScript están en [las páginas de sus SDK](../4-sdk/python.md).

## 3 · Parámetros de action y trigger

`GetPluginActionTypes` y `GetPluginTriggerTypes` describen lo que tu plugin
añade al editor de comandos, y se leen **una vez al arrancar**. Un cambio
necesita un reinicio, por lo que son declarativos en lugar de calculados.

Sus campos de parámetro usan el mismo vocabulario `FieldDef` de arriba.

## Localización

`label`, `placeholder` y `description` pueden ser claves i18n en lugar de
literales. El SDK incluye `I18n` para las cadenas propias del plugin, y
`OnLanguageChanged` te avisa de que cambió el idioma de la UI para que todo
lo visible para el usuario pueda volver a renderizarse. El idioma también
está en el contexto desde el primer momento: `ctx.language()`.
</content>
