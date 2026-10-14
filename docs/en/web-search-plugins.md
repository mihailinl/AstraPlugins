# Web search plugins

A web search plugin declares `web_search = true` in the `[capabilities]`
section of its `plugin.toml`. Astra then offers it under **AI → Web search** as
a provider for the assistant's `web_search` tool — as the **Search provider**,
or as the fallback, **If it can't answer** — next to the built-in providers.
The user's choice is stored as `plugin__<plugin id>`, with the plugin id kept
verbatim: `plugin__duckduckgo-search`, hyphen and all. That is unlike the TTS,
STT and wake-word provider ids, which turn hyphens into underscores.

The whole capability is one hook, `WebSearch`: one query in, at most `count`
hits — or a refusal — out.

## What Astra does, so the plugin does not

The daemon owns everything around the call:

- **The provider chain.** The user picks a provider and a fallback. When
  yours refuses, the daemon moves to the fallback on its own; your plugin
  never calls another search engine.
- **The cache.** A repeated query may never reach your plugin. Do not add a
  cache of your own.
- **The fence.** Results reach the model marked as untrusted text from the
  web. Return what the source says; never wrap it in instructions for the
  model.
- **Normalisation.** Markup is stripped from titles and snippets, a hit whose
  URL is not `http` or `https` is dropped, and a date that is not `YYYY-MM-DD`
  is read as unknown.

So a plugin answers ONE query, fast, and says plainly when it cannot.

## Start a provider

<!-- doctest: cli -->
```bash
astra-plugin new my-search --lang python --template blank --capabilities web_search --output ./my-search
```

`--lang` may also be `rust` or `typescript`. There is no web-search template:
the capability arrives through `--capabilities`, and the scaffold's hook
answers `not_configured` until you implement it. `astra-plugin test` calls
`WebSearch` with a real query; a refusal passes, because it is an answer.

Set `min_astra_version`. `[capabilities]` is a closed set, so an Astra older
than the one that introduced `web_search` (0.2.7) refuses the whole manifest;
with the line, it says the plugin needs a newer Astra instead. Keep the
provider's API key in the plugin's own `[config]` schema. Astra renders it on
the Plugins page, and the AI page says the key is set there:

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

The key lives there and nowhere else: not in an environment variable, not in a
file the plugin writes, not in the error messages it returns.

## The request

| Field | Value |
|---|---|
| `query` | What the model searched for, already validated by the daemon |
| `count` | How many hits to return, `1` to `10`. Fewer is fine; every SDK cuts a longer answer to this length |
| `freshness` | `""` (no restriction), `day`, `week`, `month` or `year`. The SDKs read an unknown value as `""` |
| `country` | ISO 3166-1 alpha-2, upper case (`DE`), or empty |
| `language` | ISO 639-1, lower case (`de`), or empty |

Map them onto your API and ignore what it cannot express.

## The answer

Either hits — each a `title`, a `url` (`http` or `https`), a plain-text
`snippet` and, when the source dates the page, `published` as `YYYY-MM-DD` —
or a refusal. **A refusal is an answer, not an error.** Return it; do not raise
or throw it:

| `error_code` | When | What the daemon does, besides moving to the fallback |
|---|---|---|
| `quota` | The account's allowance is spent; set `retry_after_secs` when the API says when it comes back | Stops asking this provider for `retry_after_secs`, or for 15 minutes when it is `0` |
| `rate_limited` | Too many requests right now; set `retry_after_secs` when the API says how long | Stops asking for `retry_after_secs`, or for 10 seconds when it is `0` |
| `auth` | The key was refused | Tells the model the key was rejected |
| `not_configured` | A setting the user has to make is missing — usually the key | Tells the model the provider is not set up, with your message |
| `unavailable` | Anything else: the service is down, the network failed, the answer was unreadable | Tells the model the provider is unavailable, with your message |

Every refusal moves the search to the user's fallback provider, if there is
one. Whatever `retry_after_secs` says, the daemon waits at most 15 minutes. `error_message` is short, plain English: the model reads it — as one line, outside the untrusted-content fence, so chat-template tokens and line breaks in it are removed. An
`error_code` outside these five is read as `unavailable`. A search that ran and
found nothing is an empty list of hits, not a refusal.

What is NOT an answer: a raised exception, a thrown error or a Rust `Err`
reaches the daemon as a failed RPC, which it reports as the provider being
unavailable, with the error's text — so a refusal you meant, raised instead of
returned, loses its code. A plugin that declares `web_search` and does not
implement the hook answers `UNIMPLEMENTED`, which the daemon reports as a
provider that is not set up.

The daemon waits at most 30 seconds for one search — less when
`plugin.call_timeout_secs` is lower, or when the model's own deadline is — so a
stuck provider hands over to the user's fallback within the turn. Give the HTTP
request a timeout well inside that — 10 to 15 seconds — and answer
`unavailable` when it fires. The daemon also keeps at most `count` of your hits.

## Rust

`web_search` on `PluginCapability` (or as a `#[hook]` inside
`#[astra::plugin]`) takes a `WebSearchRequest` and returns
`anyhow::Result<WebSearchResponse>`. `WebSearchResponse::hits(...)` and
`WebSearchResponse::refuse(WebSearchErrorCode::…, message)` build the answer;
`.with_retry_after(secs)` goes on a `RateLimited` refusal. The stand-in
function below is where your HTTP client goes — the SDK does not ship one.

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

Override `web_search(self, request)` on `Plugin`. It receives a
`WebSearchRequest` and returns a `WebSearchResponse` — or a bare list of
`WebSearchHit`, which means the search ran. `WebSearchResponse.refuse(code,
message, retry_after_secs=0)` checks the code, so a typo fails in your own test.
Blocking I/O belongs on a thread (`asyncio.to_thread`): the hook shares its
event loop with every other hook the plugin serves.

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

Give `plugin({...})` a `webSearch(req, ctx)` function, or override
`webSearch(req)` on a `Plugin` subclass. Return `WebSearchHit[]`, or build the
answer with `WebSearch.hits(...)` / `WebSearch.refuse(code, message,
retryAfterSecs)`.

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

## Testing

Each SDK's level-1 harness drives the hook through the same wire projection the
daemon sees — the cut to `count`, the refusal in the body:

| SDK | Call | Returns |
|---|---|---|
| Rust | `running.web_search(WebSearchRequest { .. })` | the hook's `WebSearchResponse` |
| Python | `harness.web_search(query, count=…, freshness=…, country=…, language=…)` | a `WebSearchResponse` read back off the wire |
| TypeScript | `harness.webSearch(query, { count, freshness, country, language })` | a `WebSearchResponse` read back off the wire |

`astra-plugin test` sends one real query (`count` 3) and fails on what the
daemon would misread or drop: an `error_code` outside the five, more hits than
were asked for, or a hit whose URL is not `http(s)`. It allows the hook 20
seconds. Then sideload with `astra-plugin dev`, choose the plugin under **AI →
Web search**, and press **Test** there.

## An example

[`examples/duckduckgo-search`](../../examples/duckduckgo-search/) is a complete
provider in Python with no dependency beyond the SDK: `urllib` for the request,
`html.parser` for the page, offline tests on hand-written fixtures. It reads
DuckDuckGo's HTML results page, which is **unofficial scraping**: it can break
whenever the markup changes, DuckDuckGo may refuse automated requests, and
DuckDuckGo's terms govern its use. It is an example of the shape, not a plugin
for the catalogue.
