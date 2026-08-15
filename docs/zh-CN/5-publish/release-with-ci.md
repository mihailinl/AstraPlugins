> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/5-publish/release-with-ci.md)。如与英文版有出入，以英文版为准。

# 用 CI 发布

**打标签就是整个发布流程。** 一条命令就能把它设置好，此后你再也不需要
手动构建包。

本页的一切都从 `astra-plugin` 这个二进制文件开始。如果你还没有它，
请先[安装 CLI](../install-cli.md) —— 一行 `cargo install` 命令，
需要 Rust 工具链，目前还没有预编译二进制文件。如果你想要的是完整流程
一页讲完，而不是这一个分层，请参见
[发布插件](../publishing.md)。

## 为什么不能就 `astra-plugin build` 然后自己上传呢？

因为没有任何东西能为你在自己笔记本上构建出的文件背书。注册表读取的是
GitHub 的**构建证明** —— 一个从工作流的 OIDC 身份铸造出来的
Sigstore 无密钥(keyless)签名 —— 它声明*正是这些字节，来自那个工作流，
在那个 commit，在那个仓库*。手动构建的包没有这样的东西，无论它写得多
好都会被拒绝 —— 明确地以 `E_ATTESTATION_MISSING` 的名义。

出于同样的原因，**把你的源码推送到 GitHub 不是发布**，把你在本地构建
出的 `.astraplugin` 发给别人也不是。注册表从不读取你的源码树；它读的
是一次带标签发布上的资产，并以摘要值来固定它们。

你不需要，也不会被要求提供签名密钥。参见
[安全模型](../1-orientation/security.md)。

