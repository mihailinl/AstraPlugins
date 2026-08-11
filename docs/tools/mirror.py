#!/usr/bin/env python3
"""`docs/ru` covers the written tier of `docs/en`, exactly — no more, no less.

§7.4 of the production plan makes English canonical and Russian second-tier,
covering the *written* pages only: orientation, the tutorial, publish, operate,
and the index. The generated tiers (`reference/`, `hooks/`, `parity.md`), the
normative specs, the SDK pages and the examples index are rendered or reviewed
in English alone and are deliberately not translated.

This script asserts that split as a set equality, in both directions:

* every page under `docs/en/{README.md,1-orientation,2-tutorial,5-publish,
  6-operate}` has a Russian counterpart at the same relative path, and
* every page under `docs/ru/` corresponds to an English page that still exists.

The second direction is the one that actually fires. The rewrite deleted eight
English pages; a translation whose original is gone is worse than no
translation, because nothing will ever correct it again and a reader has no way
to tell.

WHAT THIS DOES NOT CHECK, AND WHY IT IS SAID OUT LOUD

§7.4 asks for more than this: "CI fails when `docs/en/**` changes without a
matching `docs/ru/**` touch". That gate needs a base ref to diff against, and —
more to the point — it blocks an English-only typo fix until someone touches a
Russian file, which is a policy the maintainer should choose rather than
inherit from a script. It is not implemented here. What IS enforced is the part
that is objectively true or false from the tree alone and has no false
positives.

The other half of the drift story is already covered without any policy:
`doctest.py` executes each fenced block once and reports the Russian copies as
`identical to` their English original, so a sample that drifts between the two
languages stops being deduplicated and shows up as a second execution.

USAGE

    python3 docs/tools/mirror.py

Exit 0 when the two sets agree, 1 when they do not.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EN = ROOT / "docs/en"
RU = ROOT / "docs/ru"

# The written tier, as §7.4 defines it. A new top-level directory under
# docs/en is NOT added here automatically: deciding whether it is translated is
# a decision, and this list is where it is recorded.
MIRRORED = ("README.md", "1-orientation", "2-tutorial", "5-publish", "6-operate")


def pages(base: Path, restrict: bool) -> set[str]:
    out: set[str] = set()
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*.md")):
        rel = p.relative_to(base)
        if restrict and rel.parts[0] not in MIRRORED:
            continue
        out.add(rel.as_posix())
    return out


def main() -> int:
    en = pages(EN, restrict=True)
    ru = pages(RU, restrict=False)

    missing_ru = sorted(en - ru)
    orphan_ru = sorted(ru - en)

    for rel in missing_ru:
        print(f"MISSING  docs/ru/{rel}  — docs/en/{rel} is in the translated "
              f"tier and has no Russian counterpart")
    for rel in orphan_ru:
        print(f"ORPHAN   docs/ru/{rel}  — no docs/en/{rel}; either the English "
              f"page moved and this one did not, or it is outside the "
              f"translated tier (see MIRRORED in this file)")

    bad = len(missing_ru) + len(orphan_ru)
    verdict = "ok" if not bad else "FAIL"
    print(f"mirror: {verdict} — {len(en)} English page(s) in the translated "
          f"tier, {len(ru)} Russian page(s), {bad} mismatch(es)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
