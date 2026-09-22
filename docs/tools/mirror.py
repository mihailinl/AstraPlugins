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

Samples were not enough either, and the hole was the same shape a third time. A
GENERATED table mirrored by hand is a copy nobody regenerates:
`tools/parity/gen.py` writes `docs/en/parity.md` and writes no translation of
it, so every translated hook table named `manager.rs:3624` where English named
`3924` — a pointer some three hundred lines into the wrong part of the daemon,
wrong in six languages and in both doc tiers, and green here every single run,
because page sets and doctest blocks were the whole test and a table body is
neither. So table rows are compared too:

* a row whose FIRST cell is one inline-code span with no whitespace in it — an
  rpc name, a manifest key, a flag — is keyed on that name, and must appear the
  same number of times in the translation as in English; and
* in such a row, every cell that is a whitespace-free inline-code span in
  English must be byte-identical in the translation.

A whitespace-free code span is a name a machine would recognise, and a name is
the same in every language. A code span WITH whitespace is a phrase and is left
alone — `spec/registry-index.md` has `issued_at + 30 days` in a cell, and
`issued_at + 30 Tage` is the correct German for it. Plain cells are left alone
for the reason the rest of this file leaves prose alone: `yes`/`ja` and
`**none**`/`**keine**` are translations, not drift.

Table rows were not enough either, and the hole was the same shape a fourth and
a fifth time. Both were filed as separate problems and both are here:

* A section can exist in English and in no translation, and if its tables do
  not lead with a name, nothing notices. Four such sections were measured on
  2026-08-23 and written down as a frozen four; a fifth
  (`### Answering in the conversation that called you`) was appended to the
  English page on 2026-09-11 and joined them in silence. A list that grows
  while nobody is counting is the failure, not the four. So heading SKELETONS
  are compared:

  - the sequence of heading levels on a translated page must equal English's,
    minus exactly the headings `GRANDFATHERED` below declares absent; and
  - the inline-code spans inside a heading — `astra-plugin locale`,
    `ListTools` — must match position for position, because a heading that
    names a machine thing names it the same in every language. Unlike a table
    cell, a span WITH whitespace counts: a cell may hold a phrase, a heading
    holds a title, and ``## There is no `astra-plugin login` `` is a command
    line in all seven languages. That distinction was measured, not assumed —
    the narrow rule let a rename of exactly that heading through.

  Heading TEXT is not compared and cannot be: `## Everywhere` is `## Überall`
  and that is correct German.

* A GENERATED sentence mirrored by hand is a copy nobody regenerates, exactly
  as a generated table was. `reference/protocol.md`'s opening paragraph names
  the slice's `surface-sha256` and the digest `proto/PROTO_VERSION` pins. On
  2026-09-18 the six translations carried `sha256:2bccd2f5…` where English
  carried something else, and named a `source-sha256` header the slice had
  stopped carrying — two generations stale and documenting a retired field,
  green here every run, because a hash in a paragraph is neither a table row
  nor a sample. What that cost is worth stating in full: **a reader verifying
  a vendored slice against the documented hash could not tell a stale page
  from a tampered slice.** So digests are compared:

  - every run of 8 or more hex digits outside a fenced block is collected per
    page and must appear the same number of times in every language; and
  - `PINNED_DIGESTS` below names the digests that have a ground truth in this
    repository, and each one is checked against that file in EVERY language,
    not only English. That second rule is the one that matters: comparing six
    translations with English cannot catch a value all seven got wrong, and
    `docgen --check` — which does compare English with its generator — is one
    file wide by design.

THE GRANDFATHERED LIST IS DATA, AND IT ONLY RATCHETS DOWN

An exemption with no reason is indistinguishable from an exemption somebody
added to make a test pass. So every entry in `GRANDFATHERED` carries a reason,
the reason is required rather than optional, and it must begin `Leaves this
list when ` — a shape the script enforces, because the sentence that matters
is not why the exemption exists but what would have to be true for it to stop
existing.

