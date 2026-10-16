> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/web-search-plugins.md) maßgeblich.


# Web-Search-Plugins

Ein Web-Search-Plugin deklariert `web_search = true` im Abschnitt
`[capabilities]` seiner `plugin.toml`. Astra bietet es dann unter **KI →
Websuche** als Provider für das Werkzeug `web_search` des Assistenten an —
als **Such-Provider** oder als Fallback, **Wenn keine Antwort möglich ist** —
neben den eingebauten Providern. Die Wahl des Nutzers wird als
`plugin__<plugin id>` gespeichert, mit der Plugin-ID wortwörtlich:
`plugin__duckduckgo-search`, Bindestrich und alles. Das unterscheidet sich von
den Provider-IDs für TTS, STT und Wake Word, die Bindestriche in
Unterstriche verwandeln.

Die ganze Capability ist ein Hook, `WebSearch`: eine Anfrage hinein, höchstens
`count` Treffer — oder eine Ablehnung — hinaus.

## Was Astra übernimmt, damit das Plugin es nicht tun muss

Der Daemon übernimmt alles rund um den Aufruf:

- **Die Provider-Kette.** Der Nutzer wählt einen Provider und einen Fallback.
  Lehnt der deine ab, wechselt der Daemon selbständig zum Fallback; dein
  Plugin ruft nie eine andere Suchmaschine auf.
- **Der Cache.** Eine wiederholte Anfrage erreicht dein Plugin womöglich nie.
  Füge keinen eigenen Cache hinzu.
- **Der Zaun.** Ergebnisse erreichen das Modell als nicht vertrauenswürdiger
  Text aus dem Web markiert. Gib wieder, was die Quelle sagt; verpacke es nie
  in Anweisungen für das Modell.
- **Normalisierung.** Markup wird aus Titeln und Snippets entfernt, ein
  Treffer, dessen URL nicht `http` oder `https` ist, wird verworfen, und ein
  Datum, das nicht `YYYY-MM-DD` ist, gilt als unbekannt.

Ein Plugin beantwortet also EINE Anfrage, schnell, und sagt klar, wenn es
das nicht kann.

## Einen Provider anlegen

<!-- doctest: cli -->
```bash
astra-plugin new my-search --lang python --template blank --capabilities web_search --output ./my-search
```

`--lang` kann auch `rust` oder `typescript` sein. Es gibt kein
Web-Search-Template: Die Capability kommt über `--capabilities`, und der Hook
des Scaffolds antwortet `not_configured`, bis du ihn implementierst.
`astra-plugin test` ruft `WebSearch` mit einer echten Anfrage auf; eine
Ablehnung besteht den Test, weil sie eine Antwort ist.

Setze `min_astra_version`. `[capabilities]` ist eine geschlossene Menge, ein
Astra, das älter ist als das mit `web_search` (0.2.7), lehnt das ganze
Manifest ab; mit der Zeile sagt es stattdessen, dass das Plugin ein neueres
Astra braucht. Bewahre den API-Schlüssel des Providers im eigenen
`[config]`-Schema des Plugins auf. Astra zeigt ihn auf der Plugins-Seite an,
und die KI-Seite sagt, dass der Schlüssel dort gesetzt ist:

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

Der Schlüssel lebt dort und nirgendwo sonst: nicht in einer
Umgebungsvariable, nicht in einer Datei, die das Plugin schreibt, nicht in
den Fehlermeldungen, die es zurückgibt.

## Die Anfrage

| Feld | Wert |
|---|---|
| `query` | Wonach das Modell gesucht hat, bereits vom Daemon validiert |
| `count` | Wie viele Treffer zurückzugeben sind, `1` bis `10`. Weniger ist in Ordnung; jedes SDK kürzt eine längere Antwort auf diese Länge |
| `freshness` | `""` (keine Einschränkung), `day`, `week`, `month` oder `year`. Die SDKs lesen einen unbekannten Wert als `""` |
| `country` | ISO 3166-1 alpha-2, Großbuchstaben (`DE`), oder leer |
| `language` | ISO 639-1, Kleinbuchstaben (`de`), oder leer |

Bilde sie auf deine API ab und ignoriere, was sie nicht ausdrücken kann.

## Die Antwort

Entweder Treffer — jeweils ein `title`, eine `url` (`http` oder `https`), ein
reiner Text-`snippet` und, wenn die Quelle die Seite datiert, `published` als
`YYYY-MM-DD` — oder eine Ablehnung. **Eine Ablehnung ist eine Antwort, kein
Fehler.** Gib sie zurück; raise oder throw sie nicht:

| `error_code` | Wann | Was der Daemon außer dem Wechsel zum Fallback tut |
|---|---|---|
| `quota` | Das Kontingent des Kontos ist aufgebraucht; setze `retry_after_secs`, wenn die API sagt, wann es wiederkommt | Fragt diesen Provider `retry_after_secs` lang nicht mehr, oder 15 Minuten, wenn es `0` ist |
| `rate_limited` | Gerade zu viele Anfragen; setze `retry_after_secs`, wenn die API sagt, wie lange | Fragt `retry_after_secs` lang nicht mehr, oder 10 Sekunden, wenn es `0` ist |
| `auth` | Der Schlüssel wurde abgelehnt | Sagt dem Modell, dass der Schlüssel zurückgewiesen wurde |
| `not_configured` | Eine Einstellung, die der Nutzer vornehmen muss, fehlt — meist der Schlüssel | Sagt dem Modell, dass der Provider nicht eingerichtet ist, mit deiner Nachricht |
| `unavailable` | Alles andere: der Dienst ist down, das Netzwerk hat versagt, die Antwort war unlesbar | Sagt dem Modell, dass der Provider nicht verfügbar ist, mit deiner Nachricht |

