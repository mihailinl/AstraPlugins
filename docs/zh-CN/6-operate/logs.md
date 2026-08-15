> **本文档为翻译版本。** 权威来源是 [docs/en](../../en/6-operate/logs.md)。如与英文版有出入，以英文版为准。

# 日志

一个插件的输出可能落到三个不同的地方，弄清楚是哪一个能帮你省下一小时。

| | 去向哪里 | 谁能看到 |
|---|---|---|
| `tracing::info!` / `logging.info(...)`（SDK 的日志桥接） | 作为 `PluginLog` 转发给守护进程，**同时**也进 stderr | 你*和*用户，在 Astra 的日志面板中 |
| `ctx.host().log_info(...)` —— 显式调用 | 守护进程 | 你和用户 |
| `println!` / 裸露的 stderr | 进程自己的 stdout/stderr，由守护进程捕获 | 你，通过 `astra-plugin logs` |

在这座桥接建成之前，这两拨内容是完全分开的两个集合，而那些真正有意思
的行 —— 一次 panic、一个失败的请求、一次重试 —— 几乎总是落在用户看
不到的那个集合里。

## 阅读日志

<!-- doctest: cli -->
```bash
astra-plugin logs
astra-plugin logs dice-roller -f
astra-plugin logs dice-roller -n 500 --daemon-addr 127.0.0.1:32000
astra-plugin logs --json
```

不指定 id 时，它会从 `--path` 所在的清单文件中读取 `plugin.id`。这对
**已安装**的插件有效，而这正是 `astra-plugin dev` 完全无法覆盖的情形。

守护进程为每个插件保留一个**有上限的环形缓冲区**，`GetPluginLogs` 是
对它的一次一元(unary)调用 —— 所以 `-f` 其实是每 750 毫秒一次的轮询，
所谓"新"的行，就是这次尾部输出中没有延续上一次的那部分。重启会清空
这个缓冲区。

请求比缓冲区容量更多的行数是无害的。`--json` 会打印一份文档然后退出，
这是快照形式；`-f` 和 `--json` 搭配在一起没有意义。

## SDK 转发什么、不转发什么

SDK 安装的 `tracing` 层会转发给守护进程：

- 默认转发 **`INFO` 及以上**级别。`ASTRA_PLUGIN_LOG_LEVEL` 可以改变
  这一点；`DEBUG` 属于 `RUST_LOG` 和 stderr，因为那个面板是给用户
  看的。
- **不转发**传输层的堆栈 —— `h2`、`hyper`、`tonic`、`tower`、
  `rustls`、`tokio`。发出一条日志本身就是一次 RPC 调用，而一个会
  记录日志的 RPC 又会产生一条日志：如果没有这个排除机制，`h2` 的一条
  `WARN` 就会变成一个无限循环。
- **不会超过队列的容量。** 这个通道是有界的，发送是非阻塞的，所以一个
  陷入热循环的插件会丢弃日志行，而不是把背压(back-pressure)反推到自己
  的处理函数、进而反推到守护进程身上。

### Python

`install_logging_bridge()` 会以同样的方式路由标准库的 `logging`
模块。请用它，而不是 `print`：SDK 会把 stdout 重新配置为**行缓冲**
模式，因为守护进程的监督进程要读取 stdout 来确认插件还活着，而块
缓冲的输出曾经导致监督进程在启动超时时把健康的插件也一并回收掉。

## 打开 CLI 自身的跟踪日志

`RUST_LOG` 控制的是 `astra-plugin` 本身。这个变量从 0.1 版本起就有
文档记录，但在安装订阅者(subscriber)之前一直什么作用都没有 —— CLI
及其依赖发出的每一个 `tracing` 事件都无处可去。

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

默认级别是 `warn`，输出到 **stderr** —— CLI 面向用户的输出在
stdout 上，如果跟踪日志也混进去，就会破坏 `--json` 的文档格式。

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Why do I see no trace output from the CLI?
         RUST_LOG is unset, so only warnings and errors are printed.
         `RUST_LOG=astra_plugin=debug` turns on this CLI's own trace;
         `RUST_LOG=debug` turns on its dependencies' too.
```

## 磁盘上的文件

| | Linux | Windows |
|---|---|---|
| 守护进程日志 | `~/.config/astra/logs/` | `%APPDATA%\astra\astra\config\logs\` |
| CLI 解析出的配置目录 | 问 `astra-plugin doctor` | 问 `astra-plugin doctor` |

守护进程的日志文件是按日期命名的（`daemon.log.2026-08-05`）。插件
自己的日志行会通过 `PluginLog` 出现在那里，而它原始的 stdout/stderr
则是 `astra-plugin logs` 从守护进程的内存缓冲区中读取的内容 —— 那个
缓冲区不是文件，所以不会在守护进程重启后存活下来。

不要假设这台机器用的是哪个目录，去问：`doctor` 会打印出 CLI 解析到的
那一个，如果 Astra 得出的结果与之不一致，那就说明两者解析出了不同的
目录，而这本身就是一个 bug。

## 完全没有任何日志时

说明这个进程在 SDK 安装好它自己的日志机制之前就失败了。手动运行它：

<!-- doctest: cli -->
```bash
astra-plugin dev --standalone
```

这会直接 spawn 这个插件，而不是请求守护进程去做。它会打印出用那种
方式做不到的事 —— 插件无法注册，因为只有守护进程才能铸造
`Register` 所需要的令牌。
