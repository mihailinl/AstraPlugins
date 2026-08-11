# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Test your plugin without Astra running — production plan §5.6.

Two levels, and both are here because neither is enough on its own.

**Level 1, `Harness`** — the plugin in this process, driven through its own gRPC
servicer. Fast (milliseconds), synchronous, no sockets. This is where most of a
plugin's tests belong: tool dispatch, argument round-tripping, schemas, error
codes, config handling, STT streaming, and what the plugin asked the daemon for
(`RecordingHost`, with failure injection).

    from astra_plugin_sdk.testing import Harness

    def test_word_count():
        with Harness(TextUtils()) as h:
            assert h.call_tool("word_count", text="one two").json["words"] == 2

**Level 2, `WireHarness` + `MockDaemon`** — the plugin's real `run()` path,
registering with a mock daemon over loopback gRPC and answering a real
`PluginCapabilityServiceStub`. Slower, and it catches the class of bug level 1
structurally cannot: handler registration, descriptor mismatch, the capability
interceptor, the session token, and 500-slot back-pressure.

    from astra_plugin_sdk.testing import WireHarness

    def test_over_the_wire():
        with WireHarness(TextUtils()) as w:
            assert w.call_tool("word_count", text="a b c").success

Both are also available as pytest fixtures — `astra_harness`, `astra_wire`,
`golden_pcm`, `wake_seed`, `fuzz_config` — registered automatically, with no
`conftest.py` to write. See `fixtures.py`.
"""

from astra_plugin_sdk.testing.fixtures import (
    FUZZ_CONFIGS,
    SAMPLE_RATE,
    backpressure_burst,
    chunk_index,
    fuzz_configs,
    golden_pcm_f32,
    golden_pcm_i16,
    wake_seed_burst,
)
from astra_plugin_sdk.testing.harness import (
    FakeContext,
    Harness,
    HarnessError,
    Result,
    SttEvent,
)
from astra_plugin_sdk.testing.recording_host import (
    ChatMessage,
    FiredTrigger,
    LogLine,
    RecordingHost,
    UiPush,
    Variable,
)
from astra_plugin_sdk.testing.wire import MockDaemon, WireError, WireHarness

__all__ = [
    # level 1
    "Harness",
    "HarnessError",
    "Result",
    "SttEvent",
    "FakeContext",
    "RecordingHost",
    "LogLine",
    "FiredTrigger",
    "Variable",
    "UiPush",
    "ChatMessage",
    # level 2
    "WireHarness",
    "MockDaemon",
    "WireError",
    # fixtures and golden data
    "golden_pcm_f32",
    "golden_pcm_i16",
    "wake_seed_burst",
    "backpressure_burst",
    "chunk_index",
    "fuzz_configs",
    "FUZZ_CONFIGS",
    "SAMPLE_RATE",
]
