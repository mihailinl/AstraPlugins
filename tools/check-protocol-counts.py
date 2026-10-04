#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""C39: what a release says the protocol gained is what the protocol gained.

    python3 tools/check-protocol-counts.py                       # the couplings job
    python3 tools/check-protocol-counts.py --count sdk-v0.7.1    # print the numbers
    python3 tools/check-protocol-counts.py --count sdk-v0.7.1 --head sdk-v0.7.2

Rust 0.7.2's CHANGELOG said the protocol slice "gained 37 fields on messages
that existed at `sdk-v0.7.1`, and 13 new messages". That was counted on
2026-09-23 (431b969). Four more slices landed after it, and when the release
was being prepared the numbers were 49 and 25. The same 37 sat in
`docs/*/versioning.md`, in seven languages, as the worked example of why a new
field ships in a patch. Nothing compared either sentence with the proto, so
both would have gone out wrong, in a document a plugin author reads to decide
whether an exhaustive struct literal of theirs still compiles.

What is compared:

* **The newest entry of each SDK CHANGELOG, while it is `unreleased`.** The
  sentence "Between `sdk-vX` and this release the protocol gained F fields on
  M messages that already existed, N new messages and R new rpcs" must equal a
  parse of `proto/plugin.proto` at tag `sdk-vX` and in this tree. "; it retyped
  K rpc(s)" and " and removed or renumbered nothing", when present, are
  compared too. The Rust entry MUST carry the sentence whenever this tree's
  proto differs from the newest `sdk-v` tag's: the Rust SDK re-exports the
  generated types, and `docs/en/versioning.md` excludes an exhaustive struct
  literal from the patch promise, so the count is the thing its reader needs.
  A dated entry is history and is not compared.
* **`docs/<locale>/versioning.md`, every locale.** The paragraph naming
  `` `sdk-vX` `` followed by a version Y carries exactly one bare integer: the
  fields added to messages that already existed between those two. Y is read
  at its tag when the tag exists, otherwise from this tree while Y is the Rust
  SDK's version and that CHANGELOG entry is unreleased; otherwise the sentence
  names a release nobody can measure, and that is a failure.

How it counts. A field is keyed by its number inside its message, a message
by its dotted name (nested messages included), an rpc by `Service.Method`. A
map field's synthetic entry message is not a message here, because nobody
writes one. The parser is stdlib, so this runs in `couplings` without protoc;
`tools/test_protocol_counts.py` holds it to protoc's own descriptors at every
proto commit between `sdk-v0.7.1` and 0.7.2 when protoc is on PATH.

Exit 0 when every comparison holds, 1 when one does not.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTO = "proto/plugin.proto"
CHANGELOGS = {
    "rust": "astra-plugin-sdk/CHANGELOG.md",
    "python": "astra-plugin-sdk-python/CHANGELOG.md",
    "ts": "astra-plugin-sdk-ts/CHANGELOG.md",
}

SEMVER = r"\d+\.\d+\.\d+"
ENTRY = re.compile(rf"^## \[({SEMVER}[^\]]*)\]\s*[—-]\s*(.+)$", re.M)
SENTENCE = re.compile(
    rf"Between `(?P<base>sdk-v{SEMVER})` and this release the protocol gained "
    r"(?P<fields>\d+) fields? on (?P<touched>\d+) messages? that already existed, "
    r"(?P<messages>\d+) new messages? and (?P<rpcs>\d+) new rpcs?"
    r"(?:; it retyped (?P<retyped>\d+) rpcs?)?"
    r"(?P<nothing> and removed or renumbered nothing)?"
)
# `sdk-v0.7.1` and 0.7.2 / und / y / から / и / і / 到 — the connector is one
# short word in every locale, and the code span is never translated.
DOCS_PAIR = re.compile(rf"`sdk-v(?P<base>{SEMVER})`\s*\S{{1,6}}\s*(?P<head>{SEMVER})")
BARE_INT = re.compile(r"(?<![\w.`-])\d+(?![\w.`])")


# ── the parser ──────────────────────────────────────────────────────────────

@dataclass
class Proto:
    # message -> field number -> (name, type as written, label)
    messages: dict[str, dict[int, tuple[str, str, str]]] = field(default_factory=dict)
    # Service.Method -> (request, response), `stream ` kept in the type
    rpcs: dict[str, tuple[str, str]] = field(default_factory=dict)


