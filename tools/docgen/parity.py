"""`docs/en/reference/parity.md` — rendered by `tools/parity/gen.py`.

There is exactly one renderer for the hook table and it is not in this
directory. `tools/parity/gen.py` owns `spec/hooks.yaml`: it renders the parity
dashboard, the three per-SDK hook tables and `spec/generated/conformance.json`,
and `tools/parity/check.py` verifies the same spec against the three SDKs'
sources and the daemon. Reimplementing any of that here would produce a second
table that agrees with the first until the day it does not.

So this module calls it. The only thing it does on its own is move the output
one directory deeper, into the reference tier — which means rebasing the
relative links in the rendered page, since `../../spec/hooks.yaml` from
`docs/en/` is `../../../spec/hooks.yaml` from `docs/en/reference/`. That
rebase is mechanical and it is *checked*: `gen.py` resolves every relative link
in every page it writes and refuses to write one that points at nothing, so a
depth this module got wrong fails generation instead of shipping.

`docs/en/parity.md` — the same render at the old, flat path — is still written
by `tools/parity/gen.py` itself. When the flat `docs/en` tier is retired, drop
`docs/en/parity.md` from that generator's `artefacts()` and this page is the
only copy.
"""

from __future__ import annotations

import importlib.util
import re
import sys

from common import DocgenError, GEN_CMD, REPO_ROOT

PARITY_DIR = REPO_ROOT / "tools" / "parity"


def _load():
    """Import `tools/parity/{gen,spec}.py` by path, under distinct names.

    By path and not by `import gen`, because this directory also has a `gen.py`
    and a module name is a global. `tools/parity/gen.py` puts its own directory
    on `sys.path` when it loads, which is how its `import spec` resolves.
    """
    path = PARITY_DIR / "gen.py"
    if not path.exists():
        raise DocgenError(f"{path} does not exist — tools/parity owns the hook table.")
    spec_obj = importlib.util.spec_from_file_location("astra_parity_gen", path)
    if spec_obj is None or spec_obj.loader is None:  # pragma: no cover
        raise DocgenError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec_obj)
    sys.modules["astra_parity_gen"] = module
    spec_obj.loader.exec_module(module)
    # Its own `spec` module, not a second import of the same file: the doc dict
    # and the exception type both have to come from the instance that renders.
    return module, module.spec


#: `docs/en/parity.md` sits at depth 2 under the repo root; this page sits at
#: depth 3. Every repo-relative link the renderer emits therefore gains one
#: level. Anchored on `](` so it cannot touch anything but a link target.
REBASE_RE = re.compile(r"\]\(\.\./\.\./")


def render() -> str:
    parity_gen, parity_spec = _load()
    try:
        doc = parity_spec.load()
    except parity_spec.SpecError as exc:
        raise DocgenError(f"spec/hooks.yaml is malformed: {exc}") from exc

    text = parity_gen.render_parity(doc)
    if "](../../" not in text:
        raise DocgenError(
            "tools/parity/gen.py's parity page no longer emits any `../../` link. The "
            "rebase in tools/docgen/parity.py assumes the renderer writes links relative "
            "to docs/en/; check what it writes them relative to now."
        )
    text = REBASE_RE.sub("](../../../", text)

    # The banner names the generator, and the generator is not this file.
    note = (
        f"<!-- Re-rendered into the reference tier by tools/docgen/parity.py. Same\n"
        f"     renderer, one directory deeper, so the relative links differ and nothing\n"
        f"     else does. Regenerate with `{GEN_CMD}`. -->\n"
    )
    return note + text


def sources() -> list[str]:
    return ["spec/hooks.yaml", "tools/parity/gen.py"]