`GRANDFATHERED_CEILING` must equal the length of that list exactly. Adding a
sixth entry fails until somebody raises the literal, and removing one fails
until somebody lowers it. That is a ratchet, and it is honest to say what it
is not: it is **not** shrink-only, because the same commit that adds an entry
can raise the ceiling. What it buys is that accretion can no longer happen by
appending to a list — it costs a number in the diff, with a reviewer looking at
it. Making it truly shrink-only needs a base ref (the ceiling in the
merge-base's copy of this file), which is the same thing the gate below needs
and is the maintainer's call for the same reason.

THE FLOOR

Every comparison counts itself, and `main` fails if a count comes in under its
floor. A guard that silently reached nothing passes for years; two have shipped
here already. The floors are round numbers well under today's measurements, so
that deleting a page is not automatically red — a floor set to today's count
turns a deliberate deletion into a failure, which is how a check teaches people
to edit the check.

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

A heading's WORDS. Only its level and its code spans are compared, so renaming
`## Everywhere` to `## Anywhere` in English is invisible here and always will
be. Renaming ``## There is no `astra-plugin login` `` is not: the name inside
the span is a machine's, and it is the same word in seven languages.

Whether a section SAYS the same thing. An English-only section is now a
failure — that is the first of the two rules above, and it is a change from
what this file used to promise. Until 2026-09-21 the sentence here read "a
whole section that exists in English and in no translation is not a failure
unless it contains a table whose rows lead with a name", and it was true: a
section of prose cost nothing, a section with one row `| ``--brand-new`` | does
a thing |` cost six TABLE findings. That asymmetry is what let four sections
become five without anybody noticing. Now the heading itself is the unit, and
an English-only section costs six edits or one `GRANDFATHERED` entry with a
reason attached.

The policy question below — whether an English edit should be blocked until
somebody translates it — is still the maintainer's. This paragraph is only about
what the script does today, which a contributor needs to know BEFORE writing the
section rather than after CI tells them.

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
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
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
    Its block extractor is one of the two things needed here — the other is its
    `FENCE_RE`, borrowed by `table_rows` below, because having two copies of a
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


# ── the grandfathered sections, as data ──────────────────────────────────────

#: Every `reason` must begin with this. Not decoration: an exemption's reason
#: has to name its own exit condition, or it is a permanent exemption wearing a
#: temporary one's clothes. The prefix is what makes the requirement checkable
#: rather than aspirational.
LEAVE_PREFIX = "Leaves this list when "

#: A reason shorter than this is not a reason. The number is deliberately low —
#: it exists to refuse `reason="TODO"`, not to legislate prose length.
MIN_REASON = 80


@dataclass(frozen=True)
class Grandfathered:
    """One English heading that six translations are allowed not to have.

    `heading` is the English heading LINE, verbatim, `#` markers included. It
    is matched against the English page and must be found there exactly once —
    so an exemption whose heading was renamed, re-levelled or deleted fails
    instead of quietly protecting nothing. That is the second half of the
    ratchet: the list cannot rot in place either.
    """

    page: str
    heading: str
    reason: str


#: The five English sections that no translation carries. Four were measured on
#: 2026-08-23; the fifth arrived on 2026-09-11 and nothing counted it, which is
#: the whole argument for `GRANDFATHERED_CEILING` below.
GRANDFATHERED = (
    Grandfathered(
        page="3-reference/permissions.md",
        heading="## Sending a chat message",
        reason=(
            LEAVE_PREFIX + "a translator writes this section in all six "
            "languages. It landed in English on 2026-08-21 (AstraPlugins "
            "d22125c) and no translation followed. It is the only "
            "documentation of the one path a plugin has into a conversation, "
            "so a reader in any other language is told the path exists and "
            "nothing about how to use it."
        ),
    ),
    Grandfathered(
        page="3-reference/permissions.md",
        heading="### Where it lands",
        reason=(
            LEAVE_PREFIX + "all six languages carry it. It retracts a contract "
            "that the protocol and two of the three SDKs documented backwards "
            "— an empty `conversation_id` was written up as *the active "
            "conversation*, and there has never been one — so a reader who "
            "cannot read English is still being taught the retracted version "
            "by the SDK in front of them."
        ),
    ),
    Grandfathered(
        page="3-reference/permissions.md",
        heading="### Answering in the conversation that called you",
        reason=(
            LEAVE_PREFIX + "all six languages carry it. This is the fifth "
            "entry and it is not one of the original four: it landed on "
            "2026-09-11 (AstraPlugins 5f6d8d1), nineteen days after this list "
            "was measured at four, and joined it in silence. It is the entry "
            "this ceiling exists because of."
        ),
    ),
    Grandfathered(
        page="3-reference/permissions.md",
        heading="### What happens if Astra is busy",
        reason=(
            LEAVE_PREFIX + "all six languages carry it, the queued / dropped / "
            "refused table included. Those three shapes demand opposite "
            "reactions — wait, say so, back off — and are distinguishable only "
            "by shape, so a reader without English has no way to tell which of "
            "the three just happened to them."
        ),
    ),
    Grandfathered(
        page="reference/cli.md",
        heading="## astra-plugin locale",
        reason=(
            LEAVE_PREFIX + "all six languages carry it. `astra-plugin locale` "
            "landed on 2026-08-22 (AstraPlugins b56de3c) and is the only "
            "documented way to create `locales/<code>.json`. Measured "
            "2026-09-21: all six translations of `3-reference/localisation.md` "
            "send the reader to that command by name, and the section "
            "describing it exists in English only — so every one of them "
            "points at a page the reader cannot read."
        ),
    ),
)

#: Must equal `len(GRANDFATHERED)` exactly, in both directions. A sixth entry
#: fails until somebody raises this literal; removing one fails until somebody
#: lowers it. See the docstring for what this is and — more importantly — what
#: it is not.
GRANDFATHERED_CEILING = 5


# ── generated values that have a ground truth in this repository ─────────────


@dataclass(frozen=True)
class PinnedDigest:
    """A digest a page prints as prose, and the file that actually holds it.

    Checked in EVERY language, English included. Comparing six translations
    with English cannot catch a value all seven got wrong, and the check that
    does compare English with its generator (`docgen --check`) reads one file.
    """

    page: str
    label: str
    source: str
    pattern: str
    reason: str


PINNED_DIGESTS = (
    PinnedDigest(
        page="reference/protocol.md",
        label="sha256",
        source="proto/PROTO_VERSION",
        pattern=r"^\s*sha256\s*=\s*([0-9a-f]{64})\s*$",
        reason=(
            "The digest every vendored copy of the proto must have. A reader "
            "checks a slice against this number; a stale page and a tampered "
            "slice look identical to them."
        ),
    ),
    PinnedDigest(
        page="reference/protocol.md",
        label="surface-sha256",
        source="proto/plugin.proto",
        pattern=r"^//\s*surface-sha256:\s*([0-9a-f]{64})\s*$",
        reason=(
            "The digest of the plugin-facing body itself. The six "
            "translations named a `source-sha256` here until 2026-09-21 — a "
            "header the slice had already stopped carrying, so the field a "
            "reader was told to look for did not exist."
        ),
    ),
)


# ── floors ───────────────────────────────────────────────────────────────────

#: Round numbers well under today's tree (38 pages, 6 locales, ~2400 heading
#: comparisons, ~50000 prose lines scanned). Under, not at: a floor set to
#: today's count turns a deliberate page deletion red, and a check that
#: punishes correct work teaches people to edit the check.
FLOOR_LOCALES = 6
FLOOR_PAGES = 30
FLOOR_HEADINGS = 1500
FLOOR_PROSE_LINES = 20000

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


# ── generated tables ─────────────────────────────────────────────────────────

#: A cell that is ONE inline-code span with no whitespace inside it: `ListTools`,
#: `plugin.toml`, `astra-rs/astra-daemon/src/plugins/manager.rs`, `--dry-run`.
#: That is a name, and a name is the same in every language. `issued_at + 30
#: days` is a code span too and is deliberately NOT one of these — it has a
#: space in it, it is a phrase, and `issued_at + 30 Tage` is the right German.
TOKEN_CELL = re.compile(r"^`\S+`$")

#: `|---|:--:|---|` — the row that makes the row above it a header. Carries no
#: content, and its dashes are not a name.
TABLE_RULE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$")

#: Cells are separated by a pipe that is not escaped. `reference/manifest.md`
#: quotes Rust closures in a table — `all(\|c\| …)` — and splitting those on a
#: bare `|` invents four cells out of one.
CELL_SPLIT = re.compile(r"(?<!\\)\|")


def cells(row: str) -> list[str]:
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip() for c in CELL_SPLIT.split(body)]


