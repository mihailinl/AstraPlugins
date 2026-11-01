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
import json
import struct
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


class ContentLicenceSource(unittest.TestCase):
    """legal DRAFT-v3.md Part 6 G5: licence_source and E_CONTENT_LICENCE_UNDECLARED."""

    def test_a_non_vrm_part_with_no_declared_licence_is_undeclared_and_a_licence_fixes_it(self):
        doc = copy.deepcopy(ggold.load_doc("content/releases/licence-undeclared/astra-gi.toml"))
        found = ggold.find_content_files(ggold.DATA / "content/releases/licence-undeclared")
        entry = doc["integration"]["content"][0]
        pl = ggold.part_licence(entry, found.get(entry["path"]))
        self.assertIsNone(pl["licence_source"])
        self.assertIsNone(pl["gate_status"], "a non-.vrm path never reaches the VRM gate at all")

        entry["licence"] = "CC0-1.0"
        pl2 = ggold.part_licence(entry, found.get(entry["path"]))
        self.assertEqual(pl2["licence_source"], "declared")

    def test_an_unknown_vrm_falls_back_to_the_declared_licence_and_losing_it_refuses(self):
        doc = copy.deepcopy(ggold.load_doc("content/releases/vrm-unknown-but-declared/astra-gi.toml"))
        found = ggold.find_content_files(ggold.DATA / "content/releases/vrm-unknown-but-declared")
        entry = doc["integration"]["content"][0]
        pl = ggold.part_licence(entry, found.get(entry["path"]))
        self.assertEqual(pl["gate_status"], "unknown")
        self.assertEqual(pl["licence_source"], "declared")

        entry["licence"] = ""
        pl2 = ggold.part_licence(entry, found.get(entry["path"]))
        self.assertEqual(pl2["gate_status"], "unknown", "the gate's own verdict never changes")
        self.assertIsNone(pl2["licence_source"], "with nothing declared either, the part has no licence source at all")

    def test_a_readable_vrm_licence_source_is_vrm_regardless_of_a_declared_licence(self):
        doc = copy.deepcopy(ggold.load_doc("content/releases/allowed/astra-gi.toml"))
        found = ggold.find_content_files(ggold.DATA / "content/releases/allowed")
        entry = next(e for e in doc["integration"]["content"] if e["path"].endswith(".vrm"))
        pl = ggold.part_licence(entry, found.get(entry["path"]))
        self.assertEqual(pl["licence_source"], "vrm")
        self.assertEqual(pl["gate_status"], "ok")


