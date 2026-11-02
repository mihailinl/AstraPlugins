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


# ── mods (engine-descriptor-v1.md §7) ────────────────────────────────────

DESCRIPTOR_SCHEMA = ggold.load_schema("spec/games/schemas/engine-descriptor-v1.schema.json")
MODS_SCHEMA = ggold.mods_schema(DESCRIPTOR_SCHEMA)


def mods_hostile(name: str) -> dict:
    return copy.deepcopy(ggold.load_doc(f"descriptors/mods/hostile/mods-{name}.toml"))


def mods_valid() -> dict:
    """A valid descriptor carrying a valid `mods` (compat/source2-with-mods)."""
    return copy.deepcopy(ggold.load_doc("descriptors/mods/compat/source2-with-mods.toml"))


def builtin_with_mods(name: str) -> dict:
    eng = ggold.load_doc(f"descriptors/builtin/{name}.toml")
    frag = ggold.load_doc(f"descriptors/mods/builtin/{name}.mods.toml")
    return copy.deepcopy(dict(eng, mods=frag["mods"]))


def descriptor_ok(doc) -> bool:
    return ggold.schema_ok(doc, DESCRIPTOR_SCHEMA)[0]


def mods_ok(doc) -> bool:
    return ggold.schema_ok(doc.get("mods"), MODS_SCHEMA)[0] and not ggold.mods_semantic_problems(doc)


class ModsCompat(unittest.TestCase):
    """Condition 1: optional, and invisible to a reader that ignores it."""

    def test_a_descriptor_needs_no_mods(self):
        doc = mods_valid()
        del doc["mods"]
        self.assertTrue(descriptor_ok(doc))

    def test_without_mods_every_golden_is_the_descriptor_it_was(self):
        for f in sorted((ggold.DATA / "descriptors/mods").rglob("*.toml")):
            if "builtin" in f.parts:
                continue
            with self.subTest(f=f.name):
                doc = ggold.load_doc(str(f.relative_to(ggold.DATA)))
                self.assertIn("mods", doc)
                self.assertTrue(descriptor_ok(ggold.without_mods(doc)), "a mods error must never reach detection")

    def test_the_reader_ignoring_mods_refuses_only_a_non_table(self):
        reader = ggold.reader_ignoring_mods_schema(DESCRIPTOR_SCHEMA)
        doc = copy.deepcopy(ggold.load_doc("descriptors/mods/compat/source2-with-future-mods.toml"))
        self.assertFalse(descriptor_ok(doc), "this version's schema refuses the future table")
        self.assertTrue(ggold.schema_ok(doc, reader)[0], "0.5.0 reads nothing inside it")
        doc["mods"] = [doc["mods"]]  # [[mods]]
        self.assertFalse(ggold.schema_ok(doc, reader)[0], "[[mods]] is the one shape 0.5.0 refuses")
        self.assertFalse(descriptor_ok(doc))

    def test_mods_counts_toward_the_16_kib_bound(self):
        # 0.5.0 reads nothing in `mods`, but the canonical form includes it
        # (§1), so a big enough table makes 0.5.0 refuse the descriptor.
        twin = ggold.load_doc("manifests/valid/foundation-owns-engine.toml")["integration"]["engine"]
        doc = mods_valid()
        self.assertTrue(ggold.reader_ignoring_mods_accepts(doc, DESCRIPTOR_SCHEMA))
        doc["mods"]["loader"][0]["name"] = "x" * ggold.DESCRIPTOR_BYTES
        self.assertTrue(ggold.schema_ok(doc, ggold.reader_ignoring_mods_schema(DESCRIPTOR_SCHEMA))[0])
        self.assertFalse(ggold.reader_ignoring_mods_accepts(doc, DESCRIPTOR_SCHEMA))
        self.assertFalse(ggold.mods_compat(doc, twin, DESCRIPTOR_SCHEMA)["reader"])

    def test_the_future_golden_is_valid_once_its_unknowns_go(self):
        doc = copy.deepcopy(ggold.load_doc("descriptors/mods/compat/source2-with-future-mods.toml"))
        self.assertFalse(mods_ok(doc))
        del doc["mods"]["loader"][0]["load_order"]
        self.assertFalse(mods_ok(doc), "the unknown `enabled` format alone still refuses it")
        doc["mods"]["loader"][0]["enabled"] = [{"format": "dir-per-mod"}]
        self.assertTrue(mods_ok(doc))

    def test_the_compat_golden_is_its_twin_and_a_changed_detection_half_is_not(self):
        twin = ggold.load_doc("manifests/valid/foundation-owns-engine.toml")["integration"]["engine"]
        doc = mods_valid()
        c = ggold.mods_compat(doc, twin, DESCRIPTOR_SCHEMA)
        self.assertEqual(c, {"full": True, "mods": True, "reader": True, "twin": True})
        doc["rule"][0]["confidence"] = "low"  # still a valid descriptor, no longer the twin
        self.assertTrue(descriptor_ok(doc))
        self.assertFalse(ggold.mods_compat(doc, twin, DESCRIPTOR_SCHEMA)["twin"])
        doc = mods_valid()
        del doc["mods"]
        self.assertFalse(ggold.mods_compat(doc, twin, DESCRIPTOR_SCHEMA)["twin"], "a compat golden must carry mods")

    def test_a_builtin_mods_table_leaves_its_engine_untouched(self):
        for name in ("unity", "unreal"):
            with self.subTest(name=name):
                whole = builtin_with_mods(name)
                self.assertTrue(descriptor_ok(whole))
                self.assertEqual(ggold.without_mods(whole), ggold.load_doc(f"descriptors/builtin/{name}.toml"))


