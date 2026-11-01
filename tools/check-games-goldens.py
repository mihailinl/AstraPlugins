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


# ── content (manifest.md §2.7, merged plan §5.4) ──────────────────────────
# Independent of schemalite and of the launcher's descriptor rules above:
# these need real bytes, not only a parsed TOML/JSON document, so they are
# not expressed as a JSON Schema at all. astra-games-catalogue's
# lib/content.mjs is the other independent implementation of the same rule,
# over a real zip instead of a loose directory; both are pinned against
# testdata/games/content/ (manifest.md §4's exception note).

def _is_zip(b: bytes) -> bool:
    return len(b) >= 4 and b[0:2] == b"PK" and b[2] in (3, 5, 7)


def _is_glb(b: bytes) -> bool:
    return len(b) >= 4 and b[0:4] == b"glTF"


def _is_gltf_text(b: bytes) -> bool:
    return b.lstrip()[:1] == b"{"


def _is_fbx(b: bytes) -> bool:
    return len(b) >= 18 and (b[0:18] == b"Kaydara FBX Binary" or b[0:5] == b"; FBX")


def _is_png(b: bytes) -> bool:
    return b[0:8] == b"\x89PNG\r\n\x1a\n"


def _is_jpg(b: bytes) -> bool:
    return b[0:3] == b"\xff\xd8\xff"


def _is_webp(b: bytes) -> bool:
    return b[0:4] == b"RIFF" and b[8:12] == b"WEBP"


def _is_gif(b: bytes) -> bool:
    return b[0:6] in (b"GIF87a", b"GIF89a")


def _is_ogg(b: bytes) -> bool:
    return b[0:4] == b"OggS"


def _is_wav(b: bytes) -> bool:
    return b[0:4] == b"RIFF" and b[8:12] == b"WAVE"


def _is_mp3(b: bytes) -> bool:
    return b[0:3] == b"ID3" or (len(b) >= 2 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0)


def _is_flac(b: bytes) -> bool:
    return b[0:4] == b"fLaC"


# manifest.md §2.7.1's table, verbatim.
CONTENT_EXT_MAGIC = {
    ".astrapack": _is_zip, ".astrachar": _is_zip,
    ".vrma": _is_glb, ".glb": _is_glb, ".vrm": _is_glb,
    ".gltf": _is_gltf_text,
    ".fbx": _is_fbx,
    ".png": _is_png, ".jpg": _is_jpg, ".jpeg": _is_jpg, ".webp": _is_webp, ".gif": _is_gif,
    ".ogg": _is_ogg, ".wav": _is_wav, ".mp3": _is_mp3, ".flac": _is_flac,
}


def find_content_files(root: pathlib.Path) -> dict[str, bytes]:
    """Every file under `root` whose extension AND magic bytes both say it is
    content-typed (manifest.md §2.7.1), keyed by its path relative to `root`
    (posix-style, matching a [[integration.content]] `path`). The manifest
    file itself is never a content file."""
    out: dict[str, bytes] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name == "astra-gi.toml":
            continue
        sniff = CONTENT_EXT_MAGIC.get(p.suffix.lower())
        if sniff is None:
            continue
        raw = p.read_bytes()
        if sniff(raw[:32]):
            out[p.relative_to(root).as_posix()] = raw
    return out


def content_coverage(manifest: dict, found: dict[str, bytes]) -> dict:
    """manifest.md §2.7.2: every content-typed file covered by exactly one
    [[integration.content]] entry. `found` is as `find_content_files`
    returns it."""
    declared = manifest.get("integration", {}).get("content", [])
    paths = [e.get("path") for e in declared if isinstance(e, dict) and isinstance(e.get("path"), str)]
    seen: set[str] = set()
    dup: set[str] = set()
    for p in paths:
        if p in seen:
            dup.add(p)
        else:
            seen.add(p)
    declared_set = set(paths)
    found_set = set(found.keys())
    return {
        "undeclared": sorted(found_set - declared_set),
        "missing": sorted(declared_set - found_set),
        "duplicates": sorted(dup),
    }


