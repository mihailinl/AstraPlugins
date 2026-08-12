//! Finding and talking to a running Astra daemon.
//!
//! Two things live here: locating the daemon ([`resolve_addr`]) and a thin
//! client for the handful of `PluginService` RPCs `astra-plugin dev` needs
//! ([`DaemonClient`]).
//!
//! **Why the messages are hand-written.** The CLI needs five unary RPCs and
//! eight small messages. Generating them would mean vendoring a fourth copy of
//! the 2 500-line `plugin.proto` into this crate plus a `tonic-build` step —
//! exactly the duplication the rest of this change deletes. Every field below
//! is transcribed from `Astra/astra-rs/astra-proto/src/astra.proto`
//! (`service PluginService`, `service ClientAuthService`) and carries its tag,
//! so a drift is a one-line diff rather than a regenerated tree. Fields the CLI
//! does not read are omitted on purpose: prost skips unknown fields on decode.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use anyhow::{Context, Result};
use tonic::codec::ProstCodec;
use tonic::codegen::http::uri::PathAndQuery;
use tonic::metadata::{Ascii, MetadataValue};
use tonic::transport::{Channel, Endpoint};
use tonic::{Request, Status};

/// Where the daemon listens when no port file exists.
/// Mirrors `NetworkSettings::default()` in `Astra/astra-rs/astra-core/src/config.rs`.
pub const DEFAULT_DAEMON_ADDR: &str = "127.0.0.1:32000";

/// Daemon-written file carrying the actually-bound gRPC port.
/// `astra-core::config::DAEMON_PORT_FILENAME`, written by `write_port_file`.
const DAEMON_PORT_FILENAME: &str = "daemon.port";

/// Daemon-written file carrying the local IPC bootstrap secret (0600).
/// `astra-core::config::DAEMON_TOKEN_FILENAME`.
const DAEMON_TOKEN_FILENAME: &str = "daemon.token";

/// Header the daemon's `AuthLayer` reads on every non-exempt RPC.
/// Declared once in `spec/wire.yaml`; this is the generated reader.
use astra_plugin_sdk::wire::SESSION_TOKEN_HEADER;

/// Name this CLI registers under. Anything that is not the reserved overlay or
/// companion name lands in the bounded main-client FIFO, same as `astraui`.
const CLIENT_NAME: &str = "astra-plugin-cli";

const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);

/// Astra's config directory — the ONE `ProjectDirs::from` in this crate, with
/// the same arguments as `astra_core::Paths::discover`.
pub fn config_dir() -> Option<PathBuf> {
    directories::ProjectDirs::from("com", "astra", "astra")
        .map(|dirs| dirs.config_dir().to_path_buf())
}

/// Resolve the daemon's gRPC address.
///
/// Explicit `--daemon-addr` wins; otherwise read the port the daemon actually
/// bound from `<config>/daemon.port` (it takes an OS-assigned port when 32000
/// is busy, so the default is a guess, not a fact); otherwise fall back.
pub fn resolve_addr(explicit: Option<&str>) -> String {
    if let Some(addr) = explicit {
        return addr.to_string();
    }
    let from_file = config_dir()
        .map(|dir| dir.join(DAEMON_PORT_FILENAME))
        .and_then(|path| fs::read_to_string(path).ok())
        .and_then(|s| s.trim().parse::<u16>().ok())
        .filter(|port| *port != 0);
    match from_file {
        Some(port) => format!("127.0.0.1:{port}"),
        None => DEFAULT_DAEMON_ADDR.to_string(),
    }
}

/// Read the daemon's bootstrap secret from `<config>/daemon.token`.
fn read_daemon_secret() -> Result<String> {
    let path = config_dir()
        .map(|dir| dir.join(DAEMON_TOKEN_FILENAME))
        .context("Could not determine Astra's config directory")?;
    let secret = fs::read_to_string(&path).with_context(|| {
        format!(
            "Could not read {}. Astra does not look like it is running — start the app first.",
            path.display()
        )
    })?;
    let secret = secret.trim().to_string();
    if secret.is_empty() {
        anyhow::bail!("{} is empty — restart Astra", path.display());
    }
    Ok(secret)
}

// ---------------------------------------------------------------------------
// Wire messages — transcribed from astra.proto. Tags are load-bearing.
// ---------------------------------------------------------------------------

