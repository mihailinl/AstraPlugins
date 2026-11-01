#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""tools/check-games-goldens.py is green on this tree, and a check that has
only ever seen a green tree has not shown it can see anything. Each test
below takes one real golden, flips the ONE fact its rule or schema cares
about, and asserts the verdict flips with it — the same shape
test_attestation_commands.py uses for C40, applied to the games goldens
(testdata/games/vectors.json) instead of the release-notes commands.

    python3 tools/test_check_games_goldens.py        # what the couplings job runs

No network. No filesystem writes outside the OS temp directory tempfile.py
already gives each test.
"""

from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

spec = importlib.util.spec_from_file_location("ggold", ROOT / "tools/check-games-goldens.py")
ggold = importlib.util.module_from_spec(spec)
sys.modules["ggold"] = ggold
spec.loader.exec_module(ggold)


def manifest(name_glob: str) -> dict:
    for sub in ("valid", "invalid"):
        p = ROOT / "testdata/games/manifests" / sub
        for f in p.glob(name_glob):
            return ggold.load_doc(f"manifests/{sub}/{f.name}")
    raise FileNotFoundError(name_glob)


class EndToEnd(unittest.TestCase):
    def test_the_real_tree_is_green(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools/check-games-goldens.py")],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all checks pass", r.stdout)


class ManifestSchema(unittest.TestCase):
    def test_removing_target_anti_cheat_turns_a_good_manifest_bad(self):
        doc = copy.deepcopy(manifest("game-specific-link.toml"))
        ok_before, _ = ggold.schema_ok(doc, ggold.load_schema("spec/games/schemas/manifest.schema.json"))
        self.assertTrue(ok_before)
        del doc["target"]["anti_cheat"]
        ok_after, detail = ggold.schema_ok(doc, ggold.load_schema("spec/games/schemas/manifest.schema.json"))
        self.assertFalse(ok_after, "a manifest missing target.anti_cheat must be refused")
        self.assertIn("anti_cheat", detail)


class EngineUndeclared(unittest.TestCase):
    def test_fixing_the_mismatch_makes_the_rule_pass(self):
        doc = copy.deepcopy(manifest("engine-undeclared-mismatch.toml"))
        self.assertFalse(ggold.rule_engine_undeclared(doc), "the golden must still be a violation unmodified")
        doc["target"]["engine"] = "source2"  # now matches integration.engine's own code
        self.assertTrue(ggold.rule_engine_undeclared(doc), "once target.engine matches, the rule must pass")

    def test_removing_the_declaration_entirely_is_not_a_violation(self):
        doc = copy.deepcopy(manifest("engine-undeclared.toml"))
        del doc["integration"]["engine"]
        self.assertTrue(
            ggold.rule_engine_undeclared(doc),
            "a manifest with no [integration.engine] at all has nothing to declare",
        )


class LoaderPolicyConflict(unittest.TestCase):
    def test_disjoint_lists_pass(self):
        doc = copy.deepcopy(manifest("loader-policy-conflict.toml"))
        self.assertFalse(ggold.rule_loader_policy_conflict(doc))
        doc["integration"]["loader"]["keep_if_present"] = ["s2bridge.ini"]
        self.assertTrue(ggold.rule_loader_policy_conflict(doc))


class CapabilityUndeclared(unittest.TestCase):
    def test_declaring_the_capability_fixes_it(self):
        doc = copy.deepcopy(manifest("capability-undeclared.toml"))
        self.assertFalse(ggold.rule_capability_undeclared(doc))
        doc["integration"]["capabilities"] = {"companion": ["presentation"]}
        self.assertTrue(ggold.rule_capability_undeclared(doc))

    def test_no_bridge_token_at_all_needs_no_declaration(self):
        doc = copy.deepcopy(manifest("capability-undeclared.toml"))
        doc["config_writes"][0]["set"]["Token"] = "static-value"
        self.assertTrue(ggold.rule_capability_undeclared(doc))


class ReservedIdAndName(unittest.TestCase):
    def test_a_non_reserved_prefix_passes(self):
        doc = copy.deepcopy(manifest("reserved-id.toml"))
        self.assertFalse(ggold.rule_reserved_id(doc))
        doc["integration"]["id"] = "someone.totally-official-mod"
        self.assertTrue(ggold.rule_reserved_id(doc))

    def test_removing_the_reserved_word_passes(self):
        doc = copy.deepcopy(manifest("reserved-name.toml"))
        self.assertFalse(ggold.rule_reserved_name(doc))
        doc["integration"]["name"] = "Astra Companion"
        self.assertTrue(ggold.rule_reserved_name(doc))


class DescriptorAnchor(unittest.TestCase):
    def test_adding_a_literal_anchor_fixes_the_grief_fixture(self):
        doc = copy.deepcopy(ggold.load_doc("descriptors/hostile/grief-unknown-games-no-anchor.toml"))
        self.assertFalse(ggold.rule_descriptor_anchor_invalid(doc))
        doc["rule"][0]["require"] = [{"listed": "engine2.dll", "kind": "file"}]
        self.assertTrue(ggold.rule_descriptor_anchor_invalid(doc))

    def test_unity_builtin_has_a_valid_anchor(self):
        doc = ggold.load_doc("descriptors/builtin/unity.toml")
        self.assertTrue(ggold.rule_descriptor_anchor_invalid(doc))

    def test_a_wildcard_anchor_is_invalid(self):
        doc = copy.deepcopy(ggold.load_doc("descriptors/builtin/unity.toml"))
        for rule in doc["rule"]:
            rule["require"] = [{"listed": "*.dll", "kind": "file"}]
        self.assertFalse(ggold.rule_descriptor_anchor_invalid(doc))


class EngineCodeReserved(unittest.TestCase):
    def test_an_unclaimed_code_passes(self):
        self.assertFalse(ggold.rule_engine_code_reserved(["unity-mono"]))
        self.assertTrue(ggold.rule_engine_code_reserved(["source2"]))

    def test_the_sentinel_unknown_is_reserved_too(self):
        self.assertFalse(ggold.rule_engine_code_reserved(["unknown"]))


class EngineCodeTaken(unittest.TestCase):
    def test_a_different_code_does_not_collide(self):
        claimant = ggold.load_doc("descriptors/hostile/hijack-updates-code-squatting.toml")
        prior = ggold.load_doc("manifests/valid/foundation-owns-engine.toml")
        self.assertFalse(ggold.rule_engine_code_taken(claimant, prior))
        other = copy.deepcopy(claimant)
        other["engine"]["codes"] = {"a-totally-different-code": "Different"}
        self.assertTrue(ggold.rule_engine_code_taken(other, prior))


class IndexFreshness(unittest.TestCase):
    def test_issued_at_exactly_on_the_boundary_passes(self):
        now = 1_700_000_000
        self.assertTrue(ggold.rule_issued_at_too_far_ahead({"issued_at": now + 86400}, now))
        self.assertFalse(ggold.rule_issued_at_too_far_ahead({"issued_at": now + 86401}, now))

    def test_expiry_span_exactly_eight_days_passes(self):
        issued = 1_700_000_000
        self.assertTrue(ggold.rule_expiry_span_too_long({"issued_at": issued, "expires_at": issued + 8 * 86400}))
        self.assertFalse(ggold.rule_expiry_span_too_long({"issued_at": issued, "expires_at": issued + 8 * 86400 + 1}))


class ContentSchema(unittest.TestCase):
    def test_a_disallowed_kind_is_refused_and_a_real_one_passes(self):
        doc = copy.deepcopy(manifest("content-parts.toml"))
        schema = ggold.load_schema("spec/games/schemas/manifest.schema.json")
        ok_before, _ = ggold.schema_ok(doc, schema)
        self.assertTrue(ok_before)
        doc["integration"]["content"][0]["kind"] = "command"
        ok_after, detail = ggold.schema_ok(doc, schema)
        self.assertFalse(ok_after, "'command' is in the shared asset-rights rule, never in a GI's content kinds")

    def test_a_path_traversal_is_refused_and_a_relative_path_passes(self):
        doc = copy.deepcopy(manifest("content-parts.toml"))
        schema = ggold.load_schema("spec/games/schemas/manifest.schema.json")
        doc["integration"]["content"][0]["path"] = "../../outside.png"
        ok, _detail = ggold.schema_ok(doc, schema)
        self.assertFalse(ok)
        doc["integration"]["content"][0]["path"] = "art/outside.png"
        ok2, _detail2 = ggold.schema_ok(doc, schema)
        self.assertTrue(ok2)

    def test_a_builtin_style_colon_is_refused(self):
        doc = copy.deepcopy(manifest("content-parts.toml"))
        schema = ggold.load_schema("spec/games/schemas/manifest.schema.json")
        doc["integration"]["content"][0]["path"] = "builtin:default-climb"
        ok, _detail = ggold.schema_ok(doc, schema)
        self.assertFalse(ok, "a builtin: reference must never read as a declared part")


class IntegrationUsesReserved(unittest.TestCase):
    def test_removing_the_uses_table_makes_the_manifest_valid_again(self):
        doc = copy.deepcopy(ggold.load_doc("manifests/invalid/integration-uses-reserved.toml"))
        schema = ggold.load_schema("spec/games/schemas/manifest.schema.json")
        ok_before, _ = ggold.schema_ok(doc, schema)
        self.assertFalse(ok_before)
        del doc["integration"]["uses"]
        ok_after, _ = ggold.schema_ok(doc, schema)
        self.assertTrue(ok_after)


class ContentCoverage(unittest.TestCase):
    def test_declaring_the_extra_file_fixes_undeclared(self):
        root = ggold.DATA / "content/releases/undeclared"
        doc = copy.deepcopy(ggold.load_doc("content/releases/undeclared/astra-gi.toml"))
        found = ggold.find_content_files(root)
        cov = ggold.content_coverage(doc, found)
        self.assertIn("audio/theme.ogg", cov["undeclared"])
        doc["integration"]["content"].append(
            {"path": "audio/theme.ogg", "kind": "audio", "title": "t", "credit": "c", "licence": "CC0-1.0"}
        )
        cov2 = ggold.content_coverage(doc, found)
        self.assertEqual(cov2["undeclared"], [])

    def test_providing_the_missing_file_fixes_missing(self):
        root = ggold.DATA / "content/releases/missing"
        doc = copy.deepcopy(ggold.load_doc("content/releases/missing/astra-gi.toml"))
        found = ggold.find_content_files(root)
        cov = ggold.content_coverage(doc, found)
        self.assertIn("animations/climb.fbx", cov["missing"])
        found2 = dict(found)
        found2["animations/climb.fbx"] = b"Kaydara FBX Binary  \x00"
        cov2 = ggold.content_coverage(doc, found2)
        self.assertEqual(cov2["missing"], [])

    def test_removing_the_duplicate_entry_fixes_duplicate(self):
        root = ggold.DATA / "content/releases/duplicate"
        doc = copy.deepcopy(ggold.load_doc("content/releases/duplicate/astra-gi.toml"))
        found = ggold.find_content_files(root)
        cov = ggold.content_coverage(doc, found)
        self.assertIn("animations/climb.fbx", cov["duplicates"])
        doc["integration"]["content"].pop()
        cov2 = ggold.content_coverage(doc, found)
        self.assertEqual(cov2["duplicates"], [])

    def test_a_renamed_loader_is_not_picked_up_as_content_by_extension_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evil.png").write_bytes(b"MZ" + b"\x00" * 30)  # a PE header, not a PNG
            found = ggold.find_content_files(root)
            self.assertEqual(found, {}, "extension alone must never be enough -- manifest.md §2.7.1")
            (root / "real.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
            found2 = ggold.find_content_files(root)
            self.assertEqual(set(found2), {"real.png"})


class VrmLicenceGate(unittest.TestCase):
    def test_vrm0_only_author_is_refused_and_everyone_passes(self):
        meta = {"allowedUserName": "OnlyAuthor"}
        self.assertFalse(ggold.rule_vrm_licence_refused("0.x", meta)[0])
        meta["allowedUserName"] = "Everyone"
        self.assertTrue(ggold.rule_vrm_licence_refused("0.x", meta)[0])

    def test_vrm0_licence_name_prohibited_is_refused(self):
        self.assertFalse(ggold.rule_vrm_licence_refused("0.x", {"licenseName": "Redistribution_Prohibited"})[0])
        self.assertTrue(ggold.rule_vrm_licence_refused("0.x", {"licenseName": "Redistribution_Allowed"})[0])

    def test_vrm1_only_author_is_refused_and_everyone_passes(self):
        meta = {"avatarPermission": "onlyAuthor"}
        self.assertFalse(ggold.rule_vrm_licence_refused("1.0", meta)[0])
        meta["avatarPermission"] = "everyone"
        self.assertTrue(ggold.rule_vrm_licence_refused("1.0", meta)[0])

    def test_vrm1_allow_redistribution_false_is_refused(self):
        self.assertFalse(ggold.rule_vrm_licence_refused("1.0", {"allowRedistribution": False})[0])
        self.assertTrue(ggold.rule_vrm_licence_refused("1.0", {"allowRedistribution": True})[0])

    def test_an_absent_field_is_not_itself_a_refusal(self):
        self.assertTrue(ggold.rule_vrm_licence_refused("0.x", {})[0])
        self.assertTrue(ggold.rule_vrm_licence_refused("1.0", {})[0])

    def test_the_fixture_files_parse_to_the_right_refusal(self):
        cases = [
            ("refused-vrm0-only-author.vrm", "extensions.VRM.meta.allowedUserName", "OnlyAuthor"),
            ("refused-vrm1-only-author.vrm", "extensions.VRMC_vrm.meta.avatarPermission", "onlyAuthor"),
        ]
        for name, want_field, want_value in cases:
            raw = (ggold.DATA / "content/vrm" / name).read_bytes()
            ok, field, value = ggold.vrm_gate_refusal(raw)
            self.assertFalse(ok)
            self.assertEqual(field, want_field)
            self.assertEqual(value, want_value)

    def test_the_allowed_fixture_passes(self):
        raw = (ggold.DATA / "content/vrm/allowed.vrm").read_bytes()
        self.assertTrue(ggold.vrm_gate_refusal(raw)[0])

    def test_a_non_glb_file_has_no_vrm_meta_at_all(self):
        self.assertIsNone(ggold.extract_vrm_meta(b"not a glb"))


class WithdrawnSecurity(unittest.TestCase):
    def test_security_with_revoke_passes(self):
        doc = copy.deepcopy(ggold.load_doc("withdrawn/invalid-security-not-revoke.json"))
        self.assertFalse(ggold.rule_security_requires_revoke(doc))
        doc["rows"][0]["act"] = "revoke"
        doc["rows"][0]["floor_effect"] = "no-play"
        self.assertTrue(ggold.rule_security_requires_revoke(doc))


if __name__ == "__main__":
    unittest.main()
