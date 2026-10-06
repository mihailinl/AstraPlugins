#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""C40, run against the release notes every author got and against trees built to be wrong.

    python3 tools/test_attestation_commands.py        # what the couplings job runs

`tools/check-attestation-commands.py` is green on this tree, and a check that
has only seen a green tree has not shown it can see anything. So: the
`plugin-release.yml` that wrote the failing command into every author's
Release is read back out of history and must be red; then small trees spell
each near miss that also fails a good file — `--signer-repo` alone, the wrong
case, a shell variable, a ref, the other workflow — and must be red for the
reason given; and the shapes a command takes in this tree (a code line, an
inline span across a line break, a doctest `from=`, `\\` continuations, a
placeholder) must all be read. No network.
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("c40", ROOT / "tools/check-attestation-commands.py")
c40 = importlib.util.module_from_spec(spec)
sys.modules["c40"] = c40  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(c40)

#: master's head when the bug was found: its plugin-release.yml is the one
#: whose notes went into every author's Release (2026-10-05).
BUG_COMMIT = "ed3da54de6690d16d66c24dfab277fc946a5dd31"

P = "mihailinl/AstraPlugins/.github/workflows/plugin-release.yml"
C = "mihailinl/AstraPlugins/.github/workflows/release-cli.yml"


def tree(files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="c40-test-"))
    for wf in ("plugin-release.yml", "release-cli.yml", "ci.yml"):
        (d / ".github/workflows").mkdir(parents=True, exist_ok=True)
        (d / ".github/workflows" / wf).write_text("on: push\n")
    for rel, text in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    return d


def scan(files: dict[str, str]):
    with redirect_stdout(io.StringIO()):
        return c40.scan(tree(files))


class TheBugsTree(unittest.TestCase):
    def test_the_notes_every_author_got_are_red(self):
        p = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{BUG_COMMIT}:.github/workflows/plugin-release.yml"],
            capture_output=True, text=True,
        )
        self.assertEqual(p.returncode, 0, f"{BUG_COMMIT} is not in this clone: {p.stderr}")
        cmds, fails = scan({".github/workflows/plugin-release.yml": p.stdout})
        taught = [c for c in cmds if c.path.endswith("plugin-release.yml")]
        self.assertEqual(len(taught), 1, [c.text for c in cmds])
        self.assertEqual(taught[0].text, "<file>.astraplugin --repo ${GITHUB_REPOSITORY}")
        self.assertEqual(len(fails), 1, fails)
        self.assertIn("no `--signer-workflow`", fails[0])
        self.assertIn(P, fails[0])

    def test_this_tree_is_green_and_was_actually_read(self):
        with redirect_stdout(io.StringIO()):
            cmds, fails = c40.scan(ROOT)
        self.assertEqual(fails, [])
        seen = {c.path for c in cmds}
        for must in (
            ".github/workflows/plugin-release.yml",
            ".github/workflows/release-cli.yml",
            "README.md",
            "astra-plugin-cli/README.md",
            "docs/en/publishing.md",
            "docs/en/5-publish/release-with-ci.md",
            "docs/en/install-cli.md",
            "docs/zh/publishing.md",
        ):
            self.assertIn(must, seen)


class NearMisses(unittest.TestCase):
    """Each of these fails a good file the same silent way the original did."""

    def red(self, line: str, why: str):
        _, fails = scan({"README.md": f"```bash\n{line}\n```\n"})
        self.assertTrue(fails, "green on a command that fails a good file")
        self.assertTrue(all(f.startswith("README.md:2 ") for f in fails), fails)
        self.assertIn(why, "\n".join(fails))

    def test_no_flag(self):
        self.red("gh attestation verify x.astraplugin --repo you/x", "no `--signer-workflow`")

    def test_signer_repo_is_not_enough(self):
        self.red("gh attestation verify x.astraplugin --repo you/x --signer-repo mihailinl/AstraPlugins",
                 "`--signer-repo` is not enough")

    def test_case(self):
        self.red(f"gh attestation verify x.astraplugin --repo you/x --signer-workflow {P.lower()}",
                 "case-sensitively")

    def test_shell_variable(self):
        self.red("gh attestation verify x.astraplugin --repo you/x "
                 "--signer-workflow ${GITHUB_REPOSITORY}/.github/workflows/plugin-release.yml",
                 "is the CALLER")

    def test_ref(self):
        self.red(f"gh attestation verify x.astraplugin --repo you/x --signer-workflow {P}@refs/tags/plugin-release/v1",
                 "not spelled")

    def test_plugin_named_with_the_cli_workflow(self):
        self.red(f"gh attestation verify x.astraplugin --repo you/x --signer-workflow {C}",
                 "signed by `plugin-release.yml`")

    def test_cli_archive_named_with_the_plugin_workflow(self):
        self.red(f"gh attestation verify astra-plugin-1.0.0-linux-x64-musl.tar.gz --repo mihailinl/AstraPlugins --signer-workflow {P}",
                 "signed by `release-cli.yml`")

    def test_a_workflow_that_does_not_exist(self):
        self.red("gh attestation verify x.astraplugin --repo you/x "
                 "--signer-workflow mihailinl/AstraPlugins/.github/workflows/plugin-releases.yml",
                 "is not a workflow")

    def test_a_placeholder_still_names_the_right_workflow(self):
        self.red("gh attestation verify a.astraplugin --repo <r> "
                 "--signer-workflow <AstraPlugins>/.github/workflows/release-cli.yml",
                 "signed by `plugin-release.yml`")

    def test_no_value(self):
        self.red("gh attestation verify x.astraplugin --repo you/x --signer-workflow", "has no value")