def parse_glb_json_chunk(raw: bytes):
    """The GLB container's first chunk, parsed as JSON, or None when `raw`
    is not a well-formed GLB with a leading JSON chunk."""
    if len(raw) < 20 or raw[0:4] != b"glTF":
        return None
    chunk_len = int.from_bytes(raw[12:16], "little")
    if raw[16:20] != b"JSON":
        return None
    data = raw[20:20 + chunk_len]
    if len(data) < chunk_len:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def extract_vrm_metas(raw: bytes) -> dict:
    """Returns `{"0.x": meta_dict, "1.0": meta_dict}` for WHICHEVER of a
    GLB's extensions.VRM.meta / extensions.VRMC_vrm.meta are present --
    both, when the file carries both, never only the first one found (O-2:
    the earlier version of this function returned on the first match, so a
    file whose VRM 0.x meta allowed and whose VRM 1.0 meta prohibited
    passed the gate outright). Empty when neither is present (not every
    .vrm file carries one, and that is not itself a refusal)."""
    return extract_vrm_metas_doc(parse_glb_json_chunk(raw))


def extract_vrm_metas_doc(doc) -> dict:
    """extract_vrm_metas over an already-parsed glTF JSON document (a GLB's
    JSON chunk or a `.gltf` file's whole text)."""
    if not isinstance(doc, dict):
        return {}
    exts = doc.get("extensions")
    if not isinstance(exts, dict):
        return {}
    out: dict = {}
    vrm0 = exts.get("VRM")
    if isinstance(vrm0, dict) and isinstance(vrm0.get("meta"), dict):
        out["0.x"] = vrm0["meta"]
    vrm1 = exts.get("VRMC_vrm")
    if isinstance(vrm1, dict) and isinstance(vrm1.get("meta"), dict):
        out["1.0"] = vrm1["meta"]
    return out


def _reading(value, allowed, prohibited, default_prohibited=True):
    """One field's reading: "allowed", "prohibited" or "unknown"."""
    if value is None:
        return "prohibited" if default_prohibited else "unknown"
    if not isinstance(value, str):
        return "prohibited"
    if allowed(value):
        return "allowed"
    if value in prohibited:
        return "prohibited"
    return "unknown"


def rule_vrm_licence_refused(vrm_version: str, meta: dict) -> dict:
    """manifest.md §2.7.3's HARD VRM GATE / marketplace legal DRAFT-v3.md
    Part 6 G4, D8 (widened): one meta's verdict, read exactly as the content
    contract's ingest-v1.md §4.2 and astra-companion's `src/vrm/meta.rs`
    (`licence_of`, `redistribution_of`, origin/main 045b0bf) read it, so that
    the games and content gates agree on every file. Each meta gives two
    readings:

      VRM 1.0 `allowRedistribution`: `true` allowed; `false`, absent or not a
        bool (the string "true" included) prohibited.
      VRM 0.x `licenseName`: `CC0` or any token beginning `CC_` allowed;
        `Redistribution_Prohibited`, absent or not a string prohibited;
        `Other` or ANY other token unknown (the terms are elsewhere).
      VRM 1.0 `avatarPermission` / 0.x `allowedUserName`: `everyone` /
        `Everyone` allowed; `onlyAuthor`, `onlySeparatelyLicensedPerson` /
        `OnlyAuthor`, `ExplicitlyLicensedPerson`, absent (the spec default)
        or not a string prohibited; ANY other token unknown.

    The verdict is "prohibited" if either reading is, else "unknown" if
    either is, else "allowed". An unrecognised token is never allowed.
    Returns {"verdict", "refused", "field", "value", "defaulted"}: "field"
    names the reading that decided a prohibited or unknown verdict (the
    redistribution field first), "value" its literal value, and
    "defaulted" whether the field was absent and a spec default decided."""
    if vrm_version == "0.x":
        fields = (
            ("extensions.VRM.meta.licenseName", "licenseName",
             _reading(meta.get("licenseName"), lambda v: v == "CC0" or v.startswith("CC_"), ("Redistribution_Prohibited",))),
            ("extensions.VRM.meta.allowedUserName", "allowedUserName",
             _reading(meta.get("allowedUserName"), lambda v: v == "Everyone", ("OnlyAuthor", "ExplicitlyLicensedPerson"))),
        )
    elif vrm_version == "1.0":
        redist = meta.get("allowRedistribution")
        fields = (
            ("extensions.VRMC_vrm.meta.allowRedistribution", "allowRedistribution",
             "allowed" if redist is True else "prohibited"),
            ("extensions.VRMC_vrm.meta.avatarPermission", "avatarPermission",
             _reading(meta.get("avatarPermission"), lambda v: v == "everyone", ("onlyAuthor", "onlySeparatelyLicensedPerson"))),
        )
    else:
        raise NotImplementedError(vrm_version)
    for wanted in ("prohibited", "unknown"):
        for field, key, reading in fields:
            if reading == wanted:
                return {"verdict": wanted, "refused": wanted == "prohibited", "field": field,
                        "value": meta.get(key), "defaulted": key not in meta}
    return {"verdict": "allowed", "refused": False, "field": None, "value": None, "defaulted": False}