def table_rows(path: Path) -> list[tuple[int, list[str]]]:
    """Every markdown table row on a page, outside fenced blocks.

    The fence pattern is `doctest.py`'s own, not a second copy of it — see
    `_doctest_module`. Blocks are skipped because a fenced sample may quote a
    table it does not own; `docs/tools/README.md` documents the marker syntax
    by showing it.
    """
    rows: list[tuple[int, list[str]]] = []
    fence: str | None = None
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        f = DT.FENCE_RE.match(raw)
        if f:
            token = f.group("fence")
            if fence is None:
                fence = token[0] * len(token)
            elif raw.strip().startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        body = raw.strip()
        if body.startswith("|") and not TABLE_RULE.match(body):
            rows.append((lineno, cells(raw)))
    return rows


def keyed_rows(path: Path) -> dict[tuple[str, int], list[tuple[int, list[str]]]]:
    """Table rows that lead with a name, keyed on that name and the row's width.

    Keyed rather than positional so that a section English has and a translation
    does not is silence here instead of noise — see the docstring. The width is
    part of the key because `parity.md` lists `ListTools` twice, once in a
    nine-column table and once in a five-column one, and they are different rows
    saying different things.
    """
    out: dict[tuple[str, int], list[tuple[int, list[str]]]] = defaultdict(list)
    for lineno, row in table_rows(path):
        if row and TOKEN_CELL.match(row[0]):
            out[(row[0], len(row))].append((lineno, row))
    return out


