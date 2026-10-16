# Плагіни веброзшуку

> Переклад. Джерело істини — [docs/en](../en/web-search-plugins.md); за розбіжності відповідає англійська версія.

Плагін веброзшуку оголошує `web_search = true` в розділі `[capabilities]`
свого `plugin.toml`. Тоді Astra пропонує його під **AI → Веброзшук** як
провайдер для інструмента асистента `web_search` — як **провайдер
пошуку**, або як запасний варіант, **Якщо не може відповісти**, — поряд
із вбудованими провайдерами. Вибір користувача зберігається як
`plugin__<id плагіна>`, з id плагіна без змін: `plugin__duckduckgo-search`,
дефіс і все інше. Це відрізняється від id провайдерів TTS, STT і слова-
активатора, які перетворюють дефіси на підкреслення.

Уся ця capability — один хук, `WebSearch`: один запит входить, щонайбільше
`count` результатів — або відмова — виходить.

## Що робить Astra, щоб цього не робив плагін

Демон бере на себе все довкола викликy:

- **Ланцюжок провайдерів.** Користувач вибирає провайдер і запасний
  варіант. Коли ваш відмовляє, демон сам переходить до запасного; ваш
  плагін ніколи не викликає іншу пошукову систему.
- **Кеш.** Повторний запит може ніколи не дійти до вашого плагіна. Не
  додавайте власний кеш.
- **Огородження.** Результати доходять до моделі з позначкою як
  недовірений текст з вебу. Повертайте те, що каже джерело; ніколи не
  обгортайте це в інструкції для моделі.
- **Нормалізація.** З заголовків і фрагментів прибирається розмітка,
  результат, чий URL не `http` і не `https`, відкидається, а дата не
  вигляду `YYYY-MM-DD` читається як невідома.

Тож плагін відповідає на ОДИН запит, швидко, і прямо каже, коли не може.

## Створіть провайдер

<!-- doctest: cli -->
```bash
astra-plugin new my-search --lang python --template blank --capabilities web_search --output ./my-search
```

`--lang` також може бути `rust` або `typescript`. Шаблону веброзшуку
немає: capability приходить через `--capabilities`, і хук заготовки
відповідає `not_configured`, доки ви його не реалізуєте.
`astra-plugin test` викликає `WebSearch` зі справжнім запитом; відмова
проходить перевірку, бо це відповідь.

Вкажіть `min_astra_version`. `[capabilities]` — закритий набір, і Astra,
старша за ту, де з'явився `web_search` (0.2.7), відхилить увесь
маніфест; із цим рядком вона натомість скаже, що плагіну потрібна
новіша Astra. Зберігайте API-ключ провайдера у власній схемі `[config]`
плагіна. Astra показує його на сторінці плагінів, а сторінка AI каже,
що ключ там задано:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "my-search"
name = "My Search"
version = "0.1.0"
description = "Web search through Example Search"
author = "You"
license = "MIT"
min_astra_version = "0.2.7"

