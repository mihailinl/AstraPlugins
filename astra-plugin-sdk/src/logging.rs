// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! `tracing` → `PluginLog`: the plugin's own log lines, in the daemon's log
//! pane.
//!
//! # The gap this closes
//!
//! A plugin author writes `tracing::info!(..)` — the SDK's own docs tell them
//! to, and `RUST_LOG` controls it. That went to the plugin's stderr and no
//! further. The daemon's log pane, which is where a *user* looks when a plugin
//! misbehaves, only ever showed what the plugin explicitly sent with
//! `ctx.host().log_info(..)`. So the diagnostics an author writes and the
//! diagnostics a user can see were two different sets, and the interesting
//! ones — a panic, a failed request, a retry — were almost always in the first.
//!
//! [`layer`] is a `tracing_subscriber` layer that forwards events to the
//! daemon. `run_with` installs it at startup and [`attach`] plugs the host
//! client into it once registration hands one over.
//!
//! # What it does not forward, and why
//!
//! * **Anything below `INFO`** by default (`ASTRA_PLUGIN_LOG_LEVEL` changes
//!   it). The pane is for the user; `DEBUG` is for `RUST_LOG` and stderr.
//! * **The transport stack's own events** — `h2`, `hyper`, `tonic`, `tower`,
//!   `rustls`, `tokio`. Shipping a log line is itself an RPC, and an RPC that
//!   logs produces a log line: without this list one `WARN` from h2 becomes an
//!   unbounded loop. The task-local guard below covers the same hazard from the
//!   other side, for events emitted inside the shipper itself.
//! * **Anything that does not fit in the queue.** The channel is bounded and
//!   the send is non-blocking: a plugin in a hot loop drops log lines rather
//!   than back-pressuring its own handlers onto the daemon.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

use arc_swap::ArcSwapOption;
use tracing::field::{Field, Visit};
use tracing::{Level, Subscriber};
use tracing_subscriber::Layer;
use tracing_subscriber::layer::Context;

use crate::context::Host;

/// How many log lines may be in flight to the daemon before new ones are
/// dropped.
///
/// Bounded on purpose. The alternative — an unbounded queue — turns a plugin
/// that logs faster than the daemon accepts into one that grows until it is
/// killed, and the log line that would have explained it is in the queue.
const QUEUE: usize = 256;

/// Environment override for the lowest level that reaches the daemon.
/// `trace` / `debug` / `info` / `warn` / `error` / `off`.
const LEVEL_ENV: &str = "ASTRA_PLUGIN_LOG_LEVEL";

/// Targets whose events are never shipped, matched as `target == p` or
/// `target` starting with `p` followed by `::`.
const NEVER_SHIP: &[&str] = &[
    "h2", "hyper", "hyper_util", "tonic", "tower", "rustls", "tokio", "runtime", "mio",
];

static SINK: ArcSwapOption<tokio::sync::mpsc::Sender<Line>> = ArcSwapOption::const_empty();
static LAYER_INSTALLED: AtomicBool = AtomicBool::new(false);
static DROPPED: AtomicU64 = AtomicU64::new(0);

tokio::task_local! {
    /// Set for the whole life of the shipper task, so an event emitted while a
    /// log line is being sent is recognised and not shipped in turn.
    static SHIPPING: ();
}

struct Line {
    level: &'static str,
    message: String,
}

/// The layer. Install it once, at subscriber-init time; it does nothing until
/// [`attach`] gives it a host.
pub fn layer<S: Subscriber>() -> HostLogLayer<S> {
    LAYER_INSTALLED.store(true, Ordering::Release);
    HostLogLayer {
        min: min_level(),
        _subscriber: std::marker::PhantomData,
    }
}

/// Start shipping to `host`.
///
/// Called by `run_with` right after registration — the earliest moment a host
/// client exists. Events emitted before this point went to stderr only, which
/// is the honest answer: there was nowhere else for them to go.
pub fn attach(host: Arc<dyn Host>) {
    if !LAYER_INSTALLED.load(Ordering::Acquire) {
        // The plugin installed its own subscriber and ours never ran. Spawning
        // a shipper nothing feeds would be a task that lives forever doing
        // nothing.
        return;
    }
    let (tx, mut rx) = tokio::sync::mpsc::channel::<Line>(QUEUE);
    SINK.store(Some(Arc::new(tx)));

    tokio::spawn(SHIPPING.scope((), async move {
        while let Some(line) = rx.recv().await {
            // A failure here cannot be logged — that is the loop this whole
            // module is arranged to avoid. It is visible on stderr already,
            // because the fmt layer saw the same event.
            let _ = host.log(line.level, &line.message).await;
        }
    }));
}

/// Stop shipping. The queued lines are dropped with the sender.
pub fn detach() {
    SINK.store(None);
}

/// How many log lines were dropped because the queue was full. A non-zero
/// value here is the reason a log pane looks incomplete.
pub fn dropped() -> u64 {
    DROPPED.load(Ordering::Relaxed)
}

