> **本文档为翻译版本。** 权威来源是 [docs/en](../en/versioning.md)。如与英文版有出入，以英文版为准。

# 版本管理与弃用策略

这些数字各自代表什么、你所依赖的东西被保证能继续正常工作多久，以及那份保证是
写在数据里，而不是靠某个人记住的口头承诺。

## 四个数字，其中只有一个属于 SDK 本身

| 数字 | 位于何处 | 告诉你什么 |
| --- | --- | --- |
| **SDK 版本** | `astra-plugin-sdk/Cargo.toml`、`astra-plugin-sdk-python/pyproject.toml`、`astra-plugin-sdk-ts/package.json` | 你所编写代码所依据的那套创作 API。每个包各自维护自己的版本 |
| **发布列车(release train)** | `sdk-v<VERSION>` 这个 git 标签 | 一个标签同时发布全部三个 SDK。这个标签名的是 **Rust crate** 的版本号 |
| **协议版本** | `proto/PROTO_VERSION`（`protocol=1`），在每个 SDK 中都以 `PROTOCOL_VERSION` 的形式镜像 | 插件与守护进程之间的通信契约 |
| **你插件的版本** | 你的 `plugin.toml` | 属于你自己。注册表以它来给各个发布排序 |

三个 SDK 的版本号被有意地保持不一致。当前的发布列车是 `sdk-v0.7.0`，它发布的
是：

| 包 | 注册表 | 版本 |
| --- | --- | --- |
| `astra-plugin-sdk`（Rust） | crates.io | 0.7.0 |
| `astra-plugin-macros` | crates.io | 0.7.0 —— 由于 SDK 按版本号依赖它，所以**先于** SDK 发布 |
| `astra-plugin-sdk`（Python） | PyPI | 0.6.0 |
| `astra-plugin-sdk`（TypeScript） | npm | 0.6.0 |

版本号回答的是"我正在针对哪个 API 编写代码"这个问题，所以破坏性发布更少的
包，其版本号也就更小。这条发布列车所保证的是：共享同一个标签的各个包说的是
**同一套协议**，实现的是同一批钩子(hook)—— 这正是 `spec/hooks.yaml` 和
一致性检查器(parity checker)存在的意义。

## 0.x 阶段的 SemVer 解读

三个包目前都在 1.0 以下，遵循 SemVer 对 0.x 阶段的解读方式：

- **minor**（`0.5 → 0.6`）—— 可能破坏源码兼容性。请阅读 CHANGELOG。
- **patch**（`0.6.0 → 0.6.1`）—— 只包含 bug 修复和新增内容。如果一次 patch
  发布导致你的插件无法编译，那是 SDK 的 bug，请提交问题反馈。

协议版本是独立的，按自己的节奏推进。它是一个整数，不是 SemVer，对它适用的
规则不是"去读更新日志"，而是一套机制：

- 对端没有的钩子会返回 `UNIMPLEMENTED`，协议将其定义为*不存在*。守护进程
  正是这样理解并继续运行的。这就是为什么更新的插件能在更旧的守护进程上运行，
  反之亦然。
- 每个 SDK 中的 `MIN_SUPPORTED_DAEMON_PROTOCOL` 是该 SDK 愿意注册的最旧
  守护进程版本。低于这个版本，插件会在第一次调用失败之前就直接退出，并
  给出一句指明修复方法的话。

## 弃用策略

当创作 API 中的某样东西即将退场时：

1. **它至少会被弃用两个 minor 版本，且至少一个自然季度，取两者中较长的
   一个。** 在 0.6 中被弃用意味着可以在 0.8 中被移除，且不会早于三个月
   之后。今天能构建的插件，至少还能在一个你可以提前规划的发布周期内
   继续构建成功。
2. **弃用说明会指名替代方案。** 不是"已弃用"，也不是"请使用新 API"，而是
   你应该实际输入的那个标识符，或者明确写出*没有替代方案*以及原因。一个
   只让你停下来却不告诉你该往哪走的弃用提示，只会把你送去问题追踪器。
3. **移除操作记录在移除该内容的那个包的 CHANGELOG 中的 `BREAKING` 标题
   下**，指名被移除的是什么、被什么取代。任何 patch 发布都不会移除任何
   东西。

各语言中"已弃用"的表现形式：

| | 如何标记 | 你会看到什么 |
| --- | --- | --- |
| Rust | `#[deprecated(since = "0.6.0", note = "…")]` | 在使用处出现编译器警告，附带说明 |
| Python | 调用处的 `DeprecationWarning` | `python -W error::DeprecationWarning` 可以把它变成能在 CI 中卡住的失败 |
| TypeScript | `/** @deprecated … */` | 编辑器中的删除线，以及悬停时显示的说明 |

弃用只是警告，永远不是错误。如果某次发布导致已弃用的代码*无法编译*，那就是
一次移除，而移除遵循规则 3。

### 目前已被弃用的内容

