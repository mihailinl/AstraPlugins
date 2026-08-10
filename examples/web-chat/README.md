# Web Chat Client

A browser window that talks to Astra, for watching multi-client sync happen.

## What it does

Runs a small HTTP server on `http://127.0.0.1:9090`. Open it and you get a chat
interface backed by your real Astra conversations. Every chat event in every
conversation is forwarded to the browser over a WebSocket as JSON, so you can
watch a message you type in the Astra window appear in the browser, and the
reverse, in real time.

The last 10,000 events are kept in memory for replay, so a browser that connects
mid-stream sees recent history before switching to the live feed. Nothing is
written to disk.

It exists to make multi-client synchronisation observable. If you are working on
Astra's event sourcing, or writing your own client, this is the smallest thing
that shows you the wire.

## What it needs

- A free TCP port **9090** on the loopback interface. The port is a constant in
  `src/web.rs`; if something else has it, the server fails to start and says so
  in the plugin's logs.
- A browser.

No network access beyond loopback, no account, no configuration.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `client` | The plugin acts as a full chat client: it may read your conversations, create new ones, submit messages as you, and subscribe to the live event stream | It is a chat client, in a browser instead of a window |

`client` is a high-risk capability and Astra will say so before installing.

**There is no authentication on the web server.** It binds loopback only, so it
is not reachable from another machine on your network — but any process running
as you, and anything you open in your browser that can reach `127.0.0.1:9090`,
can read your conversations and send messages as you through it. This is a
development and demonstration tool. Do not run it on a shared machine, do not
port-forward it, and do not treat it as a remote-access feature.

## Configuration

None. The port is a compile-time constant.

## Build it yourself

```bash
cd examples/web-chat
cargo build --release
astra-plugin build
```

Then start Astra, open `http://127.0.0.1:9090`, and type in both places.

## Files

- `src/main.rs` — the plugin: registers as a client, forwards the firehose.
- `src/web.rs` — the axum server, the page, and the WebSocket.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
