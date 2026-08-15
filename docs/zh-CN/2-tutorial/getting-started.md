> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/2-tutorial/getting-started.md)。如与英文版有出入，以英文版为准。

# 快速上手

从零开始，做出一个会掷骰子、带测试、并已打包好用于发布的插件。大约十五
分钟，大部分时间都花在等 `cargo` 上。

本页的每一个代码块都会由 CI 中的
[`docs/tools/doctest.py`](../../tools/doctest.py) 执行。只要其中任何一个
有错，构建就会在你读到之前变红。

## 1 · 安装 CLI

一行命令。需要几分钟，最后会打印出一个版本号。

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

这个数字是有意写成占位符的：`--git` 构建的是你运行时 `master` 上的那个
commit，所以打印出来的是那个 commit 的版本，而不是你挑选的版本。

如果是从克隆开始，`cargo install --path astra-plugin-cli --locked` 效果
一样。

**你需要 Rust 1.85 或更新版本，以及 `PATH` 中的 `protoc`。** 没有
`protoc`，构建会停在 ``Could not find `protoc` `` 处。用
`apt install protobuf-compiler`、`pacman -S protobuf`、
`brew install protobuf`，或 `winget install Google.Protobuf` 安装它，
然后再次运行上面那行命令。

**版本号无法告诉你这个构建是好的，而 `0.2.0` 也不是坏的。** `init-ci`
曾经在 GitHub 需要 commit 的地方固定住标签*对象*，插件第一次
`git push --tags` 就死在那里。修复是提交 `5b8ab22`，它进入 `master` 的
时间*早于*把版本号提升到 `0.2.1` 的那次提交 —— 所以从 `master` 构建出来
的东西可以既带修复又显示 `0.2.0`，而且不存在缺少该修复的 `0.2.1`。今天
从 `master` 安装，无论数字是多少你都会拿到修复；想要验证而不是相信，就
运行 `astra-plugin init-ci` 并读它打印出的 pin ——
`e3329df252a46d747676cb540ae4b986af68a3ad` 是 commit，是对的；
`dc1a044876926e9cf1170f034e2eab533ec07641` 是标签对象，是那个 bug。详细
版本见
[安装 CLI](../install-cli.md#会破坏第一次发布的那个-bug以及如何判断你的构建是否包含修复)。

顺带一提，这不会阻碍你继续：CLI 不在 crates.io 上，也没有预编译二进制
文件，所以构建它是获取它的唯一方式。预编译二进制文件已经在计划中。完整
细节，包括不成功时该怎么办：[安装 CLI](../install-cli.md)。

在怀疑代码之前，先检查一下这台机器：

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

它会一次性回答十六个问题 —— 你正在运行哪个 CLI、它解析出了哪个配置
目录、Astra 是否可达、你有哪些工具链（包括 `protoc`）、你的发布工作流
是否已固定版本。任何东西让人困惑时，这是第一个该运行的命令。

## 2 · 生成脚手架

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang rust --template tool
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller --lang rust --template tool" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

六个文件：

<!-- doctest: illustrative reason="an annotated tree of what `astra-plugin new` wrote, not a command; the run that produced it is the output block above" -->
```
dice-roller/
├── plugin.toml      清单 —— id、版本、能力、入口点
├── Cargo.toml       只有一个依赖，外加一段解释为何只有一个的长注释
├── src/main.rs      插件本体：十五行，外加一个测试模块
├── README.md        商店在你的插件旁边展示的内容
├── icon.svg         一个占位图标，就是让你替换的
└── .gitignore       `target/` 和 `*.astraplugin`
```

`README.md` 和 `icon.svg` 不是装饰：打包器按名字把这两个文件收进去，注册表
再从校验过的 bundle 里把它们读出来，用于构建你这条listing的卡片和页面。它们
是别人在决定是否安装你之前会看到的东西，所以发布前请替换掉它们 ——
[让插件被收录](../5-publish/get-listed.md) 说明了各自的要求。

`--lang` 接受 `rust`、`python` 或 `typescript`；`--template` 决定使用
哪些能力和示例代码，`--capabilities tools,triggers` 会覆盖模板隐含的
任何设定。

### 脚手架固定了什么版本

| 语言 | 脚手架固定的版本 | 已发布版本 |
|---|---|---|
| Rust | `astra-plugin-sdk = "0.6"` | crates.io 0.6.0 |
| Python | `astra-plugin-sdk>=0.5,<0.6` | PyPI 0.5.0 |
| TypeScript | `"astra-plugin-sdk": "^0.5.0"` | npm 0.5.0 |

这些版本号能从各自的注册表解析成功，所以在一个全新项目里，`cargo build`、
`pip install -r requirements.txt` 和 `bun install` 不需要任何额外配置就
能正常工作。

**下限版本是有实际意义的。** Rust 0.6 是 `HostClient` 第一个会附带
`x-session-token` 的版本，Python 和 TypeScript 各自的对应版本是 0.5.0；
针对比这更旧的版本，守护进程会对每一次 host 调用都回答
`unauthenticated`。放宽这个下限，等于是用一个解析期的错误换来一个运行期
的错误，而这是更糟糕的交易 —— 插件能启动、能响应钩子，却悄无声息地
无法回话。

Python：`astra-plugin test` 会用 `PATH` 上找到的那个 `python` 来运行你的
插件，所以请先激活你安装依赖时用的那个虚拟环境。否则插件会在注册之前就
以 `ModuleNotFoundError: astra_plugin_sdk` 退出。

## 3 · 编写插件

用下面这段替换 `src/main.rs`。这就是整个插件 —— 带类型的参数、一个
工具、一个触发器，以及三个测试。

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

/// The arguments the model sends. The doc comments become the JSON Schema it
/// reads, so write them for a reader who has never seen this plugin.
#[astra::args]
struct Roll {
    /// How many dice to roll
    #[serde(default = "one")]
    count: u32,
    /// How many sides each die has
    #[serde(default = "six")]
    sides: u32,
}

fn one() -> u32 { 1 }
fn six() -> u32 { 6 }

#[derive(Default)]
struct DiceRoller;

#[astra::plugin]
impl DiceRoller {
    /// Roll dice and return the total. Use it whenever the user asks for a
    /// random number, a dice roll, or a coin flip.
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
        if a.sides < 2 {
            return Err(ToolError::BadArguments("a die needs at least 2 sides".into()));
        }
        let total: u32 = (0..a.count).map(|_| 1 + rand_below(a.sides)).sum();
        ctx.host()
            .fire_trigger("dice_rolled", &json!({ "total": total }).to_string())
            .await?;
        Ok(total.to_string())
    }
}

