# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Payload types for the hooks added in production plan §5.4.

These are the six hooks the daemon has served for releases and no Python plugin
could answer: `AiComplete`, `TtsSynthesizeStream`, `SttLoad`, `SttUnload`,
`SttGetLoadState`, `TtsActivate` — plus the per-utterance `SttTranscribeOptions`
and the `reasoning_effort` / `show_reasoning` pair the AI request grew.

Every type here is a plain dataclass with `from_proto` / `to_proto`, for the same
reason the Rust SDK has newtypes: a plugin author should never import
`plugin_pb2`, and the day the proto grows a field the change lands in one file
instead of in every plugin. `to_proto` only ever *reads* the dataclass, so a
handler may hold onto one, mutate it, and hand back a value the SDK still
understands.

Anything an author yields from a streaming hook may also be the obvious
primitive — a `str` from `ai_complete`, `bytes` from `tts_synthesize_stream` —
because that is what the first draft of a plugin yields and rejecting it teaches
nothing. `coerce_ai_chunk` / `coerce_audio_chunk` are where that is decided.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from astra_plugin_sdk.proto import plugin_pb2

__all__ = [
    "AiToolCall",
    "AiMessage",
    "AiCompleteRequest",
    "AiChunk",
    "AudioChunk",
    "SttOptions",
    "SttLoadState",
    "SttLoadStatus",
    "ThemeContribution",
    "WebSearchErrorCode",
    "WebSearchHit",
    "WebSearchRequest",
    "WebSearchResponse",
    "WEB_SEARCH_MAX_COUNT",
    "coerce_ai_chunk",
    "coerce_audio_chunk",
    "coerce_web_search_response",
]


# ── AI provider ──────────────────────────────────────────────────────────────


@dataclass
class AiToolCall:
    """One tool call the model asked for, or that the plugin is reporting."""

    id: str = ""
    name: str = ""
    arguments_json: str = ""

    @classmethod
    def from_proto(cls, msg: Any) -> "AiToolCall":
        return cls(id=msg.id, name=msg.name, arguments_json=msg.arguments_json)

    def to_proto(self) -> Any:
        return plugin_pb2.PluginAiToolCall(
            id=self.id, name=self.name, arguments_json=self.arguments_json
        )


@dataclass
class AiMessage:
    """One conversation turn handed to the provider."""

    role: str = "user"  # "user" | "assistant" | "system" | "tool"
    content: str = ""
    tool_call_id: str = ""
    tool_calls: list[AiToolCall] = field(default_factory=list)

    @classmethod
    def from_proto(cls, msg: Any) -> "AiMessage":
        return cls(
            role=msg.role,
            content=msg.content,
            tool_call_id=msg.tool_call_id,
            tool_calls=[AiToolCall.from_proto(t) for t in msg.tool_calls],
        )


@dataclass
class AiCompleteRequest:
    """Everything the daemon knows about one completion.

    `reasoning_effort` is a string, not an enum, and deliberately so: the proto
    comment spells out why (an unrecognised enum value arrives silently zeroed,
    making "this plugin is old" indistinguishable from "the user chose auto").
    `""` means the daemon did not say; `"auto"` means the user chose auto, and
    those are different.
    """

    messages: list[AiMessage] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    system_prompt: str = ""
    temperature: float = 0.0
    max_tokens: int = 0
    model: str = ""
    #: "" | "auto" | "off" | "low" | "medium" | "high" | "max"
    reasoning_effort: str = ""
    #: Whether the user wants the reasoning shown. When false, a provider should
    #: not spend tokens producing `AiChunk.thinking` nobody will read.
    show_reasoning: bool = False

    @classmethod
    def from_proto(cls, msg: Any) -> "AiCompleteRequest":
        return cls(
            messages=[AiMessage.from_proto(m) for m in msg.messages],
            tools=[
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters_json": t.parameters_json,
                }
                for t in msg.tools
            ],
            system_prompt=msg.system_prompt,
            temperature=msg.temperature,
            max_tokens=msg.max_tokens,
            model=msg.model,
            # Guarded with getattr: a plugin built against a newer SDK than the
            # vendored proto slice would otherwise fail at attribute lookup
            # rather than degrading to "the daemon did not say".
            reasoning_effort=getattr(msg, "reasoning_effort", ""),
            show_reasoning=getattr(msg, "show_reasoning", False),
        )


