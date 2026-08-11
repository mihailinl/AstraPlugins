//! A `PluginContext` for tests that never reaches a daemon.

use std::sync::{Arc, Mutex};

use astra_plugin_sdk::anyhow::{Result, bail};
use astra_plugin_sdk::{ChatStream, Host, PluginContext, proto};

#[derive(Default)]
pub struct RecordingHost {
    pub fired: Mutex<Vec<(String, String)>>,
}

#[astra_plugin_sdk::async_trait]
impl Host for RecordingHost {
    fn plugin_id(&self) -> &str {
        "test"
    }
    async fn fire_trigger(&self, trigger_type: &str, payload_json: &str) -> Result<()> {
        self.fired
            .lock()
            .unwrap()
            .push((trigger_type.into(), payload_json.into()));
        Ok(())
    }
    async fn log(&self, _: &str, _: &str) -> Result<()> {
        Ok(())
    }
    async fn get_config(&self) -> Result<String> {
        Ok("{}".into())
    }
    async fn get_daemon_info(&self) -> Result<proto::PluginDaemonInfoResponse> {
        Ok(Default::default())
    }
    async fn set_variable(&self, _: &str, _: &str, _: &str) -> Result<()> {
        Ok(())
    }
    async fn push_to_ui(&self, _: &str, _: &str) -> Result<()> {
        Ok(())
    }
    async fn send_chat_message(&self, _: &str, _: &str, _: bool) -> Result<ChatStream> {
        bail!("no chat in this test")
    }
    async fn set_theme_contribution(&self, _: proto::PluginThemeContribution) -> Result<()> {
        Ok(())
    }
}

pub fn ctx() -> (PluginContext, Arc<RecordingHost>) {
    let host = Arc::new(RecordingHost::default());
    (PluginContext::new("test", host.clone()), host)
}
