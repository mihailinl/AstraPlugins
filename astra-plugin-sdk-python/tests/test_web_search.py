# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""The `web_search` hook, exercised through the real servicer.

What is under test is the wire projection: a refusal the plugin MEANT is a
successful RPC with `error_code` set (the daemon falls back on `quota` and
gives up on a broken plugin, and it can only tell the two apart if they arrive
differently), the answer is cut to the requested count, and a plugin that does
not implement the hook answers UNIMPLEMENTED.

Run: `python -m pytest tests -v` from `astra-plugin-sdk-python/`.
"""

import asyncio
import unittest

import grpc

from astra_plugin_sdk import (
    Plugin,
    WebSearchErrorCode,
    WebSearchHit,
    WebSearchRequest,
    WebSearchResponse,
)
from astra_plugin_sdk.plugin import _CapabilityServicer
from astra_plugin_sdk.proto import plugin_pb2
from astra_plugin_sdk.testing import Harness, HarnessError


class FakeContext:
    def __init__(self):
        self.code = None
        self.details = ""

    def set_code(self, code):
        self.code = code

    def set_details(self, details):
        self.details = details


def run(coro):
    return asyncio.run(coro)


class Search(Plugin):
    async def web_search(self, request):
        self.seen = request
        if request.query == "spent":
            return WebSearchResponse.refuse(
                WebSearchErrorCode.RATE_LIMITED, "slow down", retry_after_secs=7
            )
        if request.query == "dicts":
            return [{"title": "A", "url": "https://a.example", "snippet": "s"}]
        return [
            WebSearchHit(title=f"hit {i}", url=f"https://example.com/{i}", published="2026-10-01")
            for i in range(5)
        ]


class WebSearchServicerTest(unittest.TestCase):
    def test_an_absent_hook_answers_unimplemented(self):
        ctx = FakeContext()
        response = run(
            _CapabilityServicer(Plugin()).WebSearch(
                plugin_pb2.PluginWebSearchRequest(query="q", count=3), ctx
            )
        )
        self.assertEqual(ctx.code, grpc.StatusCode.UNIMPLEMENTED)
        self.assertEqual(len(response.hits), 0)

    def test_the_request_is_typed_and_the_answer_is_cut_to_the_count(self):
        plugin = Search()
        ctx = FakeContext()
        response = run(
            _CapabilityServicer(plugin).WebSearch(
                plugin_pb2.PluginWebSearchRequest(
                    query="rust", count=2, freshness="week", country="DE", language=""
                ),
                ctx,
            )
        )
        self.assertIsNone(ctx.code)
        self.assertEqual(plugin.seen.freshness, "week")
        self.assertEqual(plugin.seen.country, "DE")
        self.assertEqual(plugin.seen.language, "")
        self.assertEqual(len(response.hits), 2)
        self.assertEqual(response.hits[0].url, "https://example.com/0")
        self.assertEqual(response.hits[0].published, "2026-10-01")
        self.assertEqual(response.error_code, "")

    def test_a_refusal_is_an_answer_not_a_status(self):
        ctx = FakeContext()
        response = run(
            _CapabilityServicer(Search()).WebSearch(
                plugin_pb2.PluginWebSearchRequest(query="spent", count=3), ctx
            )
        )
        self.assertIsNone(ctx.code, "a refusal the plugin meant must not fail the RPC")
        self.assertEqual(response.error_code, "rate_limited")
        self.assertEqual(response.error_message, "slow down")
        self.assertEqual(response.retry_after_secs, 7)
        self.assertEqual(len(response.hits), 0)

    def test_a_raise_is_a_status(self):
        class Broken(Plugin):
            async def web_search(self, request):
                raise RuntimeError("boom")

        ctx = FakeContext()
        run(
            _CapabilityServicer(Broken()).WebSearch(
                plugin_pb2.PluginWebSearchRequest(query="q", count=1), ctx
            )
        )
        self.assertIsNotNone(ctx.code)
        self.assertNotEqual(ctx.code, grpc.StatusCode.UNIMPLEMENTED)


class WebSearchTypesTest(unittest.TestCase):
    def test_codes_are_their_wire_strings(self):
        self.assertEqual(WebSearchErrorCode.QUOTA, "quota")
        self.assertEqual(
            [c.value for c in WebSearchErrorCode],
            ["quota", "rate_limited", "auth", "not_configured", "unavailable"],
        )

    def test_an_unknown_code_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            WebSearchResponse.refuse("out_of_coffee", "nope")
        self.assertEqual(WebSearchResponse.refuse("quota", "spent").error_code, "quota")

    def test_the_request_is_normalised(self):
        req = WebSearchRequest.from_proto(
            plugin_pb2.PluginWebSearchRequest(query="q", count=0, freshness="hour")
        )
        self.assertEqual(req.count, 1)
        self.assertEqual(req.freshness, "", "an unknown freshness reads as no restriction")
        req = WebSearchRequest.from_proto(plugin_pb2.PluginWebSearchRequest(count=50))
        self.assertEqual(req.count, 10)


class WebSearchHarnessTest(unittest.TestCase):
    def test_the_harness_drives_the_wire_path(self):
        with Harness(Search()) as h:
            got = h.web_search("dicts", count=3)
            self.assertFalse(got.refused)
            self.assertEqual(got.hits[0].title, "A")

            refused = h.web_search("spent")
            self.assertTrue(refused.refused)
            self.assertEqual(refused.error_code, WebSearchErrorCode.RATE_LIMITED)

        with Harness(Plugin()) as h, self.assertRaises(HarnessError):
            h.web_search("q")


if __name__ == "__main__":
    unittest.main()