# manifest.md §2.7.3 / legal DRAFT-v3.md G5: kept with the part so the
# install sheet and the public card can show the whole licence line. These
# are the raw keys the file carries -- an absent key's spec default is
# applied only by rule_vrm_licence_refused above, never fabricated here.
# The usage-flag quartet/triple's own defaults (false / "Disallow") are the
# VRM 1.0 meta schema's and UniVRM's own, inferred by symmetry with
# commercialUssageName since astra-companion does not read these flags at
# all yet (src/vrm/meta.rs's module comment) -- display, not this gate's
# refusal, so getting a default display value wrong here is not a safety
# bug, and nothing above substitutes one.
VRM_GATE_FIELDS = {"0.x": ("allowedUserName", "licenseName"), "1.0": ("avatarPermission", "allowRedistribution")}
VRM_USAGE_FIELDS = {
    "0.x": ("violentUssageName", "sexualUssageName", "commercialUssageName"),
    "1.0": ("allowExcessivelyViolentUsage", "allowExcessivelySexualUsage", "allowPoliticalOrReligiousUsage", "allowAntisocialOrHateUsage"),
}

def rule_vrm_conflict(meta0x: dict, meta1_0: dict) -> dict | None:
    """manifest.md §2.7.3 / the content contract's ingest-v1.md §4.2: a file
    carrying BOTH a VRM 0.x and a VRM 1.0 meta is judged on EACH (O-2 -- a
    reader that stops at the first meta it finds would pass a file whose
    0.x meta allows and whose 1.0 meta prohibits). If the two verdicts
    differ -- an unknown against an allowed included -- it is refused as
    `E_CONTENT_LICENCE_CONFLICT`. Usage flags are display, never compared
    here, exactly as the content gate does not compare them.

    Returns the refusal dict (`{"field", "detail"}`) or None when the two
    verdicts agree."""
    v0 = rule_vrm_licence_refused("0.x", meta0x)
    v1 = rule_vrm_licence_refused("1.0", meta1_0)
    if v0["verdict"] != v1["verdict"]:
        side = lambda v: v["verdict"] + (f" ({v['field']})" if v["field"] else "")
        return {"field": "gate verdict", "detail": f"VRM 0.x reads {side(v0)}; VRM 1.0 reads {side(v1)}"}
    return None


AVATAR_EXTENSIONS = ("VRM", "VRMC_vrm")
ANIMATION_EXTENSION = "VRMC_vrm_animation"


