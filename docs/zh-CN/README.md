> **本文档为翻译版本。** 权威来源是 [docs/en](../en/README.md)。如与英文版有出入，以英文版为准。

# Astra 插件文档

插件是一个独立的程序，由 Astra 启动并通过 gRPC 与之通信。它可以为模型提供工具、
提供文本转语音(TTS)或语音转文本(STT)引擎、为命令编辑器添加步骤和触发器、贡献
UI，或者作为一个独立的聊天客户端运行。

这里有两条阅读路径，本页上的每一项都属于其中之一。

## 编写插件

| | |
|---|---|
| [什么是插件](1-orientation/what-is-a-plugin.md) | 十种能力(capability),以及你需要哪一种 |
| [架构](1-orientation/architecture.md) | 进程模型、两个服务、认证握手 |
| [安全模型](1-orientation/security.md) | 签名能证明什么、不能证明什么，以及插件运行所拥有的权限 |
| [平台](1-orientation/platforms.md) | linux-x64 和 windows-x64，各操作系统的路径，构建前置条件 |
| **[快速上手](2-tutorial/getting-started.md)** | **从零到一个可运行的插件。从这里开始。** |
| [Rust SDK](4-sdk/rust.md) · [Python SDK](4-sdk/python.md) · [TypeScript SDK](4-sdk/typescript.md) | 每个各一页，包括该 SDK 目前还做不到的事 |
| [示例](7-examples/README.md) | 本仓库中的十一个插件，各自标明所支持的平台 |

## 发布插件

**发布 = 一次由 GitHub CI 构建并出具证明(attest)的带标签发布(tagged release)，
再加上一次性的一次上架申请，仅此而已。** 把源码推送到 GitHub 不是发布；把一个 zip
发给别人不是发布；请维护者帮你构建也不是发布。注册表(registry)以用户下载并读取的
那份文件的确切摘要(digest)来固定你的插件，并读取 GitHub 的构建证明来确认是哪个
工作流、哪个提交(commit)、哪个仓库产生了这些字节 —— 而在你自己笔记本上构建出的文件，
这两样都没有。

| | |
|---|---|
| **[发布插件](publishing.md)** | **一页讲完整个流程：从空目录到上架插件，每条命令附带其输出。从这里开始。** |
| [安装 CLI](install-cli.md) | 下载预编译的 `astra-plugin` 并验证它，或者从源码构建。不要用 `cargo install` —— 那行不通，这里说明了原因 |

如果你想分阶段了解，有以下三个层级：

1. [用 CI 发布](5-publish/release-with-ci.md) —— 先 `astra-plugin init-ci`，再打标签(tag)。GitHub 会构建并出具证明。
2. [申请上架](5-publish/get-listed.md) —— 一次性提交，仅此一次。此后的发布是零接触的。
3. 用户从 Astra 内部安装，构件(artifact)以摘要固定。

还有另外两种把插件放到机器上的方式。**两者都不是发布。**
两者都面向开发者，两者都有代价，且各自都说明了自己是什么：

- [安装本地文件](5-publish/local-install.md) —— 通过带外方式获得的 `.astraplugin`。四种权限被直接拒绝。
- [侧载(sideload)一个源码目录](5-publish/sideload.md) —— 开发时的循环用法。需要开发者模式，会以你的完整用户账户运行未签名代码。

另请参阅：[版本与弃用策略](versioning.md) · [迁移到 0.6](migration-0.6.md)

## 运行插件

| | |
|---|---|
| [故障排查](6-operate/troubleshooting.md) | 按守护进程和 CLI 实际打印的错误来索引 |
| [日志](6-operate/logs.md) | 各操作系统下日志的位置，以及如何跟踪它们 |
| [性能](6-operate/performance.md) | 超时、启动预算、关闭宽限期、归档限制 |

## 参考手册

参考手册层的大部分内容是从它所描述的代码**生成**的，当签入(checked-in)的页面与
重新生成的结果不一致时，CI 会失败。这是刻意的设计：手写的参考页等于给接口多定义了
一份，而这多出来的一份，永远是错的那一份。

| 页面 | 生成自 |
|---|---|
| [`plugin.toml`](reference/manifest.md) | `astra-plugin-manifest` —— 守护进程用来解析你的清单文件的 crate |
| [CLI](reference/cli.md) | `clap` 的定义，通过运行 `astra-plugin --help` 生成 |
| [协议](reference/protocol.md) | `proto/plugin.proto` |
| [错误](reference/errors.md) | 三个 SDK 中共有的错误分类 |
| [钩子对照表](reference/parity.md) | `spec/hooks.yaml` —— 三个 SDK 中全部 35 个钩子 |
| [权限](3-reference/permissions.md) | 手写: 每个权限授予什么、如何写理由说明 |
| [配置字段](3-reference/config-fields.md) | 手写: 设置界面、`[config]`，以及 TTS/STT 字段钩子 |

面向要实现校验器(verifier)或注册表(registry)的人，而非插件作者的规范性规格说明：
[bundle v2](spec/bundle-v2.md) ·
[registry index](spec/registry-index.md) · [permissions](spec/permissions.md)。

## 语言

英文版为权威版本。它旁边有六份翻译，每一份都是这些页面的逐文件镜像 ——
相同的文件、相同的标题、相同的顺序：

[Deutsch](../de/README.md) · [Español](../es/README.md) · [日本語](../ja/README.md) · [Русский](../ru/README.md) · [Українська](../uk/README.md) · [简体中文](README.md)

CI 检查的是一份翻译的「形」：它是否拥有与 `docs/en` 完全相同的页面，其中每个链接
是否都能解析，以及它的每个代码块是否仍然可以运行 —— 完全相同的代码块只执行一次，
并报告为与英文原版 `identical to`，所以在翻译中发生偏移的代码块会作为独立的一份重新执行。CI 无法检查某句话是否仍然
表达着英文原句的意思。所以一旦出现分歧，以英文为准，每个翻译页面开头都写明了这一点，
对其中任何一页的修正都欢迎提出。

## 本文档始终留意的两件事

**插件没有沙箱化。** 插件是一个以你的身份运行的原生进程，拥有你的文件访问权和网络访问权。
签名回答的问题是*这些字节是谁发布的*；权限回答的问题是*当插件发出请求时守护进程会做什么*。
这两者都不能回答该进程能对你的机器做什么。参见
[安全模型](1-orientation/security.md)。

**信任链已经锚定到委托(delegation)这一层，但还没有贯穿到目录(catalogue)本身。**
根密钥(root key)已经存在，并且双方一致；委托给索引签名密钥的、经根签名的 `trust.json`
现在也已经存在 —— 它在 `astra-root-2026a` 下可验证，并且指名了注册表在构建证明中会
接受的那一个可复用工作流提交(commit)。仍然缺失的是目录本身的签名：`registry/v1/index.json`
和 `revocations.json` 携带的都是 `"signatures": []`，因此默认构建没有任何可校验的内容，
会安全失败(fail closed),并把所有目录都归类为未签名。这一点写在
[`spec/registry-index.md` §0.1](spec/registry-index.md) 中，并在所有相关之处反复重申，
而不是被悄悄含糊带过。
