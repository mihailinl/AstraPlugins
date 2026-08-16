> **これは翻訳です。** 正式な情報源は [docs/en](../../en/3-reference/config-fields.md) です。内容に食い違いがある場合は英語版が優先されます。

# 設定とフィールド

「設定(config)」と呼ばれるものには 3 つの異なるものがあり、それらは
同じではありません。

| | 誰が編集するか | どこで宣言されるか | 何によって届けられるか |
|---|---|---|---|
| **プラグインの設定** | ユーザーが、あなたのプラグイン用の Astra の設定画面で | `plugin.toml` の `[config] schema` | `OnConfigChanged`、リクエスト時は `GetPluginSelfConfig` |
| **TTS/STT プロバイダのフィールド** | ユーザーが、Astra の Voice ページで | `TtsGetConfigFields` / `SttGetConfigFields` — マニフェストではなくフック | 同じ設定ストアを通して読み戻される |
| **アクション/トリガーのパラメータ** | ユーザーが、コマンドエディタで | `GetPluginActionTypes` / `GetPluginTriggerTypes` | `ExecuteAction` の呼び出し時に |

## 1 · プラグインの設定

マニフェスト内に JSON Schema を宣言します。Astra はそこから設定フォーム
を描画します。

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

`astra-plugin check` がこれをパースし、ルートが `"type": "object"` で
なければ警告します。

### 型付きで読む

`type Config` を宣言し、`on_config` を実装してください。SDK はペイロード
をパースし、収まらないペイロードがあれば、静かに古い設定のまま動作する
のではなく、それを報告します。

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

設定のないプラグインは `type Config = NoConfig;` と書きます — この
関連型はデフォルト値ではなく必須です。なぜなら関連型のデフォルト値は
いまだに安定化していないからです。`#[astra::plugin]` は、あなたが設定型
を宣言しなかったときにこれを埋めてくれます。

### ファイルはどこにあるか

`<astra config dir>/plugins/<id>/config.json` です。更新を生き延び、
アンインストール時にプラグインとともに削除されます — 詳しくは
[アーキテクチャ](../1-orientation/architecture.md#設定) を参照して
ください。

## 2 · TTS と STT プロバイダのフィールド

ボイスプロバイダの設定はマニフェストには入りません: Astra の Voice
ページは実行時にプラグインにそれらを尋ねます。そのため、それらはプロバイダ
がインストール時に見つけたものに依存できます。両方のフックとも
**任意**です — フックが存在しないことは「追加フィールドなし」を意味し、
それはワイヤー上で `UNIMPLEMENTED` が意味することと同じです。

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

### フィールドの種類

| コンストラクタ | `field_type` | 備考 |
|---|---|---|
| `FieldDef::text` | `text` | |
| `FieldDef::textarea` | `textarea` | |
| `FieldDef::textarea_with_variables` | `textarea_with_variables` | ユーザーに Astra の変数ピッカーを提供します |
| `FieldDef::number` | `number` | `with_min` / `with_max` / `with_step` |
| `FieldDef::toggle` | `toggle` | `default_value` は文字列 `"true"` / `"false"` です |
| `FieldDef::dropdown` | `dropdown` | `(value, label)` のペアから構築されます |
| `FieldDef::hotkey` | `hotkey_recorder` | |
| `FieldDef::file_picker` | `file_picker` | |

チェーン可能なセッター: `with_placeholder`、`with_default`、
`with_description`、`with_min`、`with_max`、`with_step`、折りたたみ
可能なセクション用の `with_group(id, label)`、表示制御用の
`with_condition(field_id, operator, value)`。

`default_value` は、どの場合でもワイヤー上では**文字列**です — これは
JSON エンコードされたデフォルト値を運びます。そのため、数値のデフォルト
は `"440"` であり、トグルのデフォルトは `"true"` です。

両方のフックとも、3 つの SDK すべてで `Vec<FieldDef>` を返します;
Python と TypeScript の形は[それぞれの SDK ページ](../4-sdk/python.md)
にあります。

## 3 · アクションとトリガーのパラメータ

`GetPluginActionTypes` と `GetPluginTriggerTypes` は、あなたのプラグイン
がコマンドエディタに何を追加するかを記述しており、**起動時に一度だけ**
読まれます。変更には再起動が必要であり、それがこれらが計算されたもの
ではなく宣言的なものである理由です。

これらのパラメータフィールドは、上と同じ `FieldDef` の語彙を使います。

## ローカライゼーション

`label`、`placeholder`、`description` はリテラルではなく i18n キーで
あってもかまいません。SDK はプラグイン自身の文字列のために `I18n` を
同梱しており、`OnLanguageChanged` は UI の言語が変わったことを伝えて
くれるため、ユーザーに見えるものを何でも再描画できます。言語は最初の
瞬間からコンテキスト上にもあります: `ctx.language()`。
