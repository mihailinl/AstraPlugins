#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""C37 — every crate this tree ships to crates.io publishes, in the order the releases push it.

    python3 tools/check-crates-publish.py               # the `crates-publish` CI job
    python3 tools/check-crates-publish.py --static-only # manifests only: no cargo, no network
    python3 tools/check-crates-publish.py --release cli # release-cli.yml, before any upload

`cli-v0.2.1`, `cli-v0.3.0` and `cli-v0.4.0` (runs 31876142869, 32689129887,
35969044932) each released their binaries and then failed the crates.io job at
the first step that asks cargo anything:

    all dependencies must have a version requirement specified when publishing.
    dependency `astra-plugin-manifest` does not specify a version

The CLI depended on its vendored manifest crate by `path` alone. Nothing on a
pull request ever ran `cargo publish`, so the defect lived from the day the crate
was vendored (ee0390a, 2026-08-10) through three release tags. `release-cli.yml`
even said so in a comment, dated 2026-08-15, and a comment is not a check. The
SDK job's
`cargo package --list` step could not have caught it either: `--list` exits 0 on
exactly this manifest (measured with cargo 1.97, 2026-09-24). This file is the
check.

What it asks, in order:

STATIC (no cargo, no network — the test bends these):
  - each crate's `[package]` names itself, carries the licence CLAUDE.md gives
    it (MPL-2.0 for what ends up inside a plugin, GPL-3.0-or-later for the CLI),
    and the metadata crates.io shows: description, repository;
  - every dependency with a `path` also has a `version` (dev-dependencies with
    `path` alone are stripped by cargo at publish, so they are allowed), the
    path is another crate in `CRATES`, the requirement accepts that crate's own
    version, and that crate is published EARLIER in `CRATES`.

CARGO (the CI job):
  - `cargo publish --dry-run` for each crate in `CRATES` order, exactly as its
    release runs it (`--locked` where the release passes it). An in-tree
    dependency that the same train publishes first is not on crates.io yet, so
    the dry run is pointed at the tree's copy with `--config patch.crates-io`,
    the way `cargo publish --workspace` overlays unpublished members. The
    requirement still has to accept the tree's version or the patch goes unused
    and resolution fails, so a mismatch stays red.

CRATES.IO (the CI job and the release):
  - which in-tree requirement crates.io cannot satisfy yet is printed as the
    release order, never failed on a pull request: a version bumped ahead of
    its release is the normal state of this tree;
  - `astra-plugin-manifest` only: when crates.io already has the vendored
    version, its `src/**`, README and dependency tables are the vendored ones.
    The CLI's release skips a manifest version crates.io already holds, so a
    sync that changed `src/` without a bump would ship a crates.io CLI built
    against the older parser, silently.

`--release cli` is the same checks narrowed to what `release-cli.yml` is about
to do: every dependency another train publishes (the SDK) must already be on
crates.io, and the output says whether the manifest crate is to be published.

Exit 0 when every check passes, 1 when one fails, 2 when a check could not be
run (crates.io answered neither a document nor a 404, or cargo was missing).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "AstraPlugins CI (github.com/mihailinl/AstraPlugins)"}

# Publish order. A crate may depend only on crates ABOVE it. `train` is the
# release workflow that uploads it; `locked` is whether that workflow passes
# `--locked` (release-sdks.yml does not, release-cli.yml does).
CRATES = [
    {"name": "astra-plugin-macros", "dir": "astra-plugin-macros", "license": "MPL-2.0",
     "train": "sdk", "locked": False},
    {"name": "astra-plugin-sdk", "dir": "astra-plugin-sdk", "license": "MPL-2.0",
     "train": "sdk", "locked": False},
    {"name": "astra-plugin-manifest", "dir": "astra-plugin-cli/vendor/astra-plugin-manifest",
     "license": "MPL-2.0", "train": "cli", "locked": True},
    {"name": "astra-plugin-cli", "dir": "astra-plugin-cli", "license": "GPL-3.0-or-later",
     "train": "cli", "locked": True},
]
TAG = {"sdk": "sdk-v", "cli": "cli-v"}
# The one crate a release publishes only when crates.io lacks its version.
REUSED = "astra-plugin-manifest"
DEP_TABLES = ("dependencies", "build-dependencies", "dev-dependencies")
SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class Fails:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.oks = 0

    def check(self, ok: bool, what: str, why: str = "") -> bool:
        if ok:
            self.oks += 1
            print(f"ok   C37 {what}")
        else:
            self.fails.append(f"C37 {what}" + (f" — {why}" if why else ""))
            print(f"FAIL C37 {what}" + (f" — {why}" if why else ""))
        return ok