class ModsSchemaHoldsNoDetection(unittest.TestCase):
    """Condition 2: `mods` can never carry what detection reads. Every
    definition $defs/mods reaches is its own (mods*), and none of them has a
    member named like a detection member."""

    DETECTION = {"engine", "rule", "walk", "programs", "tier", "confidence", "classify", "code",
                 "evidence", "binary", "anti_cheat", "wrappers", "bootstrap", "pick", "passes",
                 "named_alike", "weak_order", "as", "schema"}

    @staticmethod
    def reach(schema):
        defs, seen, todo, names = schema["$defs"], set(), ["mods"], set()

        def walk(node):
            if isinstance(node, dict):
                if "$ref" in node:
                    todo.append(node["$ref"].rsplit("/", 1)[-1])
                names.update(node.get("properties", {}).keys())
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        while todo:
            d = todo.pop()
            if d not in seen:
                seen.add(d)
                walk(defs[d])
        return seen, names

    def test_the_mods_subtree_is_self_contained_and_detection_free(self):
        seen, names = self.reach(DESCRIPTOR_SCHEMA)
        self.assertTrue(all(d.startswith("mods") for d in seen), seen)
        self.assertFalse(names & self.DETECTION, names & self.DETECTION)

    def test_the_canary_sees_a_detection_member_planted_in_mods(self):
        bad = json.loads(json.dumps(DESCRIPTOR_SCHEMA))
        bad["$defs"]["modsLoader"]["properties"]["rule"] = {"$ref": "#/$defs/rule"}
        seen, names = self.reach(bad)
        self.assertIn("rule", seen)
        self.assertIn("rule", names)


class ModsPaths(unittest.TestCase):
    """§7.3: every path is `{source}`-rooted, inside the jail."""

    def with_root(self, root):
        doc = mods_valid()
        doc["mods"]["loader"][0]["root"] = root
        return mods_ok(doc)

    def test_the_escape_golden_passes_once_it_stays_in_the_jail(self):
        doc = mods_hostile("path-escape")
        self.assertFalse(mods_ok(doc))
        doc["mods"]["loader"][0]["root"] = "{source}/s2loader/mods"
        self.assertTrue(mods_ok(doc))

    def test_the_absolute_golden_passes_once_rooted_at_source(self):
        doc = mods_hostile("absolute-path")
        self.assertFalse(mods_ok(doc))
        doc["mods"]["loader"][0]["require"][0]["stat"] = "{source}/s2loader/s2loader.dll"
        self.assertTrue(mods_ok(doc))

    def test_every_way_out_of_the_jail_is_refused(self):
        for p in ["C:/Windows/x.dll", "C:\\Windows\\x.dll", "/etc/passwd", "\\\\srv\\share\\x",
                  "s2loader/mods", "~/mods", "{game}/mods", "{profile}/mods", "{source}/{source}/x",
                  "{source}/../x", "{source}/a/..", "{source}/./a", "{source}//a", "{source}/",
                  "{source}/a\\b", "{source}/a:b", "{source}/a.", "{source}/a ", "{source}/*.dll",
                  "{source}/{unclosed", "{source}/a\x01b"]:
            with self.subTest(p=p):
                self.assertFalse(self.with_root(p))

    def test_real_layouts_are_accepted(self):
        for p in ["{source}", "{source}/BepInEx/plugins", "{source}/{project}/Content/Paks/~mods",
                  "{source}/{project}/Binaries/Win64/ue4ss/Mods", "{source}/.doorstop_version"]:
            with self.subTest(p=p):
                self.assertTrue(self.with_root(p))


class ModsGlob(unittest.TestCase):
    def with_glob(self, g):
        doc = mods_valid()
        doc["mods"]["loader"][0]["enabled"] = [{"format": "file-glob", "glob": g}]
        return mods_ok(doc)

    def test_the_over_budget_golden_passes_with_a_one_level_glob(self):
        doc = mods_hostile("over-budget-glob")
        self.assertFalse(mods_ok(doc))
        doc["mods"]["loader"][0]["enabled"][0]["glob"] = "*.pak"
        self.assertTrue(mods_ok(doc))

    def test_only_one_listing_can_be_globbed(self):
        for g in ["**", "**/*.pak", "*/*.pak", "a/*.pak", "*a*b*c", "x?.pak", "[ab]*.pak", "C:*.pak", "plain.pak"]:
            with self.subTest(g=g):
                self.assertFalse(self.with_glob(g))
        for g in ["*.pak", "*.dll", "*_P*.pak"]:
            with self.subTest(g=g):
                self.assertTrue(self.with_glob(g))


class ModsClosedEnums(unittest.TestCase):
    """§7.3, §7.4, §7.5, §7.6: every vocabulary the launcher implements is closed."""

    def test_the_unknown_enum_golden_passes_with_a_known_strategy(self):
        doc = mods_hostile("unknown-enum")
        self.assertFalse(mods_ok(doc))
        doc["mods"]["loader"][0]["coexist"][0]["strategy"] = "chain"
        self.assertTrue(mods_ok(doc))

    def test_an_unknown_value_is_refused_in_every_closed_set(self):
        cases = [
            (("bepinex5", "source"), ["game", "steam-workshop"]),
            (("bepinex5", "version", "key"), ["ProductVersion", "Comments"]),
            (("bepinex5", "enabled"), [{"format": "json-list", "list": "{source}/mods.json"}]),
            (("bepinex5", "coexist"), [{"strategy": "overwrite", "entry": "{source}/x.dll"}]),
            (("ue4ss3", "coexist"), [{"strategy": "chain", "entry": "{source}/x.dll", "tell": "LD_PRELOAD"}]),
            (("ue4ss3", "enabled"), [{"format": "enable-list", "list": "{source}/mods.txt", "line": "json"}]),
        ]
        for (loader_id, *path), value in cases:
            with self.subTest(loader=loader_id, path=path):
                engine = "unity" if loader_id.startswith("bepinex") else "unreal"
                doc = builtin_with_mods(engine)
                self.assertTrue(mods_ok(doc))
                loader = next(l for l in doc["mods"]["loader"] if l["id"] == loader_id)
                node = loader
                for p in path[:-1]:
                    node = node[p]
                node[path[-1]] = value
                self.assertFalse(mods_ok(doc))

    def test_chain_needs_an_entry(self):
        doc = builtin_with_mods("unity")
        del doc["mods"]["loader"][0]["coexist"][0]["entry"]
        self.assertFalse(mods_ok(doc))

    def test_an_empty_coexist_is_recognised_and_incapable(self):
        doc = builtin_with_mods("unreal")
        ue4ss2 = next(l for l in doc["mods"]["loader"] if l["id"] == "ue4ss2")
        self.assertEqual(ue4ss2["coexist"], [])
        self.assertTrue(mods_ok(doc))


