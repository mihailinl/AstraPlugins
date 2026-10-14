# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""The parser, the region mapping and the refusals — with no network at all.

`tests/fixtures/*.html` are hand-written pages in the shape DuckDuckGo's HTML
front end serves. Nothing here talks to DuckDuckGo: a test suite that does
fails whenever DuckDuckGo is slow, and passes whenever its markup changes in a
way this fixture does not, which is the opposite of useful.

Run: `python -m pytest tests -q` from this directory.
"""

import email.message
import io
import urllib.error
from pathlib import Path

import pytest

from astra_plugin_sdk import WebSearchErrorCode
from astra_plugin_sdk.testing import Harness

from src import ddg
from src.plugin import DuckDuckGoSearch

FIXTURES = Path(__file__).parent / "fixtures"
RESULTS = (FIXTURES / "results.html").read_text(encoding="utf-8")
CHALLENGE = (FIXTURES / "challenge.html").read_text(encoding="utf-8")


# ── the parser ───────────────────────────────────────────────────────────────


def test_results_are_read_in_order_with_ads_and_non_web_links_dropped():
    page = ddg.parse(RESULTS)
    assert not page.challenge
    assert [h.url for h in page.hits] == [
        "https://www.rust-lang.org/",
        "https://en.wikipedia.org/wiki/Rust_(programming_language)?a=1&b=2",
        "https://doc.rust-lang.org/book/",
    ]


def test_titles_and_snippets_are_plain_text():
    hits = ddg.parse(RESULTS).hits
    # `<b>` around the matched word is flattened, entities are decoded.
    assert hits[0].title == "Rust Programming Language"
    assert hits[0].snippet == (
        "A language empowering everyone to build reliable and efficient software. "
        "Rust is fast & memory-efficient."
    )
    # A `<div>` snippet reads the same as an `<a>` one, and `<br>` is a space.
    assert hits[2].snippet == "by Steve Klabnik and Carol Nichols — an introductory book about Rust."


def test_an_ads_snippet_does_not_land_on_a_real_hit():
    snippets = [h.snippet for h in ddg.parse(RESULTS).hits]
    assert not any("advertisement" in s for s in snippets)
    assert not any("no http(s) URL" in s for s in snippets)


def test_the_challenge_page_is_recognised():
    page = ddg.parse(CHALLENGE)
    assert page.challenge
    assert page.hits == []


def test_no_results_is_an_answer_and_an_unknown_page_is_not():
    page = ddg.parse('<div id="links" class="results"><div class="no-results">No results.</div></div>')
    assert page.no_results and page.hits == []
    page = ddg.parse("<html><body><p>Something else entirely</p></body></html>")
    assert not (page.no_results or page.recognised or page.challenge)


@pytest.mark.parametrize(
    "href, url",
    [
        ("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1&rut=x", "https://example.com/a?b=1"),
        ("https://duckduckgo.com/l/?uddg=http%3A%2F%2Fexample.org%2F", "http://example.org/"),
        ("https://example.net/page", "https://example.net/page"),
        ("https://duckduckgo.com/y.js?ad_domain=x", ""),
        ("//duckduckgo.com/l/?uddg=ftp%3A%2F%2Fexample.com%2Ffile", ""),
        ("javascript:alert(1)", ""),
        ("/relative/path", ""),
    ],
)
def test_result_links_are_unwrapped_to_web_pages_only(href, url):
    assert ddg.unwrap(href) == url


@pytest.mark.parametrize(
    "country, language, kl",
    [
        ("DE", "", "de-de"),
        ("de", "de", "de-de"),
        ("GB", "en", "uk-en"),  # DuckDuckGo writes the United Kingdom as `uk`
        ("UA", "uk", "ua-uk"),
        ("CH", "fr", "ch-fr"),
        ("CH", "ja", "ch-de"),  # a language the country is not paired with: its default
        ("JP", "ja", "jp-jp"),
        ("TW", "zh", "tw-tzh"),
        ("", "de", ""),  # a language is not a place
        ("XX", "en", ""),
    ],
)
def test_the_region_comes_from_the_country(country, language, kl):
    assert ddg.region(country, language) == kl


# ── fetch: what each HTTP answer becomes ─────────────────────────────────────


class _Response:
    def __init__(self, status: int, body: bytes = b"", headers: dict | None = None):
        self.status = status
        self._body = body
        self.headers = email.message.Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code: int, retry_after: str | None = None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://html.duckduckgo.com/html/", code, "x", headers, io.BytesIO())


def test_a_202_is_rate_limited(monkeypatch):
    monkeypatch.setattr(ddg.urllib.request, "urlopen", lambda req, timeout: _Response(202, b""))
    with pytest.raises(ddg.RateLimited):
        ddg.fetch("q", timeout=1)


@pytest.mark.parametrize("code", [403, 429])
def test_403_and_429_are_rate_limited_with_retry_after(monkeypatch, code):
    def refuse(req, timeout):
        raise _http_error(code, "12")

    monkeypatch.setattr(ddg.urllib.request, "urlopen", refuse)
    with pytest.raises(ddg.RateLimited) as e:
        ddg.fetch("q", timeout=1)
    assert e.value.retry_after == 12


def test_server_and_network_errors_are_unavailable(monkeypatch):
    def server_error(req, timeout):
        raise _http_error(503)

    monkeypatch.setattr(ddg.urllib.request, "urlopen", server_error)
    with pytest.raises(ddg.Unavailable):
        ddg.fetch("q", timeout=1)

    def offline(req, timeout):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(ddg.urllib.request, "urlopen", offline)
    with pytest.raises(ddg.Unavailable):
        ddg.fetch("q", timeout=1)

    def slow(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(ddg.urllib.request, "urlopen", slow)
    with pytest.raises(ddg.Unavailable):
        ddg.fetch("q", timeout=1)


def test_the_request_carries_the_query_region_and_freshness(monkeypatch):
    seen = {}

    def capture(req, timeout):
        seen["url"] = req.full_url
        seen["ua"] = req.get_header("User-agent")
        seen["timeout"] = timeout
        return _Response(200, RESULTS.encode("utf-8"))

    monkeypatch.setattr(ddg.urllib.request, "urlopen", capture)
    hits = ddg.search("rust lang", count=2, freshness="week", country="DE", language="de", timeout=15)
    assert len(hits) == 2
    assert seen["url"].startswith("https://html.duckduckgo.com/html/?")
    assert "q=rust+lang" in seen["url"]
    assert "kl=de-de" in seen["url"]
    assert "df=w" in seen["url"]
    assert seen["ua"].startswith("Mozilla/5.0")
    assert seen["timeout"] == 15


# ── the plugin: what the daemon receives ─────────────────────────────────────


def test_the_plugin_answers_with_hits_cut_to_the_count(monkeypatch):
    monkeypatch.setattr(ddg, "fetch", lambda query, **kw: RESULTS)
    with Harness(DuckDuckGoSearch()) as h:
        answer = h.web_search("rust", count=2)
    assert not answer.refused
    assert [hit.url for hit in answer.hits] == [
        "https://www.rust-lang.org/",
        "https://en.wikipedia.org/wiki/Rust_(programming_language)?a=1&b=2",
    ]


def test_a_challenge_reaches_the_daemon_as_rate_limited(monkeypatch):
    monkeypatch.setattr(ddg, "fetch", lambda query, **kw: CHALLENGE)
    with Harness(DuckDuckGoSearch()) as h:
        answer = h.web_search("rust")
    assert answer.error_code == WebSearchErrorCode.RATE_LIMITED
    assert answer.hits == []


def test_a_rate_limit_carries_its_retry_after(monkeypatch):
    def refuse(query, **kw):
        raise ddg.RateLimited("slow down", retry_after=30)

    monkeypatch.setattr(ddg, "fetch", refuse)
    with Harness(DuckDuckGoSearch()) as h:
        answer = h.web_search("rust")
    assert answer.error_code == WebSearchErrorCode.RATE_LIMITED
    assert answer.retry_after_secs == 30


def test_an_unreadable_page_or_no_network_is_unavailable(monkeypatch):
    monkeypatch.setattr(ddg, "fetch", lambda query, **kw: "<html><body>?</body></html>")
    with Harness(DuckDuckGoSearch()) as h:
        assert h.web_search("rust").error_code == WebSearchErrorCode.UNAVAILABLE

    def offline(query, **kw):
        raise ddg.Unavailable("could not reach DuckDuckGo: no route to host")

    monkeypatch.setattr(ddg, "fetch", offline)
    with Harness(DuckDuckGoSearch()) as h:
        answer = h.web_search("rust")
    assert answer.error_code == WebSearchErrorCode.UNAVAILABLE
    assert "no route to host" in answer.error_message


def test_no_results_is_an_empty_answer_not_a_refusal(monkeypatch):
    monkeypatch.setattr(
        ddg, "fetch",
        lambda query, **kw: '<div id="links" class="results"><div class="no-results">No results.</div></div>',
    )
    with Harness(DuckDuckGoSearch()) as h:
        answer = h.web_search("zzzzzzzzzzzz")
    assert not answer.refused
    assert answer.hits == []
