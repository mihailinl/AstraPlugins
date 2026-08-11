use astra_plugin_sdk::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
#[serde(default)]
struct DoomConfig {
    scale_mode: String,
}

impl Default for DoomConfig {
    fn default() -> Self {
        Self {
            scale_mode: "fit".into(),
        }
    }
}

#[derive(Default)]
struct DoomPlugin {
    config: Config<DoomConfig>,
}

#[async_trait]
impl PluginCapability for DoomPlugin {
    type Config = DoomConfig;

    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::page("doom-page", "Doom", "doom.js")]
    }

    async fn handle_ui_call(
        &self,
        _ctx: &PluginContext,
        method: &str,
        _params_json: &str,
    ) -> Result<String, ToolError> {
        match method {
            "getConfig" => Ok(serde_json::to_string(&*self.config.get())?),
            _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
        }
    }

    async fn on_config(&self, _ctx: &PluginContext, config: DoomConfig) {
        self.config.store(config);
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(DoomPlugin::default()).await
}
