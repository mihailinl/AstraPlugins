#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""C23b — what this tree says is published, held to what the registries hold.

    python3 tools/check-publication-state.py --tree-only     # the couplings job
    python3 tools/check-publication-state.py                 # scaffold-from-registries
    python3 tools/check-publication-state.py --registries fixture.json   # tests

C23 (in `ci.yml`'s couplings step) compares README's *In this tree* column with
the manifests, and says in as many words that the *Published* column is "a fact
about three registries" it does not ask. Nothing asked. So when the `sdk-v0.7.1`
train's `registries: npm` run put `astra-plugin-sdk` 0.7.0 on npm on
2026-08-25 and then went red in its summary job, the README went on saying
"0.6.0 — the 0.7.0 publish failed", the TypeScript CHANGELOG went on saying
`[0.7.0] — unreleased`, and ten commits landed under a version npm already had.
`release-sdks.yml` gate 1 was the first thing that would have noticed, on the
next release day (ops couplings register, entry 151).

Two groups of checks, split by what they need:

TREE (no network; the couplings job, on every pull request):
  - README's Publication state table still has its five rows. A table that
    stopped being one fails as unreadable, not as five rows that agreed with
    nothing.
  - Every docs locale restates the three scaffold pins twice — the "What the
    scaffold pins" table in `2-tutorial/getting-started.md`, and the fragment
    at the top of `4-sdk/{rust,python,typescript}.md`. Each copy must equal the
    pin `astra-plugin new` writes, and the table's Published cell must equal
    README's. Those pages said `^0.5.0` / `>=0.5,<0.6` / `"0.6"` for two
    releases after the scaffold stopped writing any of them.

REGISTRIES (asks crates.io, PyPI and npm; `scaffold-from-registries`, the job
that already depends on them):
  - README's Published cell for each SDK row is its registry's newest version;
    the CLI row says "not on crates.io" exactly while crates.io answers 404.
  - No CHANGELOG heading marked `unreleased` names a version its registry
    already has. This is entry 151's shape exactly, and it is the one that
    stops a release: gate 1 refuses to publish a version a registry holds.

Exit 0 when every check passes, 1 when one fails, 2 when a check could not be
run (a registry that answered neither a document nor a 404).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "docs" / "tools"))
from locales import LOCALES  # noqa: E402 — the one declaration of the docs set

# Seven locales x (one table with three rows + three SDK pages). Absolute, not
# derived: a LOCALES that lost entries would otherwise shrink the floor with it.
DOCS_FLOOR = 42
UA = {"User-Agent": "AstraPlugins CI (github.com/mihailinl/AstraPlugins)"}

# README row label -> (registry key, package name, CHANGELOG or None)
ROWS = {
    "`astra-plugin-sdk` (crates.io)": ("crates.io", "astra-plugin-sdk", "astra-plugin-sdk/CHANGELOG.md"),
    "`astra-plugin-sdk` (PyPI)": ("pypi", "astra-plugin-sdk", "astra-plugin-sdk-python/CHANGELOG.md"),
    "`astra-plugin-sdk` (npm)": ("npm", "astra-plugin-sdk", "astra-plugin-sdk-ts/CHANGELOG.md"),
    "`astra-plugin-macros` (crates.io)": ("crates.io", "astra-plugin-macros", None),
    "`astra-plugin-cli` (crates.io)": ("crates.io", "astra-plugin-cli", None),
}
NOT_PUBLISHED = "not on crates.io"
SEMVER = re.compile(r"\b(\d+\.\d+\.\d+)\b")

