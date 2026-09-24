#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""C37, run against trees built to be wrong.

    python3 tools/test_crates_publish.py        # ci.yml's crates-publish job

`tools/check-crates-publish.py` exists because `cli-v0.4.0`'s crates.io job died
on a dependency with a `path` and no `version`. The tree it runs on is fixed, so
a check that only ever reads this tree has never seen the case it is for. Each
test here copies the four crates' manifests (and the vendored crate's sources)
to a temporary directory, bends one thing, and asserts the check goes red for
that reason and no other. `ReleasePreflight` drives `--release cli` with
crates.io and cargo stubbed, for what release-cli.yml is told to upload. No
network. The last test asks cargo itself, when cargo is on PATH, and says
loudly when it is not.
"""

from __future__ import annotations

import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ccp", ROOT / "tools/check-crates-publish.py")
ccp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ccp)

CLI_TOML = "astra-plugin-cli/Cargo.toml"
MANIFEST_DIR = "astra-plugin-cli/vendor/astra-plugin-manifest"
# The line cli-v0.4.0 shipped (AstraPlugins 9f90eef, astra-plugin-cli/Cargo.toml).
V040_LINE = 'astra-plugin-manifest = { path = "vendor/astra-plugin-manifest" }'
DEP_LINE = re.compile(r'^astra-plugin-manifest = \{ version = "([^"]+)", path = "vendor/astra-plugin-manifest" \}$', re.M)


class Tree:
    """A copy of what C37's static leg reads, to be bent."""

    def __enter__(self) -> "Tree":
        self.dir = Path(tempfile.mkdtemp(prefix="c37-"))
        for crate in ccp.CRATES:
            src = ROOT / crate["dir"] / "Cargo.toml"
            dst = self.dir / crate["dir"] / "Cargo.toml"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        shutil.copytree(ROOT / MANIFEST_DIR / "src", self.dir / MANIFEST_DIR / "src")
        shutil.copyfile(ROOT / MANIFEST_DIR / "README.md", self.dir / MANIFEST_DIR / "README.md")
        return self

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def edit(self, rel: str, old: str, new: str) -> None:
        """Replace `old` exactly once, and refuse a no-op: a mutation that
        changed nothing and a check that did not go red look identical."""
        path = self.dir / rel
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise AssertionError(f"{rel}: expected exactly one {old!r}, found {text.count(old)}")
        bent = text.replace(old, new)
        if bent == text:
            raise AssertionError(f"{rel}: the edit changed nothing")
        path.write_text(bent, encoding="utf-8")


def run_static(root: Path) -> tuple[list[str], str]:
    f = ccp.Fails()
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        ccp.static_checks(root, f)
    return f.fails, out.getvalue()


def dep_line() -> str:
    m = DEP_LINE.search((ROOT / CLI_TOML).read_text(encoding="utf-8"))
    if not m:
        raise AssertionError(f"{CLI_TOML} no longer declares the manifest dependency in the shape this test bends")
    return m.group(0)