/// Not a dependency: `SystemTime` is enough entropy for a dice roll.
fn rand_below(n: u32) -> u32 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos();
    nanos % n
}

astra::main!(DiceRoller::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn it_rolls_and_fires_the_trigger() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();

        let total: u32 = h
            .call_tool("roll_dice", json!({ "count": 3, "sides": 6 }))
            .await
            .expect("the tool answered")
            .parse()
            .unwrap();
        assert!((3..=18).contains(&total), "three d6 cannot total {total}");

        assert_eq!(h.fired_triggers().len(), 1);
        assert_eq!(h.fired_triggers()[0].trigger_type, "dice_rolled");
    }

    #[tokio::test]
    async fn a_one_sided_die_is_rejected() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        let err = h
            .call_tool("roll_dice", json!({ "sides": 1 }))
            .await
            .expect_err("a die needs two sides");
        assert!(err.to_string().contains("2 sides"), "{err}");
    }

    /// What the user sees if they never granted `fire_trigger`.
    #[tokio::test]
    async fn a_denied_permission_surfaces_as_an_error() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        h.host().deny("fire_trigger");
        let err = h.call_tool("roll_dice", json!({})).await.expect_err("denied");
        assert!(err.to_string().contains("fire_trigger"), "{err}");
    }
}
```

有五点值得指出：

- **是 `#[astra::args]`，不是 `#[derive(Deserialize, JsonSchema)]`。**
  serde 的 derive 会发出 `extern crate serde`，它是通过 extern
  prelude 来解析的，无法通过重新导出（re-export）到达 —— 所以直接用
  普通的 derive 会要求*你自己的* `Cargo.toml` 里也有 `serde`，而这恰恰
  是脚手架承诺你不需要的东西。`#[astra::args]` 就是把这两个 derive
  指向了 SDK 自己的那份拷贝。
- **文档注释就是模型会读到的描述。** 工具本身和每个字段都是如此。要写
  的是什么时候该用这个工具，而不是它内部是怎么运作的。
- **处理函数返回 `Result<_, ToolError>`。** 单次调用的失败是*数据*：
  AI 循环会读取它并决定接下来怎么做，所以它是随响应本身传递的，而不是
  作为一个 gRPC 状态码。`?` 对 `serde_json::Error`、`std::io::Error`、
  `tonic::Status` 和 `anyhow::Error` 都能用。
- **`ctx.host()` 始终存在。** 这个上下文携带着 host 客户端、UI 语言，
  以及当前有效的触发器集合；把它克隆进一个后台任务的代价很低，而且它
  永远不会是 `None`。不需要把任何东西藏在锁后面塞进你的结构体里。
