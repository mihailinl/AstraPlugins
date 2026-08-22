> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/6-operate/performance.md)。如与英文版有出入，以英文版为准。

# 性能与限制

本页的每一个数字都只在一个文件里声明一次，然后生成到需要它的各个地方。
没有一个是靠猜的。

## 共享的限制值

[`spec/limits.yaml`](../../../spec/limits.yaml) 是那些必须在守护进程
和各个 SDK 之间保持一致的数字唯一被写下来的地方。`node
tools/gen-limits.mjs` 会重新生成全部三个 SDK 中的常量，而守护进程那份
拷贝旁边的一个 `const _: () = assert!(…)`，会在守护进程还没同步移动
之前一直让构建失败。促成这一切的那个 bug 是：流式 STT 的音频通道容量
在守护进程里是 500，在 Rust SDK 里却是 32，这个不一致悄悄地把每一段
语音都截断到了它最开头的一小部分。

| 限制 | 值 | 限制的是什么 |
|---|---|---|
| `plugin_start_timeout_secs` | **20** | 从 spawn 到插件的第一行输出。超过这个时间，守护进程就会判定启动失败并回收这个进程 |
| `plugin_stop_grace_secs` | **5** | 从 `Shutdown` 到进程组被 kill 的时间。你自己排空(drain)所需的预算必须小于这个值，否则守护进程会在你的收尾逻辑运行完之前就把你 kill 掉 |
| `stt_audio_channel_capacity` | **500** | 在守护进程的语音管线和你的 `stt` 钩子之间、两端各自缓冲的数据块数量。大约相当于 10 秒音频：最坏情况下的唤醒词种子突发数据，加上一个较慢的提供者仍在推理时持续到达的实时音频 |
| `max_extract_bytes` | **524 288 000**（500 MiB） | 守护进程会从单个归档中解压出的未压缩总大小 |
| `max_archive_entries` | **10 000** | 单个归档中的条目数 |

后两项是针对 zip 炸弹的缓解措施，同时也是打包上的约束：超过其中任何
一项的包会导致插件无法安装，所以 CLI 会在构建时就拒绝它，而不是让你
在用户的机器上才发现这一点。

## `call_timeout_secs` —— 需要你自己设置的那一个

清单文件中的 `plugin.call_timeout_secs` 决定了守护进程在放弃
`CallTool` 和 `ExecuteAction` 之前会等待多久。不设置的话，会使用守护
进程自己的 `PLUGIN_CALL_TIMEOUT`，这个值被刻意设得比"永远等下去"要低。

**一个作为长时间运行智能体(agent)前端的插件，必须声明这个值。** 否则
守护进程会在你的子进程继续运行的同时，把你的结果丢弃 —— 用户看到的是
一次失败，而机器却还在继续干活。

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "coding-agent"
name = "Coding Agent"
version = "0.1.0"
license = "MIT"
author = "You"
# This plugin runs an agent that can legitimately take minutes.
call_timeout_secs = 180

[entry]
command = "bin/coding_agent"

[capabilities]
tools = true
```

这是按插件设置的，就像一个 MCP 服务器的超时是按服务器设置的一样。请
把它设成你最慢的那个合理调用真正需要的时长，而不是你能想到的最大数字：
这个超时同时也是阻止一个卡死的插件把整个对话一起拖住的手段。

## 各语言的启动预算

20 秒已经相当宽松了，但三种语言里有两种依然经常把它用光。

| | 典型的冷启动 | 是什么在消耗这个时间 |
|---|---|---|
| Rust | 毫秒级 | 没有什么值得一提的 |
| TypeScript | Node 的冷启动 | 打包结果是单个文件，所以不存在遍历整棵树做模块解析的开销 |
| Python | 解释器启动 + 导入 `grpcio` | 在模块作用域就导入了一个庞大的依赖 |

在这两种解释型语言上，修复方式是一样的：**把导入延迟到真正需要它的
那个钩子内部。** 在 `on_start` 里加载的模型，是用户在插件真正活起来
之前就要等的模型；在第一次调用时才加载的模型，用户只需要等那一次。

`astra-plugin test` 会在你的机器上测出真实数值，并把它和预算放在一起
打印出来：

<!-- doctest: output from="astra-plugin test . --no-build" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 792.4µs
         (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.5ms after Shutdown
         (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
```

## 在宽限期内完成关闭

响应 `Shutdown` 之后，你就退出。五秒之后，进程组会被 kill。任何你必须
落盘或刷新的东西 —— 一个文件、一个上游会话 —— 要么在这个窗口内完成，
要么就完不成了。

一次整个守护进程范围的关闭，给出的宽限期会**短得多**，受制于整个关闭
流程的总期限。不要把这 5 秒当作一份可以随便花的预算；要把它当作一个
你应该远远留有余量的上限。

## 健康检查

`HealthCheck` 每 15 秒运行一次。它没有经过守护进程的可选钩子辅助函数
路由，所以**任何**错误 —— 包括 `UNIMPLEMENTED` —— 都会把插件标记为
已死亡。如果你要重写它，请让它既廉价又完整：一个会去调用上游服务的
健康检查，会把那个服务的故障，变成你插件被标记为死亡的原因。

## 包的大小

除了解压限制之外，没有任何东西强制规定一个最大值，但有两件事值得
了解：

- 一个 Rust 包是一个经过 strip 的 release 二进制文件，通常只有几
  兆字节。
- 一个 TypeScript 包**不携带** `node_modules` —— `astra-plugin build`
  会产出一个自包含的单一 CommonJS 文件，CI 会断言不存在任何在运行时
  还要去伸手请求某个模块的残留代码。

可复现打包（`--reproducible`）会固定条目顺序、mtime 和压缩级别，使得
用相同输入构建两次得到逐字节相同的结果。发布工作流在每一次发布时都会
运行一个金丝雀测试(canary),这正是让第三方重新构建这件事变得有意义的
原因。

## 这些数字都写在哪里

| 数字 | 声明于 |
|---|---|
| 上面那五个 | [`spec/limits.yaml`](../../../spec/limits.yaml) |
| `call_timeout_secs` | 你的 `plugin.toml` —— [参考手册](../reference/manifest.md) |
| 健康检查的间隔、单次调用超时的默认值 | 守护进程 |