class ModsManagerAsData(unittest.TestCase):
    def test_the_golden_passes_once_the_manager_goes(self):
        doc = mods_hostile("manager-as-data")
        self.assertFalse(ggold.rule_mods_manager_as_data(doc))
        self.assertFalse(mods_ok(doc))
        del doc["mods"]["loader"][0]["manager"]
        self.assertTrue(ggold.rule_mods_manager_as_data(doc))
        self.assertTrue(mods_ok(doc))

    def test_a_manager_hidden_where_the_schema_allows_text_is_still_refused(self):
        for name in ["r2modman BepInEx", "Gale profile", "Mod Organizer 2 loader", "Vortex deploy", "Thunderstore"]:
            with self.subTest(name=name):
                doc = mods_valid()
                doc["mods"]["loader"][0]["name"] = name
                self.assertTrue(ggold.schema_ok(doc.get("mods"), MODS_SCHEMA)[0], "the schema lets display text through")
                self.assertFalse(ggold.rule_mods_manager_as_data(doc))
        doc = mods_valid()
        doc["mods"]["loader"][0]["root"] = "{source}/r2modmanPlus-local/mods"
        self.assertFalse(ggold.rule_mods_manager_as_data(doc), "a manager's folder is a manager named too")

    def test_a_word_that_merely_contains_a_name_is_not_a_manager(self):
        doc = mods_valid()
        doc["mods"]["loader"][0]["name"] = "Nightingale Loader"
        self.assertTrue(ggold.rule_mods_manager_as_data(doc))


class ModsLoaderAnchor(unittest.TestCase):
    def test_the_proxy_golden_passes_once_its_own_dll_is_the_anchor(self):
        doc = mods_hostile("anchor-on-a-proxy")
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc))
        doc["mods"]["loader"][0]["require"].append({"stat": "{source}/s2loader/s2loader.dll", "kind": "file"})
        self.assertTrue(ggold.rule_mods_loader_anchor_invalid(doc))

    def test_no_proxy_or_runtime_name_anchors_a_loader(self):
        for name in ["winhttp.dll", "version.dll", "dwmapi.dll", "XINPUT1_3.DLL", "dinput8.dll",
                     "opengl32.dll", "steam_api64.dll", "vcruntime140.dll", "{project}", "{source}"]:
            with self.subTest(name=name):
                doc = mods_valid()
                path = name if name == "{source}" else "{source}/" + name
                doc["mods"]["loader"][0]["require"] = [{"stat": path, "kind": "file"}]
                self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc))

    def test_a_lookup_nested_in_any_is_never_the_anchor(self):
        doc = mods_valid()
        doc["mods"]["loader"][0]["require"] = [{"any": [{"stat": "{source}/s2loader/s2loader.dll", "kind": "file"}]}]
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc))

    def test_every_builtin_loader_has_an_anchor(self):
        for name in ("unity", "unreal"):
            with self.subTest(name=name):
                self.assertTrue(ggold.rule_mods_loader_anchor_invalid(builtin_with_mods(name)))


class ModsCodesAndIds(unittest.TestCase):
    def test_the_other_engine_golden_passes_with_its_own_code(self):
        doc = mods_hostile("loader-for-another-engine")
        self.assertFalse(ggold.rule_mods_code_undeclared(doc))
        doc["mods"]["loader"][0]["codes"] = ["source2"]
        self.assertTrue(ggold.rule_mods_code_undeclared(doc))
        del doc["mods"]["loader"][0]["codes"]
        self.assertTrue(ggold.rule_mods_code_undeclared(doc), "no `codes` means every code of this descriptor")

    def test_a_builtin_loader_cannot_name_a_code_its_engine_lacks(self):
        doc = builtin_with_mods("unity")
        doc["mods"]["loader"][0]["codes"] = ["unreal"]
        self.assertFalse(ggold.rule_mods_code_undeclared(doc))

    def test_the_duplicate_golden_passes_once_renamed(self):
        doc = mods_hostile("loader-id-duplicate")
        self.assertFalse(ggold.rule_mods_loader_id_duplicate(doc))
        doc["mods"]["loader"][1]["id"] = "s2-loader-portable"
        self.assertTrue(ggold.rule_mods_loader_id_duplicate(doc))


class ModsBudget(unittest.TestCase):
    def test_the_slow_golden_fits_with_one_loader_fewer(self):
        doc = mods_hostile("over-budget-lookups")
        self.assertEqual(ggold.mods_cost(doc)["lookups"], 66)
        self.assertFalse(ggold.rule_mods_over_budget(doc))
        doc["mods"]["loader"].pop()
        self.assertEqual(ggold.mods_cost(doc)["lookups"], 44)
        self.assertTrue(ggold.rule_mods_over_budget(doc))

    def test_exactly_the_bound_passes_and_one_more_does_not(self):
        doc = mods_hostile("over-budget-lookups")
        doc["mods"]["loader"][2]["require"] = doc["mods"]["loader"][2]["require"][:7]  # 22 + 22 + 19 = 63
        doc["mods"]["loader"][2]["require"].append({"stat": "{source}/l3/x.dll", "kind": "file"})
        self.assertEqual(ggold.mods_cost(doc)["lookups"], 64)
        self.assertTrue(ggold.rule_mods_over_budget(doc))
        doc["mods"]["loader"][2]["require"][-1] = {"any": [{"stat": "{source}/l3/x.dll", "kind": "file"},
                                                           {"stat": "{source}/l3/y.dll", "kind": "file"}]}
        self.assertEqual(ggold.mods_cost(doc)["lookups"], 65)
        self.assertFalse(ggold.rule_mods_over_budget(doc))

    def test_nesting_deeper_than_three_is_over_budget(self):
        doc = mods_valid()
        leaf = {"stat": "{source}/s2loader/x.dll", "kind": "file"}
        doc["mods"]["loader"][0]["require"].append({"any": [{"all": [{"none": [leaf]}]}]})
        self.assertTrue(ggold.rule_mods_over_budget(doc))
        doc["mods"]["loader"][0]["require"][-1] = {"any": [{"all": [{"none": [{"any": [leaf]}]}]}]}
        self.assertFalse(ggold.rule_mods_over_budget(doc))

    def test_probes_are_counted_too(self):
        doc = builtin_with_mods("unreal")
        self.assertEqual(ggold.mods_cost(doc)["probes"], 6)  # 2 versions + 2 enable lists + 2 markers
        tails = [{"tail": "{source}/{project}/Binaries/Win64/ue4ss/UE4SS.dll", "bytes": 4, "equals": "XXXX"}] * 3
        doc["mods"]["loader"][2]["require"].extend(tails)
        self.assertEqual(ggold.mods_cost(doc)["probes"], 9)
        self.assertFalse(ggold.rule_mods_over_budget(doc))


