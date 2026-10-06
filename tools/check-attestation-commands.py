#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""C40: every `gh attestation verify` this tree teaches names the workflow that signed the file.

    python3 tools/check-attestation-commands.py              # the couplings job: this tree
    python3 tools/check-attestation-commands.py --root DIR   # another tree (the test suite)
    python3 tools/check-attestation-commands.py --live       # also RUN the taught commands

THE BUG. `plugin-release.yml` writes release notes into every author's GitHub
Release, and those notes told the reader to check a download with

    gh attestation verify <file>.astraplugin --repo <the author's repository>

On a real release — `mihailinl/astra-registry-canary`'s
`release-canary-c3f3424` 0.20261005.1, run 37327594012 — that fails on a good
file, exit 1, with `Error: verifying with issuer "sigstore.dev"` and not one
word about why. The author's `release.yml` only CALLS the shared workflow, so
the certificate's signer is AstraPlugins' `plugin-release.yml`, at the commit
the caller pinned, and not the author's repository; with `--repo` alone,
`gh` derives its signer matcher from `--repo` and refuses. The registry bot
knew (it passes `--signer-workflow`, docs/en/spec/registry-index.md §7.1), an
ops survey had measured it on 12 of 18 listings (2026-09-20), and still every
author's Release, two docs pages in seven languages and the README taught the
command that fails. Nothing compared what a page teaches with what `gh`
accepts, and nobody ran the printed command against a release built by a
third-party caller until 2026-10-05. (The CLI's own commands passed: its
releases are signed by `release-cli.yml` in this repository, which is what
`--repo` names, so the flag is stricter there rather than load-bearing.)

WHAT COUNTS AS A COMMAND. Every `gh attestation verify` in a tracked text file
followed by at least one argument. Its extent is the inline-code span it opens
(which may cross a line break), the `from="…"` attribute it opens, or else its
line plus `\\` continuations. `gh attestation verify` with nothing after it is
a mention of the tool, not a command, and is not checked.

WHAT EACH COMMAND MUST CARRY. `--signer-workflow`, and:

* a literal value spelled exactly `mihailinl/AstraPlugins/.github/workflows/<f>`,
  case included — `gh` matches the certificate's SAN case-sensitively, and
  `mihailinl/astraplugins/…` fails a good file the same silent way (measured;
  `--signer-repo` does not care, which is how a lowercase spelling would look
  fine in review) — where `<f>` is a workflow file in this tree, with no
  `@ref`: an author pins `plugin-release.yml` by SHA and the SAN carries that
  SHA, so any ref typed into a page fails every caller pinned elsewhere;
* `<f>` must be the workflow that signs that kind of file: `plugin-release.yml`
  for a `.astraplugin`, `release-cli.yml` for a CLI archive;
* never a shell variable. In a reusable workflow `${GITHUB_REPOSITORY}` is the
  CALLER — precisely the repository that did not sign — so a variable here is
  the original bug wearing a different flag;
* a placeholder (`<path>`, `<AstraPlugins>/…`, `…`) passes, as long as a value
  ending in `.yml` still names the right workflow.

`--signer-repo mihailinl/AstraPlugins` also passes on a good file, and is not
enough here: it accepts a signature from ANY workflow in AstraPlugins. The
registry checks the workflow path, and a reader's check should be no weaker
than the registry's.

WHAT IS NOT CHECKED HERE. Whether the literal is the right one: that is
`--live`, which takes the command out of each release workflow's own notes
text, fills in that workflow's newest real release, and runs it (with the
release's own `--bundle`: see `live`) — and runs it once more without
`--signer-workflow` to show the flag is what makes the difference. It reaches
the network on purpose, like C24, and fails rather than skips when it cannot.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SIGNER_REPO = "mihailinl/AstraPlugins"
WORKFLOWS = ".github/workflows"
PLUGIN_SIGNER = "plugin-release.yml"
CLI_SIGNER = "release-cli.yml"

#: This file and its test spell the broken command on purpose.
SELF = {"tools/check-attestation-commands.py", "tools/test_attestation_commands.py"}

