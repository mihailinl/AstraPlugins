#!/usr/bin/env python3
"""The claims this repository makes about things that live somewhere else.

    python3 tools/check-registry-mirrors.py                  # every rule
    python3 tools/check-registry-mirrors.py --rules C24      # one of them
    python3 tools/check-registry-mirrors.py --rules C27,C31 --pins
                                  # the registry commits their PINNED legs read

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
    every job can reach, this one needs a working copy of another repository.

    In CI that copy is `proto-upstream`'s `_registry`, passed as
    `--registry-dir`, and the last two legs run there for real, in both modes.
    The `couplings` job has no registry and goes on printing the notice. The
    checkout is one commit deep, and the pinned leg reads a second commit, so
    the step fetches exactly that one by SHA first; `--pins` prints it, from
    the same header this rule reads, so the step and the rule cannot disagree
    about which commit that is. Until that step, every CI transcript this rule
    ever produced ended on NOT VERIFIED.

    The pinned leg reads a COMMIT, so its registry must be a git checkout of
    its own, never a copy of the files that some other repository encloses —
    `git -C` searches upward. An explicit `--registry-dir` that is not one is
    exit 2. A `$ASTRA_REGISTRY_DIR` or `../astra-registry` that is not one
    leaves the pinned leg NOT VERIFIED, by name, and the head leg, which reads
    files, still runs (entry 120). C31's pinned leg is held to the same rule.

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
    In CI both run in `proto-upstream`, against `_registry`, in the same step
    as C27's and wired the same way — the README's pinned commit fetched by
    SHA, then `--registry-dir`. The notice stays in the `couplings` job, which
    has no registry.

C28 — `spec/panel.yaml` is the panel's submission page, as astra-registry's
token file records it, and everything that prints it agrees.

    From CLI 0.4.0, `astra-plugin publish` sends a bound repository to the
    panel's submission page (contract FLOW-77) instead of an issue form. The
    address and its two query parameter names are the plugins service's, and
    astra-registry records them in `schema/contract-tokens-v1.json`, entry
    `page:FLOW-77`, as two members: `url`, the address alone, and `query`, the
    parameter names in order. This repository carries them four times — the
    spec file, the CLI's vendored copy, every docs literal in seven locales,
    and (through the vendored copy) the URL the CLI builds.

    Legs:

      * IN-REPO. `spec/panel.yaml` parses to an https `url` with no `?` and a
        non-empty `query`; each value names the upstream member it mirrors; the
        header names a 40-hex registry commit; and
        `astra-plugin-cli/src/panel.yaml` is byte-identical.
      * DOCS. Every literal of that address anywhere under `docs/` is followed
        by exactly the declared parameter names, in order — or by nothing at
        all. A floor of one literal per docs locale, because the author docs
        (AP-9) name the page in every language, and a rename that took the
        literal out of a page would otherwise pass as "no literal disagrees".
      * PINNED and HEAD. The entry at the header's commit, and at the
        registry's head, member by member: `url` against `url`, `query` against
        `query`. An entry whose `url` carries a `?`, or that has no `query`
        list, is a shape this rule refuses rather than parses — a single joined
        string would compare equal to a spliced one by luck, and the client
        plan's reader of the same entry compares the same two members.

C35 — the media type C32 pairs with each icon extension is astra-registry's.

    `spec/icon-formats.yaml` carries filenames alone, deliberately, so which
    media type an `icon.<ext>` is inlined under lives in astra-registry's
    `ICON_FORMATS` — `iconDataUri` writes `format.media` into every signed
    `data:` URI, so that table IS what the store receives. C32, in
    `proto-upstream`, holds the spec against the renderer's allowlist and
    needs that pairing to do it; the registry was not checked out in its job,
    so it carries a hand copy, `EMITTED`. Nothing compared the copy with the
    table. C32 fails closed on an extension it cannot pair, so this was never
    a silent green — it was a misleading red: the registry changes a type, C32
    goes on judging the old one, and when it fails it blames `listingMedia.ts`
    for a disagreement that is the registry's.

    Three legs.

      * IN-REPO. `EMITTED` parses out of ci.yml's C32 step: exactly one step,
        exactly one `EMITTED = {`, every line inside it a one-line row this
        reader understands, no extension twice. Runs everywhere.

      * REGISTRY. `EMITTED` against `ICON_FORMATS` at the checkout's head, as
        sets both ways — an extension on one side only is named, and so is an
        extension whose type differs. The alias column (`vnd.microsoft.icon`
        beside `x-icon`) is this side's own and is not compared: the registry
        emits one type per extension. No PINNED leg, because `EMITTED` names
        no commit it was taken from.

      * DAEMON. Astra's publishing document carries a fourth copy,
        `CATALOGUE_ICON_FILES`: two pairs, deliberately fewer than the
        registry accepts, each "with the media type the registry inlines each
        one under". The daemon's own canary holds those types against the
        renderer and nothing held them against the registry. Each pair it
        names must be the registry's pair — a subset, never an equality.

    Needs an astra-registry checkout for the last two and an Astra checkout for
    the third. `proto-upstream` checks the registry out in both modes (it is
    public) and Astra in full mode only, so a fork's pull request compares the
    first two copies and prints NOT VERIFIED for the daemon's.

    Both upstream files are read as TEXT and never imported. Full mode holds a
    private repository's token on disk, and executing another repository's
    module in that job to learn six strings is a trust boundary this rule has
    no reason to cross. The cost is that a reformatted table is a red here,
    naming the line it did not understand. That is the right cost: the
    alternative is a reader that guesses.

    Not compared, and why: the registry's own pin on the same table
    (`bot/tests/presentation.test.mjs`'s `media`), which the registry's suite
    holds against `ICON_FORMATS` itself; and the two generic extension-to-type
    tables Astra serves a plugin's own UI files with, which are not in the icon
    path at all — `listingIconSrc` refuses every scheme but an inline `data:`
    image and `https:`.

C21 — `docs/en/spec/registry-index.md` §5.1 names every member of
    astra-registry's `schema/index-v1.json`, and no member it does not have.

    The page is what somebody implementing a verifier or a store reads; the
    schema is what the registry validates its catalogue with. The number was
    reserved for this comparison by the localization plan, which also predicted
    its first result: red on the day it was written. It was. Counted object by
    object under `signed`, the page named 33 of the schema's 61 members —
    `i18n`, `readme`, `publisher`, the whole `publishers` map, `commit`,
    `permissions` and twenty-two more had reached the schema and the served
    index without reaching the page, which said all the while that the schema
    "is the authority on the field list". An incomplete page that says so is
    still read as complete, and the member a reader never hears of is the one
    their verifier has no answer for.

    Each object is a table in the page headed `| member | type | rule |`,
    named by the first code span of the paragraph above it — `signed`,
    `signed.plugins[]`, `signed.plugins[].releases[].artifacts.<platform>` —
    and each rule begins `required`, `optional` or `required when`. The schema
    is walked from `$defs/signed` through `$ref`, array items and map values to
    the same paths. Two legs.

      * IN-REPO. The page parses: every member table has a lead-in naming an
        object under `signed`, no object has two tables, no member two rows,
        and every row states its requiredness. Runs everywhere.

      * REGISTRY. Both ways, object by object: an object or a member on one
        side only is named by its path, and so is a member whose requiredness
        differs — `required` is the object's `required`, `required when` a
        `oneOf` branch's, `optional` neither. Against the checkout's HEAD,
        which in CI is `main`: the page describes the catalogue the registry
        serves, and that is built from `main`. No PINNED leg, because the page
        names no registry commit and should not — a pin would be a number on a
        normative page that is stale the day after it is right. The price is
        the one C35 pays: a member added on the registry's `main` turns this
        red here, on the next run, until the page documents it. That is the
        point of the rule, and the red says which member.

    Names and requiredness are compared; types, patterns, lengths and meanings
    are prose and are not. A reader that parsed "string, ≤ 64 characters" would
    be a second schema, and the one copy of those constraints CI can trust is
    the schema itself. The envelope — `$comment`, `signed`, `signatures` — is
    §1's, shared with `revocations.json` and `trust.json`, and is not in these
    tables either.

    The schema is read as JSON text and never executed. A keyword the walker
    does not understand (`allOf`, `anyOf`, `if`, `patternProperties`, …) where
    it could introduce or require a member is a red naming the path, not a
    guess: a member that exists only inside a keyword nobody taught this
    reader is a member nobody compares. The six translations of the page are
    not read here; `docs/tools/mirror.py` holds their table rows to the
    English page's, name for name.

C36 — the docs say what the served chain carries (registry plan RC-R1-11).

    Two of astra-registry's commits make sentences here false, and ROLL-47
    says each is amended in the change that makes it false. From the
    signer's first commit to `signed` (2026-09-20) the catalogue clients are
    served is signed, so no page may say a default build has nothing to
    check. That leg asks this tree only. From the commit that ADDS
    `policy/pages-withdrawal-list.json`, Pages serves the signed withdrawal
    list and shipped clients arm, so no page may say withdrawal is not
    enforced. That leg asks astra-registry's checkout, and until the flag is
    there it is dormant. While dormant it asserts that every language's
    phrases still match, so it cannot sit waiting with a phrase list that
    finds nothing. It is one phrase list per language, because mirror.py
    compares no prose.

C33 — `spec/init-ci-templates.yaml` is the token file's template list, and
    nothing a listed template or an allowlisted commit compiles is retired
    (registry plan AP-24; contract SCOPE-7, ID-73, OPEN-OWNER-27).

    The caller `init-ci` writes lives in the author's repository, and nobody
    reruns `init-ci` there, so whatever it calls stays compiled. Each template
    version therefore has a support period: its author audience and notify
    path may not be retired until 12 months after the first `cli-v` release
    that stops writing it. The contract used to count from "the last time
    `init-ci` emits" a version, which nobody can observe. A tag can be
    observed (n14).

      * IN-REPO. The mirror parses. `CALLER_TEMPLATE_VERSION` is listed,
        still written, and `live`. The generated caller's first line names
        it, and it calls the service only if the list says so. Every `cli-v`
        tag is listed under exactly one template, and each tag's own
        init_ci.rs writes that template (before the constant existed,
        `render()` is template 1). This tree's version is listed before its
        tag exists. A stopping release is a real tag that really stopped
        writing the template, and its stop day is no earlier than that tag's
        commit. Nothing is `retired` before 12 months from its stop day.
        This leg needs the tags; where the checkout has none it fetches them
        one commit deep and says so, and its floor is red on none.

      * PINNED and HEAD. The mirror equals the token file's `templates`,
        member by member. Then ID-73: every audience or path that a listed
        template, or `plugin-release.yml` at an allowlisted commit in
        trust.json, compiles is recorded in the token file and is not
        `retired`. Today there are one template and two commits, and they
        compile nothing; the floors say that at least one of each was read.
        The test file that builds each break is tools/test_init_ci_templates.py.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The own-checkout rule, shared with tools/check-locales.py's C22: the daemon's tree
# for C35's label, and (with `in_repo = ""`) the registry's for every pinned leg.
from checkouts import DAEMON_IN_REPO, checkout_top  # noqa: E402  (sys.path is set above)

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


#: `--registry-dir` and `--astra-dir`, set by `main`. A directory passed on the
#: command line is a caller asserting the tree is there, so one that does not
#: hold the file a rule reads is exit 2, not the NOT VERIFIED the environment
#: variables fall back to. `tools/check-locales.py`'s `resolve_astra` draws the
#: same line for the same reason: the CI step that checked a tree out must go
#: red the day that path moves, not degrade into the skip it shares a script
#: with and go on reading as green.
EXPLICIT: dict[str, str | None] = {"registry": None, "astra": None}


def _own_checkout(tree: Path) -> bool:
    """Whether `tree` is the top of a git work tree of its own.

    Not `rev-parse --is-inside-work-tree`: in CI `_registry` sits INSIDE the
    AstraPlugins checkout, so a `_registry` whose `.git` went missing would be
    answered for by the parent, and `git -C _registry show <pin>:…` would go
    looking for the registry's commit in this repository's history.

    `checkout_top(tree, "")`, the rule C22 and C35's daemon label are held to,
    so there is one of it (tools/checkouts.py).
    """
    return checkout_top(tree, "")[0] is not None


#: Why a rule passing `need_git=True` needs a commit and not only the files.
#: C21 passes its own sentence instead of `True`; the refusal is the same.
PINNED_NEEDS_GIT = "the pinned leg reads a commit"


def _explicit_checkout(flag: str, given: str, anchor: str, need_git: bool | str = False) -> Path:
    p = Path(given)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    if not (p / anchor).is_file():
        print(f"{flag} {given!r} holds no {anchor}. It was passed explicitly, so this is "
              "an error and not a skip.", file=sys.stderr)
        raise SystemExit(2)
    if need_git and not _own_checkout(p):
        # C27's and C31's PINNED legs read a commit, not the files on disk, so
        # a copy of the files is not a checkout they can use. Refused here, by
        # name, rather than left to reach `git show` in whatever repository
        # happens to enclose the directory.
        why = need_git if isinstance(need_git, str) else PINNED_NEEDS_GIT
        print(f"{flag} {given!r} holds {anchor} but is not a git checkout of its own, and {why}. "
              "It was passed explicitly, so this is an error and not a skip.", file=sys.stderr)
        raise SystemExit(2)
    return p


def _registry_dir(anchor: str = "policy/reserved-ids.json", need_git: bool | str = False) -> Path | None:
    """A working copy of astra-registry, or None.

    Same two candidates as `tools/check-locales.py`'s, and anchored on a file
    the CALLING rule actually reads: a directory that happens to be named
    astra-registry but holds no `policy/reserved-ids.json` is not a checkout
    C27 can compare against, and saying so is better than reporting every name
    as missing. C31 passes its own anchor for the same reason — a checkout
    parked on a branch that predates `tests/binding-line/` cannot answer its
    question either, and "no corpus there" is a sentence a reader can act on
    where "every case differs" is not.

    `--registry-dir` comes first and is never a skip; see `EXPLICIT`. With
    `need_git`, which the two rules with a PINNED leg pass, it must also be a
    git checkout of its own; C21 passes the sentence saying why it needs one.
    """
    explicit = EXPLICIT["registry"]
    if explicit is not None:
        return _explicit_checkout("--registry-dir", explicit, anchor, need_git)
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
            f"The commit IS in that checkout (the leg asked before it read), so the pin names a "
            f"commit that does not hold this file at this path: one from before it existed, or "
            f"from before it moved. The pin in spec/reserved-ids.yaml is what is wrong."
        )
    return p.stdout


def _has_commit(registry: Path, sha: str) -> bool:
    p = subprocess.run(["git", "-C", str(registry), "cat-file", "-e", f"{sha}^{{commit}}"],
                       capture_output=True)
    return p.returncode == 0


def _pin_absent(registry: Path, sha: str, named_in: str) -> str:
    """The one sentence for a pinned leg whose commit the checkout does not hold.

    Asked once, before any file is read at the pin. Left to `git show`, a
    shallow clone answers "path 'policy/reserved-ids.json' exists on disk, but
    not in '<sha>'" once per mirrored value — true, and useless: it names the
    file, when what is missing is the commit.
    """
    return (
        f"commit {sha} is not in the checkout at {registry}.\n"
        f"It is the commit {named_in} says this copy was taken from, and the pinned leg reads\n"
        f"the file as that commit held it. A one-commit-deep checkout holds only its own tip:\n"
        f"fetch exactly this one, `git -C {registry} fetch --depth=1 origin {sha}`, which is\n"
        f"what proto-upstream's step does before it runs this. If the remote answers `not our\n"
        f"ref`, no ref on GitHub reaches that SHA, and the pin is fiction."
    )


def _pinned_leg_may_read(fails: Fails, rule: str, registry: Path, sha: str, named_in: str) -> bool:
    """Whether a PINNED leg may read commits out of `registry`; if not, says why, by name.

    A pinned leg reads a commit (`git cat-file`, then `git show <pin>:<path>`),
    and `git -C` searches upward, so a directory that is not its own checkout's
    top is answered for by whatever repository encloses it. An explicit
    `--registry-dir` never gets here unchecked: `_explicit_checkout` refuses it
    with exit 2. `$ASTRA_REGISTRY_DIR` and `../astra-registry` used not to be
    asked at all (entry 120), and measured on copies of astra-registry `main`
    with both pins fetched:

      a copy inside the AstraPlugins checkout   both pinned legs FAIL, "commit … is not
                                                in the checkout at …/regcopy", with a
                                                `git -C … fetch` into THIS repository
      a copy in no checkout at all              the same FAIL, and a fetch into nothing
      a copy nested inside a registry checkout  both pinned legs GREEN, the pins read
                                                out of the ENCLOSING checkout

    So this leg is NOT VERIFIED, by name, and only this leg: the head leg reads
    the files on disk, which are what the variable pointed at, and it runs.
    """
    top, why = checkout_top(registry, "")
    if top is not None:
        return True
    print(f"{rule} NOT VERIFIED (pinned leg): the astra-registry tree at {registry} is {why},")
    print("        so it is not a checkout this leg can read a commit from. The pin")
    print(f"        {named_in} names, {sha[:12]}, was not looked for. `git` searches")
    print("        upward from a directory: asked about a copy of the registry it answers for")
    print("        whatever repository the copy sits in, and this leg would read, or fail to")
    print("        find, the pin in THAT repository's history. The head leg below reads the files")
    print("        on disk and still runs. Point $ASTRA_REGISTRY_DIR at a clone of astra-registry")
    print("        that holds the pin to compare against it.")
    fails.skip(rule, f"pinned leg: the astra-registry tree is {why}")
    return False


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
    leg = f"pinned {sha[:12]}" if sha else f"head {_git_head(registry)}"
    if sha and not _has_commit(registry, sha):
        fails.check(
            False,
            f"C27 spec/reserved-ids.yaml is astra-registry's policy ({leg}, 0 value(s))",
            _pin_absent(registry, sha, "spec/reserved-ids.yaml"),
        )
        return
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
    registry = _registry_dir(need_git=True)
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

    if pin is not None and _pinned_leg_may_read(fails, "C27", registry, pin, "spec/reserved-ids.yaml"):
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


def read_binding_pin(readme: str | None = None) -> re.Match[str] | None:
    """`astra-registry@<commit>:<path>` out of the corpus README, or None.

    One reader for the rule and for `--pins`, so that the commit CI fetches
    and the commit the pinned leg compares against cannot be two readings.
    """
    if readme is None:
        if not BINDING_README.is_file():
            return None
        readme = BINDING_README.read_text(encoding="utf-8")
    return BINDING_PIN.search(readme)


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
            f"The commit IS in that checkout (the leg asked before it read), so the pin names a "
            f"commit that does not hold this file at this path: one from before the corpus "
            f"existed, or from before it moved. The pin in testdata/binding-line/README.md is "
            f"what is wrong."
        )
    return p.stdout


def _binding_compare(fails: Fails, registry: Path, rel: str, sha: str | None) -> None:
    """One leg: the vendored corpus against the registry, at `sha` or at head."""
    leg = f"pinned {sha[:12]}" if sha else f"head {_git_head(registry)}"
    if sha and not _has_commit(registry, sha):
        fails.check(
            False,
            f"C31 testdata/binding-line is astra-registry's corpus, byte for byte ({leg})",
            _pin_absent(registry, sha, "testdata/binding-line/README.md"),
        )
        return
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
    pin_m = read_binding_pin(readme)
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
    registry = _registry_dir(upstream_rel, need_git=True)
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

    if _pinned_leg_may_read(fails, "C31", registry, pin, "testdata/binding-line/README.md"):
        _binding_compare(fails, registry, upstream_rel, pin)
    _binding_compare(fails, registry, upstream_rel, None)


# ── C35 ──────────────────────────────────────────────────────────────────────

CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: The step whose `EMITTED` this rule reads, matched on the name's prefix so
#: that rewording what the step says about itself keeps working.
C32_STEP = "- name: C32 (full)"

#: astra-registry's emitter, relative to a checkout of it.
ICON_EMITTER = "bot/lib/assets.mjs"

#: The daemon's copy, relative to `astra-rs/`.
CATALOGUE_ICONS = "astra-daemon/src/plugins/authoring/publishing.rs"

#: `"ext": ("type/subtype", ("alias", ...)),` — one row of `EMITTED`.
EMITTED_ROW = re.compile(
    r'"([a-z0-9]+)":\s*\(\s*"([a-z]+/[a-z0-9][a-z0-9.+-]*)"\s*,'
    r'\s*\(((?:\s*"[a-z]+/[a-z0-9][a-z0-9.+-]*"\s*,?)*)\s*\)\s*\),'
)

#: `{ name: "icon.<ext>", media: "type/subtype", …},` — one row of
#: `ICON_FORMATS`. The rest of the row (the signature bytes) is not this
#: rule's business; that each row is one line, and ends as a row, is.
FORMAT_ROW = re.compile(r'\{\s*name:\s*"([^"]*)"\s*,\s*media:\s*"([^"]*)"\s*,.*\}\s*,?')

#: `("icon.<ext>", "type/subtype")` — one pair of `CATALOGUE_ICON_FILES`.
CATALOGUE_PAIR = re.compile(r'\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\)')
CATALOGUE_CONST = re.compile(
    r"pub const CATALOGUE_ICON_FILES\s*:\s*&\[\(&str,\s*&str\)\]\s*=\s*&\[(.*?)\];", re.S
)

ICON_NAME = re.compile(r"icon\.([a-z0-9]+)")
MEDIA_TYPE = re.compile(r"[a-z]+/[a-z0-9][a-z0-9.+-]*")

#: A floor on each of the two parses, not a census of either. The comparison
#: is an equality, and two readers that both return nothing are equal; this is
#: what stops that. Two is the pair every link in the chain has always handled
#: (PNG and SVG) — far below the six of today, so that no deliberate narrowing
#: trips it, and above zero, which is the only number it exists to refuse.
#: Which extension went missing is the comparison's to say, by name.
MIN_ICON_FORMATS = 2


def _git_head(tree: Path, in_repo: str = "") -> str:
    """The commit of the checkout `tree` belongs to, for the transcript. A label, not an input.

    `in_repo` is where `tree` sits inside its repository BY DESIGN, and the
    toplevel git reports must be exactly `tree` with that taken off. Any other
    enclosing repository is the wrong one to name:

    * astra-registry (`""`, the default): a checkout of the registry IS the
      tree, so the toplevel must be `tree` itself. `_registry` sits inside the
      AstraPlugins checkout in CI, and asked about a `_registry` with no `.git`,
      git would answer with THIS repository's HEAD and the transcript would name
      it as the registry's. Where a rule needs the commit and not only a label,
      `--registry-dir` refuses such a directory outright (`_explicit_checkout`).
    * the daemon (`DAEMON_IN_REPO`): `astra-rs/` is a directory at the top of
      the Astra repository, so the toplevel is `tree`'s parent and never `tree`.
      Holding it to the registry's rule printed `HEAD unknown: not a git
      checkout` on the daemon line of every full-mode run from #53 on (ops
      register, entry 108). Holding it to "whatever repository encloses it"
      instead would bring back the registry's hazard one level down: an `_astra`
      whose `.git` went missing is enclosed by the AstraPlugins checkout, as
      `_astra/astra-rs`, and would be labelled with this repository's commit.
      That rule is `checkout_top` in tools/checkouts.py, and C22 in
      tools/check-locales.py calls it too: there the enclosing repository would
      not be a label but the source of the release tags the rule reads (entry
      115).

    A directory that is in no git checkout at all names no commit either way.
    """
    if not in_repo:
        if not _own_checkout(tree):
            return "HEAD unknown: not a git checkout"
    else:
        top, why = checkout_top(tree, in_repo)
        if top is None:
            return f"HEAD unknown: {why}"
    p = subprocess.run(["git", "-C", str(tree), "rev-parse", "--short=12", "HEAD"],
                       capture_output=True, text=True)
    if p.returncode == 0:
        return p.stdout.strip()
    return "HEAD unknown: not a git checkout" if not in_repo else "HEAD unknown: its checkout has no commit"


def _astra_dir(anchor: str) -> Path | None:
    """An `astra-rs/` checkout holding `anchor`, or None.

    `--astra-dir` first, and never a skip. Then `$ASTRA_RS_DIR` — set but wrong
    is the skip, with no fall-through, which is how CONTRIBUTING.md tells a
    maintainer to force it — and then `../Astra/astra-rs`. The same three steps
    as `tools/check-locales.py`'s `resolve_astra`.
    """
    explicit = EXPLICIT["astra"]
    if explicit is not None:
        return _explicit_checkout("--astra-dir", explicit, anchor)
    env = os.environ.get("ASTRA_RS_DIR")
    given = env if env is not None else "../Astra/astra-rs"
    if not given:
        return None
    p = Path(given)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p if (p / anchor).is_file() else None


def read_emitted() -> dict[str, tuple[str, tuple[str, ...]]]:
    """ext -> (media type, aliases), out of ci.yml's C32 step.

    Raises `LookupError` with a sentence for the transcript. Every anchor here
    has to match exactly once: a reader that falls back to "none found" is a
    comparison of nothing against something, which C35 exists to refuse.
    """
    rel = CI_WORKFLOW.relative_to(ROOT)
    lines = CI_WORKFLOW.read_text(encoding="utf-8").splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip().startswith(C32_STEP)]
    if len(starts) != 1:
        raise LookupError(
            f"{rel} has {len(starts)} step(s) whose name starts `{C32_STEP[2:]}`, and this rule "
            f"reads EMITTED out of exactly one. If C32 was renamed, rename C32_STEP here with it."
        )
    s = starts[0]
    indent = len(lines[s]) - len(lines[s].lstrip())
    end = next(
        (j for j in range(s + 1, len(lines))
         if lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) <= indent),
        len(lines),
    )
    step = lines[s + 1:end]
    opens = [k for k, ln in enumerate(step) if ln.strip() == "EMITTED = {"]
    if len(opens) != 1:
        raise LookupError(
            f"the C32 step in {rel} has {len(opens)} line(s) reading `EMITTED = {{`, want exactly 1."
        )
    rows: dict[str, tuple[str, tuple[str, ...]]] = {}
    for ln in step[opens[0] + 1:]:
        st = ln.strip()
        if st == "}":
            break
        if not st or st.startswith("#"):
            continue
        m = EMITTED_ROW.fullmatch(st)
        if not m:
            raise LookupError(
                f"a line inside C32's EMITTED is not a row this rule can read:\n  {st}\n"
                f'It reads one row per line, `"ext": ("type/subtype", ("alias", ...)),`. Keep '
                f"that shape, or teach EMITTED_ROW the new one — it refuses rather than skipping "
                f"a line, because a skipped row is an extension nobody compares."
            )
        ext = m.group(1)
        if ext in rows:
            raise LookupError(
                f"C32's EMITTED names `.{ext}` twice. Python keeps the second without a word, so "
                f"the first row is a type C32 never uses."
            )
        rows[ext] = (m.group(2), tuple(re.findall(r'"([^"]+)"', m.group(3))))
    else:
        raise LookupError(f"C32's EMITTED in {rel} is never closed by a line holding only `}}`.")
    return rows


def read_icon_formats(registry: Path) -> dict[str, tuple[str, str]]:
    """ext -> (filename, media type), out of astra-registry's ICON_FORMATS, as text."""
    lines = (registry / ICON_EMITTER).read_text(encoding="utf-8").splitlines()
    opens = [i for i, ln in enumerate(lines) if ln.strip() == "export const ICON_FORMATS = ["]
    if len(opens) != 1:
        raise LookupError(
            f"astra-registry/{ICON_EMITTER} has {len(opens)} line(s) reading "
            f"`export const ICON_FORMATS = [`, want exactly 1. The table moved or was renamed "
            f"upstream; find where `iconDataUri` gets `format.media` from now and point "
            f"ICON_EMITTER at it."
        )
    rows: dict[str, tuple[str, str]] = {}
    for ln in lines[opens[0] + 1:]:
        st = ln.strip()
        if st == "];":
            break
        if not st or st.startswith("//"):
            continue
        m = FORMAT_ROW.fullmatch(st)
        if not m:
            raise LookupError(
                f"a line inside astra-registry's ICON_FORMATS is not a row this rule can read:\n"
                f"  {st}\n"
                f'It reads one row per line, `{{ name: "icon.<ext>", media: "type/subtype", … }},`. '
                f"If the registry reformatted the table, teach FORMAT_ROW the new shape; it refuses "
                f"rather than skipping, because a skipped row is a type nobody compares."
            )
        name, media = m.groups()
        n = ICON_NAME.fullmatch(name)
        if not n or not MEDIA_TYPE.fullmatch(media):
            raise LookupError(
                f"astra-registry's ICON_FORMATS has a row this rule cannot pair: name {name!r}, "
                f"media {media!r}. It expects `icon.<ext>` and `type/subtype`."
            )
        ext = n.group(1)
        if ext in rows:
            raise LookupError(
                f"astra-registry's ICON_FORMATS names {name} twice. `formatOf` takes the first "
                f"with `find`, so the second row is dead there, and this rule will not guess which "
                f"one a reader meant."
            )
        rows[ext] = (name, media)
    else:
        raise LookupError(f"astra-registry's ICON_FORMATS is never closed by a line holding `];`.")
    return rows


def read_catalogue_icon_files(astra_rs: Path) -> dict[str, str]:
    """filename -> media type, out of the daemon's `CATALOGUE_ICON_FILES`, as text."""
    text = (astra_rs / CATALOGUE_ICONS).read_text(encoding="utf-8")
    declared = text.count("pub const CATALOGUE_ICON_FILES")
    if declared != 1:
        raise LookupError(
            f"astra-rs/{CATALOGUE_ICONS} declares `pub const CATALOGUE_ICON_FILES` {declared} "
            f"time(s), want exactly 1. If the table moved, point CATALOGUE_ICONS at it."
        )
    m = CATALOGUE_CONST.search(text)
    if not m:
        raise LookupError(
            f"`CATALOGUE_ICON_FILES` in astra-rs/{CATALOGUE_ICONS} is no longer "
            f"`&[(&str, &str)] = &[ … ];`. Teach CATALOGUE_CONST the new shape."
        )
    body = m.group(1)
    residue = CATALOGUE_PAIR.sub("", body).replace(",", "").strip()
    if residue:
        raise LookupError(
            f"`CATALOGUE_ICON_FILES` holds something that is not a (\"name\", \"type\") pair: "
            f"{residue!r}. This rule reads pairs and nothing else, and refuses rather than "
            f"comparing the pairs it happened to recognise."
        )
    rows: dict[str, str] = {}
    for name, media in CATALOGUE_PAIR.findall(body):
        if name in rows:
            raise LookupError(f"`CATALOGUE_ICON_FILES` names {name} twice.")
        rows[name] = media
    return rows


def rule_C35(fails: Fails) -> None:
    # ── leg 0: the copy in this repository ───────────────────────────────────
    try:
        emitted = read_emitted()
    except (LookupError, OSError) as e:
        fails.check(False, "C35 EMITTED parses out of ci.yml's C32 step", str(e))
        return
    ok = fails.check(
        len(emitted) >= MIN_ICON_FORMATS,
        f"C35 floor: C32's EMITTED has {len(emitted)} row(s) (>= {MIN_ICON_FORMATS})",
        "Either the table really was cut to almost nothing, or this reader stopped at the wrong\n"
        "line and is about to compare an empty map with the registry's. See MIN_ICON_FORMATS.",
    )
    if not ok:
        return

    # ── leg 1: against the registry ──────────────────────────────────────────
    registry = _registry_dir(ICON_EMITTER)
    if registry is None:
        print("C35 NOT VERIFIED: no astra-registry checkout holding "
              f"{ICON_EMITTER} at --registry-dir, $ASTRA_REGISTRY_DIR or ../astra-registry.")
        print(f"        taken on trust, {len(emitted)} pairing(s) C32 judges the renderer with:")
        for ext, (media, _aliases) in sorted(emitted.items()):
            print(f"          .{ext:<5} {media}")
        print("        Whether the registry still inlines each of those under that type was not")
        print("        asked, and neither was the daemon's CATALOGUE_ICON_FILES. From here a")
        print("        registry that changed a type and a C32 that is right look identical.")
        fails.skip("C35", "no astra-registry checkout")
        return

    head = _git_head(registry)
    try:
        theirs = read_icon_formats(registry)
    except (LookupError, OSError) as e:
        fails.check(False, f"C35 astra-registry's ICON_FORMATS parses ({head})", str(e))
        return
    ok = fails.check(
        len(theirs) >= MIN_ICON_FORMATS,
        f"C35 floor: astra-registry's ICON_FORMATS has {len(theirs)} row(s) "
        f"(>= {MIN_ICON_FORMATS}, {head})",
        "Either the registry accepts almost no icon at all, or this reader stopped at the wrong\n"
        "line. See MIN_ICON_FORMATS.",
    )
    if not ok:
        return

    problems: list[str] = []
    for ext in sorted(set(theirs) - set(emitted)):
        name, media = theirs[ext]
        problems.append(
            f".{ext}: astra-registry inlines {name} as `{media}`, and C32's EMITTED has no row "
            f"for `.{ext}`."
        )
    for ext in sorted(set(emitted) - set(theirs)):
        problems.append(
            f".{ext}: C32's EMITTED pairs it with `{emitted[ext][0]}`, and astra-registry's "
            f"ICON_FORMATS has no icon.{ext} — the registry refuses that file, so the row "
            f"describes an icon nobody can publish."
        )
    for ext in sorted(set(emitted) & set(theirs)):
        ours, (name, media) = emitted[ext][0], theirs[ext]
        if ours != media:
            problems.append(
                f".{ext}: C32's EMITTED says `{ours}`, and astra-registry inlines {name} as "
                f"`{media}`. C32 is judging the renderer against a type the store is never sent."
            )
    fails.check(
        not problems,
        f"C35 C32's EMITTED is astra-registry's ICON_FORMATS, both ways "
        f"({head}, {len(set(emitted) | set(theirs))} extension(s))",
        "\n".join(problems) + "\n"
        "ASTRA-REGISTRY OWNS THIS PAIRING. `iconDataUri` in bot/lib/assets.mjs writes\n"
        "`format.media` into every signed data: URI, so ICON_FORMATS is what the store receives\n"
        "and EMITTED is a copy of it. If the registry's change was meant, copy its row into\n"
        "EMITTED in .github/workflows/ci.yml's C32 step, and let C32 say whether INLINE_IMAGE in\n"
        "listingMedia.ts accepts the type — that is C32's question, not this one's. If it was not\n"
        "meant, the repair is in astra-registry, whose bot/tests/presentation.test.mjs pins the\n"
        "same rows. Until the two agree, a C32 red names the renderer for the registry's change.\n"
        "(Gap 36 in the ops register.)",
    )

    # ── leg 2: the daemon's copy, against the registry ───────────────────────
    astra = _astra_dir(CATALOGUE_ICONS)
    if astra is None:
        print("C35 NOT VERIFIED: no Astra checkout holding "
              f"astra-rs/{CATALOGUE_ICONS} at --astra-dir, $ASTRA_RS_DIR or ../Astra/astra-rs.")
        print("        The daemon's publishing document names icon files with the media type it")
        print("        says the registry inlines each one under, and the daemon's own canary holds")
        print("        those types against the renderer. Whether they are still the registry's was")
        print("        not asked: that needs the private repository, which only proto-upstream's")
        print("        full mode checks out.")
        fails.skip("C35", "no Astra checkout, so the daemon's CATALOGUE_ICON_FILES was not compared")
        return

    try:
        daemon = read_catalogue_icon_files(astra)
    except (LookupError, OSError) as e:
        fails.check(False, f"C35 the daemon's CATALOGUE_ICON_FILES parses ({_git_head(astra, DAEMON_IN_REPO)})",
                    str(e))
        return
    ok = fails.check(
        len(daemon) >= 1,
        f"C35 floor: the daemon's CATALOGUE_ICON_FILES has {len(daemon)} pair(s) (>= 1)",
        "Empty, so there is nothing to compare — and a publishing document that names no icon\n"
        "file at all is a product change, not a refactor. Say so in the commit that made it.",
    )
    if not ok:
        return
    problems = []
    by_name = {name: (ext, media) for ext, (name, media) in theirs.items()}
    for name, media in sorted(daemon.items()):
        if name not in by_name:
            problems.append(
                f"{name}: the daemon's publishing document names it, inlined as `{media}`, and "
                f"astra-registry's ICON_FORMATS has no {name} — the document recommends a file "
                f"the registry refuses."
            )
        elif by_name[name][1] != media:
            problems.append(
                f"{name}: the daemon says the registry inlines it as `{media}`; astra-registry "
                f"inlines it as `{by_name[name][1]}`. The daemon's canary is proving the renderer "
                f"draws a type the store is never sent."
            )
    fails.check(
        not problems,
        f"C35 the daemon's CATALOGUE_ICON_FILES pairs are astra-registry's "
        f"({_git_head(astra, DAEMON_IN_REPO)}, {len(daemon)} pair(s), a subset on purpose)",
        "\n".join(problems) + "\n"
        "The daemon's table is deliberately shorter than the registry's (its own comment says\n"
        "why), so this is a subset, never an equality. The repair is in Astra's\n"
        f"astra-rs/{CATALOGUE_ICONS}, unless the registry's change was the mistake.",
    )


# ── C21 ──────────────────────────────────────────────────────────────────────

INDEX_SPEC = ROOT / "docs" / "en" / "spec" / "registry-index.md"

#: astra-registry's index schema, relative to a checkout of it.
INDEX_SCHEMA = "schema/index-v1.json"

#: The header row that makes a table a member table, compared as lowercased
#: cell words so that re-aligning the pipes keeps working. A table with any
#: other header is not read — and its members are then missing from the page's
#: side, which is a red, not a skip.
MEMBER_HEADER = ["member", "type", "rule"]

#: The object a member table describes: the FIRST code span of the paragraph
#: directly above it. `[]` is an array element and `<…>` a map value; the word
#: inside the angle brackets is the page's own and is not compared.
OBJECT_PATH = re.compile(r"signed(?:\.[a-z_][a-z0-9_]*(?:\[\])?|\.<[a-z_]+>)*")
MAP_VALUE = re.compile(r"<[a-z_]+>")
MEMBER_CELL = re.compile(r"`([A-Za-z_$][A-Za-z0-9_]*)`")

#: The first words of a rule cell, longest first: `required when` is a member
#: some other member's value makes required, which is a third state and not a
#: spelling of either of the other two.
REQUIREDNESS = re.compile(r"(required when|required|optional)\b")

INDEX_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
INDEX_TABLE_RULE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$")
INDEX_CELL_SPLIT = re.compile(r"(?<!\\)\|")

#: Keywords that can introduce or require a member and that this walker does
#: not read. Met anywhere it descends, each is a red naming the path: the
#: alternative is a member that lives inside one and is compared by nobody.
#: `oneOf` is read, at an object, and only as extra `required` lists over the
#: object's own `properties` — the one shape the schema uses today.
SCHEMA_REFUSED = (
    "allOf", "anyOf", "not", "if", "then", "else", "dependentRequired",
    "dependentSchemas", "patternProperties", "unevaluatedProperties", "prefixItems",
)

#: Floors on the two parses, not a census of either. The comparison is an
#: equality, and two readers that both return nothing are equal. Two objects is
#: what a reader that stopped after the `signed` table would fail; ten members
#: is fewer than `signed.plugins[]` has required ones. Which member went is the
#: comparison's to say, by path.
MIN_INDEX_OBJECTS = 2
MIN_INDEX_MEMBERS = 10

#: Why an explicit `--registry-dir` must be a git checkout of its own for C21,
#: which reads the file off disk and has no pinned leg: its passing line names
#: the registry commit it compared against, and CI's summary repeats it. From a
#: copy of the files that commit is unknowable, and from a directory nested in
#: another repository — `_registry` sits inside the AstraPlugins checkout —
#: `git` would answer with the wrong repository's commit.
C21_NEEDS_GIT = "C21's passing line names the registry commit it compared against"


def _index_cells(row: str) -> list[str]:
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip() for c in INDEX_CELL_SPLIT.split(body)]


def _norm_path(path: str) -> str:
    return MAP_VALUE.sub("<*>", path)


def read_spec_members() -> tuple[dict[str, dict[str, tuple[str, int]]], dict[str, str], list[str]]:
    """(object -> member -> (requiredness, line), object -> the page's spelling, problems).

    Objects are keyed by normalised path (`<…>` becomes `<*>`). A table that
    cannot be read is a problem with a line number, never a table skipped: a
    skipped table is a set of members reported missing for the wrong reason.
    """
    lines = INDEX_SPEC.read_text(encoding="utf-8").splitlines()
    rel = INDEX_SPEC.relative_to(ROOT)
    objects: dict[str, dict[str, tuple[str, int]]] = {}
    spelled: dict[str, str] = {}
    where: dict[str, int] = {}
    problems: list[str] = []
    fence: str | None = None
    i = 0
    while i < len(lines):
        st = lines[i].strip()
        f = INDEX_FENCE.match(lines[i])
        if f:
            tok = f.group(1)
            if fence is None:
                fence = tok[0] * 3
            elif st.startswith(fence):
                fence = None
            i += 1
            continue
        if fence is not None or not st.startswith("|") or i + 1 >= len(lines) \
                or not INDEX_TABLE_RULE.match(lines[i + 1].strip()):
            i += 1
            continue
        header = [c.lower() for c in _index_cells(st)]
        end = i + 2
        while end < len(lines) and lines[end].strip().startswith("|"):
            end += 1
        if header != MEMBER_HEADER:
            i = end
            continue

        # The lead-in: the paragraph directly above the header, blank lines
        # skipped, ending at the previous blank line, heading or table.
        k = i - 1
        while k >= 0 and not lines[k].strip():
            k -= 1
        para: list[str] = []
        while k >= 0 and lines[k].strip() and not lines[k].lstrip().startswith(("#", "|")):
            para.insert(0, lines[k].strip())
            k -= 1
        lead = " ".join(para)
        spans = re.findall(r"`([^`]+)`", lead)
        if not lead.endswith(":") or not spans or not OBJECT_PATH.fullmatch(spans[0]):
            problems.append(
                f"{rel}:{i + 1}: a `| member | type | rule |` table whose lead-in does not name "
                f"its object. The paragraph above it must end in `:` and its first code span must "
                f"be the object's path under `signed` — `signed.plugins[]`, "
                f"`signed.publishers.<owner>`. Read: {lead[:160]!r}"
            )
            i = end
            continue
        path = _norm_path(spans[0])
        if path in objects:
            problems.append(
                f"{rel}:{i + 1}: `{spans[0]}` has a second table; the first is at line "
                f"{where[path]}. One object, one table, or the two will come to disagree."
            )
            i = end
            continue
        members: dict[str, tuple[str, int]] = {}
        for n in range(i + 2, end):
            cells = _index_cells(lines[n])
            if len(cells) != 3:
                problems.append(f"{rel}:{n + 1}: a member row with {len(cells)} cell(s), want 3")
                continue
            m = MEMBER_CELL.fullmatch(cells[0])
            if not m:
                problems.append(
                    f"{rel}:{n + 1}: the first cell of a member row must be one member name in "
                    f"backticks, and it is {cells[0]!r}"
                )
                continue
            r = REQUIREDNESS.match(cells[2])
            if not r:
                problems.append(
                    f"{rel}:{n + 1}: `{spans[0]}.{m.group(1)}` states no requiredness. Its rule "
                    f"must begin `required`, `optional` or `required when`, and says {cells[2][:80]!r}"
                )
                continue
            if m.group(1) in members:
                problems.append(
                    f"{rel}:{n + 1}: `{spans[0]}.{m.group(1)}` has a second row; the first is at "
                    f"line {members[m.group(1)][1]}"
                )
                continue
            members[m.group(1)] = (r.group(1), n + 1)
        objects[path] = members
        spelled[path] = spans[0]
        where[path] = i + 1
        i = end
    return objects, spelled, problems


def _schema_resolve(schema: dict, node, path: str):
    """Follow `$ref` within the one file. Anything else is refused, by path."""
    hops = 0
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise LookupError(f"{path}: `$ref` {ref!r} points outside {INDEX_SCHEMA}, and C21 reads one file")
        extra = sorted(set(node) - {"$ref", "$comment", "description", "title"})
        if extra:
            raise LookupError(
                f"{path}: `$ref` beside {extra}. In 2020-12 those apply too, and this reader follows "
                f"the reference alone; teach it, rather than let it drop them."
            )
        target = schema
        for part in ref[2:].split("/"):
            if not isinstance(target, dict) or part not in target:
                raise LookupError(f"{path}: `$ref` {ref!r} resolves to nothing")
            target = target[part]
        node = target
        hops += 1
        if hops > 32:
            raise LookupError(f"{path}: `$ref` {ref!r} does not terminate")
    return node


def read_schema_members(schema: dict) -> dict[str, dict[str, str]]:
    """Normalised object path -> member -> requiredness, from `$defs/signed` down."""
    objects: dict[str, dict[str, str]] = {}

    def refuse(node: dict, path: str) -> None:
        found = [k for k in SCHEMA_REFUSED if k in node]
        if found:
            raise LookupError(
                f"{path}: carries {', '.join('`' + k + '`' for k in found)}, which C21 does not read. "
                f"A member introduced or required there would be compared by nobody; teach "
                f"read_schema_members the shape rather than let it pass unread."
            )

    def descend(node, path: str) -> None:
        node = _schema_resolve(schema, node, path)
        if not isinstance(node, dict):
            return
        refuse(node, path)
        if "properties" in node:
            walk(node, path)
        elif "oneOf" in node:
            raise LookupError(
                f"{path}: `oneOf` on something with no `properties`; C21 reads it only at an object"
            )
        items = node.get("items")
        if isinstance(items, dict):
            descend(items, path + "[]")
        extra = node.get("additionalProperties")
        if isinstance(extra, dict):
            descend(extra, path + ".<*>")

    def walk(node: dict, path: str) -> None:
        props = node["properties"]
        if not isinstance(props, dict):
            raise LookupError(f"{path}: `properties` is not an object")
        required = set(node.get("required", []))
        conditional: set[str] = set()
        for b, branch in enumerate(node.get("oneOf", [])):
            if not isinstance(branch, dict):
                raise LookupError(f"{path}: `oneOf` branch {b} is not an object")
            refuse(branch, f"{path} (oneOf branch {b})")
            unknown = sorted(set(branch) - {"title", "description", "$comment", "properties", "required"})
            if unknown:
                raise LookupError(f"{path}: `oneOf` branch {b} carries {unknown}, which C21 does not read")
            stray = sorted(set(branch.get("properties", {})) - set(props))
            if stray:
                raise LookupError(
                    f"{path}: `oneOf` branch {b} declares {stray}, which the object's own "
                    f"`properties` do not; C21 reads a branch only as a `required` list over them"
                )
            conditional |= set(branch.get("required", []))
        undeclared = sorted((required | conditional) - set(props))
        if undeclared:
            raise LookupError(
                f"{path}: `required` names {undeclared}, which `properties` does not declare"
            )
        if path in objects:
            raise LookupError(f"{path}: reached twice")
        objects[path] = {
            name: "required" if name in required else "required when" if name in conditional
            else "optional"
            for name in props
        }
        for name, sub in props.items():
            descend(sub, f"{path}.{name}")

    defs = schema.get("$defs")
    if not isinstance(defs, dict) or "signed" not in defs:
        raise LookupError(
            f"{INDEX_SCHEMA} has no `$defs.signed`. C21 walks from there; if the envelope was "
            f"reshaped, point it at where `signed` is defined now"
        )
    descend(defs["signed"], "signed")
    return objects


def _registry_label(tree: Path) -> str:
    """The checkout's commit for the transcript, or a sentence saying why it is not one.

    C21 reads the schema off disk, so the commit is what the file was compared
    AT only when the file is unmodified — and `_git_head` alone answers for an
    ENCLOSING repository: in CI `_registry` sits inside the AstraPlugins
    checkout, so a `_registry` whose `.git` went missing would be labelled with
    this repository's commit. A label, not an input; the comparison is of the
    bytes on disk either way.
    """
    if not _own_checkout(tree):
        return "not a git checkout of its own, so no commit"
    head = _git_head(tree)
    p = subprocess.run(["git", "-C", str(tree), "status", "--porcelain", "--", INDEX_SCHEMA],
                       capture_output=True, text=True)
    if p.returncode != 0 or p.stdout.strip():
        return f"{head} with {INDEX_SCHEMA} modified in the working tree"
    return head


def rule_C21(fails: Fails) -> None:
    rel = INDEX_SPEC.relative_to(ROOT)
    # ── leg 0: the page ──────────────────────────────────────────────────────
    ours, spelled, problems = read_spec_members()
    n_ours = sum(len(m) for m in ours.values())
    parsed = fails.check(
        not problems,
        f"C21 {rel} parses to member tables ({len(ours)} object(s), {n_ours} member(s))",
        "\n".join(problems) + "\n"
        "Each object under `signed` is one `| member | type | rule |` table; the paragraph above\n"
        "it ends in `:` and its first code span is the object's path; each rule begins\n"
        "`required`, `optional` or `required when`. Section 5.1 of the page says the same.",
    )
    floored = fails.check(
        len(ours) >= MIN_INDEX_OBJECTS and n_ours >= MIN_INDEX_MEMBERS,
        f"C21 floor: the page has {len(ours)} member table(s) and {n_ours} member row(s) "
        f"(>= {MIN_INDEX_OBJECTS}, >= {MIN_INDEX_MEMBERS})",
        "Either the tables were cut to almost nothing, or this reader stopped at the wrong line and\n"
        "is about to compare an empty page with the schema. See MIN_INDEX_OBJECTS.",
    )
    if not (parsed and floored):
        return

    # ── leg 1: against the registry ──────────────────────────────────────────
    registry = _registry_dir(INDEX_SCHEMA, need_git=C21_NEEDS_GIT)
    if registry is None:
        print("C21 NOT VERIFIED: no astra-registry checkout holding "
              f"{INDEX_SCHEMA} at --registry-dir, $ASTRA_REGISTRY_DIR or ../astra-registry.")
        print(f"        taken on trust: the {n_ours} member(s) in {len(ours)} object(s) {rel}")
        print("        documents. Whether the schema has a member the page does not name, or has")
        print("        dropped one the page still names, or disagrees about a requiredness, was")
        print("        not asked.")
        fails.skip("C21", "no astra-registry checkout")
        return

    head = _registry_label(registry)
    try:
        theirs = read_schema_members(
            json.loads((registry / INDEX_SCHEMA).read_text(encoding="utf-8"))
        )
    except (LookupError, OSError, json.JSONDecodeError) as e:
        fails.check(False, f"C21 astra-registry's {INDEX_SCHEMA} walks to member lists ({head})", str(e))
        return
    n_theirs = sum(len(m) for m in theirs.values())
    ok = fails.check(
        len(theirs) >= MIN_INDEX_OBJECTS and n_theirs >= MIN_INDEX_MEMBERS,
        f"C21 floor: astra-registry's {INDEX_SCHEMA} has {len(theirs)} object(s) and "
        f"{n_theirs} member(s) under `signed` (>= {MIN_INDEX_OBJECTS}, >= {MIN_INDEX_MEMBERS}, "
        f"{head})",
        "Either the index lost nearly every member, or this walker stopped at `$defs/signed`\n"
        "and is about to call an empty schema documented. See MIN_INDEX_OBJECTS.",
    )
    if not ok:
        return

    def show(path: str) -> str:
        return spelled.get(path, path)

    diffs: list[str] = []
    for path in sorted(set(theirs) - set(ours)):
        names = ", ".join(f"{m} ({r})" for m, r in theirs[path].items())
        diffs.append(
            f"{path}: an object in the schema with {len(theirs[path])} member(s) — {names} — and "
            f"no table in the page"
        )
    for path in sorted(set(ours) - set(theirs)):
        diffs.append(f"{show(path)}: a table in the page, and the schema has no such object")
    for path in sorted(set(ours) & set(theirs)):
        mine, yours = ours[path], theirs[path]
        for m in sorted(set(yours) - set(mine)):
            diffs.append(
                f"{show(path)}.{m}: in the schema ({yours[m]}), and not documented in the page"
            )
        for m in sorted(set(mine) - set(yours)):
            diffs.append(
                f"{show(path)}.{m}: documented at {rel}:{mine[m][1]} ({mine[m][0]}), and the "
                f"schema has no such member"
            )
        for m in sorted(set(mine) & set(yours)):
            if mine[m][0] != yours[m]:
                diffs.append(
                    f"{show(path)}.{m}: the page says {mine[m][0]} ({rel}:{mine[m][1]}), the "
                    f"schema says {yours[m]}"
                )
    fails.check(
        not diffs,
        f"C21 {rel} documents astra-registry's {INDEX_SCHEMA}, both ways "
        f"({head}, {len(set(ours) | set(theirs))} object(s), {n_theirs} member(s))",
        "\n".join(diffs) + "\n"
        "ASTRA-REGISTRY OWNS THE SHAPE. schema/index-v1.json is what the catalogue is validated\n"
        "with and tools/build-index.mjs is what writes it; the page is what a verifier is built\n"
        "from. A member the schema has and the page does not is one a reader never hears of:\n"
        "give it a row in its object's table in section 5.1 — the rule beginning `required`,\n"
        "`optional` or `required when`, the meaning taken from the schema's `description` and\n"
        "the generator, never invented — and carry the row into the six translations, which\n"
        "docs/tools/mirror.py requires. A member the page has and the schema does not was\n"
        "removed upstream or never existed: delete its row in all seven. A requiredness that\n"
        "differs is the schema's to decide, unless the schema is what is wrong, in which case\n"
        "the repair is in astra-registry and this stays red until it lands. (Gap 10 in the ops\n"
        "register.)",
    )


# ── C28 ──────────────────────────────────────────────────────────────────────

PANEL_SPEC = ROOT / "spec" / "panel.yaml"
PANEL_VENDORED = ROOT / "astra-plugin-cli" / "src" / "panel.yaml"
TOKEN_FILE = "schema/contract-tokens-v1.json"
FLOW_77 = "page:FLOW-77"
#: The seven docs locales. `docs/tools/locales.py` is the declaration; read,
#: not copied, so a locale added there is a locale this floor counts.
sys.path.insert(0, str(ROOT / "docs" / "tools"))
from locales import LOCALES as DOC_LOCALES  # noqa: E402


def read_panel_spec() -> tuple[dict[str, object], dict[str, str], str | None]:
    """(name -> value, name -> the upstream its `mirrors:` comment names, pin).

    The same `key: value` / `key:` + `  - item` hand-parse the CLI runs in
    `panel.rs`, and `read_reserved_spec` runs for C27.
    """
    values: dict[str, object] = {}
    sources: dict[str, str] = {}
    pin: str | None = None
    pending: str | None = None
    current: str | None = None
    for raw in PANEL_SPEC.read_text(encoding="utf-8").splitlines():
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
            values[key] = value
        if pending:
            sources[key] = pending
            pending = None
    return values, sources, pin


#: A docs literal of the page and whatever query string follows it. The
#: character class stops where markdown or prose would: a backtick, a closing
#: bracket or parenthesis, whitespace, a quote, or `<` (an autolink's end).
PANEL_LITERAL = re.compile(r"https://astra\.minice\.ai/plugins/_/submit(\?[^\s`)\]\"'<>]*)?")


def _docs_panel_literals() -> list[tuple[str, int, list[str]]]:
    """Every docs literal of the page: (file, line, the parameter names it carries)."""
    out = []
    for p in sorted((ROOT / "docs").rglob("*.md")):
        rel = p.relative_to(ROOT).as_posix()
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in PANEL_LITERAL.finditer(line):
                qs = (m.group(1) or "")[1:]
                names = [kv.split("=", 1)[0] for kv in qs.split("&") if kv] if qs else []
                out.append((rel, n, names))
    return out


def _flow77_entry(registry: Path, sha: str | None) -> dict:
    doc = json.loads(_registry_text(registry, TOKEN_FILE, sha))
    entries = doc.get("entries")
    if not isinstance(entries, list):
        raise LookupError(f"{TOKEN_FILE} has no `entries` list")
    found = [e for e in entries if isinstance(e, dict) and e.get("id") == FLOW_77]
    if len(found) != 1:
        raise LookupError(f"{TOKEN_FILE} has {len(found)} entries with id `{FLOW_77}`, not one")
    return found[0]


def _panel_compare(fails: Fails, registry: Path, values: dict, sha: str | None) -> None:
    leg = f"pinned {sha[:12]}" if sha else f"head {_git_head(registry)}"
    if sha and not _has_commit(registry, sha):
        fails.check(False, f"C28 spec/panel.yaml is the token file's {FLOW_77} ({leg})",
                    _pin_absent(registry, sha, "spec/panel.yaml"))
        return
    try:
        entry = _flow77_entry(registry, sha)
    except (LookupError, json.JSONDecodeError) as e:
        fails.check(False, f"C28 spec/panel.yaml is the token file's {FLOW_77} ({leg})", str(e))
        return
    problems = []
    url, query = entry.get("url"), entry.get("query")
    # SHAPE FIRST. A joined string — `url` carrying `?repo=…&tag=…` and no
    # `query` — is a different record, and comparing it by splitting would
    # make two different shapes agree. RC-R2-1 writes two members.
    if not isinstance(url, str) or "?" in url or not url.startswith("https://"):
        problems.append(f"the entry's `url` is {url!r}: not an https address without a query string")
    if not (isinstance(query, list) and query and all(isinstance(q, str) for q in query)):
        problems.append(f"the entry's `query` is {query!r}: not a non-empty list of parameter names")
    if not problems:
        if url != values.get("url"):
            problems.append(f"url: we say {values.get('url')!r}, the entry says {url!r}")
        if query != values.get("query"):
            problems.append(f"query: we say {values.get('query')!r}, the entry says {query!r}")
    fails.check(
        not problems,
        f"C28 spec/panel.yaml is the token file's {FLOW_77}, member by member ({leg})",
        "\n".join(problems) + "\n"
        "The page is the plugins service's, recorded by astra-registry's token file. Change it\n"
        "there first; then copy `url` and `query` into spec/panel.yaml, move its PINNED AT commit,\n"
        "copy the file to astra-plugin-cli/src/panel.yaml, and fix every docs literal C28 names.",
    )


def rule_C28(fails: Fails) -> None:
    spec_text = PANEL_SPEC.read_text(encoding="utf-8") if PANEL_SPEC.is_file() else None
    fails.check(spec_text is not None, "C28 spec/panel.yaml exists", "AP-8's mirror of FLOW-77's page")
    if spec_text is None:
        return
    vendored = PANEL_VENDORED.read_text(encoding="utf-8") if PANEL_VENDORED.is_file() else None
    fails.check(
        vendored == spec_text,
        "C28 astra-plugin-cli/src/panel.yaml is byte-identical to spec/panel.yaml",
        ("that file is not there" if vendored is None else "the two differ")
        + "\nThe CLI builds its submission link from the vendored copy; the spec file is the"
        + "\nmirror. Copy it over. `cargo test` (panel::tests::panel_yaml_is_the_spec) agrees.",
    )
    values, sources, pin = read_panel_spec()
    url, query = values.get("url"), values.get("query")
    fails.check(
        isinstance(url, str) and url.startswith("https://") and "?" not in url
        and isinstance(query, list) and bool(query),
        "C28 spec/panel.yaml parses to an https `url` with no query string and a `query` list",
        f"url={url!r}, query={query!r}",
    )
    fails.check(
        sources.get("url", "").endswith(f"{FLOW_77} url") and sources.get("query", "").endswith(f"{FLOW_77} query"),
        f"C28 each value names the {FLOW_77} member it mirrors",
        f"`# mirrors:` lines read: {sources}",
    )
    fails.check(pin is not None, "C28 spec/panel.yaml names the registry commit it was taken from",
                "no `astra-registry@<40-hex>` in the header")

    # ── docs ─────────────────────────────────────────────────────────────────
    literals = _docs_panel_literals()
    bad = [f"{f}:{n}: carries {names or 'no parameters'}" for f, n, names in literals
           if names and names != query]
    fails.check(
        not bad,
        f"C28 every docs literal of the page carries exactly {query} ({len(literals)} literal(s))",
        "\n".join(bad) + "\nA link with a renamed or missing parameter opens the page with an empty field,"
        "\nand the author submits a form they believe is filled.",
    )
    per_locale = {loc: sum(1 for f, _, _ in literals if f.startswith(f"docs/{loc}/")) for loc in DOC_LOCALES}
    missing = sorted(loc for loc, c in per_locale.items() if c == 0)
    fails.check(
        not missing,
        f"C28 floor: the page is named in every docs locale ({per_locale})",
        f"no literal in docs/{', docs/'.join(missing)}. The author docs name the page in every\n"
        "language (AP-9's binding section); a locale with none is one this rule compares nothing in.",
    )

    # ── pinned and head ──────────────────────────────────────────────────────
    registry = _registry_dir(anchor=TOKEN_FILE, need_git=True)
    if registry is None:
        print("C28 NOT VERIFIED: no astra-registry checkout at $ASTRA_REGISTRY_DIR or ../astra-registry.")
        print(f"        url {url} and query {query} taken on trust against {TOKEN_FILE}'s {FLOW_77}.")
        fails.skip("C28", "no astra-registry checkout")
        return
    if pin is not None and _pinned_leg_may_read(fails, "C28", registry, pin, "spec/panel.yaml"):
        _panel_compare(fails, registry, values, pin)
    _panel_compare(fails, registry, values, None)


# ── C33: the generated-workflow template list, and ID-73 (registry plan AP-24) ─
#
# `init-ci` writes a caller into the author's repository, and whatever that file
# calls is compiled there for good. The contract therefore gives each template
# version a support period (SCOPE-7; OPEN-OWNER-27; n14): an author audience or
# author-notify path a listed template compiles may not be `retired` until 12
# months after the first `cli-v` release that stops writing that version, and
# not while an allowlisted reusable-workflow commit compiles it (ID-73). The
# registry's token file carries the list; `spec/init-ci-templates.yaml` mirrors
# it and adds the two records only this repository can make: which releases
# write each version, and the day the stopping release was published.
#
# The legs are pure functions over what `rule_C33` gathers, so
# `tools/test_init_ci_templates.py` can hand them trees built to be wrong.
TEMPLATES_SPEC = ROOT / "spec" / "init-ci-templates.yaml"
TEMPLATES_SOURCE = "schema/contract-tokens-v1.json templates"
TEMPLATE_CONST = re.compile(r"pub const CALLER_TEMPLATE_VERSION: u32 = (\d+);")
TEMPLATE_HEADER = "# astra-plugin init-ci template {template}"
TEMPLATE_ARG = "template = CALLER_TEMPLATE_VERSION"
CLI_TAG = re.compile(r"^cli-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEMPLATE_KEYS = ("version", "emitted_by", "author_audience", "notify_path",
                 "stopped_by", "stopped_on", "state")
#: mirror member -> token-file member.
TEMPLATE_MEMBERS = (("version", "version"), ("author_audience", "audience"),
                    ("notify_path", "notify_path"), ("stopped_by", "stopped_by"),
                    ("state", "state"))
TEMPLATE_STATES = ("live", "retired")
TRUST_JSON = "registry/v1/trust.json"
INIT_CI_REL = "astra-plugin-cli/src/commands/init_ci.rs"
#: `cli-v0.2.1`, `cli-v0.3.0` and `cli-v0.4.0` exist and a tag is never taken
#: back, so fewer than three read means the tags were not fetched.
FLOOR_CLI_TAGS = 3
#: At least one allowlisted commit: a trust.json that allows none compares
#: nothing. Not today's two, which is a count the next trust ceremony may lower.
FLOOR_REUSABLE_SHAS = 1
SUPPORT_MONTHS = 12


def read_templates_spec(text: str | None = None) -> tuple[list[dict], dict[str, str], str | None]:
    """(one dict per `---` document, header `mirrors:` sources, pin).

    Hand-parsed, as `read_panel_spec` is: `key: value`, `key:` then `  - item`,
    and `null`. Anything else raises, naming the line, rather than being read
    as something it is not.
    """
    if text is None:
        text = TEMPLATES_SPEC.read_text(encoding="utf-8")
    docs: list[dict] = []
    sources: dict[str, str] = {}
    pin: str | None = None
    doc: dict | None = None
    listing: str | None = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line == "---":
            doc, listing = {}, None
            docs.append(doc)
            continue
        if line.startswith("#") or not line:
            if doc is None and line.startswith("#"):
                m = MIRRORS.match(line)
                if m:
                    sources[m.group(2).strip()] = f"{m.group(1)} {m.group(2).strip()}"
                elif pin is None and (p := PINNED_AT.search(line)):
                    pin = p.group(1)
            continue
        if doc is None:
            raise ValueError(f"line {n}: {line!r} before the first `---`")
        if line.startswith("- "):
            if listing is None:
                raise ValueError(f"line {n}: a list item under no `key:`")
            doc[listing].append(line[2:].strip())
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise ValueError(f"line {n}: {line!r} is not `key: value`")
        if key in doc:
            raise ValueError(f"line {n}: `{key}` twice in one template")
        if value:
            doc[key], listing = (None if value == "null" else value), None
        else:
            doc[key], listing = [], key
    return docs, sources, pin


def _day(text: str | None) -> "datetime.date | None":
    import datetime
    if not isinstance(text, str) or not ISO_DAY.match(text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def _support_ends(start: "datetime.date") -> "datetime.date":
    """`start` plus SUPPORT_MONTHS calendar months; a 29 February lands on the 28th."""
    import calendar
    import datetime
    months = start.month - 1 + SUPPORT_MONTHS
    year, month = start.year + months // 12, months % 12 + 1
    return datetime.date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def c33_in_repo(fails: Fails, docs: list[dict], sources: dict[str, str], pin: str | None,
                const: int | None, generated: str, render_src: str, tags: dict[str, dict],
                tree_version: str, today: "datetime.date") -> None:
    """The mirror against this tree and its tags.

    `tags` maps each `cli-v` tag in the repository to what its commit held:
    `{"const": int | None, "render": bool, "date": "YYYY-MM-DD"}`.
    """
    shape_ok = fails.check(
        bool(docs) and all(set(d) == set(TEMPLATE_KEYS) for d in docs),
        f"C33 spec/init-ci-templates.yaml lists {len(docs)} template(s), each with exactly "
        f"{', '.join(TEMPLATE_KEYS)}",
        "\n".join(f"template {d.get('version')!r}: missing {sorted(set(TEMPLATE_KEYS) - set(d))}, "
                  f"extra {sorted(set(d) - set(TEMPLATE_KEYS))}" for d in docs
                  if set(d) != set(TEMPLATE_KEYS)) or "no `---` document at all",
    )
    if not shape_ok:
        return
    versions = [d["version"] for d in docs]
    fails.check(
        all(isinstance(v, str) and v.isdigit() for v in versions)
        and [int(v) for v in versions] == sorted({int(v) for v in versions}),
        f"C33 the template versions are distinct numbers, oldest first ({versions})",
    )
    fails.check(sources.get("templates") == TEMPLATES_SOURCE and pin is not None,
                "C33 the mirror names the token file's `templates` and the registry commit it was taken from",
                f"`# mirrors:` lines read {sources}; pin {pin}")
    by_version = {d["version"]: d for d in docs}

    # ── the tree's own template ─────────────────────────────────────────────
    current = by_version.get(str(const)) if const is not None else None
    fails.check(
        current is not None and current["stopped_by"] is None and current["state"] == "live",
        f"C33 CALLER_TEMPLATE_VERSION ({const}) is a listed template, still written, `live`",
        "a template version bumped in init_ci.rs and not added to spec/init-ci-templates.yaml "
        "(or the contract's list) is a caller shape the registry has never heard of; ID-73 "
        "protects nothing it compiles" if current is None else
        f"the list says template {const} stopped at {current['stopped_by']} / is {current['state']}",
    )
    fails.check(
        generated.startswith(TEMPLATE_HEADER + "\n") and TEMPLATE_ARG in render_src,
        f"C33 the generated caller's first line is `{TEMPLATE_HEADER}`, filled from the constant",
        "render() in init_ci.rs must open its literal with that line and pass "
        f"`{TEMPLATE_ARG}`; `cargo test` (the_first_line_names_the_template_version) checks the output",
    )
    if current is not None:
        found = [lit for lit, _ in SERVICE_LITERALS if lit in generated]
        compiles = current["author_audience"] is not None or current["notify_path"] is not None
        fails.check(
            compiles or not found,
            f"C33 template {const} compiles no audience or path, and the generated text calls nothing",
            f"the list says it compiles none, and render() carries {found}",
        )
        for member in ("author_audience", "notify_path"):
            value = current[member]
            if value is not None:
                fails.check(value in generated, f"C33 template {const}'s {member} {value!r} is in the generated text")

    # ── the releases ────────────────────────────────────────────────────────
    pending = f"cli-v{tree_version}"
    fails.check(len(tags) >= FLOOR_CLI_TAGS,
                f"C33 floor: {len(tags)} `cli-v` tag(s) read (at least {FLOOR_CLI_TAGS})",
                "the repository's tags were not fetched, so no release was compared: this leg "
                "needs `fetch-depth: 0` or `git fetch origin 'refs/tags/cli-v*:refs/tags/cli-v*'`")
    listed: dict[str, list[str]] = {}
    for d in docs:
        for tag in d["emitted_by"] if isinstance(d["emitted_by"], list) else []:
            listed.setdefault(tag, []).append(d["version"])
    for tag in sorted(set(tags) | set(listed)):
        where = listed.get(tag, [])
        if tag not in tags and tag != pending:
            fails.check(False, f"C33 {tag}, listed under template {where}, is a release",
                        f"no such tag, and it is not this tree's own version ({pending})")
            continue
        if not fails.check(len(where) == 1, f"C33 {tag} is listed under exactly one template ({where})",
                           "every `cli-v` release writes one template; list it under the one its "
                           "init_ci.rs names"):
            continue
        version = where[0]
        if tag in tags:
            info = tags[tag]
            wrote = str(info["const"]) if info["const"] is not None else ("1" if info["render"] else None)
            fails.check(wrote == version, f"C33 {tag}'s init-ci writes template {version}",
                        f"its init_ci.rs says {wrote}")
        else:
            fails.check(str(const) == version,
                        f"C33 {tag} (this tree, not tagged yet) writes template {version}",
                        f"CALLER_TEMPLATE_VERSION is {const}")
    fails.check(pending in listed, f"C33 this tree's release, {pending}, is listed",
                "a release PR adds its own tag to the template it writes, so the tag never "
                "exists unlisted")

    # ── stopping, and the 12 months (n14) ───────────────────────────────────
    for d in docs:
        v, stop, on, state = d["version"], d["stopped_by"], d["stopped_on"], d["state"]
        fails.check(state in TEMPLATE_STATES, f"C33 template {v}'s state {state!r} is one of {TEMPLATE_STATES}")
        if stop is None:
            fails.check(on is None and state == "live",
                        f"C33 template {v} is still written, so it has no stop day and is `live`",
                        f"stopped_on {on!r}, state {state!r}")
            continue
        if not fails.check(bool(CLI_TAG.match(stop)) and stop not in (d["emitted_by"] or []),
                           f"C33 template {v} stopped at {stop}, a `cli-v` release that does not write it"):
            continue
        if stop not in tags:
            fails.check(stop == pending and on is None and const is not None and str(const) != v,
                        f"C33 template {v}'s stopping release {stop} is this tree's, untagged, with no day yet",
                        f"{stop} is no tag; only this tree's own version ({pending}) may be named "
                        "before it is tagged")
            if state == "retired":
                fails.check(False, f"C33 template {v} is not `retired` before its stopping release exists")
            continue
        info = tags[stop]
        fails.check(info["const"] is not None and str(info["const"]) != v,
                    f"C33 {stop} really stopped writing template {v}",
                    f"its init_ci.rs writes {info['const'] if info['const'] is not None else '1 (no constant)'}")
        start, tagged = _day(on), _day(info["date"])
        if not fails.check(start is not None and tagged is not None and start >= tagged,
                           f"C33 template {v}'s stop day {on!r} is a date no earlier than {stop}'s commit ({info['date']})",
                           "the 12 months run from the day the release was published, which is never "
                           "before its commit: a back-dated stop retires a template early"):
            continue
        ends = _support_ends(start)
        fails.check(state != "retired" or today >= ends,
                    f"C33 template {v} is not `retired` before {ends} ({SUPPORT_MONTHS} months after {on})",
                    f"it is `retired` on {today}")


def _mentions(text: str, value: str) -> bool:
    """`value` in `text` where it ends, not as the head of a longer URL: the
    wake path begins with the audience, and a workflow that calls only the path
    must not read as compiling the audience too."""
    return re.search(re.escape(value) + r"(?![A-Za-z0-9_/.~%-])", text) is not None


def c33_against_token(fails: Fails, docs: list[dict], token: dict, trust: dict,
                      workflow_at, leg: str, today: "datetime.date") -> None:
    """One leg: the mirror against the token file, and ID-73, at one registry commit.

    `workflow_at(sha)` returns `plugin-release.yml` as that commit of this
    repository holds it.
    """
    rows = token.get("templates")
    if not fails.check(isinstance(rows, list) and all(isinstance(r, dict) for r in rows),
                       f"C33 the token file has a `templates` list ({leg})", f"it holds {rows!r}"):
        return
    mine = {d["version"]: d for d in docs}
    theirs = {str(r.get("version")): r for r in rows}
    problems = []
    if set(mine) != set(theirs):
        problems.append(f"versions: we list {sorted(mine)}, the token file {sorted(theirs)}")
    for v in sorted(set(mine) & set(theirs)):
        for ours, key in TEMPLATE_MEMBERS:
            a, b = mine[v][ours], theirs[v].get(key)
            if (str(a) if a is not None else None) != (str(b) if b is not None else None):
                problems.append(f"template {v} {ours}: we say {a!r}, the token file's `{key}` says {b!r}")
    fails.check(
        not problems,
        f"C33 spec/init-ci-templates.yaml is the token file's template list, member by member ({leg})",
        "\n".join(problems) + "\nThe list is astra-registry's, generated from the contract (RC-R2-1). A new "
        "template waits\nfor the contract MINOR that lists it; then copy it here and move the PINNED AT commit.",
    )
    for v, row in sorted(theirs.items()):
        if row.get("state") != "retired":
            continue
        start = _day((mine.get(v) or {}).get("stopped_on"))
        fails.check(start is not None and today >= _support_ends(start),
                    f"C33 the token file does not retire template {v} before its 12 months are up ({leg})",
                    f"retired, with our stop day {(mine.get(v) or {}).get('stopped_on')!r} and today {today}")

    # ── ID-73 ───────────────────────────────────────────────────────────────
    entries = [e for e in token.get("entries") or [] if isinstance(e, dict)
               and "author-ci" in (e.get("emitter") or [])]
    values = {e["value"]: e for e in entries if e.get("kind") == "audience" and e.get("value")}
    values.update({e["path"]: e for e in entries if e.get("kind") == "operation" and e.get("path")})
    fails.check(
        any(e.get("kind") == "audience" for e in values.values())
        and any(e.get("kind") == "operation" for e in values.values()),
        f"C33 floor: the token file records the author audience and the author-notify path ({leg}, {len(values)} value(s))",
        "ID-32 records both; without them there is nothing for ID-73 to protect, and this leg "
        "would compare nothing",
    )
    shas = ((trust.get("signed") or {}).get("reusable_workflow_shas")) if isinstance(trust, dict) else None
    if not fails.check(isinstance(shas, list) and len(shas) >= FLOOR_REUSABLE_SHAS
                       and all(isinstance(s, str) and re.fullmatch(r"[0-9a-f]{40}", s) for s in shas),
                       f"C33 floor: trust.json allows {len(shas) if isinstance(shas, list) else 0} "
                       f"reusable-workflow commit(s) ({leg})", f"`signed.reusable_workflow_shas` is {shas!r}"):
        return
    compiled: list[tuple[str, str]] = []
    for r in rows:
        for key in ("audience", "notify_path"):
            if r.get(key):
                compiled.append((r[key], f"template {r.get('version')}"))
    for sha in shas:
        text = workflow_at(sha)
        compiled += [(value, f"reusable workflow {sha[:12]}") for value in values if _mentions(text, value)]
    bad = []
    for value, who in compiled:
        entry = values.get(value)
        if entry is None:
            bad.append(f"{who} compiles {value!r}, which the token file records as no author-ci audience or path")
        elif entry.get("state") == "retired":
            bad.append(f"{who} compiles {value!r}, and the token file marks {entry.get('id')} `retired`")
    fails.check(
        not bad,
        f"C33 ID-73: nothing a listed template or an allowlisted commit compiles is retired "
        f"({leg}; {len(rows)} template(s), {len(shas)} commit(s), {len(compiled)} compiled value(s))",
        "\n".join(bad) + "\nID-73: the registry MUST NOT mark either `retired` while a listed template "
        "or an allowlisted\nreusable-workflow commit compiles it. Take it out of `retired`, or wait out the period.",
    )


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def _cli_tags() -> dict[str, dict]:
    """Every `cli-v` tag here, and what its commit's init_ci.rs writes.

    A checkout with no tags (proto-upstream's is one commit deep) gets them,
    one commit each, and says so; a leg that read no release is red on its
    floor, never quietly empty.
    """
    listed = _git("tag", "--list", "cli-v*").stdout.split()
    if not listed:
        p = _git("fetch", "--quiet", "--no-tags", "--depth=1", "origin", "refs/tags/cli-v*:refs/tags/cli-v*")
        print(f"note  C33 no `cli-v` tags in this checkout; fetched them one commit deep "
              f"(exit {p.returncode}{': ' + p.stderr.strip() if p.returncode else ''})")
        listed = _git("tag", "--list", "cli-v*").stdout.split()
    out: dict[str, dict] = {}
    for tag in listed:
        if not CLI_TAG.match(tag):
            continue
        src = _git("show", f"{tag}^{{commit}}:{INIT_CI_REL}")
        m = TEMPLATE_CONST.search(src.stdout) if src.returncode == 0 else None
        out[tag] = {
            "const": int(m.group(1)) if m else None,
            "render": src.returncode == 0 and "pub fn render(" in src.stdout,
            "date": _git("log", "-1", "--format=%cs", f"{tag}^{{commit}}").stdout.strip(),
        }
    return out


def _workflow_at(sha: str) -> str:
    """plugin-release.yml at an allowlisted commit of THIS repository, fetched if absent."""
    if _git("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        p = _git("fetch", "--quiet", "--no-tags", "--depth=1", "origin", sha)
        print(f"note  C33 fetched {sha[:12]}, an allowlisted reusable-workflow commit (exit {p.returncode})")
    p = _git("show", f"{sha}:.github/workflows/plugin-release.yml")
    if p.returncode != 0:
        raise LookupError(f"`git show {sha[:12]}:.github/workflows/plugin-release.yml` failed: "
                          f"{p.stderr.strip()}. trust.json allows a commit this repository cannot show.")
    return p.stdout


def _c33_leg(fails: Fails, registry: Path, docs: list[dict], sha: str | None, today) -> None:
    leg = f"pinned {sha[:12]}" if sha else f"head {_git_head(registry)}"
    if sha and not _has_commit(registry, sha):
        fails.check(False, f"C33 spec/init-ci-templates.yaml is the token file's template list ({leg})",
                    _pin_absent(registry, sha, "spec/init-ci-templates.yaml"))
        return
    try:
        token = json.loads(_registry_text(registry, TOKEN_FILE, sha))
        trust = json.loads(_registry_text(registry, TRUST_JSON, sha))
        c33_against_token(fails, docs, token, trust, _workflow_at, leg, today)
    except (LookupError, json.JSONDecodeError) as e:
        fails.check(False, f"C33 the token file and trust.json read ({leg})", str(e))


def rule_C33(fails: Fails) -> None:
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).date()
    if not fails.check(TEMPLATES_SPEC.is_file(), "C33 spec/init-ci-templates.yaml exists",
                       "AP-24's mirror of the token file's template list"):
        return
    try:
        docs, sources, pin = read_templates_spec()
    except ValueError as e:
        fails.check(False, "C33 spec/init-ci-templates.yaml parses", str(e))
        return
    src = INIT_CI.read_text(encoding="utf-8")
    m = TEMPLATE_CONST.search(src)
    cli = CLI / "Cargo.toml"
    ver = re.search(r'^version = "([^"]+)"', cli.read_text(encoding="utf-8"), re.M)
    c33_in_repo(fails, docs, sources, pin, int(m.group(1)) if m else None, generated_caller(),
                src[src.find("pub fn render("):], _cli_tags(), ver.group(1) if ver else "?", today)

    registry = _registry_dir(anchor=TOKEN_FILE, need_git=True)
    if registry is None:
        print("C33 NOT VERIFIED: no astra-registry checkout at $ASTRA_REGISTRY_DIR or ../astra-registry.")
        print(f"        the template list and ID-73 taken on trust against {TOKEN_FILE} and {TRUST_JSON}.")
        fails.skip("C33", "no astra-registry checkout")
        return
    if pin is not None and _pinned_leg_may_read(fails, "C33", registry, pin, "spec/init-ci-templates.yaml"):
        _c33_leg(fails, registry, docs, pin, today)
    _c33_leg(fails, registry, docs, None, today)


# ── C36: what the docs say the served chain carries (RC-R1-11; ROLL-47) ──────
#
# Contract ROLL-47: a promise is amended in the change that first makes it
# false, each with a grep canary. Two such changes are astra-registry's:
#
#   * the signer's first commit to `signed` (e0b7531, 2026-09-20), from which
#     the catalogue clients are served is signed. Every sentence saying a
#     default build "has nothing to check" or "classifies every catalogue as
#     unsigned" was false from that day. They stood, in seven languages, for
#     four days;
#   * the commit that ADDS `policy/pages-withdrawal-list.json`, from which
#     Pages serves the signed withdrawal list and shipped clients arm
#     (ROLL-14). Every sentence saying revocation is "not enforced" or "not
#     live" becomes false on that commit, and RC-R1-11's second half removes
#     them.
#
# So two legs. The catalogue leg asks the tree alone and has no condition:
# the served catalogue does not go back to unsigned. The withdrawal leg asks
# astra-registry's checkout whether the flag is there, and while it is not it
# is DORMANT and asserts the opposite: every phrase list still matches its
# language, so the day the flag lands it is a check that has been seen to
# find something, not one that passes because its phrases rotted. One phrase
# list per language, because `docs/tools/mirror.py` compares samples, tables
# and headings, never prose.
C36_FLAG = "policy/pages-withdrawal-list.json"
#: The registry file that names the flag's path. The rule holds its own copy
#: to it, so a moved flag is a red here and not a leg that asks the wrong path.
C36_FLAG_SOURCE = "tools/signer/pages.mjs"
C36_FLAG_LINE = 'export const FLAG_PATH = "policy/pages-withdrawal-list.json";'
C36_LOCALES = ("en", "ru", "uk", "de", "es", "ja", "zh")
#: RC-R1-11's pages. English is scanned across all of `docs/en/` and the root
#: README, as the plan asks; a translation only in these, because its phrases
#: are ordinary words that may mean something else on another page.
C36_PAGES = (
    "spec/registry-index.md", "1-orientation/security.md", "5-publish/get-listed.md",
    "6-operate/troubleshooting.md", "README.md", "publishing.md",
)
C36_MIN_EN_PAGES = 38
C36_CATALOGUE_PHRASES = {
    "en": ("has nothing to check", "classifies every catalogue as unsigned",
           "catalogue itself is still unsigned", "no catalogue signature verifies",
           "nothing has signed the catalogue", "the catalogue index they sign is still unsigned",
           "is signed; the catalogue is not", "Not yet in force:", "and **not anchored**"),
    "ru": ("нечего проверять", "ничто им не подписало каталог", "сам каталог всё ещё не подписан",
           "Ещё не в силе:", "**не заякорена**"),
    "uk": ("нема чого перевіряти", "нічого перевіряти", "ніщо ним не підписало каталог",
           "сам каталог досі не підписаний", "Ще не в силі:", "**не заякорений**"),
    "de": ("keine Signatur zu prüfen", "nichts zu prüfen", "nichts hat den Katalog damit signiert",
           "der Katalog selbst ist weiterhin unsigniert", "Noch nicht in Kraft:", "**nicht verankert**"),
    "es": ("no tiene firma que comprobar", "no tiene nada que comprobar",
           "nada ha firmado el catálogo", "el catálogo en sí sigue sin firmar", "Todavía no en vigor:",
           "**no anclada**"),
    "ja": ("チェックする署名がなく", "チェックするものが何もなく", "チェックするものがなく",
           "カタログ自体は今も未署名", "まだ発効していません:", "**固定されていません**"),
    "zh": ("没有签名可以核对", "没有任何可校验的内容", "没有任何东西可以核对", "目录本身仍然是未签名的",
           "**尚未生效：**", "**尚未锚定**"),
}
C36_WITHDRAWAL_PHRASES = {
    "en": ("revocation is not enforced", "revocation enforcement is not live",
           "Pages still serves", "signed withdrawal list on Pages", "not yet through the withdrawal list",
           "one link short", "Partly in force:"),
    "ru": ("отзыв пока не применяется", "применение отзыва пока не действует",
           "по-прежнему отдаёт", "сегодня не применяется", "пока не через список отзыва",
           "не хватает одного звена", "Частично в силе:"),
    "uk": ("відкликання поки не застосовується", "застосування відкликання поки не діє",
           "досі віддає", "сьогодні не застосовується", "поки не через список відкликання",
           "поки що не через список", "бракує однієї ланки", "Частково в силі:"),
    "de": ("noch nicht durchgesetzt", "Widerrufen noch nicht", "weiterhin die unsignierte",
           "weiterhin eine unsignierte", "heute nicht durchgesetzt", "noch nicht durch die Widerrufsliste",
           "einen Link zu kurz", "Teilweise in Kraft:"),
    "es": ("todavía no se aplica", "todavía no está activa", "todavía sirve", "no aplicado hoy",
           "todavía no a través de la lista de retirada", "a un eslabón de distancia",
           "le falta **un eslabón", "En vigor en parte:"),
    "ja": ("まだ強制されません", "まだ機能していません", "まだ発効していません",
           "今日は強制されていません", "今も未署名の撤回リストを配信", "撤回リストまではまだです",
           "撤回リストまでは", "1 リンク分だけ", "一部発効:"),
    "zh": ("尚未被强制执行", "机制尚未生效", "尚未强制执行", "仍然提供", "还没有贯穿到撤回列表",
           "还差一步", "**部分生效：**"),
}


def _c36_files(locale: str) -> list[Path]:
    if locale == "en":
        return sorted((ROOT / "docs" / "en").rglob("*.md")) + [ROOT / "README.md"]
    return [ROOT / "docs" / locale / page for page in C36_PAGES]


def _c36_hits(phrases: dict[str, tuple[str, ...]]) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Every `file:line: phrase` per language, and how many files each language read."""
    hits: dict[str, list[str]] = {}
    read: dict[str, int] = {}
    for locale in C36_LOCALES:
        hits[locale] = []
        read[locale] = 0
        for f in _c36_files(locale):
            if not f.is_file():
                continue
            read[locale] += 1
            # A phrase may be wrapped across lines, so the page is read as one
            # string of its stripped lines joined by single spaces, and each
            # match is reported at the line it starts on.
            starts: list[int] = []
            parts: list[str] = []
            at = 0
            for line in f.read_text(encoding="utf-8").splitlines():
                starts.append(at)
                parts.append(line.strip())
                at += len(parts[-1]) + 1
            text = " ".join(parts)
            for phrase in phrases[locale]:
                pos = text.find(phrase)
                while pos >= 0:
                    line_no = max(i for i, st in enumerate(starts) if st <= pos) + 1
                    hits[locale].append(f"{f.relative_to(ROOT)}:{line_no}: {phrase}")
                    pos = text.find(phrase, pos + 1)
    return hits, read


def rule_C36(fails: Fails) -> None:
    # ── leg 0: the tree reads every page it means to ─────────────────────────
    cat, read = _c36_hits(C36_CATALOGUE_PHRASES)
    missing = [f"docs/{l}/{p}" for l in C36_LOCALES if l != "en" for p in C36_PAGES
               if not (ROOT / "docs" / l / p).is_file()]
    if not fails.check(
        not missing and read["en"] >= C36_MIN_EN_PAGES + 1,
        f"C36 floor: {read['en']} English file(s) read (>= {C36_MIN_EN_PAGES} pages and the root "
        f"README), and every translation's {len(C36_PAGES)} page(s) present",
        ("missing: " + ", ".join(missing) + "\n" if missing else "")
        + "A page RC-R1-11 names moved or was deleted, or docs/en shrank: a phrase scan over the\n"
        "wrong set of files finds nothing and reads as clean.",
    ):
        return

    # ── leg 1: the catalogue half, unconditional ─────────────────────────────
    found = [h for l in C36_LOCALES for h in cat[l]]
    fails.check(
        not found,
        "C36 no page says the catalogue clients are served is unsigned (false since "
        "astra-registry's signer first committed to `signed`, e0b7531, 2026-09-20)",
        "\n".join(found) + "\n"
        "The copies committed on astra-registry's `main` carry `\"signatures\": []` by design and\n"
        "no client reads them; the served copies (`signed`, Pages, and the catalogue host from R2)\n"
        "are signed. Say which copy a sentence is about. Do not bring back that a default build\n"
        "has nothing to check (ROLL-47; registry plan RC-R1-11).",
    )

    # ── leg 2: the withdrawal half, keyed on the flag ────────────────────────
    registry = _registry_dir(C36_FLAG_SOURCE)
    if registry is None:
        print(f"C36 NOT VERIFIED: no astra-registry checkout holding {C36_FLAG_SOURCE} at "
              "--registry-dir, $ASTRA_REGISTRY_DIR or ../astra-registry, so whether")
        print(f"        {C36_FLAG} exists was not asked, and the withdrawal half was not compared.")
        fails.skip("C36", "no astra-registry checkout")
        return
    head = _registry_label(registry)
    source = (registry / C36_FLAG_SOURCE).read_text(encoding="utf-8")
    if not fails.check(
        source.count(C36_FLAG_LINE) == 1,
        f"C36 astra-registry's {C36_FLAG_SOURCE} names the flag this rule asks for ({head})",
        f"expected exactly one line `{C36_FLAG_LINE}`. The flag moved, or its declaration\n"
        "changed shape; move C36_FLAG with it, or this leg asks about a file nothing reads.",
    ):
        return
    wd, _ = _c36_hits(C36_WITHDRAWAL_PHRASES)
    if (registry / C36_FLAG).is_file():
        found = [h for l in C36_LOCALES for h in wd[l]]
        fails.check(
            not found,
            f"C36 no page says withdrawal is unenforced, now that astra-registry holds {C36_FLAG} ({head})",
            "\n".join(found) + "\n"
            "Pages serves the signed withdrawal list from the commit that ADDED the flag, and every\n"
            "shipped 0.2.x client arms on its next fetch. This is RC-R1-11's second half: rewrite\n"
            "each sentence to what is now true, in all seven languages, in one commit whose message\n"
            "names the flag commit's SHA (registry plan RC-R1-11; ROLL-47).",
        )
        return
    empty = [l for l in C36_LOCALES if not wd[l]]
    fails.check(
        not empty,
        f"C36 dormant: astra-registry holds no {C36_FLAG} ({head}), so the withdrawal sentences "
        f"are true and stay; every language's phrases still match ("
        + ", ".join(f"{l} {len(wd[l])}" for l in C36_LOCALES) + ")",
        "no match in: " + ", ".join(empty) + "\n"
        "The sentences in that language were reworded, so the day the flag lands this leg would\n"
        "pass having looked for nothing. Update C36_WITHDRAWAL_PHRASES to the words the pages use.",
    )


RULES = {
    "C21": rule_C21,
    "C24": rule_C24,
    "C25": rule_C25,
    "C26": rule_C26,
    "C27": rule_C27,
    "C28": rule_C28,
    "C31": rule_C31,
    "C33": rule_C33,
    "C35": rule_C35,
    "C36": rule_C36,
}

#: The rules with a PINNED leg: what reads the commit, and the file that names
#: it. The same readers the rules call, never a second parse of either file.
PINS = {
    "C27": (lambda: read_reserved_spec()[2], RESERVED_SPEC),
    "C28": (lambda: read_panel_spec()[2], PANEL_SPEC),
    "C31": (lambda: (m.group(1) if (m := read_binding_pin()) else None), BINDING_README),
    "C33": (lambda: read_templates_spec()[2], TEMPLATES_SPEC),
}


def print_pins(wanted: list[str]) -> int:
    """`--pins`: `<rule> <commit> <file that names it>`, one line per pinned rule asked for.

    For the CI step that gives a one-commit-deep astra-registry checkout the
    commits the PINNED legs read, and nothing more. A pinned rule whose pin
    cannot be read is exit 1 and a sentence, never a line quietly left out: the
    step would then fetch nothing for it, and "nothing to fetch" must not look
    like "nothing needed". The rule's own in-repo leg says what is wrong with
    the file; this only refuses to pretend.
    """
    asked = [r for r in wanted if r in PINS]
    if not asked:
        print(f"check-registry-mirrors: --pins: none of {', '.join(wanted)} has a pinned leg; "
              f"the rules that do are {', '.join(PINS)}.", file=sys.stderr)
        return 2
    status = 0
    for r in asked:
        read, where = PINS[r]
        rel = where.relative_to(ROOT)
        sha = read() if where.is_file() else None
        if sha is None:
            print(f"check-registry-mirrors: --pins: {r} names no astra-registry@<40-hex> in "
                  f"{rel}, so its pinned leg has no commit to read.", file=sys.stderr)
            status = 1
            continue
        print(f"{r} {sha} {rel}")
    return status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--rules",
        default=",".join(RULES),
        help="comma-separated rule ids (default: all of " + ", ".join(RULES) + ")",
    )
    ap.add_argument(
        "--registry-dir",
        default=None,
        help="an astra-registry checkout for C21, C27, C31 and C35; else $ASTRA_REGISTRY_DIR, else "
             "../astra-registry. Passed explicitly, a directory that is not one is exit 2, "
             "never NOT VERIFIED. Found implicitly, one that is not a git checkout of its own "
             "leaves C27's and C31's pinned legs NOT VERIFIED; their head legs still run.",
    )
    ap.add_argument(
        "--astra-dir",
        default=None,
        help="an Astra/astra-rs checkout for C35's daemon leg; else $ASTRA_RS_DIR, else "
             "../Astra/astra-rs. Passed explicitly, a directory that is not one is exit 2.",
    )
    ap.add_argument(
        "--pins",
        action="store_true",
        help="run nothing; print `<rule> <commit> <file>` for each rule asked for that has a "
             "PINNED leg (" + ", ".join(PINS) + "), read from the file the rule reads it from",
    )
    args = ap.parse_args()
    EXPLICIT["registry"] = args.registry_dir
    EXPLICIT["astra"] = args.astra_dir

    wanted = [r.strip() for r in args.rules.split(",") if r.strip()]
    unknown = [r for r in wanted if r not in RULES]
    if unknown:
        print(f"check-registry-mirrors: no such rule: {', '.join(unknown)}", file=sys.stderr)
        return 2
    if args.pins:
        return print_pins(wanted)

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
