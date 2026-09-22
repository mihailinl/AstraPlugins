#!/usr/bin/env python3
"""In a Rust doc comment, indented prose is a doctest.

    python3 tools/check-doc-fences.py                # C34, both legs
    python3 tools/check-doc-fences.py --rules C34a   # the convention alone
    python3 tools/check-doc-fences.py --rules C34b   # the lane alone
    python3 tools/check-doc-fences.py --inventory    # every code block it found

Rustdoc parses the body of a `//!` or `///` comment as CommonMark, and a
CommonMark code block needs no fence: four spaces of indentation after a blank
line is one. A code block with no info string is Rust, and rustdoc compiles it.
So a table, an ASCII diagram or an aligned list of measurements, written into a
doc comment the way anyone would write it into a paragraph, is handed to the
compiler — and the error is a lexer error about a character in a sentence, in a
file whose only change was prose.

The estate next door hit exactly that: a measurement table with backticks and a
`←` in `operations.rs`, `error: unknown start of token: \\u{2190}`, found only
because somebody eventually ran the workspace tests. The prose author did not,
and would not have: the change was a comment. **In this language, prose is a
test run**, and nothing said so.

Two legs, because the defect has two halves and the second is the one that
decides whether the first is ever seen.

C34a — no bare indented code block in any Rust doc comment in this tree.

    The convention here was already unanimous when this rule was written: 33
    code blocks in doc comments across the five crates, all 33 fenced, not one
    bare indented block. That is the reason to write it down. A unanimous
    convention that nothing enforces is one prose edit away from not being one,
    and the edit will be made by someone who correctly believes they changed no
    code.

    This leg covers crates rustdoc cannot reach. `astra-plugin-cli` and the ten
    `examples/*` are binary crates with no library target, and `cargo test
    --doc` on a bin crate does not run an empty doctest suite — it refuses:
    `error: no library targets found in package`. Their doc comments are
    compiled by nothing, ever, so this scan is the only thing that will ever
    read them.

    What it gives up, stated plainly: the CLI's scaffold templates
    (`astra-plugin-cli/src/templates/*.rs`) hold `///` lines inside Rust raw
    strings, and they are scanned as written rather than as string data. That
    is deliberate — a doc comment the scaffold emits becomes a doc comment in
    an author's crate — but it means a flag there names a line that rustdoc
    would not compile *here*.

C34b — every crate in this tree with a library target is named by a
    `cargo test … --doc` step in `ci.yml`, or is on the exemption list with a
    reason.

    This is the half that was actually broken. `ci.yml`'s `sdk-rust` job runs
    `cargo test --manifest-path astra-plugin-sdk/Cargo.toml --all-targets` and
    then, on the next line, `--doc`. It runs `cargo test --manifest-path
    astra-plugin-macros/Cargo.toml --all-targets` and does not. **`--all-targets`
    does not include doctests** — it is lib, bins, tests, examples and benches,
    and rustdoc is none of them. So `astra-plugin-macros` had seven doctests
    that no lane on this repository has ever compiled.

    Watched, before this rule existed, with a bare indented block put into
    `astra-plugin-macros/src/lib.rs`'s `//!` header:

        cargo test --manifest-path astra-plugin-macros/Cargo.toml --all-targets
            -> test result: ok. 3 passed; 0 failed                    exit 0
        cargo test --manifest-path astra-plugin-macros/Cargo.toml --doc
            -> error: unknown start of token: \\u{2190}
               test result: FAILED. 0 passed; 1 failed                exit 101

    A defect `cargo test` catches on a developer's machine but no workflow
    invokes is a defect nothing catches, and this one was green in CI for the
    life of the crate.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── floors ──────────────────────────────────────────────────────────────────
# Written before the mutation, and deliberately below the census rather than at
# it: a floor standing at today's count is not a floor, it is the tree's
# history copied into a third file (C27's lesson). Today: 83 Rust files, 13
# manifests, 33 fenced blocks, 3 library targets. A scan that finds fewer than
# these has broken as a SCAN, and says so in those words — because an empty
# enumeration passes quietly, for ever, while reading as coverage.
MIN_RUST_FILES = 60
MIN_MANIFESTS = 10
MIN_FENCED_BLOCKS = 20
# This one IS at the census, and it is the exception the rule above is about.
# Three is the whole set — there is no room under it — so its job is narrower:
# it fails when `has_lib` stops detecting anything, which is the way this leg
# would otherwise pass every crate by being unable to see one. A crate
# legitimately losing its library target reds this line, and that is wanted:
# it is a change to which sources rustdoc reads, and someone should say so here.
MIN_LIB_CRATES = 3

# ── C34b's exemption list ───────────────────────────────────────────────────
# Rule 6 of dev/couplings.md: a new library target arrives as a one-line answer
# to "does this need a --doc step, and why not?", rather than as an absence
# nobody notices.
DOC_LANE_EXEMPT = {
    "astra-plugin-cli/vendor/astra-plugin-manifest/Cargo.toml": (
        "Vendored byte-for-byte from Astra and held there by "
        "tools/check-manifest-crate.sh, so its doc comments are not this "
        "repository's to edit. It is built here only as a path dependency, and "
        "cargo never runs a dependency's doctests — a --doc step would have to "
        "name the vendored manifest directly, which is a second place to test a "
        "file this repo may not change. C34a still scans its sources, which is "
        "the coverage that matters: a bare indented block would be caught here "
        "and fixed upstream."
    ),
}

DOC_LINE = re.compile(r"^(\s*)(///|//!)(?!/)(.*)$")
FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(.*)$")
ATX = re.compile(r"^#{1,6}(\s|$)")
THEMATIC = re.compile(r"^(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
BULLET = re.compile(r"^([-+*])(\s+)(?=\S)")
ORDERED = re.compile(r"^(\d{1,9}[.)])(\s+)(?=\S)")

# Info-string tokens that leave a fence Rust as far as rustdoc is concerned.
RUST_ATTRS = {
    "", "rust", "ignore", "should_panic", "no_run", "compile_fail",
    "test_harness", "allow_fail", "standalone_crate", "standalone", "edition2015",
    "edition2018", "edition2021", "edition2024",
}


def fence_is_rust(info: str) -> bool:
    toks = [t for t in re.split(r"[,\s]+", info.strip()) if t]
    if not toks:
        return True
    return all(t.lower() in RUST_ATTRS or t.lower().startswith("ignore-") for t in toks)


def expand_tabs(line: str) -> str:
    out = []
    col = 0
    for ch in line:
        if ch == "\t":
            n = 4 - (col % 4)
            out.append(" " * n)
            col += n
        else:
            out.append(ch)
            col += 1
    return "".join(out)


def doc_runs(lines: list[str]):
    """Yield (marker, first_line_1based, [text after the marker])."""
    run = None
    for i, line in enumerate(lines):
        m = DOC_LINE.match(line)
        if m and run and run[0] == m.group(2):
            run[2].append(m.group(3))
        elif m:
            if run:
                yield tuple(run)
            run = [m.group(2), i + 1, [m.group(3)]]
        elif run:
            yield tuple(run)
            run = None
    if run:
        yield tuple(run)


def unindent(texts: list[str]) -> list[str]:
    """What rustdoc does before parsing: strip the common left margin, so
    `///     x` on every line of a run is prose and not a code block."""
    widths = [len(t) - len(t.lstrip(" ")) for t in texts if t.strip()]
    n = min(widths) if widths else 0
    return ["" if not t.strip() else t[n:] for t in texts]


def scan_blocks(body: list[str]):
    """Walk one doc comment's markdown and yield every code block it contains.

    Yields (offset, form, info) where form is "indented" or "fenced". A
    block-level CommonMark walk, not a full parser: enough to know fenced code
    from indented code from list continuation from block quotes, which is the
    whole question. Cross-checked line-for-line against rustdoc's own
    `cargo test --doc -- --list` over this tree, and against markdown-it-py
    over a corpus of nesting cases.
    """
    fence: tuple[str, int, int] | None = None   # (char, length, indent)
    containers: list[int] = []                  # content columns of open list items
    in_paragraph = False
    skip_until = -1

    for i, raw in enumerate(body):
        if i < skip_until:
            continue
        line = expand_tabs(raw)
        blank = not line.strip()

        # Block quotes: strip the markers and treat the remainder in place. A
        # quoted indented block is still a code block, and still Rust.
        quote_cols = 0
        probe = line
        while True:
            m = re.match(r"^( {0,3})>( ?)", probe)
            if not m or fence:
                break
            quote_cols += len(m.group(0))
            probe = probe[len(m.group(0)):]
        if quote_cols:
            line = probe
            blank = not line.strip()

        indent = len(line) - len(line.lstrip(" "))
        rest = line[indent:]
        base = containers[-1] if containers else 0

        if fence:
            fchar, flen, find = fence
            if not blank and indent - find <= 3:
                m = FENCE_OPEN.match(rest)
                if m and m.group(1)[0] == fchar and len(m.group(1)) >= flen \
                        and not m.group(2).strip():
                    fence = None
            continue

        if blank:
            in_paragraph = False
            continue

        # Close list items the line has dedented out of.
        while containers and indent < containers[-1] and not in_paragraph:
            containers.pop()
            base = containers[-1] if containers else 0

        rel = indent - base

        if rel >= 4:
            if not in_paragraph:
                yield (i, "indented", None)
                # Swallow the rest of the block, so its lines are not re-read
                # as markup and the same block is not reported once a line. An
                # indented block ends at the first non-blank line with rel < 4.
                j = i + 1
                while j < len(body):
                    nxt = expand_tabs(body[j])
                    if nxt.strip() and len(nxt) - len(nxt.lstrip(" ")) - base < 4:
                        break
                    j += 1
                skip_until = j
                in_paragraph = False
            continue

        m = FENCE_OPEN.match(rest)
        if m:
            fence = (m.group(1)[0], len(m.group(1)), indent)
            info = m.group(2).strip()
            yield (i, "fenced", info)
            in_paragraph = False
            continue

        if ATX.match(rest) or THEMATIC.match(rest):
            in_paragraph = False
            continue

        lm = BULLET.match(rest) or ORDERED.match(rest)
        if lm:
            containers.append(indent + len(lm.group(1)) + len(lm.group(2)))
            in_paragraph = bool(rest[len(lm.group(0)):].strip())
            continue

        in_paragraph = True


def rust_files():
    for p in sorted(ROOT.rglob("*.rs")):
        rel = p.relative_to(ROOT)
        if any(part in ("target", ".git", "node_modules") for part in rel.parts):
            continue
        yield rel, p


def collect():
    """Every code block in every Rust doc comment in the tree."""
    blocks = []
    n_files = 0
    for rel, path in rust_files():
        n_files += 1
        # Read as bytes: astra-plugin-sdk/src/testing/fixtures.rs carries a
        # deliberate NUL in a fixture, which makes it a binary file to grep and
        # to anything else that stops at the first one.
        text = path.read_bytes().decode("utf-8", errors="replace")
        lines = text.splitlines()
        for marker, start, texts in doc_runs(lines):
            body = unindent(texts)
            for off, form, info in scan_blocks(body):
                blocks.append({
                    "file": str(rel),
                    "line": start + off,
                    "marker": marker,
                    "form": form,
                    "info": info,
                    "text": (body[off] if form == "indented" else "").strip()[:80],
                })
    return n_files, blocks


class Fails(list):
    pass


def check(fails, ok, msg, detail=""):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg + (("\n       " + detail) if detail else ""))


def rule_C34a(fails):
    n_files, blocks = collect()

    check(fails, n_files >= MIN_RUST_FILES,
          f"C34a the SCAN found {n_files} Rust files (floor {MIN_RUST_FILES})",
          "The scan broke, not the rule: this walk is rglob('*.rs') from the "
          "repository root. Fewer files than the floor means it is looking in "
          "the wrong place, and an empty walk reports no indented blocks for "
          "the wrong reason.")

    fenced = [b for b in blocks if b["form"] == "fenced"]
    check(fails, len(fenced) >= MIN_FENCED_BLOCKS,
          f"C34a the SCAN found {len(fenced)} fenced blocks in doc comments "
          f"(floor {MIN_FENCED_BLOCKS})",
          "The scan broke, not the rule: doc comments in this tree carry "
          "dozens of fenced examples. Finding almost none means the doc-comment "
          "reader stopped reading them, and a reader that sees nothing cannot "
          "see an indented block either.")

    indented = [b for b in blocks if b["form"] == "indented"]
    detail = "\n       ".join(
        f"{b['file']}:{b['line']}  {b['marker']}  {b['text']!r}" for b in indented)
    check(fails, not indented,
          f"C34a no bare indented block in a Rust doc comment "
          f"({len(fenced)} fenced blocks, {len(indented)} indented)",
          (detail + "\n\n       "
           "Four spaces after a blank line is a CommonMark code block, a code "
           "block with no info string is Rust, and rustdoc compiles it. Fence "
           "it and name the language — ```text for a table or a diagram, "
           "```console for a transcript, ```json/```toml for a payload. Use "
           "```rust or ```ignore only if it really is Rust.\n       "
           "This is not a style rule: `cargo test --doc` on the crate that "
           "owns this file will fail to COMPILE, and on a crate with no "
           "library target nothing will run it at all — the block will simply "
           "be wrong for ever.") if indented else "")

    by_info = {}
    for b in fenced:
        by_info[b["info"]] = by_info.get(b["info"], 0) + 1
    print("       fences: " + ", ".join(
        f"```{k or '(bare)'} x{v}{'' if fence_is_rust(k or '') else '  [not Rust]'}"
        for k, v in sorted(by_info.items(), key=lambda kv: (-kv[1], kv[0]))))


def lib_crates():
    """Every package in this tree with a library target, which is exactly the
    set rustdoc will collect doctests from."""
    out = []
    for man in sorted(ROOT.rglob("Cargo.toml")):
        rel = man.relative_to(ROOT)
        if any(part in ("target", ".git", "node_modules") for part in rel.parts):
            continue
        text = man.read_text(encoding="utf-8")
        if "[package]" not in text:
            continue
        has_lib = (man.parent / "src" / "lib.rs").exists() or "[lib]" in text
        out.append((str(rel), has_lib))
    return out


def rule_C34b(fails):
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    crates = lib_crates()

    check(fails, len(crates) >= MIN_MANIFESTS,
          f"C34b the SCAN found {len(crates)} Cargo manifests (floor {MIN_MANIFESTS})",
          "The scan broke, not the rule.")

    libs = [c for c, has in crates if has]
    check(fails, len(libs) >= MIN_LIB_CRATES,
          f"C34b the SCAN found {len(libs)} library targets (floor {MIN_LIB_CRATES})",
          "The scan broke, not the rule: this tree has had at least three "
          "library crates since the manifest crate was vendored. Finding fewer "
          "means the lib detection stopped working, and every crate would then "
          "pass this rule by being invisible to it.")

    # A --doc step names its crate through --manifest-path. Read the pairing
    # rather than the word "--doc" on its own: a `cargo test --doc` for one
    # crate is not coverage for the next one.
    doc_steps = set()
    for line in ci.splitlines():
        if "cargo test" not in line or "--doc" not in line:
            continue
        m = re.search(r"--manifest-path\s+(\S+)", line)
        if m:
            doc_steps.add(m.group(1))

    for man in libs:
        if man in doc_steps:
            check(fails, True, f"C34b {man} is doctested by ci.yml")
        elif man in DOC_LANE_EXEMPT:
            print(f"ok   C34b {man} is exempt — {DOC_LANE_EXEMPT[man]}")
        else:
            check(fails, False,
                  f"C34b {man} has a library target and no `cargo test --doc` step",
                  "rustdoc collects doctests from every library target, and "
                  "`--all-targets` does NOT include them: it is lib, bins, "
                  "tests, examples and benches, and rustdoc is none of those. A "
                  "crate tested only with --all-targets can carry a doc comment "
                  "that does not compile, for ever, with every lane green.\n       "
                  "fix: add, beside this crate's existing `cargo test` step in "
                  ".github/workflows/ci.yml,\n       "
                  f"  run: cargo test --manifest-path {man} --doc\n       "
                  "or add it to DOC_LANE_EXEMPT in this file with the reason it "
                  "cannot have one.")

    stale = [m for m in DOC_LANE_EXEMPT if m not in dict(crates)]
    check(fails, not stale,
          "C34b every exemption names a manifest that exists",
          "\n       ".join(stale) + "\n       An exemption left open after the "
          "thing it excused was deleted has the shape of the gap it was "
          "written for." if stale else "")

    covered = [m for m in doc_steps if m not in dict(crates)]
    check(fails, not covered,
          "C34b every --doc step in ci.yml names a manifest that exists",
          "\n       ".join(covered) if covered else "")


RULES = {"C34a": rule_C34a, "C34b": rule_C34b}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rules", default=",".join(RULES),
                    help="comma-separated rule ids (default: all of "
                         + ", ".join(RULES) + ")")
    ap.add_argument("--inventory", action="store_true",
                    help="print every code block found in a Rust doc comment")
    args = ap.parse_args()

    if args.inventory:
        n_files, blocks = collect()
        print(f"{n_files} Rust files, {len(blocks)} code blocks in doc comments")
        for b in blocks:
            what = f"```{b['info'] or '(bare)'}" if b["form"] == "fenced" else "INDENTED"
            print(f"  {b['file']}:{b['line']:<6} {b['marker']}  {what}")
        return 0

    wanted = [r.strip() for r in args.rules.split(",") if r.strip()]
    unknown = [r for r in wanted if r not in RULES]
    if unknown:
        print(f"check-doc-fences: no such rule: {', '.join(unknown)}", file=sys.stderr)
        return 2

    fails = Fails()
    for r in wanted:
        RULES[r](fails)

    print()
    if fails:
        print(f"check-doc-fences: {len(fails)} broken:\n", file=sys.stderr)
        for f in fails:
            print("  " + f, file=sys.stderr)
        return 1
    print(f"check-doc-fences: {', '.join(wanted)} pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