#: Commands this tree carries and does not own. Each entry must still match a
#: command, or the run fails: an exemption that outlives its reason is how the
#: next copy of the bug gets in.
EXEMPT: dict[str, tuple[str, str]] = {
    path: (
        "<file> --repo you/dice-roller",
        "generated in Astra (astra-rs/tools/proto-slice) and held byte-identical "
        "here by tools/check-proto.sh and proto-upstream; the comment describes "
        "the string the daemon builds for `verify_command`, so the fix is the "
        "daemon's, and syncing it makes this exemption stale",
    )
    for path in (
        "proto/plugin.proto",
        "astra-plugin-sdk/proto/plugin.proto",
        "astra-plugin-sdk-python/astra_plugin_sdk/proto/plugin.proto",
    )
}

VERIFY = "gh attestation verify"
PLACEHOLDER = re.compile(r"[<>…]|\.\.\.")
LITERAL = re.compile(
    r"^" + re.escape(SIGNER_REPO) + r"/" + re.escape(WORKFLOWS) + r"/([^/@\s]+\.ya?ml)$"
)


@dataclass
class Command:
    path: str
    line: int
    text: str  # everything after `gh attestation verify`, whitespace-normalised

    @property
    def tokens(self) -> list[str]:
        return self.text.split()

    def where(self) -> str:
        return f"{self.path}:{self.line}"


def extent(text: str, at: int) -> str | None:
    """The arguments of the `gh attestation verify` at `at`, or None for a mention."""
    end_kw = at + len(VERIFY)
    if end_kw >= len(text) or text[end_kw] not in " \t":
        return None  # `verify` followed by a backtick, `<br/>`, a full stop, a newline
    line_start = text.rfind("\n", 0, at) + 1
    prefix = text[line_start:at]
    if prefix.endswith("`"):
        close = text.find("`", end_kw)
        body = text[end_kw: close if close != -1 else len(text)]
        body = body.rstrip("\\")  # a heredoc's escaped backtick, \`
    elif prefix.endswith('from="'):
        close = text.find('"', end_kw)
        body = text[end_kw: close if close != -1 else len(text)]
    else:
        parts = []
        pos = end_kw
        while True:
            nl = text.find("\n", pos)
            seg = text[pos: nl if nl != -1 else len(text)]
            if seg.rstrip().endswith("\\") and nl != -1:
                parts.append(seg.rstrip()[:-1])
                pos = nl + 1
                continue
            parts.append(seg)
            break
        body = " ".join(parts)
    body = " ".join(body.split())
    return body or None


def commands_in(rel: str, text: str) -> list[Command]:
    out = []
    pos = 0
    while True:
        at = text.find(VERIFY, pos)
        if at == -1:
            return out
        pos = at + len(VERIFY)
        body = extent(text, at)
        if body is not None:
            out.append(Command(rel, text.count("\n", 0, at) + 1, body))


def tracked_files(root: Path) -> list[str]:
    p = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True
    )
    if p.returncode == 0 and (root / ".git").exists():
        return [f for f in p.stdout.split("\0") if f]
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "target")]
        for name in filenames:
            files.append(str(Path(dirpath, name).relative_to(root)))
    return sorted(files)


def read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def flag_value(tokens: list[str], flag: str) -> str | None:
    for i, tok in enumerate(tokens):
        if tok == flag:
            return tokens[i + 1] if i + 1 < len(tokens) else ""
        if tok.startswith(flag + "="):
            return tok[len(flag) + 1:]
    return None


def expected_signer(tokens: list[str]) -> str | None:
    """Which workflow signs the file this command names, when the name says."""
    for tok in tokens:
        if tok.startswith("-"):
            return None  # the file comes first in every command this tree writes
        if tok.endswith(".astraplugin"):
            return PLUGIN_SIGNER
        if tok.endswith((".tar.gz", ".tgz", ".zip")) or tok == "<archive>":
            return CLI_SIGNER
        return None
    return None


