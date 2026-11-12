> **本文档为翻译版本。** 权威来源是 [docs/en](../en/image-provider-plugins.md)。如与英文版有出入，以英文版为准。


# 图像提供方插件

图像提供方插件在其 `plugin.toml` 的 `[capabilities]` 部分声明
`image_provider = true`。Astra 随后会向它索取助手的 `generate_image`
工具所画的图片。**目前还没有任何 Astra 发行版会这样做**（2026-11-13）：
守护进程一侧，即 Astra `21790d761`，位于 `plugin-provider-slots` 构建
特性之后；其他任何 Astra 都不会调用这个钩子。

Astra 会在两种情况下向插件索取：

- **当它是聊天的 AI 提供方时。** 同时声明了 `ai_provider` 和
  `image_provider`、并且正是用户当前聊天所用提供方的插件，会被**首先**
  询问。用户自己的图像提供方（**AI → 图片生成**）作为备选；用户的设置
  永远不会被改写。
- **当用户把它选为图像提供方时。** 这一选择保存为 `plugin__<plugin id>`，
  连字符换成下划线——`plugin__my_painter`——与 TTS 和 STT 提供方的 id
  相同，而与网络搜索的不同。AI 页面的选择器只列出 AI 提供方，所以一个能
  画图但不同时是 AI 提供方的插件，目前还无法在那里被选中。

这个 capability 由一个必需的钩子 `ImageGenerate`——一个提示词进去，一张
图片或一次拒绝出来——和一个可选的钩子 `ImageGetModels` 组成。

## Astra 会替插件做的事

- **链条。** 当你的插件拒绝或失败时，Astra 会自行尝试下一个提供方——
  除非被拒绝的是提示词本身。你的插件永远不会调用另一个图像服务。
- **计数。** Astra 每次调用只要**一张**图片。一个要了四张图的用户要花
  四次调用，Astra 会在第一次失败处停下。
- **保存与展示。** Astra 会保存图片，在聊天中展示它，并告诉模型它在
  哪里。返回字节；永远不要返回 URL 或路径。
- **检查。** 图片按它自身的字节来检查：PNG、JPEG 或 WEBP。其他任何东西，
  无论贴着什么标签，都会被拒绝；空图片也一样。
- **文字。** `error_message` 和 `caption` 会作为一行陌生人写的文本到达
  模型，并经过净化。

## 创建提供方

<!-- doctest: cli -->
```bash
astra-plugin new my-painter --lang python --template blank --capabilities image_provider --output ./my-painter
```

`--lang` 也可以是 `rust` 或 `typescript`。没有图像模板：capability 通过
`--capabilities` 加入，脚手架的钩子在你实现之前都会回答 `not_configured`。
`astra-plugin test` 会用一个真实的提示词调用 `ImageGenerate`，并调用
`ImageGetModels`；拒绝也算通过，因为它是一个应答。

`[capabilities]` 是封闭集合，所以不认识 `image_provider` 的 Astra 会拒绝
整个清单。目前还没有哪个发行版认识它，因此也没有可写的
`min_astra_version`；等某个发行版带上这个 capability 时再加上。把提供方的
API 密钥保存在插件自己的 `[config]` schema 里，用户会在插件页面设置它：

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

## 请求

| 字段 | 值 |
|---|---|
| `prompt` | 要画什么，按模型写下的原样 |
| `aspect_ratio` | `""` 表示模型自己的默认值，或 `1:1`、`16:9`、`9:16`、`4:3`、`3:4` 之一。如果你的 API 无法表达它，就按你的默认值来画 |
| `model` | 用户选择的模型——来自你的 `ImageGetModels` 列表的 id，或手动输入的——`""` 表示你的默认值 |
| `input_images` | 用户附上、用于编辑或作为绘制依据的图片，字节原样提供。除非模型是你的列表中标记为 `accepts_input_images` 的那种，否则为空 |

## 应答

恰好一张图片——PNG、JPEG 或 WEBP 字节，如果模型在旁边写了文字，就作为
`caption` 附上——或者一次拒绝。**拒绝是一种应答，不是错误。** 把它返回；
不要 raise 或 throw 它：

| `error_code` | 何时 | Astra 会做什么 |
|---|---|---|
| `quota` | 账户额度已用完 | 尝试下一个提供方；用你的话告诉模型额度已用完 |
| `rate_limited` | 现在图片请求太多；如果 API 说明了要等多久，设置 `retry_after_secs` | 尝试下一个提供方；告诉模型要等待 |
| `not_configured` | 缺少用户必须完成的设置——通常是密钥 | 尝试下一个提供方；告诉模型提供方尚未配置 |
| `unavailable` | 其他任何情况：服务宕机、网络失败、应答无法解析 | 尝试下一个提供方 |
| `refused` | 提示词本身被拒绝——安全过滤器、软拒绝 | 不再尝试别的：另一个提供方也会被问到同一个提示词 |

`error_message` 简短、使用简单英语：模型会读它。这五个之外的 `error_code`
会被当作 `unavailable` 读取。既没有图片也没有代码的应答会被当作被拒绝的
提示词，因此不会再尝试别的——每个 SDK 都会拒绝发送这样的应答。Astra 目前
还不会为图片等到 `retry_after_secs` 结束；这个字段放在线上，是为它将来会
等待的时候准备的。

