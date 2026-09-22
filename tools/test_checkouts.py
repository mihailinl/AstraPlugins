#!/usr/bin/env python3
"""C22 and C35 hold the daemon's tree to the top-level `astra-rs/` of its own checkout.

    python3 tools/test_checkouts.py        # what the `couplings` job runs

`tools/checkouts.py` is the rule, and this runs it the way its callers do. C22 is
run as `tools/check-locales.py` in a subprocess — as `proto-upstream` runs it —
against Astra-shaped git repositories built in a temporary directory; C35's daemon
label (`_git_head` in tools/check-registry-mirrors.py) is asked directly.

The case this exists for is an `_astra` whose `.git` went missing, which leaves it
enclosed by the AstraPlugins checkout: `git -C` searches upward, and C22 used to
read that repository's tags as the daemon's (ops register, entry 115). No CI run
has ever had such an `_astra`, so no CI run could have shown what C22 does with
one; the fixtures below are the only place the case exists. Each is checked to be
the layout it claims before anything is asserted about it.

No Astra, no token, no network — which is why it runs in `couplings`, on every
pull request including a fork's, and not in `proto-upstream`'s full mode.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from checkouts import DAEMON_IN_REPO  # noqa: E402  (sys.path is set above)

#: The fewest tests a run may report before it is a broken file rather than a
#: pass. The count of test methods below; raise it when you add one.
MIN_TESTS = 8

#: What C22's refusal says about a tree inside some other checkout.
NOT_TOP = f"in a git checkout, but not as its top-level {DAEMON_IN_REPO}/"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LOCALES = _load("check_locales", "check-locales.py")
MIRRORS = _load("check_registry_mirrors", "check-registry-mirrors.py")


class DaemonTreeIsItsOwnCheckout(unittest.TestCase):
    tmp: Path
    env: dict[str, str]
    tag: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="checkouts-")).resolve()
        cls.env = dict(os.environ)
        for k in ("ASTRA_RS_DIR", "ASTRA_REGISTRY_DIR", "GIT_DIR", "GIT_WORK_TREE"):
            cls.env.pop(k, None)
        cls.env.update({
            # git must not find a repository above the fixtures, whatever the
            # temporary directory happens to sit in, or "in no checkout" is not.
            "GIT_CEILING_DIRECTORIES": str(cls.tmp),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        })
        floor = LOCALES.SCAFFOLD_FLOOR_RE.search(
            (ROOT / LOCALES.SCAFFOLD_FLOOR_FILE).read_text(encoding="utf-8"))
        assert floor, f"no LABEL_RESOLVER_RELEASE in {LOCALES.SCAFFOLD_FLOOR_FILE}"
        cls.tag = f"v{floor.group(1)}"

        # An Astra: astra-rs/ at its top, the resolver in the release the
        # scaffold names, and the named ref C22 anchors on.
        astra = cls.tmp / "astra"
        (astra / DAEMON_IN_REPO / "astra-core").mkdir(parents=True)
        (astra / DAEMON_IN_REPO / "astra-core" / "README").write_text("fixture\n")
        resolver = astra / LOCALES.RESOLVER_FILE
        resolver.parent.mkdir(parents=True)
        resolver.write_text(f"pub fn {LOCALES.RESOLVER_SYMBOL}() {{}}\n")
        cls.git("init", "-q", "-b", "main", str(astra))
        cls.git("-C", str(astra), "add", "-A")
        cls.git("-C", str(astra), "commit", "-q", "-m", "an Astra")
        cls.git("-C", str(astra), "tag", "-a", cls.tag, "-m", cls.tag)
        cls.git("-C", str(astra), "update-ref", "refs/remotes/origin/main", "HEAD")

        # The AstraPlugins checkout, with an `_astra` inside it that has no `.git`.
        outer = cls.tmp / "astraplugins"
        outer.mkdir()
        (outer / "README.md").write_text("AstraPlugins, as a fixture\n")
        cls.git("init", "-q", "-b", "master", str(outer))
        cls.git("-C", str(outer), "add", "-A")
        cls.git("-C", str(outer), "commit", "-q", "-m", "AstraPlugins")
        shutil.copytree(astra / DAEMON_IN_REPO, outer / "_astra" / DAEMON_IN_REPO)

        # A copy of astra-rs/ one level deeper inside a real Astra checkout.
        shutil.copytree(astra / DAEMON_IN_REPO, astra / "vendor" / DAEMON_IN_REPO)
        # A clone whose top IS astra-rs/.
        own_top = cls.tmp / "own-top" / DAEMON_IN_REPO
        shutil.copytree(astra / DAEMON_IN_REPO, own_top)
        cls.git("init", "-q", "-b", "main", str(own_top))
        cls.git("-C", str(own_top), "add", "-A")
        cls.git("-C", str(own_top), "commit", "-q", "-m", "astra-rs as its own top")
        # In no checkout at all.
        shutil.copytree(astra / DAEMON_IN_REPO, cls.tmp / "loose" / DAEMON_IN_REPO)
        # A symlink to the real one.
        (cls.tmp / "link").symlink_to(astra / DAEMON_IN_REPO)

        cls.trees = {
            "own": astra / DAEMON_IN_REPO,
            "enclosed": outer / "_astra" / DAEMON_IN_REPO,
            "nested": astra / "vendor" / DAEMON_IN_REPO,
            "own_top": own_top,
            "loose": cls.tmp / "loose" / DAEMON_IN_REPO,
            "link": cls.tmp / "link",
        }
        # Each layout is what it says, or every assertion below is about nothing.
        want_top = {"own": astra, "enclosed": outer, "nested": astra, "own_top": own_top,
                    "loose": None, "link": astra}
        for name, tree in cls.trees.items():
            p = subprocess.run(["git", "-C", str(tree), "rev-parse", "--show-toplevel"],
                               capture_output=True, text=True, env=cls.env)
            got = Path(p.stdout.strip()).resolve() if p.returncode == 0 else None
            assert got == want_top[name], f"fixture {name}: git's top-level is {got}, want {want_top[name]}"
        assert not (outer / "_astra" / ".git").exists()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def git(cls, *args: str) -> str:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                              env=cls.env).stdout.strip()

    def c22(self, tree: Path | None, *extra: str, env_dir: Path | None = None):
        cmd = [sys.executable, str(HERE / "check-locales.py"), "--rules", "C22",
               "--astra-ref", "origin/main", *extra]
        if tree is not None:
            cmd += ["--astra-dir", str(tree)]
        env = dict(self.env)
        if env_dir is not None:
            env["ASTRA_RS_DIR"] = str(env_dir)
        return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=ROOT)

    def passes(self, tree: Path) -> None:
        p = self.c22(tree)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"ok    C22 the release the scaffold requires resolves plugin labels ({self.tag})",
                      p.stdout)

    def refused(self, tree: Path, why: str) -> None:
        p = self.c22(tree)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn(f"is {why}, and {LOCALES.C22_NEEDS_GIT}.", p.stderr)
        # refused BEFORE a tag was read: no verdict of any kind about one
        self.assertNotIn("ok    C22", p.stdout)
        self.assertNotIn("FAIL  C22", p.stdout)

    # ── the control: the fixture is a checkout C22 can pass ─────────────────
    def test_own_checkout_is_read(self) -> None:
        self.passes(self.trees["own"])

    def test_symlink_to_own_checkout_is_that_checkout(self) -> None:
        self.passes(self.trees["link"])

    # ── entry 115 ────────────────────────────────────────────────────────────
    def test_astra_without_git_inside_astraplugins_is_refused(self) -> None:
        self.refused(self.trees["enclosed"], NOT_TOP)

    def test_copy_nested_in_another_astra_checkout_is_refused(self) -> None:
        # Before the fix this one was GREEN: it read the enclosing Astra's tags.
        self.refused(self.trees["nested"], NOT_TOP)

    def test_astra_rs_as_its_own_checkout_top_is_refused(self) -> None:
        self.refused(self.trees["own_top"], NOT_TOP)

    def test_tree_in_no_checkout_is_refused(self) -> None:
        self.refused(self.trees["loose"], "not in a git checkout")

    def test_implicit_tree_is_not_verified_and_require_makes_it_red(self) -> None:
        p = self.c22(None, env_dir=self.trees["enclosed"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"C22 NOT VERIFIED: the Astra tree at {self.trees['enclosed']} is {NOT_TOP},",
                      p.stdout)
        self.assertIn(f"C22 (the Astra tree is {NOT_TOP})", p.stdout)
        self.assertNotIn("ok    C22", p.stdout)
        p = self.c22(None, "--require", "C22", env_dir=self.trees["enclosed"])
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    # ── C35's daemon label, the same rule ────────────────────────────────────
    def test_c35_label_names_only_the_trees_own_checkout(self) -> None:
        old = dict(os.environ)
        os.environ.clear()
        os.environ.update(self.env)
        try:
            head = self.git("-C", str(self.tmp / "astra"), "rev-parse", "--short=12", "HEAD")
            label = lambda name: MIRRORS._git_head(self.trees[name], DAEMON_IN_REPO)  # noqa: E731
            self.assertEqual(label("own"), head)
            self.assertEqual(label("link"), head)
            for name in ("enclosed", "nested", "own_top"):
                self.assertEqual(label(name), f"HEAD unknown: {NOT_TOP}", name)
            self.assertEqual(label("loose"), "HEAD unknown: not in a git checkout")
        finally:
            os.environ.clear()
            os.environ.update(old)


if __name__ == "__main__":
    prog = unittest.main(exit=False, verbosity=2)
    ran = prog.result.testsRun
    if ran < MIN_TESTS:
        print(f"test_checkouts: {ran} test(s) ran, want >= {MIN_TESTS}. A test file that "
              "stopped collecting its tests is not a pass.", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(0 if prog.result.wasSuccessful() else 1)