/// `astra.RegisterClientRequest`
#[derive(Clone, PartialEq, ::prost::Message)]
struct RegisterClientRequest {
    #[prost(string, tag = "1")]
    daemon_secret: String,
    #[prost(string, tag = "2")]
    client_name: String,
}

/// `astra.RegisterClientResponse`
#[derive(Clone, PartialEq, ::prost::Message)]
struct RegisterClientResponse {
    #[prost(bool, tag = "1")]
    success: bool,
    #[prost(string, tag = "2")]
    session_token: String,
    #[prost(string, tag = "3")]
    error: String,
}

/// `astra.SideloadPluginRequest`
#[derive(Clone, PartialEq, ::prost::Message)]
struct SideloadPluginRequest {
    #[prost(string, tag = "1")]
    path: String,
}

/// `astra.PluginIdRequest`
#[derive(Clone, PartialEq, ::prost::Message)]
struct PluginIdRequest {
    #[prost(string, tag = "1")]
    plugin_id: String,
}

/// `astra.PluginLogsRequest`
#[derive(Clone, PartialEq, ::prost::Message)]
struct PluginLogsRequest {
    #[prost(string, tag = "1")]
    plugin_id: String,
    #[prost(int32, tag = "2")]
    lines: i32,
}

/// `astra.PluginLogsResponse`
#[derive(Clone, PartialEq, ::prost::Message)]
struct PluginLogsResponse {
    #[prost(string, repeated, tag = "1")]
    lines: Vec<String>,
}

/// `astra.Empty`
#[derive(Clone, PartialEq, ::prost::Message)]
struct Empty {}

/// `astra.PluginStatusMsg` — only the fields the CLI reports on.
#[derive(Clone, PartialEq, ::prost::Message)]
pub struct PluginStatus {
    #[prost(string, tag = "1")]
    pub id: String,
    #[prost(string, tag = "3")]
    pub version: String,
    #[prost(string, tag = "6")]
    pub status: String,
    #[prost(string, tag = "7")]
    pub error: String,
    #[prost(string, repeated, tag = "8")]
    pub capabilities: Vec<String>,
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

/// An authenticated connection to a running daemon.
pub struct DaemonClient {
    grpc: tonic::client::Grpc<Channel>,
    session_token: MetadataValue<Ascii>,
    addr: String,
}

impl DaemonClient {
    /// Connect and register as a client, returning an already-authenticated
    /// handle. `RegisterClient` is the daemon's one exempt bootstrap path; every
    /// call after it carries `x-session-token`.
    pub async fn connect(addr: &str) -> Result<Self> {
        let secret = read_daemon_secret()?;

        let channel = Endpoint::from_shared(format!("http://{addr}"))
            .with_context(|| format!("Invalid daemon address '{addr}'"))?
            .connect_timeout(CONNECT_TIMEOUT)
            .connect()
            .await
            .with_context(|| {
                format!("Could not reach the Astra daemon at {addr}. Is Astra running?")
            })?;

        let mut grpc = tonic::client::Grpc::new(channel);
        let response: RegisterClientResponse = unary(
            &mut grpc,
            "/astra.ClientAuthService/RegisterClient",
            RegisterClientRequest {
                daemon_secret: secret,
                client_name: CLIENT_NAME.to_string(),
            },
            None,
        )
        .await
        .map_err(|s| anyhow::anyhow!("Client registration failed: {}", s.message()))?;

        if !response.success || response.session_token.is_empty() {
            anyhow::bail!(
                "The daemon refused this CLI's registration: {}",
                if response.error.is_empty() {
                    "no reason given".to_string()
                } else {
                    response.error
                }
            );
        }

        let session_token: MetadataValue<Ascii> = response
            .session_token
            .parse()
            .context("Daemon returned a session token that is not a valid header value")?;

        Ok(Self {
            grpc,
            session_token,
            addr: addr.to_string(),
        })
    }

    /// The address this client is connected to.
    pub fn addr(&self) -> &str {
        &self.addr
    }

    /// `PluginService.SideloadPlugin` — the daemon loads the plugin in place
    /// from `dir`, spawns it, and mints its `--auth-token`.
    pub async fn sideload_plugin(&mut self, dir: &Path) -> Result<PluginStatus, Status> {
        let request = SideloadPluginRequest {
            path: dir.to_string_lossy().into_owned(),
        };
        self.call("/astra.PluginService/SideloadPlugin", request).await
    }

