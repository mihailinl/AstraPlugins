#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""C23b, run against trees and registry answers built to be wrong.

    python3 tools/test_publication_state.py        # what the couplings job runs

`tools/check-publication-state.py` asks three registries in
`scaffold-from-registries`, and a check that only ever runs against the live
world has only ever seen the live world's answer. The case it exists for —
a registry holding a version the tree calls unreleased (ops couplings register,
entry 151) — was true for a month and is not true today, so it is rebuilt
here: this tree's files are copied to a temporary directory, bent back into the
2026-08-25 shape, and handed registry answers from a fixture. No network.
"""

from __future__ import annotations

import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cps", ROOT / "tools/check-publication-state.py")
cps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cps)

# What the registries held when this test was written (2026-09-24). Only the
# shape matters to the cases below; each case edits the answer it is about.
REGISTRIES = {
    "crates.io/astra-plugin-sdk": {"latest": "0.7.1", "versions": ["0.6.0", "0.7.0", "0.7.1"]},
    "crates.io/astra-plugin-macros": {"latest": "0.7.1", "versions": ["0.6.0", "0.7.0", "0.7.1"]},
    "crates.io/astra-plugin-cli": None,
    "pypi/astra-plugin-sdk": {"latest": "0.6.1", "versions": ["0.5.0", "0.6.0", "0.6.1"]},
    "npm/astra-plugin-sdk": {"latest": "0.7.0", "versions": ["0.5.0", "0.6.0", "0.7.0"]},
}


def files() -> list[str]:
    out = ["README.md"]
    out += [r[2] for r in cps.ROWS.values() if r[2]]
    out += [t[0] for t in cps.TEMPLATES.values()]
    for loc in cps.LOCALES:
        out.append(f"docs/{loc}/2-tutorial/getting-started.md")
        out += [f"docs/{loc}/{p}" for p in cps.SDK_PAGES.values()]
    return out


class Tree:
    """A copy of the files C23b reads, to be bent."""

    def __enter__(self) -> "Tree":
        self.dir = Path(tempfile.mkdtemp(prefix="c23b-"))
        for rel in files():
            dst = self.dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dst)
        return self

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.dir)

    def edit(self, rel: str, old: str, new: str) -> None:
        p = self.dir / rel
        text = p.read_text(encoding="utf-8")
        # An anchor that matched nothing would leave the tree correct and the
        # case vacuous, which reads exactly like the check missing the break.
        if text.count(old) != 1:
            raise AssertionError(f"{rel}: anchor {old!r} matched {text.count(old)} times, not once")
        p.write_text(text.replace(old, new), encoding="utf-8")

    def run(self, registries: dict | None, tree_only: bool = False) -> tuple[int, str]:
        import json
        argv = ["--root", str(self.dir)]
        if tree_only:
            argv.append("--tree-only")
        else:
            fx = self.dir / "registries.json"
            fx.write_text(json.dumps(registries), encoding="utf-8")
            argv += ["--registries", str(fx)]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cps.main(argv)
        return code, out.getvalue() + err.getvalue()


def ts_row() -> str:
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| `astra-plugin-sdk` (npm) |"):
            return line
    raise AssertionError("README has no npm row")


def ts_heading() -> str:
    import re
    text = (ROOT / "astra-plugin-sdk-ts/CHANGELOG.md").read_text(encoding="utf-8")
    return re.search(r"^## \[[^\]]+\] — .+$", text, re.M).group(0)


class C23b(unittest.TestCase):
    def test_this_tree_passes_against_the_registries_it_was_written_for(self):
        with Tree() as t:
            code, out = t.run(REGISTRIES)
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAIL", out)

    def test_entry_151_is_red_and_names_npm(self):
        """npm has 0.7.0; the tree calls 0.7.0 unreleased and says npm is at 0.6.0."""
        with Tree() as t:
            t.edit("README.md", ts_row(),
                   "| `astra-plugin-sdk` (npm) | 0.7.0 | **0.6.0 — the 0.7.0 publish failed**, "
                   "see below | `npm install astra-plugin-sdk` |")
            # The TS CHANGELOG as it read from 83c4a9f until this commit: one
            # `[0.7.0] — unreleased` heading on top, and no 0.7.1.
            t.edit("astra-plugin-sdk-ts/CHANGELOG.md", ts_heading(), "## [0.7.0] — unreleased")
            code, out = t.run(REGISTRIES)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b README's Published cell for `astra-plugin-sdk` (npm) is npm's newest, 0.7.0", out)
        self.assertIn("FAIL C23b astra-plugin-sdk-ts/CHANGELOG.md's `[0.7.0] — unreleased` is not on npm", out)
        self.assertIn("gate 1 refuses", out)

    def test_an_unreleased_heading_is_red_on_its_own(self):
        """The CHANGELOG half alone, with README right: the release-blocking half."""
        reg = {**REGISTRIES, "npm/astra-plugin-sdk": {"latest": "0.7.0",
                                                      "versions": ["0.6.0", "0.7.0", "0.7.1"]}}
        with Tree() as t:
            code, out = t.run(reg)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b astra-plugin-sdk-ts/CHANGELOG.md's `[0.7.1] — unreleased` is not on npm", out)

    def test_a_cli_that_reached_crates_io_is_red(self):
        reg = {**REGISTRIES, "crates.io/astra-plugin-cli": {"latest": "0.3.0", "versions": ["0.3.0"]}}
        with Tree() as t:
            code, out = t.run(reg)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b README's Published cell for `astra-plugin-cli` (crates.io) is crates.io's newest", out)

    def test_a_cli_row_claiming_crates_io_while_it_answers_404_is_red(self):
        """The other direction: the README says the CLI is on crates.io, and it is not."""
        with Tree() as t:
            text = (t.dir / "README.md").read_text(encoding="utf-8")
            row = next(l for l in text.splitlines() if l.startswith("| `astra-plugin-cli` (crates.io) |"))
            cells = row.split("|")
            cells[3] = " 0.4.0 "
            t.edit("README.md", row, "|".join(cells))
            code, out = t.run(REGISTRIES)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b README says astra-plugin-cli is not on crates.io, and crates.io answers 404", out)

    def test_a_table_that_lost_a_row_fails_as_unreadable(self):
        with Tree() as t:
            t.edit("README.md", ts_row() + "\n", "")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b README's Publication state table still has its 5 rows", out)

    def test_a_docs_pin_that_drifted_in_one_locale_is_red_naming_it(self):
        with Tree() as t:
            t.edit("docs/ja/2-tutorial/getting-started.md",
                   '`"astra-plugin-sdk": "^0.7.0"` |', '`"astra-plugin-sdk": "^0.6.0"` |')
            t.edit("docs/uk/4-sdk/python.md", "\nastra-plugin-sdk>=0.6,<0.7\n", "\nastra-plugin-sdk>=0.5,<0.6\n")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b docs/ja/2-tutorial/getting-started.md's TypeScript pin is the scaffold's", out)
        self.assertIn("FAIL C23b docs/uk/4-sdk/python.md shows the scaffold's pin", out)
        self.assertEqual(out.count("\nFAIL "), 2, out)

    def test_a_template_repinned_without_its_docs_is_red_in_every_locale(self):
        with Tree() as t:
            t.edit("astra-plugin-cli/src/templates/typescript.rs",
                   '"astra-plugin-sdk": "^0.7.0",', '"astra-plugin-sdk": "^0.8.0",')
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        for loc in cps.LOCALES:
            self.assertIn(f"FAIL C23b docs/{loc}/2-tutorial/getting-started.md's TypeScript pin", out)
            self.assertIn(f"FAIL C23b docs/{loc}/4-sdk/typescript.md shows the scaffold's pin", out)

    def test_the_floor_counts_what_was_compared(self):
        with Tree() as t:
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 0, out)
        self.assertIn(f"compared {len(cps.LOCALES) * 6} docs pin restatements", out)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    # No test ran is not a pass.
    sys.exit(0 if result.wasSuccessful() and result.testsRun >= 9 else 1)
