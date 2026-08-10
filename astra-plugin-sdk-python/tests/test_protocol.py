"""Tests for the protocol handshake (``astra_plugin_sdk.protocol``).

Run: ``python -m unittest discover -s tests`` from the package root.

The verdict is a pure function of the ``PluginRegisterResponse``, so these need
no daemon and no socket — which is the point of having split it out. What they
are guarding is that a plugin built against an Astra it cannot talk to says one
sentence and stops, instead of registering and then dying at the first RPC one
side does not have.
"""

import unittest

from astra_plugin_sdk import protocol
from astra_plugin_sdk.proto import plugin_pb2


def response(protocol_version: int, min_supported: int) -> plugin_pb2.PluginRegisterResponse:
    return plugin_pb2.PluginRegisterResponse(
        success=True,
        client_session_token="tok",
        protocol_version=protocol_version,
        min_supported_protocol=min_supported,
    )


class ProtocolHandshakeTest(unittest.TestCase):
    def test_a_daemon_whose_floor_is_two_stops_an_sdk_at_one(self):
        """THE acceptance case for 1.3: SDK at protocol 1, daemon floor 2."""
        self.assertEqual(protocol.PROTOCOL_VERSION, 1, "this test is written for protocol 1")

        resp = response(2, 2)
        resp.success = False
        resp.error = "too old"
        resp.error_detail.code = plugin_pb2.PLUGIN_ERROR_PROTOCOL_TOO_OLD
        resp.error_detail.message = (
            "Plugin 'dice-roller' speaks protocol 1; this daemon speaks 2 and accepts 2 or newer."
        )
        resp.error_detail.hint = (
            "Rebuild the plugin against an Astra plugin SDK whose PROTOCOL_VERSION is at "
            "least 2, then reinstall it."
        )

        sentence = protocol.evaluate(resp)
        self.assertIsNotNone(sentence)
        self.assertIn("2", sentence)
        self.assertIn(
            "PROTOCOL_VERSION",
            sentence,
            "the fix has to be in the sentence, not just the cause",
        )
        self.assertEqual(protocol.EXIT_PROTOCOL_INCOMPATIBLE, 78)

    def test_a_daemon_that_reports_no_protocol_is_served(self):
        """A daemon from before the handshake reports nothing — and is SERVED.

        This is Astra v0.1.0, the released build: identical ``PluginHostService``,
        every field this SDK sends already present, a session token issued to
        every plugin. The only thing it cannot do is name its own generation, and
        refusing it would have made every plugin built with this SDK dead on the
        only Astra in the world.
        """
        self.assertEqual(
            protocol.MIN_SUPPORTED_DAEMON_PROTOCOL,
            0,
            "protocol 1 IS the pre-handshake surface; a floor of 1 refuses Astra v0.1.0",
        )
        self.assertIsNone(protocol.evaluate(response(0, 0)))

    def test_a_floor_of_two_refuses_a_daemon_that_reports_no_protocol(self):
        """The refusal branch stays live, for the release that needs it."""
        sentence = protocol.evaluate(response(0, 0), floor=2)
        self.assertIsNotNone(sentence)
        self.assertIn("did not report", sentence)
        self.assertIn("2", sentence)
        self.assertIn("update Astra", sentence)

        # A daemon that DOES report, but below the floor, is named by number.
        sentence = protocol.evaluate(response(1, 1), floor=2)
        self.assertIsNotNone(sentence)
        self.assertIn("speaks protocol 1", sentence)

    def test_a_newer_daemon_is_served(self):
        """`UNIMPLEMENTED` means "absent", so a newer daemon is not a problem."""
        self.assertIsNone(protocol.evaluate(response(protocol.PROTOCOL_VERSION + 5, 1)))
        self.assertIsNone(
            protocol.evaluate(response(protocol.PROTOCOL_VERSION, protocol.PROTOCOL_VERSION))
        )

    def test_a_non_protocol_refusal_is_not_a_protocol_mismatch(self):
        """Exiting 78 over a bad auth token would send the author to the wrong fix."""
        resp = response(protocol.PROTOCOL_VERSION, protocol.PROTOCOL_VERSION)
        resp.success = False
        resp.error = "Invalid auth token"
        resp.error_detail.code = plugin_pb2.PLUGIN_ERROR_AUTH
        resp.error_detail.message = "Invalid auth token"
        self.assertIsNone(protocol.evaluate(resp))

    def test_register_declares_the_protocol_and_the_sdk(self):
        """The handshake has to be on the wire, not just in a constant."""
        req = plugin_pb2.PluginRegisterRequest(
            plugin_id="p",
            protocol_version=protocol.PROTOCOL_VERSION,
            sdk_name=protocol.SDK_NAME,
            sdk_version=protocol.sdk_version(),
        )
        self.assertEqual(req.protocol_version, 1)
        self.assertEqual(req.sdk_name, "astra-plugin-sdk-python")
        self.assertTrue(req.sdk_version, "the SDK release must be reported for triage")


if __name__ == "__main__":
    unittest.main()
