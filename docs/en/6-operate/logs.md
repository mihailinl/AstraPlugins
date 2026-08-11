# Logs

There are three places a plugin's output can end up, and knowing which is which
saves an hour.

| | Where it goes | Who can see it |
|---|---|---|
| `tracing::info!` / `logging.info(...)` (the SDK's log bridge) | forwarded to the daemon as `PluginLog`, **and** to stderr | you *and* the user, in Astra's log pane |
| `ctx.host().log_info(...)` — the explicit call | the daemon | you and the user |
| `println!` / bare stderr | the process's stdout/stderr, which the daemon captures | you, through `astra-plugin logs` |

Before the bridge existed these were two different sets, and the interesting
lines — a panic, a failed request, a retry — were almost always in the set the
user could not see.

## Reading them

<!-- doctest: cli -->
```bash
astra-plugin logs
astra-plugin logs dice-roller -f
astra-plugin logs dice-roller -n 500 --daemon-addr 127.0.0.1:32000
astra-plugin logs --json
```

With no id it reads `plugin.id` out of the manifest in `--path`. It works for
**installed** plugins, which is the case `astra-plugin dev` cannot serve at all.

The daemon keeps a **bounded ring buffer per plugin**, and `GetPluginLogs` is
unary over it — so `-f` is a poll every 750 ms, and "new" lines are the suffix
of this tail that does not continue the previous one. A restart resets the
buffer.

Asking for more lines than the buffer holds is harmless. `--json` prints one
document and exits, which is the snapshot form; `-f` and `--json` are not a
useful pair.

## What the SDK forwards, and what it does not

The `tracing` layer the SDK installs forwards to the daemon:

- **`INFO` and above** by default. `ASTRA_PLUGIN_LOG_LEVEL` changes it; `DEBUG`
  belongs to `RUST_LOG` and stderr, because the pane is for the user.
- **Not** the transport stack — `h2`, `hyper`, `tonic`, `tower`, `rustls`,
  `tokio`. Shipping a log line is itself an RPC, and an RPC that logs produces a
  log line: without that exclusion one `WARN` from `h2` becomes an unbounded
  loop.
- **Not more than the queue holds.** The channel is bounded and the send is
  non-blocking, so a plugin in a hot loop drops lines rather than
  back-pressuring its own handlers onto the daemon.

### Python

`install_logging_bridge()` routes the standard `logging` module the same way.
Use it rather than `print`: the SDK reconfigures stdout to **line buffering**
because the daemon's supervisor reads stdout to learn the plugin is alive, and
block-buffered output once had the supervisor reap healthy plugins at the start
timeout.

## Turning up the CLI's own trace

`RUST_LOG` controls `astra-plugin` itself. It was documented from 0.1 and did
nothing until a subscriber was installed — every `tracing` event the CLI and its
dependencies emitted went nowhere.

<!-- doctest: cli -->
```bash
RUST_LOG=astra_plugin=debug astra-plugin check
RUST_LOG=debug astra-plugin build
```

Default is `warn`, and it goes to **stderr** — the CLI's user-facing output is
on stdout, and a trace line there would corrupt a `--json` document.

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Why do I see no trace output from the CLI?
         RUST_LOG is unset, so only warnings and errors are printed.
         `RUST_LOG=astra_plugin=debug` turns on this CLI's own trace;
         `RUST_LOG=debug` turns on its dependencies' too.
```

## Files on disk

| | Linux | Windows |
|---|---|---|
| Daemon logs | `~/.config/astra/logs/` | `%APPDATA%\astra\astra\config\logs\` |
| Config dir the CLI resolved | ask `astra-plugin doctor` | ask `astra-plugin doctor` |

Daemon log files are dated (`daemon.log.2026-08-05`). A plugin's own lines
appear there via `PluginLog`, and its raw stdout/stderr is what
`astra-plugin logs` reads from the daemon's in-memory buffer — that buffer is
not a file, so it does not survive a daemon restart.

Ask rather than assume which directory this machine uses: `doctor` prints the
one the CLI resolved, and if Astra disagrees the two resolved different
directories, which is itself the bug.

## When there are no logs at all

The process is failing before the SDK installs its logging. Run it by hand:

<!-- doctest: cli -->
```bash
astra-plugin dev --standalone
```

That spawns the plugin directly instead of asking the daemon to. It prints what
it cannot do that way — the plugin cannot register, because only the daemon can
mint the token `Register` requires.
