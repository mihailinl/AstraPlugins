#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
"""Every golden in testdata/games/ validates or fails exactly as its name
says and as testdata/games/vectors.json records.

This is the spec-side half of canaries K11 and K17
(dev/game-integrations-plan-merged.md §3.3, in astra-plugins-ops): K17 is
"S's descriptor goldens are accepted or refused by the launcher parser
exactly as labelled" — the half that runs without a launcher checkout is
exactly the schema/semantic check below, over the same goldens the
launcher's own tests are meant to pin by this repository's SHA. K11 is
link-v1's framing matching astra-companion/docs/bridge.md; the half that
lives here is link-v1-message.schema.json validating against
testdata/games/link/transcript.json — self-consistency within this repo,
not a cross-repo fetch.

Three kinds of check, named per golden in vectors.json's "check" field:
  schema    spec/games/schemas/*.json alone (tools/schemalite.py) decides it.
  semantic  the schema accepts it (by design — the attack is not a parse
            error) and a small rule named here, that a JSON Schema cannot
            express, decides it instead.
  pinned    this repository can only assert the golden's schema verdict;
            the real refusal needs a live folder tree, a real zip, or the
            signed catalogue's ownership table. vectors.json's
            "enforced_by" says whose test that is.

Run: python3 tools/check-games-goldens.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" / "games"
DATA = ROOT / "testdata" / "games"

sys.path.insert(0, str(ROOT / "tools"))
import schemalite  # noqa: E402


# ── loading ──────────────────────────────────────────────────────────────

def load_schema(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def load_doc(rel: str):
    path = DATA / rel
    if path.suffix == ".toml":
        with path.open("rb") as f:
            return tomllib.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def schema_ok(doc, schema: dict) -> tuple[bool, str]:
    try:
        schemalite.validate(doc, schema)
        return True, ""
    except schemalite.SchemaError as e:
        return False, str(e)


# ── the reserved list, read once, the same file the launcher mirrors ─────

def load_reserved() -> dict:
    text = (SPEC / "reserved.yaml").read_text(encoding="utf-8")
    out: dict = {"engine_codes": [], "integration_id_reserved_prefixes": [],
                 "integration_name_reserved_substrings": [], "profile_file_names": []}
    current = None
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m and not line.startswith("  "):
            current = m.group(1)
            continue
        m = re.match(r'^\s*-\s*"?([^"\n]+?)"?\s*(#.*)?$', line)
        if m and current in out:
            out[current].append(m.group(1))
    return out


RESERVED = load_reserved()


# ── semantic rules (what a JSON Schema cannot express) ───────────────────

def rule_engine_undeclared(manifest: dict) -> bool:
    """True = OK. False = violates engine-undeclared (manifest.md §2.1)."""
    eng = manifest.get("integration", {}).get("engine")
    if eng is None:
        return True
    codes = set(eng.get("engine", {}).get("codes", {}).keys())
    target_engine = manifest.get("target", {}).get("engine")
    return target_engine in codes


def rule_engine_code_reserved(codes) -> bool:
    """True = OK. codes: iterable of engine codes this document claims."""
    return not (set(codes) & set(RESERVED["engine_codes"]))


def rule_loader_policy_conflict(manifest: dict) -> bool:
    loader = manifest.get("integration", {}).get("loader", {})
    proxies = set(loader.get("proxies", []))
    keep = set(loader.get("keep_if_present", []))
    return not (proxies & keep)


def rule_capability_undeclared(manifest: dict) -> bool:
    uses_bridge_token = any(
        "${bridge_token}" in str(v)
        for cw in manifest.get("config_writes", [])
        for v in cw.get("set", {}).values()
    )
    if not uses_bridge_token:
        return True
    companion = manifest.get("integration", {}).get("capabilities", {}).get("companion", [])
    return "presentation" in companion


def rule_reserved_id(manifest: dict) -> bool:
    iid = manifest.get("integration", {}).get("id", "")
    return not any(iid.startswith(p) for p in RESERVED["integration_id_reserved_prefixes"])


def rule_reserved_name(manifest: dict) -> bool:
    name = manifest.get("integration", {}).get("name", "")
    low = name.lower()
    return not any(sub.lower() in low for sub in RESERVED["integration_name_reserved_substrings"])


_UBIQUITOUS = [re.compile(p, re.I) for p in (
    r"^steam_api.*\.dll$", r"^vcruntime.*\.dll$", r"^d3dcompiler_.*\.dll$", r"^msvcp.*\.dll$",
)]


def _is_valid_anchor(name: str) -> bool:
    stripped = re.sub(r"\{[^}]+\}", "", name)
    if "*" in stripped or not stripped:
        return False
    return not any(p.match(stripped) for p in _UBIQUITOUS)


def rule_descriptor_anchor_invalid(descriptor: dict) -> bool:
    """True = at least one rule has a valid top-level literal anchor
    (engine-descriptor-v1.md §2.4). A per-rule, first-party-exemption-aware
    version of this check is lane L's evaluator's job (§2.6); this is the
    descriptor-wide mechanical approximation a pure spec check can do."""
    for rule in descriptor.get("rule", []):
        for entry in rule.get("require", []):
            if "listed" in entry and _is_valid_anchor(entry["listed"]):
                return True
    return False


def rule_engine_code_taken(claimant: dict, prior_owner: dict) -> bool:
    """True = OK. False = claimant repeats a code prior_owner already claims."""
    def codes_of(doc):
        eng = doc.get("integration", {}).get("engine") or (doc if "engine" in doc else None)
        if eng is None:
            return set()
        return set(eng.get("engine", {}).get("codes", {}).keys())

    return not (codes_of(claimant) & codes_of(prior_owner) - set(RESERVED["engine_codes"]))


def rule_issued_at_too_far_ahead(doc: dict, reference_now: int) -> bool:
    """games-index-v1.md §1: refused when issued_at is >1 day ahead of the
    client's own clock. reference_now stands in for that clock, fixed at
    valid-index.json's own issued_at so the goldens compare without
    depending on wall-clock time."""
    return doc["issued_at"] <= reference_now + 86400


def rule_expiry_span_too_long(doc: dict) -> bool:
    return (doc["expires_at"] - doc["issued_at"]) <= 8 * 86400


def rule_security_requires_revoke(doc: dict) -> bool:
    return all(row["act"] == "revoke" for row in doc["rows"] if row["reason_code"] == "security")


SEMANTIC_MANIFEST_RULES = {
    "engine-undeclared": rule_engine_undeclared,
    "loader-policy-conflict": rule_loader_policy_conflict,
    "capability-undeclared": rule_capability_undeclared,
    "reserved-id": rule_reserved_id,
    "reserved-name": rule_reserved_name,
}


# ── the runner ─────────────────────────────────────────────────────────

def main() -> int:
    vectors = json.loads((DATA / "vectors.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    checked = 0

    def report(name, ok, detail=""):
        nonlocal checked
        checked += 1
        print(("ok   " if ok else "FAIL ") + name + (f" — {detail}" if detail and not ok else ""))
        if not ok:
            failures.append(name)

    # -- manifests --------------------------------------------------------
    manifest_schema = load_schema(vectors["manifests"]["schema"])
    for v in vectors["manifests"]["valid"]:
        doc = load_doc(v["file"])
        ok, detail = schema_ok(doc, manifest_schema)
        report(f"manifest/valid/{v['name']}", ok == (v["verdict"] == "accept"), detail)

    for v in vectors["manifests"]["invalid"]:
        doc = load_doc(v["file"])
        sok, detail = schema_ok(doc, manifest_schema)
        if v["check"] == "schema":
            report(f"manifest/invalid/{v['name']}", sok is False, detail)
        else:
            if v["rule"] == "engine-code-reserved":
                eng = doc.get("integration", {}).get("engine", {})
                semantic_ok = rule_engine_code_reserved(eng.get("engine", {}).get("codes", {}).keys())
            else:
                semantic_ok = SEMANTIC_MANIFEST_RULES[v["rule"]](doc)
            report(
                f"manifest/invalid/{v['name']}",
                sok is True and semantic_ok is False,
                f"schema_ok={sok} semantic_ok={semantic_ok}",
            )

    # -- descriptors --------------------------------------------------------
    descriptor_schema = load_schema(vectors["descriptors"]["schema"])
    for v in vectors["descriptors"]["builtin"]:
        doc = load_doc(v["file"])
        ok, detail = schema_ok(doc, descriptor_schema)
        report(f"descriptor/builtin/{v['name']}", ok == (v["verdict"] == "accept"), detail)

    by_name = {v["name"]: v for v in vectors["descriptors"]["hostile"]}
    for v in vectors["descriptors"]["hostile"]:
        doc = load_doc(v["file"])
        sok, detail = schema_ok(doc, descriptor_schema)
        report(f"descriptor/hostile/{v['name']} (schema)", sok == (v["schema_verdict"] == "accept"), detail)
        if v["check"] == "schema":
            continue  # already the whole verdict
        if v["check"] == "pinned":
            # This repository asserts only the schema half; the semantic
            # half genuinely needs a live folder tree or the signed
            # catalogue, named in "enforced_by".
            continue
        if v["rule"] == "engine-code-reserved":
            codes = doc.get("engine", {}).get("codes", {}).keys()
            semantic_ok = rule_engine_code_reserved(codes)
        elif v["rule"] == "descriptor-anchor-invalid":
            semantic_ok = rule_descriptor_anchor_invalid(doc)
        elif v["rule"] == "engine-code-taken":
            prior = load_doc(v["paired_with"])
            semantic_ok = rule_engine_code_taken(doc, prior)
        else:
            raise NotImplementedError(v["rule"])
        report(f"descriptor/hostile/{v['name']} (semantic)", semantic_ok is False)

    # -- index --------------------------------------------------------------
    index_schema = load_schema(vectors["index"]["schema"])
    for v in vectors["index"]["valid"]:
        doc = load_doc(v["file"])
        ok, detail = schema_ok(doc, index_schema)
        report(f"index/valid/{v['name']}", ok == (v["verdict"] == "accept"), detail)
    reference_now = load_doc(vectors["index"]["valid"][0]["file"])["issued_at"]

    for v in vectors["index"]["invalid"]:
        doc = load_doc(v["file"])
        sok, detail = schema_ok(doc, index_schema)
        if v["check"] == "schema":
            report(f"index/invalid/{v['name']}", sok is False, detail)
        else:
            if v["rule"] == "issued-at-too-far-ahead":
                semantic_ok = rule_issued_at_too_far_ahead(doc, reference_now)
            elif v["rule"] == "expiry-span-too-long":
                semantic_ok = rule_expiry_span_too_long(doc)
            else:
                raise NotImplementedError(v["rule"])
            report(f"index/invalid/{v['name']}", sok is True and semantic_ok is False)

    # -- withdrawn ------------------------------------------------------------
    withdrawn_schema = load_schema(vectors["withdrawn"]["schema"])
    for v in vectors["withdrawn"]["valid"]:
        doc = load_doc(v["file"])
        ok, detail = schema_ok(doc, withdrawn_schema)
        report(f"withdrawn/valid/{v['name']}", ok == (v["verdict"] == "accept"), detail)

    for v in vectors["withdrawn"]["invalid"]:
        doc = load_doc(v["file"])
        sok, detail = schema_ok(doc, withdrawn_schema)
        if v["check"] == "schema":
            report(f"withdrawn/invalid/{v['name']}", sok is False, detail)
        else:
            semantic_ok = rule_security_requires_revoke(doc)
            report(f"withdrawn/invalid/{v['name']}", sok is True and semantic_ok is False)

    # -- link -------------------------------------------------------------
    message_schema = load_schema(vectors["link"]["message_schema"])
    transcript = load_doc(vectors["link"]["transcript"]["file"])
    all_msgs_ok = True
    for i, msg in enumerate(transcript["messages"]):
        ok, detail = schema_ok(msg, message_schema)
        if not ok:
            all_msgs_ok = False
            print(f"  transcript message {i} ({msg.get('t')}): {detail}")
    report("link/transcript", all_msgs_ok == (vectors["link"]["transcript"]["verdict"] == "accept"))

    profile_schema = load_schema(vectors["link"]["data_schema_profile"])
    for v in vectors["link"]["data_schemas"]["valid"]:
        doc = load_doc(v["file"])
        ok, detail = schema_ok(doc, profile_schema)
        report(f"link/data-schema/valid/{v['name']}", ok == (v["verdict"] == "accept"), detail)
    for v in vectors["link"]["data_schemas"]["invalid"]:
        doc = load_doc(v["file"])
        ok, detail = schema_ok(doc, profile_schema)
        report(f"link/data-schema/invalid/{v['name']}", ok is False, detail)

    print(f"\n{checked} goldens checked, {len(failures)} failed.")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("check-games-goldens: all checks pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
