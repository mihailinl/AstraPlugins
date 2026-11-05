#!/usr/bin/env python3
"""No hidden control character in any `testdata/content/*.json` file.

A raw C0 control (other than the JSON structural `\\n`), DEL (U+007F) or C1
control (U+0080-U+009F) embedded literally in a tracked JSON file trips the
minice repository's own "no hidden control character in any tracked text
file" gate, which refuses the whole file — `testdata/content/vectors.json`
carried a raw 0x7F at its `del` vector and a raw U+0085 (NEL) at its `c1`
vector, and both failed that gate on every repository that vendors this one
(minice's `plugins-ingest` and `plugins-signed` copies).

The fix is at the generator: every control character a JSON STRING needs for
a real test case is written as a `\\uXXXX` escape, never as a raw byte. The
parsed value is unchanged either way; only the on-disk representation moves.
This script is the backstop that notices if one comes back, by reading each
file as decoded Unicode text (an escape sequence is just ASCII backslash-u-
hex-digits in the file's bytes, so it is invisible to this scan — only a
LITERAL control character fails it).

    python3 tools/check-no-hidden-controls.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "testdata" / "content"


def is_hidden_control(cp: int) -> bool:
    if cp == 0x0A:  # the one control character JSON pretty-printing needs
        return False
    if 0x00 <= cp <= 0x1F:
        return True
    if cp == 0x7F:
        return True
    if 0x80 <= cp <= 0x9F:
        return True
    return False


def scan(path: pathlib.Path) -> list[tuple[int, int]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [(-1, -1)]  # not UTF-8 at all: a different problem, still worth failing on
    return [(i, ord(c)) for i, c in enumerate(text) if is_hidden_control(ord(c))]


def main() -> int:
    if not TARGET.is_dir():
        print(f"check-no-hidden-controls: {TARGET} does not exist", file=sys.stderr)
        return 1
    failed = False
    checked = 0
    for p in sorted(TARGET.rglob("*.json")):
        checked += 1
        hits = scan(p)
        if hits:
            failed = True
            rel = p.relative_to(ROOT)
            if hits == [(-1, -1)]:
                print(f"FAIL {rel}: not valid UTF-8")
                continue
            for i, cp in hits[:10]:
                print(f"FAIL {rel}: hidden control character U+{cp:04X} at character offset {i}")
            if len(hits) > 10:
                print(f"     ... and {len(hits) - 10} more in {rel}")
    if failed:
        print("check-no-hidden-controls: FAILED")
        return 1
    print(f"check-no-hidden-controls: {checked} files, no hidden control character.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
