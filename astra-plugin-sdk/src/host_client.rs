//! HostClient — plugin-side gRPC client for calling the Astra daemon.
//!
//! Registration is a two-step handshake and the types enforce it:
//!
//! ```text
//! HostClient::connect_bootstrap()  ->  BootstrapHostClient   (Register only)
//!         .register(..)            ->  HostClient            (session token attached)
//! ```
//!
//! [`BootstrapHostClient`] exposes nothing but `register`, and `register`
//! consumes it — so an un-upgraded, tokenless client can never reach
//! `fire_trigger` / `log` / `get_config` / `set_variable` / `push_to_ui`.
//! Every one of those is `unauthenticated` without the token
//! (`astra-daemon/src/server/auth_interceptor.rs`).

use std::time::Duration;

use anyhow::{Context, Result};
use tonic::transport::Channel;

use crate::auth::{AuthChannel, SessionInterceptor};
use crate::proto;
use crate::proto::plugin_host_service_client::PluginHostServiceClient;

/// Pre-registration client. Can call exactly one RPC: `Register`, the daemon's
/// only auth-exempt path. `register` consumes it and hands back an
/// authenticated [`HostClient`].
pub struct BootstrapHostClient {
    channel: Channel,
    plugin_id: String,
}

impl BootstrapHostClient {
    /// Register this plugin with the daemon and upgrade to an authenticated
    /// client.
    ///
    /// Returns the authenticated [`HostClient`] together with the raw response
    /// (config, language, `client_session_token` for `DaemonClient`).
    pub(crate) async fn register(
        self,
        port: u16,
        capabilities: Vec<String>,
        auth_token: String,
    ) -> Result<(HostClient, proto::PluginRegisterResponse)> {
        let mut bootstrap = PluginHostServiceClient::new(self.channel.clone());

        let resp = bootstrap
            .register(proto::PluginRegisterRequest {
                plugin_id: self.plugin_id.clone(),
                port: port as u32,
                capabilities,
                auth_token,
                // Reported only by the vox sidecar, which is not built on this
                // SDK; "" is "not reported" and the daemon ignores it.
                gpu_tier: String::new(),
                protocol_version: crate::protocol::PROTOCOL_VERSION,
                sdk_name: crate::protocol::SDK_NAME.to_string(),
                sdk_version: crate::protocol::SDK_VERSION.to_string(),
            })
            .await
            .context("Register RPC failed")?
            .into_inner();

        // The protocol verdict comes BEFORE the generic refusal below: "your
        // plugin is too old for this Astra" is a different problem from "the
        // daemon said no", it has a different fix, and it gets its own exit code
        // (`EXIT_PROTOCOL_INCOMPATIBLE`) rather than being flattened into a
        // sentence the author has to interpret.
        crate::protocol::evaluate(&resp)?;

        if !resp.success {
            anyhow::bail!("Registration rejected by daemon: {}", resp.error);
        }

        // SECURITY: fail closed. The daemon issues a session token to EVERY
        // plugin (host_service.rs, SECURITY(B1)) because every host RPC except
        // Register is gated on it. No token means no host call would ever
        // succeed, so stop here with a legible error instead of registering and
        // then failing `unauthenticated` on the first log line.
        if resp.client_session_token.is_empty() {
            anyhow::bail!(
                "Daemon issued no session token at registration — every host RPC would be \
                 rejected as unauthenticated. The daemon is too old for this SDK."
            );
        }

        let client = PluginHostServiceClient::with_interceptor(
            self.channel,
            SessionInterceptor::new(resp.client_session_token.clone()),
        );

        Ok((
            HostClient {
                client,
                plugin_id: self.plugin_id,
            },
            resp,
        ))
    }
}

/// Authenticated client for calling daemon services from a plugin.
///
/// Only obtainable from [`BootstrapHostClient::register`], so holding one is
/// proof that registration succeeded and the session token is attached.
#[derive(Clone)]
pub struct HostClient {
    client: PluginHostServiceClient<AuthChannel>,
    plugin_id: String,
}

