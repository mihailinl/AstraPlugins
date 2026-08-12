// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! Level 2: a mock daemon on loopback, the plugin's real startup path, and a
//! real gRPC client driving it.
//!
//! [`MockDaemon`] enforces what the daemon enforces, and no more:
//!
//! * `Register` is the only auth-exempt path; every other host RPC must carry
//!   `x-session-token` (`astra-daemon/src/server/auth_interceptor.rs`).
//! * A host RPC whose `[permissions]` grant is missing answers
//!   `PERMISSION_DENIED` (`require_permission`, `host_service.rs`). The
//!   permission names are the ones in `spec/hooks.yaml`.
//! * The protocol handshake is answered with real numbers, so the SDK's own
//!   version check runs.
//!
//! [`WireHarness`] then runs [`run_with`](crate::run_with) — the actual
//! runner, not a copy of it — against that daemon, reads the port out of the
//! `Register` the plugin sent, and connects a `PluginCapabilityServiceClient`
//! carrying the spawn token the daemon's own client carries.

use std::collections::HashSet;
use std::sync::{Arc, Mutex};

use anyhow::{Context, Result};
use tokio::task::JoinHandle;

use super::host::{
    ChatMessage, FiredTrigger, LogLine, Recorded, SDK_HOST_RPCS, UiPush, Variable, check_any_rpc,
};
use crate::capability::PluginCapability;
use crate::proto;
use crate::proto::plugin_host_service_server::{PluginHostService, PluginHostServiceServer};

/// The session token this daemon issues. A real one, in the sense that matters:
/// every non-`Register` RPC is rejected without it.
const SESSION_TOKEN: &str = "mock-daemon-session-token";

/// The spawn token the daemon passes on argv as `--auth-token` and presents
/// back to the plugin as `x-plugin-token`.
const SPAWN_TOKEN: &str = "mock-daemon-spawn-token";

/// The `PluginCapabilityService` client, as the daemon holds it.
pub type CapabilityClient = proto::plugin_capability_service_client::PluginCapabilityServiceClient<
    tonic::transport::Channel,
>;

struct DaemonState {
    recorded: Recorded,
    granted: Mutex<HashSet<String>>,
    registration: Mutex<Option<proto::PluginRegisterRequest>>,
    config_json: Mutex<String>,
    language: Mutex<String>,
    /// Events queued for `SubscribeEvents` — delivered once, then the stream
    /// stays open.
    events: Mutex<Vec<proto::PluginEventMsg>>,
    protocol: (u32, u32),
}

/// A stand-in for the Astra daemon, serving `PluginHostService` on loopback.
///
/// Cloning is cheap and shares one daemon; dropping the last clone leaves the
/// server task running until the process exits, which is what a test wants.
#[derive(Clone)]
pub struct MockDaemon {
    state: Arc<DaemonState>,
    addr: String,
    _server: Arc<ServerTask>,
}

struct ServerTask(JoinHandle<()>);

impl Drop for ServerTask {
    fn drop(&mut self) {
        self.0.abort();
    }
}

impl MockDaemon {
    /// Start on an OS-assigned loopback port, granting every permission.
    ///
    /// Grant-everything is the right default because a test that has not said
    /// anything about permissions is testing something else; use
    /// [`revoke`](Self::revoke) to test the denial.
    pub async fn start() -> Result<Self> {
        Self::start_with(
            crate::protocol::PROTOCOL_VERSION,
            crate::protocol::MIN_SUPPORTED_DAEMON_PROTOCOL,
        )
        .await
    }

    /// Start a daemon that speaks `protocol` and accepts `floor` or newer —
    /// for testing what a plugin does against an Astra that refuses it.
    pub async fn start_with(protocol: u32, floor: u32) -> Result<Self> {
        let state = Arc::new(DaemonState {
            recorded: Recorded::new(),
            granted: Mutex::new(
                super::host::HOST_RPCS
                    .iter()
                    .chain(SDK_HOST_RPCS)
                    .map(|s| s.to_string())
                    .collect(),
            ),
            registration: Mutex::new(None),
            config_json: Mutex::new(String::new()),
            language: Mutex::new("en".to_string()),
            events: Mutex::new(Vec::new()),
            protocol: (protocol, floor),
        });

        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .context("MockDaemon could not bind loopback")?;
        let addr = listener.local_addr()?.to_string();

        let service = HostService {
            state: state.clone(),
        };
        let handle = tokio::spawn(async move {
            let _ = tonic::transport::Server::builder()
                .add_service(PluginHostServiceServer::new(service))
                .serve_with_incoming(tokio_stream::wrappers::TcpListenerStream::new(listener))
                .await;
        });

        Ok(Self {
            state,
            addr,
            _server: Arc::new(ServerTask(handle)),
        })
    }

