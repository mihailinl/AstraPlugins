# Doom Plugin Setup

## 1. Build the plugin backend

```bash
cd examples/doom
cargo build --release
```

## 2. Download js-dos v7

Download js-dos v7 files into `ui/js-dos/`:

- `js-dos.js` — main library
- `wdosbox.js` — DOSBox wrapper
- `wdosbox.wasm` — DOSBox WebAssembly binary

From: https://js-dos.com/v7/build/

```bash
cd ui/js-dos
curl -LO https://js-dos.com/v7/build/js-dos.js
curl -LO https://js-dos.com/v7/build/wdosbox.js
curl -LO https://js-dos.com/v7/build/wdosbox.wasm
```

## 3. Create the DOOM.jsdos bundle

A `.jsdos` file is a zip containing the game files and DOSBox configuration.

### Get DOOM1.WAD (shareware)

Download the freely distributable DOOM shareware WAD from:
https://distro.ibiblio.org/slitaz/sources/packages/d/doom1.wad

### Create bundle

Create a directory structure:

```
bundle/
  DOOM1.WAD
  .jsdos/
    dosbox.conf
```

`dosbox.conf`:
```ini
[sdl]
autolock=true

[cpu]
cycles=max

[autoexec]
mount c .
c:
DOOM1.WAD
```

Note: DOOM1.WAD is the shareware executable — the WAD file IS the game when
launched through DOSBox. If you have the original DOS DOOM1.EXE + DOOM1.WAD,
place both and use `DOOM1.EXE` in autoexec instead.

Zip the bundle directory contents (not the directory itself) into `DOOM.jsdos`:

```bash
cd bundle
zip -r ../ui/DOOM.jsdos . -x ".*"
```

## 4. Sideload the plugin

Create a sideload marker so the Astra daemon discovers the plugin:

**Windows:**
```bash
mkdir -p "$APPDATA/astra/plugins/doom"
echo '{"source_path":"C:/Users/YOUR_USER/Github/AstraPlugins/examples/doom"}' > "$APPDATA/astra/plugins/doom/sideload.json"
```

**Linux:**
```bash
mkdir -p ~/.config/astra/astra/plugins/doom
echo '{"source_path":"/path/to/AstraPlugins/examples/doom"}' > ~/.config/astra/astra/plugins/doom/sideload.json
```

## 5. Run

Start the Astra daemon. The "Doom" tab should appear in the UI navigation.
