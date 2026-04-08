use astra_plugin_sdk::prelude::*;
use std::sync::Mutex;

struct DoomPlugin {
    config: Mutex<DoomConfig>,
}

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

#[async_trait::async_trait]
impl PluginCapability for DoomPlugin {
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::page("doom-page", "Doom", "doom.js")]
    }

    async fn handle_ui_call(&self, method: &str, _params_json: &str) -> UiCallResult {
        match method {
            "getConfig" => {
                let cfg = self.config.lock().unwrap();
                UiCallResult::ok(
                    serde_json::json!({ "scale_mode": cfg.scale_mode }).to_string(),
                )
            }
            _ => UiCallResult::err(format!("Unknown method: {}", method)),
        }
    }

    async fn on_config_changed(&self, config_json: &str) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(config_json) {
            let mut cfg = self.config.lock().unwrap();
            if let Some(s) = v.get("scale_mode").and_then(|s| s.as_str()) {
                cfg.scale_mode = s.to_string();
            }
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(DoomPlugin {
        config: Mutex::new(DoomConfig::default()),
    })
    .await
}