class ModsVersion(unittest.TestCase):
    """§7.4: BepInEx 6's be.788 is a version rule the grammar expresses."""

    BE6 = "N{1,2}.N{1,3}.N{1,3}-be.N{1,5}"
    BE5 = "N{1,2}.N{1,2}.N{1,3}"

    def test_be_788_and_nothing_else(self):
        holds = lambda v: ggold.version_holds(self.BE6, "=6.0.0-be.788", v)
        self.assertTrue(holds("6.0.0-be.788+5bd4ae5"))
        self.assertTrue(holds("6.0.0-be.788"))
        for v in ["6.0.0-be.789", "6.0.0-be.7880", "6.0.0-be.78", "6.0.0", "6.0.0-pre.1", "", "5.4.23.3"]:
            with self.subTest(v=v):
                self.assertFalse(holds(v))

    def test_bepinex_5_is_5_4_x(self):
        holds = lambda v: ggold.version_holds(self.BE5, ">=5.4, <5.5", v)
        self.assertTrue(holds("5.4.23.3"))
        self.assertTrue(holds("5.4.21.0"))
        for v in ["5.5.0.0", "5.3.9", "6.0.0-be.788", "15.4.0"]:
            with self.subTest(v=v):
                self.assertFalse(holds(v))

    def test_an_operand_compares_only_its_own_runs(self):
        # `5.4` is the 5.4 line, every patch and build of it; `6.0.0` is a
        # leading part of the BepInEx 6 shape, so it holds for every be.N.
        self.assertTrue(ggold.version_holds(self.BE5, "<=5.4", "5.4.23.3"))
        self.assertTrue(ggold.version_holds(self.BE6, "=6.0.0", "6.0.0-be.788"))
        self.assertFalse(ggold.version_holds(self.BE5, "<=5.4", "5.5.0.0"))

    def test_an_operand_out_of_the_templates_shape_never_holds(self):
        self.assertFalse(ggold.version_holds(self.BE6, "=6.0-be.788", "6.0.0-be.788"))
        self.assertIsNone(ggold.read_operand(self.BE6, "6.0-be.788"))

    def test_the_builtin_goldens_say_be_788(self):
        doc = builtin_with_mods("unity")
        be6 = next(l for l in doc["mods"]["loader"] if l["id"] == "bepinex6-il2cpp")["version"]
        self.assertTrue(ggold.version_holds(be6["template"], be6["versions"], "6.0.0-be.788+5bd4ae5"))
        self.assertFalse(ggold.version_holds(be6["template"], be6["versions"], "6.0.0-be.733+0a1b2c3"))
        ue3 = next(l for l in builtin_with_mods("unreal")["mods"]["loader"] if l["id"] == "ue4ss3")["version"]
        self.assertTrue(ggold.version_holds(ue3["template"], ue3["versions"], "3.0.1.0"))
        self.assertFalse(ggold.version_holds(ue3["template"], ue3["versions"], "2.5.2"))


MODS_VECTORS = json.loads((ggold.DATA / "vectors.json").read_text(encoding="utf-8"))["descriptors"]["mods"]


def hostile_record(name: str) -> dict:
    return copy.deepcopy(next(h for h in MODS_VECTORS["hostile"] if h["name"] == name))


def judged_ok(record: dict, doc: dict) -> bool:
    return all(ok for _n, ok, _d in ggold.judge_mods_hostile(record, doc, DESCRIPTOR_SCHEMA))


class ModsChainEntry(unittest.TestCase):
    """Review item 1: a chain entry is a file the loader's recognition found,
    never a proxy, a runtime or the game's program."""

    def test_the_proxy_entry_golden_passes_once_the_entry_is_the_loaders_own_dll(self):
        doc = mods_hostile("chain-entry-on-a-proxy")
        self.assertFalse(ggold.rule_mods_chain_entry_invalid(doc))
        self.assertTrue(ggold.rule_mods_loader_anchor_invalid(doc), "its anchor is fine: only the entry is wrong")
        doc["mods"]["loader"][0]["coexist"][0]["entry"] = "{source}/s2loader/s2loader.dll"
        self.assertTrue(ggold.rule_mods_chain_entry_invalid(doc))
        self.assertTrue(mods_ok(doc))

    def test_the_program_a_stranger_file_or_a_nested_lookup_is_never_the_entry(self):
        for entry, extra in [
            ("{source}/{stem}.exe", {"stat": "{source}/{stem}.exe", "kind": "file"}),
            ("{source}/Game.exe", {"stat": "{source}/Game.exe", "kind": "file"}),
            ("{source}/s2loader/unrecognised.dll", None),
            ("{source}/s2loader/nested.dll", {"any": [{"stat": "{source}/s2loader/nested.dll", "kind": "file"}]}),
            ("{source}/s2loader", {"stat": "{source}/s2loader", "kind": "dir"}),
        ]:
            with self.subTest(entry=entry):
                doc = mods_valid()
                loader = doc["mods"]["loader"][0]
                if extra:
                    loader["require"].append(extra)
                loader["coexist"] = [{"strategy": "chain", "entry": entry}]
                self.assertFalse(ggold.rule_mods_chain_entry_invalid(doc))

    def test_every_builtin_chain_enters_a_recognised_file(self):
        for name in ("unity", "unreal"):
            with self.subTest(name=name):
                self.assertTrue(ggold.rule_mods_chain_entry_invalid(builtin_with_mods(name)))