class VrmLicenceGate(unittest.TestCase):
    """legal DRAFT-v3.md Part 6 G4/G5. Each 0.x meta isolates the condition
    under test by setting licenseName to an explicitly-allowed value (the
    rule checks licenseName before allowedUserName); each 1.0 meta sets
    allowRedistribution=True for the same reason."""

    def test_vrm0_only_author_is_refused_and_everyone_passes(self):
        meta = {"licenseName": "CC_BY", "allowedUserName": "OnlyAuthor"}
        self.assertTrue(ggold.rule_vrm_licence_refused("0.x", meta)["refused"])
        meta["allowedUserName"] = "Everyone"
        self.assertFalse(ggold.rule_vrm_licence_refused("0.x", meta)["refused"])

    def test_vrm0_named_people_is_refused(self):
        meta = {"licenseName": "CC_BY", "allowedUserName": "ExplicitlyLicensedPerson"}
        r = ggold.rule_vrm_licence_refused("0.x", meta)
        self.assertTrue(r["refused"])
        self.assertEqual(r["field"], "extensions.VRM.meta.allowedUserName")
        self.assertFalse(r["defaulted"])

    def test_vrm0_licence_name_prohibited_is_refused(self):
        meta = {"allowedUserName": "Everyone", "licenseName": "Redistribution_Prohibited"}
        self.assertTrue(ggold.rule_vrm_licence_refused("0.x", meta)["refused"])
        meta["licenseName"] = "CC_BY"
        self.assertEqual(ggold.rule_vrm_licence_refused("0.x", meta)["verdict"], "allowed")

    def test_vrm0_absent_fields_default_to_refused(self):
        r = ggold.rule_vrm_licence_refused("0.x", {})
        self.assertTrue(r["refused"])
        self.assertEqual(r["field"], "extensions.VRM.meta.licenseName")
        self.assertTrue(r["defaulted"], "licenseName absent must default to prohibited, not to allowed")

    def test_vrm1_only_author_is_refused_and_everyone_passes(self):
        meta = {"allowRedistribution": True, "avatarPermission": "onlyAuthor"}
        self.assertTrue(ggold.rule_vrm_licence_refused("1.0", meta)["refused"])
        meta["avatarPermission"] = "everyone"
        self.assertFalse(ggold.rule_vrm_licence_refused("1.0", meta)["refused"])

    def test_vrm1_named_people_is_refused(self):
        meta = {"allowRedistribution": True, "avatarPermission": "onlySeparatelyLicensedPerson"}
        r = ggold.rule_vrm_licence_refused("1.0", meta)
        self.assertTrue(r["refused"])
        self.assertEqual(r["field"], "extensions.VRMC_vrm.meta.avatarPermission")
        self.assertFalse(r["defaulted"])

    def test_vrm1_allow_redistribution_false_is_refused(self):
        meta = {"avatarPermission": "everyone", "allowRedistribution": False}
        self.assertTrue(ggold.rule_vrm_licence_refused("1.0", meta)["refused"])
        meta["allowRedistribution"] = True
        self.assertFalse(ggold.rule_vrm_licence_refused("1.0", meta)["refused"])

    def test_vrm1_absent_fields_default_to_refused(self):
        r = ggold.rule_vrm_licence_refused("1.0", {})
        self.assertTrue(r["refused"])
        self.assertEqual(r["field"], "extensions.VRMC_vrm.meta.allowRedistribution")
        self.assertTrue(r["defaulted"], "allowRedistribution absent must default to false, not to true")

    def test_the_fixture_files_parse_to_the_right_refusal(self):
        cases = [
            ("refused-vrm0-only-author.vrm", "extensions.VRM.meta.allowedUserName", "OnlyAuthor", False),
            ("refused-vrm1-only-author.vrm", "extensions.VRMC_vrm.meta.avatarPermission", "onlyAuthor", False),
            ("refused-vrm0-named-people.vrm", "extensions.VRM.meta.allowedUserName", "ExplicitlyLicensedPerson", False),
            ("refused-vrm1-named-people.vrm", "extensions.VRMC_vrm.meta.avatarPermission", "onlySeparatelyLicensedPerson", False),
            ("refused-vrm0-redistribution-prohibited.vrm", "extensions.VRM.meta.licenseName", "Redistribution_Prohibited", False),
            ("refused-vrm1-redistribution-false.vrm", "extensions.VRMC_vrm.meta.allowRedistribution", False, False),
            ("refused-vrm0-absent-fields.vrm", "extensions.VRM.meta.licenseName", None, True),
            ("refused-vrm1-absent-fields.vrm", "extensions.VRMC_vrm.meta.allowRedistribution", None, True),
        ]
        for name, want_field, want_value, want_defaulted in cases:
            raw = (ggold.DATA / "content/vrm" / name).read_bytes()
            gate = ggold.vrm_gate(raw)
            self.assertEqual(gate["status"], "refused", name)
            self.assertEqual(gate["refusal"]["field"], want_field, name)
            self.assertEqual(gate["refusal"]["value"], want_value, name)
            self.assertEqual(gate["refusal"]["defaulted"], want_defaulted, name)

    def test_the_allowed_fixtures_pass_and_keep_their_usage_flags(self):
        raw0 = (ggold.DATA / "content/vrm/allowed.vrm").read_bytes()
        gate0 = ggold.vrm_gate(raw0)
        self.assertEqual(gate0["status"], "ok")
        self.assertEqual(gate0["vrm_licence"]["vrm_version"], "0.x")
        for k in ("violentUssageName", "sexualUssageName", "commercialUssageName"):
            self.assertIn(k, gate0["vrm_licence"]["fields"], k)

        raw1 = (ggold.DATA / "content/vrm/allowed-vrm1.vrm").read_bytes()
        gate1 = ggold.vrm_gate(raw1)
        self.assertEqual(gate1["status"], "ok")
        self.assertEqual(gate1["vrm_licence"]["vrm_version"], "1.0")
        for k in ("allowExcessivelyViolentUsage", "allowExcessivelySexualUsage", "allowPoliticalOrReligiousUsage", "allowAntisocialOrHateUsage"):
            self.assertIn(k, gate1["vrm_licence"]["fields"], k)

    def test_unknown_meta_is_flagged_not_refused(self):
        raw = (ggold.DATA / "content/vrm/unknown-no-meta.vrm").read_bytes()
        gate = ggold.vrm_gate(raw)
        self.assertEqual(gate["status"], "unknown")
        self.assertIsNone(gate["vrm_licence"])
        self.assertIsNone(gate["refusal"])

    def test_a_non_glb_file_has_no_vrm_meta_at_all(self):
        self.assertEqual(ggold.extract_vrm_metas(b"not a glb"), {})
        self.assertEqual(ggold.vrm_gate(b"not a glb")["status"], "unknown")

    def test_both_metas_are_read_not_only_the_first(self):
        """O-2: extract_vrm_metas must return BOTH blocks when a GLB
        carries both, never stop at the first it finds."""
        raw = (ggold.DATA / "content/vrm/vrm-metas-disagree.vrm").read_bytes()
        metas = ggold.extract_vrm_metas(raw)
        self.assertEqual(set(metas), {"0.x", "1.0"})

    def test_disagreeing_metas_are_a_conflict_even_though_each_alone_would_pass_or_refuse(self):
        raw = (ggold.DATA / "content/vrm/vrm-metas-disagree.vrm").read_bytes()
        gate = ggold.vrm_gate(raw)
        self.assertEqual(gate["status"], "conflict", json.dumps(gate))
        self.assertEqual(gate["vrm_licence"], None)
        self.assertEqual(gate["refusal"]["field"], "gate verdict")
        # the defect this replaces: a reader that only looked at the FIRST
        # meta (0.x here) would have read this file as allowed.
        self.assertFalse(ggold.rule_vrm_licence_refused("0.x", metas_of(raw)["0.x"])["refused"])
        self.assertTrue(ggold.rule_vrm_licence_refused("1.0", metas_of(raw)["1.0"])["refused"])

    def test_agreeing_metas_pass_reading_both(self):
        raw = (ggold.DATA / "content/vrm/vrm-metas-agree.vrm").read_bytes()
        gate = ggold.vrm_gate(raw)
        self.assertEqual(gate["status"], "ok", json.dumps(gate))
        self.assertEqual(gate["vrm_licence"]["vrm_version"], "1.0", "both present and agreeing shows VRM 1.0")

    def test_mutating_the_conflict_golden_to_agree_fixes_it(self):
        """The mutation this test proves: flip the disagreeing golden's
        VRM 1.0 allowRedistribution to true (now agreeing with the 0.x side
        that already allows) and the conflict must disappear."""
        raw = (ggold.DATA / "content/vrm/vrm-metas-disagree.vrm").read_bytes()
        metas = metas_of(raw)
        self.assertIsNotNone(ggold.rule_vrm_conflict(metas["0.x"], metas["1.0"]))
        fixed = dict(metas["1.0"], allowRedistribution=True)
        self.assertIsNone(ggold.rule_vrm_conflict(metas["0.x"], fixed))

    def test_usage_flags_are_display_and_never_a_conflict(self):
        """The content gate compares the two metas' VERDICTS only; usage
        flags are display. A disagreeing overlapping usage flag alone is
        therefore no conflict here either, so the two gates agree."""
        meta0 = {"licenseName": "CC_BY", "allowedUserName": "Everyone", "violentUssageName": "Allow"}
        meta1 = {"allowRedistribution": True, "avatarPermission": "everyone", "allowExcessivelyViolentUsage": False}
        self.assertIsNone(ggold.rule_vrm_conflict(meta0, meta1))

    def test_an_unknown_against_an_allowed_is_a_conflict(self):
        meta0 = {"licenseName": "Other", "allowedUserName": "Everyone"}
        meta1 = {"allowRedistribution": True, "avatarPermission": "everyone"}
        conflict = ggold.rule_vrm_conflict(meta0, meta1)
        self.assertIsNotNone(conflict)
        self.assertIn("unknown", conflict["detail"])


