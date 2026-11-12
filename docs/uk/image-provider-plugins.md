# Плагіни генерації зображень

> Переклад. Джерело істини — [docs/en](../en/image-provider-plugins.md); за розбіжності відповідає англійська версія.

Плагін генерації зображень оголошує `image_provider = true` в розділі
`[capabilities]` свого `plugin.toml`. Тоді Astra запитує в нього
зображення, які малює інструмент асистента `generate_image`. **Жоден
випуск Astra поки не запитує** (2026-11-13): сторона демона, Astra
`21790d761`, перебуває за build feature `plugin-provider-slots`, а
будь-яка інша Astra ніколи не викликає цей хук.

Astra звертається до плагіна у двох випадках:

- **Поки він — AI-провайдер чату.** Плагін, що оголошує і `ai_provider`,
  і `image_provider` та є провайдером, з яким людина зараз спілкується,
  запитується ПЕРШИМ. Власний провайдер зображень людини (**AI →
  Генерація зображень**) слугує запасним варіантом; її налаштування
  ніколи не переписуються.
- **Коли людина вибрала його провайдером зображень.** Вибір зберігається
  як `plugin__<id плагіна>` з дефісами, перетвореними на підкреслення, —
  `plugin__my_painter`, — як для id провайдерів TTS і STT і на відміну
  від id провайдерів веброзшуку. Список вибору на сторінці AI показує
  лише AI-провайдерів, тож плагін, який малює, але не є ще й
  AI-провайдером, поки не можна вибрати там.

Capability — це один обов'язковий хук, `ImageGenerate` — один промпт
входить, одне зображення або відмова виходить, — і один необов'язковий
хук, `ImageGetModels`.

## Що робить Astra, щоб цього не робив плагін

- **Ланцюжок.** Коли ваш плагін відмовляє або збоїть, Astra сама пробує
  наступний провайдер — якщо тільки не було відхилено сам промпт. Ваш
  плагін ніколи не викликає інший сервіс зображень.
- **Лічба.** Astra просить ОДНЕ зображення за виклик. Людина, яка
  попросила чотири, коштує чотирьох викликів, і Astra зупиняється на
  першому невдалому.
- **Збереження і показ.** Astra зберігає зображення, показує його в чаті
  й повідомляє моделі, де воно лежить. Повертайте байти; ніколи не URL і
  не шлях.
- **Перевірка.** Зображення перевіряється за його власними байтами: PNG,
  JPEG або WEBP. Усе інше відхиляється, хоч би як воно було позначене, як
  і порожнє.
- **Слова.** `error_message` і `caption` доходять до моделі як один
  очищений рядок чужого тексту.

## Створіть провайдер

<!-- doctest: cli -->
```bash
astra-plugin new my-painter --lang python --template blank --capabilities image_provider --output ./my-painter
```

`--lang` також може бути `rust` або `typescript`. Шаблону для зображень
немає: capability приходить через `--capabilities`, і хук заготовки
відповідає `not_configured`, доки ви його не реалізуєте.
`astra-plugin test` викликає `ImageGenerate` зі справжнім промптом і
`ImageGetModels`; відмова проходить перевірку, бо це відповідь.

`[capabilities]` — закритий набір, тож Astra, яка не знає
`image_provider`, відхиляє весь маніфест. Жоден випуск його поки не
знає, тож немає `min_astra_version`, який можна було б указати; додайте
його, коли випуск почне постачати цю capability. Зберігайте API-ключ
провайдера у власній схемі `[config]` плагіна, де людина задає його на
сторінці плагінів:

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

## Запит

| Поле | Значення |
|---|---|
| `prompt` | Що намалювати, як це написала модель |
| `aspect_ratio` | `""` — власне значення моделі за замовчуванням, або одне з `1:1`, `16:9`, `9:16`, `4:3`, `3:4`. Малюйте з вашим значенням за замовчуванням, якщо ваш API не може це виразити |
| `model` | Модель, яку вибрала людина, — id з вашого списку `ImageGetModels` або введений вручну — і `""` для вашої моделі за замовчуванням |
| `input_images` | Зображення, які людина додала, щоб їх відредагувати або малювати за ними, — байти як є. Порожньо, якщо тільки модель не з тих, що ваш список позначає `accepts_input_images` |

## Відповідь

Рівно одне зображення — байти PNG, JPEG або WEBP, з будь-яким текстом,
який модель написала поряд із ним, у `caption`, — або відмова. **Відмова
— це відповідь, а не помилка.** Повертайте її; не піднімайте і не
кидайте:

| `error_code` | Коли | Що робить Astra |
|---|---|---|
| `quota` | Ліміт облікового запису витрачено | Пробує наступний провайдер; повідомляє моделі, що ліміт витрачено, вашими словами |
| `rate_limited` | Зараз надто багато зображень; вкажіть `retry_after_secs`, якщо API повідомляє, скільки чекати | Пробує наступний провайдер; каже моделі зачекати |
| `not_configured` | Відсутнє налаштування, яке має зробити людина, — зазвичай ключ | Пробує наступний провайдер; повідомляє моделі, що провайдер не налаштовано |
| `unavailable` | Усе інше: сервіс недоступний, мережа відмовила, відповідь нечитабельна | Пробує наступний провайдер |
| `refused` | Відхилено сам промпт — фільтр безпеки, м'яка відмова | Більше нічого не пробує: іншому провайдеру поставили б той самий промпт |

