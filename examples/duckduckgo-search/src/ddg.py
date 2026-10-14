# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""DuckDuckGo's HTML results page, fetched and read with the standard library.

UNOFFICIAL. DuckDuckGo publishes no search API; this reads the page its
no-JavaScript front end (`html.duckduckgo.com/html/`) serves to a browser. The
markup can change on any day without notice, DuckDuckGo may refuse automated
requests (it answers them with a bot-challenge page), and its terms of service
govern any use. This module exists to show the SHAPE of a search-provider
plugin, not to be one anybody depends on.

Nothing here knows about Astra. `search()` either returns hits or raises one of
two exceptions, and `src/plugin.py` turns those into the refusal codes the
daemon reads. Keeping the two apart is what lets `tests/` exercise the parser
on a fixture without a network or an SDK.
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser

ENDPOINT = "https://html.duckduckgo.com/html/"

#: A browser's User-Agent. The HTML front end serves the challenge page to
#: anything that does not look like one.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

#: The most of a results page this reads. A real one is ~30 KB.
MAX_BODY_BYTES = 2 * 1024 * 1024

#: `df=` — DuckDuckGo's date filter. The daemon sends these four, or "".
_FRESHNESS = {"day": "d", "week": "w", "month": "m", "year": "y"}

#: `kl=` — DuckDuckGo's region codes, keyed by ISO 3166-1 alpha-2 country.
#: The value lists the languages DuckDuckGo pairs with that country, the
#: default first. DuckDuckGo's own country part is not always ISO: the United
#: Kingdom is `uk` (ISO `GB`), and Ukraine `ua` with the language `uk`.
_REGIONS: dict[str, tuple[str, list[str]]] = {
    "AR": ("ar", ["es"]), "AT": ("at", ["de"]), "AU": ("au", ["en"]),
    "BE": ("be", ["fr", "nl"]), "BG": ("bg", ["bg"]), "BR": ("br", ["pt"]),
    "CA": ("ca", ["en", "fr"]), "CH": ("ch", ["de", "fr", "it"]),
    "CL": ("cl", ["es"]), "CN": ("cn", ["zh"]), "CO": ("co", ["es"]),
    "CZ": ("cz", ["cs"]), "DE": ("de", ["de"]), "DK": ("dk", ["da"]),
    "EE": ("ee", ["et"]), "ES": ("es", ["es"]), "FI": ("fi", ["fi"]),
    "FR": ("fr", ["fr"]), "GB": ("uk", ["en"]), "GR": ("gr", ["el"]),
    "HK": ("hk", ["tzh"]), "HR": ("hr", ["hr"]), "HU": ("hu", ["hu"]),
    "ID": ("id", ["id", "en"]), "IE": ("ie", ["en"]), "IL": ("il", ["he"]),
    "IN": ("in", ["en"]), "IT": ("it", ["it"]), "JP": ("jp", ["jp"]),
    "KR": ("kr", ["kr"]), "LT": ("lt", ["lt"]), "LV": ("lv", ["lv"]),
    "MX": ("mx", ["es"]), "MY": ("my", ["ms", "en"]), "NL": ("nl", ["nl"]),
    "NO": ("no", ["no"]), "NZ": ("nz", ["en"]), "PE": ("pe", ["es"]),
    "PH": ("ph", ["en", "tl"]), "PL": ("pl", ["pl"]), "PT": ("pt", ["pt"]),
    "RO": ("ro", ["ro"]), "RU": ("ru", ["ru"]), "SE": ("se", ["sv"]),
    "SG": ("sg", ["en"]), "SK": ("sk", ["sk"]), "SI": ("sl", ["sl"]),
    "TH": ("th", ["th"]), "TR": ("tr", ["tr"]), "TW": ("tw", ["tzh"]),
    "UA": ("ua", ["uk"]), "US": ("us", ["en", "es"]), "VE": ("ve", ["es"]),
    "VN": ("vn", ["vi"]), "ZA": ("za", ["en"]),
}

#: Where an ISO 639-1 code is not what DuckDuckGo writes for the language.
_LANGUAGE_ALIASES = {"ja": "jp", "ko": "kr"}

_VOID_TAGS = frozenset({"br", "img", "wbr", "hr", "input", "meta", "link", "source"})


