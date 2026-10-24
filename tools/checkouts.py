"""Which git checkout a tree from another repository belongs to. One rule, two scripts.

`tools/check-registry-mirrors.py` (C35's daemon label) and `tools/check-locales.py`
(C22, which reads the daemon's release tags) are both handed `astra-rs/`, and both
ask git about it. `astra-rs/` is a directory at the top of the Astra repository, so
it is never a checkout's top — and in CI that repository is checked out INSIDE this
one, at `_astra`. `git -C <dir>` searches upward from the directory it is given, so
an `_astra` whose `.git` went missing is answered for by the AstraPlugins checkout
that encloses it, and so is a copy of `astra-rs/` nested anywhere inside another
repository. For C35 that was a label naming the wrong commit (ops register, entry
108); for C22 it was an input: the tags it reads to decide whether a release
resolves plugin labels would have been another repository's (entry 115).

So the rule is here once, and neither script can drift from the other: the tree must
sit at exactly `in_repo` below the top of the checkout git finds for it, with no
fall-back to whatever repository encloses it.

`in_repo = ""` is the same rule for a tree that must BE its checkout's top: an
astra-registry checkout. `tools/check-registry-mirrors.py` asks it before C27's and
C31's PINNED legs read a commit (`git cat-file`, `git show <pin>:<path>`), and its
`_own_checkout` is this call. Those legs used to ask only of an explicit
`--registry-dir`, so a `$ASTRA_REGISTRY_DIR` or `../astra-registry` that was a copy
of the files had its pins looked up in whatever repository enclosed it (entry 120).
`tools/check-locales.py`'s `_own_checkout`, which guards C20's registry, is this call
too.

`tools/check-manifest-crate.sh` is bash and cannot import this, so it spells the
same rule itself: `git rev-parse --show-toplevel` must be `$ASTRA_REPO`, compared as
physical paths. It used to ask `rev-parse --git-dir`, which any enclosing repository
answers (entry 121). `tools/test_checkouts.py` runs the script and this function on
the same layouts and fails if their verdicts differ.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: Where the daemon's tree sat inside the Astra repository through tag
#: `v0.2.7`: `astra-rs/`, one level below the checkout's top. Astra c703cabb6
#: (2026-10-23), "Flatten astra-rs/ into the repository root" — confirmed
#: final, nothing else is moving — put it AT the top instead, for every
#: commit after that one. A tag through v0.2.7 keeps the old shape forever,
#: so both are live: `astra_dir` and `daemon_checkout_top` below are how a
#: caller stops having to assume either one.
DAEMON_IN_REPO = "astra-rs"


def astra_dir(candidate: Path) -> Path | None:
    """Which of `candidate` or `candidate/astra-rs` is really the daemon's
    tree — `astra-core/`, `astra-daemon/` and the rest, directly inside it.

    `candidate` is tried first: every ref after Astra's 2026-10-23 flatten
    (c703cabb6) is flat, and a caller that still appends `/astra-rs` to an
    already-flat checkout (the old convention every caller here used) would
    otherwise build a path that does not exist. `candidate/astra-rs` is
    tried next, for every tag through v0.2.7 and for a caller who, as before
    the flatten, already pointed `candidate` at the checkout's top rather
    than at `astra-rs/` itself.

    `None` if neither holds `astra-core/` — `candidate` is not an Astra
    checkout at all, under either layout.
    """
    if (candidate / "astra-core").is_dir():
        return candidate
    nested = candidate / DAEMON_IN_REPO
    return nested if (nested / "astra-core").is_dir() else None


def daemon_checkout_top(tree: Path) -> tuple[Path | None, str]:
    """`checkout_top`, tried at both `in_repo` the daemon's tree can sit at.

    `tree` must already be resolved — e.g. by `astra_dir` above — to the
    directory `astra-core/` actually lives in; this only asks whether THAT
    directory is really its own checkout's top (flat, `in_repo=""`, every
    commit after Astra's 2026-10-23 flatten) or sits exactly `astra-rs/`
    below one (nested, every tag through v0.2.7). Trying both means this
    does not need to know which shape produced `tree` — a directory is
    either one or the other, never both, so at most one attempt can
    succeed.
    """
    found, why = checkout_top(tree, "")
    if found is not None:
        return found, ""
    return checkout_top(tree, DAEMON_IN_REPO)


def daemon_ref_paths(relative: str) -> tuple[str, str]:
    """Where `relative` (a path below the daemon's tree) sits in a
    `git show <ref>:<path>`, flat first then nested.

    A REF's layout depends on whether it predates Astra's 2026-10-23 flatten
    (c703cabb6), never on whatever layout the working tree on disk happens
    to have — `origin/main` is flat and a `v0.2.7` tag is nested, in the same
    checkout, at the same time. Flat is tried first because every ref from
    the flatten on is flat and every ref this is kept working for is a
    specific named exception (`v0.2.7` and earlier).
    """
    return (relative, f"{DAEMON_IN_REPO}/{relative}")


def checkout_top(tree: Path, in_repo: str) -> tuple[Path | None, str]:
    """`(top, "")` when `tree` sits at exactly `in_repo` below its checkout's top, else `(None, why)`.

    `top` is the top-level git reports, as it reports it. `why` completes the
    sentence "the tree is …": `not in a git checkout`, or `in a git checkout, but
    not as its top-level astra-rs/` — the second being an `_astra` that lost its
    `.git` (enclosed by the AstraPlugins checkout), a copy nested one level
    deeper in another checkout, or a clone whose top IS `astra-rs/`. With
    `in_repo = ""` the second reads `in a git checkout, but not as its top`. A
    symlink is followed, so a link to a real checkout's `astra-rs/` is that
    checkout.
    """
    p = subprocess.run(["git", "-C", str(tree), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return None, "not in a git checkout"
    top = Path(p.stdout.strip())
    try:
        rel = tree.resolve().relative_to(top.resolve()).as_posix()
    except ValueError:
        rel = None
    # `relative_to` spells the top itself ".", and `in_repo` spells it "". Until
    # entry 120 nothing called this with "", and every tree was refused.
    if rel == ".":
        rel = ""
    if rel != in_repo:
        where = f"its top-level {in_repo}/" if in_repo else "its top"
        return None, f"in a git checkout, but not as {where}"
    return top, ""