FIELD = re.compile(
    r"^(?:(?P<label>repeated|optional|required)\s+)?"
    r"(?P<type>map\s*<\s*[\w.]+\s*,\s*[\w.]+\s*>|[\w.]+)\s+"
    r"(?P<name>\w+)\s*=\s*(?P<num>\d+)\s*(?:\[.*\])?$"
)
RPC = re.compile(
    r"^rpc\s+(?P<name>\w+)\s*\(\s*(?P<req>(?:stream\s+)?[\w.]+)\s*\)\s*"
    r"returns\s*\(\s*(?P<resp>(?:stream\s+)?[\w.]+)\s*\)$"
)
BLOCK = re.compile(r"^(message|enum|service|oneof|extend)\s+(\w+)$")
NOT_A_FIELD = ("option", "reserved", "extensions", "syntax", "package", "import")
LEXEMES = re.compile(r'"(?:[^"\\\n]|\\.)*"|//[^\n]*|/\*.*?\*/', re.S)


def parse(text: str) -> Proto:
    """Messages, their fields, and rpcs, from one .proto file's text."""
    # One left-to-right pass, so whichever starts first wins: a quote inside a
    # comment (`// "running" | "stopped"`, all over this file) stays comment,
    # and a `//` inside a string literal stays string.
    text = LEXEMES.sub(lambda m: '""' if m[0].startswith('"') else " ", text)
    out = Proto()
    stack: list[tuple[str, str]] = []
    buf: list[str] = []

    def scope() -> str:
        return ".".join(n for k, n in stack if k == "message")

    def in_message() -> bool:
        kinds = [k for k, _ in stack]
        while kinds and kinds[-1] == "oneof":
            kinds.pop()
        return bool(kinds) and kinds[-1] == "message"

    def service() -> str | None:
        return stack[-1][1] if stack and stack[-1][0] == "service" else None

    def rpc(stmt: str) -> bool:
        m = RPC.match(stmt)
        svc = service()
        if m and svc:
            norm = lambda t: " ".join(t.split()).lstrip(".")
            out.rpcs[f"{svc}.{m['name']}"] = (norm(m["req"]), norm(m["resp"]))
            return True
        return False

    for ch in text:
        if ch not in "{};":
            buf.append(ch)
            continue
        stmt = " ".join("".join(buf).split())
        buf = []
        if ch == "{":
            m = BLOCK.match(stmt)
            if m:
                stack.append((m[1], m[2]))
                if m[1] == "message":
                    out.messages[scope()] = {}
            elif rpc(stmt):
                stack.append(("rpc", stmt))
            else:
                stack.append(("other", stmt))  # an option block, an rpc's body
        elif ch == ";":
            if not stmt or stmt.split()[0] in NOT_A_FIELD:
                continue
            if in_message():
                m = FIELD.match(stmt)
                if not m:
                    raise SystemExit(f"C39 cannot read this statement in {scope()}: {stmt!r}")
                t = re.sub(r"\s+", "", m["type"]) if m["type"].startswith("map") else m["type"]
                out.messages[scope()][int(m["num"])] = (m["name"], t.lstrip("."), m["label"] or "")
            else:
                rpc(stmt)
        else:  # "}"
            if stack:
                stack.pop()
    if stack:
        raise SystemExit(f"C39 unbalanced braces: still inside {stack}")
    return out


@dataclass
class Counts:
    fields: int = 0          # fields added to messages that existed at the base
    touched: int = 0         # how many such messages gained one
    messages: int = 0        # messages that did not exist at the base
    rpcs: int = 0            # rpcs that did not exist at the base
    retyped: int = 0         # rpcs whose request or response type changed
    removed: list[str] = field(default_factory=list)  # anything gone, renamed or renumbered

    def line(self) -> str:
        return (f"{self.fields} fields on {self.touched} messages that already existed, "
                f"{self.messages} new messages and {self.rpcs} new rpcs; "
                f"{self.retyped} rpc(s) retyped; {len(self.removed)} removal(s) or change(s) in place")