    /// `host:port` — what the daemon passes as `--daemon-addr`.
    pub fn addr(&self) -> &str {
        &self.addr
    }

    /// The session token this daemon issued.
    pub fn session_token(&self) -> &'static str {
        SESSION_TOKEN
    }

    /// The spawn token, as `--auth-token` and as `x-plugin-token`.
    pub fn spawn_token(&self) -> &'static str {
        SPAWN_TOKEN
    }

    /// Everything the plugin said, in order. Same type the level-1
    /// [`RecordingHost`](super::RecordingHost) fills, so assertions read the
    /// same at both levels.
    pub fn recorded(&self) -> Recorded {
        self.state.recorded.clone()
    }

    /// Every host RPC that arrived without a valid `x-session-token`.
    ///
    /// See [`Recorded::unauthenticated_calls`]. A non-empty list means the
    /// plugin's host client is not authenticating, which on a real daemon means
    /// none of its host calls do anything.
    pub fn unauthenticated_calls(&self) -> Vec<String> {
        self.state.recorded.unauthenticated_calls()
    }

    /// Every `FireTrigger` that reached the daemon.
    pub fn fired_triggers(&self) -> Vec<FiredTrigger> {
        self.state.recorded.fired_triggers()
    }
    /// Every `PluginLog`.
    pub fn logs(&self) -> Vec<LogLine> {
        self.state.recorded.logs()
    }
    /// Every `SetVariable`.
    pub fn variables(&self) -> Vec<Variable> {
        self.state.recorded.variables()
    }
    /// Every `PushToUi`.
    pub fn ui_pushes(&self) -> Vec<UiPush> {
        self.state.recorded.ui_pushes()
    }
    /// Every `SendChatMessage`.
    pub fn chat_messages(&self) -> Vec<ChatMessage> {
        self.state.recorded.chat_messages()
    }

    /// The `Register` the plugin sent, once it has sent one.
    ///
    /// This is the only place the plugin's capability list, protocol version
    /// and SDK name are observable at all — the level-1 harness never
    /// registers.
    pub fn registration(&self) -> Option<proto::PluginRegisterRequest> {
        self.state
            .registration
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }

    /// The settings this daemon hands out at registration.
    pub fn set_config_json(&self, json: impl Into<String>) {
        *self.state.config_json.lock().unwrap_or_else(|e| e.into_inner()) = json.into();
    }

    /// The UI language this daemon reports at registration.
    pub fn set_language(&self, language: impl Into<String>) {
        *self.state.language.lock().unwrap_or_else(|e| e.into_inner()) = language.into();
    }

    /// Events to deliver on the plugin's `SubscribeEvents` stream.
    pub fn queue_events(&self, events: impl IntoIterator<Item = proto::PluginEventMsg>) {
        self.state
            .events
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .extend(events);
    }

    /// Take a permission away, so the rpcs it gates answer `PERMISSION_DENIED`.
    ///
    /// `[permissions]` is default-deny in production; this is how a plugin's
    /// handling of the denial gets tested before a user meets it. Panics on a
    /// name that is not a host RPC.
    pub fn revoke(&self, rpc: &str) {
        check_any_rpc(rpc);
        self.state
            .granted
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .remove(rpc);
    }

    /// Grant a permission back.
    pub fn grant(&self, rpc: &str) {
        check_any_rpc(rpc);
        self.state
            .granted
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .insert(rpc.to_string());
    }
}

// ── the service ──────────────────────────────────────────────────────────────

struct HostService {
    state: Arc<DaemonState>,
}

