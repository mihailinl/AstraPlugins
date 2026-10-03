> **本文档为翻译版本。** 权威来源是 [docs/en](../en/wakeword-plugins.md)。如与英文版有出入，以英文版为准。

# 唤醒词插件

唤醒词插件在其 `plugin.toml` 的 `[capabilities]` 部分声明 `wakeword = true`。
Astra 会在 **语音 → Wake Word** 下列出具备该能力的已安装插件。插件被卸载后，
这一选择及其设置随之消失。插件不需要单独的页面，也不需要 UI 贡献。

## 创建新的检测器

使用当前的 CLI 和一个全新的输出目录：

<!-- doctest: cli -->
```bash
astra-plugin new my-wakeword --lang rust --template blank --capabilities wakeword --output ./my-wakeword
```

`--lang` 也可以是 `python` 或 `typescript`。目前还没有唤醒词模板。Rust 的 blank
脚手架带有一个无关的 `hello` 工具及其测试：把两者都替换掉。除非插件确实还提供
其他功能，否则让 `wakeword = true` 成为唯一的能力。用 `astra-plugin check` 可以
发现清单与编译出的二进制之间的不一致。

即使插件只声明了 `wakeword`，守护进程也会通过 `CallFromUi` 发送下面的三个调用。
这是对传输通道的复用，不需要 `ui_contributions`、iframe 或 `push_to_ui`。通用的
钩子表把 `CallFromUi` 列在 UI 下，是因为那是它最初的用途。

在 Rust 中，实现 SDK 的 `handle_ui_call(&self, ctx: &PluginContext,
method: &str, params_json: &str) -> Result<String, ToolError>` 钩子，或者使用
`#[ui_call]` 方法(带连字符的名字用 `#[ui_call(name = "process-audio")]` 和
`#[ui_call(name = "reset-audio")]`)；每个 `#[ui_call]` 方法都需要一条 `///` 文档
注释，否则宏会拒绝编译。在 impl 块上加上
`#[astra::plugin(capabilities = "wakeword")]`(上面的脚手架已经这样做了)：否则
从 `#[ui_call]` 自动推断会声明 `ui_contributions`，与清单不一致。把 `status`、
`reset-audio` 和 `process-audio` 路由到同一个检测器实例，并让它的帧缓冲区在
调用之间保留。按下面的响应形状返回 JSON 字符串。
在 Python 中使用 SDK 的 `@ui_call` 处理函数；在 TypeScript 中使用带三个方法名的
`ui: { contributions: [], onCall: { ... } }`。
这些处理函数不会创建可见的 UI 页面。
入口点、配置访问和生命周期请参阅 [Rust](4-sdk/rust.md)、
[Python](4-sdk/python.md) 和 [TypeScript](4-sdk/typescript.md) 的 SDK 指南。

插件通过现有的 `[config]` JSON Schema 提供它的设置。只有在选中该插件时，Astra
才会在语音页面显示这些字段，并通过 `UpdatePluginConfig` 保存它们。支持字符串、
数字、布尔和枚举属性。带 `"format": "password"` 的字符串使用密码框；
`"format": "file"`(或 `"x-astra-field-type": "file_picker"`)提供本地文件选择器。
`"x-astra-field-type": "slider"` 和 `"textarea"` 分别为数字和字符串属性选用这两种
控件。配置的路径由插件自己读取；Astra 不规定关键词模型的格式。

协议 1 为三个方法使用经过认证的 `CallFromUi` 请求/响应通道。这是守护进程内部的
调用，不会创建 iframe 或页面。

| 方法 | 请求 JSON | 响应 JSON |
|---|---|---|
| `status` | `{}` | `{"ready": true}` 或 `{"ready": false, "message": "…"}` |
| `process-audio` | `{"pcm_base64": "…"}` | `{"detected": false}` 或 `{"detected": true}` |
| `reset-audio` | `{}` | `{}` |

`pcm_base64` 包含 16 kHz 单声道、有符号 16 位、小端序的 PCM。Astra 每次调用发送
100 ms(1600 个采样)。如果检测器的帧长不同，插件必须在调用之间保留采样。当 Astra
重置唤醒门时，`reset-audio` 会丢弃这些保留的音频以及模型中尚未完成的检测状态。
先解码 Base64，拒绝格式错误或长度为奇数的 PCM，把每个小端字节对转换为 `i16`，
再按顺序把采样送入检测器。不要把每个 100 ms 的块当成一句完整的话。每次调用的
期限为两秒；音频循环使用有界队列，从不等待插件。
`astra-plugin test` 会调用这三个方法并检查它们 JSON 响应的形状，其中包括在插件
可能尚未配置时发送的全零音频块。这个测试并不验证所选的关键词能被检测到。交付前，
加载一个有效的模型并确认 `status.ready = true`；把唤醒短语的几段录音分散在多次
100 ms 调用中回放；再把静音、背景噪声和普通说话作为反例回放。确认 `reset-audio`
能清除说了一半的短语，并且重置后检测仍然有效。然后安装或侧载该插件，在
**语音 → Wake Word** 中选中它，确认 Astra 开始收听并会被该短语唤醒。未配置的模型
应当返回 `ready: false` 并附带有用的消息。

Astra 在开始收听前会检查 `status.ready`。如果所选插件不存在、已停止或尚未就绪，
收听会以失败关闭(fail closed)的方式拒绝启动，而不是悄悄变成持续转写。运行时的
选择使用 `voice.wake_word_mode = "plugin__<id>"`，与 STT 和 TTS 插件的提供者 ID
一样，把插件 ID 中的连字符替换为下划线。
只有在检测器及其配置的模型能够处理音频之后，才返回 `ready: true`；仅仅存在一个
文件路径是不够的。