impl HostClient {
    /// Open the pre-registration channel to the daemon.
    pub(crate) async fn connect_bootstrap(
        daemon_addr: &str,
        plugin_id: String,
    ) -> Result<BootstrapHostClient> {
        let channel = Channel::from_shared(format!("http://{daemon_addr}"))?
            .connect_timeout(Duration::from_secs(5))
            .connect()
            .await
            .context("Failed to connect to daemon")?;

        Ok(BootstrapHostClient { channel, plugin_id })
    }

    /// Fire a trigger (for trigger plugins).
    pub async fn fire_trigger(&mut self, trigger_type: &str, payload_json: &str) -> Result<()> {
        self.client
            .fire_trigger(proto::PluginFireTriggerRequest {
                trigger_type: trigger_type.into(),
                payload_json: payload_json.into(),
            })
            .await
            .context("FireTrigger RPC failed")?;
        Ok(())
    }

    /// Log a message to the daemon's log buffer.
    pub async fn log(&mut self, level: &str, message: &str) -> Result<()> {
        self.client
            .plugin_log(proto::PluginLogRequest {
                plugin_id: self.plugin_id.clone(),
                level: level.into(),
                message: message.into(),
            })
            .await
            .context("PluginLog RPC failed")?;
        Ok(())
    }

    /// Get this plugin's current config from the daemon.
    pub async fn get_config(&mut self) -> Result<String> {
        let resp = self
            .client
            .get_plugin_self_config(proto::PluginSelfIdRequest {
                plugin_id: self.plugin_id.clone(),
            })
            .await
            .context("GetPluginSelfConfig RPC failed")?;
        Ok(resp.into_inner().config_json)
    }

