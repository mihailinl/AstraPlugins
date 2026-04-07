//! Rust plugin project templates.

pub fn generate_cargo_toml(name: &str) -> String {
    let crate_name = name.replace('-', "_");
    format!(
        r#"[package]
name = "{crate_name}"
version = "0.1.0"
edition = "2024"

[dependencies]
astra-plugin-sdk = {{ git = "https://github.com/astra-assistant/astra-plugin-sdk" }}
tokio = {{ version = "1", features = ["full"] }}
serde = {{ version = "1", features = ["derive"] }}
serde_json = "1"
anyhow = "1"
async-trait = "0.1"
"#
    )
}


pub fn generate_main_rs(name: &str, capabilities: &[&str]) -> String {
    let struct_name = name
        .split('-')
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().to_string() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join("");

    let mut trait_methods = String::new();

    if capabilities.contains(&"tools") {
        trait_methods.push_str(&format!(
            r##"
    async fn list_tools(&self) -> Vec<ToolDef> {{
        vec![ToolDef {{
            name: "hello".into(),
            description: "Say hello".into(),
            parameters_json: r#"{{"type": "object", "properties": {{}}}}"#.into(),
        }}]
    }}

    async fn call_tool(&self, name: &str, _arguments_json: &str) -> ToolResult {{
        match name {{
            "hello" => ToolResult::ok("Hello from the plugin!"),
            _ => ToolResult::err(format!("Unknown tool: {{name}}")),
        }}
    }}
"##
        ));
    }

    if capabilities.contains(&"tts") {
        trait_methods.push_str(&format!(
            r##"
    async fn tts_voices(&self) -> Vec<VoiceInfo> {{
        vec![VoiceInfo {{
            id: "default".into(),
            name: "Default Voice".into(),
            language: "en".into(),
            gender: "neutral".into(),
            preview_url: String::new(),
        }}]
    }}

    async fn tts_synthesize(
        &self,
        text: &str,
        _voice_id: &str,
        _speed: f32,
        _pitch: f32,
    ) -> anyhow::Result<AudioData> {{
        // TODO: implement TTS synthesis
        anyhow::bail!("TTS synthesis not yet implemented for: {{text}}")
    }}
"##
        ));
    }

    if capabilities.contains(&"actions") {
        trait_methods.push_str(&format!(
            r##"
    async fn action_types(&self) -> Vec<ActionTypeDef> {{
        // TODO: define your action types
        vec![]
    }}

    async fn execute_action(&self, action_type: &str, params_json: &str) -> ActionResult {{
        // TODO: implement action execution
        ActionResult::err(format!("Action '{{action_type}}' not implemented"))
    }}
"##
        ));
    }

    if capabilities.contains(&"triggers") {
        trait_methods.push_str(&format!(
            r##"
    async fn trigger_types(&self) -> Vec<TriggerTypeDef> {{
        // TODO: define your trigger types
        vec![]
    }}
"##
        ));
    }

    format!(
        r#"use astra_plugin_sdk::prelude::*;

struct {struct_name};

#[async_trait]
impl PluginCapability for {struct_name} {{{trait_methods}}}

#[tokio::main]
async fn main() {{
    astra_plugin_sdk::run({struct_name}).await.unwrap();
}}
"#
    )
}
