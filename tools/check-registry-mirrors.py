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

C27 — `spec/reserved-ids.yaml` is astra-registry's reserved-id policy, still.

    The ids nobody may list under are a security list in another repository,
    and this one now carries a copy so that `astra-plugin check` can refuse a
    name before the author pushes the tag that makes the refusal expensive. A
    copy nobody compares is a guess, and this guess is wrong in both
    directions: too few names and the CLI blesses an id ingest will refuse,
    too many and it refuses one the registry would have taken — which reads,
    to the author, as the tool being broken, because it is.

    Three legs, answering three different questions.

      * IN-REPO. The file parses, every value names the upstream it mirrors,
        and the vendored copy in `astra-plugin-cli/src/` is byte-identical to
        the spec. Needs no checkout, so it is the leg that really runs in the
        `couplings` job. WHICH names are reserved is asserted by name in
        `the_reserved_ids_are_the_ones_the_spec_declares`, in the CLI's own
        suite, and against the registry below; a third enumeration here would
        be a third place a released name has to be remembered, which is how a
        list comes to have one stale copy. Nor is HOW MANY: this leg's floors
        say only that the lists are not empty, because a floor set to the
        number of names reserved today is that same third copy wearing
        arithmetic, and it goes red on the day the registry releases one.

      * PINNED. The header names `astra-registry@<sha>`. With a checkout, the
        copy has to be what that commit really held — the leg that says the
        mirror was taken honestly rather than typed from memory.

      * HEAD. The same comparison against the registry as it stands now. This
        is the leg that goes red when the policy moves, and the PAIR is what
        makes a red readable: head red with pinned green means the registry
        changed and the mirror is stale; both red means somebody edited the
        copy. The repair is never symmetric — astra-registry owns these names,
        a name added here reserves nothing, and a name dropped here only stops
        warning an author about a refusal they will meet anyway.

    With no checkout the last two print what they took on trust and record
    themselves as UNVERIFIED, the way C20 does in `tools/check-locales.py`.
    That is not the choice C24 makes — C24 fails when the remote will not
    answer — and the difference is deliberate: C24 asks about a public remote
    every job can reach, this one needs a working copy of another repository
    beside this one, which CI has never had.

C31 — `testdata/binding-line/` is astra-registry's binding-line corpus, still.

    Thirty-one files a stranger could commit to `.well-known/astra-plugin-owner`
    with the outcome ID-23 and ID-24 require, so that the bot, the CLI and the
    plugins service are measured against one fact instead of three separate
    self-agreements. `astra-registry:tests/binding-line/vectors.json` is
    canonical; this repository holds a copy, because the CLI's reader and writer
    (`astra-plugin-cli/src/binding.rs`, plan task AP-8) are tested against it
    and a suite whose fixtures live in a repository CI never clones is a suite
    that silently skips and passes forever.

    A copy of a corpus is the coupling this estate has already paid for several
    times: two files in two repositories that are supposed to be the same bytes,
    with nothing comparing them. What is different here is that the registry
    ships `SHA256SUMS` beside the corpus, and that file is small enough to
    travel — so the comparison exists even where the other repository does not.

    Four legs.

      * IN-REPO. `vectors.json` hashes to the digest in the vendored
        `SHA256SUMS`, which is byte-identical to the registry's; the provenance
        block in `README.md` names the same digest and a 40-hex registry commit;
        and the file still parses to a corpus. **This is a real comparison
        against a registry-authored artifact, and it needs no checkout and no
        network** — which is why it is the leg that actually runs in the
        `couplings` job. What it cannot see is whether `SHA256SUMS` is itself
        the registry's.

      * SWEEP. `tools/vendor-testdata.sh` copies `testdata/bundles` OUT to the
        daemon and to the registry, and sweeps each destination with `rm -f`,
        deleting everything the bundle corpus's own file list does not name.
        This corpus travels the other way and is not in that list, so the day
        it becomes one of that script's destinations is the day a vendor run
        deletes it — quietly, between two green test runs, because nothing
        would then read the file the CLI suite iterates. So the script's source
        and destinations are re-read here rather than remembered. astra-registry
        holds the mirror image of this guard: `bot/tests/binding.test.mjs`
        asserts that `tests/vectors/` — which the sweep does own — holds no
        subdirectory.

      * PINNED. These bytes are what `astra-registry@<sha>` really held. The
        leg that says the copy was taken rather than typed.

      * HEAD. The same bytes against the registry as it stands now. Head red
        with pinned green means upstream moved and this copy is stale; both red
        means somebody edited this one. The repair is never symmetric: a case
        added here proves nothing, and a case removed here only stops this
        repository noticing a disagreement it still has.

    The last two need a checkout and record themselves UNVERIFIED without one,
    exactly as C27 does. That notice is printed on every GREEN run, in the
    middle of a passing transcript, on purpose. A check that says "I did not
    compare the other side" every time it passes is cheaper, and more honest,
    than a verifier that cannot exist in the job where it would have to run.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
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

    #: What a rule declined to compare, as `(rule, why)`. A run that skipped
    #: something must not be able to end on the word "pass" alone — printing
    #: it once in the middle of the transcript, where nobody scrolls, is how a
    #: check that stopped comparing anything goes on reading as green. Carried
    #: from `tools/check-locales.py`, where C20 needs the same thing for the
    #: same reason.
    unverified: list[tuple[str, str]]

    def __init__(self) -> None:
        super().__init__()
        self.unverified = []

    def skip(self, rule: str, why: str) -> None:
        self.unverified.append((rule, why))

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


