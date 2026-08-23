> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/3-reference/README.md)。如与英文版有出入，以英文版为准。

# 参考手册

两个层次，它们之间的区别很重要。

## 生成的内容 —— 不可能产生偏差

这些内容由 [`tools/docgen`](../../../tools/docgen/) 从它们所描述的代码
生成，CI 会运行 `python3 tools/docgen/gen.py --check`：如果签入仓库的
页面和重新生成的结果不一样，构建就会失败，并附带一份差异。CLI 那一页是
通过*运行* `astra-plugin --help` 生成的，而不是解析 `main.rs`，因为再
写一个 clap derive 宏的解析器，只会多一个可能悄悄和工具本身产生分歧的
东西。

它们位于上一级目录 [`../reference/`](../reference/) 中，也就是生成器
写入的位置。

| 页面 | 生成自 |
|---|---|
| [`plugin.toml`](../reference/manifest.md) | `astra-plugin-manifest` —— 守护进程用来解析清单文件的 crate |
| [CLI](../reference/cli.md) | `clap` 的定义，通过运行这个二进制文件生成 |
| [协议](../reference/protocol.md) | [`proto/plugin.proto`](../../../proto/plugin.proto) |
| [错误](../reference/errors.md) | 三个 SDK 中共有的错误分类 |
| [钩子对照表](../reference/parity.md) | [`spec/hooks.yaml`](../../../spec/hooks.yaml) —— 35 个钩子，3 个 SDK |

按 SDK 分别渲染、但源自同一份规格的钩子表：
[Rust](../hooks/rust.md) · [Python](../hooks/python.md) ·
[TypeScript](../hooks/typescript.md)。

## 手写的内容 —— 由人来审阅

有两页描述的是任何生成器都无法从类型定义里读出来的东西：一项权限对被
要求授予它的用户来说*意味着*什么，以及被统称为"config"的三种不同东西
是如何配合在一起的。

| 页面 | |
|---|---|
| [权限](permissions.md) | 每个 id 各自授予什么，以及如何写 `reason` |
| [配置与设置字段](config-fields.md) | `[config]`、带类型的设置、TTS/STT 的字段钩子 |
| [本地化](localisation.md) | `locales/<code>.json`、`$key` 标记，以及英文校验在哪里生效 — **仅有英文版** |

这两页上的每一段代码示例，都会在 CI 中由
[`docs/tools/doctest.py`](../../tools/doctest.py) 执行。

## 规范性规格说明

面向要实现校验器(verifier)、打包工具或注册表的人，而不是面向插件作者。
这些是带有黄金向量(golden vectors)的 RFC 2119 文档，不是使用指南。

[Bundle v2](../spec/bundle-v2.md) · [Registry index](../spec/registry-index.md) ·
[Permissions](../spec/permissions.md)
