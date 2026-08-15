> **本文档为翻译版本。** 权威来源是 [docs/en](../en/install-cli.md)。如与英文版有出入，以英文版为准。

# 安装 CLI

发布流程中的一切都始于一条命令，而这一页就是教你获得这条命令的地方。这个可执行文件
叫 **`astra-plugin`** —— 不是 `astra-plugin-cli`，后者只是 crate 的名字。

## 如实说明现状

**目前还没有预编译二进制文件，`astra-plugin-cli` 也不在 crates.io 上。**
今天验证过：`https://index.crates.io/as/tr/astra-plugin-cli` 返回 `404`，而同一索引
上的 `astra-plugin-sdk` 返回 `200`，所以这不是查询失败，而是确实不存在。
`gh release list --repo mihailinl/AstraPlugins` 什么也不打印。

所以获取 CLI 的唯一方式就是自己构建，而构建需要 Rust 工具链。发布预编译二进制文件
是一项已知的、独立的、尚待完成的任务 —— 相应的发布自动化正在编写中，等到真的有一个
可供下载的 release 的那天，这一页才会长出一行下载命令。在那之前，它描述的就是现状
的全部，这里也没有任何一处要你去下载什么。

这个成本是真实的，值得说明为什么仍然值得付出：CLI 并不是套在某条更简单路径外面的
便利包装。它是唯一能写出正确发布工作流的东西，唯一能让你的各份清单在版本号上保持
一致的东西，也是唯一能打开一个注册表 bot 真正会看到的上架申请的东西。绕开它，正是
两次真实提交最终归于沉默的原因 —— 详见
[发布到底是什么](publishing.md)。

## 前置条件

| | 原因 | 检查方式 |
|---|---|---|
| **Rust 1.85 或更高版本** | 这里的每个 crate 都是 `edition = "2024"`，而 1.85 是第一个能理解它的发行版 | `cargo --version` |
| **`PATH` 中要有 `protoc`** | CLI 依赖 `astra-plugin-sdk`，其 `build.rs` 使用 `tonic-build` 编译 `proto/plugin.proto`，而这会调用外部的 `protoc` | `protoc --version` |
| **`git`** | `cargo install --git` 用它来克隆 | `git --version` |

没有任何 crate 声明 `rust-version`，而 CI 是在 `stable` 上构建的，所以实际上唯一
被强制要求的下限就是 edition。

安装 `protoc`（这是大家最容易漏掉的一步）：

<!-- doctest: illustrative reason="OS package-manager commands; the doc-test runner has one OS and installing system packages during a documentation check is not something a CI job should be allowed to do" -->
```
Debian/Ubuntu   sudo apt install protobuf-compiler
Arch            sudo pacman -S protobuf
Fedora          sudo dnf install protobuf-compiler
macOS           brew install protobuf
Windows         winget install Google.Protobuf     (or scoop install protobuf)
```

没有它，构建会在 `astra-plugin-sdk` 的构建脚本处失败，错误信息里直接给出了修复方法：

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release, run in astra-plugin-sdk/ — there is no workspace manifest at the repository root, so `-p astra-plugin-sdk` from the root cannot work" unrun="a full SDK build pointed at a protoc that does not exist; minutes long, and it has to fail to print this" -->
```
  Error: Custom { kind: NotFound, error: "Could not find `protoc`. If `protoc` is installed, try setting the `PROTOC` environment variable to the path of the `protoc` binary. To install it on Debian, run `apt-get install protobuf-compiler`. It is also available at https://github.com/protocolbuffers/protobuf/releases  For more information: https://docs.rs/prost-build/#sourcing-protoc" }
```

## 安装

**一行命令，无需克隆。** 通常应该用这个：

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

`--locked` 会针对签入仓库的 `Cargo.lock` 构建，而不是把每个依赖都重新解析到最新
发行版 —— 这决定了你构建出来的东西是否和这里构建的方式一致，还是会在你自己的机器上
突然踩到某个破坏性的补丁版本。

