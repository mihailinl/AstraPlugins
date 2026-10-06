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

def registries_matching_this_tree() -> dict:
    """Registry answers that agree with this tree's README, whatever it says today.

    Derived, never typed: a fixture written as "what the registries held on the
    day" goes red on the first correct post-release commit, which is the one
    moment this check must be green. Each package's newest version is README's
    Published cell; the CLI row is a 404.
    """
    rows = cps.readme_rows(ROOT)
    out: dict = {}
    for label, (key, name, _) in cps.ROWS.items():
        cell = rows.get(label, "")
        m = cps.SEMVER.search(cell)
        if cps.NOT_PUBLISHED in cell or not m:
            out[f"{key}/{name}"] = None
        else:
            out[f"{key}/{name}"] = {"latest": m.group(1), "versions": [m.group(1)]}
    return out


REGISTRIES = registries_matching_this_tree()


def published(key: str) -> str:
    return REGISTRIES[key]["latest"]


def files() -> list[str]:
    out = ["README.md"]
    out += [r[2] for r in cps.ROWS.values() if r[2]]
    out += [t[0] for t in cps.TEMPLATES.values()]
    for loc in cps.LOCALES:
        out.append(f"docs/{loc}/2-tutorial/getting-started.md")
        out += [f"docs/{loc}/{p}" for p in cps.SDK_PAGES.values()]
    out += [r[0] for r in cps.PACKAGE_READMES.values()]
    out += list(cps.CLAIM_FILES)
    out += [r for r in cps.RELEASE_LINK_FILES if (ROOT / r).is_file()]
    out += [f"docs/{loc}/install-cli.md" for loc in cps.LOCALES]
    return list(dict.fromkeys(out))


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


PINS = cps.template_pins(ROOT)
# Lines that exist in this tree and are not claims, to insert a claim after.
AGENTS_ANCHOR = "## 6 · If you find a bug, say so"
MACROS_ANCHOR = "Repository: <https://github.com/mihailinl/AstraPlugins>"


