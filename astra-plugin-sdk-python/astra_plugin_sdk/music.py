# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai
"""The ``music_provider`` capability: report what music services play, drive them.

A plugin that declares ``[capabilities] music_provider = true`` is a source of
media sessions for Astra's media hub. The music widget, the Dynamic Island and
the assistant's media tools then reach the services it talks to — like a track
IN the service, read its queue, search its catalogue, start playback — without
the plugin drawing any UI of its own.

Two halves:

* **Reporting** is push. Call ``self.music.publish(services, sessions)`` whenever
  what you would report changes; the SDK serves the daemon's long-lived
  ``MusicSubscribe`` stream from the latest call, re-sends it every
  ``MUSIC_SNAPSHOT_HEARTBEAT_SECS`` so a silent plugin is noticed, and lets the
  daemon reconnect at will. Every publish is the WHOLE set: a session you leave
  out has ended.
* **Answering** is four hooks on :class:`~astra_plugin_sdk.Plugin`:
  ``music_control`` (required), ``music_get_queue``, ``music_search`` and
  ``music_play``. A refusal you mean — the user is not signed in, the service
  needs a subscription, nothing is playing anywhere — is
  ``raise MusicRefusal(MusicErrorCode.NO_ACTIVE_DEVICE, "…")``: an ANSWER the
  daemon shows to the person. Any other exception reports the plugin as failing.
"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterable

from astra_plugin_sdk.limits import (
    MUSIC_SEARCH_MAX_ITEMS,
    MUSIC_SNAPSHOT_HEARTBEAT_SECS,
    MUSIC_SNAPSHOT_MAX_SESSIONS,
)
from astra_plugin_sdk.proto import plugin_pb2

__all__ = [
    "MusicErrorCode",
    "MusicRefusal",
    "MusicService",
    "MusicSession",
    "MusicItem",
    "MusicQueue",
    "MusicPlayed",
    "MusicControlRequest",
    "MusicQueueRequest",
    "MusicSearchRequest",
    "MusicPlayRequest",
    "MusicPublisher",
    "MUSIC_CONTROLS",
]

#: The verbs a session may list in ``controls`` (``MusicControl`` accepts the
#: first ten; ``queue`` and ``play_into`` say the session answers
#: ``music_get_queue`` / ``music_play``). The daemon drops anything else.
MUSIC_CONTROLS = (
    "play", "pause", "next", "previous", "seek", "like", "unlike", "shuffle", "repeat", "volume",
    "queue", "play_into",
)


class MusicErrorCode(str, enum.Enum):
    """A refusal a music provider means. The member IS its wire string."""

    NOT_SUPPORTED = "not_supported"
    NOT_FOUND = "not_found"
    NO_ACTIVE_DEVICE = "no_active_device"
    AUTH = "auth"
    PREMIUM_REQUIRED = "premium_required"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class MusicRefusal(Exception):
    """Raise from a music hook to ANSWER with a refusal (not to fail).

    ``code`` is checked here, so a typo fails in the plugin's own test rather
    than reaching the daemon as an unknown code it reads as "unavailable".
    """

    def __init__(self, code: "MusicErrorCode | str", message: str, retry_after_secs: int = 0):
        self.code = MusicErrorCode(code).value
        self.message = message
        self.retry_after_secs = max(0, int(retry_after_secs))
        super().__init__(message)


@dataclass
class MusicService:
    """A service the plugin reaches, signed in or not."""

    service_id: str
    #: For the user; a ``$key`` resolves through the plugin's locales.
    name: str
    #: "ready" | "signed_out" | "error" | "disabled"
    status: str = "ready"
    status_message: str = ""
    can_search: bool = False
    can_play: bool = False

    def to_proto(self) -> Any:
        return plugin_pb2.PluginMusicService(
            service_id=self.service_id,
            name=self.name,
            status=self.status,
            status_message=self.status_message,
            can_search=self.can_search,
            can_play=self.can_play,
        )


@dataclass
class MusicSession:
    """One playback a service reports."""

    #: ``[A-Za-z0-9._-]{1,64}``, stable while the plugin runs.
    session_key: str
    service_id: str
    #: The audio may be coming out of THIS computer. Only such a session can
    #: stand for an OS media session; any other is shown as a remote one.
    this_device: bool = False
    device_name: str = ""
    #: OS session ids of an app that plays nothing but this service (the
    #: Spotify executable, an MPRIS player name): a match pairs on its own.
    exclusive_app_hints: list[str] = field(default_factory=list)
    #: Hosts of many things (browsers): a match pairs only when the song agrees.
    shared_app_hints: list[str] = field(default_factory=list)
    #: "playing" | "paused" | "stopped" | "buffering"
    status: str = "stopped"
    title: str = ""
    artist: str = ""
    album: str = ""
    #: https only; the daemon fetches and caches it.
    artwork_url: str = ""
    position_seconds: float = 0.0
    duration_seconds: float = 0.0
    track_ref: str = ""
    #: https, or an app scheme the service registers (``spotify:``).
    track_url: str = ""
    liked: bool = False
    shuffle: bool = False
    #: "off" | "track" | "context"
    repeat: str = "off"
    #: -1 when unknown
    volume_percent: int = -1
    #: Which verbs this session takes — see :data:`MUSIC_CONTROLS`.
    controls: list[str] = field(default_factory=list)

    def to_proto(self) -> Any:
        return plugin_pb2.PluginMusicSession(
            session_key=self.session_key,
            service_id=self.service_id,
            this_device=self.this_device,
            device_name=self.device_name,
            exclusive_app_hints=list(self.exclusive_app_hints),
            shared_app_hints=list(self.shared_app_hints),
            status=self.status,
            title=self.title,
            artist=self.artist,
            album=self.album,
            artwork_url=self.artwork_url,
            position_seconds=float(self.position_seconds),
            duration_seconds=float(self.duration_seconds),
            track_ref=self.track_ref,
            track_url=self.track_url,
            liked=self.liked,
            shuffle=self.shuffle,
            repeat=self.repeat,
            volume_percent=int(self.volume_percent),
            controls=list(self.controls),
        )


@dataclass
class MusicItem:
    """Something in a catalogue or a queue."""

    #: Your own reference; it comes back in ``music_play``.
    item_ref: str
    #: "track" | "album" | "artist" | "playlist" | "wave"
    kind: str
    title: str
    subtitle: str = ""
    album: str = ""
    artwork_url: str = ""
    duration_seconds: float = 0.0
    liked: bool = False
    service_id: str = ""

    def to_proto(self) -> Any:
        return plugin_pb2.PluginMusicItem(
            item_ref=self.item_ref,
            kind=self.kind,
            title=self.title,
            subtitle=self.subtitle,
            album=self.album,
            artwork_url=self.artwork_url,
            duration_seconds=float(self.duration_seconds),
            liked=self.liked,
            service_id=self.service_id,
        )


@dataclass
class MusicQueue:
    """A session's queue around the playing item."""

    items: list[MusicItem] = field(default_factory=list)
    #: The playing item's index in ``items``, -1 if none.
    current_index: int = -1


