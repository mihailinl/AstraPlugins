> **これは翻訳です。** 正式な情報源は [docs/en](../en/image-provider-plugins.md) です。内容に食い違いがある場合は英語版が優先されます。


# 画像プロバイダープラグイン

画像プロバイダープラグインは、`plugin.toml` の `[capabilities]` セクションで
`image_provider = true` を宣言します。すると Astra は、アシスタントの
`generate_image` ツールが描く画像をそのプラグインに求めます。**これを行う
Astra のリリースはまだありません** (2026-11-13): デーモン側である Astra
`21790d761` は `plugin-provider-slots` ビルドフィーチャーの背後にあり、
それ以外の Astra がこのフックを呼ぶことはありません。

Astra がプラグインに求めるのは、次の 2 つの場合です:

- **それがチャットの AI プロバイダーである間。** `ai_provider` と
  `image_provider` の両方を宣言し、かつユーザーが会話している相手の
  プロバイダーであるプラグインは、**最初に**求められます。ユーザー自身の
  画像プロバイダー (**AI → 画像生成**) はフォールバックになり、ユーザーの
  設定が書き換えられることはありません。
- **ユーザーがそれを画像プロバイダーとして選んだとき。** その選択は、
  ハイフンをアンダースコアに変えた `plugin__<plugin id>` として保存されます —
  `plugin__my_painter`。これは TTS と STT のプロバイダー id と同じで、
  Web 検索のものとは異なります。AI ページのピッカーは AI プロバイダーしか
  一覧にしないため、画像を描くが AI プロバイダーではないプラグインは、
  まだそこでは選べません。

この capability は、必須のフック `ImageGenerate` 一つ — 1 件のプロンプトが
入り、1 枚の画像か拒否が出ます — と、任意のフック `ImageGetModels` 一つです。

## プラグインがしなくてよいように Astra がすること

- **チェーン。** あなたのプラグインが拒否するか失敗すると、Astra は自分で
  次のプロバイダーを試します — プロンプトそのものが断られた場合を除いて。
  あなたのプラグインが別の画像サービスを呼び出すことはありません。
- **数え方。** Astra は 1 回の呼び出しで **1 枚**の画像を求めます。4 枚を
  頼んだユーザーには 4 回の呼び出しがかかり、Astra は最初に失敗したところで
  止まります。
- **保存と表示。** Astra は画像を保存し、チャットに表示し、それがどこに
  あるかをモデルに伝えます。バイト列を返してください。URL やパスは決して
  返さないでください。
- **検査。** 画像はそれ自身のバイト列で検査されます: PNG、JPEG、または
  WEBP。それ以外のものは、どうラベル付けされていても拒否され、空の画像も
  同様です。
- **言葉。** `error_message` と `caption` は、第三者が書いたテキスト 1 行
  として、無害化されたうえでモデルに届きます。

## プロバイダーを始める

<!-- doctest: cli -->
```bash
astra-plugin new my-painter --lang python --template blank --capabilities image_provider --output ./my-painter
```

`--lang` には `rust` や `typescript` も指定できます。画像用のテンプレートは
ありません: capability は `--capabilities` から付与され、scaffold のフックは
実装するまで `not_configured` を返します。`astra-plugin test` は実際の
プロンプトで `ImageGenerate` を呼び出し、`ImageGetModels` も呼び出します。
拒否は応答なのでテストに通ります。

`[capabilities]` は閉じた集合なので、`image_provider` を知らない Astra は
マニフェスト全体を拒否します。それを知っているリリースはまだないため、
指定すべき `min_astra_version` もありません。この capability を含むリリースが
出たら追加してください。プロバイダーの API キーはプラグイン自身の
`[config]` スキーマに保持してください。ユーザーはそれを Plugins ページで
設定します:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "my-painter"
name = "My Painter"
version = "0.1.0"
description = "Pictures through Example Images"
author = "You"
license = "MIT"

