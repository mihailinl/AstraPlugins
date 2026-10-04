#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""C39, held to protoc and run against trees built to be wrong.

    python3 tools/test_protocol_counts.py        # what the couplings job runs

Two halves. The parser in `tools/check-protocol-counts.py` is held to numbers
protoc measured: every proto commit between `sdk-v0.7.1` and the 0.7.2 train
was compiled with `protoc --descriptor_set_out`, decoded, and diffed against
the tag's descriptor by message name and field number. Those commits are
history and never change, so the numbers are written down rather than
recomputed, and this file needs no protoc. Then the comparisons are run
against small git repositories built to say the wrong thing: the stale 37, a
sentence missing, a dated entry, a docs count aimed at a release that does not
exist.
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
spec = importlib.util.spec_from_file_location("c39", ROOT / "tools/check-protocol-counts.py")
c39 = importlib.util.module_from_spec(spec)
sys.modules["c39"] = c39  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(c39)

# protoc 36.1, `--descriptor_set_out` at each commit, diffed against sdk-v0.7.1's
# descriptor: (fields added to messages that existed, messages that gained one,
# new messages, new rpcs, retyped rpcs). Map-entry messages excluded, as here.
PROTOC = {
    "0d3174b": (22, 10, 8, 4, 0),
    "121081d": (27, 10, 9, 4, 0),
    "c496fa5": (35, 18, 12, 4, 0),
    "fa4dcdb": (37, 18, 14, 4, 0),
    "431b969": (37, 18, 14, 4, 0),  # where "37 fields … and 13 new messages" was written
    "40c32ee": (42, 22, 16, 4, 1),
    "8b02ce4": (43, 23, 16, 4, 1),
    "d72aa0a": (49, 26, 25, 11, 1),
}

BASE_PROTO = """\
syntax = "proto3";
package astra;

// A comment with "quotes", {braces} and a ; that must not count.
service Svc {
    rpc Get(Req) returns (Resp);
    rpc Watch(Req) returns (stream Resp) {
        option deprecated = true;
    }
}

message Req { string id = 1; }

message Resp {
    string id = 1;  // "running" | "stopped"
    reserved 4;
    message Inner { int32 n = 1; }
    enum Kind { KIND_UNSPECIFIED = 0; KIND_A = 1; }
}
"""

HEAD_PROTO = """\
syntax = "proto3";
package astra;

// A comment with "quotes", {braces} and a ; that must not count.
service Svc {
    rpc Get(Req) returns (Resp2);
    rpc Watch(Req) returns (stream Resp) {
        option deprecated = true;
    }
    rpc Put(Req) returns (Resp);
}

message Req { string id = 1; optional bool dry = 2; }

message Resp {
    string id = 1;  // "running" | "stopped"
    reserved 4;
    message Inner { int32 n = 1; repeated string tags = 2; }
    enum Kind { KIND_UNSPECIFIED = 0; KIND_A = 1; KIND_B = 2; }
    oneof body {
        string text = 5;
        Inner inner = 6;
    }
    map<string, uint64> cursors = 7;
}

message Resp2 { Resp resp = 1; string url = 2; /* a block comment; with } */ }
"""

# 5 fields on 3 messages (Req.dry; Resp.Inner.tags; Resp.text, .inner, .cursors
# — oneof members and a map are fields of their message), 1 new message
# (Resp2), 1 new rpc (Put), 1 retyped (Get). Enum values are not fields.
SYNTHETIC = (5, 3, 1, 1, 1)


def counts_tuple(c) -> tuple[int, int, int, int, int]:
    return (c.fields, c.touched, c.messages, c.rpcs, c.retyped)


