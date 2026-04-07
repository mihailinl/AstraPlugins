//! TypeScript plugin project templates.

pub fn generate_index_ts(name: &str, capabilities: &[&str]) -> String {
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
  async listTools() {
    return [
      {
        name: "hello",
        description: "Say hello",
        parametersJson: JSON.stringify({ type: "object", properties: {} }),
      },
    ];
  }

  async callTool(name: string, argumentsJson: string) {
    if (name === "hello") {
      return { success: true, result: "Hello from the plugin!" };
    }
    return { success: false, error: `Unknown tool: ${name}` };
  }
"#,
        );
    }

    if capabilities.contains(&"tts") {
        methods.push_str(
            r#"
  async ttsListVoices() {
    return [
      {
        id: "default",
        name: "Default Voice",
        language: "en",
        gender: "neutral",
      },
    ];
  }

  async ttsSynthesize(text: string, voiceId: string, speed: number, pitch: number) {
    // TODO: implement TTS synthesis
    throw new Error("TTS synthesis not yet implemented");
  }
"#,
        );
    }

    if capabilities.contains(&"actions") {
        methods.push_str(
            r#"
  async getActionTypes() {
    // TODO: define your action types
    return [];
  }

  async executeAction(actionType: string, paramsJson: string) {
    // TODO: implement action execution
    return { success: false, error: `Action '${actionType}' not implemented` };
  }
"#,
        );
    }

    if capabilities.contains(&"triggers") {
        methods.push_str(
            r#"
  async getTriggerTypes() {
    // TODO: define your trigger types
    return [];
  }
"#,
        );
    }

    format!(
        r#"import {{ Plugin }} from "@astra/plugin-sdk";

class {class_name} extends Plugin {{
{methods}}}

new {class_name}().run();
"#
    )
}

pub fn generate_package_json(name: &str) -> String {
    format!(
        r#"{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "An Astra plugin",
  "main": "dist/index.js",
  "scripts": {{
    "build": "esbuild src/index.ts --bundle --platform=node --outfile=dist/index.js",
    "dev": "tsx src/index.ts"
  }},
  "dependencies": {{
    "@astra/plugin-sdk": "^0.1.0",
    "@grpc/grpc-js": "^1.10.0",
    "@grpc/proto-loader": "^0.7.0"
  }},
  "devDependencies": {{
    "esbuild": "^0.20.0",
    "tsx": "^4.0.0",
    "typescript": "^5.4.0"
  }}
}}
"#
    )
}

pub fn generate_tsconfig() -> String {
    r#"{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "esModuleInterop": true,
    "strict": true,
    "outDir": "dist",
    "rootDir": "src",
    "declaration": true
  },
  "include": ["src"]
}
"#
    .into()
}
