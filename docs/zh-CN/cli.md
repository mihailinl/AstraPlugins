# `astra-plugin` CLI 参考

每个子命令、标志和行为 —— 来源于 `astra-plugin-cli/src/main.rs` 和 `astra-plugin-cli/src/commands/`。

## 安装

```bash
cd AstraPlugins/astra-plugin-cli
cargo install --path .
```

运行 `astra-plugin --help` 查看完整命令列表。每个子命令同样支持 `--help`。

## `astra-plugin create`

根据特定语言的模板生成一个新的插件项目。

```bash
astra-plugin create <NAME> [--lang <LANG>] [--capabilities <LIST>] [--output <DIR>]
```

| 参数 / 标志 | 默认值 | 说明 |
| --- | --- | --- |
| `NAME` | — | 插件 id。必须为小写字母、数字加连字符 —— 此值即成为清单中的 `[plugin].id`。 |
| `-l, --lang` | `rust` | 可选值：`rust`、`python`（别名 `py`）、`typescript`（别名 `ts`）。 |
| `-c, --capabilities` | `tools` | 以逗号分隔的列表。有效标识：`tools`、`tts`、`stt`、`ai_provider`、`actions`、`triggers`、`client`、`event_handlers`、`ui_panels`。逗号周围的空白会被去除。 |
| `-o, --output` | `./<NAME>` | 目标目录。 |

### 生成的内容

所有脚手架均包含：

- `plugin.toml` —— 预填的清单，含 id、名称、版本 `0.1.0`，以及根据你的请求启用的 `[capabilities]` 小节。
- `proto/plugin.proto` —— 插件协议的本地副本。
- `.gitignore`、`README.md`。

特定语言的附加文件：

| 语言 | 附加文件 |
| --- | --- |
| `rust` | `Cargo.toml`（依赖 `astra-plugin-sdk`、`tokio`、`serde`、`anyhow`、`async-trait`），`src/main.rs` 中包含 `PluginCapability` 实现桩。`entry.command` 被设置为 `target/release/<name>.exe`。 |
| `python` | `pyproject.toml`（依赖 `astra-plugin-sdk`、`grpcio`、`protobuf`），`src/plugin.py` 中包含 `Plugin` 子类桩。`entry.command = "python"`，`args = ["-m", "src.plugin"]`，`runtimes = ["python"]`。 |
| `typescript` | `package.json`、`tsconfig.json`，`src/index.ts` 中包含 `Plugin` 子类桩。`entry.command = "node"`，`args = ["dist/index.js"]`，`runtimes = ["node"]`。 |

## `astra-plugin dev`

以开发模式运行插件，带有文件监视和自动重建/重启。

```bash
astra-plugin dev [PATH] [--daemon-addr <HOST:PORT>]
```

| 参数 / 标志 | 默认值 | 说明 |
| --- | --- | --- |
| `PATH` | `.` | 插件目录（包含 `plugin.toml` 的目录）。 |
| `--daemon-addr` | `127.0.0.1:50051` | 正在运行的 Astra 守护进程的 gRPC 地址。 |

### 其执行流程

1. 读取 `plugin.toml` 并按语言确定构建命令。
2. 在插件目录上启动文件监视器（忽略 `target/`、`node_modules/`、`__pycache__/`、`.venv/`、`dist/`）。
3. 运行构建（Rust 使用 `cargo build`，TypeScript 使用 `bun run build` / `tsc`，Python 使用 `uv pip sync` 或不执行操作）。
4. 启动 `entry.command`，并追加 `--daemon-addr`、`--plugin-id` 及 `--auth-token`。
5. 文件变更时：终止子进程、重新构建、重新启动。

错误会内联输出。按 `Ctrl+C` 停止。

## `astra-plugin build`

将插件打包为可分发的 `.astraplugin` 归档。

```bash
astra-plugin build [PATH] [-o <FILE>]
```

| 参数 / 标志 | 默认值 | 说明 |
| --- | --- | --- |
| `PATH` | `.` | 插件目录。 |
| `-o, --output` | `<id>-<version>.astraplugin` | 归档路径。 |

### 各语言的构建步骤

| 语言 | 步骤 |
| --- | --- |
| `rust` | 运行 `cargo build --release`，将二进制复制到归档内的 `bin/`，并将 `entry.command` 重写为指向打包后的路径。 |
| `typescript` | 运行 `bun build src/index.ts --outdir dist`，失败时回退到 `npx esbuild`。打包后的 JS 位于归档中的 `dist/`。 |
| `python` | 若 `uv` 在 `PATH` 中，则通过 `uv pip compile` 生成 `requirements.lock`。复制 `src/`、`pyproject.toml`、`requirements.txt` 以及锁文件。 |

### 归档布局

```
<plugin-id>-<version>.astraplugin           (ZIP file)
├── plugin.toml              # Manifest (entry.command rewritten for Rust)
├── bin/                     # Compiled binary (Rust only)
├── dist/                    # Bundled JS (TypeScript only)
├── src/                     # Python source
├── requirements.txt         # Python deps (unlocked)
├── requirements.lock        # Python deps (resolved by uv)
├── ui/                      # Custom UI (if present)
├── locales/                 # i18n JSON files (if present)
├── icon.png / icon.svg      # Optional branding
├── README.md / LICENSE      # Optional
├── SIGNATURE                # Ed25519 signature (if keypair exists)
└── PUBKEY                   # Signing public key (if keypair exists)
```

若 `~/.astra/plugin-keys/private.key` 存在，CLI 会在每次构建时**自动签名**归档 —— 无需额外标志。

## `astra-plugin validate`

在不进行构建的情况下检查清单和配置 schema。

```bash
astra-plugin validate [PATH]
```

校验项：

- 清单必填字段：`plugin.id`、`plugin.name`、`plugin.version`、`entry.command`。
- `plugin.id` 是小写字母、数字与连字符组成。
- `plugin.version` 匹配 `X.Y.Z` SemVer（不满足时产生警告，而非错误）。
- 至少启用了一项能力（若全部为 false，则产生警告）。
- 存在 `[config].schema` 时，能解析为 JSON 且根节点为 `"type": "object"`。
- 元数据警告：缺少 `description` 或 `author`。

仅在发生硬错误（TOML 无法解析、缺少必填字段）时以非零码退出。

## `astra-plugin keygen`

生成用于 `build` 对归档进行签名的 Ed25519 密钥对。

```bash
astra-plugin keygen [--force]
```

| 标志 | 说明 |
| --- | --- |
| `--force` | 覆盖现有密钥对。未指定该标志时，命令会拒绝替换现有密钥。 |

输出位置（若不存在则创建）：

- `~/.astra/plugin-keys/private.key` —— base64 编码的 Ed25519 私钥种子（请保密）。
- `~/.astra/plugin-keys/public.key` —— base64 编码的 Ed25519 公钥（可公开分享）。

一旦密钥对存在，每次 `astra-plugin build` 都会自动追加一个 `SIGNATURE` 条目（对每个 ZIP 条目生成类似 HMAC 的摘要，并用 Ed25519 签名），以及一个 `PUBKEY` 条目，以便消费者校验真伪。

## 环境

- `RUST_LOG` —— 控制 CLI 输出的详细程度。默认为 warning 级别；使用 `RUST_LOG=debug` 查看完整跟踪。
- 所有 CLI 命令都会遵循当前 shell 的 `PATH`，用于查找 `cargo`、`node`、`bun`、`npx`、`python` 及 `uv`。