    /// `PluginService.StartPlugin`
    pub async fn start_plugin(&mut self, plugin_id: &str) -> Result<(), Status> {
        let request = PluginIdRequest {
            plugin_id: plugin_id.to_string(),
        };
        let _: Empty = self.call("/astra.PluginService/StartPlugin", request).await?;
        Ok(())
    }

    /// `PluginService.StopPlugin`
    pub async fn stop_plugin(&mut self, plugin_id: &str) -> Result<(), Status> {
        let request = PluginIdRequest {
            plugin_id: plugin_id.to_string(),
        };
        let _: Empty = self.call("/astra.PluginService/StopPlugin", request).await?;
        Ok(())
    }

    /// `PluginService.GetPluginLogs` — the last `lines` lines of the plugin's
    /// captured stdout/stderr. Unary, so the "stream" is a poll.
    pub async fn plugin_logs(&mut self, plugin_id: &str, lines: i32) -> Result<Vec<String>, Status> {
        let request = PluginLogsRequest {
            plugin_id: plugin_id.to_string(),
            lines,
        };
        let response: PluginLogsResponse =
            self.call("/astra.PluginService/GetPluginLogs", request).await?;
        Ok(response.lines)
    }

    async fn call<Req, Res>(&mut self, path: &'static str, request: Req) -> Result<Res, Status>
    where
        Req: prost::Message + Send + Sync + 'static,
        Res: prost::Message + Default + Send + Sync + 'static,
    {
        unary(&mut self.grpc, path, request, Some(&self.session_token)).await
    }
}

async fn unary<Req, Res>(
    grpc: &mut tonic::client::Grpc<Channel>,
    path: &'static str,
    message: Req,
    session_token: Option<&MetadataValue<Ascii>>,
) -> Result<Res, Status>
where
    Req: prost::Message + Send + Sync + 'static,
    Res: prost::Message + Default + Send + Sync + 'static,
{
    grpc.ready()
        .await
        .map_err(|e| Status::unavailable(format!("Daemon connection is not ready: {e}")))?;

    let mut request = Request::new(message);
    if let Some(token) = session_token {
        request
            .metadata_mut()
            .insert(SESSION_TOKEN_HEADER, token.clone());
    }

    let codec: ProstCodec<Req, Res> = ProstCodec::default();
    grpc.unary(request, PathAndQuery::from_static(path), codec)
        .await
        .map(|response| response.into_inner())
}

/// Turn a daemon refusal into something a plugin author can act on.
///
/// The two refusals worth naming are the Developer-Mode gate on
/// `sideload_plugin` (`manager.rs`, `allow_unsigned_plugins`) and the
/// user-auth/lock layer, which answers `permission_denied` for both "not signed
/// in" and "Astra is locked".
pub fn explain(action: &str, status: Status) -> anyhow::Error {
    let message = status.message().to_string();
    let lowered = message.to_lowercase();

    if lowered.contains("sideloading is disabled")
        || lowered.contains("allow_unsigned_plugins")
        || lowered.contains("developer mode")
    {
        return anyhow::anyhow!(
            "{action} was refused: Developer Mode is off.\n\
             Sideloading runs unsigned local code with your full privileges, so Astra keeps it \
             behind an explicit opt-in.\n\
             Enable it in Astra → Settings → Safety → \"Allow unsigned plugins\" \
             (safety.allow_unsigned_plugins), then run this command again.\n\
             Daemon said: {message}"
        );
    }

    match status.code() {
        tonic::Code::PermissionDenied => anyhow::anyhow!(
            "{action} was refused by the daemon: {message}\n\
             Astra refuses plugin RPCs while signed out or locked — sign in and unlock the app, \
             then try again."
        ),
        tonic::Code::Unauthenticated => anyhow::anyhow!(
            "{action} was rejected as unauthenticated: {message}\n\
             The CLI's session expired; restart the command."
        ),
        tonic::Code::Unavailable => anyhow::anyhow!(
            "{action} could not reach the daemon: {message}\n\
             Is Astra still running?"
        ),
        _ => anyhow::anyhow!("{action} failed: {message}"),
    }
}
