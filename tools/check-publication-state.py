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
  - Each SDK's package README — the page crates.io, PyPI and npm show for it —
    shows the scaffold's pin, and no other pin in the same shape. On
    2026-10-04, the day 0.7.2 / 0.6.2 / 0.7.1 published, those three pages
    still said `"0.6"`, `>=0.5,<0.6` and `^0.5.0`, and the PyPI one installs
    0.5.0 for anyone who copies its first command.
  - A claim that a version is on a registry — "0.6.0 on crates.io", "published
    at 0.5.0" — in AGENTS.md, CONTRIBUTING.md, the package READMEs and the
    English SDK and troubleshooting pages is README's Published cell for that
    registry, and a package README that calls its package unpublished belongs
    to a row whose Published cell says so. AGENTS.md said "0.6.0 on
    crates.io, 0.5.0 on PyPI, 0.5.0 on npm" under "Never invent a version" two
    trains after it stopped being true, and `astra-plugin-macros`' crates.io
    page said "Not published to crates.io yet" from 0.6.0 to 0.7.2. Pointing
    at the Publication state table is always green; repeating it is green
    exactly while it agrees.
  - A link whose text is a release tag opens that release. README's "Release
    [`cli-v0.2.1`][rel] carries ..." opened `cli-v0.3.0`: the label and the
    `[rel]:` line thirty lines below it were edited on different days, and
    nothing read them together. Every such link in README, AGENTS.md,
    CONTRIBUTING.md, the CLI's README and the docs, inline or by reference, is
    compared, with a floor (README's two, and each locale's install-cli.md).

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

# language -> (the package README, which is the registry's page for it; every
# pin-shaped string in it). The TypeScript README states its pin in prose, so a
# bare range after "pins" counts too: that is the shape that said `^0.5.0`.
PACKAGE_READMES = {
    "rust": ("astra-plugin-sdk/README.md", r'astra-plugin-sdk = "[^"\n]*"'),
    "python": ("astra-plugin-sdk-python/README.md", r'astra-plugin-sdk[<>=!~][^"\s`]*'),
    "ts": ("astra-plugin-sdk-ts/README.md", r'"astra-plugin-sdk": "[^"\n]*"|(?<=pins `)[\^~][^`]+(?=`)'),
}
# package README -> its row in README's Publication state table
README_ROWS = {
    "astra-plugin-sdk/README.md": "`astra-plugin-sdk` (crates.io)",
    "astra-plugin-sdk-python/README.md": "`astra-plugin-sdk` (PyPI)",
    "astra-plugin-sdk-ts/README.md": "`astra-plugin-sdk` (npm)",
    "astra-plugin-macros/README.md": "`astra-plugin-macros` (crates.io)",
}
# Where a sentence about what is published lives, and the registry a bare
# "published at X" in it means (None: the file is about all of them).
CLAIM_FILES = {
    "AGENTS.md": None,
    "CONTRIBUTING.md": None,
    "astra-plugin-sdk/README.md": "crates.io",
    "astra-plugin-sdk-python/README.md": "pypi",
    "astra-plugin-sdk-ts/README.md": "npm",
    "astra-plugin-macros/README.md": "crates.io",
    "docs/en/4-sdk/rust.md": "crates.io",
    "docs/en/4-sdk/python.md": "pypi",
    "docs/en/4-sdk/typescript.md": "npm",
    "docs/en/6-operate/troubleshooting.md": None,
}
# "0.6.0 on crates.io", "**0.5.0** on PyPI"
ON_REGISTRY = re.compile(r"\b(\d+\.\d+\.\d+)\W{0,3}\s+on\s+(crates\.io|PyPI|npm)\b", re.I)
# "published at 0.5.0", "is published as **0.6.1**"
PUBLISHED_AT = re.compile(r"\bpublished\W{0,3}\s+(?:at|as)\s+\W{0,3}(\d+\.\d+\.\d+)\b", re.I)
DISPLAY = {"crates.io": "crates.io", "pypi": "PyPI", "npm": "npm"}
UNPUBLISHED = re.compile(r"\bnot (?:yet )?published\b|\bunpublished\b|\bnot on (?:crates\.io|PyPI|npm)\b", re.I)
# [`cli-v0.4.0`](https://…/releases/tag/cli-v0.4.0) and [`cli-v0.4.0`][rel]
RELEASE_LABEL = re.compile(r"\[`?([a-z][a-z0-9-]*-v\d+\.\d+\.\d+)`?\](?:\(([^)\s]+)\)|\[([^\]]+)\])")
RELEASE_URL = re.compile(r"/releases/(?:tag|download)/([^/\s)#?]+)")
REF_DEF = re.compile(r"^\[([^\]]+)\]:\s*(\S+)", re.M)
RELEASE_LINK_FILES = ("README.md", "AGENTS.md", "CONTRIBUTING.md", "astra-plugin-cli/README.md")
# README's two (the download paragraph, the Publication state row) and one per
# locale's install-cli.md. Absolute, for the same reason DOCS_FLOOR is.
RELEASE_LINK_FLOOR = 9


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
    package_readme_checks(root, pins, f)
    claim_checks(root, rows, f)
    release_link_checks(root, f)
    return rows