@dataclass
class AiChunk:
    """One piece of a streamed completion — exactly one of the five kinds.

    The proto field is a `oneof`, so a chunk that sets two things is a chunk the
    daemon reads only one of. `to_proto` resolves that with a fixed precedence
    (error, tool call, thinking, done, text) instead of leaving it to protobuf's
    last-write-wins, and the classmethods below make one kind at a time.
    """

    text: str = ""
    thinking: str = ""
    tool_call: AiToolCall | None = None
    done: bool = False
    error: str = ""

    @classmethod
    def delta(cls, text: str) -> "AiChunk":
        return cls(text=text)

    @classmethod
    def thinking_delta(cls, text: str) -> "AiChunk":
        return cls(thinking=text)

    @classmethod
    def call(cls, id: str, name: str, arguments_json: str) -> "AiChunk":
        return cls(tool_call=AiToolCall(id=id, name=name, arguments_json=arguments_json))

    @classmethod
    def finished(cls) -> "AiChunk":
        return cls(done=True)

    @classmethod
    def failed(cls, message: str) -> "AiChunk":
        return cls(error=message)

    def to_proto(self) -> Any:
        if self.error:
            return plugin_pb2.PluginAiStreamChunk(error=self.error)
        if self.tool_call is not None:
            return plugin_pb2.PluginAiStreamChunk(tool_call=self.tool_call.to_proto())
        if self.thinking:
            return plugin_pb2.PluginAiStreamChunk(thinking_delta=self.thinking)
        if self.done:
            return plugin_pb2.PluginAiStreamChunk(done=True)
        return plugin_pb2.PluginAiStreamChunk(text_delta=self.text)


def coerce_ai_chunk(value: Any) -> AiChunk:
    """Accept what an author actually yields: an `AiChunk`, or a bare string."""
    if isinstance(value, AiChunk):
        return value
    if isinstance(value, str):
        return AiChunk.delta(value)
    raise TypeError(
        f"ai_complete yielded {type(value).__name__}; yield an AiChunk or a str"
    )


# ── audio ────────────────────────────────────────────────────────────────────


@dataclass
class AudioChunk:
    """One slice of PCM, in either direction.

    `sample_rate` is only read on the first chunk of a stream — the protocol
    says so, and repeating it costs nothing but says nothing either.
    """

    data: bytes = b""
    is_last: bool = False
    sample_rate: int = 0
    #: STT request stream, first chunk only. Never set on the TTS response side.
    options: "SttOptions | None" = None

    @classmethod
    def from_proto(cls, msg: Any) -> "AudioChunk":
        opts = None
        if _has_options_field() and msg.HasField("options"):
            opts = SttOptions.from_proto(msg.options)
        return cls(
            data=msg.data,
            is_last=msg.is_last,
            sample_rate=msg.sample_rate,
            options=opts,
        )

    def to_proto(self) -> Any:
        return plugin_pb2.PluginAudioChunk(
            data=self.data, is_last=self.is_last, sample_rate=self.sample_rate
        )


def _has_options_field() -> bool:
    return "options" in {f.name for f in plugin_pb2.PluginAudioChunk.DESCRIPTOR.fields}


def coerce_audio_chunk(value: Any) -> AudioChunk:
    """Accept an `AudioChunk` or raw `bytes` (the shape of a first draft)."""
    if isinstance(value, AudioChunk):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return AudioChunk(data=bytes(value))
    raise TypeError(
        f"tts_synthesize_stream yielded {type(value).__name__}; "
        f"yield an AudioChunk or bytes"
    )


# ── STT ──────────────────────────────────────────────────────────────────────


@dataclass
class SttOptions:
    """Per-utterance decoding options, from the first chunk of `SttProcess`.

    Mirrors `SttTranscribeOptions`. A recognizer that has no notion of a field
    ignores it; nothing here is required.
    """

    #: BCP-47-ish code, or "" for auto-detect.
    language: str = ""
    #: Decoding bias — wake-word spellings, names the user says a lot.
    initial_prompt: str = ""

    @classmethod
    def from_proto(cls, msg: Any) -> "SttOptions":
        return cls(
            language=getattr(msg, "language", ""),
            initial_prompt=getattr(msg, "initial_prompt", ""),
        )


