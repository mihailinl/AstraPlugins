//! Errors a handler returns, and how they reach the other side.
//!
//! # Two channels, and they are not interchangeable
//!
//! **In-band** — [`ToolError`]. A tool that failed *did answer*: "you have not
//! configured an API key" is a fact the AI loop has to read and act on, and the
//! user has to be shown as a link to the exact settings field. It travels in the
//! response message (`success = false` plus the error detail), so the daemon
//! logs one tool call with one result and the model gets the text.
//!
//! **Transport** — [`tonic::Status`]. Reserved for the call not happening: the
//! plugin has no such hook ([`HookUnimplemented`]), the caller is not
//! authenticated, the connection died. The daemon's `optional_hook` reads
//! `UNIMPLEMENTED` as *hook absent*, which is a claim about the plugin's shape,
//! not about this call. Returning `Status::internal` for a per-call failure
//! throws away the distinction and, for a tool, loses the model's answer.
//!
//! Handlers therefore return `Result<String, ToolError>`; the SDK does the
//! mapping in `runner.rs`, and no plugin ever builds a `Status` by hand.
//!
//! ```
//! use astra_plugin_sdk::ToolError;
//!
//! #[derive(serde::Deserialize)]
//! struct Args { count: u32 }
//!
//! fn parse(args: &str) -> Result<u32, ToolError> {
//!     // `?` works: serde_json::Error is bad *arguments*, not an internal fault.
//!     let a: Args = serde_json::from_str(args)?;
//!     Ok(a.count)
//! }
//! assert!(matches!(parse("{"), Err(ToolError::BadArguments(_))));
//! ```

use std::time::Duration;

use crate::proto;

/// Why a per-call handler could not answer.
///
/// The variants are the ones a *caller* can do something different about, which
/// is the only reason to have more than one. `BadArguments` says retry with
/// different arguments; `NotConfigured` says stop and send the user to a
/// settings field; `RateLimited` says wait exactly this long; `Internal` says
/// nothing the model can act on, so it is the last resort and not the default.
///
/// `#[non_exhaustive]`: matching must have a `_` arm, so a later variant is not
/// a breaking change for anyone who matches on this.
#[derive(Debug, Clone, PartialEq, Eq)]
#[non_exhaustive]
pub enum ToolError {
    /// The arguments did not parse, or did not make sense. Retryable by the
    /// model with different arguments — this is the one it can actually fix.
    BadArguments(String),

    /// The thing asked for does not exist (unknown tool, unknown id, 404).
    NotFound(String),

    /// A required setting is missing or empty. `field` is the key in the
    /// plugin's config — a deep-link target, so the UI can take the user to the
    /// exact input rather than to "Settings".
    NotConfigured {
        /// Config key, e.g. `"api_key"`. Dotted paths are allowed.
        field: String,
        /// One sentence, for a human. Names what is missing, not where.
        message: String,
    },

    /// Credentials were present and refused (401/403), or the user has not
    /// granted something this call needs.
    Unauthorized(String),

    /// An upstream quota was hit. `retry_after` is what the upstream said, when
    /// it said anything — `None` means "unknown", not "immediately".
    RateLimited {
        /// How long to wait before trying again.
        retry_after: Option<Duration>,
        /// One sentence, for a human.
        message: String,
    },

    /// A dependency is down. Retryable later, unchanged.
    Unavailable(String),

    /// The handler ran out of time.
    Timeout(String),

    /// Anything else. A bug, most of the time — nothing the model can act on.
    Internal(String),

    /// Any of the above, plus a page that documents *this* failure — the
    /// plugin's own docs, or the upstream provider's "how to get an API key".
    /// Built with [`ToolError::with_doc_url`]; the UI renders it as a link
    /// beside the message.
    Documented {
        inner: Box<ToolError>,
        /// `http(s)` only — a consumer drops any other scheme.
        doc_url: String,
    },
}

/// The error an action handler returns. Actions and tools fail for exactly the
/// same reasons, so this is the same type rather than a parallel one that has
/// to be kept in sync.
pub type ActionError = ToolError;