def load(root: Path, crate: dict) -> dict:
    return tomllib.loads((root / crate["dir"] / "Cargo.toml").read_text(encoding="utf-8"))


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = SEMVER.fullmatch(text.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def accepts(req: str, version: str) -> bool | None:
    """Cargo's reading of `req` against `version`, for the two shapes this tree
    uses: a bare `X.Y.Z` (caret) and `=X.Y.Z`. Anything else is None — refused
    rather than guessed, so a new shape is a loud failure and not a quiet pass."""
    v = parse_version(version)
    if v is None:
        return None
    req = req.strip()
    if req.startswith("="):
        r = parse_version(req[1:])
        return None if r is None else v == r
    r = parse_version(req[1:] if req.startswith("^") else req)
    if r is None:
        return None
    if v < r:
        return False
    if r[0] > 0:
        return v[0] == r[0]
    if r[1] > 0:
        return v[0] == 0 and v[1] == r[1]
    return v == r


def path_deps(manifest: dict) -> list[tuple[str, str, dict]]:
    """(table, dependency name, spec) for every dependency with a `path`,
    target-specific tables included."""
    out = []
    tables = [(t, manifest.get(t) or {}) for t in DEP_TABLES]
    for target, sub in (manifest.get("target") or {}).items():
        tables += [(f"target.{target}.{t}", sub.get(t) or {}) for t in DEP_TABLES]
    for table, deps in tables:
        for name, spec in deps.items():
            if isinstance(spec, dict) and "path" in spec:
                out.append((table, spec.get("package", name), spec))
    return out


def static_checks(root: Path, f: Fails) -> dict[str, list[str]]:
    """Returns crate name -> the in-tree crates its published manifest depends on."""
    f.check(len(CRATES) == 4, "the publish list names the four crates this tree uploads",
            f"it names {len(CRATES)}; a crate added to crates.io is added here, in order")
    by_dir = {(root / c["dir"]).resolve(): c for c in CRATES}
    position = {c["name"]: i for i, c in enumerate(CRATES)}
    versions = {}
    edges: dict[str, list[str]] = {}
    for crate in CRATES:
        m = load(root, crate)
        pkg = m.get("package") or {}
        name = crate["name"]
        versions[name] = str(pkg.get("version", ""))
        f.check(pkg.get("name") == name, f"{crate['dir']}/Cargo.toml is {name}",
                f"[package].name reads {pkg.get('name')!r}")
        f.check(parse_version(versions[name]) is not None, f"{name}'s version {versions[name]!r} is X.Y.Z")
        f.check(pkg.get("license") == crate["license"], f"{name} is licensed {crate['license']}",
                f"[package].license reads {pkg.get('license')!r}; CLAUDE.md gives this crate "
                f"{crate['license']}")
        for field in ("description", "repository"):
            f.check(bool(str(pkg.get(field, "")).strip()), f"{name} has a `{field}`",
                    "crates.io shows it, and cargo warns at publish without it")
        f.check(pkg.get("publish", True) is not False, f"{name} is publishable",
                "`publish = false` in a crate a release uploads")
    for crate in CRATES:
        name = crate["name"]
        edges[name] = []
        for table, dep, spec in path_deps(load(root, crate)):
            target = by_dir.get((root / crate["dir"] / spec["path"]).resolve())
            where = f"{name} → {dep} ({table})"
            if "version" not in spec:
                # Cargo strips a path-only dev-dependency from the published
                # manifest; everywhere else a missing version is the 0.4.0 defect.
                if table.endswith("dev-dependencies"):
                    print(f"note C37 {where} is path-only; cargo strips it at publish")
                    continue
                f.check(False, f"{where} has a version requirement",
                        "all dependencies must have a version requirement specified when "
                        "publishing — the error cli-v0.4.0's crates.io job died on. Add "
                        f"`version = \"{versions.get(dep, '<its version>')}\"` beside the path")
                continue
            if not f.check(target is not None and target["name"] == dep,
                           f"{where} points at a crate this tree publishes",
                           f"path {spec['path']!r} is not one of {[c['dir'] for c in CRATES]}"):
                continue
            ok = accepts(str(spec["version"]), versions[dep])
            f.check(ok is True, f"{where} requires {spec['version']!r}, which accepts the tree's {versions[dep]}",
                    "an unreadable requirement" if ok is None else
                    "cargo would resolve crates.io's copy, not this one")
            f.check(position[dep] < position[name], f"{where}: {dep} is published before {name}",
                    f"move it above {name} in CRATES, and in the release that uploads them")
            if not table.endswith("dev-dependencies"):
                edges[name].append(dep)
    return edges


def closure(edges: dict[str, list[str]], name: str) -> list[str]:
    seen: list[str] = []
    stack = list(edges.get(name, []))
    while stack:
        dep = stack.pop()
        if dep not in seen:
            seen.append(dep)
            stack += edges.get(dep, [])
    return [c["name"] for c in CRATES if c["name"] in seen]


def fetch(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def crates_io_versions(name: str) -> list[str] | None:
    """Unyanked versions on crates.io, or None when the crate does not exist."""
    status, body = fetch(f"https://crates.io/api/v1/crates/{name}")
    if status == 404:
        return None
    if status != 200:
        raise SystemExit(f"C37 could not ask crates.io about {name}: HTTP {status}; "
                         "refusing to guess (exit 2)")
    return [v["num"] for v in json.loads(body)["versions"] if not v.get("yanked")]


def behaviour(files: dict[str, bytes]) -> dict[str, object]:
    """What a published manifest crate does: its sources, its README, and the
    dependency and feature tables of its original Cargo.toml. Comments and
    metadata may differ between two uploads of one version; these may not."""
    out: dict[str, object] = {k: v for k, v in files.items()
                              if k.startswith("src/") or k == "README.md"}
    manifest = tomllib.loads(files["Cargo.toml"].decode("utf-8"))
    for key in DEP_TABLES + ("features", "target"):
        out[f"Cargo.toml [{key}]"] = json.dumps(manifest.get(key), sort_keys=True)
    return out


def tree_files(root: Path, crate: dict) -> dict[str, bytes]:
    base = root / crate["dir"]
    out = {"Cargo.toml": (base / "Cargo.toml").read_bytes(),
           "README.md": (base / "README.md").read_bytes()}
    for p in sorted((base / "src").rglob("*")):
        if p.is_file():
            out[p.relative_to(base).as_posix()] = p.read_bytes()
    return out


def crate_files(blob: bytes, name: str, version: str) -> dict[str, bytes]:
    """The files of a `.crate` as uploaded, keyed as in the tree. The upload's
    `Cargo.toml` is cargo's rewrite; `Cargo.toml.orig` is the author's file."""
    prefix = f"{name}-{version}/"
    out: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith(prefix):
                continue
            rel = member.name[len(prefix):]
            data = tar.extractfile(member).read()
            if rel == "Cargo.toml.orig":
                out["Cargo.toml"] = data
            elif rel != "Cargo.toml":
                out[rel] = data
    return out


def compare_published(tree: dict[str, bytes], published: dict[str, bytes], version: str,
                      f: Fails) -> None:
    want, got = behaviour(tree), behaviour(published)
    differ = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
    f.check(not differ, f"crates.io's {REUSED} {version} is the vendored crate",
            f"these differ: {', '.join(differ)}. The CLI's release skips a version crates.io "
            f"already has, so bump the vendored crate's `version` and the CLI's requirement "
            f"on it, or the crates.io CLI ships the older parser")


def reused_crate_check(root: Path, versions_on_io: list[str] | None, f: Fails) -> bool:
    """True when the release must upload the manifest crate."""
    crate = next(c for c in CRATES if c["name"] == REUSED)
    version = str(load(root, crate)["package"]["version"])
    if versions_on_io is None or version not in versions_on_io:
        print(f"note C37 crates.io has no {REUSED} {version}; the CLI release uploads it first")
        return True
    status, blob = fetch(f"https://static.crates.io/crates/{REUSED}/{REUSED}-{version}.crate")
    if status != 200:
        raise SystemExit(f"C37 could not download {REUSED} {version}: HTTP {status} (exit 2)")
    compare_published(tree_files(root, crate), crate_files(blob, REUSED, version), version, f)
    return False


def dry_run(root: Path, crate: dict, patched: list[str], f: Fails) -> None:
    if shutil.which("cargo") is None:
        raise SystemExit("C37 needs cargo on PATH for the dry runs (exit 2)")
    cmd = ["cargo", "publish", "--dry-run"] + (["--locked"] if crate["locked"] else [])
    for dep in patched:
        path = (root / next(c for c in CRATES if c["name"] == dep)["dir"]).resolve()
        cmd += ["--config", f"patch.crates-io.{dep}.path={json.dumps(str(path))}"]
    shown = " ".join(c for c in cmd if not c.startswith(("--config", "patch.")))
    print(f"::group::{crate['name']}: {shown}" + (f" (patched: {', '.join(patched)})" if patched else ""))
    # A child cargo must not inherit a token it does not need. `--dry-run`
    # authenticates nothing (measured with cargo 1.97, no credential present),
    # and it compiles every dependency's build.rs.
    env = {k: v for k, v in os.environ.items() if not k.startswith("CARGO_REGISTRY_TOKEN")
           and not k.startswith("CARGO_REGISTRIES_")}
    proc = subprocess.run(cmd, cwd=root / crate["dir"], env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout.rstrip())
    print("::endgroup::")
    tail = [l for l in proc.stdout.splitlines() if l.strip()][-6:]
    f.check(proc.returncode == 0, f"`cargo publish --dry-run` succeeds for {crate['name']}",
            f"exit {proc.returncode}: " + " | ".join(tail))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--root", default=str(ROOT), help="the tree to check (default: this checkout)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--static-only", action="store_true", help="manifests only: no cargo, no network")
    g.add_argument("--release", choices=["cli"], help="the preflight of that release's crates.io job")
    args = ap.parse_args(argv)
    root = Path(args.root)
    f = Fails()

    edges = static_checks(root, f)
    if f.fails or args.static_only:
        if args.static_only:
            print("note C37's cargo and crates.io legs NOT run (--static-only)")
        return report(f)

    on_io = {c["name"]: crates_io_versions(c["name"]) for c in CRATES}
    tree_v = {c["name"]: str(load(root, c)["package"]["version"]) for c in CRATES}
    upload_manifest = reused_crate_check(root, on_io[REUSED], f)

    if args.release == "cli":
        todo = [c for c in CRATES if c["train"] == "cli"]
        # This job uploads the manifest crate (when crates.io lacks it) and then
        # the CLI. Every other in-tree dependency is another train's upload and
        # has to be on crates.io already, or the CLI's publish fails after the
        # manifest crate has gone up.
        for crate in todo:
            for dep in edges[crate["name"]]:
                if next(c for c in CRATES if c["name"] == dep)["train"] == "cli":
                    continue
                req = next(s["version"] for t, n, s in path_deps(load(root, crate)) if n == dep)
                have = [v for v in (on_io[dep] or []) if accepts(str(req), v)]
                train = next(c for c in CRATES if c["name"] == dep)["train"]
                f.check(bool(have), f"crates.io can satisfy {crate['name']}'s {dep} {req!r}",
                        f"crates.io has {sorted(on_io[dep] or [], key=parse_version)[-3:] or 'nothing'}; "
                        f"push `{TAG[train]}{tree_v[dep]}` and let it finish first. Nothing was uploaded.")
        if f.fails:
            return report(f)
        for crate in todo:
            if crate["name"] == REUSED and not upload_manifest:
                print(f"note C37 {REUSED} {tree_v[REUSED]} is already on crates.io and is the vendored crate; not uploaded again")
                continue
            patched = [d for d in closure(edges, crate["name"]) if d == REUSED and upload_manifest]
            dry_run(root, crate, patched, f)
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(f"publish_manifest={'true' if upload_manifest else 'false'}\n")
                fh.write(f"manifest_version={tree_v[REUSED]}\n")
        print(f"release cli: {'upload' if upload_manifest else 'skip'} {REUSED} {tree_v[REUSED]}, "
              f"then astra-plugin-cli {tree_v['astra-plugin-cli']}")
        return report(f)

    # The CI job: every crate, in order, each in-tree dependency the tree's copy.
    print("\nrelease order (what crates.io lacks today, in the order it must go up):")
    for crate in CRATES:
        name, v = crate["name"], tree_v[crate["name"]]
        state = "on crates.io" if v in (on_io[name] or []) else "NOT on crates.io"
        print(f"  {name:<24} {v:<8} {state:<17} ← {TAG[crate['train']]}<version>")
    print()
    for crate in CRATES:
        dry_run(root, crate, closure(edges, crate["name"]), f)
    return report(f)


def report(f: Fails) -> int:
    if f.fails:
        print(f"\n{len(f.fails)} C37 check(s) failed:", file=sys.stderr)
        for x in f.fails:
            print("  " + x, file=sys.stderr)
        return 1
    print(f"C37: {f.oks} checks pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
