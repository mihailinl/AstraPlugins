> **これは翻訳です。** 正式な情報源は [docs/en](../en/web-search-plugins.md) です。内容に食い違いがある場合は英語版が優先されます。


# Web 検索プラグイン

Web 検索プラグインは、`plugin.toml` の `[capabilities]` セクションで
`web_search = true` を宣言します。すると Astra は、組み込みのプロバイダー
と並んで、アシスタントの `web_search` ツールのプロバイダーとして —
**検索プロバイダー**として、またはフォールバックの**答えられない場合**
として — **AI → Web 検索**の下にそれを提示します。ユーザーの選択は
`plugin__<plugin id>` として保存され、プラグイン id はそのまま使われます:
`plugin__duckduckgo-search`、ハイフンも含めて。これは TTS、STT、
ウェイクワードのプロバイダー id がハイフンをアンダースコアに変えるのとは
異なります。

この capability 全体は一つのフック `WebSearch` です: 1 件のクエリが入り、
最大 `count` 件の結果 — または拒否 — が出ます。

## プラグインがしなくてよいように Astra がすること

呼び出しの周りのことは、すべてデーモンが引き受けます:

- **プロバイダーチェーン。** ユーザーはプロバイダーとフォールバックを
  選びます。あなたのプロバイダーが拒否すると、デーモンが自分でフォール
  バックに切り替えます。あなたのプラグインが別の検索エンジンを呼び出す
  ことはありません。
- **キャッシュ。** 同じクエリの繰り返しが、あなたのプラグインに届かない
  ことがあります。自分でキャッシュを追加しないでください。
- **フェンス。** 結果は、Web からの信頼できないテキストとして印を付けて
  モデルに届きます。ソースが言っていることをそのまま返してください。
  モデルへの指示として包んではいけません。
- **正規化。** タイトルとスニペットからマークアップが取り除かれ、URL が
  `http` でも `https` でもない結果は捨てられ、`YYYY-MM-DD` でない日付は
  不明として読まれます。

つまりプラグインは、1 件のクエリに速く答え、できないときははっきりと
そう言います。

## プロバイダーを始める

<!-- doctest: cli -->
```bash
astra-plugin new my-search --lang python --template blank --capabilities web_search --output ./my-search
```

`--lang` には `rust` や `typescript` も指定できます。Web 検索専用の
テンプレートはありません: capability は `--capabilities` から付与され、
scaffold のフックは実装するまで `not_configured` を返します。
`astra-plugin test` は実際のクエリで `WebSearch` を呼び出します。拒否は
応答なのでテストに通ります。

`min_astra_version` を設定してください。`[capabilities]` は閉じた集合
なので、`web_search` を導入したもの (0.2.7) より古い Astra はマニフェスト
全体を拒否します。この行があれば、代わりにプラグインがより新しい Astra
を必要としていると伝えます。プロバイダーの API キーはプラグイン自身の
`[config]` スキーマに保持してください。Astra はそれを Plugins ページに
表示し、AI ページはキーがそこに設定されていることを示します:

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

キーはそこだけに存在します: 環境変数にも、プラグインが書くファイルにも、
返すエラーメッセージにも存在しません。

## リクエスト

| フィールド | 値 |
|---|---|
| `query` | モデルが検索した内容。デーモンによって検証済み |
| `count` | 返す結果数、`1` から `10`。少なめでも問題なく、どの SDK も長い答えをこの長さに切り詰めます |
| `freshness` | `""` (制限なし)、`day`、`week`、`month`、または `year`。未知の値は SDK によって `""` として読まれます |
| `country` | ISO 3166-1 alpha-2、大文字 (`DE`)、または空 |
| `language` | ISO 639-1、小文字 (`de`)、または空 |

これらを自分の API に対応させ、表現できないものは無視してください。

## レスポンス

結果 — それぞれ `title`、`url` (`http` か `https`)、プレーンテキストの
`snippet`、ソースがページに日付を付けている場合は `YYYY-MM-DD` 形式の
`published` — か、拒否のいずれかです。**拒否は応答であり、エラーでは
ありません。** raise や throw ではなく、返してください:

| `error_code` | いつ | フォールバックへの切り替え以外にデーモンがすること |
|---|---|---|
| `quota` | アカウントの許容量が尽きている。API が復帰時刻を示すなら `retry_after_secs` を設定 | `retry_after_secs` の間、または `0` の場合は 15 分間このプロバイダーに問い合わせない |
| `rate_limited` | 今リクエストが多すぎる。API が長さを示すなら `retry_after_secs` を設定 | `retry_after_secs` の間、または `0` の場合は 10 秒間問い合わせない |
| `auth` | キーが拒否された | モデルにキーが拒否されたことを伝える |
| `not_configured` | ユーザーが行うべき設定が欠けている — 通常はキー | モデルにプロバイダーが未設定だと、あなたのメッセージとともに伝える |
| `unavailable` | それ以外すべて: サービスがダウン、ネットワーク失敗、応答が読めない | モデルにプロバイダーが利用不可だと、あなたのメッセージとともに伝える |

