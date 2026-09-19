#!/usr/bin/env python3
"""The claims this repository makes about things that live somewhere else.

    python3 tools/check-registry-mirrors.py                  # every rule
    python3 tools/check-registry-mirrors.py --rules C24      # one of them

Every rule here compares a literal written down in AstraPlugins against the
thing it is a copy of — a tag on the remote, a workflow file, the CLI's own
sources. `tools/check-locales.py` already does this for the locale vocabulary
and the listing caps; this file is for the rest, and it exists because of one
failure in particular.

C24 — every commit SHA that claims to be `plugin-release/v1` is that tag's
    commit, and the retired pin is gone.

    An author's first release is a `uses: …/plugin-release.yml@<sha>` line that
    `astra-plugin init-ci` wrote and nobody reads again. When the SHA in it is
    wrong the run dies in the author's own repository, before a job opens, with
    `invalid value workflow reference` and no clue about whose mistake it was.
    That has already happened twice for two different reasons: `init-ci`
    resolved the ANNOTATED tag to its tag object instead of the commit it
    names, and, separately, a SHA in the docs was six characters off in the
    middle.

    The second failure is the one this rule is about, because the fix for the
    first one made it worse. The docs teach an author to check their build by
    reading the SHA `init-ci` prints — so the docs carry that SHA, in six pages
    times seven locales, plus three READMEs. The tag moved on 2026-08-19 and
    eighty-one lines in forty-five files went on naming `e3329df…`, which is
    no longer what `plugin-release/v1` points at and is no longer the only
    commit `trust.json` allows: the registry's serial-2 trust.json, issued the
    day the tag moved, lists two. Nothing in this repository compared a
    documented SHA with the tag, so nothing could have noticed.

    The comparison is against the REMOTE, on every run, because the question is
    "what does the tag point at today" and no literal in this tree can answer
    it. `git ls-remote` is asked for both the ref and its peeled `^{}` form,
    which is the same pair `init_ci.rs::tag_refspecs` asks for, and the peeled
    line wins when the remote sends one. A failed `ls-remote` FAILS this rule;
    it does not skip. A rule about a network fact that passes when the network
    is missing is the check we already got wrong once.

    On 2026-09-19 the remote answers with ONE line and no `^{}`: the tag is
    lightweight now, which is why the whole tag-object diagnostic the docs
    carried is history rather than advice. The peeled branch stays, because
    whoever moves this tag next may well annotate it again, and that is the
    day `init-ci`'s first bug comes back.

C25 — no workflow in this repository calls the plugins service.

    Neither `plugin-release.yml` nor the caller `astra-plugin init-ci`
    generates names the service's host, path, author audience, wake path or
    OIDC token-request variables, and neither fetches a host that is not
    GitHub's. The reusable workflow keeps exactly the jobs `plan`, `build`
    and `publish`.

    The asymmetry is the point. A call in `plugin-release.yml` is a line we
    can delete tomorrow; a call in the generated caller is compiled into
    every author's repository and supported for twelve months after the
    first CLI release that stops emitting it (ID-73). DEC-3 defers the notify
    job, so at launch there is no call, and FLOW-56 — no service answer,
    refusal or outage may fail an author's release run — holds by
    construction. `rule_C25`'s docstring says what a commit that adds a call
    has to do in the same commit.

C26 — the CLI holds no credential and calls no service.

    The one piece of this system that runs on the author's own machine, where
    the GitHub token, the npm token and the login keychain all live. It
    publishes by opening a browser at a form; it authenticates as nobody. Five
    legs: no HTTP client or credential store in the lockfile and no second
    path to `hyper`; no credential-shaped environment variable read outside
    `#[cfg(test)]`; `minice.ai` and `/plugins/v1` only in `src/panel.yaml`;
    no `Command::new` of `curl`, `wget` or `gh`, and `git ls-remote` spawned
    from one file; and an inventory of every remaining URL literal, which the
    first four legs are what make safe to call printed text.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Where `init-ci`'s own constants live. C24 reads the repository and the tag
#: out of the CLI rather than repeating them, so that moving `plugin-release/v1`
#: to `plugin-release/v2` moves this check too instead of leaving it green
#: against a tag nothing generates any more.
INIT_CI = ROOT / "astra-plugin-cli" / "src" / "commands" / "init_ci.rs"

EXEMPT = ROOT / "tools" / "check-registry-mirrors.exempt.yaml"

#: The two files that ARE the rule. Every scan below skips them.
#:
#: Neither is a copy of anything else: this one has to name the retired pin in
#: order to ban it, and the exemption list has to name each excused token in
#: order to excuse it. Scanning them makes the rule report on its own
#: definition — the ban reads as a violation of itself, and every exemption
#: matches its own literal, so the `min` counts that exist to notice a hole
#: closing are inflated by the record that describes the hole.
SELF = {
    "tools/check-registry-mirrors.py",
    "tools/check-registry-mirrors.exempt.yaml",
}

#: The pin the tag stopped pointing at on 2026-08-19. It is not enough to check
#: that documented SHAs equal the tag's commit: a page can name the retired pin
#: in a sentence that does not mention the tag at all, which is exactly how six
#: of the eighty-one lines read. So it is banned by name, everywhere.
RETIRED_PIN = "e3329df252a46d747676cb540ae4b986af68a3ad"

#: A 7-to-40 character lowercase hex run, not part of a longer hex word. The
#: floor of 7 is git's own abbreviation floor; below it a token is as likely to
#: be a word as a SHA.
HEX = re.compile(r"(?<![0-9a-fA-F])([0-9a-f]{7,40})(?![0-9a-fA-F])")

#: `uses: <owner>/<repo>/.github/workflows/plugin-release.yml@<sha>`.
CALLER = re.compile(r"plugin-release\.yml@([0-9a-fA-F]{7,40})")

#: Floors, each a MINIMUM: the rule is satisfied by more and broken by fewer,
#: because every one of these counts a set of COPIES that a careless edit
#: shrinks silently. Legs 1 to 3 only ever look at the SHAs that are there; a
#: page that loses its pin altogether passes all three, and these are what
#: notices.
#:
#: The first three are the real counts at the commit that added this file.
#: `FLOOR_DOCS_TOTAL` is deliberately not 7: the pin survives three times per
#: locale — two `output` transcripts and the `uses:` example — and a floor of
#: 7 is also what six deleted locales would leave.
FLOOR_CALLERS = 6          # .github/workflows/release-*.yml
FLOOR_DOCS_USES = 7        # the `uses:` example, one per locale
FLOOR_DOCS_TOTAL = 21      # every documented occurrence of the pinned commit

#: The odd one out, and it is a floor on the MACHINERY, not on the content:
#: the real total is 52 and would be a fourth copy of four numbers that already
#: live in the records' own `min` fields, where each is checked separately.
#: What this catches is the exemption scan not running at all — reading no
#: records, or matching against a path shape that stopped existing — which the
#: per-record checks cannot, because zero records means zero checks.
FLOOR_EXEMPT_MATCHES = 3


class Fails(list):
    """Failures, printed as they happen and summarised at the end.

    Same shape as `tools/check-locales.py`'s, deliberately: two files that
    report differently are two files a reader has to learn.
    """

    def check(self, ok: bool, msg: str, detail: str = "") -> bool:
        print(("ok    " if ok else "FAIL  ") + msg)
        if not ok:
            self.append(msg)
            for line in detail.splitlines():
                print("        " + line)
        return ok


# ── the exemption file ───────────────────────────────────────────────────────


def read_exemptions() -> list[dict[str, str]]:
    """`tools/check-registry-mirrors.exempt.yaml`, hand-parsed.

    The FORMAT paragraph in that file's own header is what this implements:
    blank-line separated records, one `key: value` per line, an INDENTED line
    continuing the key above it, `#` comments. No dependency, for the same
    reason `spec/locales.yaml` has none — the `couplings` job installs nothing,
    and a check that needs `pip install` is a check that stops running the
    first time a runner image changes.

    The continuation rule is here for `why` alone. Every reason in that file
    has to fit on one line without it, and a reason squeezed onto one line is
    a reason nobody writes and nobody reads — which would make the file a list
    of holes with no account of why each is open.
    """
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    last_key: str | None = None
    for n, raw in enumerate(EXEMPT.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if line.startswith("#"):
            continue
        if not line:
            if current:
                records.append(current)
                current = {}
            last_key = None
            continue
        if raw[:1] in (" ", "\t") and last_key:
            current[last_key] = (current[last_key] + " " + line).strip()
            continue
        if ":" not in line:
            raise SystemExit(f"{EXEMPT.name}:{n}: not `key: value`: {raw!r}")
        key, _, value = line.partition(":")
        last_key = key.strip()
        current[last_key] = value.strip()
    if current:
        records.append(current)
    for r in records:
        for required in ("id", "path", "token", "why"):
            if required not in r:
                raise SystemExit(f"{EXEMPT.name}: record {r} has no `{required}`")
        r.setdefault("min", "1")
    return records


def token_matches(found: str, literal: str) -> bool:
    """Is `found` the same SHA as `literal`, at whatever length each is written?

    Prefix in either direction: a paragraph may abbreviate, and an exemption
    written at full length must still cover the abbreviation of the same commit.
    """
    return found.startswith(literal) or literal.startswith(found)


# ── C24 ──────────────────────────────────────────────────────────────────────


def init_ci_const(name: str) -> str:
    text = INIT_CI.read_text(encoding="utf-8")
    m = re.search(rf'pub const {name}: &str = "([^"]+)";', text)
    if not m:
        raise SystemExit(
            f"{INIT_CI.relative_to(ROOT)} has no `pub const {name}`. C24 reads the "
            f"repository and the tag out of the CLI so the two cannot drift; if the "
            f"constant moved, move this with it rather than hard-coding the value."
        )
    return m.group(1)


def resolve_tag(fails: Fails, repo: str, tag: str) -> str | None:
    """The commit `<tag>` names on the remote, today.

    Asks for the ref AND its peeled form, which is what `init_ci.rs`'s
    `tag_refspecs` does, so that an annotated tag answers with the commit and
    not with its own object. Returns None after recording a failure — a rule
    about the remote does not get to pass when the remote did not answer.
    """
    url = f"https://github.com/{repo}.git"
    specs = [f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"]
    try:
        p = subprocess.run(
            ["git", "ls-remote", url, *specs],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as e:
        fails.check(False, f"C24 `git ls-remote {url} {tag}` ran", str(e))
        return None
    if p.returncode != 0:
        fails.check(
            False,
            f"C24 `git ls-remote {url} {tag}` ran",
            (p.stderr.strip() or f"exit {p.returncode}")
            + "\nC24 compares documented SHAs against the tag on the remote. With no"
            + "\nanswer there is nothing to compare, so this is a failure and not a skip.",
        )
        return None

    plain = peeled = None
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, name = parts
        if name.endswith("^{}"):
            peeled = sha
        else:
            plain = sha
    sha = peeled or plain
    if not sha:
        fails.check(
            False,
            f"C24 the tag {tag} exists on {repo}",
            "`git ls-remote` answered and returned no such ref. Every documented\n"
            "pin, and every author's generated `release.yml`, names a tag that is\n"
            "not there.",
        )
        return None

    kind = "annotated (peeled to its commit)" if peeled else "lightweight"
    print(f"note  {tag} on {repo} is {kind}, at {sha}")
    return sha


def scan_files() -> list[tuple[str, str]]:
    """Every tracked text file except this rule's own two, as (path, text)."""
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    out = []
    for rel in listed:
        if not rel or rel in SELF:
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            out.append((rel, p.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return out


def rule_C24(fails: Fails) -> None:
    repo = init_ci_const("WORKFLOW_REPO")
    tag = init_ci_const("WORKFLOW_TAG")
    sha = resolve_tag(fails, repo, tag)
    if sha is None:
        return

    exemptions = read_exemptions()
    hits: dict[str, int] = {e["id"]: 0 for e in exemptions}

    def exemption_for(path: str, token: str) -> dict[str, str] | None:
        for e in exemptions:
            if not fnmatch.fnmatch(path, e["path"]):
                continue
            if e["token"] != "*" and not token_matches(token, e["token"]):
                continue
            hits[e["id"]] += 1
            return e
        return None

    files = scan_files()

    # ── leg 1: every caller's pin is the tag's commit ────────────────────────
    callers = 0
    bad: list[str] = []
    for path, text in files:
        for n, line in enumerate(text.splitlines(), 1):
            for m in CALLER.finditer(line):
                found = m.group(1).lower()
                if exemption_for(path, found):
                    continue
                if path.startswith(".github/workflows/release-"):
                    callers += 1
                if not sha.startswith(found):
                    bad.append(f"{path}:{n}: @{found}")
    fails.check(
        not bad,
        f"C24 every `plugin-release.yml@<sha>` names {tag}'s commit",
        "\n".join(bad[:20])
        + (f"\n… and {len(bad) - 20} more" if len(bad) > 20 else "")
        + f"\n{tag} is at {sha}. A caller pinned to anything else fails in the"
        + "\nauthor's repository with `invalid value workflow reference`, before a job"
        + "\nopens. Re-run `astra-plugin init-ci`, or fix the literal.",
    )

    # ── leg 2: any SHA in a paragraph that names the tag is the tag's ────────
    # Paragraph, not line: the transcript in the docs prints the pin on a line
    # of its own and the tag name beside it, and the prose around a `uses:`
    # example names the tag one sentence away from the SHA it is talking about.
    wrong: list[str] = []
    for path, text in files:
        offset = 1
        for para in re.split(r"\n[ \t]*\n", text):
            if tag in para or "plugin-release.yml@" in para:
                for found in dict.fromkeys(HEX.findall(para)):
                    if sha.startswith(found):
                        continue
                    if exemption_for(path, found):
                        continue
                    wrong.append(f"{path}:~{offset}: {found}")
            offset += para.count("\n") + 2
    fails.check(
        not wrong,
        f"C24 every SHA written beside the name `{tag}` is that tag's commit",
        "\n".join(wrong[:20])
        + (f"\n… and {len(wrong) - 20} more" if len(wrong) > 20 else "")
        + f"\n{tag} is at {sha}. Every one of these is a number a reader is invited"
        + "\nto compare their own build against. If one is deliberately not the tag's"
        + f"\ncommit — a historical SHA, a fixture — give it a record in"
        + f"\n{EXEMPT.relative_to(ROOT)} with the reason.",
    )

    # ── leg 3: the retired pin is gone, everywhere ───────────────────────────
    retired: list[str] = []
    for path, text in files:
        for n, line in enumerate(text.splitlines(), 1):
            for found in HEX.findall(line):
                if token_matches(found, RETIRED_PIN):
                    retired.append(f"{path}:{n}")
    n_files = len({r.rsplit(":", 1)[0] for r in retired})
    fails.check(
        not retired,
        f"C24 the retired pin {RETIRED_PIN[:7]}… appears nowhere",
        f"{len(retired)} line(s) in {n_files} file(s):\n"
        + "\n".join(retired[:20])
        + (f"\n… and {len(retired) - 20} more" if len(retired) > 20 else "")
        + f"\nThat commit was {tag} until 2026-08-19 and is not what it points at now."
        + "\nA reader told to compare their build against it is told to distrust a"
        + "\ncorrect build and to trust a stale one.",
    )

    # ── the floors ───────────────────────────────────────────────────────────
    docs_uses = sum(
        1
        for path, text in files
        if path.startswith("docs/")
        for line in text.splitlines()
        for m in CALLER.finditer(line)
        if sha.startswith(m.group(1).lower())
    )
    docs_total = sum(
        text.count(sha) for path, text in files if path.startswith("docs/")
    )
    fails.check(
        callers >= FLOOR_CALLERS,
        f"C24 floor: {callers} caller workflow(s) pin the tag (>= {FLOOR_CALLERS})",
        "This repository releases its own example plugins through the same reusable\n"
        "workflow authors use, which is the only place it is exercised end to end.\n"
        "Fewer callers than this means one stopped being checked, not that one was\n"
        "fixed.",
    )
    fails.check(
        docs_uses >= FLOOR_DOCS_USES,
        f"C24 floor: {docs_uses} documented `uses:` example(s) (>= {FLOOR_DOCS_USES})",
        "One per locale. A locale whose example lost its pin teaches an author to\n"
        "write a workflow reference with no SHA in it.",
    )
    fails.check(
        docs_total >= FLOOR_DOCS_TOTAL,
        f"C24 floor: {docs_total} documented occurrence(s) of the pin "
        f"(>= {FLOOR_DOCS_TOTAL})",
        "The transcripts and the example, in seven locales. This floor is what\n"
        "notices a locale quietly losing the number the page tells the reader to\n"
        "compare against.",
    )

    for e in exemptions:
        want = int(e["min"])
        fails.check(
            hits[e["id"]] >= want,
            f"C24 exemption `{e['id']}` matched {hits[e['id']]} (>= {want})",
            f"{e['why']}\nAn exemption that matches nothing is either a hole left open\n"
            "after the thing it excused was removed, or a rule that stopped scanning\n"
            "what it thinks it scans. Both are worth a red build.",
        )
    total = sum(hits.values())
    fails.check(
        total >= FLOOR_EXEMPT_MATCHES,
        f"C24 floor: {total} exempted occurrence(s) (>= {FLOOR_EXEMPT_MATCHES})",
    )


# ── C25 ──────────────────────────────────────────────────────────────────────

PLUGIN_RELEASE = ROOT / ".github" / "workflows" / "plugin-release.yml"

#: Every literal that would mean a release run talks to the plugins service,
#: with what each one is. The audience and the wake path are the recorded
#: values (contract 0.12.0, ID-32): a generated workflow could legally call
#: them, which is exactly why their absence has to be checked rather than
#: assumed.
SERVICE_LITERALS = [
    ("api.minice.ai", "the plugins service's host"),
    ("/plugins/v1", "the plugins service's path prefix"),
    ("https://api.minice.ai/plugins/v1/author", "the author audience (ID-32)"),
    ("author/wake", "`author.wake`'s path (ID-32)"),
    ("astra.plugins.author-wake", "the wake event name"),
    ("ACTIONS_ID_TOKEN_REQUEST_", "the pair an OIDC-authenticated call needs"),
]

#: Anything that fetches. `Invoke-WebRequest` is here because the build job
#: runs on windows-latest too, where it is the one that needs no install.
FETCHERS = re.compile(r"\b(curl|wget|Invoke-WebRequest|iwr)\b", re.IGNORECASE)

URL_HOST = re.compile(r"https?://([A-Za-z0-9._-]+)")

#: Hosts a release run may already reach, because Actions itself reaches them.
#: Everything else on a fetching line is a call this rule exists to refuse.
GITHUB_HOSTS = {
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "codeload.github.com",
    "ghcr.io",
    "uploads.github.com",
}

#: The jobs the reusable workflow has, and the reason the set is closed: the
#: three-way split IS the security property the docs sell — `plan` reads the
#: manifest with no token, `build` runs the author's code with no write token,
#: `publish` holds `contents: write` and runs nothing of the author's. A fourth
#: job is either a fourth trust boundary or the notify job DEC-3 defers.
RELEASE_JOBS = {"plan", "build", "publish"}
FLOOR_RELEASE_JOBS = 3


def generated_caller() -> str:
    """The template `astra-plugin init-ci` writes, read out of the CLI source.

    Not by running the CLI: the `couplings` job has no Rust toolchain, and a
    rule that only runs where a binary was built is a rule that stops running
    the day somebody reorders the jobs. The template is one raw string literal
    inside `render()`, so it is read as text — the same trick C24 uses on
    `WORKFLOW_REPO`, and it fails loudly rather than silently scanning nothing.
    """
    text = INIT_CI.read_text(encoding="utf-8")
    at = text.find("pub fn render(")
    if at < 0:
        raise SystemExit(
            f"{INIT_CI.relative_to(ROOT)} has no `pub fn render(`. C25 reads the "
            f"generated caller out of that function's raw string; if it moved or "
            f"was renamed, move this with it rather than dropping the check."
        )
    start = text.find('r#"', at)
    end = text.find('"#', start + 3) if start >= 0 else -1
    if start < 0 or end < 0:
        raise SystemExit(
            f"{INIT_CI.relative_to(ROOT)}: `render()` no longer starts with an "
            f'r#"…"# literal. C25 cannot read the generated caller, so it is not '
            f"checking it — which is a red build, not a pass."
        )
    return text[start + 3:end]


def top_level_jobs(text: str) -> list[str]:
    """`jobs:`' immediate keys, by indentation. No YAML dependency; see C24."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            inside = True
            continue
        if not inside:
            continue
        if line.strip() and not line[:1].isspace():
            break  # a new top-level key ended the block
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            out.append(m.group(1))
    return out


def rule_C25(fails: Fails) -> None:
    """No workflow here calls the plugins service — neither ours nor theirs.

    Two files, and the second is the one with reach. `plugin-release.yml` is
    a file in this repository that we can edit tomorrow; the caller
    `init-ci` generates is compiled into every author's repository and stays
    there, supported for twelve months after the first CLI release that stops
    emitting it (ID-73). A call added to the template is a call we are
    promising to keep answering for a year, for a wake the poll already
    provides.

    DEC-3 defers the notify job to the owner's renewal decision, so at launch
    there is no call at all — and FLOW-56, which says no service answer,
    refusal or outage may fail an author's release run, holds by construction
    rather than by care.

    WHEN A CALL IS ADDED, the same commit must: delete the clause below that
    it violates, set `continue-on-error: true` on the calling step AND its
    job, and add FLOW-56's test — the job run against a refusing endpoint and
    against an unreachable one, both green. Deleting the clause alone turns a
    checked promise into an unchecked one.
    """
    if not PLUGIN_RELEASE.is_file():
        fails.check(
            False,
            "C25 the reusable workflow is where this rule looks for it",
            f"{PLUGIN_RELEASE.relative_to(ROOT)} is not there. Every author's "
            f"release calls that path; if it moved, C0 and C25 both need moving.",
        )
        return

    release_text = PLUGIN_RELEASE.read_text(encoding="utf-8")
    subjects = [
        (str(PLUGIN_RELEASE.relative_to(ROOT)), release_text),
        (f"{INIT_CI.relative_to(ROOT)}::render()", generated_caller()),
    ]

    # ── leg 1: none of the service's own literals ────────────────────────────
    hits: list[str] = []
    for name, text in subjects:
        for n, line in enumerate(text.splitlines(), 1):
            for literal, what in SERVICE_LITERALS:
                if literal in line:
                    hits.append(f"{name}:{n}: {literal!r} — {what}")
    fails.check(
        not hits,
        "C25 neither workflow names the plugins service",
        "\n".join(hits)
        + "\nA generated workflow that calls the service is compiled into authors'"
        + "\nrepositories and supported for 12 months after the CLI stops emitting"
        + "\nit (ID-73). If this call is intended, read this rule's docstring: the"
        + "\nclause comes out, `continue-on-error` goes on the step and the job, and"
        + "\nFLOW-56's refusing-and-unreachable test lands in the same commit.",
    )

    # ── leg 2: nothing fetches from a host that is not GitHub's ──────────────
    fetched: list[str] = []
    for name, text in subjects:
        for n, line in enumerate(text.splitlines(), 1):
            if not FETCHERS.search(line):
                continue
            for host in URL_HOST.findall(line):
                if host in GITHUB_HOSTS or host.endswith(".github.com"):
                    continue
                fetched.append(f"{name}:{n}: fetches {host}")
    fails.check(
        not fetched,
        "C25 neither workflow fetches a non-GitHub host",
        "\n".join(fetched)
        + "\nA release run holds `contents: write`, `id-token: write` and"
        + "\n`attestations: write`. Anything it downloads runs inside those.",
    )

    # ── leg 3: the three-way split is still three ────────────────────────────
    jobs = top_level_jobs(release_text)
    fails.check(
        set(jobs) == RELEASE_JOBS and len(jobs) >= FLOOR_RELEASE_JOBS,
        f"C25 the reusable workflow's jobs are exactly {sorted(RELEASE_JOBS)}",
        f"read {jobs}\nThe split is the security property: `plan` holds no token,"
        + "\n`build` runs the author's code and cannot write, `publish` can write and"
        + "\nruns none of it. A job that is neither is a fourth trust boundary — and"
        + "\nthe notify job DEC-3 defers would arrive exactly here.",
    )


# ── C26 ──────────────────────────────────────────────────────────────────────

CLI = ROOT / "astra-plugin-cli"
CARGO_LOCK = CLI / "Cargo.lock"
CLI_SRC = CLI / "src"
PANEL = "src/panel.yaml"

#: Every crate whose presence would mean the CLI can speak HTTP, or hold a
#: secret on the user's behalf. `keyring` and `oauth2` are here for the second
#: reason: a CLI that can read the login keychain is a CLI that can be asked to.
HTTP_CRATES = {
    "reqwest", "ureq", "isahc", "curl", "curl-sys",
    "surf", "attohttpc", "oauth2", "keyring",
}

#: `hyper` IS in the tree, and legitimately: tonic's channel is how the CLI
#: drives a plugin over the loopback socket during `dev` and `test`. The rule
#: is not "no hyper" — it is "no path to hyper except tonic's", because the day
#: something else pulls it in is the day an HTTP client arrived by accident.
HYPER_VIA = {"tonic", "hyper-util", "hyper-timeout"}

#: An environment variable whose name looks like a credential.
CREDENTIAL_ENV = re.compile(r"TOKEN|GH_|GITHUB_TOKEN|ACTIONS_ID_TOKEN|MINICE")

ENV_READ = re.compile(r"env::var(?:_os)?\(\s*(\"[^\"]*\"|[A-Za-z_][A-Za-z0-9_]*)\s*\)")
STR_CONST = re.compile(r'const\s+([A-Z_][A-Z0-9_]*)\s*:\s*&str\s*=\s*"([^"]*)"')

#: What it reads at the commit that wrote this rule. A FLOOR, not a list: a
#: fourth variable is somebody's business to justify, but finding zero means
#: the scan broke, and a scan that finds nothing agrees with every rule here.
FLOOR_ENV_READS = 3

SPAWN = re.compile(r'Command::new\(\s*"([^"]+)"')

#: Spawning one of these is how a program with no HTTP client makes an HTTP
#: request anyway, and `gh` is how it borrows a credential it never stored.
BANNED_SPAWN = {"curl", "wget", "gh", "Invoke-WebRequest"}

URL_LITERAL = re.compile(r"https?://([A-Za-z0-9._-]+)")

FLOOR_URL_LITERALS = 5


def strip_cfg_test(text: str) -> str:
    """`text` with every `#[cfg(test)]` item removed, by brace matching.

    Crude on purpose. The question a rule about credentials asks is "does the
    SHIPPED binary do this", and `#[cfg(test)]` is the line between shipped and
    not. A test that spawns `curl` against a local fixture is not the failure
    this rule is about; the same line in `publish.rs` is.
    """
    out = []
    i = 0
    while True:
        at = text.find("#[cfg(test)]", i)
        if at < 0:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:at])
        brace = text.find("{", at)
        if brace < 0:
            return "".join(out)
        depth, j = 0, brace
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1


def cli_sources() -> list[tuple[str, str]]:
    """Every `astra-plugin-cli/src/**/*.rs`, test modules removed."""
    out = []
    for p in sorted(CLI_SRC.rglob("*.rs")):
        rel = p.relative_to(CLI).as_posix()
        out.append((rel, strip_cfg_test(p.read_text(encoding="utf-8"))))
    if not out:
        raise SystemExit(
            f"C26 found no .rs under {CLI_SRC.relative_to(ROOT)}. The scan is "
            f"broken, and a broken scan agrees with every clause below."
        )
    return out


def lock_packages() -> dict[str, list[str]]:
    """`Cargo.lock` as {package: [dependency names]}. Hand-parsed; see C24."""
    if not CARGO_LOCK.is_file():
        raise SystemExit(
            f"C26 has no {CARGO_LOCK.relative_to(ROOT)} to read. The CLI is "
            f"installed with `--locked`, so a missing lockfile is its own bug."
        )
    graph: dict[str, list[str]] = {}
    name = None
    in_deps = False
    for raw in CARGO_LOCK.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "[[package]]":
            name, in_deps = None, False
            continue
        if line.startswith("name = "):
            name = line.split("=", 1)[1].strip().strip('"')
            graph.setdefault(name, [])
            continue
        if line == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if line == "]":
                in_deps = False
            elif name:
                graph[name].append(line.strip().strip(",").strip('"').split()[0])
    return graph


def rule_C26(fails: Fails) -> None:
    """The CLI holds no credential and calls no service.

    ROLL-34's Check, and the reason it is a Check rather than a sentence: the
    CLI is the one piece of this system that runs on the author's own machine,
    where the GitHub token, the npm token and the login keychain all are. It
    publishes by opening a browser at a form; it never authenticates as
    anybody. Nothing enforces that but this.

    THE FIRST LEG DEVIATES from the plan, deliberately. The plan says
    `cargo tree -e normal`; this reads `Cargo.lock`. Two reasons. The
    `couplings` job has no Rust toolchain, no registry cache and no reason to
    grow either, and a rule that only runs where cargo happens to be installed
    is a rule that stops running. And the lockfile is STRICTER: it cannot
    exclude dev- and build-dependencies, so an HTTP client vendored for a test
    fixture goes red here where `-e normal` would pass it. That is the right
    default for this list — if one of these nine ever has an honest
    dev-dependency reason, the argument belongs in this docstring and in the
    commit that adds it, not in a check that could not see it.
    """
    # ── leg 1: no HTTP client is linked in, and hyper arrives only via tonic ─
    graph = lock_packages()
    present = sorted(HTTP_CRATES & set(graph))
    fails.check(
        not present,
        f"C26 no HTTP client or credential store in {CARGO_LOCK.relative_to(ROOT)}",
        f"found {present}\nThe CLI speaks gRPC to a plugin on the loopback and "
        f"nothing else. An HTTP\nclient in this tree is either a call to a "
        f"service or the ability to make one.\nRead `rule_C26`'s docstring: this "
        f"leg reads the lockfile, so it sees dev- and\nbuild-dependencies too.",
    )
    parents = sorted(p for p, deps in graph.items() if "hyper" in deps)
    fails.check(
        "hyper" not in graph or set(parents) <= HYPER_VIA,
        f"C26 hyper is reached only through {sorted(HYPER_VIA)}",
        f"reached from {parents}\nhyper is here for tonic's channel, which "
        f"talks to a plugin on 127.0.0.1. A\nsecond path to it is an HTTP client "
        f"that arrived without anybody deciding to\nadd one.",
    )

    sources = cli_sources()
    consts = {}
    for _, text in sources:
        consts.update(dict(STR_CONST.findall(text)))

    # ── leg 2: no credential-shaped environment variable is read ────────────
    read_names: list[tuple[str, int, str]] = []
    for rel, text in sources:
        for n, line in enumerate(text.splitlines(), 1):
            for m in ENV_READ.finditer(line):
                tok = m.group(1)
                name = tok[1:-1] if tok.startswith('"') else consts.get(tok, tok)
                read_names.append((rel, n, name))
    credentials = [
        f"{rel}:{n}: {name}" for rel, n, name in read_names
        if CREDENTIAL_ENV.search(name)
    ]
    fails.check(
        not credentials,
        "C26 the CLI reads no credential-shaped environment variable",
        "\n".join(credentials)
        + "\nA CLI that reads GITHUB_TOKEN is a CLI that can act as the author,"
        + "\nand `publish` deliberately cannot: it opens a form in a browser.",
    )
    fails.check(
        len(read_names) >= FLOOR_ENV_READS,
        f"C26 floor: {len(read_names)} environment read(s) found "
        f"(>= {FLOOR_ENV_READS})",
        "At the commit that wrote this rule the CLI reads RUST_LOG, USERNAME and\n"
        "ASTRA_PLUGIN_WORKFLOW_SHA. Finding fewer than three means the SCAN broke,\n"
        "and a broken scan agrees with the clause above.",
    )

    # ── leg 3: the service's host and path are nowhere in the CLI ───────────
    # `.rs` comes from `sources`, so the test that ASSERTS these strings are
    # absent is not itself the thing that fails — the same reason C24 does not
    # scan its own definition. Everything else under `src/` is read raw.
    service_subjects = list(sources)
    for p in sorted(CLI_SRC.rglob("*")):
        rel = p.relative_to(CLI).as_posix()
        if not p.is_file() or p.suffix == ".rs" or rel == PANEL:
            continue  # PANEL is AP-8's panel constant, the one allowed site
        try:
            service_subjects.append((rel, p.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    service: list[str] = []
    for rel, text in service_subjects:
        for n, line in enumerate(text.splitlines(), 1):
            for lit in ("minice.ai", "/plugins/v1"):
                if lit in line:
                    service.append(f"{rel}:{n}: {lit}")
    fails.check(
        not service,
        f"C26 `minice.ai` and `/plugins/v1` appear only in {PANEL}",
        "\n".join(service)
        + f"\nThe only address of the service the CLI may carry is the panel URL"
        + f"\nAP-8 puts in {PANEL} — a link it prints for a human to open, not an"
        + "\nendpoint it calls. Anywhere else is a call, or the start of one.",
    )

    # ── leg 4: the only process it spawns that leaves the machine is git ────
    spawned: dict[str, list[str]] = {}
    for rel, text in sources:
        for n, line in enumerate(text.splitlines(), 1):
            for m in SPAWN.finditer(line):
                spawned.setdefault(m.group(1), []).append(f"{rel}:{n}")
    banned = sorted(
        f"{where}: Command::new({prog!r})"
        for prog, wheres in spawned.items() if prog in BANNED_SPAWN
        for where in wheres
    )
    fails.check(
        not banned,
        f"C26 the CLI spawns none of {sorted(BANNED_SPAWN)}",
        "\n".join(banned)
        + "\nThis is how a program with no HTTP client makes an HTTP request"
        + "\nanyway, and `gh` is how it borrows a credential it never stored.",
    )
    ls_remote = sorted(
        rel for rel, text in sources if '"ls-remote"' in text
    )
    fails.check(
        ls_remote == ["src/commands/init_ci.rs"],
        "C26 `git ls-remote` is spawned from init_ci.rs and nowhere else",
        f"found in {ls_remote}\nResolving the workflow tag is the ONE thing the "
        f"CLI does that leaves the\nmachine. A second caller is a second network "
        f"path, and the next one after\nthat is the one that carries a token.",
    )

    # ── leg 5: every other URL literal is text the CLI prints ───────────────
    #
    # It cannot be anything else, and that is established above rather than
    # here: leg 1 says there is no HTTP client to fetch with, leg 4 says there
    # is no fetching process to spawn. So this leg does not re-prove it — it
    # takes the inventory, so that "they are all printed text" is a list a
    # reader can check rather than a claim they have to take.
    hosts: dict[str, list[str]] = {}
    reachable: list[str] = []
    for rel, text in sources:
        for n, line in enumerate(text.splitlines(), 1):
            for host in URL_LITERAL.findall(line):
                host = host.rstrip(".")  # a URL at the end of an English sentence
                hosts.setdefault(host, []).append(f"{rel}:{n}")
                if SPAWN.search(line) or FETCHERS.search(line):
                    reachable.append(f"{rel}:{n}: {host}")
    fails.check(
        not reachable,
        "C26 no URL literal sits on a line that spawns or fetches",
        "\n".join(reachable),
    )
    fails.check(
        len(hosts) >= FLOOR_URL_LITERALS,
        f"C26 floor: {len(hosts)} distinct URL host(s) inventoried "
        f"(>= {FLOOR_URL_LITERALS})",
        "Finding almost none means the scan broke, not that the CLI got quieter.",
    )
    for host in sorted(hosts):
        print(f"note  C26 URL literal, printed not fetched: {host} "
              f"({len(hosts[host])} site(s))")


RULES = {"C24": rule_C24, "C25": rule_C25, "C26": rule_C26}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--rules",
        default=",".join(RULES),
        help="comma-separated rule ids (default: all of " + ", ".join(RULES) + ")",
    )
    args = ap.parse_args()

    wanted = [r.strip() for r in args.rules.split(",") if r.strip()]
    unknown = [r for r in wanted if r not in RULES]
    if unknown:
        print(f"check-registry-mirrors: no such rule: {', '.join(unknown)}", file=sys.stderr)
        return 2

    fails = Fails()
    for r in wanted:
        RULES[r](fails)

    print()
    if fails:
        print(f"check-registry-mirrors: {len(fails)} broken:\n", file=sys.stderr)
        for f in fails:
            print("  " + f, file=sys.stderr)
        return 1
    print(f"check-registry-mirrors: {', '.join(wanted)} pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