class VrmTokenReadings(unittest.TestCase):
    """O-2b: the content contract's ingest-v1.md §4.2 table, row by row. An
    unrecognised token is never allowed."""

    def verdict(self, version, meta):
        return ggold.rule_vrm_licence_refused(version, meta)

    def test_vrm0_licence_names(self):
        for name, want in [("CC0", "allowed"), ("CC_BY", "allowed"), ("CC_BY_NC_ND", "allowed"),
                           ("Redistribution_Prohibited", "prohibited"), ("Other", "unknown"),
                           ("Redistribution_Allowed", "unknown"), ("cc0", "unknown"), ("", "unknown")]:
            with self.subTest(name=name):
                self.assertEqual(self.verdict("0.x", {"licenseName": name, "allowedUserName": "Everyone"})["verdict"], want)
        self.assertEqual(self.verdict("0.x", {"licenseName": 1, "allowedUserName": "Everyone"})["verdict"], "prohibited",
                         "not a string is prohibited")

    def test_vrm0_allowed_user_names(self):
        for name, want in [("Everyone", "allowed"), ("OnlyAuthor", "prohibited"),
                           ("ExplicitlyLicensedPerson", "prohibited"), ("Anyone", "unknown"), ("everyone", "unknown")]:
            with self.subTest(name=name):
                self.assertEqual(self.verdict("0.x", {"licenseName": "CC0", "allowedUserName": name})["verdict"], want)
        self.assertEqual(self.verdict("0.x", {"licenseName": "CC0", "allowedUserName": ["Everyone"]})["verdict"], "prohibited")

    def test_vrm1_redistribution_is_exactly_true(self):
        for value, want in [(True, "allowed"), (False, "prohibited"), ("true", "prohibited"), (1, "prohibited"), (None, "prohibited")]:
            with self.subTest(value=value):
                self.assertEqual(self.verdict("1.0", {"allowRedistribution": value, "avatarPermission": "everyone"})["verdict"], want)

    def test_vrm1_avatar_permissions(self):
        for name, want in [("everyone", "allowed"), ("onlyAuthor", "prohibited"),
                           ("onlySeparatelyLicensedPerson", "prohibited"), ("anyone", "unknown"), ("Everyone", "unknown")]:
            with self.subTest(name=name):
                self.assertEqual(self.verdict("1.0", {"allowRedistribution": True, "avatarPermission": name})["verdict"], want)

    def test_prohibited_wins_over_unknown(self):
        r = self.verdict("0.x", {"licenseName": "Other", "allowedUserName": "OnlyAuthor"})
        self.assertEqual((r["verdict"], r["field"]), ("prohibited", "extensions.VRM.meta.allowedUserName"))


