<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# CLAUDE.md

**The instructions for this repository are in [`AGENTS.md`](AGENTS.md). Read it
before you touch anything** — it is short, and it is the whole thing. This file
is a pointer, not a second copy; if the two ever disagree, `AGENTS.md` is right
and this file is the bug.

The three mistakes it exists to stop, so you do not make one before you get
there:

1. **Do not hand-write `plugin.toml` or copy one from `examples/`.** Run
   `astra-plugin new`. The capability and permission vocabularies are closed
   sets, and an unknown key does not parse.
2. **Do not hand-edit a generated file.** §5 of `AGENTS.md` names every one and
   the generator that owns it.
3. **If you find a bug, do not work around it silently.** Small and provable →
   pull request. Behavioural, cross-repo, or a design question → issue first.
   §6 has the rule, and which repository and template to use.
