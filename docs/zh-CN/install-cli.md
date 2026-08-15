> **本文档为翻译版本。** 权威来源是 [docs/en](../en/install-cli.md)。如与英文版有出入，以英文版为准。

# 安装 CLI

发布流程中的一切都始于一条命令，而这一页就是教你获得这条命令的地方。这个可执行文件
叫 **`astra-plugin`** —— 不是 `astra-plugin-cli`，后者只是 crate 的名字。

## 两种方式，选哪一个

**下载二进制文件。** 发布 [`cli-v0.2.1`][rel] 带有 Linux 和 Windows 的
预编译归档文件、一个校验和文件，以及一个你可以验证的 Sigstore 包。不需要
编译任何东西，也不涉及任何工具链。这是大多数人想要的路，下面就是它的
说明。

**或者从源码构建**，这需要 Rust 1.85 或更新版本，以及 `protoc`。如果
你所在的平台还没有归档文件 —— 目前来说是 macOS 和 ARM Linux —— 或者你
想读一读甚至改一改 CLI，而不只是运行它，就选这条路。

**`cargo install astra-plugin-cli` 不是这两种方式之一，而且不会成功。**
这个 crate 以路径方式依赖一个 vendor 进来的 `astra-plugin-manifest`
(`astra-plugin-manifest = { path = "vendor/astra-plugin-manifest" }`)，
cargo 从不会打包一个路径依赖的源码，所以发布会因为 *all dependencies
must have a version requirement specified* 而失败 —— 所以这个 crate
根本就不在 crates.io 上（`https://index.crates.io/as/tr/astra-plugin-cli`
今天返回 `404`，而同一索引上的 `astra-plugin-sdk` 返回 `200`）。要解决
这个问题，得先从 Astra 发布这个清单 crate，而本页不会对此承诺任何日期。

[rel]: https://github.com/mihailinl/AstraPlugins/releases/tag/cli-v0.2.1

## 下载二进制文件

### 选哪个归档

| 你在用 | 选择 |
|---|---|
| **任意 Linux** | `astra-plugin-0.2.1-linux-x64-musl.tar.gz` |
| Linux，且特别想要 glibc 构建版本 | `astra-plugin-0.2.1-linux-x64-gnu.tar.gz` |
| **Windows** | `astra-plugin-0.2.1-windows-x64.zip` |

**musl 是安全的默认选择，理由不是口味问题。** gnu 那个构建是动态链接
的，它的符号表需要 **glibc 2.39 或更新版本**，而 Ubuntu 22.04（2.35）、
Debian 12（2.36）、RHEL 9（2.34）都没有 —— 在这些系统上它会直接启动
失败，而不是隐晦地出问题。musl 归档是一个完全不依赖 libc 的
`static-pie` 可执行文件，所以在它们上面都能跑。只有在你确实明确想要
gnu 版本时才选它。

那次发布的完整资产列表，也就是所有已发布的内容：

<!-- doctest: output from="gh release view cli-v0.2.1 --repo mihailinl/AstraPlugins --json assets" unrun="reads a GitHub release over the network; re-run the command in the from= to confirm the list, or open the release page" -->
```
astra-plugin-0.2.1-linux-x64-gnu.tar.gz     3372607
astra-plugin-0.2.1-linux-x64-musl.tar.gz    3425289
astra-plugin-0.2.1-windows-x64.zip          3450755
SHA256SUMS.txt                                  314
astra-plugin-0.2.1.sigstore.jsonl             11414
```

### 获取并验证它

在 Linux 上用 `curl` —— 这里既不需要 `gh`，也不需要 GitHub 账号：

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1-linux-x64-musl.tar.gz
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
tar xzf astra-plugin-0.2.1-linux-x64-musl.tar.gz
./astra-plugin-0.2.1-linux-x64-musl/astra-plugin --version
```

这是这些命令的一份真实记录：

<!-- doctest: output from="sha256sum -c --ignore-missing SHA256SUMS.txt" unrun="needs the release archive downloaded next to the checksum file; re-run the two curl lines above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
```

**请使用 `--ignore-missing`。** `SHA256SUMS.txt` 列出了全部三个归档
文件，普通的 `sha256sum -c SHA256SUMS.txt` 会把你没下载的那两个报告
为 `FAILED open or read`，并**以退出码 1 结束** —— 这看起来完全就像
下载损坏了，但其实不是：