impl HostService {
    /// The daemon's two gates, in the daemon's order: authenticate, then
    /// authorise. `rpc` is the permission name from `spec/hooks.yaml`, or
    /// `"none"` for an rpc no permission gates.
    #[allow(clippy::result_large_err)] // tonic::Status is large; every RPC pays it
    fn gate<T>(&self, req: &tonic::Request<T>, rpc: &str) -> Result<(), tonic::Status> {
        self.state.recorded.note(rpc);
        let token = req
            .metadata()
            .get(crate::wire::SESSION_TOKEN_HEADER)
            .and_then(|v| v.to_str().ok());
        if token != Some(SESSION_TOKEN) {
            // On the record, not just refused. `astra-plugin test` reuses this
            // daemon over a real plugin process and asserts this list is empty:
            // a host client that stops sending the token turns every RPC into
            // an `UNAUTHENTICATED` the plugin swallows, and the conformance run
            // would otherwise stay green through all of them.
            self.state.recorded.note_unauthenticated(rpc);
            return Err(tonic::Status::unauthenticated(
                "Missing or invalid session token",
            ));
        }
        if rpc != "none"
            && !self
                .state
                .granted
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .contains(rpc)
        {
            return Err(tonic::Status::permission_denied(format!(
                "plugin has no `{rpc}` grant"
            )));
        }
        Ok(())
    }
}

#[tonic::async_trait]
impl PluginHostService for HostService {
    async fn register(
        &self,
        req: tonic::Request<proto::PluginRegisterRequest>,
    ) -> Result<tonic::Response<proto::PluginRegisterResponse>, tonic::Status> {
        let req = req.into_inner();
        let declared = req.protocol_version;
        let (speaks, floor) = self.state.protocol;
        *self
            .state
            .registration
            .lock()
            .unwrap_or_else(|e| e.into_inner()) = Some(req);

        if declared < floor {
            return Ok(tonic::Response::new(proto::PluginRegisterResponse {
                success: false,
                error: format!(
                    "Plugin speaks protocol {declared}; this daemon accepts {floor} or newer."
                ),
                daemon_version: "mock".into(),
                protocol_version: speaks,
                min_supported_protocol: floor,
                ..Default::default()
            }));
        }

        Ok(tonic::Response::new(proto::PluginRegisterResponse {
            success: true,
            error: String::new(),
            config_json: self
                .state
                .config_json
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .clone(),
            daemon_version: "mock".into(),
            client_session_token: SESSION_TOKEN.into(),
            language: self
                .state
                .language
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .clone(),
            protocol_version: speaks,
            min_supported_protocol: floor,
            error_detail: None,
        }))
    }

    async fn plugin_log(
        &self,
        req: tonic::Request<proto::PluginLogRequest>,
    ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
        self.gate(&req, "log")?;
        let req = req.into_inner();
        self.state.recorded.log_line(LogLine {
            level: req.level,
            message: req.message,
        });
        Ok(tonic::Response::new(proto::Empty {}))
    }

    async fn fire_trigger(
        &self,
        req: tonic::Request<proto::PluginFireTriggerRequest>,
    ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
        self.gate(&req, "fire_trigger")?;
        // Off the metadata, before `into_inner()` consumes it. This is the only
        // place in the tree that observes the invocation lease as it actually
        // arrives on a socket, rather than as the SDK intended to send it.
        let caused_by = req
            .metadata()
            .get(crate::wire::X_ASTRA_CAUSE)
            .and_then(|v| v.to_str().ok())
            .map(str::to_owned);
        let req = req.into_inner();
        self.state.recorded.trigger(FiredTrigger {
            trigger_type: req.trigger_type,
            payload_json: req.payload_json,
            caused_by,
        });
        Ok(tonic::Response::new(proto::Empty {}))
    }

    async fn get_plugin_self_config(
        &self,
        req: tonic::Request<proto::PluginSelfIdRequest>,
    ) -> Result<tonic::Response<proto::PluginSelfConfigResponse>, tonic::Status> {
        self.gate(&req, "get_config")?;
        Ok(tonic::Response::new(proto::PluginSelfConfigResponse {
            config_json: self
                .state
                .config_json
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .clone(),
        }))
    }

    async fn get_daemon_info(
        &self,
        req: tonic::Request<proto::Empty>,
    ) -> Result<tonic::Response<proto::PluginDaemonInfoResponse>, tonic::Status> {
        self.gate(&req, "get_daemon_info")?;
        Ok(tonic::Response::new(proto::PluginDaemonInfoResponse {
            version: "mock".into(),
            state: "ready".into(),
            grpc_port: 0,
            language: self
                .state
                .language
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .clone(),
        }))
    }

    async fn set_variable(
        &self,
        req: tonic::Request<proto::PluginSetVariableRequest>,
    ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
        self.gate(&req, "set_variable")?;
        let req = req.into_inner();
        self.state.recorded.variable_set(Variable {
            name: req.name,
            value: req.value,
            scope: req.scope,
        });
        Ok(tonic::Response::new(proto::Empty {}))
    }

