# Doom

A "Doom" page in Astra that runs the Chocolate Doom engine, compiled to
WebAssembly, on the Freedoom data set.

## What it does

Adds a page to Astra's navigation. Open it and you are playing a first-person
shooter inside your assistant. Keyboard input goes to the game while the page
has focus; the canvas scales to the window according to the setting below.

Everything runs locally in the Astra window — the engine is a `.wasm` binary in
the bundle, and the game data is packed beside it. There is no server, no
streaming and no account.

## What it needs

Nothing beyond Astra. Be aware of the size: the bundle is about **15 MB** to
download and about **36 MB** on disk once installed — by far the largest example
in this repository. (Measured on a `linux-x64` build; the compressed figure is
what the store shows you before you click Install.)

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `ui_contributions` | The plugin may add its own surfaces to the Astra window | The "Doom" page |
| `dom_access` | The plugin's JavaScript runs **inside the Astra window**, with access to the page: your conversations on screen, and every other plugin's interface | A WebAssembly game needs a canvas, an input loop and an audio context in that window |

`dom_access` is high risk and Astra will say so before installing. The code it
covers here is `ui/doom.js` plus the Emscripten-generated
`ui/chocolate-doom.js`, which loads `ui/chocolate-doom.wasm`. That generated file
is machine output and is not realistically reviewable line by line — which is
exactly the kind of thing worth knowing before you grant a plugin the run of
your window.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| Scale Mode | `fit` | `fit` (letterboxed), `stretch`, or `pixel-perfect` (integer scaling, sharpest) |

## Licensing — read this before forking

The bundle contains two pieces of other people's work:

- **Chocolate Doom**, the engine, is licensed **GPL-2.0**. `chocolate-doom.js`
  and `chocolate-doom.wasm` are builds of it and carry that licence with them.
- **Freedoom** supplies the game data (`doom1.wad` inside
  `chocolate-doom.data`), under a **modified BSD** licence — freely
  redistributable. No commercial DOOM WAD is included.

`plugin.toml` declares **`GPL-2.0-or-later`**, and that is a statement about
the BUNDLE rather than about `src/`. Chocolate Doom's own source headers carry
the ordinary "either version 2 of the License, or (at your option) any later
version" boilerplate, so the engine is GPL-2.0-or-later and an aggregate that
ships it is distributed on those terms.

It said `MIT` until 2026-08-19, and this section said that had to be resolved
before anyone could install it. It was not: the plugin was published to the
catalogue twice with the wrong label, and delisted the same day once this
paragraph was read. The label is now the honest one and the listing is back.

What that does NOT touch: the Rust and JavaScript in `src/` and `ui/doom.js`
remain the authors' to license as they like at the source level — the GPL term
is on the combined thing that is distributed. It reaches no other plugin, and
it does not reach Astra: a plugin is a separate process speaking gRPC over
loopback, which is the arm's-length boundary this architecture was built with.

## Build it yourself

```bash
cd examples/doom
cargo build --release
astra-plugin build
```

The engine and data are committed, so there is nothing to download first.

## Files

- `src/main.rs` — the backend: declares the page and serves its config.
- `ui/doom.js` — the page: canvas, input, engine bootstrap.
- `ui/chocolate-doom.{js,wasm,data}` — the engine build and Freedoom data.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed (`src/` and `ui/doom.js` — see the licensing section above).
