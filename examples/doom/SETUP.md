# Doom — developer setup

User documentation is in [README.md](README.md). This file is the build and
dev-loop notes.

## Build

```bash
cd examples/doom
cargo build --release
```

The engine and game data are committed:

| File | What it is | Size |
|---|---|---|
| `ui/chocolate-doom.js` | Emscripten loader for the engine | ~380 KB |
| `ui/chocolate-doom.wasm` | Chocolate Doom, compiled to WebAssembly (GPL-2.0) | ~7.3 MB |
| `ui/chocolate-doom.data` | Packed `doom1.wad` — Freedoom, modified BSD | ~27 MB |
| `ui/doom.js` | The page: canvas, input, engine bootstrap | ~6 KB |

Nothing needs downloading. Earlier revisions of this file described fetching
js-dos v7 and building a `DOOM.jsdos` bundle — that was a different engine and
that instruction is obsolete.

## Dev loop

```bash
astra-plugin dev .
```

`dev` runs `check --strict`, builds, and asks the running daemon to sideload the
plugin, so the daemon owns the process and mints its session token. Editing a
file rebuilds and restarts it, with logs in your terminal.

Hand-writing a `sideload.json` marker no longer works: the daemon refuses any
marker it did not record itself, and requires Developer Mode at load time.

## Package

```bash
astra-plugin build
```

The resulting `linux-x64` bundle is 15,638,822 bytes — about 15 MB compressed,
about 36 MB extracted, and the largest example in this repository. Worth
remembering when testing install progress, extraction caps and download policy.

## Licensing

See the licensing section of [README.md](README.md) before distributing a build.
The engine is GPL-2.0 and `plugin.toml` currently says MIT.