def package_readme_checks(root: Path, pins: dict[str, str | None], f: Fails) -> None:
    """Each SDK's registry page shows the pin `astra-plugin new` writes, and only that one."""
    for lang, (rel, shape) in PACKAGE_READMES.items():
        pin = pins[lang]
        if pin is None:
            continue  # already a failure above: the template declares no single pin
        rng = re.search(r'": "([^"]+)"$', pin)
        accepted = {pin} | ({rng.group(1)} if rng else set())
        found = list(dict.fromkeys(re.findall(shape, read(root, rel))))
        f.check(bool(found), f"{rel} shows the {lang} scaffold's pin `{pin}`",
                f"it shows no SDK pin at all; {TEMPLATES[lang][0]} writes `{pin}`")
        for got in found:
            f.check(got in accepted, f"{rel}'s pin `{got}` is the scaffold's",
                    f"{TEMPLATES[lang][0]} writes `{pin}`, and this README is the page "
                    f"{DISPLAY[ROWS[README_ROWS[rel]][0]]} shows for the package")


def published_by_registry(rows: dict[str, str]) -> dict[str, set[str]]:
    """registry key -> the versions README's Published cells give for it."""
    out: dict[str, set[str]] = {}
    for label, (key, _, _) in ROWS.items():
        cell = rows.get(label, "")
        m = SEMVER.search(cell)
        if m and NOT_PUBLISHED not in cell:
            out.setdefault(key, set()).add(m.group(1))
    return out


def claim_checks(root: Path, rows: dict[str, str], f: Fails) -> None:
    """A sentence saying what is published says what README's table says."""
    pub = published_by_registry(rows)
    every = set().union(*pub.values()) if pub else set()
    seen = 0
    for rel, default in CLAIM_FILES.items():
        text = read(root, rel)
        line = lambda m: text.count("\n", 0, m.start()) + 1  # noqa: E731
        for m in ON_REGISTRY.finditer(text):
            seen += 1
            ver, reg = m.group(1), m.group(2)
            have = pub.get(reg.lower(), set())
            f.check(ver in have, f"{rel} says {ver} is on {reg}, as README's Published column does",
                    f"line {line(m)}; README's Publication state gives {reg} "
                    f"{', '.join(sorted(have)) or 'nothing'}: point at that table rather than repeat it")
        for m in PUBLISHED_AT.finditer(text):
            seen += 1
            ver = m.group(1)
            have = pub.get(default, set()) if default else every
            f.check(ver in have, f"{rel} says the SDK is published at {ver}, as README's Published column does",
                    f"line {line(m)}; README's Publication state gives "
                    f"{', '.join(sorted(have)) or 'nothing'}: point at that table rather than repeat it")
        if rel in README_ROWS:
            cell = rows.get(README_ROWS[rel], "")
            for m in UNPUBLISHED.finditer(text):
                seen += 1
                f.check(NOT_PUBLISHED in cell or not SEMVER.search(cell),
                        f"{rel} calls its package unpublished, as README's Published column does",
                        f"line {line(m)} says '{m.group(0)}'; README's {README_ROWS[rel]} row reads '{cell}'")
    # No floor: zero is the state wanted, every one of these files pointing at
    # README's table instead of repeating it. The count is printed so that a
    # run is read, not just its exit code.
    print(f"note C23b read {seen} published-version claim(s) across {len(CLAIM_FILES)} files")


def release_link_checks(root: Path, f: Fails) -> None:
    """A link whose text names a release tag opens that release, not another one."""
    rels = [r for r in RELEASE_LINK_FILES if (root / r).is_file()]
    rels += sorted(p.relative_to(root).as_posix() for p in (root / "docs").rglob("*.md"))
    seen = 0
    for rel in rels:
        text = read(root, rel)
        refs = {m.group(1).lower(): m.group(2) for m in REF_DEF.finditer(text)}
        for m in RELEASE_LABEL.finditer(text):
            tag, ref = m.group(1), m.group(3)
            n = text.count("\n", 0, m.start()) + 1
            url = m.group(2) or refs.get((ref or "").lower())
            if url is None:
                f.check(False, f"{rel}'s link [`{tag}`][{ref}] is defined",
                        f"line {n}: no `[{ref}]: <url>` line in the file")
                continue
            target = RELEASE_URL.search(url)
            if not target:
                continue  # labelled with a tag, but not a release page: not this check's
            seen += 1
            f.check(target.group(1) == tag, f"{rel}'s link labelled `{tag}` opens {tag}",
                    f"line {n}: it opens {target.group(1)} ({url}); a reader who clicks the "
                    "release the sentence names lands on a different one")
    f.check(seen >= RELEASE_LINK_FLOOR, f"compared {seen} release links (floor {RELEASE_LINK_FLOOR})",
            "README's download paragraph and Publication state row, and each locale's "
            "install-cli.md, each name a release by its tag")


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
