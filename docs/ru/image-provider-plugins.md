# Плагины генерации изображений

> Перевод. Источник истины — [docs/en](../en/image-provider-plugins.md); при расхождении верна английская версия.

Плагин генерации изображений объявляет `image_provider = true` в разделе
`[capabilities]` своего `plugin.toml`. Тогда Astra запрашивает у него
картинки, которые рисует инструмент ассистента `generate_image`. **Ни один
выпуск Astra пока не запрашивает** (2026-11-13): сторона демона, Astra
`21790d761`, находится за build feature `plugin-provider-slots`, а любая
другая Astra никогда не вызывает этот хук.

Astra обращается к плагину в двух случаях:

- **Пока он — AI-провайдер чата.** Плагин, который объявляет и
  `ai_provider`, и `image_provider` и является провайдером, с которым
  человек сейчас общается, спрашивается ПЕРВЫМ. Собственный провайдер
  изображений человека (**AI → Генерация изображений**) служит запасным
  вариантом; его настройки никогда не переписываются.
- **Когда человек выбрал его провайдером изображений.** Выбор хранится как
  `plugin__<id плагина>` с дефисами, превращёнными в подчёркивания, —
  `plugin__my_painter`, — как у id провайдеров TTS и STT и в отличие от
  id провайдеров веб-поиска. Список выбора на странице AI показывает
  только AI-провайдеров, так что плагин, который рисует, но не является
  ещё и AI-провайдером, пока нельзя выбрать там.

Capability — это один обязательный хук, `ImageGenerate` — один промпт
входит, одна картинка или отказ выходит, — и один необязательный хук,
`ImageGetModels`.

## Что делает Astra, чтобы этого не делал плагин

- **Цепочка.** Когда ваш плагин отказывает или сбоит, Astra сама пробует
  следующего провайдера — если только не был отклонён сам промпт. Ваш
  плагин никогда не вызывает другой сервис изображений.
- **Счёт.** Astra просит ОДНУ картинку за вызов. Человек, попросивший
  четыре, стоит четырёх вызовов, и Astra останавливается на первом
  неудачном.
- **Сохранение и показ.** Astra сохраняет картинку, показывает её в чате и
  сообщает модели, где она лежит. Возвращайте байты; никогда не URL и не
  путь.
- **Проверка.** Картинка проверяется по её собственным байтам: PNG, JPEG
  или WEBP. Всё остальное отклоняется, как бы оно ни было помечено, как и
  пустая картинка.
- **Слова.** `error_message` и `caption` доходят до модели как одна
  очищенная строка чужого текста.

## Создайте провайдер

<!-- doctest: cli -->
```bash
astra-plugin new my-painter --lang python --template blank --capabilities image_provider --output ./my-painter
```

`--lang` также может быть `rust` или `typescript`. Шаблона для изображений
нет: capability приходит через `--capabilities`, и хук заготовки отвечает
`not_configured`, пока вы его не реализуете. `astra-plugin test` вызывает
`ImageGenerate` с настоящим промптом и `ImageGetModels`; отказ проходит
проверку, потому что это ответ.

`[capabilities]` — закрытый набор, поэтому Astra, которая не знает
`image_provider`, отклоняет весь манифест. Ни один выпуск его пока не
знает, так что нет `min_astra_version`, который можно было бы указать;
добавьте его, когда выпуск начнёт поставлять эту capability. Храните
API-ключ провайдера в собственной схеме `[config]` плагина, где человек
задаёт его на странице плагинов:

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

## Запрос

| Поле | Значение |
|---|---|
| `prompt` | Что нарисовать, как это написала модель |
| `aspect_ratio` | `""` — собственное значение модели по умолчанию, либо одно из `1:1`, `16:9`, `9:16`, `4:3`, `3:4`. Рисуйте с вашим значением по умолчанию, если ваш API не может это выразить |
| `model` | Модель, которую выбрал человек, — id из вашего списка `ImageGetModels` или введённый вручную — и `""` для вашей модели по умолчанию |
| `input_images` | Картинки, которые человек приложил, чтобы их отредактировать или рисовать по ним, — байты как есть. Пусто, если только модель не из тех, что ваш список помечает `accepts_input_images` |

## Ответ

Ровно одна картинка — байты PNG, JPEG или WEBP, с любым текстом, который
модель написала рядом с ней, в `caption`, — либо отказ. **Отказ — это
ответ, а не ошибка.** Возвращайте его; не поднимайте и не бросайте:

| `error_code` | Когда | Что делает Astra |
|---|---|---|
| `quota` | Лимит аккаунта исчерпан | Пробует следующего провайдера; сообщает модели, что лимит исчерпан, вашими словами |
| `rate_limited` | Сейчас слишком много картинок; укажите `retry_after_secs`, если API сообщает, сколько ждать | Пробует следующего провайдера; говорит модели подождать |
| `not_configured` | Отсутствует настройка, которую должен сделать человек, — обычно ключ | Пробует следующего провайдера; сообщает модели, что провайдер не настроен |
| `unavailable` | Всё остальное: сервис недоступен, сеть отказала, ответ не читается | Пробует следующего провайдера |
| `refused` | Отклонён сам промпт — фильтр безопасности, мягкий отказ | Больше ничего не пробует: другому провайдеру задали бы тот же промпт |

