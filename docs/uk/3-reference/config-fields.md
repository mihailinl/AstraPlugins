# Конфігурація і поля налаштувань

> Переклад. Джерело істини — [docs/en](../../en/3-reference/config-fields.md); за розбіжності відповідає англійська версія.

«Конфігом» називають три різні речі, і вони не одне й те саме:

| | Хто редагує | Де оголошено | Доставляється через |
|---|---|---|---|
| **Налаштування плагіна** | користувач, у налаштуваннях Astra для вашого плагіна | `[config] schema` у `plugin.toml` | `OnConfigChanged`, а також `GetPluginSelfConfig` за запитом |
| **Поля провайдера TTS/STT** | користувач, на сторінці голосу Astra | `TtsGetConfigFields` / `SttGetConfigFields` — хук, а не маніфест | зчитується назад через те саме сховище налаштувань |
| **Параметри дій/тригерів** | користувач, у редакторі команд | `GetPluginActionTypes` / `GetPluginTriggerTypes` | при виклику `ExecuteAction` |

## 1 · Налаштування плагіна

Оголосіть JSON Schema в маніфесті. Astra рендерить форму налаштувань з неї.

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

`astra-plugin check` розбирає її і попереджає, якщо корінь — не
`"type": "object"`.

### Читаємо її, типізовано

Оголосіть `type Config` і реалізуйте `on_config`. SDK розбирає корисне
навантаження і повідомляє про те, що не підійшло за формою, замість того щоб
мовчки працювати на застарілих налаштуваннях.

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

Плагін без налаштувань пише `type Config = NoConfig;` — асоційований тип
обов'язковий, а не за замовчуванням, тому що значення за замовчуванням для
асоційованих типів так і не стабілізувалися. `#[astra::plugin]` підставляє
його, якщо ви не оголосили тип конфігурації.

### Де лежить файл

`<каталог конфігурації astra>/plugins/<id>/config.json`. Він переживає
оновлення і видаляється разом з плагіном при видаленні — див.
[архітектуру](../1-orientation/architecture.md#конфігурація).

## 2 · Поля провайдера TTS і STT

Налаштування голосового провайдера не йдуть у маніфест: сторінка голосу
Astra запитує їх у плагіна під час виконання, тож вони можуть залежати від
того, що провайдер виявив встановленим. Обидва хуки **опціональні** —
відсутній хук означає «немає додаткових полів», а саме це на дроті й означає
`UNIMPLEMENTED`.

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

### Типи полів

| Конструктор | `field_type` | Примітки |
|---|---|---|
| `FieldDef::text` | `text` | |
| `FieldDef::textarea` | `textarea` | |
| `FieldDef::textarea_with_variables` | `textarea_with_variables` | Пропонує користувачу вибір змінних Astra |
| `FieldDef::number` | `number` | `with_min` / `with_max` / `with_step` |
| `FieldDef::toggle` | `toggle` | `default_value` — рядок `"true"` / `"false"` |
| `FieldDef::dropdown` | `dropdown` | Будується з пар `(value, label)` |
| `FieldDef::hotkey` | `hotkey_recorder` | |
| `FieldDef::file_picker` | `file_picker` | |

Ланцюгові сеттери: `with_placeholder`, `with_default`, `with_description`,
`with_min`, `with_max`, `with_step`, `with_group(id, label)` для розділу, що
згортається, і `with_condition(field_id, operator, value)` для видимості.

`default_value` в усіх випадках — це **рядок** на дроті — він несе значення
за замовчуванням у JSON-кодуванні, тож для числа це `"440"`, а для
перемикача `"true"`.

Обидва хуки повертають `Vec<FieldDef>` у всіх трьох SDK; форми для Python і
TypeScript — на [сторінках їхніх SDK](../4-sdk/python.md).

## 3 · Параметри дій і тригерів

`GetPluginActionTypes` і `GetPluginTriggerTypes` описують, що ваш плагін
додає до редактора команд, і вони читаються **один раз при старті**. Зміна
потребує перезапуску, тому вони декларативні, а не обчислюються на льоту.

Їхні поля параметрів використовують той самий словник `FieldDef`, що й вище.

## Локалізація

`label`, `placeholder` і `description` можуть бути ключами i18n, а не
літералами. SDK постачає `I18n` для власних рядків плагіна, а
`OnLanguageChanged` повідомляє про зміну мови інтерфейсу, щоб усе, що бачить
користувач, можна було перемалювати. Мова також доступна через контекст з
самого початку: `ctx.language()`.
