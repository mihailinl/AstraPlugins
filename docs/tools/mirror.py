#!/usr/bin/env python3
"""Every translation of `docs/en` carries exactly its pages — no more, no less.

English is canonical. The six translations beside it — `de`, `es`, `ja`, `ru`,
`uk`, `zh-CN` — are file-for-file mirrors: same relative paths, same page set.
This script asserts that as a set equality, per locale, in both directions:

* every page under `docs/en/` has a counterpart at the same relative path in
  every locale, and
* every page in a locale corresponds to an English page that still exists.

The second direction is the one that actually fires. The rewrite deleted eight
English pages; a translation whose original is gone is worse than no
translation, because nothing will ever correct it again and a reader has no way
to tell.

This replaced a narrower rule. Until the six locales were re-cut from the
current English pages, only `docs/ru` was checked, and only over a "written
tier" of five paths — the generated and normative tiers were English-only, so a
Russian copy of `reference/cli.md` was an error. All six locales now cover the
whole tree, so the check covers the whole tree, for all of them.

WHAT THIS DOES NOT CHECK, AND WHY IT IS SAID OUT LOUD

Meaning. Nothing here, and nothing anywhere in CI, can tell that a translated
sentence still says what the English one says — that would need a reader of the
language, and it is the whole reason English is authoritative rather than merely
first. What is enforced is the part that is objectively true or false from the
tree alone and has no false positives.

The production plan also asks for "CI fails when `docs/en/**` changes without a
matching translation touch". That gate needs a base ref to diff against, and —
more to the point — it blocks an English-only typo fix until someone touches six
other files, which is a policy the maintainer should choose rather than inherit
from a script. It is not implemented here.

The other half of the drift story is already covered without any policy:
`doctest.py` executes each fenced block once and reports the translated copies as
`identical to` their English original, so a sample that drifts between two
languages stops being deduplicated and shows up as a second execution.

USAGE

    python3 docs/tools/mirror.py

Exit 0 when every locale agrees with `docs/en`, 1 when any does not.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
EN = DOCS / "en"

# The translations. A new locale is NOT picked up automatically: adding one is a
# decision to maintain it, and this list is where that decision is recorded.
LOCALES = ("de", "es", "ja", "ru", "uk", "zh-CN")


def pages(base: Path) -> set[str]:
    if not base.is_dir():
        return set()
    return {p.relative_to(base).as_posix() for p in base.rglob("*.md")}


def main() -> int:
    en = pages(EN)
    if not en:
        print("mirror: FAIL — docs/en has no pages", file=sys.stderr)
        return 1

    bad = 0
    for loc in LOCALES:
        base = DOCS / loc
        if not base.is_dir():
            print(f"MISSING  docs/{loc}/  — the locale directory does not exist")
            bad += 1
            continue
        got = pages(base)
        for rel in sorted(en - got):
            print(f"MISSING  docs/{loc}/{rel}  — docs/en/{rel} exists and has "
                  f"no {loc} counterpart")
            bad += 1
        for rel in sorted(got - en):
            print(f"ORPHAN   docs/{loc}/{rel}  — no docs/en/{rel}; either the "
                  f"English page moved and this one did not, or it was never "
                  f"an English page")
            bad += 1
        if got == en:
            print(f"ok       docs/{loc}/  — {len(got)} page(s), same set as docs/en")

    verdict = "ok" if not bad else "FAIL"
    print(f"mirror: {verdict} — {len(en)} English page(s), "
          f"{len(LOCALES)} locale(s), {bad} mismatch(es)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
