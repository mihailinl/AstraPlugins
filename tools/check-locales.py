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
    #: Everything a rule declined to compare, in the words the summary line
    #: repeats. A run that skipped something must not be able to end on the word
    #: "pass" alone — that is the shape of green this whole file is written
    #: against, and printing it once at the top where nobody scrolls is not
    #: enough.
    unverified: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.unverified = []

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
        fails.unverified.append("C12 (no Astra checkout)")
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
        fails.unverified.append("C12's `maintained` column")
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
        fails.unverified.append("C12's endonym column")
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
        fails.unverified.append("C20 (no astra-registry checkout)")
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


def rule_C22(fails: Fails, astra: Path | None) -> None:
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
        fails.unverified.append("C22 (no Astra checkout)")
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

    if not tags:
        print("C22 NOT VERIFIED: that Astra checkout has no `v*` tags, so there is no")
        print("        release to look inside. A shallow or single-branch clone does")
        print("        this; it is reported rather than read as `no release has it`,")
        print("        which is the answer that would keep the scaffold as it is for")
        print("        the wrong reason.")
        fails.unverified.append("C22 (no release tags in the Astra checkout)")
        return

    newest = tags[0]
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
    args = ap.parse_args()

    wanted = [r.strip().upper() for r in args.rules.split(",") if r.strip()]
    unknown = [r for r in wanted if r not in ("C12", "C14", "C20", "C22")]
    if unknown:
        print(f"unknown rule(s): {unknown}", file=sys.stderr)
        return 2

    fails = Fails()
    if "C14" in wanted:
        rule_C14(fails)
    if "C20" in wanted:
        rule_C20(fails)
    if "C12" in wanted:
        rule_C12(fails, resolve_astra(args.astra_dir))
    if "C22" in wanted:
        rule_C22(fails, resolve_astra(args.astra_dir))

    print()
    sys.stdout.flush()
    if fails:
        print(f"check-locales: {len(fails)} broken:\n", file=sys.stderr)
        for f in fails:
            print("  " + f, file=sys.stderr)
        return 1
    if fails.unverified:
        n = len(fails.unverified)
        print(f"check-locales: {', '.join(wanted)} — nothing broken, and "
              f"{n} thing{'' if n == 1 else 's'} NOT VERIFIED: "
              + "; ".join(fails.unverified) + ".")
        print("               Exit 0, and not a clean bill of health for those: each")
        print("               says above what it could not see and why.")
        return 0
    print(f"check-locales: {', '.join(wanted)} pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