def glb_of(doc: dict) -> bytes:
    chunk = json.dumps(doc).encode()
    chunk += b" " * ((-len(chunk)) % 4)
    body = struct.pack("<I4s", len(chunk), b"JSON") + chunk
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


class GltfFormat(unittest.TestCase):
    """E_CONTENT_FORMAT: the content catalogue's ingest-v1.md §3 step 10."""

    def test_a_duplicate_member_anywhere_is_refused_before_classification(self):
        text = b'{"extensions": {"VRMC_vrm": {"meta": {"allowRedistribution": false}}}, "extensions": {}}'
        chunk = text + b" " * ((-len(text)) % 4)
        raw = struct.pack("<4sII", b"glTF", 2, 20 + len(chunk)) + struct.pack("<I4s", len(chunk), b"JSON") + chunk
        self.assertIn("twice", ggold.gltf_format_problem(raw, "anim/wave.glb"))
        pl = ggold.part_licence({"path": "anim/wave.glb", "kind": "animations", "licence": "CC0-1.0"}, raw)
        self.assertEqual(pl["gate_status"], "format")

    def test_a_whole_glb_passes_and_a_truncated_one_does_not(self):
        raw = glb_of({"asset": {"version": "2.0"}})
        self.assertIsNone(ggold.gltf_format_problem(raw, "a.glb"))
        self.assertIsNotNone(ggold.gltf_format_problem(raw[:-4], "a.glb"))
        self.assertIsNotNone(ggold.gltf_format_problem(raw + b"\0\0\0\0", "a.glb"))

    def test_gltf_uris(self):
        def doc(uri):
            return json.dumps({"buffers": [{"uri": uri}]}).encode()
        present = {"m/a.gltf", "m/a.bin", "x.bin"}
        for uri, ok in [("a.bin", True), ("data:application/octet-stream;base64,AAAA", True), ("../x.bin", False),
                        ("/x.bin", False), ("https://e.invalid/a.bin", False), ("file:a.bin", False),
                        ("m\\a.bin", False), ("missing.bin", False), ("", False)]:
            with self.subTest(uri=uri):
                self.assertEqual(ggold.gltf_format_problem(doc(uri), "m/a.gltf", present) is None, ok)

    def test_a_glb_takes_data_uris_only(self):
        self.assertIsNone(ggold.gltf_format_problem(glb_of({"images": [{"uri": "data:image/png;base64,AA=="}]}), "a.glb"))
        self.assertIn("external", ggold.gltf_format_problem(glb_of({"images": [{"uri": "t.png"}]}), "a.glb"))