# language -> (template file, regex whose group 1 is the pin as a docs page writes it)
TEMPLATES = {
    "rust": ("astra-plugin-cli/src/templates/rust.rs", r'^(astra-plugin-sdk = "[^"]+")$'),
    "python": ("astra-plugin-cli/src/templates/python.rs", r'^\s*r#"(astra-plugin-sdk>=[^\n]+)$'),
    "ts": ("astra-plugin-cli/src/templates/typescript.rs", r'^\s*("astra-plugin-sdk": "[^"]+"),$'),
}
# the getting-started table's first cell per language, and its README row
TABLE_ROWS = {"rust": ("Rust", "`astra-plugin-sdk` (crates.io)"),
              "python": ("Python", "`astra-plugin-sdk` (PyPI)"),
              "ts": ("TypeScript", "`astra-plugin-sdk` (npm)")}
SDK_PAGES = {"rust": "4-sdk/rust.md", "python": "4-sdk/python.md", "ts": "4-sdk/typescript.md"}


class Fails:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.oks = 0

    def check(self, ok: bool, what: str, why: str = "") -> None:
        if ok:
            self.oks += 1
            print(f"ok   C23b {what}")
        else:
            self.fails.append(f"C23b {what}" + (f" — {why}" if why else ""))
            print(f"FAIL C23b {what}" + (f" — {why}" if why else ""))


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def readme_rows(root: Path) -> dict[str, str]:
    """Row label -> the Published cell, from README's Publication state table."""
    rows: dict[str, str] = {}
    for line in read(root, "README.md").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 5 and cells[1] in ROWS:
            rows[cells[1]] = cells[3]
    return rows


def changelog_unreleased(root: Path, rel: str) -> set[str]:
    out = set()
    for m in re.finditer(r"^## \[([^\]]+)\]\s*[—-]\s*(.+)$", read(root, rel), re.M):
        if m.group(2).strip().lower().startswith("unreleased"):
            out.add(m.group(1))
    return out


def template_pins(root: Path) -> dict[str, str]:
    pins = {}
    for lang, (rel, pat) in TEMPLATES.items():
        found = re.findall(pat, read(root, rel), re.M)
        # Every template writes its pin in one shape; two different pins in one
        # template is a template disagreeing with itself.
        pins[lang] = found[0] if found and len(set(found)) == 1 else None
    return pins


def tree_checks(root: Path, f: Fails) -> dict[str, str]:
    rows = readme_rows(root)
    f.check(len(rows) == len(ROWS), f"README's Publication state table still has its {len(ROWS)} rows",
            f"read {sorted(rows)}; the table is under '## Publication state' in README.md")

    pins = template_pins(root)
    for lang, pin in pins.items():
        f.check(pin is not None, f"the {lang} scaffold template declares one SDK pin", TEMPLATES[lang][0])

    seen = 0
    for loc in LOCALES:
        gs = read(root, f"docs/{loc}/2-tutorial/getting-started.md")
        for lang, (label, readme_label) in TABLE_ROWS.items():
            m = re.search(rf"^\| {label} \| `([^`]+)` \| (.+?) \|$", gs, re.M)
            f.check(m is not None, f"docs/{loc}/2-tutorial/getting-started.md has the {label} pin row",
                    "the 'What the scaffold pins' table lost a row")
            if not m or pins[lang] is None:
                continue
            seen += 1
            f.check(m.group(1) == pins[lang],
                    f"docs/{loc}/2-tutorial/getting-started.md's {label} pin is the scaffold's",
                    f"the page says `{m.group(1)}`, {TEMPLATES[lang][0]} writes `{pins[lang]}`")
            want = SEMVER.search(rows.get(readme_label, ""))
            got = SEMVER.search(m.group(2))
            f.check(bool(want and got and want.group(1) == got.group(1)),
                    f"docs/{loc}/2-tutorial/getting-started.md's {label} Published cell is README's",
                    f"the page says '{m.group(2)}', README says '{rows.get(readme_label, '(no row)')}'")
        for lang, page in SDK_PAGES.items():
            text = read(root, f"docs/{loc}/{page}")
            if pins[lang] is None:
                continue
            seen += 1
            f.check(pins[lang] in text, f"docs/{loc}/{page} shows the scaffold's pin `{pins[lang]}`",
                    "its dependency fragment names a pin `astra-plugin new` does not write")
    # FLOOR: 7 locales x (3 table rows + 3 pages). A glob that matched nothing
    # would otherwise pass with nothing compared.
    f.check(seen >= DOCS_FLOOR and seen == len(LOCALES) * 6,
            f"compared {seen} docs pin restatements (floor {DOCS_FLOOR})",
            f"expected {len(LOCALES) * 6} for {len(LOCALES)} locales, and never fewer than {DOCS_FLOOR}")
    return rows


