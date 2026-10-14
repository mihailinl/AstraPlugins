# DuckDuckGo Search (example)

> **This is an example, not a product.** It reads the results page DuckDuckGo
> serves to web browsers at `html.duckduckgo.com/html/`. That is **unofficial
> HTML scraping**: DuckDuckGo publishes no search API for it, the page's markup
> can change on any day and break this plugin without warning, DuckDuckGo may
> refuse automated requests (it answers them with a bot-challenge page), and
> **DuckDuckGo's terms of service govern any use of it**. It exists to show the
> shape of a `web_search` provider plugin in a few hundred lines of Python, and
> it is **not intended for the public catalogue** — do not submit it, or a copy
> of it, for listing.

A web search provider for Astra. Once installed, it appears under **AI → Web
search** as a provider for the assistant's `web_search` tool; pick it there and
the assistant's searches go to DuckDuckGo instead of a built-in provider.

## What it shows

- **The whole `web_search` capability** is one hook, `web_search` in
  [`src/plugin.py`](src/plugin.py): one query in, at most `request.count` hits
  out. The daemon owns everything around it — the provider chain and its
  fallback, the cache, and the fence that marks results as untrusted text for
  the model — so the plugin does none of that.
- **A refusal is an answer, not an exception.** A bot challenge or HTTP
  202/403/429 becomes `rate_limited` (with `retry_after_secs` when DuckDuckGo
  sends `Retry-After`); a network error, a server error or a page the parser
  cannot read becomes `unavailable`. The daemon acts on each — it falls back to
  the next provider instead of treating the plugin as broken.
- **Standard library only.** `urllib.request` for the request (15 s timeout,
  a browser-like `User-Agent`), `html.parser` for the page
  ([`src/ddg.py`](src/ddg.py)): titles and links from `a.result__a`, snippets
  from `.result__snippet`, DuckDuckGo's `//duckduckgo.com/l/?uddg=…` redirect
  links unwrapped to the real URL, ads and non-web links dropped.
- **Region and freshness.** The request's `country` (and `language`, to choose
  among a country's languages) becomes DuckDuckGo's `kl=` region; `freshness`
  becomes `df=` (day, week, month, year). A language with no country sets no
  region.
- **Tests with no network.** [`tests/test_ddg.py`](tests/test_ddg.py) runs the
  parser on hand-written pages in [`tests/fixtures/`](tests/fixtures/) and
  drives the hook through the SDK's `Harness`, with the HTTP layer replaced.

There is no API key, so there is no `[config]`. A provider that has one keeps
it in its own `[config]` schema, where the user sets it on the Plugins page —
see [the web search guide](../../docs/en/web-search-plugins.md).

## What it needs

- **Astra 0.2.7 or newer** (`min_astra_version`). An older Astra refuses a
  manifest that declares `web_search`.
- **Python 3.10 or newer** on the machine running Astra (`runtimes =
  ["python"]`).
- The Python SDK release that carries the `web_search` hook. Until that is on
  PyPI, install the one in this repository:
  `pip install -e ../../astra-plugin-sdk-python`.
- Outbound HTTPS to `html.duckduckgo.com`.

## Running it

```bash
cd examples/duckduckgo-search
python -m pytest tests -q          # offline: the parser and the refusals
astra-plugin test .                # against a mock daemon; makes ONE real search
astra-plugin dev .                 # sideload into the running Astra
```

`astra-plugin test` sends one real query, so it needs the network; offline, the
hook answers `unavailable` in band, which the test accepts as an answer.

Then choose **DuckDuckGo Search (example)** under **AI → Web search → Search
provider** (or as the fallback, **If it can't answer**), and press **Test**.
Its provider id is `plugin__duckduckgo-search`.

## Capabilities and permissions

| | Value | Why |
|---|---|---|
| `[capabilities]` | `web_search` | The one hook the daemon calls |
| `[permissions]` | none | It calls nothing on the daemon. The HTTPS request to DuckDuckGo is not a host call; a plugin is a process with your own network access |
