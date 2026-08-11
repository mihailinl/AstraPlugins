#!/usr/bin/env python3
"""Render `docs/en/reference/` from the sources it describes.

    python3 tools/docgen/gen.py            # write the files
    python3 tools/docgen/gen.py --check    # fail if the checked-in copies differ
    python3 tools/docgen/gen.py --only cli # one page, while iterating

Pages, and what each is a function of:

    reference/cli.md       the `astra-plugin` binary's own clap help, executed,
                           plus the two facts clap never prints (aliases and
                           hidden args), scanned from main.rs and verified
                           against the binary
    reference/manifest.md  the vendored `astra-plugin-manifest` crate — the same
                           code the daemon parses `plugin.toml` with
    reference/protocol.md  proto/plugin.proto, plus the per-RPC permission
                           column from spec/hooks.yaml (which parity rule R6
                           pins to the daemon's own HOST_RPC_PERMISSIONS)
    reference/errors.md    the `PluginErrorCode` enum in the proto and the three
                           SDKs' error taxonomies
    reference/parity.md    rendered by tools/parity/gen.py, which owns the hook
                           spec — called here, not reimplemented
    reference/README.md    the index, listing each page and its source

WHY A GENERATOR AND NOT A PAGE

The audit that produced this directory found ~28 factually false claims in
`docs/en`, all of the same shape: a page written once, describing an interface
that moved nine commits later. Prose can be reviewed; a table of flags cannot,
because nobody re-reads a flag table against the source. Everything a machine
can derive is derived, so the only documentation a human has to keep true is
the documentation only a human could have written.

`--check` is what makes that real. CI runs it, and a checked-in page that is
not what a fresh run produces fails the build with a diff.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cli as cli_page  # noqa: E402
import errors as errors_page  # noqa: E402
import manifest as manifest_page  # noqa: E402
import parity as parity_page  # noqa: E402
import protocol as protocol_page  # noqa: E402
from common import DocgenError, REFERENCE_DIR, REPO_ROOT, check_links  # noqa: E402

#: name -> (output file, renderer). The index renders last: it reads the others.
PAGES = {
    "cli": ("cli.md", cli_page.render),
    "manifest": ("manifest.md", manifest_page.render),
    "protocol": ("protocol.md", protocol_page.render),
    "errors": ("errors.md", errors_page.render),
    "parity": ("parity.md", parity_page.render),
}


def index(rendered: dict[str, str]) -> str:
    """`reference/README.md` — what is here, and what each page is derived from."""
    from common import banner

    rows = [
        ("cli.md", "`astra-plugin`: every command, argument and flag", "the CLI binary's `clap` definitions"),
        ("manifest.md", "`plugin.toml`: every section and field", "`astra-plugin-cli/vendor/astra-plugin-manifest`"),
        ("protocol.md", "the gRPC surface: services, RPCs, streaming, permissions", "`proto/plugin.proto` + `spec/hooks.yaml`"),
        ("errors.md", "the error taxonomy, in all three SDKs", "the proto enum + each SDK's error module"),
        ("parity.md", "which hook is bound in which SDK", "`spec/hooks.yaml`"),
    ]
    out = [
        banner("gen.py", ["the five pages listed below, and their own sources"]),
        "# Reference",
        "",
        "Generated. Every page in this directory is a function of source code in this "
        "repository, re-rendered by `python3 tools/docgen/gen.py` and drift-checked in CI "
        "by the same command with `--check`. Editing one by hand fails the build.",
        "",
        "That is the point: the reference tier is the part of the documentation nobody "
        "re-reads against the source, so it is the part that must not depend on anybody "
        "doing so.",
        "",
        "| Page | What it answers | Derived from |",
        "|---|---|---|",
    ]
    for filename, what, source in rows:
        if filename[:-3] not in rendered:
            raise DocgenError(
                f"the index lists {filename}, which no generator produced. PAGES and the "
                f"index rows have to name the same set of pages."
            )
        out.append(f"| [`{filename}`](./{filename}) | {what} | {source} |")
    out += [
        "",
        "## What is not here",
        "",
        "**Prose.** Anything that explains *why*, or walks you through something, is "
        "hand-written and lives outside this directory. A generator has no opinions.",
        "",
        "**Anything unverified.** A page here states only what its generator could read "
        "out of source. Where a fact lives in the Astra daemon rather than in this "
        "repository — the permission each host RPC is gated on, for instance — the page "
        "says which checked-in file carries it and which parity rule pins that file to "
        "the daemon.",
        "",
    ]
    return "\n".join(out).rstrip() + "\n"


def render_all(only: str | None) -> dict[Path, str]:
    rendered: dict[str, str] = {}
    out: dict[Path, str] = {}
    for name, (filename, renderer) in PAGES.items():
        if only and name != only:
            continue
        text = renderer()
        rendered[name] = text
        out[REFERENCE_DIR / filename] = text
    if not only:
        out[REFERENCE_DIR / "README.md"] = index(rendered)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    parser.add_argument("--only", choices=sorted(PAGES), help="render one page")
    args = parser.parse_args(argv)

    try:
        artefacts = render_all(args.only)
    except DocgenError as exc:
        print(f"docgen: {exc}", file=sys.stderr)
        return 2

    stale = 0
    for path, content in sorted(artefacts.items()):
        rel = path.relative_to(REPO_ROOT)
        try:
            check_links(path, content)
        except DocgenError as exc:
            print(f"docgen: {exc}", file=sys.stderr)
            return 2
        if args.check:
            on_disk = path.read_text(encoding="utf-8") if path.exists() else ""
            if on_disk != content:
                stale += 1
                print(f"STALE  {rel}", file=sys.stderr)
                sys.stderr.writelines(
                    difflib.unified_diff(
                        on_disk.splitlines(True),
                        content.splitlines(True),
                        fromfile=f"{rel} (checked in)",
                        tofile=f"{rel} (generated)",
                    )
                )
            else:
                print(f"ok     {rel}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote  {rel}")

    if stale:
        print(
            f"\n{stale} generated page(s) do not match their sources. This is not a "
            f"formatting nit: the checked-in reference describes an interface that has "
            f"moved. Run `python3 tools/docgen/gen.py` and commit the result.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
