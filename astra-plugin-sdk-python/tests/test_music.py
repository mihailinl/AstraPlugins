# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""The `music_provider` capability, exercised through the real servicer.

What is under test: the snapshot stream serves what the plugin last published
(at once, on every publish, and on the heartbeat); a refusal the plugin MEANT
(`MusicRefusal`) is a successful RPC with `error_code` set; a plugin that is not
a music provider answers UNIMPLEMENTED; and `on_start` runs after config.

Run: `python -m pytest tests -v` from `astra-plugin-sdk-python/`.
"""

import asyncio
import unittest

from astra_plugin_sdk import (
    MusicErrorCode,
    MusicItem,
    MusicPlayed,
    MusicPublisher,
    MusicQueue,
    MusicRefusal,
    MusicService,
    MusicSession,
    Plugin,
)
from astra_plugin_sdk.testing import Harness, HarnessError


class Player(Plugin):
    def __init__(self):
        super().__init__()
        self.started_with = None
        self.controlled = []

    async def on_start(self):
        self.started_with = dict(self.config)
        self.music.publish(
            [MusicService("spotify", "Spotify", can_search=True, can_play=True)],
            [MusicSession("spotify", "spotify", this_device=True, status="playing", title="Song",
                          controls=["play", "pause", "like"])],
        )

    async def music_control(self, request):
        if request.action == "like" and not self.config.get("signed_in", True):
            raise MusicRefusal(MusicErrorCode.AUTH, "sign in to Spotify first")
        self.controlled.append((request.session_key, request.action, request.value))

    async def music_get_queue(self, request):
        return MusicQueue(items=[MusicItem("spotify:track:1", "track", "One"),
                                 MusicItem("spotify:track:2", "track", "Two")], current_index=0)

    async def music_search(self, request):
        return [MusicItem(f"spotify:track:{i}", "track", f"{request.query} {i}") for i in range(50)]

    async def music_play(self, request):
        return MusicPlayed(item=MusicItem(request.item_ref or "spotify:track:9", "track", "Nine"),
                           session_key="spotify")


class NotAPlayer(Plugin):
    pass


class MusicProviderTests(unittest.TestCase):
    def test_the_stream_serves_what_on_start_published(self):
        with Harness(Player()).with_config({"signed_in": True}) as h:
            self.assertEqual(h.plugin.started_with, {"signed_in": True}, "on_start runs after config")
            snapshot = h.music_snapshot()
            self.assertEqual([s.service_id for s in snapshot.services], ["spotify"])
            self.assertEqual(snapshot.sessions[0].title, "Song")
            self.assertEqual(list(snapshot.sessions[0].controls), ["play", "pause", "like"])

    def test_a_refusal_is_an_answer_not_a_failure(self):
        with Harness(Player()).with_config({"signed_in": False}) as h:
            refused = h.music_control("spotify", "like")
            self.assertEqual(refused.error_code, "auth")
            self.assertEqual(refused.error_message, "sign in to Spotify first")
            done = h.music_control("spotify", "pause")
            self.assertEqual(done.error_code, "")
            self.assertEqual(h.plugin.controlled, [("spotify", "pause", "")])

    def test_answers_are_bounded_and_carry_the_plugin_reference(self):
        with Harness(Player()) as h:
            found = h.music_search("believer", limit=99)
            self.assertEqual(len(found.items), 20, "cut to music_search_max_items")
            queue = h.music_queue("spotify")
            self.assertEqual([i.title for i in queue.items], ["One", "Two"])
            self.assertEqual(queue.current_index, 0)
            played = h.music_play(item_ref="spotify:track:5")
            self.assertEqual(played.played.item_ref, "spotify:track:5")
            self.assertEqual(played.session_key, "spotify")

    def test_a_session_the_plugin_never_reported_never_reaches_the_hook(self):
        # What `astra-plugin test` sends: a key nobody reports. A hook that
        # ignores the key would otherwise like the author's real track.
        with Harness(Player()) as h:
            refused = h.music_control("astra-plugin-test.probe", "like")
            self.assertEqual(refused.error_code, "not_found")
            self.assertEqual(h.plugin.controlled, [])
            self.assertEqual(h.music_queue("astra-plugin-test.probe").error_code, "not_found")
            self.assertEqual(h.music_play(query="x", session_key="nobody").error_code, "not_found")
            # The plugin's choice of session (an empty key) is still the plugin's.
            self.assertEqual(h.music_play(query="x").error_code, "")

    def test_plain_dicts_are_accepted_where_items_are(self):
        class DictPlayer(Player):
            async def music_get_queue(self, request):
                return {"items": [{"item_ref": "spotify:track:1", "kind": "track", "title": "One"}], "current_index": 0}

            async def music_play(self, request):
                return MusicPlayed(item={"item_ref": "spotify:track:2", "kind": "track", "title": "Two"})

        with Harness(DictPlayer()) as h:
            queue = h.music_queue("spotify")
            self.assertEqual([i.title for i in queue.items], ["One"])
            self.assertEqual(h.music_play(query="two").played.title, "Two")

    def test_a_plugin_that_is_not_a_music_provider_says_so(self):
        with Harness(NotAPlayer()) as h:
            with self.assertRaises(HarnessError):
                h.music_control("x", "play")

    def test_the_publisher_wakes_a_subscriber_and_beats_when_quiet(self):
        async def scenario():
            publisher = MusicPublisher()
            stream = publisher.stream(heartbeat=0.05)
            first = await stream.__anext__()
            self.assertEqual(len(first.sessions), 0)
            publisher.publish([], [MusicSession("a", "yandex", status="playing")])
            second = await asyncio.wait_for(stream.__anext__(), 1)
            self.assertEqual(second.sessions[0].session_key, "a")
            beat = await asyncio.wait_for(stream.__anext__(), 1)
            self.assertEqual(beat.sessions[0].session_key, "a", "the heartbeat re-sends the latest")
            await stream.aclose()

        asyncio.run(scenario())

    def test_a_refusal_code_is_checked_where_it_is_written(self):
        with self.assertRaises(ValueError):
            MusicRefusal("teleport", "no")


if __name__ == "__main__":
    unittest.main()
