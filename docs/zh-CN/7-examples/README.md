> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/7-examples/README.md)。如与英文版有出入，以英文版为准。

# 示例

[`examples/`](../../../examples/) 中有十一个插件，全部都已移植到当前
的 SDK，也全部都在 CI 中被构建。找到一个做的事情和你想做的相符的，
读一读，然后从脚手架开始，而不是从这个示例本身开始 —— 脚手架里不带
任何你还得删掉的示例专属内容。

下面每一项的内容都读取自该插件自己的 `plugin.toml`。

## 最值得先读的几个

| | 语言 | 能力 | 权限 | 为什么读这个 |
|---|---|---|---|---|
| [`dice-roller`](../../../examples/dice-roller/) | Rust | `tools`、`actions`、`triggers` | `fire_trigger` | 参考实现插件。三种能力，一种权限，还有一套测试套件展示了每一项是如何被测试的 |
| [`json-tools`](../../../examples/json-tools/) | TypeScript | `tools`、`actions`、`triggers` | `set_variable` | 用 TypeScript 实现的同一种形态，也是测试深入到传输层的那个示例 |
| [`text-utils`](../../../examples/text-utils/) | Python | `tools`、`actions`、`triggers` | `fire_trigger` | 用 Python 实现的同一种形态 |

这三个是刻意用三种语言实现的同一个插件。如果你正在选语言，把这三个都
读一遍，挑一个你想从中调取库的生态系统 —— 每一种能力在每一个 SDK 里
都是可用的。

## 语音提供者

| | 语言 | 能力 | 为什么读这个 |
|---|---|---|---|
| [`tone-tts`](../../../examples/tone-tts/) | Rust | `tts` | 一个用蜂鸣声"说话"的文本转语音提供者。这是一个接线测试，不是一个真正的语音 |
| [`mock-stt`](../../../examples/mock-stt/) | Rust | `stt` | 返回一段描述所收到音频的确定性转写文本。相当于去掉了识别器的双向流(bidi stream) |
| [`echo-stt`](../../../examples/echo-stt/) | Rust | `stt` | 不转写任何内容，而是通过插件进程把你的麦克风原样播放回来。用来听清守护进程实际发给你的是什么 |

`tone-tts` 和 `mock-stt` 是一致性测试(conformance)job 在每次 CI 运行
时都会驱动的四个插件中的两个，恰恰因为它们行使了其他任何示例都没有
覆盖到的钩子。

## UI 与 `dom_access`

这些插件在 Astra 窗口内部运行代码。它们正是
[侧载(sideload)没有权限上限](../5-publish/sideload.md)的原因：
`dom_access` 没法用别的方式开发出来。

| | 语言 | 能力 | 为什么读这个 |
|---|---|---|---|
| [`companion`](../../../examples/companion/) | Rust | `ui_contributions`、`dom_access` | 一只在窗口里飞来飞去说话的猫。最小的完整 UI 贡献 |
| [`bad-apple`](../../../examples/bad-apple/) | Rust | `ui_contributions`、`dom_access` | 四种渲染模式下的《Bad Apple!!》动画。自带帧数据；参见它的 `SETUP.md` |
| [`doom`](../../../examples/doom/) | Rust | `ui_contributions`、`dom_access` | 一个运行 WebAssembly 引擎的 Doom 页面。一个 UI 贡献所能达到的最极端形态 |

`companion` 是一致性测试 job 为 `ui_contributions` 驱动的第四个插件。

## 客户端

一个 `client` 类型的插件是一个独立的聊天前端 —— 有自己的会话，有自己
的界面。这是一种高风险能力，对于
[本地导入的文件](../5-publish/local-install.md)会被直接拒绝。

> **这两个示例都跑在守护进程前面。** 客户端路径中守护进程那一侧的部分
> 还没有构建出来：每个插件都被注册为 `ClientType::PluginClient`，认证
> 拦截器会拒绝这个身份访问 `/astra.PluginHostService/` 之外的任何
> gRPC 路径。所以这两个示例所依据编写的那个 `DaemonClient`，在每一次
> 调用时都会返回 `permission_denied`。请把它们当作客户端插件的形态来
> 读 —— 界面、事件流、I18n —— 而不是当作今天就能端到端运行的东西。
> 参见
> [Rust SDK 的 `Daemon` 一节](../4-sdk/rust.md#daemon-sdk-中存在但会被守护进程拒绝)。

| | 语言 | 能力 | 为什么读这个 |
|---|---|---|---|
| [`telegram-client`](../../../examples/telegram-client/) | Rust | `client` | 每一个 Astra 对话都会变成一个 Telegram 话题，带有流式回复 |
| [`web-chat`](../../../examples/web-chat/) | Rust | `client` | 一个和 Astra 对话的浏览器窗口。用来观察多客户端同步是怎么发生的 |

## 平台

十一个示例中没有一个声明了 `[platform]` 段，这意味着守护进程会认为
每一个都在任何地方兼容 —— 对那两个解释型的示例来说这是对的，但一个
*已发布*的原生插件应该收紧这一点。参见
[平台](../1-orientation/platforms.md)。

| 语言 | 一次发布会构建出什么 |
|---|---|
| Rust（九个） | `linux-x64` **和** `windows-x64`，各一个包 |
| TypeScript（`json-tools`） | 一个 `noarch` 包 |
| Python（`text-utils`） | 一个 `noarch` 包 |

`doom` 和 `bad-apple` 还额外携带了数据 —— 一个 WebAssembly 引擎、
几兆字节的帧数据 —— 它们各自的 `SETUP.md` 说明了这些数据来自哪里，
以及如何重新生成它们。

## 它们各自被什么测试覆盖

| 层级 | 运行了什么 | 涉及哪些示例 |
|---|---|---|
| 单元测试 | SDK 的进程内测试工具，在各示例自己的测试中 | `dice-roller`、`mock-stt`、`text-utils`、`json-tools` |
| 构建 | 每次 CI 运行都会构建全部示例 | 全部十一个 |
| 一致性测试 | `astra-plugin test` 针对一个模拟守护进程启动真实进程，驱动其能力所隐含的每一个钩子 | `dice-roller`、`mock-stt`、`tone-tts`、`companion` |

一致性测试的这个集合是为了覆盖钩子表而挑选的，不是为了多样性 ——
工具/动作/触发器、STT 的双向流、TTS，以及 UI 贡献。**`ai_provider`
没有对应示例，因此没有被覆盖**，这一点值得明说出来：一个没有人点名
的覆盖缺口，会变成一个人人都以为已经填上的缺口。

Python 和 TypeScript 的示例目前还不在一致性测试 job 里，因为它们的
SDK 尚未发布，而一次针对半安装状态 SDK 的一致性测试运行，报告出来的
会是安装过程本身的问题，而不是插件的问题。`astra-plugin test` 驱动
的是一个进程，并不关心它是用哪种语言写的，所以等这些 SDK 发布的那天，
它们就会加入这个 job。

## 运行一个示例

<!-- doctest: cli -->
```bash
cd examples/dice-roller
astra-plugin check --strict
astra-plugin test
astra-plugin dev
```

`dev` 需要一个正在运行的 Astra 和开发者模式 —— 先阅读
[这需要付出什么代价](../5-publish/sideload.md)。
