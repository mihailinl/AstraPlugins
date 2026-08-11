use astra_plugin_sdk::prelude::*;

struct CompanionCat {
    i18n: I18n,
}

impl Default for CompanionCat {
    fn default() -> Self {
        Self {
            i18n: I18n::load(std::path::Path::new("locales")),
        }
    }
}

#[async_trait]
impl PluginCapability for CompanionCat {
    /// The cat has no settings — that is the whole of `NoConfig`.
    type Config = NoConfig;

    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::overlay("cat-overlay", "cat.js")]
    }

    async fn on_language_changed(&self, _ctx: &PluginContext, language: &str) {
        self.i18n.set_language(language);
    }

    async fn handle_ui_call(
        &self,
        _ctx: &PluginContext,
        method: &str,
        _params_json: &str,
    ) -> Result<String, ToolError> {
        match method {
            "getRandomMessage" => {
                let nanos = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .subsec_nanos() as usize;
                // Must match the number of msg.N keys in the locale files.
                let key = format!("msg.{}", nanos % 41);
                Ok(serde_json::json!({ "message": self.i18n.t(&key) }).to_string())
            }
            _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(CompanionCat::default()).await
}
