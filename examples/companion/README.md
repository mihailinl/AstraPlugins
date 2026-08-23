# Companion Cat

A cat that flies around the Astra window and occasionally says something.

## What it does

Adds a small animated cat as an overlay on top of the Astra interface. It drifts
across the window, reacts to being clicked, and every so often speaks a line
drawn at random from a phrase list. The phrase list is translated: it ships
English and Russian, and follows Astra's own language setting, so switching
Astra to Russian switches the cat.

It is decorative. It does nothing to your conversations, your settings or your
files.

## What it needs

Nothing. No network, no account, no configuration.

## Capabilities it asks for, and why

This plugin asks for the two capabilities Astra treats as **high risk**, and it
is worth being precise about what that means.

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `ui_contributions` | The plugin may add its own surfaces — pages, panels, overlays — to the Astra window | The cat is an overlay contribution |
| `dom_access` | The plugin's JavaScript runs **inside the Astra window**, with access to the page: your conversations on screen, and every other plugin's interface | An overlay that flies across the UI is, by construction, code running in that UI |

`dom_access` is the strongest thing a plugin can ask for short of the fact that
its backend is already a native process. A plugin with `dom_access` can read
what is rendered on your screen, including message text, and can interact with
anything else drawn there. There is no version of an in-window animated cat that
does not need it.

Read `ui/cat.js` if you want to know what this particular one does with it —
that is the file that runs in your window, and it is the only one.

## Configuration

None.

## Build it yourself

```bash
cd examples/companion
cargo build --release
astra-plugin build
```

## Files

- `src/main.rs` — the backend: declares the overlay and answers
  `getRandomMessage` calls from the UI side.
- `ui/cat.js` — everything visible. This is the code `dom_access` covers.
- `locales/en.json`, `locales/ru.json` — the phrase lists, plus the two
  reserved `listing.*` keys the store card is drawn from.
  `msg.0` … `msg.N`: how many there are is asked with `count_prefixed`
  rather than written down, so adding a phrase to both files is the whole
  change. It used to be a `% 41` in `main.rs` with a comment asking the
  next person to keep the two in step, and nothing that noticed when they
  were not. See [the localisation page](../../docs/en/3-reference/localisation.md).
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