    /// Get daemon info (version, state, port).
    pub async fn get_daemon_info(&mut self) -> Result<proto::PluginDaemonInfoResponse> {
        let resp = self
            .client
            .get_daemon_info(proto::Empty {})
            .await
            .context("GetDaemonInfo RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Subscribe to daemon events.
    /// `exclude_source_id` — if non-empty, ChatMessageSync events from this source are filtered out server-side.
    pub async fn subscribe_events(
        &mut self,
        event_types: Vec<String>,
        exclude_source_id: String,
    ) -> Result<tonic::Streaming<proto::PluginEventMsg>> {
        let resp = self
            .client
            .subscribe_events(proto::PluginEventFilter {
                plugin_id: self.plugin_id.clone(),
                event_types,
                exclude_source_id,
            })
            .await
            .context("SubscribeEvents RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Set a variable in the daemon's variable context.
    pub async fn set_variable(&mut self, name: &str, value: &str, scope: &str) -> Result<()> {
        self.client
            .set_variable(proto::PluginSetVariableRequest {
                plugin_id: self.plugin_id.clone(),
                name: name.into(),
                value: value.into(),
                scope: scope.into(),
            })
            .await
            .context("SetVariable RPC failed")?;
        Ok(())
    }

    /// Get the plugin ID.
    pub fn plugin_id(&self) -> &str {
        &self.plugin_id
    }

    // ── Logging convenience ──

    /// Log an info message to the daemon.
    pub async fn log_info(&mut self, msg: &str) -> Result<()> {
        self.log("info", msg).await
    }

    /// Log a warning message to the daemon.
    pub async fn log_warn(&mut self, msg: &str) -> Result<()> {
        self.log("warn", msg).await
    }

    /// Log an error message to the daemon.
    pub async fn log_error(&mut self, msg: &str) -> Result<()> {
        self.log("error", msg).await
    }

    /// Push a message to this plugin's UI iframes.
    pub async fn push_to_ui(&mut self, event: &str, payload_json: &str) -> Result<()> {
        self.client
            .push_to_ui(proto::PluginUiPushRequest {
                plugin_id: self.plugin_id.clone(),
                event: event.to_string(),
                payload_json: payload_json.to_string(),
            })
            .await?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use crate::proto;
    use crate::proto::plugin_host_service_server::{
        PluginHostService, PluginHostServiceServer,
    };

    const TOKEN: &str = "test-session-token";

    /// A stand-in for the daemon that enforces the same rule
    /// `astra-daemon/src/server/auth_interceptor.rs` does: `Register` is exempt,
    /// every other host RPC needs `x-session-token`.
    #[derive(Default)]
    struct FakeDaemon {
        /// Token seen on the last non-Register call, for assertions.
        seen: Arc<Mutex<Option<String>>>,
        /// The protocol generation this fake daemon claims to speak, and the
        /// oldest it accepts. `(0, 0)` in `Default` stands for a daemon from
        /// before the handshake existed; `with_protocol` states them.
        protocol: (u32, u32),
        /// The Register request as it arrived, so a test can assert what the
        /// SDK actually put on the wire.
        registered: Arc<Mutex<Option<proto::PluginRegisterRequest>>>,
    }

    impl FakeDaemon {
        fn with_protocol(speaks: u32, floor: u32) -> Self {
            Self {
                protocol: (speaks, floor),
                ..Default::default()
            }
        }

        /// Bind on an OS-assigned loopback port and serve until the returned
        /// handle is aborted.
        async fn serve(self) -> (String, tokio::task::JoinHandle<()>, Arc<Mutex<Option<proto::PluginRegisterRequest>>>) {
            let registered = self.registered.clone();
            let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            let addr = listener.local_addr().unwrap().to_string();
            let handle = tokio::spawn(async move {
                let _ = tonic::transport::Server::builder()
                    .add_service(PluginHostServiceServer::new(self))
                    .serve_with_incoming(tokio_stream::wrappers::TcpListenerStream::new(listener))
                    .await;
            });
            (addr, handle, registered)
        }
    }

    // `tonic::Status` is a large Err variant — same as every RPC method here.
    #[allow(clippy::result_large_err)]
    fn require_token<T>(req: &tonic::Request<T>, seen: &Mutex<Option<String>>) -> Result<(), tonic::Status> {
        let token = req
            .metadata()
            .get("x-session-token")
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_string());
        *seen.lock().unwrap() = token.clone();
        match token {
            Some(t) if t == TOKEN => Ok(()),
            _ => Err(tonic::Status::unauthenticated("Missing session token")),
        }
    }

    #[tonic::async_trait]
    impl PluginHostService for FakeDaemon {
        async fn register(
            &self,
            req: tonic::Request<proto::PluginRegisterRequest>,
        ) -> Result<tonic::Response<proto::PluginRegisterResponse>, tonic::Status> {
            let req = req.into_inner();
            let declared = req.protocol_version;
            *self.registered.lock().unwrap() = Some(req);

            let (speaks, floor) = self.protocol;
            // The daemon's own rule (`host_service::check_protocol`), mirrored
            // here so the SDK is exercised against the answer a real daemon
            // gives — refusal included — and not against a hand-written one.
            if declared < floor {
                return Ok(tonic::Response::new(proto::PluginRegisterResponse {
                    success: false,
                    error: format!("Plugin speaks protocol {declared}; this daemon accepts {floor} or newer."),
                    daemon_version: "test".into(),
                    protocol_version: speaks,
                    min_supported_protocol: floor,
                    error_detail: Some(proto::PluginError {
                        code: proto::PluginErrorCode::PluginErrorProtocolTooOld as i32,
                        message: format!(
                            "Plugin speaks protocol {declared}; this daemon speaks {speaks} and \
                             accepts {floor} or newer."
                        ),
                        hint: format!(
                            "Rebuild the plugin against an Astra plugin SDK whose \
                             PROTOCOL_VERSION is at least {floor}, then reinstall it."
                        ),
                    }),
                    ..Default::default()
                }));
            }

            Ok(tonic::Response::new(proto::PluginRegisterResponse {
                success: true,
                error: String::new(),
                config_json: "{}".into(),
                daemon_version: "test".into(),
                client_session_token: TOKEN.into(),
                language: "en".into(),
                protocol_version: speaks,
                min_supported_protocol: floor,
                error_detail: None,
            }))
        }

        async fn plugin_log(
            &self,
            req: tonic::Request<proto::PluginLogRequest>,
        ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(proto::Empty {}))
        }

        async fn fire_trigger(
            &self,
            req: tonic::Request<proto::PluginFireTriggerRequest>,
        ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(proto::Empty {}))
        }

        async fn get_plugin_self_config(
            &self,
            req: tonic::Request<proto::PluginSelfIdRequest>,
        ) -> Result<tonic::Response<proto::PluginSelfConfigResponse>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(proto::PluginSelfConfigResponse {
                config_json: "{}".into(),
            }))
        }

        async fn get_daemon_info(
            &self,
            req: tonic::Request<proto::Empty>,
        ) -> Result<tonic::Response<proto::PluginDaemonInfoResponse>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(proto::PluginDaemonInfoResponse::default()))
        }

        async fn set_variable(
            &self,
            req: tonic::Request<proto::PluginSetVariableRequest>,
        ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(proto::Empty {}))
        }

        async fn set_theme_contribution(
            &self,
            req: tonic::Request<proto::PluginThemeContribution>,
        ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(proto::Empty {}))
        }

        async fn push_to_ui(
            &self,
            req: tonic::Request<proto::PluginUiPushRequest>,
        ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(proto::Empty {}))
        }

        type SubscribeEventsStream = std::pin::Pin<
            Box<dyn tokio_stream::Stream<Item = Result<proto::PluginEventMsg, tonic::Status>> + Send>,
        >;

        async fn subscribe_events(
            &self,
            req: tonic::Request<proto::PluginEventFilter>,
        ) -> Result<tonic::Response<Self::SubscribeEventsStream>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(Box::pin(tokio_stream::empty())))
        }

        type SendChatMessageStream = std::pin::Pin<
            Box<dyn tokio_stream::Stream<Item = Result<proto::PluginChatChunk, tonic::Status>> + Send>,
        >;

        async fn send_chat_message(
            &self,
            req: tonic::Request<proto::PluginChatRequest>,
        ) -> Result<tonic::Response<Self::SendChatMessageStream>, tonic::Status> {
            require_token(&req, &self.seen)?;
            Ok(tonic::Response::new(Box::pin(tokio_stream::empty())))
        }
    }

    /// The whole point of task 0.1: after `register`, host RPCs must carry the
    /// session token. Before the interceptor existed they came back
    /// `unauthenticated`.
    #[tokio::test]
    async fn host_rpcs_after_register_carry_the_session_token() {
        let seen = Arc::new(Mutex::new(None));
        let server = FakeDaemon {
            seen: seen.clone(),
            protocol: (
                crate::protocol::PROTOCOL_VERSION,
                crate::protocol::MIN_SUPPORTED_DAEMON_PROTOCOL,
            ),
            ..Default::default()
        };
        let (addr, handle, _) = server.serve().await;

        let bootstrap = super::HostClient::connect_bootstrap(&addr, "test".into())
            .await
            .expect("bootstrap connect");
        let (mut host, resp) = bootstrap
            .register(1234, vec!["tools".into()], "spawn-token".into())
            .await
            .expect("register");
        assert_eq!(resp.client_session_token, TOKEN);

        host.log("info", "hello").await.expect("PluginLog must be authenticated");
        assert_eq!(seen.lock().unwrap().as_deref(), Some(TOKEN));

        host.set_variable("k", "v", "session").await.expect("SetVariable");
        host.push_to_ui("ev", "{}").await.expect("PushToUi");
        host.get_config().await.expect("GetPluginSelfConfig");

        handle.abort();
    }

    /// 1.3: the handshake has to be on the wire, not just in a constant. A
    /// daemon that never receives `protocol_version` cannot tell an old plugin
    /// from a new one, and its floor stops meaning anything.
    #[tokio::test]
    async fn register_declares_the_protocol_and_the_sdk() {
        let (addr, handle, registered) = FakeDaemon::with_protocol(
            crate::protocol::PROTOCOL_VERSION,
            crate::protocol::MIN_SUPPORTED_DAEMON_PROTOCOL,
        )
        .serve()
        .await;

        let bootstrap = super::HostClient::connect_bootstrap(&addr, "test".into())
            .await
            .expect("bootstrap connect");
        bootstrap
            .register(1234, vec!["tools".into()], "spawn-token".into())
            .await
            .expect("register");

        let req = registered.lock().unwrap().clone().expect("Register arrived");
        assert_eq!(req.protocol_version, crate::protocol::PROTOCOL_VERSION);
        assert_eq!(req.sdk_name, crate::protocol::SDK_NAME);
        assert_eq!(req.sdk_version, crate::protocol::SDK_VERSION);

        handle.abort();
    }

    /// THE acceptance case for 1.3, end to end over a real socket: this SDK is
    /// built at protocol 1; the daemon's floor is 2. The plugin gets one
    /// sentence — naming the number to reach and what to do — instead of
    /// registering and then dying at the first RPC one side does not have.
    ///
    /// `run_with` turns this error into `exit(EXIT_PROTOCOL_INCOMPATIBLE)`; the
    /// exit itself is not testable in-process, so the test asserts the error
    /// that reaches that branch and the code the branch uses.
    #[tokio::test]
    async fn a_daemon_whose_floor_is_two_refuses_this_sdk_with_one_sentence() {
        assert_eq!(
            crate::protocol::PROTOCOL_VERSION,
            1,
            "this test is written for an SDK at protocol 1"
        );
        let (addr, handle, _) = FakeDaemon::with_protocol(2, 2).serve().await;

        let bootstrap = super::HostClient::connect_bootstrap(&addr, "dice-roller".into())
            .await
            .expect("bootstrap connect");
        // `match`, not `expect_err`: the Ok half is `(HostClient, …)`, which is
        // not `Debug` — deliberately, it holds a session token.
        let err = match bootstrap
            .register(1234, vec!["tools".into()], "spawn-token".into())
            .await
        {
            Ok(_) => panic!("a daemon at floor 2 must refuse an SDK at 1"),
            Err(e) => e,
        };

        let mismatch = err
            .downcast_ref::<crate::protocol::ProtocolMismatch>()
            .expect("the refusal must arrive as a ProtocolMismatch, not a generic error")
            .to_string();
        assert!(mismatch.contains('2'), "{mismatch}");
        assert!(mismatch.contains("PROTOCOL_VERSION"), "{mismatch}");
        assert_eq!(crate::protocol::EXIT_PROTOCOL_INCOMPATIBLE, 78);

        handle.abort();
    }

    /// The other direction: a daemon too old to report a protocol at all — i.e.
    /// Astra v0.1.0, the released build. It is SERVED, end to end.
    ///
    /// `FakeDaemon::default()` is that daemon exactly: `(0, 0)` for the two
    /// handshake fields, and a session token issued anyway — which is what
    /// v0.1.0's `host_service.rs` does, unconditionally, under `SECURITY(B1)`.
    /// Protocol 1 IS the pre-handshake plugin surface, so there is nothing this
    /// SDK calls that such a daemon lacks; refusing it on the strength of a
    /// missing integer would have killed every plugin built with this SDK on the
    /// only Astra anyone has installed.
    ///
    /// The host RPC at the end is the point: the check that matters is whether
    /// the session token works, not what version number came back.
    #[tokio::test]
    async fn a_daemon_that_reports_no_protocol_is_served_end_to_end() {
        let seen = Arc::new(Mutex::new(None));
        let server = FakeDaemon {
            seen: seen.clone(),
            ..Default::default()
        };
        assert_eq!(server.protocol, (0, 0), "the pre-handshake daemon");
        let (addr, handle, _) = server.serve().await;

        let bootstrap = super::HostClient::connect_bootstrap(&addr, "test".into())
            .await
            .expect("bootstrap connect");
        let (mut host, resp) = bootstrap
            .register(1234, vec!["tools".into()], "spawn-token".into())
            .await
            .expect("a pre-handshake daemon must be served, not refused");
        assert_eq!(resp.protocol_version, 0, "it reported no protocol");
        assert_eq!(resp.client_session_token, TOKEN);

        host.log("info", "hello").await.expect("PluginLog must be authenticated");
        assert_eq!(seen.lock().unwrap().as_deref(), Some(TOKEN));

        handle.abort();
    }
}