def dot_crate(files: dict[str, bytes], name: str, version: str) -> bytes:
    """A `.crate` as cargo uploads one: `<name>-<version>/…`, the author's
    manifest as `Cargo.toml.orig` and cargo's rewrite as `Cargo.toml`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        entries = dict(files)
        entries["Cargo.toml.orig"] = entries.pop("Cargo.toml")
        entries["Cargo.toml"] = b"# normalised by cargo; C37 must not read this one\n"
        for rel, data in entries.items():
            info = tarfile.TarInfo(f"{name}-{version}/{rel}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class StaticLeg(unittest.TestCase):
    def test_this_tree_is_green(self) -> None:
        fails, out = run_static(ROOT)
        self.assertEqual(fails, [], out)
        self.assertIn("ok   C37 astra-plugin-cli → astra-plugin-manifest (dependencies) requires ", out,
                      "the edge that broke cli-v0.4.0 was not even read")

    def test_the_cli_v0_4_0_line_is_red(self) -> None:
        with Tree() as t:
            t.edit(CLI_TOML, dep_line(), V040_LINE)
            fails, _ = run_static(t.dir)
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("astra-plugin-cli → astra-plugin-manifest (dependencies) has a version requirement", fails[0])
        self.assertIn("all dependencies must have a version requirement specified", fails[0])

    def test_a_requirement_the_vendored_version_does_not_meet_is_red(self) -> None:
        with Tree() as t:
            line = dep_line()
            t.edit(CLI_TOML, line, line.replace(DEP_LINE.search(line).group(1), "0.2.0", 1))
            fails, _ = run_static(t.dir)
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("requires '0.2.0', which accepts the tree's", fails[0])

    def test_a_vendored_bump_the_requirement_did_not_follow_is_red(self) -> None:
        with Tree() as t:
            t.edit(f"{MANIFEST_DIR}/Cargo.toml", 'version = "0.1.0"', 'version = "0.2.0"')
            fails, _ = run_static(t.dir)
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("astra-plugin-cli → astra-plugin-manifest", fails[0])

    def test_the_wrong_licence_is_red_both_ways(self) -> None:
        with Tree() as t:
            t.edit(f"{MANIFEST_DIR}/Cargo.toml", 'license = "MPL-2.0"', 'license = "GPL-3.0-or-later"')
            t.edit(CLI_TOML, 'license = "GPL-3.0-or-later"', 'license = "MPL-2.0"')
            fails, _ = run_static(t.dir)
        self.assertEqual(sorted(x.split(" — ")[0] for x in fails),
                         ["C37 astra-plugin-cli is licensed GPL-3.0-or-later",
                          "C37 astra-plugin-manifest is licensed MPL-2.0"])

    def test_a_missing_repository_is_red(self) -> None:
        with Tree() as t:
            t.edit(f"{MANIFEST_DIR}/Cargo.toml", 'repository = "https://github.com/mihailinl/AstraPlugins"\n', "")
            fails, _ = run_static(t.dir)
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("astra-plugin-manifest has a `repository`", fails[0])

    def test_publishing_the_cli_before_its_dependency_is_red(self) -> None:
        order = list(ccp.CRATES)
        cli = next(c for c in order if c["name"] == "astra-plugin-cli")
        swapped = [c for c in order if c is not cli]
        swapped.insert(swapped.index(next(c for c in swapped if c["name"] == ccp.REUSED)), cli)
        saved, ccp.CRATES = ccp.CRATES, swapped
        try:
            fails, _ = run_static(ROOT)
        finally:
            ccp.CRATES = saved
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("astra-plugin-manifest is published before astra-plugin-cli", fails[0])

    def test_a_path_to_a_crate_nobody_publishes_is_red(self) -> None:
        with Tree() as t:
            line = dep_line()
            t.edit(CLI_TOML, line, line.replace('path = "vendor/astra-plugin-manifest"', 'path = "vendor/elsewhere"'))
            fails, _ = run_static(t.dir)
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("points at a crate this tree publishes", fails[0])

    def test_a_path_only_dev_dependency_is_allowed_and_a_path_only_dependency_is_not(self) -> None:
        # astra-plugin-macros has one today (`astra-plugin-sdk`, for its tests):
        # cargo strips it at publish. The same line under [dependencies] is 0.4.0's.
        macros = "astra-plugin-macros/Cargo.toml"
        text = (ROOT / macros).read_text(encoding="utf-8")
        self.assertIn('astra-plugin-sdk = { path = "../astra-plugin-sdk" }', text,
                      "the committed tree no longer has the case this test is about")
        fails, _ = run_static(ROOT)
        self.assertEqual(fails, [])
        with Tree() as t:
            t.edit(macros, "[dependencies]\n", '[dependencies]\nastra-plugin-manifest = { path = "../astra-plugin-cli/vendor/astra-plugin-manifest" }\n')
            fails, _ = run_static(t.dir)
        self.assertTrue(any("astra-plugin-macros → astra-plugin-manifest (dependencies) has a version requirement" in x
                            for x in fails), fails)


class Requirements(unittest.TestCase):
    def test_cargo_caret_and_exact(self) -> None:
        cases = [("0.1.0", "0.1.0", True), ("0.1.0", "0.1.7", True), ("0.1.0", "0.2.0", False),
                 ("0.7.2", "0.7.1", False), ("0.7.2", "0.7.9", True), ("1.2.3", "1.9.0", True),
                 ("1.2.3", "2.0.0", False), ("0.0.3", "0.0.4", False), ("=0.7.1", "0.7.1", True),
                 ("=0.7.1", "0.7.2", False), ("^0.7.2", "0.7.2", True)]
        for req, ver, want in cases:
            self.assertIs(ccp.accepts(req, ver), want, f"{req!r} vs {ver}")
        for req in (">=0.1", "0.1", "~0.1.0", "*"):
            self.assertIsNone(ccp.accepts(req, "0.1.0"), f"{req!r} must be refused, not guessed")


class PublishedCopy(unittest.TestCase):
    """The crates.io leg for the one crate a CLI release may skip."""

    def compare(self, published: dict[str, bytes]) -> list[str]:
        crate = next(c for c in ccp.CRATES if c["name"] == ccp.REUSED)
        tree = ccp.tree_files(ROOT, crate)
        f = ccp.Fails()
        blob = dot_crate(published, ccp.REUSED, "0.1.0")
        with redirect_stdout(io.StringIO()):
            ccp.compare_published(tree, ccp.crate_files(blob, ccp.REUSED, "0.1.0"), "0.1.0", f)
        return f.fails

    def tree(self) -> dict[str, bytes]:
        crate = next(c for c in ccp.CRATES if c["name"] == ccp.REUSED)
        return ccp.tree_files(ROOT, crate)

    def test_the_same_bytes_are_green(self) -> None:
        self.assertEqual(self.compare(self.tree()), [])

    def test_a_comment_in_cargo_toml_is_not_behaviour(self) -> None:
        files = self.tree()
        files["Cargo.toml"] = b"# an older comment\n" + files["Cargo.toml"]
        self.assertEqual(self.compare(files), [])

    def test_a_synced_source_without_a_bump_is_red(self) -> None:
        files = self.tree()
        self.assertIn("src/manifest.rs", files)
        files["src/manifest.rs"] = files["src/manifest.rs"] + b"\n// synced from Astra, version not bumped\n"
        fails = self.compare(files)
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("src/manifest.rs", fails[0])

    def test_a_new_source_file_is_red(self) -> None:
        files = self.tree()
        files["src/signing.rs"] = b"pub fn new_module() {}\n"
        self.assertIn("src/signing.rs", self.compare(files)[0])

    def test_a_changed_dependency_is_red(self) -> None:
        files = self.tree()
        old = b'semver = "1"'
        self.assertEqual(files["Cargo.toml"].count(old), 1)
        files["Cargo.toml"] = files["Cargo.toml"].replace(old, b'semver = "0.9"')
        self.assertIn("Cargo.toml [dependencies]", self.compare(files)[0])


class ReleasePreflight(unittest.TestCase):
    """`--release cli`'s decisions, with crates.io and cargo stubbed: what it
    refuses, what it dry-runs with which patch, and what it tells the job."""

    def run_release(self, on_io: dict[str, list[str] | None], manifest_blob: bytes | None = None):
        calls: list[tuple[str, list[str]]] = []
        saved = (ccp.crates_io_versions, ccp.dry_run, ccp.fetch)
        ccp.crates_io_versions = lambda name: on_io.get(name)
        ccp.dry_run = lambda root, crate, patched, f: calls.append((crate["name"], list(patched)))
        ccp.fetch = lambda url: (200, manifest_blob) if manifest_blob is not None else (404, b"")
        out_file = Path(tempfile.mkdtemp(prefix="c37-out-")) / "out"
        old_env = os.environ.get("GITHUB_OUTPUT")
        os.environ["GITHUB_OUTPUT"] = str(out_file)
        try:
            with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
                rc = ccp.main(["--release", "cli"])
        finally:
            ccp.crates_io_versions, ccp.dry_run, ccp.fetch = saved
            if old_env is None:
                os.environ.pop("GITHUB_OUTPUT", None)
            else:
                os.environ["GITHUB_OUTPUT"] = old_env
        outputs = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
        shutil.rmtree(out_file.parent, ignore_errors=True)
        return rc, calls, outputs, out.getvalue()

    def sdk_version(self) -> str:
        return str(ccp.load(ROOT, next(c for c in ccp.CRATES if c["name"] == "astra-plugin-sdk"))["package"]["version"])

    def test_no_sdk_on_crates_io_stops_before_any_dry_run_or_upload(self) -> None:
        rc, calls, outputs, text = self.run_release({"astra-plugin-sdk": ["0.7.1"]})
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])
        self.assertEqual(outputs, "", "the job must not be told to upload anything")
        self.assertIn(f"push `sdk-v{self.sdk_version()}`", text)

    def test_first_upload_dry_runs_the_manifest_then_the_cli_against_it(self) -> None:
        rc, calls, outputs, _ = self.run_release({"astra-plugin-sdk": [self.sdk_version()]})
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [("astra-plugin-manifest", []), ("astra-plugin-cli", ["astra-plugin-manifest"])],
                         "the SDK must come from crates.io, never from the tree, in a release")
        self.assertIn("publish_manifest=true", outputs)

    def test_a_manifest_already_published_as_these_bytes_is_not_uploaded_again(self) -> None:
        crate = next(c for c in ccp.CRATES if c["name"] == ccp.REUSED)
        version = str(ccp.load(ROOT, crate)["package"]["version"])
        blob = dot_crate(ccp.tree_files(ROOT, crate), ccp.REUSED, version)
        rc, calls, outputs, _ = self.run_release(
            {"astra-plugin-sdk": [self.sdk_version()], ccp.REUSED: [version]}, blob)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [("astra-plugin-cli", [])])
        self.assertIn("publish_manifest=false", outputs)

    def test_a_manifest_already_published_as_other_bytes_stops_the_release(self) -> None:
        crate = next(c for c in ccp.CRATES if c["name"] == ccp.REUSED)
        version = str(ccp.load(ROOT, crate)["package"]["version"])
        files = ccp.tree_files(ROOT, crate)
        files["src/lib.rs"] = files["src/lib.rs"] + b"\n// the older parser\n"
        rc, calls, outputs, _ = self.run_release(
            {"astra-plugin-sdk": [self.sdk_version()], ccp.REUSED: [version]},
            dot_crate(files, ccp.REUSED, version))
        self.assertEqual(rc, 1)
        self.assertEqual(calls, [])
        self.assertEqual(outputs, "")


class CargoAgrees(unittest.TestCase):
    """The static rule is cargo's rule: cargo itself refuses 0.4.0's line."""

    def test_cargo_refuses_the_cli_v0_4_0_line(self) -> None:
        if shutil.which("cargo") is None:
            print("\nNOT ASKED C37 cargo is not on PATH, so cargo's own refusal was not observed here;"
                  " the crates-publish job runs this test with cargo", file=sys.stderr)
            self.skipTest("cargo not on PATH")
        work = Path(tempfile.mkdtemp(prefix="c37-cargo-"))
        try:
            skip = shutil.ignore_patterns("target")
            for d in ("astra-plugin-cli", "astra-plugin-sdk", "astra-plugin-macros"):
                shutil.copytree(ROOT / d, work / d, ignore=skip)
            toml = work / CLI_TOML
            text = toml.read_text(encoding="utf-8")
            line = dep_line()
            self.assertEqual(text.count(line), 1)
            toml.write_text(text.replace(line, V040_LINE), encoding="utf-8")
            # `--no-verify --offline`: the refusal is in manifest preparation,
            # before resolution and before any compile, so this costs a second.
            # (`cargo package --list` exits 0 on this very manifest.)
            proc = subprocess.run(["cargo", "package", "--no-verify", "--offline", "--allow-dirty"],
                                  cwd=work / "astra-plugin-cli", text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertNotEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("dependency `astra-plugin-manifest` does not specify a version", proc.stdout)
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
