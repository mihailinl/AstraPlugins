"""Tests for the daemon → plugin guard (`astra_plugin_sdk.auth`).

Run: ``python -m unittest discover -s tests`` from the package root.

Exercised against a real ``grpc.aio`` server because the deny path is shape
sensitive: a rejection delivered with the wrong handler arity makes the call hang
instead of failing, and no unit test on the interceptor alone catches that.
"""

import asyncio
import unittest

import grpc

from astra_plugin_sdk.auth import (
    OFF,
    PLUGIN_TOKEN_HEADER,
    REQUIRE,
    WARN,
    CapabilityAuthInterceptor,
    capability_auth_mode,
)

SERVICE = "astra.PluginCapabilityService"


def _identity(payload):
    return payload


async def _unary(request, context):
    return b"ok"


async def _stream(request_iterator, context):
    async for _ in request_iterator:
        pass
    yield b"ok"


_HANDLERS = grpc.method_handlers_generic_handler(
    SERVICE,
    {
        # One of each shape the SDK actually serves.
        "CallTool": grpc.unary_unary_rpc_method_handler(_unary, _identity, _identity),
        "SttProcess": grpc.stream_stream_rpc_method_handler(_stream, _identity, _identity),
    },
)


class _Server:
    def __init__(self, mode: str, token: str):
        self.guard = CapabilityAuthInterceptor(token, mode)
        self._server = grpc.aio.server(interceptors=(self.guard,))
        self._server.add_generic_rpc_handlers((_HANDLERS,))
        self.port = self._server.add_insecure_port("127.0.0.1:0")

    async def __aenter__(self):
        await self._server.start()
        return self

    async def __aexit__(self, *_exc):
        await self._server.stop(0)

    def _metadata(self, token):
        return ((PLUGIN_TOKEN_HEADER, token),) if token is not None else ()

    async def unary(self, token):
        async with grpc.aio.insecure_channel(f"127.0.0.1:{self.port}") as ch:
            stub = ch.unary_unary(f"/{SERVICE}/CallTool", _identity, _identity)
            return await asyncio.wait_for(stub(b"x", metadata=self._metadata(token)), 5)

    async def bidi(self, token):
        async with grpc.aio.insecure_channel(f"127.0.0.1:{self.port}") as ch:
            stub = ch.stream_stream(f"/{SERVICE}/SttProcess", _identity, _identity)
            call = stub(metadata=self._metadata(token))
            await call.write(b"x")
            await call.done_writing()
            # `wait_for` rather than a bare drain: a shape-mismatched denial
            # would leave the server waiting for a message forever.
            return await asyncio.wait_for(_drain(call), 5)


async def _drain(call):
    return [message async for message in call]


class CapabilityAuthTest(unittest.IsolatedAsyncioTestCase):
    async def assert_unauthenticated(self, coro):
        with self.assertRaises(grpc.aio.AioRpcError) as caught:
            await coro
        self.assertEqual(caught.exception.code(), grpc.StatusCode.UNAUTHENTICATED)

    async def test_warn_accepts_missing_token_and_rejects_a_wrong_one(self):
        async with _Server(WARN, "s3cret") as server:
            self.assertTrue(server.guard.active)
            self.assertEqual(await server.unary("s3cret"), b"ok")
            self.assertEqual(await server.unary(None), b"ok")
            await self.assert_unauthenticated(server.unary("wrong"))
            # Streaming: the rejection must arrive as a status, not as silence.
            await self.assert_unauthenticated(server.bidi("wrong"))
            self.assertEqual(await server.bidi("s3cret"), [b"ok"])

    async def test_require_rejects_a_missing_token_on_both_shapes(self):
        async with _Server(REQUIRE, "s3cret") as server:
            await self.assert_unauthenticated(server.unary(None))
            await self.assert_unauthenticated(server.bidi(None))
            self.assertEqual(await server.unary("s3cret"), b"ok")

    async def test_guard_is_inert_without_a_spawn_token_or_with_mode_off(self):
        # A plugin run standalone shares no secret with anyone, so it must still
        # serve rather than fail closed against a daemon that will never call it.
        async with _Server(REQUIRE, "") as server:
            self.assertFalse(server.guard.active)
            self.assertEqual(await server.unary(None), b"ok")
        async with _Server(OFF, "s3cret") as server:
            self.assertFalse(server.guard.active)
            self.assertEqual(await server.unary("wrong"), b"ok")


class EnvSpellingTest(unittest.TestCase):
    def test_spellings(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(capability_auth_mode(), WARN)
        with mock.patch.dict(os.environ, {"ASTRA_PLUGIN_CAPABILITY_AUTH": "require"}):
            self.assertEqual(capability_auth_mode(), REQUIRE)
        with mock.patch.dict(os.environ, {"ASTRA_PLUGIN_CAPABILITY_AUTH": " OFF "}):
            self.assertEqual(capability_auth_mode(), OFF)
        # A typo must not silently weaken the check.
        with mock.patch.dict(os.environ, {"ASTRA_PLUGIN_CAPABILITY_AUTH": "yes"}):
            self.assertEqual(capability_auth_mode(), WARN)


if __name__ == "__main__":
    unittest.main()
