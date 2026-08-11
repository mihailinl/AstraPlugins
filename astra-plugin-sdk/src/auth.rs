// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! Authentication for both directions of the plugin↔daemon link.
//!
//! **plugin → daemon.** The daemon authenticates every non-bootstrap RPC by the
//! `x-session-token` metadata header
//! (`astra-daemon/src/server/auth_interceptor.rs`). Exactly one path is exempt —
//! `/astra.PluginHostService/Register` — which is where the plugin trades its
//! spawn-time `--auth-token` for a session token. Everything after that must
//! carry the token or comes back `unauthenticated`. Both [`crate::HostClient`]
//! and [`crate::DaemonClient`] attach it through [`SessionInterceptor`].
//!
//! **daemon → plugin.** The plugin's own `PluginCapabilityService` is guarded by
//! [`CapabilityInterceptor`], which expects the same spawn-time `--auth-token`
//! back in the `x-plugin-token` header. See [`CapabilityAuth`] for why that is
//! staged rather than enforced outright.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use tonic::service::interceptor::InterceptedService;
use tonic::transport::Channel;
use tracing::warn;

/// Metadata header the daemon reads the session token from.
/// Mirrors `astra-daemon/src/server/client_auth.rs::SESSION_TOKEN_HEADER`.
const SESSION_TOKEN_HEADER: &str = "x-session-token";

/// Attaches the plugin's session token to every outgoing request.
#[derive(Clone)]
pub(crate) struct SessionInterceptor {
    token: String,
}

impl SessionInterceptor {
    pub(crate) fn new(token: impl Into<String>) -> Self {
        Self {
            token: token.into(),
        }
    }
}

impl tonic::service::Interceptor for SessionInterceptor {
    fn call(&mut self, mut req: tonic::Request<()>) -> Result<tonic::Request<()>, tonic::Status> {
        // SECURITY: fail closed. A token that will not parse as a header value
        // cannot authenticate anything, so the request is aborted here instead
        // of being sent bare — the daemon would answer `unauthenticated` and the
        // real cause (a malformed token) would be invisible to the plugin.
        let value = self.token.parse().map_err(|_| {
            tonic::Status::unauthenticated("session token is not a valid HTTP header value")
        })?;
        req.metadata_mut().insert(SESSION_TOKEN_HEADER, value);
        Ok(req)
    }
}

/// A channel that carries the session token on every call.
pub(crate) type AuthChannel = InterceptedService<Channel, SessionInterceptor>;

// ── daemon → plugin ───────────────────────────────────────────────────────────

/// Metadata header the plugin reads the daemon's copy of the spawn token from.
///
/// Must stay identical to the header the daemon attaches in
/// `astra-daemon/src/plugins/client.rs`.
pub(crate) const PLUGIN_TOKEN_HEADER: &str = "x-plugin-token";

/// Environment override for [`CapabilityAuth`]: `off`, `warn` or `require`.
///
/// Lets an operator turn enforcement on ahead of the default flip (or off, if a
/// daemon regression makes it unusable) without rebuilding every plugin.
pub(crate) const CAPABILITY_AUTH_ENV: &str = "ASTRA_PLUGIN_CAPABILITY_AUTH";

/// How the plugin's own capability server treats inbound calls.
///
/// SECURITY: the capability server listens on loopback TCP with an OS-assigned
/// port and, historically, no authentication whatsoever. Any process running as
/// the same user — including another installed plugin, which the daemon's threat
/// model explicitly treats as untrusted — can scan loopback for the port and
/// call `OnConfigChanged` (repointing the victim plugin's API base URL at an
/// attacker-controlled host, after which it posts its real credentials there),
/// `CallTool` / `ExecuteAction` / `CallFromUi` (arbitrary execution under the
/// victim plugin's identity), or `Shutdown` (a one-RPC denial of service).
///
/// The material for the fix already exists: the spawn-time `--auth-token` is a
/// secret the daemon minted and only the daemon and this process know. It was
/// simply never checked on the way *in* — only echoed once in the outbound
/// `Register` body.
///
/// Enforcing it unilaterally would break every plugin against a daemon that does
/// not yet send the header, so the rollout is staged:
///
/// | stage | header absent | header wrong |
/// |---|---|---|
/// | [`Warn`](CapabilityAuth::Warn) — today's default | accepted, warned once | rejected |
/// | [`Require`](CapabilityAuth::Require) — the default once the daemon ships it | rejected | rejected |
/// | [`Off`](CapabilityAuth::Off) | accepted | accepted |
///
/// A wrong token is rejected in every stage but `Off`: no legitimate caller ever
/// sends one, so there is no compatibility to preserve there.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum CapabilityAuth {
    /// No check at all. For a plugin driven by something other than the daemon.
    Off,
    /// Reject a wrong token; accept a missing one and warn once. Default while
    /// daemons that predate the header are still in the field.
    #[default]
    Warn,
    /// Reject anything that does not carry the spawn token.
    Require,
}

impl CapabilityAuth {
    /// Parse the `ASTRA_PLUGIN_CAPABILITY_AUTH` spelling. `None` for anything
    /// else, including the empty string.
    fn parse(value: &str) -> Option<Self> {
        match value.trim().to_ascii_lowercase().as_str() {
            "off" | "0" | "false" => Some(Self::Off),
            "warn" => Some(Self::Warn),
            "require" | "1" | "true" => Some(Self::Require),
            _ => None,
        }
    }

    /// `self`, unless the environment names a different stage.
    ///
    /// An unparseable value is a typo, not a request to weaken the check, so it
    /// warns and keeps `self` rather than falling back to `Off`.
    pub(crate) fn resolved(self) -> Self {
        match std::env::var(CAPABILITY_AUTH_ENV) {
            Ok(raw) => match Self::parse(&raw) {
                Some(mode) => mode,
                None => {
                    warn!(
                        "{CAPABILITY_AUTH_ENV}={raw:?} is not one of off|warn|require — \
                         keeping {self:?}"
                    );
                    self
                }
            },
            Err(_) => self,
        }
    }
}

