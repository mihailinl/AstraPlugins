> **本文档为翻译版本。** 权威来源是 [docs/en](../en/web-search-plugins.md)。如与英文版有出入，以英文版为准。


# Web 搜索插件

Web 搜索插件在其 `plugin.toml` 的 `[capabilities]` 部分声明
`web_search = true`。Astra 随后会在**内置提供方**旁边，把它作为助手
`web_search` 工具的提供方，呈现在**AI → 网络搜索**下 —— 作为**搜索
提供方**，或作为备选的**当它无法回答时**。用户的选择保存为
`plugin__<plugin id>`，插件 id 原样保留：`plugin__duckduckgo-search`，
连字符也不例外。这与 TTS、STT 和唤醒词提供方的 id 不同，后者会把连字符
换成下划线。

整个 capability 就是一个钩子 `WebSearch`：一次查询进去，最多 `count`
条结果——或一次拒绝——出来。

## Astra 会替插件做的事

守护进程负责调用周围的一切：

- **提供方链。** 用户选择一个提供方和一个备选。当你的提供方拒绝时，
  守护进程会自行切换到备选；你的插件永远不会调用另一个搜索引擎。
- **缓存。** 重复的查询可能永远不会到达你的插件。不要自己添加缓存。
- **围栏。** 结果到达模型时会被标记为来自网络的不可信文本。按源头
  所说的原样返回；永远不要把它包装成对模型的指令。
- **归一化。** 标题和摘要中的标记会被剥离，URL 不是 `http` 或 `https`
  的结果会被丢弃，不是 `YYYY-MM-DD` 格式的日期会被当作未知。

所以插件只回答一次查询，要快，不能回答时也要说清楚。

## 创建提供方

<!-- doctest: cli -->
```bash
astra-plugin new my-search --lang python --template blank --capabilities web_search --output ./my-search
```

`--lang` 也可以是 `rust` 或 `typescript`。没有专门的网络搜索模板：
capability 通过 `--capabilities` 加入，脚手架的钩子在你实现之前都会
回答 `not_configured`。`astra-plugin test` 会用一次真实查询调用
`WebSearch`；拒绝也算通过，因为它是一个应答。

请设置 `min_astra_version`。`[capabilities]` 是封闭集合，所以早于引入
`web_search`（0.2.7）的 Astra 会拒绝整个清单；有了这一行，它会改为
说明插件需要更新的 Astra。把提供方的 API 密钥保存在插件自己的
`[config]` schema 里。Astra 会在插件页面渲染它，AI 页面会说明密钥
就设置在那里：

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

密钥只存在于那里，不在别处：不在环境变量里，不在插件写的文件里，也
不在它返回的错误消息里。

## 请求

| 字段 | 值 |
|---|---|
| `query` | 模型搜索的内容，已经由守护进程验证过 |
| `count` | 要返回多少条结果，`1` 到 `10`。少一些也没关系；每个 SDK 都会把更长的答案截短到这个长度 |
| `freshness` | `""`（无限制）、`day`、`week`、`month` 或 `year`。SDK 会把未知值读作 `""` |
| `country` | ISO 3166-1 alpha-2，大写（`DE`），或为空 |
| `language` | ISO 639-1，小写（`de`），或为空 |

把它们映射到你的 API 上，忽略它无法表达的部分。

## 应答

要么是结果——每条包含 `title`、`url`（`http` 或 `https`）、纯文本的
`snippet`，以及当来源给页面标注了日期时的 `published`（`YYYY-MM-DD`
格式）——要么是拒绝。**拒绝是一种应答，不是错误。** 把它返回；不要
raise 或 throw 它：

| `error_code` | 何时 | 除了切换到备选之外，守护进程还会做什么 |
|---|---|---|
| `quota` | 账户额度已用完；如果 API 说明了何时恢复，设置 `retry_after_secs` | 在 `retry_after_secs` 内，或为 `0` 时 15 分钟内，不再询问该提供方 |
| `rate_limited` | 现在请求太多；如果 API 说明了要等多久，设置 `retry_after_secs` | 在 `retry_after_secs` 内，或为 `0` 时 10 秒内，不再询问 |
| `auth` | 密钥被拒绝 | 告诉模型密钥被拒绝了 |
| `not_configured` | 缺少用户必须完成的设置——通常是密钥 | 告诉模型提供方尚未配置，附带你的消息 |
| `unavailable` | 其他任何情况：服务宕机、网络失败、应答无法解析 | 告诉模型提供方不可用，附带你的消息 |