    async fn set_theme_contribution(
        &self,
        req: tonic::Request<proto::PluginThemeContribution>,
    ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
        self.gate(&req, "set_theme_contribution")?;
        self.state.recorded.theme(req.into_inner());
        Ok(tonic::Response::new(proto::Empty {}))
    }

    async fn push_to_ui(
        &self,
        req: tonic::Request<proto::PluginUiPushRequest>,
    ) -> Result<tonic::Response<proto::Empty>, tonic::Status> {
        self.gate(&req, "push_to_ui")?;
        let req = req.into_inner();
        self.state.recorded.ui_push(UiPush {
            event: req.event,
            payload_json: req.payload_json,
        });
        Ok(tonic::Response::new(proto::Empty {}))
    }

    type SubscribeEventsStream = std::pin::Pin<
        Box<dyn tokio_stream::Stream<Item = Result<proto::PluginEventMsg, tonic::Status>> + Send>,
    >;

    async fn subscribe_events(
        &self,
        req: tonic::Request<proto::PluginEventFilter>,
    ) -> Result<tonic::Response<Self::SubscribeEventsStream>, tonic::Status> {
        // `subscribe_events` is a permission like any other — the daemon
        // enforces it server-side precisely because a plugin that subscribes to
        // everything sees every `SpeechRecognized` transcript.
        self.gate(&req, "subscribe_events")?;
        let filter = req.into_inner();
        let queued: Vec<proto::PluginEventMsg> = self
            .state
            .events
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .iter()
            .filter(|e| filter.event_types.is_empty() || filter.event_types.contains(&e.event_type))
            .cloned()
            .collect();

        // Deliver the backlog, then hold the stream open — a stream that ends
        // sends the runner into its reconnect loop, which is noise in a test.
        let out = async_stream::stream! {
            for event in queued {
                yield Ok(event);
            }
            std::future::pending::<()>().await;
        };
        Ok(tonic::Response::new(Box::pin(out)))
    }

    type SendChatMessageStream = std::pin::Pin<
        Box<dyn tokio_stream::Stream<Item = Result<proto::PluginChatChunk, tonic::Status>> + Send>,
    >;

    async fn send_chat_message(
        &self,
        req: tonic::Request<proto::PluginChatRequest>,
    ) -> Result<tonic::Response<Self::SendChatMessageStream>, tonic::Status> {
        self.gate(&req, "send_chat_message")?;
        let req = req.into_inner();
        self.state.recorded.chat(ChatMessage {
            text: req.text,
            conversation_id: req.conversation_id,
            voice_enabled: req.voice_enabled,
        });
        Ok(tonic::Response::new(Box::pin(tokio_stream::empty())))
    }
}

// ── the plugin, over the wire ────────────────────────────────────────────────

/// A plugin started the way the daemon starts it, driven the way the daemon
/// drives it. See the [module docs](super).
pub struct WireHarness {
    daemon: MockDaemon,
    client: CapabilityClient,
    addr: String,
    run: Option<JoinHandle<Result<()>>>,
}

impl WireHarness {
    /// Start `plugin` against a fresh [`MockDaemon`], with the capability
    /// server requiring the spawn token — the setting the daemon will ship.
    pub async fn start<P: PluginCapability>(plugin: P) -> Result<Self> {
        Self::start_on(MockDaemon::start().await?, plugin, "test-plugin", &[]).await
    }

