// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! The `music_provider` capability: report what music services play, drive them.
//!
//! A plugin declaring `[capabilities] music_provider = true` is a source of
//! media sessions for Astra's media hub — the music widget, the Dynamic Island
//! and the assistant's media tools then reach the services it talks to.
//!
//! * **Reporting is push.** Keep a [`MusicPublisher`], return it from
//!   [`PluginCapability::music_publisher`](crate::PluginCapability::music_publisher),
//!   and call [`MusicPublisher::publish`] whenever what you report changes. The
//!   SDK serves the daemon's `MusicSubscribe` stream from it: the latest
//!   snapshot at once, on every publish, and every
//!   [`MUSIC_SNAPSHOT_HEARTBEAT_SECS`](crate::limits::MUSIC_SNAPSHOT_HEARTBEAT_SECS).
//!   Every publish is the WHOLE set: a session left out has ended.
//! * **Answering** is four hooks. A refusal you mean is
//!   `Err(MusicRefusal::new(MusicErrorCode::NoActiveDevice, "…").into())` — an
//!   ANSWER the daemon shows to the person. Any other `Err` reports the plugin
//!   as failing.

use std::sync::Arc;
use std::time::Duration;

use crate::limits::{MUSIC_SEARCH_MAX_ITEMS, MUSIC_SNAPSHOT_HEARTBEAT_SECS, MUSIC_SNAPSHOT_MAX_SESSIONS};
use crate::proto;

/// A refusal a music provider means. The wire string is [`Self::as_str`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MusicErrorCode {
    NotSupported,
    NotFound,
    NoActiveDevice,
    Auth,
    PremiumRequired,
    RateLimited,
    Unavailable,
    NotConfigured,
}

impl MusicErrorCode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::NotSupported => "not_supported",
            Self::NotFound => "not_found",
            Self::NoActiveDevice => "no_active_device",
            Self::Auth => "auth",
            Self::PremiumRequired => "premium_required",
            Self::RateLimited => "rate_limited",
            Self::Unavailable => "unavailable",
            Self::NotConfigured => "not_configured",
        }
    }
}

/// Return as `Err(MusicRefusal::new(…).into())` from a music hook to ANSWER
/// with a refusal rather than fail.
#[derive(Debug, Clone)]
pub struct MusicRefusal {
    pub code: MusicErrorCode,
    pub message: String,
    pub retry_after_secs: u32,
}

impl MusicRefusal {
    pub fn new(code: MusicErrorCode, message: impl Into<String>) -> Self {
        Self { code, message: message.into(), retry_after_secs: 0 }
    }

    /// With [`MusicErrorCode::RateLimited`]: how long to wait.
    pub fn with_retry_after(mut self, secs: u32) -> Self {
        self.retry_after_secs = secs;
        self
    }
}

impl std::fmt::Display for MusicRefusal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code.as_str(), self.message)
    }
}

impl std::error::Error for MusicRefusal {}

/// A service the plugin reaches, signed in or not.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct MusicService {
    pub service_id: String,
    /// For the user; a `$key` resolves through the plugin's locales.
    pub name: String,
    /// `"ready"` | `"signed_out"` | `"error"` | `"disabled"`.
    pub status: String,
    pub status_message: String,
    pub can_search: bool,
    pub can_play: bool,
}

impl From<MusicService> for proto::PluginMusicService {
    fn from(s: MusicService) -> Self {
        Self {
            service_id: s.service_id,
            name: s.name,
            status: if s.status.is_empty() { "ready".into() } else { s.status },
            status_message: s.status_message,
            can_search: s.can_search,
            can_play: s.can_play,
        }
    }
}

/// One playback a service reports.
#[derive(Debug, Clone, PartialEq)]
pub struct MusicSession {
    /// `[A-Za-z0-9._-]{1,64}`, stable while the plugin runs.
    pub session_key: String,
    pub service_id: String,
    /// The audio may be coming out of THIS computer.
    pub this_device: bool,
    pub device_name: String,
    /// OS session ids of an app that plays nothing but this service.
    pub exclusive_app_hints: Vec<String>,
    /// Hosts of many things (browsers): the song must agree too.
    pub shared_app_hints: Vec<String>,
    /// `"playing"` | `"paused"` | `"stopped"` | `"buffering"`.
    pub status: String,
    pub title: String,
    pub artist: String,
    pub album: String,
    /// https only.
    pub artwork_url: String,
    pub position_seconds: f64,
    pub duration_seconds: f64,
    pub track_ref: String,
    pub track_url: String,
    pub liked: bool,
    pub shuffle: bool,
    /// `"off"` | `"track"` | `"context"`.
    pub repeat: String,
    /// `-1` when unknown.
    pub volume_percent: i32,
    /// See [`crate::music`] for the vocabulary.
    pub controls: Vec<String>,
}

