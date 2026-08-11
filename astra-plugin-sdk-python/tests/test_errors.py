"""The error taxonomy (production plan §5.2) — both halves, on the wire.

What these tests are actually defending:

* the eight codes and their wire spellings, which three SDKs have to agree on
  and which no compiler checks across languages;
* that a taxonomy error fills in `error` AND `error_detail`, because a daemon
  that has only one of them still has to show the user something useful;
* that every code binds to a real `PluginErrorCode` variant. A name that does
  not resolve serialises as 0, and `PLUGIN_ERROR_UNSPECIFIED` on a
  NOT_CONFIGURED failure is worse than no code at all — it tells the UI there
  is nothing to link to.

Run: `python -m unittest discover -s tests` from `astra-plugin-sdk-python/`.
"""

import unittest

from astra_plugin_sdk import (
    BadArguments,
    ErrorCode,
    InternalError,
    NotConfigured,
    NotFound,
    PluginError,
    RateLimited,
    Timeout,
    Unauthorized,
    Unavailable,
)
from astra_plugin_sdk import errors
from astra_plugin_sdk.proto import plugin_pb2

ALL = [
    BadArguments,
    NotFound,
    NotConfigured,
    Unauthorized,
    RateLimited,
    Unavailable,
    Timeout,
    InternalError,
]


def make(cls):
    """One instance of each class, since NotConfigured's first arg is the field."""
    return cls("api_key") if cls is NotConfigured else cls()


class TaxonomyTest(unittest.TestCase):
    def test_the_eight_codes_and_their_wire_spellings(self):
        """The vocabulary itself. Rust and TypeScript carry the same list."""
        self.assertEqual(
            [make(cls).code.value for cls in ALL],
            [
                "BAD_ARGUMENTS",
                "NOT_FOUND",
                "NOT_CONFIGURED",
                "UNAUTHORIZED",
                "RATE_LIMITED",
                "UNAVAILABLE",
                "TIMEOUT",
                "INTERNAL",
            ],
        )
        self.assertEqual(len(ErrorCode), 8)

    def test_every_code_binds_to_a_real_proto_variant(self):
        """A code that does not resolve goes on the wire as 0 — silently."""
        self.assertTrue(
            errors.structured_errors_supported(),
            "the vendored proto has no PluginError with the §5.2 fields",
        )
        for cls in ALL:
            detail = make(cls).to_proto()
            self.assertNotEqual(
                detail.code,
                plugin_pb2.PLUGIN_ERROR_UNSPECIFIED,
                f"{cls.__name__} resolved to UNSPECIFIED",
            )

    def test_grpc_mapping_is_total(self):
        """Every code has a transport status, for the streaming hooks."""
        for cls in ALL:
            self.assertIsNotNone(make(cls).grpc_status())


class BothHalvesTest(unittest.TestCase):
    def test_not_configured_names_the_field_in_both_halves(self):
        """THE acceptance case for §5.2: a missing API key becomes a link."""
        response = NotConfigured("api_key").to_response(
            plugin_pb2.PluginCallToolResponse, result=""
        )
        self.assertFalse(response.success)
        # The legacy string is the whole signal on a pre-5.2 daemon, so it
        # carries the code and the fix inside the sentence.
        self.assertTrue(response.error.startswith("NOT_CONFIGURED: "))
        self.assertIn("api_key", response.error)
        # …and the structured half is what a current daemon deep-links from.
        self.assertEqual(
            response.error_detail.code, plugin_pb2.PLUGIN_ERROR_NOT_CONFIGURED
        )
        self.assertEqual(response.error_detail.config_field, "api_key")

    def test_rate_limited_carries_the_wait_in_milliseconds(self):
        err = RateLimited("slow down", retry_after=2.5)
        self.assertEqual(err.retry_after_ms, 2500)
        response = err.to_response(plugin_pb2.PluginExecuteActionResponse, result="")
        self.assertEqual(response.error_detail.retry_after_ms, 2500)
        self.assertEqual(response.error, "RATE_LIMITED: slow down (Retry in 2 s.)")

    def test_retry_after_rounds_up(self):
        """A floor would tell a caller to retry inside the window it was given."""
        self.assertEqual(RateLimited(retry_after=0.0011).retry_after_ms, 2)
        self.assertEqual(RateLimited().retry_after_ms, 0)

    def test_an_error_message_survives_a_response_without_a_detail_field(self):
        """`PluginUiCallResponse` has no `success`; the string still lands."""
        response = Unavailable("upstream is down").to_response(
            plugin_pb2.PluginUiCallResponse, result_json=""
        )
        self.assertEqual(response.error, "UNAVAILABLE: upstream is down")

    def test_the_ai_stream_error_chunk_sets_the_oneof_and_the_detail(self):
        """The oneof is what tells the reader the stream ended badly."""
        chunk = Timeout("no answer in 30 s").to_response(plugin_pb2.PluginAiStreamChunk)
        self.assertEqual(chunk.WhichOneof("content"), "error")
        self.assertEqual(chunk.error_detail.code, plugin_pb2.PLUGIN_ERROR_TIMEOUT)


class AdoptionTest(unittest.TestCase):
    def test_taxonomy_errors_pass_through_untouched(self):
        err = NotConfigured("token")
        self.assertIs(PluginError.from_exception(err), err)

    def test_the_built_ins_that_have_an_obvious_code_get_it(self):
        """`json.loads` on the model's arguments raises ValueError. That is
        BAD_ARGUMENTS — calling it INTERNAL sends the reader to the wrong half
        of the system."""
        cases = [
            (ValueError("bad json"), ErrorCode.BAD_ARGUMENTS),
            (TypeError("wrong arity"), ErrorCode.BAD_ARGUMENTS),
            (KeyError("nope"), ErrorCode.NOT_FOUND),
            (TimeoutError(), ErrorCode.TIMEOUT),
            (PermissionError(), ErrorCode.UNAUTHORIZED),
            (RuntimeError("boom"), ErrorCode.INTERNAL),
        ]
        for exc, code in cases:
            with self.subTest(exc=type(exc).__name__):
                self.assertEqual(PluginError.from_exception(exc).code, code)

    def test_an_unclassified_exception_is_internal_not_a_crash(self):
        """An author who never reads `errors.py` keeps the behaviour they had."""
        adopted = PluginError.from_exception(RuntimeError("boom"))
        self.assertEqual(adopted.to_error_string(), "INTERNAL: boom")


if __name__ == "__main__":
    unittest.main()