def agents_sentence(crates: str, pypi: str, npm: str) -> str:
    return (f"Never invent a version — `astra-plugin-sdk` is {crates} on crates.io, {pypi} on PyPI,\n"
            f"{npm} on npm, and the CLI is published nowhere.\n")


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
        """npm has version N; the tree calls N unreleased and says npm is behind it.

        On 2026-08-25 N was 0.7.0 and the README said "0.6.0 — the 0.7.0 publish
        failed". Rebuilt from whatever npm version this tree names, so the case
        stays the case as the tree moves on.
        """
        n = published("npm/astra-plugin-sdk")
        with Tree() as t:
            t.edit("README.md", ts_row(),
                   f"| `astra-plugin-sdk` (npm) | {n} | **0.0.1 — the {n} publish failed**, "
                   "see below | `npm install astra-plugin-sdk` |")
            t.edit("astra-plugin-sdk-ts/CHANGELOG.md", ts_heading(), f"## [{n}] — unreleased")
            code, out = t.run(REGISTRIES)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b README's Published cell for `astra-plugin-sdk` (npm) is npm's newest, {n}", out)
        self.assertIn(f"FAIL C23b astra-plugin-sdk-ts/CHANGELOG.md's `[{n}] — unreleased` is not on npm", out)
        self.assertIn("gate 1 refuses", out)

    def test_an_unreleased_heading_is_red_on_its_own(self):
        """The CHANGELOG half alone, with README right: the release-blocking half."""
        n = published("npm/astra-plugin-sdk")
        with Tree() as t:
            t.edit("astra-plugin-sdk-ts/CHANGELOG.md", ts_heading(), f"## [{n}] — unreleased")
            code, out = t.run(REGISTRIES)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b astra-plugin-sdk-ts/CHANGELOG.md's `[{n}] — unreleased` is not on npm", out)
        self.assertNotIn("FAIL C23b README's Published cell", out)

    def test_a_cli_that_reached_crates_io_is_red(self):
        reg = {**REGISTRIES, "crates.io/astra-plugin-cli": {"latest": "9.9.9", "versions": ["9.9.9"]}}
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
        # npm's page for the package, too: it restates the pin in prose.
        self.assertIn(f"FAIL C23b astra-plugin-sdk-ts/README.md's pin `{PINS['ts']}` is the scaffold's", out)

    def test_the_floor_counts_what_was_compared(self):
        with Tree() as t:
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 0, out)
        self.assertIn(f"compared {len(cps.LOCALES) * 6} docs pin restatements", out)

    # ── the package READMEs: the pages crates.io, PyPI and npm show ──────────

    def test_package_readmes_on_last_trains_pins_are_red_naming_each(self):
        """The 2026-10-04 shape: 0.7.2 / 0.6.2 / 0.7.1 published, and the three
        registry pages still said `"0.6"`, `>=0.5,<0.6` and `^0.5.0`."""
        with Tree() as t:
            t.edit("astra-plugin-sdk/README.md", PINS["rust"], 'astra-plugin-sdk = "0.6"')
            t.edit("astra-plugin-sdk-python/README.md", f'pip install "{PINS["python"]}"',
                   'pip install "astra-plugin-sdk>=0.5,<0.6"')
            t.edit("astra-plugin-sdk-ts/README.md", f"pins `{PINS['ts']}`", "pins `^0.5.0`")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b astra-plugin-sdk/README.md's pin `astra-plugin-sdk = \"0.6\"` is the scaffold's", out)
        self.assertIn("FAIL C23b astra-plugin-sdk-python/README.md's pin `astra-plugin-sdk>=0.5,<0.6` is the scaffold's", out)
        self.assertIn("FAIL C23b astra-plugin-sdk-ts/README.md's pin `^0.5.0` is the scaffold's", out)
        self.assertIn("the page PyPI shows for the package", out)
        self.assertEqual(out.count("\nFAIL "), 3, out)

    def test_a_stale_pin_beside_the_right_one_is_still_red(self):
        """`contains the pin` is not the question: a page showing two pins tells
        half its readers the wrong one."""
        with Tree() as t:
            t.edit("astra-plugin-sdk/README.md", f"{PINS['rust']}\n", f"{PINS['rust']}\n# or\nastra-plugin-sdk = \"0.5\"\n")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b astra-plugin-sdk/README.md's pin `astra-plugin-sdk = \"0.5\"` is the scaffold's", out)
        self.assertNotIn(f"FAIL C23b astra-plugin-sdk/README.md's pin `{PINS['rust']}`", out)

    def test_a_package_readme_that_lost_its_pin_is_red(self):
        with Tree() as t:
            t.edit("astra-plugin-sdk-python/README.md", f'pip install "{PINS["python"]}"\n', "")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b astra-plugin-sdk-python/README.md shows the python scaffold's pin `{PINS['python']}`", out)

    # ── sentences that say what is published ─────────────────────────────────

    def test_agents_md_repeating_the_published_versions_is_green_while_they_agree(self):
        """Repeating README's table is allowed; it is checked, not forbidden."""
        with Tree() as t:
            t.edit("AGENTS.md", AGENTS_ANCHOR, AGENTS_ANCHOR + "\n" + agents_sentence(
                published("crates.io/astra-plugin-sdk"), published("pypi/astra-plugin-sdk"),
                published("npm/astra-plugin-sdk")))
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 0, out)
        self.assertIn("note C23b read 3 published-version claim(s)", out)

    def test_agents_md_with_the_old_sentence_is_red_naming_all_three(self):
        """What AGENTS.md said under "Never invent a version" until 2026-10-04."""
        with Tree() as t:
            t.edit("AGENTS.md", AGENTS_ANCHOR, AGENTS_ANCHOR + "\n" + agents_sentence("0.6.0", "0.5.0", "0.5.0"))
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b AGENTS.md says 0.6.0 is on crates.io, as README's Published column does", out)
        self.assertIn("FAIL C23b AGENTS.md says 0.5.0 is on PyPI, as README's Published column does", out)
        self.assertIn("FAIL C23b AGENTS.md says 0.5.0 is on npm, as README's Published column does", out)
        self.assertIn("point at that table rather than repeat it", out)
        self.assertEqual(out.count("\nFAIL "), 3, out)

    def test_the_next_train_turns_a_true_restatement_red(self):
        """The failure this exists for is time, not a typo: the sentence was true
        when written. Move README's PyPI cell on and AGENTS.md's copy goes red."""
        n = published("pypi/astra-plugin-sdk")
        with Tree() as t:
            t.edit("AGENTS.md", AGENTS_ANCHOR, AGENTS_ANCHOR + f"\nPyPI has {n} on PyPI today.")
            row = next(l for l in (t.dir / "README.md").read_text(encoding="utf-8").splitlines()
                       if l.startswith("| `astra-plugin-sdk` (PyPI) |"))
            cells = row.split("|")
            cells[3] = " 9.9.9 "
            t.edit("README.md", row, "|".join(cells))
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b AGENTS.md says {n} is on PyPI, as README's Published column does", out)

    def test_a_version_on_the_wrong_registry_is_red(self):
        """npm's version said of PyPI: a real version, and not PyPI's."""
        ts = published("npm/astra-plugin-sdk")
        py = published("pypi/astra-plugin-sdk")
        self.assertNotEqual(ts, py, "the case needs the two registries at different versions")
        with Tree() as t:
            t.edit("AGENTS.md", AGENTS_ANCHOR, AGENTS_ANCHOR + f"\nThe SDK is {ts} on PyPI.")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b AGENTS.md says {ts} is on PyPI, as README's Published column does", out)

    def test_the_macros_page_calling_itself_unpublished_is_red(self):
        """crates.io showed "Not published to crates.io yet" on the page of every
        astra-plugin-macros release from 0.6.0 to 0.7.2."""
        with Tree() as t:
            t.edit("astra-plugin-macros/README.md", MACROS_ANCHOR,
                   MACROS_ANCHOR + "\nNot published to crates.io yet — `index.crates.io` has no entry for it.")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b astra-plugin-macros/README.md calls its package unpublished, as README's Published column does", out)

    def test_the_python_page_saying_published_at_an_old_version_is_red(self):
        with Tree() as t:
            t.edit("docs/en/4-sdk/python.md", "\n## See also\n",
                   "\n- **The Python SDK is published at 0.5.0**, so a fresh scaffold resolves.\n\n## See also\n")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL C23b docs/en/4-sdk/python.md says the SDK is published at 0.5.0", out)

    def test_published_at_is_read_against_the_pages_own_registry(self):
        """npm's version on the PyPI page is still wrong, though README has it."""
        ts = published("npm/astra-plugin-sdk")
        py = published("pypi/astra-plugin-sdk")
        self.assertNotEqual(ts, py, "the case needs the two registries at different versions")
        with Tree() as t:
            t.edit("docs/en/4-sdk/python.md", "\n## See also\n",
                   f"\nThe SDK is published at {ts}.\n\n## See also\n")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b docs/en/4-sdk/python.md says the SDK is published at {ts}", out)


