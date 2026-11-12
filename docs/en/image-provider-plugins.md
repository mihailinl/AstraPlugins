# Image provider plugins

An image provider plugin declares `image_provider = true` in the
`[capabilities]` section of its `plugin.toml`. Astra then asks it for the
pictures the assistant's `generate_image` tool draws. **No Astra release asks
yet** (2026-11-13): the daemon side, Astra `21790d761`, is behind the
`plugin-provider-slots` build feature, and any other Astra never calls the hook.

Astra asks the plugin in two cases:

- **While it is the chat's AI provider.** A plugin that declares both
  `ai_provider` and `image_provider` and is the provider of the Chat role
  (**AI → Chat model** — not a model one conversation is pinned to, and not the
  Work model) is asked FIRST. The person's own image provider (**AI → Image
  generation**) is the fallback; their settings are never rewritten.
- **When the person chose it as the image provider.** The choice is stored as
  `plugin__<plugin id>` with hyphens turned into underscores —
  `plugin__my_painter` — as for the TTS and STT provider ids, and unlike web
  search's. The AI page's picker lists AI providers only, so a plugin that
  draws and is not also an AI provider cannot be picked there yet.

The capability is one required hook, `ImageGenerate` — one prompt in, one
picture or a refusal out — and one optional hook, `ImageGetModels`.

## What Astra does, so the plugin does not

- **The chain.** When your plugin refuses or fails, Astra tries the next
  provider on its own — unless the prompt itself was declined. Your plugin never
  calls another image service.
- **Counting.** Astra asks for ONE picture per call. A person who asked for four
  costs four calls, and Astra stops at the first that fails.
- **Saving and showing.** Astra saves the picture, shows it in the chat and
  tells the model where it is. Return the bytes; never a URL or a path.
- **Checking.** The picture is checked by its own bytes: PNG, JPEG or WEBP.
  Anything else is refused however it is labelled, and so is an empty one.
- **The words.** `error_message` and `caption` reach the model as one line of a
  stranger's text, sanitised.

## Start a provider

<!-- doctest: cli -->
```bash
astra-plugin new my-painter --lang python --template blank --capabilities image_provider --output ./my-painter
```

`--lang` may also be `rust` or `typescript`. There is no image template: the
capability arrives through `--capabilities`, and the scaffold's hook answers
`not_configured` until you implement it. `astra-plugin test` calls
`ImageGenerate` with a real prompt and `ImageGetModels`; a refusal passes,
because it is an answer.

`[capabilities]` is a closed set, so an Astra that does not know
`image_provider` refuses the whole manifest. No release knows it yet, so there
is no `min_astra_version` to name; add one when a release ships the capability.
Keep the provider's API key in the plugin's own `[config]` schema, where the
person sets it on the Plugins page:

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

## The request

| Field | Value |
|---|---|
| `prompt` | What to draw, as the model wrote it |
| `aspect_ratio` | `""` for the model's own default, or one of `1:1`, `16:9`, `9:16`, `4:3`, `3:4`. Draw at your default when your API cannot express it |
| `model` | The model the person chose — an id from your `ImageGetModels` list, or typed — and `""` for your default |
| `input_images` | The pictures the person attached to edit or draw from, bytes as they are. Empty unless the model is one your list marks `accepts_input_images` |

## The answer

Exactly one picture — PNG, JPEG or WEBP bytes, with any text the model wrote
beside it as the `caption` — or a refusal. **A refusal is an answer, not an
error.** Return it; do not raise or throw it:

| `error_code` | When | What Astra does |
|---|---|---|
| `quota` | The account's allowance is spent | Tries the next provider; tells the model the allowance is spent, in your words |
| `rate_limited` | Too many pictures right now; set `retry_after_secs` when the API says how long | Tries the next provider; tells the model to wait |
| `not_configured` | A setting the person has to make is missing — usually the key | Tries the next provider; tells the model the provider is not set up |
| `unavailable` | Anything else: the service is down, the network failed, the answer was unreadable | Tries the next provider |
| `refused` | The prompt itself was declined — a safety filter, a soft refusal | Tries nothing else: another provider would be asked the same prompt |

`error_message` is short, plain English: the model reads it. An `error_code`
outside these five is read as `unavailable`. An answer with neither a picture
nor a code is read as a declined prompt, so nothing else is tried — every SDK
refuses to send one. Astra does not yet wait out `retry_after_secs` for a
picture; it is on the wire for when it does.