def compare_tables(rel: str, loc: str, en_page: Path, loc_page: Path) -> int:
    """Every named table row on one translated page, against its English original."""
    en = keyed_rows(en_page)
    got = keyed_rows(loc_page)

    bad = 0
    for key in sorted(set(en) | set(got)):
        name, width = key
        mine, theirs = en.get(key, []), got.get(key, [])
        if len(mine) != len(theirs):
            print(
                f"TABLE    docs/{loc}/{rel}  — the {name} row of a {width}-column "
                f"table appears {len(theirs)} time(s) here and {len(mine)} time(s) "
                f"in docs/en/{rel}. A table row that leads with a name is derived "
                f"data: it exists in every language or in none. Add or remove the "
                f"row in the translation to match English"
            )
            bad += 1
            continue
        for (en_line, en_row), (loc_line, loc_row) in zip(mine, theirs):
            for col, (a, b) in enumerate(zip(en_row, loc_row), start=1):
                if not TOKEN_CELL.match(a) or a == b:
                    continue
                print(
                    f"TABLE    docs/{loc}/{rel}:{loc_line}  — column {col} of the "
                    f"{name} row says {b or '(empty)'}, docs/en/{rel}:{en_line} says "
                    f"{a}. That cell is a name, not prose, so one of the two is "
                    f"simply wrong.\n"
                    f"           If English is right, edit THIS page. If English is "
                    f"wrong, edit whatever generates docs/en/{rel} and re-run it — "
                    f"editing the English page down to match a translation is the "
                    f"fast way to green and it is never the fix"
                )
                bad += 1
    return bad


# ── heading skeletons ────────────────────────────────────────────────────────

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

