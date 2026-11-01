#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""tools/check-content-goldens.py is green on this tree, and a check that has
only ever seen a green tree has not shown it can see anything. Two kinds of
test below, the shape tools/test_check_games_goldens.py uses:

  * golden flips — take a real golden, change the ONE fact its rule reads,
    and assert the verdict flips with it;
  * rule mutations — break one rule INSIDE the checker (the guard the design
    note §10 names: "merge the two key sets", "let Unknown through", "drop
    the rule") and assert the whole run turns red on exactly the goldens that
    rule exists for. A rule whose mutation leaves the run green guards nothing.

    python3 tools/test_check_content_goldens.py -v

No network. No writes outside the OS temp directory.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

_spec = importlib.util.spec_from_file_location("cgold", ROOT / "tools/check-content-goldens.py")
cg = importlib.util.module_from_spec(_spec)
sys.modules["cgold"] = cg
_spec.loader.exec_module(cg)
C = cg.C

V = cg.load_json("vectors.json")
TRUST = cg.load_json("trust/trust.json")["signed"]


def run_quiet() -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cg.main()
    return rc, buf.getvalue()


def failed(out: str) -> list[str]:
    return [line[5:].split(" — ")[0] for line in out.splitlines() if line.startswith("FAIL ")]


class Mutation:
    """Patch one attribute of the checker module, restore it afterwards."""

    def __init__(self, name: str, value):
        self.name, self.value = name, value

    def __enter__(self):
        self.old = getattr(cg, self.name)
        setattr(cg, self.name, self.value)

    def __exit__(self, *exc):
        setattr(cg, self.name, self.old)


class EndToEnd(unittest.TestCase):
    def test_the_real_tree_is_green(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools/check-content-goldens.py")],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn("all checks pass", r.stdout)

    def test_the_generator_and_the_schemas_are_current(self):
        for cmd in (["testdata/content/gen.py", "--check"], ["tools/gen-content-schemas.py", "--check"]):
            r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Primitives(unittest.TestCase):
    def test_rfc8032_vector_1(self):
        seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        self.assertEqual(C.public_key(seed).hex(), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig = C.sign(seed, b"")
        self.assertTrue(sig.hex().startswith("e5564300c360ac729086e2cc806e828a"))
        self.assertTrue(C.verify(C.public_key(seed), b"", sig))

    def test_verify_is_strict_about_s(self):
        seed = C.test_seed("strictness")
        sig = C.sign(seed, b"m")
        s = int.from_bytes(sig[32:], "little") + C._L  # the malleable twin a permissive verifier accepts
        self.assertFalse(C.verify(C.public_key(seed), b"m", sig[:32] + s.to_bytes(32, "little")))

    def test_jcs_sorts_by_utf16_not_code_point(self):
        # by code point U+E000 sorts first; in UTF-16 code units U+1F600 (0xD83D…) sorts first. RFC 8785 is UTF-16.
        doc = {"": 1, "\U0001f600": 2}
        self.assertEqual(C.jcs(doc).decode("utf-8"), '{"\U0001f600":2,"":1}')

    def test_a_changed_byte_moves_the_part_digest(self):
        files = {"animpacks/wave/animpack.toml": b'name = "wave"\n', "animpacks/wave/clips/a.fbx": b"FBX-A",
                 "animpacks/wave/clips/b.fbx": b"FBX-B"}
        self.assertEqual(C.part_digest(files), V["part_digest"][0]["part_digest"])
        files["animpacks/wave/clips/b.fbx"] = b"FBX-C"
        self.assertNotEqual(C.part_digest(files), V["part_digest"][0]["part_digest"])

    def test_the_part_digest_ignores_input_order_but_not_names(self):
        a = {"x/b": b"1", "x/a": b"2"}
        self.assertEqual(C.part_digest(a), C.part_digest(dict(reversed(list(a.items())))))
        self.assertNotEqual(C.part_digest(a), C.part_digest({"x/c": b"1", "x/a": b"2"}))


class EverySemanticGoldenBreaksExactlyItsRule(unittest.TestCase):
    def test_the_named_rule_passes_on_valid_and_fails_on_the_golden(self):
        n = 0
        for section, doc in (("index", "index"), ("withdrawn", "withdrawn")):
            for v in V[section]:
                if v.get("check") != "semantic":
                    continue
                n += 1
                valid = cg.load_json(f"{section}/{v['kind']}/valid.json")["signed"]
                bad = cg.load_json(v["file"])["signed"]
                rule = cg.rules_for(v["kind"], doc)[v["rule"]]
                ctx = {"now": v.get("now", V["now"]), "kind": v["kind"]}
                self.assertTrue(rule(valid, ctx), f"{v['rule']} refuses the VALID {v['kind']} {doc}")
                self.assertFalse(rule(bad, ctx), f"{v['rule']} accepts {v['file']}")
        self.assertGreater(n, 20)


class GoldenFlips(unittest.TestCase):
    def test_restoring_the_act_makes_security_pairs_pass(self):
        s = copy.deepcopy(cg.load_json("withdrawn/commands/security-reason-retired-act.json")["signed"])
        self.assertFalse(cg.rule_security_pairs(s, {}))
        s["rows"][0]["act"] = "security"
        self.assertTrue(cg.rule_security_pairs(s, {}))

    def test_fixing_next_not_before_restores_the_kinds_keys(self):
        doc = copy.deepcopy(cg.load_json("trust/kind-keys/next-not-later.json"))
        self.assertEqual(cg.kind_keys_for(doc, "commands", V["now"]), [])
        next(r for r in doc["kind_keys"] if r["kind"] == "commands" and r["role"] == "next")["not_before"] = "2026-12-01T00:00:00Z"
        self.assertEqual(len(cg.kind_keys_for(doc, "commands", V["now"])), 2)

    def test_a_re_signed_tampered_index_verifies_again(self):
        env = copy.deepcopy(cg.load_json("index/commands/tampered-after-signing.json"))
        self.assertEqual(cg.verify_doc(env, "commands", "index", TRUST, V["now"])[1], "signature-invalid")
        seed = C.test_seed("astra-commands-2026a")
        env["signatures"] = [{"key_id": "astra-commands-2026a",
                              "sig": C.b64(C.sign(seed, C.signing_digest("astra.commands.index/1", env["signed"])))}]
        self.assertEqual(cg.verify_doc(env, "commands", "index", TRUST, V["now"])[0], "astra-commands-2026a")

    def test_declaring_the_hotkey_makes_the_trigger_golden_pass(self):
        cmd = cg.load_json("commands/hostile/undeclared-trigger-cap.command.json")
        with self.assertRaises(cg.Refusal):
            cg.ingest_command(cmd, {"capabilities": ["plays_audio"], "danger": "low", "requires": []})
        got = cg.ingest_command(cmd, {"capabilities": ["binds_hotkey", "plays_audio"], "danger": "low", "requires": []})
        self.assertEqual(got["capabilities"], ["binds_hotkey", "plays_audio"])

    def test_startup_and_schedule_are_their_own_words(self):
        caps = cg.derive_command(cg.load_json("commands/valid/morning.command.json"))["capabilities"]
        self.assertIn("on_startup", caps)
        self.assertNotIn("on_event:startup", caps)
        caps = cg.derive_command(cg.load_json("commands/valid/roll-dice.command.json"))["capabilities"]
        self.assertIn("on_schedule", caps)


def _all_keys(member, kind, now):
    """Mutation: merge every kind's keys (and the index keys) into one set."""
    out = []
    for r in member.get("kind_keys", []):
        if r.get("alg") == "ed25519" and C.unb64(r.get("public_key", "")):
            out.append((r["key_id"], C.unb64(r["public_key"])))
    for r in member.get("index_keys", []):
        out.append((r["key_id"], C.unb64(r["public_key"])))
    return out


class RuleMutationsTurnTheRunRed(unittest.TestCase):
    def assertRedOn(self, mutation: Mutation, *names: str):
        with mutation:
            rc, out = run_quiet()
        self.assertEqual(rc, 1, f"the run stayed green under the mutation of {mutation.name}")
        got = failed(out)
        for n in names:
            self.assertTrue(any(n in f for f in got), f"{n} did not fail; failed: {got}")

    def test_merging_the_key_sets(self):
        self.assertRedOn(Mutation("kind_keys_for", _all_keys),
                         "index/commands/signed-by-models-key", "index/commands/signed-by-index-key")

    def test_letting_unknown_through(self):
        orig = cg.vrm_verdict
        self.assertRedOn(Mutation("vrm_verdict", lambda raw, path="": "allowed" if orig(raw, path) == "unknown" else orig(raw, path)),
                         "archives/vrm-no-meta")

    def test_reading_only_the_first_meta(self):
        orig = cg.vrm_verdict
        self.assertRedOn(Mutation("vrm_verdict", lambda raw, path="": "allowed" if orig(raw, path) == "conflict" else orig(raw, path)),
                         "archives/vrm-metas-disagree")

    def test_dropping_the_exec_and_network_rule(self):
        self.assertRedOn(Mutation("EXEC_CAPS", set()), "commands/build-and-ask")

    def test_skipping_unknown_action_types(self):
        caps = dict(cg.ACTION_CAPS)
        caps["download_and_run"] = []
        self.assertRedOn(Mutation("ACTION_CAPS", caps), "commands/unknown-node-action")

    def test_skipping_unknown_node_types(self):
        self.assertRedOn(Mutation("NODE_TYPES", cg.NODE_TYPES | {"teleport"}), "commands/unknown-node")

    def test_accepting_an_unknown_event_name(self):
        self.assertRedOn(Mutation("KNOWN_EVENTS", cg.KNOWN_EVENTS | {"usb_inserted"}), "commands/unknown-event-name")

    def test_raising_the_entry_cap(self):
        self.assertRedOn(Mutation("MAX_ENTRIES", 20000), "archives/entries-10001")

    def test_forgetting_the_stored_rule(self):
        self.assertRedOn(Mutation("STORED_ONLY", ()), "archives/deflated-vrm")

    def test_trusting_the_ratio(self):
        self.assertRedOn(Mutation("MAX_RATIO", 10**9), "archives/ratio-bomb")

    def test_a_non_sticky_client(self):
        def forgetful(sc, now, member):
            states = []
            for f in sc["sequence"]:
                rows = cg.load_json(f)["signed"]["rows"]
                states.append("disarmed" if any(r["id"] == sc["installed"]["id"] for r in rows) else "armed")
            return states
        self.assertRedOn(Mutation("scenario_sticky", forgetful), "scenario/sticky-security")

    def test_a_looser_withdrawn_bound(self):
        self.assertRedOn(Mutation("WITHDRAWN_MAX_AGE", 7201), "scenario/withdrawn-freshness")

    def test_one_domain_for_everything(self):
        orig = C.signing_digest
        with Mutation("verify_doc", lambda env, kind, doc, member, now, retired=frozenset():
                      _verify_any_domain(env, kind, member, now, orig)):
            rc, out = run_quiet()
        self.assertEqual(rc, 1)
        self.assertTrue(any("signed-under-models-domain" in f for f in failed(out)), failed(out))

    def test_no_one_way_switch(self):
        orig = cg.verify_doc
        self.assertRedOn(Mutation("verify_doc", lambda env, kind, doc, member, now, retired=frozenset():
                                  orig(env, kind, doc, member, now)), "scenario/one-way-switch")

    def test_a_pack_digest_that_is_a_part_digest(self):
        orig = cg.scenario_ingest_refs

        def lax(sc, now, member, what):
            try:
                return orig(sc, now, member, what)
            except cg.Refusal as r:
                if r.code.endswith("_DIGEST"):
                    return "accept"
                raise
        self.assertRedOn(Mutation("scenario_ingest_refs", lax), "scenario/pack-member-digest",
                         "scenario/character-requires-digest")


def _verify_any_domain(env, kind, member, now, digest_fn):
    """Mutation: accept a signature over ANY content domain of the kind's keys."""
    for d in ("index", "withdrawn"):
        for other in cg.KINDS:
            dig = digest_fn(f"astra.{other}.{d}/1", env.get("signed"))
            for s in env.get("signatures") or []:
                for kid, pk in cg.kind_keys_for(member, kind, now):
                    if C.verify(pk, dig, C.unb64(s["sig"]) or b""):
                        return kid, None
    return None, "signature-invalid"


class SelfAttackFixes(unittest.TestCase):
    """The four classes the author's own attack found (OPEN.md O-20, O-21):
    each guard is removed in turn and the run must go red on its golden."""

    def assertRedOn(self, mutation, *names):
        RuleMutationsTurnTheRunRed.assertRedOn(self, mutation, *names)

    def test_a_last_wins_loader(self):
        import json as _json
        self.assertRedOn(Mutation("load_json", lambda rel: _json.loads((cg.DATA / rel).read_text(encoding="utf-8"))),
                         "index/commands/duplicate-member-name", "commands/duplicate-type-key")

    def test_a_lax_glb_reader(self):
        orig = cg.C.strict_loads
        lax = lambda t: __import__("json").loads(t if isinstance(t, str) else t.decode("utf-8"))  # noqa: E731
        cg.C.strict_loads = lax
        try:
            rc, out = run_quiet()
        finally:
            cg.C.strict_loads = orig
        self.assertEqual(rc, 1)
        got = failed(out)
        for n in ("archives/vrm-duplicate-key", "archives/manifest-duplicate-key"):
            self.assertTrue(any(n in f for f in got), got)

    def test_no_tiling_rule(self):
        orig = cg.walk_zip

        def untiled(b):
            # re-run the walk with the tiling loop's refusals swallowed
            try:
                return orig(b)
            except cg.Refusal as r:
                if "gap" in r.detail or "overlap" in r.detail or "between the last" in r.detail:
                    return {"\0order": b"[]"}
                raise
        self.assertRedOn(Mutation("walk_zip", untiled), "archives/gap-between-entries", "archives/overlapping-entries")

    def test_a_fetch_clock_only(self):
        self.assertRedOn(Mutation("WITHDRAWN_MAX_DOC_AGE", 8 * 86400), "scenario/withdrawn-freshness")

    def test_an_unparseable_range_failing_open(self):
        def fail_open(version, rng):
            try:
                return cg.in_range(version, rng)
            except (ValueError, AttributeError):
                return False  # the mutation: an unparseable range covers NOTHING
        self.assertRedOn(Mutation("covers", fail_open),
                         "scenario/unparseable-range-covers-all")


class F15ExtractorMatchesAstra(unittest.TestCase):
    """Astra origin/main 5d5ae5e83: the three places the first draft's tables disagreed."""

    def assertRedOn(self, mutation, *names):
        RuleMutationsTurnTheRunRed.assertRedOn(self, mutation, *names)

    def test_execute_always_a_shell(self):
        self.assertRedOn(Mutation("EXECUTE_OPEN_MODE", "\0never"), "commands/open-file")

    def test_linear_actions_take_node_types(self):
        self.assertRedOn(Mutation("LINEAR_TAGS", cg.LINEAR_TAGS | {"open_file"}), "commands/linear-open-file")

    def test_event_name_read_from_the_node_itself(self):
        orig_derive = cg.derive_command

        def derive(cmd):
            cmd = copy.deepcopy(cmd)
            for n in ((cmd.get("workflow") or {}).get("nodes") or {}).values():
                d = n.get("data") or {}
                if n.get("node_type") == "trigger" and "event_name" in d:
                    d["config"] = {"event_name": d["event_name"]}  # the old reading: the name wherever it is
            return orig_derive(cmd)
        self.assertRedOn(Mutation("derive_command", derive), "commands/event-node-no-config")


def _swallowing(detail_words, fallback=None):
    """A walk_zip mutation: the refusal whose detail names one of `detail_words` is not raised."""
    orig = cg.walk_zip

    def walk(b):
        try:
            return orig(b)
        except cg.Refusal as r:
            if any(w in r.detail for w in detail_words):
                return fallback(b) if fallback else {"\0order": b"[]"}
            raise
    return walk


class F1CountCoversTheDirectory(unittest.TestCase):
    def test_trusting_the_count(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, Mutation("walk_zip", _swallowing(["more than the end record counts"])),
            "archives/count-short-of-directory")

    def test_the_golden_hides_a_real_entry(self):
        b = (cg.DATA / "archives/hostile/count-short-of-directory.astrachar").read_bytes()
        self.assertEqual(b.count(b"PK\x01\x02"), 3)
        self.assertEqual(int.from_bytes(b[-12:-10], "little"), 2)


class F5DataDescriptors(unittest.TestCase):
    def test_an_unread_descriptor(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, Mutation("walk_zip", _swallowing(["the data descriptor disagrees"])), "archives/descriptor-crc-differs")

    def test_bit3_allowed_on_stored(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, Mutation("walk_zip", _swallowing(["bit 3 on a Stored entry"])), "archives/stored-bit3")

    def test_bit3_compared_on_one_side_only(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, Mutation("walk_zip", _swallowing(["local and central headers disagree"])), "archives/bit3-local-only")

    def test_valid_descriptors_are_accepted_both_ways(self):
        for n in ("model-aiko-descriptor", "model-aiko-descriptor-nosig"):
            raw = (cg.DATA / f"archives/valid/{n}.astrachar").read_bytes()
            self.assertEqual(cg.ingest_bundle(raw, {})["verdict"], "accept", n)


class F7DirectoryOrderIsFileOrder(unittest.TestCase):
    def test_order_unchecked(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, Mutation("walk_zip", _swallowing(["order is not the file's order"])), "archives/manifest-first-by-offset")

    def test_the_golden_is_last_in_the_directory_only(self):
        b = (cg.DATA / "archives/hostile/manifest-first-by-offset.astrachar").read_bytes()
        self.assertEqual(b[30:30 + len("astrachar.json")], b"astrachar.json")
        cd = b.rfind(b"PK\x01\x02")
        self.assertEqual(b[cd + 46:cd + 46 + len("astrachar.json")], b"astrachar.json")


class F8NoZip64(unittest.TestCase):
    def test_zip64_markers_tolerated(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, Mutation("walk_zip", _swallowing(["zip64 sentinel", "zip64 extra"])),
            "archives/zip64-extra", "archives/zip64-size-sentinel", "archives/zip64-offset-sentinel")

    def test_cd_size_sentinel_tolerated(self):
        orig = cg.end_record

        def lax(b):
            try:
                return orig(b)
            except cg.Refusal as r:
                if "zip64" in r.detail:
                    return 0, 0, 0  # an empty archive: anything but the zip64 refusal
                raise
        RuleMutationsTurnTheRunRed.assertRedOn(self, Mutation("end_record", lax), "archives/zip64-cd-size-sentinel")


class F2VerdictFollowsContent(unittest.TestCase):
    def assertRedOn(self, mutation, *names):
        RuleMutationsTurnTheRunRed.assertRedOn(self, mutation, *names)

    def test_selecting_by_extension(self):
        self.assertRedOn(Mutation("judged", lambda p, b: p.lower().endswith((".vrm", ".glb"))), "archives/gltf-prohibited")

    def test_names_and_magic_unchecked(self):
        self.assertRedOn(Mutation("name_matches_magic", lambda p, b: True), "archives/accessory-glb-renamed")

    def test_a_body_under_any_name(self):
        # two rules hold this golden (the body's suffix, and name/magic agreement); only both gone lets it in
        with Mutation("name_matches_magic", lambda p, b: True):
            self.assertRedOn(Mutation("BODY_EXT", ""), "archives/body-renamed-bin")

    def test_files_outside_parts_ignored(self):
        orig = cg.parts_of

        def lax(files, body, settings_dir=None):
            try:
                return orig(files, body, settings_dir)
            except cg.Refusal:
                return orig({p: b for p, b in files.items() if not p.endswith(".bin")}, body, settings_dir)
        self.assertRedOn(Mutation("parts_of", lax), "archives/file-outside-parts")


class F3UnrecognisedIsUnknown(unittest.TestCase):
    def assertRedOn(self, mutation, *names):
        RuleMutationsTurnTheRunRed.assertRedOn(self, mutation, *names)

    def test_unknown_licence_names_allowed(self):
        orig = cg._redistribution0
        self.assertRedOn(Mutation("_redistribution0", lambda m: "allowed" if orig(m) == "unknown" else orig(m)),
                         "archives/vrm0-licence-other")

    def test_unknown_permissions_allowed(self):
        lax = {k: dict(v) for k, v in cg.AVATAR.items()}
        lax["0.x"]["Friends"] = "allowed"
        lax["1.0"]["everyoneButCompetitors"] = "allowed"
        self.assertRedOn(Mutation("AVATAR", lax), "archives/vrm0-user-unrecognised", "archives/vrm1-avatar-unrecognised")

    def test_a_truthy_string(self):
        self.assertRedOn(Mutation("_redistribution1", lambda m: "allowed" if m.get("allowRedistribution") in (True, "true") else "prohibited"),
                         "archives/vrm1-redistribution-string")

    def test_cc_prefix_is_allowed(self):
        orig = cg._redistribution0
        self.assertRedOn(Mutation("_redistribution0", lambda m: "unknown" if m.get("licenseName") == "CC_BY_NC" else orig(m)),
                         "archives/model-vrm0-cc-by-nc")


class F17ParseBeforeEvaluate(unittest.TestCase):
    def test_short_circuit_evaluation(self):
        def lazy(version, rng):
            if not rng.strip():
                raise ValueError("empty")
            x = cg.semver_key(version)
            for part in rng.split(","):
                m = re.fullmatch(r"\s*(<=|>=|<|>|=)?\s*(\S+)\s*", part)
                op, v = (m.group(1) or "="), cg.semver_key(m.group(2))  # raises only when REACHED
                if not {"<=": x <= v, ">=": x >= v, "<": x < v, ">": x > v, "=": x == v}[op]:
                    return False
            return True
        RuleMutationsTurnTheRunRed.assertRedOn(self, Mutation("in_range", lazy), "scenario/unparseable-range-covers-all")


class F9EveryVerifyingKey(unittest.TestCase):
    def test_stopping_at_the_first_signature(self):
        def first_only(env, kind, doc, member, now):
            keys = cg.kind_keys_for(member, kind, now)
            digest = C.signing_digest(f"astra.{kind}.{doc}/1", env.get("signed"))
            for s in env.get("signatures") or []:
                for kid, pk in keys:
                    if C.verify(pk, digest, C.unb64(s["sig"]) or b""):
                        return {kid}, None
            return set(), "signature-invalid"
        RuleMutationsTurnTheRunRed.assertRedOn(self, Mutation("verified_by", first_only),
                                               "scenario/one-way-switch-dual-current-first")


class F14StickyRowsAndCanonicalRanges(unittest.TestCase):
    def assertRedOn(self, mutation, *names):
        RuleMutationsTurnTheRunRed.assertRedOn(self, mutation, *names)

    def _sticky(self, *, only_security=False, lift_wins=False, normalise=False):
        def run(sc, now, member):
            sticky, states, inst = {}, [], sc["installed"]
            for f in sc["sequence"]:
                env = cg.load_json(f)
                rows = {(r["id"], r["versions"], r["at"]): r for r in env["signed"]["rows"]
                        if not only_security or r["act"] == "security"}
                sticky.update(rows)
                for lift in env["signed"]["lifts"]:
                    k = (lift["id"], lift["versions"].replace(" ", "") if normalise else lift["versions"], lift["lifts_at"])
                    if lift_wins or k not in rows:
                        sticky.pop(k, None)
                live = [r for (i, v, _), r in sticky.items() if i == inst["id"] and cg.covers(inst["version"], v)]
                states.append("disarmed" if any(cg.client_effect(r) == "disarm" for r in live) else "blocked" if live else "armed")
            return states
        return run

    def test_only_security_rows_sticky(self):
        self.assertRedOn(Mutation("scenario_sticky", self._sticky(only_security=True)), "scenario/sticky-every-row")

    def test_a_lift_beating_its_row(self):
        self.assertRedOn(Mutation("scenario_sticky", self._sticky(lift_wins=True)), "scenario/sticky-every-row")

    def test_a_space_normalising_lift(self):
        self.assertRedOn(Mutation("scenario_sticky", self._sticky(normalise=True)), "scenario/sticky-every-row")

    def test_non_canonical_ranges_parsed(self):
        lax = re.compile(r".*")
        self.assertRedOn(Mutation("CANONICAL_RANGE", lax), "scenario/unparseable-range-covers-all")

    def test_lift_contradiction_checked_for_security_only(self):
        orig = cg.WITHDRAWN_RULES["lift-not-contradicted"]

        def sec_only(s, ctx):
            sec = {(r["id"], r["versions"], r["at"]) for r in s["rows"] if r["act"] == "security"}
            return all((l["id"], l["versions"], l["lifts_at"]) not in sec for l in s["lifts"])
        cg.WITHDRAWN_RULES["lift-not-contradicted"] = sec_only
        try:
            rc, out = run_quiet()
        finally:
            cg.WITHDRAWN_RULES["lift-not-contradicted"] = orig
        self.assertEqual(rc, 1)
        self.assertTrue(any("lift-contradicts-retired-row" in f for f in failed(out)), failed(out))


class F16NoGuttedCorpus(unittest.TestCase):
    def _vectors(self, mutate):
        orig = cg.load_json

        def load(rel):
            doc = orig(rel)
            if rel == "vectors.json":
                doc = copy.deepcopy(doc)
                mutate(doc)
            return doc
        return Mutation("load_json", load)

    def test_dropping_vectors(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, self._vectors(lambda d: d.update(archives=d["archives"][:3])),
            "every SHA256SUMS path is used by at least one vector", "the run made exactly")

    def test_dropping_a_check_but_keeping_every_file(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, self._vectors(lambda d: d["archives"][0].pop("parts")), "the run made exactly")

    def test_an_ingest_code_with_neither(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, self._vectors(lambda d: d["l1_only"].pop("E_CONTENT_QUOTA")),
            "every ingest code has a golden or an l1_only reason")

    def test_ignoring_revocation_windows(self):
        orig = cg.covers
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, Mutation("ingest_command", lambda cmd, claim, served=None: _old_ingest(cmd, claim, served)),
            "commands/requires-window-unparseable", "commands/requires-rc-revoked-by-release-window")
        self.assertIs(cg.covers, orig)


def _old_ingest(cmd, claim, served):
    """The first draft: a plugin is usable if some listed version is not an exact revoked string."""
    got = cg.derive_command(cmd)
    if got["capabilities"] != sorted(claim["capabilities"]) or got["danger"] != claim["danger"]:
        raise cg.Refusal("E_COMMAND_CAPS_MISMATCH")
    ids = sorted(r["id"] for r in claim["requires"])
    if got["requires"] != ids:
        raise cg.Refusal("E_COMMAND_REQUIRES_MISMATCH")
    for pid in ids if served is not None else []:
        p = served.get(pid) or {"listed": []}
        if not [v for v in p["listed"] if v not in p.get("revoked", [])]:
            raise cg.Refusal("E_COMMAND_REQUIRES_UNLISTED")
    return got


class GlbClassByExtensions(unittest.TestCase):
    def test_classifying_by_name(self):
        # the mutation: anything NAMED .vrma is an animation, whatever it carries
        orig = cg.ingest_bundle

        def by_name(raw, ctx):
            with Mutation("glb_class", lambda b: "animation" if b"VRMC_vrm_animation" in b[:4096] else "other"):
                return orig(raw, ctx)
        RuleMutationsTurnTheRunRed.assertRedOn(self, Mutation("ingest_bundle", by_name), "archives/vrma-avatar-prohibited")

    def test_no_animation_exemption(self):
        RuleMutationsTurnTheRunRed.assertRedOn(
            self, Mutation("glb_class", lambda b: "avatar" if b[:4] == cg.GLB_MAGIC else "other"), "archives/animset-vrma")


class ReasonCodes(unittest.TestCase):
    def test_a_code_cited_but_not_registered_is_caught(self):
        codes = cg.load_codes()
        self.assertIn("E_CONTENT_LICENCE_REFUSED", codes["ingest"])
        self.assertIn("requires-digest-mismatch", codes["client"])
        orig = cg.load_codes

        def without():
            c = copy.deepcopy(orig())
            del c["ingest"]["E_ZIP_HEADERS_INCONSISTENT"]
            return c
        with Mutation("load_codes", without):
            rc, out = run_quiet()
        self.assertEqual(rc, 1)
        self.assertTrue(any("cite is in reason-codes.yaml" in f for f in failed(out)), failed(out))


if __name__ == "__main__":
    unittest.main()