[entry]
command = "python"
args = ["-u", "-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
web_search = true

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
      "description": "Your Example Search key"
    }
  }
}
"""
```

Ключ живе там і лише там: не в змінній середовища, не у файлі, який
пише плагін, не в повідомленнях про помилку, які він повертає.

## Запит

| Поле | Значення |
|---|---|
| `query` | Що шукала модель, уже перевірено демоном |
| `count` | Скільки результатів повернути, від `1` до `10`. Менше — це нормально; кожен SDK урізає довшу відповідь до цієї довжини |
| `freshness` | `""` (без обмеження), `day`, `week`, `month` або `year`. SDK читають невідоме значення як `""` |
| `country` | ISO 3166-1 alpha-2, верхній регістр (`DE`), або порожньо |
| `language` | ISO 639-1, нижній регістр (`de`), або порожньо |

Відобразіть їх на свій API та ігноруйте те, що він не може виразити.

## Відповідь

Або результати — кожен із `title`, `url` (`http` чи `https`), текстовим
`snippet` і, якщо джерело датує сторінку, `published` у вигляді
`YYYY-MM-DD`, — або відмова. **Відмова — це відповідь, а не помилка.**
Повертайте її; не піднімайте і не кидайте:

| `error_code` | Коли | Що робить демон, окрім переходу до запасного варіанту |
|---|---|---|
| `quota` | Ліміт облікового запису витрачено; вкажіть `retry_after_secs`, якщо API повідомляє, коли він повернеться | Не питає цього провайдера протягом `retry_after_secs`, або 15 хвилин, якщо це `0` |
| `rate_limited` | Зараз надто багато запитів; вкажіть `retry_after_secs`, якщо API повідомляє, скільки чекати | Не питає протягом `retry_after_secs`, або 10 секунд, якщо це `0` |
| `auth` | Ключ відхилено | Повідомляє моделі, що ключ було відхилено |
| `not_configured` | Відсутнє налаштування, яке має зробити користувач — зазвичай ключ | Повідомляє моделі, що провайдер не налаштовано, з вашим повідомленням |
| `unavailable` | Усе інше: сервіс недоступний, мережа відмовила, відповідь нечитабельна | Повідомляє моделі, що провайдер недоступний, з вашим повідомленням |

Будь-яка відмова передає пошук запасному провайдеру користувача, якщо
він є. Що б не казав `retry_after_secs`, демон чекає не більше 15
хвилин. `error_message` короткий, простою англійською: модель читає
його як один рядок, поза огородженням недовіреного контенту, тому
токени шаблону чату й переноси рядків у ньому вилучаються. `error_code`
поза цими п'ятьма читається як `unavailable`. Пошук, що виконався і
нічого не знайшов, — це порожній список результатів, а не відмова.

Що НЕ є відповіддю: піднятий виняток, кинута помилка або Rust-`Err`
доходять до демона як невдалий RPC, який він повідомляє як
недоступність провайдера, з текстом помилки — тож відмова, яку ви мали
на увазі, але підняли замість того, щоб повернути, втрачає свій код.
Плагін, що оголошує `web_search` і не реалізує хук, відповідає
`UNIMPLEMENTED`, що демон повідомляє як неналаштованого провайдера.

Демон чекає не більше 30 секунд на один пошук — менше, якщо
`plugin.call_timeout_secs` нижчий, або якщо нижчий власний термін
моделі, — тож застряглий провайдер передає керування запасному
варіанту користувача в межах того самого ходу. Дайте HTTP-запиту
тайм-аут помітно коротший за це — 10–15 секунд — і відповідайте
`unavailable`, коли він спрацює. Демон також зберігає не більше
`count` ваших результатів.

## Rust

`web_search` у `PluginCapability` (або як `#[hook]` усередині
`#[astra::plugin]`) приймає `WebSearchRequest` і повертає
`anyhow::Result<WebSearchResponse>`. `WebSearchResponse::hits(...)` і
`WebSearchResponse::refuse(WebSearchErrorCode::…, message)` будують
відповідь; `.with_retry_after(secs)` додається до відмови
`RateLimited`. Функція-заглушка нижче — це місце для вашого HTTP-
клієнта: SDK його не постачає.

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
struct MySearch {
    settings: Mutex<Settings>,
}

/// What your provider's API can say. Each variant maps onto one refusal code.
enum ApiError {
    Spent,
    TooFast { retry_after: u32 },
    BadKey,
    Down(String),
}

/// Stands in for the HTTP call to your provider, so this sample runs.
fn call_api(key: &str, req: &WebSearchRequest) -> Result<Vec<(String, String, String)>, ApiError> {
    match key {
        "spent" => Err(ApiError::Spent),
        "fast" => Err(ApiError::TooFast { retry_after: 30 }),
        "bad" => Err(ApiError::BadKey),
        "down" => Err(ApiError::Down("HTTP 503".into())),
        _ => Ok((0..req.count)
            .map(|i| {
                (
                    format!("{} result {i}", req.query),
                    format!("https://example.com/{i}"),
                    "a snippet".to_string(),
                )
            })
            .collect()),
    }
}

#[astra::plugin]
impl MySearch {
    /// Called on start and on every settings change.
    #[hook]
    async fn on_config(&self, _ctx: &PluginContext, cfg: Settings) {
        *self.settings.lock().unwrap() = cfg;
    }

    /// Answer one search for the assistant's `web_search` tool.
    #[hook]
    async fn web_search(
        &self,
        _ctx: &PluginContext,
        req: WebSearchRequest,
    ) -> anyhow::Result<WebSearchResponse> {
        let key = self.settings.lock().unwrap().api_key.clone();
        if key.is_empty() {
            return Ok(WebSearchResponse::refuse(
                WebSearchErrorCode::NotConfigured,
                "set an API key in the plugin's settings",
            ));
        }
        Ok(match call_api(&key, &req) {
            Ok(rows) => WebSearchResponse::hits(rows.into_iter().map(|(title, url, text)| {
                WebSearchHit::new(title, url).with_snippet(text)
            })),
            Err(ApiError::Spent) => {
                WebSearchResponse::refuse(WebSearchErrorCode::Quota, "the plan's allowance is spent")
            }
            Err(ApiError::TooFast { retry_after }) => {
                WebSearchResponse::refuse(WebSearchErrorCode::RateLimited, "too many searches")
                    .with_retry_after(retry_after)
            }
            Err(ApiError::BadKey) => {
                WebSearchResponse::refuse(WebSearchErrorCode::Auth, "the API key was refused")
            }
            Err(ApiError::Down(why)) => WebSearchResponse::refuse(
                WebSearchErrorCode::Unavailable,
                format!("the provider is down: {why}"),
            ),
        })
    }
}

astra::main!(MySearch::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    fn request(count: u32) -> WebSearchRequest {
        WebSearchRequest {
            query: "rust".into(),
            count,
            freshness: WebSearchFreshness::Any,
            country: None,
            language: None,
        }
    }

    #[tokio::test]
    async fn no_key_is_a_refusal_not_an_error() {
        let h = Harness::new(MySearch::default()).start().await.unwrap();
        let answer = h.web_search(request(3)).await.unwrap();
        assert!(matches!(
            answer,
            WebSearchResponse::Refused { code: WebSearchErrorCode::NotConfigured, .. }
        ));
    }

    #[tokio::test]
    async fn a_spent_allowance_is_quota() {
        let h = Harness::new(MySearch::default())
            .with_config(json!({ "api_key": "spent" }))
            .start()
            .await
            .unwrap();
        let answer = h.web_search(request(3)).await.unwrap();
        assert!(matches!(
            answer,
            WebSearchResponse::Refused { code: WebSearchErrorCode::Quota, .. }
        ));
    }

    #[tokio::test]
    async fn a_key_gets_hits() {
        let h = Harness::new(MySearch::default())
            .with_config(json!({ "api_key": "k" }))
            .start()
            .await
            .unwrap();
        let WebSearchResponse::Hits(hits) = h.web_search(request(2)).await.unwrap() else {
            panic!("expected hits");
        };
        assert_eq!(hits.len(), 2);
    }
}
```

## Python

Перевизначте `web_search(self, request)` у `Plugin`. Він отримує
`WebSearchRequest` і повертає `WebSearchResponse` — або простий список
`WebSearchHit`, що означає, що пошук виконався.
`WebSearchResponse.refuse(code, message, retry_after_secs=0)` перевіряє
код, тож помилка в написанні не пройде у вашому власному тесті.
Блокувальний I/O має йти в окремому потоці (`asyncio.to_thread`): цей
хук ділить свій цикл подій із кожним іншим хуком, який обслуговує
плагін.

<!-- doctest: python-plugin -->
```python
"""MySearch — a web search provider plugin."""

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request

from astra_plugin_sdk import (
    Plugin,
    WebSearchErrorCode,
    WebSearchHit,
    WebSearchResponse,
)

API = "https://api.example.com/search"


def call_api(key, query, count, timeout=15):
    url = f"{API}?{urllib.parse.urlencode({'q': query, 'n': count})}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)["results"]


class MySearch(Plugin):
    """Web search through Example Search."""

    async def web_search(self, request):
        key = self.config.get("api_key", "")
        if not key:
            return WebSearchResponse.refuse(
                WebSearchErrorCode.NOT_CONFIGURED, "set an API key in the plugin's settings"
            )
        try:
            rows = await asyncio.to_thread(call_api, key, request.query, request.count)
        except urllib.error.HTTPError as e:
            if e.code == 402:
                return WebSearchResponse.refuse(WebSearchErrorCode.QUOTA, "the plan's allowance is spent")
            if e.code == 429:
                retry = int(e.headers.get("Retry-After", "0") or 0)
                return WebSearchResponse.refuse(
                    WebSearchErrorCode.RATE_LIMITED, "too many searches", retry_after_secs=retry
                )
            if e.code in (401, 403):
                return WebSearchResponse.refuse(WebSearchErrorCode.AUTH, "the API key was refused")
            return WebSearchResponse.refuse(WebSearchErrorCode.UNAVAILABLE, f"HTTP {e.code}")
        except OSError as e:
            return WebSearchResponse.refuse(WebSearchErrorCode.UNAVAILABLE, f"network: {e}")
        return [WebSearchHit(title=r["title"], url=r["url"], snippet=r.get("text", "")) for r in rows]


def test_no_key_is_a_refusal_not_an_error():
    from astra_plugin_sdk.testing import Harness

    with Harness(MySearch()) as h:
        answer = h.web_search("rust", count=3)
    assert answer.error_code == WebSearchErrorCode.NOT_CONFIGURED
    assert answer.hits == []


if __name__ == "__main__":
    MySearch().run()
```

## TypeScript

Дайте `plugin({...})` функцію `webSearch(req, ctx)`, або перевизначте
`webSearch(req)` у підкласі `Plugin`. Поверніть `WebSearchHit[]`, або
зберіть відповідь за допомогою `WebSearch.hits(...)` /
`WebSearch.refuse(code, message, retryAfterSecs)`.

<!-- doctest: ts-plugin -->
```typescript
import { plugin, WebSearch, type WebSearchHit } from "astra-plugin-sdk";

interface Row {
  title: string;
  url: string;
  text?: string;
}

export const app = plugin({
  async webSearch(req, ctx) {
    const key = ctx.configValue<string>("api_key", "");
    if (!key) return WebSearch.refuse("not_configured", "set an API key in the plugin's settings");

    const url = `https://api.example.com/search?q=${encodeURIComponent(req.query)}&n=${req.count}`;
    let res: Response;
    try {
      res = await fetch(url, {
        headers: { Authorization: `Bearer ${key}` },
        signal: AbortSignal.timeout(15_000),
      });
    } catch (e) {
      return WebSearch.refuse("unavailable", `network: ${String(e)}`);
    }
    if (res.status === 402) return WebSearch.refuse("quota", "the plan's allowance is spent");
    if (res.status === 429) {
      return WebSearch.refuse("rate_limited", "too many searches", Number(res.headers.get("retry-after") ?? 0));
    }
    if (res.status === 401 || res.status === 403) return WebSearch.refuse("auth", "the API key was refused");
    if (!res.ok) return WebSearch.refuse("unavailable", `HTTP ${res.status}`);

    const body = (await res.json()) as { results: Row[] };
    return body.results.map((r): WebSearchHit => ({ title: r.title, url: r.url, snippet: r.text ?? "" }));
  },
});

if (require.main === module) app.run();
```

## Тестування

Харнес рівня 1 кожного SDK проганяє хук через ту саму проєкцію на
провід, яку бачить демон, — обрізання до `count`, відмову в тілі:

| SDK | Виклик | Повертає |
|---|---|---|
| Rust | `running.web_search(WebSearchRequest { .. })` | `WebSearchResponse` хука |
| Python | `harness.web_search(query, count=…, freshness=…, country=…, language=…)` | `WebSearchResponse`, прочитаний назад із проводу |
| TypeScript | `harness.webSearch(query, { count, freshness, country, language })` | `WebSearchResponse`, прочитаний назад із проводу |

`astra-plugin test` надсилає один справжній запит (`count` 3) і падає
на тому, що демон прочитав би неправильно або відкинув: `error_code`
поза цими п'ятьма, більше результатів, ніж запитано, або результат,
чий URL не `http(s)`. Хуку дається 20 секунд. Потім підвантажте
плагін через `astra-plugin dev`, виберіть його під **AI → Веброзшук**
і натисніть там **Test**.

## Приклад

[`examples/duckduckgo-search`](../../examples/duckduckgo-search/) —
повноцінний провайдер на Python без залежностей понад SDK: `urllib`
для запиту, `html.parser` для сторінки, офлайн-тести на написаних
вручну фікстурах. Він читає HTML-сторінку результатів DuckDuckGo, що є
**неофіційним скрейпінгом**: він може зламатися щойно зміниться
розмітка, DuckDuckGo може відмовляти автоматизованим запитам, а умови
використання DuckDuckGo регулюють його застосування. Це приклад форми,
а не плагін для каталогу.
