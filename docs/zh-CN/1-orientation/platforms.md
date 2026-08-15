> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/1-orientation/platforms.md)。如与英文版有出入，以英文版为准。

# 平台

Astra 为**两个**宿主平台提供守护进程。下面的一切都由此推出。

| 平台键 | 宿主 | Astra 是否提供守护进程 |
|---|---|---|
| `linux-x64` | Linux, x86_64 | 是 |
| `windows-x64` | Windows, x86_64 | 是 |
| `noarch` | 任意 —— 没有原生代码的解释型插件 | 不适用，两边都能跑 |
| `linux-arm64` · `windows-arm64` · `macos-x64` · `macos-arm64` | — | **否** |

最后一行是*保留但不支持*的。这些名字之所以存在于注册表的 schema 里，
是为了让 Astra 日后如果为这些宿主提供了支持时，索引格式不必再改动；也是
为了让校验器能够拒绝一个拼写错误（`mac-amd64`），而不是写入一个永远不会
有任何守护进程去查找的键。以这些键之一发布的包，没有任何宿主可以运行它。
`astra-plugin build` 拒绝去猜：在一个它没有对应键的宿主上，它会告诉你
显式传入 `--target`，而不是悄悄打包出一个默认解析成 `linux-x64` 的东西。

## 每个平台一个包，以及决定你需要几个包的因素

<!-- doctest: cli -->
```bash
astra-plugin build --target linux-x64
astra-plugin build --target windows-x64
astra-plugin build --all-targets
```

- **Rust** 编译成原生代码，所以每个平台都需要一个独立的包。发布工作流
  在一个矩阵上构建它们 —— `ubuntu-24.04` 和 `windows-2022` —— 因为
  跨平台构建会遇到另一套完全不同的 bug。
- **TypeScript 和 Python** 生成单一的 `noarch` 包。索引会把同一个 URL
  和摘要写在每一个受支持的平台键下面，所以一个 `noarch` 包和其他任何
  包一样，在 `linux-x64` 和 `windows-x64` 下都能被找到。

`--all-targets` 会构建出让插件在 Astra 运行的每个地方都可安装所需要的
一切：TypeScript 和 Python 各一个文件，Rust 每个平台一个文件，各自来自
它自己的 `cargo build --target`。

## `[platform]`，以及为什么省略这个段本身就是一种断言

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "native-thing"
name = "Native Thing"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/native_thing"

[capabilities]
tools = true

[platform]
os = ["linux", "windows"]
arch = ["x86_64"]
```

`[platform]` 为空或缺失意味着*没有任何要求*，守护进程会认为这个插件在
任何地方都兼容。对于一个 `noarch` 插件来说这是对的，但对于一个携带原生
二进制文件的插件来说这就错了。`astra-plugin doctor` 会原原本本地这样
说明：

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Will this install on the platforms I expect?
         no [platform] block, so the daemon considers it compatible everywhere. Correct for a
         noarch plugin; wrong for one that ships a native binary.
```

`astra-plugin build` 会把 `--target` 得出的真实答案盖印进包的
`MANIFEST` 中，所以不管清单文件怎么说，打包出的文件都携带着真实的
`{os, arch}`。

## 构建前置条件

| 语言 | 需要什么 | 由谁检查 |
|---|---|---|
| Rust | Rust **1.85 或更新版本** —— SDK 和脚手架都是 edition 2024 | `astra-plugin doctor` |
| Rust | **`PATH` 中要有 `protoc`。** `astra-plugin-sdk/build.rs` 用 `tonic_build::configure().compile_protos(…)` 编译 `proto/plugin.proto`，而 tonic-build 0.12 是调用外部的 `protoc`，而不是自带一个。`apt install protobuf-compiler` / `pacman -S protobuf` / `brew install protobuf` / `winget install Google.Protobuf` | `astra-plugin doctor` |
| TypeScript | 运行需要 Node 20+，打包需要 `bun`（或 `build` 脚本所用的打包工具） | `astra-plugin doctor` |
| Python | `python3`，外加来自 `requirements.txt` 的 `grpcio` 和 `protobuf` | `astra-plugin doctor` |