@dataclass
class MusicPlayed:
    """What ``music_play`` started, and the session it plays in."""

    item: MusicItem | None = None
    session_key: str = ""


@dataclass
class MusicControlRequest:
    session_key: str
    #: One of the session's ``controls``.
    action: str
    #: "seek": seconds; "volume": "0".."100"; "shuffle": "on" | "off";
    #: "repeat": "off" | "track" | "context"; empty otherwise.
    value: str = ""

    @classmethod
    def from_proto(cls, msg: Any) -> "MusicControlRequest":
        return cls(session_key=msg.session_key, action=msg.action, value=msg.value)


@dataclass
class MusicQueueRequest:
    session_key: str
    limit: int = 20

    @classmethod
    def from_proto(cls, msg: Any) -> "MusicQueueRequest":
        return cls(session_key=msg.session_key, limit=max(1, min(int(msg.limit or 20), 50)))


@dataclass
class MusicSearchRequest:
    query: str
    #: "" = anything, else an item kind.
    kind: str = ""
    limit: int = 10
    #: "" = any service this plugin reaches.
    service_id: str = ""
    #: The UI language, ISO 639-1.
    language: str = ""

    @classmethod
    def from_proto(cls, msg: Any) -> "MusicSearchRequest":
        return cls(
            query=msg.query,
            kind=msg.kind,
            limit=max(1, min(int(msg.limit or 10), MUSIC_SEARCH_MAX_ITEMS)),
            service_id=msg.service_id,
            language=msg.language,
        )