def count(base: Proto, head: Proto) -> Counts:
    c = Counts()
    for name, hf in head.messages.items():
        bf = base.messages.get(name)
        if bf is None:
            c.messages += 1
            continue
        added = set(hf) - set(bf)
        c.fields += len(added)
        c.touched += bool(added)
        for num in sorted(set(bf) & set(hf)):
            if bf[num] != hf[num]:
                c.removed.append(f"{name} field {num}: {bf[num]} -> {hf[num]}")
        for num in sorted(set(bf) - set(hf)):
            c.removed.append(f"{name} field {num} ({bf[num][0]}) removed")
    c.removed += [f"message {n} removed" for n in sorted(set(base.messages) - set(head.messages))]
    c.rpcs = len(set(head.rpcs) - set(base.rpcs))
    c.retyped = sum(1 for r in set(base.rpcs) & set(head.rpcs) if base.rpcs[r] != head.rpcs[r])
    c.removed += [f"rpc {r} removed" for r in sorted(set(base.rpcs) - set(head.rpcs))]
    return c


# ── reading the tree and the tags ───────────────────────────────────────────

def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def proto_at(root: Path, ref: str | None) -> str | None:
    """The proto at a git ref, or in the working tree when `ref` is None."""
    if ref is None:
        return (root / PROTO).read_text(encoding="utf-8")
    r = git(root, "show", f"{ref}:{PROTO}")
    return r.stdout if r.returncode == 0 else None


def tag_exists(root: Path, tag: str) -> bool:
    return git(root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}").returncode == 0


def newest_sdk_tag(root: Path) -> str | None:
    """The highest `sdk-vX.Y.Z` that is an ancestor of HEAD."""
    tags = git(root, "tag", "-l", "sdk-v*").stdout.split()
    key = lambda t: tuple(int(x) for x in re.findall(r"\d+", t)[:3])
    for t in sorted((t for t in tags if re.fullmatch(rf"sdk-v{SEMVER}", t)), key=key, reverse=True):
        if git(root, "merge-base", "--is-ancestor", t, "HEAD").returncode == 0:
            return t
    return None


def newest_entry(text: str) -> tuple[str, bool, str] | None:
    """(version, unreleased?, the entry's text) for a CHANGELOG's first `## [`."""
    heads = list(ENTRY.finditer(text))
    if not heads:
        return None
    end = heads[1].start() if len(heads) > 1 else len(text)
    return heads[0][1], heads[0][2].strip().lower().startswith("unreleased"), text[heads[0].end():end]


