#!/usr/bin/env python3
"""C22 and C35 hold the daemon's tree to the top-level `astra-rs/` of its own checkout;
C27's and C31's pinned legs, and tools/check-manifest-crate.sh, hold the registry and
Astra to being their own checkout's top.

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

The second class is the same rule with `in_repo = ""`, for astra-registry. C27's
and C31's PINNED legs read a commit (`git cat-file`, `git show <pin>:<path>`), and
until entry 120 only an explicit `--registry-dir` was held to being a checkout of
its own; a `$ASTRA_REGISTRY_DIR` or `../astra-registry` that was a copy of the files
had its pins looked up in whatever repository enclosed it. CI always passes
`--registry-dir`, so no CI run could have shown that either. The registry here is
built from this repository's own two mirrors, so that both legs have something
true to compare, and the pins the rules read are pointed at its one commit — the
real pins name commits no fixture can hold.

The third class is the same rule in bash. `tools/check-manifest-crate.sh` asked
`git -C "$ASTRA_REPO" rev-parse --git-dir`, which any enclosing repository answers,
so an `_astra` without its `.git` had `HEAD` resolved in the AstraPlugins checkout
(entry 121). It now holds `--show-toplevel` to `$ASTRA_REPO`, and a canary holds that
spelling of the rule to `checkout_top`'s on every layout.

No Astra, no token, no network — which is why it runs in `couplings`, on every
pull request including a fork's, and not in `proto-upstream`'s full mode.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from checkouts import (  # noqa: E402  (sys.path is set above)
    DAEMON_IN_REPO,
    astra_dir,
    checkout_top,
    daemon_checkout_top,
    daemon_ref_paths,
)

#: The fewest tests a run may report before it is a broken file rather than a
#: pass. The count of test methods below; raise it when you add one.
MIN_TESTS = 29

#: What C22's refusal says about a tree inside some other checkout.
NOT_TOP = f"in a git checkout, but not as its top-level {DAEMON_IN_REPO}/"

#: The same, for a tree that must be its checkout's top (`in_repo = ""`).
NOT_OWN_TOP = "in a git checkout, but not as its top"
NO_CHECKOUT = "not in a git checkout"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LOCALES = _load("check_locales", "check-locales.py")
MIRRORS = _load("check_registry_mirrors", "check-registry-mirrors.py")


class AstraDirAndRefPaths(unittest.TestCase):
    """Direct, no-subprocess tests of `checkouts.astra_dir`/`daemon_ref_paths` —
    the primitives every Python tool's astra-dir resolution shares, below the
    subprocess-level coverage in `DaemonTreeIsItsOwnCheckout`."""

    def test_prefers_flat_when_both_exist(self) -> None:
        # Astra c703cabb6, 2026-10-23, "Flatten astra-rs/ into the repository
        # root": a checkout carrying astra-core/ directly is read as-is, even
        # if it ALSO happens to carry a vendored astra-rs/ copy somewhere —
        # the flat shape is never misread as nested.
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            (top / "astra-core").mkdir()
            (top / DAEMON_IN_REPO / "astra-core").mkdir(parents=True)
            self.assertEqual(astra_dir(top), top)

    def test_falls_back_to_nested(self) -> None:
        # Every tag through v0.2.7.
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            (top / DAEMON_IN_REPO / "astra-core").mkdir(parents=True)
            self.assertEqual(astra_dir(top), top / DAEMON_IN_REPO)

    def test_neither_layout_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(astra_dir(Path(tmp)))

    def test_daemon_ref_paths_is_flat_then_nested(self) -> None:
        self.assertEqual(
            daemon_ref_paths("astra-daemon/src/plugins/i18n.rs"),
            ("astra-daemon/src/plugins/i18n.rs",
             f"{DAEMON_IN_REPO}/astra-daemon/src/plugins/i18n.rs"),
        )

    def test_daemon_checkout_top_accepts_flat_and_nested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = _fixture_env(Path(tmp))
            flat = Path(tmp) / "flat"
            (flat / "astra-core").mkdir(parents=True)
            (flat / "astra-core" / "README").write_text("fixture\n")
            _git(env, "init", "-q", "-b", "main", str(flat))
            _git(env, "-C", str(flat), "add", "-A")
            _git(env, "-C", str(flat), "commit", "-q", "-m", "flat")
            with mock.patch.dict(os.environ, env, clear=True):
                top, why = daemon_checkout_top(flat)
            self.assertEqual((top, why), (flat, ""))

            nested_top = Path(tmp) / "nested"
            (nested_top / DAEMON_IN_REPO / "astra-core").mkdir(parents=True)
            (nested_top / DAEMON_IN_REPO / "astra-core" / "README").write_text("fixture\n")
            _git(env, "init", "-q", "-b", "main", str(nested_top))
            _git(env, "-C", str(nested_top), "add", "-A")
            _git(env, "-C", str(nested_top), "commit", "-q", "-m", "nested")
            with mock.patch.dict(os.environ, env, clear=True):
                top, why = daemon_checkout_top(nested_top / DAEMON_IN_REPO)
            self.assertEqual((top, why), (nested_top, ""))


def _fixture_env(tmp: Path) -> dict[str, str]:
    env = dict(os.environ)
    for k in ("ASTRA_RS_DIR", "ASTRA_REGISTRY_DIR", "GIT_DIR", "GIT_WORK_TREE"):
        env.pop(k, None)
    env.update({
        # git must not find a repository above the fixtures, whatever the
        # temporary directory happens to sit in, or "in no checkout" is not.
        "GIT_CEILING_DIRECTORIES": str(tmp),
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    })
    return env


def _git(env: dict[str, str], *args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                          env=env).stdout.strip()


def _assert_layouts(env: dict[str, str], trees: dict[str, Path], want_top: dict[str, Path | None]) -> None:
    """Each layout is what it says, or every assertion about it is about nothing."""
    for name, tree in trees.items():
        p = subprocess.run(["git", "-C", str(tree), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, env=env)
        got = Path(p.stdout.strip()).resolve() if p.returncode == 0 else None
        assert got == want_top[name], f"fixture {name}: git's top-level is {got}, want {want_top[name]}"


class DaemonTreeIsItsOwnCheckout(unittest.TestCase):
    tmp: Path
    env: dict[str, str]
    tag: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="checkouts-")).resolve()
        cls.env = _fixture_env(cls.tmp)
        floor = LOCALES.SCAFFOLD_FLOOR_RE.search(
            (ROOT / LOCALES.SCAFFOLD_FLOOR_FILE).read_text(encoding="utf-8"))
        assert floor, f"no LABEL_RESOLVER_RELEASE in {LOCALES.SCAFFOLD_FLOOR_FILE}"
        cls.tag = f"v{floor.group(1)}"

        # An Astra at the pre-flatten layout: astra-rs/ at its top (every tag
        # through v0.2.7), the resolver nested under it, and the named ref
        # C22 anchors on.
        astra = cls.tmp / "astra"
        (astra / DAEMON_IN_REPO / "astra-core").mkdir(parents=True)
        (astra / DAEMON_IN_REPO / "astra-core" / "README").write_text("fixture\n")
        resolver = astra / DAEMON_IN_REPO / LOCALES.RESOLVER_FILE
        resolver.parent.mkdir(parents=True)
        resolver.write_text(f"pub fn {LOCALES.RESOLVER_SYMBOL}() {{}}\n")
        cls.git("init", "-q", "-b", "main", str(astra))
        cls.git("-C", str(astra), "add", "-A")
        cls.git("-C", str(astra), "commit", "-q", "-m", "an Astra")
        cls.git("-C", str(astra), "tag", "-a", cls.tag, "-m", cls.tag)
        cls.git("-C", str(astra), "update-ref", "refs/remotes/origin/main", "HEAD")

        # The same Astra, flat at the top instead — Astra c703cabb6,
        # 2026-10-23, "Flatten astra-rs/ into the repository root", and every
        # commit after it. Proves `astra_dir`/`daemon_checkout_top`/
        # `daemon_ref_paths` the other way: C22 must find the resolver with
        # NO astra-rs/ prefix at all, not just tolerate one.
        astra_flat = cls.tmp / "astra-flat"
        (astra_flat / "astra-core").mkdir(parents=True)
        (astra_flat / "astra-core" / "README").write_text("fixture\n")
        resolver_flat = astra_flat / LOCALES.RESOLVER_FILE
        resolver_flat.parent.mkdir(parents=True)
        resolver_flat.write_text(f"pub fn {LOCALES.RESOLVER_SYMBOL}() {{}}\n")
        cls.git("init", "-q", "-b", "main", str(astra_flat))
        cls.git("-C", str(astra_flat), "add", "-A")
        cls.git("-C", str(astra_flat), "commit", "-q", "-m", "a flat Astra")
        cls.git("-C", str(astra_flat), "tag", "-a", cls.tag, "-m", cls.tag)
        cls.git("-C", str(astra_flat), "update-ref", "refs/remotes/origin/main", "HEAD")

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
        # A clone whose top IS astra-rs/ — by NAME only. Its own git checkout
        # has astra-core/ and the resolver directly inside it (copied from
        # `astra`'s astra-rs/, which holds them the same way), so structurally
        # this is a flat Astra checkout that happens to be confusingly named,
        # and since the 2026-10-23 flatten that is a shape this rule must
        # ACCEPT, not refuse — content decides the layout, never the name.
        own_top = cls.tmp / "own-top" / DAEMON_IN_REPO
        shutil.copytree(astra / DAEMON_IN_REPO, own_top)
        cls.git("init", "-q", "-b", "main", str(own_top))
        cls.git("-C", str(own_top), "add", "-A")
        cls.git("-C", str(own_top), "commit", "-q", "-m", "astra-rs as its own top")
        cls.git("-C", str(own_top), "tag", "-a", cls.tag, "-m", cls.tag)
        cls.git("-C", str(own_top), "update-ref", "refs/remotes/origin/main", "HEAD")
        # In no checkout at all.
        shutil.copytree(astra / DAEMON_IN_REPO, cls.tmp / "loose" / DAEMON_IN_REPO)
        # A symlink to the real one.
        (cls.tmp / "link").symlink_to(astra / DAEMON_IN_REPO)

        cls.trees = {
            "own": astra / DAEMON_IN_REPO,
            "flat": astra_flat,
            "enclosed": outer / "_astra" / DAEMON_IN_REPO,
            "nested": astra / "vendor" / DAEMON_IN_REPO,
            "own_top": own_top,
            "loose": cls.tmp / "loose" / DAEMON_IN_REPO,
            "link": cls.tmp / "link",
        }
        _assert_layouts(cls.env, cls.trees, {"own": astra, "flat": astra_flat,
                                             "enclosed": outer, "nested": astra,
                                             "own_top": own_top, "loose": None, "link": astra})
        assert not (outer / "_astra" / ".git").exists()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def git(cls, *args: str) -> str:
        return _git(cls.env, *args)

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

    def test_flat_checkout_is_read(self) -> None:
        # Astra c703cabb6, 2026-10-23, "Flatten astra-rs/ into the repository
        # root": astra-core/ and the resolver AT the top, no astra-rs/ at
        # all. `daemon_checkout_top`/`daemon_ref_paths` must find both with
        # no prefix, not merely tolerate one that happens to be there.
        self.passes(self.trees["flat"])

    def test_symlink_to_own_checkout_is_that_checkout(self) -> None:
        self.passes(self.trees["link"])

    # ── entry 115 ────────────────────────────────────────────────────────────
    def test_astra_without_git_inside_astraplugins_is_refused(self) -> None:
        self.refused(self.trees["enclosed"], NOT_TOP)

    def test_copy_nested_in_another_astra_checkout_is_refused(self) -> None:
        # Before the fix this one was GREEN: it read the enclosing Astra's tags.
        self.refused(self.trees["nested"], NOT_TOP)

    def test_astra_rs_as_its_own_checkout_top_passes(self) -> None:
        # Before Astra's 2026-10-23 flatten this was refused: a clone whose
        # top is itself named astra-rs/ was indistinguishable from a copy
        # nested one level into some other checkout. It no longer is —
        # content decides the layout now, never the name — and this
        # directory's content (astra-core/ and the resolver directly inside
        # it) is exactly what a legitimate flat Astra checkout looks like.
        self.passes(self.trees["own_top"])

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
            flat_head = self.git("-C", str(self.tmp / "astra-flat"), "rev-parse", "--short=12", "HEAD")
            own_top_head = self.git("-C", str(self.trees["own_top"]), "rev-parse", "--short=12", "HEAD")
            label = lambda name: MIRRORS._git_head(self.trees[name], DAEMON_IN_REPO)  # noqa: E731
            self.assertEqual(label("own"), head)
            self.assertEqual(label("link"), head)
            self.assertEqual(label("flat"), flat_head)
            # Legitimately flat (see test_astra_rs_as_its_own_checkout_top_passes),
            # so its own commit is the right label now, not NOT_TOP.
            self.assertEqual(label("own_top"), own_top_head)
            for name in ("enclosed", "nested"):
                self.assertEqual(label(name), f"HEAD unknown: {NOT_TOP}", name)
            self.assertEqual(label("loose"), "HEAD unknown: not in a git checkout")
        finally:
            os.environ.clear()
            os.environ.update(old)


#: A pinned leg's verdict line, whatever the verdict. Absent means the leg read nothing.
PINNED_LINE = re.compile(r"^(?:ok    |FAIL  )C(?:27|31) .*\(pinned ", re.M)
#: A head leg that ran and passed.
HEAD_OK = re.compile(r"^ok    C(?:27|31) .*\(head ", re.M)

#: The pin readers as the rules call them, before any test points them elsewhere.
REAL_RESERVED_SPEC = MIRRORS.read_reserved_spec
REAL_BINDING_PIN = MIRRORS.read_binding_pin


class RegistryPinnedLegsReadOnlyItsOwnCheckout(unittest.TestCase):
    tmp: Path
    env: dict[str, str]
    sha: str
    binding_rel: str
    trees: dict[str, Path]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="registry-")).resolve()
        cls.env = _fixture_env(cls.tmp)

        # An astra-registry holding exactly what this repository's two mirrors
        # say it holds, at the paths their `mirrors:` lines name.
        reg = cls.tmp / "astra-registry"
        values, sources, _pin = REAL_RESERVED_SPEC()
        docs: dict[str, dict] = {}
        texts: dict[str, list[str]] = {}
        for name, source in sources.items():
            rel, _, key = source.partition(" ")
            key = key.strip()
            if rel.endswith(".json"):
                docs.setdefault(rel, {})[key] = values[name]
            elif key == "ID_PATTERN":
                texts.setdefault(rel, []).append(f'export const ID_PATTERN = "{values[name]}";')
            elif key.startswith("invalidId") and values[name] == "true":
                texts.setdefault(rel, []).append(
                    'export function invalidId(id) { return id.includes("--"); }')
            else:
                raise AssertionError(f"a `mirrors:` line this fixture cannot build: {source}")
        for rel, doc in docs.items():
            (reg / rel).parent.mkdir(parents=True, exist_ok=True)
            (reg / rel).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        for rel, lines in texts.items():
            (reg / rel).parent.mkdir(parents=True, exist_ok=True)
            (reg / rel).write_text("\n".join(lines) + "\n", encoding="utf-8")
        pin_m = REAL_BINDING_PIN()
        assert pin_m, f"no `astra-registry@<sha>:<path>` in {MIRRORS.BINDING_README}"
        cls.binding_rel = pin_m.group(2)
        corpus = reg / cls.binding_rel
        corpus.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MIRRORS.BINDING_VECTORS, corpus)
        shutil.copyfile(MIRRORS.BINDING_SUMS, corpus.parent / "SHA256SUMS")
        _git(cls.env, "init", "-q", "-b", "main", str(reg))
        _git(cls.env, "-C", str(reg), "add", "-A")
        _git(cls.env, "-C", str(reg), "commit", "-q", "-m", "an astra-registry")
        cls.sha = _git(cls.env, "-C", str(reg), "rev-parse", "HEAD")

        no_git = shutil.ignore_patterns(".git")
        # The AstraPlugins checkout, with a copy of the registry's files inside it.
        outer = cls.tmp / "astraplugins"
        outer.mkdir()
        (outer / "README.md").write_text("AstraPlugins, as a fixture\n")
        _git(cls.env, "init", "-q", "-b", "master", str(outer))
        _git(cls.env, "-C", str(outer), "add", "-A")
        _git(cls.env, "-C", str(outer), "commit", "-q", "-m", "AstraPlugins")
        shutil.copytree(reg, outer / "regcopy", ignore=no_git)
        # A copy one level down inside a real registry checkout, which HOLDS the pin.
        shutil.copytree(reg, reg / "vendor" / "astra-registry", ignore=no_git)
        # In no checkout at all.
        shutil.copytree(reg, cls.tmp / "loose" / "astra-registry", ignore=no_git)
        # A symlink to the real one.
        (cls.tmp / "link").symlink_to(reg)

        cls.trees = {
            "own": reg,
            "enclosed": outer / "regcopy",
            "nested": reg / "vendor" / "astra-registry",
            "loose": cls.tmp / "loose" / "astra-registry",
            "link": cls.tmp / "link",
        }
        _assert_layouts(cls.env, cls.trees, {"own": reg, "enclosed": outer, "nested": reg,
                                             "loose": None, "link": reg})
        for name, tree in cls.trees.items():
            assert (tree / "policy" / "reserved-ids.json").is_file(), name
            assert (name in ("own", "link")) == (tree / ".git").exists(), name

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def rules(self, tree: Path) -> tuple[list[str], list[tuple[str, str]], str]:
        """C27 then C31 with the registry found through `$ASTRA_REGISTRY_DIR`, as a maintainer's is.

        In-process, with the two pins pointed at the fixture's commit, so that a
        pinned leg that does run has a commit it can find — in its own checkout,
        or, which is the defect, in whatever repository encloses a copy.
        """
        values, sources, _pin = REAL_RESERVED_SPEC()
        sha, rel = self.sha, self.binding_rel
        fails = MIRRORS.Fails()
        out = io.StringIO()
        with mock.patch.dict(os.environ, dict(self.env, ASTRA_REGISTRY_DIR=str(tree)), clear=True), \
                mock.patch.dict(MIRRORS.EXPLICIT, {"registry": None}), \
                mock.patch.object(MIRRORS, "read_reserved_spec", lambda: (values, sources, sha)), \
                mock.patch.object(MIRRORS, "read_binding_pin",
                                  lambda readme=None: MIRRORS.BINDING_PIN.search(
                                      f"astra-registry@{sha}:{rel}")), \
                contextlib.redirect_stdout(out):
            MIRRORS.rule_C27(fails)
            MIRRORS.rule_C31(fails)
        return list(fails), list(fails.unverified), out.getvalue()

    def pinned_legs_ran(self, tree: Path) -> None:
        failed, unverified, out = self.rules(tree)
        self.assertEqual(failed, [], out)
        self.assertEqual(unverified, [], out)
        self.assertRegex(out, rf"(?m)^ok    C27 .*\(pinned {self.sha[:12]}, \d+ value\(s\)\)$")
        self.assertRegex(out, rf"(?m)^ok    C31 .*\(pinned {self.sha[:12]}\)$")
        self.assertEqual(len(HEAD_OK.findall(out)), 2, out)

    def only_pinned_legs_skipped(self, tree: Path, why: str) -> None:
        failed, unverified, out = self.rules(tree)
        self.assertEqual(failed, [], out)
        # the pinned legs read nothing, and said so by name
        self.assertEqual(PINNED_LINE.findall(out), [], out)
        for rule in ("C27", "C31"):
            self.assertIn(f"{rule} NOT VERIFIED (pinned leg): the astra-registry tree at {tree} "
                          f"is {why},", out)
        self.assertEqual(unverified, [(r, f"pinned leg: the astra-registry tree is {why}")
                                      for r in ("C27", "C31")])
        # the head legs read the files, and both ran
        self.assertEqual(len(HEAD_OK.findall(out)), 2, out)

    def mirrors_cli(self, *args: str, env_dir: Path | None = None):
        env = dict(self.env)
        if env_dir is not None:
            env["ASTRA_REGISTRY_DIR"] = str(env_dir)
        return subprocess.run([sys.executable, str(HERE / "check-registry-mirrors.py"),
                               "--rules", "C27,C31", *args],
                              capture_output=True, text=True, env=env, cwd=ROOT)

    # ── the rule itself, with `in_repo = ""` ─────────────────────────────────
    def test_checkout_top_holds_a_registry_to_its_own_top(self) -> None:
        with mock.patch.dict(os.environ, self.env, clear=True):
            got = {name: checkout_top(tree, "") for name, tree in self.trees.items()}
        self.assertEqual(got["own"][1], "")
        self.assertEqual(got["own"][0].resolve(), self.trees["own"])
        self.assertEqual(got["link"][0].resolve(), self.trees["own"])
        for name in ("enclosed", "nested"):
            self.assertEqual(got[name], (None, NOT_OWN_TOP), name)
        self.assertEqual(got["loose"], (None, NO_CHECKOUT))

    # ── the controls: an own checkout's pinned legs run ─────────────────────
    def test_registry_own_checkout_runs_both_pinned_legs(self) -> None:
        self.pinned_legs_ran(self.trees["own"])

    def test_registry_symlink_to_own_checkout_is_that_checkout(self) -> None:
        self.pinned_legs_ran(self.trees["link"])

    # ── entry 120 ────────────────────────────────────────────────────────────
    def test_registry_copy_inside_astraplugins_skips_only_the_pinned_legs(self) -> None:
        # Before the fix: both pinned legs FAIL, looking for the pin in the
        # AstraPlugins checkout and advising a fetch into it.
        self.only_pinned_legs_skipped(self.trees["enclosed"], NOT_OWN_TOP)

    def test_registry_copy_nested_in_a_registry_checkout_skips_the_pinned_legs(self) -> None:
        # Before the fix this one was GREEN: the pins were read out of the
        # registry checkout that encloses the copy.
        self.only_pinned_legs_skipped(self.trees["nested"], NOT_OWN_TOP)

    def test_registry_copy_in_no_checkout_skips_the_pinned_legs(self) -> None:
        self.only_pinned_legs_skipped(self.trees["loose"], NO_CHECKOUT)

    # ── the command line, with the real pins ─────────────────────────────────
    def test_cli_implicit_copy_is_not_verified_and_not_red(self) -> None:
        p = self.mirrors_cli(env_dir=self.trees["enclosed"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("FAIL", p.stdout)
        why = f"pinned leg: the astra-registry tree is {NOT_OWN_TOP}"
        self.assertIn(f"check-registry-mirrors: C27, C31 pass, NOT VERIFIED: C27 ({why}); "
                      f"C31 ({why}).", p.stdout)

    def test_cli_explicit_copy_is_exit_2_and_never_the_skip(self) -> None:
        p = self.mirrors_cli("--registry-dir", str(self.trees["enclosed"]))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("is not a git checkout of its own, and the pinned leg reads a commit. "
                      "It was passed explicitly, so this is an error and not a skip.", p.stderr)
        self.assertNotIn("NOT VERIFIED (pinned leg)", p.stdout)


#: `tools/check-manifest-crate.sh`'s refusal of a directory inside another checkout.
MANIFEST_NOT_OWN = "is not a git checkout of its own."


class ManifestCrateReadsOnlyAstrasOwnCheckout(unittest.TestCase):
    """`tools/check-manifest-crate.sh` reads Astra through `git -C "$ASTRA_REPO"`, in bash.

    It used to ask `rev-parse --git-dir`, which any enclosing repository answers,
    so with an `_astra` whose `.git` went missing and the CI step's own env
    (ASTRA_REF=HEAD) it resolved HEAD in the AstraPlugins checkout and failed
    "HEAD carries no astra-rs/astra-plugin-manifest", blaming the ref (entry 121).
    It now holds `git rev-parse --show-toplevel` to `$ASTRA_REPO` — the rule
    `checkout_top(tree, "")` states in Python — and the last test here is the
    canary that the two spellings of it agree on every layout.
    """

    tmp: Path
    env: dict[str, str]
    trees: dict[str, Path]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="astra-crate-")).resolve()
        cls.env = _fixture_env(cls.tmp)
        for k in ("ASTRA_REPO", "ASTRA_REF"):
            cls.env.pop(k, None)

        # An Astra whose manifest crate IS the vendored one, so the check has a
        # true answer to give on a checkout it may read.
        astra = cls.tmp / "Astra"
        crate = astra / DAEMON_IN_REPO / "astra-plugin-manifest"
        shutil.copytree(ROOT / "astra-plugin-cli" / "vendor" / "astra-plugin-manifest", crate)
        _git(cls.env, "init", "-q", "-b", "main", str(astra))
        _git(cls.env, "-C", str(astra), "add", "-A")
        _git(cls.env, "-C", str(astra), "commit", "-q", "-m", "an Astra")
        _git(cls.env, "-C", str(astra), "update-ref", "refs/remotes/origin/main", "HEAD")

        no_git = shutil.ignore_patterns(".git")
        # The AstraPlugins checkout, with an `_astra` inside it that has no `.git`.
        outer = cls.tmp / "astraplugins"
        outer.mkdir()
        (outer / "README.md").write_text("AstraPlugins, as a fixture\n")
        _git(cls.env, "init", "-q", "-b", "master", str(outer))
        _git(cls.env, "-C", str(outer), "add", "-A")
        _git(cls.env, "-C", str(outer), "commit", "-q", "-m", "AstraPlugins")
        _git(cls.env, "-C", str(outer), "update-ref", "refs/remotes/origin/main", "HEAD")
        shutil.copytree(astra, outer / "_astra", ignore=no_git)
        # A copy nested inside the real Astra checkout.
        shutil.copytree(astra, astra / "vendor" / "Astra", ignore=no_git)
        # In no checkout at all.
        shutil.copytree(astra, cls.tmp / "loose" / "Astra", ignore=no_git)
        # A symlink to the real one.
        (cls.tmp / "link").symlink_to(astra)

        cls.trees = {
            "own": astra,
            "enclosed": outer / "_astra",
            "nested": astra / "vendor" / "Astra",
            "loose": cls.tmp / "loose" / "Astra",
            "link": cls.tmp / "link",
        }
        _assert_layouts(cls.env, cls.trees, {"own": astra, "enclosed": outer, "nested": astra,
                                             "loose": None, "link": astra})
        for name, tree in cls.trees.items():
            assert (tree / DAEMON_IN_REPO / "astra-plugin-manifest" / "src" / "lib.rs").is_file(), name
            assert (name in ("own", "link")) == (tree / ".git").exists(), name

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def crate_check(self, repo: str | Path, ref: str = "HEAD"):
        """The script as `proto-upstream` runs it: ASTRA_REPO and ASTRA_REF=HEAD in the env."""
        env = dict(self.env, ASTRA_REPO=str(repo), ASTRA_REF=ref)
        return subprocess.run(["bash", str(HERE / "check-manifest-crate.sh")],
                              capture_output=True, text=True, env=env, cwd=ROOT)

    def passes(self, repo: str | Path) -> None:
        p = self.crate_check(repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("check-manifest-crate: one plugin.toml definition,", p.stdout)

    def refused_by_name(self, name: str) -> None:
        tree = self.trees[name]
        p = self.crate_check(tree)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(f"check-manifest-crate: FAIL {tree} {MANIFEST_NOT_OWN}", p.stderr)
        # refused BEFORE a ref was resolved: nothing blames the ref or the crate
        self.assertNotIn("carries no", p.stderr)
        self.assertNotIn("does not resolve", p.stderr)
        self.assertNotIn("comparing against", p.stdout)

    # ── the controls: Astra's own checkout is read ─────────────────────────
    def test_manifest_crate_own_checkout_passes(self) -> None:
        self.passes(self.trees["own"])

    def test_manifest_crate_symlink_trailing_slash_and_relative_path_are_that_checkout(self) -> None:
        self.passes(self.trees["link"])
        self.passes(f"{self.trees['own']}/")
        self.passes(os.path.relpath(self.trees["own"], ROOT))

    def test_manifest_crate_loose_copy_is_not_a_git_repository(self) -> None:
        p = self.crate_check(self.trees["loose"])
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(f"check-manifest-crate: FAIL {self.trees['loose']} is not a git repository.",
                      p.stderr)

    # ── entry 121 ────────────────────────────────────────────────────────────
    def test_manifest_crate_astra_without_git_inside_astraplugins_is_refused_by_name(self) -> None:
        # Before the fix: HEAD resolved in the AstraPlugins checkout, and the
        # script failed "HEAD carries no astra-rs/astra-plugin-manifest".
        self.refused_by_name("enclosed")

    def test_manifest_crate_copy_nested_in_an_astra_checkout_is_refused_by_name(self) -> None:
        self.refused_by_name("nested")

    def test_manifest_crate_worktree_mode_names_no_enclosing_commit(self) -> None:
        # Before the fix: exit 0, describing the AstraPlugins checkout's HEAD,
        # branch and distance from origin/main as Astra's.
        tree = self.trees["enclosed"]
        p = self.crate_check(tree, "worktree")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"comparing against the WORKING TREE of {tree} (not a git checkout of its own: "
                      f"git would answer for {tree.parent},", p.stdout)
        self.assertNotIn(" on master", p.stdout)

    # ── the canary: the bash rule and checkout_top agree ────────────────────
    def test_manifest_crate_and_checkout_top_agree_on_every_layout(self) -> None:
        with mock.patch.dict(os.environ, self.env, clear=True):
            python = {name: checkout_top(tree, "")[0] is not None for name, tree in self.trees.items()}
        bash = {}
        for name, tree in self.trees.items():
            p = self.crate_check(tree)
            refused = (MANIFEST_NOT_OWN in p.stderr) or ("is not a git repository." in p.stderr)
            bash[name] = not refused
        self.assertEqual(bash, python)
        self.assertEqual(python, {"own": True, "enclosed": False, "nested": False, "loose": False,
                                  "link": True})


if __name__ == "__main__":
    prog = unittest.main(exit=False, verbosity=2)
    ran = prog.result.testsRun
    if ran < MIN_TESTS:
        print(f"test_checkouts: {ran} test(s) ran, want >= {MIN_TESTS}. A test file that "
              "stopped collecting its tests is not a pass.", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(0 if prog.result.wasSuccessful() else 1)