VECTORS = json.loads((ggold.DATA / "vectors.json").read_text(encoding="utf-8"))
RELEASES = {v["name"]: v for v in VECTORS["content"]["releases"]}


def release(name: str) -> tuple[dict, dict]:
    """A release golden's files (synthesised ones included) and manifest."""
    v = RELEASES[name]
    files = ggold.release_files(ggold.DATA / v["dir"])
    for rel, synth in v.get("synth", {}).items():
        files[rel] = ggold.gen_module().synth(synth)
    return files, ggold.load_doc(v["manifest"])


def codes_of(files: dict, doc: dict) -> list[str]:
    return sorted({f["code"] for f in ggold.release_findings(files, doc)["findings"]})


class ContentByBytes(unittest.TestCase):
    """manifest.md §2.7.1: a name never decides whether a file is content --
    the content catalogue's own sniff and name rule, over EVERY file."""

    def test_a_glb_under_another_name_is_refused_and_its_glb_name_makes_it_content(self):
        files, doc = release("glb-named-bin")
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_FORMAT"])
        files["data/avatar.vrm"] = files.pop("data/avatar.bin")
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_UNDECLARED"], "named as a GLB it is content-typed, and undeclared")

    def test_only_the_root_manifest_is_exempt(self):
        files, doc = release("vrm-named-manifest-nested")
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_FORMAT"])
        self.assertTrue(ggold.is_manifest("astra-gi.toml"))
        for path in ("models/astra-gi.toml", "a/b/astra-gi.toml"):
            with self.subTest(path=path):
                self.assertFalse(ggold.is_manifest(path))
                self.assertIsNotNone(ggold.name_problem(path, files["models/astra-gi.toml"]))

    def test_a_text_gltf_under_another_name_is_refused_and_as_gltf_it_is_content(self):
        files, doc = release("gltf-named-json")
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_FORMAT"])
        files["data/avatar.gltf"] = files.pop("data/avatar.json")
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_UNDECLARED"])

    def test_the_sniff_is_the_content_catalogues_own(self):
        raw = ggold.release_files(ggold.DATA / "content/releases/gltf-named-json")["data/avatar.json"]
        self.assertTrue(ggold.CG.is_gltf_json(raw))
        self.assertTrue(ggold.is_text_gltf(ggold.CG.UTF8_BOM + raw), "a UTF-8 BOM is skipped, as three.js does")
        self.assertTrue(ggold.is_text_gltf(b'{"\\u0061sset": {}}'), "the key is compared decoded")
        self.assertFalse(ggold.is_text_gltf(b'{"meta": {"asset": 1}}'), "only a top-level key decides")

    def test_a_utf16_text_is_sniffed_as_what_it_decodes_to_and_otherwise_accepted(self):
        files, doc = release("localisation-utf16")
        self.assertIsNotNone(ggold.CG.bom_refusal("lang/strings.json", files["lang/strings.json"]),
                             "the content catalogue would refuse this file")
        self.assertEqual(codes_of(files, doc), [], "a game integration's localisation file is not")
        self.assertTrue(ggold.is_text_gltf(release("gltf-named-json-utf16")[0]["data/avatar.json"]))

    def test_over_16_mib_an_asset_key_refuses_in_any_spelling_and_its_absence_accepts(self):
        pad = b"x" * (ggold.CG.MAX_GLTF_JSON + 1)
        for key, refused in [(b'"asset"', True), (b'"\\u0061ss\\u0065t"', True), (b'"assets"', False), (b'"meta"', False)]:
            with self.subTest(key=key):
                raw = b'{"strings": "' + pad + b'", ' + key + b': 1}'
                self.assertEqual(ggold.name_problem("data/big.json", raw) is not None, refused)
        self.assertIsNone(ggold.name_problem("data/big.bin", b"\x00" + pad + b'"asset"'), "not JSON-looking")

    def test_turning_the_rule_off_turns_its_goldens_green_for_the_wrong_reason(self):
        for name in ("glb-named-bin", "gltf-named-json", "gltf-named-json-utf16", "json-over-16mib-nested-asset"):
            with self.subTest(name=name):
                files, doc = release(name)
                original = ggold.name_problem
                ggold.name_problem = lambda p, b: None
                try:
                    self.assertEqual(codes_of(files, doc), [], "without the rule the golden is accepted -- so the golden sees it")
                finally:
                    ggold.name_problem = original


