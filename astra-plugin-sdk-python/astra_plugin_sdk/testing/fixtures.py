"""Golden audio, config fuzz sets, and the pytest fixtures that hand them out.

This module is registered as a pytest plugin through the `pytest11` entry point
in `pyproject.toml`, so a plugin's tests get `astra_harness`, `astra_wire`,
`golden_pcm` and `fuzz_configs` with no `conftest.py`. Importing it directly
works too — nothing here needs pytest to exist.
"""

from __future__ import annotations

import math
import struct
from typing import Any, Callable, Iterator

from astra_plugin_sdk import limits
from astra_plugin_sdk.proto import plugin_pb2
from astra_plugin_sdk.types import AudioChunk

__all__ = [
    "golden_pcm_f32",
    "golden_pcm_i16",
    "wake_seed_burst",
    "backpressure_burst",
    "fuzz_configs",
    "FUZZ_CONFIGS",
]

#: Sample rate the daemon's voice pipeline runs at, everywhere.
SAMPLE_RATE = 16000

#: How long the wake-word seed buffer can be: the daemon replays the audio it
#: had already captured when the wake word fired, so the first thing a
#: recognizer sees is a burst of history, not live audio. `spec/limits.yaml`
#: sizes the channel for this exact case.
WAKE_SEED_SECONDS = 8.0

#: The daemon's batch size on the voice path.
BATCH_MS = 100


def golden_pcm_f32(
    seconds: float = 1.0,
    *,
    sample_rate: int = SAMPLE_RATE,
    frequency: float = 440.0,
    amplitude: float = 0.25,
) -> bytes:
    """Deterministic 32-bit float PCM — the format `SttProcess` carries.

    A sine, not noise or silence: silence is indistinguishable from a bug that
    sends nothing, and a random buffer makes a failure unreproducible. Same
    bytes on every machine and every run, so a test that asserts on a byte count
    or a hash keeps meaning the same thing.
    """
    frames = int(seconds * sample_rate)
    step = 2.0 * math.pi * frequency / sample_rate
    return struct.pack(f"<{frames}f", *(amplitude * math.sin(step * n) for n in range(frames)))


def golden_pcm_i16(
    seconds: float = 1.0,
    *,
    sample_rate: int = SAMPLE_RATE,
    frequency: float = 440.0,
    amplitude: float = 0.25,
) -> bytes:
    """The same signal as 16-bit signed PCM, for a plugin that wants that."""
    frames = int(seconds * sample_rate)
    step = 2.0 * math.pi * frequency / sample_rate
    peak = int(amplitude * 32767)
    return struct.pack(
        f"<{frames}h", *(int(peak * math.sin(step * n)) for n in range(frames))
    )


def _chunks(
    pcm: bytes, *, sample_rate: int, batch_ms: int, bytes_per_frame: int
) -> list[AudioChunk]:
    per_chunk = max(1, int(sample_rate * batch_ms / 1000) * bytes_per_frame)
    out = [
        AudioChunk(data=pcm[i : i + per_chunk], sample_rate=sample_rate)
        for i in range(0, len(pcm), per_chunk)
    ]
    if out:
        out[-1].is_last = True
    return out


def wake_seed_burst(
    *,
    seconds: float = WAKE_SEED_SECONDS,
    sample_rate: int = SAMPLE_RATE,
    batch_ms: int = BATCH_MS,
) -> list[AudioChunk]:
    """The wake-word seed dump, chunked the way the daemon sends it.

    ~8 seconds of already-captured audio, in 100 ms batches, arriving at once
    the instant the wake word fires. This is the burst `spec/limits.yaml` sizes
    the STT audio channel for, and it is what a recognizer that assumes audio
    arrives in real time gets wrong.
    """
    return _chunks(
        golden_pcm_f32(seconds, sample_rate=sample_rate),
        sample_rate=sample_rate,
        batch_ms=batch_ms,
        bytes_per_frame=4,
    )