`--git` 构建的是执行时 `master` 上的内容，所以它报告的版本和 commit 就是运行那一刻
`master` 上的内容。下面尖括号里的每一处都会因机器和运行而异 —— 版本号和 SHA 来自
`master`，路径来自你的 home 目录，耗时来自你的 CPU：

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" unrun="clones over the network and compiles for minutes; a documentation check must not do either" -->
```
   Compiling astra-plugin-cli v<version> (<home>/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in <duration>
  Installing <scratch>/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<short-sha>)` (executable `astra-plugin`)
warning: be sure to add `<scratch>/bin` to your PATH to be able to run the installed binaries
```

这段记录是加了 `--root <scratch>` 采集的，这样采集它就不会覆盖任何人已经装好的
二进制文件。**不要加 `--root`** —— 就像上面那条命令一样 —— 这样最后两行会变化：
`Installing` 指向的是 `<home>/.cargo/bin/astra-plugin`，而那条 `PATH` 警告只有在
`~/.cargo/bin` 尚未在你的 `PATH` 里时才会出现。两处 SHA 是同一个 commit 以两种不同
长度打印出来的，这是 cargo 的做法，不是不一致。

如果你还想阅读或修改 CLI 本身，而不只是运行它，就**从克隆开始**：

<!-- doctest: cli -->
```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

普通的 `git clone` 检出的就是 `master`，而当前的 CLI 就在 `master` 上 —— 没有什么
额外的分支需要你去记住。

## 验证是否成功

<!-- doctest: cli -->
```bash
astra-plugin --version
astra-plugin --help
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

这个数字是占位符，因为两条安装命令都不让你挑版本：它们构建的都是某个 commit 而不是
某个 release，所以你拿到的就是那个 commit 的 `Cargo.toml` 里写的版本。`0.2.1` 是
[CLI 的 changelog](../../astra-plugin-cli/CHANGELOG.md) 里最新的一条，那里同样记录了
这个 crate 没有发布列车 —— 没有 crates.io，没有标签，也没有二进制文件。

如果 shell 找不到它，说明 `cargo install` 把它装到了 `~/.cargo/bin`（Windows 上是
`%USERPROFILE%\.cargo\bin`），而这个目录不在你的 `PATH` 里。出现这种情况时，
`cargo` 会明确打印出相应的警告。

### 会破坏第一次发布的那个 bug，以及如何判断你的构建是否包含修复

**`astra-plugin init-ci` 曾经在 GitHub 需要 commit 的地方，固定住一个带注释标签
(annotated tag)的*对象* SHA**，导致第一次 `git push --tags` 在任何 job 开始之前
就以 `invalid value workflow reference` 失败。这就是
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2)。

**修复是提交 `5b8ab22`，而不是某个版本号**，这一点最容易把人绕进去。这里没有发布
列车 —— 什么都没有发布，所以没有人安装“选定的版本”；每个人构建的都是自己克隆到的
那个 commit。`5b8ab22` 进入 `master` 的时间*早于*把版本号提升到 `0.2.1` 的那次
提交，这意味着：

- `5b8ab22` 之后从 `master` 构建出来的东西**既包含修复，又仍然显示 `0.2.0`** ——
  那不是坏掉的构建；
- 任何 `0.2.1` 构建都不可能*缺少*修复，因为 `5b8ab22` 是版本号提升那次提交的祖先；
- 真正坏掉的是 `5b8ab22` *之前*构建的 `0.2.0`，而 `--version` 无法把它和第一种
  情况区分开。

所以 `0.2.1` 是值得拥有的 —— 它是第一个能自己回答这个问题的数字，它存在的意义正在
于此 —— 但一个显示 `0.2.0` 的 `0.2.0` 并不能证明任何事。`0.2.1` 没有新增参数，也
没有改动 API；唯一有变化的行为是 `publish --notify` —— 它给出的链接现在会点名
注册表的 release-ping 表单，而不再依赖注册表此后已经关掉的空白 issue。

如果 `--version` 打印出的是 `0.2.0`，先运行 `which astra-plugin`（Windows 上用
`where`）：最常见的原因是 `PATH` 中有一个更旧的二进制文件排在前面，而光看
`--version` 无法把这种情况和“较旧 commit 的新构建”分开。然后就别再从数字上猜了，
去读那个 pin —— `init-ci` 写下的正是这个 bug 的核心，而且一行就能给出答案。

下面这项检查完全不依赖版本号：

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

包含修复的构建会报告固定值 `e3329df252a46d747676cb540ae4b986af68a3ad` —— 一个
commit。不包含修复的构建会报告 `dc1a044876926e9cf1170f034e2eab533ec07641`，那是
`plugin-release/v1` 的标签*对象*(tag object)，也正是 GitHub 会拒绝的东西。如果你
看到的是后者，就用上面那行命令从 `master` 重新安装，然后再跑一次 `init-ci`。它可以
安全地重复运行：它会保留你的输入，只重写固定值。它不会就地修复已有文件，所以已存在
的 `release.yml` 在你重新运行之前会一直带着错误的 SHA。

完整的命令集如下：

<!-- doctest: output from="astra-plugin --help" -->
```
Astra Plugin Development CLI