def problems(cmd: Command, workflows: set[str]) -> list[str]:
    toks = cmd.tokens
    value = flag_value(toks, "--signer-workflow")
    want = expected_signer(toks)
    if value is None:
        hint = (
            f" — and `--signer-repo` is not enough: it accepts any workflow in {SIGNER_REPO}"
            if flag_value(toks, "--signer-repo") is not None else ""
        )
        name = want or PLUGIN_SIGNER
        return [
            f"no `--signer-workflow`{hint}. The signer is "
            f"{SIGNER_REPO}/{WORKFLOWS}/{name}, not the repository `--repo` names, so "
            f"this fails a good file with `Error: verifying with issuer \"sigstore.dev\"`. "
            f"Add `--signer-workflow {SIGNER_REPO}/{WORKFLOWS}/{name}`."
        ]
    if not value:
        return ["`--signer-workflow` has no value"]
    if "$" in value:
        return [
            f"`--signer-workflow {value}` is a shell variable. Name the signer literally: "
            "in a reusable workflow `${GITHUB_REPOSITORY}` is the CALLER, which is exactly "
            "the repository that did not sign the file."
        ]
    name = value.rsplit("/", 1)[-1] if value.endswith((".yml", ".yaml")) else None
    found = []
    if not PLACEHOLDER.search(value):
        m = LITERAL.match(value)
        if not m:
            return [
                f"`--signer-workflow {value}` is not spelled "
                f"`{SIGNER_REPO}/{WORKFLOWS}/<file>.yml` exactly. `gh` matches it against the "
                "certificate case-sensitively and refuses a ref the caller did not pin, so a "
                "near miss fails a good file."
            ]
        if m.group(1) not in workflows:
            found.append(f"`{m.group(1)}` is not a workflow in {WORKFLOWS}/")
    if want and name and name != want:
        found.append(
            f"`--signer-workflow` names `{name}`, but this file is signed by `{want}`"
        )
    return found


def scan(root: Path) -> tuple[list[Command], list[str]]:
    """Every command in the tree, and every failure, exemptions applied."""
    workflows = {p.name for p in (root / WORKFLOWS).glob("*.y*ml")}
    cmds: list[Command] = []
    fails: list[str] = []
    used: set[str] = set()
    for rel in tracked_files(root):
        if rel in SELF:
            continue
        text = read_text(root / rel)
        if text is None or VERIFY not in text:
            continue
        for cmd in commands_in(rel, text):
            cmds.append(cmd)
            errs = problems(cmd, workflows)
            if not errs:
                continue
            ex = EXEMPT.get(rel)
            if ex and cmd.text == ex[0]:
                used.add(rel)
                print(f"exempt {cmd.where()}  {VERIFY} {cmd.text}\n       ({ex[1]})")
                continue
            for e in errs:
                fails.append(f"{cmd.where()}  {VERIFY} {cmd.text}\n       {e}")
    for rel, (text, _) in EXEMPT.items():
        if rel not in used and (root / rel).exists():
            fails.append(
                f"{rel}  the exemption for `{VERIFY} {text}` matches no failing command. "
                "Whatever it excused is gone or fixed: delete it from EXEMPT."
            )
    return cmds, fails


# ── --live ────────────────────────────────────────────────────────────────────

CANARY_REPO = "mihailinl/astra-registry-canary"
CLI_REPO = SIGNER_REPO


def gh(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, cwd=cwd)


def notes_command(root: Path, workflow: str) -> Command:
    rel = f"{WORKFLOWS}/{workflow}"
    cmds = [c for c in commands_in(rel, (root / rel).read_text(encoding="utf-8"))]
    if len(cmds) != 1:
        raise SystemExit(
            f"FAIL {rel}: expected exactly one taught `{VERIFY}` in the release notes, "
            f"found {len(cmds)}"
        )
    return cmds[0]


def newest_release(repo: str, prefix: str) -> dict:
    p = gh("release", "list", "-R", repo, "--limit", "40",
           "--json", "tagName,isDraft,publishedAt")
    if p.returncode != 0:
        raise SystemExit(f"FAIL could not list {repo}'s releases:\n{p.stderr.strip()}")
    rels = [r for r in json.loads(p.stdout)
            if not r["isDraft"] and r["tagName"].startswith(prefix)]
    if not rels:
        raise SystemExit(f"FAIL {repo} has no published release tagged {prefix}*")
    return max(rels, key=lambda r: r["publishedAt"])


def run_taught(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", "attestation", "verify", *argv],
                          capture_output=True, text=True, cwd=cwd)


def without_signer(argv: list[str]) -> list[str]:
    out, skip = [], False
    for tok in argv:
        if skip:
            skip = False
            continue
        if tok == "--signer-workflow":
            skip = True
            continue
        if tok.startswith("--signer-workflow="):
            continue
        out.append(tok)
    return out