#: Any inline-code span inside a heading, whitespace included — and that is
#: where this rule is deliberately WIDER than `TOKEN_CELL`. A cell may hold a
#: phrase (`issued_at + 30 days`, correctly `issued_at + 30 Tage` in German), so
#: cells with a space in them are left alone. A heading holds a title, and a
#: code span in a title is the thing being titled: ``## There is no
#: `astra-plugin login` `` has a space in its span and is still a command line,
#: not German. Measured across the tree before widening it — 38 pages, six
#: locales, zero findings — so this costs nothing and catches the rename that
#: the narrow rule let through.
HEADING_TOKEN = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line: int

    @property
    def raw(self) -> str:
        """The heading line as it is written, which is what `GRANDFATHERED` keys on."""
        return "#" * self.level + " " + self.text

    @property
    def shape(self) -> tuple:
        """The part of a heading that is the same in every language."""
        return (self.level, tuple(HEADING_TOKEN.findall(self.text)))


def prose_lines(path: Path) -> list[tuple[int, str]]:
    """Every line of a page outside a fenced block, numbered.

    Same fence handling as `table_rows`, same reason — a sample may quote a
    heading or a digest it does not own. `spec/bundle-v2.md` fences two example
    manifests whose hashes are deliberately not this repository's.
    """
    out: list[tuple[int, str]] = []
    fence: str | None = None
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        f = DT.FENCE_RE.match(raw)
        if f:
            token = f.group("fence")
            if fence is None:
                fence = token[0] * len(token)
            elif raw.strip().startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        out.append((lineno, raw))
    return out


def headings(path: Path) -> list[Heading]:
    return [
        Heading(len(m.group(1)), m.group(2), lineno)
        for lineno, raw in prose_lines(path)
        if (m := HEADING_RE.match(raw))
    ]


def audit_grandfathered(en: set[str]) -> int:
    """The exemption list, held to its own rules before it is allowed to excuse anything.

    Four checks, and the order matters: the ceiling first, because that is the
    one that stops accretion; then the reason, because an exemption without one
    is indistinguishable from an exemption added to make a test pass; then that
    the heading it names still exists in English, because an exemption
    protecting nothing is a line nobody will ever delete.
    """
    bad = 0
    if len(GRANDFATHERED) > GRANDFATHERED_CEILING:
        print(
            f"CEILING  docs/tools/mirror.py  — GRANDFATHERED has "
            f"{len(GRANDFATHERED)} entr(ies) and GRANDFATHERED_CEILING is "
            f"{GRANDFATHERED_CEILING}. This list ratchets DOWN, so a new entry "
            f"is refused here rather than accepted quietly.\n"
            f"           Translating the section costs six files once. Every "
            f"entry on this list costs every reader of those six languages, "
            f"for as long as it stays. If it genuinely has to go on the list, "
            f"raise the ceiling to {len(GRANDFATHERED)} in the same commit — "
            f"deliberately, where a reviewer sees the number move"
        )
        bad += 1
    elif len(GRANDFATHERED) < GRANDFATHERED_CEILING:
        print(
            f"CEILING  docs/tools/mirror.py  — GRANDFATHERED has "
            f"{len(GRANDFATHERED)} entr(ies) and GRANDFATHERED_CEILING is "
            f"still {GRANDFATHERED_CEILING}. An entry left; lower the ceiling "
            f"to {len(GRANDFATHERED)} so the room it freed cannot be taken by "
            f"the next one without anybody deciding to give it"
        )
        bad += 1

    seen: set[tuple[str, str]] = set()
    for g in GRANDFATHERED:
        where = f"{g.page} :: {g.heading}"
        if (g.page, g.heading) in seen:
            print(f"REASON   {where}  — listed twice")
            bad += 1
        seen.add((g.page, g.heading))

        if not g.reason.startswith(LEAVE_PREFIX):
            print(
                f"REASON   {where}  — its reason must begin {LEAVE_PREFIX!r}. "
                f"An exemption has to name its own exit condition; a reason "
                f"that only explains why it exists is how a temporary "
                f"exemption becomes permanent"
            )
            bad += 1
        elif len(g.reason) < MIN_REASON:
            print(
                f"REASON   {where}  — its reason is {len(g.reason)} characters "
                f"and the floor is {MIN_REASON}. Say what would have to be true "
                f"for this entry to leave, and what its absence costs a reader"
            )
            bad += 1

        if g.page not in en:
            print(
                f"STALE    {where}  — docs/en/{g.page} does not exist. Delete "
                f"this entry and lower GRANDFATHERED_CEILING"
            )
            bad += 1
            continue
        hit = [h for h in headings(EN / g.page) if h.raw == g.heading]
        if len(hit) != 1:
            print(
                f"STALE    {where}  — appears {len(hit)} time(s) in "
                f"docs/en/{g.page}, expected exactly once. A renamed, "
                f"re-levelled or deleted English heading leaves this entry "
                f"excusing nothing; delete it and lower "
                f"GRANDFATHERED_CEILING, or correct it to the heading as "
                f"English writes it now"
            )
            bad += 1
    return bad