    /// [`start`](Self::start), against a daemon a test has already staged, with
    /// an explicit plugin id and the capability list the daemon would pass from
    /// `plugin.toml`.
    pub async fn start_on<P: PluginCapability>(
        daemon: MockDaemon,
        plugin: P,
        plugin_id: &str,
        capabilities: &[&str],
    ) -> Result<Self> {
        let mut argv = vec![
            "plugin".to_string(),
            "--daemon-addr".to_string(),
            daemon.addr().to_string(),
            "--plugin-id".to_string(),
            plugin_id.to_string(),
            "--auth-token".to_string(),
            SPAWN_TOKEN.to_string(),
        ];
        if !capabilities.is_empty() {
            argv.push("--capabilities".to_string());
            argv.push(capabilities.join(","));
        }

        let config = crate::RunConfig {
            init_tracing: false,
            argv: Some(argv),
            // Require the token: this is the level that can test the guard at
            // all, so it tests the strict setting.
            capability_auth: crate::CapabilityAuth::Require,
            ..crate::RunConfig::default()
        };

        let mut run = tokio::spawn(crate::run_with(plugin, config));

        // Two things have to be raced against the plugin dying, and both of
        // them used to be waits on a clock. Registration happens *before*
        // `on_start`, so a plugin whose `on_start` fails has already told the
        // daemon a port that will never accept — waiting on that socket reports
        // "transport error" ten seconds later, when what the author needs is
        // the sentence `on_start` returned.
        //
        // `&mut JoinHandle` is itself a future, so the select leaves the handle
        // usable when the plugin is the one that won.

        // The plugin binds before it registers, so the port on the `Register`
        // it sent is a port that is already listening.
        let port = {
            let deadline = tokio::time::sleep(std::time::Duration::from_secs(10));
            tokio::pin!(deadline);
            loop {
                if let Some(reg) = daemon.registration() {
                    break reg.port as u16;
                }
                tokio::select! {
                    biased;
                    joined = &mut run => return Err(exit_error(joined, "registering")),
                    _ = &mut deadline => {
                        anyhow::bail!("the plugin did not register within 10s")
                    }
                    _ = tokio::time::sleep(std::time::Duration::from_millis(5)) => {}
                }
            }
        };

        let addr = format!("http://127.0.0.1:{port}");
        let client = tokio::select! {
            biased;
            joined = &mut run => return Err(exit_error(joined, "serving")),
            client = connect(&addr) => client?,
        };

        Ok(Self {
            daemon,
            client,
            addr,
            run: Some(run),
        })
    }

    /// The daemon the plugin registered with.
    pub fn daemon(&self) -> &MockDaemon {
        &self.daemon
    }

    /// Every `FireTrigger` that reached the daemon.
    pub fn fired_triggers(&self) -> Vec<FiredTrigger> {
        self.daemon.fired_triggers()
    }
    /// Every `PluginLog` that reached the daemon.
    pub fn logs(&self) -> Vec<LogLine> {
        self.daemon.logs()
    }
    /// Every `SetVariable` that reached the daemon.
    pub fn variables(&self) -> Vec<Variable> {
        self.daemon.variables()
    }

    /// `http://127.0.0.1:<port>` — the plugin's own gRPC server.
    pub fn plugin_addr(&self) -> &str {
        &self.addr
    }

    /// A client carrying the spawn token, as the daemon's own client carries
    /// it. Clone it per call; tonic clients are `Clone` for that.
    pub fn client(&self) -> CapabilityClient {
        self.client.clone()
    }

    /// A request with the spawn token attached.
    pub fn request<T>(&self, message: T) -> tonic::Request<T> {
        let mut req = tonic::Request::new(message);
        req.metadata_mut()
            .insert(crate::wire::PLUGIN_TOKEN_HEADER, SPAWN_TOKEN.parse().unwrap());
        req
    }

    /// A request with **no** token — what another local process would send.
    /// Everything must answer `UNAUTHENTICATED`.
    pub fn unauthenticated_request<T>(&self, message: T) -> tonic::Request<T> {
        tonic::Request::new(message)
    }

    /// `ListTools`, over the wire.
    pub async fn list_tools(&self) -> Result<Vec<crate::capability::ToolDef>, tonic::Status> {
        let resp = self
            .client()
            .list_tools(self.request(proto::Empty {}))
            .await?;
        Ok(resp.into_inner().tools.into_iter().map(Into::into).collect())
    }

    /// `CallTool`, over the wire. A failed tool call is a *successful* RPC —
    /// the response carries `success = false` and the coded error.
    pub async fn call_tool(
        &self,
        tool_name: &str,
        arguments_json: &str,
    ) -> Result<proto::PluginCallToolResponse, tonic::Status> {
        let resp = self
            .client()
            .call_tool(self.request(proto::PluginCallToolRequest {
                tool_name: tool_name.to_string(),
                arguments_json: arguments_json.to_string(),
            }))
            .await?;
        Ok(resp.into_inner())
    }

    /// `ExecuteAction`, over the wire.
    pub async fn execute_action(
        &self,
        action_type: &str,
        params_json: &str,
    ) -> Result<proto::PluginExecuteActionResponse, tonic::Status> {
        let resp = self
            .client()
            .execute_action(self.request(proto::PluginExecuteActionRequest {
                action_type: action_type.to_string(),
                params_json: params_json.to_string(),
            }))
            .await?;
        Ok(resp.into_inner())
    }