/// The machine-readable half of a [`ToolError`], stable across languages.
///
/// These names are the ones `PluginErrorCode` gains in `astra.proto` (task 5.2's
/// AS half); until they are on the wire, [`ToolError::wire_string`] carries them
/// in the human `error` field, which is what a pre-5.2 daemon and the AI loop
/// both read today.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[non_exhaustive]
pub enum ToolErrorCode {
    BadArguments,
    NotFound,
    NotConfigured,
    Unauthorized,
    RateLimited,
    Unavailable,
    Timeout,
    Internal,
}

impl ToolErrorCode {
    /// The wire spelling — SCREAMING_SNAKE, identical in all three SDKs.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::BadArguments => "BAD_ARGUMENTS",
            Self::NotFound => "NOT_FOUND",
            Self::NotConfigured => "NOT_CONFIGURED",
            Self::Unauthorized => "UNAUTHORIZED",
            Self::RateLimited => "RATE_LIMITED",
            Self::Unavailable => "UNAVAILABLE",
            Self::Timeout => "TIMEOUT",
            Self::Internal => "INTERNAL",
        }
    }

    /// The generated proto enum. One place, so a renamed variant is a compile
    /// error here rather than a silently wrong integer on the wire.
    pub const fn to_proto(self) -> proto::PluginErrorCode {
        use proto::PluginErrorCode as C;
        match self {
            Self::BadArguments => C::PluginErrorBadArguments,
            Self::NotFound => C::PluginErrorNotFound,
            Self::NotConfigured => C::PluginErrorNotConfigured,
            Self::Unauthorized => C::PluginErrorUnauthorized,
            Self::RateLimited => C::PluginErrorRateLimited,
            Self::Unavailable => C::PluginErrorUnavailable,
            Self::Timeout => C::PluginErrorTimeout,
            Self::Internal => C::PluginErrorInternal,
        }
    }
}

impl std::fmt::Display for ToolErrorCode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

impl ToolError {
    /// Missing setting, with a generic sentence. Prefer
    /// [`ToolError::not_configured_with`] when you can say what it is for.
    pub fn not_configured(field: impl Into<String>) -> Self {
        let field = field.into();
        Self::NotConfigured {
            message: format!("required setting `{field}` is not set"),
            field,
        }
    }

    /// Missing setting, with your own sentence.
    pub fn not_configured_with(field: impl Into<String>, message: impl Into<String>) -> Self {
        Self::NotConfigured {
            field: field.into(),
            message: message.into(),
        }
    }

    /// Rate limited, with a known wait.
    pub fn rate_limited(retry_after: Duration, message: impl Into<String>) -> Self {
        Self::RateLimited {
            retry_after: Some(retry_after),
            message: message.into(),
        }
    }

    /// Anything unexpected. Takes any error, including `anyhow::Error`, and
    /// keeps its cause chain in the message (`{:#}`).
    pub fn internal(e: impl std::fmt::Display) -> Self {
        Self::Internal(e.to_string())
    }

    /// Attach a page documenting this failure. `http(s)` only.
    pub fn with_doc_url(self, url: impl Into<String>) -> Self {
        match self {
            // Re-attaching replaces rather than nesting, so the accessors stay
            // one level deep no matter how many hands the error passed through.
            Self::Documented { inner, .. } => Self::Documented {
                inner,
                doc_url: url.into(),
            },
            other => Self::Documented {
                inner: Box::new(other),
                doc_url: url.into(),
            },
        }
    }

    /// The underlying failure, with any documentation wrapper stripped.
    fn bare(&self) -> &Self {
        match self {
            Self::Documented { inner, .. } => inner,
            other => other,
        }
    }

    /// The page documenting this failure, if one was attached.
    pub fn doc_url(&self) -> Option<&str> {
        match self {
            Self::Documented { doc_url, .. } => Some(doc_url),
            _ => None,
        }
    }

