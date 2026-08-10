# Bad Apple — developer setup

User documentation is in [README.md](README.md). This file is the build and
dev-loop notes.

## Build

```bash
cd examples/bad-apple
cargo build --release
```

The frame data (`ui/frames.bin`) and audio (`ui/bad-apple.mp3`) are committed —
there is nothing to generate before the plugin runs.

## Dev loop

```bash
astra-plugin dev .
```

`dev` runs `check --strict`, builds, and asks the running daemon to sideload the
plugin, so the daemon owns the process and mints its session token. Editing a
file rebuilds and restarts it, with logs in your terminal.

Hand-writing a `sideload.json` marker no longer works: the daemon refuses any
marker it did not record itself, and requires Developer Mode at load time.
Earlier revisions of this file told you to write one. They were wrong.

## Regenerating the frame data

Only needed if you want a different animation or a different resolution.

```bash
pip install opencv-python numpy
python tools/extract_frames.py bad-apple.mp4 ui/frames.bin          # 120x90, the default
python tools/extract_frames.py bad-apple.mp4 ui/frames.bin 160 120  # sharper, more CPU
```

The output is 1-bit black and white, run-length encoded. At 120x90 it is about
3 MB for the full song.

## Package

```bash
astra-plugin build
```
