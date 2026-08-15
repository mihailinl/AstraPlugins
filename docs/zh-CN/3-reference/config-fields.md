> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/3-reference/config-fields.md)。如与英文版有出入，以英文版为准。

# 配置与设置字段

被统称为"config"的东西其实有三种不同的含义，它们并不是一回事：

| | 由谁编辑 | 在哪里声明 | 由什么传递 |
|---|---|---|---|
| **插件设置** | 用户，在 Astra 为你的插件提供的设置界面中 | `plugin.toml` 中的 `[config] schema` | `OnConfigChanged`，按需时用 `GetPluginSelfConfig` |
| **TTS/STT 提供者字段** | 用户，在 Astra 的 Voice 页面 | `TtsGetConfigFields` / `SttGetConfigFields` —— 一个钩子，不是清单文件 | 通过同一个设置存储读回 |
| **动作/触发器参数** | 用户，在命令编辑器中 | `GetPluginActionTypes` / `GetPluginTriggerTypes` | 在 `ExecuteAction` 调用时 |

## 1 · 插件设置

在清单文件中声明一份 JSON Schema。Astra 会据此渲染出设置表单。

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

`astra-plugin check` 会解析它，如果根不是 `"type": "object"` 就会发出
警告。

### 带类型地读取它

声明 `type Config` 并实现 `on_config`。SDK 会解析负载(payload)，如果
负载不匹配就报告出来，而不是悄悄地沿用过期的设置继续运行。

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

一个没有任何设置的插件写作 `type Config = NoConfig;` —— 这个关联类型
是必须的，而不是有默认值的，因为关联类型的默认值机制至今都没有稳定下来。
当你没有声明配置类型时，`#[astra::plugin]` 会替你填上这一项。

### 文件位于何处

`<astra config dir>/plugins/<id>/config.json`。它能在更新中存活，
并且会在卸载插件时随插件一起被删除 —— 参见
[架构](../1-orientation/architecture.md#配置)。

## 2 · TTS 和 STT 提供者字段

语音提供者的设置不放在清单文件里：Astra 的 Voice 页面会在运行时向插件
询问这些设置，这样它们就能依赖提供者当时实际检测到的安装情况。这两个
钩子都是**可选的**——钩子缺失意味着"没有额外字段"，这也正是
`UNIMPLEMENTED` 在传输层面上的含义。

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

### 字段类型

| 构造函数 | `field_type` | 说明 |
|---|---|---|
| `FieldDef::text` | `text` | |
| `FieldDef::textarea` | `textarea` | |
| `FieldDef::textarea_with_variables` | `textarea_with_variables` | 为用户提供 Astra 的变量选择器 |
| `FieldDef::number` | `number` | `with_min` / `with_max` / `with_step` |
| `FieldDef::toggle` | `toggle` | `default_value` 是字符串 `"true"` / `"false"` |
| `FieldDef::dropdown` | `dropdown` | 由 `(value, label)` 对构建而成 |
| `FieldDef::hotkey` | `hotkey_recorder` | |
| `FieldDef::file_picker` | `file_picker` | |

可链式调用的设置方法：`with_placeholder`、`with_default`、
`with_description`、`with_min`、`with_max`、`with_step`，用于可折叠区块
的 `with_group(id, label)`，以及用于控制可见性的
`with_condition(field_id, operator, value)`。

在传输层面上，`default_value` 在任何情况下都是一个**字符串**——它携带
的是一个 JSON 编码后的默认值，所以一个数字类型字段的默认值是
`"440"`，一个开关类型字段的默认值是 `"true"`。

这两个钩子在全部三个 SDK 中返回的都是 `Vec<FieldDef>`；Python 和
TypeScript 中对应的形态见
[各自的 SDK 页面](../4-sdk/python.md)。

## 3 · 动作和触发器参数

`GetPluginActionTypes` 和 `GetPluginTriggerTypes` 描述的是你的插件向
命令编辑器添加了什么，它们**只在启动时被读取一次**。改动需要重启才能
生效，这也是为什么它们是声明式的，而不是动态计算出来的。

它们的参数字段使用的是和上面相同的 `FieldDef` 词汇表。

## 本地化

`label`、`placeholder` 和 `description` 可以是 i18n 键，而不一定是
字面量。SDK 自带了 `I18n`，供插件自己的字符串使用，而
`OnLanguageChanged` 会告诉你 UI 语言变了，好让任何用户可见的内容都能
重新渲染。从最初的那一刻起，语言信息也已经在上下文中：`ctx.language()`。
