# Плагины веб-поиска

> Перевод. Источник истины — [docs/en](../en/web-search-plugins.md); при расхождении верна английская версия.

Плагин веб-поиска объявляет `web_search = true` в разделе `[capabilities]`
своего `plugin.toml`. Тогда Astra предлагает его под **AI → Веб-поиск** как
провайдера для инструмента ассистента `web_search` — как **провайдера
поиска** или как запасной вариант, **Если не может ответить**, — рядом со
встроенными провайдерами. Выбор пользователя хранится как
`plugin__<id плагина>`, с id плагина без изменений:
`plugin__duckduckgo-search`, дефис и всё остальное. Это отличается от id
провайдеров TTS, STT и слова-активатора, которые превращают дефисы в
подчёркивания.

Вся эта capability — один хук, `WebSearch`: один запрос входит, до `count`
результатов — или отказ — выходит.

## Что делает Astra, чтобы этого не делал плагин

Демон берёт на себя всё вокруг вызова:

- **Цепочка провайдеров.** Пользователь выбирает провайдера и запасной
  вариант. Когда ваш отказывает, демон сам переходит к запасному; ваш
  плагин никогда не вызывает другую поисковую систему.
- **Кэш.** Повторный запрос может никогда не дойти до вашего плагина. Не
  добавляйте собственный кэш.
- **Ограждение.** Результаты доходят до модели с пометкой как
  недоверенный текст из веба. Возвращайте то, что говорит источник;
  никогда не оборачивайте это в инструкции для модели.
- **Нормализация.** Из заголовков и фрагментов удаляется разметка,
  результат, чей URL не `http` и не `https`, отбрасывается, а дата не
  вида `YYYY-MM-DD` читается как неизвестная.

Так что плагин отвечает на ОДИН запрос, быстро, и прямо говорит, когда не
может.

## Создайте провайдер

<!-- doctest: cli -->
```bash
astra-plugin new my-search --lang python --template blank --capabilities web_search --output ./my-search
```

`--lang` также может быть `rust` или `typescript`. Шаблона веб-поиска
нет: capability приходит через `--capabilities`, и хук заготовки
отвечает `not_configured`, пока вы его не реализуете. `astra-plugin test`
вызывает `WebSearch` с настоящим запросом; отказ проходит проверку,
потому что это ответ.

Укажите `min_astra_version`. `[capabilities]` — закрытый набор, и Astra
старше той, где появился `web_search` (0.2.7), отклонит весь манифест; с
этой строкой она вместо этого скажет, что плагину нужен более новый
Astra. Храните API-ключ провайдера в собственной схеме `[config]`
плагина. Astra показывает его на странице плагинов, а страница AI
говорит, что ключ там задан:

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

Ключ живёт там и только там: не в переменной окружения, не в файле,
который пишет плагин, не в сообщениях об ошибке, которые он возвращает.

## Запрос

| Поле | Значение |
|---|---|
| `query` | Что искала модель, уже проверено демоном |
| `count` | Сколько результатов вернуть, от `1` до `10`. Меньше — нормально; каждый SDK урезает более длинный ответ до этой длины |
| `freshness` | `""` (без ограничения), `day`, `week`, `month` или `year`. SDK читают неизвестное значение как `""` |
| `country` | ISO 3166-1 alpha-2, верхний регистр (`DE`), либо пусто |
| `language` | ISO 639-1, нижний регистр (`de`), либо пусто |

Отобразите их на свой API и игнорируйте то, что он не может выразить.

## Ответ

Либо результаты — каждый с `title`, `url` (`http` или `https`),
текстовым `snippet` и, если источник датирует страницу, `published` в
виде `YYYY-MM-DD`, — либо отказ. **Отказ — это ответ, а не ошибка.**
Возвращайте его; не поднимайте и не бросайте:

| `error_code` | Когда | Что делает демон, помимо перехода к запасному варианту |
|---|---|---|
| `quota` | Лимит аккаунта исчерпан; укажите `retry_after_secs`, если API сообщает, когда он вернётся | Не спрашивает этого провайдера в течение `retry_after_secs`, или 15 минут, если это `0` |
| `rate_limited` | Сейчас слишком много запросов; укажите `retry_after_secs`, если API сообщает, сколько ждать | Не спрашивает в течение `retry_after_secs`, или 10 секунд, если это `0` |
| `auth` | Ключ отклонён | Сообщает модели, что ключ был отклонён |
| `not_configured` | Отсутствует настройка, которую должен сделать пользователь — обычно ключ | Сообщает модели, что провайдер не настроен, с вашим сообщением |
| `unavailable` | Всё остальное: сервис недоступен, сеть отказала, ответ не читается | Сообщает модели, что провайдер недоступен, с вашим сообщением |