impl Default for MusicSession {
    fn default() -> Self {
        Self {
            session_key: String::new(),
            service_id: String::new(),
            this_device: false,
            device_name: String::new(),
            exclusive_app_hints: Vec::new(),
            shared_app_hints: Vec::new(),
            status: "stopped".into(),
            title: String::new(),
            artist: String::new(),
            album: String::new(),
            artwork_url: String::new(),
            position_seconds: 0.0,
            duration_seconds: 0.0,
            track_ref: String::new(),
            track_url: String::new(),
            liked: false,
            shuffle: false,
            repeat: "off".into(),
            volume_percent: -1,
            controls: Vec::new(),
        }
    }
}

impl From<MusicSession> for proto::PluginMusicSession {
    fn from(s: MusicSession) -> Self {
        Self {
            session_key: s.session_key,
            service_id: s.service_id,
            this_device: s.this_device,
            device_name: s.device_name,
            exclusive_app_hints: s.exclusive_app_hints,
            shared_app_hints: s.shared_app_hints,
            status: s.status,
            title: s.title,
            artist: s.artist,
            album: s.album,
            artwork_url: s.artwork_url,
            position_seconds: s.position_seconds,
            duration_seconds: s.duration_seconds,
            track_ref: s.track_ref,
            track_url: s.track_url,
            liked: s.liked,
            shuffle: s.shuffle,
            repeat: s.repeat,
            volume_percent: s.volume_percent,
            controls: s.controls,
        }
    }
}

/// Something in a catalogue or a queue.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct MusicItem {
    /// Your own reference; it comes back in `music_play`.
    pub item_ref: String,
    /// `"track"` | `"album"` | `"artist"` | `"playlist"` | `"wave"`.
    pub kind: String,
    pub title: String,
    pub subtitle: String,
    pub album: String,
    pub artwork_url: String,
    pub duration_seconds: f64,
    pub liked: bool,
    pub service_id: String,
}

impl From<MusicItem> for proto::PluginMusicItem {
    fn from(i: MusicItem) -> Self {
        Self {
            item_ref: i.item_ref,
            kind: i.kind,
            title: i.title,
            subtitle: i.subtitle,
            album: i.album,
            artwork_url: i.artwork_url,
            duration_seconds: i.duration_seconds,
            liked: i.liked,
            service_id: i.service_id,
        }
    }
}

/// A session's queue around the playing item.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct MusicQueue {
    pub items: Vec<MusicItem>,
    /// The playing item's index in `items`, `-1` if none.
    pub current_index: i32,
}

/// What `music_play` started, and the session it plays in.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct MusicPlayed {
    pub item: Option<MusicItem>,
    pub session_key: String,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct MusicControlRequest {
    pub session_key: String,
    pub action: String,
    /// `"seek"`: seconds; `"volume"`: `"0"`..`"100"`; `"shuffle"`: `"on"` | `"off"`;
    /// `"repeat"`: `"off"` | `"track"` | `"context"`; empty otherwise.
    pub value: String,
}