class RateLimited(Exception):
    """DuckDuckGo refused this request for being automated or too frequent."""

    def __init__(self, message: str, retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after


class Unavailable(Exception):
    """The search did not happen: network, server, or a page this cannot read."""


@dataclass
class Hit:
    title: str
    url: str
    snippet: str = ""


@dataclass
class Page:
    hits: list[Hit] = field(default_factory=list)
    #: The bot-challenge ("anomaly") page instead of results.
    challenge: bool = False
    #: DuckDuckGo said in so many words that nothing matched.
    no_results: bool = False
    #: The page carried the results container at all — a page without it,
    #: without hits and without a challenge, is one this parser cannot read.
    recognised: bool = False


def region(country: str, language: str) -> str:
    """The `kl=` value for an ISO country and language, or "" for none.

    The country decides the region; the language only picks among the
    languages DuckDuckGo pairs with that country. A language with no country
    sets no region — it is not a place, and guessing one would bias the
    results somewhere the user never asked for.
    """
    entry = _REGIONS.get(country.strip().upper())
    if entry is None:
        return ""
    cc, languages = entry
    lang = language.strip().lower()
    lang = _LANGUAGE_ALIASES.get(lang, lang)
    if lang == "zh" and "tzh" in languages:
        lang = "tzh"
    return f"{cc}-{lang if lang in languages else languages[0]}"


def unwrap(href: str) -> str:
    """The destination of a result link, or "" when it is not an http(s) page.

    The HTML front end links every result through its own redirect,
    `//duckduckgo.com/l/?uddg=<the real URL, percent-encoded>&rut=…`. Ads go
    through `duckduckgo.com/y.js` instead, and come back as "" here.
    """
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    parts = urllib.parse.urlsplit(href)
    host = (parts.hostname or "").lower()
    if host == "duckduckgo.com" or host.endswith(".duckduckgo.com"):
        if parts.path.rstrip("/") != "/l":
            return ""
        target = urllib.parse.parse_qs(parts.query).get("uddg", [""])[0]
        parts = urllib.parse.urlsplit(target)
        href = target
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return href


def _text(chunks: list[str]) -> str:
    return " ".join("".join(chunks).split())


class _ResultsParser(HTMLParser):
    """Reads `a.result__a` (title + link) and `.result__snippet` per result.

    A result is a `div.result`; an ad is a `div.result.result--ad`. Titles and
    snippets carry inline markup (`<b>` around the matched words), so text is
    collected across nested tags until the element that opened the capture
    closes.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = Page()
        self._in_ad = False
        self._capture: str | None = None
        self._depth = 0
        self._buf: list[str] = []
        self._href = ""
        self._ad_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        classes = set(a.get("class", "").split())

        if (
            any(c.startswith("anomaly-modal") for c in classes)
            or a.get("id") == "challenge-form"
            or (tag == "form" and "anomaly" in a.get("action", ""))
        ):
            self.page.challenge = True
        if "no-results" in classes:
            self.page.no_results = True
        if a.get("id") == "links" or "results" in classes:
            self.page.recognised = True
        if tag == "div" and "result" in classes:
            self._in_ad = "result--ad" in classes

        if self._capture is not None:
            if tag in _VOID_TAGS:
                # `<br>` separates words the way a space does.
                self._buf.append(" ")
            else:
                self._depth += 1
            return
        if tag == "a" and "result__a" in classes:
            self._capture, self._depth, self._buf = "title", 1, []
            self._href = a.get("href", "")
            self._ad_title = self._in_ad
        elif "result__snippet" in classes and tag not in _VOID_TAGS:
            self._capture, self._depth, self._buf = "snippet", 1, []

    def handle_endtag(self, tag: str) -> None:
        if self._capture is None or tag in _VOID_TAGS:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        text = _text(self._buf)
        if self._capture == "title":
            url = "" if self._ad_title else unwrap(self._href)
            if url and text:
                self.page.hits.append(Hit(title=text, url=url))
            else:
                # Keep the slot so this result's snippet does not land on the
                # previous real hit.
                self.page.hits.append(Hit(title="", url=""))
        elif self._capture == "snippet" and self.page.hits and not self.page.hits[-1].snippet:
            self.page.hits[-1].snippet = text
        self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._buf.append(data)
        elif "bots use DuckDuckGo too" in data:
            self.page.challenge = True
        elif data.strip() in ("No results.", "No  results."):
            self.page.no_results = True


def parse(html: str) -> Page:
    """Everything the results page says, ads and unreadable links dropped."""
    parser = _ResultsParser()
    parser.feed(html)
    parser.close()
    page = parser.page
    page.hits = [h for h in page.hits if h.url and h.title]
    if page.hits:
        page.recognised = True
    return page


def _retry_after(value: str | None) -> int:
    try:
        return max(0, int((value or "").strip()))
    except ValueError:
        return 0


def fetch(query: str, *, kl: str = "", df: str = "", language: str = "", timeout: float) -> str:
    """GET the results page and return its HTML. Raises `RateLimited` or `Unavailable`."""
    params = {"q": query}
    if kl:
        params["kl"] = kl
    if df:
        params["df"] = df
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": f"{language},en;q=0.5" if language else "en",
    }
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            # 202 with a challenge page is how the HTML front end says "slow
            # down" — it is a 2xx, so urllib does not raise for it.
            if response.status == 202:
                raise RateLimited(
                    "DuckDuckGo is refusing automated requests right now (HTTP 202)",
                    _retry_after(response.headers.get("Retry-After")),
                )
            body = response.read(MAX_BODY_BYTES + 1)
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise RateLimited(
                f"DuckDuckGo refused the request (HTTP {e.code})",
                _retry_after(e.headers.get("Retry-After") if e.headers else None),
            ) from e
        raise Unavailable(f"DuckDuckGo answered HTTP {e.code}") from e
    except (http.client.HTTPException, OSError) as e:
        # URLError (DNS, refused, TLS), a timeout, a connection reset or a
        # truncated body: all "the search did not happen", none the plugin's
        # fault. OSError covers URLError and every socket error.
        reason = getattr(e, "reason", None) or e
        raise Unavailable(f"could not reach DuckDuckGo: {reason}") from e
    if len(body) > MAX_BODY_BYTES:
        raise Unavailable("DuckDuckGo's answer was larger than any results page")
    return body.decode(charset, errors="replace")


def search(
    query: str,
    *,
    count: int,
    freshness: str = "",
    country: str = "",
    language: str = "",
    timeout: float,
) -> list[Hit]:
    """Up to `count` hits for `query`. Raises `RateLimited` or `Unavailable`."""
    html = fetch(
        query,
        kl=region(country, language),
        df=_FRESHNESS.get(freshness, ""),
        language=language,
        timeout=timeout,
    )
    page = parse(html)
    if page.challenge:
        raise RateLimited("DuckDuckGo answered with its bot-challenge page")
    if not page.hits and not page.no_results and not page.recognised:
        raise Unavailable("DuckDuckGo's results page could not be read; its layout may have changed")
    return page.hits[: max(0, count)]
