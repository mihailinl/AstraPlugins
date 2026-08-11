//! Panic containment: a handler that panics answers an error, and the process
//! keeps serving.
//!
//! # Why this is not optional
//!
//! A plugin is a *process the daemon supervises*. Before this, a panic in one
//! tool call unwound out of the tonic handler; the connection died, the daemon
//! saw a transport failure with no message in it, and — under
//! `panic = "abort"`, which is a perfectly ordinary release profile — the whole
//! plugin went down and took every other capability with it. One bad `unwrap`
//! on one code path turned a plugin into a crash loop.
//!
//! Two pieces, and they do different jobs:
//!
//! * [`catch`] wraps each handler, so a panic becomes
//!   `ToolError::Internal("… panicked: …")` — data the AI loop can read and the
//!   user can see, on the same channel as every other per-call failure.
//! * [`install_hook`] runs on *every* panic, caught or not, and reports the
//!   payload, the source location and the backtrace at error level — which,
//!   once [`crate::logging`] is attached, means the daemon's log pane and the
//!   plugin's own log file. A caught panic that left no trace is a bug that
//!   never gets fixed.
//!
//! # `panic = "abort"` turns the first half off
//!
//! There is no unwinding to catch, so a panicking handler kills the process no
//! matter what this module does. Do not put
//!
//! ```toml
//! [profile.release]
//! panic = "abort"
//! ```
//!
//! in a plugin's `Cargo.toml`: the binary is a supervised service, and a
//! smaller one that dies on the first bad `unwrap` is not the trade it looks
//! like. [`install_hook`] still runs — the report is the last thing the process
//! does.

use std::any::Any;
use std::future::Future;
use std::panic::AssertUnwindSafe;
use std::pin::Pin;
use std::sync::OnceLock;
use std::task::{Context, Poll};

use crate::error::ToolError;

/// What a panic said, as far as it can be recovered.
#[derive(Debug, Clone)]
pub struct Panicked {
    /// The hook that panicked, e.g. `"call_tool"`.
    pub hook: String,
    /// The panic payload, when it was a `&str` or a `String` — which covers
    /// every `panic!`, `unwrap`, `expect` and failed assertion.
    pub message: String,
    /// `file:line:col`, when the hook was installed early enough to catch it.
    pub location: Option<String>,
}

impl std::fmt::Display for Panicked {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{} panicked: {}", self.hook, self.message)?;
        if let Some(loc) = &self.location {
            write!(f, " (at {loc})")?;
        }
        Ok(())
    }
}

impl From<Panicked> for ToolError {
    fn from(p: Panicked) -> Self {
        // `Internal`, deliberately: a panic is a bug in the plugin and there is
        // nothing the model can do differently. Saying `BadArguments` would send
        // it round the loop again with new arguments and the same crash.
        ToolError::Internal(p.to_string())
    }
}

impl From<Panicked> for tonic::Status {
    fn from(p: Panicked) -> Self {
        // NOT `unimplemented`: the daemon reads that as "this hook is absent"
        // and stops calling it for the life of the process.
        tonic::Status::internal(p.to_string())
    }
}

/// Run `fut` to completion, turning a panic into [`Panicked`].
///
/// The future is never polled again after it panics, which is what makes the
/// `AssertUnwindSafe` honest: the half-updated state inside it is dropped, not
/// resumed.
///
/// The SDK wraps every hook in this. It is public because a plugin's own
/// `tokio::spawn`ed loops are not hooks, and a panic in one of those is
/// invisible until the loop is noticed to have stopped:
///
/// ```no_run
/// # use astra_plugin_sdk::panics::catch;
/// # async fn f() {
/// tokio::spawn(async move {
///     loop {
///         if let Err(panicked) = catch("poll_loop", tick()).await {
///             tracing::error!("{panicked}");   // and carry on
///         }
///     }
/// });
/// # }
/// # async fn tick() {}
/// ```
pub async fn catch<F: Future>(hook: &str, fut: F) -> Result<F::Output, Panicked> {
    match (CatchUnwind { inner: fut }).await {
        Ok(v) => Ok(v),
        Err(payload) => Err(Panicked {
            hook: hook.to_string(),
            message: payload_message(&payload),
            location: last_panic_location(),
        }),
    }
}

/// The payload as a string. `panic!("…")`, `unwrap`, `expect` and every
/// assertion macro produce one of these two types; anything else is reported as
/// what it is rather than as an empty message.
fn payload_message(payload: &Box<dyn Any + Send>) -> String {
    if let Some(s) = payload.downcast_ref::<&'static str>() {
        (*s).to_string()
    } else if let Some(s) = payload.downcast_ref::<String>() {
        s.clone()
    } else {
        "panicked with a non-string payload".to_string()
    }
}

