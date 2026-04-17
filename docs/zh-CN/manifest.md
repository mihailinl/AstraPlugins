# `plugin.toml` 参考

每个插件都在其项目根目录下的 `plugin.toml` 清单中声明自身。此文件告知守护进程如何启动该插件、它实现了哪些能力，以及它接受何种配置。

## 完整示例

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"
description = "Word count, case conversion, regex matching"
author = "Astra Team"
license = "MIT"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
tts = false
stt = false
ai_provider = false
client = false
ui_contributions = false
event_handlers = false

[config]
schema = """
{
  "type": "object",
  "properties": {
    "max_text_length": {
      "type": "number",
      "default": 10000,
      "title": "Max Text Length"
    }
  }
}
"""
```

## `[plugin]` —— 元数据

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 小写字母、数字与连字符。唯一标识该插件。 |
| `name` | string | 是 | 在 Plugins UI 中显示的名称。 |
| `version` | string | 是 | 语义化版本（`X.Y.Z`）。用于升级检测。 |
| `description` | string | 建议 | 简短描述。在 Plugins UI 中显示。 |
| `author` | string | 建议 | 作者或组织名称。 |
| `license` | string | 建议 | SPDX 许可标识（`MIT`、`Apache-2.0` 等）。 |

## `[entry]` —— 如何启动插件

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `command` | string | 是 | 要调用的可执行文件。对 Rust，这是已编译的二进制路径；对 Python 为 `"python"`；对 TypeScript 为 `"node"`。 |
| `args` | string 数组 | 否 | 在 `--daemon-addr`、`--plugin-id`、`--auth-token` 之前追加的参数。典型值：Python 为 `["-m", "src.plugin"]`，Node 为 `["dist/index.js"]`。 |
| `runtimes` | string 数组 | 否 | 给守护进程的提示。支持：`"python"`、`"node"`、`"rust"`。Python/Node 插件应始终设置该项，使守护进程能够准备运行时（例如为 Python 创建 `uv` venv）。 |

守护进程在每次启动时都会追加 `--daemon-addr <addr> --plugin-id <id>`，并对 client 插件可选追加 `--auth-token <token>`。

## `[capabilities]` —— 插件实现了哪些能力

每个字段为布尔值，默认为 `false`。仅将你代码实际处理的能力设置为 `true` —— 守护进程据此分配资源，并决定是否在相关 UI 中呈现该插件（例如将其 voices 加入 TTS 选择器）。

| 能力 | 用途 |
| --- | --- |
| `tools` | 可被聊天模型调用的 AI 工具。 |
| `tts` | 文本转语音 voice 提供者。 |
| `stt` | 语音转文本语言提供者。 |
| `ai_provider` | 可替代的 AI 补全后端。 |
| `actions` | 命令图中的自定义操作类型。 |
| `triggers` | 命令图中的自定义触发器类型。 |
| `client` | 完整的守护进程客户端（需要会话令牌）。 |
| `ui_contributions` | UI 页面、覆盖层、效果层、插槽注入。 |
| `event_handlers` | 订阅守护进程事件流。 |

每种能力的完整行为请参见[能力](capabilities.md)。

## `[config]` —— 面向用户的设置

```toml
[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "Token for the remote service",
      "x-secret": true
    },
    "timeout_ms": {
      "type": "number",
      "default": 5000,
      "minimum": 100,
      "maximum": 60000,
      "title": "Timeout (ms)"
    },
    "mode": {
      "type": "string",
      "enum": ["fast", "accurate"],
      "default": "fast",
      "title": "Mode"
    }
  },
  "required": ["api_key"]
}
"""
```

规则：

- `schema` 是一个 **JSON Schema 字符串**。根节点必须为 `"type": "object"`。
- 守护进程会将该 schema 渲染为插件设置页面上的表单。
- `title` 用作字段标签；`description` 作为帮助文本显示。
- `default` 提供初始值。
- `x-secret: true` 会在 UI 中遮蔽该值，并以加密方式存储。
- `enum` 渲染为下拉框。
- `required` 数组标记必填字段。
- 当用户更新设置时，守护进程会以新的 JSON 数据调用 `OnConfigChanged`。

## 非 schema TOML 字段

插件可以添加任意顶层小节，守护进程会忽略它们 —— 对工具链有帮助。CLI 会对未知字段发出警告，但不会拒绝它们。

## 清单本地化

你可以在插件包内随附 `locales/<lang>.json` 文件，用于翻译面向用户的字符串（`name`、`description`、action 标签、字段标签等）。在代码中使用每个 SDK 的 `I18n` 辅助工具读取它们。只有清单中的**文本**会被本地化 —— 键名、ID 和枚举值保持不变。

## 校验清单

```bash
astra-plugin validate
```

检查项：

- 存在必填字段（`plugin.id`、`plugin.name`、`plugin.version`、`entry.command`）。
- `plugin.id` 匹配小写字母、数字与连字符。
- `plugin.version` 匹配 SemVer（`X.Y.Z`）。
- 至少启用了一项能力。
- `[config].schema` 能解析为 JSON，且根节点为 `"type": "object"`。
- 元数据（description、author）存在。

参见 [CLI 参考 → validate](cli.md#astra-plugin-validate)。