`error_message` короткий, простою англійською: його читає модель.
`error_code` поза цими п'ятьма читається як `unavailable`. Відповідь без
зображення і без коду читається як відхилений промпт, тож більше нічого
не пробується, — кожен SDK відмовляється таку надсилати. Astra поки не
вичікує `retry_after_secs` для зображення; поле є на проводі на той
випадок, коли почне.

Що НЕ є відповіддю: піднятий виняток, кинута помилка або Rust-`Err`
доходять до Astra як невдалий виклик, який вона читає як збій цього
плагіна, і переходить до наступного провайдера — тож відмова, яку ви
мали на увазі, але підняли замість того, щоб повернути, втрачає свій
код. Плагін, що оголошує `image_provider` і не реалізує хук, відповідає
`UNIMPLEMENTED`, що Astra повідомляє як неналаштованого провайдера.

Astra чекає одне зображення не довше за менше з
`plugin.call_timeout_secs` (120 секунд, якщо не задано) і власної
стелі: 150 секунд, або 55, поки чат працює на Astra AI, чий сервер
перестає чекати інструмент через 60. Дайте запиту до вашого сервісу
тайм-аут у цих межах і відповідайте `unavailable`, коли він спрацює.

## Моделі та редагування зображення

`ImageGetModels` необов'язковий. Він перелічує моделі, які пропонує
список вибору, — `id`, `name` і те, чи приймає модель зображення для
редагування (`accepts_input_images`), — і `default_model`, що
використовується, коли людина не назвала жодної (`""` = перша). Astra
відкидає модель, чий id порожній, довший за 200 символів або містить
керувальний символ, і ігнорує `default_model`, якого немає в списку.

Саме за ним Astra вирішує, чи надсилати зображення. Коли людина додала
зображення і попросила їх відредагувати, Astra спершу питає
`ImageGetModels`, бере модель, яку вибрала людина (інакше
`default_model`, інакше першу), і надсилає ВСІ зображення в
`input_images`, лише якщо ця модель указана в списку з
`accepts_input_images`. Інакше вона повідомляє моделі, що цей провайдер
не вміє редагувати, і пробує наступний. Плагіну без списку зображення
для редагування ніколи не надсилається.

## Rust

`image_generate` у `PluginCapability` (або як `#[hook]` усередині
`#[astra::plugin]`) приймає `ImageRequest` і повертає
`anyhow::Result<ImageResponse>`. `ImageResponse::drawn(bytes)` визначає
тип зображення за його байтами; `.with_caption(text)` додає підпис.
`ImageResponse::refuse(ImageErrorCode::…, message)` будує відмову, а
`.with_retry_after(secs)` додається до відмови `RateLimited`.
`image_models` повертає `(models, default_model)`;
`ImageModelInfo::new(id, name).accepts_input_images()` позначає модель,
що редагує. Функція-заглушка нижче — це місце для вашого HTTP-клієнта:
SDK його не постачає.

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

Перевизначте `image_generate(self, request)` у `Plugin`. Він отримує
`ImageRequest` і повертає `ImageResponse` — або байти зображення, що
означає, що його намальовано. `ImageResponse.drawn(data, caption=…)`
визначає тип за байтами;
`ImageResponse.refuse(code, message, retry_after_secs=0)` перевіряє код,
тож помилка в написанні не пройде у вашому власному тесті.
`image_get_models(self)` повертає `ImageModelList` або кортеж
`(models, default_model)`. Блокувальний I/O має йти в окремому потоці
(`asyncio.to_thread`): цей хук ділить свій цикл подій із кожним іншим
хуком, який обслуговує плагін.

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

Дайте `plugin({...})` розділ `image` — `generate(req, ctx)` і, за
бажанням, `models` (список або `(ctx) => list`), — або перевизначте
`imageGenerate(req)` і `imageGetModels()` у підкласі `Plugin`. Зберіть
відповідь за допомогою `ImageGeneration.drawn(bytes, { caption })`, який
визначає тип за байтами, або
`ImageGeneration.refuse(code, message, retryAfterSecs)`; `generate` може
також повернути байти.

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

## Тестування

Харнес рівня 1 кожного SDK проганяє хуки через ту саму проєкцію на
провід, яку бачить Astra, — одне зображення або відмову в тілі:

| SDK | Виклик | Повертає |
|---|---|---|
| Rust | `running.image_generate(ImageRequest::new(..))`, `running.image_models()` | `ImageResponse` хука; його `(models, default_model)` |
| Python | `harness.image_generate(prompt, aspect_ratio=…, model=…, input_images=…)`, `harness.image_models()` | `ImageResponse`, прочитаний назад із проводу; `ImageModelList` |
| TypeScript | `harness.imageGenerate(prompt, { aspectRatio, model, inputImages })`, `harness.imageGetModels()` | `ImageResponse`, прочитаний назад із проводу; `ImageModelList` |

Харнес надсилає `input_images`, хоч би що казав ваш список; вирішувати,
хто їх отримує, — справа Astra. `astra-plugin test` просить одне
справжнє зображення, дає на це 60 секунд і падає на тому, що Astra
прочитала б неправильно або відхилила: `error_code` поза цими п'ятьма,
відповідь без зображення і без коду, більше одного зображення або
зображення, яке за своїми байтами не є PNG, JPEG чи WEBP. Він читає
список моделей так, як його приймає Astra. Потім підвантажте плагін
через `astra-plugin dev` в Astra, зібрану з `plugin-provider-slots`.