    /// `OnConfigChanged`, over the wire.
    pub async fn config_changed(&self, config_json: &str) -> Result<(), tonic::Status> {
        self.client()
            .on_config_changed(self.request(proto::PluginConfigChangedMsg {
                config_json: config_json.to_string(),
            }))
            .await?;
        Ok(())
    }

    /// `OnActiveTriggers`, over the wire.
    pub async fn active_triggers(&self, types: &[&str]) -> Result<(), tonic::Status> {
        self.client()
            .on_active_triggers(self.request(proto::PluginActiveTriggersMsg {
                trigger_types: types.iter().map(|s| s.to_string()).collect(),
            }))
            .await?;
        Ok(())
    }

    /// `HealthCheck`, over the wire.
    pub async fn health(&self) -> Result<proto::PluginHealthResponse, tonic::Status> {
        let resp = self
            .client()
            .health_check(self.request(proto::Empty {}))
            .await?;
        Ok(resp.into_inner())
    }

    /// `SttProcess`: stream `chunks` in and collect every event that comes
    /// back.
    ///
    /// The audio channel between the inbound stream and the plugin's hook is
    /// the one `spec/limits.yaml` sizes, and this is the only level at which it
    /// exists — see
    /// [`fixtures::channel_saturating_burst`](super::fixtures::channel_saturating_burst).
    pub async fn stt_process(
        &self,
        chunks: Vec<Vec<u8>>,
        sample_rate: u32,
        options: crate::capability::SttOptions,
    ) -> Result<Vec<proto::PluginSttEvent>, tonic::Status> {
        use tokio_stream::StreamExt;

        let outbound = async_stream::stream! {
            let mut first = true;
            for data in chunks {
                yield proto::PluginAudioChunk {
                    data,
                    is_last: false,
                    sample_rate,
                    options: first.then(|| options.clone()),
                };
                first = false;
            }
            yield proto::PluginAudioChunk {
                data: Vec::new(),
                is_last: true,
                sample_rate,
                options: None,
            };
        };

        let mut stream = self
            .client()
            .stt_process(self.request(outbound))
            .await?
            .into_inner();
        let mut events = Vec::new();
        while let Some(ev) = stream.next().await {
            events.push(ev?);
        }
        Ok(events)
    }

    /// `Shutdown`, then wait for the runner to finish and report what it
    /// returned — a serve failure has to surface as an `Err`, not as a quiet
    /// exit.
    pub async fn shutdown(mut self) -> Result<()> {
        let _ = self
            .client()
            .shutdown(self.request(proto::Empty {}))
            .await;
        let Some(run) = self.run.take() else {
            return Ok(());
        };
        match tokio::time::timeout(std::time::Duration::from_secs(10), run).await {
            Ok(joined) => joined.context("the plugin task panicked")?,
            Err(_) => {
                anyhow::bail!("the plugin did not stop within 10s of `Shutdown`")
            }
        }
    }
}

impl std::fmt::Debug for WireHarness {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("WireHarness")
            .field("daemon", &self.daemon.addr())
            .field("plugin", &self.addr)
            .field("running", &self.run.as_ref().is_some_and(|r| !r.is_finished()))
            .finish()
    }
}

impl Drop for WireHarness {
    fn drop(&mut self) {
        if let Some(run) = self.run.take() {
            run.abort();
        }
    }
}

/// What the plugin's own exit means, as one sentence naming the phase it never
/// reached.
fn exit_error(
    joined: std::result::Result<Result<()>, tokio::task::JoinError>,
    phase: &'static str,
) -> anyhow::Error {
    match joined {
        Ok(Err(e)) => e.context(format!("the plugin exited before {phase}")),
        Ok(Ok(())) => anyhow::anyhow!("the plugin exited cleanly before {phase}"),
        Err(join) => anyhow::Error::new(join).context(format!("the plugin panicked before {phase}")),
    }
}

/// Connect a capability client, retrying while the listener finishes coming up.
async fn connect(addr: &str) -> Result<CapabilityClient> {
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    loop {
        match CapabilityClient::connect(addr.to_string()).await {
            Ok(c) => return Ok(c),
            Err(e) => {
                anyhow::ensure!(
                    std::time::Instant::now() < deadline,
                    "could not reach the plugin at {addr}: {e}"
                );
                tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            }
        }
    }
}
