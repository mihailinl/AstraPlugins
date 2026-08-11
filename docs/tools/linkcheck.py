#!/usr/bin/env python3
"""Every relative link in the documentation resolves to something on disk.

The companion to `doctest.py`. That one proves the *samples* are true; this
one proves the *navigation* is. Both exist because the docs were written in a
single commit and then left behind by nine commits of code — and a reader who
follows a 404 stops reading, whether or not the paragraph was correct.

WHAT IS CHECKED

* Every markdown file under `docs/`, plus every `README.md` anywhere in the
  repository that is not vendored, generated or a build artefact.
* Inline links `[text](target)` and reference definitions `[label]: target`.
* A relative target must exist as a file or directory.
* A `#fragment` — on a relative link into a `.md`, or on a bare in-page link —
  must match a heading in the target file, under GitHub's slug rules, or an
  explicit `<a id=…>` / `<a name=…>` anchor.

WHAT IS NOT CHECKED, AND WHY

* `http(s)://` and `mailto:` — this must pass with no network. The canonical
  repository URL is asserted by C6/6.4's grep instead.
* Anything inside a fenced code block. A sample that prints a path is a
  sample, not a link; `doctest.py` owns those.
* Image links `![…](…)`, which the docs do not use — they are skipped rather
  than half-checked, and this comment is the note to delete if that changes.

EXCLUDED FILES, EACH FOR A STATED REASON

* `PRODUCTION_PLAN.md` — it *quotes* the docs, including §7.4's banner with
  the `../../en/README.md` link as it appears inside a translated page. The
  link is correct where the banner is installed and wrong where it is quoted;
  checking the quote would be checking the wrong file.
* `astra-plugin-cli/vendor/**` — byte-identical copies of Astra's crate,
  guarded by `tools/check-manifest-crate.sh`. Nothing here can be fixed here.
* `target/`, `node_modules/`, `dist/`, `__pycache__/`, `.git/`.

USAGE

    python3 docs/tools/linkcheck.py            # the whole repository
    python3 docs/tools/linkcheck.py docs/ru    # one subtree

Exit 0 when every link resolves, 1 when any does not. Every broken link is
printed as `path:line  target  — reason`, one per line, so the output pastes
straight into an editor.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SKIP_DIRS = {".git", "target", "node_modules", "dist", "__pycache__",
             ".venv", "venv", ".mypy_cache", ".pytest_cache"}
SKIP_PREFIXES = ("astra-plugin-cli/vendor/",)
SKIP_FILES = {"PRODUCTION_PLAN.md"}

INLINE = re.compile(r"(?<!!)\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]+)"
                    r"(?:\s+\"[^\"]*\")?\)")
REFDEF = re.compile(r"^\s{0,3}\[(?P<label>[^\]]+)\]:\s*(?P<target>\S+)")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(?P<text>.*?)\s*#*\s*$")
HTML_ANCHOR = re.compile(r"<a\s+[^>]*(?:id|name)=[\"'](?P<id>[^\"']+)[\"']")


def slug(text: str) -> str:
    """GitHub's heading slug: strip markup, lowercase, spaces to dashes."""
    text = re.sub(r"`([^`]*)`", r"\1", text)          # inline code
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)     # bold
    text = re.sub(r"\*([^*]*)\*", r"\1", text)         # italic
    text = INLINE.sub(lambda m: m.group("text"), text)  # links keep their text
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text.strip())


def anchors(path: Path) -> set[str]:
    """Every fragment `path` can be linked to."""
    found: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return found
    seen: dict[str, int] = {}
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING.match(line)
        if m:
            s = slug(m.group("text"))
            # GitHub disambiguates repeats with -1, -2, …
            n = seen.get(s, 0)
            seen[s] = n + 1
            found.add(s if n == 0 else f"{s}-{n}")
        for a in HTML_ANCHOR.finditer(line):
            found.add(a.group("id").lower())
    return found


def markdown_files(scope: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(scope):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            p = Path(dirpath) / name
            rel = p.relative_to(ROOT).as_posix()
            if rel in SKIP_FILES or rel.startswith(SKIP_PREFIXES):
                continue
            # Docs, plus every README anywhere.
            if rel.startswith("docs/") or name == "README.md":
                out.append(p)
    return sorted(out)


def links(path: Path):
    """Yield (line_no, target) for every link outside a fenced block."""
    in_fence = False
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in INLINE.finditer(line):
            yield n, m.group("target")
        m = REFDEF.match(line)
        if m:
            yield n, m.group("target").strip("<>")


def main(argv: list[str]) -> int:
    scope = Path(argv[1]).resolve() if len(argv) > 1 else ROOT
    files = markdown_files(scope)
    if not files:
        print(f"linkcheck: no markdown under {scope}", file=sys.stderr)
        return 1

    cache: dict[Path, set[str]] = {}
    broken: list[tuple[str, int, str, str]] = []
    total = 0

    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        for n, target in links(f):
            total += 1
            if target.startswith(("http://", "https://", "mailto:", "tel:",
                                  "ftp://", "data:")):
                continue
            path_part, _, frag = target.partition("#")
            path_part = urllib.parse.unquote(path_part)
            frag = urllib.parse.unquote(frag).lower()

            if not path_part:                       # in-page link
                if frag and frag not in cache.setdefault(f, anchors(f)):
                    broken.append((rel, n, target, "no such heading in this file"))
                continue

            resolved = (f.parent / path_part).resolve()
            if not resolved.exists():
                broken.append((rel, n, target, "no such file"))
                continue
            if frag and resolved.suffix == ".md":
                if frag not in cache.setdefault(resolved, anchors(resolved)):
                    broken.append((rel, n, target, "no such heading in the target"))

    for rel, n, target, why in broken:
        print(f"{rel}:{n}  {target}  — {why}")
    verdict = "ok" if not broken else "FAIL"
    print(f"linkcheck: {verdict} — {len(files)} file(s), {total} link(s), "
          f"{len(broken)} broken")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