Jede Ablehnung schickt die Suche zum Fallback-Provider des Nutzers, falls es
einen gibt. Was auch immer `retry_after_secs` sagt, der Daemon wartet
höchstens 15 Minuten. `error_message` ist kurz und auf einfachem Englisch:
Das Modell liest es — als eine Zeile, außerhalb des Zauns für
nicht vertrauenswürdige Inhalte, sodass Chat-Template-Tokens und
Zeilenumbrüche darin entfernt werden. Ein `error_code` außerhalb dieser
fünf wird als `unavailable` gelesen. Eine Suche, die lief und nichts fand,
ist eine leere Trefferliste, keine Ablehnung.

Was KEINE Antwort ist: eine ausgelöste Exception, ein geworfener Fehler oder
ein Rust-`Err` erreicht den Daemon als fehlgeschlagener RPC, den er als
nicht verfügbaren Provider meldet, mit dem Text des Fehlers — eine Ablehnung,
die du meintest, aber stattdessen ausgelöst hast, verliert also ihren Code.
Ein Plugin, das `web_search` deklariert und den Hook nicht implementiert,
antwortet `UNIMPLEMENTED`, was der Daemon als nicht eingerichteten Provider
meldet.

Der Daemon wartet höchstens 30 Sekunden auf eine Suche — weniger, wenn
`plugin.call_timeout_secs` niedriger ist, oder wenn die eigene Deadline des
Modells es ist — sodass ein hängender Provider innerhalb der Runde an den
Fallback des Nutzers übergibt. Gib der HTTP-Anfrage ein Timeout deutlich
innerhalb dessen — 10 bis 15 Sekunden — und antworte `unavailable`, wenn es
auslöst. Der Daemon behält außerdem höchstens `count` deiner Treffer.

## Rust

`web_search` auf `PluginCapability` (oder als `#[hook]` innerhalb von
`#[astra::plugin]`) nimmt eine `WebSearchRequest` und gibt
`anyhow::Result<WebSearchResponse>` zurück. `WebSearchResponse::hits(...)`
und `WebSearchResponse::refuse(WebSearchErrorCode::…, message)` bauen die
Antwort; `.with_retry_after(secs)` kommt auf eine `RateLimited`-Ablehnung.
Die Platzhalterfunktion unten ist, wo dein HTTP-Client hingehört — das SDK
liefert keinen mit.

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

Überschreibe `web_search(self, request)` auf `Plugin`. Es erhält eine
`WebSearchRequest` und gibt eine `WebSearchResponse` zurück — oder eine
einfache Liste von `WebSearchHit`, was bedeutet, dass die Suche gelaufen ist.
`WebSearchResponse.refuse(code, message, retry_after_secs=0)` prüft den
Code, sodass ein Tippfehler in deinem eigenen Test scheitert. Blockierendes
I/O gehört auf einen Thread (`asyncio.to_thread`): Der Hook teilt seinen
Event-Loop mit jedem anderen Hook, den das Plugin bedient.

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

Gib `plugin({...})` eine Funktion `webSearch(req, ctx)`, oder überschreibe
`webSearch(req)` auf einer `Plugin`-Subklasse. Gib `WebSearchHit[]` zurück,
oder baue die Antwort mit `WebSearch.hits(...)` / `WebSearch.refuse(code,
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

## Testen

Der Level-1-Harness jedes SDKs steuert den Hook durch dieselbe
Draht-Projektion, die der Daemon sieht — die Kürzung auf `count`, die
Ablehnung im Body:

| SDK | Aufruf | Gibt zurück |
|---|---|---|
| Rust | `running.web_search(WebSearchRequest { .. })` | die `WebSearchResponse` des Hooks |
| Python | `harness.web_search(query, count=…, freshness=…, country=…, language=…)` | eine vom Draht zurückgelesene `WebSearchResponse` |
| TypeScript | `harness.webSearch(query, { count, freshness, country, language })` | eine vom Draht zurückgelesene `WebSearchResponse` |

`astra-plugin test` schickt eine echte Anfrage (`count` 3) und schlägt fehl
bei allem, was der Daemon falsch lesen oder verwerfen würde: ein
`error_code` außerhalb der fünf, mehr Treffer als verlangt, oder ein
Treffer, dessen URL nicht `http(s)` ist. Es gibt dem Hook 20 Sekunden.
Lade dann mit `astra-plugin dev` seitwärts, wähle das Plugin unter **KI →
Websuche** und drücke dort **Test**.

## Ein Beispiel

[`examples/duckduckgo-search`](../../examples/duckduckgo-search/) ist ein
vollständiger Provider in Python ohne Abhängigkeit über das SDK hinaus:
`urllib` für die Anfrage, `html.parser` für die Seite, Offline-Tests auf
handgeschriebenen Fixtures. Er liest DuckDuckGos HTML-Ergebnisseite, was
**inoffizielles Scraping** ist: Es kann brechen, sobald sich das Markup
ändert, DuckDuckGo kann automatisierte Anfragen ablehnen, und DuckDuckGos
Nutzungsbedingungen regeln seine Verwendung. Es ist ein Beispiel der Form,
kein Plugin für den Katalog.