Usage: astra-plugin [OPTIONS] <COMMAND>

Commands:
  new      Create a new plugin project from a template
  dev      Start a plugin in dev mode (sideload into the running Astra + hot-reload)
  build    Build a plugin into a distributable .astraplugin bundle
  sign     Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle
  verify   Verify a built .astraplugin bundle and print its digests
  test     Run the conformance suite against a real plugin process
  doctor   Answer, in one command, every question asked when a plugin will not start: toolchains, the daemon, the manifest, the entry point, permissions, the platform block, the release workflow
  logs     Read a plugin's output from the daemon that spawned it
  check    Check a plugin manifest, config schema and release workflow
  init-ci  Write .github/workflows/release.yml, pinned to a commit of the Astra reusable workflow. Re-run it to upgrade the pin; it keeps your inputs
  version  Set the version in plugin.toml and every other manifest at once
  publish  Get a release listed: preflight it, or open a prefilled submission
  keygen   Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses
  help     Print this message or the help of the given subcommand(s)

Options:
      --json     Print one JSON document instead of human output. Progress lines are suppressed so the output is safe to pipe
  -h, --help     Print help
  -V, --version  Print version

Exit codes: 0 success · 1 the plugin/bundle is wrong · 2 the CLI could not run the check.
RUST_LOG controls trace output, e.g. RUST_LOG=astra_plugin=debug.
```

**没有 `astra-plugin login` 这个命令**，这是刻意的设计，而不是没做完：这整套工具链
从来不会向你索要任何凭证。参见
[申请上架](5-publish/get-listed.md)。

## 保持最新

重新运行同一条 `cargo install --git` 命令即可，Cargo 会原地替换掉可执行文件。
目前没有自我更新机制，而且在有了签名的发布二进制文件之前，也不会有。

## 常见问题

| 症状 | 原因 |
|---|---|
| `Could not find` protoc` ` | `protoc` 不在 `PATH` 中，参见上面的表格 |
| `feature `edition2024` is required` | Rust 版本低于 1.85 |
| 安装成功后仍提示 `astra-plugin: command not found` | `~/.cargo/bin` 不在 `PATH` 中 |
| 在仓库根目录运行 `cargo install --path .` 时出现 `error: could not find `Cargo.toml`` | 根目录没有工作区清单文件。把 `--path` 指向 `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | `PATH` 中有一个更旧的 `astra-plugin`排在前面。`--version` 无法帮你分辨，用 `which astra-plugin`（Windows 上用 `where`）查看你实际运行的是哪个文件 |
| 第一次推送标签时出现 `invalid value workflow reference` | 写出 `release.yml` 的那个 CLI 早于 `5b8ab22`，固定的是标签对象。参见[如何判断你的构建是否包含修复](#会破坏第一次发布的那个-bug以及如何判断你的构建是否包含修复) |

## 接下来

- **[发布到底是什么](publishing.md)** —— 从空目录到上架插件的完整流程，一页讲完。
- [快速上手](2-tutorial/getting-started.md) —— 编写插件本身。