def rust_version(root: Path) -> str:
    toml = (root / "astra-plugin-sdk/Cargo.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', toml, re.M).group(1)


def docs_locales(root: Path) -> tuple[str, ...]:
    sys.path.insert(0, str(root / "docs" / "tools"))
    try:
        from locales import LOCALES  # the one declaration of the docs set
    finally:
        sys.path.pop(0)
    return tuple(LOCALES)


# ── the comparisons ─────────────────────────────────────────────────────────

class Checker:
    def __init__(self, root: Path):
        self.root = root
        self.fails: list[str] = []
        self.oks = 0
        self.compared = 0  # statements actually held against a parse
        self._cache: dict[tuple[str | None, str | None], Counts | None] = {}

    def check(self, ok: bool, msg: str, detail: str = "") -> None:
        print(("ok   " if ok else "FAIL ") + msg)
        if ok:
            self.oks += 1
        else:
            self.fails.append(msg)
            if detail:
                print("       " + detail)

    def counts(self, base: str, head: str | None) -> Counts | None:
        key = (base, head)
        if key not in self._cache:
            b, h = proto_at(self.root, base), proto_at(self.root, head)
            self._cache[key] = None if b is None or h is None else count(parse(b), parse(h))
        return self._cache[key]

    def changelogs(self) -> None:
        newest = newest_sdk_tag(self.root)
        tree = proto_at(self.root, None)
        changed = newest is not None and proto_at(self.root, newest) != tree
        for name, path in CHANGELOGS.items():
            entry = newest_entry((self.root / path).read_text(encoding="utf-8"))
            if entry is None:
                self.check(False, f"C39 {path} has a `## [version]` entry")
                continue
            version, unreleased, body = entry
            if not unreleased:
                print(f"note C39 {path}'s newest entry, [{version}], is dated: history, not compared")
                continue
            flat = " ".join(body.replace("*", "").split())
            claims = list(SENTENCE.finditer(flat))
            if name == "rust" and changed:
                self.check(bool(claims),
                           f"C39 {path} [{version}] says what the protocol gained since {newest}",
                           "the Rust SDK re-exports the generated types; write \"Between "
                           f"`{newest}` and this release the protocol gained F fields on M "
                           "messages that already existed, N new messages and R new rpcs\", "
                           f"with the numbers from `--count {newest}`")
            for m in claims:
                self.compare(f"{path} [{version}]", m, self.counts(m["base"], None), m["base"], "this tree")

    def compare(self, where: str, m: re.Match, c: Counts | None, base: str, head: str) -> None:
        if c is None:
            self.check(False, f"C39 {where} names {base}, which this checkout cannot read",
                       "is the tag fetched? the couplings job checks out with fetch-depth: 0")
            return
        self.compared += 1
        said = {k: int(m[k]) for k in ("fields", "touched", "messages", "rpcs")}
        real = {"fields": c.fields, "touched": c.touched, "messages": c.messages, "rpcs": c.rpcs}
        if m["retyped"] is not None:
            said["retyped"], real["retyped"] = int(m["retyped"]), c.retyped
        elif c.retyped:
            said["retyped"], real["retyped"] = 0, c.retyped
        self.check(said == real, f"C39 {where}: {base} -> {head} is {c.line()}",
                   f"the entry says {said}, the proto says {real}")
        if m["nothing"]:
            self.check(not c.removed, f"C39 {where} says nothing was removed or renumbered",
                       "; ".join(c.removed[:5]))

    def docs(self) -> None:
        rust_v = rust_version(self.root)
        rust_entry = newest_entry((self.root / CHANGELOGS["rust"]).read_text(encoding="utf-8"))
        for loc in docs_locales(self.root):
            path = f"docs/{loc}/versioning.md"
            text = (self.root / path).read_text(encoding="utf-8")
            paras = [p for p in re.split(r"\n\s*\n", text) if DOCS_PAIR.search(" ".join(p.split()))]
            self.check(len(paras) == 1,
                       f"C39 {path} has one paragraph counting the fields a re-sync added",
                       f"found {len(paras)}")
            if len(paras) != 1:
                continue
            flat = " ".join(paras[0].split())
            pair = DOCS_PAIR.search(flat)
            base, head_v = f"sdk-v{pair['base']}", pair["head"]
            ints = BARE_INT.findall(flat)
            if tag_exists(self.root, f"sdk-v{head_v}"):
                head, label = f"sdk-v{head_v}", f"sdk-v{head_v}"
            elif head_v == rust_v and rust_entry and rust_entry[1]:
                head, label = None, f"this tree ({head_v}, unreleased)"
            else:
                self.check(False, f"C39 {path} counts up to {head_v}, which is measurable",
                           f"there is no tag sdk-v{head_v} and this tree is {rust_v}")
                continue
            c = self.counts(base, head)
            if c is None:
                self.check(False, f"C39 {path} names {base}, which this checkout cannot read")
                continue
            self.compared += 1
            self.check(ints == [str(c.fields)],
                       f"C39 {path}: {base} -> {label} added {c.fields} fields to messages that already existed",
                       f"the paragraph's bare numbers are {ints}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--count", metavar="BASE", help="print what the protocol gained since BASE")
    ap.add_argument("--head", metavar="REF", help="with --count: a ref instead of the working tree")
    a = ap.parse_args()
    if a.count:
        b, h = proto_at(a.root, a.count), proto_at(a.root, a.head)
        if b is None or h is None:
            print(f"cannot read {PROTO} at {a.count if b is None else a.head}", file=sys.stderr)
            return 2
        c = count(parse(b), parse(h))
        print(c.line())
        for r in c.removed:
            print("  " + r)
        return 0
    ch = Checker(a.root)
    ch.changelogs()
    ch.docs()
    # Every locale's paragraph, at least: a check that matches nothing is green
    # for ever. (The Rust CHANGELOG's sentence has its own MUST, above, and is
    # rightly absent once the entry is dated.)
    floor = len(docs_locales(a.root))
    ch.check(ch.compared >= floor, f"C39 compared {ch.compared} statement(s); the floor is {floor}")
    if ch.fails:
        print(f"\nC39: {len(ch.fails)} statement(s) about the protocol disagree with it.")
        return 1
    print(f"\nC39: {ch.oks} statement(s) about the protocol agree with it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