def rel_definition(rel: str) -> tuple[str, str]:
    """The `[rel]: …/releases/tag/<tag>` line in a tree file, and its tag."""
    import re
    m = re.search(r"^\[rel\]: https://github\.com/mihailinl/AstraPlugins/releases/tag/(\S+)$",
                  (ROOT / rel).read_text(encoding="utf-8"), re.M)
    if not m:
        raise AssertionError(f"{rel} has no [rel] release definition")
    return m.group(0), m.group(1)


class C23bReleaseLinks(unittest.TestCase):
    """README said "Release [`cli-v0.2.1`][rel]" and `[rel]` opened cli-v0.3.0 (to 2026-10-05)."""

    def test_the_2026_10_05_readme_is_red(self):
        """The label names one release, the definition thirty lines below opens another."""
        line, tag = rel_definition("README.md")
        with Tree() as t:
            t.edit("README.md", line, line.replace(tag, "cli-v0.0.1"))
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b README.md's link labelled `{tag}` opens {tag}", out)
        self.assertIn("it opens cli-v0.0.1", out)

    def test_an_inline_link_in_the_publication_state_row_is_compared_too(self):
        import re
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        m = re.search(r"\[`(cli-v[0-9.]+)`\]\((https://github\.com/mihailinl/AstraPlugins/releases/tag/cli-v[0-9.]+)\)", text)
        self.assertIsNotNone(m, "README's CLI row has no inline release link")
        with Tree() as t:
            t.edit("README.md", m.group(0), f"[`{m.group(1)}`]({m.group(2).rsplit('/', 1)[0]}/cli-v0.0.1)")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b README.md's link labelled `{m.group(1)}` opens {m.group(1)}", out)

    def test_one_translation_drifting_is_red_naming_it(self):
        line, tag = rel_definition("docs/ja/install-cli.md")
        with Tree() as t:
            t.edit("docs/ja/install-cli.md", line, line.replace(tag, "cli-v0.0.1"))
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b docs/ja/install-cli.md's link labelled `{tag}` opens {tag}", out)
        self.assertNotIn("FAIL C23b docs/en/install-cli.md", out)

    def test_a_label_whose_definition_is_gone_is_red(self):
        line, tag = rel_definition("README.md")
        with Tree() as t:
            t.edit("README.md", line + "\n", "")
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b README.md's link [`{tag}`][rel] is defined", out)

    def test_the_floor_counts_what_was_compared(self):
        """A docs tree that lost install-cli.md compares two links, not nine, and says so."""
        with Tree() as t:
            for loc in cps.LOCALES:
                (t.dir / f"docs/{loc}/install-cli.md").unlink()
            code, out = t.run(None, tree_only=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAIL C23b compared 2 release links (floor {cps.RELEASE_LINK_FLOOR})", out)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    # No test ran is not a pass.
    sys.exit(0 if result.wasSuccessful() and result.testsRun >= 24 else 1)
