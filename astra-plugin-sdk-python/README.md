# Astra Plugin SDK (Python)

Build plugins for [Astra](https://github.com/astra-assistant) in Python.

## Installation

```bash
pip install astra-plugin-sdk
```

## Quick Start

```python
from astra_plugin_sdk import Plugin

class MyPlugin(Plugin):
    async def list_tools(self):
        return [{
            "name": "hello",
            "description": "Say hello",
            "parameters_json": '{"type": "object", "properties": {}}',
        }]

    async def call_tool(self, name, arguments_json):
        if name == "hello":
            return {"success": True, "result": "Hello from the plugin!"}
        return {"success": False, "error": f"Unknown tool: {name}"}

if __name__ == "__main__":
    MyPlugin().run()
```

## Capabilities

Override the methods you need:

- **Tools**: `list_tools()`, `call_tool(name, args)`
- **TTS**: `tts_list_voices()`, `tts_synthesize(text, voice_id, speed, pitch)`
- **STT**: `stt_get_languages()`
- **AI Provider**: `ai_get_models()`
- **Actions**: `get_action_types()`, `execute_action(type, params)`
- **Triggers**: `get_trigger_types()`
- **Lifecycle**: `on_config_changed(config)`, `on_shutdown()`, `health_check()`

## Host Client

Access daemon services from your plugin:

```python
class MyPlugin(Plugin):
    async def on_config_changed(self, config):
        # Log to daemon
        await self.host.log("info", f"Config updated: {config}")

        # Fire a trigger
        await self.host.fire_trigger("my_trigger", '{"key": "value"}')

        # Get daemon info
        info = await self.host.get_daemon_info()
        print(f"Daemon version: {info.version}")
```