def compare_headings(rel: str, loc: str, en_page: Path, loc_page: Path) -> tuple[int, int]:
    """One translated page's heading skeleton against English's.

    Returns `(findings, headings compared)` — the second is the floor's
    evidence that this pass reached something.
    """
    exempt = {g.heading for g in GRANDFATHERED if g.page == rel}
    en_all = headings(en_page)
    expected = [h for h in en_all if h.raw not in exempt]
    got = headings(loc_page)

    for i in range(max(len(expected), len(got))):
        mine = expected[i] if i < len(expected) else None
        theirs = got[i] if i < len(got) else None
        if mine is not None and theirs is not None and mine.shape == theirs.shape:
            continue
        skipped = len(en_all) - len(expected)
        note = f", {skipped} grandfathered" if skipped else ""
        untranslated = (
            "Translate the section, or — if it is genuinely not going to be "
            "translated — add it to GRANDFATHERED in docs/tools/mirror.py with "
            "a reason and raise GRANDFATHERED_CEILING, which is a decision "
            "somebody has to make on purpose"
        )
        if mine is None:
            what = (
                f"docs/{loc}/{rel}:{theirs.line} has {theirs.raw!r} and "
                f"docs/en/{rel} has nothing left to mirror it"
            )
            remedy = (
                "A translated section whose English original is gone will "
                "never be corrected again and a reader has no way to tell. "
                "Delete it here, or restore the English heading it mirrors. "
                "If English still HAS that heading, a GRANDFATHERED entry is "
                "hiding it: the list excuses sections nobody translated, and "
                "it cannot be used to excuse one somebody did"
            )
        elif theirs is None:
            what = (
                f"docs/en/{rel}:{mine.line} is {mine.raw!r} and this "
                f"translation stops before it"
            )
            remedy = untranslated
        elif mine.level != theirs.level:
            what = (
                f"docs/en/{rel}:{mine.line} is a level-{mine.level} heading "
                f"and docs/{loc}/{rel}:{theirs.line} is level-{theirs.level} "
                f"({theirs.raw!r})"
            )
            remedy = untranslated
        else:
            what = (
                f"docs/en/{rel}:{mine.line} names {list(mine.shape[1])} and "
                f"docs/{loc}/{rel}:{theirs.line} names {list(theirs.shape[1])} "
                f"({theirs.raw!r}). A name inside a code span is a machine's "
                f"word and is the same in every language"
            )
            remedy = (
                "If English is right, carry the rename into this heading and "
                "the five other languages. If English is wrong, fix whatever "
                "renamed it — editing the English heading back to match a "
                "translation is the fast way to green and it is never the fix"
            )
        print(
            f"HEADING  docs/{loc}/{rel}  — {len(got)} heading(s) against "
            f"{len(expected)} to mirror{note}. First divergence at heading "
            f"{i + 1}: {what}.\n"
            f"           {remedy}"
        )
        return 1, min(len(expected), len(got))
    return 0, len(got)