class ModsAnchorIsAFile(unittest.TestCase):
    """Review item 2: §2.4's "never the program", and a FILE, with one passive exception."""

    def test_the_program_golden_passes_once_its_own_dll_anchors_it(self):
        doc = mods_hostile("anchor-on-the-program")
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc))
        doc["mods"]["loader"][0]["require"].append({"stat": "{source}/s2loader/s2loader.dll", "kind": "file"})
        self.assertTrue(ggold.rule_mods_loader_anchor_invalid(doc))

    def test_no_program_shaped_name_anchors_a_loader(self):
        for path in ["{source}/{stem}.exe", "{source}/{program}", "{source}/{name}.dll", "{source}/Game.EXE",
                     "{source}/run.sh", "{source}/Game.x86_64", "{source}/start.bat"]:
            with self.subTest(path=path):
                doc = mods_valid()
                doc["mods"]["loader"][0]["require"] = [{"stat": path, "kind": "file"}]
                self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc))

    def test_the_folder_golden_passes_only_once_the_folder_is_its_own_root(self):
        doc = mods_hostile("anchor-on-a-folder")
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc), "a folder that is not its root anchors nothing")
        doc["mods"]["loader"][0]["root"] = "{source}/{project}/Plugins"
        self.assertTrue(ggold.rule_mods_loader_anchor_invalid(doc), "passive, anchored on its own root")
        self.assertTrue(ggold.rule_mods_root_anchor_not_passive(doc))

    def test_a_file_name_of_kind_dir_is_not_a_file_anchor(self):
        doc = mods_valid()
        doc["mods"]["loader"][0]["require"] = [{"stat": "{source}/s2loader/s2loader.dll", "kind": "dir"}]
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc))

    def test_the_paks_are_the_passive_case(self):
        doc = builtin_with_mods("unreal")
        paks = next(l for l in doc["mods"]["loader"] if l["id"] == "unreal-paks")
        self.assertTrue(ggold.rule_mods_loader_anchor_invalid(doc))
        self.assertTrue(ggold.rule_mods_root_anchor_not_passive(doc))
        paks["coexist"] = [{"strategy": "side-by-side", "tell": "ue4ss-mods-paths"}]
        self.assertFalse(ggold.rule_mods_root_anchor_not_passive(doc), "a root anchor holds only while Astra tells nothing")


class ModsRootAnchoredIsPassive(unittest.TestCase):
    """ops-42's follow-up: "passive" is exactly no `chain` and no `tell`, and
    a root-anchored loader that declares either is refused on its own rule."""

    def test_the_golden_passes_once_its_tell_goes(self):
        doc = mods_hostile("root-anchor-not-passive")
        self.assertTrue(ggold.rule_mods_loader_anchor_invalid(doc), "it IS anchored, on its root")
        self.assertFalse(ggold.rule_mods_root_anchor_not_passive(doc))
        del doc["mods"]["loader"][0]["coexist"][0]["tell"]
        self.assertTrue(ggold.rule_mods_root_anchor_not_passive(doc))
        self.assertTrue(mods_ok(doc))

    def test_chain_makes_a_root_anchored_loader_active_too(self):
        doc = mods_hostile("root-anchor-not-passive")
        loader = doc["mods"]["loader"][0]
        loader["require"].append({"stat": "{source}/winhttp.dll", "kind": "file"})  # a proxy: no file anchor
        loader["coexist"] = [{"strategy": "chain", "entry": "{source}/winhttp.dll"}]
        self.assertFalse(ggold.rule_mods_root_anchor_not_passive(doc))

    def test_passive_is_exactly_no_chain_no_via_manager_and_no_tell(self):
        for coexist, passive in [
            ([], True),
            ([{"strategy": "side-by-side"}], True),
            ([{"strategy": "via-manager"}], False),
            ([{"strategy": "side-by-side", "tell": "ue4ss-mods-paths"}], False),
            ([{"strategy": "chain", "entry": "{source}/x.dll"}], False),
            ([{"strategy": "side-by-side"}, {"strategy": "via-manager"}], False),
        ]:
            with self.subTest(coexist=coexist):
                self.assertEqual(ggold._passive({"coexist": coexist}), passive)

    def test_the_spec_states_the_definition_the_reason_and_the_refusal(self):
        s = " ".join(spec_section("### 7.4 Recognising a loader").split())
        for needle in [
            "A loader is **passive** when, exactly, its `coexist` holds no `chain` strategy, no `via-manager` strategy, and no strategy with a `tell`.",
            "a false \"recognised\" for a root-anchored loader changes only what the player sees on their own machine",
            "Astra loads nothing of it and tells it nothing",
            "A root-anchored loader that also declares `chain`, `via-manager` or a `tell` is reason `root-anchor-not-passive`.",
            "Only `child` and `stat` anchor a root",
        ]:
            with self.subTest(needle=needle):
                self.assertIn(needle, s)

    def test_an_active_loader_with_a_file_anchor_may_also_require_its_root(self):
        # Not root-anchored: its file anchors it, so the root lookup is just a requirement.
        doc = builtin_with_mods("unreal")
        ue3 = next(l for l in doc["mods"]["loader"] if l["id"] == "ue4ss3")
        ue3["require"].append({"child": ue3["root"], "kind": "dir"})
        self.assertTrue(ggold.rule_mods_root_anchor_not_passive(doc))
        self.assertTrue(mods_ok(doc))


