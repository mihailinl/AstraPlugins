# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""DuckDuckGo Search — an EXAMPLE `web_search` provider plugin.

The user picks this plugin as the provider for the assistant's `web_search`
tool (`plugin__duckduckgo-search`). The daemon then sends it one query at a
time and owns everything around that call: the provider chain and its
fallback, the cache, and the fence that marks results as untrusted text for
the model. So this file answers one query and does none of that itself.

It is an example and NOT a catalogue plugin: `src/ddg.py` scrapes a page
DuckDuckGo serves to browsers, which is unofficial, can break any day, and is
subject to DuckDuckGo's terms. Read README.md before running it.

Every way the search can fail is a REFUSAL the daemon reads, never an
exception: a bot challenge or HTTP 202/403/429 is `rate_limited` (so the
daemon backs off or falls back), and a network error, a server error or a page
the parser does not recognise is `unavailable`. Only a bug in this file would
reach the daemon as a failure of the plugin itself.
"""

import asyncio

from astra_plugin_sdk import (
    Plugin,
    WebSearchErrorCode,
    WebSearchHit,
    WebSearchRequest,
    WebSearchResponse,
)

from src import ddg

#: How long one search may take. The daemon's own budget for the call is
#: longer; this is the point at which waiting stops being worth it.
TIMEOUT_SECS = 15.0


class DuckDuckGoSearch(Plugin):
    """Answers `WebSearch` from DuckDuckGo's HTML results page."""

    async def web_search(self, request: WebSearchRequest):
        try:
            # urllib blocks, and the plugin's gRPC server shares this event
            # loop with every other hook, so the request runs on a thread.
            hits = await asyncio.to_thread(
                ddg.search,
                request.query,
                count=request.count,
                freshness=request.freshness,
                country=request.country,
                language=request.language,
                timeout=TIMEOUT_SECS,
            )
        except ddg.RateLimited as e:
            return WebSearchResponse.refuse(
                WebSearchErrorCode.RATE_LIMITED, str(e), retry_after_secs=e.retry_after
            )
        except ddg.Unavailable as e:
            return WebSearchResponse.refuse(WebSearchErrorCode.UNAVAILABLE, str(e))
        return [WebSearchHit(title=h.title, url=h.url, snippet=h.snippet) for h in hits]


if __name__ == "__main__":
    DuckDuckGoSearch().run()