class TheParserIsProtocs(unittest.TestCase):
    def test_every_slice_since_sdk_v0_7_1(self):
        base = c39.proto_at(ROOT, "sdk-v0.7.1")
        self.assertIsNotNone(base, "sdk-v0.7.1 is not in this checkout; couplings fetches with depth 0")
        for commit, want in PROTOC.items():
            head = c39.proto_at(ROOT, commit)
            self.assertIsNotNone(head, commit)
            c = c39.count(c39.parse(base), c39.parse(head))
            self.assertEqual(counts_tuple(c), want, commit)
            self.assertEqual(c.removed, [], commit)

    def test_the_constructs_this_file_does_not_use_yet(self):
        c = c39.count(c39.parse(BASE_PROTO), c39.parse(HEAD_PROTO))
        self.assertEqual(counts_tuple(c), SYNTHETIC)
        self.assertEqual(c.removed, [])

    def test_a_rename_and_a_removal_are_changes_not_additions(self):
        head = BASE_PROTO.replace("string id = 1;  //", "string ident = 1;  //").replace(
            "message Inner { int32 n = 1; }", "message Inner { }")
        c = c39.count(c39.parse(BASE_PROTO), c39.parse(head))
        self.assertEqual(c.fields, 0)
        self.assertEqual(len(c.removed), 2, c.removed)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=c39", "-c", "user.email=c39@example.invalid",
                    "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                   cwd=repo, check=True, capture_output=True)


def entry(version: str, when: str, body: str) -> str:
    return f"# Changelog\n\n## [{version}] — {when}\n\n{body}\n\n## [0.0.1] — 2026-01-01\n\nOld.\n"


GOOD = ("Between `sdk-v1.0.0` and this release the protocol gained 5 fields on 3 "
        "messages that already existed, 1 new message and 1 new rpc; it retyped 1 rpc "
        "and removed or renumbered nothing.")
DOCS = ("# Versioning\n\nIntro, 3 SDKs.\n\nWhy a new field is not a minor: every sync adds "
        "fields — {n} on messages that already existed, between `sdk-v1.0.0` and {head} — so "
        "a minor per field would make every sync a minor.\n")


class Fixture:
    """A git repository with this checker's inputs and nothing else."""

    def __init__(self, tmp: Path):
        self.root = tmp
        git(tmp, "init", "-q")
        (tmp / "proto").mkdir()
        (tmp / "docs/tools").mkdir(parents=True)
        (tmp / "docs/en").mkdir()
        (tmp / "docs/tools/locales.py").write_text('LOCALES = ("en",)\n')
        for d in ("astra-plugin-sdk", "astra-plugin-sdk-python", "astra-plugin-sdk-ts"):
            (tmp / d).mkdir()
        self.write(rust="1.0.0", proto=BASE_PROTO, rust_log=entry("1.0.0", "2026-02-01", "First."),
                   docs=DOCS.format(n=0, head="1.0.0"))
        git(tmp, "add", "-A")
        git(tmp, "commit", "-qm", "base")
        git(tmp, "tag", "sdk-v1.0.0")

    def write(self, *, rust="1.0.1", proto=HEAD_PROTO, rust_log=None, py_log=None,
              ts_log=None, docs=None):
        r = self.root
        (r / "astra-plugin-sdk/Cargo.toml").write_text(f'[package]\nversion = "{rust}"\n')
        (r / "proto/plugin.proto").write_text(proto)
        (r / "astra-plugin-sdk/CHANGELOG.md").write_text(rust_log or entry(rust, "unreleased", GOOD))
        (r / "astra-plugin-sdk-python/CHANGELOG.md").write_text(py_log or entry("0.1.0", "unreleased", "No count."))
        (r / "astra-plugin-sdk-ts/CHANGELOG.md").write_text(ts_log or entry("0.1.0", "unreleased", "No count."))
        (r / "docs/en/versioning.md").write_text(docs or DOCS.format(n=5, head=rust))
        return self

    def run(self) -> tuple[list[str], str]:
        ch = c39.Checker(self.root)
        out = io.StringIO()
        with redirect_stdout(out):
            ch.changelogs()
            ch.docs()
        return ch.fails, out.getvalue()


