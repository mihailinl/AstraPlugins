# 快速入门

一个 5 分钟上手教程：安装 CLI、生成一个 Rust tools 插件、在开发模式下运行，并构建可分发的 `.astraplugin` 包。

## 先决条件

- 在 `127.0.0.1:50051`（默认 gRPC 端口）运行的 **Astra 守护进程**。
- **Rust** 1.75+（用于 Rust 插件，或从源码安装 CLI）。
- 可选：若选择相应 SDK，则需要 **Python** 3.10+ 或 **Node.js** 20+。

## 1. 安装 CLI

`astra-plugin` CLI 用于创建、运行、构建、校验和签名插件。从仓库进行安装：

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

验证：

```bash
astra-plugin --version
```

## 2. 生成插件项目

```bash
astra-plugin create hello-world --lang rust --capabilities tools
cd hello-world
```

CLI 接受 `--lang rust|python|ts` 以及以逗号分隔的 `--capabilities` 列表。完整选项请参见 [CLI 参考](cli.md)。

生成的 Rust 项目包含：

```
hello-world/
├── Cargo.toml          # Depends on astra-plugin-sdk
├── plugin.toml         # Manifest (id, name, entry, capabilities)
├── src/main.rs         # PluginCapability impl with a stub tool
├── proto/plugin.proto  # Copy of the plugin protocol
├── .gitignore
└── README.md
```

打开 `src/main.rs`，给你的工具加上有用的实现：

```rust
use astra_plugin_sdk::prelude::*;

struct HelloWorld;

#[async_trait]
impl PluginCapability for HelloWorld {
    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![ToolDef {
            name: "greet".into(),
            description: "Return a greeting for the given name".into(),
            parameters_json: r#"{
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }"#.into(),
        }]
    }

    async fn call_tool(&self, _name: &str, arguments_json: &str) -> ToolResult {
        let args: serde_json::Value = serde_json::from_str(arguments_json)
            .unwrap_or_default();
        let who = args.get("name").and_then(|v| v.as_str()).unwrap_or("world");
        ToolResult::ok(format!("Hello, {who}!"))
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(HelloWorld).await
}
```

## 3. 以开发模式运行

```bash
astra-plugin dev
```

该命令会监视插件目录，在文件变更时重新构建，并重启进程，同时重新连接至 `127.0.0.1:50051` 上的守护进程。打开 Astra 的聊天窗口，输入 "greet Ada" —— 守护进程会将该工具调用路由到你的插件，并将结果流式回传到聊天中。

忽略的目录：`target/`、`node_modules/`、`__pycache__/`、`.venv/`、`dist/`。

通过 `--daemon-addr` 指定非默认守护进程：

```bash
astra-plugin dev --daemon-addr 127.0.0.1:60051
```

## 4. 校验清单

```bash
astra-plugin validate
```

可捕获缺失的必填字段、无效的 SemVer 以及格式错误的配置 schema。在每次构建前运行此命令 —— 守护进程会拒绝加载未通过校验的插件。

## 5. 构建可分发的包

```bash
astra-plugin build
```

生成 `hello-world-0.1.0.astraplugin` —— 一个 ZIP 归档，内含已编译的二进制、清单、任何 UI 资源、本地化文件，并在你拥有签名密钥的情况下包含一个 Ed25519 `SIGNATURE` 条目。

通过 `-o` 输出到指定路径：

```bash
astra-plugin build -o dist/hello-world.astraplugin
```

## 6.（可选）生成签名密钥

```bash
astra-plugin keygen
```

在 `~/.astra/plugin-keys/{private,public}.key` 创建一个 Ed25519 密钥对。之后每一次 `astra-plugin build` 都会自动对归档签名。将 `public.key` 分发给希望校验包真伪的用户。

## 7. 安装插件

将 `.astraplugin` 文件拖入 Astra UI 的 Plugins 页面，或调用守护进程的 `SideloadPlugin` RPC。安装完成后，守护进程会使用正确的凭据重启插件进程，插件随即出现在插件列表中。

## 下一步

- [Rust SDK](sdk-rust.md) —— 每个 trait 方法、`FieldDef` / `UiContribution` 构建器，以及面向 client 插件的 `DaemonClient`。
- [Python SDK](sdk-python.md) —— 如果你更喜欢 `@tool` / `@action` 装饰器以及基于类型提示的自动 schema。
- [TypeScript SDK](sdk-typescript.md) —— 基于类的 API，使用 `@grpc/grpc-js`。
- [能力](capabilities.md) —— tools、TTS、STT、AI provider、actions、triggers、UI contributions、事件处理器及 client 模式的完整参考。
- [发布](publishing.md) —— 签名、分发及升级策略。