`error_message` короткий, на простом английском: его читает модель.
`error_code` вне этих пяти читается как `unavailable`. Ответ без картинки
и без кода читается как отклонённый промпт, так что больше ничего не
пробуется, — каждый SDK отказывается такой отправлять. Astra пока не
выжидает `retry_after_secs` для картинки; поле есть на проводе на тот
случай, когда начнёт.

Что НЕ является ответом: поднятое исключение, брошенная ошибка или
Rust-`Err` доходят до Astra как неудавшийся вызов, который она читает как
сбой этого плагина, и переходит к следующему провайдеру — так что отказ,
который вы имели в виду, но подняли вместо того, чтобы вернуть, теряет
свой код. Плагин, который объявляет `image_provider` и не реализует хук,
отвечает `UNIMPLEMENTED`, что Astra сообщает как ненастроенного
провайдера.

Astra ждёт одну картинку не дольше меньшего из `plugin.call_timeout_secs`
(120 секунд, если не задано) и собственного потолка: 150 секунд, или 55,
пока чат работает на Astra AI, чей сервер перестаёт ждать инструмент через
60. Дайте запросу к вашему сервису тайм-аут в этих пределах и отвечайте
`unavailable`, когда он срабатывает.

## Модели и редактирование картинки

`ImageGetModels` необязателен. Он перечисляет модели, которые предлагает
список выбора, — `id`, `name` и то, принимает ли модель картинки для
редактирования (`accepts_input_images`), — и `default_model`, который
используется, когда человек не назвал никакую (`""` = первая). Astra
отбрасывает модель, чей id пуст, длиннее 200 символов или содержит
управляющий символ, и игнорирует `default_model`, которого нет в списке.

По нему же Astra решает, отправлять ли картинку. Когда человек приложил
картинки и попросил их отредактировать, Astra сначала спрашивает
`ImageGetModels`, берёт модель, которую выбрал человек (иначе
`default_model`, иначе первую), и отправляет ВСЕ картинки в
`input_images`, только если эта модель указана в списке с
`accepts_input_images`. Иначе она сообщает модели, что этот провайдер не
умеет редактировать, и пробует следующего. Плагину без списка картинка
для редактирования никогда не отправляется.

## Rust

`image_generate` в `PluginCapability` (или как `#[hook]` внутри
`#[astra::plugin]`) принимает `ImageRequest` и возвращает
`anyhow::Result<ImageResponse>`. `ImageResponse::drawn(bytes)` определяет
тип картинки по её байтам; `.with_caption(text)` добавляет подпись.
`ImageResponse::refuse(ImageErrorCode::…, message)` строит отказ, а
`.with_retry_after(secs)` добавляется к отказу `RateLimited`.
`image_models` возвращает `(models, default_model)`;
`ImageModelInfo::new(id, name).accepts_input_images()` помечает модель,
которая редактирует. Функция-заглушка ниже — это место для вашего
HTTP-клиента: SDK его не поставляет.

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

Переопределите `image_generate(self, request)` в `Plugin`. Он получает
`ImageRequest` и возвращает `ImageResponse` — либо байты картинки, что
означает, что она нарисована. `ImageResponse.drawn(data, caption=…)`
определяет тип по байтам;
`ImageResponse.refuse(code, message, retry_after_secs=0)` проверяет код,
так что опечатка не пройдёт в вашем собственном тесте.
`image_get_models(self)` возвращает `ImageModelList` или кортеж
`(models, default_model)`. Блокирующий I/O должен идти в отдельном потоке
(`asyncio.to_thread`): этот хук делит свой event loop с каждым другим
хуком, который обслуживает плагин.

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

Дайте `plugin({...})` раздел `image` — `generate(req, ctx)` и, по
желанию, `models` (список или `(ctx) => list`), — либо переопределите
`imageGenerate(req)` и `imageGetModels()` в подклассе `Plugin`. Соберите
ответ с помощью `ImageGeneration.drawn(bytes, { caption })`, который
определяет тип по байтам, или
`ImageGeneration.refuse(code, message, retryAfterSecs)`; `generate` может
также вернуть байты.

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

## Тестирование

Харнесс уровня 1 каждого SDK прогоняет хуки через ту же проекцию на
провод, которую видит Astra, — одна картинка или отказ в теле:

| SDK | Вызов | Возвращает |
|---|---|---|
| Rust | `running.image_generate(ImageRequest::new(..))`, `running.image_models()` | `ImageResponse` хука; его `(models, default_model)` |
| Python | `harness.image_generate(prompt, aspect_ratio=…, model=…, input_images=…)`, `harness.image_models()` | `ImageResponse`, прочитанный обратно с провода; `ImageModelList` |
| TypeScript | `harness.imageGenerate(prompt, { aspectRatio, model, inputImages })`, `harness.imageGetModels()` | `ImageResponse`, прочитанный обратно с провода; `ImageModelList` |

Харнесс отправляет `input_images`, что бы ни говорил ваш список; решать,
кто их получает, — дело Astra. `astra-plugin test` просит одну настоящую
картинку, даёт на это 60 секунд и падает на том, что Astra прочитала бы
неверно или отклонила: `error_code` вне этих пяти, ответ без картинки и
без кода, больше одной картинки или картинка, которая по своим байтам не
PNG, JPEG или WEBP. Он читает список моделей так, как его принимает
Astra. Затем подгрузите плагин с `astra-plugin dev` в Astra, собранную с
`plugin-provider-slots`.
