#!/usr/bin/env python3
"""Every translation of `docs/en` carries exactly its pages — no more, no less.

English is canonical. The translations beside it — `docs/tools/locales.py`
declares which, and that file is the only place the set is written down — are
file-for-file mirrors: same relative paths, same page set. This script asserts
that as a set equality, per locale, in both directions:

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

Page sets were once all this checked, and that was not enough. A correction to
an English transcript passed CI with the six translations still carrying the
retracted claim, because matching filenames was the whole test — the summary
line said "0 mismatches" about a tree in which six of seven languages disagreed
with English on a fact. So the samples are compared too:

* the sequence of `<!-- doctest: … -->` runners on a page must be the same in
  every language, and
* an `output` block — a transcript of a real command — must be byte-identical
  to its English original, `from=` and `unrun=` attributes included.

A transcript is a machine's words, not an author's, so translating one is
always a mistake, and drift in one is exactly the failure this tool missed.
`illustrative` reasons are compared too: they are notes to the next editor
about why a block cannot run, they are written in English throughout the tree,
and a translated one is a copy that will not be updated when the English is.

WHAT THIS DOES NOT CHECK, AND WHY IT IS SAID OUT LOUD

Meaning. Nothing here, and nothing anywhere in CI, can tell that a translated
sentence still says what the English one says — that would need a reader of the
language, and it is the whole reason English is authoritative rather than merely
first. What is enforced is the part that is objectively true or false from the
tree alone and has no false positives.

Prose inside a `rust-plugin`, `python-plugin`, `ts-plugin` or `toml-manifest`
block is not compared. Those bodies are code, every one of them is executed by
`doctest.py` in every language, and a comment inside one is fair to translate.
Their runner *positions* are still compared, so a block that disappears from a
translation is still caught.

The production plan also asks for "CI fails when `docs/en/**` changes without a
matching translation touch". That gate needs a base ref to diff against, and —
more to the point — it blocks an English-only typo fix until someone touches six
other files, which is a policy the maintainer should choose rather than inherit
from a script. It is not implemented here.

USAGE

    python3 docs/tools/mirror.py

Exit 0 when every locale agrees with `docs/en`, 1 when any does not.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# The translations. A new locale is still NOT picked up automatically — adding
# one is a decision to maintain it — but the decision is recorded in
# `locales.py`, and only there. It used to live in three files at once, with a
# comment in THIS one claiming to be the place it was recorded; all three
# spelled Chinese `zh-CN`, which is not a language Astra can be set to. C14 in
# the `couplings` job compares that file with `spec/locales.yaml` and with the
# directories that are actually under `docs/`.
from locales import TRANSLATIONS

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
EN = DOCS / "en"


def _doctest_module():
    """`docs/tools/doctest.py`, loaded under a name that is not `doctest`.

    A plain `import doctest` would find the standard library's, and naming this
    file's sibling anything else would break every reference to it in the docs.
    Its block extractor is the one thing needed here, and having two copies of a
    markdown fence parser is how they drift.
    """
    spec = importlib.util.spec_from_file_location(
        "_docs_doctest", Path(__file__).with_name("doctest.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


DT = _doctest_module()

#: Runners whose body must be identical in every language. A transcript is what
#: a program printed, so there is nothing in it to translate.
VERBATIM_BODIES = {"output"}

#: Marker attributes that must be identical in every language, per runner. Most
#: are notes to the next editor rather than prose for a reader; `locales=` is
#: not a note at all.
VERBATIM_ATTRS = {
    "output": ("from", "unrun"),
    "illustrative": ("reason",),
    # `locales=1` changes what `run_toml_manifest` puts on disk before
    # `astra-plugin check` sees the sample. A translation that drops it turns
    # that page's manifest sample red on `[E7]` in one language only, six pages
    # away from whoever last touched English.
    "toml-manifest": ("locales",),
}


def samples(path: Path) -> list:
    return DT.extract(path)[0] if path.is_file() else []


def compare_samples(rel: str, loc: str, en_page: Path, loc_page: Path) -> int:
    """Every doctest block on one translated page, against its English original."""
    en, got = samples(en_page), samples(loc_page)
    en_runners = [b.runner for b in en]
    got_runners = [b.runner for b in got]
    if en_runners != got_runners:
        print(
            f"SAMPLES  docs/{loc}/{rel}  — {len(got)} doctest block(s) "
            f"[{', '.join(got_runners) or 'none'}], but docs/en/{rel} has "
            f"{len(en)} [{', '.join(en_runners) or 'none'}]"
        )
        return 1

    bad = 0
    for a, b in zip(en, got):
        if a.runner in VERBATIM_BODIES and a.body != b.body:
            print(
                f"DRIFT    docs/{loc}/{rel}:{b.line}  — this {a.runner} block "
                f"differs from docs/en/{rel}:{a.line}. A transcript is what a "
                f"command printed; it is the same in every language"
            )
            bad += 1
        for name in VERBATIM_ATTRS.get(a.runner, ()):
            if a.attrs.get(name) != b.attrs.get(name):
                print(
                    f"DRIFT    docs/{loc}/{rel}:{b.line}  — {name}= differs from "
                    f"docs/en/{rel}:{a.line}\n"
                    f"           en: {a.attrs.get(name)!r}\n"
                    f"           {loc}: {b.attrs.get(name)!r}"
                )
                bad += 1
    return bad

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
    drift = 0
    for loc in TRANSLATIONS:
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
        # Only pages that exist in both: a page reported MISSING above has
        # nothing to compare, and saying so twice helps nobody.
        here = sum(
            compare_samples(rel, loc, EN / rel, base / rel)
            for rel in sorted(en & got)
        )
        drift += here
        if got == en and not here:
            print(f"ok       docs/{loc}/  — {len(got)} page(s), same set and "
                  f"same samples as docs/en")

    verdict = "ok" if not (bad or drift) else "FAIL"
    print(f"mirror: {verdict} — {len(en)} English page(s), "
          f"{len(TRANSLATIONS)} locale(s), {bad} page-set mismatch(es), "
          f"{drift} sample drift(s)")
    return 1 if (bad or drift) else 0


if __name__ == "__main__":
    raise SystemExit(main())