class SttLoadState(enum.IntEnum):
    """Mirrors `SttLoadStateResponse.State`, numbers included.

    `NOT_NEEDED` is 0 on purpose: it is what the daemon assumes when the hook is
    absent, so a plugin that answers it is saying the same thing as a plugin
    that does not implement the hook at all.
    """

    NOT_NEEDED = 0
    UNLOADED = 1
    LOADING = 2
    READY = 3
    FAILED = 4


@dataclass
class SttLoadStatus:
    """What `stt_load_state` answers. `detail` explains a `FAILED`."""

    state: SttLoadState = SttLoadState.NOT_NEEDED
    detail: str = ""

    def to_proto(self) -> Any:
        return plugin_pb2.SttLoadStateResponse(
            state=int(self.state), detail=self.detail
        )


# ── web search ───────────────────────────────────────────────────────────────

#: The most hits the daemon ever asks a `web_search` provider for.
WEB_SEARCH_MAX_COUNT = 10

#: The freshness values the daemon sends. Anything else (a newer daemon's
#: sixth value) reads as "" — no restriction — so a provider answers too
#: broadly rather than not at all.
_FRESHNESS = ("", "day", "week", "month", "year")


class WebSearchErrorCode(str, enum.Enum):
    """Why a provider did not search. Each code changes what the daemon does
    next, which is why they are a closed set rather than a message.

    A `str` enum, so the member IS its wire string: `WebSearchErrorCode.QUOTA ==
    "quota"`.
    """

    #: The account's allowance is spent; the daemon falls back to the next
    #: provider in the user's chain.
    QUOTA = "quota"
    #: Too many requests right now. Set `retry_after_secs` when the API says.
    RATE_LIMITED = "rate_limited"
    #: The key was refused.
    AUTH = "auth"
    #: Something the user has to set (usually the key) is missing.
    NOT_CONFIGURED = "not_configured"
    #: Anything else: the service is down, the network failed, the answer was
    #: unreadable.
    UNAVAILABLE = "unavailable"


@dataclass
class WebSearchRequest:
    """One web search, as the daemon asks a `web_search` provider for it.

    The daemon has already validated the query and normalised the region, so a
    provider maps these fields onto its own API and nothing more. Empty strings
    mean "not asked for".
    """

    #: What the model searched for.
    query: str = ""
    #: How many hits to return, 1..=`WEB_SEARCH_MAX_COUNT`. Fewer is fine; the
    #: SDK cuts a longer answer to this length.
    count: int = 5
    #: "" | "day" | "week" | "month" | "year"
    freshness: str = ""
    #: ISO 3166-1 alpha-2, upper case ("DE"), or "".
    country: str = ""
    #: ISO 639-1, lower case ("de"), or "".
    language: str = ""

    @classmethod
    def from_proto(cls, msg: Any) -> "WebSearchRequest":
        freshness = msg.freshness.strip()
        return cls(
            query=msg.query,
            # The daemon sends 1..=10. A zero still asks for one hit.
            count=max(1, min(int(msg.count), WEB_SEARCH_MAX_COUNT)),
            freshness=freshness if freshness in _FRESHNESS else "",
            country=msg.country.strip(),
            language=msg.language.strip(),
        )


@dataclass
class WebSearchHit:
    """One search result."""

    title: str = ""
    #: `http` or `https` only — the daemon drops a hit with any other scheme.
    url: str = ""
    #: Plain text. The daemon strips markup anyway, but a provider that sends
    #: text is the one whose snippets read well.
    snippet: str = ""
    #: "YYYY-MM-DD" when the source dates the page, else "".
    published: str = ""

    @classmethod
    def from_proto(cls, msg: Any) -> "WebSearchHit":
        return cls(
            title=msg.title, url=msg.url, snippet=msg.snippet, published=msg.published
        )

    def to_proto(self) -> Any:
        return plugin_pb2.PluginWebSearchHit(
            title=self.title,
            url=self.url,
            snippet=self.snippet,
            published=self.published,
        )