What is NOT an answer: a raised exception, a thrown error or a Rust `Err`
reaches Astra as a failed call, which it reads as this plugin failing, and moves
on to the next provider — so a refusal you meant, raised instead of returned,
loses its code. A plugin that declares `image_provider` and does not implement
the hook answers `UNIMPLEMENTED`, which Astra reports as a provider that is not
set up.

Astra waits for one picture the smaller of `plugin.call_timeout_secs` (120
seconds when unset) and its own ceiling: 150 seconds, or 55 while the chat runs
on Astra AI, whose server stops waiting for a tool at 60. Give the request to
your service a timeout inside that, and answer `unavailable` when it fires.

## Models, and editing a picture

`ImageGetModels` is optional. It lists the models the picker offers — an `id`,
a `name`, and whether the model takes pictures to edit (`accepts_input_images`)
— and the `default_model` used when the person names none (`""` = the first).
Astra drops a model whose id is empty, longer than 200 characters or carries a
control character, and ignores a `default_model` that is not in the list.

It is also how Astra decides whether to send a picture. When the person attached
pictures and asked for an edit, Astra first asks `ImageGetModels`, takes the
model the person chose (else `default_model`, else the first), and sends ALL the
pictures in `input_images` only when that model is listed with
`accepts_input_images`. Otherwise it tells the model this provider cannot edit
and tries the next. A plugin with no list is never sent a picture to edit.

## Rust

`image_generate` on `PluginCapability` (or as a `#[hook]` inside
`#[astra::plugin]`) takes an `ImageRequest` and returns
`anyhow::Result<ImageResponse>`. `ImageResponse::drawn(bytes)` reads the
picture's type from its bytes; `.with_caption(text)` adds the caption.
`ImageResponse::refuse(ImageErrorCode::…, message)` builds a refusal, and
`.with_retry_after(secs)` goes on a `RateLimited` one. `image_models` returns
`(models, default_model)`; `ImageModelInfo::new(id, name).accepts_input_images()`
marks a model that edits. The stand-in function below is where your HTTP client
goes — the SDK does not ship one.

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

Override `image_generate(self, request)` on `Plugin`. It receives an
`ImageRequest` and returns an `ImageResponse` — or the picture's bytes, which
means it was drawn. `ImageResponse.drawn(data, caption=…)` reads the type from
the bytes; `ImageResponse.refuse(code, message, retry_after_secs=0)` checks the
code, so a typo fails in your own test. `image_get_models(self)` returns an
`ImageModelList`, or a `(models, default_model)` tuple. Blocking I/O belongs on
a thread (`asyncio.to_thread`): the hook shares its event loop with every other
hook the plugin serves.

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

Give `plugin({...})` an `image` section — `generate(req, ctx)` and, optionally,
`models` (a list, or `(ctx) => list`) — or override `imageGenerate(req)` and
`imageGetModels()` on a `Plugin` subclass. Build the answer with
`ImageGeneration.drawn(bytes, { caption })`, which reads the type from the
bytes, or `ImageGeneration.refuse(code, message, retryAfterSecs)`; `generate`
may also return the bytes.

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

## Testing

Each SDK's level-1 harness drives the hooks through the same wire projection
Astra sees — one picture, or the refusal in the body:

| SDK | Call | Returns |
|---|---|---|
| Rust | `running.image_generate(ImageRequest::new(..))`, `running.image_models()` | the hook's `ImageResponse`; its `(models, default_model)` |
| Python | `harness.image_generate(prompt, aspect_ratio=…, model=…, input_images=…)`, `harness.image_models()` | an `ImageResponse` read back off the wire; an `ImageModelList` |
| TypeScript | `harness.imageGenerate(prompt, { aspectRatio, model, inputImages })`, `harness.imageGetModels()` | an `ImageResponse` read back off the wire; an `ImageModelList` |

The harness sends `input_images` whatever your list says; choosing who receives
them is Astra's part. `astra-plugin test` asks for one real picture, allowed 60
seconds, and fails on what Astra would misread or refuse: an `error_code`
outside the five, an answer with neither a picture nor a code, more than one
picture, or a picture that is not PNG, JPEG or WEBP by its bytes. It reads the
model list the way Astra admits it. Then sideload with `astra-plugin dev` into
an Astra built with `plugin-provider-slots`.