class ModsDeviceNamesAndReservedCharacters(unittest.TestCase):
    """Review item 3."""

    def test_the_device_golden_passes_once_the_name_is_not_a_device(self):
        doc = mods_hostile("device-name")
        self.assertFalse(mods_ok(doc))
        doc["mods"]["loader"][0]["require"][1]["stat"] = "{source}/s2loader/COM10"
        self.assertTrue(mods_ok(doc))

    def test_the_paths_golden_names_every_device_and_reserved_character(self):
        reasons = {c["path"]: c["reason"] for c in json.loads((ggold.DATA / "descriptors/mods/paths.json").read_text())["paths"]}
        for p in ["{source}/CON", "{source}/NUL.txt", "{source}/COM1", "{source}/a/LPT1.log", "{source}/CONIN$",
                  "{source}/a<b", "{source}/a|b", "{source}/a?b", "{source}/a" + chr(0x7F) + "b",
                  "{source}/a" + chr(0x85) + "b"]:
            with self.subTest(p=p):
                self.assertEqual(reasons[p], "path-invalid")

    def test_a_marker_or_glob_is_held_to_the_same_rules(self):
        doc = builtin_with_mods("unreal")
        doc["mods"]["loader"][0]["enabled"][0]["marker"] = "NUL.txt"
        self.assertFalse(mods_ok(doc))
        doc = mods_valid()
        doc["mods"]["loader"][0]["enabled"] = [{"format": "file-glob", "glob": "*|.pak"}]
        self.assertFalse(mods_ok(doc))


class ModsSubstitutionAndPlaceholders(unittest.TestCase):
    """Review item 4."""

    def test_the_placeholder_golden_passes_with_a_known_name(self):
        doc = mods_hostile("unknown-placeholder")
        self.assertFalse(ggold.rule_mods_placeholder_unknown(doc))
        self.assertTrue(ggold.schema_ok(doc.get("mods"), MODS_SCHEMA)[0], "the schema sees only a placeholder's syntax")
        doc["mods"]["loader"][0]["root"] = "{source}/{project}/s2loader/mods"
        self.assertTrue(ggold.rule_mods_placeholder_unknown(doc))

    def test_a_capture_is_known_only_to_the_descriptor_that_binds_it(self):
        doc = mods_valid()  # its rule binds `as = "core"`
        doc["mods"]["loader"][0]["root"] = "{source}/{core}/mods"
        self.assertTrue(ggold.rule_mods_placeholder_unknown(doc))
        doc["mods"]["loader"][0]["root"] = "{source}/{data}/mods"  # Unity's capture, not this descriptor's
        self.assertFalse(ggold.rule_mods_placeholder_unknown(doc))

    def test_every_component_is_checked_again_after_substitution(self):
        self.assertEqual(ggold.substitute("{source}/{dir}/x.dll", {"dir": "a/b"}), ["a", "b", "x.dll"])
        for value in ["", "..", "../x", "a//b", "/abs", "C:", "CON", "a\\b", "{source}", "{x}", "a."]:
            with self.subTest(value=value):
                self.assertIsNone(ggold.substitute("{source}/{dir}/x.dll", {"dir": value}))
        self.assertIsNone(ggold.substitute("{source}/{dir}/x.dll", {}), "an unbound placeholder yields nothing")

    def test_the_substitution_golden_is_read(self):
        cases = json.loads((ggold.DATA / "descriptors/mods/paths.json").read_text())
        self.assertTrue(all(ok for _n, ok, _d in ggold.judge_mods_paths(cases, DESCRIPTOR_SCHEMA)))
        cases["substitution"][2]["components"] = ["", "x.dll"]  # claim an empty value survives
        self.assertFalse(all(ok for _n, ok, _d in ggold.judge_mods_paths(cases, DESCRIPTOR_SCHEMA)))


class ModsNestingIsBounded(unittest.TestCase):
    """Review item 5: no input makes a reader recurse past §7.1's bound."""

    @staticmethod
    def deep(levels: int) -> dict:
        doc = mods_valid()
        node = {"stat": "{source}/s2loader/x.dll", "kind": "file"}
        for _ in range(levels):
            node = {"any": [node]}
        doc["mods"]["loader"][0]["require"].append(node)
        return doc

    def test_the_schema_stops_at_depth_three(self):
        self.assertTrue(ggold.schema_ok(self.deep(3).get("mods"), MODS_SCHEMA)[0])
        self.assertFalse(ggold.schema_ok(self.deep(4).get("mods"), MODS_SCHEMA)[0])
        self.assertEqual(ggold.nesting(self.deep(3)["mods"]), ggold.MODS_MAX_NESTING)

    def test_the_deep_golden_is_refused_and_depth_three_is_not(self):
        doc = mods_hostile("deep-nesting")
        self.assertFalse(ggold.rule_mods_over_budget(doc))
        self.assertGreater(ggold.nesting(doc["mods"]), ggold.MODS_MAX_NESTING)
        self.assertTrue(ggold.rule_mods_over_budget(self.deep(3)))

    def test_nesting_past_any_recursion_limit_is_refused_not_a_crash(self):
        doc = self.deep(3000)
        record = hostile_record("deep-nesting")
        results = ggold.judge_mods_hostile(record, doc, DESCRIPTOR_SCHEMA)  # must not raise
        by_name = {n.rsplit(" ", 1)[-1]: ok for n, ok, _d in results}
        self.assertTrue(by_name["(schema)"], results)
        self.assertTrue(by_name["(reasons)"], results)
        self.assertTrue(by_name["(semantic)"], results)
        self.assertFalse(ggold.reader_ignoring_mods_accepts(doc, DESCRIPTOR_SCHEMA), "too deep to serialize is too big")

    def test_a_recursive_definition_fed_a_deep_document_is_a_refusal_not_a_crash(self):
        # Detection's own `requireEntry` still recurses; a document nested
        # past Python's limit there must refuse, never take main() down.
        doc = mods_valid()
        node = {"listed": "engine2.dll", "kind": "file"}
        for _ in range(3000):
            node = {"any": [node]}
        doc["rule"][0]["require"].append(node)
        ok, detail = ggold.schema_ok(doc, DESCRIPTOR_SCHEMA)
        self.assertFalse(ok)
        self.assertIn("too deep", detail)


