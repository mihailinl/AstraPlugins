> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/web-search-plugins.md) es la referencia autorizada.


# Plugins de búsqueda web

Un plugin de búsqueda web declara `web_search = true` en la sección
`[capabilities]` de su `plugin.toml`. Astra lo ofrece entonces bajo **IA →
Búsqueda web** como proveedor para la herramienta `web_search` del
asistente — como **Proveedor de búsqueda**, o como respaldo, **Si no puede
responder** — junto a los proveedores integrados. La elección del usuario
se guarda como `plugin__<id del plugin>`, con el id del plugin tal cual:
`plugin__duckduckgo-search`, guion y todo. Eso es distinto de los ids de
proveedor de TTS, STT y palabra de activación, que convierten los guiones
en guiones bajos.

Toda la capability es un hook, `WebSearch`: una consulta entra, como mucho
`count` resultados — o un rechazo — salen.

## Lo que hace Astra para que el plugin no tenga que hacerlo

El daemon se ocupa de todo lo que rodea la llamada:

- **La cadena de proveedores.** El usuario elige un proveedor y un
  respaldo. Cuando el tuyo rechaza, el daemon pasa al respaldo por su
  cuenta; tu plugin nunca llama a otro motor de búsqueda.
- **La caché.** Una consulta repetida puede no llegar nunca a tu plugin.
  No añadas una caché propia.
- **La valla.** Los resultados llegan al modelo marcados como texto no
  fiable de la web. Devuelve lo que diga la fuente; nunca lo envuelvas en
  instrucciones para el modelo.
- **Normalización.** Se elimina el marcado de títulos y fragmentos, un
  resultado cuya URL no es `http` o `https` se descarta, y una fecha que no
  es `YYYY-MM-DD` se lee como desconocida.

Así que un plugin responde UNA consulta, rápido, y dice claramente cuando
no puede.

## Crear un proveedor

<!-- doctest: cli -->
```bash
astra-plugin new my-search --lang python --template blank --capabilities web_search --output ./my-search
```

`--lang` también puede ser `rust` o `typescript`. No hay plantilla de
búsqueda web: la capability llega mediante `--capabilities`, y el hook del
scaffold responde `not_configured` hasta que lo implementes.
`astra-plugin test` llama a `WebSearch` con una consulta real; un rechazo
aprueba, porque es una respuesta.

Fija `min_astra_version`. `[capabilities]` es un conjunto cerrado, así que
un Astra anterior al que introdujo `web_search` (0.2.7) rechaza el
manifiesto entero; con la línea, dice en cambio que el plugin necesita un
Astra más nuevo. Guarda la clave de API del proveedor en el propio
esquema `[config]` del plugin. Astra la muestra en la página de plugins, y
la página de IA dice que la clave está puesta ahí:

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

La clave vive ahí y en ningún otro sitio: ni en una variable de entorno, ni
en un archivo que escriba el plugin, ni en los mensajes de error que
devuelve.

## La solicitud

| Campo | Valor |
|---|---|
| `query` | Lo que buscó el modelo, ya validado por el daemon |
| `count` | Cuántos resultados devolver, de `1` a `10`. Menos está bien; cada SDK recorta una respuesta más larga a esta longitud |
| `freshness` | `""` (sin restricción), `day`, `week`, `month` o `year`. Los SDKs leen un valor desconocido como `""` |
| `country` | ISO 3166-1 alfa-2, mayúsculas (`DE`), o vacío |
| `language` | ISO 639-1, minúsculas (`de`), o vacío |

Mapéalos a tu API e ignora lo que no pueda expresar.

## La respuesta

O bien resultados — cada uno con `title`, `url` (`http` o `https`), un
`snippet` de texto plano y, cuando la fuente fecha la página, `published`
como `YYYY-MM-DD` — o un rechazo. **Un rechazo es una respuesta, no un
error.** Devuélvelo; no lo lances (`raise`/`throw`):

| `error_code` | Cuándo | Qué hace el daemon, además de pasar al respaldo |
|---|---|---|
| `quota` | El cupo de la cuenta está agotado; fija `retry_after_secs` si la API dice cuándo vuelve | Deja de preguntar a este proveedor durante `retry_after_secs`, o 15 minutos si es `0` |
| `rate_limited` | Demasiadas solicitudes ahora mismo; fija `retry_after_secs` si la API dice cuánto | Deja de preguntar durante `retry_after_secs`, o 10 segundos si es `0` |
| `auth` | Se rechazó la clave | Dice al modelo que se rechazó la clave |
| `not_configured` | Falta un ajuste que debe hacer el usuario — normalmente la clave | Dice al modelo que el proveedor no está configurado, con tu mensaje |
| `unavailable` | Cualquier otra cosa: el servicio está caído, falló la red, la respuesta era ilegible | Dice al modelo que el proveedor no está disponible, con tu mensaje |