每次拒绝都会把搜索转给用户的备选提供方（如果有的话）。无论
`retry_after_secs` 怎么说，守护进程最多等待 15 分钟。`error_message`
简短、使用简单英语：模型会把它当作一行来读——在不可信内容围栏之外，
因此其中的聊天模板 token 和换行都会被移除。这五个之外的 `error_code`
会被当作 `unavailable` 读取。一次运行过但什么都没找到的搜索，是空的
结果列表，不是拒绝。

不算应答的情况：抛出的异常、throw 的错误，或 Rust 的 `Err`，都会以
失败的 RPC 到达守护进程，守护进程会把它报告为提供方不可用，并附带
错误文本——所以你本想表达的拒绝，一旦用 raise 而不是 return，就会丢失
它的代码。声明了 `web_search` 却没实现这个钩子的插件会应答
`UNIMPLEMENTED`，守护进程会把它报告为未配置的提供方。

守护进程为一次搜索最多等待 30 秒——如果 `plugin.call_timeout_secs`
更短，或模型自身的截止时间更短，则等待更短的时间——这样卡住的提供方
会在这一轮内就交给用户的备选。给 HTTP 请求设置一个明显短于这个时间
的超时——10 到 15 秒——并在它触发时应答 `unavailable`。守护进程还
只会保留你最多 `count` 条结果。

## Rust

`PluginCapability` 上的 `web_search`（或 `#[astra::plugin]` 内的
`#[hook]`）接收一个 `WebSearchRequest`，返回
`anyhow::Result<WebSearchResponse>`。`WebSearchResponse::hits(...)`
和 `WebSearchResponse::refuse(WebSearchErrorCode::…, message)` 用来
构造应答；`.with_retry_after(secs)` 加在 `RateLimited` 的拒绝上。下面
这个占位函数就是你的 HTTP 客户端该放的地方——SDK 本身不附带一个。

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

重写 `Plugin` 上的 `web_search(self, request)`。它接收一个
`WebSearchRequest`，返回一个 `WebSearchResponse`——或一个裸的
`WebSearchHit` 列表，表示搜索确实运行了。
`WebSearchResponse.refuse(code, message, retry_after_secs=0)` 会检查
code，所以写错在你自己的测试里就会失败。阻塞式 I/O 应该放到线程里
（`asyncio.to_thread`）：这个钩子与插件提供的每一个其他钩子共享同一个
事件循环。

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

给 `plugin({...})` 一个 `webSearch(req, ctx)` 函数，或者在 `Plugin`
子类上重写 `webSearch(req)`。返回 `WebSearchHit[]`，或者用
`WebSearch.hits(...)` / `WebSearch.refuse(code, message,
retryAfterSecs)` 构造应答。

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

## 测试

每个 SDK 的一级 harness 都通过守护进程所见的同一种线上投影来驱动这个
钩子——包括截断到 `count`、body 里的拒绝：

| SDK | 调用 | 返回 |
|---|---|---|
| Rust | `running.web_search(WebSearchRequest { .. })` | 钩子的 `WebSearchResponse` |
| Python | `harness.web_search(query, count=…, freshness=…, country=…, language=…)` | 从线上读回的 `WebSearchResponse` |
| TypeScript | `harness.webSearch(query, { count, freshness, country, language })` | 从线上读回的 `WebSearchResponse` |

`astra-plugin test` 会发送一次真实查询（`count` 为 3），并在守护
进程会误读或丢弃的情况下失败：五个之外的 `error_code`、比请求的更多
的结果数，或 URL 不是 `http(s)` 的结果。它给钩子 20 秒。然后用
`astra-plugin dev` 侧载，在**AI → 网络搜索**下选择插件，在那里按
**Test**。

## 一个示例

[`examples/duckduckgo-search`](../../examples/duckduckgo-search/) 是一个
完整的 Python 提供方，除 SDK 外没有任何依赖：请求用 `urllib`，页面
解析用 `html.parser`，离线测试用手写的 fixture。它读取的是
DuckDuckGo 的 HTML 结果页，这属于**非官方爬取**：标记一旦变化就可能
失效，DuckDuckGo 可能拒绝自动化请求，而且它的使用受 DuckDuckGo 条款
约束。它只是展示这种形状的示例，不是面向目录的插件。
