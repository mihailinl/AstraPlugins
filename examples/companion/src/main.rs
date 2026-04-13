use std::sync::Arc;

use astra_plugin_sdk::prelude::*;

struct CompanionCat {
    i18n: Arc<I18n>,
}

impl CompanionCat {
    fn new() -> Self {
        Self {
            i18n: Arc::new(I18n::load(std::path::Path::new("locales"))),
        }
    }
}

#[async_trait::async_trait]
impl PluginCapability for CompanionCat {
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![
            UiContribution::overlay("cat-overlay", "cat.js"),
        ]
    }

    async fn on_language_changed(&self, language: &str) {
        self.i18n.set_language(language);
    }

    async fn handle_ui_call(&self, method: &str, _params_json: &str) -> UiCallResult {
        match method {
            "getRandomMessage" => {
                let nanos = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .subsec_nanos() as usize;
                // Get message count from locale, fall back to key count
                let count = 41; // must match number of msg.N keys in locale files
                let idx = nanos % count;
                let key = format!("msg.{}", idx);
                let msg = self.i18n.t(&key);
                UiCallResult::ok(serde_json::json!({ "message": msg }).to_string())
            }
            _ => UiCallResult::err(format!("Unknown method: {}", method)),
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(CompanionCat::new()).await
}