# ── generated values ─────────────────────────────────────────────────────────

#: Eight or more hex digits, at least one of them a digit, bounded by
#: non-alphanumerics. The digit requirement is not paranoia about `deadbeef`:
#: it is what keeps an English word made of a–f out of a check that would
#: otherwise fire on prose in one language and not another.
DIGEST_RE = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*[0-9])[0-9a-f]{8,}(?![0-9A-Za-z])")


def digests(path: Path) -> Counter:
    found: Counter = Counter()
    for _, raw in prose_lines(path):
        for m in DIGEST_RE.finditer(raw):
            found[m.group(0)] += 1
    return found


def compare_digests(rel: str, loc: str, en_page: Path, loc_page: Path) -> int:
    """Every digest a translated page prints, against the English page's."""
    en, got = digests(en_page), digests(loc_page)
    bad = 0
    for value in sorted(set(en) | set(got)):
        if en[value] == got[value]:
            continue
        if got[value] and not en[value]:
            print(
                f"DIGEST   docs/{loc}/{rel}  — prints {value}…, which "
                f"docs/en/{rel} does not print at all. A hash is a machine's "
                f"word: this page is carrying a generation English has moved "
                f"past, and a reader checking a slice against it cannot tell "
                f"a stale page from a tampered slice"
            )
        elif en[value] and not got[value]:
            print(
                f"DIGEST   docs/{loc}/{rel}  — does not print {value}…, which "
                f"docs/en/{rel} does. Copy the English paragraph's value; it "
                f"is generated, and re-deriving it by hand is how this drifted "
                f"two generations the last time"
            )
        else:
            print(
                f"DIGEST   docs/{loc}/{rel}  — prints {value}… "
                f"{got[value]} time(s) and docs/en/{rel} prints it "
                f"{en[value]} time(s)"
            )
        bad += 1
    return bad


def pin_truth(pin: PinnedDigest) -> str | None:
    """The digest `pin.source` actually holds, or None if the file cannot say."""
    src = ROOT / pin.source
    if not src.is_file():
        return None
    m = re.search(pin.pattern, src.read_text(encoding="utf-8"), re.MULTILINE)
    return m.group(1) if m else None


def check_pinned() -> tuple[int, int]:
    """Every pinned digest, in every language, against the file that holds it.

    This is the rule that does not depend on English being right. Six
    translations compared with English go green the moment all seven agree on a
    wrong number, and the check that holds English to its generator reads one
    file. Returns `(findings, assertions made)`.
    """
    bad = 0
    made = 0
    for pin in PINNED_DIGESTS:
        truth = pin_truth(pin)
        if truth is None:
            print(
                f"PIN      {pin.source}  — no digest matching "
                f"{pin.pattern!r}. This is the ground truth for "
                f"`{pin.label}` on docs/*/{pin.page}; without it that value is "
                f"documented and verified by nothing"
            )
            bad += 1
            continue
        label = re.compile(
            rf"(?<![\w-]){re.escape(pin.label)}\s*[:=]\s*([0-9a-f]{{8,}})"
        )
        for loc in ("en",) + tuple(TRANSLATIONS):
            page = DOCS / loc / pin.page
            if not page.is_file():
                continue
            # Joined, because `ja` and `zh` wrap a line inside the code span
            # that carries the value and a line-at-a-time scan splits the
            # label off its digits.
            text = " ".join(raw for _, raw in prose_lines(page))
            hits = label.findall(text)
            if not hits:
                print(
                    f"PIN      docs/{loc}/{pin.page}  — no `{pin.label}` value "
                    f"in the prose of this page. If it deliberately stopped "
                    f"printing one, delete this PINNED_DIGESTS row; until then "
                    f"the row says a value is being checked here and none is"
                )
                bad += 1
                continue
            for hit in hits:
                made += 1
                if not truth.startswith(hit):
                    print(
                        f"PIN      docs/{loc}/{pin.page}  — says `{pin.label}: "
                        f"{hit}…` and {pin.source} says {truth[:len(hit)]}….\n"
                        f"           {pin.reason}"
                    )
                    bad += 1
    return bad, made