# ── C27 ──────────────────────────────────────────────────────────────────────

RESERVED_SPEC = ROOT / "spec" / "reserved-ids.yaml"
RESERVED_VENDORED = ROOT / "astra-plugin-cli" / "src" / "reserved-ids.yaml"

#: Floors on the MACHINERY, not on the content — the same distinction
#: `FLOOR_EXEMPT_MATCHES` above is written around, and here for a sharper
#: reason.
#:
#: These were 22 and 3, the real counts on 2026-09-19, after ID-66 narrowed
#: the panel names from sixteen to eight the same day. That is the one thing a
#: floor must never be. `reserved` shrinks whenever the registry RELEASES a
#: name back to authors — ID-66 did it to `search` and `sitemap`, and it is an
#: ordinary, argued, deliberate act — so a floor standing at the census goes
#: red the first time this mirror is updated CORRECTLY, naming a name somebody
#: released on purpose, while the pinned and head legs below, the only ones
#: that can tell a release from a deletion, both pass. Watched doing exactly
#: that against a registry clone with one name released. `validate.rs` carried
#: the same `>= 22` and no longer does: the three ids it names are its floor.
#:
#: What is left is the job a floor actually has, and C27 cannot hand it to the
#: names the way the cargo test can. This rule knows no names on purpose —
#: `the_reserved_ids_are_the_ones_the_spec_declares` names three ids and three
#: prefixes, the registry comparison below names any of them, and a third
#: enumeration here would be a third place a released name has to be
#: remembered. So a count is all that stands between "the file parsed" and
#: "the file parsed to nothing": `isinstance(ids, list)` is just as true of
#: `[]`, and in the `couplings` job, which has no registry checkout, the two
#: comparing legs do not run at all. An empty or truncated parse must not
#: reach `NOT VERIFIED` reading like a scan that looked and was happy.
#:
#: Hence: far below any census, and low enough that no narrowing the registry
#: could plausibly argue for reaches them. Three ids is what survives a
#: release of everything but the structural names. One prefix is the whole
#: floor the prefixes need, because all three of them are asserted BY NAME in
#: the CLI's own suite — a prefix dropped from both copies is caught there, by
#: name, which is the answer a reader can act on, and not by arithmetic here.
MIN_RESERVED_IDS = 3
MIN_RESERVED_PREFIXES = 1

#: `# mirrors: astra-registry/<path> <key>`, the convention
#: `spec/listing-limits.yaml` already uses. Read rather than hard-coded so that
#: a definition moving upstream moves this comparison with it, instead of
#: leaving it green against a file nothing reads any more.
MIRRORS = re.compile(r"#\s*mirrors:\s*astra-registry/(\S+)\s+(.+)$")

#: The provenance line in the spec file's header.
PINNED_AT = re.compile(r"astra-registry@([0-9a-f]{40})")


def read_reserved_spec() -> tuple[dict[str, object], dict[str, str], str | None]:
    """(name -> value, name -> the upstream its `mirrors:` comment names, pin).

    The format `spec/reserved-ids.yaml`'s own FORMAT paragraph promises, and
    the same hand-parse the CLI does in `validate.rs::reserved_ids`. No YAML
    dependency, for the reason that file states: the `couplings` job installs
    nothing.
    """
    values: dict[str, object] = {}
    sources: dict[str, str] = {}
    pin: str | None = None
    pending: str | None = None
    current: str | None = None
    for raw in RESERVED_SPEC.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            m = MIRRORS.match(line)
            if m:
                pending = f"{m.group(1)} {m.group(2).strip()}"
            elif pin is None:
                p = PINNED_AT.search(line)
                if p:
                    pin = p.group(1)
            continue
        if not line:
            continue
        if line.startswith("- "):
            if current and isinstance(values.get(current), list):
                values[current].append(line[2:].strip())  # type: ignore[union-attr]
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if not value:
            current = key
            values[key] = []
        else:
            current = None
            values[key] = value.strip('"')
        if pending:
            sources[key] = pending
            pending = None
    return values, sources, pin