- **`h.host().deny("fire_trigger")` 会预设一次拒绝。** 这就是一个没有
  同意的用户的样子，值得为它写一个测试 —— 否则这就是你的问题追踪器
  日后会收到的那种失败。

`cargo test` 会针对一个记录型 host 运行这三个测试：没有守护进程，没有
套接字，没有安装 Astra。

<!-- doctest: illustrative reason="the block above carries test=1, so the doc-test already ran cargo test on it" -->
```bash
cargo test
```

## 4 · 声明你需要的权限

这个工具调用了 `fire_trigger`，而 `[permissions]` 是默认拒绝的，所以
它必须提出申请。`reason` 就是 Astra 请求用户同意时用户会读到的文字 ——
把它写成一句关于*你这个插件*的话，而不是关于这项权限本身的话。

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat, and fire a trigger with the result."
author = "Your Name"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

然后检查它：

<!-- doctest: cli -->
```bash
astra-plugin check --strict
astra-plugin check --fix
```

`check` 用守护进程自己的解析器来读取清单文件 —— 是同一个 crate，作为
vendor 依赖并保持逐字节一致 —— 所以它不可能和安装时实际发生的情况有
分歧。`--fix` 会应用它能证明正确的修正，其余的会报告出来。

## 5 · 运行一致性测试套件

<!-- doctest: cli -->
```bash
astra-plugin test
```

这比 `cargo test`高一个层次：它按照守护进程启动插件的真实方式来启动你的
插件，针对一个提供 `PluginHostService` 的模拟守护进程运行，并调用你已
声明的能力所隐含的每一个入站钩子。

<!-- doctest: output from="astra-plugin test . --no-build, in the dice-roller project this page builds (the plugin's own tracing lines, which go to stderr, are left out)" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] GetPluginTriggerTypes    required  0 trigger type(s)
  [ok  ] CallTool                 required  `roll_dice` answered
  [ok  ] OnActiveTriggers         optional  accepted 0 active trigger(s)
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 40.8ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 775.4µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] Shutdown is honoured within the grace period: the process exited 40.8ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 2 host call(s) reached the daemon: fire_trigger, log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 8 hook(s) exercised, 6 check(s) passed.
```

尽管这个插件会触发一次触发器，`GetPluginTriggerTypes` 仍然报告 **0**。
触发一次和*提供*一个是两回事：命令编辑器列出的是插件所声明的内容，也就
是一个 `#[hook] async fn trigger_types(&self) -> Vec<TriggerTypeDef>`，
而上面这个插件并没有它。用 `--capabilities tools,triggers` 生成脚手架
会替你写好这个钩子；§3 为了让文件保持在一屏之内而省略了它。不声明就
触发，触发器依然会真的触发 —— 只是没有人能把一条命令接到它上面。

一个 `required` 的钩子不能返回 `UNIMPLEMENTED`；一个 `optional` 的
可以，因为在传输层面上 `UNIMPLEMENTED` *就意味着*"这个钩子不存在"。

## 6 · 在 Astra 内部运行它

这一步需要一个正在运行的 Astra，并且需要**开发者模式**，因为它会侧载
(sideload)一个未签名的目录：

<!-- doctest: cli -->
```bash
astra-plugin dev
```

它会运行 `check --strict`、构建、把这个目录交给守护进程 —— 由守护进程
spawn 这个进程、铸造它的令牌、并掌管它的生命周期 —— 然后监视变更、
重新构建、重启，并持续输出日志。

在打开开发者模式之前，请先阅读
[侧载(sideload)](../5-publish/sideload.md)。它是一个开发工具：它会以
你的完整用户权限运行未签名的本地代码，而且这个开关会降低这台机器上*
所有*插件的门槛，不只是这一个。这不是任何人安装插件的方式。

如果 `dev` 无法连接到 Astra，`astra-plugin doctor` 会告诉你这两种情况
中到底是哪一种出了问题 —— 是守护进程没有运行，还是它解析出的配置目录
和 CLI 解析出的不一样。

## 7 · 打包

<!-- doctest: cli -->
```bash
astra-plugin build
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin build ., in the dice-roller project this page builds (the size and the two digests are properties of your build, not constants)" unrun="needs a scaffolded, compiled plugin on disk; re-run it in the project this page builds" -->
```
Building plugin 'dice-roller' v0.1.0 (rust) for linux-x64...
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 0.04s
  Added: README.md (0644)
  Added: bin/dice_roller (0755)
  Added: plugin.toml (0644)
  Built: dice-roller-0.1.0-linux-x64.astraplugin (2757.1 KB, 3 files)
  target:          linux-x64
  artifact sha256: 3ae95e05f49156b137afe4b528dc1feb4df4c36c5e8c284b52b7b15e4f3345fa
  manifest digest: 11b1b78dd55232877c881e862e109ec594aa535167d27063a2e3fcbe373d9824
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
  See https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/publishing.md#what-establishes-trust
