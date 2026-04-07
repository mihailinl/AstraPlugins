//! HostClient — plugin-side gRPC client for calling the Astra daemon.

use anyhow::{Context, Result};
use tonic::transport::Channel;

use crate::proto;
use crate::proto::plugin_host_service_client::PluginHostServiceClient;

/// Client for calling daemon services from a plugin.
#[derive(Clone)]
pub struct HostClient {
    client: PluginHostServiceClient<Channel>,
    plugin_id: String,
}

impl HostClient {
    pub(crate) async fn connect(daemon_addr: &str, plugin_id: String) -> Result<Self> {
        let client = PluginHostServiceClient::connect(format!("http://{daemon_addr}"))
            .await
            .context("Failed to connect to daemon")?;

        Ok(Self { client, plugin_id })
    }

    /// Register this plugin with the daemon.
    pub(crate) async fn register(
        &mut self,
        port: u16,
        capabilities: Vec<String>,
    ) -> Result<proto::PluginRegisterResponse> {
        let resp = self
            .client
            .register(proto::PluginRegisterRequest {
                plugin_id: self.plugin_id.clone(),
                port: port as u32,
                capabilities,
            })
            .await
            .context("Register RPC failed")?;

        Ok(resp.into_inner())
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
    pub async fn subscribe_events(
        &mut self,
        event_types: Vec<String>,
    ) -> Result<tonic::Streaming<proto::PluginEventMsg>> {
        let resp = self
            .client
            .subscribe_events(proto::PluginEventFilter {
                plugin_id: self.plugin_id.clone(),
                event_types,
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