[entry]
command = "python"
args = ["-u", "-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
image_provider = true

[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "format": "password",
      "default": "",
      "title": "API key",
      "description": "Your Example Images key"
    }
  }
}
"""
```

## リクエスト

| フィールド | 値 |
|---|---|
| `prompt` | 何を描くか。モデルが書いたとおり |
| `aspect_ratio` | モデル自身のデフォルトなら `""`、または `1:1`、`16:9`、`9:16`、`4:3`、`3:4` のいずれか。API で表現できない場合は、あなたのデフォルトで描いてください |
| `model` | ユーザーが選んだモデル — あなたの `ImageGetModels` のリストにある id、または手入力されたもの — で、あなたのデフォルトなら `""` |
| `input_images` | ユーザーが編集や描画の元として添付した画像。バイト列はそのまま。モデルがあなたのリストで `accepts_input_images` と印を付けたものでない限り、空です |

## レスポンス

ちょうど 1 枚の画像 — PNG、JPEG、または WEBP のバイト列で、モデルがその横に
書いたテキストがあれば `caption` として添えたもの — か、拒否のいずれかです。
**拒否は応答であり、エラーではありません。** raise や throw ではなく、
返してください:

| `error_code` | いつ | Astra がすること |
|---|---|---|
| `quota` | アカウントの許容量が尽きている | 次のプロバイダーを試す。許容量が尽きたことを、あなたの言葉でモデルに伝える |
| `rate_limited` | 今画像が多すぎる。API が長さを示すなら `retry_after_secs` を設定 | 次のプロバイダーを試す。モデルに待つよう伝える |
| `not_configured` | ユーザーが行うべき設定が欠けている — 通常はキー | 次のプロバイダーを試す。モデルにプロバイダーが未設定だと伝える |
| `unavailable` | それ以外すべて: サービスがダウン、ネットワーク失敗、応答が読めない | 次のプロバイダーを試す |
| `refused` | プロンプトそのものが断られた — 安全フィルター、ソフトな拒否 | ほかに何も試さない: 別のプロバイダーにも同じプロンプトを求めることになるため |

`error_message` は短い平易な英語です: モデルがそれを読みます。これら 5 つ
以外の `error_code` は `unavailable` として読まれます。画像もコードもない
応答は断られたプロンプトとして読まれるため、ほかに何も試されません — どの
SDK もそうした応答の送信を拒否します。Astra は画像について、まだ
`retry_after_secs` の経過を待ちません。これは、待つようになったときのために
ワイヤー上にあります。

応答で**ない**もの: 発生した例外、throw されたエラー、Rust の `Err` は、
失敗した呼び出しとして Astra に届き、Astra はそれをこのプラグインの失敗と
して読んで、次のプロバイダーに移ります — つまり意図した拒否を返す代わりに
raise してしまうと、そのコードは失われます。`image_provider` を宣言していて
フックを実装していないプラグインは `UNIMPLEMENTED` を返し、Astra はそれを
未設定のプロバイダーとして報告します。

Astra が 1 枚の画像を待つ時間は、`plugin.call_timeout_secs` (未設定なら 120
秒) と Astra 自身の上限のうち小さいほうです: 上限は 150 秒、またはチャットが
Astra AI で動いている間は 55 秒です。Astra AI のサーバーは 60 秒でツールを
待つのをやめるからです。サービスへのリクエストにはその範囲内のタイムアウトを
設定し、発火したら `unavailable` を返してください。

## モデルと、画像の編集

`ImageGetModels` は任意です。これはピッカーが提示するモデル — `id`、`name`、
そしてそのモデルが編集用の画像を受け取るかどうか (`accepts_input_images`)
— と、ユーザーが何も指定しないときに使われる `default_model` (`""` = 最初の
もの) を一覧にします。Astra は、id が空のモデル、200 文字より長いモデル、
制御文字を含むモデルを捨て、リストにない `default_model` は無視します。

これは、Astra が画像を送るかどうかを決める方法でもあります。ユーザーが画像を
添付して編集を頼んだとき、Astra はまず `ImageGetModels` に問い合わせ、
ユーザーが選んだモデル (なければ `default_model`、それもなければ最初のもの)
を取り、そのモデルが `accepts_input_images` 付きで一覧にある場合にだけ、
**すべての**画像を `input_images` で送ります。そうでなければ、この
プロバイダーは編集できないとモデルに伝え、次を試します。リストを持たない
プラグインに、編集用の画像が送られることはありません。

## Rust

`PluginCapability` の `image_generate` (または `#[astra::plugin]` 内の
`#[hook]`) は `ImageRequest` を受け取り、
`anyhow::Result<ImageResponse>` を返します。
`ImageResponse::drawn(bytes)` は画像の種類をそのバイト列から読み取り、
`.with_caption(text)` はキャプションを加えます。
`ImageResponse::refuse(ImageErrorCode::…, message)` は拒否を組み立て、
`RateLimited` の拒否には `.with_retry_after(secs)` を付けます。
`image_models` は `(models, default_model)` を返し、
`ImageModelInfo::new(id, name).accepts_input_images()` は編集できる
モデルに印を付けます。下のスタンドイン関数は、あなたの HTTP クライアントが
入る場所です — SDK はクライアントを同梱していません。

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;
use std::sync::Mutex;

/// Settings. `#[astra::config]` fills a missing field from `Default`, because
/// a fresh install's first config payload is `{}`.
#[astra::config]
#[derive(Default)]
struct Settings {
    api_key: String,
}

#[derive(Default)]
struct MyPainter {
    settings: Mutex<Settings>,
}

/// What your provider's API can say. Each variant maps onto one refusal code.
enum ApiError {
    Spent,
    TooFast { retry_after: u32 },
    Declined(String),
    Down(String),
}

/// Stands in for the HTTP call to your provider, so this sample runs. A real
/// one returns the bytes of the picture your API drew.
fn call_api(key: &str, req: &ImageRequest) -> Result<Vec<u8>, ApiError> {
    match key {
        "spent" => Err(ApiError::Spent),
        "fast" => Err(ApiError::TooFast { retry_after: 30 }),
        "down" => Err(ApiError::Down("HTTP 503".into())),
        _ if req.prompt.contains("forbidden") => {
            Err(ApiError::Declined("the safety filter declined the prompt".into()))
        }
        _ => Ok(vec![0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a]),
    }
}

#[astra::plugin]
impl MyPainter {
    /// Called on start and on every settings change.
    #[hook]
    async fn on_config(&self, _ctx: &PluginContext, cfg: Settings) {
        *self.settings.lock().unwrap() = cfg;
    }

    /// Draw one picture for the assistant's `generate_image` tool.
    #[hook]
    async fn image_generate(
        &self,
        _ctx: &PluginContext,
        req: ImageRequest,
    ) -> anyhow::Result<ImageResponse> {
        let key = self.settings.lock().unwrap().api_key.clone();
        if key.is_empty() {
            return Ok(ImageResponse::refuse(
                ImageErrorCode::NotConfigured,
                "set an API key in the plugin's settings",
            ));
        }
        Ok(match call_api(&key, &req) {
            Ok(picture) => ImageResponse::drawn(picture),
            Err(ApiError::Spent) => {
                ImageResponse::refuse(ImageErrorCode::Quota, "the plan's allowance is spent")
            }
            Err(ApiError::TooFast { retry_after }) => {
                ImageResponse::refuse(ImageErrorCode::RateLimited, "too many pictures")
                    .with_retry_after(retry_after)
            }
            Err(ApiError::Declined(why)) => ImageResponse::refuse(ImageErrorCode::Refused, why),
            Err(ApiError::Down(why)) => ImageResponse::refuse(
                ImageErrorCode::Unavailable,
                format!("the provider is down: {why}"),
            ),
        })
    }

    /// The models the picker offers. `edit-1` takes pictures to edit.
    #[hook]
    async fn image_models(
        &self,
        _ctx: &PluginContext,
    ) -> anyhow::Result<(Vec<ImageModelInfo>, String)> {
        Ok((
            vec![
                ImageModelInfo::new("draw-1", "Draw 1"),
                ImageModelInfo::new("edit-1", "Edit 1").accepts_input_images(),
            ],
            "draw-1".into(),
        ))
    }
}

astra::main!(MyPainter::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn no_key_is_a_refusal_not_an_error() {
        let h = Harness::new(MyPainter::default()).start().await.unwrap();
        let answer = h.image_generate(ImageRequest::new("a fox")).await.unwrap();
        assert!(matches!(
            answer,
            ImageResponse::Refused { code: ImageErrorCode::NotConfigured, .. }
        ));
    }

    #[tokio::test]
    async fn a_key_gets_one_png() {
        let h = Harness::new(MyPainter::default())
            .with_config(json!({ "api_key": "k" }))
            .start()
            .await
            .unwrap();
        let ImageResponse::Drawn { mime_type, .. } =
            h.image_generate(ImageRequest::new("a fox")).await.unwrap()
        else {
            panic!("expected a picture");
        };
        assert_eq!(mime_type, "image/png");
    }
}
```

## Python

`Plugin` の `image_generate(self, request)` をオーバーライドします。
`ImageRequest` を受け取り、`ImageResponse` — または描画されたことを意味する
画像のバイト列 — を返します。`ImageResponse.drawn(data, caption=…)` は
種類をバイト列から読み取り、
`ImageResponse.refuse(code, message, retry_after_secs=0)` はコードを検証する
ので、タイプミスは自分のテストで失敗します。`image_get_models(self)` は
`ImageModelList`、または `(models, default_model)` のタプルを返します。
ブロッキング I/O はスレッドに置いてください (`asyncio.to_thread`): この
フックは、プラグインが提供する他のすべてのフックとイベントループを共有
します。

<!-- doctest: python-plugin -->
```python
"""MyPainter — an image provider plugin."""

import asyncio
import base64
import json
import urllib.error
import urllib.request

from astra_plugin_sdk import (
    ImageErrorCode,
    ImageModelInfo,
    ImageModelList,
    ImageResponse,
    Plugin,
)

API = "https://api.example.com/images"


def call_api(key, prompt, aspect_ratio, model, timeout=90):
    body = json.dumps({"prompt": prompt, "aspect_ratio": aspect_ratio or "1:1", "model": model})
    req = urllib.request.Request(
        API,
        data=body.encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return base64.b64decode(json.load(response)["image_base64"])


class MyPainter(Plugin):
    """Pictures through Example Images."""

    async def image_generate(self, request):
        key = self.config.get("api_key", "")
        if not key:
            return ImageResponse.refuse(
                ImageErrorCode.NOT_CONFIGURED, "set an API key in the plugin's settings"
            )
        try:
            picture = await asyncio.to_thread(
                call_api, key, request.prompt, request.aspect_ratio, request.model
            )
        except urllib.error.HTTPError as e:
            if e.code == 402:
                return ImageResponse.refuse(ImageErrorCode.QUOTA, "the plan's allowance is spent")
            if e.code == 429:
                after = e.headers.get("Retry-After", "")
                retry = int(after) if after.isdigit() else 0  # an HTTP date says nothing usable here
                return ImageResponse.refuse(
                    ImageErrorCode.RATE_LIMITED, "too many pictures", retry_after_secs=retry
                )
            if e.code == 400 and "content_policy" in e.read().decode("utf-8", "replace"):
                # Only a refusal OF THE PROMPT is `refused`: Astra then asks no other provider.
                return ImageResponse.refuse(ImageErrorCode.REFUSED, "the prompt was declined")
            if e.code in (401, 403):
                return ImageResponse.refuse(ImageErrorCode.NOT_CONFIGURED, "the API key was refused")
            return ImageResponse.refuse(ImageErrorCode.UNAVAILABLE, f"HTTP {e.code}")
        except OSError as e:
            return ImageResponse.refuse(ImageErrorCode.UNAVAILABLE, f"network: {e}")
        return ImageResponse.drawn(picture)

    async def image_get_models(self):
        return ImageModelList(
            models=[
                ImageModelInfo("draw-1", "Draw 1"),
                ImageModelInfo("edit-1", "Edit 1", accepts_input_images=True),
            ],
            default_model="draw-1",
        )


def test_no_key_is_a_refusal_not_an_error():
    from astra_plugin_sdk.testing import Harness

    with Harness(MyPainter()) as h:
        answer = h.image_generate("a fox")
        models = h.image_models()
    assert answer.error_code == ImageErrorCode.NOT_CONFIGURED
    assert answer.data == b""
    assert [m.id for m in models.models if m.accepts_input_images] == ["edit-1"]


if __name__ == "__main__":
    MyPainter().run()
```

## TypeScript

`plugin({...})` に `image` セクション — `generate(req, ctx)` と、任意で
`models` (リスト、または `(ctx) => list`) — を与えるか、`Plugin` の
サブクラスで `imageGenerate(req)` と `imageGetModels()` をオーバーライド
してください。応答は、種類をバイト列から読み取る
`ImageGeneration.drawn(bytes, { caption })`、または
`ImageGeneration.refuse(code, message, retryAfterSecs)` で組み立てます。
`generate` はバイト列をそのまま返すこともできます。

<!-- doctest: ts-plugin -->
```typescript
import { plugin, ImageGeneration } from "astra-plugin-sdk";

export const app = plugin({
  image: {
    async generate(req, ctx) {
      const key = ctx.configValue<string>("api_key", "");
      if (!key) return ImageGeneration.refuse("not_configured", "set an API key in the plugin's settings");

      let res: Response;
      try {
        res = await fetch("https://api.example.com/images", {
          method: "POST",
          headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: req.prompt, aspect_ratio: req.aspectRatio || "1:1", model: req.model }),
          signal: AbortSignal.timeout(90_000),
        });
      } catch (e) {
        return ImageGeneration.refuse("unavailable", `network: ${String(e)}`);
      }
      if (res.status === 402) return ImageGeneration.refuse("quota", "the plan's allowance is spent");
      if (res.status === 429) {
        return ImageGeneration.refuse("rate_limited", "too many pictures", Number.parseInt(res.headers.get("retry-after") ?? "", 10) || 0);
      }
      if (res.status === 400 && (await res.clone().text()).includes("content_policy")) {
        // Only a refusal OF THE PROMPT is `refused`: Astra then asks no other provider.
        return ImageGeneration.refuse("refused", "the prompt was declined");
      }
      if (res.status === 401 || res.status === 403) return ImageGeneration.refuse("not_configured", "the API key was refused");
      if (!res.ok) return ImageGeneration.refuse("unavailable", `HTTP ${res.status}`);

      const body = (await res.json()) as { image_base64: string };
      return ImageGeneration.drawn(Buffer.from(body.image_base64, "base64"));
    },
    models: {
      models: [
        { id: "draw-1", name: "Draw 1" },
        { id: "edit-1", name: "Edit 1", acceptsInputImages: true },
      ],
      defaultModel: "draw-1",
    },
  },
});

if (require.main === module) app.run();
```

## テスト

各 SDK のレベル 1 ハーネスは、Astra が見るのと同じワイヤー上の投影を通して
フックを駆動します — 1 枚の画像、またはボディ内の拒否:

| SDK | 呼び出し | 戻り値 |
|---|---|---|
| Rust | `running.image_generate(ImageRequest::new(..))`、`running.image_models()` | フックの `ImageResponse`。フックの `(models, default_model)` |
| Python | `harness.image_generate(prompt, aspect_ratio=…, model=…, input_images=…)`、`harness.image_models()` | ワイヤーから読み戻した `ImageResponse`。`ImageModelList` |
| TypeScript | `harness.imageGenerate(prompt, { aspectRatio, model, inputImages })`、`harness.imageGetModels()` | ワイヤーから読み戻した `ImageResponse`。`ImageModelList` |

ハーネスは、あなたのリストが何を言おうと `input_images` を送ります。誰が
それを受け取るかを選ぶのは Astra の役割です。`astra-plugin test` は実際の
画像を 1 枚求めて 60 秒を与え、Astra が読み違えたり拒否したりする内容で
失敗します: 5 つ以外の `error_code`、画像もコードもない応答、2 枚以上の画像、
またはバイト列で見て PNG、JPEG、WEBP のいずれでもない画像。モデルのリストは、
Astra が受け入れるのと同じやり方で読みます。その後、
`plugin-provider-slots` 付きでビルドされた Astra に `astra-plugin dev` で
サイドロードしてください。