@dataclass
class WebSearchResponse:
    """A provider's answer: the hits, or the refusal it means.

    A refusal is an ANSWER, not an exception. ``WebSearchResponse.refuse(
    WebSearchErrorCode.QUOTA, "monthly allowance used")`` is how the daemon
    learns to fall back to another provider; raising tells it this plugin is
    broken.
    """

    hits: list[WebSearchHit] = field(default_factory=list)
    #: "" when the search ran (even with no hits), else a `WebSearchErrorCode`.
    error_code: str = ""
    #: Short and in English: the model reads it.
    error_message: str = ""
    #: With `RATE_LIMITED`: seconds to wait, 0 when unknown.
    retry_after_secs: int = 0

    @classmethod
    def of(cls, hits: "list[WebSearchHit | dict]") -> "WebSearchResponse":
        """The search ran. An empty list is a search with no results."""
        return cls(hits=[_coerce_hit(h) for h in hits])

    @classmethod
    def refuse(
        cls,
        code: "WebSearchErrorCode | str",
        message: str,
        retry_after_secs: int = 0,
    ) -> "WebSearchResponse":
        """The search did not run, for `code`'s reason.

        `code` is checked here, so a typo fails in the plugin's own test rather
        than reaching the daemon as an unknown code it reads as "unavailable".
        """
        return cls(
            error_code=WebSearchErrorCode(code).value,
            error_message=message,
            retry_after_secs=max(0, int(retry_after_secs)),
        )

    @property
    def refused(self) -> bool:
        return bool(self.error_code)

    @classmethod
    def from_proto(cls, msg: Any) -> "WebSearchResponse":
        return cls(
            hits=[WebSearchHit.from_proto(h) for h in msg.hits],
            error_code=msg.error_code,
            error_message=msg.error_message,
            retry_after_secs=msg.retry_after_secs,
        )

    def to_proto(self, count: int | None = None) -> Any:
        """The wire message, with at most `count` hits. A refusal carries none."""
        if self.error_code:
            return plugin_pb2.PluginWebSearchResponse(
                error_code=self.error_code,
                error_message=self.error_message,
                retry_after_secs=max(0, int(self.retry_after_secs)),
            )
        hits = self.hits if count is None else self.hits[: max(0, count)]
        return plugin_pb2.PluginWebSearchResponse(
            hits=[_coerce_hit(h).to_proto() for h in hits]
        )


def _coerce_hit(value: Any) -> WebSearchHit:
    if isinstance(value, WebSearchHit):
        return value
    if isinstance(value, dict):
        return WebSearchHit(
            title=str(value.get("title", "")),
            url=str(value.get("url", "")),
            snippet=str(value.get("snippet", "")),
            published=str(value.get("published", "") or ""),
        )
    raise TypeError(
        f"a web search hit must be a WebSearchHit or a dict, not {type(value).__name__}"
    )


def coerce_web_search_response(value: Any) -> WebSearchResponse:
    """Accept what an author returns: a `WebSearchResponse`, or a bare list of
    hits (`WebSearchHit` or dicts), which means the search ran."""
    if isinstance(value, WebSearchResponse):
        return value
    if isinstance(value, (list, tuple)):
        return WebSearchResponse.of(list(value))
    raise TypeError(
        f"web_search returned {type(value).__name__}; return a WebSearchResponse "
        f"or a list of WebSearchHit"
    )


# ── theme ────────────────────────────────────────────────────────────────────


@dataclass
class ThemeContribution:
    """Colours, wallpaper and shader a plugin contributes to the active theme.

    Gated on the `set_theme_contribution` permission, which Phase 4 classes
    high-risk: this is a plugin repainting the user's whole application, so the
    daemon refuses it below Tier 1 no matter what the manifest asks for.
    """

    theme_name: str = ""
    theme_description: str = ""
    #: CSS custom properties, e.g. `{"--accent": "#7c5cff"}`.
    css_variables: dict[str, str] = field(default_factory=dict)
    #: Path relative to the plugin's `ui/` directory.
    wallpaper_path: str = ""
    wallpaper_mode: str = ""  # "cover" | "contain" | "tile"
    wallpaper_opacity: float = 1.0
    #: GLSL replacing the built-in Threads effect.
    fragment_shader: str = ""
    effect_config_json: str = ""

    def to_proto(self, plugin_id: str) -> Any:
        return plugin_pb2.PluginThemeContribution(
            plugin_id=plugin_id,
            theme_name=self.theme_name,
            theme_description=self.theme_description,
            css_variables=self.css_variables,
            wallpaper_path=self.wallpaper_path,
            wallpaper_mode=self.wallpaper_mode,
            wallpaper_opacity=self.wallpaper_opacity,
            fragment_shader=self.fragment_shader,
            effect_config_json=self.effect_config_json,
        )