不算应答的情况：抛出的异常、throw 的错误，或 Rust 的 `Err`，都会以失败的
调用到达 Astra，Astra 会把它当作这个插件失败，并转到下一个提供方——所以
你本想表达的拒绝，一旦用 raise 而不是 return，就会丢失它的代码。声明了
`image_provider` 却没实现这个钩子的插件会应答 `UNIMPLEMENTED`，Astra 会把
它报告为未配置的提供方。

Astra 为一张图片等待的时间，取 `plugin.call_timeout_secs`（未设置时为 120
秒）与它自己的上限中较小的那个：上限为 150 秒，或者在聊天运行于 Astra AI
时为 55 秒，因为 Astra AI 的服务器等待一个工具的时间到 60 秒就会停止。给
发往你的服务的请求设置一个在此之内的超时，并在它触发时应答
`unavailable`。

## 模型，以及编辑图片

`ImageGetModels` 是可选的。它列出选择器提供的模型——`id`、`name`，以及
该模型是否接受要编辑的图片（`accepts_input_images`）——以及用户没有指定时
使用的 `default_model`（`""` = 第一个）。Astra 会丢弃 id 为空、长于 200
个字符或含有控制字符的模型，并忽略不在列表中的 `default_model`。

它也是 Astra 决定是否发送图片的依据。当用户附上了图片并要求编辑时，Astra
会先询问 `ImageGetModels`，取用户选择的模型（否则取 `default_model`，再
否则取第一个），并且只有当该模型在列表中带有 `accepts_input_images` 时，
才会把**所有**图片放进 `input_images` 发送。否则，它会告诉模型这个提供方
无法编辑，然后尝试下一个。没有列表的插件永远不会收到要编辑的图片。

## Rust

`PluginCapability` 上的 `image_generate`（或 `#[astra::plugin]` 内的
`#[hook]`）接收一个 `ImageRequest`，返回
`anyhow::Result<ImageResponse>`。`ImageResponse::drawn(bytes)` 从字节中
读出图片的类型；`.with_caption(text)` 加上说明文字。
`ImageResponse::refuse(ImageErrorCode::…, message)` 构造一次拒绝，
`.with_retry_after(secs)` 加在 `RateLimited` 的拒绝上。`image_models`
返回 `(models, default_model)`；
`ImageModelInfo::new(id, name).accepts_input_images()` 标记一个能编辑的
模型。下面这个占位函数就是你的 HTTP 客户端该放的地方——SDK 本身不附带
一个。

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

重写 `Plugin` 上的 `image_generate(self, request)`。它接收一个
`ImageRequest`，返回一个 `ImageResponse`——或图片的字节，表示图片已经
画好。`ImageResponse.drawn(data, caption=…)` 从字节中读出类型；
`ImageResponse.refuse(code, message, retry_after_secs=0)` 会检查 code，
所以写错在你自己的测试里就会失败。`image_get_models(self)` 返回一个
`ImageModelList`，或一个 `(models, default_model)` 元组。阻塞式 I/O 应该
放到线程里（`asyncio.to_thread`）：这个钩子与插件提供的每一个其他钩子共享
同一个事件循环。

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

给 `plugin({...})` 一个 `image` 部分——`generate(req, ctx)`，以及可选的
`models`（一个列表，或 `(ctx) => list`）——或者在 `Plugin` 子类上重写
`imageGenerate(req)` 和 `imageGetModels()`。用
`ImageGeneration.drawn(bytes, { caption })`（它从字节中读出类型）或
`ImageGeneration.refuse(code, message, retryAfterSecs)` 构造应答；
`generate` 也可以直接返回字节。

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

## 测试

每个 SDK 的一级 harness 都通过 Astra 所见的同一种线上投影来驱动这些
钩子——一张图片，或 body 里的拒绝：

| SDK | 调用 | 返回 |
|---|---|---|
| Rust | `running.image_generate(ImageRequest::new(..))`、`running.image_models()` | 钩子的 `ImageResponse`；它的 `(models, default_model)` |
| Python | `harness.image_generate(prompt, aspect_ratio=…, model=…, input_images=…)`、`harness.image_models()` | 从线上读回的 `ImageResponse`；一个 `ImageModelList` |
| TypeScript | `harness.imageGenerate(prompt, { aspectRatio, model, inputImages })`、`harness.imageGetModels()` | 从线上读回的 `ImageResponse`；一个 `ImageModelList` |

不管你的列表怎么说，harness 都会发送 `input_images`；选择谁来接收它们是
Astra 的事。`astra-plugin test` 会索取一张真实图片，给它 60 秒，并在 Astra
会误读或拒绝的情况下失败：五个之外的 `error_code`、既没有图片也没有代码的
应答、多于一张的图片，或按字节看不是 PNG、JPEG 或 WEBP 的图片。它按 Astra
接纳模型列表的方式来读取列表。然后用 `astra-plugin dev` 侧载到一个以
`plugin-provider-slots` 构建特性构建的 Astra 中。
