# Конфигурация и поля настроек

> Перевод. Источник истины — [docs/en](../../en/3-reference/config-fields.md); при расхождении верна английская версия.

«Конфигом» называют три разные вещи, и они не одно и то же:

| | Кто редактирует | Где объявлено | Доставляется через |
|---|---|---|---|
| **Настройки плагина** | пользователь, в настройках Astra для вашего плагина | `[config] schema` в `plugin.toml` | `OnConfigChanged`, а также `GetPluginSelfConfig` по запросу |
| **Поля провайдера TTS/STT** | пользователь, на странице голоса Astra | `TtsGetConfigFields` / `SttGetConfigFields` — хук, а не манифест | считывается обратно через то же хранилище настроек |
| **Параметры действий/триггеров** | пользователь, в редакторе команд | `GetPluginActionTypes` / `GetPluginTriggerTypes` | при вызове `ExecuteAction` |

## 1 · Настройки плагина

Объявите JSON Schema в манифесте. Astra отрисовывает форму настроек из неё.

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

`astra-plugin check` разбирает её и предупреждает, если корень — не
`"type": "object"`.

### Читаем её, типизированно

Объявите `type Config` и реализуйте `on_config`. SDK разбирает полезную
нагрузку и сообщает о той, что не подошла по форме, вместо того чтобы молча
работать на устаревших настройках.

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

Плагин без настроек пишет `type Config = NoConfig;` — ассоциированный тип
обязателен, а не по умолчанию, потому что значения по умолчанию для
ассоциированных типов так и не стабилизировались. `#[astra::plugin]`
подставляет его, если вы не объявили тип конфигурации.

### Где лежит файл

`<каталог конфигурации astra>/plugins/<id>/config.json`. Он переживает
обновление и удаляется вместе с плагином при удалении — см.
[архитектуру](../1-orientation/architecture.md#конфигурация).

## 2 · Поля провайдера TTS и STT

Настройки голосового провайдера не идут в манифест: страница голоса Astra
запрашивает их у плагина во время выполнения, так что они могут зависеть от
того, что провайдер обнаружил установленным. Оба хука **опциональны** —
отсутствующий хук означает «нет дополнительных полей», а именно это на
проводе и значит `UNIMPLEMENTED`.

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

### Типы полей

| Конструктор | `field_type` | Заметки |
|---|---|---|
| `FieldDef::text` | `text` | |
| `FieldDef::textarea` | `textarea` | |
| `FieldDef::textarea_with_variables` | `textarea_with_variables` | Предлагает пользователю выбор переменных Astra |
| `FieldDef::number` | `number` | `with_min` / `with_max` / `with_step` |
| `FieldDef::toggle` | `toggle` | `default_value` — строка `"true"` / `"false"` |
| `FieldDef::dropdown` | `dropdown` | Строится из пар `(value, label)` |
| `FieldDef::hotkey` | `hotkey_recorder` | |
| `FieldDef::file_picker` | `file_picker` | |

Цепочные сеттеры: `with_placeholder`, `with_default`, `with_description`,
`with_min`, `with_max`, `with_step`, `with_group(id, label)` для
сворачиваемого раздела, и `with_condition(field_id, operator, value)` для
видимости.

`default_value` во всех случаях — это **строка** на проводе — она несёт
значение по умолчанию в JSON-кодировке, так что для числа это `"440"`, а для
переключателя `"true"`.

Оба хука возвращают `Vec<FieldDef>` во всех трёх SDK; формы для Python и
TypeScript — на [страницах их SDK](../4-sdk/python.md).

## 3 · Параметры действий и триггеров

`GetPluginActionTypes` и `GetPluginTriggerTypes` описывают, что ваш плагин
добавляет в редактор команд, и они читаются **один раз при старте**.
Изменение требует перезапуска, поэтому они декларативны, а не вычисляются на
лету.

Их поля параметров используют тот же словарь `FieldDef`, что и выше.

## Локализация

`label`, `placeholder` и `description` могут быть ключами i18n, а не
литералами. SDK поставляет `I18n` для собственных строк плагина, а
`OnLanguageChanged` сообщает о смене языка интерфейса, чтобы всё, что видит
пользователь, можно было перерисовать. Язык также доступен через контекст с
самого начала: `ctx.language()`.
