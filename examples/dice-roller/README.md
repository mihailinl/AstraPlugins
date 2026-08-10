# Dice Roller

Roll dice and flip coins — in conversation, in a command, or as the thing that
starts a command.

## What it does

Ask Astra to *"roll 3d6"* and it rolls three six-sided dice and tells you the
faces and the total. Ask it to flip five coins and it flips five coins.

Beyond conversation, it plugs into the command editor in two directions:

- **A "Roll Dice" action** you can drop into any command. It takes dice notation
  (`d20`, `3d6`, `4d10`) and can store the result in a variable that later steps
  read. Counts are clamped to 1–100 dice with 2–1000 sides each, so a typo
  cannot ask for a million rolls.
- **A "Dice Roll Value" trigger** that fires once per die, carrying `value`,
  `roll` and `sum`. Set it to `20` and you have a command that runs on a natural
  20; set it to `1` and you have one that runs on a fumble. Leave the value
  empty and it fires on every roll.

The randomness is a small xorshift seeded from the system clock. It is fine for
a d20 at the table and it is **not** suitable for anything where the outcome
matters — no cryptography, no money, no lottery.

## What it needs

Nothing. No network, no files, no account, no configuration to get started. It
is a single native binary that talks only to Astra.

## Capabilities it asks for, and why

| Capability | What it allows | Why this plugin asks |
|---|---|---|
| `tools` | Astra's assistant may call the plugin during a conversation | So *"roll 2d6"* works as a sentence rather than a menu |
| `actions` | The plugin contributes steps to the command editor | The "Roll Dice" action |
| `triggers` | The plugin can start your commands | The "Dice Roll Value" trigger |

It asks for nothing else. It does not read your conversations, does not run code
in the Astra window, and does not open a socket.

As with every Astra plugin, the binary runs as a normal program with your user
account's privileges. The capability list above describes what Astra will *route
to it*, not a sandbox.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| Default Dice Sides | `6` | Sides assumed when you say "roll a die" without naming a size |

## Build it yourself

```bash
cd examples/dice-roller
cargo build --release
astra-plugin build            # produces dice-roller-<version>-<target>.astraplugin
```

To develop against a running Astra:

```bash
astra-plugin dev .
```

## Files

- `src/main.rs` — the whole plugin, about 250 lines. If you are writing your
  first Astra plugin, read this one: it is the smallest complete example that
  uses all three of tools, actions and triggers.
- `icon.svg` — the store icon, hand-drawn SVG.

MIT licensed.