Todo rechazo pasa la búsqueda al proveedor de respaldo del usuario, si hay
uno. Sea lo que diga `retry_after_secs`, el daemon espera como mucho 15
minutos. `error_message` es corto, en inglés llano: el modelo lo lee —
como una línea, fuera de la valla de contenido no fiable, así que se le
quitan los tokens de plantilla de chat y los saltos de línea. Un
`error_code` fuera de estos cinco se lee como `unavailable`. Una búsqueda
que se ejecutó y no encontró nada es una lista vacía de resultados, no un
rechazo.

Lo que NO es una respuesta: una excepción lanzada, un error arrojado o un
`Err` de Rust llegan al daemon como un RPC fallido, que este reporta como
que el proveedor no está disponible, con el texto del error — así que un
rechazo que querías, lanzado en vez de devuelto, pierde su código. Un
plugin que declara `web_search` y no implementa el hook responde
`UNIMPLEMENTED`, que el daemon reporta como un proveedor sin configurar.

El daemon espera como mucho 30 segundos por una búsqueda — menos si
`plugin.call_timeout_secs` es más bajo, o si lo es el propio plazo del
modelo — así que un proveedor atascado pasa al respaldo del usuario
dentro del turno. Pon a la solicitud HTTP un tiempo de espera bien por
debajo de eso — de 10 a 15 segundos — y responde `unavailable` cuando se
dispare. El daemon también se queda como mucho con `count` de tus
resultados.

## Rust

`web_search` en `PluginCapability` (o como `#[hook]` dentro de
`#[astra::plugin]`) toma una `WebSearchRequest` y devuelve
`anyhow::Result<WebSearchResponse>`. `WebSearchResponse::hits(...)` y
`WebSearchResponse::refuse(WebSearchErrorCode::…, message)` construyen la
respuesta; `.with_retry_after(secs)` va en un rechazo `RateLimited`. La
función de relleno de abajo es donde va tu cliente HTTP — el SDK no
incluye uno.

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

Sobrescribe `web_search(self, request)` en `Plugin`. Recibe una
`WebSearchRequest` y devuelve una `WebSearchResponse` — o una lista simple
de `WebSearchHit`, lo que significa que la búsqueda se ejecutó.
`WebSearchResponse.refuse(code, message, retry_after_secs=0)` comprueba el
código, así que una errata falla en tu propia prueba. El I/O bloqueante va
en un hilo (`asyncio.to_thread`): el hook comparte su bucle de eventos con
cada otro hook que sirve el plugin.

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

Dale a `plugin({...})` una función `webSearch(req, ctx)`, o sobrescribe
`webSearch(req)` en una subclase `Plugin`. Devuelve `WebSearchHit[]`, o
construye la respuesta con `WebSearch.hits(...)` / `WebSearch.refuse(code,
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

## Pruebas

El harness de nivel 1 de cada SDK dirige el hook a través de la misma
proyección de cable que ve el daemon — el recorte a `count`, el rechazo
en el cuerpo:

| SDK | Llamada | Devuelve |
|---|---|---|
| Rust | `running.web_search(WebSearchRequest { .. })` | la `WebSearchResponse` del hook |
| Python | `harness.web_search(query, count=…, freshness=…, country=…, language=…)` | una `WebSearchResponse` leída de vuelta desde el cable |
| TypeScript | `harness.webSearch(query, { count, freshness, country, language })` | una `WebSearchResponse` leída de vuelta desde el cable |

`astra-plugin test` envía una consulta real (`count` 3) y falla con todo
lo que el daemon leería mal o descartaría: un `error_code` fuera de los
cinco, más resultados de los pedidos, o un resultado cuya URL no es
`http(s)`. Le da al hook 20 segundos. Luego, haz sideload con
`astra-plugin dev`, elige el plugin bajo **IA → Búsqueda web**, y pulsa
**Probar** ahí.

## Un ejemplo

[`examples/duckduckgo-search`](../../examples/duckduckgo-search/) es un
proveedor completo en Python sin dependencias más allá del SDK: `urllib`
para la solicitud, `html.parser` para la página, pruebas sin conexión
sobre fixtures escritas a mano. Lee la página HTML de resultados de
DuckDuckGo, lo cual es **scraping no oficial**: puede romperse en cuanto
cambie el marcado, DuckDuckGo puede rechazar solicitudes automatizadas, y
los términos de DuckDuckGo rigen su uso. Es un ejemplo de la forma, no un
plugin para el catálogo.