impl From<proto::PluginMusicControlRequest> for MusicControlRequest {
    fn from(r: proto::PluginMusicControlRequest) -> Self {
        Self { session_key: r.session_key, action: r.action, value: r.value }
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct MusicQueueRequest {
    pub session_key: String,
    pub limit: u32,
}

impl From<proto::PluginMusicQueueRequest> for MusicQueueRequest {
    fn from(r: proto::PluginMusicQueueRequest) -> Self {
        Self { session_key: r.session_key, limit: if r.limit == 0 { 20 } else { r.limit.min(50) } }
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct MusicSearchRequest {
    pub query: String,
    pub kind: String,
    pub limit: u32,
    pub service_id: String,
    pub language: String,
}

impl From<proto::PluginMusicSearchRequest> for MusicSearchRequest {
    fn from(r: proto::PluginMusicSearchRequest) -> Self {
        let max = MUSIC_SEARCH_MAX_ITEMS as u32;
        Self {
            query: r.query,
            kind: r.kind,
            limit: if r.limit == 0 { 10.min(max) } else { r.limit.min(max) },
            service_id: r.service_id,
            language: r.language,
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct MusicPlayRequest {
    pub item_ref: String,
    pub query: String,
    pub kind: String,
    /// `"now"` | `"next"` | `"end"`.
    pub mode: String,
    pub session_key: String,
    pub service_id: String,
}

impl From<proto::PluginMusicPlayRequest> for MusicPlayRequest {
    fn from(r: proto::PluginMusicPlayRequest) -> Self {
        Self {
            item_ref: r.item_ref,
            query: r.query,
            kind: r.kind,
            mode: if r.mode.is_empty() { "now".into() } else { r.mode },
            session_key: r.session_key,
            service_id: r.service_id,
        }
    }
}

/// What the plugin last reported, served as the `MusicSubscribe` stream.
/// Cheap to clone; every clone publishes to the same subscribers.
#[derive(Clone)]
pub struct MusicPublisher {
    tx: Arc<tokio::sync::watch::Sender<proto::PluginMusicSnapshot>>,
}

impl Default for MusicPublisher {
    fn default() -> Self {
        Self::new()
    }
}

impl MusicPublisher {
    pub fn new() -> Self {
        Self { tx: Arc::new(tokio::sync::watch::channel(proto::PluginMusicSnapshot::default()).0) }
    }

    /// Replace everything reported. A session left out has ended.
    pub fn publish(
        &self,
        services: impl IntoIterator<Item = MusicService>,
        sessions: impl IntoIterator<Item = MusicSession>,
    ) {
        let snapshot = proto::PluginMusicSnapshot {
            services: services.into_iter().map(Into::into).collect(),
            sessions: sessions
                .into_iter()
                .take(MUSIC_SNAPSHOT_MAX_SESSIONS as usize)
                .map(Into::into)
                .collect(),
        };
        self.tx.send_replace(snapshot);
    }

    /// The latest snapshot, as the daemon will receive it.
    pub fn snapshot(&self) -> proto::PluginMusicSnapshot {
        self.tx.borrow().clone()
    }

    /// Whether the latest snapshot reports a session with this key.
    pub fn knows_session(&self, session_key: &str) -> bool {
        self.tx.borrow().sessions.iter().any(|s| s.session_key == session_key)
    }

    /// The latest snapshot now, then on every publish and every heartbeat.
    pub fn stream(
        &self,
    ) -> impl tokio_stream::Stream<Item = proto::PluginMusicSnapshot> + Send + 'static {
        self.stream_every(Duration::from_secs(MUSIC_SNAPSHOT_HEARTBEAT_SECS))
    }

    pub(crate) fn stream_every(
        &self,
        heartbeat: Duration,
    ) -> impl tokio_stream::Stream<Item = proto::PluginMusicSnapshot> + Send + 'static {
        let mut rx = self.tx.subscribe();
        async_stream::stream! {
            // Cloned out before each yield: the watch guard is not `Send`
            // and must not live across the await a yield is.
            let first = rx.borrow_and_update().clone();
            yield first;
            loop {
                match tokio::time::timeout(heartbeat, rx.changed()).await {
                    Ok(Err(_)) => break,
                    Ok(Ok(())) | Err(_) => {
                        let latest = rx.borrow_and_update().clone();
                        yield latest;
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio_stream::StreamExt;

    #[tokio::test]
    async fn the_stream_serves_the_latest_now_on_publish_and_on_the_heartbeat() {
        let publisher = MusicPublisher::new();
        let mut stream = Box::pin(publisher.stream_every(Duration::from_millis(50)));
        assert!(stream.next().await.unwrap().sessions.is_empty());
        publisher.publish(
            [],
            [MusicSession { session_key: "a".into(), service_id: "spotify".into(), ..Default::default() }],
        );
        assert_eq!(stream.next().await.unwrap().sessions[0].session_key, "a");
        let beat = tokio::time::timeout(Duration::from_secs(1), stream.next()).await.unwrap().unwrap();
        assert_eq!(beat.sessions[0].session_key, "a", "the heartbeat re-sends the latest");
    }

    #[test]
    fn a_snapshot_is_cut_to_the_shared_bound() {
        let publisher = MusicPublisher::new();
        publisher.publish(
            [],
            (0..40).map(|i| MusicSession { session_key: format!("k{i}"), ..Default::default() }),
        );
        assert_eq!(publisher.snapshot().sessions.len(), MUSIC_SNAPSHOT_MAX_SESSIONS as usize);
    }
}
