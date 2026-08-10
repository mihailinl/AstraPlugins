# Bad Apple

The *Bad Apple!!* animation, rendered as ASCII, CRT phosphor, particles or
silhouette, behind the Astra interface.

## What it does

Plays a 1-bit black-and-white animation as a background effect in the Astra
window, at low opacity by default so it reads as texture rather than a video.
Four renderers are included:

| Mode | What you see |
|---|---|
| **ASCII** | Characters from one of four sets — blocks `█▓▒░`, braille dot matrix, classic `@#*=:.`, or katakana rain |
| **CRT** | Canvas with scanlines, phosphor glow and VHS jitter |
| **Particles** | Lit pixels spawn particles that drift and fade |
| **Silhouette** | Clean black and white with an accent glow |

The frame data is a pre-extracted 1-bit RLE stream (`ui/frames.bin`, ~3 MB) —
there is no video decoder involved, which is what makes it cheap enough to run
behind a working interface.

## What it needs

Nothing at run time — the frames and audio are inside the bundle. No network, no
account.

`tools/extract_frames.py` is included for regenerating `frames.bin` from a video
file (it needs `opencv-python` and `numpy`), but you only need it if you want a
different animation or a different resolution.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `ui_contributions` | The plugin may add its own surfaces to the Astra window | The background effect is a UI contribution |
| `dom_access` | The plugin's JavaScript runs **inside the Astra window**, with access to the page: your conversations on screen, and every other plugin's interface | Drawing behind the interface means drawing *in* the interface |

`dom_access` is a high-risk capability, and Astra will say so before installing.
A plugin that has it can read what is on your screen. There is no way to paint a
background effect into a window without running code in that window; if that
trade is not worth an animation to you, it should not be, and you should not
install this.

The code that runs in your window is `ui/bad-apple-bg.js`, `ui/renderer.js` and
`ui/bad-apple-player.js`. Nothing else.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| Render Mode | `ascii` | `ascii`, `crt`, `particles`, `silhouette` |
| Background Opacity | `0.15` | 0.05–1.0. Above ~0.3 it competes with the text |
| ASCII Character Set | `blocks` | `blocks`, `braille`, `classic`, `katakana` |
| Color Mode | `mono` | `mono`, `accent` (follows your Astra theme), `green`, `amber` |
| Loop Playback | `true` | Restart at the end |

## A note on the media

`ui/bad-apple.mp3` and `ui/frames.bin` are derived from *Bad Apple!!* — the
Touhou-derived song and the shadow-art music video built on it. Those are other
people's work, and this example redistributes them for demonstration. The MIT
licence on this directory covers **the code**, not the audio or the frame data.
Before publishing a fork of this plugin anywhere, sort that out.

## Build it yourself

```bash
cd examples/bad-apple
cargo build --release
astra-plugin build
```

To regenerate the frame data from your own video:

```bash
pip install opencv-python numpy
python tools/extract_frames.py bad-apple.mp4 ui/frames.bin        # 120x90
python tools/extract_frames.py bad-apple.mp4 ui/frames.bin 160 120 # sharper, costlier
```

## Files

- `src/main.rs` — the backend: declares the effect and serves its config.
- `ui/` — the renderers, the frame data and the audio.
- `tools/extract_frames.py` — video to 1-bit RLE.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed (the code — see the media note above).