def fetch(url: str) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, None


def live_registries() -> dict[str, dict | None]:
    """The fixture shape: `<registry>/<package>` -> {latest, versions} or None (404)."""
    out: dict[str, dict | None] = {}
    for key, name in sorted({(k, n) for k, n, _ in ROWS.values()}):
        url = {"crates.io": f"https://crates.io/api/v1/crates/{name}",
               "pypi": f"https://pypi.org/pypi/{name}/json",
               "npm": f"https://registry.npmjs.org/{name}"}[key]
        status, doc = fetch(url)
        if status == 404:
            out[f"{key}/{name}"] = None
            continue
        if status != 200 or doc is None:
            raise SystemExit(f"C23b could not ask {url}: HTTP {status}; refusing to guess (exit 2)")
        if key == "crates.io":
            versions = [v["num"] for v in doc["versions"] if not v.get("yanked")]
            latest = doc["crate"]["max_version"]
        elif key == "pypi":
            versions = list(doc["releases"])
            latest = doc["info"]["version"]
        else:
            versions = list(doc["versions"])
            latest = doc["dist-tags"]["latest"]
        out[f"{key}/{name}"] = {"latest": latest, "versions": versions}
    return out


def registry_checks(root: Path, rows: dict[str, str], reg: dict[str, dict | None], f: Fails) -> None:
    for label, (key, name, changelog) in ROWS.items():
        cell = rows.get(label)
        if cell is None:
            continue
        where = f"{key}/{name}"
        if where not in reg:
            f.check(False, f"{where} was asked", "the registry answers carry no entry for it")
            continue
        ans = reg[where]
        if ans is None:
            f.check(NOT_PUBLISHED in cell, f"README says {name} is not on {key}, and {key} answers 404",
                    f"the Published cell reads '{cell}'")
        else:
            m = SEMVER.search(cell)
            f.check(bool(m) and m.group(1) == ans["latest"],
                    f"README's Published cell for {label} is {key}'s newest, {ans['latest']}",
                    f"the cell reads '{cell}' — edit the Publication state table in README.md")
        if changelog:
            have = set(ans["versions"]) if ans else set()
            for ver in sorted(changelog_unreleased(root, changelog)):
                f.check(ver not in have, f"{changelog}'s `[{ver}] — unreleased` is not on {key}",
                        f"{key} already has {name} {ver}: date that heading, and give the tree's "
                        "package the next version — release-sdks.yml gate 1 refuses to publish "
                        "a version a registry holds")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--root", default=str(ROOT), help="the tree to check (default: this checkout)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--tree-only", action="store_true", help="skip the registry checks")
    g.add_argument("--registries", metavar="JSON", help="registry answers from a file, not the network")
    args = ap.parse_args(argv)

    root = Path(args.root)
    f = Fails()
    rows = tree_checks(root, f)
    if args.tree_only:
        print("note C23b's registry checks NOT run (--tree-only); scaffold-from-registries runs them")
    else:
        reg = (json.loads(Path(args.registries).read_text(encoding="utf-8"))
               if args.registries else live_registries())
        registry_checks(root, rows, reg, f)

    if f.fails:
        print(f"\n{len(f.fails)} C23b check(s) failed:", file=sys.stderr)
        for x in f.fails:
            print("  " + x, file=sys.stderr)
        return 1
    print(f"C23b: {f.oks} checks pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
