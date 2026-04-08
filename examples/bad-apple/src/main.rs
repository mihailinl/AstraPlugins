use astra_plugin_sdk::prelude::*;
use std::sync::Mutex;

struct BadApple {
    config: Mutex<BadAppleConfig>,
}

struct BadAppleConfig {
    render_mode: String,
    opacity: f64,
    charset: String,
    color: String,
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

const ICON_SVG: &str = r#"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>"#;

#[async_trait::async_trait]
impl PluginCapability for BadApple {
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![
            UiContribution::effect("bad-apple-bg.js")
                .with_id("bad-apple-bg"),
            UiContribution::page("bad-apple-page", "Bad Apple", "bad-apple-player.js")
                .with_icon_svg(ICON_SVG),
        ]
    }

    async fn handle_ui_call(&self, method: &str, _params_json: &str) -> UiCallResult {
        match method {
            "getConfig" => {
                let cfg = self.config.lock().unwrap();
                UiCallResult::ok(
                    serde_json::json!({
                        "render_mode": cfg.render_mode,
                        "opacity": cfg.opacity,
                        "charset": cfg.charset,
                        "color": cfg.color,
                        "loop": cfg.do_loop,
                    })
                    .to_string(),
                )
            }
            _ => UiCallResult::err(format!("Unknown method: {}", method)),
        }
    }

    async fn on_config_changed(&self, config_json: &str) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(config_json) {
            let mut cfg = self.config.lock().unwrap();
            if let Some(s) = v.get("render_mode").and_then(|s| s.as_str()) {
                cfg.render_mode = s.to_string();
            }
            if let Some(n) = v.get("opacity").and_then(|n| n.as_f64()) {
                cfg.opacity = n;
            }
            if let Some(s) = v.get("charset").and_then(|s| s.as_str()) {
                cfg.charset = s.to_string();
            }
            if let Some(s) = v.get("color").and_then(|s| s.as_str()) {
                cfg.color = s.to_string();
            }
            if let Some(b) = v.get("loop").and_then(|b| b.as_bool()) {
                cfg.do_loop = b;
            }
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(BadApple {
        config: Mutex::new(BadAppleConfig::default()),
    })
    .await
}