## 1 · 写出工作流

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned e3329df252a46d747676cb540ae4b986af68a3ad (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

**这在今天是可用的，而且其中每一半都是可以核实的。**
`.github/workflows/plugin-release.yml` 在 `mihailinl/AstraPlugins`
的默认分支上 —— `git ls-tree -r master --name-only
.github/workflows` 能列出它 —— 而且发布用的标签也存在：
`git ls-remote --tags origin` 会把 `plugin-release/v1` 解析为
`e3329df252a46d747676cb540ae4b986af68a3ad`。因为这个标签存在，
`init-ci` 固定的是那个 commit，而不是一个会移动的分支头，它也不再打印
本页早期版本引用过的"Not verified"提示。

那个 SHA 和注册表经根签名的 `trust.json` 在构建证明中所允许的那个是
同一个 —— `astra-registry` 中的
`node tools/sign-trust.mjs --verify registry/v1/trust.json` 会在
*允许的可复用工作流 SHA* 下把它打印出来。由任何其他工作流产出的构建，
在摄入(ingest)时都会被以 `E_WORKFLOW_NOT_ALLOWED` 拒绝，所以这个固定
值不是一个可有可无的修饰；它正是让你的证明对注册表有实际意义的关键。

每当有更新的 `plugin-release/vN` 发布时，随时重新运行 `init-ci`；它
会保留你的输入，只移动固定值。

这就是作者这一侧 CI 的全部内容。之所以这么短，是因为它把工作委托了
出去：

<!-- doctest: illustrative reason="the file `astra-plugin init-ci` writes; it lives in the author's repository, not in this one, and its pin is resolved at generation time" -->
```yaml
name: Release

on:
  push:
    tags: ["v*"]

# Required, and required HERE: a reusable workflow can only reduce the
# permissions its caller granted, never grant itself more. Leave all three.
permissions:
  contents: write       # create the Release and upload assets
  id-token: write       # mint the OIDC token that makes signing keyless
  attestations: write   # store the build attestation on GitHub

jobs:
  release:
    # Pinned by commit SHA, not by a moving tag: whoever can move
    # `plugin-release/v1` in mihailinl/AstraPlugins would otherwise own the build
    # step of every plugin that trusts it — and that build step runs in YOUR
    # repository with the token above. `astra-plugin init-ci` keeps this current.
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@e3329df252a46d747676cb540ae4b986af68a3ad  # plugin-release/v1
    with:
      plugin-dir: .
      tag-prefix: "v"
      linux-packages: ""      # e.g. "libasound2-dev pkg-config" for audio plugins
    # No `secrets: inherit`, deliberately. This workflow declares no secrets,
    # so the job that runs your build.rs and your npm lifecycle scripts has
    # nothing to leak.
```

想要推进这个固定值，重新运行 `init-ci` 即可；它会保留你已经设置的
输入值。`--offline` 会保留文件里已有的固定值，`--ref <sha-or-ref>`
则可以固定到某个特定的值。

## 2 · 打标签

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

`astra-plugin version` 会在一次编辑中同时重写 `plugin.toml` **以及**
项目中其他所有清单文件 —— `Cargo.toml`、`package.json`、
`pyproject.toml` —— 所以它们不会互相矛盾。除非你传入
`--allow-downgrade`，否则它会拒绝一个排序低于当前版本的版本号，因为
Astra 拒绝安装降级版本，那样的发布将无法被安装。

标签必须匹配 `tag-prefix` 加上清单文件中的版本号，CI 会在构建任何东西
之前断言这一点。`astra-plugin version` 会打印出应该使用的确切标签：

<!-- doctest: output from="astra-plugin version 0.2.0" unrun="rewrites every manifest in a plugin project; re-run it in your own plugin" -->
```
Setting version to 0.2.0 (plugin.toml was 0.1.0)
  plugin.toml                    [plugin] version           0.1.0 -> 0.2.0
  Cargo.toml                     [package] version          0.1.0 -> 0.2.0
  2 file(s) rewritten

Release it:
  git commit -am "release 0.2.0"
  git tag v0.2.0
  git push && git push --tags

  The tag must be exactly 'v0.2.0': the release workflow asserts it
  against plugin.toml before it builds anything.
```

## 3 · CI 做了什么

这一节描述的是 `.github/workflows/plugin-release.yml`，按照它在这个
仓库的 `master` 分支上、`plugin-release/v1` 所指向的那个 commit 处的
写法来说明 —— 也就是你的 `release.yml` 所调用的那个 commit。

三个 job，这种拆分正是安全属性所在。

| Job | 运行你的代码 | 持有写入令牌 | 它做什么 |
|---|---|---|---|
| **plan** | **否** | 是 | 用 Python 的 `tomllib` 把 `plugin.toml` 当作*数据*读取，检查标签是否等于版本号，决定构建矩阵，创建草稿 Release |
| **build**（矩阵） | 是 | **否** | `astra-plugin check --strict`、`astra-plugin build`、验证、解包，断言 glibc 下限和 TypeScript 包的自包含性 |
| **publish** | 否 | 是 | 自己重新推导每一个摘要值，写出 `SHA256SUMS.txt`，出具证明，上传，把 Release 从草稿状态转正 |

`plan` 从不执行仓库之外的任何东西 —— 没有子模块，没有持久化在
`.git/config` 中的凭证。`build` 会运行你的 `build.rs` 和你的生命周期
脚本，但没有令牌可供窃取。`publish` 会下载各个构件，自己对它们计算
哈希，并为自己哈希过的内容出具证明。

矩阵是根据你插件所用的语言决定的：Rust 是 `linux-x64` +
`windows-x64`，TypeScript 和 Python 是单一的 `noarch` 分支。

### 最终落在 Release 上的内容

| 资产 | |
|---|---|
| `<id>-<version>-linux-x64.astraplugin` | 每个平台键各一个 |
| `<id>-<version>-windows-x64.astraplugin` | |
| `<id>-<version>.sigstore.jsonl` | 证明包，好让一个连不上 GitHub 网络的用户依然能做检查 |
| `SHA256SUMS.txt` | 和注册表所记录的相同的摘要值 |

只有当所有资产都已附加后，这个 Release 才会变为可见。

### 出具证明需要一个公开仓库

构建证明会发布到一个公开的透明日志(transparency log)中；在私有仓库上
需要 GitHub Enterprise。这个工作流会解析你仓库的可见性，当它不是公开
的时候，会在 job 摘要中说明这一点，并产出**没有证明**的包 —— 而注册表
不会上架这样的包。这是一个真实存在的限制，它会大声报错，而不是产出一个
看起来没问题的发布。

### 可复现性(Reproducibility)

`astra-plugin build --reproducible` 会断言打包过程是确定性的：条目
排序固定、mtime 固定、压缩级别固定。用相同的输入构建两次，会产出相同
的 sha256。CI 在每一次发布时都会运行一个可复现性金丝雀测试
(reproducibility canary)，这正是让第三方重新构建这件事变得有意义的
原因。

## 4 · 自己核实

任何人都可以在不信任 Astra 或注册表的情况下核实一次发布：

<!-- doctest: cli -->
```bash
gh attestation verify dice-roller-0.2.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.2.0-linux-x64.astraplugin
```

`astra-plugin verify` 会读取包本身，并打印出它发现的内容：

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" unrun="needs that exact bundle, which is a build artefact and is not committed anywhere" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
  schema:          astra.bundle/2
  plugin:          dice-roller v0.1.0
  target:          linux-x64 (os=linux, arch=x86_64)
  protocol:        1
  capabilities:    tools
  entry:           ./bin/dice_roller
  permissions:     sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
  artifact sha256: 7f77e3f02a83fdcad96e62b9748c3265b6506e9800e432d0270009bdb4c9fbc3
  manifest digest: a2cc2e1bd38538ca5f087fd0f00efd74328b5b5852c6144ead3849c74e86980d
  size:            2730916 bytes (2666.9 KB)
  legacy in-ZIP signature: absent

  4 listed files:
    0644       1063  a9288520e75b02d6  README.md
    0755    8729640  982348bb71764594  bin/dice_roller
    0644       2509  70e9035f388492b0  icon.svg
    0644       1334  acb85afb406f182c  plugin.toml
  1 unlisted entries: MANIFEST.json

  OK — MANIFEST.json is entry 0 and stored, the file list is exhaustive in both
       directions, and every listed digest, size and mode matches the archive.
```

这里的退出码很重要，每一个发布工作流都会据此分支处理：**1** 表示包本身
有问题，**2** 表示 CLI 无法给出答案（比如文件缺失）。归档格式，以及
校验器必须拒绝的内容，见 [`spec/bundle-v2.md`](../spec/bundle-v2.md)。

## 5 · 然后申请上架

只需一次。→ [申请上架](get-listed.md)。

## 常见问题

| 症状 | 原因 |
|---|---|
| 工作流根本没有启动 | `on: push: tags:` 与 `tag-prefix:` 互相矛盾。一个比前缀更窄的 glob 永远不会触发 |
| "tag does not match the manifest version" | 打标签之前先运行 `astra-plugin version <v>` 并提交 |
| Linux 构建因为缺少头文件而失败 | 在调用方的工作流中设置 `linux-packages: "libasound2-dev pkg-config"` |
| 包没有证明 | 仓库是私有的 |
| 首次启动时出现 `MODULE_NOT_FOUND` | 有一个打包工具没能追踪到的 TypeScript 依赖。CI 会对此进行断言；检查一下打包工具的 externals 配置 |
| 用户机器上出现 glibc 错误 | 归档中有某样东西需要高于 `GLIBC_2.39` 的符号版本。CI 也会对此进行断言 |
| 在任何 job 开始之前就出现 `invalid value workflow reference` | 固定值指名的那个 commit 不携带 `plugin-release.yml`。重新运行 `astra-plugin init-ci` 以重新固定到 `plugin-release/v1` |
| 注册表以 `E_WORKFLOW_NOT_ALLOWED` 拒绝这次发布 | 构建没有运行那个被固定的 Astra 可复用工作流。重新运行 `init-ci`，重新打标签，让 CI 重新构建 |

更多内容：[故障排查](../6-operate/troubleshooting.md)。