    /// The stable code for this failure.
    pub fn code(&self) -> ToolErrorCode {
        match self.bare() {
            Self::BadArguments(_) => ToolErrorCode::BadArguments,
            Self::NotFound(_) => ToolErrorCode::NotFound,
            Self::NotConfigured { .. } => ToolErrorCode::NotConfigured,
            Self::Unauthorized(_) => ToolErrorCode::Unauthorized,
            Self::RateLimited { .. } => ToolErrorCode::RateLimited,
            Self::Unavailable(_) => ToolErrorCode::Unavailable,
            Self::Timeout(_) => ToolErrorCode::Timeout,
            // A `Documented { inner: Documented { .. } }` cannot be built —
            // `with_doc_url` flattens — so this arm is only the catch-all
            // `#[non_exhaustive]` demands.
            Self::Internal(_) | Self::Documented { .. } => ToolErrorCode::Internal,
        }
    }

    /// What went wrong. One sentence, for a human and for the model.
    pub fn message(&self) -> &str {
        match self.bare() {
            Self::BadArguments(m)
            | Self::NotFound(m)
            | Self::Unauthorized(m)
            | Self::Unavailable(m)
            | Self::Timeout(m)
            | Self::Internal(m) => m,
            Self::NotConfigured { message, .. } | Self::RateLimited { message, .. } => message,
            Self::Documented { .. } => "",
        }
    }

    /// The config key this failure points at, if any. A deep-link target: the
    /// UI turns it into a link to that exact field on this plugin's settings
    /// page.
    pub fn config_field(&self) -> Option<&str> {
        match self.bare() {
            Self::NotConfigured { field, .. } if !field.is_empty() => Some(field),
            _ => None,
        }
    }

    /// How long the caller should wait before retrying, if the upstream said.
    pub fn retry_after(&self) -> Option<Duration> {
        match self.bare() {
            Self::RateLimited { retry_after, .. } => *retry_after,
            _ => None,
        }
    }

    /// What to DO about it. One sentence, or nothing when there is nothing
    /// useful to say.
    pub fn hint(&self) -> Option<String> {
        match self.bare() {
            Self::NotConfigured { field, .. } if !field.is_empty() => Some(format!(
                "Set `{field}` in this plugin's settings, then try again."
            )),
            Self::RateLimited {
                retry_after: Some(d),
                ..
            } => Some(format!("Retry in {} s.", d.as_secs().max(1))),
            _ => None,
        }
    }

    /// The string that goes in the response's plain `error` field.
    ///
    /// The structured [`to_plugin_error`](Self::to_plugin_error) is the real
    /// answer, but this string stays populated and stays useful, because two
    /// readers only ever see it: a peer built before `error_detail` existed, and
    /// the model — the tool result the AI loop reads back is text. The code is
    /// prefixed on purpose: `NOT_CONFIGURED: …` tells the loop to stop retrying,
    /// which a bare sentence does not.
    pub fn wire_string(&self) -> String {
        let mut s = format!("{}: {}", self.code(), self.message());
        if let Some(hint) = self.hint() {
            s.push_str(" (");
            s.push_str(&hint);
            s.push(')');
        }
        if let Some(url) = self.doc_url() {
            s.push_str(" See ");
            s.push_str(url);
        }
        s
    }

    /// The structured half, as the generated proto type.
    ///
    /// Attached to the response alongside the plain `error` string, never
    /// instead of it. `config_field` is what the UI turns into a link to the
    /// exact settings input; `retry_after_ms` is `0` for "not stated", which is
    /// not the same as "retry immediately".
    pub fn to_plugin_error(&self) -> proto::PluginError {
        proto::PluginError {
            code: self.code().to_proto() as i32,
            message: self.message().to_string(),
            hint: self.hint().unwrap_or_default(),
            config_field: self.config_field().unwrap_or_default().to_string(),
            retry_after_ms: self
                .retry_after()
                .map(|d| d.as_millis().min(u32::MAX as u128) as u32)
                .unwrap_or(0),
            doc_url: self.doc_url().unwrap_or_default().to_string(),
        }
    }
}

impl std::fmt::Display for ToolError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.wire_string())
    }
}

impl std::error::Error for ToolError {}

// ── `?` conversions ──────────────────────────────────────────────────────────
//
// Every one of these is a claim about which of the eight kinds the failure is,
// so they are enumerated rather than blanket-implemented. A blanket
// `impl<E: Error> From<E>` would land everything in `Internal`, which is the
// single least useful answer and the one the model cannot act on.