def gltf_document(raw: bytes, path: str | None = None):
    """The glTF JSON of a GLB (by its magic, whatever it is called) or of a
    `.gltf` text file, or None for anything else."""
    if raw[:4] == b"glTF":
        return parse_glb_json_chunk(raw)
    if path is not None and path.lower().endswith(".gltf") and _is_gltf_text(raw):
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    return None


def gltf_class(doc) -> str:
    """The content contract's ingest-v1.md §4 classification, by the glTF
    JSON's extensions and never by the file's name: "avatar" when an avatar
    extension (`VRM`, `VRMC_vrm`) appears in `extensions` or
    `extensionsUsed`; "animation" when `VRMC_vrm_animation` does and no
    avatar extension does; "plain" otherwise."""
    names: set[str] = set()
    if isinstance(doc, dict):
        if isinstance(doc.get("extensions"), dict):
            names.update(doc["extensions"])
        if isinstance(doc.get("extensionsUsed"), list):
            names.update(n for n in doc["extensionsUsed"] if isinstance(n, str))
    if any(n in names for n in AVATAR_EXTENSIONS):
        return "avatar"
    if ANIMATION_EXTENSION in names:
        return "animation"
    return "plain"


def part_licence(entry: dict, raw) -> dict:
    """legal DRAFT-v3.md Part 6 G5: the licence_source decision for one
    covered [[integration.content]] entry, given the real bytes at its
    path (or None when nothing covers it). `licence_source` is `"vrm"`
    when readable, recognised VRM meta decided it (allowed or refused),
    `"declared"` when the manifest's own `licence` string is the whole
    licence, and `None` when neither exists -- `E_CONTENT_LICENCE_UNDECLARED`.
    `gate_status` is the VRM gate's own verdict
    ("ok"/"refused"/"conflict"/"unknown"), or None when the gate does not
    apply: not a GLB or `.gltf`, an animation (`VRMC_vrm_animation` with no
    avatar extension), or a plain glTF in a part that is not a character.
    The gate runs on the bytes, never on the name, so a renamed avatar is
    judged as an avatar."""
    path = entry.get("path") if isinstance(entry, dict) else None
    gate_status = None
    vrm_licence = None
    refusal = None
    doc = gltf_document(raw, path if isinstance(path, str) else None) if raw is not None else None
    if doc is not None:
        cls = gltf_class(doc)
        if cls == "avatar" or (cls == "plain" and entry.get("kind") == "character"):
            gate = vrm_gate(raw, path if isinstance(path, str) else None)
            gate_status = gate["status"]
            refusal = gate["refusal"]
            if gate_status != "unknown":
                vrm_licence = gate["vrm_licence"]
    if vrm_licence is not None:
        licence_source = "vrm"
    elif entry.get("licence"):
        licence_source = "declared"
    else:
        licence_source = None
    return {"licence_source": licence_source, "vrm_licence": vrm_licence, "gate_status": gate_status, "refusal": refusal}