<!-- doctest: output from="sha256sum -c SHA256SUMS.txt" unrun="needs one of the three archives present and the other two absent; re-run the curl lines above and then this one to reproduce it" -->
```
sha256sum: astra-plugin-0.2.1-linux-x64-gnu.tar.gz: No such file or directory
astra-plugin-0.2.1-linux-x64-gnu.tar.gz: FAILED open or read
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
sha256sum: astra-plugin-0.2.1-windows-x64.zip: No such file or directory
astra-plugin-0.2.1-windows-x64.zip: FAILED open or read
sha256sum: WARNING: 2 listed files could not be read
```

这个归档会解压出一个目录，其中包含二进制文件和它的许可证文件：

<!-- doctest: output from="tar tzf astra-plugin-0.2.1-linux-x64-musl.tar.gz" unrun="needs the downloaded archive; re-run the curl line above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl/
astra-plugin-0.2.1-linux-x64-musl/LICENSE
astra-plugin-0.2.1-linux-x64-musl/NOTICE
astra-plugin-0.2.1-linux-x64-musl/README.md
astra-plugin-0.2.1-linux-x64-musl/astra-plugin
```

把 `astra-plugin` 移动到 `PATH` 中的某个位置 —— `~/.local/bin` 是常见
的选择，而且不需要 `sudo`：

<!-- doctest: cli -->
```bash
mkdir -p ~/.local/bin
cp astra-plugin-0.2.1-linux-x64-musl/astra-plugin ~/.local/bin/
astra-plugin --version
```

在 Windows 上，从发布页面下载 `.zip`，解压它，然后把
`astra-plugin.exe` 放到你的 `PATH` 中。`certutil -hashfile <file>
SHA256` 是内置的校验和工具，把它的输出和 `SHA256SUMS.txt` 用肉眼比对。

### 验证是谁构建的它

校验和证明的是这些字节和发布中列出的某个文件相匹配。它不能证明是谁
生产了那个文件 —— 为此有一个 Sigstore 包，`gh` 会拿它去和 GitHub 的
构建证明核对：

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1.sigstore.jsonl
gh attestation verify astra-plugin-0.2.1-linux-x64-musl.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins
astra-plugin --version
```

**成功时，如果输出不是终端就什么都不打印，并以 `0` 退出。** 第一次
遇到这个会让人费解；请检查 `echo $?`，而不是去找一个对勾。失败时会
很吵闹，并以 `1` 退出：

<!-- doctest: output from="gh attestation verify tampered.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins" unrun="needs the bundle and a deliberately corrupted copy of the archive; append a byte to the archive and re-run to reproduce it" -->
```
Error: verifying with issuer "sigstore.dev"
```

这是通过在归档文件末尾附加一个字节产生的；把 `--repo` 指向一个没有
构建过它的仓库也会以同样的方式失败。一个包会覆盖全部三个归档文件，
它证明的内容可以用 `--format json` 读取：签名用的工作流是
`https://github.com/mihailinl/AstraPlugins/.github/workflows/release-cli.yml@refs/tags/cli-v0.2.1`，
issuer 是 `https://token.actions.githubusercontent.com`，三个 subject
摘要值就是 `SHA256SUMS.txt` 的三行。`gh attestation verify` 需要网络
访问来获取信任根，但不需要 GitHub 登录。

## 从源码构建

在 macOS 或 ARM Linux 上选这条路，因为那里还没有归档文件，或者是为了
在 CLI 本身上做开发。这不是下载失败时的备用方案 —— 上面的二进制文件
就是同一个程序。

### 前置条件

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

### 构建它

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

要构建出和已发布二进制文件完全相同的代码，而不是 `master` 今天携带的
内容，请先检出那个发布标签：