def backpressure_burst(
    *, chunks: int = limits.STT_AUDIO_CHANNEL_CAPACITY + 100, frames: int = 160
) -> list[AudioChunk]:
    """More chunks than the SDK's audio queue can hold, each one identifiable.

    THE CONDITION THIS REPRODUCES. The SDK buffers inbound STT audio in a queue
    bounded by `limits.STT_AUDIO_CHANNEL_CAPACITY` (500). A smaller bound on
    either side of a two-channel bridge is the real capacity — which is how a
    32-slot SDK queue silently truncated every utterance past its first fraction
    against a 500-slot daemon channel, with no error anywhere. A correct SDK
    slows the sender; a broken one drops the tail.

    Each chunk's first four bytes are its index, so a test can assert not only
    that 600 chunks arrived but that they arrived *in order and complete*.
    """
    out = []
    for i in range(chunks):
        payload = struct.pack("<I", i) + bytes(frames * 4 - 4)
        out.append(AudioChunk(data=payload, sample_rate=SAMPLE_RATE))
    if out:
        out[-1].is_last = True
    return out


def chunk_index(chunk: AudioChunk | plugin_pb2.PluginAudioChunk) -> int:
    """Read back the index `backpressure_burst` stamped into a chunk."""
    data = chunk.data
    return struct.unpack("<I", data[:4])[0]


#: Config values a plugin will meet and usually has not thought about.
#:
#: Every entry has been a real bug somewhere: a user clearing a text field
#: leaves `""` and not the default; a number field arrives as a string from a
#: JSON form; a nested object arrives when the schema said scalar; and `None` is
#: what the daemon sends for a key the user has never touched. A plugin is
#: allowed to reject any of them — what it may not do is raise out of
#: `on_config_changed`, because that hook has nowhere to put a failure and the
#: plugin then runs on with the config it had.
FUZZ_CONFIGS: tuple[dict[str, Any], ...] = (
    {},
    {"unknown_key": "surprise"},
    {"api_key": ""},
    {"api_key": None},
    {"count": "12"},
    {"count": -1},
    {"count": 10**18},
    {"count": 1.5},
    {"enabled": "false"},
    {"nested": {"a": {"b": [1, 2, 3]}}},
    {"text": "ünïcödé — 🎧 \x00 \n\t"},
    {"text": "x" * 100_000},
    {"list": []},
    {"list": [None, {}, []]},
)


def fuzz_configs() -> tuple[dict[str, Any], ...]:
    """The fuzz set, as a tuple you can parametrize over."""
    return FUZZ_CONFIGS


# ── pytest fixtures (registered via the `pytest11` entry point) ──────────────

try:  # pragma: no cover — pytest is optional at runtime
    import pytest
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore[assignment]


if pytest is not None:

    @pytest.fixture
    def astra_harness() -> Iterator[Callable[..., Any]]:
        """Build level-1 harnesses; every one is stopped when the test ends.

            def test_word_count(astra_harness):
                h = astra_harness(TextUtils(), config={"max_text_length": 20})
                assert h.call_tool("word_count", text="a b").json["words"] == 2

        A factory rather than a fixture returning one harness, because only the
        test knows which plugin, with which config.
        """
        from astra_plugin_sdk.testing.harness import Harness

        built: list[Harness] = []

        def make(plugin, *, config: dict | None = None, language: str = "en", **kwargs):
            harness = Harness(plugin, **kwargs)
            if config is not None:
                harness.with_config(config)
            harness.with_language(language)
            built.append(harness)
            return harness.start()

        try:
            yield make
        finally:
            for harness in built:
                harness.stop()

    @pytest.fixture
    def astra_wire() -> Iterator[Callable[..., Any]]:
        """Build level-2 wire harnesses; every one is stopped when the test ends."""
        from astra_plugin_sdk.testing.wire import WireHarness

        built: list[WireHarness] = []

        def make(plugin, **kwargs):
            harness = WireHarness(plugin, **kwargs)
            built.append(harness)
            return harness.start()

        try:
            yield make
        finally:
            for harness in built:
                harness.stop()

    @pytest.fixture
    def golden_pcm() -> bytes:
        """One second of deterministic 16 kHz f32 PCM."""
        return golden_pcm_f32(1.0)

    @pytest.fixture
    def wake_seed() -> list[AudioChunk]:
        """The 8-second wake-word seed dump, in 100 ms chunks."""
        return wake_seed_burst()

    @pytest.fixture(params=FUZZ_CONFIGS, ids=lambda c: str(sorted(c))[:40])
    def fuzz_config(request) -> dict[str, Any]:
        """One config from the fuzz set, parametrized over all of them."""
        return request.param