`protoc` 是最先咬人的那一个，而且症状看起来像别的问题。CLI 依赖 Rust
SDK，所以*安装 `astra-plugin` 本身*就需要它 —— 在你还没有项目、没有
清单文件，甚至还没有理由怀疑是 protobuf 编译器的问题之前。没有它，
`cargo install` 会停在
`error: failed to run custom build command for astra-plugin-sdk`，
再往下几行会看到 `Could not find `protoc``。本仓库自己的 CI 在每一个
Rust job 里都会安装它（`.github/workflows/ci.yml` 中出现了七次
`arduino/setup-protoc@v3`），这就是它绝非可选项的最有力证据。

`astra-plugin doctor` 会在你实际所在的这台机器上，用一条命令回答这一切：

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Can I build a Rust plugin?
         cargo 1.97.0 (c980f4866 2026-06-30)
  [ok  ] Can I compile the SDK's protobufs?
         libprotoc 35.1
  [ok  ] Can I build and run a TypeScript plugin?
         node v26.4.0
  [ok  ] What will bundle my TypeScript?
         bun — `astra-plugin build` uses bun run build
  [ok  ] Can I build and run a Python plugin?
         python3: Python 3.14.6
```

### glibc 下限

在 CI 中构建的 Linux 包会针对 **GLIBC_2.39** 进行检查 —— 发布工作流会
反汇编成品压缩包里的每一个 ELF 目标文件，一旦发现有任何东西需要更新的
符号版本，就让构建失败。正是这一点保证了在 `ubuntu-24.04` 上构建出的
插件能在 Astra 所面向的那些发行版上运行，而这类失败原本只会出现在
用户的机器上。

如果你在一个更新的发行版上手动构建 Linux 包，是不会有任何东西检查这一点
的。这正是发布路径必须走 CI 的原因之一。

### TypeScript 包不携带 `node_modules`

`.astraplugin` 出货的是打包后的产物，而不是一整棵依赖树。发布工作流会
断言这个包是自包含的：一个打包工具没能追踪到的孤立 `require("chalk")`，
安装时不会报错，却会在首次启动时以 `MODULE_NOT_FOUND` 死掉 —— 而且是在
一台没有人能修复它的机器上。

## 各操作系统下东西都在哪里

Astra 用 `directories` crate，基于 `("com", "astra", "astra")` 来解析
自己的目录 —— CLI 用的是完全相同的调用，所以两者不可能产生分歧
（`astra-plugin-cli/src/daemon.rs`）。

| | Linux | Windows |
|---|---|---|
| 配置目录 | `~/.config/astra` | `%APPDATA%\astra\astra\config` |
| 守护进程端口文件 | `<config>/daemon.port` | 相同 |
| 守护进程引导密钥 | `<config>/daemon.token` | 相同 |
| 已安装插件 | `<config>/plugins/<id>/` | 相同 |
| 插件的设置 | `<config>/plugins/<id>/config.json` | 相同 |
| 守护进程日志 | `<config>/logs/` | 相同 |

去问，而不是去假设 —— `doctor` 会打印出这台机器实际解析出的路径：

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [warn] Where does the CLI look for the running daemon?
         /home/you/.config/astra — but there is no daemon.port in it, so the CLI will fall
         back to 127.0.0.1:32000
```

当 32000 端口被占用时，守护进程会使用一个由操作系统分配的端口，所以
`127.0.0.1:32000` 只是一个兜底的猜测，`daemon.port` 里的内容才是事实。

## macOS

不受支持，而且不是因为疏漏。Astra 自己的发布工作流只构建 `linux-x64`
和 `windows-x64`，所以一个 `macos-arm64` 的插件包将没有任何宿主可以
运行它；macOS 还会给每一位第三方作者额外带来 Apple 公证(notarization)
的问题。这些键名保留在索引 schema 里，但没有任何东西会产出它们，一个
未被处理的宿主会得到一个硬性错误，而不是悄悄的回退。等到 Astra 为该
目标提供守护进程的那个版本，再重新考虑这个问题。