impl From<serde_json::Error> for ToolError {
    /// Arguments and config arrive as JSON strings, so a parse failure is a
    /// statement about the *arguments*. This is what makes
    /// `serde_json::from_str(args)?` compile — and mean the right thing —
    /// inside `call_tool`.
    fn from(e: serde_json::Error) -> Self {
        Self::BadArguments(e.to_string())
    }
}

impl From<anyhow::Error> for ToolError {
    /// Recover the kind, rather than flatten it.
    ///
    /// `?` on a host call is the line §3.1's sample writes —
    /// `ctx.host().fire_trigger(..).await?` — and every [`Host`](crate::Host)
    /// method returns `anyhow::Result`, so this conversion is on the path of
    /// the *most common* failure an author will ever hit: a host RPC they did
    /// not declare in `[permissions]`, which is default-deny. Flattening that
    /// to `Internal` tells the AI loop the tool suffered an internal fault and
    /// to retry it, when the truth is `Unauthorized` and retrying can never
    /// work.
    ///
    /// Both downcasts see through `.context(..)`: anyhow keeps the original
    /// error in the chain, so a `ToolError` or a `tonic::Status` that was
    /// widened and annotated on the way up still comes back out as itself.
    fn from(e: anyhow::Error) -> Self {
        match e.downcast::<ToolError>() {
            Ok(tool) => tool,
            // A gRPC failure the SDK already knows how to read — see the fixed
            // mapping in `From<tonic::Status>` right below. Reaching `Internal`
            // with a `Status` in hand would be throwing away an answer we have.
            Err(other) => match other.downcast::<tonic::Status>() {
                Ok(status) => status.into(),
                Err(other) => Self::Internal(format!("{other:#}")),
            },
        }
    }
}

impl From<std::io::Error> for ToolError {
    fn from(e: std::io::Error) -> Self {
        use std::io::ErrorKind;
        match e.kind() {
            ErrorKind::NotFound => Self::NotFound(e.to_string()),
            ErrorKind::PermissionDenied => Self::Unauthorized(e.to_string()),
            ErrorKind::TimedOut => Self::Timeout(e.to_string()),
            ErrorKind::ConnectionRefused | ErrorKind::ConnectionReset | ErrorKind::BrokenPipe => {
                Self::Unavailable(e.to_string())
            }
            _ => Self::Internal(e.to_string()),
        }
    }
}

impl From<tonic::Status> for ToolError {
    /// The fixed mapping, used when a plugin calls something that answers in
    /// gRPC and wants to pass the failure on. It is the inverse of
    /// [`ToolError::to_status`], so a round trip does not change the meaning.
    fn from(s: tonic::Status) -> Self {
        use tonic::Code;
        let msg = s.message().to_string();
        match s.code() {
            Code::InvalidArgument | Code::OutOfRange => Self::BadArguments(msg),
            Code::NotFound => Self::NotFound(msg),
            Code::FailedPrecondition => Self::NotConfigured {
                field: String::new(),
                message: msg,
            },
            Code::Unauthenticated | Code::PermissionDenied => Self::Unauthorized(msg),
            Code::ResourceExhausted => Self::RateLimited {
                retry_after: None,
                message: msg,
            },
            Code::Unavailable => Self::Unavailable(msg),
            Code::DeadlineExceeded => Self::Timeout(msg),
            _ => Self::Internal(msg),
        }
    }
}

impl From<std::num::ParseIntError> for ToolError {
    fn from(e: std::num::ParseIntError) -> Self {
        Self::BadArguments(e.to_string())
    }
}

impl From<std::num::ParseFloatError> for ToolError {
    fn from(e: std::num::ParseFloatError) -> Self {
        Self::BadArguments(e.to_string())
    }
}

impl From<std::str::Utf8Error> for ToolError {
    fn from(e: std::str::Utf8Error) -> Self {
        Self::BadArguments(e.to_string())
    }
}

impl From<std::string::FromUtf8Error> for ToolError {
    fn from(e: std::string::FromUtf8Error) -> Self {
        Self::BadArguments(e.to_string())
    }
}