どの拒否も、あれば検索をユーザーのフォールバックプロバイダーに渡します。
`retry_after_secs` が何を言おうと、デーモンは最大 15 分待ちます。
`error_message` は短い平易な英語です: モデルはそれを 1 行として、
信頼できないコンテンツのフェンスの外側で読みます。そのためチャット
テンプレートのトークンや改行は取り除かれます。これら 5 つ以外の
`error_code` は `unavailable` として読まれます。実行されて何も
見つからなかった検索は、拒否ではなく空の結果リストです。

応答で**ない**もの: 発生した例外、throw されたエラー、Rust の `Err` は、
失敗した RPC としてデーモンに届き、デーモンはそれをプロバイダーが
利用不可だとエラーのテキストとともに報告します — つまり意図した拒否を
返す代わりに raise してしまうと、そのコードは失われます。`web_search`
を宣言していてフックを実装していないプラグインは `UNIMPLEMENTED` を
返し、デーモンはそれを未設定のプロバイダーとして報告します。

デーモンは 1 回の検索に最大 30 秒待ちます — `plugin.call_timeout_secs`
がそれより短い場合や、モデル自身の期限がそれより短い場合はより短く —
そのため止まったプロバイダーは、そのターン内でユーザーのフォールバック
に引き渡されます。HTTP リクエストには、それより十分短いタイムアウト —
10 秒から 15 秒 — を設定し、発火したら `unavailable` を返してください。
デーモンはまた、あなたの結果を最大 `count` 件までしか保持しません。

## Rust

`PluginCapability` の `web_search` (または `#[astra::plugin]` 内の
`#[hook]`) は `WebSearchRequest` を受け取り、
`anyhow::Result<WebSearchResponse>` を返します。
`WebSearchResponse::hits(...)` と
`WebSearchResponse::refuse(WebSearchErrorCode::…, message)` が応答を
組み立て、`RateLimited` の拒否には `.with_retry_after(secs)` を付けます。
下のスタンドイン関数は、あなたの HTTP クライアントが入る場所です —
SDK はクライアントを同梱していません。

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

`Plugin` の `web_search(self, request)` をオーバーライドします。
`WebSearchRequest` を受け取り、`WebSearchResponse` — または検索が実行
されたことを意味する `WebSearchHit` の素のリスト — を返します。
`WebSearchResponse.refuse(code, message, retry_after_secs=0)` はコードを
検証するので、タイプミスは自分のテストで失敗します。ブロッキング I/O は
スレッドに置いてください (`asyncio.to_thread`): このフックは、プラグイン
が提供する他のすべてのフックとイベントループを共有します。

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

`plugin({...})` に `webSearch(req, ctx)` 関数を与えるか、`Plugin` の
サブクラスで `webSearch(req)` をオーバーライドしてください。
`WebSearchHit[]` を返すか、`WebSearch.hits(...)` /
`WebSearch.refuse(code, message, retryAfterSecs)` で応答を組み立てます。

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

## テスト

各 SDK のレベル 1 ハーネスは、デーモンが見るのと同じワイヤー上の
投影を通してフックを駆動します — `count` への切り詰め、ボディ内の拒否も
含めて:

| SDK | 呼び出し | 戻り値 |
|---|---|---|
| Rust | `running.web_search(WebSearchRequest { .. })` | フックの `WebSearchResponse` |
| Python | `harness.web_search(query, count=…, freshness=…, country=…, language=…)` | ワイヤーから読み戻した `WebSearchResponse` |
| TypeScript | `harness.webSearch(query, { count, freshness, country, language })` | ワイヤーから読み戻した `WebSearchResponse` |

`astra-plugin test` は実際のクエリを 1 件 (`count` 3) 送り、デーモンが
読み違えたり捨てたりする内容で失敗します: 5 つ以外の `error_code`、
要求より多い結果数、`http(s)` でない URL の結果。フックには 20 秒
与えられます。その後 `astra-plugin dev` でサイドロードし、**AI → Web
検索**の下でプラグインを選び、そこで**テスト**を押してください。

## 実装例

[`examples/duckduckgo-search`](../../examples/duckduckgo-search/) は、
SDK 以外に依存のない Python の完全なプロバイダーです: リクエストには
`urllib`、ページの解析には `html.parser`、手書きのフィクスチャによる
オフラインテスト。これは DuckDuckGo の HTML 結果ページを読みますが、
これは**非公式なスクレイピング**です: マークアップが変わればいつでも
壊れる可能性があり、DuckDuckGo は自動化されたリクエストを拒否する
ことがあり、DuckDuckGo の利用規約がその使用を規律します。これは形を
示す例であって、カタログ向けのプラグインではありません。