/// Guards `PluginCapabilityService` with the spawn-time `--auth-token`.
///
/// Cloned per connection by tonic, so the "warned already" flag is shared.
#[derive(Clone)]
pub(crate) struct CapabilityInterceptor {
    /// `None` when the plugin was started without `--auth-token` — standalone,
    /// or under `astra-plugin dev --standalone`. There is no shared secret to
    /// check against, so there is nothing to enforce.
    token: Option<Arc<str>>,
    mode: CapabilityAuth,
    warned: Arc<AtomicBool>,
}

impl CapabilityInterceptor {
    pub(crate) fn new(token: &str, mode: CapabilityAuth) -> Self {
        Self {
            token: (!token.is_empty()).then(|| Arc::from(token)),
            mode,
            warned: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Whether this interceptor will actually check anything — used only to
    /// decide what to log at startup.
    pub(crate) fn is_active(&self) -> bool {
        self.token.is_some() && self.mode != CapabilityAuth::Off
    }
}

/// Length-independent-of-content comparison of two secrets.
///
/// Lengths are compared first and leak, which is fine: the token's length is
/// fixed by the daemon, not secret. The bytes are folded so a near-miss costs
/// the same as a first-byte miss.
fn secrets_match(a: &[u8], b: &[u8]) -> bool {
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

impl tonic::service::Interceptor for CapabilityInterceptor {
    fn call(&mut self, req: tonic::Request<()>) -> Result<tonic::Request<()>, tonic::Status> {
        let Some(expected) = self.token.as_deref() else {
            return Ok(req);
        };
        if self.mode == CapabilityAuth::Off {
            return Ok(req);
        }

        match req.metadata().get(PLUGIN_TOKEN_HEADER) {
            Some(value) => {
                // A non-ASCII header cannot be the token the daemon was given,
                // so it is a mismatch, not a decoding problem to report.
                let presented = value.to_str().unwrap_or_default();
                if secrets_match(presented.as_bytes(), expected.as_bytes()) {
                    Ok(req)
                } else {
                    // Deliberately says nothing about which part was wrong.
                    Err(tonic::Status::unauthenticated(
                        "invalid plugin token — this RPC did not come from the daemon that \
                         spawned this plugin",
                    ))
                }
            }
            None if self.mode == CapabilityAuth::Require => Err(tonic::Status::unauthenticated(
                "missing x-plugin-token — this plugin requires the daemon to authenticate \
                 capability calls",
            )),
            None => {
                // Accept-and-warn. Once, not once per RPC: the daemon calls into
                // a plugin constantly and a per-call warning would bury the log.
                if !self.warned.swap(true, Ordering::Relaxed) {
                    warn!(
                        "Capability call arrived without {PLUGIN_TOKEN_HEADER}. This daemon \
                         predates bidirectional plugin auth, so any local process can reach \
                         this plugin's tools, config and shutdown. Accepting it for \
                         compatibility; set {CAPABILITY_AUTH_ENV}=require to refuse instead."
                    );
                }
                Ok(req)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tonic::service::Interceptor;

    fn request(token: Option<&str>) -> tonic::Request<()> {
        let mut req = tonic::Request::new(());
        if let Some(token) = token {
            req.metadata_mut()
                .insert(PLUGIN_TOKEN_HEADER, token.parse().unwrap());
        }
        req
    }

    #[test]
    fn warn_stage_accepts_a_missing_token_and_rejects_a_wrong_one() {
        let mut guard = CapabilityInterceptor::new("s3cret", CapabilityAuth::Warn);
        assert!(guard.call(request(None)).is_ok());
        assert!(guard.call(request(Some("s3cret"))).is_ok());
        assert!(guard.call(request(Some("s3cres"))).is_err());
        assert!(guard.call(request(Some(""))).is_err());
    }

    #[test]
    fn require_stage_rejects_a_missing_token() {
        let mut guard = CapabilityInterceptor::new("s3cret", CapabilityAuth::Require);
        assert!(guard.call(request(None)).is_err());
        assert!(guard.call(request(Some("s3cret"))).is_ok());
    }

    #[test]
    fn off_stage_and_no_token_accept_everything() {
        let mut guard = CapabilityInterceptor::new("s3cret", CapabilityAuth::Off);
        assert!(guard.call(request(None)).is_ok());
        assert!(guard.call(request(Some("wrong"))).is_ok());

        // No `--auth-token` at all: nothing to compare against, so the guard is
        // inert rather than fail-closed — a standalone plugin has no daemon to
        // get a token from and must still be runnable.
        let mut guard = CapabilityInterceptor::new("", CapabilityAuth::Require);
        assert!(!guard.is_active());
        assert!(guard.call(request(None)).is_ok());
    }

    #[test]
    fn env_spellings() {
        assert_eq!(CapabilityAuth::parse("require"), Some(CapabilityAuth::Require));
        assert_eq!(CapabilityAuth::parse(" WARN "), Some(CapabilityAuth::Warn));
        assert_eq!(CapabilityAuth::parse("off"), Some(CapabilityAuth::Off));
        assert_eq!(CapabilityAuth::parse("yes"), None);
        assert_eq!(CapabilityAuth::parse(""), None);
    }

    #[test]
    fn secrets_match_is_exact() {
        assert!(secrets_match(b"abc", b"abc"));
        assert!(!secrets_match(b"abc", b"abd"));
        assert!(!secrets_match(b"abc", b"ab"));
        assert!(secrets_match(b"", b""));
    }
}