impl ToolError {
    /// The transport spelling, for the hooks whose response message has no
    /// in-band error field (TTS, STT, AI). Fixed both ways — see the `From`
    /// impl above.
    pub fn to_status(&self) -> tonic::Status {
        use tonic::Code;
        let code = match self.code() {
            ToolErrorCode::BadArguments => Code::InvalidArgument,
            ToolErrorCode::NotFound => Code::NotFound,
            ToolErrorCode::NotConfigured => Code::FailedPrecondition,
            ToolErrorCode::Unauthorized => Code::PermissionDenied,
            ToolErrorCode::RateLimited => Code::ResourceExhausted,
            ToolErrorCode::Unavailable => Code::Unavailable,
            ToolErrorCode::Timeout => Code::DeadlineExceeded,
            ToolErrorCode::Internal => Code::Internal,
        };
        tonic::Status::new(code, self.wire_string())
    }
}

// ── hook absence ─────────────────────────────────────────────────────────────

/// "This plugin does not have that hook."
///
/// Every defaulted hook that has no sensible fallback returns this, and
/// `runner.rs` turns it into `Status::unimplemented` — the protocol's word for
/// *absent*, which the daemon's `optional_hook` reads as such
/// (`astra-daemon/src/plugins/manager.rs`). It is deliberately distinct from
/// [`ToolError::Internal`]: "I have no TTS" and "my TTS crashed" have different
/// consequences, and answering the second when you mean the first makes the
/// daemon mark a working plugin dead.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HookUnimplemented {
    /// The hook's name, as spelled on the trait.
    pub hook: &'static str,
}

impl std::fmt::Display for HookUnimplemented {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "this plugin does not implement `{}`", self.hook)
    }
}

impl std::error::Error for HookUnimplemented {}

/// Build the [`HookUnimplemented`] error a defaulted hook returns.
pub fn unimplemented(hook: &'static str) -> anyhow::Error {
    anyhow::Error::new(HookUnimplemented { hook })
}

