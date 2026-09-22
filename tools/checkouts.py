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
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: Where the daemon's tree sits inside the Astra repository: `astra-rs/`, at
#: its top. CI checks Astra out at `_astra` and passes `--astra-dir
#: _astra/astra-rs`; a maintainer's default is `../Astra/astra-rs`. Either way
#: the directory the rules read is never a checkout's top, which is what
#: `checkout_top` has to be told.
DAEMON_IN_REPO = "astra-rs"


def checkout_top(tree: Path, in_repo: str) -> tuple[Path | None, str]:
    """`(top, "")` when `tree` sits at exactly `in_repo` below its checkout's top, else `(None, why)`.

    `top` is the top-level git reports, as it reports it. `why` completes the
    sentence "the tree is …": `not in a git checkout`, or `in a git checkout, but
    not as its top-level astra-rs/` — the second being an `_astra` that lost its
    `.git` (enclosed by the AstraPlugins checkout), a copy nested one level
    deeper in another checkout, or a clone whose top IS `astra-rs/`. A symlink is
    followed, so a link to a real checkout's `astra-rs/` is that checkout.
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
    if rel != in_repo:
        return None, f"in a git checkout, but not as its top-level {in_repo}/"
    return top, ""