Любой отказ передаёт поиск запасному провайдеру пользователя, если он
есть. Что бы ни говорил `retry_after_secs`, демон ждёт не более 15
минут. `error_message` короткий, на простом английском: модель читает
его как одну строку, вне ограждения недоверенного контента, поэтому
токены шаблона чата и переносы строк в нём удаляются. `error_code` вне
этих пяти читается как `unavailable`. Поиск, который выполнился и
ничего не нашёл, — это пустой список результатов, а не отказ.

Что НЕ является ответом: поднятое исключение, брошенная ошибка или
Rust-`Err` доходят до демона как неудавшийся RPC, который он сообщает
как недоступность провайдера, с текстом ошибки — так что отказ, который
вы имели в виду, но подняли вместо того, чтобы вернуть, теряет свой код.
Плагин, который объявляет `web_search` и не реализует хук, отвечает
`UNIMPLEMENTED`, что демон сообщает как ненастроенного провайдера.

Демон ждёт не более 30 секунд на один поиск — меньше, если
`plugin.call_timeout_secs` ниже, или если ниже собственный срок модели,
— так что застрявший провайдер передаёт управление запасному варианту
пользователя в рамках того же хода. Дайте HTTP-запросу тайм-аут заметно
короче этого — 10–15 секунд — и отвечайте `unavailable`, когда он
срабатывает. Демон также хранит не более `count` ваших результатов.

## Rust

`web_search` в `PluginCapability` (или как `#[hook]` внутри
`#[astra::plugin]`) принимает `WebSearchRequest` и возвращает
`anyhow::Result<WebSearchResponse>`. `WebSearchResponse::hits(...)` и
`WebSearchResponse::refuse(WebSearchErrorCode::…, message)` строят ответ;
`.with_retry_after(secs)` добавляется к отказу `RateLimited`.
Функция-заглушка ниже — это место для вашего HTTP-клиента: SDK его не
поставляет.

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

Переопределите `web_search(self, request)` в `Plugin`. Он получает
`WebSearchRequest` и возвращает `WebSearchResponse` — либо простой
список `WebSearchHit`, что означает, что поиск выполнился.
`WebSearchResponse.refuse(code, message, retry_after_secs=0)` проверяет
код, так что опечатка не пройдёт в вашем собственном тесте. Блокирующий
I/O должен идти в отдельном потоке (`asyncio.to_thread`): этот хук
делит свой event loop с каждым другим хуком, который обслуживает плагин.

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

Дайте `plugin({...})` функцию `webSearch(req, ctx)`, либо переопределите
`webSearch(req)` в подклассе `Plugin`. Верните `WebSearchHit[]`, либо
соберите ответ с помощью `WebSearch.hits(...)` / `WebSearch.refuse(code,
message, retryAfterSecs)`.

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

## Тестирование

Харнесс уровня 1 каждого SDK прогоняет хук через ту же проекцию на
провод, которую видит демон, — обрезку до `count`, отказ в теле:

| SDK | Вызов | Возвращает |
|---|---|---|
| Rust | `running.web_search(WebSearchRequest { .. })` | `WebSearchResponse` хука |
| Python | `harness.web_search(query, count=…, freshness=…, country=…, language=…)` | `WebSearchResponse`, прочитанный обратно с провода |
| TypeScript | `harness.webSearch(query, { count, freshness, country, language })` | `WebSearchResponse`, прочитанный обратно с провода |

`astra-plugin test` отправляет один настоящий запрос (`count` 3) и
падает на том, что демон прочитал бы неверно или отбросил: `error_code`
вне этих пяти, больше результатов, чем запрошено, или результат, чей
URL не `http(s)`. Хуку даётся 20 секунд. Затем подгрузите плагин с
`astra-plugin dev`, выберите его под **AI → Веб-поиск** и нажмите там
**Test**.

## Пример

[`examples/duckduckgo-search`](../../examples/duckduckgo-search/) —
полноценный провайдер на Python без зависимостей сверх SDK: `urllib`
для запроса, `html.parser` для страницы, офлайн-тесты на написанных
вручную фикстурах. Он читает HTML-страницу результатов DuckDuckGo, что
является **неофициальным скрейпингом**: он может сломаться при любом
изменении разметки, DuckDuckGo может отказывать автоматизированным
запросам, и условия использования DuckDuckGo регулируют его
применение. Это пример формы, а не плагин для каталога.