class ModsTemplateReads(unittest.TestCase):
    """Review item 6."""

    def test_the_reversed_golden_passes_with_a_run_that_reads(self):
        doc = mods_hostile("template-reversed")
        self.assertFalse(mods_ok(doc))
        doc["mods"]["loader"][0]["version"]["template"] = "N{1,5}.N{1,3}"
        self.assertTrue(mods_ok(doc))

    def test_a_template_that_does_not_read_never_raises_and_never_holds(self):
        for template in ["N{5,1}", "N{2,1}.N{1,3}", "N{0,3}", "N{1,6}"]:
            with self.subTest(template=template):
                self.assertFalse(ggold.version_holds(template, ">=1", "5.4.23.3"))
                self.assertIsNone(ggold.read_version(template, "5.4.23.3"))


class ModsMarkersAreCounted(unittest.TestCase):
    """Review item 7."""

    def test_the_probes_golden_fits_without_its_markers(self):
        doc = mods_hostile("over-budget-probes")
        self.assertEqual(ggold.mods_cost(doc)["probes"], 9)
        self.assertFalse(ggold.rule_mods_over_budget(doc))
        for loader in doc["mods"]["loader"]:
            del loader["enabled"][0]["marker"]
        self.assertEqual(ggold.mods_cost(doc)["probes"], 6)
        self.assertTrue(ggold.rule_mods_over_budget(doc))


def spec_section(heading: str) -> str:
    text = (ROOT / "spec/games/engine-descriptor-v1.md").read_text(encoding="utf-8")
    start = text.index(heading)
    nxt = text.find("\n### ", start + len(heading))
    return text[start:nxt if nxt != -1 else len(text)]


class ModsPrivacyAndManagersAreStated(unittest.TestCase):
    """Review items 8 and 10: the spec text IS the guarantee here, so the
    canary is the text. Each sink and rule the review named must be there."""

    def test_the_privacy_section_names_every_sink(self):
        s = " ".join(spec_section("### 7.10 Read-only and private").split())
        for needle in ["`link-v1`", "bridge", "plugin host's RPCs", "AI tool", "game integration", "not a log",
                       "`entry` path and the `tell` value", "No download, update check or catalogue request",
                       "never synced", "problem or crash report", "analytics",
                       "Even that line never goes into any log that a problem report attaches"]:
            with self.subTest(needle=needle):
                self.assertIn(needle, s)

    def test_the_manager_section_states_the_structural_rule_and_the_blocklists_limit(self):
        s = " ".join(spec_section("### 7.7 Managers are adapters, never data").split())
        self.assertIn("**The structural rule comes first.**", s)
        self.assertIn("only a list of names", s)
        self.assertIn("`{source}/r2mm/profiles/Default`", s)

    def test_the_blocklists_limit_is_what_the_spec_says_it_is(self):
        # Pinned on purpose: the name rule cannot see an unknown spelling,
        # and the spec says so (§7.7). If this ever turns false, update the
        # spec's sentence with it.
        doc = mods_valid()
        doc["mods"]["loader"][0]["root"] = "{source}/r2mm/profiles/Default"
        self.assertTrue(ggold.rule_mods_manager_as_data(doc))


class ModsReasonsAreAsserted(unittest.TestCase):
    """Review item 9: each hostile golden is refused for exactly its reasons,
    and the reason classifier sees each class on its own."""

    def test_a_wrong_recorded_reason_turns_the_golden_red(self):
        record = hostile_record("path-escape")
        doc = mods_hostile("path-escape")
        self.assertTrue(judged_ok(record, doc))
        record["reasons"] = ["path-invalid"]
        self.assertFalse(judged_ok(record, doc))

    def test_dot_dot_alone_is_an_escape_not_a_trailing_dot(self):
        self.assertEqual(ggold.mods_path_reason("{source}/.."), "path-escapes")
        self.assertEqual(ggold.mods_path_reason("{source}/a/../b."), "path-escapes")
        self.assertEqual(ggold.mods_path_reason("{source}/a."), "path-invalid")

    def test_each_reason_class_is_seen(self):
        def reasons_after(mutate):
            doc = mods_valid()
            mutate(doc["mods"]["loader"][0])
            return ggold.mods_reasons(doc)
        self.assertEqual(ggold.mods_reasons(mods_valid()), set())
        self.assertEqual(reasons_after(lambda l: l.update(root="/etc")), {"path-outside-jail"})
        self.assertEqual(reasons_after(lambda l: l.update(root="{source}/CON")), {"path-invalid"})
        self.assertEqual(reasons_after(lambda l: l.update(source=["steam"])), {"unknown"})
        self.assertEqual(reasons_after(lambda l: l.update(extra=1)), {"unknown"})
        self.assertEqual(reasons_after(lambda l: l.pop("root")), {"shape"})
        self.assertEqual(reasons_after(lambda l: l.update(enabled=[{"format": "file-glob", "glob": "**"}])),
                         {"glob-over-budget"})
        self.assertEqual(reasons_after(lambda l: l.update(version={"pe": "{source}/s2loader/s2loader.dll",
                                                                   "key": ["ProductVersion"], "template": "N{3,1}"})),
                         {"version-invalid"})
        self.assertEqual(ggold.mods_reasons(dict(mods_valid(), mods=[{}])), {"descriptor-invalid"})