def vrm_gate(raw: bytes, path: str | None = None) -> dict:
    """The full G4/G5 verdict for one glTF's bytes (a GLB by its magic, or a
    `.gltf` text file), reading BOTH a VRM 0.x and a VRM 1.0 meta when it
    carries both (O-2). Returns {"status": "ok"|"refused"|"conflict"|"unknown",
    "vrm_licence": {"vrm_version","fields"}|None, "refusal": {...}|None}.
    "unknown" is no VRM meta of either spec, meta that cannot be read, or a
    meta whose verdict is unknown (an unrecognised licence or permission
    token). It is NEVER a refusal: G4 says it is flagged
    (F_CONTENT_VRM_META_UNKNOWN) and passes only with the character checkbox
    and a declared licence (G5); `refusal` then names the deciding field
    when there is one. "conflict" is `E_CONTENT_LICENCE_CONFLICT`
    (`rule_vrm_conflict`) and runs before any single-meta verdict."""
    doc = gltf_document(raw, path)
    metas = extract_vrm_metas_doc(doc)
    if not metas:
        return {"status": "unknown", "vrm_licence": None, "refusal": None}
    if "0.x" in metas and "1.0" in metas:
        conflict = rule_vrm_conflict(metas["0.x"], metas["1.0"])
        if conflict is not None:
            return {"status": "conflict", "vrm_licence": None, "refusal": conflict}
    # Both present and agreeing, or only one present: VRM 1.0 takes display
    # precedence when both exist, the same order astra-companion's own
    # `licence_of` reads them in ("a file carrying both is read as 1.0").
    vrm_version = "1.0" if "1.0" in metas else "0.x"
    meta = metas[vrm_version]
    verdict = rule_vrm_licence_refused(vrm_version, meta)
    fields = {k: meta[k] for k in VRM_GATE_FIELDS[vrm_version] + VRM_USAGE_FIELDS[vrm_version] if k in meta}
    vrm_licence = {"vrm_version": vrm_version, "fields": fields}
    if verdict["verdict"] == "unknown":
        return {"status": "unknown", "vrm_licence": None,
                "refusal": {"field": verdict["field"], "value": verdict["value"], "defaulted": verdict["defaulted"]}}
    if verdict["refused"]:
        refusal = {"field": verdict["field"], "value": verdict["value"], "defaulted": verdict["defaulted"]}
        return {"status": "refused", "vrm_licence": vrm_licence, "refusal": refusal}
    return {"status": "ok", "vrm_licence": vrm_licence, "refusal": None}


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

    # -- content (manifest.md §2.7, merged plan §5.4 / legal DRAFT-v3.md
    # Part 6 G4-G5) -----------------------------------------------------
    if "content" in vectors:
        for v in vectors["content"]["releases"]:
            doc = load_doc(v["manifest"])
            found = find_content_files(DATA / v["dir"])
            cov = content_coverage(doc, found)
            coverage_problems = cov["undeclared"] + cov["missing"] + cov["duplicates"]
            licence_refused = []
            licence_undeclared = []
            for entry in doc.get("integration", {}).get("content", []):
                p = entry.get("path")
                raw = found.get(p) if isinstance(p, str) else None
                if raw is None:
                    continue
                pl = part_licence(entry, raw)
                if pl["gate_status"] in ("refused", "conflict"):
                    licence_refused.append((p, pl["refusal"]["field"]))
                if pl["licence_source"] is None:
                    licence_undeclared.append(p)
            refused = bool(coverage_problems) or bool(licence_refused) or bool(licence_undeclared)
            report(
                f"content/releases/{v['name']}",
                refused == (v["verdict"] == "refuse"),
                f"coverage={coverage_problems} licence_refused={licence_refused} licence_undeclared={licence_undeclared}",
            )

        for v in vectors["content"]["vrm_gate"]:
            raw = (DATA / v["file"]).read_bytes()
            gate = vrm_gate(raw)
            if v["verdict"] == "accept":
                report(f"content/vrm/{v['name']}", gate["status"] == "ok")
            elif v["verdict"] == "unknown":
                ok = gate["status"] == "unknown" and gate["vrm_licence"] is None
                if "field" in v:
                    ok = ok and gate["refusal"] is not None and gate["refusal"]["field"] == v["field"] \
                        and gate["refusal"]["value"] == v["value"]
                else:
                    ok = ok and gate["refusal"] is None
                report(f"content/vrm/{v['name']}", ok, json.dumps(gate))
            elif v["verdict"] == "conflict":
                ok = gate["status"] == "conflict" and gate["refusal"]["field"] == v["field"]
                report(f"content/vrm/{v['name']}", ok, json.dumps(gate))
            else:
                ok = (
                    gate["status"] == "refused"
                    and gate["refusal"]["field"] == v["field"]
                    and gate["refusal"]["value"] == v["value"]
                    and gate["refusal"]["defaulted"] == v.get("defaulted", False)
                )
                report(f"content/vrm/{v['name']}", ok, json.dumps(gate))

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