/// A future that survives its inner future panicking.
///
/// This is `futures::FutureExt::catch_unwind`, written out. Pulling in
/// `futures` for one combinator would put a second executor-adjacent crate in
/// every plugin's dependency graph for thirty lines of code.
struct CatchUnwind<F> {
    inner: F,
}

impl<F: Future> Future for CatchUnwind<F> {
    type Output = Result<F::Output, Box<dyn Any + Send>>;

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        // SAFETY: `inner` is never moved out of, and the projection is the only
        // way it is reached. Standard structural pinning.
        let inner = unsafe { self.map_unchecked_mut(|s| &mut s.inner) };
        match std::panic::catch_unwind(AssertUnwindSafe(|| inner.poll(cx))) {
            Ok(Poll::Pending) => Poll::Pending,
            Ok(Poll::Ready(v)) => Poll::Ready(Ok(v)),
            Err(payload) => Poll::Ready(Err(payload)),
        }
    }
}

// ── the hook ─────────────────────────────────────────────────────────────────

thread_local! {
    /// Where the last panic on this thread happened. The payload is available
    /// from `catch_unwind`; the location is not, and it is the half that says
    /// which line to open.
    static LAST_LOCATION: std::cell::RefCell<Option<String>> =
        const { std::cell::RefCell::new(None) };
}

fn last_panic_location() -> Option<String> {
    LAST_LOCATION.with(|l| l.borrow_mut().take())
}

static INSTALLED: OnceLock<()> = OnceLock::new();

/// Report every panic — caught or fatal — at error level, with payload,
/// location and backtrace.
///
/// Chains the previous hook rather than replacing it, so the default's stderr
/// report still happens (the daemon captures a plugin's stderr) and a plugin
/// that installed its own hook keeps it.
///
/// Idempotent: calling it twice installs one hook. `run_with` calls it before
/// anything else can panic.
pub fn install_hook() {
    INSTALLED.get_or_init(|| {
        let previous = std::panic::take_hook();
        std::panic::set_hook(Box::new(move |info| {
            let location = info.location().map(|l| l.to_string());
            LAST_LOCATION.with(|l| *l.borrow_mut() = location.clone());

            // `capture()`, not `force_capture()`: it honours `RUST_BACKTRACE`,
            // which is the switch the user has already been told about, and
            // costs nothing when it is off.
            let backtrace = std::backtrace::Backtrace::capture();
            let message = info
                .payload()
                .downcast_ref::<&str>()
                .map(|s| (*s).to_string())
                .or_else(|| info.payload().downcast_ref::<String>().cloned())
                .unwrap_or_else(|| "panicked with a non-string payload".to_string());

            // Error is the highest level `tracing` has, and — once
            // `logging::attach` has run — this is what reaches the daemon's log
            // pane as a `PluginLog`. The target is named so the log layer can
            // recognise its own reports and never ship a panic twice.
            tracing::error!(
                target: PANIC_TARGET,
                location = location.as_deref().unwrap_or("unknown"),
                backtrace = %backtrace,
                "plugin panicked: {message}",
            );

            previous(info);
        }));
    });
}

/// The tracing target panics are reported under.
pub(crate) const PANIC_TARGET: &str = "astra_plugin_sdk::panic";

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn a_panicking_future_becomes_an_error() {
        install_hook();
        let caught = catch("call_tool", async { panic!("boom") })
            .await
            .expect_err("a panic must not escape");
        assert_eq!(caught.hook, "call_tool");
        assert_eq!(caught.message, "boom");
        assert!(
            caught.location.is_some_and(|l| l.contains("panics.rs")),
            "the location is the half that says which line to open",
        );
    }

    #[tokio::test]
    async fn a_panic_after_an_await_is_caught_too() {
        // The interesting case: the panic happens on a later poll, on whatever
        // thread the runtime resumed the task on.
        install_hook();
        let caught = catch("call_tool", async {
            tokio::task::yield_now().await;
            let none: Option<u32> = None;
            // The bug is the point.
            #[allow(clippy::unnecessary_literal_unwrap)]
            none.expect("no value")
        })
        .await
        .expect_err("a panic after an await must not escape");
        assert!(caught.message.contains("no value"), "{caught}");
    }

    #[tokio::test]
    async fn a_hook_that_does_not_panic_is_untouched() {
        assert_eq!(catch("call_tool", async { 7 }).await.unwrap(), 7);
    }

    #[tokio::test]
    async fn the_error_a_panic_becomes_is_internal_and_names_the_hook() {
        install_hook();
        let e: ToolError = catch("call_tool", async { panic!("boom") })
            .await
            .unwrap_err()
            .into();
        match &e {
            ToolError::Internal(m) => {
                assert!(m.contains("call_tool"), "{m}");
                assert!(m.contains("boom"), "{m}");
            }
            other => panic!("a panic must be Internal, not {other:?}"),
        }
    }
}
