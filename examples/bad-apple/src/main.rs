use astra_plugin_sdk::prelude::*;
use serde::{Deserialize, Serialize};

/// Everything bad-apple can be configured with.
///
/// This declaration plus the two-line `on_config` below replaces the twenty
/// lines of `v.get("opacity").and_then(|n| n.as_f64())` this plugin used to
/// carry — one arm per field, each silently skipping a field of the wrong type.
/// `#[serde(default)]` means a config missing a key keeps that key's default
/// instead of failing the whole parse.
#[derive(Serialize, Deserialize)]
#[serde(default)]
struct BadAppleConfig {
    render_mode: String,
    opacity: f64,
    charset: String,
    color: String,
    #[serde(rename = "loop")]
    do_loop: bool,
}

impl Default for BadAppleConfig {
    fn default() -> Self {
        Self {
            render_mode: "ascii".into(),
            opacity: 0.15,
            charset: "blocks".into(),
            color: "mono".into(),
            do_loop: true,
        }
    }
}

#[derive(Default)]
struct BadApple {
    config: Config<BadAppleConfig>,
}

#[async_trait]
impl PluginCapability for BadApple {
    type Config = BadAppleConfig;

    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::effect("bad-apple-bg.js").with_id("bad-apple-bg")]
    }

    async fn handle_ui_call(
        &self,
        _ctx: &PluginContext,
        method: &str,
        _params_json: &str,
    ) -> Result<String, ToolError> {
        match method {
            // The effect script gets the same struct the daemon parsed, so
            // there is no second hand-written JSON object to keep in sync with
            // the first.
            "getConfig" => Ok(serde_json::to_string(&*self.config.get())?),
            _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
        }
    }

    async fn on_config(&self, _ctx: &PluginContext, config: BadAppleConfig) {
        self.config.store(config);
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(BadApple::default()).await
}
