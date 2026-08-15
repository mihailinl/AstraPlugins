> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/1-orientation/architecture.md)。如与英文版有出入，以英文版为准。

# 架构

插件进程是如何启动的、它如何证明自己的身份，以及两个 gRPC 服务中哪个
承载哪种调用。

## 进程模型

<!-- doctest: illustrative reason="an ASCII diagram of the two services, not code" -->
```
   ┌──────────────────────────┐                  ┌──────────────────────────┐
   │      Astra daemon        │                  │     your plugin          │
   │                          │   spawns with    │     (a separate OS       │
   │  plugin manager ─────────┼──── argv ───────▶│      process, your       │
   │                          │                  │      user account)       │
   │                          │                  │                          │
   │  PluginHostService       │◀── plugin calls ─┤  HostClient              │
   │  (the daemon serves)     │   x-session-token│                          │
   │                          │                  │                          │
   │  capability client ──────┼── daemon calls ─▶│  PluginCapabilityService │
   │                          │   x-plugin-token │  (your plugin serves)    │
   └──────────────────────────┘                  └──────────────────────────┘
             both ends are gRPC over loopback TCP
```

守护进程用四个参数把这个进程 spawn 出来。以下是从一次真实的
`astra-plugin test` 运行中复制出来的确切命令行：

<!-- doctest: output from="astra-plugin test . --no-build, in a scaffolded plugin" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
target/release/dice_roller --daemon-addr=127.0.0.1:46495 --plugin-id=dice-roller \
  --auth-token=mock-daemon-spawn-token --capabilities=tools
```

这些参数由 SDK 替你解析。`--auth-token` 是其中最值得关注的一个：它是
守护进程为这次 spawn 铸造的一个密令(secret),并且在**两个**方向上都会
用到。

## 启动顺序

SDK 会执行一个固定的顺序（`astra-plugin-sdk/src/runner.rs`）：

<!-- doctest: illustrative reason="the startup order as prose, quoted from runner.rs" -->
```
bind → register → build ctx → on_config → on_language_changed → on_start → serve
```

- **在 register 之前 bind**，因为守护进程会在 `Register` 期间被告知
  端口号，并可能立即回调。此时监听器已经启动，所以那些调用会排进
  accept 的积压队列，而不是被拒绝。
- **在 `on_start` 之前执行 `on_config`**，因为启动后台循环的插件需要
  先拿到自己的设置。
- **在 `serve` 之前执行 `on_start`**，并且它返回 `Err` 会中止启动：
  一个无法完成自己工作的插件，绝不能让守护进程误以为它是健康的。

有两个数字为此设定了边界，都在
[`spec/limits.yaml`](../../../spec/limits.yaml) 中只声明一次，然后生成
进每个 SDK：

| 限制 | 值 | 超出时会发生什么 |
|---|---|---|
| `plugin_start_timeout_secs` | 20 | 守护进程判定启动失败，并回收该进程 |
| `plugin_stop_grace_secs` | 5 | `Shutdown` 之后，进程组会被 kill |

## 握手过程

1. 守护进程带着 `--auth-token=<spawn token>` 把进程 spawn 出来。
2. 插件在一个由操作系统分配的 loopback 端口上绑定一个 gRPC 服务器。
3. 插件调用 `PluginHostService.Register`，出示 spawn token、自己的端口、
   协议版本和能力列表。
4. 守护进程回应一个**会话令牌(session token)**。
5. 此后每一次插件 → 守护进程的调用，都会在 `x-session-token` 元数据
   头中携带这个会话令牌。`Register` 是唯一的例外路径
   （`astra-plugin-sdk/src/auth.rs`）；任何其他不带它的调用都会得到
   `unauthenticated`。

一次针对 `astra-plugin test` 启动的模拟守护进程的真实注册过程：

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
INFO astra_plugin_sdk::runner: Starting plugin 'dice-roller', connecting to daemon at 127.0.0.1:46495
INFO astra_plugin_sdk::runner: Plugin gRPC server listening on port 41627
INFO astra_plugin_sdk::runner: Registering with capabilities: ["tools"]
INFO astra_plugin_sdk::runner: Registered successfully. Daemon version: mock, protocol: 1 (accepts 0+)
```

### 反方向

守护进程 → 插件方向使用的是*同一个* spawn token，在每次调用时通过
`x-plugin-token` 头发回给插件。你的能力服务端(capability server)会
检查它，而这部分工作 SDK 已经替你做好了。