class GltfUris(unittest.TestCase):
    """The content catalogue's own uri_refusal (N2): no % ? # or \\ in a uri
    that is not data:, because a loader decodes and splits before it joins."""

    def test_each_forbidden_character_refuses_even_with_the_literal_file_present(self):
        for uri in ("..%2fsecret.bin", "a.bin?x=1", "a.bin#frag", "a\\b.bin", "a%20b.bin"):
            with self.subTest(uri=uri):
                doc = json.dumps({"buffers": [{"uri": uri}]}).encode()
                why = ggold.gltf_format_problem(doc, "m/a.gltf", {"m/a.gltf", f"m/{uri}"})
                self.assertIsNotNone(why)
                self.assertIn("containing", why)

    def test_the_percent_rule_wins_over_the_dotdot_rule(self):
        doc = json.dumps({"buffers": [{"uri": "../x%2fy.bin"}]}).encode()
        self.assertIn("'%'", ggold.gltf_format_problem(doc, "m/a.gltf", {"m/a.gltf"}))

    def test_the_golden_turns_green_for_the_wrong_reason_without_the_rule(self):
        files, doc = release("gltf-uri-percent")
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_FORMAT"])
        saved = ggold.CG.URI_FORBIDDEN
        ggold.CG.URI_FORBIDDEN = ""
        try:
            self.assertEqual(codes_of(files, doc), [], "the literal file is present, so only the % rule refuses it")
        finally:
            ggold.CG.URI_FORBIDDEN = saved

    def test_images_or_buffers_that_are_not_an_array_are_refused_not_skipped(self):
        for images in ({"0": {"uri": "https://e.invalid/t.png"}}, 5, "t.png"):
            with self.subTest(images=images):
                doc = json.dumps({"asset": {"version": "2.0"}, "images": images}).encode()
                self.assertIn("not an array", ggold.gltf_format_problem(doc, "m/a.gltf", {"m/a.gltf"}))


