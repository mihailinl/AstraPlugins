use astra_plugin_sdk::prelude::*;

struct CompanionCat;

const MESSAGES: &[&str] = &[
    "Meow!",
    "I'm hungry...",
    "Pet me!",
    "*purrs*",
    "Did you know cats sleep 16 hours a day?",
    "I knocked your code off the table",
    "Mrrp?",
    "Have you tried turning it off and on again?",
    "*stares at cursor*",
    "Feed me or I delete main.rs",
    "*yawn*",
    "Why is the red dot moving?",
    "I sit on keyboard now.",
    "Error 404: Treats not found",
    "*knocks glass off desk*",
];

#[async_trait::async_trait]
impl PluginCapability for CompanionCat {
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![
            UiContribution::overlay("cat-overlay", "cat.html")
                .with_size(180, 220),
        ]
    }

    async fn handle_ui_call(&self, method: &str, _params_json: &str) -> UiCallResult {
        match method {
            "getRandomMessage" => {
                let nanos = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .subsec_nanos() as usize;
                let msg = MESSAGES[nanos % MESSAGES.len()];
                UiCallResult::ok(serde_json::json!({ "message": msg }).to_string())
            }
            _ => UiCallResult::err(format!("Unknown method: {}", method)),
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(CompanionCat).await
}