class ModsBypassesClosed(unittest.TestCase):
    """ops-42's re-review of a1d096c: the bypasses of the anchor and entry rules."""

    def test_a_short_name_is_never_a_component(self):
        for p in ["{source}/XINPUT~1.DLL", "{source}/PROGRA~1/x.dll", "{source}/BEPINE~1/core/BepInEx.dll"]:
            with self.subTest(p=p):
                self.assertEqual(ggold.mods_path_reason(p), "path-invalid")
        self.assertIsNone(ggold.mods_path_reason("{source}/{project}/Content/Paks/~mods"))
        doc = mods_hostile("short-name")
        self.assertFalse(mods_ok(doc))
        doc["mods"]["loader"][0]["require"][0]["stat"] = "{source}/s2loader/s2loader.dll"
        doc["mods"]["loader"][0]["coexist"][0]["entry"] = "{source}/s2loader/s2loader.dll"
        self.assertTrue(mods_ok(doc))

    def test_the_engines_own_files_anchor_nothing(self):
        doc = builtin_with_mods("unity")
        doc["mods"]["loader"][0]["require"] = [{"stat": "{source}/UnityPlayer.dll", "kind": "file"}]
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc), "UnityPlayer.dll is Unity's detection file")
        doc["mods"]["loader"][0]["require"] = [{"stat": "{source}/x/Assembly-CSharp.dll", "kind": "file"}]
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc), "a detection stat's last component, any folder")
        doc = builtin_with_mods("unreal")
        doc["mods"]["loader"][0]["require"] = [{"stat": "{source}/{project}/Content/Paks/pakchunk0-Windows.pak", "kind": "file"}]
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc), "a `*` in detection's name matches any run")
        doc = mods_hostile("anchor-on-the-engine")
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc))
        doc["mods"]["loader"][0]["require"].append({"stat": "{source}/s2loader/s2loader.dll", "kind": "file"})
        self.assertTrue(ggold.rule_mods_loader_anchor_invalid(doc))

    def test_a_pure_placeholder_detection_name_does_not_refuse_everything(self):
        doc = ggold.load_doc("descriptors/builtin/godot.toml")  # its weak rule tails `{program}`
        self.assertNotIn("*", ggold.detection_patterns(doc))

    def test_an_entry_is_only_a_dll(self):
        for name, ok in [("s2loader.scr", False), ("s2loader.cpl", False), ("s2loader.ocx", False),
                         ("s2loader.DLL", True), ("s2loader.dll", True)]:
            with self.subTest(name=name):
                doc = mods_valid()
                loader = doc["mods"]["loader"][0]
                loader["require"].append({"stat": f"{{source}}/s2loader/{name}", "kind": "file"})
                loader["coexist"] = [{"strategy": "chain", "entry": f"{{source}}/s2loader/{name}"}]
                self.assertEqual(ggold.rule_mods_chain_entry_invalid(doc), ok)

    def test_each_entry_golden_passes_once_the_entry_is_the_loaders_own_dll(self):
        for name in ["chain-entry-on-the-engine", "chain-entry-not-a-dll", "chain-entry-unrecognised",
                     "chain-entry-on-the-program"]:
            with self.subTest(name=name):
                doc = mods_hostile(name)
                self.assertFalse(ggold.rule_mods_chain_entry_invalid(doc))
                doc["mods"]["loader"][0]["coexist"][0]["entry"] = "{source}/s2loader/s2loader.dll"
                self.assertTrue(ggold.rule_mods_chain_entry_invalid(doc))

    def test_via_manager_needs_a_file_anchor(self):
        doc = mods_hostile("root-anchor-via-manager")
        self.assertFalse(ggold.rule_mods_root_anchor_not_passive(doc))
        doc["mods"]["loader"][0]["require"].append({"stat": "{source}/s2loader/s2loader.dll", "kind": "file"})
        self.assertTrue(ggold.rule_mods_root_anchor_not_passive(doc), "file-anchored: may ride a manager")
        self.assertTrue(mods_ok(doc))

    def test_listed_anchors_no_root_and_child_or_stat_does(self):
        doc = mods_hostile("root-anchor-listed")
        self.assertFalse(ggold.rule_mods_loader_anchor_invalid(doc))
        for key in ("child", "stat"):
            with self.subTest(key=key):
                fixed = copy.deepcopy(doc)
                fixed["mods"]["loader"][0]["require"] = [{key: "{source}/s2loader/mods", "kind": "dir"}]
                self.assertTrue(ggold.rule_mods_loader_anchor_invalid(fixed))

    def test_an_operand_must_read_in_its_template(self):
        doc = mods_hostile("versions-unreadable")
        self.assertFalse(ggold.rule_mods_version_unreadable(doc))
        v = doc["mods"]["loader"][0]["version"]
        v["versions"] = ">=a.b"
        self.assertFalse(ggold.rule_mods_version_unreadable(doc))
        v["versions"] = ">=1.2"
        self.assertTrue(ggold.rule_mods_version_unreadable(doc))
        self.assertTrue(mods_ok(doc))

    def test_the_nesting_bound_holds_through_an_unknown_member(self):
        doc = mods_hostile("deep-unknown-member")
        self.assertEqual(ggold.mods_cost(doc)["depth"], 0, "nothing in require is deep")
        self.assertFalse(ggold.rule_mods_over_budget(doc), "the 11-level bound alone refuses it")
        del doc["mods"]["loader"][0]["later"]
        self.assertTrue(ggold.rule_mods_over_budget(doc))


class ModsGoldensEach(unittest.TestCase):
    """Every hostile `mods` golden is refused by exactly the check vectors.json names."""

    def test_each_semantic_golden_breaks_one_rule(self):
        v = json.loads((ggold.DATA / "vectors.json").read_text(encoding="utf-8"))["descriptors"]["mods"]
        rules = set()
        for h in v["hostile"]:
            doc = ggold.load_doc(h["file"])
            with self.subTest(name=h["name"]):
                if h["check"] == "semantic":
                    named = h.get("rules") or [h["rule"]]
                    self.assertEqual(ggold.mods_semantic_problems(doc), named)
                    rules.update(named)
                else:
                    self.assertEqual(ggold.mods_semantic_problems(doc), [])
                    self.assertFalse(ggold.schema_ok(doc.get("mods"), MODS_SCHEMA)[0])
        self.assertEqual(rules, set(ggold.SEMANTIC_MODS_RULES), "one hostile golden per semantic rule")


if __name__ == "__main__":
    unittest.main()