class GltfCaps(unittest.TestCase):
    """The content catalogue's caps, by its own gltf_problem: 16 MiB per JSON
    chunk or .gltf before parsing, depth 128, 32 MiB per release; any BOM on
    a .gltf; and a JSON too deep to parse is a refusal, never a crash."""

    def gen(self):
        return ggold.gen_module()

    def test_depth_128_passes_and_129_is_refused_in_a_glb_and_a_gltf(self):
        for depth, ok in ((128, True), (129, False)):
            text = self.gen().deep_gltf(depth)
            chunk = text + b" " * ((-len(text)) % 4)
            glb = struct.pack("<4sII", b"glTF", 2, 20 + len(chunk)) + struct.pack("<I4s", len(chunk), b"JSON") + chunk
            for raw, path in ((text, "m/a.gltf"), (glb, "m/a.glb")):
                with self.subTest(depth=depth, path=path):
                    self.assertEqual(ggold.gltf_format_problem(raw, path) is None, ok)

    def test_a_json_too_deep_to_parse_is_a_format_error_not_a_crash(self):
        raw = self.gen().synth("gltf-million-deep")
        with self.assertRaises(ggold.GltfFormatError):
            ggold._strict_json(raw)
        self.assertIn("does not parse", ggold.gltf_format_problem(raw, "m/a.gltf"))

    def test_the_16_mib_cap_is_read_before_the_json_is_parsed(self):
        n = ggold.CG.MAX_GLTF_JSON + 4
        glb = struct.pack("<4sII", b"glTF", 2, 20 + n) + struct.pack("<I4s", n, b"JSON") + b"{" * n  # never valid JSON
        self.assertIn("over 16777216", ggold.gltf_format_problem(glb, "m/a.glb"))
        self.assertIn("over 16777216", ggold.gltf_format_problem(b"{" * (n - 3), "m/a.gltf"))

    def test_any_bom_on_a_gltf_is_refused_and_the_same_bytes_under_another_name_are_only_sniffed(self):
        for bom in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
            with self.subTest(bom=bom.hex()):
                raw = bom + b'{"asset": {"version": "2.0"}}'
                self.assertIn("byte-order mark", ggold.gltf_format_problem(raw, "m/a.gltf"))
                self.assertIsNone(ggold.gltf_format_problem(raw, "m/a.json"))

    def test_the_release_budget_counts_every_glb_and_gltf_and_two_of_three_fit(self):
        files, doc = release("gltf-total-over-32mib")
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_FORMAT"])
        del files["models/c.glb"]
        doc["integration"]["content"] = [e for e in doc["integration"]["content"] if e["path"] != "models/c.glb"]
        self.assertEqual(codes_of(files, doc), [], "22 MiB of glTF JSON is under the 32 MiB a release may hold")


class EmbeddedBundles(unittest.TestCase):
    """manifest.md §2.7.3: a .astrachar/.astrapack inside a release is judged
    by the content contract's own ingest_bundle, refusals keeping its codes."""

    ENTRY = {"path": "characters/x.astrachar", "kind": "character", "title": "t", "credit": "c", "licence": "CC0-1.0"}

    def cgen(self):
        return ggold.CG.gen_module()

    def test_the_refusal_is_contents_own_code_naming_the_inner_path(self):
        files, doc = release("bundle-glb-prohibited-beside-allowed-body")
        (f,) = ggold.release_findings(files, doc)["findings"]
        self.assertEqual(f["code"], "E_CONTENT_LICENCE_REFUSED")
        self.assertEqual(f["detail"], "characters/scout.astrachar!characters/aiko/accessories/hat/hat.glb")

    def test_a_manifest_content_cannot_read_is_refused_never_a_crash(self):
        raw = self.cgen().zip_bytes([{"name": "astrachar.json", "data": b"[]", "method": 0}])
        with self.assertRaises(AttributeError):  # the content checker's own reader raises on it
            ggold.CG.ingest_bundle(raw, {})
        pl = ggold.part_licence(self.ENTRY, raw)
        self.assertEqual(pl["gate_status"], "bundle")
        self.assertEqual(pl["refusal"]["code"], "E_CONTENT_FORMAT")

    def test_a_valid_bundle_accepts_and_a_declared_licence_covers_its_parts(self):
        files, doc = release("bundle-animset-wave")
        self.assertEqual(codes_of(files, doc), [])
        doc["integration"]["content"][0]["licence"] = ""
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_LICENCE_UNDECLARED"], "nothing else covers the animations")

    def test_a_renamed_bundle_named_back_is_content_typed_and_a_plain_zip_is_not_a_bundle(self):
        files, doc = release("bundle-renamed")
        files["packs/wave.astrapack"] = files.pop("packs/wave.zip")
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_UNDECLARED"])
        jar = self.cgen().zip_bytes([{"name": "META-INF/MANIFEST.MF", "data": b"Manifest-Version: 1.0\n"}])
        self.assertIsNone(ggold.name_problem("mods/loader.jar", jar), "a game's own zip is not a bundle")

    def test_an_unknown_inside_needs_the_declared_licence(self):
        files, doc = release("bundle-vrm0-licence-other")
        got = ggold.release_findings(files, doc)
        self.assertEqual([f["flag"] for f in got["flags"]], ["F_CONTENT_VRM_META_UNKNOWN"])
        doc["integration"]["content"][0]["licence"] = ""
        self.assertEqual(codes_of(files, doc), ["E_CONTENT_LICENCE_UNDECLARED"])

    def test_the_cloaked_bundle_turns_green_for_the_wrong_reason_under_a_lenient_reader(self):
        import io
        import zipfile
        files, doc = release("bundle-gap-between-entries")
        self.assertEqual(codes_of(files, doc), ["E_ZIP_HEADERS_INCONSISTENT"])
        raw = files["characters/scout.astrachar"]
        zipfile.ZipFile(io.BytesIO(raw)).testzip()  # Python's zipfile reads it without complaint


