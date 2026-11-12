# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""The `image_provider` hooks, exercised through the real servicer and a socket.

What is under test is the wire projection Astra reads (from `21790d761`): a
refusal the plugin MEANT is a successful RPC with `error_code` set — the daemon
tries the person's own provider on `quota`, `rate_limited`, `not_configured`
and `unavailable`, stops on `refused`, and gives up on a plugin that raises —
the answer carries exactly one picture, and `ImageGetModels` is optional: an
absent one answers UNIMPLEMENTED, the daemon's word for "no list".

Run: `python -m pytest tests -v` from `astra-plugin-sdk-python/`.
"""

import asyncio
import unittest

import grpc

from astra_plugin_sdk import (
    IMAGE_ASPECT_RATIOS,
    AiImage,
    ImageErrorCode,
    ImageModelInfo,
    ImageModelList,
    ImageRequest,
    ImageResponse,
    Plugin,
    image_mime_type,
)
from astra_plugin_sdk.plugin import _CapabilityServicer
from astra_plugin_sdk.proto import plugin_pb2
from astra_plugin_sdk.testing import Harness, HarnessError, WireHarness

PNG = b"\x89PNG\r\n\x1a\n\x00\x01\x02\xff"
JPEG = b"\xff\xd8\xff\xe0\x07\x07\x07"
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 "


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


def cat() -> AiImage:
    return AiImage(mime_type="image/jpeg", data=JPEG, filename="cat.jpg")


class Painter(Plugin):
    """Draws a PNG, refuses by keyword, and reports what it was asked in the
    caption so a test can read the request back."""

    async def image_generate(self, request):
        refusals = {
            "spent": ImageResponse.refuse(ImageErrorCode.QUOTA, "monthly allowance used"),
            "slow": ImageResponse.refuse("rate_limited", "slow down", retry_after_secs=7),
            "nope": ImageResponse.refuse(ImageErrorCode.REFUSED, "the prompt was declined"),
            "keyless": ImageResponse.refuse(ImageErrorCode.NOT_CONFIGURED, "no API key set"),
            "down": ImageResponse.refuse(ImageErrorCode.UNAVAILABLE, "the service is down"),
        }
        if request.prompt in refusals:
            return refusals[request.prompt]
        if request.prompt == "bytes":
            return JPEG
        if request.prompt == "broken":
            raise RuntimeError("the API answered garbage")
        if request.prompt == "nothing":
            return ImageResponse()
        inputs = ",".join(
            f"{i.mime_type}:{i.filename}:{len(i.data)}" for i in request.input_images
        )
        return ImageResponse.drawn(
            PNG,
            caption=f"ratio={request.aspect_ratio or '-'} model={request.model} inputs={inputs}",
        )

    async def image_get_models(self):
        return ImageModelList(
            models=[
                ImageModelInfo("draw-1", "Draw 1"),
                ImageModelInfo("edit-1", "Edit 1", accepts_input_images=True),
            ],
            default_model="edit-1",
        )


class NoList(Plugin):
    """Draws, and lists nothing: `image_get_models` is optional."""

    async def image_generate(self, request):
        return ImageResponse.drawn(WEBP)


class TupleList(Plugin):
    async def image_generate(self, request):
        return PNG

    async def image_get_models(self):
        return [ImageModelInfo("a", "A")], ""


class ImageTypesTest(unittest.TestCase):
    def test_codes_are_their_wire_strings(self):
        self.assertEqual(
            [c.value for c in ImageErrorCode],
            ["quota", "rate_limited", "not_configured", "unavailable", "refused"],
        )
        self.assertEqual(ImageErrorCode.REFUSED, "refused")

    def test_an_unknown_code_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            ImageResponse.refuse("out_of_ink", "nope")

    def test_a_pictures_type_is_read_from_its_bytes(self):
        self.assertEqual(image_mime_type(PNG), "image/png")
        self.assertEqual(image_mime_type(JPEG), "image/jpeg")
        self.assertEqual(image_mime_type(WEBP), "image/webp")
        self.assertEqual(image_mime_type(b"GIF89a"), "", "the daemon refuses a GIF")
        self.assertEqual(ImageResponse.drawn(PNG).mime_type, "image/png")
        self.assertEqual(ImageResponse.drawn(b"???", mime_type="image/png").mime_type, "image/png")

    def test_the_request_is_read_off_the_wire(self):
        req = ImageRequest.from_proto(
            plugin_pb2.PluginImageGenerateRequest(
                prompt="a fox", aspect_ratio=" 16:9 ", model=" m ", input_images=[cat().to_proto()]
            )
        )
        self.assertEqual(req.aspect_ratio, "16:9")
        self.assertEqual(req.model, "m")
        self.assertEqual(req.input_images, [cat()])
        self.assertIn("3:4", IMAGE_ASPECT_RATIOS)

    def test_a_refusal_carries_no_picture_and_a_picture_exactly_one(self):
        refused = ImageResponse.refuse("quota", "spent").to_proto()
        self.assertEqual(len(refused.images), 0)
        drawn = ImageResponse.drawn(PNG, caption="hi").to_proto()
        self.assertEqual(len(drawn.images), 1)
        self.assertEqual(drawn.images[0].data, PNG)
        self.assertEqual(drawn.caption, "hi")
        self.assertEqual(drawn.error_code, "")


class ImageServicerTest(unittest.TestCase):
    def test_an_absent_hook_answers_unimplemented(self):
        ctx = FakeContext()
        response = run(
            _CapabilityServicer(Plugin()).ImageGenerate(
                plugin_pb2.PluginImageGenerateRequest(prompt="x"), ctx
            )
        )
        self.assertEqual(ctx.code, grpc.StatusCode.UNIMPLEMENTED)
        self.assertEqual(len(response.images), 0)

    def test_an_absent_model_list_answers_unimplemented(self):
        ctx = FakeContext()
        run(_CapabilityServicer(NoList()).ImageGetModels(plugin_pb2.Empty(), ctx))
        self.assertEqual(
            ctx.code,
            grpc.StatusCode.UNIMPLEMENTED,
            "the daemon reads UNIMPLEMENTED as `no list`; anything else is a broken plugin",
        )

    def test_every_refusal_is_an_answer_not_a_status(self):
        for prompt, code, message, retry in [
            ("spent", "quota", "monthly allowance used", 0),
            ("slow", "rate_limited", "slow down", 7),
            ("nope", "refused", "the prompt was declined", 0),
            ("keyless", "not_configured", "no API key set", 0),
            ("down", "unavailable", "the service is down", 0),
        ]:
            ctx = FakeContext()
            response = run(
                _CapabilityServicer(Painter()).ImageGenerate(
                    plugin_pb2.PluginImageGenerateRequest(prompt=prompt), ctx
                )
            )
            self.assertIsNone(ctx.code, f"`{prompt}` must not fail the RPC")
            self.assertEqual(len(response.images), 0)
            self.assertEqual(response.error_code, code)
            self.assertEqual(response.error_message, message)
            self.assertEqual(response.retry_after_secs, retry)

    def test_a_raise_or_an_empty_answer_is_a_status(self):
        for prompt in ("broken", "nothing"):
            ctx = FakeContext()
            run(
                _CapabilityServicer(Painter()).ImageGenerate(
                    plugin_pb2.PluginImageGenerateRequest(prompt=prompt), ctx
                )
            )
            self.assertIsNotNone(ctx.code, prompt)
            self.assertNotEqual(ctx.code, grpc.StatusCode.UNIMPLEMENTED, prompt)

    def test_bare_bytes_are_a_picture(self):
        ctx = FakeContext()
        response = run(
            _CapabilityServicer(Painter()).ImageGenerate(
                plugin_pb2.PluginImageGenerateRequest(prompt="bytes"), ctx
            )
        )
        self.assertIsNone(ctx.code)
        self.assertEqual(response.images[0].data, JPEG)
        self.assertEqual(response.images[0].mime_type, "image/jpeg")

    def test_a_tuple_model_list_is_accepted(self):
        ctx = FakeContext()
        listed = run(_CapabilityServicer(TupleList()).ImageGetModels(plugin_pb2.Empty(), ctx))
        self.assertIsNone(ctx.code)
        self.assertEqual([m.id for m in listed.models], ["a"])

    def test_the_capability_is_discovered_from_the_hook(self):
        self.assertIn("image_provider", run(NoList()._discover_capabilities()))
        self.assertNotIn("image_provider", run(Plugin()._discover_capabilities()))


class ImageHarnessTest(unittest.TestCase):
    def test_the_harness_drives_the_servicer(self):
        with Harness(Painter()) as h:
            got = h.image_generate("a fox", aspect_ratio="4:3", model="edit-1", input_images=[cat()])
            self.assertFalse(got.refused)
            self.assertEqual(got.data, PNG)
            self.assertEqual(got.mime_type, "image/png")
            self.assertEqual(got.caption, "ratio=4:3 model=edit-1 inputs=image/jpeg:cat.jpg:7")

            refused = h.image_generate("nope")
            self.assertTrue(refused.refused)
            self.assertEqual(refused.error_code, ImageErrorCode.REFUSED)

            listed = h.image_models()
            self.assertEqual(listed.default_model, "edit-1")
            self.assertEqual(
                [(m.id, m.accepts_input_images) for m in listed.models],
                [("draw-1", False), ("edit-1", True)],
            )

        with Harness(NoList()) as h, self.assertRaises(HarnessError) as raised:
            h.image_models()
        self.assertIn("UNIMPLEMENTED", str(raised.exception))

        with Harness(Plugin()) as h, self.assertRaises(HarnessError):
            h.image_generate("x")


class ImageWireTest(unittest.TestCase):
    """Over a socket, through `run()` — the path a real daemon takes."""

    def test_one_picture_and_the_model_list_cross_the_wire(self):
        with WireHarness(Painter()) as w:
            drawn = w.stub().ImageGenerate(
                plugin_pb2.PluginImageGenerateRequest(
                    prompt="a fox", aspect_ratio="16:9", input_images=[cat().to_proto()]
                ),
                metadata=w.metadata,
                timeout=5.0,
            )
            self.assertEqual(len(drawn.images), 1)
            self.assertEqual(drawn.images[0].data, PNG)
            self.assertEqual(drawn.caption, "ratio=16:9 model= inputs=image/jpeg:cat.jpg:7")

            refused = w.stub().ImageGenerate(
                plugin_pb2.PluginImageGenerateRequest(prompt="spent"),
                metadata=w.metadata,
                timeout=5.0,
            )
            self.assertEqual(refused.error_code, "quota")

            listed = w.stub().ImageGetModels(plugin_pb2.Empty(), metadata=w.metadata, timeout=5.0)
            self.assertEqual(listed.default_model, "edit-1")
            self.assertTrue(listed.models[1].accepts_input_images)

    def test_an_absent_model_list_is_unimplemented_on_the_wire(self):
        with WireHarness(NoList()) as w:
            with self.assertRaises(grpc.RpcError) as raised:
                w.stub().ImageGetModels(plugin_pb2.Empty(), metadata=w.metadata, timeout=5.0)
            self.assertEqual(raised.exception.code(), grpc.StatusCode.UNIMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