| 内容 | 弃用于 | 移除于 | 替代方案 |
| --- | --- | --- | --- |
| Rust：整个 0.5 trait 接口，作为 `astra_plugin_sdk::compat` | 0.6.0 | 0.8.0 | `PluginCapability`（0.6）：`&PluginContext`、`Result<_, ToolError>`、`type Config`。参见 [migration-0.6.md](migration-0.6.md) |
| Rust：`PluginCapability::source_id()` | 0.6.0 | 0.8.0 | 把 id 传给 `Host::send_chat_message`；守护进程已不再按 source id 过滤 |
| Rust：`compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.6.0 | 0.8.0 | `Result<String, ToolError>` |
| Rust：`compat::HostClient` / `DaemonClient` 别名 | 0.6.0 | 0.8.0 | `ctx.host()` / `ctx.daemon()` |
| Python：在期望某个能力(capability)数据类的地方使用 `dict` | 0.5.0 | 0.7.0 | 对应的数据类 —— `VoiceInfo`、`ToolDef` 等 —— 或其 `to_proto()` |
| TypeScript：`UiPanel` 类型别名 | 0.5.0 | 0.7.0 | `UiContribution` |
| 钩子：`AiGetModels` | 0.6.0 | 0.8.0 | 没有替代方案 —— 守护进程不会向插件询问它有哪些模型 |

两条附注，因为它们正是这项策略要防止的那类情况：

- Python 中针对 dict 的 `DeprecationWarning` 说它"还会被再接受一个 minor
  版本"。**具有约束力的数字以表格为准**：两个 minor 加一个季度，所以最早
  也要到 0.7.0。
- `UiPanel` 在 TypeScript 中被弃用时完全没有记录版本号。这里把它标注为
  0.5.0 —— 这是第一个以书面形式说明这件事的发布版本 —— 从 0.7.0 起可以
  移除。

## 策略即数据

只存在于文档中的规则，恰恰会在最关键的那一刻被忘记：也就是有人要删掉那样
东西的那次发布。所以这项策略中按钩子(hook)划分的那一半，是
[`spec/hooks.yaml`](../../spec/hooks.yaml) 中的一列：

<!-- doctest: illustrative reason="one row of spec/hooks.yaml, quoted; the file it belongs to is the source of truth and is checked by tools/parity/check.py" -->
```yaml
  - rpc: AiGetModels
    ...
    routing: deprecated
    deprecated_in: "0.6"
    removed_in: "0.8"
    note: "… Deprecated in 0.6, removed in 0.8, and there is no replacement: nothing in the daemon asks a plugin what models it has, and AiComplete carries the chosen model on the request."
```

`tools/parity/spec.py` 在每次解析时都会校验这一点 —— 也就是说，每次运行
`gen.py`、每次运行 `check.py`，因而也就是每次 CI 运行时都会校验：

| 规则 | 它防止的失败情形 |
| --- | --- |
| `routing: deprecated` 要求存在 `deprecated_in` | 一个"已弃用"了好几年却没有附带日期的钩子 |
| `deprecated_in` 要求存在 `removed_in` | 一个没有终点的弃用，那不过是一句不礼貌的注释 |
| `removed_in` ≥ `deprecated_in` + 2 个 minor | 一次移除在任何人还没有一个发布周期可用于迁移之前就落地 |
| 已弃用行的 `note` 指名了另一个 rpc，或者说明 `no replacement` | 一句"已弃用"却没有留下任何转发地址 |

只要写错一处，检查器就会连同行号一起指出来：

<!-- doctest: illustrative reason="the failure `tools/parity/check.py` prints for a hooks.yaml row that violates the removal policy; no such row exists in the tree, so producing it means editing hooks.yaml first" -->
```
spec/hooks.yaml is malformed:
  hooks.yaml:336: `AiGetModels` is deprecated in 0.6 and removed in 0.7 — the policy is
  2 minors and one quarter minimum, so the earliest removal is 0.8
```

这些列中的版本号是 **SDK 的 minor 版本号**，不是协议版本号：`0.6` 就是你
`Cargo.toml` 里的那个数字，也是 CHANGELOG 标题下归档所用的那个数字。这项
策略里"一个季度"的那一半靠的是日历而不是数据 —— 由发布列车定下具体日期，
而这份文档就是记录它的地方。

## 这一切都不覆盖的内容

- **守护进程自身的行为。** Astra 的 UI、它的配置布局、它的内部服务，都
  不是插件 API。插件可以依赖的只有协议、`spec/hooks.yaml` 中的钩子，以及
  清单文件中的权限。
- **任何标记为 `#[doc(hidden)]`、`_private`，或专为测试工具导出的内容。**
  这些可以在 patch 版本中改变。
- **`unrouted` 的钩子。** 一个钩子可以同时存在于 proto 和全部三个 SDK 中，
  却在守护进程里没有任何调用点 —— 今天 `TtsSynthesizeStream` 就是这样。
  实现它是安全的，也不会有任何代价；但*依赖*守护进程会去调用它，在其
  `routing:` 变为 `live` 之前是不受支持的。

## 如果弃用窗口不够用

请在窗口关闭之前提出来。已经落地的移除就是移除；但只要还停留在
`spec/hooks.yaml` 里的 `removed_in` 字段中，它就只是一个日期，而只要有人
及时说明理由，日期是可以调整的。