class Shapes(unittest.TestCase):
    """Every shape a command takes in this tree is read, and a mention is not a command."""

    def test_green_shapes(self):
        files = {
            "a.md": f"```bash\ngh attestation verify x.astraplugin --repo you/x --signer-workflow {P}\n```\n",
            "b.md": ("To check, `gh attestation verify <archive> --bundle\nb.jsonl --repo "
                     f"mihailinl/AstraPlugins --signer-workflow\n{C}`; it is silent.\n"),
            "c.md": (f'<!-- doctest: output from="gh attestation verify t.tar.gz --repo '
                     f'mihailinl/AstraPlugins --signer-workflow {C}" unrun="x" -->\n'),
            "d.md": ("```sh\ngh attestation verify a.astraplugin \\\n   --repo <release.repo> \\\n"
                     "   --signer-workflow <AstraPlugins>/.github/workflows/plugin-release.yml \\\n"
                     "   --format json\n```\n"),
            "e.md": "1. `gh attestation verify <file> --repo <repo> --signer-workflow <path>\n   --format json`.\n",
            "f.yml": (f"          \\`\\`\\`\n          gh attestation verify <file>.astraplugin "
                      f"--repo ${{GITHUB_REPOSITORY}} --signer-workflow {P}\n          \\`\\`\\`\n"),
            "g.md": f"gh attestation verify x.astraplugin --repo you/x --signer-workflow={P}\n",
        }
        cmds, fails = scan(files)
        self.assertEqual(fails, [])
        self.assertEqual(sorted(c.path for c in cmds), sorted(files))
        by = {c.path: c for c in cmds}
        self.assertIn(C, by["b.md"].tokens)
        self.assertIn("--format", by["d.md"].tokens)
        self.assertNotIn("\\", by["d.md"].tokens)

    def test_a_split_inline_command_without_the_flag_is_still_read(self):
        _, fails = scan({"b.md": "`gh attestation verify <archive> --bundle\nb.jsonl --repo mihailinl/AstraPlugins`\n"})
        self.assertEqual(len(fails), 1, fails)

    def test_mentions_are_not_commands(self):
        cmds, fails = scan({
            "a.md": "`gh attestation verify` fetches the bundle.\n",
            "b.md": 'BOT["registry bot<br/>gh attestation verify<br/>+ 15 policy checks"]\n',
            "c.md": "re-audit it with `gh attestation verify`.\n",
            "d.yml": "          # Not required — `gh attestation verify` fetches it\n",
            "e.md": "| `gh attestation verify` printed nothing at all | a pass |\n",
        })
        self.assertEqual((cmds, fails), ([], []))


class Exemptions(unittest.TestCase):
    PROTO = "    // e.g. `gh attestation verify <file> --repo you/dice-roller`. Built by the\n"

    def protos(self, text: str) -> dict[str, str]:
        return {path: text for path in c40.EXEMPT}

    def test_the_proto_comment_is_excused(self):
        _, fails = scan(self.protos(self.PROTO))
        self.assertEqual(fails, [])

    def test_a_fixed_proto_makes_the_exemption_stale(self):
        _, fails = scan(self.protos(f"    // e.g. `gh attestation verify <file> --repo you/x --signer-workflow {P}`.\n"))
        self.assertEqual(len(fails), len(c40.EXEMPT), fails)
        self.assertTrue(all("matches no failing command" in f for f in fails), fails)

    def test_the_exemption_covers_that_text_only(self):
        _, fails = scan(self.protos(self.PROTO + "    // or `gh attestation verify <file> --repo you/other`\n"))
        self.assertEqual(len(fails), len(c40.EXEMPT), fails)
        self.assertTrue(all("you/other" in f for f in fails), fails)


class LiveHelpers(unittest.TestCase):
    """--live itself needs the network; what it runs is fixed here."""

    def test_each_release_workflow_teaches_one_command_that_live_can_fill(self):
        cmd = c40.notes_command(ROOT, c40.PLUGIN_SIGNER)
        self.assertEqual(cmd.tokens[:3], ["<file>.astraplugin", "--repo", "${GITHUB_REPOSITORY}"])
        self.assertEqual(c40.flag_value(cmd.tokens, "--signer-workflow"), P)
        cmd = c40.notes_command(ROOT, c40.CLI_SIGNER)
        self.assertEqual(cmd.tokens[0], "astra-plugin-$VERSION-linux-x64-musl.tar.gz")
        self.assertEqual(c40.flag_value(cmd.tokens, "--signer-workflow"), C)

    def test_without_signer_drops_the_flag_and_its_value_only(self):
        self.assertEqual(
            c40.without_signer(["f", "--repo", "r", "--signer-workflow", P, "--format", "json"]),
            ["f", "--repo", "r", "--format", "json"],
        )
        self.assertEqual(c40.without_signer(["f", f"--signer-workflow={P}"]), ["f"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