@dataclass
class MusicPlayRequest:
    #: An item you handed out, or empty with ``query``.
    item_ref: str = ""
    query: str = ""
    #: Narrows ``query``; "" = a track.
    kind: str = ""
    #: "now" | "next" | "end"
    mode: str = "now"
    #: Play into this session; empty = your choice.
    session_key: str = ""
    #: "" = your choice.
    service_id: str = ""

    @classmethod
    def from_proto(cls, msg: Any) -> "MusicPlayRequest":
        return cls(
            item_ref=msg.item_ref,
            query=msg.query,
            kind=msg.kind,
            mode=msg.mode or "now",
            session_key=msg.session_key,
            service_id=msg.service_id,
        )


def _coerce(value: Any, cls: type) -> Any:
    if isinstance(value, cls):
        return value
    if isinstance(value, dict):
        return cls(**value)
    raise TypeError(f"expected {cls.__name__} or a dict, got {type(value).__name__}")


class MusicPublisher:
    """What the plugin last reported, served as the ``MusicSubscribe`` stream.

    ``publish`` may be called from any coroutine on the plugin's loop, as
    often as anything changes; subscribers always read the latest whole set.
    """

    def __init__(self) -> None:
        self._snapshot = plugin_pb2.PluginMusicSnapshot()
        self._version = 0
        self._changed: asyncio.Condition | None = None

    def _condition(self) -> asyncio.Condition:
        if self._changed is None:
            self._changed = asyncio.Condition()
        return self._changed

    def publish(self, services: Iterable[Any] = (), sessions: Iterable[Any] = ()) -> None:
        """Replace everything reported. A session left out has ended."""
        snapshot = plugin_pb2.PluginMusicSnapshot(
            services=[_coerce(s, MusicService).to_proto() for s in services],
            sessions=[_coerce(s, MusicSession).to_proto() for s in sessions][:MUSIC_SNAPSHOT_MAX_SESSIONS],
        )
        self._snapshot = snapshot
        self._version += 1
        changed = self._condition()

        async def notify() -> None:
            async with changed:
                changed.notify_all()

        try:
            asyncio.get_running_loop().create_task(notify())
        except RuntimeError:
            # No loop yet (published before the plugin started): the first
            # subscriber reads the snapshot anyway.
            pass

    @property
    def snapshot(self) -> Any:
        """The latest snapshot, as the daemon will receive it."""
        return self._snapshot

    def knows_session(self, session_key: str) -> bool:
        """Whether the latest snapshot reports a session with this key."""
        return any(s.session_key == session_key for s in self._snapshot.sessions)

    async def stream(self, heartbeat: float = MUSIC_SNAPSHOT_HEARTBEAT_SECS) -> AsyncIterator[Any]:
        """The latest snapshot now, then on every publish, and every ``heartbeat``."""
        changed = self._condition()
        seen = self._version
        yield self._snapshot
        while True:
            async with changed:
                try:
                    await asyncio.wait_for(changed.wait_for(lambda: self._version != seen), heartbeat)
                except asyncio.TimeoutError:
                    pass
            seen = self._version
            yield self._snapshot