def _registry_dir(anchor: str = "policy/reserved-ids.json") -> Path | None:
    """A working copy of astra-registry, or None.

    Same two candidates as `tools/check-locales.py`'s, and anchored on a file
    the CALLING rule actually reads: a directory that happens to be named
    astra-registry but holds no `policy/reserved-ids.json` is not a checkout
    C27 can compare against, and saying so is better than reporting every name
    as missing. C31 passes its own anchor for the same reason — a checkout
    parked on a branch that predates `tests/binding-line/` cannot answer its
    question either, and "no corpus there" is a sentence a reader can act on
    where "every case differs" is not.
    """
    env = os.environ.get("ASTRA_REGISTRY_DIR")
    candidates = [env] if env is not None else ["../astra-registry"]
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        if (p / anchor).is_file():
            return p
    return None


def _registry_text(registry: Path, rel: str, sha: str | None) -> str:
    """One upstream file, at `sha` or as the checkout stands.

    Raises `LookupError` with a sentence for the transcript rather than
    returning None: every caller's next move is to record a failure naming the
    file, and a rule that cannot read its own input has not passed.
    """
    if sha is None:
        path = registry / rel
        if not path.is_file():
            raise LookupError(f"{rel} is not in that checkout")
        return path.read_text(encoding="utf-8")
    p = subprocess.run(
        ["git", "-C", str(registry), "show", f"{sha}:{rel}"],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise LookupError(
            f"`git show {sha[:12]}:{rel}` failed: {p.stderr.strip() or p.returncode}\n"
            f"That commit is what spec/reserved-ids.yaml says this copy was taken from. A "
            f"shallow clone will not have it (`git fetch --unshallow`); a SHA that is in no "
            f"clone at all was never on a branch anybody can read, and the pin is fiction."
        )
    return p.stdout


def _upstream_value(registry: Path, source: str, sha: str | None):
    """Whatever `# mirrors: astra-registry/<path> <key>` names, upstream.

    Three shapes, because three is what this file mirrors, and anything else
    raises rather than guessing: a `mirrors:` line this cannot follow means
    the convention grew a fourth shape and nobody taught the comparison about
    it, which is a red build and not a pass.
    """
    rel, _, key = source.partition(" ")
    key = key.strip()
    text = _registry_text(registry, rel, sha)
    if rel.endswith(".json"):
        doc = json.loads(text)
        if key not in doc:
            raise LookupError(f"{rel} has no `{key}`")
        return doc[key]
    if key == "ID_PATTERN":
        m = re.search(r'export const ID_PATTERN = "([^"]+)";', text)
        if not m:
            raise LookupError(
                f"{rel} has no `export const ID_PATTERN = \"…\";`. The charset moved or was "
                f"renamed upstream; this side is hand-implementing a pattern that is no longer "
                f"the registry's."
            )
        return m.group(1)
    if key.startswith("invalidId"):
        # A rule rather than a value: the registry refuses `a--b` in
        # `invalidId`, outside the pattern. Matched as the literal predicate,
        # so a reword upstream is a red here — which is the right answer. A
        # reworded rule is one somebody has just touched, and this copy is
        # what decides whether an author hears about it before their tag.
        return 'includes("--")' in text
    raise LookupError(
        f"cannot follow `mirrors: astra-registry/{source}` — this rule knows a JSON key, "
        f"ID_PATTERN and invalidId's double-hyphen refusal, and nothing else"
    )


def _compare_against(fails: Fails, registry: Path, values, sources, sha: str | None) -> None:
    """One leg: every mirrored value against the registry, at `sha` or at head."""
    leg = f"pinned {sha[:12]}" if sha else "head"
    compared = 0
    problems: list[str] = []
    for name in sorted(values):
        source = sources.get(name)
        if source is None:
            continue  # the in-repo leg already failed this one
        try:
            theirs = _upstream_value(registry, source, sha)
        except (LookupError, json.JSONDecodeError) as e:
            problems.append(f"{name}: {e}")
            continue
        compared += 1
        ours = values[name]
        if isinstance(ours, list):
            # Membership, never order: the registry sorts `astra` first and
            # the rest alphabetically, and that is a convention for readable
            # diffs, not a policy. Reported as names, both ways round, because
            # "22 against 23" sends a reader counting instead of reading.
            missing = sorted(set(theirs) - set(ours))
            extra = sorted(set(ours) - set(theirs))
            if missing:
                problems.append(
                    f"{name}: astra-registry has {', '.join(missing)} and this mirror does not, "
                    f"so `astra-plugin check` tells an author those are theirs to publish under"
                )
            if extra:
                problems.append(
                    f"{name}: this mirror has {', '.join(extra)} and astra-registry does not, so "
                    f"`astra-plugin check` refuses an id the registry would have listed"
                )
        elif isinstance(theirs, bool):
            # A row that stands for a RULE being present upstream rather than
            # for a value — `refuse_double_hyphen`. The bool test comes first
            # because every scalar on this side is the string it was written
            # as, so `"true" != True` and the string branch below would have
            # reported the rule as drifted on a tree where it is fine. Watched
            # doing exactly that on the first run against a real checkout.
            if theirs != (ours == "true"):
                problems.append(
                    f"{name}: this file says {ours}, and astra-registry/{source} "
                    f"{'has' if theirs else 'no longer has'} that rule"
                )
        elif str(theirs) != str(ours):
            problems.append(f"{name}: we say {ours!r}, astra-registry/{source} says {theirs!r}")

    fails.check(
        compared >= 3 and not problems,
        f"C27 spec/reserved-ids.yaml is astra-registry's policy ({leg}, {compared} value(s))",
        "\n".join(problems) + "\n"
        "THE REGISTRY OWNS THESE NAMES. A name added here reserves nothing and a name dropped\n"
        "here only stops warning the author about a refusal they will meet at ingest anyway, so\n"
        "the repair is: change it in astra-registry, then copy policy/reserved-ids.json's\n"
        "`reserved` and `reserved_prefixes` into spec/reserved-ids.yaml, update the pinned SHA in\n"
        "its header, copy the file to astra-plugin-cli/src/reserved-ids.yaml, and run\n"
        "`cargo test --manifest-path astra-plugin-cli/Cargo.toml`.\n"
        "\n"
        "A name that vanished upstream may have been RELEASED on purpose — eight ordinary words\n"
        "were, on 2026-09-19. policy/reserved-ids.json's `reserved_note` is where that argument\n"
        "lives, and it is not copied here on purpose: a second copy of the reasoning is the copy\n"
        "that rots. Read it there before deciding which side is wrong.",
    )


def rule_C27(fails: Fails) -> None:
    # ── leg 0: the two copies in this repository ─────────────────────────────
    spec_text = RESERVED_SPEC.read_text(encoding="utf-8")
    vendored = (
        RESERVED_VENDORED.read_text(encoding="utf-8")
        if RESERVED_VENDORED.is_file()
        else None
    )
    fails.check(
        vendored == spec_text,
        "C27 astra-plugin-cli/src/reserved-ids.yaml is byte-identical to spec/reserved-ids.yaml",
        ("that file is not there" if vendored is None else "the two differ")
        + "\nThe spec file cannot be `include_str!`d from inside the crate — `cargo package`"
        + "\nrefuses a path outside the package directory — so the CLI carries a vendored copy,"
        + "\nand the copy is what ships to authors. The spec file is the list; copy it over."
        + "\n`cargo test --manifest-path astra-plugin-cli/Cargo.toml` says the same thing, and"
        + "\nthis job has no Rust toolchain, which is why it is also said here.",
    )

    values, sources, pin = read_reserved_spec()
    ids = values.get("reserved")
    prefixes = values.get("reserved_prefixes")
    fails.check(
        isinstance(ids, list) and isinstance(prefixes, list),
        "C27 spec/reserved-ids.yaml parses to two lists",
        f"reserved={type(ids).__name__}, reserved_prefixes={type(prefixes).__name__}\n"
        "That file's FORMAT paragraph promises `key:` and `  - item` lines. If it still looks\n"
        "like that, THIS READER is what broke and nothing is unreserved; if it does not, the CLI's\n"
        "own parser in validate.rs is reading the same file and has the same problem — and a\n"
        "reserved list that parses to nothing reserves nothing.",
    )
    if not isinstance(ids, list) or not isinstance(prefixes, list):
        return

    fails.check(
        len(ids) >= MIN_RESERVED_IDS,
        f"C27 floor: {len(ids)} reserved id(s) (>= {MIN_RESERVED_IDS})",
        "This floor is not a count of the policy and must never be set to one — see the comment\n"
        "on MIN_RESERVED_IDS. It is here so that a `reserved:` block that parsed to nothing, or\n"
        "to the first two lines of itself, cannot reach the NOT VERIFIED notice below reading\n"
        "like a scan that looked and was happy. Under it, the question is not WHICH name went:\n"
        "it is whether this file still says what its FORMAT paragraph promises and whether\n"
        "`read_reserved_spec` still reads it. If both are fine and the list really is this\n"
        "short, the registry has released nearly everything and that is a conversation, not a\n"
        "red build. WHICH name is a question for the two legs below and for\n"
        "`cargo test -p astra-plugin-cli`, which name three of them.",
    )
    fails.check(
        len(prefixes) >= MIN_RESERVED_PREFIXES,
        f"C27 floor: {len(prefixes)} reserved prefix(es) (>= {MIN_RESERVED_PREFIXES})",
        "Empty. `reserved_prefixes:` is the block that parsed to nothing, so nothing on this\n"
        "side warns an author about `astra-`, `official-` or `verified-` any more. Which of the\n"
        "three it is, if it is not all of them, is what the CLI's own suite says by name.",
    )
    unsourced = sorted(n for n in values if n not in sources)
    fails.check(
        not unsourced,
        "C27 every mirrored value names the upstream it copies",
        f"no `# mirrors:` line above: {unsourced}\n"
        "A copy that does not say what it is a copy OF is a copy nothing can compare, which is\n"
        "how a local decision comes to read as an echo of somebody else's policy.",
    )
    fails.check(
        pin is not None,
        "C27 spec/reserved-ids.yaml names the commit it was taken from",
        "no `astra-registry@<40-hex>` in the header. The pinned leg has nothing to compare\n"
        "against, so provenance becomes a claim rather than a check.",
    )

    # ── legs 1 and 2: pinned, and head ───────────────────────────────────────
    registry = _registry_dir()
    if registry is None:
        print("C27 NOT VERIFIED: no astra-registry checkout at "
              "$ASTRA_REGISTRY_DIR or ../astra-registry.")
        print(f"        {len(ids)} reserved id(s) taken on trust: {' '.join(sorted(ids))}")
        print(f"        {len(prefixes)} reserved prefix(es): {' '.join(sorted(prefixes))}")
        print(f"        id_pattern: {values.get('id_pattern')}")
        print("        A name missing from that list is one `astra-plugin check` tells an author")
        print("        they may publish under, and the refusal arrives at ingest, in a repository")
        print("        they have never opened, after the tag. A name too many is a refusal here")
        print("        for a listing the registry would have taken. Neither is visible from this")
        print("        side alone — and neither is the question of whether the registry has")
        print("        reserved something new since the pin.")
        fails.skip("C27", "no astra-registry checkout")
        return

    if pin is not None:
        _compare_against(fails, registry, values, sources, pin)
    _compare_against(fails, registry, values, sources, None)


# ── C31 ──────────────────────────────────────────────────────────────────────

BINDING_DIR = ROOT / "testdata" / "binding-line"
BINDING_VECTORS = BINDING_DIR / "vectors.json"
BINDING_SUMS = BINDING_DIR / "SHA256SUMS"
BINDING_README = BINDING_DIR / "README.md"

VENDOR_SCRIPT = ROOT / "tools" / "vendor-testdata.sh"

#: `mirrors:  astra-registry@<40-hex>:<path>` in the corpus README's provenance
#: block. The upstream PATH is read rather than hard-coded, the way C27 reads
#: its `# mirrors:` comments, so that a corpus moving upstream moves this
#: comparison with it instead of leaving it green against a file nothing reads.
BINDING_PIN = re.compile(r"astra-registry@([0-9a-f]{40}):(\S+)")

#: `sha256:   <64-hex>  <name>` in the same block, and the one line of
#: `SHA256SUMS`. Two spellings of one fact, in two files, so that neither can be
#: moved alone — a pin updated without its digest is a pin that says the copy
#: came from somewhere it did not.
BINDING_DIGEST = re.compile(r"^[ \t]*sha256:[ \t]+([0-9a-f]{64})[ \t]+(\S+)[ \t]*$", re.M)
SUMS_LINE = re.compile(r"^([0-9a-f]{64})[ \t]+\*?(\S+)$")

#: A floor on the MACHINERY, not on the corpus — the same distinction
#: `MIN_RESERVED_IDS` is written around, and the reasoning transfers exactly.
#:
#: The census is 31 cases over 25 vector numbers, and it is written down twice
#: already: in `vectors.json`'s own `floors` member, and by name in
#: `astra-registry:bot/tests/binding.test.mjs`, which asserts it before it
#: parses a case. A third copy here would be a third place a corpus that grows
#: has to be remembered, and it would go red the first time this mirror is
#: updated CORRECTLY.
#:
#: What is left is the job a floor actually has. The digest leg above already
#: catches a truncated or edited file, so this one is not about the bytes: it is
#: about THIS READER still reading them. `isinstance(cases, list)` is just as
#: true of `[]`, and in the `couplings` job the two comparing legs do not run at
#: all, so a parse that produced nothing must not reach the NOT VERIFIED notice
#: looking like a scan that looked and was happy.
MIN_BINDING_CASES = 3


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sums_entries(text: str) -> dict[str, str]:
    """`SHA256SUMS` as {name: digest}, in `sha256sum`'s own format."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = SUMS_LINE.match(line)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def _registry_blob(registry: Path, rel: str, sha: str | None) -> bytes:
    """One upstream file's BYTES, at `sha` or as the checkout stands.

    Bytes and not text, unlike `_registry_text`: this is a fixture whose whole
    value is that both sides hold the same octets, and a corpus compared after
    a decode is a corpus that agrees about a BOM it may not agree about. Raises
    `LookupError` with a sentence for the transcript, for the same reason.
    """
    if sha is None:
        path = registry / rel
        if not path.is_file():
            raise LookupError(
                f"{rel} is not in that checkout. It is a working copy of astra-registry, so "
                f"either it is parked on a branch that predates the corpus, or the corpus moved "
                f"and this side's provenance line still names the old path."
            )
        return path.read_bytes()
    p = subprocess.run(
        ["git", "-C", str(registry), "show", f"{sha}:{rel}"],
        capture_output=True,
    )
    if p.returncode != 0:
        raise LookupError(
            f"`git show {sha[:12]}:{rel}` failed: "
            f"{p.stderr.decode('utf-8', 'replace').strip() or p.returncode}\n"
            f"That commit is what testdata/binding-line/README.md says this copy was taken from. "
            f"A shallow clone will not have it (`git fetch --unshallow`); a SHA that is in no "
            f"clone at all was never on a branch anybody can read, and the pin is fiction."
        )
    return p.stdout


def _binding_compare(fails: Fails, registry: Path, rel: str, sha: str | None) -> None:
    """One leg: the vendored corpus against the registry, at `sha` or at head."""
    leg = f"pinned {sha[:12]}" if sha else "head"
    sums_rel = rel.rsplit("/", 1)[0] + "/SHA256SUMS"
    problems: list[str] = []
    for ours_path, upstream_rel in ((BINDING_VECTORS, rel), (BINDING_SUMS, sums_rel)):
        try:
            theirs = _registry_blob(registry, upstream_rel, sha)
        except LookupError as e:
            problems.append(f"{upstream_rel}: {e}")
            continue
        ours = ours_path.read_bytes()
        if ours != theirs:
            problems.append(
                f"{ours_path.relative_to(ROOT)} is {len(ours)} byte(s) hashing to "
                f"{_sha256(ours)[:16]}…; astra-registry/{upstream_rel} is {len(theirs)} byte(s) "
                f"hashing to {_sha256(theirs)[:16]}…"
            )

    fails.check(
        not problems,
        f"C31 testdata/binding-line is astra-registry's corpus, byte for byte ({leg})",
        "\n".join(problems) + "\n"
        "THE REGISTRY OWNS THIS CORPUS (plan B-T2.4). A case added here proves nothing and a\n"
        "case removed here only stops this repository noticing a disagreement it still has, so\n"
        "the repair is: change `tests/binding-line/generate.mjs` in astra-registry and run it,\n"
        "then copy `vectors.json` AND `SHA256SUMS` into testdata/binding-line/ and move both\n"
        "lines of README.md's provenance block.\n"
        "\n"
        "HEAD red with PINNED green is the ordinary case and means upstream moved: this copy is\n"
        "stale, and nothing here was edited. Both red means this copy was edited. The corpus's\n"
        "own README upstream is where the argument for each case lives, and it is deliberately\n"
        "not duplicated here — read it there before deciding which side is wrong.",
    )


def rule_C31(fails: Fails) -> None:
    # ── leg 0: the copy agrees with the digest that travelled with it ────────
    missing = [
        str(p.relative_to(ROOT))
        for p in (BINDING_VECTORS, BINDING_SUMS, BINDING_README)
        if not p.is_file()
    ]
    if not fails.check(
        not missing,
        "C31 the vendored binding-line corpus is present",
        f"not there: {missing}\n"
        "`astra-plugin-cli/src/binding.rs` (AP-8) is tested against this corpus. A suite whose\n"
        "fixtures are missing is a suite that skips quietly and passes for ever, which is the\n"
        "failure `tools/vendor-testdata.sh`'s header is written around. Take the files from\n"
        "astra-registry:tests/binding-line/ — vectors.json and SHA256SUMS, unmodified.",
    ):
        return

    sums_text = BINDING_SUMS.read_text(encoding="utf-8")
    entries = _sums_entries(sums_text)
    if not fails.check(
        list(entries) == ["vectors.json"],
        "C31 SHA256SUMS covers vectors.json and nothing else",
        f"it names {sorted(entries) or 'nothing'}\n"
        "Upstream's SHA256SUMS covers one file on purpose: the READMEs on the two sides differ,\n"
        "because this one names the registry commit the copy was taken from, and a sums file\n"
        "covering prose would make that provenance line impossible to write honestly. A sums\n"
        "file that has grown or lost an entry is not the registry's file any more, and the two\n"
        "legs below are what say which side changed.",
    ):
        return

    vectors_bytes = BINDING_VECTORS.read_bytes()
    actual = _sha256(vectors_bytes)
    fails.check(
        actual == entries["vectors.json"],
        "C31 vectors.json hashes to the digest in SHA256SUMS",
        f"SHA256SUMS says {entries['vectors.json']}\n"
        f"these bytes are  {actual}\n"
        "This is the one leg that compares against a registry-authored artifact with no checkout\n"
        "and no network, so it is the leg that really runs in CI — and it is red. Either the\n"
        "corpus was edited here (it must not be: it is a copy, and upstream owns it) or the copy\n"
        "is half-done, with new bytes beside an old sums file.",
    )

    readme = BINDING_README.read_text(encoding="utf-8")
    pin_m = BINDING_PIN.search(readme)
    fails.check(
        pin_m is not None,
        "C31 README.md names the registry commit and path this copy came from",
        "no `astra-registry@<40-hex>:<path>` in the provenance block. The pinned leg has nothing\n"
        "to compare against, so provenance becomes a claim rather than a check — and there is\n"
        "then no way to tell a stale mirror from an edited one.",
    )
    digest_m = BINDING_DIGEST.search(readme)
    if fails.check(
        digest_m is not None,
        "C31 README.md names the digest as well as the commit",
        "no `sha256:  <64-hex>  <name>` line in the provenance block.\n"
        "The commit and the digest are written in two files so that neither can be moved alone:\n"
        "a pin bumped without its digest says the copy came from somewhere it did not, and a\n"
        "digest bumped without its pin says a commit held bytes it never held.",
    ):
        fails.check(
            digest_m.group(1) == entries["vectors.json"]
            and digest_m.group(2) == "vectors.json",
            "C31 README.md's digest is SHA256SUMS' digest",
            f"README.md says {digest_m.group(1)}  {digest_m.group(2)}\n"
            f"SHA256SUMS says {entries['vectors.json']}  vectors.json\n"
            "Half a refresh. Whichever of the two was updated, the other was not, and the\n"
            "provenance block is now a sentence about bytes that are not these.",
        )

    # The reader, not the bytes: the digest leg above already owns those.
    try:
        doc = json.loads(vectors_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        fails.check(False, "C31 vectors.json parses", str(e))
        return
    cases = doc.get("cases")
    floors = doc.get("floors")
    n_cases = len(cases) if isinstance(cases, list) else 0
    numbering = {
        c.get("vector") for c in (cases if isinstance(cases, list) else [])
        if isinstance(c, dict)
    }
    fails.check(
        isinstance(cases, list) and n_cases >= MIN_BINDING_CASES,
        f"C31 floor: {n_cases if isinstance(cases, list) else 'no'} case(s) "
        f"(>= {MIN_BINDING_CASES})",
        "This floor is not a count of the corpus and must never be set to one — see the comment\n"
        "on MIN_BINDING_CASES. The census is 31 over 25 vector numbers and it is asserted by\n"
        "name in astra-registry:bot/tests/binding.test.mjs, and by AP-8's cargo suite, both of\n"
        "which read the corpus's own `floors` member. This is here so a `cases` block that\n"
        "parsed to nothing cannot reach the NOT VERIFIED notice below reading like a scan that\n"
        "looked and was happy.",
    )
    fails.check(
        isinstance(floors, dict) and {"vectors", "cases"} <= set(floors),
        "C31 vectors.json still declares its own floors",
        f"`floors` is {type(floors).__name__}\n"
        "Upstream writes the corpus's floors into the corpus so that the three readers do not\n"
        "each keep a census. If that member is gone, the shape changed upstream and nobody\n"
        "taught this reader — which is a red build and not a pass, because the CLI suite and\n"
        "the bot's read the same member.",
    )
    if isinstance(cases, list) and isinstance(floors, dict):
        want = floors.get("cases")
        fails.check(
            isinstance(want, int) and n_cases >= want,
            f"C31 the corpus meets the floor it declares ({n_cases} case(s), "
            f"floor {want})",
            "The file's own `floors.cases` is what upstream's suite asserts before it parses a\n"
            "case. A copy under it is a copy that lost cases in transit — the digest leg above\n"
            "says whether the bytes were edited, and this says what the edit cost.",
        )
        fails.check(
            isinstance(floors.get("vectors"), int)
            and numbering >= set(range(1, floors["vectors"] + 1)),
            f"C31 vector numbers 1..{floors.get('vectors')} all have a case",
            f"present: {sorted(n for n in numbering if isinstance(n, int))}\n"
            "B-T2.4's numbering is read by three tasks and two other repositories. A gap is a\n"
            "case that went missing, not a rule that got smaller.",
        )

    # ── leg 1: the vendor sweep cannot reach this directory ──────────────────
    #
    # The failure this leg exists for is a deletion, not a mismatch: a hand-
    # copied file inside a directory `vendor-testdata.sh` sweeps is a file the
    # next vendor run removes, between two green runs, with the CLI suite then
    # iterating an empty corpus.
    if VENDOR_SCRIPT.is_file():
        script = VENDOR_SCRIPT.read_text(encoding="utf-8")
        src_m = re.search(r'^\s*src="\$here/(\S+?)"', script, re.M)
        dests = re.findall(r'^\s*\w*_?dest="([^"]+)"', script, re.M)
        local_dests = [d for d in dests if d.startswith("$here")]
        fails.check(
            src_m is not None and src_m.group(1) == "testdata/bundles"
            and not local_dests
            and "binding-line" not in script,
            "C31 tools/vendor-testdata.sh neither copies nor sweeps testdata/binding-line",
            f"src={src_m.group(1) if src_m else 'unreadable'}, "
            f"destinations inside this repository: {local_dests or 'none'}, "
            f"names binding-line: {'binding-line' in script}\n"
            "That script pushes `testdata/bundles` OUT to the daemon and to the registry and\n"
            "sweeps each destination with `rm -f`, deleting whatever the bundle corpus's file\n"
            "list does not name (tools/vendor-testdata.sh:101-112). This corpus travels the\n"
            "OTHER way — astra-registry owns it — so it must be neither a source nor a\n"
            "destination of that script. If a second corpus really does need vendoring, it needs\n"
            "its own source, its own sums file and its own sweep; sharing this one's would make\n"
            "AstraPlugins look canonical for a file it only copies.\n"
            "astra-registry holds the mirror image of this guard: bot/tests/binding.test.mjs\n"
            "asserts that tests/vectors/ — which the sweep does own — holds no subdirectory.",
        )
    else:
        fails.check(
            False,
            "C31 tools/vendor-testdata.sh is where this rule looks for it",
            f"no {VENDOR_SCRIPT.relative_to(ROOT)}. If it moved, this leg is looking at nothing\n"
            "and the sweep it guards against is unguarded.",
        )

    if pin_m is None:
        return
    pin, upstream_rel = pin_m.group(1), pin_m.group(2)

    # ── legs 2 and 3: pinned, and head ───────────────────────────────────────
    registry = _registry_dir(upstream_rel)
    if registry is None:
        print("C31 NOT VERIFIED: no astra-registry checkout holding "
              f"{upstream_rel} at $ASTRA_REGISTRY_DIR or ../astra-registry.")
        print(f"        taken on trust: {n_cases} case(s) over "
              f"{len(numbering)} vector number(s),")
        print(f"        {len(vectors_bytes)} bytes hashing to {actual},")
        print(f"        claimed to be astra-registry@{pin[:12]}…:{upstream_rel}.")
        print("        The digest above WAS compared, against the SHA256SUMS the registry wrote")
        print("        and this copy carries. What was not compared is whether that sums file is")
        print("        still the registry's, and whether the registry has changed the corpus")
        print("        since the pin. A stale mirror and an edited one look identical from here,")
        print("        and the difference decides whether `astra-plugin check` predicts what the")
        print("        bot will actually do to an author's tag.")
        fails.skip("C31", "no astra-registry checkout")
        return

    _binding_compare(fails, registry, upstream_rel, pin)
    _binding_compare(fails, registry, upstream_rel, None)


RULES = {
    "C24": rule_C24,
    "C25": rule_C25,
    "C26": rule_C26,
    "C27": rule_C27,
    "C31": rule_C31,
}


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
    # A run that declined to compare something does not get to end on the word
    # "pass" alone. Same sentence shape as `tools/check-locales.py`'s, so a
    # reader who has learnt one transcript has learnt both.
    if fails.unverified:
        listed = "; ".join(f"{rule} ({why})" for rule, why in fails.unverified)
        print(f"check-registry-mirrors: {', '.join(wanted)} pass, NOT VERIFIED: {listed}.")
        return 0
    print(f"check-registry-mirrors: {', '.join(wanted)} pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
