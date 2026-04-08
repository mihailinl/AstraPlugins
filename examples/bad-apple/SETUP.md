# Bad Apple Plugin Setup

## 1. Build the plugin backend

```bash
cd examples/bad-apple
cargo build --release
```

## 2. Generate frame data

You need a Bad Apple!! video file (MP4). Then extract frames:

```bash
pip install opencv-python numpy
cd tools
python extract_frames.py bad-apple.mp4 ../ui/frames.bin
```

This produces `ui/frames.bin` (~1-3 MB) containing all frames at 120x90 resolution,
1-bit black/white, RLE compressed.

Optional: adjust resolution for higher quality (costs more CPU):
```bash
python extract_frames.py bad-apple.mp4 ../ui/frames.bin 160 120
```

## 3. Sideload the plugin

Create a sideload marker:

**Windows:**
```bash
mkdir -p "$APPDATA/astra/plugins/bad-apple"
echo '{"source_path":"C:/Users/YOUR_USER/Github/AstraPlugins/examples/bad-apple"}' > "$APPDATA/astra/plugins/bad-apple/sideload.json"
```

**Linux:**
```bash
mkdir -p ~/.config/astra/astra/plugins/bad-apple
echo '{"source_path":"/path/to/AstraPlugins/examples/bad-apple"}' > ~/.config/astra/astra/plugins/bad-apple/sideload.json
```

## 4. Run

Start the Astra daemon. Two things will appear:

1. **Background effect** — Bad Apple renders behind the UI at low opacity (15% by default)
2. **"Bad Apple" tab** — dedicated page with full controls:
   - Play/Pause/Stop
   - Frame scrubber
   - Mode switcher: ASCII, CRT, Particles, Silhouette
   - Color modes: Mono (white), Green (terminal), Amber (warm CRT), Accent (Astra theme)

## Render Modes

| Mode | Description |
|------|-------------|
| **ASCII** | Characters from selected charset — blocks (█▓▒░), braille (2x4 dot matrix), classic (@#*=:.), or katakana (Matrix-style rain) |
| **CRT** | Canvas with scanlines, phosphor glow, VHS jitter — retro monitor feel |
| **Particles** | White pixels spawn particles that drift and fade — organic, flowing |
| **Silhouette** | Clean B&W on canvas with accent color and subtle glow |