/// Map a hook's `anyhow::Error` to the status the daemon should see:
/// `UNIMPLEMENTED` when the hook is absent, `INTERNAL` when it ran and failed.
pub(crate) fn hook_status(e: anyhow::Error) -> tonic::Status {
    if let Some(u) = e.downcast_ref::<HookUnimplemented>() {
        tonic::Status::unimplemented(u.to_string())
    } else if let Some(t) = e.downcast_ref::<ToolError>() {
        t.to_status()
    } else {
        tonic::Status::internal(format!("{e:#}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(serde::Deserialize)]
    struct Args {
        #[allow(dead_code)]
        count: u32,
    }

    /// `ctx.host().fire_trigger(..).await?` — §3.1's own line — must not turn a
    /// permission denial into `Internal`.
    ///
    /// This is the failure every author meets first, because `[permissions]` is
    /// default-deny: the first host RPC you call and did not declare comes back
    /// `PERMISSION_DENIED`. Flattened to `Internal`, the AI loop is told the
    /// tool suffered an internal fault and retries a call that can never
    /// succeed — and the user is shown tonic's `Display`, `details: []` and
    /// `MetadataMap { headers: {} }` included.
    ///
    /// The error built here is exactly what `HostClient::fire_trigger` produces
    /// (`host_client::rpc_failed`), context wrapper and all.
    #[test]
    fn a_denied_host_call_arrives_as_unauthorized_not_internal() {
        let denied =
            tonic::Status::permission_denied("plugin 'dice-roller' has no `fire_trigger` grant");
        let widened: anyhow::Error =
            anyhow::Error::new(ToolError::from(denied)).context("FireTrigger failed");

        let recovered = ToolError::from(widened);
        assert_eq!(recovered.code(), ToolErrorCode::Unauthorized);
        assert!(
            recovered
                .to_string()
                .contains("has no `fire_trigger` grant"),
            "{recovered}"
        );
        for tonic_noise in ["MetadataMap", "details: []", "status: PermissionDenied"] {
            assert!(
                !recovered.to_string().contains(tonic_noise),
                "tonic's Debug-ish Display reached the model's context window: {recovered}"
            );
        }
    }

    /// The same recovery for a bare `tonic::Status` that was widened into
    /// `anyhow` by someone else's code and annotated on the way up.
    ///
    /// Both downcasts have to see *through* `.context(..)`; anyhow keeps the
    /// original error in the chain, and this is the test that says so out loud.
    #[test]
    fn a_status_widened_into_anyhow_keeps_its_code() {
        let cases = [
            (
                tonic::Status::resource_exhausted("slow down"),
                ToolErrorCode::RateLimited,
            ),
            (
                tonic::Status::not_found("no such row"),
                ToolErrorCode::NotFound,
            ),
            (
                tonic::Status::unavailable("daemon restarting"),
                ToolErrorCode::Unavailable,
            ),
            (
                tonic::Status::invalid_argument("sides must be >= 2"),
                ToolErrorCode::BadArguments,
            ),
        ];
        for (status, expected) in cases {
            let widened: anyhow::Error = anyhow::Error::new(status).context("SomeRpc failed");
            assert_eq!(ToolError::from(widened).code(), expected);
        }

        // And something that is neither is still `Internal` — the chain is a
        // recovery, not a reclassification of every failure in the world.
        let plain = anyhow::anyhow!("the disk is on fire");
        assert_eq!(ToolError::from(plain).code(), ToolErrorCode::Internal);
    }

    /// 5.2's acceptance sentence, compiled.
    #[test]
    fn question_mark_on_serde_json_means_bad_arguments() {
        fn call_tool(args: &str) -> Result<String, ToolError> {
            let a: Args = serde_json::from_str(args)?;
            Ok(a.count.to_string())
        }
        assert_eq!(call_tool("{\"count\":3}").unwrap(), "3");
        let err = call_tool("not json").unwrap_err();
        assert_eq!(err.code(), ToolErrorCode::BadArguments);
    }

    /// The other acceptance sentence: a missing API key has to arrive as a
    /// pointer at one field, not as prose.
    #[test]
    fn not_configured_names_the_field_and_says_what_to_do() {
        let e = ToolError::not_configured_with("api_key", "OpenAI API key is not set");
        assert_eq!(e.config_field(), Some("api_key"));
        assert_eq!(
            e.wire_string(),
            "NOT_CONFIGURED: OpenAI API key is not set \
             (Set `api_key` in this plugin's settings, then try again.)"
        );
        assert_eq!(e.to_plugin_error().hint, e.hint().unwrap());
    }

    #[test]
    fn rate_limited_carries_the_wait() {
        let e = ToolError::rate_limited(Duration::from_secs(30), "upstream quota");
        assert_eq!(e.retry_after(), Some(Duration::from_secs(30)));
        assert!(e.wire_string().contains("Retry in 30 s."));
    }

    /// The status mapping is a bijection on the eight codes; a plugin that
    /// forwards a gRPC failure must not have it change kind on the way.
    #[test]
    fn status_round_trips_through_every_code() {
        for e in [
            ToolError::BadArguments("a".into()),
            ToolError::NotFound("a".into()),
            ToolError::not_configured("f"),
            ToolError::Unauthorized("a".into()),
            ToolError::RateLimited {
                retry_after: None,
                message: "a".into(),
            },
            ToolError::Unavailable("a".into()),
            ToolError::Timeout("a".into()),
            ToolError::Internal("a".into()),
        ] {
            let back = ToolError::from(e.to_status());
            assert_eq!(back.code(), e.code(), "{e}");
        }
    }

    /// A `ToolError` widened into `anyhow` by an intermediate helper has to
    /// survive the trip; flattening it into `Internal` is how a NOT_CONFIGURED
    /// turns into "something went wrong".
    #[test]
    fn anyhow_round_trip_preserves_the_code() {
        let e: anyhow::Error = ToolError::not_configured("token").into();
        assert_eq!(ToolError::from(e).code(), ToolErrorCode::NotConfigured);

        let plain = anyhow::anyhow!("disk on fire");
        assert_eq!(ToolError::from(plain).code(), ToolErrorCode::Internal);
    }

    #[test]
    fn an_absent_hook_is_unimplemented_and_a_broken_one_is_not() {
        assert_eq!(
            hook_status(unimplemented("stt_load")).code(),
            tonic::Code::Unimplemented
        );
        assert_eq!(
            hook_status(anyhow::anyhow!("model file corrupt")).code(),
            tonic::Code::Internal
        );
    }
}