def pages(base: Path) -> set[str]:
    if not base.is_dir():
        return set()
    return {p.relative_to(base).as_posix() for p in base.rglob("*.md")}


def main() -> int:
    en = pages(EN)
    if not en:
        print("mirror: FAIL — docs/en has no pages", file=sys.stderr)
        return 1

    exemptions = audit_grandfathered(en)
    pinned, assertions = check_pinned()

    bad = 0
    drift = 0
    tables = 0
    skeleton = 0
    values = 0
    locales_seen = 0
    pages_compared = 0
    headings_compared = 0
    prose_scanned = 0
    for loc in TRANSLATIONS:
        base = DOCS / loc
        if not base.is_dir():
            print(f"MISSING  docs/{loc}/  — the locale directory does not exist")
            bad += 1
            continue
        locales_seen += 1
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
        shared = sorted(en & got)
        here = sum(compare_samples(rel, loc, EN / rel, base / rel) for rel in shared)
        rows = sum(compare_tables(rel, loc, EN / rel, base / rel) for rel in shared)
        heads = 0
        marks = 0
        for rel in shared:
            found, counted = compare_headings(rel, loc, EN / rel, base / rel)
            heads += found
            headings_compared += counted
            marks += compare_digests(rel, loc, EN / rel, base / rel)
            prose_scanned += len(prose_lines(base / rel))
        pages_compared = max(pages_compared, len(shared))
        drift += here
        tables += rows
        skeleton += heads
        values += marks
        if got == en and not (here or rows or heads or marks):
            print(f"ok       docs/{loc}/  — {len(got)} page(s), same set, same "
                  f"samples, same table names, same heading skeleton and same "
                  f"generated values as docs/en")

    # The floor. Every number above is evidence that this run reached
    # something; a guard that compared nothing and said "ok" is the failure
    # mode two checks in this repository shipped with.
    floor = 0
    for name, saw, least in (
        ("locales", locales_seen, FLOOR_LOCALES),
        ("pages", pages_compared, FLOOR_PAGES),
        ("headings", headings_compared, FLOOR_HEADINGS),
        ("prose lines", prose_scanned, FLOOR_PROSE_LINES),
    ):
        if saw < least:
            print(
                f"FLOOR    mirror.py  — compared {saw} {name}, and the floor "
                f"is {least}. Either this run reached far less of the tree "
                f"than it should have, or the tree really did shrink that far "
                f"and the floor is the thing to change — deliberately, in a "
                f"commit that says which"
            )
            floor += 1
    if assertions < len(PINNED_DIGESTS):
        print(
            f"FLOOR    mirror.py  — made {assertions} pinned-digest "
            f"assertion(s) for {len(PINNED_DIGESTS)} PINNED_DIGESTS row(s). A "
            f"row that asserts nothing is a row that says a value is watched "
            f"and does not watch it"
        )
        floor += 1

    total = bad + drift + tables + skeleton + values + exemptions + pinned + floor
    verdict = "ok" if not total else "FAIL"
    print(f"mirror: {verdict} — {len(en)} English page(s), "
          f"{len(TRANSLATIONS)} locale(s), {bad} page-set mismatch(es), "
          f"{drift} sample drift(s), {tables} table drift(s), "
          f"{skeleton} heading drift(s), {values} digest drift(s), "
          f"{exemptions} exemption fault(s), {pinned} pinned-digest fault(s)")
    print(f"mirror: floor — {locales_seen} locale(s), {pages_compared} page(s), "
          f"{headings_compared} heading(s), {prose_scanned} prose line(s), "
          f"{assertions} pinned-digest assertion(s), "
          f"{len(GRANDFATHERED)}/{GRANDFATHERED_CEILING} grandfathered")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