**这不是你需要配置的东西。** 守护进程会在你插件的环境中设置
`ASTRA_PLUGIN_CAPABILITY_AUTH=require`，告诉 SDK 拒绝任何不携带该
令牌的能力调用。这是守护进程在宣告自己那一半的行为，而不是靠谁去
比对版本号：一个老到不会发送这个头的守护进程根本不会设置这个变量，
此时 SDK 会保持在 `CapabilityAuth::Warn` 状态 —— **错误**的令牌会被
拒绝，**缺失**的令牌会被接受并附带一条警告 —— 这样你的插件在那样的
守护进程上依然能正常工作。

这一点之所以重要，是因为 loopback 并不是一道边界。你的能力服务端监听
在 `127.0.0.1` 上的一个由操作系统分配的端口，以你的用户身份运行的每一个
进程都能找到它。如果没有这个头，找到它就足以调用 `CallTool`、
`OnConfigChanged`（把你的 API 基础 URL 重新指向别人的主机，随后你的
插件就会把真实凭证发送到那里去）,或者 `Shutdown`。

`astra-plugin test` 设置的是同一个变量，出示的也是同一个令牌，所以你在
本地测试的内容，就是在用户机器上实际运行的内容。

## 两个服务

| | `PluginCapabilityService` | `PluginHostService` |
|---|---|---|
| 由谁提供 | 你的插件 | 守护进程 |
| 由谁调用 | 守护进程 | 你的插件 |
| 受什么管辖 | `[capabilities]` | `[permissions]` |
| 钩子数量 | 25 | 10 |

`PluginService` —— proto 中的第三个服务 —— 由守护进程提供给 Astra 的
UI。插件从不会调用它；`astra-plugin dev` 和 `astra-plugin logs` 会
作为本地客户端调用它。

每个钩子及其对应的能力(capability)、权限(permission)、是否为必需，以及
调用它的守护进程源码行：见[对照表](../reference/parity.md)。

## 健康检查、关闭与重启

- `HealthCheck` 每 15 秒运行一次，并且**不被**视为可选的：它返回的任何
  错误，包括 `UNIMPLEMENTED`，都会把插件标记为已死亡。
- 响应 `Shutdown` 之后，你就退出。宽限期是 5 秒。
- 处理函数中的 panic 会被捕获并作为错误返回，而不是穿透 gRPC 服务器
  向上展开（`astra-plugin-sdk/src/panics.rs`）。panic 依然是一个 bug；
  只是它不会造成服务中断。

## 配置

插件的设置是 JSON 格式，由守护进程存储，并根据你 `[config]` 段中的
JSON Schema，在 Astra 的设置界面中被编辑。守护进程会通过
`OnConfigChanged` 把它送达，插件也可以通过 `GetPluginSelfConfig` 主动
询问 —— 这是不需要权限的四个调用之一。

全新安装时收到的第一份负载是 `{}`，这就是为什么 SDK 的配置类型会给
每个字段设置默认值。参见
[配置字段](../3-reference/config-fields.md)。

设置文件位于 `<astra config dir>/plugins/<id>/config.json`
（[平台](platforms.md) 中列出了各操作系统对应的目录）。它**能在更新中
存活**——更新的过程是先停止、再安装、再启动，而以前 install 会对用户
设置所在的目录执行 `remove_dir_all`；现在守护进程会保留这个文件，并在
一个测试中断言这一点（`config_survives_update`，
`astra-daemon/src/plugins/manager.rs`），打包进新压缩包中的副本无法
覆盖它。但它**无法在卸载中存活**：`uninstall_plugin` 最终会执行
`remove_dir_all`。任何需要比卸载活得更久的东西，都应该放在你自己拥有的
其他地方。

## 各部分位于何处

| 内容 | 路径 |
|---|---|
| `plugin.toml` 的模式(schema) | `astra-plugin-cli/vendor/astra-plugin-manifest/` —— 与守护进程所用 crate 逐字节相同的一份拷贝 |
| 通信线路(wire) | [`proto/plugin.proto`](../../../proto/plugin.proto)，从 Astra 的 `astra.proto` 生成出的一部分 |
| 钩子表 | [`spec/hooks.yaml`](../../../spec/hooks.yaml) |
| 共享的数值 | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| 包(bundle)格式 | [`spec/bundle-v2.md`](../spec/bundle-v2.md) |