class TheComparisons(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_true_sentence_is_green(self):
        fails, out = self.fx.write().run()
        self.assertEqual(fails, [], out)
        self.assertIn("5 fields on 3 messages", out)

    def test_the_stale_37(self):
        stale = GOOD.replace("5 fields on 3", "37 fields on 3").replace("1 new message and", "13 new messages and")
        fails, out = self.fx.write(rust_log=entry("1.0.1", "unreleased", stale)).run()
        self.assertEqual(len(fails), 1, out)
        self.assertIn("'fields': 37", out)

    def test_markdown_emphasis_and_line_wrapping_do_not_hide_a_sentence(self):
        wrapped = GOOD.replace("gained 5 fields", "gained **5\nfields**")
        fails, out = self.fx.write(rust_log=entry("1.0.1", "unreleased", wrapped)).run()
        self.assertEqual(fails, [], out)

    def test_the_rust_entry_must_say_it_when_the_proto_moved(self):
        fails, out = self.fx.write(rust_log=entry("1.0.1", "unreleased", "Nothing about it.")).run()
        self.assertEqual(len(fails), 1, out)
        self.assertIn("says what the protocol gained since sdk-v1.0.0", fails[0])

    def test_no_sentence_is_owed_when_the_proto_did_not_move(self):
        fails, out = self.fx.write(proto=BASE_PROTO, rust_log=entry("1.0.1", "unreleased", "Docs only."),
                                   docs=DOCS.format(n=0, head="1.0.1")).run()
        self.assertEqual(fails, [], out)

    def test_a_dated_entry_is_history(self):
        self.fx.write()
        git(self.fx.root, "add", "-A")
        git(self.fx.root, "commit", "-qm", "1.0.1")
        git(self.fx.root, "tag", "sdk-v1.0.1")
        stale = GOOD.replace("5 fields", "37 fields")
        fails, out = self.fx.write(rust_log=entry("1.0.1", "2026-03-01", stale)).run()
        # The dated entry is not compared; the docs paragraph is read at the tag.
        self.assertEqual(fails, [], out)
        self.assertIn("is dated: history", out)

    def test_the_other_two_changelogs_are_compared_when_they_say_it(self):
        fails, out = self.fx.write(py_log=entry("0.1.0", "unreleased", GOOD.replace("5 fields", "7 fields"))).run()
        self.assertEqual(len(fails), 1, out)
        self.assertIn("astra-plugin-sdk-python/CHANGELOG.md", fails[0])

    def test_a_retyped_rpc_cannot_go_unmentioned(self):
        silent = GOOD.replace("; it retyped 1 rpc", "")
        fails, out = self.fx.write(rust_log=entry("1.0.1", "unreleased", silent)).run()
        self.assertEqual(len(fails), 1, out)
        self.assertIn("'retyped': 1", out)

    def test_removed_nothing_is_checked(self):
        head = HEAD_PROTO.replace("string id = 1;  //", "string ident = 1;  //")
        fails, out = self.fx.write(proto=head).run()
        self.assertEqual(len(fails), 1, out)
        self.assertIn("nothing was removed or renumbered", fails[0])

    def test_the_docs_count(self):
        fails, out = self.fx.write(docs=DOCS.format(n=37, head="1.0.1")).run()
        self.assertEqual(len(fails), 1, out)
        self.assertIn("docs/en/versioning.md", fails[0])

    def test_the_docs_count_reads_a_released_head_at_its_tag(self):
        # 1.0.1 is tagged with 5 fields; a later sync adds one more. The page's
        # "between sdk-v1.0.0 and 1.0.1" is history and stays 5.
        self.fx.write()
        git(self.fx.root, "add", "-A")
        git(self.fx.root, "commit", "-qm", "1.0.1")
        git(self.fx.root, "tag", "sdk-v1.0.1")
        later = HEAD_PROTO.replace("message Req { string id = 1; optional bool dry = 2; }",
                              "message Req { string id = 1; optional bool dry = 2; int32 x = 3; }")
        fails, out = self.fx.write(rust="1.0.2", proto=later, docs=DOCS.format(n=5, head="1.0.1"),
                                   rust_log=entry("1.0.2", "unreleased", GOOD.replace(
                                       "sdk-v1.0.0", "sdk-v1.0.1").replace("5 fields on 3 messages", "1 field on 1 message").replace(
                                       "1 new message and 1 new rpc; it retyped 1 rpc", "0 new messages and 0 new rpcs"))).run()
        self.assertEqual(fails, [], out)

    def test_a_docs_count_up_to_a_release_nobody_can_measure(self):
        fails, out = self.fx.write(docs=DOCS.format(n=5, head="1.0.5")).run()
        self.assertEqual(len(fails), 1, out)
        self.assertIn("1.0.5, which is measurable", fails[0])

    def test_a_docs_page_without_the_paragraph(self):
        fails, out = self.fx.write(docs="# Versioning\n\nNo count here.\n").run()
        self.assertEqual(len(fails), 1, out)
        self.assertIn("has one paragraph", fails[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