<!-- doctest: cli -->
```bash
git clone --branch cli-v0.2.1 https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

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

下载的二进制文件会打印出 `astra-plugin 0.2.1`，因为这个归档是从标签
`cli-v0.2.1` 构建的，别无其他来源。`<version>` 只在源码这条路上才是
占位符：`cargo install --git` 构建的是那一刻 `master` 上的内容，所以
你拿到的就是那个 commit 的 `Cargo.toml` 里写的版本，它可能领先于最新
的发布版本。`0.2.1` 是 [CLI 的 changelog](../../astra-plugin-cli/CHANGELOG.md)
里最新的一条。

如果 shell 找不到它：下载的二进制文件就在你复制到的那个位置，而
`cargo install` 会把它装到 `~/.cargo/bin`（Windows 上是
`%USERPROFILE%\.cargo\bin`）。无论哪种情况，这个目录都不在你的
`PATH` 里。出现这种情况时，`cargo` 会明确打印出相应的警告。

### 会破坏第一次发布的那个 bug，以及如何判断你的构建是否包含修复

**`astra-plugin init-ci` 曾经在 GitHub 需要 commit 的地方，固定住一个带注释标签
(annotated tag)的*对象* SHA**，导致第一次 `git push --tags` 在任何 job 开始之前
就以 `invalid value workflow reference` 失败。这就是
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2)。

**下载 `0.2.1` 二进制文件就能解决这个问题，这是最简短的答案。** 这个
归档是从标签 `cli-v0.2.1` 构建的，`5b8ab22` 是它的祖先提交，所以下载的
二进制文件已经带有这个修复。本节剩下的内容是关于从源码构建的，那里的
数字才无法给出定论。

**修复是提交 `5b8ab22`，而不是某个版本号**，这一点最容易把人绕进去。从源码构建
安装的是你克隆到的那个 commit，而不是某个选定的发布版本。`5b8ab22` 进入 `master`
的时间*早于*把版本号提升到 `0.2.1` 的那次提交，这意味着：

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

如果你下载的是二进制文件，下载下一个发布版本的归档文件并替换掉旧的 ——
再核对一次校验和，因为新发布就意味着新的字节。如果你是从源码构建的，
重新运行同一条 `cargo install` 命令，cargo 就会原地替换掉可执行文件。
**没有自我更新机制**，这套工具链里也没有任何东西会主动联网去发现是否
有新版本存在。

## 常见问题

| 症状 | 原因 |
|---|---|
| `sha256sum -c` 报出 `FAILED open or read` | 你只下载了一个归档，而文件里列出了三个。加上 `--ignore-missing` |
| `Error: verifying with issuer "sigstore.dev"` | 归档和包不匹配，或者 `--repo` 指向的仓库并没有构建过它。重新下载一次，而不是去推理原因 |
| `gh attestation verify` 完全没有输出 | 那就是成功。它在输出不是终端时保持沉默；用 `echo $?` 确认是 `0` |
| 二进制文件启动不了，加载器抱怨找不到 `GLIBC_2.39` 版本 | 你在一个 glibc 较旧的系统上选用了 gnu 归档。换成 musl 的，它不需要 libc |
| `error: could not find `astra-plugin-cli` in registry `crates-io` with version `*`` | `cargo install astra-plugin-cli` 无法成功，这就是它给出的报错。参见本页开头 |
| `Could not find` protoc` ` | `protoc` 不在 `PATH` 中，参见上面的表格 |
| `feature `edition2024` is required` | Rust 版本低于 1.85 |
| 安装成功后仍提示 `astra-plugin: command not found` | 放二进制文件的那个目录不在 `PATH` 中 —— 对于从源码构建，那就是 `~/.cargo/bin` |
| 在仓库根目录运行 `cargo install --path .` 时出现 `error: could not find `Cargo.toml`` | 根目录没有工作区清单文件。把 `--path` 指向 `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | `PATH` 中有一个更旧的 `astra-plugin`排在前面。`--version` 无法帮你分辨，用 `which astra-plugin`（Windows 上用 `where`）查看你实际运行的是哪个文件 |
| 第一次推送标签时出现 `invalid value workflow reference` | 写出 `release.yml` 的那个 CLI 早于 `5b8ab22`，固定的是标签对象。参见[如何判断你的构建是否包含修复](#会破坏第一次发布的那个-bug以及如何判断你的构建是否包含修复) |

## 接下来

- **[发布到底是什么](publishing.md)** —— 从空目录到上架插件的完整流程，一页讲完。
- [快速上手](2-tutorial/getting-started.md) —— 编写插件本身。