def live_leg(label: str, cmd: Command, argv: list[str], work: Path) -> list[str]:
    fails = []
    print(f"run   {label}: gh attestation verify {' '.join(argv)}")
    p = run_taught(argv, work)
    if p.returncode != 0:
        fails.append(
            f"{cmd.where()} the command these notes teach FAILS on a real release "
            f"({label}), exit {p.returncode}:\n       {p.stderr.strip()}"
        )
    else:
        print(f"ok    {label}: the taught command passes (exit 0)")
    bare = without_signer(argv)
    q = run_taught(bare, work)
    if q.returncode != 0 and "verifying with issuer" in q.stderr:
        print(f"note  {label}: without --signer-workflow it fails, exit {q.returncode}: "
              f"{q.stderr.strip()}")
    elif q.returncode == 0:
        print(f"note  {label}: without --signer-workflow it passes too — the flag is "
              "stricter here, not load-bearing (signer and source are one repository)")
    else:
        print(f"note  {label}: without --signer-workflow: exit {q.returncode}, "
              f"{q.stderr.strip()}")
    return fails


def fetch(repo: str, tag: str, pattern: str, work: Path) -> Path | str:
    """One asset of a release, or why not."""
    p = gh("release", "download", tag, "-R", repo, "-p", pattern, "-D", str(work), "--clobber")
    got = sorted(work.glob(pattern))
    if p.returncode != 0 or len(got) != 1:
        return f"could not download {repo} {tag}'s {pattern}: {p.stderr.strip() or got}"
    return got[0]


def live(root: Path) -> list[str]:
    """Run each release workflow's taught command against its newest real release.

    `--bundle` is added, pointing at the `.sigstore.jsonl` the same release
    carries, and that is the one change to what a reader runs: it moves where
    the attestation comes from, not what is checked. It is there because the
    API lookup needs `attestations: read`, which ci.yml cannot ask for —
    `release-sdks.yml` calls ci.yml with `contents: read`, and a called job
    asking for more fails the release at startup.
    """
    if not shutil.which("gh"):
        return ["--live needs `gh` on PATH"]
    fails: list[str] = []
    with tempfile.TemporaryDirectory(prefix="c40-") as tmp:
        work = Path(tmp)

        # A third party's release, built by calling plugin-release.yml: the case
        # every author is in, and the one the printed command failed.
        cmd = notes_command(root, PLUGIN_SIGNER)
        tag = newest_release(CANARY_REPO, "release-canary-")["tagName"]
        asset = fetch(CANARY_REPO, tag, "*-linux-x64.astraplugin", work)
        bundle = fetch(CANARY_REPO, tag, "*.sigstore.jsonl", work)
        for got in (asset, bundle):
            if isinstance(got, str):
                return fails + [got]
        argv = [
            {"<file>.astraplugin": asset.name}.get(t, t)
            .replace("${GITHUB_REPOSITORY}", CANARY_REPO)
            for t in cmd.tokens
        ] + ["--bundle", bundle.name]
        fails += live_leg(f"{CANARY_REPO} {tag}", cmd, argv, work)

        # The CLI's own release, built by release-cli.yml in this repository.
        cmd = notes_command(root, CLI_SIGNER)
        tag = newest_release(CLI_REPO, "cli-v")["tagName"]
        version = tag.removeprefix("cli-v")
        asset = fetch(CLI_REPO, tag, f"astra-plugin-{version}-linux-x64-musl.tar.gz", work)
        bundle = fetch(CLI_REPO, tag, f"astra-plugin-{version}.sigstore.jsonl", work)
        for got in (asset, bundle):
            if isinstance(got, str):
                return fails + [got]
        argv = [
            t.replace("$VERSION", version).replace("${GITHUB_REPOSITORY}", CLI_REPO)
            for t in cmd.tokens
        ] + ["--bundle", bundle.name]
        fails += live_leg(f"{CLI_REPO} {tag}", cmd, argv, work)
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--live", action="store_true",
                    help="also run each release workflow's taught command against a real release")
    args = ap.parse_args()
    root = args.root.resolve()

    cmds, fails = scan(root)
    for cmd in cmds:
        print(f"seen  {cmd.where()}")
    print(f"C40   {len(cmds)} taught `{VERIFY}` command(s); {len(fails)} failure(s)")
    if args.live:
        fails += live(root)
    for f in fails:
        print(f"FAIL  {f}", file=sys.stderr)
    if fails:
        return 1
    print("ok    every taught command names its signer workflow"
          + (", and the release workflows' own commands pass on real releases" if args.live else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
