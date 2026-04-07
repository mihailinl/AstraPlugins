# Astra Plugin SDK (TypeScript)

Build plugins for [Astra](https://github.com/astra-assistant) in TypeScript.

## Installation

```bash
npm install @astra/plugin-sdk
```

## Quick Start

```typescript
import { Plugin } from "@astra/plugin-sdk";

class MyPlugin extends Plugin {
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
    return { success: false, error: `Unknown tool: ${name}`, result: "" };
  }
}

new MyPlugin().run();
```

## Capabilities

Override the methods you need:

- **Tools**: `listTools()`, `callTool(name, args)`
- **TTS**: `ttsListVoices()`, `ttsSynthesize(text, voiceId, speed, pitch)`
- **STT**: `sttGetLanguages()`
- **AI Provider**: `aiGetModels()`
- **Actions**: `getActionTypes()`, `executeAction(type, params)`
- **Triggers**: `getTriggerTypes()`
- **Lifecycle**: `onConfigChanged(config)`, `onShutdown()`, `healthCheck()`

## Host Client

Access daemon services from your plugin:

```typescript
class MyPlugin extends Plugin {
  async onConfigChanged(config: Record<string, unknown>) {
    // Log to daemon
    await this.host!.log("info", `Config updated: ${JSON.stringify(config)}`);

    // Fire a trigger
    await this.host!.fireTrigger("my_trigger", JSON.stringify({ key: "value" }));

    // Get daemon info
    const info = await this.host!.getDaemonInfo();
    console.log(`Daemon version: ${info.version}`);
  }
}
```
