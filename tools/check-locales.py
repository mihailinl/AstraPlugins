#!/usr/bin/env python3
"""The locale vocabulary, held against the two things that can contradict it.

    python3 tools/check-locales.py                       # C12 and C14
    python3 tools/check-locales.py --rules C14           # what the couplings job runs
    python3 tools/check-locales.py --rules C12 \\
        --astra-dir ../Astra/astra-rs                    # what proto-upstream runs, full mode

`spec/locales.yaml` is a mirror of a list that lives in another repository, and
a mirror nobody compares is a guess. Two rules compare it:

C12 — spec/locales.yaml vs the daemon's own list.
    `Settings::validate` refuses any language outside `SUPPORTED_LANGUAGES`, so
    those strings are the complete set of values that can reach a plugin, and
    they are the only names a bundle's `locales/<code>.json` may take. A code we
    declare and the daemon does not is a file an author is invited to write that
    nothing will ever read. A code the daemon has and we do not is a language we
    would refuse to pack for. Neither produces an error anywhere today.

    This needs the private Astra repository, so it CANNOT run on a pull request
    from a fork — GitHub withholds `ASTRA_REPO_TOKEN` there by design, and
    `ci.yml` calls that the normal state. Without a checkout this rule prints
    what it did not verify and exits 0. It does not pass quietly.

C20 — spec/listing-limits.yaml vs astra-registry's own numbers.
    Four length caps that belong to another repository and are enforced HERE, at
    pack time, because the alternative is an author discovering them at ingest
    after a tag is pushed. A copy nobody compares is a guess, so this compares
    them — against `policy/limits.json` and `schema/version-v1.json` — whenever
    an astra-registry checkout is reachable, and says out loud that it did not
    when there is none.

C22 — has a RELEASED Astra started resolving plugin labels?
    `astra-plugin new` scaffolds LITERAL English action, trigger and UI labels,
    because a `$key` there renders as literal text on every daemon that does not
    resolve it — and no Astra release does. The code is on Astra's `main`. The
    day it ships in a tag, the scaffold must flip to `key(...)` and start writing
    a `min_astra_version`, and this rule is what makes that a red build instead
    of a paragraph somebody has to remember. It FAILS when the condition it
    watches for becomes true, which is the same shape as `ARCHIVE_PENDING` in
    ci.yml: an exception that cannot outlive the work it was waiting for.

    It reads a tag through two constants — a path and a symbol — so it first
    proves BOTH of them against a named ref of the checkout it was handed
    (`--astra-ref`, default `origin/main`, never HEAD). A `git show` that fails
    because the path moved is otherwise indistinguishable from a tag that
    genuinely lacks the symbol, and the false negative gets printed as evidence:
    against a repository whose resolver had merely moved one path along, this
    rule answered `ok C22 no released Astra resolves plugin labels yet` and
    exited 0. `rule_C12` had applied exactly that discipline to itself from the
    start; C22 had not.

    Then it needs tags, and a CI checkout has none: `actions/checkout` fetches
    tags matching the REF NAME, so a job that asks for `main` gets the refspec
    `+refs/tags/main*:refs/tags/main*` and no `v*` tag at all. `fetch-tags: true`
    does not change that — it only drops `--no-tags`, and at `fetch-depth: 1`
    with explicit refspecs there is no fetched history for a tag to be followed
    into. (Both halves measured, the second of them by trying it and watching
    this rule go red.) So for its whole life in CI this rule took its "no release
    to look inside" branch, on every run, and nothing turned that into a failure.
    `ci.yml` now fetches `+refs/tags/v*:refs/tags/v*` in a step of its own, and
    `--require C22` is how a caller that supplied a checkout on purpose says that
    a skip is a broken job rather than a normal state.

    **CI and a maintainer's machine can name different tags, and CI is the one
    to believe.** The first run that read a tag said `newest tag: v0.1.0` where
    this machine says `v0.2.0`; `git ls-remote --tags origin 'v*'` on Astra
    returns exactly `refs/tags/v0.1.0`, so v0.2.0 exists locally and has never
    been pushed. A tag nobody can fetch is not a release, which is the subject of
    this rule — so a local run's extra tags make it stricter than reality and
    never laxer, and the verdict was the same either way here because neither tag
    carries the resolver. Read the tag name in the evidence line rather than
    assuming the two agree.

C14 — spec/locales.yaml vs docs/tools/locales.py vs the directories under docs/.
    A translated documentation directory is the most likely place an author
    learns a locale name, and for months `docs/zh-CN` taught a spelling Astra
    cannot be set to. This rule needs no checkout and runs everywhere.

    It is also the answer to "what would add a member this check cannot see?".
    The set it enumerates is `docs/*/`, so a new directory is a new member — and
    a new directory is exactly what `mirror.py` and `doctest.py` are blind to,
    because both iterate a declared tuple rather than the filesystem. C14
    compares the tuple with the filesystem in both directions and floors the
    scan, so a walk that stops finding anything fails as a broken walk instead
    of as a clean bill of health.

Exit 0 when every rule that could run passed, 1 when any failed. A rule that
could not run is named on stdout and does not affect the exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "locales.yaml"
DOCS = ROOT / "docs"

#: Directories under `docs/` that are not a locale. Anything else down there is
#: treated as a locale directory and must be declared — a new non-locale
#: directory fails this check rather than being waved through, which is the
#: direction an enumerating check should be wrong in.
NOT_A_LOCALE = {"tools"}

#: The fewest rows `spec/locales.yaml` may contain before this reader concludes
#: its own parse has broken rather than that the list shrank. Not the real
#: count: a floor, so that growth is allowed and an empty scan is not.
MIN_SPEC_ROWS = 2

#: Likewise for `docs/`. English plus one translation is the least this tree has
#: ever carried.
MIN_DOC_LOCALES = 2


class Fails(list):
    #: Everything a rule declined to compare, as `(rule, why)`, in the words the
    #: summary line repeats. A run that skipped something must not be able to
    #: end on the word "pass" alone — that is the shape of green this whole file
    #: is written against, and printing it once at the top where nobody scrolls
    #: is not enough.
    #:
    #: The rule id is carried alongside the sentence so that `--require` can
    #: turn one rule's skip into a red build without turning every rule's into
    #: one. Grepping the prose would do it too, and that is what
    #: astra-registry's build-index.yml does for its own gate — but prose gets
    #: reworded, and a gate a reword can silently disarm is the shape of check
    #: this repository keeps getting bitten by.
    unverified: list[tuple[str, str]]

    def __init__(self) -> None:
        super().__init__()
        self.unverified = []

    def skip(self, rule: str, why: str) -> None:
        self.unverified.append((rule, why))

    def check(self, ok: bool, msg: str, detail: str = "") -> bool:
        print(("ok    " if ok else "FAIL  ") + msg)
        if not ok:
            indented = "\n".join("        " + l for l in detail.splitlines())
            self.append(msg + (("\n" + indented) if detail else ""))
            if detail:
                for line in detail.splitlines():
                    print("        " + line)
        return ok


# ── spec/locales.yaml ────────────────────────────────────────────────────────


def read_spec() -> tuple[list[str], list[str], dict[str, str]]:
    """(codes in file order, the `maintained` subset, code -> endonym).

    The hand-parse `spec/locales.yaml`'s own FORMAT paragraph promises: split on
    whitespace, first field is the code, last field is `maintained` or is not.
    Two readers implement it — this file and `astra-plugin-cli/src/locales.rs`'s
    test — and neither takes a dependency to do it.
    """
    text = SPEC.read_text(encoding="utf-8")
    codes: list[str] = []
    maintained: list[str] = []
    endonyms: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        code = fields[0]
        rest = fields[1:]
        if rest and rest[-1] == "maintained":
            maintained.append(code)
            rest = rest[:-1]
        codes.append(code)
        endonyms[code] = " ".join(rest)
    return codes, maintained, endonyms


# ── C12 ──────────────────────────────────────────────────────────────────────


def _astra_languages(astra: Path) -> tuple[list[str] | None, list[str] | None, str]:
    """The daemon's own vocabulary, from the best source present.

    Preferred: `astra-core/locale-vocabulary.json`, which Astra generates from
    the two consts and pins with its own test — comparing two files beats
    parsing somebody's Rust. It does not exist on Astra's `main` yet, so the
    consts are the fallback and the fallback is the path this runs on today.
    """
    vocab = astra / "astra-core" / "locale-vocabulary.json"
    if vocab.is_file():
        doc = json.loads(vocab.read_text(encoding="utf-8"))
        return doc.get("languages"), doc.get("maintained"), str(vocab)

    langs = _rust_str_slice(astra / "astra-core" / "src" / "config.rs",
                            "SUPPORTED_LANGUAGES")
    kept = _rust_str_slice(astra / "astra-core" / "src" / "i18n.rs",
                           "MAINTAINED_LANGUAGES")
    return langs, kept, str(astra / "astra-core" / "src")


def _rust_str_slice(path: Path, name: str) -> list[str] | None:
    """`pub const NAME: &[&str] = &["a", "b"];` -> ["a", "b"], or None.

    Anchored on the declaration, not on the first mention of the name: R6 in
    `tools/parity/check.py` learned that lesson the expensive way when a module
    doc comment naming a const started a scan 330 lines above the const.
    """
    if not path.is_file():
        return None
    m = re.search(
        r"const\s+" + re.escape(name) + r"\s*:\s*&\[&str\]\s*=\s*&\[(.*?)\]\s*;",
        path.read_text(encoding="utf-8", errors="replace"),
        re.S,
    )
    if not m:
        return None
    return re.findall(r'"([^"]*)"', m.group(1))


def _astra_endonyms(astra: Path) -> tuple[dict[str, str] | None, str]:
    path = astra / "astra-ui" / "src" / "i18n" / "I18nContext.tsx"
    if not path.is_file():
        return None, str(path)
    m = re.search(r"const\s+ENDONYMS\s*:\s*Record<[^>]*>\s*=\s*\{(.*?)\}\s*;",
                  path.read_text(encoding="utf-8", errors="replace"), re.S)
    if not m:
        return None, str(path)
    return dict(re.findall(r'(\w+)\s*:\s*"([^"]*)"', m.group(1))), str(path)


def rule_C12(fails: Fails, astra: Path | None) -> None:
    codes, maintained, endonyms = read_spec()

    if astra is None:
        print("C12 NOT VERIFIED: no Astra checkout at "
              f"{_default_astra_hint()}. The locale vocabulary was not compared "
              "with the daemon's.")
        print(f"        {len(codes)} code(s) in spec/locales.yaml were taken on trust: "
              + " ".join(codes))
        print(f"        the `maintained` subset was taken on trust too: "
              + " ".join(maintained))
        print("        Nothing here proves the daemon still accepts exactly these, or")
        print("        that it has not gained an eleventh. `Settings::validate` is what")
        print("        refuses everything else, and it is in a private repository.")
        print("        What DOES run without a checkout: C13 (the CLI's mirror of this")
        print("        file, on every `cargo test`) and C14 (the docs locales, in the")
        print("        `couplings` job).")
        fails.skip("C12", "no Astra checkout")
        return

    langs, kept, source = _astra_languages(astra)

    if langs is None:
        fails.check(
            False,
            "C12 the daemon's language list was found",
            f"looked in {source}. Neither astra-core/locale-vocabulary.json nor a\n"
            "`pub const SUPPORTED_LANGUAGES: &[&str] = &[…];` in astra-core/src/config.rs.\n"
            "This is a FAILURE and not a skip: a checkout was supplied, so the anchor\n"
            "moved rather than being absent, and a comparison whose input stopped being\n"
            "the thing under test is the one shape of green that means nothing.",
        )
        return

    fails.check(
        len(langs) >= MIN_SPEC_ROWS,
        f"C12 the daemon's list has at least {MIN_SPEC_ROWS} languages "
        f"({len(langs)} found in {source})",
        "an empty or near-empty parse is a broken reader, not a shrunken vocabulary",
    )

    ours, theirs = set(codes), set(langs)
    fails.check(
        ours == theirs,
        f"C12 spec/locales.yaml declares the {len(langs)} languages the daemon accepts",
        f"only in spec/locales.yaml: {sorted(ours - theirs) or '—'}\n"
        f"only in {source}: {sorted(theirs - ours) or '—'}\n"
        "A code we declare and the daemon refuses is a locale file an author is\n"
        "invited to write and nothing will ever read. A code the daemon accepts\n"
        "and we do not is a language `astra-plugin` would refuse to pack for.\n"
        "Fix spec/locales.yaml, then astra-plugin-cli/src/locales.rs (C13 will\n"
        "tell you), then docs/tools/locales.py if the docs follow.",
    )
    if ours == theirs and codes != langs:
        print(f"        note: same set, different order — spec/locales.yaml has "
              f"{' '.join(codes)}, the daemon has {' '.join(langs)}. Order is not "
              "meaningful here; `en` first is.")

    if kept is None:
        print("C12 PARTIAL: the `maintained` subset was NOT compared.")
        print(f"        {source} has no MAINTAINED_LANGUAGES and no")
        print("        locale-vocabulary.json. That const is on Astra's")
        print("        `worktree-plugin-i18n-w1` and is not on `main`, so this line is")
        print("        expected until that branch lands — and it is printed rather than")
        print("        assumed, because `maintained` is the one column in")
        print("        spec/locales.yaml that nothing else in this repository can check.")
        print(f"        Taken on trust: {' '.join(maintained)}")
        fails.skip("C12", "the `maintained` column")
    else:
        fails.check(
            set(maintained) == set(kept),
            "C12 the `maintained` subset is the daemon's",
            f"ours: {sorted(maintained)}\ntheirs: {sorted(kept)}\n"
            "`maintained` is the set whose Astra UI translation is held complete.\n"
            "It is not the docs set and it is not permission for a plugin to skip a\n"
            "locale; it is here so that a reader of spec/locales.yaml can tell how\n"
            "complete the shell around their plugin will be.",
        )

    theirs_endonyms, endonym_source = _astra_endonyms(astra)
    if theirs_endonyms is None:
        print("C12 PARTIAL: the endonyms were NOT compared.")
        print(f"        no ENDONYMS map at {endonym_source}.")
        print("        The second column of spec/locales.yaml is a copy of that map and")
        print("        is unpinned in this run.")
        fails.skip("C12", "the endonym column")
    else:
        drift = {c: (endonyms.get(c), theirs_endonyms.get(c))
                 for c in sorted(ours & set(theirs_endonyms))
                 if endonyms.get(c) != theirs_endonyms.get(c)}
        fails.check(
            not drift,
            "C12 the endonyms are the ones Astra renders",
            "\n".join(f"{c}: spec says {a!r}, Astra says {b!r}"
                      for c, (a, b) in drift.items())
            + "\nNothing in this repository renders these, so nobody would notice."
              "\nThat is precisely why they are compared.",
        )


def _default_astra_hint() -> str:
    env = os.environ.get("ASTRA_RS_DIR")
    return env if env else "../Astra/astra-rs (or $ASTRA_RS_DIR, or --astra-dir)"


# ── C14 ──────────────────────────────────────────────────────────────────────


def rule_C14(fails: Fails) -> None:
    codes, _, _ = read_spec()
    fails.check(
        len(codes) >= MIN_SPEC_ROWS,
        f"C14 spec/locales.yaml parses to at least {MIN_SPEC_ROWS} codes "
        f"({len(codes)} found)",
        "the format changed under this reader; see that file's FORMAT paragraph",
    )

    sys.path.insert(0, str(DOCS / "tools"))
    try:
        import locales as declared  # noqa: E402  (path is set immediately above)
    except ImportError as exc:
        fails.check(False, "C14 docs/tools/locales.py is importable", str(exc))
        return
    finally:
        sys.path.pop(0)

    tuple_locales = list(declared.LOCALES)
    on_disk = sorted(p.name for p in DOCS.iterdir()
                     if p.is_dir() and p.name not in NOT_A_LOCALE)

    fails.check(
        len(on_disk) >= MIN_DOC_LOCALES,
        f"C14 docs/ holds at least {MIN_DOC_LOCALES} locale directories "
        f"({len(on_disk)} found)",
        "this walk found almost nothing, which is a broken walk and not an empty tree",
    )
    fails.check(
        "en" in tuple_locales and (DOCS / "en").is_dir(),
        "C14 docs/en exists and is declared",
        "English is what every other locale is a mirror of",
    )
    fails.check(
        sorted(tuple_locales) == on_disk,
        "C14 docs/tools/locales.py names exactly the directories under docs/",
        f"declared and absent: {sorted(set(tuple_locales) - set(on_disk)) or '—'}\n"
        f"present and undeclared: {sorted(set(on_disk) - set(tuple_locales)) or '—'}\n"
        "An undeclared directory is invisible to mirror.py and doctest.py — it is\n"
        "checked by nothing except linkcheck.py, which only walks it. Declare it in\n"
        "docs/tools/locales.py, or delete it. If it is not a locale at all, add its\n"
        "name to NOT_A_LOCALE in tools/check-locales.py and say why.",
    )
    stray = sorted(set(tuple_locales) - set(codes))
    fails.check(
        not stray,
        "C14 every documentation locale is a language Astra can be set to",
        f"not in spec/locales.yaml: {stray}\n"
        "A directory name under docs/ is where an author reads a locale code, and\n"
        "`locales/<that>.json` is what they will write. If the daemon cannot be set\n"
        "to it, the file they write is packed, digested, signed and read by nothing.\n"
        "`docs/zh-CN` was exactly this, for months.",
    )
    print(f"        docs/ carries {len(on_disk)} directories against "
          f"{len(codes)} declared codes: {' '.join(on_disk)}. A proper subset is "
          "allowed — translating a page is a commitment, declaring a code is not.")


# ── C20 ──────────────────────────────────────────────────────────────────────

LISTING_LIMITS = ROOT / "spec" / "listing-limits.yaml"

#: The fewest rows `spec/listing-limits.yaml` may have before this reader
#: concludes its own parse broke. A floor, not the real count.
MIN_LIMIT_ROWS = 4


def read_listing_limits() -> tuple[dict[str, int], dict[str, str]]:
    """(name -> value, name -> the source its `mirrors:` comment names).

    The format that file's own header promises: `name: <integer>` per line, and
    a `# mirrors: <source>` comment above each value. The mirror line is a
    comment on purpose — a human reads it, this regex reads it, and nothing
    breaks if it is reworded.
    """
    values: dict[str, int] = {}
    sources: dict[str, str] = {}
    pending: str | None = None
    for raw in LISTING_LIMITS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        m = re.match(r"#\s*mirrors:\s*(.+)$", line)
        if m:
            pending = m.group(1).strip()
            continue
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([a-z_]+)\s*:\s*([0-9_]+)", line)
        if m:
            values[m.group(1)] = int(m.group(2).replace("_", ""))
            if pending:
                sources[m.group(1)] = pending
            pending = None
    return values, sources


def _registry_dir() -> Path | None:
    env = os.environ.get("ASTRA_REGISTRY_DIR")
    candidates = [env] if env is not None else ["../astra-registry"]
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        if (p / "policy" / "limits.json").is_file():
            return p
    return None


def _json_pointer(doc, pointer: str):
    """`$.permissions.*.reason maxLength` -> the number, or None.

    Deliberately tiny and deliberately not RFC 6901: one `mirrors:` line in this
    project needs a path into a JSON Schema, and a dependency-free walk that
    understands `*` is the whole requirement. Anything it cannot follow is a
    None, which becomes a PARTIAL rather than a pass.
    """
    node = doc
    for step in pointer.split("."):
        if step in ("$", ""):
            continue
        if step == "*":
            values = [v for v in node.values()] if isinstance(node, dict) else []
            if len(values) != 1:
                # More than one branch and no way to choose: refuse to guess.
                return None
            node = values[0]
            continue
        if isinstance(node, dict) and step in node:
            node = node[step]
        elif isinstance(node, dict) and "properties" in node and step in node["properties"]:
            node = node["properties"][step]
        else:
            return None
    return node


def rule_C20(fails: Fails) -> None:
    values, sources = read_listing_limits()
    fails.check(
        len(values) >= MIN_LIMIT_ROWS,
        f"C20 spec/listing-limits.yaml parses to at least {MIN_LIMIT_ROWS} caps "
        f"({len(values)} found)",
        "that file's FORMAT paragraph promises `name: <integer>` per line — if it\n"
        "still looks like that, this reader is what broke and not the list.",
    )
    missing_source = sorted(n for n in values if n not in sources)
    fails.check(
        not missing_source,
        "C20 every cap names the upstream constant it mirrors",
        f"no `# mirrors:` line above: {missing_source}\n"
        "A copy that does not say what it is a copy OF is a copy nothing can\n"
        "compare, which is how a local decision comes to read as an echo of\n"
        "somebody else's number — see the `_mirrors` convention in\n"
        "astra-registry/policy/limits.json, which this is the other half of.",
    )

    registry = _registry_dir()
    if registry is None:
        print("C20 NOT VERIFIED: no astra-registry checkout at "
              "$ASTRA_REGISTRY_DIR or ../astra-registry.")
        for name, value in sorted(values.items()):
            print(f"        {name} = {value} taken on trust "
                  f"(mirrors {sources.get(name, 'nothing stated')})")
        print("        `astra-plugin check` REFUSES a manifest over these numbers, so a")
        print("        value too low here refuses a listing the registry would have taken,")
        print("        and one too high lets an author through to a refusal at ingest they")
        print("        cannot act on. Neither is visible from this repository alone.")
        fails.skip("C20", "no astra-registry checkout")
        return

    policy = json.loads((registry / "policy" / "limits.json").read_text(encoding="utf-8"))
    schemas: dict[str, dict] = {}
    compared = 0
    drift: list[str] = []
    unreadable: list[str] = []

    for name, ours in sorted(values.items()):
        source = sources.get(name, "")
        m = re.match(r"astra-registry/([^\s]+)\s+(.+)$", source)
        if not m:
            unreadable.append(f"{name}: cannot parse its mirrors line {source!r}")
            continue
        rel, key = m.group(1), m.group(2).strip()
        if rel == "policy/limits.json":
            if key not in policy:
                unreadable.append(f"{name}: {rel} has no `{key}`")
                continue
            theirs = policy[key]
        else:
            path = registry / rel
            if not path.is_file():
                unreadable.append(f"{name}: {rel} is not in that checkout")
                continue
            if rel not in schemas:
                schemas[rel] = json.loads(path.read_text(encoding="utf-8"))
            pointer, _, member = key.rpartition(" ")
            node = _json_pointer(schemas[rel], pointer)
            if not isinstance(node, dict) or member not in node:
                unreadable.append(f"{name}: {rel} has nothing at `{key}`")
                continue
            theirs = node[member]
        compared += 1
        if theirs != ours:
            drift.append(f"{name}: we say {ours}, {source} says {theirs}")

    fails.check(
        compared >= MIN_LIMIT_ROWS,
        f"C20 at least {MIN_LIMIT_ROWS} cap(s) were actually compared ({compared})",
        "\n".join(unreadable) + "\n"
        "A checkout WAS supplied, so an anchor that cannot be found means it moved\n"
        "rather than that it is absent — and a comparison whose inputs stopped being\n"
        "the thing under test is the one shape of green that means nothing.",
    )
    fails.check(
        not drift,
        f"C20 spec/listing-limits.yaml agrees with astra-registry ({compared} cap(s))",
        "\n".join(drift) + "\n"
        "These are the REGISTRY's numbers. Change them there first: a cap lowered\n"
        "here refuses a listing the registry would have accepted, and one raised here\n"
        "lets an author push a tag that dies at ingest. Then mirror, then\n"
        "`cargo test --manifest-path astra-plugin-cli/Cargo.toml` for the CLI's own\n"
        "vendored copy of this file.",
    )


# ── C22 ──────────────────────────────────────────────────────────────────────

#: The function whose presence in a RELEASED Astra means the scaffold must flip.
#: Serve-time resolution of a plugin's action labels — `get_config_schema` has
#: resolved config schemas for far longer, and that is not what this watches.
RESOLVER_SYMBOL = "resolve_action_type"
RESOLVER_FILE = "astra-rs/astra-daemon/src/plugins/i18n.rs"

#: The NAMED ref this rule proves its own anchor against before it believes a
#: word a tag says.
#:
#: A named ref and never `HEAD`: HEAD in a maintainer's Astra checkout is
#: whatever they were working on, and this repository has already been bitten
#: once by a comparison whose inputs stopped being the thing under test. Verified
#: on the machine this was written on — the local `main` there carries no
#: `plugins/i18n.rs` at all, while `origin/main` carries it with the symbol in
#: it, so anchoring on the working tree would have failed a correct checkout.
#:
#: `actions/checkout` writes `refs/remotes/origin/<ref>` for the branch it takes,
#: so the CI step passes `--astra-ref origin/$ASTRA_REF` and this default is what
#: a maintainer's clone answers to.
ANCHOR_REF = "origin/main"

#: The fewest `v*` tags this rule may find before it concludes that the CHECKOUT
#: is what broke rather than that Astra has never cut a release. A floor, not a
#: count.
#:
#: This is the whole of the second half of the defect: `actions/checkout` fetches
#: no tags unless told to, so `git tag --list 'v*'` came back empty on every run
#: since the rule was written, the rule took its "no release to look inside"
#: branch every time, and nothing on this side turned that into a failure.
MIN_RELEASE_TAGS = 1


def _anchor_holds(fails: Fails, top: str, ref: str) -> bool:
    """Is `RESOLVER_FILE` still where this rule thinks, with the symbol in it?

    **This runs BEFORE the tag is read, and its absence is a FAILURE and never a
    skip or a pass** — `rule_C12` above says why in its own words, and C22 is the
    rule that needed it. `shipped = blob.returncode == 0 and SYMBOL in stdout`
    cannot tell *this tag does not carry the resolver* from *the daemon renamed
    the file* or *renamed the function*, and it prints the false negative as
    evidence: against a real repository whose resolver had merely moved one path
    along, the unmodified rule answered `ok C22 no released Astra resolves plugin
    labels yet` and exited 0.

    Turning on `fetch-tags` without this would have been strictly worse than the
    bug it fixes: a loud, permanent skip becomes a confident, permanent green.
    """
    have = subprocess.run(["git", "-C", top, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"],
                          capture_output=True, text=True)
    if have.returncode != 0:
        return fails.check(
            False,
            f"C22 the Astra checkout has `{ref}` to anchor on",
            f"`git rev-parse {ref}` failed in {top}.\n"
            "This rule proves its own anchor against a NAMED ref before it reads a tag,\n"
            "and it will not fall back to HEAD: HEAD is whatever the checkout happens to\n"
            "be sitting on, which on a maintainer's machine may be a branch with no\n"
            f"{RESOLVER_FILE} in it at all.\n"
            "Pass the right one with --astra-ref (CI passes origin/$ASTRA_REF), or fetch\n"
            "it. This is a FAILURE and not a skip: a checkout was supplied.",
        )

    blob = subprocess.run(["git", "-C", top, "show", f"{ref}:{RESOLVER_FILE}"],
                          capture_output=True, text=True)
    if blob.returncode != 0:
        return fails.check(
            False,
            f"C22 {RESOLVER_FILE} is still there on {ref}",
            f"`git show {ref}:{RESOLVER_FILE}` failed.\n"
            "The path this rule greps a release for has moved, so every verdict it could\n"
            "reach about a tag is about a file that is not the thing under test — and the\n"
            "shape of that mistake is a GREEN one: a `git show` that fails because the\n"
            "path moved is indistinguishable from a tag that genuinely lacks the symbol.\n"
            "Point RESOLVER_FILE at wherever the daemon resolves labels now. Do not\n"
            "silence this by pointing it at something that is still absent.",
        )
    if RESOLVER_SYMBOL not in blob.stdout:
        return fails.check(
            False,
            f"C22 `{RESOLVER_SYMBOL}` is still the symbol to watch for, on {ref}",
            f"{RESOLVER_FILE} exists on {ref} and does not contain `{RESOLVER_SYMBOL}`.\n"
            "Either the daemon renamed it, or serve-time label resolution moved somewhere\n"
            "else. Until RESOLVER_SYMBOL names the real thing, `this tag does not carry\n"
            "it` is a sentence about a string nobody uses, printed as evidence.\n"
            "This is a FAILURE and not a skip: a checkout was supplied, so the anchor\n"
            "moved rather than being absent.",
        )
    return True


def _tag_tree_readable(fails: Fails, top: str, tag: str) -> bool:
    """Is that tag's tree actually HERE, or only its name?

    The verdict below is `git show <tag>:<path>` failing, read as *this release
    does not carry the resolver*. That reading is only sound if the release's
    tree is present locally, and a checkout can hold a tag ref whose objects it
    would have to go and get — a treeless or blobless partial clone is the live
    example, and shallow-plus-partial is a plausible next optimisation of a
    checkout whose comment already says the repository is large.

    So the root tree is listed and floored at one entry, BEFORE any verdict. An
    empty listing is this rule looking at nothing, and it must not be able to
    come out the same way as `no release resolves labels yet`.
    """
    tree = subprocess.run(["git", "-C", top, "ls-tree", "--name-only", tag],
                          capture_output=True, text=True)
    entries = tree.stdout.split()
    return fails.check(
        tree.returncode == 0 and len(entries) >= 1,
        f"C22 {tag}'s tree is readable in this checkout ({len(entries)} root entr"
        f"{'y' if len(entries) == 1 else 'ies'})",
        f"`git ls-tree --name-only {tag}` returned {tree.returncode} and "
        f"{len(entries)} entries.\n"
        f"{tree.stderr.strip()}\n"
        "The tag ref is here and what it points at is not, so every `git show`\n"
        "below would fail for a reason that has nothing to do with the release —\n"
        "and this rule reads a failed `git show` as `that release does not carry\n"
        "the resolver`. Fetch the tag's objects (CI does\n"
        "`git -C _astra fetch --depth=1 origin '+refs/tags/v*:refs/tags/v*'`),\n"
        "or stop filtering trees out of this checkout.",
    )


def rule_C22(fails: Fails, astra: Path | None, anchor_ref: str = ANCHOR_REF) -> None:
    if astra is None:
        print("C22 NOT VERIFIED: no Astra checkout at "
              f"{_default_astra_hint()}. Nothing here can see whether a RELEASED")
        print("        Astra resolves a plugin's action, trigger and UI labels yet.")
        print("        Until one does, `astra-plugin new` scaffolds LITERAL English on")
        print("        that surface on purpose: a `$key` there is not rendered by a")
        print("        daemon that does not resolve it — it is shown to the user as it")
        print("        stands. The flip is a two-line change in")
        print("        astra-plugin-cli/src/templates/mod.rs and it is gated on a")
        print("        release, not on a merge.")
        fails.skip("C22", "no Astra checkout")
        return

    try:
        top = subprocess.run(["git", "-C", str(astra), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True).stdout.strip()
        tags = subprocess.run(
            ["git", "-C", top, "tag", "--list", "v*", "--sort=-v:refname"],
            capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError) as exc:
        fails.check(False, "C22 the Astra checkout's tags are readable", str(exc))
        return

    # The anchor FIRST. Everything below reads `git show <tag>:<path>` and asks
    # whether a symbol is in it, and both halves of that question are worthless
    # if the path or the symbol has moved.
    if not _anchor_holds(fails, top, anchor_ref):
        return
    print(f"        anchor: `{RESOLVER_SYMBOL}` is in {RESOLVER_FILE} on {anchor_ref}, so a tag "
          "that lacks it lacks the resolver and not the file.")

    if len(tags) < MIN_RELEASE_TAGS:
        print(f"C22 NOT VERIFIED: that Astra checkout has no `v*` tags (floor: "
              f"{MIN_RELEASE_TAGS}), so there is")
        print("        no release to look inside. Two different things produce this and")
        print("        they need opposite fixes: the SCAN is what broke if the checkout")
        print("        is shallow or was fetched without tags — `actions/checkout` takes")
        print("        none unless told to, and that is what kept this rule in its")
        print("        degraded branch on every CI run it has ever had. Astra genuinely")
        print("        never having cut a release is the other one, and it is not the")
        print("        state this repository is in.")
        print("        It is reported rather than read as `no release has it`, which is")
        print("        the answer that would keep the scaffold as it is for the wrong")
        print("        reason — and `--require C22` is how a caller that HAS supplied a")
        print("        checkout turns this line red instead of letting it ride.")
        fails.skip("C22", "no release tags in the Astra checkout")
        return

    newest = tags[0]
    if not _tag_tree_readable(fails, top, newest):
        return
    blob = subprocess.run(["git", "-C", top, "show", f"{newest}:{RESOLVER_FILE}"],
                          capture_output=True, text=True)
    shipped = blob.returncode == 0 and RESOLVER_SYMBOL in blob.stdout

    fails.check(
        not shipped,
        f"C22 no released Astra resolves plugin labels yet (newest tag: {newest})",
        f"{newest} carries `{RESOLVER_SYMBOL}` in {RESOLVER_FILE}.\n"
        "THIS IS NOT A REGRESSION. It is the thing the scaffold has been waiting\n"
        "for, and this rule fails so that nobody has to remember it:\n"
        "  1. astra-plugin-cli/src/templates/mod.rs — `generate_locales`' doc block\n"
        "     states the condition; the generated action/trigger/UI labels become\n"
        f"    `key(\"…\")` and `generate_manifest` starts writing\n"
        f"     min_astra_version = \"{newest.lstrip('v')}\".\n"
        "  2. The E17 message in astra-plugin-cli/src/commands/locale.rs says there\n"
        "     is no release to name. There is now — name it.\n"
        "  3. Update RESOLVER_SYMBOL here only if the daemon renamed it; do not\n"
        "     silence this by pointing it at something that is still absent.",
    )
    if not shipped:
        print(f"        {newest} does not carry `{RESOLVER_SYMBOL}`. The scaffold's literal")
        print("        English labels are still the right answer, and this line is the")
        print("        evidence rather than a memory.")


# ── main ─────────────────────────────────────────────────────────────────────


def _as_checkout(candidate: str) -> Path | None:
    p = Path(candidate)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p if (p / "astra-core").is_dir() else None


def resolve_astra(arg: str | None) -> Path | None:
    """The checkout to compare against, or None — but never None by accident.

    An explicit `--astra-dir` is a caller asserting the tree is there, so a bad
    one is a hard error rather than a skip. That distinction is the whole point:
    the full-mode CI step passes `--astra-dir _astra/astra-rs` after checking
    Astra out, and if that path ever stops being a checkout the step must go red
    instead of quietly degrading into the skip it shares a script with. A check
    that turns itself off when its input moves is the shape this repository has
    now been bitten by three times.

    `$ASTRA_RS_DIR` is the opposite case by convention: `ASTRA_RS_DIR=/nonexistent`
    is how CONTRIBUTING.md tells you to force the skip and see what it prints.
    """
    if arg:
        found = _as_checkout(arg)
        if found is None:
            print(f"--astra-dir {arg!r} has no astra-core/ under it. It was passed "
                  "explicitly, so this is an error and not a skip.", file=sys.stderr)
            raise SystemExit(2)
        return found
    env = os.environ.get("ASTRA_RS_DIR")
    if env is not None:
        # Set-but-wrong is the skip, with no fall-through to the default path.
        # Falling through would make `ASTRA_RS_DIR=/nonexistent` silently find a
        # checkout on a maintainer's machine and quietly not find one in CI —
        # the two runs would print different things for the same command.
        return _as_checkout(env)
    return _as_checkout("../Astra/astra-rs")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rules", default="C12,C14,C20,C22",
                    help="comma-separated subset of C12,C14,C20,C22 (default: all)")
    ap.add_argument("--astra-dir", default=None,
                    help="an Astra/astra-rs checkout; else $ASTRA_RS_DIR, else "
                         "../Astra/astra-rs. C12 says so out loud when there is none.")
    ap.add_argument("--astra-ref", default=ANCHOR_REF,
                    help=f"the NAMED ref C22 proves its own anchor against before it reads a "
                         f"tag (default: {ANCHOR_REF}). Never HEAD. CI passes "
                         f"origin/$ASTRA_REF, matching the branch it checked out.")
    ap.add_argument("--require", default="",
                    help="comma-separated rules that must actually RUN. A rule listed here "
                         "which reports NOT VERIFIED exits 1 instead of 0. Use it wherever the "
                         "inputs were supplied on purpose — a skip there is a broken job, not "
                         "a normal state.")
    args = ap.parse_args()

    wanted = [r.strip().upper() for r in args.rules.split(",") if r.strip()]
    required = [r.strip().upper() for r in args.require.split(",") if r.strip()]
    unknown = [r for r in wanted + required if r not in ("C12", "C14", "C20", "C22")]
    if unknown:
        print(f"unknown rule(s): {unknown}", file=sys.stderr)
        return 2
    not_run = [r for r in required if r not in wanted]
    if not_run:
        # Requiring a rule this invocation never runs would be a gate that
        # passes because it was pointed at nothing — the exact shape of green
        # this file exists to refuse.
        print(f"--require names rule(s) --rules does not run: {not_run}", file=sys.stderr)
        return 2

    fails = Fails()
    if "C14" in wanted:
        rule_C14(fails)
    if "C20" in wanted:
        rule_C20(fails)
    if "C12" in wanted:
        rule_C12(fails, resolve_astra(args.astra_dir))
    if "C22" in wanted:
        rule_C22(fails, resolve_astra(args.astra_dir), args.astra_ref)

    print()
    sys.stdout.flush()
    if fails:
        print(f"check-locales: {len(fails)} broken:\n", file=sys.stderr)
        for f in fails:
            print("  " + f, file=sys.stderr)
        return 1

    said = [f"{rule} ({why})" for rule, why in fails.unverified]
    blocked = [f"{rule} ({why})" for rule, why in fails.unverified if rule in required]
    if blocked:
        print(f"check-locales: {', '.join(wanted)} — nothing broken, and "
              + f"{len(said)} thing{'' if len(said) == 1 else 's'} NOT VERIFIED: "
              + "; ".join(said) + ".")
        print(f"check-locales: EXIT 1. --require named {', '.join(required)}, and "
              + "; ".join(blocked) + " did not run.", file=sys.stderr)
        print("               A rule whose inputs were supplied on purpose and which skipped "
              "anyway\n"
              "               is a broken job, not a normal state. Nothing above is wrong with "
              "this\n"
              "               repository; something is wrong with what this run was given.",
              file=sys.stderr)
        return 1
    if said:
        n = len(said)
        print(f"check-locales: {', '.join(wanted)} — nothing broken, and "
              f"{n} thing{'' if n == 1 else 's'} NOT VERIFIED: " + "; ".join(said) + ".")
        print("               Exit 0, and not a clean bill of health for those: each")
        print("               says above what it could not see and why.")
        return 0
    print(f"check-locales: {', '.join(wanted)} pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
