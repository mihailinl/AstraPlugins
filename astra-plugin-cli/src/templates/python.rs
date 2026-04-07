//! Python plugin project templates.

pub fn generate_plugin_py(name: &str, capabilities: &[&str]) -> String {
    let class_name = name
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

    let mut methods = String::new();

    if capabilities.contains(&"tools") {
        methods.push_str(
            r#"
    async def list_tools(self):
        return [
            {
                "name": "hello",
                "description": "Say hello",
                "parameters_json": '{"type": "object", "properties": {}}',
            }
        ]

    async def call_tool(self, name: str, arguments_json: str):
        if name == "hello":
            return {"success": True, "result": "Hello from the plugin!"}
        return {"success": False, "error": f"Unknown tool: {name}"}
"#,
        );
    }

    if capabilities.contains(&"tts") {
        methods.push_str(
            r#"
    async def tts_list_voices(self):
        return [
            {
                "id": "default",
                "name": "Default Voice",
                "language": "en",
                "gender": "neutral",
            }
        ]

    async def tts_synthesize(self, text: str, voice_id: str, speed: float, pitch: float):
        # TODO: implement TTS synthesis
        raise NotImplementedError("TTS synthesis not yet implemented")
"#,
        );
    }

    if capabilities.contains(&"actions") {
        methods.push_str(
            r#"
    async def get_action_types(self):
        # TODO: define your action types
        return []

    async def execute_action(self, action_type: str, params_json: str):
        # TODO: implement action execution
        return {"success": False, "error": f"Action '{action_type}' not implemented"}
"#,
        );
    }

    if capabilities.contains(&"triggers") {
        methods.push_str(
            r#"
    async def get_trigger_types(self):
        # TODO: define your trigger types
        return []
"#,
        );
    }

    format!(
        r#""""{class_name} — Astra plugin."""

from astra_plugin_sdk import Plugin


class {class_name}(Plugin):
    """Astra plugin: {name}."""
{methods}

if __name__ == "__main__":
    {class_name}().run()
"#
    )
}

pub fn generate_requirements() -> String {
    r#"astra-plugin-sdk
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
"#
    .into()
}

pub fn generate_pyproject(name: &str) -> String {
    let pkg_name = name.replace('-', "_");
    format!(
        r#"[project]
name = "{pkg_name}"
version = "0.1.0"
description = "An Astra plugin"
requires-python = ">=3.10"
dependencies = [
    "astra-plugin-sdk",
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
]
"#
    )
}