class VrmGoldensGenerator(unittest.TestCase):
    def test_every_vrm_golden_is_what_gen_py_writes(self):
        gen = ggold.DATA / "content/vrm/gen.py"
        r = subprocess.run([sys.executable, str(gen), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class GltfClassification(unittest.TestCase):
    """The content contract's ingest-v1.md §4: a GLB is classified by its
    glTF JSON extensions, never by its name."""

    AVATAR = {"extensions": {"VRM": {"meta": {"licenseName": "Redistribution_Prohibited", "allowedUserName": "Everyone"}}}}
    ANIMATION = {"extensionsUsed": ["VRMC_vrm_animation"], "extensions": {"VRMC_vrm_animation": {"specVersion": "1.0"}}}
    PLAIN = {"asset": {"version": "2.0"}}

    def part(self, path, kind, doc, licence="CC0-1.0"):
        return ggold.part_licence({"path": path, "kind": kind, "licence": licence}, glb_of(doc))

    def test_a_renamed_avatar_is_judged_as_an_avatar(self):
        for path, kind in [("models/emotes.glb", "animations"), ("art/prop.glb", "art"), ("a/avatar.vrma", "animations")]:
            with self.subTest(path=path):
                self.assertEqual(self.part(path, kind, self.AVATAR)["gate_status"], "refused")

    def test_an_avatar_extension_only_in_extensions_used_is_an_avatar(self):
        doc = {"extensionsUsed": ["VRMC_vrm", "VRMC_vrm_animation"]}
        self.assertEqual(ggold.gltf_class(doc), "avatar")
        self.assertEqual(self.part("a.glb", "animations", doc)["gate_status"], "unknown")

    def test_an_animation_gets_no_avatar_verdict(self):
        pl = self.part("anim/wave.vrma", "animations", self.ANIMATION)
        self.assertIsNone(pl["gate_status"])
        self.assertEqual(pl["licence_source"], "declared")

    def test_a_plain_gltf_is_judged_only_as_a_character(self):
        self.assertIsNone(self.part("art/prop.glb", "art", self.PLAIN)["gate_status"])
        self.assertEqual(self.part("character/body.glb", "character", self.PLAIN)["gate_status"], "unknown")

    def test_a_gltf_text_file_is_judged_too(self):
        raw = json.dumps(self.AVATAR).encode()
        pl = ggold.part_licence({"path": "char/a.gltf", "kind": "character", "licence": "CC0-1.0"}, raw)
        self.assertEqual(pl["gate_status"], "refused")

    def test_a_non_gltf_file_never_reaches_the_gate(self):
        pl = ggold.part_licence({"path": "art/x.png", "kind": "art", "licence": "CC0-1.0"}, b"\x89PNG\r\n\x1a\n" + b"\0" * 16)
        self.assertIsNone(pl["gate_status"])


def metas_of(raw: bytes) -> dict:
    return ggold.extract_vrm_metas(raw)


class WithdrawnSecurity(unittest.TestCase):
    def test_security_with_revoke_passes(self):
        doc = copy.deepcopy(ggold.load_doc("withdrawn/invalid-security-not-revoke.json"))
        self.assertFalse(ggold.rule_security_requires_revoke(doc))
        doc["rows"][0]["act"] = "revoke"
        doc["rows"][0]["floor_effect"] = "no-play"
        self.assertTrue(ggold.rule_security_requires_revoke(doc))


if __name__ == "__main__":
    unittest.main()