```

`verify` 会重新读取 `build` 刚刚写下的内容，并回答一个不同的问题：
`MANIFEST.json` 是不是条目 0 且未压缩存储(stored)、文件列表在两个方向上
是否都是穷尽的、以及列表中每一项的摘要、大小和权限模式是否都和归档内容
匹配。它不会说明是谁写的它 —— 那是注册表的工作。

文件名不是装饰性的：`<id>-<version>-<target>.astraplugin` 是一个已发布
的包必须使用的名字，其中 target 那一段就是注册表的平台键。

**`build` 不会签名，你也不需要密钥。** 让 Astra 决定安装一个插件的，是
一条对整份文件的 sha256 进行反签名的注册表记录 —— 而不是你手上持有的
任何密钥。参见[安全模型](../1-orientation/security.md)。

## 8 · 发布

现在是真正重要的部分了，只有两条命令：

<!-- doctest: cli -->
```bash
astra-plugin init-ci
astra-plugin version 0.1.1
```

`init-ci` 会写出 `.github/workflows/release.yml`，通过 commit SHA 固定
到 Astra 的可复用发布工作流。此后，**打标签就是整个发布流程**：CI 会
构建每一个目标平台，用 GitHub 的构建溯源(provenance)为每个包出具证明，
并把它们附加到一个 GitHub Release 上。

然后只需要一次性提交一次，此后每一次发布都是零接触的。

请注意发布**不是**什么：把这个仓库推送到 GitHub 并不会发布你的插件，
把你刚刚构建出的 `.astraplugin` 发给别人也不会。注册表固定的是 CI 生成
的那份文件的摘要，并读取附加在它上面的构建证明，而在你笔记本上构建出的
文件两样都没有。

**→ [发布插件](../publishing.md)** —— 从这里到一个已上架插件的完整
流程，一页讲完，附带每条命令及其预期输出。它背后的分层页面：
[用 CI 发布](../5-publish/release-with-ci.md) ·
[申请上架](../5-publish/get-listed.md)

## 用 Python 做同样的事

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang python --template tool
```

<!-- doctest: python-plugin -->
```python
"""DiceRoller — an Astra plugin."""

from astra_plugin_sdk import Plugin, tool


class DiceRoller(Plugin):
    """Roll dice from chat."""

    @tool("Roll dice and return the total.")
    async def roll_dice(self, count: int = 1, sides: int = 6) -> str:
        # The parameters ARE the schema: a parameter with no default is
        # required, one with a default is optional, and the type hints become
        # the JSON types the model is shown.
        if sides < 2:
            raise ValueError("a die needs at least 2 sides")
        total = sum(1 + (i % sides) for i in range(count))
        await self.host.fire_trigger("dice_rolled", f'{{"total": {total}}}')
        return str(total)


if __name__ == "__main__":
    DiceRoller().run()
```

入口点是 `[entry] command = "python"`、`args = ["-m", "src.plugin"]`、
`runtimes = ["python"]`，包的类型是 `noarch`。

## 用 TypeScript 做同样的事

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang typescript --template tool
```

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    roll_dice: tool({
      description: "Roll dice and return the total.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs.
      input: s.object({
        count: s.number({ description: "How many dice to roll" }).optional(),
        sides: s.number({ description: "How many sides each die has" }).optional(),
      }),
      run: ({ count, sides }) => {
        const n = count ?? 1;
        const faces = sides ?? 6;
        if (faces < 2) throw new Error("a die needs at least 2 sides");
        let total = 0;
        for (let i = 0; i < n; i++) total += 1 + Math.floor(Math.random() * faces);
        return String(total);
      },
    }),
  },
});

// `astra-plugin build` bundles this to CommonJS, so `require.main` is the
// honest "am I the entrypoint" test. Importing this module — as a test does —
// does not start a server.
if (require.main === module) app.run();
```

## 接下来去哪里

| 如果你想要 | 请阅读 |
|---|---|
| 完整的 Rust API | [Rust SDK](../4-sdk/rust.md) |
| 每一个 `plugin.toml` 键 | [清单参考手册](../reference/manifest.md) |
| 每个 SDK 中的每一个钩子 | [对照表](../reference/parity.md) |
| 想要把它发布出去 | [用 CI 发布](../5-publish/release-with-ci.md) |
| 有什么东西坏了 | [故障排查](../6-operate/troubleshooting.md) |
| 一个完整的实例 | [示例](../7-examples/README.md) —— 共十一个 |