fn min_level() -> Option<Level> {
    match std::env::var(LEVEL_ENV) {
        Ok(v) => match v.trim().to_ascii_lowercase().as_str() {
            "trace" => Some(Level::TRACE),
            "debug" => Some(Level::DEBUG),
            "info" => Some(Level::INFO),
            "warn" => Some(Level::WARN),
            "error" => Some(Level::ERROR),
            "off" | "none" => None,
            other => {
                // Not a reason to ship nothing, and not a reason to ship
                // everything: keep the default and say so.
                eprintln!("{LEVEL_ENV}={other:?} is not a level — using `info`");
                Some(Level::INFO)
            }
        },
        Err(_) => Some(Level::INFO),
    }
}

/// The daemon's four level names, which are not `tracing`'s five.
fn wire_level(level: &Level) -> &'static str {
    match *level {
        Level::TRACE | Level::DEBUG => "debug",
        Level::INFO => "info",
        Level::WARN => "warn",
        Level::ERROR => "error",
    }
}

fn shippable(target: &str) -> bool {
    !NEVER_SHIP
        .iter()
        .any(|p| target == *p || target.strip_prefix(p).is_some_and(|r| r.starts_with("::")))
}

/// Forwards `tracing` events to the daemon as `PluginLog`. See the
/// [module docs](self).
pub struct HostLogLayer<S> {
    min: Option<Level>,
    _subscriber: std::marker::PhantomData<fn(S)>,
}

impl<S: Subscriber> Layer<S> for HostLogLayer<S> {
    fn on_event(&self, event: &tracing::Event<'_>, _ctx: Context<'_, S>) {
        let Some(min) = self.min else { return };
        let meta = event.metadata();
        if *meta.level() > min || !shippable(meta.target()) {
            return;
        }
        // Emitted from inside the shipper: shipping it would be the loop.
        if SHIPPING.try_with(|_| ()).is_ok() {
            return;
        }
        let Some(sink) = SINK.load_full() else { return };

        let mut visitor = Message::default();
        event.record(&mut visitor);
        let message = visitor.finish();
        if message.is_empty() {
            return;
        }

        // `try_send`, never `send`: this runs inside whatever handler emitted
        // the event, and a full queue must not make that handler wait on the
        // daemon.
        if sink
            .try_send(Line {
                level: wire_level(meta.level()),
                message,
            })
            .is_err()
        {
            DROPPED.fetch_add(1, Ordering::Relaxed);
        }
    }
}

/// Flattens an event into one line: the `message` field first, then the rest as
/// `key=value`.
#[derive(Default)]
struct Message {
    message: String,
    fields: Vec<String>,
}

impl Message {
    fn finish(mut self) -> String {
        if self.fields.is_empty() {
            return self.message;
        }
        if self.message.is_empty() {
            return self.fields.join(" ");
        }
        self.message.push(' ');
        self.message.push_str(&self.fields.join(" "));
        self.message
    }
}

impl Visit for Message {
    fn record_debug(&mut self, field: &Field, value: &dyn std::fmt::Debug) {
        if field.name() == "message" {
            self.message = format!("{value:?}");
        } else {
            self.fields.push(format!("{}={value:?}", field.name()));
        }
    }

    fn record_str(&mut self, field: &Field, value: &str) {
        if field.name() == "message" {
            self.message = value.to_string();
        } else {
            self.fields.push(format!("{}={value}", field.name()));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_transport_stacks_own_events_are_never_shipped() {
        // Shipping a log line is an RPC; an RPC that logs is a log line. The
        // list is what keeps that from being a loop.
        assert!(!shippable("h2"));
        assert!(!shippable("h2::codec::framed_write"));
        assert!(!shippable("tonic::transport::channel"));
        assert!(shippable("dice_roller"));
        assert!(shippable("astra_plugin_sdk::runner"));
        // A prefix match must not swallow an unrelated crate.
        assert!(shippable("h2o_plugin"));
        assert!(shippable("tokio_flavoured_plugin"));
    }

    #[test]
    fn tracings_five_levels_become_the_daemons_four() {
        assert_eq!(wire_level(&Level::TRACE), "debug");
        assert_eq!(wire_level(&Level::DEBUG), "debug");
        assert_eq!(wire_level(&Level::INFO), "info");
        assert_eq!(wire_level(&Level::WARN), "warn");
        assert_eq!(wire_level(&Level::ERROR), "error");
    }

    #[test]
    fn fields_ride_along_with_the_message() {
        let m = Message {
            message: "registered".into(),
            fields: vec!["port=42".into()],
        };
        assert_eq!(m.finish(), "registered port=42");

        // An event with fields and no message is still worth a line.
        let m = Message {
            message: String::new(),
            fields: vec!["port=42".into()],
        };
        assert_eq!(m.finish(), "port=42");
    }
}
