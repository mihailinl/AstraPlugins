# Astra 插件开发

使用 Rust、Python 或 TypeScript 为 [Astra](https://github.com/Stella)（AI 驱动的数字助手）构建插件。

插件是由 Astra 作为边车（sidecar）进程启动的独立程序。它们通过 gRPC 与守护进程通信，可以暴露 AI 工具、提供 TTS/STT 后端、向命令图（Command Graph）贡献自定义操作与触发器、注入 UI 面板，或作为完整的守护进程客户端运行。

## 目录

| 文档 | 内容简介 |
| --- | --- |
| [快速入门](getting-started.md) | 安装 CLI，生成你的第一个插件，在开发模式下运行，构建可分发的包 |
| [CLI 参考](cli.md) | 每个 `astra-plugin` 子命令的标志、行为和退出码 |
| [Rust SDK](sdk-rust.md) | 基于 trait 的 API（`PluginCapability`）、字段构建器、`HostClient`、`DaemonClient` |
| [Python SDK](sdk-python.md) | 装饰器 API（`@tool`、`@action`、`@trigger`）、基于类型提示的自动 schema、UV 集成 |
| [TypeScript SDK](sdk-typescript.md) | 基于类的 API、能力自动发现、`@grpc/grpc-js` 运行时 |
| [清单](manifest.md) | `plugin.toml` 参考 —— 每个小节和字段 |
| [能力](capabilities.md) | 全部 9 种能力、每个 SDK 的 API、proto RPC |
| [发布](publishing.md) | `.astraplugin` 包格式、Ed25519 签名、侧载 |

## 架构概览

```
┌────────────────────────┐     gRPC     ┌────────────────────────┐
│        Astra           │◀────────────▶│        Plugin          │
│        daemon          │   localhost  │      (sidecar)         │
│                        │              │                        │
│ PluginHostService ─────┼────────────▶│ HostClient             │
│                        │              │                        │
│ plugin-capability ◀────┼──────────────│ PluginCapability       │
│   service client       │              │   service              │
└────────────────────────┘              └────────────────────────┘
```

- 守护进程将每个插件作为独立进程启动，在命令行上传入 `--daemon-addr`、`--plugin-id`，并可选传入 `--auth-token`。
- 插件在随机本地端口上启动一个 gRPC 服务器，连回守护进程的 `PluginHostService`，并进行**注册** —— 声明它实现了哪些能力。
- 注册完成后，守护进程会调用插件的 `PluginCapabilityService` 进行工具调用、操作执行、TTS 及生命周期事件。
- 插件使用 `HostClient` 进行日志记录、触发触发器、读取自身配置、设置变量，或向其 UI iframe 推送事件。具备 client 能力的插件还会额外获得一个完整的 `DaemonClient`，可访问 Chat、Voice、Command、Media、Monitor 和 Config 服务。

## 选择 SDK

| 考量 | Rust | Python | TypeScript |
| --- | --- | --- | --- |
| 启动延迟 | ~10 ms（原生二进制） | ~300 ms（解释器 + grpcio 导入） | ~100 ms（Node 冷启动） |
| 内存占用 | 最低 | 最高 | 中等 |
| 包体积 | ~5–10 MB 二进制 | ~100 KB 源码 + 守护进程管理的 venv | ~200 KB 包体（esbuild） |
| 适用场景 | 性能敏感、系统集成、TTS/STT 提供者 | AI 工具、数据处理、机器学习库 | Web API、大量 JSON 处理、UI 集成 |
| 类型安全 | 完整（编译期） | 通过类型提示可选启用（运行时生成 schema） | 完整（编译期） |

三种 SDK 均为一等公民 —— 每种能力在每个 SDK 中都可用。选择你希望引入其库生态的那一个即可。

## 下一步

前往[快速入门](getting-started.md)，体验 5 分钟上手教程。
